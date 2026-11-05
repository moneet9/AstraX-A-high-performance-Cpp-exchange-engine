# AstraX React Native Trading App Interview Preparation

## Project pitch

“I built AstraX as a simulated trading app using React Native and TypeScript, a FastAPI service, and a C++ matching engine. The app has no login: it shows a live simulated quote, order book and recent trades, and lets a user submit a batch of mock orders. The API validates orders, queues them to a single matching worker for the symbol, and streams sequenced full-book snapshots to the app. I designed bounded queues so overload is visible and slow clients don’t accumulate an unlimited backlog. The C++ engine applies price-time priority. AstraX is a simulator, not a broker-connected trading product.”

## Be precise about project scope

The mobile client is Expo / React Native / TypeScript. Its public simulator API is a separate FastAPI app on port 8770; the existing dashboard service remains separate. The mobile API configures one symbol (`ASTR`), with one bounded queue and worker, a batch endpoint, metrics, and a WebSocket that publishes sequenced full-book snapshots. This demonstrates good concurrency boundaries for a simulator, but it is not a distributed, horizontally scaled broker backend. There is no real account, exchange connection, durable order lifecycle, cancel/replace flow, market-data entitlement, or production audit trail. Distinguish current implementation from production design in every interview answer.

## Concurrency and responsiveness in plain language

The key interview idea is: **keep the UI thread for interaction, keep network waits asynchronous, and give each order book one clear writer.** A quote can be refreshed many times, but order input, navigation, and confirmation must still respond immediately.

- **In React Native:** `fetch` and WebSocket work are asynchronous, so they should not block rendering. Store the latest book snapshot and avoid recalculating or rerendering unrelated screens for each message. Coalesce replaceable quote snapshots, virtualize long trade/order lists, and profile release builds before optimizing.
- **In the Python API:** FastAPI’s `async def` handles concurrent network waits efficiently. It does not make CPU-heavy or blocking functions magically parallel. AstraX puts C++ calls behind a bounded per-symbol queue, but currently invokes the binding synchronously on the event loop and holds the GIL. For higher load, profile this path, then move matching to a dedicated worker and release the GIL only around native work that uses owned, thread-safe data. Keep queue capacity, ordering, result delivery, and shutdown behavior explicit.
- **For matching:** multiple submissions for the same symbol must have one deterministic sequence. A single worker owns that book and processes commands in queue order. Different symbols can have independent workers. This avoids racing two mutations of the same order book while still enabling cross-symbol parallelism.
- **For slow clients:** use a one-slot or otherwise bounded outbound queue for complete replaceable market snapshots. Drop an older pending snapshot and keep the newest. If the protocol uses incremental deltas instead, a gap means stop applying deltas and request a fresh snapshot.
- **For order commands:** never silently drop an accepted order. Return an explicit overload response when the bounded input queue is full. Use an idempotency key for safe retries and return a status that distinguishes received, queued, accepted, partially filled, filled, and rejected.

The current mobile API uses a bounded `asyncio.Queue` and one worker task for ASTR and publishes full snapshots every 100 ms while clients are connected. It measures HTTP request latency plus queue and engine duration. Important nuance: the worker calls the C++ binding synchronously, and the binding does not release Python’s GIL. A long match can therefore briefly block the asyncio event loop. Do not claim that the current service is multithreaded or that the queue makes C++ execution nonblocking. A next measured improvement would move matching to a dedicated per-symbol thread or process, preserve one-writer ordering, and make a safe native binding boundary that releases the GIL while C++ works on owned data.

## What a full brokerage trading app usually needs

Use this as domain vocabulary in interviews. These are product expectations and design topics, not features to claim for AstraX today.

- **Market discovery:** watchlists, symbol search, quotes, market status, charts, and sometimes depth. Quotes need a source timestamp and a visible stale/delayed state.
- **Order workflow:** order ticket, review/preview, server-side validation, accepted/rejected acknowledgement, open orders, partial fills, cancel/replace, and final fills. A timed-out POST needs an idempotent recovery path.
- **Account context:** positions, cash/buying power, margin/risk checks, executions, and account-specific permissions. These require authentication and server-side authorization.
- **Live data:** streaming market data is a separate read path from order commands. Each stream needs versioning, sequence numbers, snapshots, heartbeat, reconnect, and bounded fanout.
- **Operational correctness:** durable audit events, deterministic order sequencing, explicit market-hours/order-type rules, monitoring, incident response, privacy controls, and tested deployment/recovery.

For AstraX, the credible demo is intentionally narrower: one simulated symbol, public market snapshots, a mock order ticket, batch order submission, and an in-memory C++ book. In an interview, explain how the broader concepts would be added without implying the simulator already handles real accounts or live brokerage orders.

## 35 questions on UI and mobile app development

### Architecture, UI, and product decisions

**1. How would you describe the mobile architecture?**

**Answer:** “I use React Native and TypeScript. `App.tsx` owns the simulator screens and local ticket state, `src/api.ts` centralizes HTTP configuration and typed calls, and `src/socket.ts` owns the reconnecting market stream. The mobile app uses public simulator routes, with no account or login flow. For this compact demo, hooks are enough; I’d add a server-state cache if screens and API workflows grew.”

**Follow-up:** What would make you introduce a state-management library? **Answer:** “Multiple screens needing normalized shared entities, complex cache invalidation, offline mutations, or many independent async workflows. I’d first define server state separately from short-lived UI state, then choose a library based on those needs.”

