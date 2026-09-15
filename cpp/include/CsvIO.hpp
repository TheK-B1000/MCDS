#pragma once

#include <istream>
#include <string>

#include "PointSet.hpp"

namespace mcds {

/// Reads a point set in the project's shared CSV format:
///
///     id,x,y
///     0,1.25,4.70
///     1,1.80,4.32
///
/// Accepted: an optional `id,x,y` header line, blank lines, `#` comment lines,
/// CRLF or LF endings, and surrounding whitespace around fields.
///
/// Rejected with a `std::runtime_error` naming the offending line: a wrong field
/// count, a field that is not fully numeric, a non-finite coordinate, a negative
/// id, a duplicate id, and a file with no points at all.
///
/// `label` only appears in error messages.
PointSet loadPointsCsv(std::istream& in, const std::string& label = "<stream>");

/// Same as above, reading from a file. Throws `std::runtime_error` if the file
/// cannot be opened.
PointSet loadPointsCsvFile(const std::string& path);

}  // namespace mcds
