#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <queue>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "Connectivity.hpp"
#include "GridSpatialIndex.hpp"
#include "Point.hpp"
#include "PointSet.hpp"
#include "SpatialIndex.hpp"
#include "TestHarness.hpp"
#include "algorithms/WanLevelMis.hpp"

using mcds::GridSpatialIndex;
using mcds::Point;
using mcds::PointSet;
using mcds::SpatialIndex;
using mcds::computeWanLevelBasedMis;
using mcds::isConnected;

namespace {

constexpr double kRadius = 1.0;

PointSet makePoints(const std::vector<std::pair<double, double>>& coords) {
    std::vector<Point> points;
    points.reserve(coords.size());
    for (std::size_t i = 0; i < coords.size(); ++i) {
        points.push_back(Point{static_cast<int>(i), coords[i].first, coords[i].second});
    }
    return PointSet(std::move(points));
}

std::vector<int> sortedCopy(std::vector<int> ids) {
    std::sort(ids.begin(), ids.end());
    return ids;
}

std::string formatIds(const std::vector<int>& ids) {
    std::ostringstream out;
    out << '[';
    for (std::size_t i = 0; i < ids.size(); ++i) {
        if (i != 0) {
            out << ',';
        }
        out << ids[i];
    }
    out << ']';
    return out.str();
}

std::string formatCoords(const std::vector<std::pair<double, double>>& coords) {
    std::ostringstream out;
    out.setf(std::ios::fixed);
    out.precision(6);
    for (std::size_t i = 0; i < coords.size(); ++i) {
        out << i << ':' << coords[i].first << ',' << coords[i].second;
        if (i + 1 != coords.size()) {
            out << " | ";
        }
    }
    return out.str();
}

struct BfsLevels {
    std::vector<int> level;
};

BfsLevels buildReferenceLevels(
    const PointSet& points,
    const SpatialIndex& index,
    double radius) {

    const std::size_t n = points.size();
    std::size_t leader = 0;
    for (std::size_t i = 1; i < n; ++i) {
        if (points.idAt(i) < points.idAt(leader)) {
            leader = i;
        }
    }

    BfsLevels tree;
    tree.level.assign(n, -1);
    std::vector<char> visited(n, 0);
    std::queue<std::size_t> queue;
    std::vector<int> neighbors;

    visited[leader] = 1;
    tree.level[leader] = 0;
    queue.push(leader);

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
            tree.level[v] = tree.level[u] + 1;
            queue.push(v);
        }
    }
    return tree;
}

bool rankLess(
    const BfsLevels& tree,
    const PointSet& points,
    std::size_t a,
    std::size_t b) {

    if (tree.level[a] != tree.level[b]) {
        return tree.level[a] < tree.level[b];
    }
    return points.idAt(a) < points.idAt(b);
}

enum class PaperColour : std::uint8_t { White = 0, Black, Gray };

/// Literal centralized simulation of Wan level-based colour marking:
/// WHITE / BLACK / GRAY with rank `(level, ID)`.
///
/// Does not emulate radio messages. Implements the selection rule:
///   - a WHITE node with a BLACK neighbour becomes GRAY
///   - the lowest-ranked WHITE whose lower-ranked neighbours have all
///     resolved (not WHITE) becomes BLACK
std::vector<int> paperWanMisReference(
    const PointSet& points,
    const SpatialIndex& index,
    double radius) {

    const std::size_t n = points.size();
    if (n == 0) {
        return {};
    }

    const BfsLevels tree = buildReferenceLevels(points, index, radius);
    std::vector<PaperColour> colour(n, PaperColour::White);
    std::vector<int> neighbors;

    auto hasBlackNeighbor = [&](std::size_t v) {
        index.radiusQuery(points.idAt(v), radius, neighbors);
        for (const int nid : neighbors) {
            if (colour[points.indexOf(nid)] == PaperColour::Black) {
                return true;
            }
        }
        return false;
    };

    auto lowerRankedResolved = [&](std::size_t v) {
        index.radiusQuery(points.idAt(v), radius, neighbors);
        for (const int nid : neighbors) {
            const std::size_t u = points.indexOf(nid);
            if (!rankLess(tree, points, u, v)) {
                continue;
            }
            if (colour[u] == PaperColour::White) {
                return false;
            }
        }
        return true;
    };

    for (;;) {
        bool grayed = true;
        while (grayed) {
            grayed = false;
            for (std::size_t v = 0; v < n; ++v) {
                if (colour[v] != PaperColour::White) {
                    continue;
                }
                if (hasBlackNeighbor(v)) {
                    colour[v] = PaperColour::Gray;
                    grayed = true;
                }
            }
        }

        std::size_t best = n;
        for (std::size_t v = 0; v < n; ++v) {
            if (colour[v] != PaperColour::White) {
                continue;
            }
            if (!lowerRankedResolved(v)) {
                continue;
            }
            if (best == n || rankLess(tree, points, v, best)) {
                best = v;
            }
        }

        if (best == n) {
            break;
        }
        colour[best] = PaperColour::Black;
    }

    std::vector<int> ids;
    for (std::size_t i = 0; i < n; ++i) {
        if (colour[i] == PaperColour::Black) {
            ids.push_back(points.idAt(i));
        } else if (colour[i] == PaperColour::White) {
            // Selection rule failed to resolve the graph.
            throw std::runtime_error(
                "paperWanMisReference: unresolved WHITE vertex id=" +
                std::to_string(points.idAt(i)));
        }
    }
    return ids;
}

