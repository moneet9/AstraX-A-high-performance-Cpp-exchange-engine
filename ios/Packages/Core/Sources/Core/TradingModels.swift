import Foundation

public struct TickPrice: Codable, Sendable, Hashable, Comparable {
    public let rawValue: Int64
    public let scale: Int64

    public init(rawValue: Int64, scale: Int64 = 10_000) {
        self.rawValue = rawValue
        self.scale = max(scale, 1)
    }

    public static func < (lhs: Self, rhs: Self) -> Bool {
        guard lhs.scale == rhs.scale else { return lhs.decimalValue < rhs.decimalValue }
        return lhs.rawValue < rhs.rawValue
    }

    public var decimalValue: Decimal {
        Decimal(rawValue) / Decimal(scale)
    }

    public func adding(_ other: Self) -> Decimal {
        decimalValue + other.decimalValue
    }
}

public struct MarketBook: Codable, Sendable, Equatable {
    public let symbol: String
    public let sequence: Int64
    public let bids: [BookLevel]
    public let asks: [BookLevel]
    public let receivedAtNanoseconds: Int64

    public init(symbol: String, sequence: Int64, bids: [BookLevel], asks: [BookLevel], receivedAtNanoseconds: Int64) {
        self.symbol = symbol
        self.sequence = sequence
        self.bids = bids
        self.asks = asks
        self.receivedAtNanoseconds = receivedAtNanoseconds
    }

    public var bestBid: BookLevel? { bids.first }
    public var bestAsk: BookLevel? { asks.first }
    public var midpointTicks: Int64? {
        guard let bid = bestBid?.priceTicks, let ask = bestAsk?.priceTicks else { return nil }
        return bid + (ask - bid) / 2
    }
}

public struct BookLevel: Codable, Sendable, Equatable, Identifiable {
    public let priceTicks: Int64
    public let quantity: Int64
    public var id: Int64 { priceTicks }

    public init(priceTicks: Int64, quantity: Int64) {
        self.priceTicks = priceTicks
        self.quantity = quantity
    }
}

public struct TradePrint: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public let symbol: String
    public let priceTicks: Int64
    public let quantity: Int64
    public let side: OrderSide
    public let timestampNanoseconds: Int64

    public init(id: String, symbol: String, priceTicks: Int64, quantity: Int64, side: OrderSide, timestampNanoseconds: Int64) {
        self.id = id
        self.symbol = symbol
        self.priceTicks = priceTicks
        self.quantity = quantity
        self.side = side
        self.timestampNanoseconds = timestampNanoseconds
    }
}

public struct ExecutionFill: Codable, Sendable, Equatable, Identifiable {
    public let orderID: Int64
    public let symbol: String
    public let side: OrderSide
    public let priceTicks: Int64
    public let quantity: Int64
    public var id: String { "\(orderID):\(priceTicks):\(quantity)" }

    public init(orderID: Int64, symbol: String, side: OrderSide, priceTicks: Int64, quantity: Int64) {
        self.orderID = orderID; self.symbol = symbol; self.side = side
        self.priceTicks = priceTicks; self.quantity = quantity
    }

    enum CodingKeys: String, CodingKey {
        case symbol, side, quantity
        case orderID = "order_id"
        case priceTicks = "price_ticks"
    }
}

public struct PrivateExecutionEvent: Codable, Sendable, Equatable {
    public let version: Int
    public let type: String
    public let fills: [ExecutionFill]

    enum CodingKeys: String, CodingKey {
        case type, fills
        case version = "v"
    }
}

public struct Candle: Codable, Sendable, Equatable, Identifiable {
    public let timestamp: Int64
    public let openTicks: Int64
    public let highTicks: Int64
    public let lowTicks: Int64
    public let closeTicks: Int64
    public let volume: Int64
    public var id: Int64 { timestamp }

    public init(timestamp: Int64, openTicks: Int64, highTicks: Int64, lowTicks: Int64, closeTicks: Int64, volume: Int64) {
        self.timestamp = timestamp
        self.openTicks = openTicks
        self.highTicks = highTicks
        self.lowTicks = lowTicks
        self.closeTicks = closeTicks
        self.volume = volume
    }
}

public struct SessionTokens: Codable, Sendable, Equatable {
    public let accessToken: String
    public let refreshToken: String
    public let expiresAt: Date
    public let accountID: Int64

    public init(accessToken: String, refreshToken: String, expiresAt: Date, accountID: Int64) {
        self.accessToken = accessToken
        self.refreshToken = refreshToken
        self.expiresAt = expiresAt
        self.accountID = accountID
    }
}
