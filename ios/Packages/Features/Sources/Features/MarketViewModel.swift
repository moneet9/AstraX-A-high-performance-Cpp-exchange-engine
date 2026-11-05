import Core
import Foundation
import MarketData
import Networking
import Observation
import Persistence

@Observable
@MainActor
public final class MarketViewModel {
    public let symbol: String
    public private(set) var book: MarketBook?
    public private(set) var candles: [Candle] = []
    public private(set) var chartPoints: [ChartPoint] = []
    public private(set) var isConnected = false
    public private(set) var errorMessage: String?

    private let hub: MarketDataHub
    private let api: APIClient
    private let repository: CandleRepository?
    private let aggregator = CandleAggregator(intervalSeconds: 60)
    private let consumerID = UUID()
    private var lastSavedBucket: Int64 = 0

    public init(symbol: String = "ASTR", hub: MarketDataHub, api: APIClient, repository: CandleRepository?) {
        self.symbol = symbol
        self.hub = hub
        self.api = api
        self.repository = repository
    }

    public func start() async {
        await loadHistory()
        let stream = await hub.updates()
        await hub.connect(symbol: symbol, consumerID: consumerID)
        isConnected = true
        for await update in stream {
            guard !Task.isCancelled else { break }
            book = update
            if let midpoint = update.midpointTicks {
                await aggregator.ingestQuote(priceTicks: midpoint, timestampNanoseconds: update.receivedAtNanoseconds)
                let values = await aggregator.snapshot(limit: 500)
                candles = values
                chartPoints = await aggregator.projection(values)
                await persistIfNeeded(values)
            }
        }
        isConnected = false
        await hub.disconnect(consumerID: consumerID)
    }

    public func stop() async {
        await hub.disconnect(consumerID: consumerID)
        isConnected = false
    }

    private func loadHistory() async {
        do {
            let remote = try await api.candles(symbol: symbol)
            let mapped = remote.map { Candle(timestamp: $0.time * 1_000_000_000,
                openTicks: $0.openTicks, highTicks: $0.highTicks, lowTicks: $0.lowTicks,
                closeTicks: $0.closeTicks, volume: $0.volume) }
            await aggregator.merge(mapped)
            candles = await aggregator.snapshot()
            chartPoints = await aggregator.projection(candles)
        } catch {
            if let cached = try? await repository?.load(symbol: symbol) {
                await aggregator.merge(cached)
                candles = await aggregator.snapshot()
                chartPoints = await aggregator.projection(candles)
            }
            errorMessage = error.localizedDescription
        }
    }

    private func persistIfNeeded(_ values: [Candle]) async {
        guard let latest = values.last else { return }
        let bucket = latest.timestamp
        guard bucket != lastSavedBucket else { return }
        lastSavedBucket = bucket
        try? await repository?.save(values, symbol: symbol)
    }
}
