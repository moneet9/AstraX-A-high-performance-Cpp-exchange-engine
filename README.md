# AstraX

**Author:** moneet

A high-performance C++ exchange engine.

AstraX is a fast exchange simulator written in C++ with a Python dashboard, live market replay, and optional AI analysis through a local LM Studio server.

It is designed to help you:

- Match buy and sell orders quickly
- Watch the order book and trades update in real time
- Replay market data into the simulator
- Inspect agent behavior, latency, and fills
- Compare the current market regime with similar past conditions using embeddings

---

## What This Project Does

At its core, AstraX simulates a trading exchange:

- Traders submit orders
- The matching engine pairs orders using price-time priority
- The system records trades, prices, depth, and latency
- A dashboard shows what is happening as the simulation runs

On top of that, the dashboard can use a local language model to:

- Write a strategy plan from the current market snapshot
- Summarize the current market state
- Summarize simulation results
- Turn recent market conditions into embeddings and compare them with archived regimes

In simple terms, embeddings let the simulator describe the current market in a compact numeric form, then search for older market snapshots that "feel similar" by measuring closeness between those vectors.

---

## Embeddings And Regime Comparison

This project includes helpers in `dashboard/server/ai.py` that:

1. Convert a live market snapshot into a short text description
2. Send that text to the local embedding model in LM Studio
3. Save the resulting vector with the snapshot
4. Compare the current regime with past archived regimes using cosine similarity
5. Return the most similar historical conditions

This is useful when you want to answer questions like:

- "Have we seen this kind of spread and depth before?"
- "What happened last time liquidity looked like this?"
- "Which older regime is most similar to the current one?"

The dashboard now archives regimes automatically while it runs, and the live UI can ask for the closest historical matches on demand.

---

## What This Project Already Has

The codebase already includes a lot of the systems-programming pieces you asked about:

- Arena, slab, and object-pool allocators in `engine/src/allocators.hpp`
- Cache-aware `alignas(64)` data types for hot order-book structures
- Intrusive order lists inside each price level
- A lock-free single-producer/single-consumer ring buffer in `engine/src/ring_buffer.hpp`
- Multi-asset parallel submission for independent symbols
- Google Benchmark targets in `engine/bench/`
- Profiling scripts through `profile.sh` and `profile.ps1`
- Randomized stress and fuzz-style tests in `engine/tests/`

What is still worth adding later, if you want to push AstraX further as an interview project:

- A deeper cache-line redesign of the full book structure
- True multi-threaded matching within a single symbol
- Larger benchmark suites and longer perf runs
- More exhaustive fuzzing across all order types and cancel paths

---

## Features

- Price-time priority matching
- Supports:
  - Limit orders
  - Market orders
  - Iceberg orders
  - Stop orders
  - Pegged orders
- Custom memory allocator for lower overhead
- Cache-friendly order book layout
- Binary TCP market data feed
- Live dashboard showing:
  - Prices
  - Trades
  - Latency
  - Trading agent activity
- Optional LM Studio integration for:
  - Strategy planning
  - Market analysis reports
  - Simulation summaries
  - Embedding-based regime similarity

---

## Project Layout

```text
engine/       C++ matching engine and order book
bindings/     Python bindings
agents/       Example trading agents
data/         Replay data, generators, and TCP feeder
dashboard/    Live web dashboard and AI helpers
tests/        Python test suite
```

---

## Quick Start

### 1) Build the C++ engine

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

### 2) Run the C++ tests

```bash
ctest --test-dir build --output-on-failure
```

### 3) Run the Python tests

```bash
PYTHONPATH=build/bindings:. python3 -m pytest tests/ -v
```

### 4) Start the dashboard backend

```bash
PYTHONPATH=build/bindings:. python3 dashboard/server/app.py
```

### 5) Start the dashboard frontend

```bash
cd dashboard/frontend
npm install
npm run dev
```

### 6) Stream replay data

```bash
PYTHONPATH=build/bindings:. python3 -m data.tcp_feeder --source path/to/lobster.csv
```

---

## LM Studio Setup

AstraX can connect to a local LM Studio server for analysis and embedding generation.

Set these environment variables before starting the dashboard backend:

```bash
LM_STUDIO_BASE_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=qwen/qwen3-4b-2507
LM_STUDIO_EMBED_MODEL=nomic-embed-text
```

If LM Studio is not running, the simulator still works. Only the AI analysis features will be unavailable.

---

## How The Dashboard Uses AI

The dashboard can request:

- A strategy plan based on the current exchange snapshot
- A market report about the live book, trade flow, and latency
- A simulation summary for the current run

The AI helpers are implemented in `dashboard/server/ai.py`, and the live server is in `dashboard/server/app.py`.

---

## Python Example

```python
import exchange_simulator as ex

engine = ex.MatchingEngine()

order = ex.Order()
order.id = 1
order.side = ex.Side.Buy
order.price = 10000
order.quantity = 10
order.type = ex.OrderType.Limit
order.tif = ex.TimeInForce.GTC
order.timestamp = 1

engine.submit(order)
```

---

## If You Are New Here

The easiest way to understand AstraX is:

1. Start the engine
2. Start the dashboard
3. Watch orders enter the book and trades appear
4. Turn on LM Studio if you want written analysis
5. Add archived regime snapshots if you want historical similarity search

---

## Goals

- Fast order matching
- Low memory usage
- Better cache locality
- Easy benchmarking
- Real-time market visualization
- Simple AI-assisted market analysis
