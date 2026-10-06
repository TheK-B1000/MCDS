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
    src/JsonIO.cpp
    src/algorithms/Marathe.cpp
    src/algorithms/Wan.cpp
    src/algorithms/Funke.cpp
    src/algorithms/LiSMIS.cpp
    src/algorithms/WanLevelMis.cpp
    src/ExactSmallMCDS.cpp
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
mcds_add_test(test_wan)
mcds_add_test(test_funke)
mcds_add_test(test_li_smis)
mcds_add_test(test_wan_level_mis)
mcds_add_test(test_exact_small)

# ---------------------------------------------------------------------------
# CGAL spatial backend (primary backend of the final study).
#
# Required by default. Point CMake at an install, e.g. the conda-forge env:
#   cmake -S cpp -B cpp/build-msvc -DCMAKE_PREFIX_PATH=<conda>/envs/mcds-cgal/Library
# A grid-only build is possible only by asking for it explicitly with
# -DMCDS_WITH_CGAL=OFF; such a binary refuses `--spatial-backend cgal` at run
# time instead of substituting another backend.
# ---------------------------------------------------------------------------
option(MCDS_WITH_CGAL "Build the CGAL spatial backend (required for the final study)" ON)
set(MCDS_CGAL_MIN_VERSION 6.0)
if(MCDS_WITH_CGAL)
    find_package(CGAL ${MCDS_CGAL_MIN_VERSION} CONFIG QUIET)
    if(NOT CGAL_FOUND)
        message(FATAL_ERROR
            "CGAL >= ${MCDS_CGAL_MIN_VERSION} not found, but MCDS_WITH_CGAL=ON (CGAL is the primary "
            "spatial backend of the final study).
"
            "Install it, e.g.:  conda create -n mcds-cgal -c conda-forge cgal-cpp=6.1.2 libboost-headers=1.88
"
            "then configure with -DCMAKE_PREFIX_PATH=<conda>/envs/mcds-cgal/Library.
"
            "Only for grid-only development builds: -DMCDS_WITH_CGAL=OFF.")
    endif()
    message(STATUS "MCDS: CGAL ${CGAL_VERSION} found (${CGAL_DIR})")
    add_library(mcds_cgal STATIC src/CgalSpatialIndex.cpp)
    target_include_directories(mcds_cgal PUBLIC include)
    target_link_libraries(mcds_cgal PUBLIC mcds_core CGAL::CGAL)
    if(MSVC)
        target_compile_options(mcds_cgal PRIVATE /W4 /permissive- /bigobj)
    else()
        target_compile_options(mcds_cgal PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endif()

# ---------------------------------------------------------------------------
# Experiment measurement harness used by python/run_study.py. The `mcds` CLI
# above remains the interactive / GUI driver.
#
#   mcds_bench      timing / work counters (stock allocator)
#   mcds_bench_mem  memory probes (heap-tracking operator new; never timed)
# ---------------------------------------------------------------------------
if(MSVC)
    set(MCDS_BI_WARNING_FLAGS "/W4 /permissive-")
else()
    set(MCDS_BI_WARNING_FLAGS "-Wall -Wextra -Wpedantic")
endif()
foreach(cfg "" _RELEASE _DEBUG _RELWITHDEBINFO _MINSIZEREL)
    string(STRIP "${CMAKE_CXX_FLAGS${cfg}}" _flags)
    string(REPLACE "\"" "\\\"" _flags "${_flags}")
    set(MCDS_BI_CXX_FLAGS${cfg} "${_flags}")
endforeach()
configure_file(include/bench/BuildInfo.hpp.in ${CMAKE_CURRENT_BINARY_DIR}/generated/bench/BuildInfo.hpp @ONLY)

add_library(mcds_bench_support STATIC src/bench/BenchSupport.cpp)
target_link_libraries(mcds_bench_support PUBLIC mcds_core)
target_include_directories(mcds_bench_support PUBLIC include ${CMAKE_CURRENT_BINARY_DIR}/generated)
if(WIN32)
    target_link_libraries(mcds_bench_support PUBLIC psapi)
endif()
if(MCDS_WITH_CGAL)
    target_link_libraries(mcds_bench_support PUBLIC mcds_cgal)
    target_compile_definitions(mcds_bench_support PUBLIC MCDS_WITH_CGAL=1)
else()
    target_compile_definitions(mcds_bench_support PUBLIC MCDS_WITH_CGAL=0)
endif()

function(mcds_add_bench target heap_tracking)
    if(heap_tracking)
        add_executable(${target} src/bench_main.cpp src/bench/HeapTracker.cpp)
    else()
        add_executable(${target} src/bench_main.cpp)
    endif()
    target_link_libraries(${target} PRIVATE mcds_bench_support)
    target_compile_definitions(${target} PRIVATE
        MCDS_HEAP_TRACKING=${heap_tracking}
        MCDS_BUILD_CONFIG="$<CONFIG>")
endfunction()

mcds_add_bench(mcds_bench 0)
mcds_add_bench(mcds_bench_mem 1)

foreach(target mcds_bench_support mcds_bench mcds_bench_mem)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /permissive-)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endforeach()

add_executable(test_bench_support tests/test_bench_support.cpp)
target_link_libraries(test_bench_support PRIVATE mcds_bench_support)
target_include_directories(test_bench_support PRIVATE tests)
if(MSVC)
    target_compile_options(test_bench_support PRIVATE /W4 /permissive-)
else()
    target_compile_options(test_bench_support PRIVATE -Wall -Wextra -Wpedantic)
endif()
add_test(NAME test_bench_support COMMAND test_bench_support)

# Differential spatial-backend tests: CGAL vs grid vs brute force, and every
# algorithm through each backend (CGAL builds only).
if(MCDS_WITH_CGAL)
    add_executable(test_spatial_backends tests/test_spatial_backends.cpp)
    target_link_libraries(test_spatial_backends PRIVATE mcds_bench_support)
    target_include_directories(test_spatial_backends PRIVATE tests)
    if(MSVC)
        target_compile_options(test_spatial_backends PRIVATE /W4 /permissive- /bigobj)
    else()
        target_compile_options(test_spatial_backends PRIVATE -Wall -Wextra -Wpedantic)
    endif()
    add_test(NAME test_spatial_backends COMMAND test_spatial_backends)

    # Output equivalence: current Funke and Li S-MIS against verbatim copies of the
    # pre-audit full-scan implementations (commit a5cebd7).
    add_executable(test_search_equivalence tests/test_search_equivalence.cpp
                   tests/reference/FunkeFullScanRef.cpp tests/reference/LiSMISFullScanRef.cpp)
    target_link_libraries(test_search_equivalence PRIVATE mcds_bench_support)
    target_include_directories(test_search_equivalence PRIVATE tests)
    if(MSVC)
        target_compile_options(test_search_equivalence PRIVATE /W4 /permissive- /bigobj)
    else()
        target_compile_options(test_search_equivalence PRIVATE -Wall -Wextra -Wpedantic)
    endif()
    add_test(NAME test_search_equivalence COMMAND test_search_equivalence)
endif()
