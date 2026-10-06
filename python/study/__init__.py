"""Experiment framework for MCDS on implicit unit disk graphs.

The single authoritative study runner of the project (entry point
``python/run_study.py``). It measures the algorithms; it never changes their
semantics, the generators, the validator or the spatial-index contract.

METHODOLOGY_VERSION names the methodology state recorded in every result row:
"v1.0-final-experiment" = the locked v1 protocol (git tag of the same name).
Earlier results (pilots, calibration) carry "v1-dev".
"""

METHODOLOGY_VERSION = "v1.0-final-experiment"
