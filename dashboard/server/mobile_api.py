"""Versioned, public simulator API for native mobile clients and local tools.

This is a development/portfolio simulator API. It deliberately has no login or
broker connectivity. Each symbol has one bounded command queue and one worker;
market-data fanout uses conflated bounded queues so slow clients cannot stall
matching or other subscribers.
"""
from __future__ import annotations

import asyncio
import collections
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "build" / "bindings"))
sys.path.insert(0, str(ROOT))
import exchange_simulator as ex  # noqa: E402

API_VERSION = 1
QUEUE_CAPACITY = 256
MAX_BATCH = 50
PRICE_SCALE = 10_000


class OrderInput(BaseModel):
    symbol: str = Field(default="ASTR", min_length=1, max_length=16)
    side: Literal["buy", "sell"]
    type: Literal["limit", "market"] = "limit"
    quantity: int = Field(gt=0, le=10_000)
    price: int = Field(default=0, ge=0, le=9_000_000_000_000)
    client_order_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_price(self):
        if self.type == "limit" and (self.price <= 0 or self.price % 100):
            raise ValueError("limit price must be positive and aligned to the 0.01 tick")
        if self.type == "market" and self.price != 0:
            raise ValueError("market orders must not include a price")
        return self


class BatchInput(BaseModel):
    orders: list[OrderInput] = Field(min_length=1, max_length=MAX_BATCH)


class SymbolActor:
    """Single-writer owner of one symbol book, with bounded admission."""
    def __init__(self, symbol: str, capacity: int = QUEUE_CAPACITY):
        self.symbol = symbol
        self.engine = ex.MatchingEngine()
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=capacity)
        self.task: asyncio.Task | None = None
        self.sequence = 0
        self.trades: collections.deque = collections.deque(maxlen=500)
        self.latencies: collections.deque = collections.deque(maxlen=2000)
        self.accepted = 0
        self.rejected = 0
        self._seed()

    def _seed(self):
        """Add demo liquidity so a new install has a visible two-sided quote."""
        for idx, (side, price) in enumerate(((ex.Side.Buy, 999_900), (ex.Side.Sell, 1_000_100)), 1):
            order = ex.Order()
            order.id = (int(time.time_ns()) + idx) & 0x7FFFFFFFFFFFFFFF
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
            self.engine.submit(order)

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self._run(), name=f"symbol-{self.symbol}")

    async def submit(self, item: OrderInput) -> dict:
        if self.queue.full():
            self.rejected += 1
            raise HTTPException(status_code=503, detail={"code":"ENGINE_BUSY", "retryable":True})
        loop = asyncio.get_running_loop()
        result = loop.create_future()
        command = {"input": item, "future": result, "received_ns": time.perf_counter_ns()}
        self.queue.put_nowait(command)
        return await result

    async def _run(self):
        while True:
            command = await self.queue.get()
            try:
                item: OrderInput = command["input"]
                order = ex.Order()
                order.id = time.time_ns() & 0x7FFFFFFFFFFFFFFF
                order.side = ex.Side.Buy if item.side == "buy" else ex.Side.Sell
                order.price = item.price
                order.stop_price = 0
                order.peg_offset = 0
                order.quantity = item.quantity
                order.filled_quantity = 0
                order.visible_quantity = 0
                order.hidden_quantity = 0
                order.type = ex.OrderType.Limit if item.type == "limit" else ex.OrderType.Market
                order.tif = ex.TimeInForce.GTC
                order.timestamp = time.time_ns()
                started = time.perf_counter_ns()
                fills = self.engine.submit(order)
                engine_us = (time.perf_counter_ns() - started) // 1000
                total_us = (time.perf_counter_ns() - command["received_ns"]) // 1000
                self.latencies.append({"queue_us": max(0, total_us-engine_us), "engine_us": engine_us, "total_us": total_us})
                self.accepted += 1
                fill_rows = [{"price":int(f.price),"quantity":int(f.quantity),"side":f.aggressor_side.name.lower(),"timestamp":time.time_ns()} for f in fills]
                self.trades.extend(fill_rows)
                self.sequence += 1
                command["future"].set_result({"v":API_VERSION,"symbol":self.symbol,"status":"filled" if order.is_filled() else "partially_filled" if order.filled_quantity else "accepted","filled":int(order.filled_quantity),"quantity":item.quantity,"remaining":int(order.remaining()),"client_order_id":item.client_order_id,"engine_order_id":int(order.id),"fills":fill_rows,"timing_us":{"queue":max(0,total_us-engine_us),"engine":engine_us,"total":total_us},"seq":self.sequence})
            except Exception as exc:
                if not command["future"].done(): command["future"].set_exception(exc)
            finally:
                self.queue.task_done()

    def snapshot(self) -> dict:
        book = self.engine.book()
        return {"v":API_VERSION,"type":"book","kind":"snapshot","symbol":self.symbol,"seq":self.sequence,"time":time.time_ns(),"bids":book.bid_levels(10),"asks":book.ask_levels(10)}


app = FastAPI(title="AstraX Simulator API", version="1.0.0")
actors = {"ASTR": SymbolActor("ASTR")}
subscribers: set[asyncio.Queue] = set()
metric_requests = collections.Counter()
metric_rejects = collections.Counter()
http_latency_ms: collections.deque = collections.deque(maxlen=2000)


