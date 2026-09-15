#include "ExactSmallMCDS.hpp"

#include <cstdint>
#include <queue>
#include <string>

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

bool dominates(const std::vector<std::vector<std::size_t>>& adj, const std::vector<char>& selected) {
    const std::size_t n = adj.size();
    for (std::size_t i = 0; i < n; ++i) {
        if (selected[i]) {
            continue;
        }
        bool ok = false;
        for (const std::size_t j : adj[i]) {
            if (selected[j]) {
                ok = true;
                break;
            }
        }
        if (!ok) {
            return false;
        }
    }
    return true;
}

bool selectedConnected(const std::vector<std::vector<std::size_t>>& adj, const std::vector<char>& selected,
                       std::size_t selectedCount) {
    if (selectedCount == 0) {
        return false;
    }
    const std::size_t n = adj.size();
    std::size_t start = n;
    for (std::size_t i = 0; i < n; ++i) {
        if (selected[i]) {
            start = i;
            break;
        }
    }
    std::vector<char> visited(n, 0);
    std::queue<std::size_t> q;
    visited[start] = 1;
    q.push(start);
    std::size_t reached = 0;
    while (!q.empty()) {
        const std::size_t u = q.front();
        q.pop();
        ++reached;
        for (const std::size_t v : adj[u]) {
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

    // Explicit adjacency ONLY inside this analysis oracle.
    const double r2 = radius * radius;
    std::vector<std::vector<std::size_t>> adj(n);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = i + 1; j < n; ++j) {
            if (distanceSquared(points[i], points[j]) <= r2) {
                adj[i].push_back(j);
                adj[j].push_back(i);
            }
        }
    }

    const std::uint64_t limit = 1ull << static_cast<unsigned>(n);
    for (std::size_t k = 1; k <= n; ++k) {
        for (std::uint64_t mask = 1; mask < limit; ++mask) {
            if (popcount64(mask) != k) {
                continue;
            }
            std::vector<char> selected(n, 0);
            std::vector<int> ids;
            ids.reserve(k);
            for (std::size_t i = 0; i < n; ++i) {
                if (mask & (1ull << i)) {
                    selected[i] = 1;
                    ids.push_back(points.idAt(i));
                }
            }
            if (!dominates(adj, selected)) {
                continue;
            }
            if (!selectedConnected(adj, selected, k)) {
                continue;
            }
            ExactSmallResult out;
            out.optSize = k;
            out.selectedIds = std::move(ids);
            return out;
        }
    }

    throw std::runtime_error("exactSmallMCDS: no CDS found (graph may be disconnected)");
}

}  // namespace mcds
