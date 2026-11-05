import Features
import SwiftUI

@main
struct AstraXApp: App {
    @State private var dependencies = AppDependencies()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView(dependencies: dependencies)
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
