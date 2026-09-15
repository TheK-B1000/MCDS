#pragma once

#include <ostream>
#include <string>
#include <vector>

namespace mcds {

struct RunResult {
    int schemaVersion = 1;
    std::string algorithm;
    std::string inputFile;
    std::string indexBackend;
    std::size_t n = 0;
    double radius = 1.0;

    bool connectedInput = false;
    std::size_t componentCount = 0;
    std::size_t largestComponent = 0;
    std::size_t isolatedCount = 0;

    std::size_t cdsSize = 0;
    double cdsRatio = 0.0;

    double loadMs = 0.0;
    double indexBuildMs = 0.0;
    double connectivityMs = 0.0;
    double algorithmMs = 0.0;
    double validationMs = 0.0;
    double totalMs = 0.0;

    unsigned long long connectivityNeighborQueries = 0;
    unsigned long long connectivityCandidatesExamined = 0;

    unsigned long long algorithmNeighborQueries = 0;
    unsigned long long algorithmCandidatesExamined = 0;

    unsigned long long validationNeighborQueries = 0;
    unsigned long long validationCandidatesExamined = 0;

    bool validDominating = false;
    bool validConnected = false;

    std::vector<int> selectedIds;
};

/// Writes `result` as JSON. Header-only, no third-party dependency.
void writeRunResultJson(std::ostream& out, const RunResult& result, bool pretty);

}  // namespace mcds
