"""Focused tests for the account/risk foundation (engine binding is stubbed)."""
import sys
import types

from dashboard.server.trading import TradingService


class Book:
    def best_bid_price(self): return 1_000_000
    def best_ask_price(self): return 1_001_000


class Engine:
    def __init__(self): self.orders=[]
    def book(self): return Book()
    def submit(self, order):
        self.orders.append(order)
        class Fill:
            price=1_000_000; quantity=2
        order.filled_quantity=2
        return [Fill()]


def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRAX_TRADER1_PASSWORD", "trader-pass")
    monkeypatch.setenv("ASTRAX_TRADER2_PASSWORD", "trader-pass-2")
    monkeypatch.setenv("ASTRAX_ADMIN_PASSWORD", "admin-pass")
    engine=Engine()
    svc=TradingService(engine, str(tmp_path/"test.sqlite3"))
    return svc,engine


def install_binding(monkeypatch):
    class Order:
        def is_filled(self): return self.filled_quantity >= self.quantity
    module=types.SimpleNamespace(Order=Order, Side=types.SimpleNamespace(Buy=1,Sell=2),
        OrderType=types.SimpleNamespace(Limit=1,Market=2), TimeInForce=types.SimpleNamespace(GTC=1))
    monkeypatch.setitem(sys.modules,"exchange_simulator",module)


def test_auth_and_risk_rejection(tmp_path, monkeypatch):
    svc,engine=service(tmp_path,monkeypatch)
    token=svc.login("trader1","trader-pass")
    assert svc.user_for_token(token)["role"] == "trader"
    assert svc.login("trader1","wrong") is None
    user=svc.user_for_token(token)
    result,_=svc.submit(user,{"symbol":"NOPE","side":"buy","type":"limit","price":1_000_000,"quantity":1})
    assert result["status"] == "REJECTED"
    assert result["reason_code"] == "UNKNOWN_SYMBOL"
    assert engine.orders == []


def test_fill_updates_cash_position_and_pnl(tmp_path, monkeypatch):
    install_binding(monkeypatch)
    svc,engine=service(tmp_path,monkeypatch)
    user=svc.user_for_token(svc.login("trader1","trader-pass"))
    result,timings=svc.submit(user,{"symbol":"ASTR","side":"buy","type":"limit","price":1_000_000,"quantity":2,"idempotency_key":"one"})
    assert result["status"] == "FILLED"
    portfolio=svc.portfolio(user["id"])
    assert portfolio["positions"][0]["quantity"] == 2
    assert portfolio["cash"] == 999800
    assert timings["engine_submit_us"] >= 0
    again,_=svc.submit(user,{"symbol":"ASTR","side":"buy","type":"limit","price":1_000_000,"quantity":2,"idempotency_key":"one"})
    assert again["id"] == result["id"]
