#include "algorithms/LiSMIS.hpp"

#include <algorithm>
#include <cstdint>
#include <queue>
#include <stdexcept>
#include <utility>
#include <vector>

namespace mcds {
namespace {

enum class Colour : std::uint8_t { Grey = 0, Black, Blue };

struct BfsTree {
    std::vector<int> parent;
    std::vector<int> level;
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
                "LiSMISAlgorithm: input UDG is not connected; refuse to run");
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

struct Dsu {
    std::vector<int> parent;

    explicit Dsu(std::size_t n) : parent(n) {
        for (std::size_t i = 0; i < n; ++i) {
            parent[i] = static_cast<int>(i);
        }
    }

    int find(int x) {
        while (parent[static_cast<std::size_t>(x)] != x) {
            parent[static_cast<std::size_t>(x)] =
                parent[static_cast<std::size_t>(parent[static_cast<std::size_t>(x)])];
            x = parent[static_cast<std::size_t>(x)];
        }
        return x;
    }
};

/// Deterministic union: always attach higher root index under lower root index.
void uniteMinRoot(Dsu& dsu, int a, int b) {
    a = dsu.find(a);
    b = dsu.find(b);
    if (a == b) {
        return;
    }
    if (a > b) {
        std::swap(a, b);
    }
    dsu.parent[static_cast<std::size_t>(b)] = a;
}

int greyScore(const PointSet& points, const SpatialIndex& index, double radius, std::size_t g,
              const std::vector<Colour>& colour, Dsu& dsu, std::vector<int>& neighbors,
              std::vector<int>& rootsScratch) {
    index.radiusQuery(points.idAt(g), radius, neighbors);
    rootsScratch.clear();
    for (const int nid : neighbors) {
        const std::size_t v = points.indexOf(nid);
        if (colour[v] != Colour::Black) {
            continue;
        }
        rootsScratch.push_back(dsu.find(static_cast<int>(v)));
    }
    if (rootsScratch.empty()) {
        return 0;
    }
    std::sort(rootsScratch.begin(), rootsScratch.end());
    rootsScratch.erase(std::unique(rootsScratch.begin(), rootsScratch.end()), rootsScratch.end());
    return static_cast<int>(rootsScratch.size());
}

}  // namespace

MCDSResult LiSMISAlgorithm::solve(const PointSet& points, const SpatialIndex& index, double radius) {
    if (!(radius >= 0.0)) {
        throw std::invalid_argument("LiSMISAlgorithm: radius must be non-negative");
    }
    if (points.empty()) {
        return MCDSResult{};
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
        return rankLess(tree.level[a], points.idAt(a), tree.level[b], points.idAt(b));
    });

    // Step 1: Wan/Cheng MIS → black; others grey.
    std::vector<Colour> colour(n, Colour::Grey);
    std::vector<int> neighbors;
    for (const std::size_t u : order) {
        index.radiusQuery(points.idAt(u), radius, neighbors);
        bool blocked = false;
        for (const int nid : neighbors) {
            if (colour[points.indexOf(nid)] == Colour::Black) {
                blocked = true;
                break;
            }
        }
        if (!blocked) {
            colour[u] = Colour::Black;
        }
    }

    Dsu dsu(n);
    std::vector<int> rootsScratch;
    rootsScratch.reserve(8);

    // Step 2: Algorithm A — greedy Steiner blues.
    for (int i = 5; i >= 2; --i) {
        for (;;) {
            int bestY = -1;
            std::size_t best = n;
            for (std::size_t g = 0; g < n; ++g) {
                if (colour[g] != Colour::Grey) {
                    continue;
                }
                const int y = greyScore(points, index, radius, g, colour, dsu, neighbors, rootsScratch);
                if (y < i) {
                    continue;
                }
                if (bestY < 0 || y > bestY ||
                    (y == bestY && points.idAt(g) < points.idAt(best))) {
                    bestY = y;
                    best = g;
                }
            }
            if (bestY < 0) {
                break;
            }

            colour[best] = Colour::Blue;
            index.radiusQuery(points.idAt(best), radius, neighbors);
            int firstBlack = -1;
            for (const int nid : neighbors) {
                const std::size_t v = points.indexOf(nid);
                if (colour[v] != Colour::Black) {
                    continue;
                }
                if (firstBlack < 0) {
                    firstBlack = static_cast<int>(v);
                } else {
                    uniteMinRoot(dsu, firstBlack, static_cast<int>(v));
                }
            }
        }
    }

    MCDSResult result;
    result.selectedIds.reserve(n);
    for (std::size_t i = 0; i < n; ++i) {
        if (colour[i] == Colour::Black || colour[i] == Colour::Blue) {
            result.selectedIds.push_back(points.idAt(i));
        }
    }
    return result;
}

}  // namespace mcds
