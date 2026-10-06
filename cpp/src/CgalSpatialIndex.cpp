#include "CgalSpatialIndex.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iterator>
#include <limits>
#include <stdexcept>

#include <boost/version.hpp>

#include <CGAL/Fuzzy_iso_box.h>
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
using Box = CGAL::Fuzzy_iso_box<Traits>;

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

    // Candidate box half-side. The exact predicate below accepts q only if
    // dx*dx + dy*dy <= r*r in floating point, which implies |dx|, |dy| <= r
    // up to rounding. The margin covers that rounding and the rounding of
    // p.x +/- half itself, so the box is a strict superset of the accepted set.
    const double scale = std::abs(p.x) + std::abs(p.y) + radius;
    const double half = radius * (1.0 + 1e-9) + 8.0 * std::numeric_limits<double>::epsilon() * scale;
    const Box box(CgalPoint(p.x - half, p.y - half), CgalPoint(p.x + half, p.y + half), 0.0,
                  impl_->tree->traits());

    std::vector<std::size_t>& cand = impl_->candidates;
    cand.clear();
    impl_->tree->search(std::back_inserter(cand), box);
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
