#pragma once

#include <cstddef>
#include <unordered_map>
#include <vector>

#include "Point.hpp"

namespace mcds {

/// Axis-aligned bounding box of a point set.
struct BoundingBox {
    double minX = 0.0;
    double minY = 0.0;
    double maxX = 0.0;
    double maxY = 0.0;

    double width() const { return maxX - minX; }
    double height() const { return maxY - minY; }
};

/// The complete input to the problem: just the points.
///
/// This is the *only* thing the project stores at O(n). There is deliberately
/// no adjacency structure here, and none is ever built: adjacency is recovered
/// on demand through `SpatialIndex`.
///
/// Two addressing schemes coexist and must not be confused:
///   * an **index** in `[0, size())`, which is the position in input order and
///     is what internal data structures use;
///   * an **id**, which is the value read from the CSV and is what the public
///     query API and the JSON output speak in.
///
/// When the input ids happen to be exactly `0, 1, ..., n-1` in that order (the
/// case for every generator in `python/generators.py`) the two coincide and no
/// lookup table is allocated at all. Otherwise a hash map is built. This keeps
/// the common large-scale case free of a per-point map.
class PointSet {
public:
    PointSet() = default;

    /// Takes ownership of the points and builds the id -> index mapping.
    /// Throws `std::invalid_argument` if two points share an id.
    explicit PointSet(std::vector<Point> points);

    std::size_t size() const { return points_.size(); }
    bool empty() const { return points_.empty(); }

    /// Access by index in `[0, size())`. No bounds checking; callers inside the
    /// project always derive the index from the set itself.
    const Point& operator[](std::size_t index) const { return points_[index]; }

    const std::vector<Point>& points() const { return points_; }

    /// Index of the point carrying `id`. Throws `std::out_of_range` if absent.
    std::size_t indexOf(int id) const;

    bool hasId(int id) const;

    int idAt(std::size_t index) const { return points_[index].id; }

    /// True when ids are `0..n-1` in input order, i.e. id == index.
    bool usesIdentityIds() const { return identityIds_; }

    /// Bounding box of all points. Returns a zero box for an empty set.
    BoundingBox boundingBox() const;

private:
    std::vector<Point> points_;

    /// Only populated when `identityIds_` is false.
    std::unordered_map<int, std::size_t> idToIndex_;

    bool identityIds_ = true;
};

}  // namespace mcds
