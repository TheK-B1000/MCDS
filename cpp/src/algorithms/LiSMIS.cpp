#include "algorithms/LiSMIS.hpp"

#include <algorithm>
#include <cstdint>
#include <queue>
#include <stdexcept>
#include <utility>
#include <vector>

namespace mcds {

namespace {

enum class Colour : std::uint8_t {
    Grey = 0,
    Black,
    Blue
};

struct BfsTree {
    std::vector<int> parent;
    std::vector<int> level;
};

struct Dsu {
    std::vector<int> parent;

    explicit Dsu(std::size_t n) : parent(n) {
        for (std::size_t i = 0; i < n; ++i) {
            parent[i] = static_cast<int>(i);
        }
    }

    int find(int x) {
        if (parent[static_cast<std::size_t>(x)] != x) {
            parent[static_cast<std::size_t>(x)] =
                find(parent[static_cast<std::size_t>(x)]);
        }

        return parent[static_cast<std::size_t>(x)];
    }

    void unite(int a, int b) {
        a = find(a);
        b = find(b);

        if (a == b) {
            return;
        }

        // Deterministic representative.
        if (a > b) {
            std::swap(a, b);
        }

        parent[static_cast<std::size_t>(b)] = a;
    }
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

        // Deterministic BFS.
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
                "LiSMISAlgorithm: input UDG must be connected");
        }
    }

    return tree;
}

bool rankLess(
    int levelA,
    int idA,
    int levelB,
    int idB) {

    if (levelA != levelB) {
        return levelA < levelB;
    }

    return idA < idB;
}

/*
 * Step 1 of S-MIS.
 *
 * Li et al. do not redefine the MIS construction here.
 * They state that the MIS may be constructed using the
 * Wan/Cheng method and assume the resulting MIS has the
 * required property used in their analysis.
 *
 * This is our deterministic Wan-style realization:
 * BFS rank (level, id), then greedily add a vertex when
 * no previously selected MIS vertex is adjacent to it.
 */
std::vector<Colour> buildMis(
    const PointSet& points,
    const SpatialIndex& index,
    double radius,
    const BfsTree& tree) {

    const std::size_t n = points.size();

    std::vector<std::size_t> order(n);

    for (std::size_t i = 0; i < n; ++i) {
        order[i] = i;
    }

    std::sort(
        order.begin(),
        order.end(),
        [&](std::size_t a, std::size_t b) {
            return rankLess(
                tree.level[a],
                points.idAt(a),
                tree.level[b],
                points.idAt(b));
        });

    std::vector<Colour> colour(n, Colour::Grey);
    std::vector<int> neighbors;

    for (const std::size_t u : order) {
        index.radiusQuery(
            points.idAt(u),
            radius,
            neighbors);

        bool adjacentToBlack = false;

        for (const int neighborId : neighbors) {
            const std::size_t v =
                points.indexOf(neighborId);

            if (colour[v] == Colour::Black) {
                adjacentToBlack = true;
                break;
            }
        }

        if (!adjacentToBlack) {
            colour[u] = Colour::Black;
        }
    }

    return colour;
}

/*
 * Paper definition:
 *
 * y(g) = number of distinct black-blue components
 * adjacent to grey vertex g through BLACK neighbors.
 *
 * Blue-blue edges are deliberately ignored.
 */
int computeY(
    const PointSet& points,
    const SpatialIndex& index,
    double radius,
    std::size_t greyVertex,
    const std::vector<Colour>& colour,
    Dsu& dsu,
    std::vector<int>& neighbors,
    std::vector<int>& componentRoots) {

    index.radiusQuery(
        points.idAt(greyVertex),
        radius,
        neighbors);

    componentRoots.clear();

    for (const int neighborId : neighbors) {
        const std::size_t v =
            points.indexOf(neighborId);

        // This is important:
        // only BLACK neighbors count.
        //
        // S-MIS ignores BLUE-BLUE connections
        // when defining black-blue components.
        if (colour[v] != Colour::Black) {
            continue;
        }

        componentRoots.push_back(
            dsu.find(static_cast<int>(v)));
    }

    std::sort(
        componentRoots.begin(),
        componentRoots.end());

    componentRoots.erase(
        std::unique(
            componentRoots.begin(),
            componentRoots.end()),
        componentRoots.end());

    return static_cast<int>(
        componentRoots.size());
}

/*
 * When a grey vertex becomes blue, every black-blue
 * component adjacent to that vertex is merged.
 */
