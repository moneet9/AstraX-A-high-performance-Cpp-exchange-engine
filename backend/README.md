# AstraX Mobile Backend

This FastAPI service is the versioned API for the native iOS client. It is a paper-trading simulator and has no broker connectivity. The legacy service under `dashboard/server` remains available for existing simulation and replay workflows.

## Start locally

1. Build the C++ engine and Python bindings.
2. Start PostgreSQL and Redis, then configure the values in `.env.example` in your process environment. Set a unique `ASTRAX_JWT_SECRET` with at least 32 random characters; no secrets belong in the repository.
3. Install the backend dependencies and apply the migration:

```powershell
python -m pip install -e ".[backend]"
alembic -c backend/alembic.ini upgrade head
```

4. Start the API:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8780
```

OpenAPI is served at `/v1/openapi.json`; interactive docs are at `/v1/docs`. The committed contract is [`openapi.yaml`](openapi.yaml). The binary order TCP adapter listens on `127.0.0.1:8771` by default and uses the C++ engine's existing version 1 order/fill frame format. It does not modify matching behavior.

## Contract and numeric rules

All prices, quantities, balances, positions and P&L values are integers. Price fields use the engine's fixed-point tick representation (`price_scale=10000`, configured `tick_size=100`). No API field accepts a floating-point price or quantity. The Swift contract models are in [`../ios/Generated/AstraXAPIModels.swift`](../ios/Generated/AstraXAPIModels.swift).

Access tokens expire after 15 minutes by default. Refresh tokens are one-use and rotate through Redis. Password and Apple sign-in are supported; Apple sign-in requires the service's Apple client ID. Order submission requires a per-request `Idempotency-Key`. Per-user limits, paper accounts, position checks, order/execution persistence, cancel/replace, and account deletion are implemented in this service.

WebSocket clients connect at `/v1/market`, send `{"type":"auth","token":"..."}` first, then subscribe with `{"type":"subscribe","symbol":"ASTR"}`. The service sends an initial snapshot, sequenced full-book refresh frames at 10 Hz, heartbeat messages while idle, and private execution events. A sequence gap can be repaired with `{"type":"resync","symbol":"ASTR"}`. Redis pub/sub distributes updates between service workers.

Run the durable APNs Stream worker separately when its key, team, bundle, and key-file environment values are present: `python -m backend.push_worker`. AI analysis proxies to a local LM Studio OpenAI-compatible endpoint; responses include “Informational only, not financial advice.”

## Current service boundary

The API currently maps the `ASTR` symbol to a single in-process C++ matching engine. PostgreSQL persists accounts and records; the matching book itself is not reconstructed from the database after a process restart. The binary feeder and order API must run in the same service process to share that book. This deployment is suitable for the simulator vertical slice, not production brokerage custody or exchange connectivity.