**2. What user problem does the interface solve?**

**Answer:** “It lets a user inspect a simulated market and submit mock orders from a phone. The app has Markets, Trade, and Activity tabs. A live status label shows whether the market snapshot stream is connected, and the ticket supports a batch of orders without adding account setup to a simulator demo.”

**Follow-up:** How do you know the navigation is understandable? **Answer:** “I’d validate it with task-based usability sessions: ask a first-time user to find the spread, submit a batch, and inspect its result, then track completion time and errors. The repository doesn’t include usability-study results.”

**3. How did you choose what belongs on the market screen?**

**Answer:** “I surfaced the simulated symbol and a prominent price with bid and ask, then made the card open the detailed book and recent trades. The order ticket is a separate tab so browsing market data doesn’t accidentally submit an order.”

**Follow-up:** Why not show every book level on the first screen? **Answer:** “Depth is useful when requested, but it competes with the headline quote and consumes mobile space. I show top-of-book first and put up to ten levels in the detail view.”

**4. How do you communicate that this is simulated trading?**

**Answer:** “The interface labels the app and order ticket as simulated or mock trading, and the mobile README explicitly says it does not connect to a broker or exchange. I’d keep the label adjacent to order confirmation and order results so it remains clear in the highest-risk flow.”

**Follow-up:** What would you change before a financial production app? **Answer:** “A full risk, compliance, suitability, audit, and security review, plus a clear separation between simulation and live modes. I would never make a live order look like the current mock order flow.”

**5. How do you support light and dark appearance?**

**Answer:** “The app reads `useColorScheme()` and chooses background, card, text, and muted colors from a small palette. I’d centralize those tokens and verify contrast and semantic colors across both modes rather than scattering one-off colors as the UI grows.”

**Follow-up:** How do you prevent color from being the only signal? **Answer:** “Pair color with text and shape. For example, buy/sell and stale states should have readable labels, not only green, red, or amber.”

**6. How do you make the layout responsive across iPhones and iPads?**

**Answer:** “I use flexible containers, `flex: 1`, wrapping content, and scrollable content rather than fixed screen coordinates. For a production polish pass, I’d use `useWindowDimensions()` and breakpoints: a single-column phone layout and a two-pane tablet layout, while respecting safe areas, orientation, and Dynamic Type.”

**Follow-up:** What is a concrete tablet adaptation? **Answer:** “Keep the book and trade tape side by side, with the order ticket in a persistent third pane when width permits. On compact widths, return to the current stacked screen.”

**7. What makes the UI feel fast?**

**Answer:** “The app renders local state immediately, limits the visible book to ten levels and the trade list to ten rows, and uses `FlatList` for scalable list rendering where the data grows. I would measure interaction-to-feedback and render time on real devices before claiming a performance improvement.”

**Follow-up:** What would you profile first if scrolling stuttered? **Answer:** “Use React Native performance tooling and Xcode Instruments to locate JS-thread stalls, expensive renders, layout work, and image or native-module costs. Then memoize stable rows or reduce update frequency only where profiling identifies a bottleneck.”

**8. Why should you use `FlatList` instead of mapping a long array in a `ScrollView`?**

**Answer:** “`FlatList` virtualizes rows, so it can keep a window of items mounted instead of rendering an arbitrarily long list at once. The current detailed book is small and maps ten levels, but I used `FlatList` as the appropriate pattern for a growing activity or order history.”

**Follow-up:** What would you tune? **Answer:** “Stable keys, `getItemLayout` for fixed-height rows, `initialNumToRender`, and `windowSize`, measured against memory and scroll behavior. I wouldn’t tune blindly for a ten-row list.”

**9. How do you handle empty, loading, error, and stale states?**

**Answer:** “The client has a busy state during batch submission, inline validation and API errors, an empty trade/activity state, and a reconnecting indicator driven by the market socket. It keeps the last quote visible while warning that the stream is reconnecting.”

**Follow-up:** Why is stale data different from an error? **Answer:** “The last known book can still be useful, but its freshness is unknown. I keep it visible with a warning and should timestamp it so the user can judge how old it is.”

**10. How would you make accessibility part of the implementation?**

**Answer:** “I’d add accessibility labels, roles, and hints to controls, verify VoiceOver order, support larger text without clipping, check contrast in both themes, and ensure the order confirmation is announced. The current code has readable text but is not a complete accessibility implementation.”

**Follow-up:** How would a VoiceOver user operate the order ticket? **Answer:** “Each side/type selector should expose selected state, fields should have clear labels and validation guidance, and the final button should announce the order summary before submission.”

### React Native implementation

**11. Why React Native for this project?**

**Answer:** “It let me build a cross-platform simulator UI in TypeScript while keeping a shared API and socket client. It fits this portfolio project’s conventional screens and network-driven data. I focus on clear component structure, performance, accessibility, and device testing rather than claiming this is a native Swift app.”

**Follow-up:** What is the cost of React Native? **Answer:** “The app depends on the JS runtime and native modules, and platform-specific behavior still needs testing. A shared codebase reduces duplication, but it doesn’t remove iOS build, lifecycle, or accessibility work.”

**12. What platform-specific behavior still matters in React Native?**

**Answer:** “The screen code is shared, but networking permissions, safe areas, keyboard behavior, app lifecycle, release builds, and accessibility still need device-level testing on iOS and Android. This project uses React Native, so I’d describe it as cross-platform mobile work rather than claim native Swift implementation.”

