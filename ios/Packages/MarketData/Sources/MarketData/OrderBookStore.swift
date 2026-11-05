import Core

public actor OrderBookStore {
    private var books: [String: MarketBook] = [:]

    public init() {}

    @discardableResult
    public func apply(_ update: MarketBook, isSnapshot: Bool) -> Bool {
        if let current = books[update.symbol], !isSnapshot,
           update.sequence != current.sequence + 1 {
            return false
        }
        books[update.symbol] = update
        return true
    }

    public func snapshot(for symbol: String) -> MarketBook? {
        books[symbol]
    }
}
