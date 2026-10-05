#pragma once

// Benchmark support for the experiment runner. Nothing in this header is used
// by the algorithms or by the interactive `mcds` CLI; it exists so that `mcds_bench` can
// measure shared preprocessing, graph statistics and spatial-query work
// without touching algorithm code.

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "GridSpatialIndex.hpp"
#include "Metrics.hpp"
#include "PointSet.hpp"
#include "SpatialIndex.hpp"

namespace mcds::bench {

/// Statistics of the implicit UDG, computed from radius queries only (no edge
/// list is stored). Degrees need one query per vertex; components reuse the
/// tested `findConnectedComponents`. This runs outside every algorithm timer.
struct GraphStats {
    std::size_t n = 0;
    std::uint64_t edges = 0;  // sum of degrees / 2
    std::size_t minDegree = 0;
    std::size_t maxDegree = 0;
    double meanDegree = 0.0;
    double medianDegree = 0.0;
    double degreeStdDev = 0.0;  // population standard deviation
    double graphDensity = 0.0;  // 2|E| / (n (n - 1)); 0 when n < 2
    std::size_t isolatedCount = 0;
    std::size_t componentCount = 0;
    std::size_t largestComponent = 0;
    bool connected = true;

    // Spatial work spent computing these statistics (not algorithm work).
    std::uint64_t neighborQueries = 0;
    std::uint64_t candidatesExamined = 0;
};

GraphStats computeGraphStats(const PointSet& points, const SpatialIndex& index, double radius);

/// FNV-1a 64 over (n, then each point's id as int64 and x, y as IEEE-754
/// binary64, little-endian, in input order). The Python side computes the same
/// value from the canonical CSV, so the harness can prove every algorithm saw
/// byte-identical coordinates.
std::uint64_t pointsFingerprint(const PointSet& points);

/// FNV-1a 64 over the sorted, de-duplicated id list. Used to show that repeated
/// executions of a deterministic algorithm return the same set.
std::uint64_t idSetFingerprint(std::vector<int> ids);

std::string toHex64(std::uint64_t value);

/// Per-query maxima and cell counts that the base `QueryStats` does not track.
struct ExtendedQueryStats {
    std::uint64_t cellsExamined = 0;
    std::uint64_t maxCandidatesPerQuery = 0;
    std::uint64_t maxNeighborsPerQuery = 0;
    std::uint64_t queryTimeNs = 0;  // only when query timing is enabled

    void reset() { *this = ExtendedQueryStats{}; }
};

/// Decorator over the grid index used for BASIC / DETAILED instrumentation.
///
/// It forwards every query unchanged to the wrapped grid, so the neighbour ids
/// an algorithm sees are exactly the ids the grid returns. It adds one virtual
/// hop and a few per-query counters, which is why NONE instrumentation passes
/// the grid itself to the algorithm instead.
class InstrumentedSpatialIndex : public SpatialIndex {
public:
    InstrumentedSpatialIndex(const GridSpatialIndex& inner, bool timeQueries)
        : inner_(&inner), timeQueries_(timeQueries) {}

    std::size_t size() const override { return inner_->size(); }
    const QueryStats& stats() const override { return stats_; }
    void resetStats() override {
        stats_.reset();
        extended_.reset();
    }
    const char* name() const override { return inner_->name(); }

    const ExtendedQueryStats& extendedStats() const { return extended_; }

protected:
    void radiusQueryImpl(int pointId, double radius, std::vector<int>& out) const override;

private:
    const GridSpatialIndex* inner_;
    bool timeQueries_;
    mutable QueryStats stats_;
    mutable ExtendedQueryStats extended_;
};

/// Resident-set figures for the current process. `available` is false where
/// the platform call is not implemented.
struct ProcessMemory {
    bool available = false;
    std::uint64_t currentRssBytes = 0;
    std::uint64_t peakRssBytes = 0;
};

ProcessMemory processMemory();

}  // namespace mcds::bench
