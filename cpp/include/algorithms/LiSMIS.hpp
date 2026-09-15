#pragma once

#include "MCDSAlgorithm.hpp"

namespace mcds {

/// Li et al. S-MIS CDS (WCMC 2005, Section 3).
///
/// See docs/li.md. Wan/Cheng Lemma-2 MIS, then greedy Steiner Algorithm A
/// (grey→blue by black-blue component count, ignoring blue–blue edges).
/// Paper guarantee: (4.8 + ln 5) · opt + 1.2.
class LiSMISAlgorithm : public MCDSAlgorithm {
public:
    MCDSResult solve(const PointSet& points, const SpatialIndex& index, double radius) override;

    std::string name() const override { return "li"; }
};

}  // namespace mcds
