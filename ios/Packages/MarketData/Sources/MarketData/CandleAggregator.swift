import Core
import Foundation

public struct ChartPoint: Sendable, Equatable, Identifiable {
    public let id: Int64
    public let xBasisPoints: Int64
    public let yBasisPoints: Int64
}

public actor CandleAggregator {
    private let intervalNanoseconds: Int64
    private var candles: [Int64: Candle] = [:]

    public init(intervalSeconds: Int64 = 60) {
        self.intervalNanoseconds = max(1, intervalSeconds) * 1_000_000_000
    }

    public func ingest(_ trade: TradePrint) {
        let start = trade.timestampNanoseconds / intervalNanoseconds * intervalNanoseconds
        guard let old = candles[start] else {
            candles[start] = Candle(timestamp: start, openTicks: trade.priceTicks,
                                    highTicks: trade.priceTicks, lowTicks: trade.priceTicks,
                                    closeTicks: trade.priceTicks, volume: trade.quantity)
            return
        }
        candles[start] = Candle(timestamp: start, openTicks: old.openTicks,
                                highTicks: max(old.highTicks, trade.priceTicks),
                                lowTicks: min(old.lowTicks, trade.priceTicks),
                                closeTicks: trade.priceTicks, volume: old.volume + trade.quantity)
    }

    public func ingestQuote(priceTicks: Int64, timestampNanoseconds: Int64) {
        let start = timestampNanoseconds / intervalNanoseconds * intervalNanoseconds
        guard let old = candles[start] else {
            candles[start] = Candle(timestamp: start, openTicks: priceTicks, highTicks: priceTicks,
                                    lowTicks: priceTicks, closeTicks: priceTicks, volume: 0)
            return
        }
        candles[start] = Candle(timestamp: start, openTicks: old.openTicks,
                                highTicks: max(old.highTicks, priceTicks), lowTicks: min(old.lowTicks, priceTicks),
                                closeTicks: priceTicks, volume: old.volume)
    }

    public func merge(_ incoming: [Candle]) {
        for candle in incoming { candles[candle.timestamp] = candle }
    }

    public func snapshot(limit: Int = 500) -> [Candle] {
        Array(candles.values.sorted { $0.timestamp < $1.timestamp }.suffix(max(1, limit)))
    }

    /// Converts integer candle prices into a normalized chart projection off the UI actor.
    public func projection(_ items: [Candle]) -> [ChartPoint] {
        guard !items.isEmpty else { return [] }
        let values = items.map(\.closeTicks)
        let low = values.min() ?? 0
        let high = values.max() ?? low
        let span = max(1, high - low)
        let lastIndex = max(1, items.count - 1)
        return items.enumerated().map { index, candle in
            let x = Int64(index) * 10_000 / Int64(lastIndex)
            let y = Decimal(candle.closeTicks - low) * 10_000 / Decimal(span)
            return ChartPoint(id: candle.timestamp, xBasisPoints: x,
                              yBasisPoints: NSDecimalNumber(decimal: y).int64Value)
        }
    }
}
