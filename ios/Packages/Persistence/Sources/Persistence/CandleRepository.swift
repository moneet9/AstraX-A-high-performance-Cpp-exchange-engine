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
        guard let oldest = candles.map(\.timestamp).min(), let newest = candles.map(\.timestamp).max() else { return }
        let context = ModelContext(container)
        let symbolKey = symbol
        let existingDescriptor = FetchDescriptor<StoredCandle>(
            predicate: #Predicate { $0.symbol == symbolKey && $0.timestamp >= oldest && $0.timestamp <= newest })
        let existing = try context.fetch(existingDescriptor)
        var byTimestamp = Dictionary(uniqueKeysWithValues: existing.map { ($0.timestamp, $0) })
        for candle in candles {
            if let stored = byTimestamp[candle.timestamp] {
                stored.openTicks = candle.openTicks
                stored.highTicks = candle.highTicks
                stored.lowTicks = candle.lowTicks
                stored.closeTicks = candle.closeTicks
                stored.volume = candle.volume
            } else {
                let stored = StoredCandle(symbol: symbol, candle: candle)
                context.insert(stored)
                byTimestamp[candle.timestamp] = stored
            }
        }
        let cutoff = newest - 2_000 * 60 * 1_000_000_000
        let retentionDescriptor = FetchDescriptor<StoredCandle>(
            predicate: #Predicate { $0.symbol == symbolKey && $0.timestamp < cutoff })
        for stored in try context.fetch(retentionDescriptor) { context.delete(stored) }
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
