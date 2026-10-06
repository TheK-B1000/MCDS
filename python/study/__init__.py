"""Experiment framework for MCDS on implicit unit disk graphs.

The single authoritative study runner of the project (entry point
``python/run_study.py``). It measures the algorithms; it never changes their
semantics, the generators, the validator or the spatial-index contract.

METHODOLOGY_VERSION names the methodology state recorded in every result row:
"v1.0-dev" = protocol reopened before any final data (pre-final audit:
Funke / Li S-MIS implementation efficiency, outputs unchanged). Results made
with the rejected 2026-10-06 lock (commit a5cebd7) carry
"v1.0-final-experiment"; earlier pilot and calibration results carry "v1-dev".
Every result also records its git commit.
"""

METHODOLOGY_VERSION = "v1.0-dev"
