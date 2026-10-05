#include <algorithm>
#include <cmath>
#include <queue>
#include <random>
#include <string>
#include <utility>
#include <vector>

#include "Connectivity.hpp"
#include "GridSpatialIndex.hpp"
#include "Point.hpp"
#include "PointSet.hpp"
#include "TestHarness.hpp"
#include "Validator.hpp"
#include "algorithms/Marathe.hpp"
#include "algorithms/Wan.hpp"
#include "algorithms/WanLevelMis.hpp"

using mcds::GridSpatialIndex;
using mcds::isConnected;
using mcds::MaratheAlgorithm;
using mcds::MCDSResult;
using mcds::Point;
using mcds::PointSet;
using mcds::validateCDS;
using mcds::ValidationOptions;
using mcds::ValidationResult;
using mcds::WanAlgorithm;

namespace {

PointSet makePoints(const std::vector<std::pair<double, double>>& coords) {
    std::vector<Point> points;
    points.reserve(coords.size());
    for (std::size_t i = 0; i < coords.size(); ++i) {
        points.push_back(Point{static_cast<int>(i), coords[i].first, coords[i].second});
    }
    return PointSet(std::move(points));
}

ValidationResult runWanValidate(const PointSet& points) {
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(isConnected(points, index, 1.0));
    WanAlgorithm algo;
    const MCDSResult result = algo.solve(points, index, 1.0);
    ValidationOptions opts;
    opts.maxDiagnostics = 32;
    return validateCDS(points, index, result.selectedIds, 1.0, opts);
}

MCDSResult runWan(const PointSet& points) {
    const GridSpatialIndex index(points, 1.0);
    WanAlgorithm algo;
    return algo.solve(points, index, 1.0);
}

}  // namespace

MCDS_TEST(wan_single_vertex) {
    const PointSet points = makePoints({{0.0, 0.0}});
    const ValidationResult v = runWanValidate(points);
    MCDS_CHECK(v.valid());
    MCDS_CHECK_EQ(v.selectedCount, std::size_t{1});
    MCDS_CHECK(runWan(points).selectedIds == std::vector<int>({0}));
}

MCDS_TEST(wan_two_adjacent) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}});
    const ValidationResult v = runWanValidate(points);
    MCDS_CHECK(v.valid());
    // Leader 0 is MIS; child 1 is dominated so not MIS; parent connector of empty
    // extra: CDS is {0} which dominates 1.
    MCDS_CHECK(runWan(points).selectedIds == std::vector<int>({0}));
}

MCDS_TEST(wan_path) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}, {3.0, 0.0}});
    const ValidationResult v = runWanValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(wan_dense_clique) {
    std::mt19937 rng(3);
    std::uniform_real_distribution<double> coord(0.0, 0.2);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 30; ++i) {
        coords.emplace_back(coord(rng), coord(rng));
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runWanValidate(points);
    MCDS_CHECK(v.valid());
    // Clique: MIS is a singleton (the leader), CDS size 1.
    MCDS_CHECK_EQ(v.selectedCount, std::size_t{1});
}

MCDS_TEST(wan_small_grid) {
    std::vector<std::pair<double, double>> coords;
    for (int y = 0; y < 4; ++y) {
        for (int x = 0; x < 4; ++x) {
            coords.emplace_back(static_cast<double>(x), static_cast<double>(y));
        }
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runWanValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(wan_corridor) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 16; ++i) {
        coords.emplace_back(0.8 * i, 0.0);
    }
    const ValidationResult v = runWanValidate(makePoints(coords));
    MCDS_CHECK(v.valid());
}

MCDS_TEST(wan_cluster_bridge) {
    const PointSet points = makePoints({
        {0.0, 0.0}, {0.2, 0.0}, {0.0, 0.2},
        {1.0, 0.0},
        {2.0, 0.0}, {2.2, 0.0}, {2.0, 0.2},
    });
    const ValidationResult v = runWanValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(wan_perturbed_grid_like) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 8; ++i) {
        for (int j = 0; j < 6; ++j) {
            coords.emplace_back(0.7 * i, 0.7 * j);
        }
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runWanValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(wan_exact_radius_boundary) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}});
    const ValidationResult v = runWanValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(wan_deterministic_and_unique_ids) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 10; ++i) {
        for (int j = 0; j < 8; ++j) {
            coords.emplace_back(0.75 * i, 0.75 * j);
        }
    }
    const PointSet points = makePoints(coords);
    const MCDSResult a = runWan(points);
    const MCDSResult b = runWan(points);
    MCDS_CHECK(a.selectedIds == b.selectedIds);

    std::vector<int> ids = a.selectedIds;
    std::sort(ids.begin(), ids.end());
    MCDS_CHECK(std::unique(ids.begin(), ids.end()) == ids.end());
    for (const int id : ids) {
        MCDS_CHECK(points.hasId(id));
    }
    MCDS_CHECK(runWanValidate(points).valid());
}

