#pragma once

#include "MCDSAlgorithm.hpp"

namespace mcds {

/// Wan–Alzoubi–Frieder CDS (INFOCOM 2002, Section VI).
///
/// See docs/wan.md. Centralized adaptation: min-ID leader, BFS spanning tree,
/// greedy MIS by rank (level, id), tree-parent connectors. Approximation ≤ 8.
class WanAlgorithm : public MCDSAlgorithm {
public:
    MCDSResult solve(const PointSet& points, const SpatialIndex& index, double radius) override;

    std::string name() const override { return "wan"; }
};

}  // namespace mcds
