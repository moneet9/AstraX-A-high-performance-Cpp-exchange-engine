#include <gtest/gtest.h>

#include "binary_protocol.hpp"

using namespace exsim;

TEST(BinaryProtocolTest, OrderRoundTrip) {
    Order order{};
    order.id = 42;
    order.price = 10123;
    order.stop_price = 9900;
    order.peg_offset = 5;
    order.quantity = 250;
    order.filled_quantity = 75;
    order.visible_quantity = 100;
    order.hidden_quantity = 150;
    order.side = Side::Buy;
    order.type = OrderType::Limit;
    order.tif = TimeInForce::GTC;
    order.timestamp = 123456789;

    auto bytes = BinaryProtocol::encode_order(order);
    auto decoded = BinaryProtocol::decode_order(bytes);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->id, order.id);
    EXPECT_EQ(decoded->price, order.price);
    EXPECT_EQ(decoded->stop_price, order.stop_price);
    EXPECT_EQ(decoded->peg_offset, order.peg_offset);
    EXPECT_EQ(decoded->quantity, order.quantity);
    EXPECT_EQ(decoded->filled_quantity, order.filled_quantity);
    EXPECT_EQ(decoded->visible_quantity, order.visible_quantity);
    EXPECT_EQ(decoded->hidden_quantity, order.hidden_quantity);
    EXPECT_EQ(decoded->side, order.side);
    EXPECT_EQ(decoded->type, order.type);
    EXPECT_EQ(decoded->tif, order.tif);
    EXPECT_EQ(decoded->timestamp, order.timestamp);
}

TEST(BinaryProtocolTest, FillRoundTrip) {
    Fill fill{};
    fill.maker_order_id = 11;
    fill.taker_order_id = 22;
    fill.price = 10001;
    fill.quantity = 37;
    fill.aggressor_side = Side::Sell;
    fill.timestamp = 987654321;

    auto bytes = BinaryProtocol::encode_fill(fill);
    auto decoded = BinaryProtocol::decode_fill(bytes);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->maker_order_id, fill.maker_order_id);
    EXPECT_EQ(decoded->taker_order_id, fill.taker_order_id);
    EXPECT_EQ(decoded->price, fill.price);
    EXPECT_EQ(decoded->quantity, fill.quantity);
    EXPECT_EQ(decoded->aggressor_side, fill.aggressor_side);
    EXPECT_EQ(decoded->timestamp, fill.timestamp);
}

// AstraX repo sync
