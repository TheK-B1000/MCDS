#pragma once

#include "MCDSAlgorithm.hpp"

namespace mcds {

/// Li et al. S-MIS algorithm.
///
/// Step 1: Wan level-based MIS (black nodes).
/// Step 2: Li greedy Steiner Algorithm A (blue connectors).
/// Grey nodes are scored by distinct black-blue components via black
/// neighbors; blue-blue edges are ignored. Final CDS = black ∪ blue.
/// Adaptation: "S-MIS connector phase with centralized Wan-level MIS".
/// The paper's bound (4.8 + ln 5)·opt + 1.2 (Theorem 1) holds only for an MIS
/// satisfying its Lemma 2; it is NOT claimed unconditionally for this
/// implementation. See docs/algorithms/li_smis.md.
class LiSMISAlgorithm : public MCDSAlgorithm {
public:
    MCDSResult solve(const PointSet& points, const SpatialIndex& index, double radius) override;

    std::string name() const override { return "li"; }
};

}  // namespace mcds
