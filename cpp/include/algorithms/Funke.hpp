#pragma once

#include "MCDSAlgorithm.hpp"

namespace mcds {

/// Funke–Kesselman–Meyer–Segal CDS, §II / Figure 1 of the 4-page paper "A Simple
/// Improved Distributed Algorithm for Minimum CDS in Unit Disk Graphs" (the
/// audited implementation source; the ACM TOSN 2006 article was not audited and
/// is not the implementation source).
///
/// See docs/algorithms/funke.md. Centralized, round-synchronous adaptation of
/// the red-frontier colouring algorithm (Fig. 1); D2-colouring / slotting not
/// simulated. Deterministic tie-breaks: leader = minimum id; when several new
/// blue nodes recruit the same white node in one round (Fig. 1 does not say
/// which), its parent is the blue node with the minimum id. Selection logic is
/// not the Wan BFS-rank construction.
class FunkeAlgorithm : public MCDSAlgorithm {
public:
    MCDSResult solve(const PointSet& points, const SpatialIndex& index, double radius) override;

    std::string name() const override { return "funke"; }
};

}  // namespace mcds
