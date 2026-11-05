import AuthenticationServices
import DesignSystem
import SwiftUI

public struct LoginView: View {
    @Bindable private var session: SessionViewModel
    @State private var email = ""
    @State private var password = ""
    @State private var isCreatingAccount = false

    public init(session: SessionViewModel) { self.session = session }

    public var body: some View {
        ZStack {
            AstraXTheme.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("ASTRAX").font(.caption.weight(.bold)).tracking(3).foregroundStyle(AstraXTheme.buy)
                        Text("Paper trading,\nwith precision.")
                            .font(.largeTitle.weight(.bold)).foregroundStyle(AstraXTheme.text)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("A simulated exchange client. No real trades or broker connection.")
                            .font(.subheadline).foregroundStyle(AstraXTheme.secondaryText)
                    }
                    CardSurface {
                        VStack(spacing: 16) {
                            TextField("Email", text: $email)
                                .textContentType(.emailAddress).keyboardType(.emailAddress)
                                .textInputAutocapitalization(.never).autocorrectionDisabled()
                                .accessibilityLabel("Email address")
                            Divider().overlay(AstraXTheme.border)
                            SecureField("Password", text: $password)
                                .textContentType(isCreatingAccount ? .newPassword : .password)
                                .accessibilityLabel("Password")
                        }
                        .padding(14)
                        .background(AstraXTheme.raised, in: RoundedRectangle(cornerRadius: 12))
                        .font(.body)
                    }
                    Button {
                        Task {
                            if isCreatingAccount { await session.register(email: email, password: password) }
                            else { await session.login(email: email, password: password) }
                        }
                    } label: {
                        HStack {
                            Spacer()
                            if session.isBusy { ProgressView().tint(.white) }
                            else { Text(isCreatingAccount ? "Create paper account" : "Sign in").fontWeight(.semibold) }
                            Spacer()
                        }
                        .padding(.vertical, 15)
                        .background(AstraXTheme.buy, in: RoundedRectangle(cornerRadius: 12))
                        .foregroundStyle(.black)
                    }
                    .disabled(session.isBusy || email.isEmpty || password.count < 12)
                    .accessibilityHint("Password must contain at least 12 characters")

                    SignInWithAppleButton(.signIn, onRequest: { _ in }, onCompletion: handleApple)
                        .signInWithAppleButtonStyle(.white)
                        .frame(height: 48)
                        .clipShape(RoundedRectangle(cornerRadius: 12))

                    Button(isCreatingAccount ? "Already have an account? Sign in" : "Create a paper account") {
                        isCreatingAccount.toggle()
                    }
                    .frame(maxWidth: .infinity)
                    .foregroundStyle(AstraXTheme.text)

                    Text("Paper trading only. Prices and fills are simulated. This app does not provide investment advice.")
                        .font(.footnote).foregroundStyle(AstraXTheme.secondaryText)
                        .accessibilityAddTraits(.isStaticText)
                }
                .padding(24)
                .frame(maxWidth: 520)
                .frame(maxWidth: .infinity, minHeight: 600, alignment: .center)
            }
        }
        .alert("Unable to sign in", isPresented: Binding(get: { session.errorMessage != nil }, set: { if !$0 { session.errorMessage = nil } })) {
            Button("OK", role: .cancel) { session.errorMessage = nil }
        } message: { Text(session.errorMessage ?? "Please try again.") }
    }

    private func handleApple(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let authorization):
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let token = credential.identityToken,
                  let tokenString = String(data: token, encoding: .utf8) else { return }
            Task { await session.loginWithApple(identityToken: tokenString) }
        case .failure(let error):
            session.errorMessage = error.localizedDescription
        }
    }
}
