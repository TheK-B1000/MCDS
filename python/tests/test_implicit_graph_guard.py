"""Guard for the hard project invariant: the input is a set of n points and the
unit disk graph is NEVER constructed or stored explicitly (no adjacency lists,
matrices, edge lists or CSR) in any production or experimental path. Adjacency
is only ever obtained on demand through radius queries.

Two layers:

1. Behavioural: run the real memory-probe solver on a *dense* graph (millions of
   edges) through every production phase — graph statistics, backend
   cross-check, all four algorithms, independent validation, CDS diameter — and
   require the process's lifetime heap peak to stay a small fraction of what
   storing the UDG as CSR would need. The real-data largest-component
   preprocessing is checked the same way with tracemalloc.
2. Static tripwire: no C++ or Python source in the repository (production,
   tooling, visualisation/GUI, tests and test oracles) may contain
   adjacency-building or edge-drawing constructs, except for an explicit,
   justified allowlist.
"""

from __future__ import annotations

import json
import math
import random
import re
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path

_PYTHON_DIR = Path(__file__).resolve().parent.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from real_dataset import extract_largest_connected_component  # noqa: E402
from study.bench import find_binary  # noqa: E402

REPO_ROOT = _PYTHON_DIR.parent

# A run that stored the UDG would need at least the CSR footprint; allow the
# implicit pipeline only a small fraction of it.
MAX_FRACTION_OF_CSR = 0.10


def _dense_points(n: int, side: float, seed: int) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    return [(rng.uniform(0, side), rng.uniform(0, side)) for _ in range(n)]


