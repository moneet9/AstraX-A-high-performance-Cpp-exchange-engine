import Core
import Observation
import MarketData
import Trading

@Observable
@MainActor
public final class OrdersViewModel {
    public private(set) var orders: [OrderStateSnapshot] = []
    public private(set) var isLoading = false
    public var errorMessage: String?

    private let manager: OrderManager
    private let marketData: MarketDataHub
    private let accountID: Int64
    private var updatesTask: Task<Void, Never>?
    private var executionTask: Task<Void, Never>?
    private let consumerID = UUID()

    public init(manager: OrderManager, marketData: MarketDataHub, accountID: Int64) {
        self.manager = manager
        self.marketData = marketData
        self.accountID = accountID
    }

    public func start() async {
        guard updatesTask == nil else { return }
        updatesTask = Task { [weak self] in
            guard let self else { return }
            let stream = await manager.updates()
            for await snapshot in stream {
                guard !Task.isCancelled else { break }
                orders = snapshot
            }
        }
        let executionUpdates = await marketData.executionUpdates()
        executionTask = Task { [weak self] in
            guard let self else { return }
            for await event in executionUpdates {
                guard !Task.isCancelled else { break }
                await manager.apply(event)
            }
        }
        await marketData.connect(symbol: "ASTR", consumerID: consumerID)
        await refresh()
    }

    public func stop() {
        updatesTask?.cancel(); updatesTask = nil
        executionTask?.cancel(); executionTask = nil
        Task { await marketData.disconnect(consumerID: consumerID) }
    }

    public func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do { orders = try await manager.load(accountID: accountID) }
        catch { errorMessage = error.localizedDescription }
    }

    public func cancel(_ order: OrderStateSnapshot) async {
        do { try await manager.cancel(accountID: accountID, clientID: order.id) }
        catch { errorMessage = error.localizedDescription }
    }
}