**Follow-up:** What React Native skills matter most here? **Answer:** “State ownership, navigation, list rendering, JS/native performance boundaries, platform behavior, accessibility, networking, and release-build debugging.”

**13. How did you organize reusable network code?**

**Answer:** “`api.ts` contains a typed request helper that adds JSON and request-ID headers, checks `response.ok`, and parses structured errors. Its methods group book, trades, and batch order submission so the screen doesn’t construct endpoint URLs directly.”

**Follow-up:** What would you add to the request helper? **Answer:** “Timeout/cancellation, structured error types, schema validation for untrusted JSON, request IDs, and safe retry rules. I would not automatically retry a non-idempotent order POST without an idempotency key.”

**14. How do you manage configuration for local device testing?**

**Answer:** “The client reads `EXPO_PUBLIC_API_URL` and `EXPO_PUBLIC_WS_URL`; the API module defaults to port 8770 on localhost for iOS Simulator and uses the Android emulator’s special host for Android. A physical phone needs the laptop’s LAN address and the FastAPI server listening on that interface.”

**Follow-up:** What network issue often surprises developers? **Answer:** “`localhost` on a physical phone means the phone itself, not the development computer. The phone and laptop need the same network, and development HTTP access must be configured intentionally.”

**15. How would you manage screen state as the app expands?**

**Answer:** “I’d split screens into focused components and put remote data in a cache with explicit loading, freshness, and mutation state. Form state would remain local. I’d avoid duplicating the same portfolio or book across screens and define which layer owns each piece of data.”

**Follow-up:** Would you adopt Redux immediately? **Answer:** “No. I’d choose it only if the shared state and event flows justify it. A server-state cache may solve refetching and cache invalidation better than putting every API result in a global reducer.”

**16. How do you manage app lifecycle and socket cleanup?**

**Answer:** “The app effect creates a `MarketSocket`, connects, and closes it in cleanup. `close()` marks it stopped and clears its reconnect timer. For background/foreground behavior, I’d listen to React Native `AppState`, suspend unnecessary updates while backgrounded, and refresh the full snapshot on foreground.”

**Follow-up:** Why not keep the socket alive in the background indefinitely? **Answer:** “iOS may suspend the app, network connections can die, and continuous background activity costs battery. I’d rely on a foreground reconnect and a fresh snapshot unless a justified background mode is approved and supported.”

**17. Why did you remove login from this simulator app?**

**Answer:** “The goal here is to demonstrate the trading interface and API flow, so I removed account setup to make the simulator immediately usable. The new mobile API is explicitly a public mock service. A real brokerage app must restore authentication, account authorization, and protected account data before supporting live trading.”

**Follow-up:** Does public access mean the real backend should be unauthenticated? **Answer:** “No. Only the local mock simulator is public. A broker service must authenticate and authorize every account operation server-side.”

**18. What account security would a real trading app require?**

**Answer:** “Strong authentication, session expiry/revocation, secure credential storage, TLS, device/session management, authorization on every account endpoint, and audit records. Biometrics can unlock a locally protected session but do not replace server authorization.”

**Follow-up:** Should market data and account data use the same permissions? **Answer:** “Not necessarily. Market data may be public or entitlement-based, while balances, orders, and portfolio data must be tied to an authenticated account and checked on every request.”

**19. What happens if a phone loses connectivity during order entry?**

**Answer:** “The UI should keep the typed order, show connection status, and avoid claiming submission succeeded until it receives a server result. If the request might have reached the server, the client needs an idempotency key and a status lookup before retrying.”

**Follow-up:** Why not queue it offline automatically? **Answer:** “The market and risk state may change before delivery. Any deferred order needs explicit product semantics, expiry, and server-side duplicate protection.”

**20. How would you secure a live order confirmation?**

**Answer:** “I validate quantity, order count, and limit-price tick in the client, then show pending feedback and each server result. The API repeats validation as the authority. The current client order ID is a correlation value only; it is not yet a durable idempotency guarantee.”

**Follow-up:** Why is client validation insufficient? **Answer:** “A modified client can bypass it. The backend must validate every field, enforce limits, and return explicit reason codes.”

### Real-time data, reliability, and app quality

**21. How does the live order book update?**

**Answer:** “The public mobile socket connects to `/ws/v1/market` and applies versioned, sequenced full-book snapshots to React state. It needs no login or subscription handshake in the current one-symbol simulator.”

**Follow-up:** Why use snapshots for this version? **Answer:** “The client can replace stale state with each complete book and recover after reconnect without reconstructing missed changes. If bandwidth becomes a measured problem, I can add delta messages plus explicit gap detection and resync.”

**22. How does reconnect and backoff work?**

**Answer:** “On close, the socket marks data stale and reconnects with exponential backoff capped at 20 seconds with jitter. On open it waits for a full snapshot. This limits synchronized retry bursts and restores the latest market state after a network interruption.”

**Follow-up:** What could go wrong with retries? **Answer:** “A timer can survive after the screen is gone or multiple connection attempts can overlap. The current class stops reconnects on explicit close; I’d test repeated close/open races and consider a connection generation ID.”

**23. How do you detect missing market updates?**

**Answer:** “The server increments a sequence when a symbol book changes and publishes complete snapshots. The current client uses each snapshot as the latest book; it reconnects and receives a new snapshot rather than applying deltas.”

**Follow-up:** What would you add if the client later consumes deltas? **Answer:** “Track the last sequence, apply only the next sequence, mark data stale on a gap, stop applying further deltas, and request a complete snapshot before resuming.”

