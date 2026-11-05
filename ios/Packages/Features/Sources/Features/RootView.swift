import DesignSystem
import SwiftUI

public struct RootView: View {
    private let dependencies: AppDependencies
    @State private var session: SessionViewModel

    public init(dependencies: AppDependencies) {
        self.dependencies = dependencies
        _session = State(initialValue: dependencies.session)
    }

    public var body: some View {
        Group {
            if session.isAuthenticated, let accountID = session.accountID {
                TradingTabs(dependencies: dependencies, accountID: accountID)
            } else {
                LoginView(session: session)
            }
        }
        .preferredColorScheme(.dark)
        .tint(AstraXTheme.buy)
        .task {
            await session.restore()
            session.observeTokenRotation()
        }
    }
}

private struct TradingTabs: View {
    let dependencies: AppDependencies
    let accountID: Int64

    var body: some View {
        TabView {
            WatchlistView(dependencies: dependencies)
                .tabItem { Label("Watchlist", systemImage: "star") }
            PortfolioView(dependencies: dependencies, accountID: accountID)
                .tabItem { Label("Portfolio", systemImage: "chart.pie") }
            OrdersView(dependencies: dependencies, accountID: accountID)
                .tabItem { Label("Orders", systemImage: "list.bullet.rectangle") }
            TradeView(dependencies: dependencies, accountID: accountID)
                .tabItem { Label("Trade", systemImage: "arrow.left.arrow.right") }
            AccountView(session: dependencies.session, api: dependencies.api, accountID: accountID)
                .tabItem { Label("Account", systemImage: "person.crop.circle") }
        }
    }
}
