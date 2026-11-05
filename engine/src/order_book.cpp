// engine/src/order_book.cpp
#include "order_book.hpp"

namespace exsim {

bool OrderBook::add(const Order& order) {
    if (order.type != OrderType::Limit) return false;

    OrderNode* node = node_pool_.create(order);
    if (!node) {
        return false;
    }

    if (order.side == Side::Buy) {
        auto& level = bids_[order.price];
        if (level.order_count == 0) level.price = order.price;
        level.push_back(node);
        level.total_quantity += order.remaining();
        level.order_count++;
        order_map_[order.id] = {Side::Buy, order.price, node};
    } else {
        auto& level = asks_[order.price];
        if (level.order_count == 0) level.price = order.price;
        level.push_back(node);
        level.total_quantity += order.remaining();
        level.order_count++;
        order_map_[order.id] = {Side::Sell, order.price, node};
    }
    return true;
}

CancelResult OrderBook::cancel(OrderId id) {
    auto it = order_map_.find(id);
    if (it == order_map_.end()) return CancelResult::OrderNotFound;

    auto& loc = it->second;
    Quantity remaining = loc.node->order.remaining();

    if (loc.side == Side::Buy) {
        auto level_it = bids_.find(loc.price);
        level_it->second.total_quantity -= remaining;
        level_it->second.order_count--;
        level_it->second.erase(loc.node);
        if (level_it->second.empty()) bids_.erase(level_it);
    } else {
        auto level_it = asks_.find(loc.price);
        level_it->second.total_quantity -= remaining;
        level_it->second.order_count--;
        level_it->second.erase(loc.node);
        if (level_it->second.empty()) asks_.erase(level_it);
    }

    node_pool_.destroy(loc.node);
    order_map_.erase(it);
    return CancelResult::Success;
}

const PriceLevel* OrderBook::best_bid() const noexcept {
    if (bids_.empty()) return nullptr;
    return &bids_.begin()->second;
}

const PriceLevel* OrderBook::best_ask() const noexcept {
    if (asks_.empty()) return nullptr;
    return &asks_.begin()->second;
}

PriceLevel* OrderBook::best_bid() noexcept {
    if (bids_.empty()) return nullptr;
    return &bids_.begin()->second;
}

PriceLevel* OrderBook::best_ask() noexcept {
    if (asks_.empty()) return nullptr;
    return &asks_.begin()->second;
}

Price OrderBook::spread() const noexcept {
    auto* bid = best_bid();
    auto* ask = best_ask();
    if (!bid || !ask) return 0;
    return ask->price - bid->price;
}

size_t OrderBook::bid_depth() const noexcept { return bids_.size(); }
size_t OrderBook::ask_depth() const noexcept { return asks_.size(); }

} // namespace exsim

// AstraX repo sync
