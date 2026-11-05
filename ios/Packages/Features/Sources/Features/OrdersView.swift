import DesignSystem
import SwiftUI
import Trading

public struct OrdersView: View {
    @State private var model: OrdersViewModel

    public init(dependencies: AppDependencies, accountID: Int64) {
        _model = State(initialValue: OrdersViewModel(manager: dependencies.orderManager,
            marketData: dependencies.marketData, accountID: accountID))
    }

    public var body: some View {
        NavigationStack {
            Group {
                if model.orders.isEmpty && model.isLoading {
                    ProgressView("Loading orders")
                } else if model.orders.isEmpty {
                    ContentUnavailableView("No paper orders", systemImage: "list.bullet.rectangle",
                        description: Text("Orders you place in the simulated market will appear here."))
                } else {
                    List(model.orders) { order in
                        HStack(spacing: 12) {
                            RoundedRectangle(cornerRadius: 2).fill(order.request.side == .buy ? AstraXTheme.buy : AstraXTheme.sell)
                                .frame(width: 4, height: 40)
                            VStack(alignment: .leading, spacing: 4) {
                                Text("\(order.request.side == .buy ? "Buy" : "Sell") \(order.request.quantity) ASTR")
                                    .font(.subheadline.weight(.semibold)).foregroundStyle(AstraXTheme.text)
                                Text(order.request.type.rawValue.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.caption).foregroundStyle(AstraXTheme.secondaryText)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 4) {
                                Text(order.lifecycle.rawValue.capitalized)
                                    .font(.caption.weight(.bold)).foregroundStyle(statusColor(order.lifecycle))
                                if order.filledQuantity > 0 {
                                    Text("Filled \(order.filledQuantity)").font(.caption2).foregroundStyle(AstraXTheme.secondaryText)
                                }
                            }
                        }
                        .listRowBackground(AstraXTheme.surface)
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            if order.lifecycle == .accepted || order.lifecycle == .partiallyFilled {
                                Button(role: .destructive) { Task { await model.cancel(order) } } label: {
                                    Label("Cancel", systemImage: "xmark")
                                }
                            }
                        }
                    }
                    .scrollContentBackground(.hidden)
                }
            }
            .background(AstraXTheme.background)
            .navigationTitle("Orders")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") } } }
            .task { await model.start() }
            .onDisappear { model.stop() }
            .alert("Orders", isPresented: Binding(get: { model.errorMessage != nil }, set: { if !$0 { model.errorMessage = nil } })) {
                Button("OK", role: .cancel) { model.errorMessage = nil }
            } message: { Text(model.errorMessage ?? "") }
        }
    }

    private func statusColor(_ status: OrderLifecycle) -> Color {
        switch status {
        case .filled, .accepted: AstraXTheme.positive
        case .partiallyFilled, .submitting, .cancelPending: AstraXTheme.buy
        case .rejected: AstraXTheme.negative
        default: AstraXTheme.secondaryText
        }
    }
}
