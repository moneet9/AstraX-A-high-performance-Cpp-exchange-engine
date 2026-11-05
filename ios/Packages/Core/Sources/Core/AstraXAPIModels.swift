// Contract models for backend/openapi.yaml. Keep prices and quantities as integers.
import Foundation

public struct TokenPair: Codable, Sendable, Equatable {
    public let accessToken: String
    public let refreshToken: String
    public let tokenType: String
    public let expiresIn: Int
    public let userID: Int64?
    public let accountID: Int64?

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
        case userID = "user_id"
        case accountID = "account_id"
    }
}

public struct AccountDTO: Codable, Sendable, Equatable, Identifiable {
    public let id: Int64
    public let name: String
    public let currency: String
    public let cashTicks: Int64

    public init(id: Int64, name: String, currency: String, cashTicks: Int64) {
        self.id = id; self.name = name; self.currency = currency; self.cashTicks = cashTicks
    }

    enum CodingKeys: String, CodingKey {
        case id, name, currency
        case cashTicks = "cash_ticks"
    }
}

public struct SymbolDTO: Codable, Sendable, Equatable, Identifiable {
    public let symbol: String
    public let priceScale: Int64
    public let tickSize: Int64
    public let quantityUnit: String
    public let simulated: Bool
    public var id: String { symbol }

    enum CodingKeys: String, CodingKey {
        case symbol, simulated
        case priceScale = "price_scale"
        case tickSize = "tick_size"
        case quantityUnit = "quantity_unit"
    }
}

public enum OrderSide: String, Codable, Sendable { case buy, sell }
public enum TimeInForce: String, Codable, Sendable { case gtc = "GTC", ioc = "IOC", fok = "FOK" }
public enum OrderKind: String, Codable, Sendable {
    case market, limit, stop, stopLimit = "stop_limit", iceberg, pegged
}

public struct OrderRequestDTO: Codable, Sendable, Equatable {
    public let symbol: String
    public let side: OrderSide
    public let type: OrderKind
    public let quantity: Int64
    public let priceTicks: Int64
    public let stopPriceTicks: Int64
    public let visibleQuantity: Int64
    public let pegOffsetTicks: Int64
    public let tif: TimeInForce

    public init(symbol: String, side: OrderSide, type: OrderKind, quantity: Int64,
                priceTicks: Int64 = 0, stopPriceTicks: Int64 = 0,
                visibleQuantity: Int64 = 0, pegOffsetTicks: Int64 = 0,
                tif: TimeInForce = .gtc) {
        self.symbol = symbol
        self.side = side
        self.type = type
        self.quantity = quantity
        self.priceTicks = priceTicks
        self.stopPriceTicks = stopPriceTicks
        self.visibleQuantity = visibleQuantity
        self.pegOffsetTicks = pegOffsetTicks
        self.tif = tif
    }

    enum CodingKeys: String, CodingKey {
        case symbol, side, type, quantity, tif
        case priceTicks = "price_ticks"
        case stopPriceTicks = "stop_price_ticks"
        case visibleQuantity = "visible_quantity"
        case pegOffsetTicks = "peg_offset_ticks"
    }
}

public struct OrderDTO: Codable, Sendable, Equatable, Identifiable {
    public let id: Int64
    public let symbol: String
    public let side: OrderSide
    public let type: String
    public let tif: String
    public let priceTicks: Int64
    public let stopPriceTicks: Int64
    public let pegOffsetTicks: Int64
    public let quantity: Int64
    public let filledQuantity: Int64
    public let status: String

    public init(id: Int64, symbol: String, side: OrderSide, type: String, tif: String,
                priceTicks: Int64, stopPriceTicks: Int64, pegOffsetTicks: Int64,
                quantity: Int64, filledQuantity: Int64, status: String) {
        self.id = id; self.symbol = symbol; self.side = side; self.type = type; self.tif = tif
        self.priceTicks = priceTicks; self.stopPriceTicks = stopPriceTicks; self.pegOffsetTicks = pegOffsetTicks
        self.quantity = quantity; self.filledQuantity = filledQuantity; self.status = status
    }

    enum CodingKeys: String, CodingKey {
        case id, symbol, side, type, tif, status, quantity
        case priceTicks = "price_ticks"
        case stopPriceTicks = "stop_price_ticks"
        case pegOffsetTicks = "peg_offset_ticks"
        case filledQuantity = "filled_quantity"
    }
}

public struct PositionDTO: Codable, Sendable, Equatable, Identifiable {
    public let symbol: String
    public let quantity: Int64
    public let averagePriceTicks: Int64
    public let realizedPnlTicks: Int64
    public var id: String { symbol }

    public init(symbol: String, quantity: Int64, averagePriceTicks: Int64, realizedPnlTicks: Int64) {
        self.symbol = symbol; self.quantity = quantity
        self.averagePriceTicks = averagePriceTicks; self.realizedPnlTicks = realizedPnlTicks
    }

    enum CodingKeys: String, CodingKey {
        case symbol, quantity
        case averagePriceTicks = "average_price_ticks"
        case realizedPnlTicks = "realized_pnl_ticks"
    }
}

public struct ExecutionDTO: Codable, Sendable, Equatable, Identifiable {
    public let id: Int64
    public let symbol: String
    public let side: OrderSide
    public let priceTicks: Int64
    public let quantity: Int64
    public let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, symbol, side, quantity
        case priceTicks = "price_ticks"
        case createdAt = "created_at"
    }
}

public struct CandleDTO: Codable, Sendable, Equatable, Identifiable {
    public let time: Int64
    public let openTicks: Int64
    public let highTicks: Int64
    public let lowTicks: Int64
    public let closeTicks: Int64
    public let volume: Int64
    public var id: Int64 { time }

    enum CodingKeys: String, CodingKey {
        case time, volume
        case openTicks = "open_ticks"
        case highTicks = "high_ticks"
        case lowTicks = "low_ticks"
        case closeTicks = "close_ticks"
    }
}

public struct BookLevelDTO: Codable, Sendable, Equatable {
    public let priceTicks: Int64
    public let quantity: Int64
}

public struct BookSnapshotDTO: Codable, Sendable, Equatable {
    public let version: Int
    public let type: String
    public let kind: String
    public let symbol: String
    public let sequence: Int64
    public let bids: [[Int64]]
    public let asks: [[Int64]]

    enum CodingKeys: String, CodingKey {
        case type, kind, symbol, bids, asks
        case version = "v"
        case sequence = "seq"
    }
}
