"""WebSocket server that streams live exchange data to the dashboard."""

import asyncio
import collections
import json
import sys
import os
import time
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'build', 'bindings'))

import exchange_simulator as ex
from agents import RandomAgent, MarketMakerAgent
from ai import (
    archive_regime_snapshot,
    LMStudioClient,
    generate_market_analysis_report,
    generate_simulation_result_summary,
    generate_strategy_plan,
    find_similar_regimes,
    regime_text,
    simulation_summary_metrics,
)

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)


class LiveExchange:
    """Runs the exchange simulation and broadcasts state via WebSocket."""

    regime_archive_interval = 100
    max_regime_archive_size = 120

    def __init__(self):
        self.engine = ex.MatchingEngine()
        self.agents = [
            MarketMakerAgent(agent_id=0),
            RandomAgent(agent_id=1, seed=42),
            RandomAgent(agent_id=2, seed=123),
            RandomAgent(agent_id=3, seed=456),
            RandomAgent(agent_id=4, seed=789),
        ]
        self.step_count = 0
        self.recent_fills: list[dict] = []
        self.order_to_agent: dict[int, object] = {}
        self.running = False
        # Latency tracking: ring buffer of last 1000 submit latencies (nanoseconds)
        self.latency_samples: collections.deque = collections.deque(maxlen=1000)
        self.llm = LMStudioClient()
        self.regime_archive: list[dict] = []

    def _compute_latency_stats(self) -> dict | None:
        """Compute latency histogram summary from recent samples."""
        if not self.latency_samples:
            return None
        samples = sorted(self.latency_samples)
        n = len(samples)

        def percentile(p: float) -> int:
            idx = int(p / 100.0 * (n - 1))
            return samples[idx]

        return {
            "p50": percentile(50),
            "p90": percentile(90),
            "p95": percentile(95),
            "p99": percentile(99),
            "mean": int(sum(samples) / n),
            "min": samples[0],
            "max": samples[-1],
            "count": n,
        }

    def tick(self) -> dict:
        """Execute one simulation step and return state snapshot."""
        self.step_count += 1
        timestamp = self.step_count * 1_000_000

        step_fills = []

        for agent in self.agents:
            orders = agent.on_market_data(self.engine, timestamp)
            for order in orders:
                self.order_to_agent[order.id] = agent
                t0 = time.perf_counter_ns()
                fills = self.engine.submit(order)
                t1 = time.perf_counter_ns()
                self.latency_samples.append(t1 - t0)
                order_rate_samples.append(time.time())
                for fill in fills:
                    fill_dict = {
                        "price": fill.price,
                        "quantity": fill.quantity,
                        "side": fill.aggressor_side.name,
                        "timestamp": timestamp,
                    }
                    step_fills.append(fill_dict)

                    taker = self.order_to_agent.get(fill.taker_order_id)
                    if taker:
                        taker.on_fill(fill)
                    maker = self.order_to_agent.get(fill.maker_order_id)
                    if maker:
                        maker.on_fill(fill)

        self.recent_fills.extend(step_fills)
        self.recent_fills = self.recent_fills[-50:]

        book = self.engine.book()
        best_bid = book.best_bid_price()
        best_ask = book.best_ask_price()

        msg = {
            "type": "tick",
            "step": self.step_count,
            "book": {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid": (best_bid + best_ask) // 2 if best_bid and best_ask else None,
                "spread": best_ask - best_bid if best_bid and best_ask else None,
                "bid_depth": book.bid_depth(),
                "ask_depth": book.ask_depth(),
            },
            "fills": step_fills,
            "agents": [
                {
                    "name": a.name,
                    "pnl": a.pnl,
                    "inventory": a.inventory,
                    "fills": len(a.fills),
                }
                for a in self.agents
            ],
        }

        # Broadcast latency histogram every 100 ticks
        if self.step_count % 100 == 0:
            latency_stats = self._compute_latency_stats()
            if latency_stats:
                msg["latency"] = latency_stats

        if self.step_count % self.regime_archive_interval == 0:
            self._archive_regime_state()

        return msg

    def _archive_regime_state(self) -> None:
        """Store the current market regime for later similarity lookup."""
        snapshot = self.snapshot()
        try:
            archive_regime_snapshot(
                self.llm,
                self.regime_archive,
                snapshot,
                max_items=self.max_regime_archive_size,
            )
        except RuntimeError:
            # Keep the simulation running if local embeddings are unavailable.
            pass

    def compare_regime(self, limit: int = 3) -> dict:
        """Compare the current market regime against archived snapshots."""
        snapshot = self.snapshot()
        current_description = regime_text(snapshot)
        try:
            matches = find_similar_regimes(
                self.llm,
                snapshot,
                self.regime_archive,
                limit=limit,
            )
            return {
                "type": "regime_similarity",
                "ok": True,
                "current_step": snapshot.get("step"),
                "current_description": current_description,
                "archive_size": len(self.regime_archive),
                "matches": matches,
            }
        except RuntimeError as exc:
            return {
                "type": "regime_similarity",
                "ok": False,
                "current_step": snapshot.get("step"),
                "current_description": current_description,
                "archive_size": len(self.regime_archive),
                "matches": [],
                "error": str(exc),
            }

    def submit_binary_order(self, payload: bytes) -> list[bytes]:
        """Decode a binary order frame, submit it, and return encoded fill frames."""
        order = ex.BinaryProtocol.decode_order(payload)
        if order is None:
            return []

        self.order_to_agent[order.id] = None
        t0 = time.perf_counter_ns()
        fills = self.engine.submit(order)
        t1 = time.perf_counter_ns()
        self.latency_samples.append(t1 - t0)

        encoded_fills: list[bytes] = []
        for fill in fills:
            encoded_fills.append(ex.BinaryProtocol.encode_fill(fill))
        return encoded_fills

    def snapshot(self) -> dict:
        """Return the latest exchange state for analysis requests."""
        book = self.engine.book()
        best_bid = book.best_bid_price()
        best_ask = book.best_ask_price()
        return {
            "type": "snapshot",
            "step": self.step_count,
            "book": {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid": (best_bid + best_ask) // 2 if best_bid and best_ask else None,
                "spread": best_ask - best_bid if best_bid and best_ask else None,
                "bid_depth": book.bid_depth(),
                "ask_depth": book.ask_depth(),
            },
            "fills": list(self.recent_fills),
            "agents": [
                {
                    "name": a.name,
                    "pnl": a.pnl,
                    "inventory": a.inventory,
                    "fills": len(a.fills),
                }
                for a in self.agents
            ],
            "latency": self._compute_latency_stats(),
        }


