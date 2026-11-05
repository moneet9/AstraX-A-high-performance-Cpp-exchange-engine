import Core
import Foundation
import SwiftData

@Model
final class StoredCandle {
    @Attribute(.unique) var key: String
    var symbol: String
    var timestamp: Int64
    var openTicks: Int64
    var highTicks: Int64
    var lowTicks: Int64
    var closeTicks: Int64
    var volume: Int64

    init(symbol: String, candle: Candle) {
        self.key = "\(symbol):\(candle.timestamp)"
        self.symbol = symbol
        self.timestamp = candle.timestamp
        self.openTicks = candle.openTicks
        self.highTicks = candle.highTicks
        self.lowTicks = candle.lowTicks
        self.closeTicks = candle.closeTicks
        self.volume = candle.volume
    }
}

public actor CandleRepository {
    private let container: ModelContainer

    public init() throws {
        self.container = try ModelContainer(for: StoredCandle.self)
    }

    public func save(_ candles: [Candle], symbol: String) throws {
        let context = ModelContext(container)
        for candle in candles {
            let key = "\(symbol):\(candle.timestamp)"
            var descriptor = FetchDescriptor<StoredCandle>(predicate: #Predicate { $0.key == key })
            descriptor.fetchLimit = 1
            if let stored = try context.fetch(descriptor).first {
                stored.openTicks = candle.openTicks
                stored.highTicks = candle.highTicks
                stored.lowTicks = candle.lowTicks
                stored.closeTicks = candle.closeTicks
                stored.volume = candle.volume
            } else {
                context.insert(StoredCandle(symbol: symbol, candle: candle))
            }
        }
        try context.save()
    }

    public func load(symbol: String, limit: Int = 500) throws -> [Candle] {
        let context = ModelContext(container)
        var descriptor = FetchDescriptor<StoredCandle>(predicate: #Predicate { $0.symbol == symbol })
        descriptor.sortBy = [SortDescriptor(\.timestamp, order: .forward)]
        descriptor.fetchLimit = max(1, min(limit, 2000))
        return try context.fetch(descriptor).map {
            Candle(timestamp: $0.timestamp, openTicks: $0.openTicks, highTicks: $0.highTicks,
                   lowTicks: $0.lowTicks, closeTicks: $0.closeTicks, volume: $0.volume)
        }
    }
}
