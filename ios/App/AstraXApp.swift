import Features
import SwiftUI

@main
struct AstraXApp: App {
    @State private var dependencies = AppDependencies()
    @UIApplicationDelegateAdaptor(PushRegistration.self) private var pushRegistration
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView(dependencies: dependencies, pushRegistration: pushRegistration)
                .task { pushRegistration.configure(api: dependencies.api) }
                .overlay {
                    if scenePhase != .active {
                        Color.black.ignoresSafeArea().overlay {
                            Text("ASTRAX · PAPER TRADING")
                                .font(.caption.weight(.bold)).tracking(2).foregroundStyle(.white.opacity(0.75))
                        }
                    }
                }
        }
    }
}
