import Core
import Foundation
import Observation
import Persistence
import Trading
import UIKit

@Observable
@MainActor
public final class OrderTicketViewModel {
    public var side: OrderSide = .buy
    public var kind: OrderKind = .limit
    public var tif: TimeInForce = .gtc
    public var quantityText = "1"
    public var priceText = "100.00"
    public var stopPriceText = "100.00"
    public var visibleQuantityText = "1"
    public var pegOffsetText = "0"
    public private(set) var isSubmitting = false
    public private(set) var resultMessage: String?
    public var errorMessage: String?

    private let manager: OrderManager
    private let biometric: BiometricGate
    private let accountID: Int64
    private let tickSize: Int64
    private var submissionKey: String?
    private var pendingRequest: OrderRequestDTO?

    public init(manager: OrderManager, biometric: BiometricGate, accountID: Int64, tickSize: Int64 = 100) {
        self.manager = manager
        self.biometric = biometric
        self.accountID = accountID
        self.tickSize = tickSize
    }

    public func makeRequest() throws -> OrderRequestDTO {
        guard let quantity = Int64(quantityText), quantity > 0 else { throw TicketError.invalidQuantity }
        let price = kind == .market || kind == .stop || kind == .pegged ? 0 : try Self.parsePrice(priceText)
        let stopPrice = kind == .stop || kind == .stopLimit ? try Self.parsePrice(stopPriceText) : 0
        let visible: Int64
        if kind == .iceberg {
            guard let parsed = Int64(visibleQuantityText) else { throw TicketError.invalidVisibleQuantity }
            visible = parsed
        } else { visible = 0 }
        let peg: Int64
        if kind == .pegged {
            guard let parsed = Int64(pegOffsetText) else { throw TicketError.invalidPegOffset }
            peg = parsed
        } else { peg = 0 }
        let order = OrderRequestDTO(symbol: "ASTR", side: side, type: kind, quantity: quantity,
                                    priceTicks: price, stopPriceTicks: stopPrice,
                                    visibleQuantity: visible, pegOffsetTicks: peg, tif: tif)
        try OrderManager.validate(order, tickSize: tickSize)
        return order
    }

    public func submitConfirmed() async {
        isSubmitting = true
        errorMessage = nil
        resultMessage = nil
        defer { isSubmitting = false }
        do {
            _ = try makeRequest()
            let authenticated = try await biometric.authenticate()
            guard authenticated else { throw TicketError.biometricCancelled }
            // Keep retries byte-for-byte equivalent to the original submission. A timeout
            // can happen after the server accepted the order, so edited fields must not
            // be sent with the old idempotency key.
            let request = pendingRequest ?? (try makeRequest())
            let key: String
            if let submissionKey {
                key = submissionKey
            } else {
                key = UUID().uuidString.lowercased()
                submissionKey = key
                pendingRequest = request
            }
            let result = try await manager.submit(accountID: accountID, request: request, tickSize: tickSize,
                                                  idempotencyKey: key)
            submissionKey = nil
            pendingRequest = nil
            resultMessage = switch result.lifecycle {
            case .filled: "Paper order filled"
            case .partiallyFilled: "Paper order partially filled"
            case .accepted: "Paper order accepted"
            default: "Paper order submitted"
            }
            UINotificationFeedbackGenerator().notificationOccurred(.success)
        } catch {
            errorMessage = error.localizedDescription
            UINotificationFeedbackGenerator().notificationOccurred(.error)
        }
    }

    private static func parsePrice(_ text: String) throws -> Int64 {
        guard let decimal = Decimal(string: text, locale: Locale(identifier: "en_US_POSIX")), decimal > 0 else {
            throw TicketError.invalidPrice
        }
        var scaled = decimal * Decimal(10_000)
        var rounded = Decimal()
        NSDecimalRound(&rounded, &scaled, 0, .plain)
        guard rounded == scaled else { throw TicketError.invalidPrice }
        return NSDecimalNumber(decimal: rounded).int64Value
    }
}

private enum TicketError: LocalizedError {
    case invalidQuantity, invalidPrice, invalidVisibleQuantity, invalidPegOffset, biometricCancelled
    var errorDescription: String? {
        switch self {
        case .invalidQuantity: "Enter a positive whole-number quantity."
        case .invalidPrice: "Enter a valid price with up to four decimal places."
        case .invalidVisibleQuantity: "Enter a valid whole-number visible quantity."
        case .invalidPegOffset: "Enter a whole-number peg offset in ticks."
        case .biometricCancelled: "Order confirmation was cancelled."
        }
    }
}