def _write_csv(path: Path, pts: list[tuple[float, float]]) -> None:
    lines = ["id,x,y"] + [f"{i},{x:.6f},{y:.6f}" for i, (x, y) in enumerate(pts)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mem_binary():
    try:
        return find_binary(REPO_ROOT, "mcds_bench_mem")
    except FileNotFoundError:
        return None


@unittest.skipIf(_mem_binary() is None, "mcds_bench_mem not built")
class SolverNeverStoresTheGraph(unittest.TestCase):
    def test_dense_graph_all_phases_stay_far_below_explicit_size(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = Path(d) / "dense.csv"
            _write_csv(csv_path, _dense_points(4000, 2.5, seed=11))  # mean degree ~ 1800
            for backend in ("cgal", "grid"):
                out = Path(d) / f"{backend}.json"
                proc = subprocess.run(
                    [str(_mem_binary()), "--input", str(csv_path), "--radius", "1.0", "--output", str(out),
                     "--spatial-backend", backend, "--algorithms", "marathe,wan,funke,li"],
                    capture_output=True, text=True, timeout=900)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                data = json.loads(out.read_text(encoding="utf-8"))
                g = data["graph"]
                self.assertGreater(g["edges"], 2_000_000)  # really dense
                csr = g["explicit_csr_bytes_estimate"]
                lifetime = data["heap_lifetime_peak_bytes"]
                print(f"\n    {backend}: |E|={g['edges']:,} explicit CSR estimate={csr:,} B "
                      f"lifetime heap peak={lifetime:,} B "
                      f"final representation={data['index']['final_representation_bytes']:,} B")
                self.assertEqual(data["status"], "ok")
                self.assertTrue(all(r["valid_solution"] for r in data["runs"]))
                self.assertTrue(all(r.get("cds_diameter") is not None for r in data["runs"]))
                self.assertLess(
                    lifetime, MAX_FRACTION_OF_CSR * csr,
                    f"{backend}: lifetime heap peak {lifetime} B is not << explicit CSR {csr} B "
                    f"(|E| = {g['edges']}); some path may be materialising adjacency")
                self.assertLess(data["index"]["final_representation_bytes"], MAX_FRACTION_OF_CSR * csr)


class PreprocessingNeverStoresTheGraph(unittest.TestCase):
    def test_largest_component_is_implicit(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "dense.csv"
            pts = _dense_points(2000, 1.5, seed=5)  # ~ 2.4M edges
            pts += [(100.0 + i, 100.0) for i in range(5)]  # a separate small component
            _write_csv(src, pts)
            tracemalloc.start()
            result = extract_largest_connected_component(src, Path(d) / "lcc.csv", radius=1.0)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertEqual(result.point_count, 2000)
            # A Python adjacency list for ~2.4M edges needs > 40 MB; the
            # implicit union-find needs O(n).
            self.assertLess(peak, 5 * 1024 * 1024, f"tracemalloc peak {peak} B")


# Static tripwire -----------------------------------------------------------
# Scope: every C++ and Python source in the repository: production code,
# experiment tooling, visualisation/GUI, and the test suites (validation and
# test oracles are covered by the invariant too). Comment lines are skipped.
_CPP_FORBIDDEN = [
    re.compile(r"std::vector<\s*std::vector<"),          # adjacency lists
    re.compile(r"\badj(acency)?(List|Matrix)?\s*[\[(=]"),  # adj[...] / adjacency = ...
    re.compile(r"\bedge_?[Ll]ist\b"),
    re.compile(r"class\s+\w*(Explicit|Adjacency)\w*Index"),
    re.compile(r"std::(unordered_)?map<[^;]*std::vector"),  # vertex -> neighbour vector
    re.compile(r"\bedges\.(push_back|emplace_back)\("),   # edge accumulation
    re.compile(r"std::vector<\s*std::pair<[^;]*>>\s*\w*[Ee]dges?\b"),
    re.compile(r"\b(row_?[Pp]tr|col_?[Ii]dx|rowOffsets|colIndices)\b"),  # CSR arrays
    re.compile(r"std::vector<\s*bool\s*>\s*\w*([Mm]atrix|adj)\w*"),  # bit matrix
    re.compile(r"boost::adjacency_|adjacency_list<"),
]
_PY_FORBIDDEN = [
    re.compile(r"\badj(acency)?\s*[\[=:]"),
    re.compile(r"\bnetworkx\b|\badd_edge\("),
    re.compile(r"\bedge_?list\b"),
    re.compile(r"^\s*edges\s*(:[^=]+)?=\s*(\[|\{|set\(|dict\(|defaultdict|list\()"),  # edge containers
    re.compile(r"\bedges\.(append|add|extend)\("),
    re.compile(r"^\s*neighbou?rs\s*(:[^=]+)?=\s*(\{|defaultdict|dict\()"),  # neighbour maps
    re.compile(r"\bscipy\.sparse\b|\bcsr_matrix\b|\bquery_pairs\(|\bquery_ball_tree\(|"
               r"\bsparse_distance_matrix\("),
    re.compile(r"\bimport\s+igraph\b|\bgraph_tool\b"),
    re.compile(r"\bcds_edges\b|show[-_]cds[-_]edges"),  # removed visualisation edge drawing
    re.compile(r"\bLineCollection\b"),                   # bulk segment drawing
]
# path -> [(line regex, justification)]. Anything else matching is a failure.
_ALLOW = {
    "cpp/src/algorithms/Marathe.cpp": [
        (re.compile(r"levels;\s*//\s*level -> indices"),
         "BFS level -> vertex-index lists (each vertex once, O(n)); no edges"),
    ],
    "python/tests/test_visualization.py": [
        (re.compile(r'assertFalse\(hasattr\(visualization, "cds_edges"\)\)'),
         "negative assertion that the removed edge helper no longer exists"),
        (re.compile(r'assertFalse\(\{"--show-cds-edges"'),
         "negative assertion that the removed CLI flags no longer exist"),
    ],
}
_SELF = Path(__file__).resolve()


def _sources():
    for root in (REPO_ROOT / "cpp" / "src", REPO_ROOT / "cpp" / "include", REPO_ROOT / "cpp" / "tests"):
        for p in sorted(root.rglob("*")):
            if p.suffix in (".cpp", ".hpp", ".h", ".in"):
                yield p, _CPP_FORBIDDEN
    for sub in ("", "study", "tests"):
        for p in sorted((REPO_ROOT / "python" / sub).glob("*.py")):
            if p.resolve() != _SELF:  # this file spells out the patterns
                yield p, _PY_FORBIDDEN


def _scan(path: Path, patterns, allow) -> list[str]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    hits = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("//", "#", "///", "*")):
            continue  # comments may discuss adjacency
        if any(rx.search(line) for rx, _why in allow):
            continue
        if any(pat.search(line) for pat in patterns):
            hits.append(f"{rel}:{lineno}: {stripped}")
    return hits


class StaticTripwire(unittest.TestCase):
    def test_no_adjacency_constructs_in_any_source(self):
        hits = []
        scanned = set()
        for path, patterns in _sources():
            rel = path.relative_to(REPO_ROOT).as_posix()
            scanned.add(rel)
            hits += _scan(path, patterns, _ALLOW.get(rel, []))
        self.assertEqual(hits, [], "adjacency-building construct(s) found:\n" + "\n".join(hits))
        # The scope really includes visualisation, GUI, tooling and tests.
        for rel in ("python/visualization.py", "python/gui.py", "python/run_study.py",
                    "python/study/runner.py", "cpp/src/bench_main.cpp", "cpp/tests/test_wan_level_mis.cpp",
                    "python/tests/test_study.py"):
            self.assertIn(rel, scanned)

    def test_tripwire_flags_known_violations(self):
        # Each pattern family must fire on a representative construct, including
        # the pre-fix ones (explicit index, CDS edge drawing, test-oracle adjacency).
        cpp = ["std::vector<std::vector<std::size_t>> adj(m);", "class ExplicitAdjacencyIndex final",
               "std::unordered_map<int, std::vector<int>> nbrs;", "edges.push_back({u, v});",
               "std::vector<std::pair<int, int>> edges;", "std::vector<std::size_t> rowPtr(n + 1);",
               "std::vector<bool> adjMatrix(n * n);"]
        py = ["edges = []", "edges.append((ax, ay, bx, by))", "neighbors = defaultdict(list)",
              "G = networkx.Graph()", "pairs = tree.query_pairs(r)", "def cds_edges(data):",
              'parser.add_argument("--show-cds-edges")', "ax.add_collection(LineCollection(segs))"]
        for line in cpp:
            self.assertTrue(any(p.search(line) for p in _CPP_FORBIDDEN), line)
        for line in py:
            self.assertTrue(any(p.search(line) for p in _PY_FORBIDDEN), line)
        # ...and stay quiet on the implicit idioms the code legitimately uses.
        for line in ['f"n={n} edges={edges}"', "edges += 1", 'g["edges"]', "for q in index.radiusQuery(p, r):"]:
            self.assertFalse(any(p.search(line) for p in _PY_FORBIDDEN + _CPP_FORBIDDEN), line)

    def test_allowlist_entries_still_exist(self):
        # A stale allowlist would silently stop guarding anything.
        for rel, entries in _ALLOW.items():
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for pattern, _why in entries:
                self.assertTrue(pattern.search(text), f"stale allowlist entry for {rel}: {pattern.pattern}")


if __name__ == "__main__":
    unittest.main()
