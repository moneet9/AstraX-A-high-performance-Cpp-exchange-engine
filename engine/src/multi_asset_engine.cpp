// engine/src/multi_asset_engine.cpp
#include "multi_asset_engine.hpp"

#include <algorithm>
#include <future>

namespace {
using exsim::Order;
using exsim::SpscRingBuffer;
using exsim::MultiAssetEngine;
}

namespace exsim {

MatchingEngine& MultiAssetEngine::get_book(uint32_t symbol_id) {
    auto [it, _] = books_.try_emplace(symbol_id);
    return it->second;
}

std::vector<Fill> MultiAssetEngine::submit(uint32_t symbol_id, Order& order) {
    order_to_symbol_[order.id] = symbol_id;
    auto& engine = get_book(symbol_id);
    return engine.submit(order);
}

std::vector<MultiAssetEngine::SymbolBatchResult> MultiAssetEngine::submit_parallel(const std::vector<SymbolOrder>& orders) {
    std::unordered_map<uint32_t, std::vector<Order>> grouped_orders;
    grouped_orders.reserve(orders.size());

    for (const auto& entry : orders) {
        order_to_symbol_[entry.order.id] = entry.symbol_id;
        grouped_orders[entry.symbol_id].push_back(entry.order);
    }

    std::vector<std::future<SymbolBatchResult>> futures;
    futures.reserve(grouped_orders.size());

    for (auto& [symbol_id, symbol_orders] : grouped_orders) {
        auto& engine = get_book(symbol_id);
        futures.push_back(std::async(std::launch::async, [symbol_id, &engine, orders = std::move(symbol_orders)]() mutable {
            SpscRingBuffer<Order, 1024> queue;

            SymbolBatchResult result{symbol_id, {}};
            result.fills.reserve(orders.size() * 2);

            std::size_t index = 0;
            Order next{};
            while (index < orders.size()) {
                while (index < orders.size() && queue.try_push(std::move(orders[index]))) {
                    ++index;
                }

                while (queue.try_pop(next)) {
                    auto fills = engine.submit(next);
                    result.fills.insert(result.fills.end(), fills.begin(), fills.end());
                }
            }

            while (queue.try_pop(next)) {
                auto fills = engine.submit(next);
                result.fills.insert(result.fills.end(), fills.begin(), fills.end());
            }

            return result;
        }));
    }

    std::vector<SymbolBatchResult> results;
    results.reserve(futures.size());
    for (auto& future : futures) {
        results.push_back(future.get());
    }
    return results;
}

CancelResult MultiAssetEngine::cancel(uint64_t order_id) {
    auto it = order_to_symbol_.find(order_id);
    if (it == order_to_symbol_.end()) {
        return CancelResult::OrderNotFound;
    }
    uint32_t symbol_id = it->second;
    auto book_it = books_.find(symbol_id);
    if (book_it == books_.end()) {
        return CancelResult::OrderNotFound;
    }
    return book_it->second.cancel(order_id);
}

std::vector<uint32_t> MultiAssetEngine::symbols() const {
    std::vector<uint32_t> result;
    result.reserve(books_.size());
    for (const auto& [id, _] : books_) {
        result.push_back(id);
    }
    return result;
}

} // namespace exsim

// AstraX repo sync
