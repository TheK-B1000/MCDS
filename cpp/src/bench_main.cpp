// mcds_bench — measurement driver for python/run_study.py.
//
// One process = one graph. The point set is loaded once and the spatial index
// is built once; every algorithm then runs against that same in-memory graph in
// the execution order given on the command line (the Python orchestrator
// supplies a seeded, balanced order). Repetitions are interleaved:
//
//     warmup 1:  A B C D
//     ...
//     timed 1:   A B C D
//     timed 2:   A B C D
//
// Timed region = `algorithm->solve(points, index, radius)` and nothing else.
// Index-stat reset happens before the clock starts; validation, hashing and
// JSON writing happen after it stops. No I/O occurs between the two clock
// reads.
//
// When compiled with MCDS_HEAP_TRACKING=1 (target `mcds_bench_mem`), every
// execution is a memory probe: heap counters are reset before `solve` and read
// after it. Those runs are never used for timing.

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <fstream>
#include <iomanip>
#include <memory>
#include <ratio>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "CsvIO.hpp"
#include "ExactSmallMCDS.hpp"
#include "GridSpatialIndex.hpp"
#include "PointSet.hpp"
#include "Validator.hpp"
#include "algorithms/Funke.hpp"
#include "algorithms/LiSMIS.hpp"
#include "algorithms/Marathe.hpp"
#include "algorithms/Wan.hpp"
#include "bench/BenchSupport.hpp"
#include "bench/BuildInfo.hpp"

#if MCDS_WITH_CGAL
#include "CgalSpatialIndex.hpp"
#endif

#ifndef MCDS_HEAP_TRACKING
#define MCDS_HEAP_TRACKING 0
#endif

#if MCDS_HEAP_TRACKING
#include "bench/HeapTracker.hpp"
#endif

#ifndef MCDS_BUILD_CONFIG
#define MCDS_BUILD_CONFIG "unknown"
#endif

namespace {

using Clock = std::chrono::steady_clock;
namespace bench = mcds::bench;

constexpr const char* kSchema = "mcds-bench/2";
constexpr std::size_t kExactHardMaxN = 20;

// ---------------------------------------------------------------------------
// Minimal JSON writer (no third-party dependency).
// ---------------------------------------------------------------------------
class Json {
public:
    explicit Json(std::ostream& out) : out_(out) {}

    void beginObject() { open('{'); }
    void endObject() { close('}'); }
    void beginArray() { open('['); }
    void endArray() { close(']'); }

    void key(const char* k) {
        comma();
        str(k);
        out_ << ':';
        pendingValue_ = true;
    }

    void value(const std::string& v) { pre(); str(v.c_str()); }
    void value(const char* v) { pre(); str(v); }
    void value(bool v) { pre(); out_ << (v ? "true" : "false"); }
    void value(std::uint64_t v) { pre(); out_ << v; }
    void value(std::int64_t v) { pre(); out_ << v; }
    void value(int v) { pre(); out_ << v; }
    void value(double v) {
        pre();
        if (!std::isfinite(v)) {
            out_ << "null";
            return;
        }
        std::ostringstream s;
        s << std::setprecision(17) << v;
        out_ << s.str();
    }
    void null() { pre(); out_ << "null"; }

    void null_field(const char* k) {
        key(k);
        null();
    }

    template <typename T>
    void field(const char* k, const T& v) {
        key(k);
        value(v);
    }

private:
    void open(char c) {
        pre();
        out_ << c;
        first_.push_back(true);
    }
    void close(char c) {
        first_.pop_back();
        out_ << c;
    }
    void comma() {
        if (!first_.empty()) {
            if (!first_.back()) {
                out_ << ',';
            }
            first_.back() = false;
        }
    }
    void pre() {
        if (pendingValue_) {
            pendingValue_ = false;
            return;
        }
        comma();
    }
    void str(const char* s) {
        out_ << '"';
        for (const char* p = s; *p; ++p) {
            const unsigned char ch = static_cast<unsigned char>(*p);
            switch (ch) {
                case '"': out_ << "\\\""; break;
                case '\\': out_ << "\\\\"; break;
                case '\n': out_ << "\\n"; break;
                case '\r': out_ << "\\r"; break;
                case '\t': out_ << "\\t"; break;
                default:
                    if (ch < 0x20) {
                        char buf[8];
                        std::snprintf(buf, sizeof(buf), "\\u%04x", ch);
                        out_ << buf;
                    } else {
                        out_ << static_cast<char>(ch);
                    }
            }
        }
        out_ << '"';
    }

