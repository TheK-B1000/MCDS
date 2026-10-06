// Differential tests: CGAL backend vs uniform-grid backend vs brute force.
//
// Goal: prove N_CGAL(p) == N_GRID(p) == N_BRUTE(p) for every tested point set,
// query point and radius, and that every MCDS algorithm produces the same output
// through either backend. Failures print everything needed to reproduce.

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <random>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include "BruteForce.hpp"
#include "CgalSpatialIndex.hpp"
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

using mcds::CgalSpatialIndex;
using mcds::GridSpatialIndex;
using mcds::Point;
using mcds::PointSet;

namespace {

constexpr const char* kGeometries[] = {"uniform", "clustered", "perturbed_grid", "corridor", "cluster_bridge"};

std::uint64_t g_graphs = 0;
std::uint64_t g_queries = 0;

/// Deterministic stand-ins for the five project geometries (the Python
/// generators are exercised separately through the bench cross-check).
std::vector<std::pair<double, double>> makeGeometry(const std::string& geometry, int n, double density,
                                                    unsigned seed) {
    std::mt19937_64 rng(seed);
    std::uniform_real_distribution<double> u01(0.0, 1.0);
    std::normal_distribution<double> gauss(0.0, 1.0);
    std::vector<std::pair<double, double>> pts;
    pts.reserve(static_cast<std::size_t>(n));
    const double side = std::sqrt(static_cast<double>(n) / density);
    if (geometry == "uniform") {
        for (int i = 0; i < n; ++i) pts.emplace_back(side * u01(rng), side * u01(rng));
    } else if (geometry == "clustered") {
        std::vector<std::pair<double, double>> centres;
        for (int c = 0; c < 4; ++c) centres.emplace_back(side * u01(rng), side * u01(rng));
        for (int i = 0; i < n; ++i) {
            const auto& c = centres[static_cast<std::size_t>(i) % centres.size()];
            pts.emplace_back(c.first + 0.8 * gauss(rng), c.second + 0.8 * gauss(rng));
        }
    } else if (geometry == "perturbed_grid") {
        const double spacing = 1.0 / std::sqrt(density);
        const int cols = std::max(1, static_cast<int>(std::ceil(std::sqrt(static_cast<double>(n)))));
        for (int i = 0; i < n; ++i) {
            pts.emplace_back((i % cols) * spacing + 0.15 * spacing * (u01(rng) - 0.5),
                             (i / cols) * spacing + 0.15 * spacing * (u01(rng) - 0.5));
        }
    } else if (geometry == "corridor") {
        const double width = 3.0;
        const double length = std::max(width, n / (density * width));
        for (int i = 0; i < n; ++i) pts.emplace_back(length * u01(rng), width * u01(rng));
    } else {  // cluster_bridge
        std::vector<std::pair<double, double>> centres = {{0.0, 0.0}, {6.0, 0.0}, {3.0, 5.0}};
        const int bridge = n / 5;
        for (int i = 0; i < n - bridge; ++i) {
            const auto& c = centres[static_cast<std::size_t>(i) % centres.size()];
            pts.emplace_back(c.first + 0.45 * gauss(rng), c.second + 0.45 * gauss(rng));
        }
        for (int i = 0; i < bridge; ++i) {
            const auto& a = centres[static_cast<std::size_t>(i) % centres.size()];
            const auto& b = centres[(static_cast<std::size_t>(i) + 1) % centres.size()];
            const double t = u01(rng);
            pts.emplace_back(a.first + t * (b.first - a.first) + 0.3 * (u01(rng) - 0.5),
                             a.second + t * (b.second - a.second) + 0.3 * (u01(rng) - 0.5));
        }
    }
    return pts;
}

PointSet toPointSet(const std::vector<std::pair<double, double>>& coords, double dx = 0.0, double dy = 0.0,
                    int idStride = 1) {
    std::vector<Point> pts;
    pts.reserve(coords.size());
    for (std::size_t i = 0; i < coords.size(); ++i) {
        pts.push_back(Point{static_cast<int>(i) * idStride, coords[i].first + dx, coords[i].second + dy});
    }
    return PointSet(std::move(pts));
}

std::string join(const std::vector<int>& v) {
    std::ostringstream s;
    s << '{';
    for (std::size_t i = 0; i < v.size(); ++i) s << (i ? "," : "") << v[i];
    s << '}';
    return s.str();
}

/// Compares all three neighbour sets for every point. Returns mismatches.
int compareAll(const PointSet& pts, double radius, const std::string& context) {
    // The grid's constructor radius only tunes its cell size and must be > 0;
    // queries at any radius (including 0) are part of its contract.
    const GridSpatialIndex grid(pts, radius > 0.0 ? radius : 1.0);
    const CgalSpatialIndex cgal(pts);
    ++g_graphs;
    int mismatches = 0;
    std::vector<int> a;
    std::vector<int> b;
    for (std::size_t i = 0; i < pts.size(); ++i) {
        const int id = pts.idAt(i);
        cgal.radiusQuery(id, radius, a);
        grid.radiusQuery(id, radius, b);
        std::sort(a.begin(), a.end());
        std::sort(b.begin(), b.end());
        const std::vector<int> brute = mcds::test::bruteForceNeighbors(pts, id, radius);
        ++g_queries;
        if (a != brute || b != brute) {
            if (++mismatches <= 3) {
                std::ostringstream m;
                m << context << " radius=" << radius << " point_id=" << id << " CGAL=" << join(a)
                  << " GRID=" << join(b) << " BRUTE=" << join(brute);
                ::mcds::test::Registry::instance().fail(__FILE__, __LINE__, m.str());
            }
        }
    }
    return mismatches;
}

}  // namespace

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

