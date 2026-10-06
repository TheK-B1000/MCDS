// Output equivalence of the current Funke and Li S-MIS implementations with
// the verbatim pre-audit code (tests/reference/*FullScanRef.cpp, copied from
// commit a5cebd7). The pre-final audit changed only how the next affected
// vertices are found (Funke: frontier-driven Phase III; Li: lazy max-heap selection), so the
// outputs must be identical: same selected ids in the same order and the same
// roles, on both spatial backends, for identity and permuted point ids (all
// tie-breaks are by id), and the same exception on disconnected inputs.

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <numeric>
#include <random>
#include <string>
#include <typeinfo>
#include <utility>
#include <vector>

#include "CgalSpatialIndex.hpp"
#include "Connectivity.hpp"
#include "GridSpatialIndex.hpp"
#include "PointSet.hpp"
#include "TestHarness.hpp"
#include "Validator.hpp"
#include "algorithms/Funke.hpp"
#include "algorithms/LiSMIS.hpp"
#include "reference/FullScanReference.hpp"

using namespace mcds;

#define EQUIV_FAIL(msg) ::mcds::test::Registry::instance().fail(__FILE__, __LINE__, (msg))

namespace {

using Coords = std::vector<std::pair<double, double>>;

struct Tally {
    std::size_t connected = 0;
    std::size_t disconnected = 0;
    std::size_t comparisons = 0;
    std::size_t maxN = 0;
};
Tally g_tally;

PointSet makePoints(const Coords& c, bool permuteIds, std::uint64_t seed) {
    std::vector<int> ids(c.size());
    std::iota(ids.begin(), ids.end(), 0);
    if (permuteIds) {
        std::mt19937_64 rng(seed ^ 0x9e3779b97f4a7c15ull);
        // Distinct, non-contiguous ids in a shuffled order.
        for (int& id : ids) id = id * 7 + 3;
        std::shuffle(ids.begin(), ids.end(), rng);
    }
    std::vector<Point> pts;
    pts.reserve(c.size());
    for (std::size_t i = 0; i < c.size(); ++i) pts.push_back(Point{ids[i], c[i].first, c[i].second});
    return PointSet(std::move(pts));
}

Coords geometry(const std::string& g, std::size_t n, double density, std::uint64_t seed) {
    std::mt19937_64 rng(seed);
    std::uniform_real_distribution<double> u(0.0, 1.0);
    std::normal_distribution<double> gauss(0.0, 1.0);
    const double side = std::sqrt(static_cast<double>(n) / density);
    Coords c;
    c.reserve(n);
    if (g == "uniform") {
        for (std::size_t i = 0; i < n; ++i) c.emplace_back(u(rng) * side, u(rng) * side);
    } else if (g == "clustered") {  // D3-v2 shape: 4 hotspots, 50% background, sigma = 0.05 L, in-window
        std::vector<std::pair<double, double>> centres;
        for (int k = 0; k < 4; ++k) centres.emplace_back(u(rng) * side, u(rng) * side);
        const std::size_t bg = n / 2;
        for (std::size_t i = 0; i < bg; ++i) c.emplace_back(u(rng) * side, u(rng) * side);
        for (std::size_t i = bg; i < n; ++i) {
            const auto& ctr = centres[i % 4];
            double x = 0.0;
            double y = 0.0;
            do {
                x = ctr.first + 0.05 * side * gauss(rng);
                y = ctr.second + 0.05 * side * gauss(rng);
            } while (x < 0.0 || x > side || y < 0.0 || y > side);
            c.emplace_back(x, y);
        }
    } else if (g == "perturbed_grid") {
        const double s = 1.0 / std::sqrt(density);
        const std::size_t k = static_cast<std::size_t>(std::ceil(std::sqrt(static_cast<double>(n))));
        for (std::size_t i = 0; i < n; ++i) {
            c.emplace_back((i % k) * s + 0.15 * s * (u(rng) - 0.5), (i / k) * s + 0.15 * s * (u(rng) - 0.5));
        }
    } else if (g == "corridor") {
        const double w = 1.5;
        const double len = static_cast<double>(n) / (density * w);
        for (std::size_t i = 0; i < n; ++i) c.emplace_back(u(rng) * len, u(rng) * w);
    } else {  // dumbbell: two squares + a 1 x 3 neck
        const double area = static_cast<double>(n) / density;
        const double a = std::sqrt(std::max(area - 3.0, 2.0) / 2.0);
        const double y0 = a / 2.0 - 0.5;
        for (std::size_t i = 0; i < n; ++i) {
            const double r = u(rng);
            if (r < 0.45) c.emplace_back(u(rng) * a, u(rng) * a);
            else if (r < 0.55) c.emplace_back(a + 3.0 * u(rng), y0 + u(rng));
            else c.emplace_back(a + 3.0 + u(rng) * a, u(rng) * a);
        }
    }
    return c;
}

/// Runs the full-scan reference and the current version of one algorithm on one index; outputs (or exceptions)
/// must be identical.
void compare(MCDSAlgorithm& ref, MCDSAlgorithm& cur, const PointSet& pts, const SpatialIndex& idx,
             const std::string& label) {
    MCDSResult a;
    MCDSResult b;
    std::string ea = "";
    std::string eb = "";
    try { a = ref.solve(pts, idx, 1.0); } catch (const std::exception& e) { ea = std::string(typeid(e).name()) + e.what(); }
    try { b = cur.solve(pts, idx, 1.0); } catch (const std::exception& e) { eb = std::string(typeid(e).name()) + e.what(); }
    ++g_tally.comparisons;
    if (ea != eb) {
        EQUIV_FAIL(label + ": exceptions differ: reference '" + ea + "' vs current '" + eb + "'");
        return;
    }
    if (!ea.empty()) return;
    if (a.selectedIds != b.selectedIds || a.roles != b.roles) {
        EQUIV_FAIL(label + ": outputs differ (|D| reference " + std::to_string(a.selectedIds.size()) +
                                  ", current " + std::to_string(b.selectedIds.size()) + ")");
    }
}

void checkInstance(const Coords& c, const std::string& label, std::uint64_t seed) {
    FunkeFullScanRef f10;
    FunkeAlgorithm f11;
    LiSMISFullScanRef l10;
    LiSMISAlgorithm l11;
    for (const bool permute : {false, true}) {
        const PointSet pts = makePoints(c, permute, seed);
        const GridSpatialIndex grid(pts, 1.0);
        const CgalSpatialIndex cgal(pts);
        const bool conn = isConnected(pts, grid, 1.0);
        (conn ? g_tally.connected : g_tally.disconnected) += 1;
        g_tally.maxN = std::max(g_tally.maxN, c.size());
        const std::string l = label + (permute ? " [permuted ids]" : "");
        for (const SpatialIndex* idx : {static_cast<const SpatialIndex*>(&grid), static_cast<const SpatialIndex*>(&cgal)}) {
            compare(f10, f11, pts, *idx, "funke " + l + " " + idx->name());
            compare(l10, l11, pts, *idx, "li " + l + " " + idx->name());
        }
    }
}

}  // namespace

