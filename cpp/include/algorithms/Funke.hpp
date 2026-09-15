#pragma once

#include "MCDSAlgorithm.hpp"

namespace mcds {

/// Funke–Kesselman–Meyer–Segal CDS (ACM TOSN 2006 / WiMob 2005, §II).
///
/// See docs/funke.md. Centralized adaptation of the red-frontier colouring
/// algorithm (Fig. 1). Approximation ≤ 6.91 from refined MIS-vs-OPT analysis;
/// selection logic is not the Wan BFS-rank construction.
class FunkeAlgorithm : public MCDSAlgorithm {
public:
    MCDSResult solve(const PointSet& points, const SpatialIndex& index, double radius) override;

    std::string name() const override { return "funke"; }
};

}  // namespace mcds
