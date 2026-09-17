#include "algorithms/WanLevelMis.hpp"

#include <algorithm>
#include <cstdint>
#include <queue>
#include <stdexcept>
#include <utility>
#include <vector>

namespace mcds {
namespace {

struct BfsTree {
    std::vector<int> parent;
    std::vector<int> level;
};

BfsTree buildBfsTree(
    const PointSet& points,
    const SpatialIndex& index,
    double radius,
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
        std::sort(neighbors.begin(), neighbors.end());

        for (const int neighborId : neighbors) {
            const std::size_t v = points.indexOf(neighborId);
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
                "computeWanLevelBasedMis: input UDG must be connected");
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

std::vector<int> computeWanLevelBasedMis(
    const PointSet& points,
    const SpatialIndex& index,
    double radius) {

    if (!(radius >= 0.0)) {
        throw std::invalid_argument(
            "computeWanLevelBasedMis: radius must be non-negative");
    }
    if (points.empty()) {
        return {};
    }

    const std::size_t n = points.size();

    std::size_t leader = 0;
    for (std::size_t i = 1; i < n; ++i) {
        if (points.idAt(i) < points.idAt(leader)) {
            leader = i;
        }
    }

    const BfsTree tree = buildBfsTree(points, index, radius, leader);

    std::vector<std::size_t> order(n);
    for (std::size_t i = 0; i < n; ++i) {
        order[i] = i;
    }
    std::sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) {
        return rankLess(
            tree.level[a],
            points.idAt(a),
            tree.level[b],
            points.idAt(b));
    });

    std::vector<char> inMis(n, 0);
    std::vector<int> neighbors;
    for (const std::size_t u : order) {
        index.radiusQuery(points.idAt(u), radius, neighbors);
        bool blocked = false;
        for (const int neighborId : neighbors) {
            if (inMis[points.indexOf(neighborId)]) {
                blocked = true;
                break;
            }
        }
        if (!blocked) {
            inMis[u] = 1;
        }
    }

    std::vector<int> ids;
    ids.reserve(n);
    for (std::size_t i = 0; i < n; ++i) {
        if (inMis[i]) {
            ids.push_back(points.idAt(i));
        }
    }
    return ids;
}

}  // namespace mcds