exchange = LiveExchange()
clients: set = set()
from trading import TradingService
trading = TradingService(exchange.engine)


async def http_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Minimal JSON HTTP surface for account and mock-order operations."""
    try:
        header = await reader.readuntil(b"\r\n\r\n")
        lines = header.decode("latin1").split("\r\n")
        method, raw_path, _ = lines[0].split(" ", 2)
        parsed = urlparse(raw_path)
        path, query = parsed.path, parse_qs(parsed.query)
        headers = {k.strip().lower(): v.strip() for line in lines[1:] if ":" in line for k,v in [line.split(":",1)]}
        length = int(headers.get("content-length", "0"))
        body = json.loads(await reader.readexactly(length)) if length else {}
        status, payload = 200, {"error": "NOT_FOUND"}
        if method == "GET" and path == "/api/v1/health":
            payload = {"ok": True, "version": 1}
        elif method == "GET" and path == "/api/v1/symbols":
            payload = {"symbols": [{"symbol":"ASTR","price_scale":10000,"quantity_unit":"share","tick_size":100}]}
        elif method == "GET" and path == "/api/v1/book/ASTR":
            levels = min(10, max(1, int(query.get("levels", [10])[0])))
            book = exchange.engine.book()
            payload = {"v":1,"symbol":"ASTR","bids":book.bid_levels(levels),"asks":book.ask_levels(levels)}
        elif method == "GET" and path == "/api/v1/trades/ASTR":
            limit = min(500, max(1, int(query.get("limit", [100])[0])))
            payload = {"symbol":"ASTR","trades":exchange.recent_fills[-limit:]}
        elif method == "GET" and path == "/api/v1/candles":
            if query.get("symbol", ["ASTR"])[0].upper() != "ASTR":
                status, payload = 404, {"error":"UNKNOWN_SYMBOL"}
            else:
                interval = max(1, int(query.get("interval", ["60"])[0]))
                limit = min(500, max(1, int(query.get("limit", ["100"])[0])))
                buckets = {}
                for trade in exchange.recent_fills:
                    t = int(trade["timestamp"] // 1_000_000_000)
                    start = t // interval * interval
                    c = buckets.setdefault(start, {"time":start,"open":trade["price"],"high":trade["price"],"low":trade["price"],"close":trade["price"],"volume":0})
                    c["high"] = max(c["high"], trade["price"]); c["low"] = min(c["low"], trade["price"])
                    c["close"] = trade["price"]; c["volume"] += trade["quantity"]
                payload = {"symbol":"ASTR","interval":interval,"candles":sorted(buckets.values(), key=lambda x:x["time"])[-limit:]}
        elif method == "POST" and path == "/api/v1/auth/login":
            token = trading.login(str(body.get("username", "")), str(body.get("password", "")))
            status, payload = (200, {"token": token}) if token else (401, {"error": "INVALID_CREDENTIALS"})
        else:
            auth = headers.get("authorization", "")
            user = trading.user_for_token(auth.removeprefix("Bearer ")) if auth.startswith("Bearer ") else None
            if not user:
                status, payload = 401, {"error": "UNAUTHENTICATED"}
            elif method == "GET" and path == "/api/v1/me":
                payload = {"id": user["id"], "username": user["username"], "role": user["role"], "cash": user["cash"]}
            elif method == "GET" and path == "/api/v1/portfolio":
                payload = trading.portfolio(user["id"])
            elif method == "POST" and path == "/api/v1/orders":
                row, timings = trading.submit(user, body)
                payload = {"order": row, "timings": timings}
                status = 400 if row["status"] == "REJECTED" else 200
            elif method == "GET" and path == "/api/v1/orders":
                payload = {"orders": trading.user_orders(user["id"], query.get("status", [None])[0])}
            elif method == "DELETE" and path.startswith("/api/v1/orders/"):
                order_id = int(path.rsplit("/",1)[1])
                row = trading.db.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id,user["id"])).fetchone()
                if not row: status,payload=404,{"error":"ORDER_NOT_FOUND"}
                elif row["status"] not in ("NEW","PARTIALLY_FILLED"): status,payload=409,{"error":"ORDER_NOT_OPEN"}
                else:
                    result=exchange.engine.cancel(int(row["engine_id"]))
                    if str(result).endswith("Success"):
                        trading.db.execute("UPDATE orders SET status='CANCELLED',updated=? WHERE id=?",(time.time(),order_id)); trading.db.commit()
                        payload={"ok":True,"order_id":order_id}
                    else: status,payload=409,{"error":"ENGINE_CANCEL_FAILED"}
            elif path.startswith("/api/v1/admin/"):
                if user["role"] != "admin": status,payload=403,{"error":"FORBIDDEN"}
                elif method == "POST" and path == "/api/v1/admin/simulator/start":
                    exchange.running=True; payload={"ok":True,"running":True}
                elif method == "POST" and path == "/api/v1/admin/simulator/stop":
                    exchange.running=False; payload={"ok":True,"running":False}
                elif method == "GET" and path == "/api/v1/admin/stats":
                    values=list(exchange.latency_samples)
                    ordered=sorted(values)
                    percentile=lambda p: ordered[min(len(ordered)-1,int((len(ordered)-1)*p))] if ordered else None
                    payload={"orders_per_second":sum(t>=time.time()-1 for t in order_rate_samples),"p50_ns":percentile(.50),"p99_ns":percentile(.99),"connected_clients":len(clients),"active_users":trading.db.execute("SELECT COUNT(DISTINCT user_id) FROM tokens WHERE created> ?",(time.time()-3600,)).fetchone()[0]}
                elif method == "POST" and path == "/api/v1/admin/benchmarks/run":
                    global benchmark_active
                    if benchmark_active: status,payload=409,{"error":"BENCHMARK_ALREADY_RUNNING"}
                    else:
                        cur=trading.db.execute("INSERT INTO benchmark_runs(status,created) VALUES('RUNNING',?)",(time.time(),)); trading.db.commit()
                        run_id=cur.lastrowid; benchmark_active=True
                        benchmark_tasks[run_id]=asyncio.create_task(run_benchmarks(run_id))
                        status,payload=202,{"run_id":run_id,"status":"RUNNING","warning":"Results under server load are not clean measurements."}
                elif method == "GET" and path == "/api/v1/admin/benchmarks":
                    payload={"runs":[dict(r) for r in trading.db.execute("SELECT id,status,created,finished,error FROM benchmark_runs ORDER BY id DESC LIMIT 100")]}
                elif method == "GET" and path.startswith("/api/v1/admin/benchmarks/"):
                    run_id=int(path.rsplit("/",1)[1]); r=trading.db.execute("SELECT * FROM benchmark_runs WHERE id=?",(run_id,)).fetchone()
                    if not r: status,payload=404,{"error":"RUN_NOT_FOUND"}
                    else: payload={**dict(r),"result":json.loads(r["result_json"]) if r["result_json"] else None}
                else: status,payload=404,{"error":"NOT_FOUND"}
            else:
                status, payload = 404, {"error": "NOT_FOUND"}
        encoded = json.dumps(payload).encode()
        reason = "OK" if status == 200 else "Error"
        writer.write(f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {len(encoded)}\r\nConnection: close\r\n\r\n".encode() + encoded)
        await writer.drain()
    except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def broadcast(message: str):
    if clients:
        await asyncio.gather(*(c.send(message) for c in clients))


async def simulation_loop():
    """Run simulation at ~100 steps/sec, broadcasting each tick."""
    while True:
        if exchange.running:
            state = exchange.tick()
            await broadcast(json.dumps(state))
        await asyncio.sleep(0.01)


async def run_benchmarks(run_id):
    global benchmark_active
    try:
        root=pathlib.Path(__file__).resolve().parents[2]
        exe=".exe" if os.name == "nt" else ""
        results=[]
        for name in ("bench_order_book","bench_matching"):
            binary=root/"build"/"engine"/"bench"/(name+exe)
            if not binary.exists(): raise FileNotFoundError(f"Missing benchmark binary: {binary}")
            proc=await asyncio.create_subprocess_exec(str(binary),"--benchmark_format=json",stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            out,err=await asyncio.wait_for(proc.communicate(),timeout=120)
            if proc.returncode: raise RuntimeError(err.decode(errors="replace")[:1000])
            results.append({"name":name,"results":json.loads(out)})
        metadata={"benchmarks":results,"machine":platform.platform(),"processor":platform.processor(),"compiler":"not recorded by current benchmark binary","git_commit":"unavailable"}
        trading.db.execute("UPDATE benchmark_runs SET status='COMPLETED',finished=?,result_json=? WHERE id=?",(time.time(),json.dumps(metadata),run_id)); trading.db.commit()
    except Exception as exc:
        trading.db.execute("UPDATE benchmark_runs SET status='FAILED',finished=?,error=? WHERE id=?",(time.time(),str(exc),run_id)); trading.db.commit()
    finally:
        benchmark_active=False


async def tcp_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Accept fixed-size binary order frames from a TCP feeder."""
    frame_size = ex.BinaryProtocol.order_size()
    try:
        while True:
            payload = await reader.readexactly(frame_size)
            fill_frames = exchange.submit_binary_order(payload)
            for frame in fill_frames:
                writer.write(frame)
            if fill_frames:
                await writer.drain()
    except asyncio.IncompleteReadError:
        pass
    finally:
        writer.close()
        await writer.wait_closed()