bool isIndependent(
    const PointSet& points,
    const SpatialIndex& index,
    double radius,
    const std::vector<int>& mis) {

    std::vector<char> inMis(points.size(), 0);
    for (const int id : mis) {
        inMis[points.indexOf(id)] = 1;
    }
    std::vector<int> neighbors;
    for (const int id : mis) {
        index.radiusQuery(id, radius, neighbors);
        for (const int nid : neighbors) {
            if (inMis[points.indexOf(nid)]) {
                return false;
            }
        }
    }
    return true;
}

bool isMaximal(
    const PointSet& points,
    const SpatialIndex& index,
    double radius,
    const std::vector<int>& mis) {

    std::vector<char> inMis(points.size(), 0);
    for (const int id : mis) {
        inMis[points.indexOf(id)] = 1;
    }
    std::vector<int> neighbors;
    for (std::size_t i = 0; i < points.size(); ++i) {
        if (inMis[i]) {
            continue;
        }
        index.radiusQuery(points.idAt(i), radius, neighbors);
        bool covered = false;
        for (const int nid : neighbors) {
            if (inMis[points.indexOf(nid)]) {
                covered = true;
                break;
            }
        }
        if (!covered) {
            return false;
        }
    }
    return true;
}

bool shareCommonNeighbor(
    const SpatialIndex& index,
    double radius,
    int idA,
    int idB) {

    std::vector<int> neighborsA;
    std::vector<int> neighborsB;
    index.radiusQuery(idA, radius, neighborsA);
    index.radiusQuery(idB, radius, neighborsB);
    std::sort(neighborsA.begin(), neighborsA.end());
    std::sort(neighborsB.begin(), neighborsB.end());
    std::size_t i = 0;
    std::size_t j = 0;
    while (i < neighborsA.size() && j < neighborsB.size()) {
        if (neighborsA[i] == neighborsB[j]) {
            return true;
        }
        if (neighborsA[i] < neighborsB[j]) {
            ++i;
        } else {
            ++j;
        }
    }
    return false;
}

/// Li Lemma 2 test: the distance-2 graph H over MIS vertices is connected.
/// Edge (u,v) in H iff UDG distance is exactly 2 (common neighbour; not adjacent).
bool satisfiesLiLemma2(
    const PointSet& points,
    const SpatialIndex& index,
    double radius,
    const std::vector<int>& mis) {

    const std::size_t m = mis.size();
    if (m <= 1) {
        return true;
    }
    (void)points;

    std::vector<std::vector<std::size_t>> adj(m);
    for (std::size_t i = 0; i < m; ++i) {
        for (std::size_t j = i + 1; j < m; ++j) {
            if (shareCommonNeighbor(index, radius, mis[i], mis[j])) {
                adj[i].push_back(j);
                adj[j].push_back(i);
            }
        }
    }

    std::vector<char> seen(m, 0);
    std::queue<std::size_t> q;
    seen[0] = 1;
    q.push(0);
    std::size_t visited = 0;
    while (!q.empty()) {
        const std::size_t u = q.front();
        q.pop();
        ++visited;
        for (const std::size_t v : adj[u]) {
            if (seen[v]) {
                continue;
            }
            seen[v] = 1;
            q.push(v);
        }
    }
    return visited == m;
}

struct Counterexample {
    bool found = false;
    std::string reason;
    std::string label;
    std::vector<std::pair<double, double>> coords;
    std::vector<int> production;
    std::vector<int> reference;
};

