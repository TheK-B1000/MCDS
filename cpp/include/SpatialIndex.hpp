#pragma once

#include <cstddef>
#include <vector>

#include "Metrics.hpp"

namespace mcds {

/// The single channel through which every algorithm learns about adjacency.
///
/// This class is the whole point of the project. MCDS algorithms are written
/// against this interface and nothing else, so they never see an adjacency
/// matrix, an adjacency list, or the geometric library underneath. Swapping the
/// grid backend for a CGAL range-search backend must not require touching a
/// single line of algorithm code.
///
///     MCDS algorithm
///           |
///           v
///     SpatialIndex          <-- this interface
///           |
///           v
///     uniform grid / CGAL / other geometric index
///
/// Contract for `radiusQuery`:
///   * returns the **ids** of all points `q` with `distance(p, q) <= radius`;
///   * **excludes the query point itself** (see the note below);
///   * the boundary is inclusive, so a point at distance exactly `radius` is
///     returned;
///   * points sharing identical coordinates with `p` *are* returned, since only
///     `p` itself is filtered out, not everything at distance zero;
///   * the order of the returned ids is unspecified.
///
/// Self-exclusion decision: the query point is excluded. Graph algorithms want
/// the open neighborhood N(p), and callers that need the closed neighborhood
/// N[p] can add `p` themselves, which is cheaper and less error-prone than
/// having every caller remember to filter `p` out.
class SpatialIndex {
public:
    virtual ~SpatialIndex() = default;

    /// Neighbor query writing into a caller-owned buffer. Preferred on hot
    /// paths because it lets the caller reuse one allocation across queries.
    /// `out` is cleared before the backend runs.
    void radiusQuery(int pointId, double radius, std::vector<int>& out) const {
        out.clear();
        radiusQueryImpl(pointId, radius, out);
    }

    /// Convenience overload. Allocates a fresh vector per call.
    std::vector<int> radiusQuery(int pointId, double radius) const {
        std::vector<int> out;
        radiusQuery(pointId, radius, out);
        return out;
    }

    /// Number of indexed points.
    virtual std::size_t size() const = 0;

    /// Instrumentation counters accumulated since construction or the last
    /// `resetStats()`.
    virtual const QueryStats& stats() const = 0;

    virtual void resetStats() = 0;

    /// Short human-readable backend name, e.g. "uniform-grid". Reported in the
    /// experiment output so results can be attributed to a backend.
    virtual const char* name() const = 0;

protected:
    /// The one thing a backend has to supply. Kept separate from the public
    /// overloads on purpose: if a backend overrode `radiusQuery` directly, its
    /// declaration would hide the two-argument convenience overload for every
    /// caller holding a derived-class reference. Splitting the virtual out means
    /// the public API is identical no matter which backend is in use.
    ///
    /// `out` arrives already cleared and must be filled with neighbor ids.
    virtual void radiusQueryImpl(int pointId, double radius, std::vector<int>& out) const = 0;
};

}  // namespace mcds
