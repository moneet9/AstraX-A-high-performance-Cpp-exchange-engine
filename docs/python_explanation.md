# Python Backend Explanation

## 1. Interview summary

> “Python is the application and integration layer around a C++ paper exchange. The new mobile service is FastAPI: it validates versioned requests, authenticates users, checks account ownership and risk limits, translates an order DTO into the engine model, invokes the matching engine, and persists account/order/fill/position state. PostgreSQL is durable state, Redis supports refresh-session revocation, rate limiting, and event distribution. A WebSocket gateway publishes sequenced market snapshots/deltas and private execution events. Python does not replace the engine’s matching logic.”

This describes intended structure and implemented source, not a production deployment guarantee. Backend routes and contract exist, but database/Redis/APNs production operation and full integration behavior need deployment verification. Prices and quantities stay integer-valued across the service boundary.

## 2. Repository roles and Python layers

- `backend/main.py`: FastAPI app, REST routes, engine adaptation, risk checks, WebSocket gateway and market publisher.
- `backend/schemas.py`: Pydantic request/response types and constraints.
- `backend/models.py`: SQLAlchemy 2 persistence models.
- `backend/database.py`: engine/session and configuration.
- `backend/security.py`: password hashes, JWTs, refresh rotation/revocation, dependencies and rate limiting.
- `backend/feed_bridge.py`: asynchronous TCP feed adapter.
- `backend/push_worker.py`: Redis stream consumer and APNs worker entry point.
- `backend/migrations/`: Alembic environment and initial schema migration.
- `backend/openapi.yaml`: versioned API contract intended to drive client models.
- `dashboard/server/`: legacy simulation/dashboard service and AI support; distinct from the new mobile service.
- `bindings/`: Python binding to C++ engine; built artifact/import name is `exchange_simulator`.
- `simulation/`, `agents/`, `rl/`, `data/`: research, simulation, agent, training and replay utilities.

FastAPI supplies routing, dependency injection, request parsing, OpenAPI generation, and WebSocket support. Pydantic handles API validation/serialization. SQLAlchemy 2 expresses persistence. Alembic migrates schema. Redis is used for short-lived/session and event workflows. These libraries do not themselves make all application operations correct; transaction boundaries, engine synchronization, and idempotency need explicit design.

## 3. Request path: order example

1. The client sends `POST /v1/accounts/{account_id}/orders`, a Bearer access token, and `Idempotency-Key`.
2. FastAPI validates JSON as `OrderRequest`; the authenticated-user dependency checks the access JWT.
3. The route verifies the account belongs to that user and checks the idempotency record/key.
4. Tick size, order shape and account risk constraints are checked before calling the engine. Inputs are integer ticks and integer quantities.
5. The service maps API enums/fields into the Python binding’s engine order and serializes access to the shared engine instance.
6. Engine fills are translated into durable order/fill/position updates in a DB transaction. The idempotency result is persisted so a repeated key returns the original outcome.
7. The response includes order lifecycle and fill quantities. Market/private event publication informs connected clients; REST remains the recovery source after reconnect.

For interview discussion, be ready to explain failure boundaries: what happens if the engine accepts an order but DB commit fails, if the DB commits but Redis publish fails, or if a client retries after a timeout? A production design needs a durable outbox/reconciliation path or a carefully defined transactional boundary; do not claim cross-system atomicity from a normal SQL transaction.

## 4. REST endpoint map

| Endpoint | Purpose |
| --- | --- |
| `GET /healthz` | Liveness/health response |
| `POST /v1/auth/register` | Create user and paper account, return session tokens |
| `POST /v1/auth/login` | Email/password login |
| `POST /v1/auth/apple` | Verify/accept Sign in with Apple identity flow and issue app tokens |
| `POST /v1/auth/refresh` | Consume refresh token and rotate token pair |
| `POST /v1/auth/logout` | Revoke refresh session/family |
| `GET /v1/accounts` | Current user’s accounts |
| `GET /v1/symbols` | Supported instruments/tick metadata |
| `GET /v1/market/{symbol}/book` | Authoritative order-book snapshot |
| `POST /v1/accounts/{account_id}/orders` | Submit simulated order (idempotency key) |
| `GET /v1/accounts/{account_id}/orders` | List account orders |
| `POST /v1/accounts/{account_id}/orders/{order_id}/cancel` | Cancel eligible order |
| `POST /v1/accounts/{account_id}/orders/{order_id}/replace` | Replace order under a new order identity |
| `GET /v1/accounts/{account_id}/positions` | Positions and P&L-related state |
| `GET /v1/accounts/{account_id}/executions` | Fills/executions |
| `GET /v1/candles/{symbol}` | Historical/aggregated candle data |
| `POST /v1/push-tokens` | Register APNs token for current user |
| `POST /v1/ai/strategy-plan` | Informational AI strategy-plan proxy |
| `POST /v1/ai/market-report` | Informational AI market-report proxy |
| `POST /v1/ai/regime-similarity` | Informational regime-similarity proxy |
| `DELETE /v1/account` | Delete user/account data after explicit confirmation |

The WebSocket endpoint is `/v1/market`. Consult `backend/openapi.yaml` and route definitions for the exact current payload fields; API docs must be regenerated whenever code changes.

## 5. Authentication and security model

