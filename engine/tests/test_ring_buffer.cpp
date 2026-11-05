#include <gtest/gtest.h>

#include "ring_buffer.hpp"

using namespace exsim;

TEST(RingBufferTest, PushPopPreservesOrder) {
    SpscRingBuffer<int, 4> queue;

    EXPECT_TRUE(queue.try_push(1));
    EXPECT_TRUE(queue.try_push(2));
    EXPECT_TRUE(queue.try_push(3));
    EXPECT_FALSE(queue.try_push(4));

    int value = 0;
    EXPECT_TRUE(queue.try_pop(value));
    EXPECT_EQ(value, 1);
    EXPECT_TRUE(queue.try_pop(value));
    EXPECT_EQ(value, 2);
    EXPECT_TRUE(queue.try_pop(value));
    EXPECT_EQ(value, 3);
    EXPECT_FALSE(queue.try_pop(value));
}

// AstraX repo sync
