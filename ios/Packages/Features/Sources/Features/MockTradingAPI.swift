import Core
import Trading

public actor MockTradingAPI: TradingAPI {
    private var records: [OrderDTO] = []
    private var keys: [String: Int64] = [:]
    private var nextID: Int64 = 1

    public init() {}

    public func placeOrder(accountID: Int64, order: OrderRequestDTO, idempotencyKey: String) async throws -> OrderDTO {
        if let existingID = keys[idempotencyKey], let duplicate = records.first(where: { $0.id == existingID }) {
            return duplicate
        }
        let record = OrderDTO(id: nextID, symbol: order.symbol, side: order.side, type: order.type.rawValue,
            tif: order.tif.rawValue, priceTicks: order.priceTicks, stopPriceTicks: order.stopPriceTicks,
            pegOffsetTicks: order.pegOffsetTicks, quantity: order.quantity, filledQuantity: 0, status: "open")
        nextID += 1
        keys[idempotencyKey] = record.id
        records.insert(record, at: 0)
        return record
    }

    public func cancelOrder(accountID: Int64, orderID: Int64) async throws -> OrderDTO {
        guard let index = records.firstIndex(where: { $0.id == orderID }) else { throw MockError.notFound }
        let old = records[index]
        let cancelled = OrderDTO(id: old.id, symbol: old.symbol, side: old.side, type: old.type, tif: old.tif,
            priceTicks: old.priceTicks, stopPriceTicks: old.stopPriceTicks, pegOffsetTicks: old.pegOffsetTicks,
            quantity: old.quantity, filledQuantity: old.filledQuantity, status: "cancelled")
        records[index] = cancelled
        return cancelled
    }

    public func orders(accountID: Int64) async throws -> [OrderDTO] { records }
}

private enum MockError: Error { case notFound }
