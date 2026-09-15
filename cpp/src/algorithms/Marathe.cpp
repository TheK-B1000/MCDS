#include "algorithms/Marathe.hpp"

#include <algorithm>
#include <cstdint>
#include <queue>
#include <stdexcept>
#include <vector>

namespace mcds {
namespace {

/// Implicit BFS spanning tree. Neighbours are discovered lazily.
///
/// Parent of a newly discovered vertex is the dequeued vertex that first
/// reaches it. Neighbours are always scanned in ascending id order so the
/// discovery sequence (and therefore parents) is deterministic.
struct BfsTree {
    std::vector<int> parent;          // index -> parent index; root has -1
    std::vector<int> level;           // index -> BFS level
    std::vector<std::vector<std::size_t>> levels;  // level -> indices
    int depth = 0;
};

BfsTree buildBfsTree(const PointSet& points, const SpatialIndex& index, double radius,
                     std::size_t rootIndex) {
    const std::size_t n = points.size();
    BfsTree tree;
    tree.parent.assign(n, -1);
    tree.level.assign(n, -1);

    std::vector<char> visited(n, 0);
    std::queue<std::size_t> queue;
    std::vector<int> neighbors;

    visited[rootIndex] = 1;
    tree.level[rootIndex] = 0;
    queue.push(rootIndex);

    while (!queue.empty()) {
        const std::size_t u = queue.front();
        queue.pop();

        index.radiusQuery(points.idAt(u), radius, neighbors);
        // Deterministic discovery: ascending neighbour ids.
        std::sort(neighbors.begin(), neighbors.end());

        for (const int nid : neighbors) {
            const std::size_t v = points.indexOf(nid);
            if (visited[v]) {
                continue;
            }
            visited[v] = 1;
            tree.parent[v] = static_cast<int>(u);
            tree.level[v] = tree.level[u] + 1;
            if (tree.level[v] > tree.depth) {
                tree.depth = tree.level[v];
            }
            queue.push(v);
        }
    }

    // Verify the UDG was connected (every vertex reached).
    for (std::size_t i = 0; i < n; ++i) {
        if (!visited[i]) {
            throw std::invalid_argument(
                "MaratheAlgorithm: input UDG is not connected; refuse to run CDOM");
        }
    }

    tree.levels.assign(static_cast<std::size_t>(tree.depth) + 1, {});
    for (std::size_t i = 0; i < n; ++i) {
        tree.levels[static_cast<std::size_t>(tree.level[i])].push_back(i);
    }
    return tree;
}

/// True if vertex `u` has a neighbour whose index is marked in `isSet`.
bool adjacentToSet(const PointSet& points, const SpatialIndex& index, double radius,
                   std::size_t u, const std::vector<char>& isSet, std::vector<int>& neighbors) {
    index.radiusQuery(points.idAt(u), radius, neighbors);
    for (const int nid : neighbors) {
        if (isSet[points.indexOf(nid)]) {
            return true;
        }
    }
    return false;
}

/// Maximal independent set in the induced subgraph on `candidates`, always
/// pivoting on the remaining candidate with the smallest id.
std::vector<std::size_t> maximalIndependentSet(
    const PointSet& points,
    const SpatialIndex& index,
    double radius,
    std::vector<std::size_t> candidates
) {
    std::sort(candidates.begin(), candidates.end(), [&](std::size_t a, std::size_t b) {
        return points.idAt(a) < points.idAt(b);
    });

    std::vector<char> remaining(points.size(), 0);
    for (const std::size_t idx : candidates) {
        remaining[idx] = 1;
    }

    std::vector<std::size_t> iset;
    std::vector<int> neighbors;

    for (const std::size_t pivot : candidates) {
        if (!remaining[pivot]) {
            continue;
        }
        iset.push_back(pivot);
        remaining[pivot] = 0;
        index.radiusQuery(points.idAt(pivot), radius, neighbors);
        for (const int nid : neighbors) {
            const std::size_t v = points.indexOf(nid);
            if (remaining[v]) {
                remaining[v] = 0;
            }
        }
    }
    return iset;
}

}  // namespace

MCDSResult MaratheAlgorithm::solve(const PointSet& points, const SpatialIndex& index,
                                   double radius) {
    if (!(radius >= 0.0)) {
        throw std::invalid_argument("MaratheAlgorithm: radius must be non-negative");
    }
    if (points.empty()) {
        return MCDSResult{};
    }

    // Deterministic root: smallest input index (id 0 for our generators).
    const std::size_t root = 0;
    const BfsTree tree = buildBfsTree(points, index, radius, root);

    std::vector<char> selected(points.size(), 0);

    // IS_0 = {root}, NS_0 = ∅
    selected[root] = 1;

    std::vector<int> neighbors;
    std::vector<char> currentIs(points.size(), 0);
    currentIs[root] = 1;  // IS_{i-1} for the first iteration

    for (int i = 1; i <= tree.depth; ++i) {
        const auto& levelVerts = tree.levels[static_cast<std::size_t>(i)];

        // remaining = S_i \ DS_i
        std::vector<std::size_t> remaining;
        remaining.reserve(levelVerts.size());
        for (const std::size_t u : levelVerts) {
            if (!adjacentToSet(points, index, radius, u, currentIs, neighbors)) {
                remaining.push_back(u);
            }
        }

        const std::vector<std::size_t> isLevel =
            maximalIndependentSet(points, index, radius, std::move(remaining));

        // Prepare IS_i bitmap for the next iteration; also collect NS_i.
        std::fill(currentIs.begin(), currentIs.end(), 0);
        for (const std::size_t u : isLevel) {
            selected[u] = 1;
            currentIs[u] = 1;

            const int p = tree.parent[u];
            if (p >= 0) {
                selected[static_cast<std::size_t>(p)] = 1;
            }
        }
    }

    MCDSResult result;
    result.selectedIds.reserve(points.size());
    for (std::size_t i = 0; i < points.size(); ++i) {
        if (selected[i]) {
            result.selectedIds.push_back(points.idAt(i));
        }
    }
    return result;
}

}  // namespace mcds