async def handler(websocket):
    if getattr(websocket, "path", "") == "/ws":
        await phone_ws_handler(websocket)
        return
    clients.add(websocket)
    try:
        # Send initial state
        await websocket.send(json.dumps({
            "type": "init",
            "agents": [a.name for a in exchange.agents],
            "llm": {
                "chat_model": exchange.llm.config.chat_model,
                "embed_model": exchange.llm.config.embed_model,
            },
        }))
        async for message in websocket:
            data = json.loads(message)
            if data.get("command") == "reset":
                exchange.__init__()
                await websocket.send(json.dumps({"type": "reset", "ok": True}))
            elif data.get("command") == "analysis":
                analysis_type = data.get("analysis_type", "strategy_plan")
                snapshot = exchange.snapshot()
                if analysis_type == "market_report":
                    content = generate_market_analysis_report(exchange.llm, snapshot)
                elif analysis_type == "simulation_summary":
                    metrics = simulation_summary_metrics(snapshot)
                    content = generate_simulation_result_summary(exchange.llm, metrics)
                else:
                    content = generate_strategy_plan(exchange.llm, snapshot)
                await websocket.send(json.dumps({
                    "type": "analysis",
                    "analysis_type": analysis_type,
                    "content": content,
                }))
            elif data.get("command") == "regime_similarity":
                limit = int(data.get("limit", 3))
                await websocket.send(json.dumps(exchange.compare_regime(limit=limit)))
    finally:
        clients.discard(websocket)


