#include "CgalSpatialIndex.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iterator>
#include <limits>
#include <stdexcept>

#include <boost/version.hpp>

#include <CGAL/Fuzzy_sphere.h>
#include <CGAL/Kd_tree.h>
#include <CGAL/Search_traits_2.h>
#include <CGAL/Search_traits_adapter.h>
#include <CGAL/Simple_cartesian.h>
#include <CGAL/property_map.h>
#include <CGAL/version.h>

namespace mcds {
namespace {

using Kernel = CGAL::Simple_cartesian<double>;
using CgalPoint = Kernel::Point_2;
using PointMap = CGAL::Pointer_property_map<CgalPoint>::const_type;
using BaseTraits = CGAL::Search_traits_2<Kernel>;
using Traits = CGAL::Search_traits_adapter<std::size_t, PointMap, BaseTraits>;
using Tree = CGAL::Kd_tree<Traits>;
using Sphere = CGAL::Fuzzy_sphere<Traits>;

}  // namespace

struct CgalSpatialIndex::Impl {
    std::vector<CgalPoint> coords;  // index -> CGAL point (same order as PointSet)
    std::unique_ptr<Tree> tree;
    mutable std::vector<std::size_t> candidates;  // reused query buffer
};

CgalSpatialIndex::CgalSpatialIndex(const PointSet& points) : impl_(std::make_unique<Impl>()), points_(&points) {
    const std::size_t n = points.size();
    impl_->coords.reserve(n);
    for (std::size_t i = 0; i < n; ++i) {
        impl_->coords.emplace_back(points[i].x, points[i].y);
    }
    std::vector<std::size_t> keys(n);
    for (std::size_t i = 0; i < n; ++i) {
        keys[i] = i;
    }
    const PointMap pmap = CGAL::make_property_map(static_cast<const CgalPoint*>(impl_->coords.data()));
    impl_->tree = std::make_unique<Tree>(keys.begin(), keys.end(), Tree::Splitter(), Traits(pmap));
    if (n > 0) {
        impl_->tree->build();  // eager: construction belongs to T_spatial_index
    }
}

CgalSpatialIndex::~CgalSpatialIndex() = default;

std::size_t CgalSpatialIndex::size() const { return points_->size(); }

void CgalSpatialIndex::radiusQueryImpl(int pointId, double radius, std::vector<int>& out) const {
    if (radius < 0.0) {
        throw std::invalid_argument("CgalSpatialIndex: radius must not be negative");
    }
    const std::size_t pi = points_->indexOf(pointId);
    const Point& p = (*points_)[pi];
    ++stats_.neighborQueries;

    // Candidate retrieval: CGAL radial range search (Fuzzy_sphere, eps = 0)
    // with radius r' slightly larger than r. CGAL's sphere is NOT used as the
    // adjacency test: in CGAL 6.1.2 its contains() is inclusive (<= r'^2) but
    // contains_point_given_as_coordinates() is exclusive (< r'^2), and which
    // one runs depends on the kd-tree's internal path. Every point the exact
    // predicate below can accept has squared distance <= r^2 up to rounding,
    // which is strictly below r'^2, so it is reported on either path. The
    // margin therefore only adds candidates (rejected below), never edges.
    const double scale = std::abs(p.x) + std::abs(p.y) + radius;
    const double searchRadius = radius * (1.0 + 1e-9) + 8.0 * std::numeric_limits<double>::epsilon() * scale;
    const Sphere sphere(CgalPoint(p.x, p.y), searchRadius, 0.0, impl_->tree->traits());

    std::vector<std::size_t>& cand = impl_->candidates;
    cand.clear();
    impl_->tree->search(std::back_inserter(cand), sphere);
    stats_.candidatesExamined += cand.size();

    const double radiusSquared = radius * radius;
    for (const std::size_t qi : cand) {
        if (qi == pi) {
            continue;  // the query point is never its own neighbour
        }
        const Point& q = (*points_)[qi];
        if (distanceSquared(p, q) <= radiusSquared) {
            out.push_back(q.id);
        }
    }
    stats_.neighborsReturned += out.size();
}

std::string cgalVersionString() { return CGAL_VERSION_STR; }

std::string cgalBoostVersionString() { return BOOST_LIB_VERSION; }

}  // namespace mcds
