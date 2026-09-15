#pragma once

// ###########################################################################
// # ExactSmallMCDS — TEST / ANALYSIS ONLY                                     #
// #                                                                            #
// # Exhaustive minimum connected dominating set for tiny n (default n <= 20). #
// # May build an explicit adjacency list because n is intentionally tiny.     #
// # Must NEVER be used by production Marathe/Wan algorithms or large runs.    #
// ###########################################################################

#include <cstddef>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include "Point.hpp"
#include "PointSet.hpp"

namespace mcds {

struct ExactSmallResult {
    std::size_t optSize = 0;
    std::vector<int> selectedIds;
};

/// Exact MCDS by increasing subset size. Throws if n > maxN or UDG disconnected
/// under the given radius (caller should ensure connectivity for meaningful OPT).
ExactSmallResult exactSmallMCDS(
    const PointSet& points,
    double radius,
    std::size_t maxN = 20
);

}  // namespace mcds
