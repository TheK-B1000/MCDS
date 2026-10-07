#include "algorithms/Funke.hpp"

#include <cstdint>
#include <stdexcept>
#include <vector>

namespace mcds {
namespace {

enum class Colour : std::uint8_t { White = 0, Red, Blue, Grey, Black };

}  // namespace

// Implementation note (pre-final audit). The colour rules, round structure,
// termination, exceptions and the min-id parent rule are those of Fig. 1 as
// before. Only the way the affected vertices are FOUND changed: the pre-audit
// code (commit a5cebd7) queried every red/white and every white vertex in every
// round; this version queries only the neighbourhoods
// of this round's new blacks (Phase III-a) and new blues (Phase III-b), which
// are exactly the vertices whose colour can change in those phases (adjacency
// is symmetric). Output identity with the pre-audit code is checked by
// tests/test_search_equivalence.cpp against a verbatim copy of it.
MCDSResult FunkeAlgorithm::solve(const PointSet& points, const SpatialIndex& index, double radius) {
    if (!(radius >= 0.0)) {
        throw std::invalid_argument("FunkeAlgorithm: radius must be non-negative");
    }
    if (points.empty()) {
        return MCDSResult{};
    }
    // Connectivity is a precondition verified once, untimed, for all four
    // algorithms by the experiment runner / CLI. A disconnected input is still
    // rejected below: the red frontier dies out while white vertices remain.

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
    std::size_t redCount = 1;
    std::size_t whiteCount = n - 1;
    std::vector<std::size_t> reds{leader};  // current red vertices (any order)

    // Round stamp instead of a per-round flag vector: recruitStamp[v] == round
    // marks a white recruited (turned red) in the current round.
    std::vector<std::uint32_t> recruitStamp(n, 0);

    std::vector<int> neighbors;
    std::vector<std::size_t> winners;
    std::vector<std::size_t> newBlues;
    std::vector<std::size_t> nextReds;
    // Progress: each round blacks ≥1 red while reds exist (paper invariant).
    for (std::size_t guard = 0; guard < n + 2; ++guard) {
        const std::uint32_t round = static_cast<std::uint32_t>(guard) + 1;
        if (redCount == 0 && whiteCount == 0) {
            break;
        }
        if (redCount == 0) {
            // Only possible when some vertex is unreachable from the leader.
            throw std::invalid_argument(
                "FunkeAlgorithm: input UDG is not connected (red frontier exhausted with white "
                "vertices left); refuse to run");
        }

        // Phases I–II: reds with locally minimal ID among red neighbours win.
        winners.clear();
        for (const std::size_t u : reds) {
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

        for (const std::size_t u : winners) {
            colour[u] = Colour::Black;
            --redCount;
            if (parent[u] >= 0) {
                colour[static_cast<std::size_t>(parent[u])] = Colour::Grey;
            }
        }

        // Phase III-a: red/white adjacent to new blacks → blue. Only
        // neighbours of new blacks can qualify.
        newBlues.clear();
        for (const std::size_t b : winners) {
            index.radiusQuery(points.idAt(b), radius, neighbors);
            for (const int nid : neighbors) {
                const std::size_t v = points.indexOf(nid);
                if (colour[v] == Colour::Red) {
                    --redCount;
                } else if (colour[v] == Colour::White) {
                    --whiteCount;
                } else {
                    continue;
                }
                colour[v] = Colour::Blue;
                newBlues.push_back(v);
            }
        }

        // Phase III-b: whites adjacent to new blues → red; parent = min-ID new
        // blue. Only neighbours of new blues can qualify; a white reached from
        // several new blues keeps the one with the smallest id.
        nextReds.clear();
        for (const std::size_t u : reds) {
            if (colour[u] == Colour::Red) {
                nextReds.push_back(u);  // reds that neither won nor turned blue
            }
        }
        for (const std::size_t b : newBlues) {
            index.radiusQuery(points.idAt(b), radius, neighbors);
            const int bid = points.idAt(b);
            for (const int nid : neighbors) {
                const std::size_t v = points.indexOf(nid);
                if (recruitStamp[v] == round) {
                    if (bid < points.idAt(static_cast<std::size_t>(parent[v]))) {
                        parent[v] = static_cast<int>(b);
                    }
                    continue;
                }
                if (colour[v] != Colour::White) {
                    continue;
                }
                colour[v] = Colour::Red;
                --whiteCount;
                ++redCount;
                parent[v] = static_cast<int>(b);
                recruitStamp[v] = round;
                nextReds.push_back(v);
            }
        }
        reds.swap(nextReds);
    }

    MCDSResult result;
    result.selectedIds.reserve(n);
    result.roles.reserve(n);
    for (std::size_t i = 0; i < n; ++i) {
        if (colour[i] == Colour::Black) {
            result.selectedIds.push_back(points.idAt(i));
            result.roles.emplace_back(points.idAt(i), "core");
        } else if (colour[i] == Colour::Grey) {
            result.selectedIds.push_back(points.idAt(i));
            result.roles.emplace_back(points.idAt(i), "connector");
        }
    }
    return result;
}

}  // namespace mcds
