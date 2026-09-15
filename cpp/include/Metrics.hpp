#pragma once

#include <chrono>
#include <cstdint>

namespace mcds {

/// Instrumentation for the spatial-query layer.
///
/// These counters are the experimental payload of the project: because the UDG
/// is never materialised, the cost an algorithm pays for adjacency information
/// is exactly the cost recorded here.
struct QueryStats {
    /// Number of calls to `SpatialIndex::radiusQuery`.
    std::uint64_t neighborQueries = 0;

    /// Number of points whose distance was actually evaluated. For a grid index
    /// this is every point sitting in a scanned cell, including the query point
    /// itself, so it is always >= `neighborsReturned`. The ratio of the two is a
    /// direct measure of how much work the index wastes.
    std::uint64_t candidatesExamined = 0;

    /// Total number of neighbors handed back to callers (sum over all queries).
    std::uint64_t neighborsReturned = 0;

    void reset() { *this = QueryStats{}; }
};

/// Minimal wall-clock stopwatch.
class Timer {
public:
    Timer() : start_(Clock::now()) {}

    void restart() { start_ = Clock::now(); }

    double elapsedMs() const {
        const std::chrono::duration<double, std::milli> d = Clock::now() - start_;
        return d.count();
    }

private:
    using Clock = std::chrono::steady_clock;
    Clock::time_point start_;
};

}  // namespace mcds