MCDS_TEST(empty_point_set_builds) {
    const PointSet pts;
    const CgalSpatialIndex cgal(pts);
    MCDS_CHECK_EQ(cgal.size(), std::size_t{0});
}

MCDS_TEST(single_point_has_no_neighbours) {
    const PointSet pts({Point{7, 3.0, -2.0}});
    const CgalSpatialIndex cgal(pts);
    MCDS_CHECK(cgal.radiusQuery(7, 1.0).empty());
    MCDS_CHECK_EQ(compareAll(pts, 1.0, "single"), 0);
}

MCDS_TEST(two_points_boundary_inclusive_and_just_outside) {
    const double outside = std::nextafter(1.0, 2.0);
    const PointSet at({Point{0, 0.0, 0.0}, Point{1, 1.0, 0.0}});
    const PointSet out({Point{0, 0.0, 0.0}, Point{1, outside, 0.0}});
    const CgalSpatialIndex ca(at);
    const CgalSpatialIndex co(out);
    MCDS_CHECK(ca.radiusQuery(0, 1.0) == std::vector<int>({1}));  // exactly R: neighbour
    MCDS_CHECK(ca.radiusQuery(1, 1.0) == std::vector<int>({0}));
    MCDS_CHECK(co.radiusQuery(0, 1.0).empty());                    // one ulp beyond R: not
    MCDS_CHECK_EQ(compareAll(at, 1.0, "boundary"), 0);
    MCDS_CHECK_EQ(compareAll(out, 1.0, "just-outside"), 0);
}

MCDS_TEST(boundary_in_every_axis_direction) {
    // Exactly representable distances of 1 along +/-x and +/-y, plus one just outside each.
    const double o = std::nextafter(1.0, 2.0);
    const PointSet pts({Point{0, 0.0, 0.0}, Point{1, 1.0, 0.0}, Point{2, -1.0, 0.0}, Point{3, 0.0, 1.0},
                        Point{4, 0.0, -1.0}, Point{5, o, 0.0}, Point{6, 0.0, -o}, Point{7, 0.5, 0.5}});
    const CgalSpatialIndex cgal(pts);
    MCDS_CHECK(mcds::test::sorted(cgal.radiusQuery(0, 1.0)) == std::vector<int>({1, 2, 3, 4, 7}));
    MCDS_CHECK_EQ(compareAll(pts, 1.0, "axis-boundary"), 0);
}

MCDS_TEST(coincident_points_are_mutual_neighbours) {
    const PointSet pts({Point{10, 2.0, 2.0}, Point{11, 2.0, 2.0}, Point{12, 2.0, 2.0}, Point{13, 9.0, 9.0}});
    const CgalSpatialIndex cgal(pts);
    MCDS_CHECK(mcds::test::sorted(cgal.radiusQuery(10, 1.0)) == std::vector<int>({11, 12}));
    MCDS_CHECK(mcds::test::sorted(cgal.radiusQuery(11, 0.0)) == std::vector<int>({10, 12}));  // r = 0
    MCDS_CHECK(cgal.radiusQuery(13, 1.0).empty());
    MCDS_CHECK_EQ(compareAll(pts, 1.0, "coincident"), 0);
    MCDS_CHECK_EQ(compareAll(pts, 0.0, "coincident-r0"), 0);
}

