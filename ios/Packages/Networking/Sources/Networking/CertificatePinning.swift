import CryptoKit
import Foundation
import Security

public final class CertificatePinningDelegate: NSObject, URLSessionDelegate, @unchecked Sendable {
    private let pins: Set<String>

    public init(pins: Set<String>) {
        self.pins = Set(pins.map { $0.lowercased().replacingOccurrences(of: ":", with: "") })
    }

    public func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                          completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust,
              SecTrustEvaluateWithError(trust, nil),
              let certificate = SecTrustGetCertificateAtIndex(trust, 0) else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }
        let digest = SHA256.hash(data: SecCertificateCopyData(certificate) as Data)
        let fingerprint = digest.map { String(format: "%02x", $0) }.joined()
        guard pins.contains(fingerprint) else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }
        completionHandler(.useCredential, URLCredential(trust: trust))
    }
}
