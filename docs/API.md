# Version 1 API (Phase 2)

## Native iOS backend contract

The production-oriented simulator API is implemented in [`backend/main.py`](../backend/main.py). Start it using [`backend/README.md`](../backend/README.md). Its OpenAPI 3.1 contract is committed at [`backend/openapi.yaml`](../backend/openapi.yaml), generated at runtime at `/v1/openapi.json`, and the current Swift data types are in `ios/Generated/AstraXAPIModels.swift`. It uses PostgreSQL/SQLAlchemy for records and Redis for refresh-token rotation, rate limits, and market/private-event pub/sub. All submitted and returned prices and quantities remain integers. The initial market adapter is one local C++ engine for `ASTR`; this is a simulated trading service.

The legacy endpoints documented below remain separate compatibility surfaces. They are not used by the new client contract.

## Mobile simulator API (FastAPI)

The standalone simulator API is `dashboard.server.mobile_api:app` on port 8770. It is an unauthenticated local simulator API and is separate from the legacy simulation service below. Start with `python -m uvicorn dashboard.server.mobile_api:app --host 127.0.0.1 --port 8770` after installing `pip install -e ".[api]"`.

- `GET /api/v1/health` returns service health and API version.
- `GET /api/v1/symbols` returns configured simulator symbols and price scale.
- `GET /api/v1/book/{symbol}` returns a sequenced complete top-ten snapshot.
- `GET /api/v1/trades/{symbol}?limit=50` returns retained simulator fills.
- `POST /api/v1/orders` accepts one validated simulated order.
- `POST /api/v1/orders/batch` accepts 1 to 50 validated orders and processes them in request order.
- `GET /api/v1/metrics` reports HTTP request counts/latency, engine and queue latency, queue depth, rejects, and connected market subscribers.
- `WS /ws/v1/market` emits an initial snapshot and then sequenced complete snapshots, plus heartbeats.

Each symbol has one bounded (256 command) queue and a single matching worker. Queue saturation returns a retryable 503 for single-order submission; batch responses identify individual rejects. WebSocket subscribers each have a one-message queue. When a client is slow, the publisher replaces an older queued snapshot with the newest full snapshot; clients do not need to replay missed intermediate book changes. This is appropriate for this simulator's state display, not a broker execution or durable order-delivery guarantee. The API currently configures only `ASTR` and seeds a small two-sided demo book at startup. It has no login, account persistence, broker connection, or real-market data.

Every HTTP response includes `x-api-version`, `x-request-id`, and `server-timing` headers. Supply an `X-Request-ID` to correlate a client request with server logs; if omitted, the API creates one.

The local Python server listens for the existing dashboard WebSocket on port 8765, the replay TCP feeder on 8766, and JSON HTTP API on 8767. HTTP routes are under `/api/v1`. The current market contains one configured simulated symbol, `ASTR`; this is not a real market feed.

## Market HTTP endpoints

- `GET /api/v1/health` returns `{ "ok": true, "version": 1 }`.
- `GET /api/v1/symbols` returns symbol metadata, including engine price scale and tick size.
- `GET /api/v1/book/ASTR?levels=10` returns up to ten levels: `{ "v":1, "symbol":"ASTR", "bids":[[price,quantity]], "asks":[[price,quantity]] }`.
- `GET /api/v1/trades/ASTR?limit=100` returns recent simulator fills.
- `GET /api/v1/candles?symbol=ASTR&interval=60&limit=100` aggregates currently retained fills. Candle times are simulator-derived, and history is limited to retained fills; it is not durable historical market data.

Prices in book/trade/candle payloads are engine fixed-point integers: divide by 10,000 for display. Quantity is an integer unit count. HTTP public market routes currently do not require login.

## Mobile WebSocket

Connect to `ws://localhost:8765/ws` and send the token in the first message (not the URL):

```json
{"v":1,"type":"auth","token":"<opaque-token>"}
```

Successful authentication returns `{"v":1,"type":"auth","ok":true,"role":"trader"}`. Subscribe with `{"v":1,"type":"subscribe","symbol":"ASTR"}`. A subscription first receives a snapshot:

```json
{"v":1,"type":"book","kind":"snapshot","symbol":"ASTR","seq":1,"bids":[[1000000,5]],"asks":[[1000100,7]]}
```

The server refreshes the top-ten book at most about ten times per second and increments `seq`; clients should detect sequence gaps and send `{"v":1,"type":"resync","symbol":"ASTR"}`. Unsubscribe with `{"v":1,"type":"unsubscribe","symbol":"ASTR"}`. Heartbeats are `{ "v":1,"type":"heartbeat","time":... }`.

Phase 2 sends a complete top-ten book refresh on each sequenced update (currently `kind:"delta"`); it does not yet encode changed levels only. Private order/fill/alert events and per-user order acknowledgements are not implemented yet. Existing dashboard WebSocket messages remain unversioned and unchanged.

## Admin and order management (Phase 3)

Authenticated users can use `GET /api/v1/orders?status=NEW` and `DELETE /api/v1/orders/{id}` for their own orders. Admin-only routes are `GET /api/v1/admin/stats`, `POST /api/v1/admin/simulator/start`, `POST /api/v1/admin/simulator/stop`, `POST /api/v1/admin/benchmarks/run`, `GET /api/v1/admin/benchmarks`, and `GET /api/v1/admin/benchmarks/{id}`. Benchmark launch returns a run ID immediately; clients poll the detail route for `RUNNING`, `COMPLETED`, or `FAILED`. Benchmark results collected while server load is present are not clean measurements. Compiler and git revision metadata are explicitly marked unavailable until captured by the build configuration.

The simulator currently supports only start/stop controls; runtime volatility/regime changes and user reset are not available.
