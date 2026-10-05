# Paper-to-code audit: Marathe et al. — Heuristic CDOM

Audit date: 2026-10-05. Code: `main` @ `06bf246`. No algorithm code was changed.

## Citation

M. V. Marathe, H. Breu, H. B. Hunt III, S. S. Ravi, D. J. Rosenkrantz,
“Simple Heuristics for Unit Disk Graphs,” arXiv:math/9409226v1, 21 Sep 1994.
The preprint states that an extended abstract appeared in CCCG 1992 and that
the journal version is *Networks* 25 (1995), pp. 59–68. **This audit read the
arXiv preprint, not a separate *Networks* PDF.** Section and theorem numbers
below are the preprint’s.

| Item | Value |
| --- | --- |
| Local paper | `papers/primary/marathe_simple_heuristics_unit_disk_graphs.pdf` (gitignored) |
| SHA-256 | `6827FBEF1FB7B1644D484C2AC80805E8A4F92ECA2E50CBABFE494C7062C495DA` |
| Pages | 19 |
| Exact section used | §4.4.2, Figure 2 (Heuristic CDOM); supporting §4.4.1, Lemma 3.2, Theorem 4.8, Lemma 4.4, Theorem 4.9 |

## Model

A unit disk graph is an intersection graph of disks of radius 1: two vertices
are adjacent iff the disks intersect, including tangency, so center distance
is at most 2. Our project uses proximity adjacency `distance ≤ R` with
`R = 1`. That is the same graph family after scaling all coordinates by `1/2`.
It is not treated as an algorithm discrepancy.

The paper assumes the input graph is connected when a connected dominating
set is required (§4.4.2). Our `solve` throws if the implicit UDG is
disconnected.

## Paper algorithm (Figure 2)

1. Pick an arbitrary vertex `v`.
2. Build a BFS spanning tree `T` rooted at `v`. Let `S_i` be the vertices at level `i`, and `k` the depth.
3. `IS_0 = {v}`, `NS_0 = ∅`.
4. For `i = 1 .. k`:
   - `DS_i` = vertices of `S_i` dominated by `IS_{i-1}`.
   - `IS_i` = a maximal independent set of the induced subgraph `G(S_i − DS_i)`.
   - `NS_i` = the parents in `T` of vertices in `IS_i` (so `NS_i ⊆ S_{i-1}`).
5. Output `(∪ IS_i) ∪ (∪ NS_i)`.

§4.4.1 says a maximal independent set may be built by repeatedly selecting an
**arbitrary** remaining vertex and deleting it and its neighbors. No further
tie-break is specified for the root, the BFS parent, or the MIS pivot.

Termination: the loop ends at the deepest BFS level. Lemma 4.4 proves the
output is a CDS. Theorem 4.9: the output has size at most **10 times** an
optimal CDS (and at most 10 times a minimum total dominating set). The proof
uses that `∪ IS_i` is a maximal independent set, hence `|IS| ≤ 5 |OPT_DS|` by
Theorem 4.8 (from `K_{1,6}`-freeness, Lemma 3.2), and `|NS| ≤ |IS|`.

## Source code

| Piece | Location |
| --- | --- |
| Entry | `MaratheAlgorithm::solve` in `cpp/src/algorithms/Marathe.cpp` |
| Declaration | `cpp/include/algorithms/Marathe.hpp` |
| BFS | `buildBfsTree` |
| Level MIS | `maximalIndependentSet` |
| Tests | `cpp/tests/test_marathe.cpp` |

## Paper-to-code mapping

| Paper step | Code |
| --- | --- |
| Arbitrary root `v` | Input **index 0** (`root = 0`), not a random vertex |
| BFS tree and levels `S_i` | `buildBfsTree`; neighbours scanned in ascending id; first discoverer is the parent |
| `IS_0 = {root}` | `selected[root] = isCore[root] = 1` |
| `DS_i` | Level-`i` vertices adjacent to `currentIs` (`IS_{i-1}`) are excluded from `remaining` |
| MIS of `G(S_i − DS_i)` | `maximalIndependentSet`: remaining candidates in increasing id; pivot deletes itself and its still-remaining neighbours |
| `NS_i` | `tree.parent[u]` of each vertex in `IS_i` is marked selected |
| Output | Selected ids; role `core` if in some `IS_i`, else `connector` |

## Intentional adaptations

- Root, BFS parent, and MIS pivot are deterministic. Each is a legal reading of the paper’s “arbitrary”.
- The graph is given implicitly by point coordinates and a radius query, not as an explicit adjacency list. The combinatorial steps use only neighbourhood queries.

## Implementation-specific decisions

- Root is the first point in input order. For generator and importer CSVs, ids are `0..n-1` in order, so this is also the minimum id. For an arbitrary CSV it need not be.
- Neighbour scan order is ascending id.
- An `IS` vertex that is also some later vertex’s parent stays `core`.

## Unresolved ambiguities

- The preprint and the *Networks* article were not compared page-for-page. Numbers cited here are the preprint’s.
- Resolved: the `Marathe.hpp` header now states that `solve` throws on a disconnected UDG (comment-only change).

## Theoretical guarantee

**Paper:** Theorem 4.9, `|D| ≤ 10 · |OPT_CDS|`.

**Applies to our implementation: yes.** Any root, any BFS tree, and any maximal independent set inside each `G(S_i − DS_i)` are enough for Lemma 4.4 and Theorem 4.9. Our fixed choices are instances of those arbitrary choices. The `K_{1,6}` argument is geometric and transfers under the scale normalization above.

`IMPLEMENTATION VERIFIED: YES`
