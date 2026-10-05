"""Versioned long-form result schemas for MCDS studies.

One row of ``raw_runs.csv`` = one algorithm execution on one graph for one
repetition (warmups, timed repetitions, memory probes and counter passes are
all kept; ``phase`` says which is which). Nothing is pre-aggregated.

Bump ``SCHEMA_VERSION`` whenever a column is added, removed or redefined.
"""

from __future__ import annotations

SCHEMA_VERSION = "mcds-results-1"

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
    "candidates_examined",
    "distance_computations",
    "neighbors_returned",
    "avg_candidates_per_query",
    "avg_neighbors_per_query",
    "cells_examined",
    "max_candidates_per_query",
    "max_neighbors_per_query",
    "query_time_ns",
    # memory (memory_probe rows only)
    "heap_peak_additional_bytes",
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
    "t_dataset_ms",
    "t_spatial_index_ms",
    "t_graph_stats_ms",
    "t_exact_ms",
    "index_backend",
    "index_cell_size",
    "index_cells",
    "index_bytes",
    "dataset_bytes",
    "edges",
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
