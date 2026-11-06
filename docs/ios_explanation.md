# iOS App Explanation

This guide describes the native client currently in `ios/`. It is a paper-trading vertical slice and an interview project, not a production broker app. The honest distinction matters: the app source and package structure exist, but this Windows workspace has no Xcode/Swift toolchain, so a simulator build, device run, Instruments trace, and App Store validation have not been completed.

## 1. Two-minute project explanation

> “AstraX is a simulated exchange client. The iOS app is native SwiftUI, targets iOS 17, and is organized as local Swift packages. SwiftUI owns rendering and navigation; `@Observable` main-actor view models adapt domain state into immutable snapshots; actors own network access, order state, book updates, and candle aggregation. REST handles account and order commands, while an authenticated WebSocket streams market and private execution events. Prices and quantities cross the API as integers. A paper order is validated, reviewed, biometrically confirmed, sent with an idempotency key, and reconciled with execution events. The API service connects that client to the existing Python/C++ simulator.”

If asked about production readiness, say the implementation has not yet been compiled or profiled on Apple tooling. Mention the missing candlestick/indicator screen, iPad adaptation, accessibility audit, UI automation, and production deployment configuration directly.

## 2. App structure and libraries

The app entry point is `ios/App/AstraXApp.swift`; the Xcode project is `ios/AstraX.xcodeproj`. The app uses SwiftUI and Apple frameworks only, with local Swift Package Manager modules and no CocoaPods or third-party UI framework.

| Package | Responsibility | Important types |
| --- | --- | --- |
| `Core` | API DTOs, integer tick values, immutable market/book/trade snapshots | `TickPrice`, `BookSnapshotDTO`, `MarketBook`, `OrderRequestDTO` |
| `Networking` | REST, JSON coding, token rotation, WebSocket task creation, TLS pin delegate | `APIClient` actor |
| `MarketData` | WebSocket lifecycle, snapshot/delta sequencing, book state, candle aggregation | `MarketDataHub`, `OrderBookStore`, `CandleAggregator` actors |
| `Persistence` | Keychain session tokens, LocalAuthentication gate, SwiftData candle cache | `KeychainTokenStore`, `BiometricGate`, `CandleRepository` |
| `Trading` | Order lifecycle and API/mock service boundary | `OrderManager` actor, trading service protocol |
| `DesignSystem` | Dark theme, surfaces, semantic colors, price display | `AstraXTheme`, `CardSurface`, `PriceFormatting` |
| `Features` | SwiftUI screens and `@Observable` view models | `RootView`, `SessionViewModel`, `MarketViewModel`, etc. |

The root dependency container `AppDependencies` constructs the shared API client, persistence services, market hub, order manager, and session model. Views receive these dependencies instead of creating separate clients. This is lightweight constructor injection; it is not a full external DI framework.

## 3. Navigation and screen-by-screen walkthrough

`RootView` restores the session in `.task`. If authenticated with an account ID, it shows a `TabView`; otherwise it shows `LoginView`. Tabs currently implemented are Watchlist, Portfolio, Orders, Trade, and Account.

### Login and registration

`LoginView` contains email and password fields, account-creation toggle, email/password sign-in, and Apple sign-in through `AuthenticationServices` (`SignInWithAppleButton`). It displays the paper-trading disclosure and error alert. `SessionViewModel` handles `login`, `register`, `loginWithApple`, `restore`, `logout`, and `deleteAccount`. On successful auth it stores the token pair through `KeychainTokenStore`, fetches the paper account, and updates observable session state. The Apple identity token is sent to the backend; the app does not treat the client credential alone as proof of a backend session.

### Watchlist

`WatchlistView` is a `NavigationStack` with an ASTR row, short line sparkline, midpoint, and LIVE/CONNECTING status. Tapping the row navigates to `MarketScreen`. It visibly labels the instrument and app as simulated. This is currently a single-symbol demonstration, not a full editable watchlist with multiple symbols and flash-on-update behavior.

### Market detail: chart and Level 2

