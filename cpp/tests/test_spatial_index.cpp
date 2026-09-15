#include <cstdint>
#include <random>
#include <string>
#include <utility>
#include <vector>

#include "BruteForce.hpp"
#include "GridSpatialIndex.hpp"
#include "Point.hpp"
#include "PointSet.hpp"
#include "SpatialIndex.hpp"
#include "TestHarness.hpp"

using mcds::GridSpatialIndex;
using mcds::Point;
using mcds::PointSet;
using mcds::SpatialIndex;
using mcds::test::bruteForceNeighbors;
using mcds::test::sorted;

namespace {

/// Builds a point set from raw coordinates, assigning ids 0..n-1.
PointSet makePoints(const std::vector<std::pair<double, double>>& coords) {
    std::vector<Point> points;
    points.reserve(coords.size());
    for (std::size_t i = 0; i < coords.size(); ++i) {
        points.push_back(Point{static_cast<int>(i), coords[i].first, coords[i].second});
    }
    return PointSet(std::move(points));
}

/// The core differential check: for every point, the index must agree with the
/// brute-force scan exactly.
void expectMatchesBruteForce(const PointSet& points, const SpatialIndex& index, double radius,
                             const std::string& context) {
    for (const Point& p : points.points()) {
        const std::vector<int> fromIndex = sorted(index.radiusQuery(p.id, radius));
        const std::vector<int> reference = bruteForceNeighbors(points, p.id, radius);
        if (fromIndex != reference) {
            ::mcds::test::Registry::instance().fail(
                __FILE__, __LINE__,
                context + ": mismatch at id " + std::to_string(p.id) + " (index returned " +
                    std::to_string(fromIndex.size()) + " neighbors, brute force " +
                    std::to_string(reference.size()) + ")");
            return;
        }
    }
}

}  // namespace

// --------------------------------------------------------------------------
// The hand-checked configuration from the project specification
// --------------------------------------------------------------------------

MCDS_TEST(specification_example_A_B_C_D) {
    // A=(0,0) B=(0.5,0) C=(1,0) D=(1.01,0)
    // For A with radius 1: B and C are neighbors, D is not.
    const PointSet points = makePoints({{0.0, 0.0}, {0.5, 0.0}, {1.0, 0.0}, {1.01, 0.0}});
    const GridSpatialIndex index(points, 1.0);

    const std::vector<int> aNeighbors = sorted(index.radiusQuery(0, 1.0));
    MCDS_CHECK_EQ(aNeighbors.size(), std::size_t{2});
    MCDS_CHECK(aNeighbors == std::vector<int>({1, 2}));

    // D sees B (0.51), C (0.01) but not A (1.01).
    const std::vector<int> dNeighbors = sorted(index.radiusQuery(3, 1.0));
    MCDS_CHECK(dNeighbors == std::vector<int>({1, 2}));

    expectMatchesBruteForce(points, index, 1.0, "spec example");
}

MCDS_TEST(query_point_is_excluded_from_its_own_neighbors) {
    const PointSet points = makePoints({{0.0, 0.0}, {0.25, 0.0}});
    const GridSpatialIndex index(points, 1.0);

    const std::vector<int> neighbors = index.radiusQuery(0, 1.0);
    MCDS_CHECK_EQ(neighbors.size(), std::size_t{1});
    MCDS_CHECK_EQ(neighbors[0], 1);
}

MCDS_TEST(radius_boundary_is_inclusive_in_every_direction) {
    // Four points at distance exactly 1.0 from the origin point plus one just
    // beyond. The diagonal case uses a Pythagorean triple scaled to length 1 so
    // the squared distance is exact in binary floating point.
    const PointSet points = makePoints({
        {0.0, 0.0},     // 0: origin
        {1.0, 0.0},     // 1: distance 1 exactly
        {-1.0, 0.0},    // 2: distance 1 exactly
        {0.0, 1.0},     // 3: distance 1 exactly
        {0.0, -1.0},    // 4: distance 1 exactly
        {0.6, 0.8},     // 5: 0.36 + 0.64 = 1.0 exactly
        {0.0, 1.0000001} // 6: just outside
    });
    const GridSpatialIndex index(points, 1.0);

    const std::vector<int> neighbors = sorted(index.radiusQuery(0, 1.0));
    MCDS_CHECK(neighbors == std::vector<int>({1, 2, 3, 4, 5}));
    expectMatchesBruteForce(points, index, 1.0, "boundary");
}

