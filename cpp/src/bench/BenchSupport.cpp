#include "bench/BenchSupport.hpp"

#include <algorithm>
#include <chrono>
#include <queue>
#include <stdexcept>
#include <unordered_map>
#include <cmath>
#include <cstring>

#include "Connectivity.hpp"

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <psapi.h>
#else
#include <sys/resource.h>
#include <unistd.h>
#include <cstdio>
#endif

namespace mcds::bench {
namespace {

constexpr std::uint64_t kFnvOffset = 14695981039346656037ull;
constexpr std::uint64_t kFnvPrime = 1099511628211ull;

void fnvBytes(std::uint64_t& h, const unsigned char* bytes, std::size_t count) {
    for (std::size_t i = 0; i < count; ++i) {
        h ^= bytes[i];
        h *= kFnvPrime;
    }
}

/// Little-endian byte image, independent of host byte order.
void fnvU64(std::uint64_t& h, std::uint64_t v) {
    unsigned char b[8];
    for (int i = 0; i < 8; ++i) {
        b[i] = static_cast<unsigned char>((v >> (8 * i)) & 0xffu);
    }
    fnvBytes(h, b, 8);
}

void fnvDouble(std::uint64_t& h, double d) {
    std::uint64_t bits = 0;
    static_assert(sizeof(bits) == sizeof(d), "binary64 expected");
    std::memcpy(&bits, &d, sizeof(bits));
    fnvU64(h, bits);
}

}  // namespace

GraphStats computeGraphStats(const PointSet& points, const SpatialIndex& index, double radius) {
    GraphStats s;
    s.n = points.size();
    const QueryStats before = index.stats();

    const auto t0 = std::chrono::steady_clock::now();
    if (s.n > 0) {
        std::vector<std::size_t> degree(s.n, 0);
        std::vector<int> neighbors;
        std::uint64_t sum = 0;
        for (std::size_t i = 0; i < s.n; ++i) {
            index.radiusQuery(points.idAt(i), radius, neighbors);
            degree[i] = neighbors.size();
            sum += neighbors.size();
        }
        s.edges = sum / 2;
        s.minDegree = *std::min_element(degree.begin(), degree.end());
        s.maxDegree = *std::max_element(degree.begin(), degree.end());
        s.meanDegree = static_cast<double>(sum) / static_cast<double>(s.n);
        double sq = 0.0;
        for (const std::size_t d : degree) {
            const double diff = static_cast<double>(d) - s.meanDegree;
            sq += diff * diff;
        }
        s.degreeStdDev = std::sqrt(sq / static_cast<double>(s.n));

        std::vector<std::size_t> sorted = degree;
        std::sort(sorted.begin(), sorted.end());
        const std::size_t mid = s.n / 2;
        s.medianDegree = (s.n % 2 == 1)
                             ? static_cast<double>(sorted[mid])
                             : 0.5 * (static_cast<double>(sorted[mid - 1]) + static_cast<double>(sorted[mid]));
        if (s.n >= 2) {
            s.graphDensity = 2.0 * static_cast<double>(s.edges) /
                             (static_cast<double>(s.n) * static_cast<double>(s.n - 1));
        }
    }

    const auto t1 = std::chrono::steady_clock::now();
    const ConnectivityResult conn = findConnectedComponents(points, index, radius);
    const auto t2 = std::chrono::steady_clock::now();
    s.degreePassMs = std::chrono::duration<double, std::milli>(t1 - t0).count();
    s.connectivityMs = std::chrono::duration<double, std::milli>(t2 - t1).count();
    s.connected = conn.connected;
    s.componentCount = conn.componentCount;
    s.largestComponent = conn.largestComponent;
    s.isolatedCount = conn.isolatedCount;

    s.neighborQueries = index.stats().neighborQueries - before.neighborQueries;
    s.candidatesExamined = index.stats().candidatesExamined - before.candidatesExamined;
    return s;
}

long long cdsDiameter(const PointSet& points, const SpatialIndex& index, const std::vector<int>& selectedIds,
                      double radius) {
    // Local indices 0..k-1 for the distinct selected ids.
    std::unordered_map<int, std::size_t> local;
    std::vector<int> ids;
    for (const int id : selectedIds) {
        if (local.emplace(id, ids.size()).second) {
            ids.push_back(id);
        }
    }
    const std::size_t k = ids.size();
    if (k == 0) {
        return -1;
    }
    std::vector<std::vector<std::size_t>> adj(k);
    std::vector<int> neighbors;
    for (std::size_t a = 0; a < k; ++a) {
        index.radiusQuery(ids[a], radius, neighbors);
        for (const int nid : neighbors) {
            const auto it = local.find(nid);
            if (it != local.end()) {
                adj[a].push_back(it->second);
            }
        }
    }
    (void)points;
    long long diameter = 0;
    std::vector<long long> dist(k);
    std::queue<std::size_t> q;
    for (std::size_t src = 0; src < k; ++src) {
        std::fill(dist.begin(), dist.end(), -1);
        dist[src] = 0;
        q.push(src);
        std::size_t reached = 0;
        while (!q.empty()) {
            const std::size_t u = q.front();
            q.pop();
            ++reached;
            diameter = std::max(diameter, dist[u]);
            for (const std::size_t v : adj[u]) {
                if (dist[v] < 0) {
                    dist[v] = dist[u] + 1;
                    q.push(v);
                }
            }
        }
        if (reached != k) {
            return -1;  // induced subgraph disconnected
        }
    }
    return diameter;
}

ExplicitAdjacencyIndex::ExplicitAdjacencyIndex(const PointSet& points, const SpatialIndex& source, double radius)
    : points_(&points), radius_(radius) {
    const std::size_t n = points.size();
    offsets_.assign(n + 1, 0);
    std::vector<int> buf;
    for (std::size_t i = 0; i < n; ++i) {
        source.radiusQuery(points.idAt(i), radius, buf);
        neighbors_.insert(neighbors_.end(), buf.begin(), buf.end());
        offsets_[i + 1] = neighbors_.size();
    }
    neighbors_.shrink_to_fit();
}

std::size_t ExplicitAdjacencyIndex::adjacencyBytes() const {
    return offsets_.size() * sizeof(std::uint64_t) + neighbors_.size() * sizeof(int);
}

void ExplicitAdjacencyIndex::radiusQueryImpl(int pointId, double radius, std::vector<int>& out) const {
    if (radius != radius_) {
        throw std::invalid_argument("ExplicitAdjacencyIndex: queried with a radius it was not built for");
    }
    const std::size_t i = points_->indexOf(pointId);
    out.assign(neighbors_.begin() + static_cast<std::ptrdiff_t>(offsets_[i]),
               neighbors_.begin() + static_cast<std::ptrdiff_t>(offsets_[i + 1]));
    ++stats_.neighborQueries;
    stats_.neighborsReturned += out.size();
}

std::uint64_t pointsFingerprint(const PointSet& points) {
    std::uint64_t h = kFnvOffset;
    fnvU64(h, static_cast<std::uint64_t>(points.size()));
    for (std::size_t i = 0; i < points.size(); ++i) {
        const Point& p = points[i];
        fnvU64(h, static_cast<std::uint64_t>(static_cast<std::int64_t>(p.id)));
        fnvDouble(h, p.x);
        fnvDouble(h, p.y);
    }
    return h;
}

std::uint64_t idSetFingerprint(std::vector<int> ids) {
    std::sort(ids.begin(), ids.end());
    ids.erase(std::unique(ids.begin(), ids.end()), ids.end());
    std::uint64_t h = kFnvOffset;
    fnvU64(h, static_cast<std::uint64_t>(ids.size()));
    for (const int id : ids) {
        fnvU64(h, static_cast<std::uint64_t>(static_cast<std::int64_t>(id)));
    }
    return h;
}

std::string toHex64(std::uint64_t value) {
    static const char* digits = "0123456789abcdef";
    std::string s(16, '0');
    for (int i = 15; i >= 0; --i) {
        s[static_cast<std::size_t>(i)] = digits[value & 0xfu];
        value >>= 4;
    }
    return s;
}

void InstrumentedSpatialIndex::radiusQueryImpl(int pointId, double radius, std::vector<int>& out) const {
    const std::uint64_t candidatesBefore = inner_->stats().candidatesExamined;
    if (timeQueries_) {
        const auto t0 = std::chrono::steady_clock::now();
        inner_->radiusQuery(pointId, radius, out);
        const auto t1 = std::chrono::steady_clock::now();
        extended_.queryTimeNs += static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
    } else {
        inner_->radiusQuery(pointId, radius, out);
    }
    const std::uint64_t candidates = inner_->stats().candidatesExamined - candidatesBefore;

    ++stats_.neighborQueries;
    stats_.candidatesExamined += candidates;
    stats_.neighborsReturned += out.size();

    if (grid_ != nullptr) {
        extended_.cellsExamined += grid_->cellsScannedFor(pointId, radius);
    }
    extended_.maxCandidatesPerQuery = std::max<std::uint64_t>(extended_.maxCandidatesPerQuery, candidates);
    extended_.maxNeighborsPerQuery = std::max<std::uint64_t>(extended_.maxNeighborsPerQuery, out.size());
}

ProcessMemory processMemory() {
    ProcessMemory m;
#if defined(_WIN32)
    PROCESS_MEMORY_COUNTERS pmc;
    std::memset(&pmc, 0, sizeof(pmc));
    if (GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc))) {
        m.available = true;
        m.currentRssBytes = static_cast<std::uint64_t>(pmc.WorkingSetSize);
        m.peakRssBytes = static_cast<std::uint64_t>(pmc.PeakWorkingSetSize);
    }
#else
    struct rusage usage;
    if (getrusage(RUSAGE_SELF, &usage) == 0) {
        m.available = true;
#if defined(__APPLE__)
        m.peakRssBytes = static_cast<std::uint64_t>(usage.ru_maxrss);  // bytes on macOS
#else
        m.peakRssBytes = static_cast<std::uint64_t>(usage.ru_maxrss) * 1024ull;  // KiB on Linux
#endif
    }
#if defined(__linux__)
    if (FILE* f = std::fopen("/proc/self/statm", "r")) {
        unsigned long size = 0;
        unsigned long resident = 0;
        if (std::fscanf(f, "%lu %lu", &size, &resident) == 2) {
            m.currentRssBytes = static_cast<std::uint64_t>(resident) *
                                static_cast<std::uint64_t>(sysconf(_SC_PAGESIZE));
        }
        std::fclose(f);
    }
#endif
#endif
    return m;
}

}  // namespace mcds::bench