`MarketScreen` displays ASTR/USD, simulated-market status, midpoint, spread, a line chart, and the top five bid/ask levels. `LivePriceChart` draws a normalized path with SwiftUI `Canvas` and `.drawingGroup()`. **It is a simple price line, not a native candlestick chart and not a Swift Charts implementation.** `MarketViewModel` subscribes to the shared `MarketDataHub`, obtains an initial REST book/candles, updates the chart points, and caches candle data where available. The expensive sequence/book and candle calculations belong in actors; observable view state is published on the main actor.

The screen uses `.task(id: model.symbol)` for subscription lifetime and stops on disappearance. The client handles sequence gaps by requesting a fresh snapshot, and the hub reconnects with backoff/jitter. Discuss the code as an implemented design, not as proven zero-loss production streaming: no live Instruments trace or network chaos test has been run.

### Trade / order ticket

`TradeView` uses a SwiftUI `Form`. The user selects buy/sell, order type, time-in-force, and inputs the fields relevant to that type. Supported UI types are market, limit, stop, stop-limit, iceberg, and pegged; TIF choices are GTC, IOC, and FOK. The review sheet summarizes the order, repeats the paper-trading risk disclosure, and requires Face ID / device biometrics through `BiometricGate` before submission. Haptics report result state.

`OrderTicketViewModel.makeRequest()` parses quantity as `Int64`, parses a typed price through `Decimal`, scales to integer engine units, rejects precision beyond four decimal places, and calls `OrderManager.validate`. There is no `Double` in the price/quantity API path. A stable idempotency key is paired with the original request body after first submission; if a timeout makes the outcome uncertain, a retry must resend that exact payload. The lifecycle is presented as accepted, partial, filled, rejected, cancelling, or cancelled based on available server/events.

### Orders

`OrdersView` shows order side, type, lifecycle and filled quantity, supports refresh, and offers a swipe cancellation for accepted or partially filled orders. `OrdersViewModel` loads server state through `OrderManager`, subscribes to execution events through `MarketDataHub`, and applies fills to the manager actor. Stream tasks are cancelled when the view stops. The current event/UI implementation should be extended with stronger reconciliation for reconnects, duplicate fills, and server-authoritative refresh after cancellation.

### Portfolio

`PortfolioView` loads account and position data concurrently with `async let`, then renders simulated cash, positions, and P&L fields returned by the API. It is a basic portfolio screen; it has not received a full product design or financial-calculation audit.

### Account

`AccountView` exposes session/logout and account deletion. Account deletion requires a confirmation and calls the backend deletion endpoint. `AstraXApp` uses a privacy cover when the app backgrounds. The privacy manifest is present, but a manifest is only a declaration: the App Store privacy label must still be checked against actual service, SDK, telemetry, and retention behavior.

### Not implemented as complete UI features

There is no finished AI insights screen, full candlestick/indicator screen, multi-symbol editable watchlist, demo reviewer account package, full iPad-specific layout, snapshot-test suite, or login-to-fill XCUITest. Fill notifications now have an opt-in client flow and APNs token registration, but require valid Apple push credentials and have not been device-verified. Strings are prepared for localization, but translation completeness, Dynamic Type, VoiceOver, Reduce Motion, and color-blind testing still require an audit.

## 4. Concurrency, ownership, and UI smoothness

The main actor owns view models and published view state. It should do small assignments and presentation decisions only. `APIClient` is an actor around URLSession and token state. `MarketDataHub` owns WebSocket connection/reconnect and fan-out; `OrderBookStore` serializes book mutation and sequence application; `CandleAggregator` owns candle math; `OrderManager` owns order-state transitions. These actors prevent unsynchronized shared mutation. Actors do not automatically make every operation non-blocking: synchronous CPU-heavy work inside an actor still occupies an executor thread, so aggregation must remain bounded or move to an appropriate worker.

`AsyncStream` connects actors to view models. Book streams buffer the newest state; execution streams have a bounded buffer. Stream continuation termination removes subscribers. SwiftUI `.task` and explicit `Task.cancel()` are used to end subscriptions with view lifetime. `MarketDataHub` coalesces high-rate publication to roughly ten updates per second, a sensible first limit for this UI.

