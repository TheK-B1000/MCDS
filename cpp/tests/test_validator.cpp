#include <utility>
#include <vector>

#include "GridSpatialIndex.hpp"
#include "Point.hpp"
#include "PointSet.hpp"
#include "TestHarness.hpp"
#include "Validator.hpp"

using mcds::GridSpatialIndex;
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

ValidationResult check(const PointSet& points, const std::vector<int>& selected,
                       std::size_t maxDiagnostics = 32) {
    const GridSpatialIndex index(points, 1.0);
    ValidationOptions opts;
    opts.maxDiagnostics = maxDiagnostics;
    return validateCDS(points, index, selected, 1.0, opts);
}

}  // namespace

MCDS_TEST(valid_cds_on_path) {
    // Path 0-1-2-3. Selecting {1, 2} dominates all and is connected.
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}, {3.0, 0.0}});
    const ValidationResult r = check(points, {1, 2});
    MCDS_CHECK(r.dominating);
    MCDS_CHECK(r.connected);
    MCDS_CHECK(r.valid());
    MCDS_CHECK_EQ(r.selectedCount, std::size_t{2});
    MCDS_CHECK_EQ(r.dominatedCount, std::size_t{4});
    MCDS_CHECK(r.undominatedIds.empty());
}

MCDS_TEST(dominating_but_disconnected) {
    // Path 0-1-2-3-4. Selecting {0, 4} dominates nothing in the middle wait:
    // 0 covers 0,1; 4 covers 3,4; point 2 is undominated. Need a longer gap.
    // Use two distant edges: 0-1 and 10-11.
    const PointSet points = makePoints({
        {0.0, 0.0}, {1.0, 0.0},
        {10.0, 0.0}, {11.0, 0.0},
    });
    // Selecting both endpoints of each edge: dominating and disconnected.
    const ValidationResult r = check(points, {0, 1, 2, 3});
    MCDS_CHECK(r.dominating);
    MCDS_CHECK(!r.connected);
    MCDS_CHECK(!r.valid());
    MCDS_CHECK(!r.disconnectedSelectedIds.empty());
}

MCDS_TEST(connected_but_not_dominating) {
    // Path 0-1-2-3. Selecting only {1} is connected but leaves 3 undominated.
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}, {3.0, 0.0}});
    const ValidationResult r = check(points, {1});
    MCDS_CHECK(r.connected);
    MCDS_CHECK(!r.dominating);
    MCDS_CHECK(!r.valid());
    MCDS_CHECK_EQ(r.undominatedIds.size(), std::size_t{1});
    MCDS_CHECK_EQ(r.undominatedIds[0], 3);
}

MCDS_TEST(neither_connected_nor_dominating) {
    // Two spaced triples. Selecting one endpoint from each leaves the far
    // points undominated, and the two selected vertices cannot reach each other.
    const PointSet points = makePoints({
        {0.0, 0.0}, {1.5, 0.0}, {3.0, 0.0},
        {20.0, 0.0}, {21.5, 0.0}, {23.0, 0.0},
    });
    const ValidationResult r = check(points, {0, 3});
    MCDS_CHECK(!r.dominating);
    MCDS_CHECK(!r.connected);
    MCDS_CHECK(!r.valid());
    MCDS_CHECK(r.undominatedIds.size() >= 2);
    MCDS_CHECK(r.disconnectedSelectedIds.size() >= 1);
}

MCDS_TEST(all_vertices_selected) {
    const PointSet points = makePoints({{0.0, 0.0}, {0.5, 0.0}, {5.0, 5.0}});
    // Even with a disconnected UDG, selecting all vertices: dominating yes,
    // connected no (two components).
    const ValidationResult r = check(points, {0, 1, 2});
    MCDS_CHECK(r.dominating);
    MCDS_CHECK(!r.connected);

    const PointSet clique = makePoints({{0.0, 0.0}, {0.3, 0.0}, {0.0, 0.3}});
    const ValidationResult r2 = check(clique, {0, 1, 2});
    MCDS_CHECK(r2.dominating);
    MCDS_CHECK(r2.connected);
}