void setCounterexample(
    Counterexample& cx,
    const std::string& reason,
    const std::string& label,
    const std::vector<std::pair<double, double>>& coords,
    const std::vector<int>& production,
    const std::vector<int>& reference) {

    if (cx.found) {
        return;
    }
    cx.found = true;
    cx.reason = reason;
    cx.label = label;
    cx.coords = coords;
    cx.production = production;
    cx.reference = reference;
}

bool verifyInstance(
    Counterexample& cx,
    const std::string& label,
    const std::vector<std::pair<double, double>>& coords) {

    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, kRadius);
    if (!isConnected(points, index, kRadius)) {
        setCounterexample(cx, "input UDG not connected", label, coords, {}, {});
        return false;
    }

    std::vector<int> production;
    std::vector<int> reference;
    try {
        production = sortedCopy(computeWanLevelBasedMis(points, index, kRadius));
        reference = sortedCopy(paperWanMisReference(points, index, kRadius));
    } catch (const std::exception& e) {
        setCounterexample(cx, std::string("exception: ") + e.what(), label, coords, production, reference);
        return false;
    }

    if (production != reference) {
        setCounterexample(
            cx,
            "production MIS != paper reference MIS",
            label,
            coords,
            production,
            reference);
        return false;
    }
    if (!isIndependent(points, index, kRadius, production)) {
        setCounterexample(cx, "MIS not independent", label, coords, production, reference);
        return false;
    }
    if (!isMaximal(points, index, kRadius, production)) {
        setCounterexample(cx, "MIS not maximal", label, coords, production, reference);
        return false;
    }
    if (!satisfiesLiLemma2(points, index, kRadius, production)) {
        setCounterexample(
            cx,
            "Li Lemma 2 failed (distance-2 MIS graph not connected)",
            label,
            coords,
            production,
            reference);
        return false;
    }
    return true;
}

double sideForDensity(int n, double density) {
    return std::sqrt(static_cast<double>(n) / density);
}

std::vector<std::pair<double, double>> genUniform(int n, std::mt19937& rng, double side) {
    std::uniform_real_distribution<double> dist(0.0, side);
    std::vector<std::pair<double, double>> coords;
    coords.reserve(static_cast<std::size_t>(n));
    for (int i = 0; i < n; ++i) {
        coords.emplace_back(dist(rng), dist(rng));
    }
    return coords;
}

std::vector<std::pair<double, double>> genClustered(
    int n,
    std::mt19937& rng,
    double side,
    int clusters,
    double spread) {

    std::uniform_real_distribution<double> center(0.0, side);
    std::normal_distribution<double> jitter(0.0, spread);
    std::vector<std::pair<double, double>> centers;
    centers.reserve(static_cast<std::size_t>(clusters));
    for (int c = 0; c < clusters; ++c) {
        centers.emplace_back(center(rng), center(rng));
    }
    std::vector<std::pair<double, double>> coords;
    coords.reserve(static_cast<std::size_t>(n));
    for (int i = 0; i < n; ++i) {
        const auto& c = centers[static_cast<std::size_t>(i % clusters)];
        double x = std::min(side, std::max(0.0, c.first + jitter(rng)));
        double y = std::min(side, std::max(0.0, c.second + jitter(rng)));
        coords.emplace_back(x, y);
    }
    return coords;
}

std::vector<std::pair<double, double>> genPerturbedGrid(int n, std::mt19937& rng, double density) {
    const double spacing = 1.0 / std::sqrt(density);
    const int cols = std::max(1, static_cast<int>(std::ceil(std::sqrt(static_cast<double>(n)))));
    const int rows = std::max(1, static_cast<int>(std::ceil(static_cast<double>(n) / cols)));
    std::uniform_real_distribution<double> jitter(-0.2 * spacing, 0.2 * spacing);
    std::vector<std::pair<double, double>> coords;
    coords.reserve(static_cast<std::size_t>(n));
    for (int r = 0; r < rows && static_cast<int>(coords.size()) < n; ++r) {
        for (int c = 0; c < cols && static_cast<int>(coords.size()) < n; ++c) {
            coords.emplace_back(c * spacing + jitter(rng), r * spacing + jitter(rng));
        }
    }
    return coords;
}

