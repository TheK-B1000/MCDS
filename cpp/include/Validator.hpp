#pragma once

#include <cstddef>
#include <vector>

#include "PointSet.hpp"
#include "SpatialIndex.hpp"

namespace mcds {

/// Independent check that a candidate CDS is dominating and connected.
///
/// The validator does not trust algorithm internals. It only sees the point
/// set, the spatial index, the selected ids, and the radius.
struct ValidationResult {
    bool dominating = false;
    bool connected = false;

    std::size_t dominatedCount = 0;
    std::size_t selectedCount = 0;

    /// Present only when diagnostics are requested. Limited to the first
    /// `maxDiagnostics` undominated ids so million-point runs stay cheap.
    std::vector<int> undominatedIds;

    /// Selected points that were never reached by the selected-only BFS.
    /// Empty when `connected` is true or diagnostics are disabled.
    std::vector<int> disconnectedSelectedIds;

    bool valid() const { return dominating && connected; }
};

struct ValidationOptions {
    /// When zero, only counts are returned. When positive, collect up to this
    /// many offending ids for debugging.
    std::size_t maxDiagnostics = 0;
};

/// Validate a candidate connected dominating set.
///
/// Domination strategy: for each selected point, mark the point itself and
/// every neighbor returned by `radiusQuery` as dominated. This is one query
/// per selected point, which is cheaper than querying every unselected point
/// when the CDS is a small fraction of n.
///
/// Connectivity strategy: BFS restricted to the selected set. Neighbors that
/// are not selected are ignored, so paths through unselected vertices cannot
/// falsely connect the CDS.
ValidationResult validateCDS(
    const PointSet& points,
    const SpatialIndex& index,
    const std::vector<int>& selectedIds,
    double radius,
    ValidationOptions options = {}
);

}  // namespace mcds
