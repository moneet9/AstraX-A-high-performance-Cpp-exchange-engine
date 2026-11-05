import Core
import DesignSystem
import SwiftUI

public struct TradeView: View {
    @State private var model: OrderTicketViewModel
    @State private var isReviewPresented = false

    public init(dependencies: AppDependencies, accountID: Int64) {
        _model = State(initialValue: OrderTicketViewModel(manager: dependencies.orderManager,
            biometric: dependencies.biometricGate, accountID: accountID))
    }

    public var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack {
                        Text("ASTR / USD").font(.headline)
                        Spacer()
                        Text("PAPER").font(.caption.weight(.bold)).foregroundStyle(AstraXTheme.buy)
                    }
                }
                Section("Side and order type") {
                    Picker("Side", selection: $model.side) {
                        Text("Buy").tag(OrderSide.buy)
                        Text("Sell").tag(OrderSide.sell)
                    }.pickerStyle(.segmented)
                    Picker("Order type", selection: $model.kind) {
                        Text("Market").tag(OrderKind.market)
                        Text("Limit").tag(OrderKind.limit)
                        Text("Stop").tag(OrderKind.stop)
                        Text("Stop limit").tag(OrderKind.stopLimit)
                        Text("Iceberg").tag(OrderKind.iceberg)
                        Text("Pegged").tag(OrderKind.pegged)
                    }
                    Picker("Time in force", selection: $model.tif) {
                        Text("GTC").tag(TimeInForce.gtc)
                        Text("IOC").tag(TimeInForce.ioc)
                        Text("FOK").tag(TimeInForce.fok)
                    }
                }
                Section("Order details") {
                    LabeledContent("Quantity") {
                        TextField("Shares", text: $model.quantityText).keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing).accessibilityLabel("Quantity in shares")
                    }
                    if [.limit, .stopLimit, .iceberg].contains(model.kind) {
                        decimalField("Limit price", text: $model.priceText)
                    }
                    if [.stop, .stopLimit].contains(model.kind) {
                        decimalField("Stop price", text: $model.stopPriceText)
                    }
                    if model.kind == .iceberg {
                        LabeledContent("Visible quantity") {
                            TextField("Visible shares", text: $model.visibleQuantityText).keyboardType(.numberPad)
                                .multilineTextAlignment(.trailing)
                        }
                    }
                    if model.kind == .pegged {
                        LabeledContent("Peg offset (ticks)") {
                            TextField("Offset", text: $model.pegOffsetText).keyboardType(.numbersAndPunctuation)
                                .multilineTextAlignment(.trailing)
                        }
                    }
                }
                Section {
                    Button {
                        do { _ = try model.makeRequest(); isReviewPresented = true }
                        catch { model.errorMessage = error.localizedDescription }
                    } label: {
                        HStack {
                            Spacer()
                            Text(model.side == .buy ? "Review buy order" : "Review sell order")
                                .fontWeight(.semibold)
                            Spacer()
                        }
                    }
                    .disabled(model.isSubmitting)
                    .listRowBackground(model.side == .buy ? AstraXTheme.buy.opacity(0.2) : AstraXTheme.sell.opacity(0.2))
                }
                Section {
                    Text("Simulated paper trading only. Orders are matched by the local AstraX engine and do not reach a broker.")
                        .font(.footnote).foregroundStyle(AstraXTheme.secondaryText)
                }
            }
            .scrollContentBackground(.hidden)
            .background(AstraXTheme.background)
            .navigationTitle("Order Ticket")
            .sheet(isPresented: $isReviewPresented) { confirmationSheet }
            .alert("Order update", isPresented: Binding(get: { model.errorMessage != nil || model.resultMessage != nil }, set: { if !$0 { model.errorMessage = nil; model.resultMessage = nil } })) {
                Button("OK", role: .cancel) { model.errorMessage = nil; model.resultMessage = nil }
            } message: { Text(model.errorMessage ?? model.resultMessage ?? "") }
        }
    }

    private func decimalField(_ label: String, text: Binding<String>) -> some View {
        LabeledContent(label) {
            TextField("0.00", text: text).keyboardType(.decimalPad).multilineTextAlignment(.trailing)
                .accessibilityLabel(label)
        }
    }

    private var confirmationSheet: some View {
        NavigationStack {
            VStack(spacing: 20) {
                CardSurface {
                    VStack(spacing: 14) {
                        reviewRow("Action", value: "\(model.side == .buy ? "Buy" : "Sell") ASTR")
                        reviewRow("Type", value: model.kind.rawValue.replacingOccurrences(of: "_", with: " ").capitalized)
                        reviewRow("Quantity", value: "\(model.quantityText) shares")
                        if let request = try? model.makeRequest(), request.priceTicks > 0 {
                            reviewRow("Limit price", value: PriceFormatting.string(ticks: request.priceTicks))
                        }
                        reviewRow("Time in force", value: model.tif.rawValue)
                    }
                }
                Text("Paper trading only · Prices and fills are simulated · Not financial advice")
                    .font(.footnote).multilineTextAlignment(.center).foregroundStyle(AstraXTheme.secondaryText)
                Spacer()
                Button {
                    isReviewPresented = false
                    Task { await model.submitConfirmed() }
                } label: {
                    HStack { Spacer(); Label("Confirm with Face ID", systemImage: "faceid").fontWeight(.semibold); Spacer() }
                        .padding(15)
                        .background(model.side == .buy ? AstraXTheme.buy : AstraXTheme.sell,
                                    in: RoundedRectangle(cornerRadius: 12))
                        .foregroundStyle(.black)
                }
            }
            .padding(20)
            .background(AstraXTheme.background)
            .navigationTitle("Review order")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button("Edit") { isReviewPresented = false } } }
        }
        .presentationDetents([.medium, .large])
    }

    private func reviewRow(_ title: String, value: String) -> some View {
        HStack { Text(title).foregroundStyle(AstraXTheme.secondaryText); Spacer(); Text(value).foregroundStyle(AstraXTheme.text).fontWeight(.medium) }
    }
}