MCDS_TEST(negative_and_large_magnitude_coordinates) {
    // Distances exactly 1 at |x| = 1e7 (representable), and a dense negative block.
    const PointSet big({Point{0, -1e7, -1e7}, Point{1, -1e7 + 1.0, -1e7}, Point{2, -1e7, -1e7 + 1.0},
                        Point{3, -1e7 + 2.0, -1e7}, Point{4, 1e7, 1e7}, Point{5, 1e7 - 1.0, 1e7}});
    const CgalSpatialIndex cgal(big);
    MCDS_CHECK(mcds::test::sorted(cgal.radiusQuery(0, 1.0)) == std::vector<int>({1, 2}));
    MCDS_CHECK(cgal.radiusQuery(4, 1.0) == std::vector<int>({5}));
    MCDS_CHECK_EQ(compareAll(big, 1.0, "large-magnitude"), 0);
    for (unsigned seed = 1; seed <= 5; ++seed) {
        const auto coords = makeGeometry("uniform", 300, 6.0, seed);
        MCDS_CHECK_EQ(compareAll(toPointSet(coords, -5000.25, -123.5), 1.0, "negative-offset seed=" + std::to_string(seed)), 0);
        MCDS_CHECK_EQ(compareAll(toPointSet(coords, 3.5e6, -2.2e6), 1.0, "large-offset seed=" + std::to_string(seed)), 0);
    }
}

MCDS_TEST(projected_real_world_coordinates_metre_radius) {
    // UTM-like magnitudes (easting ~4.5e5 m, northing ~3.3e6 m), radius 100 m.
    std::mt19937_64 rng(4242);
    std::uniform_real_distribution<double> u(0.0, 2000.0);
    std::vector<std::pair<double, double>> coords;
    for (int i = 0; i < 400; ++i) coords.emplace_back(451000.0 + u(rng), 3302000.0 + u(rng));
    coords.emplace_back(451000.0, 3302000.0);
    coords.emplace_back(451100.0, 3302000.0);  // exactly 100 m east
    coords.emplace_back(451000.0, 3302100.0);  // exactly 100 m north
    const PointSet pts = toPointSet(coords);
    for (const double r : {50.0, 100.0, 250.0}) {
        MCDS_CHECK_EQ(compareAll(pts, r, "projected"), 0);
    }
    const CgalSpatialIndex cgal(pts);
    const std::vector<int> nb = mcds::test::sorted(cgal.radiusQuery(400, 100.0));
    MCDS_CHECK(std::binary_search(nb.begin(), nb.end(), 401));
    MCDS_CHECK(std::binary_search(nb.begin(), nb.end(), 402));
}

MCDS_TEST(non_identity_ids_are_preserved) {
    // Ids 0, 7, 14, ... : CGAL's internal indices must map back to the CSV ids.
    const auto coords = makeGeometry("uniform", 250, 5.0, 77);
    const PointSet pts = toPointSet(coords, 0.0, 0.0, 7);
    MCDS_CHECK(!pts.usesIdentityIds());
    MCDS_CHECK_EQ(compareAll(pts, 1.0, "id-stride-7"), 0);
}

// ---------------------------------------------------------------------------
// Randomised differential sweep over the five geometries
// ---------------------------------------------------------------------------

MCDS_TEST(randomised_sweep_all_geometries_densities_radii) {
    const int sizes[] = {1, 2, 5, 40, 200, 600};
    const double densities[] = {0.5, 2.0, 5.0, 12.0, 40.0};  // sparse ... dense
    const double radii[] = {0.5, 1.0, 1.7, 3.0};
    int mismatches = 0;
    for (const char* geometry : kGeometries) {
        for (const int n : sizes) {
            for (const double d : densities) {
                for (unsigned seed = 1; seed <= 3; ++seed) {
                    const PointSet pts = toPointSet(makeGeometry(geometry, n, d, seed * 1000u + static_cast<unsigned>(n)));
                    for (const double r : radii) {
                        std::ostringstream ctx;
                        ctx << "geometry=" << geometry << " n=" << n << " density=" << d << " seed=" << seed;
                        mismatches += compareAll(pts, r, ctx.str());
                    }
                }
            }
        }
    }
    MCDS_CHECK_EQ(mismatches, 0);
}

// ---------------------------------------------------------------------------
// Algorithm output equivalence: same graph through CGAL and through the grid
// ---------------------------------------------------------------------------
namespace {

struct Summary {
    std::vector<int> ids;
    std::vector<std::pair<int, std::string>> roles;
    bool valid = false;
    std::uint64_t queries = 0;
    std::uint64_t returned = 0;
};

Summary run(mcds::MCDSAlgorithm& algo, const PointSet& pts, mcds::SpatialIndex& index, const GridSpatialIndex& check) {
    index.resetStats();
    mcds::MCDSResult r = algo.solve(pts, index, 1.0);
    Summary s;
    s.queries = index.stats().neighborQueries;
    s.returned = index.stats().neighborsReturned;
    s.ids = mcds::test::sorted(r.selectedIds);
    s.roles = r.roles;
    std::sort(s.roles.begin(), s.roles.end());
    s.valid = mcds::validateCDS(pts, check, r.selectedIds, 1.0).valid();
    return s;
}

/// Returns each query's neighbours in a seeded random order. Used to prove the
/// algorithms do not depend on the (unspecified) order a backend returns.
class ShuffledIndex : public mcds::SpatialIndex {
public:
    ShuffledIndex(const mcds::SpatialIndex& inner, unsigned seed) : inner_(&inner), rng_(seed) {}
    std::size_t size() const override { return inner_->size(); }
    const mcds::QueryStats& stats() const override { return inner_->stats(); }
    void resetStats() override {}
    const char* name() const override { return "shuffled"; }

protected:
    void radiusQueryImpl(int pointId, double radius, std::vector<int>& out) const override {
        inner_->radiusQuery(pointId, radius, out);
        std::shuffle(out.begin(), out.end(), rng_);
    }

private:
    const mcds::SpatialIndex* inner_;
    mutable std::mt19937 rng_;
};

}  // namespace

