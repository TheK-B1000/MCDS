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
#include "algorithms/Funke.hpp"
#include "algorithms/Marathe.hpp"
#include "algorithms/Wan.hpp"

using mcds::FunkeAlgorithm;
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

ValidationResult runFunkeValidate(const PointSet& points) {
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(isConnected(points, index, 1.0));
    FunkeAlgorithm algo;
    const MCDSResult result = algo.solve(points, index, 1.0);
    ValidationOptions opts;
    opts.maxDiagnostics = 32;
    return validateCDS(points, index, result.selectedIds, 1.0, opts);
}

MCDSResult runFunke(const PointSet& points) {
    const GridSpatialIndex index(points, 1.0);
    FunkeAlgorithm algo;
    return algo.solve(points, index, 1.0);
}

}  // namespace

MCDS_TEST(funke_single_vertex) {
    const PointSet points = makePoints({{0.0, 0.0}});
    const ValidationResult v = runFunkeValidate(points);
    MCDS_CHECK(v.valid());
    MCDS_CHECK_EQ(v.selectedCount, std::size_t{1});
    MCDS_CHECK(runFunke(points).selectedIds == std::vector<int>({0}));
}

MCDS_TEST(funke_two_adjacent) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}});
    const ValidationResult v = runFunkeValidate(points);
    MCDS_CHECK(v.valid());
    // Leader 0 blacks; neighbour 1 becomes blue (not in S).
    MCDS_CHECK(runFunke(points).selectedIds == std::vector<int>({0}));
}

MCDS_TEST(funke_path) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}, {3.0, 0.0}});
    const ValidationResult v = runFunkeValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(funke_dense_clique) {
    std::mt19937 rng(3);
    std::uniform_real_distribution<double> dist(0.0, 0.4);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 20; ++i) {
        coords.emplace_back(dist(rng), dist(rng));
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runFunkeValidate(points);
    MCDS_CHECK(v.valid());
    MCDS_CHECK_EQ(v.selectedCount, std::size_t{1});
}

MCDS_TEST(funke_small_grid) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 4; ++i) {
        for (int j = 0; j < 4; ++j) {
            coords.emplace_back(0.8 * i, 0.8 * j);
        }
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runFunkeValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(funke_corridor) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 15; ++i) {
        coords.emplace_back(0.7 * i, (i % 3) * 0.15);
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runFunkeValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(funke_cluster_bridge) {
    // Two clusters joined by a bridge point (spacing keeps UDG connected).
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 6; ++i) {
        coords.emplace_back(0.25 * (i % 3), 0.25 * (i / 3));
    }
    coords.emplace_back(1.0, 0.15);  // bridge
    for (int i = 0; i < 6; ++i) {
        coords.emplace_back(1.75 + 0.25 * (i % 3), 0.25 * (i / 3));
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runFunkeValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(funke_perturbed_grid) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 8; ++i) {
        for (int j = 0; j < 6; ++j) {
            coords.emplace_back(0.7 * i + 0.05 * ((i + j) % 3), 0.7 * j);
        }
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runFunkeValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(funke_exact_radius_boundary) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}});
    const ValidationResult v = runFunkeValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(funke_deterministic_and_unique_ids) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 10; ++i) {
        for (int j = 0; j < 8; ++j) {
            coords.emplace_back(0.75 * i, 0.75 * j);
        }
    }
    const PointSet points = makePoints(coords);
    const MCDSResult a = runFunke(points);
    const MCDSResult b = runFunke(points);
    MCDS_CHECK(a.selectedIds == b.selectedIds);

    std::vector<int> ids = a.selectedIds;
    std::sort(ids.begin(), ids.end());
    MCDS_CHECK(std::unique(ids.begin(), ids.end()) == ids.end());
    for (const int id : ids) {
        MCDS_CHECK(points.hasId(id));
    }
    MCDS_CHECK(runFunkeValidate(points).valid());
}

MCDS_TEST(funke_rejects_disconnected) {
    const PointSet points = makePoints({{0.0, 0.0}, {10.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(!isConnected(points, index, 1.0));
    FunkeAlgorithm algo;
    MCDS_CHECK_THROWS(algo.solve(points, index, 1.0));
}

MCDS_TEST(funke_name_stable) {
    FunkeAlgorithm algo;
    MCDS_CHECK_EQ(algo.name(), std::string("funke"));
}

MCDS_TEST(funke_marathe_wan_shared_input_all_valid) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 12; ++i) {
        coords.emplace_back(0.8 * i, (i % 2) * 0.2);
    }
    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(isConnected(points, index, 1.0));

    MaratheAlgorithm marathe;
    WanAlgorithm wan;
    FunkeAlgorithm funke;
    const MCDSResult m = marathe.solve(points, index, 1.0);
    const MCDSResult w = wan.solve(points, index, 1.0);
    const MCDSResult f = funke.solve(points, index, 1.0);

    ValidationOptions opts;
    opts.maxDiagnostics = 16;
    MCDS_CHECK(validateCDS(points, index, m.selectedIds, 1.0, opts).valid());
    MCDS_CHECK(validateCDS(points, index, w.selectedIds, 1.0, opts).valid());
    MCDS_CHECK(validateCDS(points, index, f.selectedIds, 1.0, opts).valid());

    // Record sizes; do not assert ordering between heuristics.
    MCDS_CHECK(m.selectedIds.size() >= 1);
    MCDS_CHECK(w.selectedIds.size() >= 1);
    MCDS_CHECK(f.selectedIds.size() >= 1);
}

MCDS_TEST_MAIN()
