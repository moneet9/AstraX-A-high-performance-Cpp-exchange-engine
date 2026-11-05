import LocalAuthentication

public actor BiometricGate {
    public init() {}

    public func authenticate(reason: String = "Confirm this simulated order") async throws -> Bool {
        let context = LAContext()
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {
            throw error ?? BiometricError.unavailable
        }
        return try await context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: reason)
    }
}

private enum BiometricError: Error { case unavailable }