async def phone_ws_handler(websocket):
    """Versioned, authenticated, conflated market feed for mobile clients."""
    try:
        first = await asyncio.wait_for(websocket.recv(), timeout=10)
        auth = json.loads(first)
        user = trading.user_for_token(str(auth.get("token", ""))) if auth.get("type") == "auth" else None
        if not user:
            await websocket.send(json.dumps({"v":1,"type":"error","code":"UNAUTHENTICATED"}))
            return
        await websocket.send(json.dumps({"v":1,"type":"auth","ok":True,"role":user["role"]}))
        symbols, seq = set(), {}
        last_send = 0.0
        while True:
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=max(0.01, 0.1-(time.monotonic()-last_send)))
                msg = json.loads(raw)
                if msg.get("type") == "subscribe":
                    symbol = str(msg.get("symbol", "")).upper()
                    if symbol == "ASTR":
                        symbols.add(symbol); seq[symbol] = seq.get(symbol,0)+1
                        await send_mobile_book(websocket, symbol, seq[symbol], "snapshot")
                elif msg.get("type") == "unsubscribe":
                    symbols.discard(str(msg.get("symbol", "")).upper())
                elif msg.get("type") == "resync" and msg.get("symbol") in symbols:
                    symbol = msg["symbol"]; seq[symbol] += 1
                    await send_mobile_book(websocket, symbol, seq[symbol], "snapshot")
            except asyncio.TimeoutError:
                if symbols:
                    for symbol in tuple(symbols):
                        seq[symbol] = seq.get(symbol,0)+1
                        await send_mobile_book(websocket, symbol, seq[symbol], "delta")
                    last_send = time.monotonic()
                else:
                    await websocket.send(json.dumps({"v":1,"type":"heartbeat","time":time.time()}))
                    last_send = time.monotonic()
    except (asyncio.TimeoutError, websockets.ConnectionClosed):
        return


async def send_mobile_book(websocket, symbol, seq, kind):
    book=exchange.engine.book()
    await websocket.send(json.dumps({"v":1,"type":"book","kind":kind,"symbol":symbol,"seq":seq,
      "bids":book.bid_levels(10),"asks":book.ask_levels(10)}))


async def main():
    print("Starting exchange dashboard server on ws://localhost:8765")
    tcp_server = await asyncio.start_server(tcp_handler, "localhost", 8766)
    http_server = await asyncio.start_server(http_handler, "localhost", 8767)
    async with websockets.serve(handler, "localhost", 8765), tcp_server, http_server:
        await simulation_loop()


if __name__ == "__main__":
    asyncio.run(main())

# AstraX repo sync
