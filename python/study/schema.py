"""Versioned long-form result schemas for MCDS studies.

One row of ``raw_runs.csv`` = one algorithm execution on one graph for one
repetition (warmups, timed repetitions, memory probes and counter passes are
all kept; ``phase`` says which is which). Nothing is pre-aggregated.

Bump ``SCHEMA_VERSION`` whenever a column is added, removed or redefined.
"""

from __future__ import annotations

SCHEMA_VERSION = "mcds-results-3"

# Execution phases. Only TIMED rows enter runtime statistics.
PHASE_WARMUP = "warmup"
PHASE_TIMED = "timed"
PHASE_MEMORY = "memory_probe"
PHASE_COUNTERS = "counters"
PHASES = (PHASE_WARMUP, PHASE_TIMED, PHASE_MEMORY, PHASE_COUNTERS)

RAW_RUN_COLUMNS = [
    # identity
    "schema_version",
    "methodology_version",
    "study_id",
    "experiment_id",
    "config_sha256",
    "trial_id",
    "graph_id",
    "dataset_id",
    "cell_id",
    "replicate",
    "graph_seed",
    "algorithm",
    "algorithm_seed",
    "algorithm_source_sha256",
    "git_commit",
    "git_dirty",
    "machine_id",
    "solver_sha256",
    "build_config",
    # point data (denormalised for readability; full detail in datasets.csv)
    "source_type",
    "geometry",
    "n",
    "radius",
    "radius_units",
    "density_target",
    "dataset_sha256",
    "points_fingerprint",
    # spatial backend (one per row; never mixed within an algorithm comparison)
    "spatial_backend",
    "spatial_index_name",
    "t_spatial_index_ms",
    "index_bytes",
    "index_build_peak_bytes",
    "final_representation_bytes",
    "backend_crosscheck",
    # execution
    "phase",
    "repetition",
    "sequence",
    "process_mode",
    "instrumentation",
    "execution_order",
    "execution_position",
    "schedule_row",
    # timing (primary comparison uses t_algorithm_ms on phase == timed)
    "t_algorithm_ns",
    "t_algorithm_ms",
    "t_validation_ms",
    # spatial / neighbour work
    "neighbor_queries",
    "neighbors_returned",
    "avg_neighbors_per_query",
    # backend-specific diagnostics: filled only for their own backend, else empty
    "grid_candidates_examined",
    "grid_distance_computations",
    "grid_avg_candidates_per_query",
    "grid_cells_examined",
    "grid_max_candidates_per_query",
    "cgal_range_candidates",
    "cgal_exact_distance_evaluations",
    "cgal_max_range_candidates_per_query",
    "max_neighbors_per_query",
    "query_time_ns",
    # memory (memory_probe rows only)
    "algorithm_incremental_peak_bytes",
    "pipeline_peak_bytes",
    "heap_allocation_count",
    "heap_allocated_bytes",
    "rss_before_algorithm_bytes",
    "process_peak_rss_bytes",
    # solution
    "cds_size",
    "cds_fraction",
    "core_count",
    "connector_count",
    "roles_reported",
    "duplicate_ids",
    "cds_hash",
    "cds_diameter",
    "opt_size",
    "empirical_ratio",
    # validation
    "validated",
    "valid_solution",
    "domination_valid",
    "connectivity_valid",
    "undominated_count",
    "failure_reason",
    "status",
    "error",
]

DATASET_COLUMNS = [
    "schema_version",
    "study_id",
    "graph_id",
    "dataset_id",
    "cell_id",
    "replicate",
    "source_type",
    "geometry",
    "n",
    "radius",
    "radius_units",
    "density_target",
    "target_expected_degree",
    "graph_seed",
    "generation_attempt",
    "dataset_path",
    "dataset_sha256",
    "points_fingerprint",
    "source_path",
    "source_sha256",
    "coordinate_system",
    "projection",
    "units",
    "sampling",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
    "generator_parameters_json",
    "probe_spatial_backend",
    "backend_crosscheck",
    "t_dataset_ms",
    "t_spatial_index_ms",
    "t_graph_stats_ms",
    "t_connectivity_ms",
    "t_exact_ms",
    "index_backend",
    "index_cell_size",
    "index_cells",
    "index_bytes",
    "dataset_bytes",
    "edges",
    "explicit_csr_bytes_estimate",
    "explicit_bitmatrix_bytes_estimate",
    "mean_degree",
    "min_degree",
    "max_degree",
    "median_degree",
    "degree_std",
    "graph_density",
    "isolated_count",
    "component_count",
    "largest_component",
    "connected",
    "opt_size",
    "exact_status",
    "graph_status",
]

GENERATION_ATTEMPT_COLUMNS = [
    "schema_version",
    "study_id",
    "cell_id",
    "dataset_id",
    "replicate",
    "attempt",
    "graph_seed",
    "geometry",
    "n",
    "density_target",
    "radius",
    "accepted",
    "rejection_reason",
    "connected",
    "component_count",
    "largest_component",
    "isolated_count",
    "mean_degree",
    "dataset_sha256",
    "points_fingerprint",
]

# Metric taxonomy (documented in docs/experimental_methodology.md). Backend-
# specific diagnostics are never compared across backends.
METRIC_TAXONOMY = {
    "primary": ["valid_solution", "t_algorithm_ms", "cds_size", "cds_fraction"],
    # Memory (memory-probe rows; one common baseline H0 = live heap just before
    # the representation build, see experimental_methodology.md):
    #   index_build_peak_bytes           extra heap needed at any point while building the representation
    #   final_representation_bytes       representation footprint retained after the build
    #   algorithm_incremental_peak_bytes extra heap above the solve()-entry level during the algorithm
    #   pipeline_peak_bytes              max end-to-end heap increase above H0 (build + algorithm)
    "secondary": ["algorithm_incremental_peak_bytes", "final_representation_bytes", "index_build_peak_bytes",
                  "pipeline_peak_bytes", "t_spatial_index_ms", "neighbor_queries", "neighbors_returned",
                  "cds_diameter", "empirical_ratio"],
    "diagnostic": ["core_count", "connector_count", "domination_valid", "connectivity_valid", "undominated_count",
                   "max_neighbors_per_query", "query_time_ns"],
    # Each is defined for one backend only and is never compared across backends.
    "backend_specific_diagnostic": ["grid_candidates_examined", "grid_distance_computations",
                                    "grid_avg_candidates_per_query", "grid_cells_examined",
                                    "grid_max_candidates_per_query", "cgal_range_candidates",
                                    "cgal_exact_distance_evaluations", "cgal_max_range_candidates_per_query",
                                    "index_bytes"],
    # Count-only analytical estimates (datasets.csv): what an explicit graph WOULD
    # occupy, from |E| counted by streaming radius queries. No graph is built.
    "analytical_estimate": ["explicit_csr_bytes_estimate", "explicit_bitmatrix_bytes_estimate"],
}

FAILURE_COLUMNS = [
    "schema_version",
    "study_id",
    "stage",
    "graph_id",
    "dataset_id",
    "cell_id",
    "algorithm",
    "phase",
    "repetition",
    "status",
    "detail",
]
