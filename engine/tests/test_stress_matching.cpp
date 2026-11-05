#include <gtest/gtest.h>

#include "order_book.hpp"

#include <algorithm>
#include <map>
#include <random>
#include <unordered_map>
#include <vector>

using namespace exsim;

namespace {
struct LevelModel {
    Quantity total_quantity{0};
    std::size_t order_count{0};
};

using ModelBook = std::map<Price, LevelModel, std::greater<Price>>;

Order make_limit(uint64_t id, Side side, Price price, Quantity qty, uint64_t ts) {
    Order order{};
    order.id = id;
    order.side = side;
    order.price = price;
    order.quantity = qty;
    order.filled_quantity = 0;
    order.type = OrderType::Limit;
    order.tif = TimeInForce::GTC;
    order.timestamp = ts;
    return order;
}

void apply_add(ModelBook& model, const Order& order) {
    auto& level = model[order.price];
    level.total_quantity += order.quantity;
    level.order_count += 1;
}

void apply_cancel(ModelBook& model, const Order& order) {
    auto it = model.find(order.price);
    ASSERT_NE(it, model.end());
    it->second.total_quantity -= order.quantity;
    it->second.order_count -= 1;
    if (it->second.order_count == 0) {
        model.erase(it);
    }
}

void expect_book_matches_model(const OrderBook& book, const ModelBook& bids, const ModelBook& asks) {
    EXPECT_EQ(book.bid_depth(), bids.size());
    EXPECT_EQ(book.ask_depth(), asks.size());

    if (bids.empty()) {
        EXPECT_EQ(book.best_bid(), nullptr);
    } else {
        ASSERT_NE(book.best_bid(), nullptr);
        EXPECT_EQ(book.best_bid()->price, bids.begin()->first);
        EXPECT_EQ(book.best_bid()->total_quantity, bids.begin()->second.total_quantity);
        EXPECT_EQ(book.best_bid()->order_count, bids.begin()->second.order_count);
    }

    if (asks.empty()) {
        EXPECT_EQ(book.best_ask(), nullptr);
    } else {
        ASSERT_NE(book.best_ask(), nullptr);
        EXPECT_EQ(book.best_ask()->price, asks.begin()->first);
        EXPECT_EQ(book.best_ask()->total_quantity, asks.begin()->second.total_quantity);
        EXPECT_EQ(book.best_ask()->order_count, asks.begin()->second.order_count);
    }

    if (!bids.empty() && !asks.empty()) {
        EXPECT_EQ(book.spread(), asks.begin()->first - bids.begin()->first);
    }
}
} // namespace

TEST(OrderBookStressTest, RandomizedAddCancelMaintainsInvariants) {
    OrderBook book;
    ModelBook bids;
    ModelBook asks;

    std::mt19937 rng(1337);
    std::uniform_int_distribution<int> side_dist(0, 1);
    std::uniform_int_distribution<int> action_dist(0, 4);
    std::uniform_int_distribution<int> price_dist(9900, 10100);
    std::uniform_int_distribution<int> qty_dist(1, 100);

    std::unordered_map<OrderId, Order> active_orders;
    std::vector<OrderId> active_ids;
    uint64_t next_id = 1;

    for (int step = 0; step < 4000; ++step) {
        const bool should_add = active_orders.empty() || action_dist(rng) < 3;

        if (should_add) {
            Side side = side_dist(rng) == 0 ? Side::Buy : Side::Sell;
            Price price = static_cast<Price>(price_dist(rng));
            Quantity qty = static_cast<Quantity>(qty_dist(rng));
            Order order = make_limit(next_id++, side, price, qty, step);

            ASSERT_TRUE(book.add(order));
            active_orders.emplace(order.id, order);
            active_ids.push_back(order.id);

            if (side == Side::Buy) {
                apply_add(bids, order);
            } else {
                apply_add(asks, order);
            }
        } else {
            std::uniform_int_distribution<std::size_t> pick(0, active_ids.size() - 1);
            const OrderId id = active_ids[pick(rng)];
            auto order_it = active_orders.find(id);
            ASSERT_NE(order_it, active_orders.end());

            const Order order = order_it->second;
            EXPECT_EQ(book.cancel(id), CancelResult::Success);

            if (order.side == Side::Buy) {
                apply_cancel(bids, order);
            } else {
                apply_cancel(asks, order);
            }

            active_orders.erase(order_it);
            active_ids.erase(std::remove(active_ids.begin(), active_ids.end(), id), active_ids.end());
        }

        expect_book_matches_model(book, bids, asks);
    }
}

// AstraX repo sync
