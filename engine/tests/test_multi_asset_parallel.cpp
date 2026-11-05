#include <gtest/gtest.h>

#include "multi_asset_engine.hpp"

#include <algorithm>

using namespace exsim;

namespace {
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
} // namespace

TEST(MultiAssetEngineParallelTest, ProcessesIndependentSymbolsInParallel) {
    MultiAssetEngine engine;

    std::vector<MultiAssetEngine::SymbolOrder> orders;
    orders.push_back({1, make_limit(1, Side::Buy, 10000, 10, 1)});
    orders.push_back({2, make_limit(2, Side::Sell, 10000, 10, 2)});
    orders.push_back({3, make_limit(3, Side::Buy, 10100, 20, 3)});
    orders.push_back({4, make_limit(4, Side::Sell, 10100, 20, 4)});

    auto results = engine.submit_parallel(orders);

    ASSERT_EQ(results.size(), 2);
    std::sort(results.begin(), results.end(), [](const auto& a, const auto& b) {
        return a.symbol_id < b.symbol_id;
    });

    EXPECT_EQ(results[0].symbol_id, 1u);
    EXPECT_EQ(results[1].symbol_id, 2u);
    EXPECT_EQ(engine.get_book(1).book().bid_depth(), 1);
    EXPECT_EQ(engine.get_book(2).book().ask_depth(), 1);
}

// AstraX repo sync
