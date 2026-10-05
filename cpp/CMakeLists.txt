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
