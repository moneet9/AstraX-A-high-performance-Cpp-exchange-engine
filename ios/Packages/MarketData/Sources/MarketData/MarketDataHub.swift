import Core
import Foundation
import Networking
import os

public actor MarketDataHub {
    private let api: APIClient
    private let store: OrderBookStore
    private var socket: URLSessionWebSocketTask?
    private var reader: Task<Void, Never>?
    private var reconnectTask: Task<Void, Never>?
    private var continuations: [UUID: AsyncStream<MarketBook>.Continuation] = [:]
    private var executionContinuations: [UUID: AsyncStream<PrivateExecutionEvent>.Continuation] = [:]
    private var latest: MarketBook?
    private var stopped = true
    private var currentSymbol = "ASTR"
    private var reconnectAttempt = 0
    private var lastPublishedAt: Int64 = 0
    private var consumers: Set<UUID> = []
    private let signposter = OSSignposter(subsystem: "com.astrax.paper-trading", category: "MarketData")

    public init(api: APIClient, store: OrderBookStore = OrderBookStore()) {
        self.api = api
        self.store = store
    }

    public func updates() -> AsyncStream<MarketBook> {
        let id = UUID()
        let pair = AsyncStream<MarketBook>.makeStream(bufferingPolicy: .bufferingNewest(1))
        continuations[id] = pair.continuation
        if let latest { pair.continuation.yield(latest) }
        pair.continuation.onTermination = { @Sendable [weak self] _ in
            Task { await self?.removeContinuation(id) }
        }
        return pair.stream
    }

    public func executionUpdates() -> AsyncStream<PrivateExecutionEvent> {
        let id = UUID()
        // Fill events are state-changing commands; never discard older fills when a
        // consumer is briefly busy. The orders screen reconciles with REST on resume.
        let pair = AsyncStream<PrivateExecutionEvent>.makeStream(bufferingPolicy: .unbounded)
        executionContinuations[id] = pair.continuation
        pair.continuation.onTermination = { @Sendable [weak self] _ in
            Task { await self?.removeExecutionContinuation(id) }
        }
        return pair.stream
    }

    public func connect(symbol: String = "ASTR", consumerID: UUID) async {
        let isNew = consumers.insert(consumerID).inserted
        currentSymbol = symbol.uppercased()
        guard isNew || socket == nil else { return }
        stopped = true
        reconnectTask?.cancel()
        reconnectTask = nil
        await stopSocket()
        stopped = false
        await openSocket()
    }

    public func disconnect(consumerID: UUID) async {
        consumers.remove(consumerID)
        guard consumers.isEmpty else { return }
        stopped = true
        reconnectTask?.cancel()
        reconnectTask = nil
        await stopSocket()
    }

    private func openSocket() async {
        guard !stopped else { return }
        do {
            try await api.refreshSession()
        } catch {
            // Existing valid access token may still be usable after a transient refresh error.
        }
        guard let token = await api.bearerToken() else {
            scheduleReconnect()
            return
        }
        let task = await api.makeWebSocketTask(path: "/v1/market")
        socket = task
        task.resume()
        do {
            let auth = try JSONSerialization.data(withJSONObject: ["type": "auth", "token": token])
            try await task.send(.data(auth))
            let subscription = try JSONSerialization.data(withJSONObject: ["type": "subscribe", "symbol": currentSymbol])
            try await task.send(.data(subscription))
            reconnectAttempt = 0
            reader = Task { [weak self] in await self?.readLoop(task) }
        } catch {
            await stopSocket()
            scheduleReconnect()
        }
    }

    private func readLoop(_ task: URLSessionWebSocketTask) async {
        do {
            while !Task.isCancelled, !stopped {
                let message = try await task.receive()
                let data: Data
                switch message {
                case .data(let bytes): data = bytes
                case .string(let text): data = Data(text.utf8)
                @unknown default: continue
                }
                await consume(data)
            }
        } catch {
            guard !stopped else { return }
            await stopSocket()
            scheduleReconnect()
        }
    }

    private func consume(_ data: Data) async {
        let interval = signposter.beginInterval("MarketData decode to view model")
        defer { signposter.endInterval("MarketData decode to view model", interval) }
        if let event = try? JSONDecoder().decode(PrivateExecutionEvent.self, from: data), event.type == "execution" {
            executionContinuations.values.forEach { $0.yield(event) }
            return
        }
        guard let frame = try? JSONDecoder().decode(BookSnapshotDTO.self, from: data),
              frame.type == "book", frame.symbol == currentSymbol else { return }
        let book = MarketBook(symbol: frame.symbol, sequence: frame.sequence,
                              bids: frame.bids.compactMap { $0.count >= 2 ? BookLevel(priceTicks: $0[0], quantity: $0[1]) : nil },
                              asks: frame.asks.compactMap { $0.count >= 2 ? BookLevel(priceTicks: $0[0], quantity: $0[1]) : nil },
                              receivedAtNanoseconds: Int64(Date().timeIntervalSince1970 * 1_000_000_000))
        let isSnapshot = frame.kind == "snapshot"
        guard await store.apply(book, isSnapshot: isSnapshot) else {
            await requestResync()
            return
        }
        latest = book
        let now = book.receivedAtNanoseconds
        guard now - lastPublishedAt >= 100_000_000 || isSnapshot else { return }
        lastPublishedAt = now
        continuations.values.forEach { $0.yield(book) }
    }

    private func requestResync() async {
        guard let socket else { return }
        if let message = try? JSONSerialization.data(withJSONObject: ["type": "resync", "symbol": currentSymbol]) {
            try? await socket.send(.data(message))
        }
    }

    private func scheduleReconnect() {
        guard !stopped, reconnectTask == nil else { return }
        reconnectAttempt += 1
        let ceiling = min(30_000, 500 * (1 << min(reconnectAttempt, 6)))
        let delay = Int.random(in: max(250, ceiling / 2)...ceiling)
        reconnectTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(delay))
            guard !Task.isCancelled else { return }
            await self?.reconnectNow()
        }
    }

    private func reconnectNow() async {
        reconnectTask = nil
        guard !stopped else { return }
        if let snapshot = try? await api.book(symbol: currentSymbol) {
            await consume(try? JSONEncoder().encode(snapshot) ?? Data())
        }
        await openSocket()
    }

    private func stopSocket() async {
        reader?.cancel()
        reader = nil
        socket?.cancel(with: .goingAway, reason: nil)
        socket = nil
    }

    private func removeContinuation(_ id: UUID) {
        continuations[id] = nil
    }

    private func removeExecutionContinuation(_ id: UUID) {
        executionContinuations[id] = nil
    }
}
