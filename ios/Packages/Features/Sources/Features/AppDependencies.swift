import Core
import Foundation
import MarketData
import Networking
import Persistence
import Trading

@MainActor
public final class AppDependencies {
    public let api: APIClient
    public let keychain: KeychainTokenStore
    public let biometricGate: BiometricGate
    public let marketData: MarketDataHub
    public let orderManager: OrderManager
    public let candleRepository: CandleRepository?
    public let session: SessionViewModel

    public init() {
        let info = Bundle.main.infoDictionary ?? [:]
        let base = URL(string: info["ASTRAX_API_URL"] as? String ?? "https://localhost:8780")!
        let pins = Set((info["ASTRAX_CERT_PINS"] as? String ?? "").split(separator: ",").map(String.init))
        api = APIClient(configuration: APIConfiguration(baseURL: base, certificatePins: pins))
        keychain = KeychainTokenStore()
        biometricGate = BiometricGate()
        marketData = MarketDataHub(api: api)
        orderManager = OrderManager(api: api)
        candleRepository = try? CandleRepository()
        session = SessionViewModel(api: api, keychain: keychain)
    }
}