Passwords are hashed, not stored as plaintext. Access tokens are short-lived JWTs; refresh tokens rotate. A refresh token is consumed once, and reuse/revocation can invalidate its family. API dependencies decode and validate the Bearer token to obtain a user identity. Route-level account ownership checks prevent one user from accessing another account. Per-user limits are bucketed in Redis. Do not log passwords, Apple identity tokens, bearer tokens, or raw refresh tokens.

Security review questions:

- Is the Apple identity token signature, issuer, audience, expiry, and nonce validated using Apple’s current keys? An identity token must be verified server-side; decoding it is not verification.
- Are refresh tokens stored as digests in Redis, bounded by TTL, and revoked on password/account deletion?
- Is rate limiting shared across workers and resistant to key evasion?
- Are CORS, TLS termination, trusted proxy headers, secret management, and request size limits set for deployment?
- Does account deletion remove personal data, tokens, push registrations, and dependent records according to retention policy?

The source has security mechanisms, but the answers above must be checked against actual deployed configuration before calling the service production secure.

## 6. Data model and transaction handling

SQLAlchemy models cover users, accounts, orders, fills, positions, push tokens, and idempotency/session-related records where configured. Alembic migration `0001_initial.py` establishes the initial relational schema. PostgreSQL is the intended durable store. Integer prices are stored as engine ticks; conversion to decimal strings/display values belongs at presentation boundaries.

Explain ACID transaction boundaries around fill accounting: one fill changes an order’s filled quantity/status, creates a fill row, and updates the matching position/cash ledger. Those related writes should commit together. Concurrent submissions need database constraints/locking in addition to a Python lock. A shared in-process matching engine is not automatically horizontally scalable: separate API workers would otherwise each own a different book. A production deployment would isolate the matching engine behind one authoritative process/service or use a partitioned ownership model and durable event log.

## 7. WebSocket and binary feed integration

The Python gateway authenticates the socket, handles subscribe messages, and emits initial book snapshot followed by deltas with per-symbol sequence numbers. Heartbeat and sequence numbers let the client detect a broken stream. On a gap, client requests REST snapshot and resumes from its sequence. Private execution frames are scoped to the authenticated user/account; never broadcast another user’s order details.

The project has a binary TCP protocol/feed bridge for engine-side data and a JSON gateway for the mobile app. The feed adapter reads framed bytes asynchronously, validates/decodes the protocol, and dispatches engine changes. WebSocket fan-out should avoid doing blocking engine/database work in the event loop. Any synchronous binding calls are serialized and, if they become slow, moved to a dedicated worker thread/process or service boundary.

At-least-once/reconnect behavior means consumers should tolerate duplicate events. Sequence checking and unique execution identifiers are the basis for dedupe. Redis pub/sub can lose messages while consumers are disconnected; a durable stream/outbox or REST reconciliation is needed where guaranteed delivery matters.

## 8. AI, APNs, and operational pieces

The AI endpoints proxy prompts to a local LM Studio-compatible endpoint so the iOS app does not access localhost-only model services. Responses are informational and must include a “not financial advice” disclosure. Do not feed secrets or unnecessary personally identifying information to the model. Add timeouts, output limits, schema validation, and clear unavailable behavior when the local model is down.

APNs work is separated into a worker that consumes a Redis stream and sends fill/alert notifications. The HTTP order path should not wait for APNs. A production worker needs credential configuration outside the repository, retry/backoff, dead-letter handling, token invalidation, and observability. `.env.example` documents configuration names but must contain no usable credentials.

## 9. Tests and interview caveats

The repository contains Python API/trading tests, but this workspace runs Python 3.10 while project metadata requires Python 3.11+, and Redis/Postgres integrations are not provisioned here. Do not claim those integration tests passed unless run in the supported environment. Explain test layers: pure schema/unit tests; mocked engine and Redis route tests; PostgreSQL migration/transaction tests; WebSocket auth/sequence/reconnect tests; end-to-end order-to-fill test.

Likely grilling questions:

**Why FastAPI?** Typed request/response validation, async/WebSocket support, dependency injection, and generated OpenAPI fit a mobile service. The engine call remains a separate integration boundary.

**Why PostgreSQL and Redis?** PostgreSQL is durable transactional account/order state; Redis is suited to expiring session/rate-limit state and fast event distribution. Redis pub/sub alone is not durable delivery.

**How do you prevent a duplicate order?** Scope an idempotency key to user/account/route, store its request fingerprint and completed response, and reject reuse with a different body. Commit the idempotency result with durable order state.

**What is the biggest scaling concern?** A single in-memory matching engine cannot be duplicated behind multiple API workers without splitting authoritative books. Route engine commands to one owner per instrument and publish durable sequence-numbered events.

**How would you debug delayed fills?** Correlate request ID/order ID through API validation, engine submission, fill persistence, event publication, WebSocket receipt, and UI update; emit structured logs/metrics with durations and no secrets.

## 10. Useful files

- `backend/main.py`, `schemas.py`, `models.py`, `database.py`, `security.py`
- `backend/feed_bridge.py`, `push_worker.py`, `migrations/versions/0001_initial.py`
- `backend/openapi.yaml`, `.env.example`, `README.md`
- `bindings/`, `simulation/`, `data/`, `dashboard/server/`