MCDS_TEST(duplicate_coordinates_are_mutual_neighbors) {
    // Three points at the identical location plus one far away. Self-exclusion
    // filters the query point only, never everything at distance zero.
    const PointSet points = makePoints({{2.0, 2.0}, {2.0, 2.0}, {2.0, 2.0}, {50.0, 50.0}});
    const GridSpatialIndex index(points, 1.0);

    MCDS_CHECK(sorted(index.radiusQuery(0, 1.0)) == std::vector<int>({1, 2}));
    MCDS_CHECK(sorted(index.radiusQuery(1, 1.0)) == std::vector<int>({0, 2}));
    MCDS_CHECK(index.radiusQuery(3, 1.0).empty());
    expectMatchesBruteForce(points, index, 1.0, "duplicates");
}

MCDS_TEST(isolated_points_return_no_neighbors) {
    const PointSet points = makePoints({{0.0, 0.0}, {10.0, 0.0}, {0.0, 10.0}, {10.0, 10.0}});
    const GridSpatialIndex index(points, 1.0);
    for (const Point& p : points.points()) {
        MCDS_CHECK(index.radiusQuery(p.id, 1.0).empty());
    }
}

MCDS_TEST(single_point_set_has_no_neighbors) {
    const PointSet points = makePoints({{3.0, -4.0}});
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK_EQ(index.size(), std::size_t{1});
    MCDS_CHECK(index.radiusQuery(0, 1.0).empty());
}

MCDS_TEST(dense_cluster_is_a_clique_without_storing_its_edges) {
    // 300 points inside a 0.1 x 0.1 box: every pair is adjacent, so the UDG has
    // 300 * 299 / 2 = 44,850 edges. The index must answer 299 neighbors per
    // query while its own storage stays proportional to n.
    std::mt19937 rng(12345);
    std::uniform_real_distribution<double> coord(0.0, 0.1);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 300; ++i) {
        coords.emplace_back(coord(rng), coord(rng));
    }
    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, 1.0);

    MCDS_CHECK_EQ(index.radiusQuery(0, 1.0).size(), std::size_t{299});
    expectMatchesBruteForce(points, index, 1.0, "dense cluster");

    // Index storage is O(n), nowhere near the 44,850 edges of the graph.
    MCDS_CHECK(index.indexBytes() < 44850 * sizeof(int));
}

MCDS_TEST(negative_coordinates_are_handled) {
    std::mt19937 rng(777);
    std::uniform_real_distribution<double> coord(-10.0, -2.0);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 200; ++i) {
        coords.emplace_back(coord(rng), coord(rng));
    }
    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, 1.0);
    expectMatchesBruteForce(points, index, 1.0, "negative coordinates");
}

MCDS_TEST(large_coordinates_are_handled) {
    // Offsetting a small neighborhood to ~1e6 exercises the origin subtraction.
    std::mt19937 rng(31337);
    std::uniform_real_distribution<double> jitter(0.0, 8.0);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 200; ++i) {
        coords.emplace_back(1'000'000.0 + jitter(rng), -2'500'000.0 + jitter(rng));
    }
    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, 1.0);
    expectMatchesBruteForce(points, index, 1.0, "large coordinates");
}

MCDS_TEST(huge_coordinate_span_forces_larger_cells_but_stays_correct) {
    // Two tight clusters ten million units apart. A grid of radius-sized cells
    // would need 10^14 cells, so the index must enlarge its cells instead of
    // allocating them, and must still answer exactly.
    std::mt19937 rng(4242);
    std::uniform_real_distribution<double> jitter(0.0, 2.0);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 100; ++i) {
        coords.emplace_back(jitter(rng), jitter(rng));
    }
    for (int i = 0; i < 100; ++i) {
        coords.emplace_back(10'000'000.0 + jitter(rng), jitter(rng));
    }
    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, 1.0);

    MCDS_CHECK(index.cellSize() > 1.0);  // the budget must have kicked in
    MCDS_CHECK(static_cast<double>(index.cellCount()) <= 4.0 * 200.0 + 1024.0);
    expectMatchesBruteForce(points, index, 1.0, "huge span");
}