MCDS_TEST(single_vertex_graph) {
    const PointSet points = makePoints({{0.0, 0.0}});
    const ValidationResult r = check(points, {0});
    MCDS_CHECK(r.valid());
    MCDS_CHECK_EQ(r.selectedCount, std::size_t{1});

    const ValidationResult emptySel = check(points, {});
    MCDS_CHECK(!emptySel.dominating);
    MCDS_CHECK(!emptySel.connected);
}

MCDS_TEST(empty_point_set) {
    const PointSet points;
    const GridSpatialIndex index(points, 1.0);
    const ValidationResult r = validateCDS(points, index, {}, 1.0);
    MCDS_CHECK(r.valid());
}

MCDS_TEST(star_like_geometry) {
    // Centre at origin, leaves on the unit circle axes.
    const PointSet points = makePoints({
        {0.0, 0.0},
        {1.0, 0.0}, {-1.0, 0.0}, {0.0, 1.0}, {0.0, -1.0},
    });
    // Selecting only the centre is a valid CDS.
    const ValidationResult r = check(points, {0});
    MCDS_CHECK(r.valid());
    MCDS_CHECK_EQ(r.selectedCount, std::size_t{1});

    // Selecting only leaves: dominating (each leaf covers centre? leaf covers
    // itself and centre; but opposite leaves are at distance 2, so not covered
    // by each other). Centre is covered by any leaf. Each leaf covers itself.
    // So all leaves selected is dominating and... are leaves connected through
    // each other? No — distance between adjacent leaves is sqrt(2) > 1.
    // So selected leaves alone are disconnected.
    const ValidationResult leaves = check(points, {1, 2, 3, 4});
    MCDS_CHECK(leaves.dominating);
    MCDS_CHECK(!leaves.connected);
}

MCDS_TEST(two_cluster_bridge) {
    // Bridge at 1.0 sits within unit distance of both clusters.
    const PointSet points = makePoints({
        {0.0, 0.0}, {0.2, 0.0},
        {1.0, 0.0},  // bridge
        {1.8, 0.0}, {2.0, 0.0},
    });
    const ValidationResult bridgeOnly = check(points, {2});
    MCDS_CHECK(bridgeOnly.valid());

    // Far representatives dominate via the geometry but are not adjacent, so
    // paths through the unselected bridge must not count as CDS connectivity.
    const ValidationResult ends = check(points, {0, 4});
    MCDS_CHECK(ends.dominating);
    MCDS_CHECK(!ends.connected);
}

MCDS_TEST(boundary_distance_exactly_one) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}, {2.0, 0.0}});
    // Selecting middle covers both ends at exact distance 1.
    const ValidationResult r = check(points, {1});
    MCDS_CHECK(r.valid());
}

MCDS_TEST(diagnostics_are_capped) {
    const PointSet points = makePoints({
        {0.0, 0.0}, {10.0, 0.0}, {20.0, 0.0}, {30.0, 0.0}, {40.0, 0.0},
    });
    ValidationOptions opts;
    opts.maxDiagnostics = 2;
    const GridSpatialIndex index(points, 1.0);
    const ValidationResult r = validateCDS(points, index, {0}, 1.0, opts);
    MCDS_CHECK(!r.dominating);
    MCDS_CHECK_EQ(r.undominatedIds.size(), std::size_t{2});
}

MCDS_TEST(duplicate_selected_ids_are_ignored) {
    const PointSet points = makePoints({{0.0, 0.0}, {1.0, 0.0}});
    const ValidationResult r = check(points, {0, 0, 1, 1});
    MCDS_CHECK(r.valid());
    MCDS_CHECK_EQ(r.selectedCount, std::size_t{2});
}

MCDS_TEST(unknown_selected_id_throws) {
    const PointSet points = makePoints({{0.0, 0.0}});
    const GridSpatialIndex index(points, 1.0);
    MCDS_CHECK_THROWS(validateCDS(points, index, {99}, 1.0));
}

MCDS_TEST_MAIN()
