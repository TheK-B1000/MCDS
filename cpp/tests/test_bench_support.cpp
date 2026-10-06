#include <algorithm>
#include <random>
#include <string>
#include <utility>
#include <vector>

#include "BruteForce.hpp"
#include "GridSpatialIndex.hpp"
#include "Point.hpp"
#include "PointSet.hpp"
#include "TestHarness.hpp"
#include "algorithms/Funke.hpp"
#include "algorithms/LiSMIS.hpp"
#include "algorithms/Marathe.hpp"
#include "algorithms/Wan.hpp"
#include "bench/BenchSupport.hpp"

using mcds::GridSpatialIndex;
using mcds::Point;
using mcds::PointSet;
namespace bench = mcds::bench;

namespace {

PointSet randomPoints(std::size_t n, double side, unsigned seed) {
    std::mt19937 rng(seed);
    std::uniform_real_distribution<double> u(0.0, side);
    std::vector<Point> pts;
    pts.reserve(n);
    for (std::size_t i = 0; i < n; ++i) {
        pts.push_back(Point{static_cast<int>(i), u(rng), u(rng)});
    }
    return PointSet(std::move(pts));
}

/// Dense enough to be connected for the seeds used below.
PointSet connectedRandomPoints(std::size_t n, unsigned seed) {
    for (unsigned s = seed;; ++s) {
        PointSet p = randomPoints(n, std::sqrt(static_cast<double>(n) / 6.0), s);
        GridSpatialIndex g(p, 1.0);
        if (mcds::isConnected(p, g, 1.0)) {
            return p;
        }
    }
}

}  // namespace

MCDS_TEST(graph_stats_match_brute_force) {
    for (unsigned seed = 1; seed <= 6; ++seed) {
        const PointSet pts = randomPoints(300, 8.0, seed);
        const GridSpatialIndex grid(pts, 1.0);
        const bench::GraphStats gs = bench::computeGraphStats(pts, grid, 1.0);

        std::vector<std::size_t> deg(pts.size());
        std::uint64_t sum = 0;
        for (std::size_t i = 0; i < pts.size(); ++i) {
            deg[i] = mcds::test::bruteForceNeighbors(pts, pts.idAt(i), 1.0).size();
            sum += deg[i];
        }
        MCDS_CHECK_EQ(gs.edges, sum / 2);
        MCDS_CHECK_EQ(gs.minDegree, *std::min_element(deg.begin(), deg.end()));
        MCDS_CHECK_EQ(gs.maxDegree, *std::max_element(deg.begin(), deg.end()));
        MCDS_CHECK(std::abs(gs.meanDegree - static_cast<double>(sum) / 300.0) < 1e-12);

        const mcds::ConnectivityResult bf = mcds::test::bruteForceComponents(pts, 1.0);
        MCDS_CHECK_EQ(gs.componentCount, bf.componentCount);
        MCDS_CHECK_EQ(gs.largestComponent, bf.largestComponent);
        MCDS_CHECK_EQ(gs.isolatedCount, bf.isolatedCount);
        MCDS_CHECK_EQ(gs.connected, bf.connected);
        // Degree pass + component pass: exactly 2n queries.
        MCDS_CHECK_EQ(gs.neighborQueries, static_cast<std::uint64_t>(2 * pts.size()));
    }
}

MCDS_TEST(graph_stats_median_and_density_on_known_graph) {
    // Path a-b-c plus isolated d: degrees 1,2,1,0.
    const PointSet pts({Point{0, 0.0, 0.0}, Point{1, 1.0, 0.0}, Point{2, 2.0, 0.0}, Point{3, 9.0, 9.0}});
    const GridSpatialIndex grid(pts, 1.0);
    const bench::GraphStats gs = bench::computeGraphStats(pts, grid, 1.0);
    MCDS_CHECK_EQ(gs.edges, static_cast<std::uint64_t>(2));
    MCDS_CHECK(std::abs(gs.medianDegree - 1.0) < 1e-12);
    MCDS_CHECK(std::abs(gs.graphDensity - (2.0 * 2.0) / (4.0 * 3.0)) < 1e-12);
    MCDS_CHECK_EQ(gs.componentCount, static_cast<std::size_t>(2));
    MCDS_CHECK_EQ(gs.isolatedCount, static_cast<std::size_t>(1));
    MCDS_CHECK(!gs.connected);
}

MCDS_TEST(points_fingerprint_matches_python_reference) {
    // Expected values computed by python/study/fingerprint.py; the same
    // constants are asserted in python/tests/test_study.py.
    const PointSet pts({Point{0, 0.0, 0.0}, Point{1, 0.5, 0.0}, Point{2, 1.0, 0.25}, Point{7, -3.125, 2.0}});
    MCDS_CHECK_EQ(bench::toHex64(bench::pointsFingerprint(pts)), std::string("ad972ec0862f3689"));
    MCDS_CHECK_EQ(bench::toHex64(bench::pointsFingerprint(PointSet{})), std::string("a8c7f832281a39c5"));
}

MCDS_TEST(points_fingerprint_detects_any_change) {
    const PointSet a({Point{0, 0.0, 0.0}, Point{1, 0.5, 0.0}});
    const PointSet b({Point{0, 0.0, 0.0}, Point{1, 0.5000001, 0.0}});
    const PointSet c({Point{1, 0.5, 0.0}, Point{0, 0.0, 0.0}});  // reordered
    MCDS_CHECK(bench::pointsFingerprint(a) != bench::pointsFingerprint(b));
    MCDS_CHECK(bench::pointsFingerprint(a) != bench::pointsFingerprint(c));
}

