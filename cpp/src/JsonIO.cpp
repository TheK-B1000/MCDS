#include "JsonIO.hpp"

#include <iomanip>
#include <sstream>

namespace mcds {
namespace {

void writeEscaped(std::ostream& out, const std::string& s) {
    out << '"';
    for (const char ch : s) {
        switch (ch) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << ch; break;
        }
    }
    out << '"';
}

std::string formatDouble(double v) {
    std::ostringstream oss;
    oss << std::setprecision(6) << std::defaultfloat << v;
    return oss.str();
}

}  // namespace

void writeRunResultJson(std::ostream& out, const RunResult& result, bool pretty) {
    const char* nl = pretty ? "\n" : "";
    const char* sp = pretty ? "  " : "";
    const char* colon = pretty ? ": " : ":";

    auto fieldRaw = [&](const std::string& key, const std::string& value) {
        out << sp << '"' << key << '"' << colon << value << ',' << nl;
    };
    auto fieldStr = [&](const std::string& key, const std::string& value) {
        out << sp << '"' << key << '"' << colon;
        writeEscaped(out, value);
        out << ',' << nl;
    };

    out << '{' << nl;

    fieldRaw("schema_version", std::to_string(result.schemaVersion));
    fieldStr("algorithm", result.algorithm);
    fieldStr("input_file", result.inputFile);
    fieldStr("index_backend", result.indexBackend);
    fieldRaw("n", std::to_string(result.n));
    fieldRaw("radius", formatDouble(result.radius));

    fieldRaw("connected_input", result.connectedInput ? "true" : "false");
    fieldRaw("component_count", std::to_string(result.componentCount));
    fieldRaw("largest_component", std::to_string(result.largestComponent));
    fieldRaw("isolated_count", std::to_string(result.isolatedCount));

    fieldRaw("cds_size", std::to_string(result.cdsSize));
    fieldRaw("cds_ratio", formatDouble(result.cdsRatio));

    fieldRaw("load_ms", formatDouble(result.loadMs));
    fieldRaw("index_build_ms", formatDouble(result.indexBuildMs));
    fieldRaw("connectivity_ms", formatDouble(result.connectivityMs));
    fieldRaw("algorithm_ms", formatDouble(result.algorithmMs));
    fieldRaw("validation_ms", formatDouble(result.validationMs));
    fieldRaw("total_ms", formatDouble(result.totalMs));

    fieldRaw("connectivity_neighbor_queries", std::to_string(result.connectivityNeighborQueries));
    fieldRaw("connectivity_candidates_examined",
             std::to_string(result.connectivityCandidatesExamined));
    fieldRaw("algorithm_neighbor_queries", std::to_string(result.algorithmNeighborQueries));
    fieldRaw("algorithm_candidates_examined", std::to_string(result.algorithmCandidatesExamined));
    fieldRaw("validation_neighbor_queries", std::to_string(result.validationNeighborQueries));
    fieldRaw("validation_candidates_examined",
             std::to_string(result.validationCandidatesExamined));

    fieldRaw("valid_dominating", result.validDominating ? "true" : "false");
    fieldRaw("valid_connected", result.validConnected ? "true" : "false");

    out << sp << "\"selected_ids\"" << colon << '[';
    for (std::size_t i = 0; i < result.selectedIds.size(); ++i) {
        if (i > 0) out << ',';
        if (pretty && result.selectedIds.size() > 24 && i % 24 == 0) {
            out << nl << sp << sp;
        }
        out << result.selectedIds[i];
    }
    out << ']' << nl;

    out << '}' << nl;
}

}  // namespace mcds
