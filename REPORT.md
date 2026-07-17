# AstraX Project Report

## 1. Project Overview

AstraX is a high-performance C++ exchange engine with a live Python dashboard, replay tools, and optional local AI analysis.

The core idea is simple:

- Incoming orders are submitted to a matching engine.
- The engine applies exchange rules such as price-time priority.
- Trades are generated when buy and sell orders cross.
- The dashboard streams live state so you can observe price, spread, fills, latency, and agent behavior.
- Optional LM Studio integration can summarize the market and compare current regimes with archived historical conditions using embeddings.

This makes AstraX useful both as a trading-system simulator and as an interview project that demonstrates systems programming, memory management, performance thinking, testing, and basic AI integration.

---

## 2. Main Technologies Used

### C++

C++ is the primary language for the exchange engine.

Why C++:

- It gives low-level control over memory layout and performance.
- It is the most relevant language for exchange-engine and low-latency systems interviews.
- It supports value types, custom allocators, intrusive structures, atomics, and predictable runtime behavior.
- It allows the project to demonstrate cache locality, allocation strategy, and algorithmic efficiency.

### Python

Python is used for:

- Dashboard server logic
- Replay and analysis glue
- Testing and simulation helpers
- LM Studio client integration

Why Python:

- It is fast to iterate with.
- It makes the dashboard and analysis workflows easier to build.
- It is a good companion language for a C++ core because it lets you script, inspect, and visualize engine behavior quickly.

### JavaScript / React

The live dashboard frontend uses React.

Why React:

- It is a common choice for live data dashboards.
- It makes it easy to show streaming market state.
- It works well with WebSocket-based updates.

### CMake

CMake is used to build the C++ engine and tests.

Why CMake:

- It is standard in C++ projects.
- It supports portable builds and third-party dependencies.
- It allows separate build targets for engine, tests, and benchmarks.

### GoogleTest and Google Benchmark

GoogleTest is used for unit and stress tests.
Google Benchmark is used for performance benchmarks.

Why these tools:

- They are common in production C++ codebases.
- They help demonstrate discipline around correctness and performance measurement.
- They are recognizable to interviewers.

### LM Studio

LM Studio is used as a local OpenAI-compatible model server.

Why LM Studio:

- It keeps AI analysis local.
- It avoids depending on external hosted APIs.
- It gives the project a modern analysis layer without making the core engine dependent on cloud services.

---

## 3. How the System Works

### 3.1 Order Flow

1. A trader or agent creates an order.
2. The order is sent to `MatchingEngine`.
3. The matching engine checks the book.
4. If prices cross, fills are created immediately.
5. If not, the order is stored in the order book.
6. The dashboard receives updated state through WebSocket messages.

### 3.2 Matching Logic

The engine uses price-time priority:

- Better price wins first.
- If two orders have the same price, the older one gets priority.

This is the standard exchange rule and is important for interview discussion because it shows you understand fairness and market microstructure.

### 3.3 Order Book Structure

The order book keeps bids and asks separated.

For each price level:

- Orders are kept in intrusive linked lists.
- The book tracks total quantity at that level.
- Best bid and best ask are always available for fast top-of-book access.

### 3.4 Allocation Strategy

The engine includes custom memory management:

- Arena allocator
- Slab allocator
- Object pool
- Memory pool for reusable storage

The goal is to reduce heap churn and make object lifetime more predictable.

### 3.5 Concurrency and Multi-Asset Support

AstraX includes multi-asset support so different symbols can be handled independently.

It also includes a lock-free SPSC ring buffer for producer/consumer style messaging.

Important note:

- The project has parallel support for independent symbols.
- It does not yet implement fully multi-threaded matching inside a single symbol book.

That distinction matters in interviews.

### 3.6 Profiling and Testing

The project includes:

- Unit tests
- Stress-style randomized tests
- Benchmark targets
- Profiling scripts for performance runs

This makes the project more credible because it is not just an algorithm demo.

### 3.7 Dashboard and AI Layer

The dashboard shows:

- Order book
- Trades
- Price chart
- Agent activity
- Latency statistics
- AI analysis output
- Embedding-based regime similarity results

The AI layer is optional. If the local model server is offline, the exchange still runs.

---

## 4. Why These Choices Were Made

### Why not just use Python for the engine?

Because the project is meant to demonstrate low-latency systems thinking.

Python is great for orchestration and UI, but it is not the best choice for:

- Tight memory control
- Cache-aware structures
- Micro-optimization
- Latency-sensitive matching logic

### Why not use a database-backed order book?

Because a live exchange engine must keep the hot path in memory.

Databases are useful for persistence and analytics, but they are too slow for the matching path itself.

### Why not use `std::list` for orders?

Because `std::list` allocates a node per element and tends to hurt locality.

The intrusive approach used here:

- Reduces allocation overhead
- Improves cache locality
- Makes cancellation and relinking more efficient

### Why not use a general-purpose queue instead of an SPSC ring buffer?

Because single-producer/single-consumer ring buffers are simpler and faster for the specific communication pattern they target.

They also give a good interview opportunity to discuss:

