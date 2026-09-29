#pragma once

#include <vector>

#include "PointSet.hpp"
#include "SpatialIndex.hpp"

namespace mcds {

/// Centralized Wan level-based MIS (type-1 blacks).
///
/// Construction:
///   1. Leader = minimum point ID
///   2. Deterministic BFS spanning tree (ascending neighbour-ID discovery)
///   3. Greedy first-fit MIS in increasing rank `(level, ID)`
///
/// This is the MIS stage consumed by Li S-MIS Step 1. It does **not** add
/// Wan's tree-parent connectors.
///
/// Throws `std::invalid_argument` if `radius < 0` or the UDG is disconnected.
/// Returns selected point **ids** (input order among selected indices).
std::vector<int> computeWanLevelBasedMis(
    const PointSet& points,
    const SpatialIndex& index,
    double radius);

}  // namespace mcds
