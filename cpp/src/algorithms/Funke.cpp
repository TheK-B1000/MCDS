#include "algorithms/Funke.hpp"

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <vector>

#include "Connectivity.hpp"

namespace mcds {
namespace {

enum class Colour : std::uint8_t { White = 0, Red, Blue, Grey, Black };

}  // namespace

MCDSResult FunkeAlgorithm::solve(const PointSet& points, const SpatialIndex& index, double radius) {
    if (!(radius >= 0.0)) {
        throw std::invalid_argument("FunkeAlgorithm: radius must be non-negative");
    }
    if (points.empty()) {
        return MCDSResult{};
    }
    if (!isConnected(points, index, radius)) {
        throw std::invalid_argument(
            "FunkeAlgorithm: input UDG is not connected; refuse to run");
    }

    const std::size_t n = points.size();
    std::vector<Colour> colour(n, Colour::White);
    std::vector<int> parent(n, -1);  // index of blue recruiter; -1 = none

    std::size_t leader = 0;
    for (std::size_t i = 1; i < n; ++i) {
        if (points.idAt(i) < points.idAt(leader)) {
            leader = i;
        }
    }
    colour[leader] = Colour::Red;

    std::vector<int> neighbors;
    // Progress: each round blacks ≥1 red while reds exist (paper invariant).
    for (std::size_t guard = 0; guard < n + 2; ++guard) {
        bool hasRed = false;
        bool hasWhite = false;
        for (std::size_t i = 0; i < n; ++i) {
            if (colour[i] == Colour::Red) {
                hasRed = true;
            } else if (colour[i] == Colour::White) {
                hasWhite = true;
            }
        }
        if (!hasRed && !hasWhite) {
            break;
        }
        if (!hasRed) {
            // Connected UDG should not strand whites without a red frontier.
            throw std::runtime_error("FunkeAlgorithm: whites remain without red frontier");
        }

        // Phases I–II: reds with locally minimal ID among red neighbours win.
        std::vector<std::size_t> winners;
        for (std::size_t u = 0; u < n; ++u) {
            if (colour[u] != Colour::Red) {
                continue;
            }
            index.radiusQuery(points.idAt(u), radius, neighbors);
            bool loses = false;
            for (const int nid : neighbors) {
                const std::size_t v = points.indexOf(nid);
                if (colour[v] == Colour::Red && points.idAt(v) < points.idAt(u)) {
                    loses = true;
                    break;
                }
            }
            if (!loses) {
                winners.push_back(u);
            }
        }
        if (winners.empty()) {
            throw std::runtime_error("FunkeAlgorithm: no red winner in a round");
        }

        std::vector<char> isNewBlack(n, 0);
        for (const std::size_t u : winners) {
            colour[u] = Colour::Black;
            isNewBlack[u] = 1;
            if (parent[u] >= 0) {
                colour[static_cast<std::size_t>(parent[u])] = Colour::Grey;
            }
        }

        // Phase III: red/white adjacent to new blacks → blue.
        std::vector<char> isNewBlue(n, 0);
        std::vector<std::size_t> newBlues;
        for (std::size_t u = 0; u < n; ++u) {
            if (colour[u] != Colour::Red && colour[u] != Colour::White) {
                continue;
            }
            index.radiusQuery(points.idAt(u), radius, neighbors);
            bool hitBlack = false;
            for (const int nid : neighbors) {
                if (isNewBlack[points.indexOf(nid)]) {
                    hitBlack = true;
                    break;
                }
            }
            if (hitBlack) {
                colour[u] = Colour::Blue;
                isNewBlue[u] = 1;
                newBlues.push_back(u);
            }
        }

        // Phase III: whites adjacent to new blues → red; parent = min-ID new blue.
        for (std::size_t u = 0; u < n; ++u) {
            if (colour[u] != Colour::White) {
                continue;
            }
            index.radiusQuery(points.idAt(u), radius, neighbors);
            int bestParent = -1;
            int bestId = 0;
            for (const int nid : neighbors) {
                const std::size_t v = points.indexOf(nid);
                if (!isNewBlue[v]) {
                    continue;
                }
                const int vid = points.idAt(v);
                if (bestParent < 0 || vid < bestId) {
                    bestParent = static_cast<int>(v);
                    bestId = vid;
                }
            }
            if (bestParent >= 0) {
                colour[u] = Colour::Red;
                parent[u] = bestParent;
            }
        }
    }

    MCDSResult result;
    result.selectedIds.reserve(n);
    for (std::size_t i = 0; i < n; ++i) {
        if (colour[i] == Colour::Black || colour[i] == Colour::Grey) {
            result.selectedIds.push_back(points.idAt(i));
        }
    }
    return result;
}

}  // namespace mcds