MCDS_TEST(wan_rejects_disconnected) {
    const PointSet points = makePoints({{0.0, 0.0}, {10.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(!isConnected(points, index, 1.0));
    WanAlgorithm algo;
    MCDS_CHECK_THROWS(algo.solve(points, index, 1.0));
}

MCDS_TEST(wan_name_stable) {
    WanAlgorithm algo;
    MCDS_CHECK_EQ(algo.name(), std::string("wan"));
}

MCDS_TEST(wan_and_marathe_same_input_both_valid) {
    // Connected strip with mild vertical jitter (spacing 0.8 < 1).
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 12; ++i) {
        coords.emplace_back(0.8 * i, (i % 2) * 0.2);
    }
    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(isConnected(points, index, 1.0));

    MaratheAlgorithm marathe;
    WanAlgorithm wan;
    const MCDSResult m = marathe.solve(points, index, 1.0);
    const MCDSResult w = wan.solve(points, index, 1.0);

    ValidationOptions opts;
    opts.maxDiagnostics = 16;
    const ValidationResult vm = validateCDS(points, index, m.selectedIds, 1.0, opts);
    const ValidationResult vw = validateCDS(points, index, w.selectedIds, 1.0, opts);
    MCDS_CHECK(vm.valid());
    MCDS_CHECK(vw.valid());
    MCDS_CHECK(m.selectedIds.size() >= 1);
    MCDS_CHECK(w.selectedIds.size() >= 1);
}

// ---------------------------------------------------------------------------
// Black -> gray pruning (INFOCOM 2002 §VI.A, fourth colour rule).
// ---------------------------------------------------------------------------
namespace {

struct Reference {
    std::vector<char> prePrune;  // type-1 (MIS) ∪ type-2 (tree parents)
    std::vector<char> isMis;
    std::vector<int> level;
};

/// Independent reconstruction of Wan's black set BEFORE pruning: MIS from
/// computeWanLevelBasedMis, BFS tree rebuilt here (ascending-id scan, first
/// discoverer is parent), type-2 = parents of non-leader MIS vertices.
Reference prePruneReference(const PointSet& points, const GridSpatialIndex& index) {
    const std::size_t n = points.size();
    Reference ref;
    ref.prePrune.assign(n, 0);
    ref.isMis.assign(n, 0);
    ref.level.assign(n, -1);
    std::vector<int> parent(n, -1);
    std::queue<std::size_t> q;
    ref.level[0] = 0;  // leader = min id = index 0 for makePoints
    q.push(0);
    while (!q.empty()) {
        const std::size_t u = q.front();
        q.pop();
        std::vector<int> nb = index.radiusQuery(points.idAt(u), 1.0);
        std::sort(nb.begin(), nb.end());
        for (const int id : nb) {
            const std::size_t v = points.indexOf(id);
            if (ref.level[v] < 0) {
                ref.level[v] = ref.level[u] + 1;
                parent[v] = static_cast<int>(u);
                q.push(v);
            }
        }
    }
    for (const int id : mcds::computeWanLevelBasedMis(points, index, 1.0)) {
        const std::size_t v = points.indexOf(id);
        ref.isMis[v] = 1;
        ref.prePrune[v] = 1;
        if (parent[v] >= 0) {
            ref.prePrune[static_cast<std::size_t>(parent[v])] = 1;
        }
    }
    return ref;
}

bool outranks(const Reference& ref, const PointSet& points, std::size_t a, std::size_t b) {
    if (ref.level[a] != ref.level[b]) return ref.level[a] > ref.level[b];
    return points.idAt(a) > points.idAt(b);
}

/// Paper rule applied one node at a time, in a random order, re-evaluated
/// against the CURRENT colouring until nothing changes (asynchronous reading).
std::vector<int> sequentialPruneFixpoint(const PointSet& points, const GridSpatialIndex& index,
                                         const Reference& ref, unsigned seed) {
    std::vector<char> black = ref.prePrune;
    std::vector<std::size_t> order(points.size());
    for (std::size_t i = 0; i < order.size(); ++i) order[i] = i;
    std::mt19937 rng(seed);
    for (bool changed = true; changed;) {
        changed = false;
        std::shuffle(order.begin(), order.end(), rng);
        for (const std::size_t v : order) {
            if (!black[v]) continue;
            const std::vector<int> nb = index.radiusQuery(points.idAt(v), 1.0);
            if (nb.empty()) continue;
            bool ok = true;
            for (const int id : nb) {
                const std::size_t u = points.indexOf(id);
                if (!black[u] || !outranks(ref, points, v, u)) { ok = false; break; }
            }
            if (ok) { black[v] = 0; changed = true; }
        }
    }
    std::vector<int> ids;
    for (std::size_t i = 0; i < black.size(); ++i) if (black[i]) ids.push_back(points.idAt(i));
    return ids;
}

std::vector<int> sortedIds(std::vector<int> ids) {
    std::sort(ids.begin(), ids.end());
    return ids;
}

}  // namespace

MCDS_TEST(wan_pruning_removes_highest_ranked_all_black_leaf) {
    // Path 0 - 1 - 2. MIS {0, 2}; type-2 connector 1 (parent of 2).
    // Node 2: only neighbour 1 is black and lower ranked -> remarked gray.
    const PointSet points = makePoints({{0.0, 0.0}, {0.9, 0.0}, {1.8, 0.0}});
    MCDS_CHECK(sortedIds(runWan(points).selectedIds) == std::vector<int>({0, 1}));
    MCDS_CHECK(runWanValidate(points).valid());
}

MCDS_TEST(wan_pruning_keeps_node_with_a_gray_neighbour) {
    // Path 0-1-2-3: MIS {0, 2}, connector 1; node 2 has gray neighbour 3 -> kept.
    const PointSet points = makePoints({{0.0, 0.0}, {0.9, 0.0}, {1.8, 0.0}, {2.7, 0.0}});
    MCDS_CHECK(sortedIds(runWan(points).selectedIds) == std::vector<int>({0, 1, 2}));
}

MCDS_TEST(wan_pruning_matches_paper_rule_and_is_order_independent) {
    std::mt19937 rng(20261005);
    int instances = 0;
    int prunedTotal = 0;
    for (int trial = 0; trial < 4000 && instances < 1500; ++trial) {
        const int n = 8 + static_cast<int>(rng() % 120);
        const double side = std::sqrt(static_cast<double>(n) / (2.0 + (rng() % 60) / 10.0));
        std::uniform_real_distribution<double> u(0.0, side);
        std::vector<std::pair<double, double>> coords;
        for (int i = 0; i < n; ++i) coords.emplace_back(u(rng), u(rng));
        const PointSet points = makePoints(coords);
        const GridSpatialIndex index(points, 1.0);
        if (!isConnected(points, index, 1.0)) continue;
        ++instances;

        const Reference ref = prePruneReference(points, index);
        WanAlgorithm algo;
        const MCDSResult res = algo.solve(points, index, 1.0);
        const std::vector<int> got = sortedIds(res.selectedIds);

        // Production == paper rule applied asynchronously, for two random orders.
        MCDS_CHECK(got == sequentialPruneFixpoint(points, index, ref, static_cast<unsigned>(trial)));
        MCDS_CHECK(got == sequentialPruneFixpoint(points, index, ref, static_cast<unsigned>(trial) + 7777u));

        // Pruned nodes are type-1 (MIS) only, and the result stays a valid CDS.
        std::vector<char> inGot(points.size(), 0);
        for (const int id : got) inGot[points.indexOf(id)] = 1;
        for (std::size_t v = 0; v < points.size(); ++v) {
            MCDS_CHECK(!inGot[v] || ref.prePrune[v]);
            if (ref.prePrune[v] && !inGot[v]) {
                MCDS_CHECK(ref.isMis[v]);
                ++prunedTotal;
            }
        }
        const ValidationResult v = validateCDS(points, index, res.selectedIds, 1.0);
        MCDS_CHECK(v.valid());
    }
    MCDS_CHECK(instances >= 1000);
    MCDS_CHECK(prunedTotal > 0);  // the rule actually fires on random UDGs
}

MCDS_TEST_MAIN()