MCDS_TEST(id_set_fingerprint_is_order_and_duplicate_insensitive) {
    MCDS_CHECK_EQ(bench::idSetFingerprint({3, 1, 2}), bench::idSetFingerprint({1, 2, 3, 3}));
    MCDS_CHECK(bench::idSetFingerprint({1, 2}) != bench::idSetFingerprint({1, 2, 3}));
}

MCDS_TEST(instrumented_index_is_transparent_and_counts_match) {
    const PointSet pts = randomPoints(500, 9.0, 11);
    const GridSpatialIndex raw(pts, 1.0);
    const GridSpatialIndex inner(pts, 1.0);
    bench::InstrumentedSpatialIndex inst(inner, true, &inner);

    std::vector<int> a;
    std::vector<int> b;
    std::uint64_t maxCand = 0;
    std::uint64_t maxNbr = 0;
    std::uint64_t cells = 0;
    for (std::size_t i = 0; i < pts.size(); ++i) {
        const int id = pts.idAt(i);
        const std::uint64_t before = raw.stats().candidatesExamined;
        raw.radiusQuery(id, 1.0, a);
        inst.radiusQuery(id, 1.0, b);
        MCDS_CHECK(a == b);  // identical ids in identical order
        maxCand = std::max<std::uint64_t>(maxCand, raw.stats().candidatesExamined - before);
        maxNbr = std::max<std::uint64_t>(maxNbr, a.size());
        cells += raw.cellsScannedFor(id, 1.0);
        // Distance computations per query = candidates - 1 (self) >= neighbours.
        MCDS_CHECK(raw.stats().candidatesExamined - before >= 1 + a.size());
    }
    MCDS_CHECK_EQ(inst.stats().neighborQueries, raw.stats().neighborQueries);
    MCDS_CHECK_EQ(inst.stats().candidatesExamined, raw.stats().candidatesExamined);
    MCDS_CHECK_EQ(inst.stats().neighborsReturned, raw.stats().neighborsReturned);
    MCDS_CHECK_EQ(inst.extendedStats().maxCandidatesPerQuery, maxCand);
    MCDS_CHECK_EQ(inst.extendedStats().maxNeighborsPerQuery, maxNbr);
    MCDS_CHECK_EQ(inst.extendedStats().cellsExamined, cells);

    inst.resetStats();
    MCDS_CHECK_EQ(inst.stats().neighborQueries, static_cast<std::uint64_t>(0));
    MCDS_CHECK_EQ(inst.extendedStats().cellsExamined, static_cast<std::uint64_t>(0));
}

MCDS_TEST(cells_scanned_is_three_by_three_in_grid_interior) {
    // Regular lattice: cell size == radius, interior points scan 3x3 cells.
    std::vector<Point> pts;
    int id = 0;
    for (int y = 0; y < 10; ++y) {
        for (int x = 0; x < 10; ++x) {
            pts.push_back(Point{id++, x + 0.5, y + 0.5});
        }
    }
    const PointSet ps(std::move(pts));
    const GridSpatialIndex grid(ps, 1.0);
    MCDS_CHECK_EQ(grid.cellsScannedFor(55, 1.0), static_cast<std::size_t>(9));
    MCDS_CHECK_EQ(grid.cellsScannedFor(0, 1.0), static_cast<std::size_t>(4));  // corner
}

MCDS_TEST(algorithms_return_identical_sets_through_instrumented_index) {
    // Instrumentation must not change what any algorithm computes.
    for (unsigned seed = 1; seed <= 4; ++seed) {
        const PointSet pts = connectedRandomPoints(250, seed);
        GridSpatialIndex raw(pts, 1.0);
        const GridSpatialIndex inner(pts, 1.0);
        bench::InstrumentedSpatialIndex inst(inner, false);

        mcds::MaratheAlgorithm marathe;
        mcds::WanAlgorithm wan;
        mcds::FunkeAlgorithm funke;
        mcds::LiSMISAlgorithm li;
        mcds::MCDSAlgorithm* algos[] = {&marathe, &wan, &funke, &li};
        for (mcds::MCDSAlgorithm* algo : algos) {
            raw.resetStats();
            inst.resetStats();
            std::vector<int> x = algo->solve(pts, raw, 1.0).selectedIds;
            std::vector<int> y = algo->solve(pts, inst, 1.0).selectedIds;
            std::sort(x.begin(), x.end());
            std::sort(y.begin(), y.end());
            MCDS_CHECK(x == y);
            MCDS_CHECK_EQ(raw.stats().neighborQueries, inst.stats().neighborQueries);
            MCDS_CHECK_EQ(raw.stats().candidatesExamined, inst.stats().candidatesExamined);
        }
    }
}

MCDS_TEST(process_memory_reports_something_on_supported_platforms) {
    const bench::ProcessMemory m = bench::processMemory();
#if defined(_WIN32) || defined(__linux__)
    MCDS_CHECK(m.available);
    MCDS_CHECK(m.peakRssBytes > 0);
#else
    (void)m;
#endif
}

MCDS_TEST_MAIN()