std::vector<std::pair<double, double>> genCorridor(int n, std::mt19937& rng, double density) {
    const double length = static_cast<double>(n) / std::max(1.0, density);
    const double width = 0.4;
    std::uniform_real_distribution<double> xDist(0.0, length);
    std::uniform_real_distribution<double> yDist(0.0, width);
    std::vector<std::pair<double, double>> coords;
    coords.reserve(static_cast<std::size_t>(n));
    for (int i = 0; i < n; ++i) {
        coords.emplace_back(xDist(rng), yDist(rng));
    }
    return coords;
}

std::vector<std::pair<double, double>> genClusterBridge(int n, std::mt19937& rng, double density) {
    // Two compact clusters joined by an explicit unit-radius bridge chain.
    const double xLeft = 0.0;
    const double xRight = 2.4;
    const double y = 0.0;
    const double step = 0.75;  // < radius so the chain is connected
    const int bridge = std::max(2, static_cast<int>(std::ceil((xRight - xLeft) / step)) + 1);
    const int remaining = std::max(0, n - bridge);
    const int left = remaining / 2;
    const int right = remaining - left;
    std::normal_distribution<double> jitter(0.0, 0.18);

    std::vector<std::pair<double, double>> coords;
    coords.reserve(static_cast<std::size_t>(n));

    for (int i = 0; i < bridge; ++i) {
        const double t = (bridge == 1) ? 0.5 : static_cast<double>(i) / (bridge - 1);
        coords.emplace_back(xLeft + t * (xRight - xLeft), y);
    }

    auto addCluster = [&](int count, double cx, double cy) {
        for (int i = 0; i < count; ++i) {
            coords.emplace_back(cx + jitter(rng), cy + jitter(rng));
        }
    };
    addCluster(left, xLeft, y);
    addCluster(right, xRight, y);

    if (static_cast<int>(coords.size()) > n) {
        coords.resize(static_cast<std::size_t>(n));
    }
    while (static_cast<int>(coords.size()) < n) {
        coords.emplace_back(0.5 * (xLeft + xRight), y);
    }
    (void)density;
    return coords;
}

std::vector<std::pair<double, double>> generateConnected(
    const std::string& dist,
    int n,
    double density,
    int seed) {

    for (int attempt = 0; attempt < 200; ++attempt) {
        std::mt19937 rng(static_cast<std::uint32_t>(seed + 100000 * attempt));
        const double side = sideForDensity(n, density);
        std::vector<std::pair<double, double>> coords;
        if (dist == "uniform") {
            coords = genUniform(n, rng, side);
        } else if (dist == "clustered") {
            coords = genClustered(n, rng, side, 4, 0.20);
        } else if (dist == "perturbed_grid") {
            coords = genPerturbedGrid(n, rng, density);
        } else if (dist == "corridor") {
            coords = genCorridor(n, rng, density);
        } else if (dist == "cluster_bridge") {
            coords = genClusterBridge(n, rng, density);
        } else {
            throw std::runtime_error("unknown distribution: " + dist);
        }

        const PointSet points = makePoints(coords);
        const GridSpatialIndex index(points, kRadius);
        if (isConnected(points, index, kRadius)) {
            return coords;
        }
    }
    throw std::runtime_error(
        "failed to generate connected UDG for " + dist + " n=" + std::to_string(n) +
        " density=" + std::to_string(density) + " seed=" + std::to_string(seed));
}

}  // namespace

