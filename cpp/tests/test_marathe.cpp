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

using mcds::GridSpatialIndex;
using mcds::isConnected;
using mcds::MaratheAlgorithm;
using mcds::MCDSResult;
using mcds::Point;
using mcds::PointSet;
using mcds::validateCDS;
using mcds::ValidationOptions;
using mcds::ValidationResult;

namespace {

PointSet makePoints(const std::vector<std::pair<double, double>>& coords) {
    std::vector<Point> points;
    points.reserve(coords.size());
    for (std::size_t i = 0; i < coords.size(); ++i) {
        points.push_back(Point{static_cast<int>(i), coords[i].first, coords[i].second});
    }
    return PointSet(std::move(points));
}

ValidationResult runAndValidate(const PointSet& points) {
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(isConnected(points, index, 1.0));

    MaratheAlgorithm algo;
    const MCDSResult result = algo.solve(points, index, 1.0);

    ValidationOptions opts;
    opts.maxDiagnostics = 32;
    return validateCDS(points, index, result.selectedIds, 1.0, opts);
}

MCDSResult runOnce(const PointSet& points) {
    const GridSpatialIndex index(points, 1.0);
    MaratheAlgorithm algo;
    return algo.solve(points, index, 1.0);
}

}  // namespace

MCDS_TEST(single_vertex) {
    const PointSet points = makePoints({{0.0, 0.0}});
    const ValidationResult v = runAndValidate(points);
    MCDS_CHECK(v.valid());
    MCDS_CHECK_EQ(v.selectedCount, std::size_t{1});

    const MCDSResult r = runOnce(points);
    MCDS_CHECK(r.selectedIds == std::vector<int>({0}));
}

MCDS_TEST(two_vertices) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}});
    const ValidationResult v = runAndValidate(points);
    MCDS_CHECK(v.valid());
    MCDS_CHECK(v.selectedCount >= 1);
    MCDS_CHECK(v.selectedCount <= 2);
}

MCDS_TEST(path_of_four) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}, {3.0, 0.0}});
    const ValidationResult v = runAndValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(small_grid) {
    std::vector<std::pair<double, double>> coords;
    for (int y = 0; y < 4; ++y) {
        for (int x = 0; x < 4; ++x) {
            coords.emplace_back(static_cast<double>(x), static_cast<double>(y));
        }
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runAndValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(dense_clique) {
    std::mt19937 rng(7);
    std::uniform_real_distribution<double> coord(0.0, 0.2);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 40; ++i) {
        coords.emplace_back(coord(rng), coord(rng));
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runAndValidate(points);
    MCDS_CHECK(v.valid());
    // In a clique any singleton dominates and is connected.
    MCDS_CHECK_EQ(v.selectedCount, std::size_t{1});
}

MCDS_TEST(corridor) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 20; ++i) {
        coords.emplace_back(0.8 * i, 0.0);
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runAndValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(cluster_plus_bridge) {
    const PointSet points = makePoints({
        {0.0, 0.0}, {0.2, 0.0}, {0.0, 0.2},
        {1.0, 0.0},
        {2.0, 0.0}, {2.2, 0.0}, {2.0, 0.2},
    });
    const ValidationResult v = runAndValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(deterministic_output) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 12; ++i) {
        for (int j = 0; j < 8; ++j) {
            coords.emplace_back(0.7 * i, 0.7 * j);
        }
    }
    const PointSet points = makePoints(coords);
    const MCDSResult a = runOnce(points);
    const MCDSResult b = runOnce(points);
    MCDS_CHECK(a.selectedIds == b.selectedIds);

    const ValidationResult v = runAndValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(rejects_disconnected_input) {
    const PointSet points = makePoints({{0.0, 0.0}, {10.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(!isConnected(points, index, 1.0));
    MaratheAlgorithm algo;
    MCDS_CHECK_THROWS(algo.solve(points, index, 1.0));
}

MCDS_TEST(empty_point_set) {
    const PointSet points;
    const GridSpatialIndex index(points, 1.0);
    MaratheAlgorithm algo;
    const MCDSResult r = algo.solve(points, index, 1.0);
    MCDS_CHECK(r.selectedIds.empty());
    MCDS_CHECK_EQ(std::string(algo.name()), std::string("marathe"));
}

MCDS_TEST(name_is_stable) {
    MaratheAlgorithm algo;
    MCDS_CHECK_EQ(algo.name(), std::string("marathe"));
}

MCDS_TEST_MAIN()