@app.middleware("http")
async def request_metrics(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        metric_requests[(request.method, request.url.path, 500)] += 1
        raise
    elapsed = (time.perf_counter() - start) * 1000
    http_latency_ms.append(elapsed)
    metric_requests[(request.method, request.url.path, response.status_code)] += 1
    response.headers["x-request-id"] = request_id
    response.headers["x-api-version"] = str(API_VERSION)
    response.headers["server-timing"] = f"app;dur={elapsed:.2f}"
    return response


@app.exception_handler(404)
async def not_found(_request: Request, _exc):
    return JSONResponse(status_code=404, content={"v":API_VERSION,"error":{"code":"NOT_FOUND"}})


@app.exception_handler(HTTPException)
async def api_error(_request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code":str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"v":API_VERSION,"error":detail}, headers=exc.headers)


@app.get("/api/v1/health")
async def health():
    return {"v":API_VERSION,"ok":True,"service":"astrax-simulator"}


@app.get("/api/v1/symbols")
async def symbols():
    return {"v":API_VERSION,"symbols":[{"symbol":s,"price_scale":PRICE_SCALE,"tick_size":100} for s in actors]}


@app.get("/api/v1/book/{symbol}")
async def book(symbol: str):
    actor = actors.get(symbol.upper())
    if actor is None: raise HTTPException(404, detail={"code":"UNKNOWN_SYMBOL"})
    return actor.snapshot()


@app.get("/api/v1/trades/{symbol}")
async def trades(symbol: str, limit: int = 50):
    actor = actors.get(symbol.upper())
    if actor is None: raise HTTPException(404, detail={"code":"UNKNOWN_SYMBOL"})
    return {"v":API_VERSION,"symbol":actor.symbol,"trades":list(actor.trades)[-max(1,min(limit,500)):],"seq":actor.sequence}


@app.post("/api/v1/orders")
async def submit_order(order: OrderInput):
    actor = actors.get(order.symbol.upper())
    if actor is None: raise HTTPException(422, detail={"code":"UNKNOWN_SYMBOL"})
    try: return await actor.submit(order)
    except HTTPException: metric_rejects["queue_full"] += 1; raise


@app.post("/api/v1/orders/batch")
async def submit_batch(batch: BatchInput):
    # Preserve request order. Every symbol actor independently serializes its book.
    results = []
    for item in batch.orders:
        actor = actors.get(item.symbol.upper())
        if actor is None:
            results.append({"v":API_VERSION,"symbol":item.symbol,"status":"rejected","error":{"code":"UNKNOWN_SYMBOL"},"client_order_id":item.client_order_id})
            metric_rejects["unknown_symbol"] += 1
            continue
        try: results.append(await actor.submit(item))
        except HTTPException as exc:
            if exc.status_code != 503: raise
            results.append({"v":API_VERSION,"symbol":item.symbol,"status":"rejected","error":exc.detail,"client_order_id":item.client_order_id})
    return {"v":API_VERSION,"results":results,"count":len(results)}


@app.get("/api/v1/metrics")
async def metrics():
    def summary(values):
        vals = sorted(values)
        return {"count":len(vals),"p50":round(vals[int((len(vals)-1)*.50)],2) if vals else None,"p95":round(vals[int((len(vals)-1)*.95)],2) if vals else None,"p99":round(vals[int((len(vals)-1)*.99)],2) if vals else None}
    return {"v":API_VERSION,"http_latency_ms":summary(http_latency_ms),"requests":[{"method":k[0],"path":k[1],"status":k[2],"count":v} for k,v in metric_requests.items()],"rejects":dict(metric_rejects),"symbols":{s:{"queue_depth":a.queue.qsize(),"queue_capacity":a.queue.maxsize,"accepted":a.accepted,"rejected":a.rejected,"latency_us":summary([x["total_us"] for x in a.latencies]),"engine_us":summary([x["engine_us"] for x in a.latencies]),"queue_us":summary([x["queue_us"] for x in a.latencies])} for s,a in actors.items()},"subscribers":len(subscribers)}


@app.websocket("/ws/v1/market")
async def market_stream(ws: WebSocket):
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    subscribers.add(queue)
    last_seq = 0
    try:
        await ws.send_json(actors["ASTR"].snapshot())
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                await ws.send_json({"v":API_VERSION,"type":"heartbeat","time":time.time_ns()})
                continue
            # Full snapshots are intentionally conflated: skipping an intermediate
            # snapshot is safe, and every message is independently usable.
            if payload["seq"] > last_seq:
                await ws.send_json(payload)
                last_seq = payload["seq"]
    except WebSocketDisconnect:
        pass
    finally:
        subscribers.discard(queue)


async def market_publisher():
    while True:
        await asyncio.sleep(0.1)
        if not subscribers: continue
        payload = actors["ASTR"].snapshot()
        for queue in tuple(subscribers):
            if queue.full():
                try: queue.get_nowait(); queue.task_done()
                except asyncio.QueueEmpty: pass
            try: queue.put_nowait(payload)
            except asyncio.QueueFull: pass


@app.on_event("startup")
async def startup():
    for actor in actors.values(): actor.start()
    app.state.publisher = asyncio.create_task(market_publisher(), name="market-publisher")


@app.on_event("shutdown")
async def shutdown():
    app.state.publisher.cancel()
    for actor in actors.values():
        if actor.task: actor.task.cancel()