MCDS_TEST(wan_level_mis_hand_cases) {
    Counterexample cx;
    std::vector<std::pair<std::string, std::vector<std::pair<double, double>>>> cases;

    cases.push_back({"single", {{0.0, 0.0}}});
    cases.push_back({"two_adjacent", {{0.0, 0.0}, {1.0, 0.0}}});
    cases.push_back({"path4", {{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}, {3.0, 0.0}}});
    cases.push_back({"path8", {{0, 0}, {0.9, 0}, {1.8, 0}, {2.7, 0}, {3.6, 0}, {4.5, 0}, {5.4, 0}, {6.3, 0}}});

    // Near-cycle (unit disks along a hexagon ring).
    {
        std::vector<std::pair<double, double>> cycle;
        for (int i = 0; i < 8; ++i) {
            const double a = (2.0 * 3.14159265358979323846 * i) / 8.0;
            cycle.emplace_back(1.2 * std::cos(a), 1.2 * std::sin(a));
        }
        cases.push_back({"cycle8", cycle});
    }

    {
        std::vector<std::pair<double, double>> grid;
        for (int i = 0; i < 5; ++i) {
            for (int j = 0; j < 5; ++j) {
                grid.emplace_back(0.75 * i, 0.75 * j);
            }
        }
        cases.push_back({"grid5x5", grid});
    }

    {
        std::vector<std::pair<double, double>> corridor;
        for (int i = 0; i < 20; ++i) {
            corridor.emplace_back(0.6 * i, (i % 2) * 0.2);
        }
        cases.push_back({"corridor20", corridor});
    }

    {
        // Two clusters linked by a unit-radius bridge chain (must stay connected).
        std::vector<std::pair<double, double>> clustered;
        for (int i = 0; i < 8; ++i) {
            clustered.emplace_back(0.15 * (i % 4), 0.15 * (i / 4));
        }
        for (int i = 0; i < 8; ++i) {
            clustered.emplace_back(2.4 + 0.15 * (i % 4), 0.15 * (i / 4));
        }
        clustered.emplace_back(0.9, 0.05);
        clustered.emplace_back(1.7, 0.05);
        cases.push_back({"cluster_bridge_hand", clustered});
    }

    {
        std::vector<std::pair<double, double>> awkward = {
            {0.0, 0.0},
            {1.0, 0.0},
            {0.5, 0.866},
            {2.0, 0.0},
            {1.5, 0.866},
            {1.0, 1.732},
        };
        cases.push_back({"triangle_pair", awkward});
    }

    int passed = 0;
    for (const auto& c : cases) {
        if (!verifyInstance(cx, c.first, c.second)) {
            break;
        }
        ++passed;
    }

    if (cx.found) {
        std::printf(
            "FIRST COUNTEREXAMPLE\n"
            "  label: %s\n"
            "  reason: %s\n"
            "  production: %s\n"
            "  reference:  %s\n"
            "  coords: %s\n",
            cx.label.c_str(),
            cx.reason.c_str(),
            formatIds(cx.production).c_str(),
            formatIds(cx.reference).c_str(),
            formatCoords(cx.coords).c_str());
    }

    MCDS_CHECK(!cx.found);
    MCDS_CHECK_EQ(passed, static_cast<int>(cases.size()));
}

MCDS_TEST(wan_level_mis_random_6000) {
    const std::vector<std::string> dists = {
        "uniform",
        "clustered",
        "perturbed_grid",
        "corridor",
        "cluster_bridge",
    };
    const std::vector<double> densities = {5.0, 8.0, 12.0};
    const std::vector<int> sizes = {10, 25, 50, 100};
    constexpr int kSeeds = 100;

    Counterexample cx;
    int checked = 0;

    for (const std::string& dist : dists) {
        for (const double density : densities) {
            for (const int n : sizes) {
                for (int seed = 0; seed < kSeeds; ++seed) {
                    if (cx.found) {
                        break;
                    }
                    std::vector<std::pair<double, double>> coords;
                    try {
                        coords = generateConnected(dist, n, density, seed);
                    } catch (const std::exception& e) {
                        setCounterexample(
                            cx,
                            std::string("generator failure: ") + e.what(),
                            dist + "/n=" + std::to_string(n) + "/d=" + std::to_string(density) +
                                "/seed=" + std::to_string(seed),
                            {},
                            {},
                            {});
                        break;
                    }

                    const std::string label = dist + "/n=" + std::to_string(n) +
                                              "/d=" + std::to_string(static_cast<int>(density)) +
                                              "/seed=" + std::to_string(seed);
                    if (!verifyInstance(cx, label, coords)) {
                        break;
                    }
                    ++checked;
                }
                if (cx.found) {
                    break;
                }
            }
            if (cx.found) {
                break;
            }
        }
        if (cx.found) {
            break;
        }
    }

    if (cx.found) {
        std::printf(
            "FIRST COUNTEREXAMPLE\n"
            "  label: %s\n"
            "  reason: %s\n"
            "  production: %s\n"
            "  reference:  %s\n"
            "  coords: %s\n",
            cx.label.c_str(),
            cx.reason.c_str(),
            formatIds(cx.production).c_str(),
            formatIds(cx.reference).c_str(),
            formatCoords(cx.coords).c_str());
    }

    MCDS_CHECK(!cx.found);
    MCDS_CHECK_EQ(checked, 5 * 3 * 4 * 100);
    std::printf(
        "wan_level_mis_random_6000 summary: checked=%d "
        "reference_eq=PASS independence=PASS maximality=PASS lemma2=PASS\n",
        checked);
}

MCDS_TEST_MAIN()
