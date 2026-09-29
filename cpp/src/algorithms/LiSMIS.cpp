#include "algorithms/LiSMIS.hpp"

#include "algorithms/WanLevelMis.hpp"

#include <algorithm>
#include <cstdint>
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

    index.radiusQuery(points.idAt(greyVertex), radius, neighbors);
    componentRoots.clear();

    for (const int neighborId : neighbors) {
        const std::size_t v = points.indexOf(neighborId);

        // Only BLACK neighbors count. S-MIS ignores BLUE-BLUE connections
        // when defining black-blue components.
        if (colour[v] != Colour::Black) {
            continue;
        }
        componentRoots.push_back(dsu.find(static_cast<int>(v)));
    }

    std::sort(componentRoots.begin(), componentRoots.end());
    componentRoots.erase(
        std::unique(componentRoots.begin(), componentRoots.end()),
        componentRoots.end());

    return static_cast<int>(componentRoots.size());
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

    index.radiusQuery(points.idAt(blueVertex), radius, neighbors);

    int firstBlack = -1;
    for (const int neighborId : neighbors) {
        const std::size_t v = points.indexOf(neighborId);
        if (colour[v] != Colour::Black) {
            continue;
        }
        if (firstBlack < 0) {
            firstBlack = static_cast<int>(v);
            continue;
        }
        dsu.unite(firstBlack, static_cast<int>(v));
    }
}

}  // namespace

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
     * ------------------------------------------------
     * STEP 1
     *
     * Wan level-based MIS (not Cheng).
     * MIS nodes are BLACK; all others remain GREY.
     * ------------------------------------------------
     */
    const std::vector<int> misIds = computeWanLevelBasedMis(points, index, radius);

    std::vector<Colour> colour(n, Colour::Grey);
    for (const int id : misIds) {
        colour[points.indexOf(id)] = Colour::Black;
    }

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
    for (int threshold = 5; threshold >= 2; --threshold) {
        for (;;) {
            std::size_t bestVertex = n;
            int bestY = -1;

            for (std::size_t g = 0; g < n; ++g) {
                if (colour[g] != Colour::Grey) {
                    continue;
                }

                const int y = computeY(
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
                 * The centralized Algorithm A only requires a qualifying
                 * grey vertex. For deterministic execution we use the
                 * ranking from the paper's distributed implementation:
                 *   1. larger y
                 *   2. smaller ID
                 */
                if (bestVertex == n || y > bestY ||
                    (y == bestY && points.idAt(g) < points.idAt(bestVertex))) {
                    bestVertex = g;
                    bestY = y;
                }
            }

            if (bestVertex == n) {
                break;
            }

            colour[bestVertex] = Colour::Blue;
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
     * S-MIS CDS = BLACK ∪ BLUE
     */
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
