#include "PointSet.hpp"

#include <stdexcept>
#include <string>

namespace mcds {

PointSet::PointSet(std::vector<Point> points) : points_(std::move(points)) {
    // Detect the identity case first: ids are 0..n-1 in input order.
    identityIds_ = true;
    for (std::size_t i = 0; i < points_.size(); ++i) {
        if (points_[i].id != static_cast<int>(i)) {
            identityIds_ = false;
            break;
        }
    }

    if (identityIds_) {
        return;  // id == index, no table needed
    }

    idToIndex_.reserve(points_.size() * 2);
    for (std::size_t i = 0; i < points_.size(); ++i) {
        const auto inserted = idToIndex_.emplace(points_[i].id, i);
        if (!inserted.second) {
            throw std::invalid_argument("duplicate point id " + std::to_string(points_[i].id));
        }
    }
}

std::size_t PointSet::indexOf(int id) const {
    if (identityIds_) {
        if (id < 0 || static_cast<std::size_t>(id) >= points_.size()) {
            throw std::out_of_range("unknown point id " + std::to_string(id));
        }
        return static_cast<std::size_t>(id);
    }
    const auto it = idToIndex_.find(id);
    if (it == idToIndex_.end()) {
        throw std::out_of_range("unknown point id " + std::to_string(id));
    }
    return it->second;
}

bool PointSet::hasId(int id) const {
    if (identityIds_) {
        return id >= 0 && static_cast<std::size_t>(id) < points_.size();
    }
    return idToIndex_.find(id) != idToIndex_.end();
}

BoundingBox PointSet::boundingBox() const {
    BoundingBox box;
    if (points_.empty()) {
        return box;
    }
    box.minX = box.maxX = points_[0].x;
    box.minY = box.maxY = points_[0].y;
    for (const Point& p : points_) {
        if (p.x < box.minX) box.minX = p.x;
        if (p.x > box.maxX) box.maxX = p.x;
        if (p.y < box.minY) box.minY = p.y;
        if (p.y > box.maxY) box.maxY = p.y;
    }
    return box;
}

}  // namespace mcds
