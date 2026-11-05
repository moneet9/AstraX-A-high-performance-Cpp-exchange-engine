#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <new>
#include <type_traits>
#include <utility>

namespace exsim {

template <typename T, std::size_t Capacity>
class SpscRingBuffer {
public:
    static_assert(Capacity > 0, "Capacity must be positive");

    SpscRingBuffer() = default;
    SpscRingBuffer(const SpscRingBuffer&) = delete;
    SpscRingBuffer& operator=(const SpscRingBuffer&) = delete;

    ~SpscRingBuffer() {
        T value{};
        while (try_pop(value)) {
        }
    }

    [[nodiscard]] bool try_push(const T& value) noexcept {
        return emplace(value);
    }

    [[nodiscard]] bool try_push(T&& value) noexcept {
        return emplace(std::move(value));
    }

    [[nodiscard]] bool try_pop(T& out) noexcept {
        const std::size_t head = head_.load(std::memory_order_relaxed);
        if (head == tail_.load(std::memory_order_acquire)) {
            return false;
        }

        auto* slot = std::launder(reinterpret_cast<T*>(&storage_[head]));
        out = std::move(*slot);
        slot->~T();
        head_.store((head + 1) % Capacity, std::memory_order_release);
        return true;
    }

    [[nodiscard]] bool empty() const noexcept {
        return head_.load(std::memory_order_acquire) == tail_.load(std::memory_order_acquire);
    }

    [[nodiscard]] bool full() const noexcept {
        return ((tail_.load(std::memory_order_acquire) + 1) % Capacity) == head_.load(std::memory_order_acquire);
    }

private:
    template <typename U>
    [[nodiscard]] bool emplace(U&& value) noexcept {
        const std::size_t tail = tail_.load(std::memory_order_relaxed);
        const std::size_t next_tail = (tail + 1) % Capacity;
        if (next_tail == head_.load(std::memory_order_acquire)) {
            return false;
        }

        auto* slot = std::launder(reinterpret_cast<T*>(&storage_[tail]));
        std::construct_at(slot, std::forward<U>(value));
        tail_.store(next_tail, std::memory_order_release);
        return true;
    }

    using Storage = std::aligned_storage_t<sizeof(T), alignof(T)>;
    std::array<Storage, Capacity> storage_{};
    std::atomic<std::size_t> head_{0};
    std::atomic<std::size_t> tail_{0};
};

} // namespace exsim

// AstraX repo sync