    std::ostream& out_;
    std::vector<bool> first_;
    bool pendingValue_ = false;
};

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------
enum class Instrumentation { None, Basic, Detailed };

const char* instrumentationName(Instrumentation i) {
    switch (i) {
        case Instrumentation::None: return "none";
        case Instrumentation::Basic: return "basic";
        case Instrumentation::Detailed: return "detailed";
    }
    return "none";
}

struct Options {
    std::string input;
    std::string output;
    double radius = 1.0;
    std::vector<std::string> algorithms;
    int repetitions = 1;
    int warmups = 0;
    Instrumentation instrumentation = Instrumentation::None;
    bool validateAll = true;
    std::size_t exactMaxN = 0;
    bool graphOnly = false;
    bool runDisconnected = false;
    bool emitSolution = false;
    std::string spatialBackend;  // required: grid | cgal | explicit
};

void usage() {
    std::printf(
        "usage: mcds_bench --input F.csv --output out.json [--radius R]\n"
        "                  [--algorithms a,b,c,d] [--repetitions N] [--warmups W]\n"
        "                  [--instrumentation none|basic|detailed] [--validate all|first]\n"
        "                  [--exact-max-n K] [--graph-only] [--run-disconnected] [--emit-solution]\n"
        "                  --spatial-backend grid|cgal|explicit\n"
        "\n"
        "Algorithms run in the order given; repetitions are interleaved across algorithms.\n");
}

std::vector<std::string> splitCsv(const std::string& s) {
    std::vector<std::string> out;
    std::string cur;
    for (const char c : s) {
        if (c == ',') {
            if (!cur.empty()) out.push_back(cur);
            cur.clear();
        } else {
            cur.push_back(c);
        }
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

std::unique_ptr<mcds::MCDSAlgorithm> makeAlgorithm(const std::string& name) {
    if (name == "marathe") return std::make_unique<mcds::MaratheAlgorithm>();
    if (name == "wan") return std::make_unique<mcds::WanAlgorithm>();
    if (name == "funke") return std::make_unique<mcds::FunkeAlgorithm>();
    if (name == "li") return std::make_unique<mcds::LiSMISAlgorithm>();
    return nullptr;
}

double msSince(Clock::time_point t0) {
    return std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
}

/// Smallest non-zero difference between consecutive clock reads; reported so
/// readers can judge whether sub-millisecond timings are meaningful.
std::int64_t observedClockResolutionNs() {
    std::int64_t best = 0;
    for (int trial = 0; trial < 200; ++trial) {
        const auto a = Clock::now();
        auto b = Clock::now();
        while (b == a) {
            b = Clock::now();
        }
        const std::int64_t d = std::chrono::duration_cast<std::chrono::nanoseconds>(b - a).count();
        if (best == 0 || d < best) {
            best = d;
        }
    }
    return best;
}

void writeBuild(Json& j) {
    j.key("build");
    j.beginObject();
    j.field("config", MCDS_BUILD_CONFIG);
    j.field("compiler_id", MCDS_CXX_COMPILER_ID);
    j.field("compiler_version", MCDS_CXX_COMPILER_VERSION);
    j.field("cxx_standard", static_cast<std::int64_t>(MCDS_CXX_STANDARD));
#if defined(_MSVC_LANG)
    j.field("cplusplus_macro", static_cast<std::int64_t>(_MSVC_LANG));
#else
    j.field("cplusplus_macro", static_cast<std::int64_t>(__cplusplus));
#endif
    j.field("cxx_flags", MCDS_CXX_FLAGS);
    const std::string config = MCDS_BUILD_CONFIG;
    const char* configFlags = "";
    if (config == "Release") configFlags = MCDS_CXX_FLAGS_RELEASE;
    else if (config == "Debug") configFlags = MCDS_CXX_FLAGS_DEBUG;
    else if (config == "RelWithDebInfo") configFlags = MCDS_CXX_FLAGS_RELWITHDEBINFO;
    else if (config == "MinSizeRel") configFlags = MCDS_CXX_FLAGS_MINSIZEREL;
    j.field("cxx_flags_config", configFlags);
    j.field("target_warning_flags", MCDS_TARGET_WARNING_FLAGS);
    j.field("generator", MCDS_CMAKE_GENERATOR);
    j.field("system", MCDS_CMAKE_SYSTEM);
#if defined(NDEBUG)
    j.field("ndebug", true);
#else
    j.field("ndebug", false);
#endif
#if MCDS_HEAP_TRACKING
    j.field("heap_tracking", true);
#else
    j.field("heap_tracking", false);
#endif
#if MCDS_WITH_CGAL
    j.field("cgal_available", true);
    j.field("cgal_version", mcds::cgalVersionString());
    j.field("boost_version", mcds::cgalBoostVersionString());
#else
    j.field("cgal_available", false);
    j.null_field("cgal_version");
    j.null_field("boost_version");
#endif
    j.field("clock", "std::chrono::steady_clock");
    j.field("clock_is_steady", Clock::is_steady);
    j.field("clock_period_ns", static_cast<double>(Clock::period::num) * 1e9 /
                                   static_cast<double>(Clock::period::den));
    j.field("clock_observed_resolution_ns", observedClockResolutionNs());
    j.endObject();
}

void writeMemory(Json& j, const char* key) {
    const bench::ProcessMemory m = bench::processMemory();
    j.key(key);
    j.beginObject();
    j.field("available", m.available);
    j.field("current_rss_bytes", m.currentRssBytes);
    j.field("peak_rss_bytes", m.peakRssBytes);
    j.endObject();
}

}  // namespace

int main(int argc, char** argv) {
    Options opt;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto need = [&](const char* name) -> std::string {
            if (i + 1 >= argc) {
                std::fprintf(stderr, "error: %s requires a value\n", name);
                std::exit(2);
            }
            return argv[++i];
        };
        try {
            if (arg == "--help" || arg == "-h") { usage(); return 0; }
            else if (arg == "--input") opt.input = need("--input");
            else if (arg == "--output") opt.output = need("--output");
            else if (arg == "--radius") opt.radius = std::stod(need("--radius"));
            else if (arg == "--algorithms") opt.algorithms = splitCsv(need("--algorithms"));
            else if (arg == "--repetitions") opt.repetitions = std::stoi(need("--repetitions"));
            else if (arg == "--warmups") opt.warmups = std::stoi(need("--warmups"));
            else if (arg == "--instrumentation") {
                const std::string v = need("--instrumentation");
                if (v == "none") opt.instrumentation = Instrumentation::None;
                else if (v == "basic") opt.instrumentation = Instrumentation::Basic;
                else if (v == "detailed") opt.instrumentation = Instrumentation::Detailed;
                else { std::fprintf(stderr, "error: bad --instrumentation '%s'\n", v.c_str()); return 2; }
            } else if (arg == "--validate") {
                const std::string v = need("--validate");
                if (v == "all") opt.validateAll = true;
                else if (v == "first") opt.validateAll = false;
                else { std::fprintf(stderr, "error: bad --validate '%s'\n", v.c_str()); return 2; }
            } else if (arg == "--exact-max-n") opt.exactMaxN = static_cast<std::size_t>(std::stoul(need("--exact-max-n")));
            else if (arg == "--graph-only") opt.graphOnly = true;
            else if (arg == "--run-disconnected") opt.runDisconnected = true;
            else if (arg == "--emit-solution") opt.emitSolution = true;
            else if (arg == "--spatial-backend") opt.spatialBackend = need("--spatial-backend");
            else { std::fprintf(stderr, "error: unknown option '%s'\n", arg.c_str()); usage(); return 2; }
        } catch (const std::exception&) {
            std::fprintf(stderr, "error: bad value for %s\n", arg.c_str());
            return 2;
        }
    }

    if (opt.input.empty() || opt.output.empty()) { usage(); return 2; }
    if (!(opt.radius > 0.0)) { std::fprintf(stderr, "error: radius must be positive\n"); return 2; }
    if (opt.repetitions < 1 || opt.warmups < 0) { std::fprintf(stderr, "error: repetitions >= 1, warmups >= 0\n"); return 2; }
    if (opt.exactMaxN > kExactHardMaxN) {
        std::fprintf(stderr, "error: --exact-max-n is capped at %zu (exhaustive search)\n", kExactHardMaxN);
        return 2;
    }
    {
        std::unordered_set<std::string> seen;
        for (const std::string& a : opt.algorithms) {
            if (!makeAlgorithm(a)) { std::fprintf(stderr, "error: unknown algorithm '%s'\n", a.c_str()); return 2; }
            if (!seen.insert(a).second) { std::fprintf(stderr, "error: algorithm '%s' listed twice\n", a.c_str()); return 2; }
        }
    }
    if (opt.spatialBackend != "grid" && opt.spatialBackend != "cgal" && opt.spatialBackend != "explicit") {
        std::fprintf(stderr, "error: --spatial-backend must be grid, cgal or explicit (got '%s')\n",
                     opt.spatialBackend.c_str());
        return 2;
    }
#if !MCDS_WITH_CGAL
    if (opt.spatialBackend != "grid") {
        // Never substitute another backend: provenance would silently be wrong.
        std::fprintf(stderr,
                     "error: --spatial-backend %s requires CGAL, but this binary was built with "
                     "MCDS_WITH_CGAL=OFF. Rebuild with CGAL (see cpp/CMakeLists.txt); no fallback.\n",
                     opt.spatialBackend.c_str());
        return 2;
    }
#endif
    if (!opt.graphOnly && opt.algorithms.empty()) {
        std::fprintf(stderr, "error: --algorithms required unless --graph-only\n");
        return 2;
    }

    const auto processStart = Clock::now();
    std::ostringstream body;
    Json j(body);

    try {
        j.beginObject();
        j.field("schema", kSchema);
        writeBuild(j);

        // --- T_dataset ----------------------------------------------------
        auto t0 = Clock::now();
        const mcds::PointSet points = mcds::loadPointsCsvFile(opt.input);
        const double datasetMs = msSince(t0);

        const std::uint64_t fingerprint = bench::pointsFingerprint(points);

        // --- Independent grid ---------------------------------------------
        // Always built. It is the backend when --spatial-backend grid, and
        // otherwise the independent reference used (untimed, after the
        // algorithm timer) for validation, CDS diameter and the full
        // neighbour-set cross-check. Algorithms never see it unless it is the
        // selected backend.
#if MCDS_HEAP_TRACKING
        bench::heapResetWindow();
        const std::uint64_t gridHeapBase = bench::heapSnapshot().currentBytes;
#endif
        t0 = Clock::now();
        mcds::GridSpatialIndex grid(points, opt.radius);
        const double gridMs = msSince(t0);
#if MCDS_HEAP_TRACKING
        const std::uint64_t gridHeapPeak = bench::heapSnapshot().peakBytes - gridHeapBase;
#endif

        // --- T_spatial_index: the selected backend -------------------------
        // Built once per graph and reused read-only by every algorithm in this
        // process (counters reset before each execution): identical for all.
        mcds::SpatialIndex* backend = &grid;
        double indexMs = gridMs;
        double validationIndexMs = 0.0;  // grid shared when it is the backend
        std::int64_t indexHeapPeak = -1;
#if MCDS_HEAP_TRACKING
        indexHeapPeak = static_cast<std::int64_t>(gridHeapPeak);
#endif
#if MCDS_WITH_CGAL
        std::unique_ptr<mcds::CgalSpatialIndex> cgal;
        std::unique_ptr<bench::ExplicitAdjacencyIndex> explicitIndex;
        if (opt.spatialBackend != "grid") {
            validationIndexMs = gridMs;
#if MCDS_HEAP_TRACKING
            bench::heapResetWindow();
            const std::uint64_t base = bench::heapSnapshot().currentBytes;
#endif
            t0 = Clock::now();
            cgal = std::make_unique<mcds::CgalSpatialIndex>(points);
            if (opt.spatialBackend == "explicit") {
                // Explicit representation: materialise the UDG once (CSR) from
                // the CGAL range queries; construction includes the CGAL build.
                explicitIndex = std::make_unique<bench::ExplicitAdjacencyIndex>(points, *cgal, opt.radius);
                backend = explicitIndex.get();
            } else {
                backend = cgal.get();
            }
            indexMs = msSince(t0);
#if MCDS_HEAP_TRACKING
            indexHeapPeak = static_cast<std::int64_t>(bench::heapSnapshot().peakBytes - base);
#endif
            cgal->resetStats();
        }
#endif
        (void)indexHeapPeak;

        // --- Backend cross-check (untimed; every graph) ---------------------
        // The selected backend must return exactly the grid's neighbour set
        // for every point; otherwise the graph is not run.
        std::string crossStatus = "not_applicable";
        std::uint64_t crossMismatches = 0;
        long long firstMismatchId = -1;
        double crossMs = 0.0;
        if (backend != &grid) {
            t0 = Clock::now();
            std::vector<int> a;
            std::vector<int> b;
            for (std::size_t i = 0; i < points.size(); ++i) {
                backend->radiusQuery(points.idAt(i), opt.radius, a);
                grid.radiusQuery(points.idAt(i), opt.radius, b);
                std::sort(a.begin(), a.end());
                std::sort(b.begin(), b.end());
                if (a != b) {
                    if (crossMismatches++ == 0) firstMismatchId = points.idAt(i);
                }
            }
            crossMs = msSince(t0);
            crossStatus = crossMismatches == 0 ? "identical" : "mismatch";
        }
        backend->resetStats();
        grid.resetStats();

        // --- Graph statistics (analysis only; never given to algorithms) ----
        t0 = Clock::now();
        const bench::GraphStats gs = bench::computeGraphStats(points, *backend, opt.radius);
        const double graphStatsMs = msSince(t0);
        backend->resetStats();
        grid.resetStats();

        j.field("spatial_backend", opt.spatialBackend);

        j.key("input");
        j.beginObject();
        j.field("path", opt.input);
        j.field("radius", opt.radius);
        j.field("n", static_cast<std::uint64_t>(points.size()));
        j.field("points_fingerprint", bench::toHex64(fingerprint));
        j.field("identity_ids", points.usesIdentityIds());
        const mcds::BoundingBox box = points.boundingBox();
        j.key("bbox");
        j.beginArray();
        j.value(box.minX); j.value(box.minY); j.value(box.maxX); j.value(box.maxY);
        j.endArray();
        j.field("dataset_bytes", static_cast<std::uint64_t>(points.size() * sizeof(mcds::Point)));
        j.endObject();

        j.key("index");
        j.beginObject();
        j.field("backend", backend->name());
        if (backend == &grid) {
            j.field("counter_semantics", "grid_cell_scan");
            j.field("cell_size", grid.cellSize());
            j.field("cells_x", static_cast<std::int64_t>(grid.cellsX()));
            j.field("cells_y", static_cast<std::int64_t>(grid.cellsY()));
            j.field("index_bytes", static_cast<std::uint64_t>(grid.indexBytes()));
        }
#if MCDS_WITH_CGAL
        else if (explicitIndex) {
            j.field("counter_semantics", "none_stored_adjacency");
            j.field("index_bytes", static_cast<std::uint64_t>(explicitIndex->adjacencyBytes()));
            j.field("adjacency_slots", explicitIndex->edgeSlots());
            j.field("built_from", "cgal-kd-tree");
        } else {
            j.field("counter_semantics", "cgal_box_report");
            j.null_field("index_bytes");  // not exposed by the CGAL API; see memory probes
        }
#endif
#if MCDS_HEAP_TRACKING
        j.field("index_heap_peak_bytes", indexHeapPeak);
#endif
        j.endObject();

        j.key("backend_crosscheck");
        j.beginObject();
        j.field("status", crossStatus);
        j.field("reference", "uniform-grid");
        j.field("points_checked", static_cast<std::uint64_t>(backend != &grid ? points.size() : 0));
        j.field("mismatching_points", crossMismatches);
        j.field("first_mismatch_id", static_cast<std::int64_t>(firstMismatchId));
        j.endObject();

        j.key("graph");
        j.beginObject();
        j.field("n", static_cast<std::uint64_t>(gs.n));
        j.field("edges", gs.edges);
        j.field("min_degree", static_cast<std::uint64_t>(gs.minDegree));
        j.field("max_degree", static_cast<std::uint64_t>(gs.maxDegree));
        j.field("mean_degree", gs.meanDegree);
        j.field("median_degree", gs.medianDegree);
        j.field("degree_std", gs.degreeStdDev);
        j.field("graph_density", gs.graphDensity);
        j.field("isolated_count", static_cast<std::uint64_t>(gs.isolatedCount));
        j.field("component_count", static_cast<std::uint64_t>(gs.componentCount));
        j.field("largest_component", static_cast<std::uint64_t>(gs.largestComponent));
        j.field("connected", gs.connected);
        j.field("stats_neighbor_queries", gs.neighborQueries);
        j.field("stats_candidates_examined", gs.candidatesExamined);
        j.field("stats_backend", backend->name());
        j.endObject();

        // --- Optional exact OPT (analysis only) ---------------------------
        double exactMs = 0.0;
        j.key("exact");
        j.beginObject();
        if (opt.exactMaxN == 0) {
            j.field("status", "disabled");
        } else if (!gs.connected) {
            j.field("status", "skipped_disconnected");
        } else if (points.size() > opt.exactMaxN) {
            j.field("status", "skipped_n_too_large");
        } else {
            j.field("method", "exhaustive_by_increasing_size");
            t0 = Clock::now();
            try {
                const mcds::ExactSmallResult ex = mcds::exactSmallMCDS(points, opt.radius, opt.exactMaxN);
                exactMs = msSince(t0);
                // Independent check of the exact answer with the validator.
                const mcds::ValidationResult ev = mcds::validateCDS(points, grid, ex.selectedIds, opt.radius);
                j.field("status", ev.valid() ? "computed" : "computed_but_invalid");
                j.field("opt_size", static_cast<std::uint64_t>(ex.optSize));
                j.field("valid", ev.valid());
            } catch (const std::exception& e) {
                // Recorded, never silently dropped; heuristics still run.
                exactMs = msSince(t0);
                j.field("status", "error");
                j.field("error", e.what());
            }
        }
        j.endObject();

        j.key("timing_ms");
        j.beginObject();
        j.field("dataset", datasetMs);
        j.field("spatial_index", indexMs);
        j.field("validation_index", validationIndexMs);
        j.field("backend_crosscheck", crossMs);
        j.field("graph_stats", graphStatsMs);  // degree pass + components
        j.field("degree_pass", gs.degreePassMs);
        j.field("connectivity", gs.connectivityMs);
        j.field("exact", exactMs);
        j.endObject();

        j.field("instrumentation", instrumentationName(opt.instrumentation));
        j.field("repetitions", opt.repetitions);
        j.field("warmups", opt.warmups);
        j.key("execution_order");
        j.beginArray();
        for (const std::string& a : opt.algorithms) j.value(a);
        j.endArray();

        writeMemory(j, "process_memory_after_preprocessing");

        const bool mismatch = crossStatus == "mismatch";
        const bool skipAlgorithms = opt.graphOnly || mismatch || (!gs.connected && !opt.runDisconnected);
        j.field("status", mismatch ? "backend_mismatch"
                                   : (opt.graphOnly ? "graph_only" : (skipAlgorithms ? "input_disconnected" : "ok")));

        // --- Algorithm executions -----------------------------------------
        bench::InstrumentedSpatialIndex instrumented(*backend, opt.instrumentation == Instrumentation::Detailed,
                                                     backend == &grid ? &grid : nullptr);
        mcds::SpatialIndex& algoIndex =
            opt.instrumentation == Instrumentation::None ? *backend
                                                         : static_cast<mcds::SpatialIndex&>(instrumented);
        const bool hasCandidates = backend->name() != std::string("explicit-csr");
        std::unordered_map<std::string, long long> diameterByHash;

        j.key("runs");
        j.beginArray();
        if (!skipAlgorithms) {
            std::vector<std::unique_ptr<mcds::MCDSAlgorithm>> algos;
            for (const std::string& a : opt.algorithms) algos.push_back(makeAlgorithm(a));

            std::int64_t sequence = 0;
            const int totalRounds = opt.warmups + opt.repetitions;
            for (int round = 0; round < totalRounds; ++round) {
                const bool warmup = round < opt.warmups;
                const int rep = warmup ? round : round - opt.warmups;
                for (std::size_t pos = 0; pos < algos.size(); ++pos) {
                    mcds::MCDSAlgorithm& algo = *algos[pos];

                    mcds::MCDSResult res;
                    std::string error;
                    algoIndex.resetStats();
#if MCDS_HEAP_TRACKING
                    const bench::ProcessMemory rssBefore = bench::processMemory();
                    bench::heapResetWindow();
                    const std::uint64_t heapBaseline = bench::heapSnapshot().currentBytes;
#endif
                    // ======== timed region ========
                    const auto start = Clock::now();
                    try {
                        res = algo.solve(points, algoIndex, opt.radius);
                    } catch (const std::exception& e) {
                        error = e.what();
                    }
                    const auto stop = Clock::now();
                    // ======== end timed region ====
#if MCDS_HEAP_TRACKING
                    const bench::HeapSnapshot heap = bench::heapSnapshot();
                    const bench::ProcessMemory rssAfter = bench::processMemory();
#endif
                    const mcds::QueryStats qs = algoIndex.stats();
                    const std::int64_t ns =
                        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();

                    j.beginObject();
                    j.field("sequence", sequence++);
#if MCDS_HEAP_TRACKING
                    j.field("phase", "memory_probe");
#else
                    j.field("phase", warmup ? "warmup" : "timed");
#endif
                    j.field("repetition", rep);
                    j.field("execution_position", static_cast<std::int64_t>(pos));
                    j.field("algorithm", algo.name());
                    j.field("t_algorithm_ns", ns);
                    j.field("t_algorithm_ms", static_cast<double>(ns) / 1e6);
                    j.field("neighbor_queries", qs.neighborQueries);
                    j.field("neighbors_returned", qs.neighborsReturned);
                    if (hasCandidates) {
                        // Backend-specific (see index.counter_semantics). For
                        // grid and CGAL the query point is always among the
                        // candidates and is the only one skipped before the
                        // exact distance test, so this difference is exact.
                        j.field("candidates_examined", qs.candidatesExamined);
                        j.field("distance_computations", qs.candidatesExamined - qs.neighborQueries);
                    }
                    if (opt.instrumentation != Instrumentation::None) {
                        const bench::ExtendedQueryStats& ex = instrumented.extendedStats();
                        if (backend == &grid) {
                            j.field("cells_examined", ex.cellsExamined);
                        }
                        j.field("max_candidates_per_query", ex.maxCandidatesPerQuery);
                        j.field("max_neighbors_per_query", ex.maxNeighborsPerQuery);
                        if (opt.instrumentation == Instrumentation::Detailed) {
                            j.field("query_time_ns", ex.queryTimeNs);
                        }
                    }
#if MCDS_HEAP_TRACKING
                    j.field("heap_peak_additional_bytes", heap.peakBytes - heapBaseline);
                    j.field("heap_allocation_count", heap.allocationCount);
                    j.field("heap_allocated_bytes", heap.allocatedBytes);
                    j.field("rss_before_algorithm_bytes", rssBefore.currentRssBytes);
                    j.field("process_peak_rss_bytes", rssAfter.peakRssBytes);
#endif

                    if (!error.empty()) {
                        j.field("status", "algorithm_error");
                        j.field("error", error);
                        j.endObject();
                        continue;
                    }

                    std::unordered_set<int> uniq(res.selectedIds.begin(), res.selectedIds.end());
                    std::size_t cores = 0;
                    std::size_t connectors = 0;
                    for (const auto& role : res.roles) {
                        if (role.second == "core") ++cores;
                        else if (role.second == "connector") ++connectors;
                    }
                    j.field("cds_size", static_cast<std::uint64_t>(res.selectedIds.size()));
                    j.field("duplicate_ids", static_cast<std::uint64_t>(res.selectedIds.size() - uniq.size()));
                    j.field("cds_hash", bench::toHex64(bench::idSetFingerprint(res.selectedIds)));
                    j.field("roles_reported", !res.roles.empty());
                    j.field("core_count", static_cast<std::uint64_t>(cores));
                    j.field("connector_count", static_cast<std::uint64_t>(connectors));

                    const bool doValidate = opt.validateAll || rep == 0;
                    if (doValidate) {
                        // Validation uses the raw grid so its queries never
                        // touch the algorithm's counters.
                        const auto vt0 = Clock::now();
                        bool threw = false;
                        mcds::ValidationResult v;
                        std::string verr;
                        try {
                            v = mcds::validateCDS(points, grid, res.selectedIds, opt.radius);
                        } catch (const std::exception& e) {
                            threw = true;
                            verr = e.what();
                        }
                        j.field("t_validation_ms", msSince(vt0));
                        j.field("validated", true);
                        std::string reason;
                        if (threw) {
                            reason = std::string("validator_exception:") + verr;
                        } else {
                            if (res.selectedIds.empty() && !points.empty()) reason = "empty_selection";
                            else {
                                if (!v.dominating) reason = "not_dominating";
                                if (!v.connected) reason += reason.empty() ? "not_connected" : ";not_connected";
                            }
                        }
                        j.field("domination_valid", !threw && v.dominating);
                        j.field("connectivity_valid", !threw && v.connected);
                        j.field("valid_solution", !threw && v.valid());
                        j.field("undominated_count",
                                static_cast<std::uint64_t>(threw ? points.size() : points.size() - v.dominatedCount));
                        j.field("failure_reason", reason);
                        j.field("status", (!threw && v.valid()) ? "ok" : "invalid_solution");
                        // CDS diameter (secondary metric): hop diameter of the
                        // subgraph induced by D, computed after the timer with
                        // the independent grid, once per distinct CDS.
                        if (!threw && v.valid()) {
                            const std::string h = bench::toHex64(bench::idSetFingerprint(res.selectedIds));
                            auto it = diameterByHash.find(h);
                            if (it == diameterByHash.end()) {
                                const auto dt0 = Clock::now();
                                const long long d = bench::cdsDiameter(points, grid, res.selectedIds, opt.radius);
                                j.field("t_cds_diameter_ms", msSince(dt0));
                                it = diameterByHash.emplace(h, d).first;
                            }
                            if (it->second >= 0) j.field("cds_diameter", static_cast<std::int64_t>(it->second));
                            else j.null_field("cds_diameter");
                        }
                    } else {
                        j.field("validated", false);
                        j.field("status", "ok_unvalidated");
                    }
                    if (opt.emitSolution && !warmup && rep == 0) {
                        std::vector<int> sorted = res.selectedIds;
                        std::sort(sorted.begin(), sorted.end());
                        j.key("selected_ids");
                        j.beginArray();
                        for (const int id : sorted) j.value(id);
                        j.endArray();
                    }
                    j.endObject();
                }
            }
        }
        j.endArray();

        writeMemory(j, "process_memory_final");
        j.field("t_total_ms_before_output", msSince(processStart));
        j.endObject();
    } catch (const std::exception& e) {
        std::fprintf(stderr, "error: %s\n", e.what());
        return 1;
    }

    std::ofstream out(opt.output, std::ios::binary);
    if (!out) {
        std::fprintf(stderr, "error: cannot write '%s'\n", opt.output.c_str());
        return 1;
    }
    out << body.str() << '\n';
    return out ? 0 : 1;
}
