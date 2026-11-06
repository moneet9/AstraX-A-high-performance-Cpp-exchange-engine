import Core
import DesignSystem
import MarketData
import SwiftUI

public struct LivePriceChart: View {
    public let points: [ChartPoint]
    public let latestPriceTicks: Int64?

    public init(points: [ChartPoint], latestPriceTicks: Int64? = nil) {
        self.points = points
        self.latestPriceTicks = latestPriceTicks
    }

    public var body: some View {
        Canvas { context, size in
            guard points.count > 1 else { return }
            var line = Path()
            for (index, point) in points.enumerated() {
                let x = size.width * CGFloat(point.xBasisPoints) / 10_000
                let y = size.height * (1 - CGFloat(point.yBasisPoints) / 10_000)
                if index == 0 { line.move(to: CGPoint(x: x, y: y)) }
                else { line.addLine(to: CGPoint(x: x, y: y)) }
            }
            context.stroke(line, with: .color(AstraXTheme.buy), style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
        }
        .drawingGroup()
        .frame(height: 160)
        .accessibilityLabel("Live simulated price chart")
        .accessibilityValue(latestPriceTicks.map { "Latest simulated price \(PriceFormatting.string(ticks: $0))" } ?? "Waiting for price data")
    }
}

public struct MarketScreen: View {
    @Environment(\.scenePhase) private var scenePhase
    private let isActive: Bool
    @State private var model: MarketViewModel

    public init(dependencies: AppDependencies, isActive: Bool = true) {
        self.isActive = isActive
        _model = State(initialValue: MarketViewModel(hub: dependencies.marketData, api: dependencies.api,
                                                    repository: dependencies.candleRepository))
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("ASTR / USD").font(.title2.weight(.bold)).foregroundStyle(AstraXTheme.text)
                        Text("Simulated market").font(.caption).foregroundStyle(AstraXTheme.secondaryText)
                    }
                    Spacer()
                    Label(model.isConnected ? "LIVE" : "CONNECTING", systemImage: "circle.fill")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(model.isConnected ? AstraXTheme.positive : AstraXTheme.secondaryText)
                        .accessibilityLabel(model.isConnected ? "Market data live" : "Connecting to market data")
                }
                CardSurface {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(model.book?.midpointTicks.map { PriceFormatting.string(ticks: $0) } ?? "—")
                                .font(.system(.largeTitle, design: .rounded, weight: .semibold).monospacedDigit())
                                .foregroundStyle(AstraXTheme.text)
                            Spacer()
                            if let bid = model.book?.bestBid, let ask = model.book?.bestAsk {
                                VStack(alignment: .trailing) {
                                    Text("SPREAD").font(.caption2).foregroundStyle(AstraXTheme.secondaryText)
                                    Text(PriceFormatting.string(ticks: ask.priceTicks - bid.priceTicks, currency: "USD"))
                                        .font(.caption.monospacedDigit()).foregroundStyle(AstraXTheme.text)
                                }
                            }
                        }
                        LivePriceChart(points: model.chartPoints, latestPriceTicks: model.book?.midpointTicks)
                        HStack { Text("1m candles"); Spacer(); Text("Integer tick prices") }
                            .font(.caption2).foregroundStyle(AstraXTheme.secondaryText)
                    }
                }
                OrderBookCard(book: model.book)
                if let error = model.errorMessage {
                    Text(error).font(.caption).foregroundStyle(AstraXTheme.secondaryText)
                }
            }
            .padding(16)
            .frame(maxWidth: 760)
            .frame(maxWidth: .infinity)
        }
        .background(AstraXTheme.background)
        .navigationTitle("Market")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: "\(model.symbol)-\(isActive)-\(scenePhase == .active)") {
            guard isActive, scenePhase == .active else { await model.stop(); return }
            await model.start()
        }
        .onDisappear { Task { await model.stop() } }
    }
}

private struct OrderBookCard: View {
    let book: MarketBook?

    var body: some View {
        CardSurface {
            VStack(alignment: .leading, spacing: 12) {
                Text("LEVEL 2 · TOP 5").font(.caption.weight(.bold)).tracking(1.1).foregroundStyle(AstraXTheme.secondaryText)
                HStack {
                    Text("BID SIZE").foregroundStyle(AstraXTheme.buy)
                    Spacer()
                    Text("PRICE").foregroundStyle(AstraXTheme.secondaryText)
                    Spacer()
                    Text("ASK SIZE").foregroundStyle(AstraXTheme.sell)
                }.font(.caption2.weight(.bold))
                ForEach(0..<5, id: \.self) { index in
                    HStack {
                        Text(book?.bids[safe: index].map { String($0.quantity) } ?? "—")
                            .foregroundStyle(AstraXTheme.buy)
                        Spacer()
                        Text(book?.bids[safe: index].map { PriceFormatting.string(ticks: $0.priceTicks) } ?? "—")
                            .foregroundStyle(AstraXTheme.text)
                        Spacer()
                        Text(book?.asks[safe: index].map { String($0.quantity) } ?? "—")
                            .foregroundStyle(AstraXTheme.sell)
                    }
                    .font(.caption.monospacedDigit())
                    .accessibilityElement(children: .combine)
                }
            }
        }
    }
}

private extension Array {
    subscript(safe index: Int) -> Element? { indices.contains(index) ? self[index] : nil }
}
