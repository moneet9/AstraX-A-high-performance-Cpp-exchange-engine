import Core
import DesignSystem
import SwiftUI

public struct WatchlistView: View {
    let dependencies: AppDependencies
    let isActive: Bool

    public init(dependencies: AppDependencies, isActive: Bool = true) {
        self.dependencies = dependencies
        self.isActive = isActive
    }

    public var body: some View {
        NavigationStack {
            List {
                NavigationLink {
                    MarketScreen(dependencies: dependencies, isActive: isActive)
                } label: {
                    WatchlistRow(dependencies: dependencies, isActive: isActive)
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
    @Environment(\.scenePhase) private var scenePhase
    let isActive: Bool
    @State private var model: MarketViewModel

    init(dependencies: AppDependencies, isActive: Bool) {
        self.isActive = isActive
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
            LivePriceChart(points: model.chartPoints, latestPriceTicks: model.book?.midpointTicks)
                .frame(width: 76, height: 32)
            VStack(alignment: .trailing, spacing: 5) {
                Text(model.book?.midpointTicks.map { PriceFormatting.string(ticks: $0) } ?? "—")
                    .font(.subheadline.monospacedDigit().weight(.semibold)).foregroundStyle(AstraXTheme.text)
                Text(model.isConnected ? "LIVE" : "CONNECTING")
                    .font(.caption2.weight(.bold)).foregroundStyle(model.isConnected ? AstraXTheme.positive : AstraXTheme.secondaryText)
            }
        }
        .padding(.vertical, 8)
        .task(id: "\(model.symbol)-\(isActive)-\(scenePhase == .active)") {
            guard isActive, scenePhase == .active else { await model.stop(); return }
            await model.start()
        }
        .onDisappear { Task { await model.stop() } }
    }
}
