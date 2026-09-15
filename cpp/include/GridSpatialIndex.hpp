#pragma once

#include <cstdint>
#include <vector>

#include "PointSet.hpp"
#include "SpatialIndex.hpp"

namespace mcds {

/// Uniform-grid (spatial hashing) implementation of `SpatialIndex`.
///
/// Points are bucketed into square cells of side `cellSize`, which defaults to
/// the query radius. A radius query then only has to scan the 3x3 block of
/// cells around the query point. Buckets are stored in CSR form: one `cellStart`
/// offset array plus one array holding the point indices grouped by cell. Total
/// storage is `4 * n + 4 * cells` bytes and, crucially, is independent of the
/// number of UDG edges. A single dense cluster of 10,000 mutually adjacent
/// points would carry 50 million edges but still occupies only its 10,000 slots
/// here.
///
/// The index keeps a reference to the `PointSet`, which must outlive it.
class GridSpatialIndex : public SpatialIndex {
public:
    /// `queryRadius` is the radius the index is tuned for (1.0 for a unit disk
    /// graph). Queries with a different radius still return correct results,
    /// just with more cells scanned. Throws `std::invalid_argument` if
    /// `queryRadius <= 0`.
    GridSpatialIndex(const PointSet& points, double queryRadius);

    std::size_t size() const override { return points_->size(); }

    const QueryStats& stats() const override { return stats_; }

    void resetStats() override { stats_.reset(); }

    const char* name() const override { return "uniform-grid"; }

    // --- Introspection, used by tests and by the CLI report ---

    double cellSize() const { return cellSize_; }
    int cellsX() const { return nx_; }
    int cellsY() const { return ny_; }
    std::size_t cellCount() const { return static_cast<std::size_t>(nx_) * static_cast<std::size_t>(ny_); }

    /// Bytes held by the bucket arrays. Reported so experiments can show that
    /// index memory grows with n and not with the edge count.
    std::size_t indexBytes() const;

protected:
    void radiusQueryImpl(int pointId, double radius, std::vector<int>& out) const override;

private:
    int cellX(double x) const;
    int cellY(double y) const;
    std::size_t cellIndex(int gx, int gy) const {
        return static_cast<std::size_t>(gy) * static_cast<std::size_t>(nx_) + static_cast<std::size_t>(gx);
    }

    /// How many cell rings around the query cell must be scanned to be sure no
    /// point within `radius` is missed.
    int ringsFor(double radius) const;

    const PointSet* points_;

    double cellSize_ = 1.0;
    double originX_ = 0.0;
    double originY_ = 0.0;
    int nx_ = 1;
    int ny_ = 1;

    /// Size `cellCount() + 1`. Points of cell c are
    /// `cellPoints_[cellStart_[c] .. cellStart_[c + 1])`.
    std::vector<std::uint32_t> cellStart_;

    /// Point *indices* (not ids) grouped by cell.
    std::vector<std::uint32_t> cellPoints_;

    /// Counters are bookkeeping, not observable state, so queries stay const.
    mutable QueryStats stats_;
};

}  // namespace mcds
