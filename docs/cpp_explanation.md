# C++ Matching Engine Explanation

## 1. Interview summary

> “The C++20 core is an in-memory price-time-priority matching engine. A price is a signed 64-bit fixed-point integer and quantity is an unsigned 32-bit integer. Each order book keeps bid price levels descending and ask levels ascending in `std::map`; each level is a FIFO intrusive doubly linked list, while an order-ID hash map makes cancellation locate the node directly. The matching engine crosses incoming orders against the opposite best price, generates fills at the resting maker price, and supports market, limit, IOC/FOK, iceberg, stop, pegged and auction-phase behavior. Python bindings and a versioned binary codec integrate it with services and feed tools.”

Describe only measured throughput numbers from the project’s benchmark outputs and name the machine/compiler/build mode. Do not infer latency from data-structure complexity alone.

## 2. Core source map

- `engine/src/types.hpp`: fixed-width aliases, `Order`, `Fill`, enums, phases and result types.
- `engine/src/order_book.hpp/.cpp`: sorted price levels, FIFO queues, order-ID lookup and cancellation.
- `engine/src/matching_engine.hpp/.cpp`: order validation/dispatch, crossing, TIF behavior, iceberg, stop, pegged and auction handling.
- `engine/src/allocators.hpp`: arena, slab allocator and placement-new object pool.
- `engine/src/memory_pool.hpp`: fixed-capacity raw slot pool implementation.
- `engine/src/binary_protocol.hpp`: explicit versioned little-endian order/fill frame codec.
- `engine/src/multi_asset_engine.hpp/.cpp`: one matching engine per symbol and parallel batches across independent symbols.
- `engine/src/ring_buffer.hpp`: bounded SPSC ring buffer.
- `engine/tests/`: GoogleTest unit, behavior, protocol, stress and fuzz-style tests.
- `engine/bench/`: Google Benchmark targets for matching and order book.
- `bindings/`: Python integration to the C++ library.

Build uses CMake and C++20. GoogleTest and Google Benchmark are wired through CMake `FetchContent`; offline builds need those dependencies already available or a configured cache/vendor strategy.

## 3. Price-time-priority order book

`OrderBook` stores:

- `bids_`: `std::map<Price, PriceLevel, std::greater<Price>>`, so `begin()` is best (highest) bid.
- `asks_`: `std::map<Price, PriceLevel, std::less<Price>>`, so `begin()` is best (lowest) ask.
- Each `PriceLevel` stores aggregate remaining quantity, order count, and head/tail of an intrusive FIFO list.
- `order_map_` maps `OrderId` to side, price, and direct `OrderNode*` for cancellation.
- `ObjectPool<OrderNode>` recycles order nodes.

New same-price orders append to the tail, preserving time priority. Removing a known order is average O(1) hash lookup + O(1) list removal, plus O(log P) map lookup/removal when a price level becomes empty; adding a new price level is O(log P), while appending at an existing level is O(1) after locating the map key. Matching walks best price levels and FIFO orders until no crossing quantity remains. Be precise: total cost is proportional to price-level/order nodes visited plus map operations, not simply O(1).

An incoming buy crosses the best ask while its limit allows; a sell crosses the best bid. Fill price is the maker/resting order’s price. Both orders’ filled quantity and aggregate level quantity are updated. Fully consumed resting nodes are removed. A market order walks available contra liquidity and does not rest. A limit remainder can rest on its own side.

## 4. Order types and edge cases

- **Limit:** execute at prices no worse than the limit, then rest any permitted remainder.
- **Market:** execute against available opposite liquidity; remaining quantity does not become a limit order.
- **IOC:** execute immediately; cancel leftover quantity rather than resting it.
- **FOK:** pre-check available eligible quantity and only proceed if the full requested quantity is available. Recheck assumptions if concurrency ever allows book mutation between precheck and match; current engine ownership should serialize per book.
- **Iceberg:** only a visible slice is placed on the book. When that slice fills, a refill is inserted at the back of the price queue, so it loses time priority relative to orders already queued at that level.
- **Stop:** stored dormant until the last-trade trigger condition is met, then transformed into an executable order. Triggered fills can cascade into more triggers, so implementation loops until no more stops fire.
- **Pegged:** price is recalculated relative to best bid/ask with offset and crossing caps; repricing can remove/reinsert and affects queue priority.
- **Stop-limit:** enum exists in the type model; inspect and verify the current path before claiming full semantics in a production interview. Source comments indicate this behavior is future work.
- **Auction:** pre-open accepts without continuous matching; uncross evaluates candidate prices for max executable quantity and tie-breaks on lower imbalance, then returns to continuous phase.

Follow-up discussion should cover malformed orders (zero quantity, invalid side/type, extreme prices), duplicate IDs, overflow in aggregate quantities, and behavior when the pool is exhausted. Those are useful correctness review topics, even where validation is currently at a higher layer.

## 5. Memory and cache behavior