MCDS_TEST(all_points_identical_gives_a_one_cell_grid) {
    const PointSet points = makePoints({{5.0, 5.0}, {5.0, 5.0}, {5.0, 5.0}});
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK_EQ(index.cellsX(), 1);
    MCDS_CHECK_EQ(index.cellsY(), 1);
    MCDS_CHECK_EQ(index.radiusQuery(0, 1.0).size(), std::size_t{2});
}

// --------------------------------------------------------------------------
// Randomised differential testing against brute force
// --------------------------------------------------------------------------

MCDS_TEST(differential_uniform_random_across_seeds_sizes_and_densities) {
    const int seeds[] = {1, 2, 3, 7, 11, 101};
    const int sizes[] = {1, 2, 5, 17, 60, 250, 900};
    const double extents[] = {0.5, 2.0, 5.0, 20.0};  // tight clique .. sparse

    for (const int seed : seeds) {
        for (const int n : sizes) {
            for (const double extent : extents) {
                std::mt19937 rng(static_cast<unsigned>(seed * 1000 + n));
                std::uniform_real_distribution<double> coord(-extent, extent);
                std::vector<std::pair<double, double>> coords;
                for (int i = 0; i < n; ++i) {
                    coords.emplace_back(coord(rng), coord(rng));
                }
                const PointSet points = makePoints(coords);
                const GridSpatialIndex index(points, 1.0);
                expectMatchesBruteForce(points, index, 1.0,
                                        "uniform seed=" + std::to_string(seed) + " n=" + std::to_string(n) +
                                            " extent=" + std::to_string(extent));
            }
        }
    }
}

MCDS_TEST(differential_on_a_grid_where_many_distances_are_exactly_one) {
    // A unit-spaced lattice is the worst case for boundary handling: every
    // orthogonal neighbor sits at distance exactly 1.0.
    std::vector<std::pair<double, double>> coords;
    for (int gx = 0; gx < 12; ++gx) {
        for (int gy = 0; gy < 12; ++gy) {
            coords.emplace_back(static_cast<double>(gx), static_cast<double>(gy));
        }
    }
    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, 1.0);

    // An interior lattice point has exactly 4 orthogonal neighbors at distance 1
    // (the diagonals are at sqrt(2)).
    MCDS_CHECK_EQ(index.radiusQuery(points.idAt(6 * 12 + 6), 1.0).size(), std::size_t{4});
    expectMatchesBruteForce(points, index, 1.0, "unit lattice");
}

MCDS_TEST(differential_on_clustered_input) {
    std::mt19937 rng(9001);
    std::normal_distribution<double> spread(0.0, 0.35);
    std::uniform_real_distribution<double> centerCoord(0.0, 15.0);

    std::vector<std::pair<double, double>> coords;
    for (int cluster = 0; cluster < 8; ++cluster) {
        const double cx = centerCoord(rng);
        const double cy = centerCoord(rng);
        for (int i = 0; i < 40; ++i) {
            coords.emplace_back(cx + spread(rng), cy + spread(rng));
        }
    }
    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, 1.0);
    expectMatchesBruteForce(points, index, 1.0, "clustered");
}

MCDS_TEST(differential_for_radii_other_than_the_index_radius) {
    // The index is tuned for radius 1.0 but must answer any radius correctly,
    // including radii several cells wide and radii below the cell size.
    std::mt19937 rng(55);
    std::uniform_real_distribution<double> coord(0.0, 6.0);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 300; ++i) {
        coords.emplace_back(coord(rng), coord(rng));
    }
    const PointSet points = makePoints(coords);
    const GridSpatialIndex index(points, 1.0);

    for (const double radius : {0.0, 0.05, 0.25, 0.5, 1.0, 1.5, 2.0, 3.7, 12.0}) {
        expectMatchesBruteForce(points, index, radius, "radius=" + std::to_string(radius));
    }
}

// --------------------------------------------------------------------------
// Instrumentation and error handling
// --------------------------------------------------------------------------

