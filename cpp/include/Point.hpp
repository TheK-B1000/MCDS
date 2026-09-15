#pragma once

namespace mcds {

/// A single input site of the Unit Disk Graph.
///
/// `id` is the identifier that came from the input CSV. It is preserved
/// unchanged all the way to the JSON output so that Python can map results
/// back onto its own point list.
struct Point {
    int id = -1;
    double x = 0.0;
    double y = 0.0;
};

/// Squared Euclidean distance.
///
/// Everything in this project compares squared distances against a squared
/// radius so that no `sqrt()` is ever needed on a hot path. For radius 1.0
/// this degenerates to the exact test `distanceSquared <= 1.0`.
inline double distanceSquared(const Point& a, const Point& b) {
    const double dx = a.x - b.x;
    const double dy = a.y - b.y;
    return dx * dx + dy * dy;
}

/// True when `a` and `b` are adjacent in the UDG of the given squared radius.
///
/// The comparison is `<=`, so a pair at distance exactly `radius` is adjacent.
inline bool withinRadiusSquared(const Point& a, const Point& b, double radiusSquared) {
    return distanceSquared(a, b) <= radiusSquared;
}

}  // namespace mcds
