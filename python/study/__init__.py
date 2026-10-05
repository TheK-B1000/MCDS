"""Experiment framework for MCDS on implicit unit disk graphs.

The single authoritative study runner of the project (entry point
``python/run_study.py``). It measures the algorithms; it never changes their
semantics, the generators, the validator or the spatial-index contract.

METHODOLOGY_VERSION names the methodology state recorded in every result row:
"v1-dev" = v1 methodology still under development. Set it to the freeze label
(e.g. "v1.0-final-experiment") when the final protocol is locked.
"""

METHODOLOGY_VERSION = "v1.0-final-experiment"
