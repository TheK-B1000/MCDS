"""Experiment framework for MCDS on implicit unit disk graphs.

The single authoritative study runner of the project (entry point
``python/run_study.py``). It measures the algorithms; it never changes their
semantics, the generators, the validator or the spatial-index contract.

METHODOLOGY_VERSION names the methodology state recorded in every result row:
"v1.0-final-experiment" = the locked final protocol (git tag of the same
name). Caution: results made with the rejected 2026-10-06 lock (commit a5cebd7)
carry the same label; they are told apart by the git commit every result
records. Results made while the protocol was reopened carry "v1.0-dev";
earlier pilot and calibration results carry "v1-dev".
"""

METHODOLOGY_VERSION = "v1.0-final-experiment"
