import Core
import Foundation
import Networking
import Observation
import Persistence

@Observable
@MainActor
public final class SessionViewModel {
    public private(set) var isAuthenticated = false
    public private(set) var isBusy = false
    public private(set) var accountID: Int64?
    public private(set) var email = ""
    public var errorMessage: String?

    private let api: APIClient
    private let keychain: KeychainTokenStore
    private var rotationTask: Task<Void, Never>?

    public init(api: APIClient, keychain: KeychainTokenStore) {
        self.api = api
        self.keychain = keychain
    }

    public func restore() async {
        do {
            guard let saved = try await keychain.load() else { return }
            await api.install(accessToken: saved.accessToken, refreshToken: saved.refreshToken)
            if saved.expiresAt <= .now.addingTimeInterval(60) {
                let updated = try await api.refreshSession()
                try await keychain.save(SessionTokens(accessToken: updated.accessToken,
                    refreshToken: updated.refreshToken,
                    expiresAt: .now.addingTimeInterval(TimeInterval(updated.expiresIn)), accountID: saved.accountID))
            }
            accountID = saved.accountID
            isAuthenticated = true
        } catch {
            try? await keychain.delete()
            await api.clearTokens()
        }
    }

    public func observeTokenRotation() {
        guard rotationTask == nil else { return }
        rotationTask = Task { [weak self] in
            guard let self else { return }
            let updates = await api.tokenUpdates()
            for await pair in updates {
                guard !Task.isCancelled else { break }
                await persistRotatedTokens(pair)
            }
        }
    }

    public func login(email: String, password: String) async {
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            let tokens = try await api.login(email: email, password: password)
            let availableAccounts = try await api.accounts()
            guard let accountID = tokens.accountID ?? availableAccounts.first?.id else {
                throw SessionError.noPaperAccount
            }
            self.email = email
            self.accountID = accountID
            try await keychain.save(SessionTokens(accessToken: tokens.accessToken, refreshToken: tokens.refreshToken,
                expiresAt: .now.addingTimeInterval(TimeInterval(tokens.expiresIn)), accountID: accountID))
            isAuthenticated = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func register(email: String, password: String) async {
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            let tokens = try await api.register(email: email, password: password)
            guard let accountID = tokens.accountID else { throw SessionError.noPaperAccount }
            self.email = email
            self.accountID = accountID
            try await keychain.save(SessionTokens(accessToken: tokens.accessToken, refreshToken: tokens.refreshToken,
                expiresAt: .now.addingTimeInterval(TimeInterval(tokens.expiresIn)), accountID: accountID))
            isAuthenticated = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func loginWithApple(identityToken: String) async {
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            let tokens = try await api.signInWithApple(identityToken: identityToken)
            let availableAccounts = try await api.accounts()
            guard let accountID = tokens.accountID ?? availableAccounts.first?.id else {
                throw SessionError.noPaperAccount
            }
            self.accountID = accountID
            self.email = "Apple account"
            try await keychain.save(SessionTokens(accessToken: tokens.accessToken, refreshToken: tokens.refreshToken,
                expiresAt: .now.addingTimeInterval(TimeInterval(tokens.expiresIn)), accountID: accountID))
            isAuthenticated = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func logout() async {
        try? await api.logout()
        await api.clearTokens()
        try? await keychain.delete()
        isAuthenticated = false
        accountID = nil
        rotationTask?.cancel()
        rotationTask = nil
    }

    private func persistRotatedTokens(_ pair: TokenPair) async {
        guard let accountID else { return }
        try? await keychain.save(SessionTokens(accessToken: pair.accessToken, refreshToken: pair.refreshToken,
            expiresAt: .now.addingTimeInterval(TimeInterval(pair.expiresIn)), accountID: accountID))
    }
}

private enum SessionError: LocalizedError {
    case noPaperAccount
    var errorDescription: String? { "No paper trading account is available for this login." }
}