- Atomics
- Acquire/release memory ordering
- Lock-free design

### Why not use an external cloud AI service?

Because LM Studio keeps the AI analysis local, private, and easy to run offline.

That also makes the project easier to demo in an interview environment.

### Why not over-focus on the dashboard?

Because interviewers for C++ exchange-engine roles usually care more about:

- Matching correctness
- Memory layout
- Latency
- Concurrency
- Benchmarks
- Tests

The dashboard is useful, but it should support the engine rather than distract from it.

---

## 5. Interview Notes: How To Explain Each Technology

### C++

What it shows:

- Low-level control
- Performance awareness
- Memory discipline
- Strong understanding of data structures

What to say in an interview:

- “I used C++ because the engine needs predictable performance and careful memory control.”
- “The code emphasizes data locality and allocation strategy.”
- “I chose C++ so I could talk about cache lines, intrusive structures, and benchmark-driven optimization.”

### Custom Allocators

What it shows:

- You understand heap overhead
- You can design reusable object storage
- You think about allocation patterns, not just algorithms

What to say:

- “I introduced custom allocators to reduce heap churn in the hot path.”
- “The goal was to keep object creation predictable and improve locality.”

### Intrusive Lists

What it shows:

- You understand how production order books avoid extra indirection
- You know the tradeoff between convenience and performance

What to say:

- “I used intrusive structures so order nodes live inside the book rather than in separate list nodes.”
- “That reduces memory overhead and improves cache behavior.”

### SPSC Ring Buffer

What it shows:

- You understand lock-free patterns
- You can reason about atomic ordering
- You know when a simpler concurrency model is enough

What to say:

- “I used an SPSC ring buffer where the communication pattern is one producer and one consumer.”
- “That lets me avoid mutex overhead on the hot path.”

### Google Benchmark

What it shows:

- You measure performance instead of guessing
- You understand the difference between correctness and optimization

What to say:

- “I added benchmarks so I could compare changes objectively.”
- “That helped me validate that the engine changes actually improved performance.”

### Stress and Fuzz Tests

What it shows:

- You care about edge cases
- You test beyond the happy path
- You think like a systems engineer

What to say:

- “I added randomized stress coverage to catch subtle order-book invariants.”
- “This helps protect against regressions in cancellation and matching logic.”

### LM Studio

What it shows:

- You can integrate modern tooling without compromising the core engine
- You know how to keep optional features isolated

What to say:

- “The AI layer is optional and local.”
- “It runs separately from the matching path, so it does not interfere with engine correctness or latency.”

---

## 6. Alternative Approaches And Why They Were Not Chosen

### Alternative: Standard containers everywhere

Rejected because:

- They are convenient but not always optimal for exchange hot paths.
- They hide allocation costs.
- They do not demonstrate low-level systems skill as strongly.

### Alternative: `std::list` for order queues

Rejected because:

- It is easy to use but allocates per node.
- It has poorer cache locality.
- It is not the strongest design for interview discussion.

### Alternative: One giant monolithic engine with no Python layer

Rejected because:

- It would be harder to demo visually.
- The dashboard and replay tools make the project easier to understand.
- Python is useful for orchestration without affecting the C++ core design.

### Alternative: Cloud-hosted AI APIs

Rejected because:

- They add cost and network dependency.
- They make demos less self-contained.
- Local LM Studio keeps the project reproducible.

### Alternative: Focus mainly on RL or deep learning

Rejected because:

- The strongest story for this project is exchange-engine engineering.
- Most systems interviewers will care more about the matching engine than the ML layer.

---

## 7. Current Feature Status

### Already implemented

- C++ matching engine
- Price-time priority matching
- Order book
- Iceberg, stop, pegged, market, limit, IOC, and FOK behaviors
- Custom allocators
- Intrusive order-level structure
- Ring buffer
- Multi-asset support
- Benchmarks
- Unit tests
- Stress tests
- Replay feeder
- Python bindings
- React dashboard
- Optional LM Studio analysis
- Embedding-based regime similarity

### Still future work

- Full multi-threaded matching inside one symbol
- A more aggressive cache-line redesign of the entire book
- Expanded profiling automation across many workloads
- Larger fuzzing coverage across every order type and failure path

---

## 8. Short Interview Summary

If you need a 30-second explanation:

> AstraX is a high-performance C++ exchange engine with Python and React tooling around it. The main focus is low-latency order matching, custom memory management, intrusive order-book data structures, benchmarks, and tests. I also added a local LM Studio analysis layer so the dashboard can summarize live market conditions and compare the current regime to similar past regimes using embeddings.

If you want a 2-minute explanation:

> I built AstraX as a realistic exchange simulator to demonstrate systems programming skills. The hot path is in C++, where the engine uses price-time priority, custom allocators, intrusive order lists, and cache-aware structures. I added Google Benchmark targets and randomized stress tests so performance and correctness can be measured, not guessed. On top of that, I built a Python dashboard and WebSocket server for live visibility, plus optional local LM Studio integration for strategy reports and embedding-based regime similarity. The AI layer is optional, so it does not interfere with the engine’s core matching behavior.