**24. How would you reduce bandwidth and rendering work?**

**Answer:** “First I’d measure payload and render cost. Then I’d send changed levels with sequence numbers, batch updates at a controlled cadence, and update only affected rows. I’d retain a snapshot/resync mechanism and avoid displaying a partial book after a gap.”

**Follow-up:** Why not update on every tick? **Answer:** “More frequent updates can saturate the JS thread and battery without improving perceived usefulness. I’d choose a cadence based on user needs and measured latency, and ensure order confirmations remain immediate.”

**25. How do you prevent stale network responses from overwriting newer state?**

**Answer:** “The current request helper does not implement request generations or cancellation, so I’d add them when screens can rapidly change symbols or issue overlapping refreshes. A request ID or AbortController can ignore a response that no longer matches the active symbol/session.”

**Follow-up:** How would you handle reconnect snapshot ordering? **Answer:** “Reset or validate the per-symbol sequence state when a fresh snapshot arrives, and only apply messages from the current connection generation.”

**26. How do you handle order submission uncertainty?**

**Answer:** “The client sends a unique `client_order_id` for every member of a batch and displays each returned status. This is only a correlation ID today, not server-enforced idempotency. For reliable retries, I’d persist an idempotency key on the server and return the first result when the same key is retried.”

**Follow-up:** What if the server processes the batch but the response is lost? **Answer:** “The current API does not yet guarantee safe retry or batch deduplication. A production API needs a durable batch ID and per-order idempotency records so a retry can return original outcomes instead of submitting duplicates.”

**27. How should a real-time trading app surface fills and order status?**

**Answer:** “A real app should show the immediate submit acknowledgement, then stream later order-state changes and partial/full fills. The simulator shows the batch response and retains results in the current screen; it does not yet provide durable order history or private fill events.”

**Follow-up:** Why can’t the app assume an order response means it is filled? **Answer:** “An order can be accepted and remain open, partially filled, canceled, or rejected. The UI must model the lifecycle, not collapse every response into success/failure.”

**28. How would you test the UI and networking?**

**Answer:** “I’d unit test formatting and API validation, mock HTTP and WebSocket boundaries for UI behavior, and add device-level flows for reconnect, batch submission, and partial batch rejection. The repository includes tests for formatting and sequence-gap utility behavior; I’d report exact results only after running them.”

**Follow-up:** What is one important failure scenario? **Answer:** “Drop the WebSocket after a few book messages, verify the UI becomes stale, reconnect and resubscribe, then ensure a snapshot restores the correct state without applying an older message.”

**29. What would you measure to prove the app is responsive?**

**Answer:** “I’d measure cold/warm launch, screen transition response, time to first market snapshot, UI frame drops, JS-thread stalls, order-submit round-trip percentiles, reconnect recovery time, and battery/network use under a defined test. I would not substitute engine microseconds for user-perceived latency.”

**Follow-up:** How do you separate client and server latency? **Answer:** “Add request and trace IDs and timestamp client send, server receive, engine submit, server response, and client receive. Keep clock-synchronization limits in mind; same-process duration measurements are more reliable than subtracting unsynchronized wall clocks.”

**30. How do you handle number formatting and price precision?**

**Answer:** “The API returns prices as fixed-point integers with a scale of 10,000. The app converts them for display using shared formatting helpers and multiplies a typed limit price by 10,000 before submission. I’d make parsing decimal-safe and align input validation with the symbol’s tick size to avoid floating-point rounding errors.”

**Follow-up:** Why not store money as a JavaScript number? **Answer:** “Integer fixed-point is safer for exact tick comparisons, but JavaScript’s safe-integer range still matters. I’d bound values, use a decimal library or strings for larger values, and define rounding explicitly.”

**31. How do you keep order entry usable on a small screen?**

**Answer:** “I use numeric keyboards for quantity and price, conditionally hide the price field for market orders, and separate buy/sell and limit/market choices. I’d also handle keyboard avoidance, field-level validation, and a review summary so the confirm button stays visible and unambiguous.”

**Follow-up:** What validation feedback should happen inline? **Answer:** “Reject blank, nonpositive, invalid-tick, or out-of-range values before enabling confirmation, while still treating the API as authoritative. Preserve input and show a human-readable reason if the server rejects the order.”

**32. What analytics or crash data would you add?**

**Answer:** “For a real app I’d add privacy-reviewed crash reporting and coarse performance events: screen load, API failure class, reconnect count, and order outcome. I’d avoid collecting credentials, raw account details, or sensitive order data unless there is a clear purpose and consent.”

**Follow-up:** How would you debug a user-specific failure? **Answer:** “Use a correlation ID and sanitized structured logs on the server; the client can show that ID for support. Keep secrets and personal data out of logs.”

**33. How would you support offline use?**

**Answer:** “I would allow read-only viewing of a clearly timestamped cached snapshot, but I would not queue simulated or live trading commands blindly. On reconnect, refresh from the server and show whether data is current.”

**Follow-up:** Why not queue an order offline? **Answer:** “The market and user risk state may change before delivery. Queuing a financial command can create surprising execution; it needs explicit product semantics and server-side expiry and idempotency.”

**34. How do you prepare a React Native app for release?**

**Answer:** “I’d create Expo development and release builds, configure bundle IDs, signing, versioning, privacy disclosures and permissions, use TLS endpoints, and test on real supported devices. This repository currently documents local Expo development, not store-release readiness.”

