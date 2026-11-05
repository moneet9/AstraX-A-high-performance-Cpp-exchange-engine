import Core
import DesignSystem
import Networking
import Observation
import SwiftUI

@Observable
@MainActor
private final class PortfolioViewModel {
    private(set) var positions: [PositionDTO] = []
    private(set) var account: AccountDTO?
    private(set) var isLoading = false
    var errorMessage: String?
    private let api: APIClient
    private let accountID: Int64

    init(api: APIClient, accountID: Int64) { self.api = api; self.accountID = accountID }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let allAccounts = api.accounts()
            async let allPositions = api.positions(accountID: accountID)
            let accountRows = try await allAccounts
            account = accountRows.first { $0.id == accountID }
            positions = try await allPositions
        } catch { errorMessage = error.localizedDescription }
    }
}

public struct PortfolioView: View {
    @State private var model: PortfolioViewModel

    public init(dependencies: AppDependencies, accountID: Int64) {
        _model = State(initialValue: PortfolioViewModel(api: dependencies.api, accountID: accountID))
    }

    public var body: some View {
        NavigationStack {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("SIMULATED CASH").font(.caption.weight(.bold)).tracking(1).foregroundStyle(AstraXTheme.secondaryText)
                        Text(model.account.map { PriceFormatting.string(ticks: $0.cashTicks) } ?? "—")
                            .font(.largeTitle.monospacedDigit().weight(.semibold)).foregroundStyle(AstraXTheme.text)
                        Text("Paper account · No real funds").font(.caption).foregroundStyle(AstraXTheme.secondaryText)
                    }
                    .padding(.vertical, 8)
                    .listRowBackground(AstraXTheme.surface)
                }
                Section("Positions") {
                    if model.positions.isEmpty {
                        Text("No open paper positions").foregroundStyle(AstraXTheme.secondaryText)
                            .listRowBackground(AstraXTheme.surface)
                    }
                    ForEach(model.positions) { position in
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(position.symbol).font(.headline).foregroundStyle(AstraXTheme.text)
                                Text("\(position.quantity) shares · Avg \(PriceFormatting.string(ticks: position.averagePriceTicks))")
                                    .font(.caption).foregroundStyle(AstraXTheme.secondaryText)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 4) {
                                Text("Realized P&L").font(.caption2).foregroundStyle(AstraXTheme.secondaryText)
                                Text(PriceFormatting.string(ticks: position.realizedPnlTicks))
                                    .font(.caption.monospacedDigit().weight(.semibold))
                                    .foregroundStyle(position.realizedPnlTicks >= 0 ? AstraXTheme.positive : AstraXTheme.sell)
                            }
                        }.listRowBackground(AstraXTheme.surface)
                    }
                }
                Section {
                    Text("Balances and positions belong to the local paper-trading simulator. They are not brokerage assets.")
                        .font(.footnote).foregroundStyle(AstraXTheme.secondaryText)
                        .listRowBackground(AstraXTheme.background)
                }
            }
            .scrollContentBackground(.hidden)
            .background(AstraXTheme.background)
            .navigationTitle("Portfolio")
            .refreshable { await model.load() }
            .task { await model.load() }
            .alert("Portfolio", isPresented: Binding(get: { model.errorMessage != nil }, set: { if !$0 { model.errorMessage = nil } })) {
                Button("OK", role: .cancel) { model.errorMessage = nil }
            } message: { Text(model.errorMessage ?? "") }
        }
    }
}
