# AstraX Phase 0 Audit

Audit date: 2026-10-29. This is a historical audit of the repository before the mobile and frontend cleanup; its statements about checked-in UI files and startup commands are no longer current. The browser frontend and Expo client have since been removed. The intended client is native SwiftUI.

## What the folders do

- `engine/`: C++20 order types, order book, matching engine, multi-asset wrapper, binary protocol, tests, and Google Benchmark programs.
- `bindings/`: pybind11 module exposing engine types and operations as `exchange_simulator`.
- `agents/`: Python random and market-making agents.
- `data/`: LOBSTER and Databento CSV replay, synthetic scenario/Hawkes generation, backtesting, and TCP feeder.
- `simulation/`: Python loop that drives agents through the matching engine.
- `dashboard/server/`: Python asyncio server, live simulation, TCP ingestion, and optional LM Studio analysis.
- `tests/`: Python tests for agents, replay, multi-asset, data, RL, and AI helpers.
- `rl/`: Gymnasium trading environments and training/evaluation/self-play utilities.
- `docs/`: project documentation (this audit is the first file).

## Server and current stream

At the time of this historical audit, `dashboard/server/app.py` used Python `asyncio` and the third-party `websockets` package. The separate `dashboard/server/mobile_api.py` FastAPI simulator service was added later and remains. Refer to [API.md](API.md) and the current service README for active routes and startup instructions.

The current WebSocket protocol is unversioned JSON. On connection it sends `{ "type":"init", "agents":[...], "llm":{"chat_model":"...","embed_model":"..."} }`. The server then broadcasts a `tick` approximately every 10 ms with `step`, `book` (`best_bid`, `best_ask`, `mid`, `spread`, `bid_depth`, `ask_depth`), `fills` (each has `price`, `quantity`, `side`, `timestamp`), and `agents` (`name`, `pnl`, `inventory`, `fills`). Every 100 steps it may add `latency` with nanosecond p50/p90/p95/p99/mean/min/max/count. Clients can send JSON commands `reset`, `analysis` (optional `analysis_type`), or `regime_similarity` (optional `limit`). There are no REST endpoints, authentication, per-symbol subscriptions, delta messages, or private user channel currently.

The TCP listener accepts fixed-size binary order frames and returns binary fill frames. `data/tcp_feeder.py` is the corresponding sender.

## Price and quantity representation

`engine/src/types.hpp` defines `Price` as signed 64-bit fixed point equal to displayed price times 10,000 (four decimal places), and `Quantity` as unsigned 32-bit units. For a displayed price of 123.4567, engine price is 1,234,567. Quantity is an abstract whole unit/share count; there is no instrument-specific contract multiplier. Proposed API mapping: transmit integer `price_ticks`/`price` unchanged and have each symbol metadata record define `price_scale=10000` and `quantity_unit`; render `price / 10000` with the selected currency precision. Tick-size validation needs per-symbol configuration not present today.

## Binding coverage and gaps

`bindings/py_exchange.cpp` exposes `MatchingEngine.submit`, `cancel`, `book`, best bid/ask, aggregate bid/ask depth, plus order/fill fields and binary encode/decode. Fills are returned directly from `submit` as a vector, so there is no asynchronous callback or polling API. It exposes no modify/replace operation. The order book exposes best prices and depth counts, but not a top-N price-level snapshot. Submit timing can be measured in Python around the binding call; this includes Python-to-C++ binding overhead and engine execution, not just internal matching time. No C++ internal-duration result is currently returned.

`MultiAssetEngine` exposes symbol-specific book lookup, submit, parallel batch submit, cancel, and symbol list. Symbols are represented by integer IDs, with a distinct book per symbol. `submit_parallel` dispatches independent symbol orders using the implementation in `engine/src/multi_asset_engine.cpp`; this is not parallel matching inside one symbol book.

## Existing startup commands

Commands documented by the repo (not verified here):

- Configure/build: `cmake -B build -DCMAKE_BUILD_TYPE=Release` then `cmake --build build`.
- Python server: `PYTHONPATH=build/bindings:. python3 dashboard/server/app.py` (PowerShell equivalent uses `$env:PYTHONPATH='build/bindings;.'`).
- Replay feeder: `PYTHONPATH=build/bindings:. python3 -m data.tcp_feeder --source path/to/lobster.csv`.
- Agent simulation: invoke `simulation.loop.SimulationLoop` from Python; no standalone command-line entry point is provided.

## Benchmarks

