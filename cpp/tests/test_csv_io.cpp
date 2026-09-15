#include <sstream>
#include <string>

#include "CsvIO.hpp"
#include "Point.hpp"
#include "PointSet.hpp"
#include "TestHarness.hpp"

using mcds::BoundingBox;
using mcds::distanceSquared;
using mcds::loadPointsCsv;
using mcds::Point;
using mcds::PointSet;

namespace {

PointSet parse(const std::string& text) {
    std::istringstream in(text);
    return loadPointsCsv(in, "<test>");
}

}  // namespace

// --------------------------------------------------------------------------
// Distance helpers
// --------------------------------------------------------------------------

MCDS_TEST(distance_squared_is_exact_for_axis_aligned_pairs) {
    const Point a{0, 0.0, 0.0};
    const Point b{1, 3.0, 4.0};
    MCDS_CHECK_EQ(distanceSquared(a, b), 25.0);
    MCDS_CHECK_EQ(distanceSquared(b, a), 25.0);
    MCDS_CHECK_EQ(distanceSquared(a, a), 0.0);
}

MCDS_TEST(unit_distance_boundary_is_inclusive) {
    const Point a{0, 0.0, 0.0};
    const Point onBoundary{1, 1.0, 0.0};
    const Point justOutside{2, 1.01, 0.0};

    // The exact comparison the project relies on for R = 1.0.
    MCDS_CHECK(distanceSquared(a, onBoundary) <= 1.0);
    MCDS_CHECK(!(distanceSquared(a, justOutside) <= 1.0));
    MCDS_CHECK(mcds::withinRadiusSquared(a, onBoundary, 1.0));
    MCDS_CHECK(!mcds::withinRadiusSquared(a, justOutside, 1.0));
}

// --------------------------------------------------------------------------
// Well-formed CSV
// --------------------------------------------------------------------------

MCDS_TEST(loads_csv_with_header) {
    const PointSet points = parse("id,x,y\n0,1.25,4.70\n1,1.80,4.32\n2,7.10,2.11\n");
    MCDS_CHECK_EQ(points.size(), std::size_t{3});
    MCDS_CHECK_EQ(points[0].id, 0);
    MCDS_CHECK_EQ(points[0].x, 1.25);
    MCDS_CHECK_EQ(points[0].y, 4.70);
    MCDS_CHECK_EQ(points[2].id, 2);
    MCDS_CHECK_EQ(points[2].x, 7.10);
}

MCDS_TEST(loads_csv_without_header) {
    const PointSet points = parse("0,0.0,0.0\n1,1.0,0.0\n");
    MCDS_CHECK_EQ(points.size(), std::size_t{2});
    MCDS_CHECK_EQ(points[1].id, 1);
}

MCDS_TEST(tolerates_crlf_blank_lines_comments_and_padding) {
    const PointSet points = parse("id,x,y\r\n# a comment\r\n\r\n 0 , -1.5 , 2.5 \r\n1,0,0\r\n");
    MCDS_CHECK_EQ(points.size(), std::size_t{2});
    MCDS_CHECK_EQ(points[0].x, -1.5);
    MCDS_CHECK_EQ(points[0].y, 2.5);
}

MCDS_TEST(accepts_negative_and_large_coordinates_and_scientific_notation) {
    const PointSet points = parse("0,-1e6,-2.5e-3\n1,1234567.875,-9999999.5\n");
    MCDS_CHECK_EQ(points.size(), std::size_t{2});
    MCDS_CHECK_EQ(points[0].x, -1e6);
    MCDS_CHECK_EQ(points[1].y, -9999999.5);
}

MCDS_TEST(identity_ids_are_detected_and_lookup_still_works_for_arbitrary_ids) {
    const PointSet identity = parse("0,0,0\n1,1,0\n2,2,0\n");
    MCDS_CHECK(identity.usesIdentityIds());
    MCDS_CHECK_EQ(identity.indexOf(2), std::size_t{2});
    MCDS_CHECK(!identity.hasId(3));

    // Sparse, out-of-order ids must still resolve, just via the hash map.
    const PointSet sparse = parse("70,0,0\n5,1,0\n900,2,0\n");
    MCDS_CHECK(!sparse.usesIdentityIds());
    MCDS_CHECK_EQ(sparse.indexOf(70), std::size_t{0});
    MCDS_CHECK_EQ(sparse.indexOf(5), std::size_t{1});
    MCDS_CHECK_EQ(sparse.indexOf(900), std::size_t{2});
    MCDS_CHECK(!sparse.hasId(0));
    MCDS_CHECK_THROWS(sparse.indexOf(0));
}

MCDS_TEST(bounding_box_spans_all_points) {
    const PointSet points = parse("0,-3,2\n1,5,-1\n2,0,7\n");
    const BoundingBox box = points.boundingBox();
    MCDS_CHECK_EQ(box.minX, -3.0);
    MCDS_CHECK_EQ(box.maxX, 5.0);
    MCDS_CHECK_EQ(box.minY, -1.0);
    MCDS_CHECK_EQ(box.maxY, 7.0);
    MCDS_CHECK_EQ(box.width(), 8.0);
    MCDS_CHECK_EQ(box.height(), 8.0);
}

// --------------------------------------------------------------------------
// Malformed CSV
// --------------------------------------------------------------------------

MCDS_TEST(rejects_empty_input) {
    MCDS_CHECK_THROWS(parse(""));
    MCDS_CHECK_THROWS(parse("id,x,y\n"));
    MCDS_CHECK_THROWS(parse("\n\n# nothing here\n"));
}

MCDS_TEST(rejects_wrong_field_count) {
    MCDS_CHECK_THROWS(parse("0,0,0\n1,1\n"));
    MCDS_CHECK_THROWS(parse("0,0,0\n1,1,1,1\n"));
}

MCDS_TEST(rejects_non_numeric_fields) {
    MCDS_CHECK_THROWS(parse("0,0,0\n1,abc,0\n"));
    MCDS_CHECK_THROWS(parse("0,0,0\nx1,0,0\n"));
    MCDS_CHECK_THROWS(parse("0,0,0\n1,1.0.0,0\n"));
    MCDS_CHECK_THROWS(parse("0,0,0\n1,0,\n"));
    MCDS_CHECK_THROWS(parse("0,0,0\n1,2.5abc,0\n"));
}

MCDS_TEST(rejects_non_finite_coordinates) {
    MCDS_CHECK_THROWS(parse("0,0,0\n1,nan,0\n"));
    MCDS_CHECK_THROWS(parse("0,0,0\n1,inf,0\n"));
    MCDS_CHECK_THROWS(parse("0,0,0\n1,0,-inf\n"));
}

MCDS_TEST(rejects_negative_and_duplicate_ids) {
    MCDS_CHECK_THROWS(parse("0,0,0\n-1,1,1\n"));
    MCDS_CHECK_THROWS(parse("7,0,0\n7,1,1\n"));
    MCDS_CHECK_THROWS(parse("0,0,0\n1,1,1\n1,2,2\n"));
}

MCDS_TEST(error_message_names_the_offending_line) {
    bool sawLineNumber = false;
    try {
        parse("id,x,y\n0,0,0\n1,oops,0\n");
    } catch (const std::exception& e) {
        const std::string message = e.what();
        sawLineNumber = message.find("<test>:3") != std::string::npos;
        if (!sawLineNumber) {
            std::printf("  (message was: %s)\n", message.c_str());
        }
    }
    MCDS_CHECK(sawLineNumber);
}

MCDS_TEST_MAIN()
