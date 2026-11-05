// engine/src/order_book.hpp
#pragma once

#include "allocators.hpp"
#include "types.hpp"
#include <cstddef>
#include <map>
#include <unordered_map>

namespace exsim {

struct alignas(64) OrderNode {
    OrderNode* next{nullptr};
    OrderNode* prev{nullptr};
    Order order;

    explicit OrderNode(const Order& o) : order(o) {}
};

struct alignas(64) PriceLevel {
    Price price;
    Quantity total_quantity;
    size_t order_count;
    OrderNode* head;
    OrderNode* tail;

    PriceLevel() : price(0), total_quantity(0), order_count(0), head(nullptr), tail(nullptr) {}
    explicit PriceLevel(Price p) : price(p), total_quantity(0), order_count(0), head(nullptr), tail(nullptr) {}

    [[nodiscard]] bool empty() const noexcept { return order_count == 0; }
    [[nodiscard]] OrderNode* front() noexcept { return head; }
    [[nodiscard]] const OrderNode* front() const noexcept { return head; }

    void push_back(OrderNode* node) noexcept {
        node->next = nullptr;
        node->prev = tail;
        if (tail) {
            tail->next = node;
        } else {
            head = node;
        }
        tail = node;
    }

    void erase(OrderNode* node) noexcept {
        if (node->prev) {
            node->prev->next = node->next;
        } else {
            head = node->next;
        }

        if (node->next) {
            node->next->prev = node->prev;
        } else {
            tail = node->prev;
        }

        node->next = nullptr;
        node->prev = nullptr;
    }
};

class OrderBook {
public:
    OrderBook() = default;

    bool add(const Order& order);
    CancelResult cancel(OrderId id);

    [[nodiscard]] const PriceLevel* best_bid() const noexcept;
    [[nodiscard]] const PriceLevel* best_ask() const noexcept;
    [[nodiscard]] PriceLevel* best_bid() noexcept;
    [[nodiscard]] PriceLevel* best_ask() noexcept;
    [[nodiscard]] Price spread() const noexcept;
    [[nodiscard]] size_t bid_depth() const noexcept;
    [[nodiscard]] size_t ask_depth() const noexcept;

    // Const iterators for liquidity scanning (FOK pre-check)
    using BidsMap = std::map<Price, PriceLevel, std::greater<Price>>;
    using AsksMap = std::map<Price, PriceLevel, std::less<Price>>;

    [[nodiscard]] BidsMap::const_iterator bids_begin() const noexcept { return bids_.cbegin(); }
    [[nodiscard]] BidsMap::const_iterator bids_end() const noexcept { return bids_.cend(); }
    [[nodiscard]] AsksMap::const_iterator asks_begin() const noexcept { return asks_.cbegin(); }
    [[nodiscard]] AsksMap::const_iterator asks_end() const noexcept { return asks_.cend(); }

private:
    // Bids: highest price first (reverse order)
    std::map<Price, PriceLevel, std::greater<Price>> bids_;
    // Asks: lowest price first (natural order)
    std::map<Price, PriceLevel, std::less<Price>> asks_;
    // Fast lookup by order ID
    struct OrderLocation {
        Side side;
        Price price;
        OrderNode* node;
    };
    std::unordered_map<OrderId, OrderLocation> order_map_;
    ObjectPool<OrderNode> node_pool_;
};

} // namespace exsim

// AstraX repo sync
