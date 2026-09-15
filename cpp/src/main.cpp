// Unified CLI for implicit-UDG MCDS experiments.
//
//   mcds --input datasets/example.csv --algorithm marathe --radius 1.0 \
//        --output results/example.json --pretty
//
//   mcds --input datasets/example.csv --check-connectivity

#include <cstdio>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>

#include "Connectivity.hpp"
#include "CsvIO.hpp"
#include "GridSpatialIndex.hpp"
#include "JsonIO.hpp"
#include "Metrics.hpp"
#include "PointSet.hpp"
#include "SpatialIndex.hpp"
#include "Validator.hpp"
#include "algorithms/Funke.hpp"
#include "algorithms/Marathe.hpp"
#include "algorithms/Wan.hpp"
#include "ExactSmallMCDS.hpp"

namespace {

void printUsage() {
    std::printf(
        "usage:\n"
        "  mcds --input <file.csv> --algorithm <marathe|wan|funke> [--radius R]\n"
        "       [--output results/out.json] [--pretty]\n"
        "  mcds --input <file.csv> --check-connectivity [--radius R]\n"
        "  mcds --input <file.csv> --exact-small [--radius R] [--output out.json]\n"
        "\n"
        "options:\n"
        "  --input PATH           point-set CSV (required)\n"
        "  --algorithm NAME       marathe | wan | funke\n"
        "  --radius R             UDG radius (default 1.0)\n"
        "  --output PATH          write JSON result (default: stdout)\n"
        "  --pretty               pretty-print JSON\n"
        "  --check-connectivity   report components and exit (no algorithm)\n"
        "  --exact-small          exact MCDS for n<=16 (analysis only)\n"
        "  --help                 show this help\n");
}

std::unique_ptr<mcds::MCDSAlgorithm> makeAlgorithm(const std::string& name) {
    if (name == "marathe") {
        return std::make_unique<mcds::MaratheAlgorithm>();
    }
    if (name == "wan") {
        return std::make_unique<mcds::WanAlgorithm>();
    }
    if (name == "funke") {
        return std::make_unique<mcds::FunkeAlgorithm>();
    }
    return nullptr;
}

}  // namespace

