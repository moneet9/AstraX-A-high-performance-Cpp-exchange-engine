import Core
import Foundation
import Networking

public protocol TradingAPI: Sendable {
    func placeOrder(accountID: Int64, order: OrderRequestDTO, idempotencyKey: String) async throws -> OrderDTO
    func cancelOrder(accountID: Int64, orderID: Int64) async throws -> OrderDTO
    func orders(accountID: Int64) async throws -> [OrderDTO]
}

extension APIClient: TradingAPI {}

public actor OrderManager {
    private let api: any TradingAPI
    private var states: [String: OrderStateSnapshot] = [:]
    private var appliedExecutionIDs: Set<Int64> = []
    private var appliedExecutionOrder: [Int64] = []
    private var continuations: [UUID: AsyncStream<[OrderStateSnapshot]>.Continuation] = [:]

    public init(api: any TradingAPI) { self.api = api }

    public func updates() -> AsyncStream<[OrderStateSnapshot]> {
        let id = UUID()
        let pair = AsyncStream<[OrderStateSnapshot]>.makeStream(bufferingPolicy: .bufferingNewest(1))
        continuations[id] = pair.continuation
        pair.continuation.yield(sortedStates())
        pair.continuation.onTermination = { @Sendable [weak self] _ in
            Task { await self?.removeContinuation(id) }
        }
        return pair.stream
    }

    public func submit(accountID: Int64, request: OrderRequestDTO, tickSize: Int64,
                       idempotencyKey: String = UUID().uuidString.lowercased()) async throws -> OrderStateSnapshot {
        try Self.validate(request, tickSize: tickSize)
        let key = idempotencyKey
        var machine = OrderStateMachine()
        try machine.transition(to: .submitting)
        let clientID = key
        states[clientID] = OrderStateSnapshot(id: clientID, serverID: nil, request: request, lifecycle: .submitting)
        publish()
        do {
            let response = try await api.placeOrder(accountID: accountID, order: request, idempotencyKey: key)
            let next: OrderLifecycle = switch response.status.lowercased() {
            case "filled": .filled
            case "partially_filled": .partiallyFilled
            case "rejected": .rejected
            default: .accepted
            }
            try machine.transition(to: next)
            let updated = OrderStateSnapshot(id: clientID, serverID: response.id, request: request,
                                             lifecycle: next, filledQuantity: response.filledQuantity)
            states[clientID] = updated
            publish()
            return updated
        } catch {
            try? machine.transition(to: .rejected)
            let failed = OrderStateSnapshot(id: clientID, serverID: nil, request: request,
                                            lifecycle: .rejected, reason: String(describing: error))
            states[clientID] = failed
            publish()
            throw error
        }
    }

    public func cancel(accountID: Int64, clientID: String) async throws {
        guard let state = states[clientID], let orderID = state.serverID else { return }
        guard state.lifecycle == .accepted || state.lifecycle == .partiallyFilled else { return }
        var machine = OrderStateMachine(state: state.lifecycle)
        try machine.transition(to: .cancelPending)
        states[clientID] = OrderStateSnapshot(id: clientID, serverID: orderID, request: state.request,
                                               lifecycle: .cancelPending, filledQuantity: state.filledQuantity)
        publish()
        do {
            let response = try await api.cancelOrder(accountID: accountID, orderID: orderID)
            let next: OrderLifecycle = response.status == "cancelled" ? .cancelled : .filled
            try machine.transition(to: next)
            states[clientID] = OrderStateSnapshot(id: clientID, serverID: orderID, request: state.request,
                                                   lifecycle: next, filledQuantity: response.filledQuantity)
            publish()
        } catch {
            states[clientID] = state
            publish()
            throw error
        }
    }

    public func load(accountID: Int64) async throws -> [OrderStateSnapshot] {
        let records = try await api.orders(accountID: accountID)
        let serverIDs = Set(records.map(\.id))
        states = states.filter { _, state in
            guard let serverID = state.serverID else { return true }
            return !serverIDs.contains(serverID)
        }
        for order in records {
            let lifecycle: OrderLifecycle = switch order.status.lowercased() {
            case "filled": .filled
            case "partially_filled": .partiallyFilled
            case "cancelled": .cancelled
            case "rejected": .rejected
            case "replaced": .replaced
            default: .accepted
            }
            let request = OrderRequestDTO(symbol: order.symbol, side: order.side,
                type: OrderKind(rawValue: order.type) ?? .limit, quantity: order.quantity,
                priceTicks: order.priceTicks, stopPriceTicks: order.stopPriceTicks,
                pegOffsetTicks: order.pegOffsetTicks, tif: TimeInForce(rawValue: order.tif) ?? .gtc)
            let state = OrderStateSnapshot(id: "server-\(order.id)", serverID: order.id, request: request,
                                           lifecycle: lifecycle, filledQuantity: order.filledQuantity)
            states[state.id] = state
        }
        publish()
        return sortedStates()
    }

    public func snapshot() -> [OrderStateSnapshot] { sortedStates() }

    public func apply(_ event: PrivateExecutionEvent) {
        for fill in event.fills {
            if let executionID = fill.executionID {
                guard appliedExecutionIDs.insert(executionID).inserted else { continue }
                appliedExecutionOrder.append(executionID)
                if appliedExecutionOrder.count > 4_096 {
                    appliedExecutionIDs.remove(appliedExecutionOrder.removeFirst())
                }
            }
            guard let entry = states.first(where: { $0.value.serverID == fill.orderID }) else { continue }
            let old = entry.value
            let reportedFilled = fill.filledQuantity ?? (old.filledQuantity + fill.quantity)
            let filled = min(old.request.quantity, max(old.filledQuantity, reportedFilled))
            let lifecycle: OrderLifecycle = filled >= old.request.quantity ? .filled : .partiallyFilled
            states[entry.key] = OrderStateSnapshot(id: old.id, serverID: old.serverID,
                request: old.request, lifecycle: lifecycle, filledQuantity: filled)
        }
        publish()
    }

    public static func validate(_ request: OrderRequestDTO, tickSize: Int64) throws {
        guard request.quantity > 0 else { throw ValidationError.invalidQuantity }
        if [.limit, .stopLimit, .iceberg].contains(request.type),
           request.priceTicks <= 0 || request.priceTicks % max(1, tickSize) != 0 {
            throw ValidationError.invalidPrice
        }
        if [.stop, .stopLimit].contains(request.type),
           request.stopPriceTicks <= 0 || request.stopPriceTicks % max(1, tickSize) != 0 {
            throw ValidationError.invalidStopPrice
        }
        if request.type == .iceberg && !(0 < request.visibleQuantity && request.visibleQuantity < request.quantity) {
            throw ValidationError.invalidVisibleQuantity
        }
    }

    private func sortedStates() -> [OrderStateSnapshot] {
        states.values.sorted { $0.id < $1.id }
    }

    private func publish() {
        let value = sortedStates()
        continuations.values.forEach { $0.yield(value) }
    }

    private func removeContinuation(_ id: UUID) { continuations[id] = nil }
}

public enum ValidationError: Error, Sendable, Equatable {
    case invalidQuantity, invalidPrice, invalidStopPrice, invalidVisibleQuantity
}
