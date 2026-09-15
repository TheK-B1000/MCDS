#include "GridSpatialIndex.hpp"

#include <cmath>
#include <limits>
#include <stdexcept>

namespace mcds {
namespace {

/// Cell-count budget, expressed as a multiple of n. Without a budget a
/// degenerate input (two points a million units apart) would ask for a grid
/// with 10^12 cells. Enlarging the cells instead keeps index memory O(n) and
/// stays correct, only slower per query in dense regions.
constexpr double kCellsPerPoint = 4.0;
constexpr double kMinCellBudget = 1024.0;

}  // namespace

GridSpatialIndex::GridSpatialIndex(const PointSet& points, double queryRadius) : points_(&points) {
    if (!(queryRadius > 0.0)) {
        throw std::invalid_argument("GridSpatialIndex: queryRadius must be positive");
    }
    if (points.size() > static_cast<std::size_t>(std::numeric_limits<std::uint32_t>::max())) {
        throw std::invalid_argument("GridSpatialIndex: more points than the 32-bit bucket arrays can address");
    }

    const BoundingBox box = points.boundingBox();
    originX_ = box.minX;
    originY_ = box.minY;

    if (points.empty()) {
        nx_ = ny_ = 1;
        cellStart_.assign(2, 0);
        return;
    }

    // Choose the cell size: the query radius, doubled as often as needed to fit
    // the cell budget.
    const double budget = kCellsPerPoint * static_cast<double>(points.size()) + kMinCellBudget;
    cellSize_ = queryRadius;
    double wantX = 0.0;
    double wantY = 0.0;
    bool sized = false;
    for (int attempt = 0; attempt < 2048; ++attempt) {
        wantX = std::floor(box.width() / cellSize_) + 1.0;
        wantY = std::floor(box.height() / cellSize_) + 1.0;
        if (wantX * wantY <= budget) {
            sized = true;
            break;
        }
        cellSize_ *= 2.0;
    }
    if (!sized) {
        throw std::invalid_argument("GridSpatialIndex: point coordinates span an unusable range");
    }
    nx_ = static_cast<int>(wantX);
    ny_ = static_cast<int>(wantY);

    // Bucket the points with a counting sort into CSR layout.
    const std::size_t cells = cellCount();
    cellStart_.assign(cells + 1, 0);
    for (std::size_t i = 0; i < points.size(); ++i) {
        const Point& p = points[i];
        const std::size_t c = cellIndex(cellX(p.x), cellY(p.y));
        ++cellStart_[c + 1];
    }
    for (std::size_t c = 0; c < cells; ++c) {
        cellStart_[c + 1] += cellStart_[c];
    }

    std::vector<std::uint32_t> cursor = cellStart_;
    cellPoints_.resize(points.size());
    for (std::size_t i = 0; i < points.size(); ++i) {
        const Point& p = points[i];
        const std::size_t c = cellIndex(cellX(p.x), cellY(p.y));
        cellPoints_[cursor[c]++] = static_cast<std::uint32_t>(i);
    }
}

int GridSpatialIndex::cellX(double x) const {
    const double raw = std::floor((x - originX_) / cellSize_);
    if (raw < 0.0) return 0;
    if (raw > static_cast<double>(nx_ - 1)) return nx_ - 1;
    return static_cast<int>(raw);
}

int GridSpatialIndex::cellY(double y) const {
    const double raw = std::floor((y - originY_) / cellSize_);
    if (raw < 0.0) return 0;
    if (raw > static_cast<double>(ny_ - 1)) return ny_ - 1;
    return static_cast<int>(raw);
}

int GridSpatialIndex::ringsFor(double radius) const {
    int k = static_cast<int>(std::ceil(radius / cellSize_));
    if (k < 1) {
        k = 1;
    }
    // `ceil` on a division can land one short after rounding; make the covering
    // guarantee explicit instead of trusting the floating-point result.
    while (static_cast<double>(k) * cellSize_ < radius) {
        ++k;
    }
    return k;
}

void GridSpatialIndex::radiusQueryImpl(int pointId, double radius, std::vector<int>& out) const {
    if (radius < 0.0) {
        throw std::invalid_argument("GridSpatialIndex: radius must not be negative");
    }

    const std::size_t pi = points_->indexOf(pointId);
    const Point& p = (*points_)[pi];

    ++stats_.neighborQueries;

    const double radiusSquared = radius * radius;
    const int k = ringsFor(radius);
    const int gx = cellX(p.x);
    const int gy = cellY(p.y);

    const int x0 = (gx - k > 0) ? gx - k : 0;
    const int y0 = (gy - k > 0) ? gy - k : 0;
    const int x1 = (gx + k < nx_ - 1) ? gx + k : nx_ - 1;
    const int y1 = (gy + k < ny_ - 1) ? gy + k : ny_ - 1;

    for (int cy = y0; cy <= y1; ++cy) {
        for (int cx = x0; cx <= x1; ++cx) {
            const std::size_t c = cellIndex(cx, cy);
            const std::uint32_t begin = cellStart_[c];
            const std::uint32_t end = cellStart_[c + 1];
            for (std::uint32_t slot = begin; slot < end; ++slot) {
                const std::uint32_t qi = cellPoints_[slot];
                ++stats_.candidatesExamined;
                if (qi == pi) {
                    continue;  // the query point is never its own neighbor
                }
                const Point& q = (*points_)[qi];
                if (distanceSquared(p, q) <= radiusSquared) {
                    out.push_back(q.id);
                }
            }
        }
    }

    stats_.neighborsReturned += out.size();
}

std::size_t GridSpatialIndex::indexBytes() const {
    return cellStart_.size() * sizeof(std::uint32_t) + cellPoints_.size() * sizeof(std::uint32_t);
}

}  // namespace mcds
