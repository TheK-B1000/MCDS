#include <algorithm>
#include <cstdint>
#include <random>
#include <string>
#include <utility>
#include <vector>

#include "BruteForce.hpp"
#include "Connectivity.hpp"
#include "GridSpatialIndex.hpp"
#include "Point.hpp"
#include "PointSet.hpp"
#include "TestHarness.hpp"

using mcds::ConnectivityResult;
using mcds::findConnectedComponents;
using mcds::GridSpatialIndex;
using mcds::isConnected;
using mcds::Point;
using mcds::PointSet;
using mcds::test::bruteForceComponents;

namespace {

PointSet makePoints(const std::vector<std::pair<double, double>>& coords) {
    std::vector<Point> points;
    points.reserve(coords.size());
    for (std::size_t i = 0; i < coords.size(); ++i) {
        points.push_back(Point{static_cast<int>(i), coords[i].first, coords[i].second});
    }
    return PointSet(std::move(points));
}

void expectSameComponents(const ConnectivityResult& a, const ConnectivityResult& b, const char* context) {
    MCDS_CHECK_EQ(a.connected, b.connected);
    MCDS_CHECK_EQ(a.visitedCount, b.visitedCount);
    MCDS_CHECK_EQ(a.componentCount, b.componentCount);
    MCDS_CHECK_EQ(a.largestComponent, b.largestComponent);
    MCDS_CHECK_EQ(a.isolatedCount, b.isolatedCount);

    std::vector<std::size_t> as = a.componentSizes;
    std::vector<std::size_t> bs = b.componentSizes;
    std::sort(as.begin(), as.end());
    std::sort(bs.begin(), bs.end());
    if (as != bs) {
        ::mcds::test::Registry::instance().fail(__FILE__, __LINE__,
                                                std::string(context) + ": component size multisets differ");
    }
}

}  // namespace

MCDS_TEST(empty_point_set_is_connected) {
    const PointSet points;
    const GridSpatialIndex index(points, 1.0);
    const ConnectivityResult result = findConnectedComponents(points, index, 1.0);
    MCDS_CHECK(result.connected);
    MCDS_CHECK_EQ(result.componentCount, std::size_t{0});
    MCDS_CHECK_EQ(result.visitedCount, std::size_t{0});
    MCDS_CHECK_EQ(result.isolatedCount, std::size_t{0});
    MCDS_CHECK(isConnected(points, index, 1.0));
}

