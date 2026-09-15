#include <utility>
#include <vector>

#include "ExactSmallMCDS.hpp"
#include "GridSpatialIndex.hpp"
#include "Point.hpp"
#include "PointSet.hpp"
#include "TestHarness.hpp"
#include "Validator.hpp"
#include "algorithms/Marathe.hpp"
#include "algorithms/Wan.hpp"

using mcds::exactSmallMCDS;
using mcds::GridSpatialIndex;
using mcds::MaratheAlgorithm;
using mcds::Point;
using mcds::PointSet;
using mcds::validateCDS;
using mcds::WanAlgorithm;

namespace {

PointSet makePoints(const std::vector<std::pair<double, double>>& coords) {
    std::vector<Point> points;
    for (std::size_t i = 0; i < coords.size(); ++i) {
        points.push_back(Point{static_cast<int>(i), coords[i].first, coords[i].second});
    }
    return PointSet(std::move(points));
}

}  // namespace

MCDS_TEST(exact_single_and_path) {
    auto one = exactSmallMCDS(makePoints({{0.0, 0.0}}), 1.0);
    MCDS_CHECK_EQ(one.optSize, std::size_t{1});

    auto path = exactSmallMCDS(makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}, {3.0, 0.0}}), 1.0);
    // Optimal CDS on P4 is size 2.
    MCDS_CHECK_EQ(path.optSize, std::size_t{2});
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}, {3.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(validateCDS(points, index, path.selectedIds, 1.0).valid());
}

MCDS_TEST(exact_clique_is_one) {
    auto opt = exactSmallMCDS(makePoints({{0.0, 0.0}, {0.1, 0.0}, {0.0, 0.1}, {0.1, 0.1}}), 1.0);
    MCDS_CHECK_EQ(opt.optSize, std::size_t{1});
}

MCDS_TEST(exact_rejects_large_n) {
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 21; ++i) {
        coords.emplace_back(0.5 * i, 0.0);
    }
    MCDS_CHECK_THROWS(exactSmallMCDS(makePoints(coords), 1.0, 20));
}

MCDS_TEST(heuristics_at_least_opt_on_tiny) {
    const PointSet points = makePoints({
        {0.0, 0.0}, {0.8, 0.0}, {1.6, 0.0}, {2.4, 0.0},
        {0.0, 0.8}, {0.8, 0.8}, {1.6, 0.8}, {2.4, 0.8},
    });
    const auto opt = exactSmallMCDS(points, 1.0);
    const GridSpatialIndex index(points, 1.0);
    MaratheAlgorithm marathe;
    WanAlgorithm wan;
    const auto m = marathe.solve(points, index, 1.0);
    const auto w = wan.solve(points, index, 1.0);
    MCDS_CHECK(m.selectedIds.size() >= opt.optSize);
    MCDS_CHECK(w.selectedIds.size() >= opt.optSize);
    MCDS_CHECK(validateCDS(points, index, m.selectedIds, 1.0).valid());
    MCDS_CHECK(validateCDS(points, index, w.selectedIds, 1.0).valid());
}

MCDS_TEST_MAIN()
