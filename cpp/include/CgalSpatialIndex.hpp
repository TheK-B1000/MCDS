#pragma once

#include <cstddef>
#include <memory>
#include <string>
#include <vector>

#include "PointSet.hpp"
#include "SpatialIndex.hpp"

namespace mcds {

/// CGAL-backed implementation of `SpatialIndex` (the primary backend of the
/// final study). Compiled only when CMake finds CGAL (MCDS_WITH_CGAL).
///
/// Data structure: `CGAL::Kd_tree` (package "dD Spatial Searching") over point
/// *indices*, using `CGAL::Search_traits_adapter` with a pointer property map
/// onto `CGAL::Search_traits_2<CGAL::Simple_cartesian<double>>`. The tree is
/// built eagerly in the constructor, so construction cost lands in
/// T_spatial_index and never in the first algorithm's T_algorithm.
///
/// Range query: `Kd_tree::search` with a `CGAL::Fuzzy_sphere` (radial range
/// search, epsilon 0) of radius r' = r(1 + 1e-9) + 8*eps*(|x| + |y| + r),
/// slightly larger than r so it is guaranteed to report every point the exact
/// predicate could accept (CGAL's own sphere boundary test is inclusive on one
/// internal path and exclusive on another, so it is never used to decide
/// adjacency). Adjacency is then decided by the same exact predicate as every
/// other backend:
///
///     distanceSquared(p, q) <= radius * radius
///
/// so the margin can only add candidates that are rejected, never change the
/// graph. Contract identical to `GridSpatialIndex`: query point excluded,
/// coincident distinct points included, boundary inclusive, order unspecified.
///
/// Counters: `neighborQueries` and `neighborsReturned` mean the same as for the
/// grid. `candidatesExamined` counts the points the CGAL radial search reported
/// (including the query point), i.e. the exact-predicate evaluations + 1 per
/// query. It is a backend-specific diagnostic: it does NOT count CGAL's
/// internal kd-tree node visits, which the API does not expose, and is not
/// comparable to the grid's cell-scan count.
///
/// The index keeps a reference to the `PointSet`, which must outlive it.
class CgalSpatialIndex : public SpatialIndex {
public:
    explicit CgalSpatialIndex(const PointSet& points);
    ~CgalSpatialIndex() override;

    CgalSpatialIndex(const CgalSpatialIndex&) = delete;
    CgalSpatialIndex& operator=(const CgalSpatialIndex&) = delete;

    std::size_t size() const override;
    const QueryStats& stats() const override { return stats_; }
    void resetStats() override { stats_.reset(); }
    const char* name() const override { return "cgal-kd-tree"; }

protected:
    void radiusQueryImpl(int pointId, double radius, std::vector<int>& out) const override;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    const PointSet* points_;
    mutable QueryStats stats_;
};

/// "6.1.2"-style version string of the CGAL headers this binary was built with.
std::string cgalVersionString();

/// Boost version string (BOOST_LIB_VERSION) of the headers CGAL was built with.
std::string cgalBoostVersionString();

}  // namespace mcds
