"""LM Studio-backed analysis helpers for strategy, summaries, and regime similarity."""

from __future__ import annotations

import json
import os
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    chat_model: str
    embed_model: str
    timeout_seconds: float


def load_config() -> LLMConfig:
    """Load LM Studio settings from environment variables."""
    return LLMConfig(
        base_url=os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1").rstrip("/"),
        chat_model=os.getenv("LM_STUDIO_MODEL", "qwen/qwen3-4b-2507"),
        embed_model=os.getenv("LM_STUDIO_EMBED_MODEL", "nomic-embed-text"),
        timeout_seconds=float(os.getenv("LM_STUDIO_TIMEOUT_SECONDS", "30")),
    )


class LMStudioClient:
    """Tiny OpenAI-compatible client for local LM Studio models."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or load_config()

    def chat(self, system: str, user: str, temperature: float = 0.2) -> str:
        payload = {
            "model": self.config.chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        data = self._post("/chat/completions", payload)
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("LM Studio returned no chat choices")
        message = choices[0].get("message", {})
        return message.get("content", "").strip()

    def embed(self, text: str) -> list[float]:
        payload = {
            "model": self.config.embed_model,
            "input": text,
        }
        data = self._post("/embeddings", payload)
        embedding = data.get("data", [{}])[0].get("embedding")
        if not embedding:
            raise RuntimeError("LM Studio returned no embedding vector")
        return embedding

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.config.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Unable to reach LM Studio at {self.config.base_url}: {exc}"
            ) from exc


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def build_market_snapshot(exchange_state: dict[str, Any]) -> dict[str, Any]:
    """Convert live engine state into a compact snapshot for prompting."""
    book = exchange_state.get("book", {})
    agents = exchange_state.get("agents", [])
    fills = exchange_state.get("fills", [])
    latency = exchange_state.get("latency", {})

    return {
        "step": exchange_state.get("step"),
        "mid": book.get("mid"),
        "spread": book.get("spread"),
        "bid_depth": book.get("bid_depth"),
        "ask_depth": book.get("ask_depth"),
        "recent_fills": fills[-10:],
        "agent_count": len(agents),
        "agent_pnl": [
            {
                "name": agent.get("name"),
                "pnl": agent.get("pnl"),
                "inventory": agent.get("inventory"),
                "fills": agent.get("fills"),
            }
            for agent in agents
        ],
        "latency": latency,
    }


def regime_text(snapshot: dict[str, Any]) -> str:
    """Turn a market snapshot into a compact embedding-friendly description."""
    recent_fills = snapshot.get("recent_fills", [])
    agent_pnl = snapshot.get("agent_pnl", [])
    latency = snapshot.get("latency") or {}
    top_agent = max(agent_pnl, key=lambda item: item.get("pnl", 0), default=None)
    return (
        f"step={snapshot.get('step')} "
        f"mid={snapshot.get('mid')} "
        f"spread={snapshot.get('spread')} "
        f"bid_depth={snapshot.get('bid_depth')} "
        f"ask_depth={snapshot.get('ask_depth')} "
        f"fills={len(recent_fills)} "
        f"agent_count={snapshot.get('agent_count')} "
        f"top_agent={top_agent.get('name') if top_agent else 'n/a'} "
        f"top_pnl={top_agent.get('pnl') if top_agent else 'n/a'} "
        f"latency_p95={latency.get('p95', 'n/a')} "
        f"latency_p99={latency.get('p99', 'n/a')}"
    )


def generate_strategy_plan(client: LMStudioClient, exchange_state: dict[str, Any]) -> str:
    snapshot = build_market_snapshot(exchange_state)
    return client.chat(
        system=(
            "You are a trading strategy planner for an exchange simulator. "
            "Produce concise, practical strategy guidance in bullets with risk notes."
        ),
        user=(
            "Based on this live market snapshot, propose the next strategy plan.\n\n"
            f"Snapshot:\n{json.dumps(snapshot, indent=2)}"
        ),
    )


def generate_market_analysis_report(client: LMStudioClient, exchange_state: dict[str, Any]) -> str:
    snapshot = build_market_snapshot(exchange_state)
    return client.chat(
        system=(
            "You are a market analyst. Summarize live microstructure, trade flow, "
            "and notable anomalies in a short report."
        ),
        user=(
            "Write a market analysis report for this simulator state.\n"
            "Focus on trend, liquidity, volatility, and agent behavior.\n\n"
            f"Snapshot:\n{json.dumps(snapshot, indent=2)}"
        ),
    )


def generate_simulation_result_summary(client: LMStudioClient, results: dict[str, Any]) -> str:
    return client.chat(
        system=(
            "You are a simulation results calculator. Summarize performance clearly "
            "and include the main takeaways and any cautions."
        ),
        user=(
            "Summarize these simulation results and explain what they mean.\n\n"
            f"Results:\n{json.dumps(results, indent=2)}"
        ),
    )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def embed_regime(client: LMStudioClient, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Create an embedding record for a regime snapshot."""
    description = regime_text(snapshot)
    return {
        "step": snapshot.get("step"),
        "description": description,
        "snapshot": snapshot,
        "embedding": client.embed(description),
    }


def find_similar_regimes(
    client: LMStudioClient,
    current_snapshot: dict[str, Any],
    archive: list[dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Compare the current regime with archived past regimes using embeddings."""
    if not archive:
        return []

    current_embedding = client.embed(regime_text(current_snapshot))
    scored = []
    for item in archive:
        if item.get("step") == current_snapshot.get("step"):
            continue
        score = cosine_similarity(current_embedding, item.get("embedding", []))
        scored.append({
            "step": item.get("step"),
            "score": round(score, 4),
            "description": item.get("description"),
            "snapshot": item.get("snapshot", {}),
        })
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def archive_regime_snapshot(
    client: LMStudioClient,
    archive: list[dict[str, Any]],
    snapshot: dict[str, Any],
    max_items: int = 80,
) -> dict[str, Any]:
    """Embed and store a regime snapshot, keeping the archive bounded."""
    item = embed_regime(client, snapshot)
    archive.append(item)
    if len(archive) > max_items:
        del archive[:-max_items]
    return item


def simulation_summary_metrics(exchange_state: dict[str, Any]) -> dict[str, Any]:
    """Compute deterministic summary numbers before sending them to the model."""
    book = exchange_state.get("book", {})
    latency = exchange_state.get("latency") or {}
    agents = exchange_state.get("agents", [])
    pnl_values = [a.get("pnl", 0) for a in agents]
    return {
        "step": exchange_state.get("step", 0),
        "mid": book.get("mid"),
        "spread": book.get("spread"),
        "agent_count": len(agents),
        "total_pnl": sum(pnl_values),
        "best_pnl": max(pnl_values) if pnl_values else 0,
        "worst_pnl": min(pnl_values) if pnl_values else 0,
        "latency_p50": latency.get("p50"),
        "latency_p95": latency.get("p95"),
        "latency_p99": latency.get("p99"),
    }
