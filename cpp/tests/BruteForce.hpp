#pragma once

// ###########################################################################
// #  TEST-ONLY REFERENCE IMPLEMENTATION -- NOT FOR USE BY ANY ALGORITHM.    #
// #                                                                          #
// #  This header lives under cpp/tests/ and is not on the include path of    #
// #  the mcds_core library, so production code physically cannot include it. #
// #  It answers a neighbor query by scanning all n points, which is the      #
// #  quadratic behaviour the whole project exists to avoid. Its only purpose #
// #  is to be the ground truth that SpatialIndex implementations are         #
// #  differentially tested against.                                          #
// ###########################################################################

#include <algorithm>
#include <vector>

#include "Point.hpp"
#include "PointSet.hpp"

namespace mcds::test {

/// Ids of every point within `radius` of the point carrying `pointId`, self
/// excluded, sorted ascending. Matches the `SpatialIndex` contract exactly,
/// including the inclusive boundary.
inline std::vector<int> bruteForceNeighbors(const PointSet& points, int pointId, double radius) {
    const Point& p = points[points.indexOf(pointId)];
    const double radiusSquared = radius * radius;

    std::vector<int> result;
    for (const Point& q : points.points()) {
        if (q.id == pointId) {
            continue;
        }
        if (distanceSquared(p, q) <= radiusSquared) {
            result.push_back(q.id);
        }
    }
    std::sort(result.begin(), result.end());
    return result;
}

/// Helper so index results (unspecified order) can be compared against the
/// sorted brute-force answer.
inline std::vector<int> sorted(std::vector<int> ids) {
    std::sort(ids.begin(), ids.end());
    return ids;
}

}  // namespace mcds::test
