import Foundation
import Networking
import Observation
import UIKit
import UserNotifications

@Observable
@MainActor
public final class PushRegistration: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    private let enabledKey = "astrax.fillNotificationsEnabled"
    public private(set) var status = "Off"
    public private(set) var errorMessage: String?
    private var api: APIClient?
    private var pendingToken: String?

    public func configure(api: APIClient) {
        self.api = api
        UNUserNotificationCenter.current().delegate = self
        if let pendingToken { register(pendingToken) }
        if UserDefaults.standard.bool(forKey: enabledKey) {
            Task {
                let settings = await UNUserNotificationCenter.current().notificationSettings()
                guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else {
                    status = "Permission unavailable"
                    return
                }
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    public func enable() async {
        errorMessage = nil
        do {
            let granted = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .badge, .sound])
            guard granted else {
                status = "Permission denied"
                return
            }
            UserDefaults.standard.set(true, forKey: enabledKey)
            UIApplication.shared.registerForRemoteNotifications()
            status = "Waiting for device registration"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        pendingToken = token
        register(token)
    }

    public func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        status = "Unavailable"
        errorMessage = error.localizedDescription
    }

    public func userNotificationCenter(_ center: UNUserNotificationCenter,
                                       willPresent notification: UNNotification,
                                       withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .badge, .sound])
    }

    private func register(_ token: String) {
        guard let api else { return }
        Task {
            do {
                try await api.registerPushToken(token)
                status = "Enabled"
                errorMessage = nil
                pendingToken = nil
            } catch {
                status = "Registration failed"
                errorMessage = error.localizedDescription
            }
        }
    }
}
