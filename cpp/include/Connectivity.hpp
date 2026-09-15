#pragma once

#include <cstddef>
#include <vector>

#include "PointSet.hpp"
#include "SpatialIndex.hpp"

namespace mcds {

/// Statistics from an implicit UDG traversal.
///
/// No adjacency structure is built: neighbors are discovered only through
/// `SpatialIndex::radiusQuery`. The result describes the connected components
/// of the unit disk graph induced by the point set at the given radius.
struct ConnectivityResult {
    /// True when the UDG has exactly one component (or the point set is empty).
    bool connected = true;

    /// Number of points visited by the traversal. Always equals `n` when the
    /// whole set is scanned for components.
    std::size_t visitedCount = 0;

    /// Number of connected components. Zero for an empty point set.
    std::size_t componentCount = 0;

    /// Size of each component, in the order components were discovered
    /// (smallest input index first as the seed of each new component).
    std::vector<std::size_t> componentSizes;

    /// Maximum entry of `componentSizes`, or zero when empty.
    std::size_t largestComponent = 0;

    /// Number of components of size 1.
    std::size_t isolatedCount = 0;
};

/// Discover all connected components of the implicit UDG via lazy BFS.
///
/// Uses a visited bitmap indexed by internal point index, a queue, and one
/// reused neighbor buffer. Peak auxiliary memory is O(n + max degree), never
/// O(edges). Empty point sets yield `connected == true` with zero components.
ConnectivityResult findConnectedComponents(
    const PointSet& points,
    const SpatialIndex& index,
    double radius
);

/// Convenience wrapper: true iff the UDG is connected (including the empty set).
inline bool isConnected(const PointSet& points, const SpatialIndex& index, double radius) {
    return findConnectedComponents(points, index, radius).connected;
}

}  // namespace mcds
