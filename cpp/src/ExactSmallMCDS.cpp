#include "ExactSmallMCDS.hpp"

#include <cstdint>
#include <queue>
#include <string>

#include "GridSpatialIndex.hpp"

namespace mcds {
namespace {

std::size_t popcount64(std::uint64_t mask) {
    std::size_t bits = 0;
    while (mask) {
        bits += static_cast<std::size_t>(mask & 1ull);
        mask >>= 1;
    }
    return bits;
}

/// Every vertex is selected or has a selected neighbour. One radius query per
/// selected vertex; no adjacency is stored.
bool dominates(const PointSet& points, const SpatialIndex& index, double radius, const std::vector<char>& selected,
               std::vector<char>& dominated, std::vector<int>& neighbors) {
    const std::size_t n = points.size();
    std::fill(dominated.begin(), dominated.end(), 0);
    for (std::size_t i = 0; i < n; ++i) {
        if (!selected[i]) {
            continue;
        }
        dominated[i] = 1;
        index.radiusQuery(points.idAt(i), radius, neighbors);
        for (const int id : neighbors) {
            dominated[points.indexOf(id)] = 1;
        }
    }
    for (std::size_t i = 0; i < n; ++i) {
        if (!dominated[i]) {
            return false;
        }
    }
    return true;
}

/// The selected vertices induce a connected subgraph: BFS over selected
/// vertices with on-demand radius queries; no adjacency is stored.
bool selectedConnected(const PointSet& points, const SpatialIndex& index, double radius,
                       const std::vector<char>& selected, std::size_t selectedCount, std::vector<char>& visited,
                       std::vector<int>& neighbors) {
    if (selectedCount == 0) {
        return false;
    }
    const std::size_t n = points.size();
    std::size_t start = n;
    for (std::size_t i = 0; i < n; ++i) {
        if (selected[i]) {
            start = i;
            break;
        }
    }
    std::fill(visited.begin(), visited.end(), 0);
    std::queue<std::size_t> q;
    visited[start] = 1;
    q.push(start);
    std::size_t reached = 0;
    while (!q.empty()) {
        const std::size_t u = q.front();
        q.pop();
        ++reached;
        index.radiusQuery(points.idAt(u), radius, neighbors);
        for (const int id : neighbors) {
            const std::size_t v = points.indexOf(id);
            if (selected[v] && !visited[v]) {
                visited[v] = 1;
                q.push(v);
            }
        }
    }
    return reached == selectedCount;
}

}  // namespace

ExactSmallResult exactSmallMCDS(const PointSet& points, double radius, std::size_t maxN) {
    const std::size_t n = points.size();
    if (n == 0) {
        return ExactSmallResult{};
    }
    if (n > maxN) {
        throw std::invalid_argument("exactSmallMCDS: n=" + std::to_string(n) + " exceeds maxN=" +
                                    std::to_string(maxN));
    }

    // Implicit graph only: adjacency is recovered on demand from the points
    // through the SpatialIndex interface, exactly like every algorithm. The
    // grid stores point-index buckets (O(n)), never edges.
    const GridSpatialIndex index(points, radius > 0.0 ? radius : 1.0);

    std::vector<char> selected(n, 0);
    std::vector<char> dominated(n, 0);
    std::vector<char> visited(n, 0);
    std::vector<int> neighbors;

    const std::uint64_t limit = 1ull << static_cast<unsigned>(n);
    for (std::size_t k = 1; k <= n; ++k) {
        for (std::uint64_t mask = 1; mask < limit; ++mask) {
            if (popcount64(mask) != k) {
                continue;
            }
            for (std::size_t i = 0; i < n; ++i) {
                selected[i] = (mask & (1ull << i)) ? 1 : 0;
            }
            if (!dominates(points, index, radius, selected, dominated, neighbors)) {
                continue;
            }
            if (!selectedConnected(points, index, radius, selected, k, visited, neighbors)) {
                continue;
            }
            ExactSmallResult out;
            out.optSize = k;
            out.selectedIds.reserve(k);
            for (std::size_t i = 0; i < n; ++i) {
                if (selected[i]) {
                    out.selectedIds.push_back(points.idAt(i));
                }
            }
            return out;
        }
    }

    throw std::runtime_error("exactSmallMCDS: no CDS found (graph may be disconnected)");
}

}  // namespace mcds
