"""Tests for embedding-based regime comparison helpers."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.server.ai import (
    archive_regime_snapshot,
    cosine_similarity,
    embed_regime,
    find_similar_regimes,
)


class FakeClient:
    def __init__(self, embeddings):
        self.embeddings = list(embeddings)
        self.calls = []

    def embed(self, text):
        self.calls.append(text)
        if not self.embeddings:
            raise AssertionError("No more embeddings available")
        return self.embeddings.pop(0)


def test_cosine_similarity_handles_basic_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_embed_regime_returns_snapshot_and_embedding():
    client = FakeClient([[0.1, 0.2, 0.3]])
    snapshot = {
        "step": 12,
        "mid": 100,
        "spread": 2,
        "bid_depth": 8,
        "ask_depth": 7,
        "recent_fills": [{"price": 100, "quantity": 1}],
        "agent_count": 3,
        "agent_pnl": [{"name": "A", "pnl": 5, "inventory": 1, "fills": 2}],
        "latency": {"p95": 4, "p99": 6},
    }

    item = embed_regime(client, snapshot)

    assert item["step"] == 12
    assert item["snapshot"] == snapshot
    assert item["embedding"] == [0.1, 0.2, 0.3]
    assert "mid=100" in item["description"]
    assert len(client.calls) == 1


def test_find_similar_regimes_sorts_best_matches_first():
    client = FakeClient([
        [1.0, 0.0],  # current
        [1.0, 0.0],  # best archive match
        [0.0, 1.0],  # worst archive match
        [0.6, 0.8],  # middle archive match
    ])

    current_snapshot = {
        "step": 100,
        "mid": 101,
        "spread": 3,
        "bid_depth": 12,
        "ask_depth": 11,
        "recent_fills": [],
        "agent_count": 2,
        "agent_pnl": [],
        "latency": {"p95": 5, "p99": 8},
    }
    archive = [
        {
            "step": 20,
            "description": "best",
            "snapshot": {"step": 20},
            "embedding": [1.0, 0.0],
        },
        {
            "step": 40,
            "description": "worst",
            "snapshot": {"step": 40},
            "embedding": [0.0, 1.0],
        },
        {
            "step": 60,
            "description": "middle",
            "snapshot": {"step": 60},
            "embedding": [0.6, 0.8],
        },
    ]

    matches = find_similar_regimes(client, current_snapshot, archive, limit=3)

    assert [match["step"] for match in matches] == [20, 60, 40]
    assert matches[0]["score"] == 1.0
    assert matches[-1]["score"] == 0.0
    assert len(client.calls) == 1


def test_find_similar_regimes_skips_same_step():
    client = FakeClient([
        [1.0, 0.0],  # current
        [1.0, 0.0],  # same-step archive entry, should be skipped
        [0.0, 1.0],  # remaining archive entry
    ])

    current_snapshot = {
        "step": 100,
        "mid": 101,
        "spread": 3,
        "bid_depth": 12,
        "ask_depth": 11,
        "recent_fills": [],
        "agent_count": 2,
        "agent_pnl": [],
        "latency": {"p95": 5, "p99": 8},
    }
    archive = [
        {
            "step": 100,
            "description": "same-step",
            "snapshot": {"step": 100},
            "embedding": [1.0, 0.0],
        },
        {
            "step": 40,
            "description": "older",
            "snapshot": {"step": 40},
            "embedding": [0.0, 1.0],
        },
    ]

    matches = find_similar_regimes(client, current_snapshot, archive, limit=3)

    assert [match["step"] for match in matches] == [40]
    assert len(client.calls) == 1


def test_archive_regime_snapshot_keeps_archive_bounded():
    client = FakeClient([[0.1, 0.2]] * 10)
    archive = []

    for step in range(5):
        archive_regime_snapshot(
            client,
            archive,
            {
                "step": step,
                "mid": 100 + step,
                "spread": 2,
                "bid_depth": 10,
                "ask_depth": 9,
                "recent_fills": [],
                "agent_count": 1,
                "agent_pnl": [],
                "latency": {"p95": 1, "p99": 2},
            },
            max_items=3,
        )

    assert len(archive) == 3
    assert [item["step"] for item in archive] == [2, 3, 4]
