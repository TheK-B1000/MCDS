#include "Validator.hpp"

#include <queue>
#include <stdexcept>
#include <string>
#include <unordered_set>

namespace mcds {

ValidationResult validateCDS(
    const PointSet& points,
    const SpatialIndex& index,
    const std::vector<int>& selectedIds,
    double radius,
    ValidationOptions options
) {
    if (!(radius >= 0.0)) {
        throw std::invalid_argument("validateCDS: radius must be non-negative");
    }

    ValidationResult result;
    const std::size_t n = points.size();

    // Membership bitmap indexed by internal point index. An empty selection on
    // a non-empty point set fails both properties.
    std::vector<char> selected(n, 0);
    std::vector<std::size_t> selectedIndices;
    selectedIndices.reserve(selectedIds.size());

    std::unordered_set<int> seenIds;
    seenIds.reserve(selectedIds.size() * 2);
    for (const int id : selectedIds) {
        if (!seenIds.insert(id).second) {
            continue;  // ignore duplicate ids in the candidate list
        }
        if (!points.hasId(id)) {
            throw std::out_of_range("validateCDS: selected id " + std::to_string(id) +
                                   " is not in the point set");
        }
        const std::size_t idx = points.indexOf(id);
        selected[idx] = 1;
        selectedIndices.push_back(idx);
    }
    result.selectedCount = selectedIndices.size();

    if (n == 0) {
        result.dominating = true;
        result.connected = true;
        return result;
    }

    if (result.selectedCount == 0) {
        result.dominating = false;
        result.connected = false;  // empty set is not a connected CDS of a non-empty graph
        result.dominatedCount = 0;
        if (options.maxDiagnostics > 0) {
            for (std::size_t i = 0; i < n && result.undominatedIds.size() < options.maxDiagnostics; ++i) {
                result.undominatedIds.push_back(points.idAt(i));
            }
        }
        return result;
    }

    // --- Domination: one radius query per selected vertex ---------------
    std::vector<char> dominated(n, 0);
    std::vector<int> neighbors;
    for (const std::size_t idx : selectedIndices) {
        dominated[idx] = 1;
        index.radiusQuery(points.idAt(idx), radius, neighbors);
        for (const int nid : neighbors) {
            dominated[points.indexOf(nid)] = 1;
        }
    }

    for (std::size_t i = 0; i < n; ++i) {
        if (dominated[i]) {
            ++result.dominatedCount;
        } else if (options.maxDiagnostics > 0 &&
                   result.undominatedIds.size() < options.maxDiagnostics) {
            result.undominatedIds.push_back(points.idAt(i));
        }
    }
    result.dominating = (result.dominatedCount == n);

    // --- Connectivity: BFS restricted to selected vertices --------------
    std::vector<char> visited(n, 0);
    std::queue<std::size_t> queue;
    const std::size_t start = selectedIndices.front();
    visited[start] = 1;
    queue.push(start);
    std::size_t reached = 0;

    while (!queue.empty()) {
        const std::size_t current = queue.front();
        queue.pop();
        ++reached;

        index.radiusQuery(points.idAt(current), radius, neighbors);
        for (const int nid : neighbors) {
            const std::size_t qi = points.indexOf(nid);
            if (selected[qi] && !visited[qi]) {
                visited[qi] = 1;
                queue.push(qi);
            }
        }
    }

    result.connected = (reached == result.selectedCount);
    if (!result.connected && options.maxDiagnostics > 0) {
        for (const std::size_t idx : selectedIndices) {
            if (!visited[idx] &&
                result.disconnectedSelectedIds.size() < options.maxDiagnostics) {
                result.disconnectedSelectedIds.push_back(points.idAt(idx));
            }
        }
    }

    return result;
}

}  // namespace mcds
