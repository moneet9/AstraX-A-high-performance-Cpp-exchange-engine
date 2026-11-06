import DesignSystem
import SwiftUI

public struct RootView: View {
    private let dependencies: AppDependencies
    private let pushRegistration: PushRegistration
    @State private var session: SessionViewModel

    public init(dependencies: AppDependencies, pushRegistration: PushRegistration) {
        self.dependencies = dependencies
        self.pushRegistration = pushRegistration
        _session = State(initialValue: dependencies.session)
    }

    public var body: some View {
        Group {
            if session.isAuthenticated, let accountID = session.accountID {
                TradingTabs(dependencies: dependencies, accountID: accountID, pushRegistration: pushRegistration)
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
    let pushRegistration: PushRegistration
    @State private var selectedTab = "watchlist"

    var body: some View {
        TabView(selection: $selectedTab) {
            WatchlistView(dependencies: dependencies, isActive: selectedTab == "watchlist")
                .tabItem { Label("Watchlist", systemImage: "star") }
                .tag("watchlist")
            PortfolioView(dependencies: dependencies, accountID: accountID)
                .tabItem { Label("Portfolio", systemImage: "chart.pie") }
                .tag("portfolio")
            OrdersView(dependencies: dependencies, accountID: accountID, isActive: selectedTab == "orders")
                .tabItem { Label("Orders", systemImage: "list.bullet.rectangle") }
                .tag("orders")
            TradeView(dependencies: dependencies, accountID: accountID)
                .tabItem { Label("Trade", systemImage: "arrow.left.arrow.right") }
                .tag("trade")
            AccountView(session: dependencies.session, api: dependencies.api, accountID: accountID,
                        pushRegistration: pushRegistration)
                .tabItem { Label("Account", systemImage: "person.crop.circle") }
                .tag("account")
        }
    }
}
