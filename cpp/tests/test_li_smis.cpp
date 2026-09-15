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
#include "algorithms/LiSMIS.hpp"
#include "algorithms/Marathe.hpp"
#include "algorithms/Wan.hpp"

using mcds::FunkeAlgorithm;
using mcds::GridSpatialIndex;
using mcds::isConnected;
using mcds::LiSMISAlgorithm;
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

ValidationResult runLiValidate(const PointSet& points) {
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(isConnected(points, index, 1.0));
    LiSMISAlgorithm algo;
    const MCDSResult result = algo.solve(points, index, 1.0);
    ValidationOptions opts;
    opts.maxDiagnostics = 32;
    return validateCDS(points, index, result.selectedIds, 1.0, opts);
}

MCDSResult runLi(const PointSet& points) {
    const GridSpatialIndex index(points, 1.0);
    LiSMISAlgorithm algo;
    return algo.solve(points, index, 1.0);
}

}  // namespace

MCDS_TEST(li_single_vertex) {
    const PointSet points = makePoints({{0.0, 0.0}});
    const ValidationResult v = runLiValidate(points);
    MCDS_CHECK(v.valid());
    MCDS_CHECK_EQ(v.selectedCount, std::size_t{1});
    MCDS_CHECK(runLi(points).selectedIds == std::vector<int>({0}));
}

MCDS_TEST(li_two_adjacent) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}});
    const ValidationResult v = runLiValidate(points);
    MCDS_CHECK(v.valid());
    // MIS = {0}; no second black to connect → CDS = {0}.
    MCDS_CHECK(runLi(points).selectedIds == std::vector<int>({0}));
}

MCDS_TEST(li_path) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}, {3.0, 0.0}});
    const ValidationResult v = runLiValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(li_dense_clique) {
    std::mt19937 rng(3);
    std::uniform_real_distribution<double> dist(0.0, 0.4);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 20; ++i) {
        coords.emplace_back(dist(rng), dist(rng));
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runLiValidate(points);
    MCDS_CHECK(v.valid());
    MCDS_CHECK_EQ(v.selectedCount, std::size_t{1});
}

MCDS_TEST(li_small_grid) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 4; ++i) {
        for (int j = 0; j < 4; ++j) {
            coords.emplace_back(0.8 * i, 0.8 * j);
        }
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runLiValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(li_corridor) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 15; ++i) {
        coords.emplace_back(0.7 * i, (i % 3) * 0.15);
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runLiValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(li_cluster_bridge) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 6; ++i) {
        coords.emplace_back(0.25 * (i % 3), 0.25 * (i / 3));
    }
    coords.emplace_back(1.0, 0.15);
    for (int i = 0; i < 6; ++i) {
        coords.emplace_back(1.75 + 0.25 * (i % 3), 0.25 * (i / 3));
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runLiValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(li_perturbed_grid) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 8; ++i) {
        for (int j = 0; j < 6; ++j) {
            coords.emplace_back(0.7 * i + 0.05 * ((i + j) % 3), 0.7 * j);
        }
    }
    const PointSet points = makePoints(coords);
    const ValidationResult v = runLiValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(li_exact_radius_boundary) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}});
    const ValidationResult v = runLiValidate(points);
    MCDS_CHECK(v.valid());
}

MCDS_TEST(li_deterministic_and_unique_ids) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 10; ++i) {
        for (int j = 0; j < 8; ++j) {
            coords.emplace_back(0.75 * i, 0.75 * j);
        }
    }
    const PointSet points = makePoints(coords);
    const MCDSResult a = runLi(points);
    const MCDSResult b = runLi(points);
    MCDS_CHECK(a.selectedIds == b.selectedIds);

    std::vector<int> ids = a.selectedIds;
    std::sort(ids.begin(), ids.end());
    MCDS_CHECK(std::unique(ids.begin(), ids.end()) == ids.end());
    for (const int id : ids) {
        MCDS_CHECK(points.hasId(id));
    }
    MCDS_CHECK(runLiValidate(points).valid());
}

MCDS_TEST(li_rejects_disconnected) {
    const PointSet points = makePoints({{0.0, 0.0}, {10.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(!isConnected(points, index, 1.0));
    LiSMISAlgorithm algo;
    MCDS_CHECK_THROWS(algo.solve(points, index, 1.0));
}

MCDS_TEST(li_name_stable) {
    LiSMISAlgorithm algo;
    MCDS_CHECK_EQ(algo.name(), std::string("li"));
}

MCDS_TEST(li_four_algorithm_shared_input_all_valid) {
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
    LiSMISAlgorithm li;
    const MCDSResult m = marathe.solve(points, index, 1.0);
    const MCDSResult w = wan.solve(points, index, 1.0);
    const MCDSResult f = funke.solve(points, index, 1.0);
    const MCDSResult l = li.solve(points, index, 1.0);

    ValidationOptions opts;
    opts.maxDiagnostics = 16;
    MCDS_CHECK(validateCDS(points, index, m.selectedIds, 1.0, opts).valid());
    MCDS_CHECK(validateCDS(points, index, w.selectedIds, 1.0, opts).valid());
    MCDS_CHECK(validateCDS(points, index, f.selectedIds, 1.0, opts).valid());
    MCDS_CHECK(validateCDS(points, index, l.selectedIds, 1.0, opts).valid());
}

MCDS_TEST_MAIN()