**Follow-up:** Why test release builds? **Answer:** “Development builds can have different performance and behavior. I’d validate startup, scrolling, memory, reconnects, and network behavior in the build users will actually install.”

**35. What is your strongest UI engineering story from this project?**

**Answer:** “I connected a real-time market view to the backend while making connection health visible. The socket reconnects with backoff, receives complete sequenced snapshots, and drives the stale indicator. The order ticket sends a batch request and presents results without blocking navigation. That’s a practical example of designing for network failure and keeping the UI responsive.”

**Follow-up:** What would you improve next? **Answer:** “Split `App.tsx` into reusable screens, add a persistent order history endpoint, and introduce deltas only if bandwidth measurements justify them and snapshot/resync semantics stay clear.”

## 15 questions on API and server scalability

**36. Describe the backend in this project.**

**Answer:** “The mobile client uses a dedicated FastAPI application on port 8770. Pydantic models validate orders, HTTP exposes health, symbols, book, trades, single-order and batch-order routes, and a WebSocket publishes market snapshots. FastAPI routes order commands to a bounded per-symbol queue whose single worker owns that matching engine.”

**Follow-up:** Is it production-ready? **Answer:** “No. It is a public local simulator with one configured symbol, in-memory book state, no broker connection, no durable order history, and no production identity or market-data entitlements. I describe the service boundaries and production requirements separately.”

**37. How would you scale HTTP reads?**

**Answer:** “Keep market reads lightweight and serve the latest snapshot from a read model instead of making the UI poll the matching engine. In this demo the engine is local and only one API process owns it. To add API replicas, I’d move market snapshots and order routing behind shared services rather than create a separate in-memory engine per replica.”

**Follow-up:** Would you cache the live book? **Answer:** “A cache can serve snapshots but must carry sequence/version and freshness metadata. A stale cache must never be presented as current without a timestamp or resync path.”

**38. How would you scale WebSocket fanout?**

**Answer:** “For a larger service, use WebSocket gateways that subscribe to a sequenced market-data bus. Partition streams by symbol, support initial snapshots and resync, and apply bounded per-client queues. AstraX currently publishes full snapshots from one process; a broker and gateway fleet are future scaling steps.”

**Follow-up:** Why partition by symbol? **Answer:** “It preserves ordering within a symbol and allows independent symbols to scale across partitions. A single symbol remains a single ordered stream unless the matching model is fundamentally changed.”

**39. How do you prevent one slow mobile client from blocking others?**

**Answer:** “Use bounded per-connection queues, detect lag, coalesce replaceable market snapshots, and disconnect clients that exceed a limit. Never let a slow socket writer block the matching or global broadcast loop.”

**Follow-up:** Can book updates be dropped? **Answer:** “Intermediate deltas can only be skipped if the client is forced to resync from a complete snapshot. A latest-state snapshot stream can coalesce safely because it replaces the previous state.”

**40. What is your approach to API versioning?**

**Answer:** “The HTTP routes are under `/api/v1`, and the mobile WebSocket messages carry `v:1`. I’d make compatibility rules explicit, add fields compatibly where possible, and support a migration period before removing a version.”

**Follow-up:** What should happen on an unsupported protocol version? **Answer:** “Reject it with a clear protocol error and close or require an upgrade, rather than silently interpreting fields with the wrong meaning.”

**41. How do you design idempotent order submission?**

**Answer:** “The app currently sends `client_order_id` values, but the new simulator API does not persist or deduplicate them. In a real trading API, I’d use a durable idempotency key scoped to the account, atomically associate it with the accepted command and outcome, and return the original result for a retry.”

**Follow-up:** What race must be handled? **Answer:** “Two concurrent requests with the same key can both pass a pre-check before either inserts. The unique constraint must be the final guard, and the losing transaction should read and return the first result.”

**42. How would you secure authentication and authorization?**

**Answer:** “The mobile simulator intentionally has no login. A real broker app must authenticate users and devices, authorize every account/order action, protect transport with TLS, manage session expiry and revocation, and audit sensitive actions. Market data may also require entitlements, and account information must never be exposed through public simulator routes.”

**Follow-up:** What prevents one user from reading another user’s orders? **Answer:** “Every query must scope by the authenticated user ID. Never accept a user ID from the client as the authority.”

**43. How would you protect the API from abusive traffic?**

**Answer:** “Set request body and query limits, per-user/IP rate limits, connection limits, input schemas, timeouts, and bounded work queues. Expensive operations such as benchmarks or AI analysis need role checks and quotas.”

**Follow-up:** What should rate limiting return? **Answer:** “A consistent 429 response with retry guidance, while logging enough metadata to identify abuse without recording sensitive payloads.”

**44. What database changes would you make for scale and reliability?**

**Answer:** “SQLite is appropriate for a local demo, but I’d move account/order/fill persistence to a managed relational database with migrations, indexes, transactions, backups, and connection pooling. I’d separate durable account records from ephemeral book state and define a journal/replay strategy for engine recovery.”

**Follow-up:** Does a database transaction alone make engine and DB updates atomic? **Answer:** “No. The in-memory engine and database are separate failure domains. I’d use a durable command log/outbox or a carefully designed single-writer transaction protocol so crashes cannot leave accepted orders and persisted records inconsistent.”

**45. How do you scale matching for many symbols?**

