#include "CsvIO.hpp"

#include <cctype>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace mcds {
namespace {

std::string trim(const std::string& s) {
    std::size_t b = 0;
    std::size_t e = s.size();
    while (b < e && std::isspace(static_cast<unsigned char>(s[b]))) ++b;
    while (e > b && std::isspace(static_cast<unsigned char>(s[e - 1]))) --e;
    return s.substr(b, e - b);
}

std::vector<std::string> splitFields(const std::string& line) {
    std::vector<std::string> fields;
    std::string current;
    for (const char ch : line) {
        if (ch == ',') {
            fields.push_back(trim(current));
            current.clear();
        } else {
            current.push_back(ch);
        }
    }
    fields.push_back(trim(current));
    return fields;
}

/// Parses a complete integer token. Returns false on trailing junk, an empty
/// token, or overflow.
bool parseInt(const std::string& token, int& value) {
    if (token.empty()) return false;
    errno = 0;
    char* end = nullptr;
    const long parsed = std::strtol(token.c_str(), &end, 10);
    if (end != token.c_str() + token.size()) return false;
    if (errno == ERANGE) return false;
    if (parsed < static_cast<long>(std::numeric_limits<int>::min()) ||
        parsed > static_cast<long>(std::numeric_limits<int>::max())) {
        return false;
    }
    value = static_cast<int>(parsed);
    return true;
}

/// Parses a complete finite floating-point token. NaN and infinity are rejected
/// because every downstream distance comparison would silently become false.
bool parseDouble(const std::string& token, double& value) {
    if (token.empty()) return false;
    errno = 0;
    char* end = nullptr;
    const double parsed = std::strtod(token.c_str(), &end);
    if (end != token.c_str() + token.size()) return false;
    if (errno == ERANGE) return false;
    if (!std::isfinite(parsed)) return false;
    value = parsed;
    return true;
}

[[noreturn]] void fail(const std::string& label, std::size_t lineNumber, const std::string& what) {
    std::ostringstream msg;
    msg << label << ":" << lineNumber << ": " << what;
    throw std::runtime_error(msg.str());
}

}  // namespace

PointSet loadPointsCsv(std::istream& in, const std::string& label) {
    std::vector<Point> points;
    std::string line;
    std::size_t lineNumber = 0;
    bool sawFirstContentLine = false;

    while (std::getline(in, line)) {
        ++lineNumber;

        // Tolerate CRLF endings even when the file is read in text mode on a
        // platform that does not translate them.
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }

        const std::string stripped = trim(line);
        if (stripped.empty() || stripped[0] == '#') {
            continue;
        }

        const std::vector<std::string> fields = splitFields(stripped);

        if (!sawFirstContentLine) {
            sawFirstContentLine = true;
            // A first content line whose id field is not an integer is treated
            // as the column header and skipped.
            int probe = 0;
            if (fields.size() == 3 && !parseInt(fields[0], probe)) {
                continue;
            }
        }

        if (fields.size() != 3) {
            fail(label, lineNumber,
                 "expected 3 comma-separated fields (id,x,y) but found " + std::to_string(fields.size()));
        }

        Point p;
        if (!parseInt(fields[0], p.id)) {
            fail(label, lineNumber, "id field '" + fields[0] + "' is not an integer");
        }
        if (p.id < 0) {
            fail(label, lineNumber, "id field '" + fields[0] + "' is negative");
        }
        if (!parseDouble(fields[1], p.x)) {
            fail(label, lineNumber, "x field '" + fields[1] + "' is not a finite number");
        }
        if (!parseDouble(fields[2], p.y)) {
            fail(label, lineNumber, "y field '" + fields[2] + "' is not a finite number");
        }
        points.push_back(p);
    }

    if (points.empty()) {
        throw std::runtime_error(label + ": contains no points");
    }

    try {
        return PointSet(std::move(points));
    } catch (const std::invalid_argument& e) {
        throw std::runtime_error(label + ": " + e.what());
    }
}

PointSet loadPointsCsvFile(const std::string& path) {
    std::ifstream in(path);
    if (!in) {
        throw std::runtime_error("cannot open input file '" + path + "'");
    }
    return loadPointsCsv(in, path);
}

}  // namespace mcds
