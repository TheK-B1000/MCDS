#include "algorithms/Wan.hpp"

#include <algorithm>
#include <cstdint>
#include <queue>
#include <stdexcept>
#include <utility>
#include <vector>

namespace mcds {
namespace {

struct WanBfsTree {
    std::vector<int> parent;  // index -> parent index; root -1
    std::vector<int> level;   // index -> depth
};

/// Deterministic BFS tree: ascending neighbour-id scan; first discoverer is parent.
WanBfsTree buildWanBfsTree(const PointSet& points, const SpatialIndex& index, double radius,
                           std::size_t rootIndex) {
    const std::size_t n = points.size();
    WanBfsTree tree;
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
        std::sort(neighbors.begin(), neighbors.end());

        for (const int nid : neighbors) {
            const std::size_t v = points.indexOf(nid);
            if (visited[v]) {
                continue;
            }
            visited[v] = 1;
            tree.parent[v] = static_cast<int>(u);
            tree.level[v] = tree.level[u] + 1;
            queue.push(v);
        }
    }

    for (std::size_t i = 0; i < n; ++i) {
        if (!visited[i]) {
            throw std::invalid_argument(
                "WanAlgorithm: input UDG is not connected; refuse to run");
        }
    }
    return tree;
}

bool rankLess(int levelA, int idA, int levelB, int idB) {
    if (levelA != levelB) {
        return levelA < levelB;
    }
    return idA < idB;
}

}  // namespace

MCDSResult WanAlgorithm::solve(const PointSet& points, const SpatialIndex& index, double radius) {
    if (!(radius >= 0.0)) {
        throw std::invalid_argument("WanAlgorithm: radius must be non-negative");
    }
    if (points.empty()) {
        return MCDSResult{};
    }

    // Leader = smallest point ID (paper allows ID-based leadership).
    std::size_t leader = 0;
    for (std::size_t i = 1; i < points.size(); ++i) {
        if (points.idAt(i) < points.idAt(leader)) {
            leader = i;
        }
    }

    const WanBfsTree tree = buildWanBfsTree(points, index, radius, leader);

    // Order vertices by rank (level, id).
    std::vector<std::size_t> order(points.size());
    for (std::size_t i = 0; i < points.size(); ++i) {
        order[i] = i;
    }
    std::sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) {
        return rankLess(tree.level[a], points.idAt(a), tree.level[b], points.idAt(b));
    });

    // Type-1 blacks: greedy MIS by increasing rank.
    std::vector<char> inMis(points.size(), 0);
    std::vector<int> neighbors;
    for (const std::size_t u : order) {
        index.radiusQuery(points.idAt(u), radius, neighbors);
        bool blocked = false;
        for (const int nid : neighbors) {
            if (inMis[points.indexOf(nid)]) {
                blocked = true;
                break;
            }
        }
        if (!blocked) {
            inMis[u] = 1;
        }
    }

    // CDS = MIS ∪ tree parents of MIS vertices (type-2 connectors).
    std::vector<char> selected(points.size(), 0);
    for (std::size_t i = 0; i < points.size(); ++i) {
        if (!inMis[i]) {
            continue;
        }
        selected[i] = 1;
        if (i != leader) {
            const int p = tree.parent[i];
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