**Answer:** “Assign each symbol to one authoritative matching owner and route commands by symbol. Different symbols can process concurrently; one symbol remains ordered. The mobile API demonstrates one bounded queue and worker for ASTR only, not a distributed sharded service.”

**Follow-up:** How do you handle moving a symbol to another shard? **Answer:** “Fence the old owner, persist or snapshot its state and sequence, transfer it, then activate the new owner. Routing must prevent two writers from accepting commands simultaneously.”

**46. How would you handle backpressure between API and matching engine?**

**Answer:** “The mobile API uses a bounded queue of 256 commands per symbol. When full, a single-order request returns retryable 503; batch results identify rejected items. The key rule is to be explicit about whether an order was accepted—never silently drop an order that the client believes was accepted.”

**Follow-up:** What does the client see? **Answer:** “A clear retryable overload result with a correlation ID and no claim that the order was accepted. If acceptance is ambiguous, the client queries by idempotency key.”

**47. What observability would you add?**

**Answer:** “The API creates or propagates an `X-Request-ID` and reports HTTP request counts/latency, queue depth, queue wait, engine duration, accepted/rejected counts, and subscriber count at `/api/v1/metrics`. For a production service I’d add structured logs, distributed traces, WebSocket lag, persistence errors, and alerts on p95/p99.”

**Follow-up:** How do you distinguish a slow API from a slow engine? **Answer:** “Trace timings across ingress validation, queue wait, engine call, persistence, serialization, and network send. The current service reports a local engine submit duration, not full end-to-end latency.”

**48. How would you deploy this service reliably?**

**Answer:** “Package the API and C++ binding reproducibly, expose readiness/health, use TLS, and define graceful shutdown. Before multiple replicas, make symbol ownership explicit and add durable command recovery; otherwise each replica could accept orders against a different book.”

**Follow-up:** Can two replicas share one in-memory engine? **Answer:** “No. They would diverge. They need a single authoritative owner per symbol or a replicated deterministic state machine with a carefully specified consensus and recovery model.”

**49. How do you handle API compatibility between mobile releases and backend releases?**

**Answer:** “The simulator uses `/api/v1` and `v:1` on market snapshots. Use additive schema evolution, tolerate unknown optional fields, and version breaking behavior. A production trading app must keep older installed clients compatible while ensuring order and fill semantics never become ambiguous.”

**Follow-up:** Why is a WebSocket contract especially important? **Answer:** “A long-lived connection can outlast a deployment and clients may reconnect with old protocol assumptions. Include version negotiation and a defined reconnect/upgrade behavior.”

**50. Does `async def` mean FastAPI is multithreaded, and what is the current C++ matching limitation?**

**Answer:** “No. `async def` lets the event loop serve other requests while a coroutine awaits I/O; it does not automatically parallelize CPU work. AstraX has a bounded per-symbol queue and one worker task, but that task calls `MatchingEngine.submit` synchronously. The pybind binding does not release the GIL, so a slow match can block the event loop and other Python threads. I’d profile first, then move matching to a bounded dedicated worker and design a safe native wrapper that releases the GIL around C++ using owned order data. I would keep one writer per book and never create an unbounded thread per request.”

**Follow-up:** Does releasing the GIL make the engine thread-safe? **Answer:** “No. It only lets Python threads run while native code executes. The engine still needs exclusive per-symbol ownership, and the wrapper must avoid Python object access while the GIL is released.”

## 25 questions on the C++ AstraX engine

**51. Explain the engine’s matching rule.**

**Answer:** “AstraX uses price-time priority. Better prices have priority; within the same price level, the intrusive FIFO queue gives earlier resting orders priority. A crossing incoming order consumes the best opposing price first and fills at the maker’s price.”

**Follow-up:** How is the best price selected? **Answer:** “Bids use a descending `std::map`, asks use an ascending `std::map`, so `begin()` is the best level on either side.”

**52. Walk through a limit order submission.**

**Answer:** “`MatchingEngine::submit` dispatches by order type, and a limit order enters `match_limit`. The engine scans the opposite best levels while prices cross, creates fills, updates quantities, removes completed maker nodes, then rests a GTC remainder in the book. The Python binding exposes the engine to orchestration code.”

**Follow-up:** What price does a fill use? **Answer:** “The resting maker order’s price, as stored in the maker node.”

**53. What are the main order-book data structures?**

**Answer:** “Two ordered maps store price levels, each level owns an intrusive doubly linked queue and aggregate quantity/count, an unordered map indexes order IDs to locations for cancellation, and an object pool supplies order nodes.”

**Follow-up:** What are the costs? **Answer:** “Best price is constant-time through the map head; inserting/removing a price level is logarithmic in number of levels; ID lookup is average constant-time; queue unlink is constant-time once the node is located.”

**54. Why use intrusive queues?**

**Answer:** “The links live in `OrderNode`, avoiding a separate list allocation and allowing direct unlink on cancel. It reduces indirection and supports FIFO, but requires careful link and aggregate invariants.”

**Follow-up:** What must be true after unlink? **Answer:** “Neighbor links, head/tail, order count, total quantity, and the ID index must all agree; the node must then be destroyed or returned to the pool exactly once.”

**55. How does cancellation work?**

**Answer:** “The order ID map locates the node and side/price, the book unlinks it from the level, adjusts aggregates, erases the index entry, and returns the node to the pool. The hash index is intended to make lookup average O(1).”

**Follow-up:** What lifecycle gap exists? **Answer:** “The separate stop/pegged order vectors and multi-asset symbol routing need consistent cleanup and indexing; cancellation must cover all live order states, not just resting book nodes.”

