# AstraX iOS

Native SwiftUI paper-trading client for iOS 17+. The app uses local Swift packages, Swift 6 strict concurrency, and no CocoaPods or JavaScript runtime. The C++ engine remains the matching authority through the Python service.

## Open and run

Open `AstraX.xcodeproj` in Xcode 16 or newer. The Debug configuration points at the local API (`http://localhost:8780`) and allows the simulator's local-network connection. Start PostgreSQL, Redis, the C++ bindings, and the backend first; follow [`../backend/README.md`](../backend/README.md). For a physical device, set `ASTRAX_API_URL` to the development machine's reachable address.

Release builds fail closed for HTTPS unless `ASTRAX_CERT_PINS` is populated with comma-separated SHA-256 hashes of the API leaf certificate DER. Set a real HTTPS API URL in `Configuration/Release.xcconfig` before archiving; the checked-in `.invalid` host is an intentional placeholder. ATS remains strict, including for production.

## Included flow

- Email/password registration and login, plus Sign in with Apple.
- Watchlist quote, live line chart, and top-five level-two book.
- Market, limit, stop, stop-limit, iceberg, and pegged order ticket with GTC/IOC/FOK, local validation, review sheet, Face ID confirmation, and haptic result.
- Orders with live private execution events and cancellation; portfolio and account screens.
- Paper trading disclosure, account deletion, Keychain `ThisDeviceOnly` sessions, app-switcher privacy cover, local candle cache, and `PrivacyInfo.xcprivacy`.

Every submitted price and quantity stays in `Int64` engine units. `Decimal` is used only when converting a typed display price into integer ticks or formatting a value for display. Buy and sell use text labels and blue/coral cues so color is not the only signal.

## Package map

| Package | Responsibility |
| --- | --- |
| `Core` | Integer-tick money, API models, immutable market snapshots |
| `Networking` | REST, token rotation, retry, WebSocket construction, certificate pinning |
| `MarketData` | `MarketDataHub`, `OrderBookStore`, `CandleAggregator`, reconnect/resync |
| `Persistence` | Keychain, biometric gate, SwiftData candle cache |
| `Trading` | Order state machine, order manager, protocol-based trading service |
| `DesignSystem` | Dark-first colors, cards, price formatting |
| `Features` | Observable view models and SwiftUI screens; includes a mock trading service |

## Threading model

SwiftUI view models are `@MainActor` and receive immutable `Equatable` values. Network I/O and JSON decoding run in `APIClient` and `MarketDataHub` actors. `OrderBookStore`, `CandleAggregator`, and `OrderManager` are actors. Candle aggregation and chart normalization run in the `CandleAggregator` actor. Stream consumers are tied to SwiftUI `.task` lifetimes, use newest-value buffering, and cancel their tasks when views disappear. The server publishes at 10 Hz; the client coalesces faster messages before publishing snapshots.

`MarketDataHub` emits an `OSSignposter` interval named “MarketData decode to view model”. Inspect it with Instruments alongside SwiftUI, Time Profiler, and Hitches. The iOS client has not yet been profiled on a physical device; no frame-rate or latency target is claimed.

## Checks

On macOS with Xcode and Swift 6:

```sh
swift test --package-path ios/Packages/Core
swift test --package-path ios/Packages/Trading
xcodebuild build -project ios/AstraX.xcodeproj -scheme AstraX -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO
```

The GitHub Actions iOS workflow runs SwiftLint, swift-format, package tests, and an iOS Simulator build. This workspace is on Windows and cannot run Xcode or Instruments.
