from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

import httpx
import jwt
from redis import asyncio as aioredis
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build" / "bindings"))
sys.path.insert(0, str(ROOT))
import exchange_simulator as ex  # noqa: E402
from backend.database import engine, session_scope
from backend.feed_bridge import serve_tcp_feed
from backend.models import Account, Base, Execution, Order, Position, PushToken, User
from backend.schemas import AppleToken, Credentials, DeleteAccountRequest, OrderRequest, RefreshRequest
from backend.security import (JWT_ISSUER, JWT_SECRET, consume_refresh, current_user,
                              password_hash, rate_limit, redis_client, revoke_refresh, token_pair,
                              revoke_user_sessions, verify_password)

API_VERSION = 1
PRICE_SCALE = 10_000
TICK_SIZE = 100
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "")
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
app = FastAPI(title="AstraX Paper Trading API", version="1.0.0",
              description="Simulated trading API. No broker connectivity.",
              openapi_url="/v1/openapi.json", docs_url="/v1/docs", redoc_url=None)
core = ex.MatchingEngine()
engine_lock = threading.RLock()
symbol_ids = {"ASTR": 1}
sequence = defaultdict(int)
async_redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)


def _seed_paper_book():
    """Seed visibly simulated liquidity so a fresh client can chart and fill demo orders."""
    for index, (side, price) in enumerate(((ex.Side.Buy, 999_900), (ex.Side.Sell, 1_000_100)), start=1):
        order = ex.Order()
        order.id = time.time_ns() + index
        order.side = side
        order.price = price
        order.stop_price = 0
        order.peg_offset = 0
        order.quantity = 100
        order.filled_quantity = 0
        order.visible_quantity = 0
        order.hidden_quantity = 0
        order.type = ex.OrderType.Limit
        order.tif = ex.TimeInForce.GTC
        order.timestamp = time.time_ns()
        core.submit(order)


_seed_paper_book()


def _account(session: Session, user_id: int, account_id: int) -> Account:
    account = session.scalar(select(Account).where(Account.id == account_id, Account.user_id == user_id))
    if account is None:
        raise HTTPException(404, "account not found")
    return account


