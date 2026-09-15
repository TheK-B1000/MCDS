#pragma once

#include <string>
#include <vector>

#include "PointSet.hpp"
#include "SpatialIndex.hpp"

namespace mcds {

/// Output of an MCDS heuristic: selected point ids only.
///
/// Timing, validation, and serialization belong to the runner, not here.
struct MCDSResult {
    std::vector<int> selectedIds;
};

/// Shared interface for every connected-dominating-set heuristic.
///
/// Algorithms see only a point set and a neighbour oracle. They must not build
/// an adjacency matrix or permanently store all UDG edges.
class MCDSAlgorithm {
public:
    virtual ~MCDSAlgorithm() = default;

    virtual MCDSResult solve(const PointSet& points, const SpatialIndex& index, double radius) = 0;

    virtual std::string name() const = 0;
};

}  // namespace mcds