MCDS_TEST(stats_count_queries_candidates_and_results) {
    const PointSet points = makePoints({{0.0, 0.0}, {0.5, 0.0}, {1.0, 0.0}, {1.01, 0.0}});
    GridSpatialIndex index(points, 1.0);

    MCDS_CHECK_EQ(index.stats().neighborQueries, std::uint64_t{0});

    index.radiusQuery(0, 1.0);
    MCDS_CHECK_EQ(index.stats().neighborQueries, std::uint64_t{1});
    MCDS_CHECK_EQ(index.stats().neighborsReturned, std::uint64_t{2});
    // Candidates include the query point itself, so at least 3 were examined.
    MCDS_CHECK(index.stats().candidatesExamined >= 3);

    index.radiusQuery(1, 1.0);
    MCDS_CHECK_EQ(index.stats().neighborQueries, std::uint64_t{2});
    MCDS_CHECK_EQ(index.stats().neighborsReturned, std::uint64_t{5});  // 2 + 3

    index.resetStats();
    MCDS_CHECK_EQ(index.stats().neighborQueries, std::uint64_t{0});
    MCDS_CHECK_EQ(index.stats().candidatesExamined, std::uint64_t{0});
    MCDS_CHECK_EQ(index.stats().neighborsReturned, std::uint64_t{0});
}

MCDS_TEST(candidates_examined_never_undercounts_neighbors_returned) {
    std::mt19937 rng(606);
    std::uniform_real_distribution<double> coord(0.0, 10.0);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 500; ++i) {
        coords.emplace_back(coord(rng), coord(rng));
    }
    const PointSet points = makePoints(coords);
    GridSpatialIndex index(points, 1.0);

    for (const Point& p : points.points()) {
        index.radiusQuery(p.id, 1.0);
    }
    MCDS_CHECK_EQ(index.stats().neighborQueries, std::uint64_t{500});
    MCDS_CHECK(index.stats().candidatesExamined >= index.stats().neighborsReturned);
    // Every neighbor relation is symmetric, so the total must be even.
    MCDS_CHECK_EQ(index.stats().neighborsReturned % 2, std::uint64_t{0});
}

MCDS_TEST(buffer_overload_clears_and_reuses_the_caller_vector) {
    const PointSet points = makePoints({{0.0, 0.0}, {0.5, 0.0}, {50.0, 50.0}});
    const GridSpatialIndex index(points, 1.0);

    std::vector<int> buffer{99, 98, 97};
    index.radiusQuery(0, 1.0, buffer);
    MCDS_CHECK(buffer == std::vector<int>({1}));

    index.radiusQuery(2, 1.0, buffer);
    MCDS_CHECK(buffer.empty());
}

MCDS_TEST(rejects_unknown_ids_and_invalid_construction) {
    const PointSet points = makePoints({{0.0, 0.0}, {0.5, 0.0}});
    const GridSpatialIndex index(points, 1.0);

    MCDS_CHECK_THROWS(index.radiusQuery(5, 1.0));
    MCDS_CHECK_THROWS(index.radiusQuery(-1, 1.0));
    MCDS_CHECK_THROWS(index.radiusQuery(0, -1.0));
    MCDS_CHECK_THROWS(GridSpatialIndex(points, 0.0));
    MCDS_CHECK_THROWS(GridSpatialIndex(points, -1.0));
}

MCDS_TEST(empty_point_set_is_indexable) {
    const PointSet points;
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK_EQ(index.size(), std::size_t{0});
    MCDS_CHECK_THROWS(index.radiusQuery(0, 1.0));
}

MCDS_TEST(algorithms_can_use_the_abstract_interface_only) {
    // Compile-time evidence that nothing about the grid leaks into callers: the
    // whole contract is reachable through a SpatialIndex reference.
    const PointSet points = makePoints({{0.0, 0.0}, {0.5, 0.5}, {9.0, 9.0}});
    GridSpatialIndex grid(points, 1.0);
    SpatialIndex& index = grid;

    MCDS_CHECK_EQ(std::string(index.name()), std::string("uniform-grid"));
    MCDS_CHECK_EQ(index.size(), std::size_t{3});
    MCDS_CHECK_EQ(index.radiusQuery(0, 1.0).size(), std::size_t{1});
    MCDS_CHECK_EQ(index.stats().neighborQueries, std::uint64_t{1});
    index.resetStats();
    MCDS_CHECK_EQ(index.stats().neighborQueries, std::uint64_t{0});
}

MCDS_TEST_MAIN()
