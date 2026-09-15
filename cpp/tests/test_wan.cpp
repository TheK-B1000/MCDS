#include <algorithm>
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

MCDS_TEST_MAIN()
