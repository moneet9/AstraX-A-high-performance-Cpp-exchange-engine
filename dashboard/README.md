# AstraX Python Services

The Python services connect the C++ matching engine to simulation agents, replay tools, market APIs, and optional local AI analysis. The browser dashboard has been removed; this directory now contains backend code only.

The native iOS API is being developed in the separate [`backend/`](../backend/README.md) service. The older `mobile_api.py` endpoint remains an unauthenticated local simulator API for compatibility and is not the production-oriented mobile contract.

## Legacy simulation service

Build the engine and bindings first, then start the service:

```bash
PYTHONPATH=build/bindings:. python3 dashboard/server/app.py
```

It listens on localhost for the simulation WebSocket (8765), binary TCP feeder (8766), and JSON HTTP API (8767). Route and payload details are in [../docs/API.md](../docs/API.md).

## Standalone simulator API

The simulator API is available as `dashboard.server.mobile_api:app`:

```bash
pip install -e ".[api]"
python -m uvicorn dashboard.server.mobile_api:app --host 127.0.0.1 --port 8770
```

This API currently supports unauthenticated simulated market data and order submission. It is a local simulator service, not a broker API. See [../docs/API.md](../docs/API.md) for details.

## Optional AI analysis

Set `LM_STUDIO_BASE_URL`, `LM_STUDIO_MODEL`, and `LM_STUDIO_EMBED_MODEL` to use a local LM Studio server. The matching engine and simulation can run without it.