**56. Why are prices fixed-point integers?**

**Answer:** “`Price` is a signed 64-bit integer with scale 10,000. Integer comparisons avoid floating-point equality errors in ordered maps and crossing checks. The API converts display prices at the boundary.”

**Follow-up:** What validation remains? **Answer:** “The system must enforce valid tick size, price range, nonnegative values if required, and overflow-safe notional calculations at ingress.”

**57. What are IOC, FOK, and GTC?**

**Answer:** “GTC rests any unfilled limit quantity; IOC executes available quantity and discards the remainder; FOK first checks whether enough crossing liquidity exists and rejects if not. The implementation’s FOK precheck must be safe against concurrent book mutation and aggregate overflow.”

**Follow-up:** Why is single-writer ownership important? **Answer:** “Without it, liquidity could change between the FOK precheck and actual matching, breaking all-or-none behavior.”

**58. How are market orders different from marketable limit orders?**

**Answer:** “A market order consumes opposing liquidity without a price cap and does not rest. A marketable limit order crosses only up to its limit and may rest any eligible remainder when its time-in-force permits. The simulator should consider price protection for market orders.”

**Follow-up:** What safety mechanism would you add? **Answer:** “A collar or worst acceptable price, plus quantity/notional limits and explicit behavior when liquidity is insufficient.”

**59. How does the object pool help?**

**Answer:** “The pool reuses fixed-size `OrderNode` storage instead of asking the general heap for each resting order node. This can reduce allocation overhead and improve predictability, but it is not automatically faster; benchmark it under realistic order/cancel workloads.”

**Follow-up:** What are pool risks? **Answer:** “Alignment and object lifetime must be correct; double-free, exhaustion, exception safety, and thread safety need explicit handling. The current pool is not a general thread-safe allocator.”

**60. What does `alignas(64)` achieve?**

**Answer:** “It requests 64-byte alignment for hot structures, a common cache-line-sized choice. It can help avoid some sharing patterns, but does not prove false sharing is eliminated and can increase memory footprint.”

**Follow-up:** How would you verify benefit? **Answer:** “Benchmark and profile with hardware counters on the target CPU, compare memory footprint and cache misses, and avoid claiming benefit from alignment alone.”

**61. Explain the SPSC ring buffer.**

**Answer:** “It is a single-producer/single-consumer circular buffer using atomic head and tail indices. The producer publishes a slot with release semantics; the consumer observes it with acquire semantics and returns the slot after consuming. One slot is reserved to distinguish full from empty.”

**Follow-up:** What is its usable capacity for `Capacity=1024`? **Answer:** “1023 elements. It must not be used with multiple producers or consumers without redesign.”

**62. What does multi-asset parallel submission do?**

**Answer:** “The engine groups orders by symbol and runs work for independent symbols asynchronously, preserving serial order within each symbol’s batch. This is the useful concurrency boundary because distinct order books can progress independently.”

**Follow-up:** Is the current implementation production thread-safe? **Answer:** “I would not claim that. Shared routing state and concurrent external calls need a clear ownership or synchronization contract, and the local ring-buffer use should be justified by a real producer-consumer need.”

**63. How do stop and pegged orders work?**

**Answer:** “The engine maintains separate vectors for dormant stop and pegged orders and has trigger/repricing helpers. I would explain current semantics from the actual implementation and tests; for example, the checked-in stop trigger path converts triggered stop orders to market behavior, so I would not claim StopLimit semantics are complete.”

**Follow-up:** Why should dormant orders have an index? **Answer:** “So cancel and replace can find them efficiently, IDs remain unique across all states, and trigger/reprice operations do not leave stale entries.”

**64. How do iceberg orders work?**

**Answer:** “An iceberg exposes a visible slice while retaining hidden quantity, and the engine creates a refill when the visible maker slice is consumed. The key semantic question is whether a refill loses time priority; exchange rules usually treat the refreshed slice as newly displayed, and tests should make that behavior explicit.”

**Follow-up:** What invariant matters? **Answer:** “Visible plus hidden plus filled quantities must reconcile to original quantity, with level aggregates counting only displayed liquidity if that is the defined book contract.”

**65. How does the auction uncross work?**

**Answer:** “The engine collects candidate prices, computes executable volume and imbalance for each, chooses a clearing price, then matches eligible orders at that price before returning to continuous trading. Tie-breaking must be documented and tested because choosing the first equal candidate is not a complete exchange rule.”

**Follow-up:** What special order interactions need tests? **Answer:** “Iceberg refresh, stop triggers, pegged repricing, residual quantity, and deterministic tie-breaking during auction uncross.”

**66. What invariants would you check after every command?**

**Answer:** “For each level, aggregate quantity equals the sum of resting visible quantities; order count equals node count; head/tail and previous/next pointers are symmetric; every live order ID maps to exactly one node; each node matches its map side/price; and filled quantity never exceeds total quantity.”

**Follow-up:** How do you enforce them in testing? **Answer:** “Debug assertions plus randomized command sequences compared against a simple reference matcher, checking canonical book state and fill conservation after each operation.”

**67. What is the duplicate-order-ID failure mode?**

**Answer:** “If adding an order overwrites the ID map entry while the old node remains in a queue, later cancellation reaches only the newer node and leaves orphaned liquidity. The correct policy is to reject duplicate live IDs atomically before mutating the book.”