These are good smoothness-oriented choices, but no performance claim is measured yet. To prove responsiveness on a Mac/iOS device: build with Xcode, run Instruments SwiftUI + Time Profiler + Hitches, inspect the `OSSignposter` market-data interval, run under rapid feed/reconnect and long lists, and verify frame pacing and worst UI stalls. Do not claim a 120 fps result without a trace; the current chart is a small line chart, not a benchmarked depth/candlestick renderer.

## 5. API and WebSocket flow

`APIClient` owns JSON encoder/decoder, URLSession, base URL, pins, and access/refresh tokens. REST paths use `/v1`. It provides login/register/Apple login, refresh/logout, symbols/accounts/book/orders/positions/candles, order placement/cancel/replace, and account deletion. GET calls retry transient failures; idempotent order submission may retry with the same key. A 401 attempts refresh and repeats with the rotated access token. Cancellation propagates.

Market connection flow:

1. `MarketDataHub.connect` registers a consumer and opens one shared socket as needed.
2. Client refreshes token, obtains bearer token, opens WebSocket `/v1/market` and sends auth then subscribe messages.
3. Server sends a JSON book snapshot followed by sequenced deltas and heartbeats; private execution frames are routed to the execution stream.
4. `OrderBookStore` applies only valid next sequence updates. A gap triggers REST snapshot resync; disconnect schedules jittered exponential backoff.
5. Hub coalesces market snapshots and sends immutable values to views; execution events update order state separately.

Prices use integer fixed-point values (the engine scale is 10,000 units per displayed price unit). Formatting converts at the UI boundary. Never convert a price to `Double` and back for an order.

## 6. Security, App Store compliance, and what can be claimed

Implemented measures include Keychain token storage using device-only accessibility, Face ID confirmation, refresh-token rotation support, ATS-related configuration, a certificate pinning delegate, app-switcher privacy overlay, account-deletion control, paper-trading disclosures, and a privacy manifest. These are controls, not proof of compliance. The release base URL is a placeholder until configured; certificate pins must match a deployed certificate/public key and have a rotation plan. Check `ITSAppUsesNonExemptEncryption` against the shipped cryptography and export-compliance answers. Confirm privacy labels from actual collection and third-party SDK behavior. Prepare App Review notes and a working demo account. Complete accessibility and legal/product review. No claim should be made that App Review has approved this app.

## 7. Interview questions to rehearse

**Why actors?** They isolate mutable book/order/network state and serialize access. They avoid lock coordination in Swift concurrency, but do not justify doing unbounded CPU work on the main actor.

**Why `@Observable` plus `@MainActor`?** SwiftUI needs predictable UI state updates. The view model is main-actor isolated; services remain actors. Keep only presentation state on the UI actor.

**Why idempotency?** A request timeout does not tell the client whether the server committed the order. Reusing a key with the exact same body lets the server return the original result instead of creating a duplicate.

**How do you handle a sequence gap?** Stop trusting the local book, fetch a REST snapshot with its sequence, then resume deltas from the next sequence. Never silently apply a delta on top of stale state.

**How do you prove performance?** Build and profile on device with Instruments, use signposts from event decode/publication, test worst-case update bursts and reconnect, and report measured numbers with device/OS/feed rate. The current repo has no such result.

**What is the principal limitation?** This is a vertical slice with source-level structure; Apple build/device verification and several production UI/quality gates remain outstanding.

## 8. File map

- `ios/App/AstraXApp.swift`, `ios/AstraX.xcodeproj` — app lifecycle and Xcode target.
- `ios/Packages/Features/Sources/Features/RootView.swift` — auth gate and tabs.
- `LoginView.swift`, `SessionViewModel.swift` — authentication UI/state.
- `WatchlistView.swift`, `LivePriceChart.swift`, `MarketViewModel.swift` — watchlist and market view.
- `TradeView.swift`, `OrderTicketViewModel.swift`, `OrdersView.swift`, `OrdersViewModel.swift` — order flow.
- `PortfolioView.swift`, `AccountView.swift` — account-related screens.
- `ios/Packages/Networking` — REST/WebSocket transport and TLS pinning.
- `ios/Packages/MarketData`, `Trading`, `Persistence`, `Core`, `DesignSystem` — domain/service modules.
- `ios/App/PrivacyInfo.xcprivacy`, `ios/Configuration/*.xcconfig` — privacy and environment configuration.