int main(int argc, char** argv) {
    std::string inputPath;
    std::string algorithmName;
    std::string outputPath;
    double radius = 1.0;
    bool pretty = false;
    bool checkConnectivityOnly = false;
    bool exactSmall = false;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto needValue = [&](const char* opt) -> const char* {
            if (i + 1 >= argc) {
                std::fprintf(stderr, "error: %s requires a value\n", opt);
                std::exit(2);
            }
            return argv[++i];
        };

        if (arg == "--help" || arg == "-h") {
            printUsage();
            return 0;
        }
        if (arg == "--input") {
            inputPath = needValue("--input");
            continue;
        }
        if (arg == "--algorithm") {
            algorithmName = needValue("--algorithm");
            continue;
        }
        if (arg == "--radius") {
            try {
                radius = std::stod(needValue("--radius"));
            } catch (const std::exception&) {
                std::fprintf(stderr, "error: --radius value is not a number\n");
                return 2;
            }
            continue;
        }
        if (arg == "--output") {
            outputPath = needValue("--output");
            continue;
        }
        if (arg == "--pretty") {
            pretty = true;
            continue;
        }
        if (arg == "--check-connectivity") {
            checkConnectivityOnly = true;
            continue;
        }
        if (arg == "--exact-small") {
            exactSmall = true;
            continue;
        }
        // Backward-compatible positional input: mcds file.csv
        if (!arg.empty() && arg[0] != '-') {
            if (!inputPath.empty()) {
                std::fprintf(stderr, "error: more than one input path given\n");
                return 2;
            }
            inputPath = arg;
            continue;
        }
        std::fprintf(stderr, "error: unknown option '%s'\n", arg.c_str());
        printUsage();
        return 2;
    }

    if (inputPath.empty()) {
        printUsage();
        return 2;
    }
    if (!(radius > 0.0)) {
        std::fprintf(stderr, "error: radius must be positive\n");
        return 2;
    }
    if (!checkConnectivityOnly && !exactSmall && algorithmName.empty()) {
        // Default for the milestone: run marathe when no mode is specified,
        // matching the early `mcds input.csv` habit once the algorithm exists.
        algorithmName = "marathe";
    }

    try {
        mcds::Timer totalTimer;
        mcds::RunResult result;
        result.inputFile = inputPath;
        result.radius = radius;
        result.algorithm = checkConnectivityOnly ? "none" : (exactSmall ? "exact_small" : algorithmName);

        mcds::Timer stage;
        const mcds::PointSet points = mcds::loadPointsCsvFile(inputPath);
        result.loadMs = stage.elapsedMs();
        result.n = points.size();

        stage.restart();
        mcds::GridSpatialIndex grid(points, radius);
        result.indexBuildMs = stage.elapsedMs();
        result.indexBackend = grid.name();
        mcds::SpatialIndex& index = grid;

        // --- Connectivity stage (own metric snapshot) -------------------
        index.resetStats();
        stage.restart();
        const mcds::ConnectivityResult connectivity =
            mcds::findConnectedComponents(points, index, radius);
        result.connectivityMs = stage.elapsedMs();
        result.connectedInput = connectivity.connected;
        result.componentCount = connectivity.componentCount;
        result.largestComponent = connectivity.largestComponent;
        result.isolatedCount = connectivity.isolatedCount;
        result.connectivityNeighborQueries = index.stats().neighborQueries;
        result.connectivityCandidatesExamined = index.stats().candidatesExamined;

        if (checkConnectivityOnly) {
            result.totalMs = totalTimer.elapsedMs();
            if (outputPath.empty()) {
                std::printf("input            %s\n", inputPath.c_str());
                std::printf("points           %zu\n", result.n);
                std::printf("radius           %.6g\n", radius);
                std::printf("connected        %s\n", result.connectedInput ? "true" : "false");
                std::printf("components       %zu\n", result.componentCount);
                std::printf("largest          %zu\n", result.largestComponent);
                std::printf("isolated         %zu\n", result.isolatedCount);
                std::printf("neighbor queries %llu\n",
                            static_cast<unsigned long long>(result.connectivityNeighborQueries));
                std::printf("connectivity_ms  %.3f\n", result.connectivityMs);
                return result.connectedInput ? 0 : 1;
            }
            std::ofstream out(outputPath);
            if (!out) {
                std::fprintf(stderr, "error: cannot write '%s'\n", outputPath.c_str());
                return 1;
            }
            mcds::writeRunResultJson(out, result, pretty);
            return result.connectedInput ? 0 : 1;
        }

        if (!result.connectedInput) {
            std::fprintf(stderr,
                         "error: input UDG is disconnected (%zu components); "
                         "refusing to run %s\n",
                         result.componentCount, result.algorithm.c_str());
            return 1;
        }

        if (exactSmall) {
            // ANALYSIS ONLY: never used by Marathe/Wan production paths.
            constexpr std::size_t kExactMaxN = 16;
            if (points.size() > kExactMaxN) {
                std::fprintf(stderr, "error: --exact-small requires n <= %zu (got %zu)\n", kExactMaxN,
                             points.size());
                return 2;
            }
            index.resetStats();
            stage.restart();
            const mcds::ExactSmallResult exact = mcds::exactSmallMCDS(points, radius, kExactMaxN);
            result.algorithmMs = stage.elapsedMs();
            result.algorithmNeighborQueries = 0;
            result.algorithmCandidatesExamined = 0;
            result.selectedIds = exact.selectedIds;
            result.cdsSize = exact.optSize;
            result.cdsRatio =
                result.n == 0 ? 0.0 : static_cast<double>(result.cdsSize) / static_cast<double>(result.n);

            index.resetStats();
            stage.restart();
            mcds::ValidationOptions vopts;
            vopts.maxDiagnostics = 32;
            const mcds::ValidationResult validation =
                mcds::validateCDS(points, index, exact.selectedIds, radius, vopts);
            result.validationMs = stage.elapsedMs();
            result.validationNeighborQueries = index.stats().neighborQueries;
            result.validationCandidatesExamined = index.stats().candidatesExamined;
            result.validDominating = validation.dominating;
            result.validConnected = validation.connected;
            result.totalMs = totalTimer.elapsedMs();

            if (outputPath.empty()) {
                mcds::writeRunResultJson(std::cout, result, true);
            } else {
                std::ofstream out(outputPath);
                if (!out) {
                    std::fprintf(stderr, "error: cannot write '%s'\n", outputPath.c_str());
                    return 1;
                }
                mcds::writeRunResultJson(out, result, pretty);
                std::printf("wrote %s  opt_size=%zu  valid=%s\n", outputPath.c_str(), result.cdsSize,
                            validation.valid() ? "true" : "false");
            }
            return validation.valid() ? 0 : 1;
        }

        auto algorithm = makeAlgorithm(algorithmName);
        if (!algorithm) {
            std::fprintf(stderr, "error: unknown algorithm '%s'\n", algorithmName.c_str());
            return 2;
        }

        // --- Algorithm stage --------------------------------------------
        index.resetStats();
        stage.restart();
        const mcds::MCDSResult cds = algorithm->solve(points, index, radius);
        result.algorithmMs = stage.elapsedMs();
        result.algorithmNeighborQueries = index.stats().neighborQueries;
        result.algorithmCandidatesExamined = index.stats().candidatesExamined;
        result.selectedIds = cds.selectedIds;
        result.cdsSize = cds.selectedIds.size();
        result.cdsRatio =
            result.n == 0 ? 0.0 : static_cast<double>(result.cdsSize) / static_cast<double>(result.n);

        // --- Validation stage -------------------------------------------
        index.resetStats();
        stage.restart();
        mcds::ValidationOptions vopts;
        vopts.maxDiagnostics = 32;
        const mcds::ValidationResult validation =
            mcds::validateCDS(points, index, cds.selectedIds, radius, vopts);
        result.validationMs = stage.elapsedMs();
        result.validationNeighborQueries = index.stats().neighborQueries;
        result.validationCandidatesExamined = index.stats().candidatesExamined;
        result.validDominating = validation.dominating;
        result.validConnected = validation.connected;

        result.totalMs = totalTimer.elapsedMs();

        if (!validation.valid()) {
            std::fprintf(stderr, "VALIDATION FAILED\n");
            std::fprintf(stderr, "Dominating: %s\n", validation.dominating ? "true" : "false");
            std::fprintf(stderr, "Connected:  %s\n", validation.connected ? "true" : "false");
            if (!validation.undominatedIds.empty()) {
                std::fprintf(stderr, "Undominated point IDs (capped):\n");
                for (const int id : validation.undominatedIds) {
                    std::fprintf(stderr, "  %d\n", id);
                }
            }
        }

        if (outputPath.empty()) {
            mcds::writeRunResultJson(std::cout, result, pretty || true);
        } else {
            std::ofstream out(outputPath);
            if (!out) {
                std::fprintf(stderr, "error: cannot write '%s'\n", outputPath.c_str());
                return 1;
            }
            mcds::writeRunResultJson(out, result, pretty);
            std::printf("wrote %s  cds_size=%zu  valid=%s  algorithm_ms=%.3f\n", outputPath.c_str(),
                        result.cdsSize, validation.valid() ? "true" : "false", result.algorithmMs);
        }

        return validation.valid() ? 0 : 1;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "error: %s\n", e.what());
        return 1;
    }
}
