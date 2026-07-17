"""WebSocket server that streams live exchange data to the dashboard."""

import asyncio
import collections
import json
import sys
import os
import time

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


async def broadcast(message: str):
    if clients:
        await asyncio.gather(*(c.send(message) for c in clients))


async def simulation_loop():
    """Run simulation at ~100 steps/sec, broadcasting each tick."""
    exchange.running = True
    while exchange.running:
        state = exchange.tick()
        await broadcast(json.dumps(state))
        await asyncio.sleep(0.01)


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


async def main():
    print("Starting exchange dashboard server on ws://localhost:8765")
    tcp_server = await asyncio.start_server(tcp_handler, "localhost", 8766)
    async with websockets.serve(handler, "localhost", 8765), tcp_server:
        await simulation_loop()


if __name__ == "__main__":
    asyncio.run(main())

# AstraX repo sync
