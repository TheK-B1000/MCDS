#pragma once

#include "MCDSAlgorithm.hpp"

namespace mcds {

/// Heuristic CDOM from Marathe et al., Networks 1995, Section 4.4.2.
///
/// See docs/marathe.md for the paper mapping, radius convention, and
/// deterministic tie-breaking (smallest-index root; ascending-id neighbour
/// scan for BFS; smallest-id MIS pivots).
///
/// Preconditions: the UDG must be connected. The algorithm does not check
/// connectivity itself; the CLI / experiment runner is responsible for that.
class MaratheAlgorithm : public MCDSAlgorithm {
public:
    MCDSResult solve(const PointSet& points, const SpatialIndex& index, double radius) override;

    std::string name() const override { return "marathe"; }
};

}  // namespace mcds