MCDS_TEST(all_algorithms_identical_through_cgal_and_grid) {
    mcds::MaratheAlgorithm marathe;
    mcds::WanAlgorithm wan;
    mcds::FunkeAlgorithm funke;
    mcds::LiSMISAlgorithm li;
    mcds::MCDSAlgorithm* algos[] = {&marathe, &wan, &funke, &li};
    int graphs = 0;
    for (const char* geometry : kGeometries) {
        for (const double d : {5.0, 8.0, 12.0}) {
            for (unsigned seed = 1; graphs < 1000 && seed <= 80; ++seed) {
                const PointSet pts = toPointSet(makeGeometry(geometry, 30 + static_cast<int>(seed % 7) * 40, d, seed));
                GridSpatialIndex grid(pts, 1.0);
                if (!mcds::isConnected(pts, grid, 1.0)) continue;
                CgalSpatialIndex cgal(pts);
                ++graphs;
                for (mcds::MCDSAlgorithm* algo : algos) {
                    const Summary g = run(*algo, pts, grid, grid);
                    const Summary c = run(*algo, pts, cgal, grid);
                    if (!(g.ids == c.ids && g.roles == c.roles && g.queries == c.queries &&
                          g.returned == c.returned && g.valid && c.valid)) {
                        std::ostringstream m;
                        m << "algorithm=" << algo->name() << " geometry=" << geometry << " density=" << d
                          << " seed=" << seed << " n=" << pts.size() << " grid=" << join(g.ids)
                          << " cgal=" << join(c.ids) << " valid=" << g.valid << "/" << c.valid
                          << " queries=" << g.queries << "/" << c.queries;
                        ::mcds::test::Registry::instance().fail(__FILE__, __LINE__, m.str());
                    }
                }
            }
        }
    }
    std::printf("    algorithm-equivalence graphs: %d (x4 algorithms)\n", graphs);
    MCDS_CHECK(graphs >= 300);
}

MCDS_TEST(algorithms_do_not_depend_on_neighbour_order) {
    mcds::MaratheAlgorithm marathe;
    mcds::WanAlgorithm wan;
    mcds::FunkeAlgorithm funke;
    mcds::LiSMISAlgorithm li;
    mcds::MCDSAlgorithm* algos[] = {&marathe, &wan, &funke, &li};
    int graphs = 0;
    for (const char* geometry : kGeometries) {
        for (unsigned seed = 1; seed <= 30; ++seed) {
            const PointSet pts = toPointSet(makeGeometry(geometry, 150, 8.0, 500u + seed));
            GridSpatialIndex grid(pts, 1.0);
            if (!mcds::isConnected(pts, grid, 1.0)) continue;
            CgalSpatialIndex cgal(pts);
            ++graphs;
            for (mcds::MCDSAlgorithm* algo : algos) {
                const Summary base = run(*algo, pts, cgal, grid);
                for (unsigned s = 1; s <= 3; ++s) {
                    ShuffledIndex shuffled(cgal, seed * 31u + s);
                    mcds::MCDSResult r = algo->solve(pts, shuffled, 1.0);
                    std::vector<std::pair<int, std::string>> roles = r.roles;
                    std::sort(roles.begin(), roles.end());
                    if (mcds::test::sorted(r.selectedIds) != base.ids || roles != base.roles) {
                        std::ostringstream m;
                        m << "order dependence: algorithm=" << algo->name() << " geometry=" << geometry
                          << " seed=" << seed << " shuffle=" << s;
                        ::mcds::test::Registry::instance().fail(__FILE__, __LINE__, m.str());
                    }
                }
            }
        }
    }
    MCDS_CHECK(graphs >= 50);
}

MCDS_TEST(zz_report_counts) {
    std::printf("    differential graphs: %llu, neighbour queries compared (CGAL/grid/brute): %llu\n",
                static_cast<unsigned long long>(g_graphs), static_cast<unsigned long long>(g_queries));
    MCDS_CHECK(g_queries >= 10000);
}

MCDS_TEST_MAIN()
