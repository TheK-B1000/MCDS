// Milestone 1 driver: load a point set, build the spatial index, and exercise
// radius queries. No MCDS algorithm is wired up yet, and no graph is built.
//
//     mcds <input.csv> [--radius R]

#include <cstdio>
#include <exception>
#include <string>
#include <vector>

#include "CsvIO.hpp"
#include "GridSpatialIndex.hpp"
#include "Metrics.hpp"
#include "PointSet.hpp"
#include "SpatialIndex.hpp"

namespace {

void printUsage() {
    std::printf(
        "usage: mcds <input.csv> [--radius R]\n"
        "\n"
        "  Loads a point set, builds the spatial index, and reports degree\n"
        "  statistics obtained purely through radius queries.\n");
}

/// Walks every point once through the SpatialIndex to summarise the UDG without
/// ever storing it. Only one reusable neighbor buffer is held at a time, so peak
/// memory stays O(n + max degree) rather than O(edges).
struct DegreeSummary {
    std::size_t minDegree = 0;
    std::size_t maxDegree = 0;
    std::size_t isolated = 0;
    double meanDegree = 0.0;
    double elapsedMs = 0.0;
};

DegreeSummary summarizeDegrees(const mcds::PointSet& points, const mcds::SpatialIndex& index, double radius) {
    DegreeSummary summary;
    if (points.empty()) {
        return summary;
    }

    mcds::Timer timer;
    std::vector<int> neighbors;  // one buffer, reused for every query
    unsigned long long degreeTotal = 0;
    summary.minDegree = static_cast<std::size_t>(-1);

    for (const mcds::Point& p : points.points()) {
        index.radiusQuery(p.id, radius, neighbors);
        const std::size_t degree = neighbors.size();
        degreeTotal += degree;
        if (degree < summary.minDegree) summary.minDegree = degree;
        if (degree > summary.maxDegree) summary.maxDegree = degree;
        if (degree == 0) ++summary.isolated;
    }

    summary.meanDegree = static_cast<double>(degreeTotal) / static_cast<double>(points.size());
    summary.elapsedMs = timer.elapsedMs();
    return summary;
}

}  // namespace

int main(int argc, char** argv) {
    std::string inputPath;
    double radius = 1.0;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            printUsage();
            return 0;
        }
        if (arg == "--radius") {
            if (i + 1 >= argc) {
                std::fprintf(stderr, "error: --radius requires a value\n");
                return 2;
            }
            try {
                radius = std::stod(argv[++i]);
            } catch (const std::exception&) {
                std::fprintf(stderr, "error: --radius value '%s' is not a number\n", argv[i]);
                return 2;
            }
            continue;
        }
        if (!arg.empty() && arg[0] == '-') {
            std::fprintf(stderr, "error: unknown option '%s'\n", arg.c_str());
            printUsage();
            return 2;
        }
        if (!inputPath.empty()) {
            std::fprintf(stderr, "error: more than one input file given\n");
            return 2;
        }
        inputPath = arg;
    }

    if (inputPath.empty()) {
        printUsage();
        return 2;
    }
    if (!(radius > 0.0)) {
        std::fprintf(stderr, "error: radius must be positive\n");
        return 2;
    }

    try {
        mcds::Timer loadTimer;
        const mcds::PointSet points = mcds::loadPointsCsvFile(inputPath);
        const double loadMs = loadTimer.elapsedMs();

        const mcds::BoundingBox box = points.boundingBox();

        mcds::Timer buildTimer;
        mcds::GridSpatialIndex grid(points, radius);
        const double buildMs = buildTimer.elapsedMs();

        const mcds::SpatialIndex& index = grid;
        const DegreeSummary degrees = summarizeDegrees(points, index, radius);

        std::printf("input            %s\n", inputPath.c_str());
        std::printf("points           %zu\n", points.size());
        std::printf("radius           %.6g\n", radius);
        std::printf("bounding box     [%.6g, %.6g] x [%.6g, %.6g]\n", box.minX, box.maxX, box.minY, box.maxY);
        std::printf("identity ids     %s\n", points.usesIdentityIds() ? "yes" : "no");
        std::printf("\n");
        std::printf("index backend    %s\n", index.name());
        std::printf("cell size        %.6g\n", grid.cellSize());
        std::printf("grid             %d x %d cells (%zu total)\n", grid.cellsX(), grid.cellsY(), grid.cellCount());
        std::printf("index memory     %.3f MB\n", static_cast<double>(grid.indexBytes()) / (1024.0 * 1024.0));
        std::printf("\n");
        std::printf("degree min/mean/max   %zu / %.3f / %zu\n", degrees.minDegree, degrees.meanDegree,
                    degrees.maxDegree);
        std::printf("isolated points       %zu\n", degrees.isolated);
        std::printf("implied UDG edges     %.0f  (counted, never stored)\n",
                    static_cast<double>(index.stats().neighborsReturned) / 2.0);
        std::printf("\n");
        std::printf("neighbor queries      %llu\n", static_cast<unsigned long long>(index.stats().neighborQueries));
        std::printf("candidates examined   %llu\n", static_cast<unsigned long long>(index.stats().candidatesExamined));
        std::printf("candidates per result %.2f\n",
                    index.stats().neighborsReturned == 0
                        ? 0.0
                        : static_cast<double>(index.stats().candidatesExamined) /
                              static_cast<double>(index.stats().neighborsReturned));
        std::printf("\n");
        std::printf("csv load              %.2f ms\n", loadMs);
        std::printf("index build           %.2f ms\n", buildMs);
        std::printf("all radius queries    %.2f ms\n", degrees.elapsedMs);
        return 0;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "error: %s\n", e.what());
        return 1;
    }
}
