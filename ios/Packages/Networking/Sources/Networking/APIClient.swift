import Core
import Foundation

public enum APIError: Error, Sendable, Equatable {
    case invalidResponse
    case httpStatus(Int, String)
    case notAuthenticated
}

public struct APIConfiguration: Sendable {
    public let baseURL: URL
    public let certificatePins: Set<String>

    public init(baseURL: URL, certificatePins: Set<String> = []) {
        self.baseURL = baseURL
        self.certificatePins = certificatePins
    }
}

public actor APIClient {
    private let configuration: APIConfiguration
    private let session: URLSession
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    private var accessToken: String?
    private var refreshToken: String?
    private var tokenContinuations: [UUID: AsyncStream<TokenPair>.Continuation] = [:]

    public init(configuration: APIConfiguration) {
        self.configuration = configuration
        self.session = URLSession(configuration: .ephemeral,
                                  delegate: CertificatePinningDelegate(pins: configuration.certificatePins),
                                  delegateQueue: nil)
    }

    public func install(tokens: TokenPair) {
        accessToken = tokens.accessToken
        refreshToken = tokens.refreshToken
        tokenContinuations.values.forEach { $0.yield(tokens) }
    }

    public func install(accessToken: String, refreshToken: String) {
        self.accessToken = accessToken
        self.refreshToken = refreshToken
    }

    public func bearerToken() -> String? { accessToken }

    public func tokenUpdates() -> AsyncStream<TokenPair> {
        let id = UUID()
        let pair = AsyncStream<TokenPair>.makeStream(bufferingPolicy: .bufferingNewest(1))
        tokenContinuations[id] = pair.continuation
        pair.continuation.onTermination = { @Sendable [weak self] _ in
            Task { await self?.removeTokenContinuation(id) }
        }
        return pair.stream
    }

    @discardableResult
    public func refreshSession() async throws -> TokenPair {
        guard let refreshToken else { throw APIError.notAuthenticated }
        return try await rotate(refreshToken: refreshToken)
    }

    public func makeWebSocketURL(path: String) -> URL {
        var components = URLComponents(url: configuration.baseURL.appending(path: path), resolvingAgainstBaseURL: false)!
        components.scheme = components.scheme == "https" ? "wss" : "ws"
        return components.url!
    }

    public func makeWebSocketTask(path: String) -> URLSessionWebSocketTask {
        session.webSocketTask(with: makeWebSocketURL(path: path))
    }

    public func clearTokens() {
        accessToken = nil
        refreshToken = nil
    }

    public func login(email: String, password: String) async throws -> TokenPair {
        let payload = LoginPayload(email: email, password: password)
        let tokens: TokenPair = try await send(path: "/v1/auth/login", method: "POST", body: encoder.encode(payload), authenticated: false)
        install(tokens: tokens)
        return tokens
    }

    public func register(email: String, password: String) async throws -> TokenPair {
        let payload = LoginPayload(email: email, password: password)
        let tokens: TokenPair = try await send(path: "/v1/auth/register", method: "POST", body: encoder.encode(payload),
                                                authenticated: false, acceptedStatuses: [200, 201])
        install(tokens: tokens)
        return tokens
    }

    public func signInWithApple(identityToken: String) async throws -> TokenPair {
        let payload = AppleLoginPayload(identityToken: identityToken)
        let tokens: TokenPair = try await send(path: "/v1/auth/apple", method: "POST",
            body: encoder.encode(payload), authenticated: false)
        install(tokens: tokens)
        return tokens
    }

    public func symbols() async throws -> [SymbolDTO] {
        let response: SymbolsResponse = try await send(path: "/v1/symbols", method: "GET")
        return response.symbols
    }

    public func accounts() async throws -> [AccountDTO] {
        let response: AccountsResponse = try await send(path: "/v1/accounts", method: "GET")
        return response.accounts
    }

    public func logout() async throws {
        guard let refreshToken else { clearTokens(); return }
        let payload = RefreshPayload(refreshToken: refreshToken)
        let _: LogoutResponse = try await send(path: "/v1/auth/logout", method: "POST",
                                               body: encoder.encode(payload), authenticated: false)
        clearTokens()
    }

    public func candles(symbol: String, intervalSeconds: Int = 60, limit: Int = 200) async throws -> [CandleDTO] {
        var components = URLComponents()
        components.path = "/v1/candles/\(symbol)"
        components.queryItems = [URLQueryItem(name: "interval_seconds", value: String(intervalSeconds)),
                                 URLQueryItem(name: "limit", value: String(limit))]
        let response: CandlesResponse = try await send(path: components.string ?? components.path, method: "GET")
        return response.candles
    }

    public func book(symbol: String) async throws -> BookSnapshotDTO {
        try await send(path: "/v1/market/\(symbol)/book", method: "GET")
    }

    public func orders(accountID: Int64) async throws -> [OrderDTO] {
        let response: OrdersResponse = try await send(path: "/v1/accounts/\(accountID)/orders", method: "GET")
        return response.orders
    }

    public func positions(accountID: Int64) async throws -> [PositionDTO] {
        let response: PositionsResponse = try await send(path: "/v1/accounts/\(accountID)/positions", method: "GET")
        return response.positions
    }

    public func deleteAccount() async throws {
        struct Confirmation: Encodable, Sendable { let confirmation = "DELETE" }
        let _: DeleteResponse = try await send(path: "/v1/account", method: "DELETE",
                                               body: encoder.encode(Confirmation()))
        clearTokens()
    }

    public func placeOrder(accountID: Int64, order: OrderRequestDTO, idempotencyKey: String) async throws -> OrderDTO {
        try await send(path: "/v1/accounts/\(accountID)/orders", method: "POST", body: encoder.encode(order),
                       headers: ["Idempotency-Key": idempotencyKey], acceptedStatuses: [200, 201])
    }

    public func cancelOrder(accountID: Int64, orderID: Int64) async throws -> OrderDTO {
        try await send(path: "/v1/accounts/\(accountID)/orders/\(orderID)/cancel", method: "POST")
    }

    public func replaceOrder(accountID: Int64, orderID: Int64, order: OrderRequestDTO,
                             idempotencyKey: String) async throws -> OrderDTO {
        let response: ReplaceResponse = try await send(path: "/v1/accounts/\(accountID)/orders/\(orderID)/replace", method: "POST",
            body: encoder.encode(order), headers: ["Idempotency-Key": idempotencyKey], acceptedStatuses: [200, 201])
        return response.replacement
    }

    private func send<Response: Decodable & Sendable>(
        path: String, method: String, body: Data? = nil,
        headers: [String: String] = [:], authenticated: Bool = true,
        acceptedStatuses: Set<Int> = [200]
    ) async throws -> Response {
        var request = URLRequest(url: configuration.baseURL.appending(path: path))
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        headers.forEach { request.setValue($1, forHTTPHeaderField: $0) }
        request.httpBody = body
        if authenticated {
            guard let accessToken else { throw APIError.notAuthenticated }
            request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        }
        let retryableSubmission = method == "POST" && path.hasSuffix("/orders") && headers["Idempotency-Key"] != nil
        let mayRetry = method == "GET" || retryableSubmission
        for attempt in 0..<3 {
            do {
                let (data, response) = try await session.data(for: request)
                guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
                if acceptedStatuses.contains(http.statusCode) {
                    return try decoder.decode(Response.self, from: data)
                }
                if http.statusCode == 401, authenticated, let refreshToken {
                    _ = try await rotate(refreshToken: refreshToken)
                    request.setValue("Bearer \(accessToken ?? "")", forHTTPHeaderField: "Authorization")
                    continue
                }
                let errorText = String(data: data, encoding: .utf8) ?? "Request failed"
                if (500...599).contains(http.statusCode), mayRetry, attempt < 2 {
                    try await Task.sleep(for: .milliseconds(250 * (1 << attempt)))
                    continue
                }
                throw APIError.httpStatus(http.statusCode, errorText)
            } catch let error as APIError {
                throw error
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                guard mayRetry, attempt < 2 else { throw error }
                try await Task.sleep(for: .milliseconds(250 * (1 << attempt)))
            }
        }
        throw APIError.invalidResponse
    }

    private func rotate(refreshToken: String) async throws -> TokenPair {
        let body = RefreshPayload(refreshToken: refreshToken)
        let tokens: TokenPair = try await send(path: "/v1/auth/refresh", method: "POST", body: encoder.encode(body),
                                                authenticated: false)
        accessToken = tokens.accessToken
        self.refreshToken = tokens.refreshToken
        tokenContinuations.values.forEach { $0.yield(tokens) }
        return tokens
    }

    private func removeTokenContinuation(_ id: UUID) { tokenContinuations[id] = nil }
}

private struct LoginPayload: Encodable, Sendable { let email: String; let password: String }
private struct AppleLoginPayload: Encodable, Sendable { let identityToken: String; enum CodingKeys: String, CodingKey { case identityToken = "identity_token" } }
private struct RefreshPayload: Encodable, Sendable { let refreshToken: String; enum CodingKeys: String, CodingKey { case refreshToken = "refresh_token" } }
private struct SymbolsResponse: Decodable, Sendable { let symbols: [SymbolDTO] }
private struct AccountsResponse: Decodable, Sendable { let accounts: [AccountDTO] }
private struct CandlesResponse: Decodable, Sendable { let candles: [CandleDTO] }
private struct OrdersResponse: Decodable, Sendable { let orders: [OrderDTO] }
private struct PositionsResponse: Decodable, Sendable { let positions: [PositionDTO] }
private struct ReplaceResponse: Decodable, Sendable { let replacement: OrderDTO }
private struct LogoutResponse: Decodable, Sendable { let ok: Bool }
private struct DeleteResponse: Decodable, Sendable { let deleted: Bool }
