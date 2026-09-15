cmake_minimum_required(VERSION 3.16)
project(mcds_implicit_udg LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

# ---------------------------------------------------------------------------
# mcds_core: everything except the entry point, so tests can link against it.
#
# No third-party dependency. CGAL is not required by this target: the spatial
# index in use is a self-contained uniform grid behind the SpatialIndex
# interface. A CGAL-backed index can be added later as a second implementation
# of that interface without touching this list.
# ---------------------------------------------------------------------------
add_library(mcds_core STATIC
    src/PointSet.cpp
    src/GridSpatialIndex.cpp
    src/CsvIO.cpp
    src/Connectivity.cpp
    src/Validator.cpp
    src/algorithms/Marathe.cpp
)
target_include_directories(mcds_core PUBLIC include)

if(MSVC)
    target_compile_options(mcds_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(mcds_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

# ---------------------------------------------------------------------------
# Command-line driver
# ---------------------------------------------------------------------------
add_executable(mcds src/main.cpp)
target_link_libraries(mcds PRIVATE mcds_core)

# ---------------------------------------------------------------------------
# Tests. Registered with CTest; run with `ctest --test-dir <build dir>`.
#
# The tests directory is on the include path of test targets only, which is what
# keeps the brute-force reference in BruteForce.hpp unreachable from mcds_core.
# ---------------------------------------------------------------------------
enable_testing()

function(mcds_add_test test_name)
    add_executable(${test_name} tests/${test_name}.cpp)
    target_link_libraries(${test_name} PRIVATE mcds_core)
    target_include_directories(${test_name} PRIVATE tests)
    if(MSVC)
        target_compile_options(${test_name} PRIVATE /W4 /permissive-)
    else()
        target_compile_options(${test_name} PRIVATE -Wall -Wextra -Wpedantic)
    endif()
    add_test(NAME ${test_name} COMMAND ${test_name})
endfunction()

mcds_add_test(test_csv_io)
mcds_add_test(test_spatial_index)
mcds_add_test(test_connectivity)
mcds_add_test(test_validator)
mcds_add_test(test_marathe)