void mergeTouchedBlackComponents(
    const PointSet& points,
    const SpatialIndex& index,
    double radius,
    std::size_t blueVertex,
    const std::vector<Colour>& colour,
    Dsu& dsu,
    std::vector<int>& neighbors) {

    index.radiusQuery(
        points.idAt(blueVertex),
        radius,
        neighbors);

    int firstBlack = -1;

    for (const int neighborId : neighbors) {
        const std::size_t v =
            points.indexOf(neighborId);

        if (colour[v] != Colour::Black) {
            continue;
        }

        if (firstBlack < 0) {
            firstBlack =
                static_cast<int>(v);

            continue;
        }

        dsu.unite(
            firstBlack,
            static_cast<int>(v));
    }
}

} // namespace

MCDSResult LiSMISAlgorithm::solve(
    const PointSet& points,
    const SpatialIndex& index,
    double radius) {

    if (!(radius >= 0.0)) {
        throw std::invalid_argument(
            "LiSMISAlgorithm: radius must be non-negative");
    }

    if (points.empty()) {
        return MCDSResult{};
    }

    const std::size_t n = points.size();

    /*
     * Choose deterministic leader.
     */
    std::size_t leader = 0;

    for (std::size_t i = 1; i < n; ++i) {
        if (points.idAt(i) < points.idAt(leader)) {
            leader = i;
        }
    }

    /*
     * Construct BFS ranking used by the Wan-style
     * MIS implementation.
     */
    const BfsTree tree =
        buildBfsTree(
            points,
            index,
            radius,
            leader);

    /*
     * ------------------------------------------------
     * STEP 1
     *
     * Construct MIS.
     *
     * MIS nodes are BLACK.
     * All other vertices remain GREY.
     * ------------------------------------------------
     */
    std::vector<Colour> colour =
        buildMis(
            points,
            index,
            radius,
            tree);

    /*
     * Initially each black MIS vertex belongs to its
     * own black-blue component.
     */
    Dsu dsu(n);

    std::vector<int> neighbors;
    std::vector<int> componentRoots;

    componentRoots.reserve(8);

    /*
     * ------------------------------------------------
     * STEP 2
     *
     * Li et al. Algorithm A:
     *
     * for i = 5, 4, 3, 2:
     *
     *     while there exists a GREY vertex adjacent
     *     to at least i BLACK vertices belonging to
     *     different black-blue components:
     *
     *         colour that vertex BLUE
     *
     * ------------------------------------------------
     */
    for (int threshold = 5;
         threshold >= 2;
         --threshold) {

        for (;;) {

            std::size_t bestVertex = n;
            int bestY = -1;

            /*
             * Search all currently GREY vertices.
             */
            for (std::size_t g = 0;
                 g < n;
                 ++g) {

                if (colour[g] != Colour::Grey) {
                    continue;
                }

                const int y =
                    computeY(
                        points,
                        index,
                        radius,
                        g,
                        colour,
                        dsu,
                        neighbors,
                        componentRoots);

                if (y < threshold) {
                    continue;
                }

                /*
                 * The centralized Algorithm A only
                 * requires a qualifying grey vertex.
                 *
                 * For deterministic execution we use
                 * the ranking described later in the
                 * paper's distributed implementation:
                 *
                 *   1. larger y
                 *   2. smaller ID
                 */
                if (
                    bestVertex == n ||
                    y > bestY ||
                    (
                        y == bestY &&
                        points.idAt(g) <
                        points.idAt(bestVertex)
                    )
                ) {
                    bestVertex = g;
                    bestY = y;
                }
            }

            /*
             * No grey vertex meets this threshold.
             * Move from 5 → 4 → 3 → 2.
             */
            if (bestVertex == n) {
                break;
            }

            /*
             * Grey → Blue.
             *
             * This vertex is now a Steiner connector.
             */
            colour[bestVertex] = Colour::Blue;

            /*
             * Merge all black-blue components
             * connected by this new blue vertex.
             *
             * Notice that we merge using BLACK
             * neighbors only.
             *
             * BLUE-BLUE edges remain ignored.
             */
            mergeTouchedBlackComponents(
                points,
                index,
                radius,
                bestVertex,
                colour,
                dsu,
                neighbors);
        }
    }

    /*
     * ------------------------------------------------
     * RESULT
     *
     * S-MIS CDS = BLACK ∪ BLUE
     * ------------------------------------------------
     */
    MCDSResult result;

    result.selectedIds.reserve(n);

    for (std::size_t i = 0;
         i < n;
         ++i) {

        if (
            colour[i] == Colour::Black ||
            colour[i] == Colour::Blue
        ) {
            result.selectedIds.push_back(
                points.idAt(i));
        }
    }

    return result;
}

} // namespace mcds