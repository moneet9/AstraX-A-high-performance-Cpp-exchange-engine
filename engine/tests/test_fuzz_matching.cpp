#include <gtest/gtest.h>

#include "matching_engine.hpp"

#include <algorithm>
#include <map>
#include <random>
#include <unordered_map>
#include <vector>

using namespace exsim;

namespace {
Order make_limit(OrderId id, Side side, Price price, Quantity qty, Timestamp ts) {
    Order order{};
    order.id = id;
    order.side = side;
    order.price = price;
    order.quantity = qty;
    order.filled_quantity = 0;
    order.visible_quantity = 0;
    order.hidden_quantity = 0;
    order.stop_price = 0;
    order.peg_offset = 0;
    order.type = OrderType::Limit;
    order.tif = TimeInForce::GTC;
    order.timestamp = ts;
    return order;
}
} // namespace

TEST(MatchingEngineFuzzTest, RandomizedSubmitAndCancelStayConsistent) {
    MatchingEngine engine;
    std::mt19937 rng(20260717);
    std::uniform_int_distribution<int> action_dist(0, 7);
    std::uniform_int_distribution<int> side_dist(0, 1);
    std::uniform_int_distribution<int> price_dist(9900, 10100);
    std::uniform_int_distribution<int> qty_dist(1, 250);

    std::unordered_map<OrderId, Order> active_orders;
    std::vector<OrderId> active_ids;
    OrderId next_id = 1;

    for (int step = 0; step < 5000; ++step) {
        const bool should_add = active_orders.empty() || action_dist(rng) < 5;

        if (should_add) {
            const Side side = side_dist(rng) == 0 ? Side::Buy : Side::Sell;
            const Price price = static_cast<Price>(price_dist(rng));
            const Quantity qty = static_cast<Quantity>(qty_dist(rng));
            Order order = make_limit(next_id++, side, price, qty, static_cast<Timestamp>(step));

            auto fills = engine.submit(order);
            EXPECT_LE(order.filled_quantity, order.quantity);
            EXPECT_EQ(order.remaining(), order.quantity - order.filled_quantity);

            if (!order.is_filled()) {
                active_orders.emplace(order.id, order);
                active_ids.push_back(order.id);
            }

            for (const auto& fill : fills) {
                EXPECT_GT(fill.quantity, 0u);
                EXPECT_EQ(fill.timestamp, order.timestamp);
            }
        } else {
            std::uniform_int_distribution<std::size_t> pick(0, active_ids.size() - 1);
            const OrderId id = active_ids[pick(rng)];
            auto it = active_orders.find(id);
            ASSERT_NE(it, active_orders.end());

            const CancelResult result = engine.cancel(id);
            EXPECT_TRUE(result == CancelResult::Success || result == CancelResult::AlreadyFilled);

            if (result == CancelResult::Success) {
                active_orders.erase(it);
                active_ids.erase(std::remove(active_ids.begin(), active_ids.end(), id), active_ids.end());
            }
        }

        const auto& book = engine.book();
        if (book.best_bid() && book.best_ask()) {
            EXPECT_GT(book.best_ask()->price, book.best_bid()->price);
        }
    }
}

