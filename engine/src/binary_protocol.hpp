#pragma once

#include "types.hpp"
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <optional>
#include <vector>

namespace exsim {

enum class WireMessageType : std::uint8_t {
    SubmitOrder = 1,
    CancelOrder = 2,
    Fill = 3,
};

class BinaryProtocol {
public:
    static std::vector<std::uint8_t> encode_order(const Order& order) {
        std::vector<std::uint8_t> bytes;
        bytes.reserve(order_size());
        append_u8(bytes, kVersion);
        append_u8(bytes, static_cast<std::uint8_t>(WireMessageType::SubmitOrder));
        append_u64(bytes, order.id);
        append_i64(bytes, order.price);
        append_i64(bytes, order.stop_price);
        append_i64(bytes, order.peg_offset);
        append_u32(bytes, order.quantity);
        append_u32(bytes, order.filled_quantity);
        append_u32(bytes, order.visible_quantity);
        append_u32(bytes, order.hidden_quantity);
        append_u8(bytes, static_cast<std::uint8_t>(order.side));
        append_u8(bytes, static_cast<std::uint8_t>(order.type));
        append_u8(bytes, static_cast<std::uint8_t>(order.tif));
        append_u8(bytes, 0);
        append_u64(bytes, order.timestamp);
        return bytes;
    }

    static std::optional<Order> decode_order(const std::vector<std::uint8_t>& bytes) {
        if (bytes.size() != order_size()) {
            return std::nullopt;
        }

        std::size_t offset = 0;
        if (read_u8(bytes, offset++) != kVersion) {
            return std::nullopt;
        }
        if (static_cast<WireMessageType>(read_u8(bytes, offset++)) != WireMessageType::SubmitOrder) {
            return std::nullopt;
        }

        Order order{};
        order.id = read_u64(bytes, offset);
        order.price = read_i64(bytes, offset);
        order.stop_price = read_i64(bytes, offset);
        order.peg_offset = read_i64(bytes, offset);
        order.quantity = read_u32(bytes, offset);
        order.filled_quantity = read_u32(bytes, offset);
        order.visible_quantity = read_u32(bytes, offset);
        order.hidden_quantity = read_u32(bytes, offset);
        order.side = static_cast<Side>(read_u8(bytes, offset));
        order.type = static_cast<OrderType>(read_u8(bytes, offset));
        order.tif = static_cast<TimeInForce>(read_u8(bytes, offset));
        offset += 1; // reserved padding byte
        order.timestamp = read_u64(bytes, offset);
        return order;
    }

    static std::vector<std::uint8_t> encode_fill(const Fill& fill) {
        std::vector<std::uint8_t> bytes;
        bytes.reserve(fill_size());
        append_u8(bytes, kVersion);
        append_u8(bytes, static_cast<std::uint8_t>(WireMessageType::Fill));
        append_u64(bytes, fill.maker_order_id);
        append_u64(bytes, fill.taker_order_id);
        append_i64(bytes, fill.price);
        append_u32(bytes, fill.quantity);
        append_u8(bytes, static_cast<std::uint8_t>(fill.aggressor_side));
        append_u8(bytes, 0);
        append_u8(bytes, 0);
        append_u8(bytes, 0);
        append_u64(bytes, fill.timestamp);
        return bytes;
    }

    static std::optional<Fill> decode_fill(const std::vector<std::uint8_t>& bytes) {
        if (bytes.size() != fill_size()) {
            return std::nullopt;
        }

        std::size_t offset = 0;
        if (read_u8(bytes, offset++) != kVersion) {
            return std::nullopt;
        }
        if (static_cast<WireMessageType>(read_u8(bytes, offset++)) != WireMessageType::Fill) {
            return std::nullopt;
        }

        Fill fill{};
        fill.maker_order_id = read_u64(bytes, offset);
        fill.taker_order_id = read_u64(bytes, offset);
        fill.price = read_i64(bytes, offset);
        fill.quantity = read_u32(bytes, offset);
        fill.aggressor_side = static_cast<Side>(read_u8(bytes, offset));
        offset += 3; // reserved bytes
        fill.timestamp = read_u64(bytes, offset);
        return fill;
    }

    static constexpr std::size_t order_size() noexcept {
        return 2 + 8 + 8 + 8 + 8 + 4 + 4 + 4 + 4 + 1 + 1 + 1 + 1 + 8;
    }

    static constexpr std::size_t fill_size() noexcept {
        return 2 + 8 + 8 + 8 + 4 + 1 + 3 + 8;
    }

private:
    static constexpr std::uint8_t kVersion = 1;

    static void append_u8(std::vector<std::uint8_t>& bytes, std::uint8_t value) {
        bytes.push_back(value);
    }

    static void append_u32(std::vector<std::uint8_t>& bytes, std::uint32_t value) {
        for (int i = 0; i < 4; ++i) {
            bytes.push_back(static_cast<std::uint8_t>((value >> (i * 8)) & 0xFF));
        }
    }

    static void append_u64(std::vector<std::uint8_t>& bytes, std::uint64_t value) {
        for (int i = 0; i < 8; ++i) {
            bytes.push_back(static_cast<std::uint8_t>((value >> (i * 8)) & 0xFF));
        }
    }

    static void append_i64(std::vector<std::uint8_t>& bytes, std::int64_t value) {
        append_u64(bytes, static_cast<std::uint64_t>(value));
    }

    static std::uint8_t read_u8(const std::vector<std::uint8_t>& bytes, std::size_t index) {
        return bytes[index];
    }

    static std::uint32_t read_u32(const std::vector<std::uint8_t>& bytes, std::size_t& offset) {
        std::uint32_t value = 0;
        for (int i = 0; i < 4; ++i) {
            value |= static_cast<std::uint32_t>(bytes[offset++]) << (i * 8);
        }
        return value;
    }

    static std::uint64_t read_u64(const std::vector<std::uint8_t>& bytes, std::size_t& offset) {
        std::uint64_t value = 0;
        for (int i = 0; i < 8; ++i) {
            value |= static_cast<std::uint64_t>(bytes[offset++]) << (i * 8);
        }
        return value;
    }

    static std::int64_t read_i64(const std::vector<std::uint8_t>& bytes, std::size_t& offset) {
        return static_cast<std::int64_t>(read_u64(bytes, offset));
    }
};

} // namespace exsim

// AstraX repo sync
