import DesignSystem
import Networking
import SwiftUI

public struct AccountView: View {
    @Bindable private var session: SessionViewModel
    let api: APIClient
    let accountID: Int64
    @Bindable private var pushRegistration: PushRegistration
    @State private var confirmDelete = false
    @State private var errorMessage: String?

    public init(session: SessionViewModel, api: APIClient, accountID: Int64, pushRegistration: PushRegistration) {
        self.session = session
        self.api = api
        self.accountID = accountID
        self.pushRegistration = pushRegistration
    }

    public var body: some View {
        NavigationStack {
            List {
                Section("Account") {
                    LabeledContent("Account", value: "Paper · \(accountID)")
                    LabeledContent("Mode", value: "Simulation")
                }.listRowBackground(AstraXTheme.surface)
                Section("Risk disclosure") {
                    Text("AstraX is a paper-trading simulator. Orders, balances, prices, and fills are simulated. This app is not a broker, does not handle real funds, and does not provide financial advice.")
                        .font(.footnote).foregroundStyle(AstraXTheme.secondaryText)
                }.listRowBackground(AstraXTheme.surface)
                Section("Notifications") {
                    LabeledContent("Fill alerts", value: pushRegistration.status)
                    Button("Enable fill notifications") { Task { await pushRegistration.enable() } }
                    if let error = pushRegistration.errorMessage {
                        Text(error).font(.footnote).foregroundStyle(AstraXTheme.negative)
                    }
                }.listRowBackground(AstraXTheme.surface)
                Section {
                    Button("Sign out", role: .destructive) { Task { await session.logout() } }
                    Button("Delete paper account data", role: .destructive) { confirmDelete = true }
                }.listRowBackground(AstraXTheme.surface)
            }
            .scrollContentBackground(.hidden)
            .background(AstraXTheme.background)
            .navigationTitle("Account")
            .confirmationDialog("Delete all paper account data?", isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("Delete account data", role: .destructive) {
                    Task {
                        do {
                            try await api.deleteAccount()
                            await session.logout()
                        } catch { errorMessage = error.localizedDescription }
                    }
                }
            } message: {
                Text("This permanently deletes the simulator account, orders, fills, and positions.")
            }
            .alert("Account deletion failed", isPresented: Binding(get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })) {
                Button("OK", role: .cancel) { errorMessage = nil }
            } message: { Text(errorMessage ?? "") }
        }
    }
}
