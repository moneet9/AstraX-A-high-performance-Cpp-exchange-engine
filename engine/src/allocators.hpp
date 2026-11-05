#pragma once

#include <algorithm>
#include <cstddef>
#include <memory>
#include <new>
#include <utility>
#include <vector>

namespace exsim {

class ArenaAllocator {
public:
    explicit ArenaAllocator(std::size_t min_chunk_bytes = 64 * 1024) noexcept
        : min_chunk_bytes_(min_chunk_bytes) {}

    ArenaAllocator(const ArenaAllocator&) = delete;
    ArenaAllocator& operator=(const ArenaAllocator&) = delete;

    ~ArenaAllocator() {
        for (auto& chunk : chunks_) {
            ::operator delete(chunk.raw, std::align_val_t(chunk.alignment));
        }
    }

    [[nodiscard]] void* allocate(std::size_t bytes, std::size_t alignment) {
        if (bytes == 0) {
            return nullptr;
        }

        alignment = std::max<std::size_t>(alignment, alignof(std::max_align_t));

        if (!chunks_.empty()) {
            if (void* ptr = try_allocate_from_chunk(chunks_.back(), bytes, alignment)) {
                return ptr;
            }
        }

        return allocate_chunk(bytes, alignment);
    }

private:
    struct Chunk {
        void* raw{nullptr};
        std::byte* current{nullptr};
        std::byte* end{nullptr};
        std::size_t alignment{alignof(std::max_align_t)};
    };

    [[nodiscard]] void* try_allocate_from_chunk(Chunk& chunk, std::size_t bytes, std::size_t alignment) {
        void* ptr = chunk.current;
        std::size_t space = static_cast<std::size_t>(chunk.end - chunk.current);
        if (!std::align(alignment, bytes, ptr, space)) {
            return nullptr;
        }

        chunk.current = static_cast<std::byte*>(ptr) + bytes;
        return ptr;
    }

    [[nodiscard]] void* allocate_chunk(std::size_t bytes, std::size_t alignment) {
        const std::size_t slab_bytes = std::max(min_chunk_bytes_, bytes + alignment);
        void* raw = ::operator new(slab_bytes, std::align_val_t(alignment));
        auto* begin = static_cast<std::byte*>(raw);
        chunks_.push_back(Chunk{raw, begin, begin + slab_bytes, alignment});
        return try_allocate_from_chunk(chunks_.back(), bytes, alignment);
    }

    std::vector<Chunk> chunks_;
    std::size_t min_chunk_bytes_;
};

template <typename T, std::size_t SlabCapacity = 256>
class SlabAllocator {
public:
    SlabAllocator() = default;
    SlabAllocator(const SlabAllocator&) = delete;
    SlabAllocator& operator=(const SlabAllocator&) = delete;

    [[nodiscard]] T* allocate() {
        if (!free_list_) {
            refill();
        }

        if (!free_list_) {
            return nullptr;
        }

        auto* node = free_list_;
        free_list_ = node->next;
        return reinterpret_cast<T*>(node);
    }

    void deallocate(T* ptr) noexcept {
        if (!ptr) {
            return;
        }

        auto* node = reinterpret_cast<FreeNode*>(ptr);
        node->next = free_list_;
        free_list_ = node;
    }

private:
    struct FreeNode {
        FreeNode* next{nullptr};
    };

    static constexpr std::size_t slot_size =
        ((sizeof(T) + alignof(T) - 1) / alignof(T)) * alignof(T);

    void refill() {
        void* slab = arena_.allocate(slot_size * SlabCapacity, alignof(T));
        if (!slab) {
            return;
        }

        auto* base = static_cast<std::byte*>(slab);
        for (std::size_t i = 0; i < SlabCapacity; ++i) {
            auto* node = reinterpret_cast<FreeNode*>(base + i * slot_size);
            node->next = free_list_;
            free_list_ = node;
        }
    }

    ArenaAllocator arena_;
    FreeNode* free_list_{nullptr};
};

template <typename T, std::size_t SlabCapacity = 256>
class ObjectPool {
public:
    ObjectPool() = default;
    ObjectPool(const ObjectPool&) = delete;
    ObjectPool& operator=(const ObjectPool&) = delete;

    template <typename... Args>
    [[nodiscard]] T* create(Args&&... args) {
        if (auto* memory = slab_.allocate()) {
            return new (memory) T(std::forward<Args>(args)...);
        }
        return nullptr;
    }

    void destroy(T* ptr) noexcept {
        if (!ptr) {
            return;
        }

        ptr->~T();
        slab_.deallocate(ptr);
    }

private:
    SlabAllocator<T, SlabCapacity> slab_;
};

} // namespace exsim

// AstraX repo sync
