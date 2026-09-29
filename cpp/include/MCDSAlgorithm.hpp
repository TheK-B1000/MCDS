#pragma once

#include <string>
#include <utility>
#include <vector>

#include "PointSet.hpp"
#include "SpatialIndex.hpp"

namespace mcds {

/// Output of an MCDS heuristic: selected point ids, plus optional visualization
/// metadata that is ignored by validation and experiment CSV semantics.
struct MCDSResult {
    std::vector<int> selectedIds;

    /// Visualization-only role tags for selected vertices.
    /// Allowed values: "core", "connector". Empty means roles unavailable.
    /// Does not affect CDS size or validator behaviour.
    std::vector<std::pair<int, std::string>> roles;
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