`OrderNode` and `PriceLevel` are cache-line aligned. The order book’s pool avoids one general-heap allocation per resting order and improves locality/reuse. `ObjectPool<T>` obtains slabs through `SlabAllocator<T>` backed by an arena; placement new constructs nodes and `destroy` runs the destructor before recycling the slot. The pool still has capacity/allocation failure and lifetime correctness concerns. Measure allocation and cache effects rather than saying “zero allocation”: maps, hash maps, vectors of fills, stop/peg vectors, and slab growth can allocate.

`SpscRingBuffer<T, Capacity>` uses atomic head/tail with acquire/release ordering and raw aligned storage. Its contract is **single producer, single consumer**; it is not a general MPMC queue. It leaves one slot empty to distinguish full from empty, so usable capacity is `Capacity - 1`. Consumers must honor `try_push` failure and define backpressure/drop behavior.

## 6. Multi-symbol concurrency

`MultiAssetEngine` owns a map from symbol ID to `MatchingEngine`. Orders for different symbols/books can be processed in parallel by `submit_parallel`; operations on the same order book must remain serialized to preserve price-time priority and avoid data races. Explain how worker tasks are partitioned by symbol. The shared routing map from order ID to symbol also needs synchronization if concurrent submit/cancel access is introduced; do not state that the entire class is automatically thread-safe without verifying locking and call contracts.

The mobile Python backend currently uses a shared in-process engine integration. That is suitable for a simulator/demo but does not make a horizontally scaled API cluster share one authoritative book. A production design would route each symbol to one engine owner and publish ordered, durable events.

## 7. Binary protocol

`BinaryProtocol` manually appends/reads fixed-width integer fields in little-endian order. Frames begin with protocol version and message type; order and fill have fixed sizes, and reserved bytes allow future extension. Encoding avoids transmitting native struct padding or host endianness. Decoders reject wrong frame size, version, and message type.

The codec currently demonstrates order submit and fill frames; enum ranges, semantic validity, maximum frame size, and forward/backward version negotiation must also be checked at the receiving boundary. TCP is a byte stream, so production readers must frame incomplete/coalesced reads rather than assume one `read()` equals one message. Authentication, integrity, encryption and replay policy are transport responsibilities, not supplied merely by the binary format.

## 8. Python and iOS integration story

The Python binding exposes engine operations to service/simulation code. FastAPI validates mobile REST requests, maps integer tick DTOs into engine `Order` values, serializes access to the engine, persists fills/positions in PostgreSQL, and emits WebSocket JSON events. The feed bridge and binary codec address a separate engine/feed integration path. The iOS app does not link C++ directly: it uses versioned REST for commands/snapshots and WebSocket for market and execution events. This keeps engine ABI and matching code out of the mobile binary.

The money invariant is end-to-end: C++ `Price` is `int64_t` fixed point at scale 10,000; quantity is integer. Python schemas/DB columns and Swift DTOs preserve integer values. Formatting or input parsing happens at UI boundaries. Never compute order price in binary floating point.

## 9. Test strategy and likely grilling questions

The engine test suite includes order book behavior, matching, TIF, iceberg, stop, pegged, auctions, binary protocol, memory pool, multi-asset behavior, stress and fuzz-oriented cases. Explain invariant tests: total level quantity equals sum of resting leaves; FIFO ordering within a price; best bid/ask ordering; no fill at an impermissible limit; both fill quantities agree; no negative remainder; cancel removes exactly one live order.

**Why `std::map`?** It keeps prices ordered and makes the best level available at begin; add/remove price levels cost logarithmic time. A tree is simpler and flexible but may have poorer cache locality than a dense/tick-indexed structure. Benchmark alternatives before replacing it.

**Why linked FIFO levels?** O(1) insertion at tail/removal of a known node and direct cancellation lookup preserve queue order. The cost is pointer chasing and per-node bookkeeping; pooling reduces but does not eliminate locality costs.

**Why maker price?** The resting order set the quote and receives price priority; the incoming taker accepts that available price. Be ready to state the simulator’s policy and note that exchange rules vary.

**How does FOK avoid partial fills?** Check eligible contra quantity before mutation, then execute atomically with respect to that book. If multiple threads can mutate the same book, guard the check+match as one serialized operation.

**What does the ring buffer guarantee?** Bounded SPSC transport with acquire/release publication; not wait-free for arbitrary work and not safe for multiple producers/consumers.

**Where is the performance evidence?** Benchmarks live under `engine/bench`. Report measured benchmark results only with hardware, compiler, optimization level, workload, warm-up, and repetitions. Do not equate a microbenchmark with end-to-end service latency.

## 10. Useful commands

```powershell
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

Useful files to open during a code walkthrough: `types.hpp`, `order_book.hpp/.cpp`, `matching_engine.cpp`, `binary_protocol.hpp`, `multi_asset_engine.cpp`, and the corresponding tests.