def _order_dict(row: Order) -> dict:
    return {"id": row.id, "symbol": row.symbol, "side": row.side, "type": row.order_type,
            "tif": row.tif, "price_ticks": row.price_ticks, "stop_price_ticks": row.stop_price_ticks,
            "peg_offset_ticks": row.peg_offset_ticks, "quantity": row.quantity,
            "filled_quantity": row.filled_quantity, "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None}


def _engine_order(request: OrderRequest):
    order = ex.Order()
    order.id = time.time_ns() & 0x7FFFFFFFFFFFFFFF
    order.side = ex.Side.Buy if request.side == "buy" else ex.Side.Sell
    order.price = request.price_ticks
    order.stop_price = request.stop_price_ticks
    order.peg_offset = request.peg_offset_ticks
    order.quantity = request.quantity
    order.filled_quantity = 0
    order.visible_quantity = request.visible_quantity if request.type == "iceberg" else 0
    order.hidden_quantity = request.quantity - request.visible_quantity if request.type == "iceberg" else 0
    order.type = {"market": ex.OrderType.Market, "limit": ex.OrderType.Limit,
                  "iceberg": ex.OrderType.Limit, "stop": ex.OrderType.Stop,
                  "stop_limit": ex.OrderType.StopLimit, "pegged": ex.OrderType.Pegged}[request.type]
    order.tif = {"GTC": ex.TimeInForce.GTC, "IOC": ex.TimeInForce.IOC, "FOK": ex.TimeInForce.FOK}[request.tif]
    order.timestamp = time.time_ns()
    return order


def _apply_position_fill(session: Session, account: Account, row: Order, qty: int, price: int):
    position = session.scalar(select(Position).where(Position.account_id == account.id, Position.symbol == row.symbol))
    if position is None:
        position = Position(account_id=account.id, symbol=row.symbol, quantity=0,
                            average_price_ticks=0, realized_pnl_ticks=0)
        session.add(position)
        session.flush()
    signed = qty if row.side == "buy" else -qty
    old_q = position.quantity
    if old_q == 0 or old_q * signed > 0:
        position.average_price_ticks = (abs(old_q) * position.average_price_ticks + qty * price) // (abs(old_q) + qty)
    else:
        closed = min(abs(old_q), qty)
        position.realized_pnl_ticks += closed * (price - position.average_price_ticks) * (1 if old_q > 0 else -1)
        if qty > abs(old_q):
            position.average_price_ticks = price
    position.quantity += signed
    # All account and execution values remain integers in engine price units.
    account.cash_ticks += (-price * qty if row.side == "buy" else price * qty)


def _apply_fills(session: Session, fills, submitted_engine_id: int):
    user_events = defaultdict(list)
    for fill in fills:
        qty, price = int(fill.quantity), int(fill.price)
        engine_ids = {int(fill.maker_order_id), int(fill.taker_order_id)}
        matched = session.scalars(select(Order).where(Order.engine_order_id.in_(engine_ids))).all()
        for row in matched:
            if row.engine_order_id != submitted_engine_id and row.filled_quantity < row.quantity:
                row.filled_quantity = min(row.quantity, row.filled_quantity + qty)
            row.status = "filled" if row.filled_quantity >= row.quantity else "partially_filled"
            account = session.get(Account, row.account_id)
            if account is None:
                continue
            execution = Execution(order_id=row.id, price_ticks=price, quantity=qty, side=row.side)
            session.add(execution)
            session.flush()
            _apply_position_fill(session, account, row, qty, price)
            user_events[row.account_id].append({"execution_id": execution.id, "order_id": row.id,
                                                "symbol": row.symbol, "side": row.side,
                                                "price_ticks": price, "quantity": qty,
                                                "filled_quantity": row.filled_quantity})
    return user_events


def _check_price(request: OrderRequest):
    if request.symbol.upper() not in symbol_ids:
        raise HTTPException(404, "unknown symbol")
    if request.type in {"limit", "iceberg", "stop_limit"} and request.price_ticks % TICK_SIZE:
        raise HTTPException(422, "price_ticks must align to configured tick_size")
    if request.stop_price_ticks and request.stop_price_ticks % TICK_SIZE:
        raise HTTPException(422, "stop_price_ticks must align to configured tick_size")


def _risk_check(session: Session, account: Account, request: OrderRequest):
    symbol = request.symbol.upper()
    position = session.scalar(select(Position).where(Position.account_id == account.id, Position.symbol == symbol))
    current = position.quantity if position else 0
    open_orders = session.scalars(select(Order).where(Order.account_id == account.id, Order.symbol == symbol,
        Order.status.in_(("open", "partially_filled")))).all()
    projected = current + sum((o.quantity - o.filled_quantity) * (1 if o.side == "buy" else -1) for o in open_orders)
    projected += request.quantity * (1 if request.side == "buy" else -1)
    max_position = int(os.getenv("ASTRAX_MAX_POSITION", "1000"))
    if abs(projected) > max_position:
        raise HTTPException(422, "maximum position limit exceeded")
    policy_price = request.price_ticks or request.stop_price_ticks
    if policy_price:
        with engine_lock:
            book = core.book()
            bid, ask = book.best_bid_price(), book.best_ask_price()
        reference = (bid + ask) // 2 if bid and ask else bid or ask
        band_bps = int(os.getenv("ASTRAX_PRICE_BAND_BPS", "2000"))
        if reference and abs(policy_price - reference) * 10_000 > reference * band_bps:
            raise HTTPException(422, "price outside configured market band")
    if request.side == "buy":
        reference = request.price_ticks or request.stop_price_ticks
        if not reference:
            with engine_lock:
                book = core.book()
                reference = book.best_ask_price() or book.best_bid_price() or 0
        pending = sum((o.quantity - o.filled_quantity) * o.price_ticks for o in open_orders if o.side == "buy")
        if reference and pending + reference * request.quantity > account.cash_ticks:
            raise HTTPException(422, "insufficient simulated buying power")


@app.middleware("http")
async def api_headers(request, call_next):
    response = await call_next(request)
    response.headers["x-api-version"] = str(API_VERSION)
    response.headers["x-request-id"] = request.headers.get("x-request-id") or os.urandom(12).hex()
    return response


@app.get("/healthz")
def health():
    return {"ok": True, "service": "astrax-api", "api_version": API_VERSION}


@app.post("/v1/auth/register", status_code=201)
def register(data: Credentials):
    with session_scope() as session:
        email = data.email.strip().lower()
        if session.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(409, "email already registered")
        user = User(email=email, password_hash=password_hash(data.password))
        session.add(user)
        session.flush()
        account = Account(user_id=user.id)
        session.add(account)
        session.flush()
        user_id = user.id
        result = {"user_id": user_id, "account_id": account.id, **token_pair(user_id)}
    return result


@app.post("/v1/auth/login")
def login(data: Credentials):
    with session_scope() as session:
        user = session.scalar(select(User).where(User.email == data.email.strip().lower(), User.is_active.is_(True)))
        if user is None or user.password_hash is None or not verify_password(data.password, user.password_hash):
            raise HTTPException(401, "invalid credentials")
        user_id = user.id
        account = session.scalar(select(Account).where(Account.user_id == user_id))
        account_id = account.id if account else None
    return {"user_id": user_id, "account_id": account_id, **token_pair(user_id)}


@app.post("/v1/auth/apple")
def apple_login(data: AppleToken):
    if not APPLE_CLIENT_ID:
        raise HTTPException(503, "Sign in with Apple is not configured")
    try:
        signing_key = jwt.PyJWKClient(APPLE_JWKS_URL).get_signing_key_from_jwt(data.identity_token)
        claims = jwt.decode(data.identity_token, signing_key.key, algorithms=["RS256"],
                            audience=APPLE_CLIENT_ID, issuer="https://appleid.apple.com")
        subject, email = claims["sub"], claims.get("email", f"{claims['sub']}@privaterelay.invalid")
        email_verified = claims.get("email_verified") in (True, "true")
    except Exception as exc:
        raise HTTPException(401, "invalid Apple identity token") from exc
    with session_scope() as session:
        user = session.scalar(select(User).where(User.apple_subject == subject))
        if user is None:
            user = session.scalar(select(User).where(User.email == email.lower()))
            if user is not None:
                if not email_verified:
                    raise HTTPException(409, "Apple email is not verified for account linking")
                user.apple_subject = subject
            else:
                user = User(email=email.lower(), apple_subject=subject)
                session.add(user)
                session.flush()
                session.add(Account(user_id=user.id))
                session.flush()
        user_id = user.id
        account = session.scalar(select(Account).where(Account.user_id == user_id))
        account_id = account.id
    return {"user_id": user_id, "account_id": account_id, **token_pair(user_id)}


@app.post("/v1/auth/refresh")
def refresh(data: RefreshRequest):
    user_id, family = consume_refresh(data.refresh_token)
    with session_scope() as session:
        user = session.scalar(select(User.id).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        revoke_user_sessions(user_id)
        raise HTTPException(401, "account is unavailable")
    return token_pair(user_id, family)


@app.post("/v1/auth/logout")
def logout(data: RefreshRequest):
    revoke_refresh(data.refresh_token)
    return {"ok": True}


@app.get("/v1/accounts")
def accounts(user_id: int = Depends(current_user)):
    with session_scope() as session:
        return {"accounts": [{"id": a.id, "name": a.name, "currency": a.currency, "cash_ticks": a.cash_ticks}
                             for a in session.scalars(select(Account).where(Account.user_id == user_id))]}


@app.get("/v1/symbols")
def symbols():
    return {"symbols": [{"symbol": "ASTR", "price_scale": PRICE_SCALE, "tick_size": TICK_SIZE,
                         "quantity_unit": "share", "simulated": True}]}


@app.get("/v1/market/{symbol}/book")
def market_book(symbol: str):
    symbol = symbol.upper()
    if symbol not in symbol_ids:
        raise HTTPException(404, "unknown symbol")
    return _book_frame(symbol, sequence[symbol], "snapshot")


@app.post("/v1/accounts/{account_id}/orders", status_code=201)
def place_order(account_id: int, request: OrderRequest, user_id: int = Depends(current_user),
                idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key")):
    rate_limit(user_id, "orders", 60)
    _check_price(request)
    symbol = request.symbol.upper()
    with session_scope() as session:
        account = _account(session, user_id, account_id)
        existing = session.scalar(select(Order).where(Order.account_id == account_id, Order.idempotency_key == idempotency_key))
        if existing:
            return _order_dict(existing)
        with engine_lock:
            # Recheck after serializing on the engine lock so simultaneous
            # retries cannot submit the same idempotency key twice.
            existing = session.scalar(select(Order).where(Order.account_id == account_id, Order.idempotency_key == idempotency_key))
            if existing:
                return _order_dict(existing)
            _risk_check(session, account, request)
            engine_order = _engine_order(request)
            try:
                fills = core.submit(engine_order)
            except Exception as exc:
                raise HTTPException(422, "engine rejected the order") from exc
            row = Order(account_id=account_id, symbol=symbol, side=request.side, order_type=request.type,
                        tif=request.tif, price_ticks=request.price_ticks, stop_price_ticks=request.stop_price_ticks,
                        peg_offset_ticks=request.peg_offset_ticks, quantity=request.quantity,
                        filled_quantity=int(engine_order.filled_quantity), engine_order_id=int(engine_order.id),
                        idempotency_key=idempotency_key,
                        status="filled" if engine_order.is_filled() else "partially_filled" if engine_order.filled_quantity else "open")
            session.add(row)
            session.flush()
            user_events = _apply_fills(session, fills, int(engine_order.id))
            response = _order_dict(row)
            response["fills"] = [{"price_ticks": int(f.price), "quantity": int(f.quantity)} for f in fills]
            session.commit()
            for affected_user, events in user_events.items():
                redis_client.publish(f"astrax:user:{affected_user}", json.dumps({"v": API_VERSION,
                    "type": "execution", "fills": events}))
                for token in session.scalars(select(PushToken.token).where(PushToken.user_id == affected_user)):
                    redis_client.xadd("astrax:push:events", {"token": token,
                        "title": "Simulated order filled", "body": f"{symbol} order executed"},
                        maxlen=10000, approximate=True)
            sequence[symbol] += 1
    return response


@app.get("/v1/accounts/{account_id}/orders")
def list_orders(account_id: int, user_id: int = Depends(current_user)):
    with session_scope() as session:
        _account(session, user_id, account_id)
        return {"orders": [_order_dict(o) for o in session.scalars(select(Order).where(Order.account_id == account_id).order_by(Order.id.desc()))]}


@app.post("/v1/accounts/{account_id}/orders/{order_id}/cancel")
def cancel_order(account_id: int, order_id: int, user_id: int = Depends(current_user)):
    with session_scope() as session:
        _account(session, user_id, account_id)
        row = session.scalar(select(Order).where(Order.id == order_id, Order.account_id == account_id))
        if row is None:
            raise HTTPException(404, "order not found")
        if row.status not in {"open", "partially_filled"} or row.engine_order_id is None:
            raise HTTPException(409, "order cannot be cancelled")
        with engine_lock:
            outcome = core.cancel(row.engine_order_id)
        if str(outcome).lower().endswith("success"):
            row.status = "cancelled"
        else:
            raise HTTPException(409, "engine could not cancel the order")
        return _order_dict(row)


@app.post("/v1/accounts/{account_id}/orders/{order_id}/replace")
def replace_order(account_id: int, order_id: int, request: OrderRequest, user_id: int = Depends(current_user),
                  idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key")):
    _check_price(request)
    with session_scope() as session:
        _account(session, user_id, account_id)
        old = session.scalar(select(Order).where(Order.id == order_id, Order.account_id == account_id))
        if old is None or old.status not in {"open", "partially_filled"}:
            raise HTTPException(409, "order cannot be replaced")
        if old.engine_order_id is None:
            raise HTTPException(409, "order has no live engine order")
        with engine_lock:
            result = core.cancel(old.engine_order_id)
        if not str(result).lower().endswith("success"):
            raise HTTPException(409, "engine could not cancel the existing order")
        old.status = "replaced"
    replacement = place_order(account_id, request, user_id, idempotency_key)
    return {"replaced_order_id": order_id, "replacement": replacement}


@app.get("/v1/accounts/{account_id}/positions")
def positions(account_id: int, user_id: int = Depends(current_user)):
    with session_scope() as session:
        _account(session, user_id, account_id)
        rows = session.scalars(select(Position).where(Position.account_id == account_id))
        return {"positions": [{"symbol": p.symbol, "quantity": p.quantity,
                               "average_price_ticks": p.average_price_ticks,
                               "realized_pnl_ticks": p.realized_pnl_ticks} for p in rows]}


@app.get("/v1/accounts/{account_id}/executions")
def executions(account_id: int, user_id: int = Depends(current_user)):
    with session_scope() as session:
        _account(session, user_id, account_id)
        rows = session.execute(select(Execution, Order.symbol).join(Order).where(Order.account_id == account_id).order_by(Execution.id.desc()).limit(500))
        return {"executions": [{"id": e.id, "symbol": symbol, "side": e.side,
                                "price_ticks": e.price_ticks, "quantity": e.quantity,
                                "created_at": e.created_at.isoformat() if e.created_at else None} for e, symbol in rows]}


@app.get("/v1/candles/{symbol}")
def candles(symbol: str, interval_seconds: int = 60, limit: int = 200):
    if symbol.upper() not in symbol_ids:
        raise HTTPException(404, "unknown symbol")
    interval_seconds, limit = max(1, min(interval_seconds, 86400)), max(1, min(limit, 1000))
    with session_scope() as session:
        rows = session.execute(select(Execution.price_ticks, Execution.quantity, Execution.created_at)
                               .join(Order).where(Order.symbol == symbol.upper()).order_by(Execution.id.desc()).limit(10000)).all()
    buckets = {}
    for price, quantity, created in reversed(rows):
        timestamp = int(created.timestamp())
        start = timestamp // interval_seconds * interval_seconds
        candle = buckets.setdefault(start, {"time": start, "open_ticks": price, "high_ticks": price,
                                             "low_ticks": price, "close_ticks": price, "volume": 0})
        candle["high_ticks"] = max(candle["high_ticks"], price)
        candle["low_ticks"] = min(candle["low_ticks"], price)
        candle["close_ticks"], candle["volume"] = price, candle["volume"] + quantity
    return {"symbol": symbol.upper(), "interval_seconds": interval_seconds,
            "candles": list(buckets.values())[-limit:]}


@app.post("/v1/push-tokens")
def register_push_token(token: str = Header(min_length=32, max_length=256, alias="X-APNS-Token"), user_id: int = Depends(current_user)):
    with session_scope() as session:
        if session.scalar(select(PushToken.id).where(PushToken.token == token)) is None:
            session.add(PushToken(user_id=user_id, token=token))
    return {"ok": True}


async def _ai_completion(prompt: str):
    base = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
    model = os.getenv("LM_STUDIO_MODEL", "")
    if not model:
        raise HTTPException(503, "AI service is not configured")
    with engine_lock:
        book = core.book()
        market = {"symbol": "ASTR", "bids": book.bid_levels(10), "asks": book.ask_levels(10)}
    prompt = f"{prompt}\n\nCurrent simulated market data (integer ticks): {json.dumps(market)}"
    async with httpx.AsyncClient(timeout=45) as client:
        try:
            response = await client.post(f"{base}/chat/completions", json={"model": model,
                "messages": [{"role": "user", "content": prompt + "\n\nInformational only, not financial advice."}]})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(503, "AI service is unavailable") from exc
    return {"content": response.json()["choices"][0]["message"]["content"],
            "disclaimer": "Informational only, not financial advice."}


@app.post("/v1/ai/strategy-plan")
async def strategy_plan(user_id: int = Depends(current_user)):
    rate_limit(user_id, "ai", 10)
    return await _ai_completion("Provide a concise educational strategy-planning analysis for a paper trading simulator. State assumptions and risks.")


@app.post("/v1/ai/market-report")
async def market_report(user_id: int = Depends(current_user)):
    rate_limit(user_id, "ai", 10)
    return await _ai_completion("Summarize market structure and liquidity for a simulated exchange. Avoid trade recommendations.")


@app.post("/v1/ai/regime-similarity")
async def regime_similarity(user_id: int = Depends(current_user)):
    rate_limit(user_id, "ai", 10)
    return await _ai_completion("Explain how regime similarity can be interpreted in a paper trading simulation, including limitations.")


@app.delete("/v1/account")
def delete_account(request: DeleteAccountRequest, user_id: int = Depends(current_user)):
    revoke_user_sessions(user_id)
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is not None:
            user.is_active = False
            for account in session.scalars(select(Account).where(Account.user_id == user_id)):
                for row in session.scalars(select(Order).where(Order.account_id == account.id, Order.status.in_(("open", "partially_filled")))):
                    if row.engine_order_id:
                        with engine_lock:
                            core.cancel(row.engine_order_id)
            session.delete(user)
    return {"deleted": True}


@app.websocket("/v1/market")
async def market_gateway(ws: WebSocket):
    await ws.accept()
    try:
        auth = await asyncio.wait_for(ws.receive_json(), timeout=10)
        if auth.get("type") != "auth":
            await ws.close(code=4401)
            return
        try:
            claims = jwt.decode(auth["token"], JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)
            if claims.get("typ") != "access" or not redis_client.exists(f"session:{claims['sub']}:{claims['family']}"):
                raise ValueError("invalid token type")
        except Exception:
            await ws.close(code=4401)
            return
        await ws.send_json({"v": API_VERSION, "type": "auth", "ok": True})
        seq = defaultdict(int)
        subscriptions = set()
        last_heartbeat = time.monotonic()
        pubsub = async_redis.pubsub()
        await pubsub.subscribe(f"astrax:user:{claims['sub']}")
        try:
            while True:
                try:
                    message = await asyncio.wait_for(ws.receive_json(), timeout=0.05)
                    symbol = str(message.get("symbol", "")).upper()
                    if message.get("type") == "subscribe" and symbol in symbol_ids:
                        subscriptions.add(symbol)
                        await pubsub.subscribe(f"astrax:market:{symbol}")
                        frame = _book_frame(symbol, sequence[symbol], "snapshot")
                        seq[symbol] = frame["seq"]
                        await ws.send_json(frame)
                    elif message.get("type") == "unsubscribe":
                        subscriptions.discard(symbol)
                        await pubsub.unsubscribe(f"astrax:market:{symbol}")
                    elif message.get("type") == "resync" and symbol in subscriptions:
                        frame = _book_frame(symbol, sequence[symbol], "snapshot")
                        seq[symbol] = frame["seq"]
                        await ws.send_json(frame)
                except asyncio.TimeoutError:
                    pass
                event = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
                if event and event.get("data"):
                    try:
                        payload = json.loads(event["data"])
                    except (TypeError, json.JSONDecodeError):
                        payload = {}
                    if payload.get("type") == "execution":
                        await ws.send_json(payload)
                    elif payload.get("symbol") in subscriptions and int(payload.get("seq", 0)) > seq[payload["symbol"]]:
                        seq[payload["symbol"]] = int(payload["seq"])
                        await ws.send_json(payload)
                elif not subscriptions and time.monotonic() - last_heartbeat >= 10:
                    await ws.send_json({"v": API_VERSION, "type": "heartbeat", "time": time.time_ns()})
                    last_heartbeat = time.monotonic()
        finally:
            await pubsub.aclose()
    except (WebSocketDisconnect, asyncio.TimeoutError, KeyError):
        return


def _book_frame(symbol: str, seq: int, kind: str):
    with engine_lock:
        book = core.book()
        return {"v": API_VERSION, "type": "book", "kind": kind, "symbol": symbol, "seq": seq,
                "bids": book.bid_levels(10), "asks": book.ask_levels(10), "time": time.time_ns()}


async def _market_publisher():
    while True:
        await asyncio.sleep(0.1)
        for symbol in symbol_ids:
            sequence[symbol] += 1
            await async_redis.publish(f"astrax:market:{symbol}",
                                      json.dumps(_book_frame(symbol, sequence[symbol], "delta")))


@app.on_event("startup")
async def startup():
    if len(JWT_SECRET) < 32:
        raise RuntimeError("Set ASTRAX_JWT_SECRET to a random value of at least 32 characters")
    redis_client.ping()
    app.state.market_task = asyncio.create_task(_market_publisher(), name="market-publisher")
    app.state.feed_server = await serve_tcp_feed(core, engine_lock, _feed_changed)


async def _feed_changed(fills):
    with session_scope() as session:
        user_events = _apply_fills(session, fills, submitted_engine_id=0)
        session.commit()
        for user_id, events in user_events.items():
            redis_client.publish(f"astrax:user:{user_id}", json.dumps({"v": API_VERSION, "type": "execution", "fills": events}))
            for token in session.scalars(select(PushToken.token).where(PushToken.user_id == user_id)):
                redis_client.xadd("astrax:push:events", {"token": token, "title": "Simulated order filled",
                    "body": "A simulated order was executed"}, maxlen=10000, approximate=True)
    for symbol in symbol_ids:
        sequence[symbol] += 1


@app.on_event("shutdown")
async def shutdown():
    app.state.market_task.cancel()
    app.state.feed_server.close()
    await app.state.feed_server.wait_closed()
    await async_redis.aclose()
