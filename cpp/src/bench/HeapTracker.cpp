#include "bench/HeapTracker.hpp"

#include <cstddef>
#include <cstdlib>
#include <new>

namespace mcds::bench {
namespace {

// 16 bytes keeps the user pointer aligned to __STDCPP_DEFAULT_NEW_ALIGNMENT__
// on the platforms we build for (malloc returns 16-byte aligned blocks).
constexpr std::size_t kHeader = 16;

std::uint64_t g_current = 0;
std::uint64_t g_peak = 0;
std::uint64_t g_count = 0;
std::uint64_t g_bytes = 0;
std::uint64_t g_lifetime = 0;

void* trackedAlloc(std::size_t size) {
    void* raw = std::malloc(size + kHeader);
    if (raw == nullptr) {
        return nullptr;
    }
    *static_cast<std::size_t*>(raw) = size;
    g_current += size;
    g_bytes += size;
    ++g_count;
    if (g_current > g_peak) {
        g_peak = g_current;
    }
    if (g_current > g_lifetime) {
        g_lifetime = g_current;
    }
    return static_cast<unsigned char*>(raw) + kHeader;
}

void trackedFree(void* p) noexcept {
    if (p == nullptr) {
        return;
    }
    unsigned char* raw = static_cast<unsigned char*>(p) - kHeader;
    g_current -= *reinterpret_cast<std::size_t*>(raw);
    std::free(raw);
}

void* allocOrThrow(std::size_t size) {
    if (size == 0) {
        size = 1;
    }
    for (;;) {
        if (void* p = trackedAlloc(size)) {
            return p;
        }
        std::new_handler handler = std::get_new_handler();
        if (handler == nullptr) {
            throw std::bad_alloc();
        }
        handler();
    }
}

}  // namespace

HeapSnapshot heapSnapshot() {
    HeapSnapshot s;
    s.currentBytes = g_current;
    s.peakBytes = g_peak;
    s.allocationCount = g_count;
    s.allocatedBytes = g_bytes;
    s.lifetimePeakBytes = g_lifetime;
    return s;
}

void heapResetWindow() {
    g_peak = g_current;
    g_count = 0;
    g_bytes = 0;
}

}  // namespace mcds::bench

void* operator new(std::size_t size) { return mcds::bench::allocOrThrow(size); }
void* operator new[](std::size_t size) { return mcds::bench::allocOrThrow(size); }
void* operator new(std::size_t size, const std::nothrow_t&) noexcept {
    try {
        return mcds::bench::allocOrThrow(size);
    } catch (...) {
        return nullptr;
    }
}
void* operator new[](std::size_t size, const std::nothrow_t&) noexcept {
    try {
        return mcds::bench::allocOrThrow(size);
    } catch (...) {
        return nullptr;
    }
}
void operator delete(void* p) noexcept { mcds::bench::trackedFree(p); }
void operator delete[](void* p) noexcept { mcds::bench::trackedFree(p); }
void operator delete(void* p, std::size_t) noexcept { mcds::bench::trackedFree(p); }
void operator delete[](void* p, std::size_t) noexcept { mcds::bench::trackedFree(p); }
void operator delete(void* p, const std::nothrow_t&) noexcept { mcds::bench::trackedFree(p); }
void operator delete[](void* p, const std::nothrow_t&) noexcept { mcds::bench::trackedFree(p); }
