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

#include "Connectivity.hpp"
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

/// Brute-force connected-component analysis for TESTING ONLY.
///
/// Builds an implicit adjacency check by scanning all pairs — O(n^2) — and then
/// runs a standard BFS over that oracle. Production code must never call this.
inline ConnectivityResult bruteForceComponents(const PointSet& points, double radius) {
    const std::size_t n = points.size();
    ConnectivityResult result;
    if (n == 0) {
        result.connected = true;
        return result;
    }

    const double radiusSquared = radius * radius;
    std::vector<char> visited(n, 0);

    for (std::size_t seed = 0; seed < n; ++seed) {
        if (visited[seed]) {
            continue;
        }
        std::vector<std::size_t> stack;
        stack.push_back(seed);
        visited[seed] = 1;
        std::size_t size = 0;
        while (!stack.empty()) {
            const std::size_t current = stack.back();
            stack.pop_back();
            ++size;
            const Point& p = points[current];
            for (std::size_t j = 0; j < n; ++j) {
                if (visited[j]) {
                    continue;
                }
                if (distanceSquared(p, points[j]) <= radiusSquared) {
                    visited[j] = 1;
                    stack.push_back(j);
                }
            }
        }
        result.componentSizes.push_back(size);
        result.visitedCount += size;
        if (size == 1) {
            ++result.isolatedCount;
        }
        if (size > result.largestComponent) {
            result.largestComponent = size;
        }
    }
    result.componentCount = result.componentSizes.size();
    result.connected = (result.componentCount <= 1);
    return result;
}

}  // namespace mcds::test
