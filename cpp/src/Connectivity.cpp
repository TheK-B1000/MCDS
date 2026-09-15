#include "Connectivity.hpp"

#include <queue>
#include <stdexcept>

namespace mcds {

ConnectivityResult findConnectedComponents(
    const PointSet& points,
    const SpatialIndex& index,
    double radius
) {
    if (!(radius >= 0.0)) {
        throw std::invalid_argument("findConnectedComponents: radius must be non-negative");
    }

    ConnectivityResult result;
    const std::size_t n = points.size();
    if (n == 0) {
        result.connected = true;
        return result;
    }

    std::vector<char> visited(n, 0);
    std::queue<std::size_t> queue;
    std::vector<int> neighbors;

    for (std::size_t seed = 0; seed < n; ++seed) {
        if (visited[seed]) {
            continue;
        }

        // Start a new component at the smallest unvisited input index.
        visited[seed] = 1;
        queue.push(seed);
        std::size_t size = 0;

        while (!queue.empty()) {
            const std::size_t current = queue.front();
            queue.pop();
            ++size;

            index.radiusQuery(points.idAt(current), radius, neighbors);
            for (const int neighborId : neighbors) {
                const std::size_t qi = points.indexOf(neighborId);
                if (!visited[qi]) {
                    visited[qi] = 1;
                    queue.push(qi);
                }
            }
        }

        result.componentSizes.push_back(size);
        result.visitedCount += size;
        if (size == 1) {
            ++result.isolatedCount;
        }
        if (size > result.largestComponent) {
            result.largestComponent = size;
        }
    }

    result.componentCount = result.componentSizes.size();
    result.connected = (result.componentCount <= 1);
    return result;
}

}  // namespace mcds
