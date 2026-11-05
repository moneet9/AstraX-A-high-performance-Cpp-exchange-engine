"""Focused contract checks for the versioned native-client API."""
import pytest

pytest.importorskip("exchange_simulator")
pytest.importorskip("sqlalchemy")
pytest.importorskip("redis")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("pydantic")

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import app
from backend.schemas import OrderRequest


client = TestClient(app)


def test_health_has_service_version_headers():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "astrax-api", "api_version": 1}
    assert response.headers["x-api-version"] == "1"
    assert response.headers["x-request-id"]


def test_symbols_use_integer_price_metadata():
    response = client.get("/v1/symbols")
    assert response.status_code == 200
    symbol = response.json()["symbols"][0]
    assert symbol["price_scale"] == 10_000
    assert symbol["tick_size"] == 100
    assert isinstance(symbol["price_scale"], int)


def test_book_route_returns_snapshot_with_integer_levels():
    response = client.get("/v1/market/ASTR/book")
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "snapshot"
    assert body["symbol"] == "ASTR"
    assert all(isinstance(value, int) for level in body["bids"] + body["asks"] for value in level)


def test_order_contract_rejects_float_prices_and_invalid_iceberg_slices():
    with pytest.raises(ValidationError):
        OrderRequest.model_validate({"symbol": "ASTR", "side": "buy", "type": "limit",
                                     "quantity": 2, "price_ticks": 1000.0})
    with pytest.raises(ValidationError):
        OrderRequest.model_validate({"symbol": "ASTR", "side": "buy", "type": "iceberg",
                                     "quantity": 10, "price_ticks": 1000, "visible_quantity": 10})


def test_openapi_is_versioned_and_includes_order_lifecycle():
    schema = client.get("/v1/openapi.json").json()
    assert "/v1/accounts/{account_id}/orders" in schema["paths"]
    assert "/v1/accounts/{account_id}/orders/{order_id}/cancel" in schema["paths"]
    assert "/v1/accounts/{account_id}/orders/{order_id}/replace" in schema["paths"]
