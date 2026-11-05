import Core
import Foundation

public enum OrderLifecycle: String, Sendable, Equatable {
    case draft, submitting, accepted, partiallyFilled, filled, cancelPending, cancelled, rejected, replaced
}

public struct OrderStateSnapshot: Sendable, Equatable, Identifiable {
    public let id: String
    public let serverID: Int64?
    public let request: OrderRequestDTO
    public let lifecycle: OrderLifecycle
    public let filledQuantity: Int64
    public let reason: String?

    public init(id: String, serverID: Int64?, request: OrderRequestDTO, lifecycle: OrderLifecycle,
                filledQuantity: Int64 = 0, reason: String? = nil) {
        self.id = id
        self.serverID = serverID
        self.request = request
        self.lifecycle = lifecycle
        self.filledQuantity = filledQuantity
        self.reason = reason
    }
}

public enum OrderTransitionError: Error, Sendable, Equatable {
    case invalidTransition(OrderLifecycle, OrderLifecycle)
}

public struct OrderStateMachine: Sendable {
    public private(set) var state: OrderLifecycle

    public init(state: OrderLifecycle = .draft) { self.state = state }

    public mutating func transition(to next: OrderLifecycle) throws {
        let allowed: [OrderLifecycle: Set<OrderLifecycle>] = [
            .draft: [.submitting, .rejected],
            .submitting: [.accepted, .partiallyFilled, .filled, .rejected],
            .accepted: [.partiallyFilled, .filled, .cancelPending, .cancelled, .replaced],
            .partiallyFilled: [.partiallyFilled, .filled, .cancelPending, .cancelled, .replaced],
            .cancelPending: [.cancelled, .partiallyFilled, .filled, .rejected],
            .filled: [], .cancelled: [], .rejected: [], .replaced: []
        ]
        guard allowed[state, default: []].contains(next) else {
            throw OrderTransitionError.invalidTransition(state, next)
        }
        state = next
    }
}