MCDS_TEST(single_point_is_connected) {
    const PointSet points = makePoints({{0.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    const ConnectivityResult result = findConnectedComponents(points, index, 1.0);
    MCDS_CHECK(result.connected);
    MCDS_CHECK_EQ(result.componentCount, std::size_t{1});
    MCDS_CHECK_EQ(result.largestComponent, std::size_t{1});
    MCDS_CHECK_EQ(result.isolatedCount, std::size_t{1});
}

MCDS_TEST(two_connected_points) {
    const PointSet points = makePoints({{0.0, 0.0}, {0.5, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    const ConnectivityResult result = findConnectedComponents(points, index, 1.0);
    MCDS_CHECK(result.connected);
    MCDS_CHECK_EQ(result.componentCount, std::size_t{1});
    MCDS_CHECK_EQ(result.largestComponent, std::size_t{2});
    MCDS_CHECK_EQ(result.isolatedCount, std::size_t{0});
}

MCDS_TEST(two_disconnected_points) {
    const PointSet points = makePoints({{0.0, 0.0}, {2.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    const ConnectivityResult result = findConnectedComponents(points, index, 1.0);
    MCDS_CHECK(!result.connected);
    MCDS_CHECK_EQ(result.componentCount, std::size_t{2});
    MCDS_CHECK_EQ(result.isolatedCount, std::size_t{2});
}

MCDS_TEST(simple_chain) {
    // 0--1--2--3 at spacing 1.0
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}, {3.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    const ConnectivityResult result = findConnectedComponents(points, index, 1.0);
    MCDS_CHECK(result.connected);
    MCDS_CHECK_EQ(result.componentCount, std::size_t{1});
    MCDS_CHECK_EQ(result.largestComponent, std::size_t{4});
}

MCDS_TEST(exact_distance_one_connects) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(isConnected(points, index, 1.0));

    const PointSet justOutside = makePoints({{0.0, 0.0}, {1.0000001, 0.0}});
    const GridSpatialIndex indexOut(justOutside, 1.0);
    MCDS_CHECK(!isConnected(justOutside, indexOut, 1.0));
}

MCDS_TEST(dense_clique_is_one_component) {
    std::mt19937 rng(99);
    std::uniform_real_distribution<double> coord(0.0, 0.2);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 80; ++i) {
        coords.emplace_back(coord(rng), coord(rng));
    }
    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, 1.0);
    const ConnectivityResult result = findConnectedComponents(points, index, 1.0);
    MCDS_CHECK(result.connected);
    MCDS_CHECK_EQ(result.componentCount, std::size_t{1});
    MCDS_CHECK_EQ(result.largestComponent, std::size_t{80});
}

MCDS_TEST(two_disconnected_clusters) {
    const PointSet points = makePoints({
        {0.0, 0.0}, {0.2, 0.0}, {0.0, 0.2},
        {10.0, 10.0}, {10.2, 10.0}, {10.0, 10.2},
    });
    const GridSpatialIndex index(points, 1.0);
    const ConnectivityResult result = findConnectedComponents(points, index, 1.0);
    MCDS_CHECK(!result.connected);
    MCDS_CHECK_EQ(result.componentCount, std::size_t{2});
    MCDS_CHECK_EQ(result.largestComponent, std::size_t{3});
    MCDS_CHECK_EQ(result.isolatedCount, std::size_t{0});
}

MCDS_TEST(clusters_joined_by_one_bridge_point) {
    // Two clusters joined by a single bridge at x=1.0. Distances along the
    // chain are exactly 1.0, so the UDG is connected. Without the bridge the
    // clusters sit more than a unit apart and form two components.
    const PointSet points = makePoints({
        {0.0, 0.0}, {0.1, 0.0}, {0.0, 0.1},   // cluster A
        {1.0, 0.0},                             // bridge
        {2.0, 0.0}, {2.1, 0.0}, {2.0, 0.1},   // cluster B
    });
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK(isConnected(points, index, 1.0));

    const PointSet withoutBridge = makePoints({
        {0.0, 0.0}, {0.1, 0.0}, {0.0, 0.1},
        {2.0, 0.0}, {2.1, 0.0}, {2.0, 0.1},
    });
    const GridSpatialIndex index2(withoutBridge, 1.0);
    const ConnectivityResult split = findConnectedComponents(withoutBridge, index2, 1.0);
    MCDS_CHECK(!split.connected);
    MCDS_CHECK_EQ(split.componentCount, std::size_t{2});
}

MCDS_TEST(coincident_points_are_connected) {
    const PointSet points = makePoints({{5.0, 5.0}, {5.0, 5.0}, {5.0, 5.0}});
    const GridSpatialIndex index(points, 1.0);
    const ConnectivityResult result = findConnectedComponents(points, index, 1.0);
    MCDS_CHECK(result.connected);
    MCDS_CHECK_EQ(result.componentCount, std::size_t{1});
    MCDS_CHECK_EQ(result.largestComponent, std::size_t{3});
}

MCDS_TEST(differential_against_brute_force_on_small_random) {
    const int seeds[] = {1, 2, 3, 11, 42};
    const int sizes[] = {0, 1, 2, 5, 20, 60, 120};
    const double extents[] = {0.5, 3.0, 8.0, 20.0};

    for (const int seed : seeds) {
        for (const int n : sizes) {
            for (const double extent : extents) {
                std::mt19937 rng(static_cast<unsigned>(seed * 1000 + n * 17));
                std::uniform_real_distribution<double> coord(0.0, extent);
                std::vector<std::pair<double, double>> coords;
                for (int i = 0; i < n; ++i) {
                    coords.emplace_back(coord(rng), coord(rng));
                }
                const PointSet points = makePoints(coords);
                const GridSpatialIndex index(points, 1.0);
                const ConnectivityResult lazy = findConnectedComponents(points, index, 1.0);
                const ConnectivityResult brute = bruteForceComponents(points, 1.0);
                expectSameComponents(lazy, brute, "differential connectivity");
            }
        }
    }
}

MCDS_TEST(rejects_negative_radius) {
    const PointSet points = makePoints({{0.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK_THROWS(findConnectedComponents(points, index, -0.1));
}

MCDS_TEST_MAIN()
