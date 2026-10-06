#pragma once

// Test-only verbatim copies of the pre-audit Funke and Li S-MIS
// implementations (commit a5cebd7), which found the next affected vertices by
// scanning every vertex. They are the reference against which the current
// implementations must produce exactly the same output (selected ids, order
// and roles). Never used by the benchmark or any study.

#include "MCDSAlgorithm.hpp"

namespace mcds {

class FunkeFullScanRef : public MCDSAlgorithm {
public:
    MCDSResult solve(const PointSet& points, const SpatialIndex& index, double radius) override;
    std::string name() const override { return "funke_full_scan_ref"; }
};

class LiSMISFullScanRef : public MCDSAlgorithm {
public:
    MCDSResult solve(const PointSet& points, const SpatialIndex& index, double radius) override;
    std::string name() const override { return "li_full_scan_ref"; }
};

}  // namespace mcds
