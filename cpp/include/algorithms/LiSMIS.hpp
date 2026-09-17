#pragma once

#include "MCDSAlgorithm.hpp"

namespace mcds {

/*
 * Li et al. S-MIS algorithm.
 *
 * Step 1:
 * Build the Wan/Cheng-style MIS.
 * The MIS nodes become black.
 *
 * Step 2:
 * Use Li's greedy Steiner Algorithm A
 * to connect the black nodes.
 *
 * Grey nodes are scored by how many different
 * black-blue components they can connect.
 * Selected connector nodes become blue.
 *
 * Blue-blue edges are ignored when calculating
 * the black-blue components, following the paper.
 *
 * Final CDS = black nodes + blue connector nodes.
 *
 * The paper gives the bound:
 * (4.8 + ln(5)) * OPT + 1.2
 *
 * See docs/li.md for the paper interpretation.
 */
class LiSMISAlgorithm : public MCDSAlgorithm {
public:
    MCDSResult solve(
        const PointSet& points,
        const SpatialIndex& index,
        double radius
    ) override;

    std::string name() const override {
        return "li";
    }
};

} // namespace mcds