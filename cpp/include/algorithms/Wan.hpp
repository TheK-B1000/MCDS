#pragma once

#include "MCDSAlgorithm.hpp"

namespace mcds {

/// Wan–Alzoubi–Frieder CDS (INFOCOM 2002, Section VI).
///
/// See docs/algorithms/wan.md. Centralized adaptation: min-ID leader, BFS
/// spanning tree, greedy MIS by rank (level, id) (type-1 blacks), tree-parent
/// connectors (type-2 blacks), then the §VI.A black->gray pruning rule. The
/// BFS tree replaces the paper's Cidon–Mokryn tree, so the selected vertices
/// can differ from a distributed execution. The paper bounds the pre-pruning
/// set by 8·opt + 1; pruning only removes vertices. No time/message claims.
class WanAlgorithm : public MCDSAlgorithm {
public:
    MCDSResult solve(const PointSet& points, const SpatialIndex& index, double radius) override;

    std::string name() const override { return "wan"; }
};

}  // namespace mcds
