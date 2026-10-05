#pragma once

#include <cstdint>

// Heap accounting for the memory-probe binary `mcds_bench_mem` ONLY.
//
// HeapTracker.cpp replaces the global operator new / delete family, prefixing
// every allocation with a 16-byte size header. That changes allocation layout
// and adds a few instructions per allocation, so it is deliberately NOT linked
// into `mcds_bench`, whose timings are the primary runtime measurement.
//
// Assumption: the benchmark is single-threaded, so plain (non-atomic)
// counters are exact. Allocations made with the over-aligned `operator new`
// overloads (std::align_val_t) are not counted; none of the project's code
// requests over-aligned storage.

namespace mcds::bench {

struct HeapSnapshot {
    std::uint64_t currentBytes = 0;    // live bytes requested by the program
    std::uint64_t peakBytes = 0;       // maximum of currentBytes since last resetPeak
    std::uint64_t allocationCount = 0; // calls to operator new since last resetPeak
    std::uint64_t allocatedBytes = 0;  // bytes requested since last resetPeak
};

HeapSnapshot heapSnapshot();

/// Starts a new measurement window: peak := current, counters := 0.
void heapResetWindow();

}  // namespace mcds::bench
