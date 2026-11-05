import Core
import DesignSystem
import SwiftUI

public struct WatchlistView: View {
    let dependencies: AppDependencies

    public init(dependencies: AppDependencies) { self.dependencies = dependencies }

    public var body: some View {
        NavigationStack {
            List {
                NavigationLink {
                    MarketScreen(dependencies: dependencies)
                } label: {
                    WatchlistRow(dependencies: dependencies)
                }
                .listRowBackground(AstraXTheme.surface)
                .accessibilityHint("Opens the live chart and level two order book")
            }
            .scrollContentBackground(.hidden)
            .background(AstraXTheme.background)
            .navigationTitle("Watchlist")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Text("PAPER").font(.caption2.weight(.bold)).tracking(1)
                        .foregroundStyle(AstraXTheme.buy)
                }
            }
        }
    }
}

private struct WatchlistRow: View {
    @State private var model: MarketViewModel

    init(dependencies: AppDependencies) {
        _model = State(initialValue: MarketViewModel(hub: dependencies.marketData,
            api: dependencies.api, repository: dependencies.candleRepository))
    }

    var body: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 5) {
                Text("ASTR").font(.headline).foregroundStyle(AstraXTheme.text)
                Text("AstraX Simulated Asset").font(.caption).foregroundStyle(AstraXTheme.secondaryText)
            }
            Spacer(minLength: 8)
            LivePriceChart(points: model.chartPoints)
                .frame(width: 76, height: 32)
            VStack(alignment: .trailing, spacing: 5) {
                Text(model.book?.midpointTicks.map { PriceFormatting.string(ticks: $0) } ?? "—")
                    .font(.subheadline.monospacedDigit().weight(.semibold)).foregroundStyle(AstraXTheme.text)
                Text(model.isConnected ? "LIVE" : "CONNECTING")
                    .font(.caption2.weight(.bold)).foregroundStyle(model.isConnected ? AstraXTheme.positive : AstraXTheme.secondaryText)
            }
        }
        .padding(.vertical, 8)
        .task(id: model.symbol) { await model.start() }
        .onDisappear { Task { await model.stop() } }
    }
}