`engine/bench/CMakeLists.txt` defines `bench_order_book` and `bench_matching`. From a configured build, run `build/engine/bench/bench_order_book.exe --benchmark_format=json` and `build/engine/bench/bench_matching.exe --benchmark_format=json` on Windows (omit `.exe` on Unix). Existing scripts write JSON output, though `profile.ps1` runs both binaries and `profile.sh` is primarily a perf/Valgrind wrapper. No benchmark numbers are claimed in this audit.

## Documentation claims checked

- README says “Multi-asset parallel submission for independent symbols”; the code has `submit_parallel`, but its implementation should be described narrowly as batch dispatch across separate symbol books, not single-symbol parallel matching.
- README describes LOBSTER/Databento replay and a binary TCP feeder; corresponding modules exist. The binary protocol serializes fields manually in `engine/src/binary_protocol.hpp`; it is not evidence of a `#pragma pack(1)` wire struct.
- Hawkes synthetic generation exists in `data/hawkes.py`; this is a generator, not proof of a Hawkes process inside the matching engine.
- REPORT contains interview-script-style paragraphs and claims (for example benchmark-driven performance comparisons) that are not backed by measurements in the repository. Treat them as narrative, not verified measurements.
- The README's stated Python requirement is 3.11+, while this environment has Python 3.10.11.

## Build and test results

Not run successfully in this environment. `cmake` is not available on PATH, and the available Python is 3.10.11, below the `pyproject.toml` requirement of 3.11+. Consequently C++ configure/build, `ctest`, and `pytest` results are unavailable; no passing status is claimed. Retry on Windows after installing CMake and Python 3.11+ with project dependencies.

## Risks and open questions

- Per-symbol tick sizes, currency/display conventions, price bands, position limits, and starting balance need configurable policy.
- Existing engine order IDs are not user-scoped; cancellation authorization must be enforced in the service.
- In-memory live state and a single shared simulation instance are not suitable account isolation or durable portfolio behavior; persistence and transaction design are required.
- The server currently binds only to localhost, so a phone on the LAN cannot reach it. Mobile development needs LAN binding and secure deployment guidance.
- Local LM Studio analysis runs in server request handling; it must remain outside order execution and may block event-loop work.
- There is no authentication, user/account model, REST API, alert system, candles endpoint, benchmark API, or admin control plane yet.
- The mobile Expo/TypeScript implementation and Expo Go constraints should be checked against current Expo docs before Phase 1.
- The requested branch `feature/mobile-trading-app` could not be created because Git could not create its nested ref directory; branch state must be resolved before implementation.

## Phase 1 implementation note (2026-10-29)

Added `dashboard/server/trading.py` with SQLite users/tokens/orders/fills/positions, scrypt password hashes, opaque bearer tokens, demo user seeding, idempotency-key handling, basic order risk checks, fill-based cash/position accounting, and submit timings. `dashboard/server/app.py` now adds a separate minimal JSON HTTP listener on port 8767 under `/api/v1` for health, login, current user, portfolio, and mock order submission; the existing WebSocket and TCP listeners are retained. Initial endpoints are intentionally a foundation, not the full requested API. This code has not yet been tested or exercised end to end because the environment lacks the configured build tools and Python version.

Configuration: `ASTRAX_DB_PATH`, `ASTRAX_STARTING_CASH`, `ASTRAX_TRADER1_PASSWORD`, `ASTRAX_TRADER2_PASSWORD`, `ASTRAX_ADMIN_PASSWORD`, `ASTRAX_MAX_POSITION`, and `ASTRAX_PRICE_BAND_BPS`. When a demo password is not supplied, a random one is printed once during first-time account creation. `engine_submit_us` currently measures the Python-to-binding call plus engine execution; it is not a C++-internal-only duration.

Phase 3 added user-scoped order list/cancel routes, role-checked benchmark run/history/detail and simulator start/stop routes, live admin counters, and focused account/risk tests. The benchmark API launches the existing binaries only; no binaries were available to run here. See `docs/API.md` for routes and limitations.

Phase 4 adds an Expo SDK 57 TypeScript app in `mobile/`. Its source provides login/session storage, biometric unlock, idle lock, market/book/trade views, mock order form, portfolio view, admin actions, a reconnecting versioned WebSocket client, and local order notifications. It has pure tests for price/P&L formatting and sequence-gap detection. Alerts, charting, admin benchmark history visualization, full open-order cancel/history UI, and live private fill events remain unavailable because their backend contracts are incomplete. Expo dependency installation did not complete in the current environment, so TypeScript/Jest and Expo Go runtime checks were not run.