**Follow-up:** How would you test the fix? **Answer:** “Rest the same ID at two levels, attempt a duplicate, verify no depth change, cancel the original, and prove no same-ID order remains or can trade.”

**68. How do you reason about numeric overflow?**

**Answer:** “Order quantities and level aggregates use 32-bit unsigned quantities, so sums can wrap. I’d validate request limits and use wider checked arithmetic for aggregate, auction, and notional calculations; I’d also reject `filled_quantity > quantity` before calling `remaining()`.”

**Follow-up:** Why can unsigned underflow be dangerous? **Answer:** “A malformed order can turn a negative remainder into a very large positive quantity, corrupting matching and book totals.”

**69. How would you make `OrderBook::add` exception-safe?**

**Answer:** “It should either commit the node, level, and ID index together or leave the original book unchanged. I’d use RAII to hold a newly allocated node until insertion succeeds, carefully order potentially throwing map/hash operations, and roll back intermediate changes.”

**Follow-up:** What fault test would help? **Answer:** “Inject allocation failures at each stage and assert all book invariants and pool counts remain unchanged.”

**70. How do you prove correctness beyond unit tests?**

**Answer:** “Combine focused tests for matching semantics with randomized stress/fuzz sequences and a deliberately simple reference model. Fix random seeds, emit failing command traces, compare fills and book state, and include boundary quantities, duplicate IDs, partial fills, cancels, and time-in-force cases.”

**Follow-up:** What do the test filenames prove? **Answer:** “Only that test targets exist. They don’t prove the tests pass or cover every edge case; I’d state the exact build and results I personally ran.”

**71. How would you benchmark the engine?**

**Answer:** “Use separate workloads for inserts, same-level FIFO matching, deep sweeps, cancels, FOK scans, and mixed flows. Fix build flags and machine conditions, warm up, repeat, and report throughput plus latency percentiles. Don’t claim speed from code shape or a single average.”

**Follow-up:** What is the danger of comparing Debug and Release? **Answer:** “The compiler and runtime behavior differ substantially, so the result says little about the production configuration. Compare identical Release builds with recorded compiler and flags.”

**72. How do you keep performance work honest?**

**Answer:** “Profile first, change one hotspot, run correctness checks, then rerun the same workload and save raw results. In AstraX, I’d be especially cautious about describing the pool, alignment, or asynchronous batches as faster before measurements confirm it.”

**Follow-up:** Which latency does the dashboard report? **Answer:** “The Python service measures the call around C++ engine submission. It is not full client-to-server latency and excludes much of the network and broadcast path.”

**73. What concurrency model would you use for a production engine?**

**Answer:** “A single writer per symbol processes sequenced commands from a bounded queue; separate symbols run in parallel. This simplifies book invariants and deterministic replay. Cross-symbol operations need an explicit coordination design.”

**Follow-up:** Would you parallelize matching inside one symbol? **Answer:** “Not casually. Price-time order is inherently sequential for one book; parallelizing it can change outcomes or require a substantially different architecture.”

**74. What durability and recovery guarantees does AstraX have?**

**Answer:** “The matching book is in memory, and the project does not implement a durable event journal or replicated matching state. A process restart does not provide production recovery guarantees. I’d add a sequenced durable command/event log and deterministic replay before claiming crash recovery.”

**Follow-up:** How would you avoid losing a fill after a crash? **Answer:** “Persist the accepted command and result with a defined write-ahead boundary, then publish through an idempotent outbox or replayable event stream.”

**75. What would you improve first in the C++ engine?**

**Answer:** “I’d prioritize correctness and lifecycle: reject duplicate IDs, unify cancel/index handling across resting and dormant orders, validate numeric limits, and make insertion exception-safe. Then I’d expand model-based tests and benchmark representative workloads before optimizing data layout.”

**Follow-up:** How do you present a bug you discovered but did not fix? **Answer:** “I’d say I identified it during review and explain the reproduction and proposed repair. I would not say ‘I fixed it’ or ‘the test passes’ unless I implemented the change and ran the regression.”

## Strong closing response

“AstraX connects a responsive React Native trading interface, real-time market snapshots, a typed FastAPI service, and a C++ matching engine. The mobile UI is intentionally simple: no login, a quote/book/trade view, and batch simulated order entry. The Python API validates requests, uses a bounded queue and one matching owner for the symbol, and reports request, queue, and engine timings. I understand the production gaps too: real brokerage software needs authenticated accounts, durable order and fill state, idempotent retries, cancel/replace, risk checks, entitlements, audit, and recovery. AstraX demonstrates the core concepts in a simulator; it is not a live broker.”

## Source map for interview follow-ups

- Mobile screens and session behavior: `mobile/App.tsx`
- HTTP and WebSocket configuration: `mobile/src/api.ts`
- Reconnect, subscribe, and sequence-gap behavior: `mobile/src/socket.ts`
- FastAPI schemas, per-symbol queue, market snapshots, and metrics: `dashboard/server/mobile_api.py`
- Mobile setup and known limitations: `mobile/README.md`
- HTTP/WebSocket contract: `docs/API.md`
- Server and trading service: `dashboard/server/app.py`, `dashboard/server/trading.py`
- C++ order, price, and quantity types: `engine/src/types.hpp`
- Order book and price levels: `engine/src/order_book.hpp`, `engine/src/order_book.cpp`
- Matching behavior: `engine/src/matching_engine.hpp`, `engine/src/matching_engine.cpp`
- Build overview and project boundaries: `README.md`, `REPORT.md`