MCDS_TEST(random_geometries_match_reference) {
    const char* geoms[] = {"uniform", "clustered", "perturbed_grid", "corridor", "dumbbell"};
    const std::size_t sizes[] = {2, 3, 5, 8, 13, 20, 40, 75, 150, 300, 600, 1200, 2500};
    const double densities[] = {1.5, 3.0, 5.0, 8.0, 12.0, 25.0};
    std::uint64_t seed = 1;
    for (const char* g : geoms) {
        for (const std::size_t n : sizes) {
            for (const double d : densities) {
                const int reps = n <= 150 ? 6 : (n <= 600 ? 2 : 1);
                for (int r = 0; r < reps; ++r, ++seed) {
                    checkInstance(geometry(g, n, d, seed), std::string(g) + " n=" + std::to_string(n) + " d=" +
                                                           std::to_string(d) + " seed=" + std::to_string(seed), seed);
                }
            }
        }
    }
}

MCDS_TEST(adversarial_shapes_match_reference) {
    std::uint64_t seed = 900000;
    // Exact boundary distances: unit-spaced lattice and path (distance exactly r).
    for (const std::size_t k : {2u, 3u, 7u, 15u, 30u}) {
        Coords lattice;
        for (std::size_t i = 0; i < k; ++i)
            for (std::size_t j = 0; j < k; ++j) lattice.emplace_back(static_cast<double>(i), static_cast<double>(j));
        checkInstance(lattice, "unit lattice k=" + std::to_string(k), ++seed);
        Coords path;
        for (std::size_t i = 0; i < k * k; ++i) path.emplace_back(static_cast<double>(i), 0.0);
        checkInstance(path, "unit path n=" + std::to_string(k * k), ++seed);
    }
    // Clique, coincident points, star, two cliques joined by a single bridge.
    for (const std::size_t n : {1u, 2u, 6u, 40u, 200u}) {
        std::mt19937_64 rng(++seed);
        std::uniform_real_distribution<double> u(0.0, 0.7);
        Coords clique;
        for (std::size_t i = 0; i < n; ++i) clique.emplace_back(u(rng), u(rng));
        checkInstance(clique, "clique n=" + std::to_string(n), seed);
        Coords same(n, {3.0, 3.0});
        checkInstance(same, "coincident n=" + std::to_string(n), seed);
        Coords star{{0.0, 0.0}};
        for (std::size_t i = 0; i < n; ++i) {
            const double t = 6.283185307179586 * static_cast<double>(i) / static_cast<double>(n + 1);
            star.emplace_back(std::cos(t), std::sin(t));  // on the boundary circle
        }
        checkInstance(star, "boundary star n=" + std::to_string(n), seed);
        Coords bridge = clique;
        for (std::size_t i = 0; i < n; ++i) bridge.emplace_back(clique[i].first + 1.6, clique[i].second);
        checkInstance(bridge, "two cliques n=" + std::to_string(2 * n), seed);
    }
    // Disconnected inputs: both versions must raise the same exception.
    checkInstance({{0.0, 0.0}, {5.0, 0.0}}, "disconnected pair", ++seed);
    checkInstance(geometry("uniform", 300, 0.5, ++seed), "sparse uniform (disconnected)", seed);
}

MCDS_TEST(zz_report_counts) {
    std::printf("    instances: %zu connected, %zu disconnected (both id schemes), max n %zu; "
                "reference-vs-current comparisons: %zu\n",
                g_tally.connected, g_tally.disconnected, g_tally.maxN, g_tally.comparisons);
    MCDS_CHECK(g_tally.connected > 1000);
    MCDS_CHECK(g_tally.disconnected > 0);
}

MCDS_TEST_MAIN()
