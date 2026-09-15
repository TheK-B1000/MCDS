# Marathe et al. Connected Domination Heuristic (CDOM)

Source (authoritative):

> M. V. Marathe, H. Breu, H. B. Hunt III, S. S. Ravi, D. J. Rosenkrantz,
> “Simple Heuristics for Unit Disk Graphs,”
> *Networks* 25(2):59–68, 1995.
>
> Public preprint: [arXiv:math/9409226](https://arxiv.org/abs/math/9409226)

This note documents **Heuristic CDOM** from **Section 4.4.2** (Figure 2 in the
preprint). Implementation must follow this document. If a step below cannot be
resolved from the paper, stop and report the ambiguity rather than inventing
behaviour.

---

## Paper terminology

| Term | Meaning in the paper |
| --- | --- |
| Unit disk graph (intersection model) | Vertices ↔ disks of radius 1; edge iff disks intersect (tangency counts). Equivalent to centres at distance ≤ 2. |
| Proximity model | Vertices ↔ points; edge iff distance ≤ a fixed bound. |
| Domination | Every vertex outside `D` has a neighbour in `D`. |
| Connected dominating set (CDS) | Dominating set whose induced subgraph is connected. |
| Maximal independent set (MIS) | Independent set that is not a proper subset of any larger independent set. Every MIS is dominating. |
| BFS spanning tree `T` | Breadth-first spanning tree of the (connected) input graph. |
| Level `ℓ(v)` | Number of edges on the unique `T`-path from the root to `v`. |
| `S_i` | Vertices at level `i` in `T`. |
| `IS_i` | Independent-set vertices chosen at level `i`. |
| `DS_i` | Vertices of `S_i` already dominated by `IS_{i-1}`. |
| `NS_i` | Connector vertices: parents in `T` of the vertices in `IS_i`. |

---

## Inputs / outputs / assumptions

**Input**

- A **connected** unit disk graph `G = (V, E)` with no isolated vertices
  (paper §4.4.2). If `G` is disconnected, a CDS does not exist.
- No geometric representation is required by the heuristic itself (paper
  abstract / §1). Geometry is used only to prove the approximation ratio.

**Output**

- A connected dominating set
  `D = (⋃_{i=0}^{k} IS_i) ∪ (⋃_{i=0}^{k} NS_i)`.

**Claimed approximation guarantee (Theorem 4.9)**

- `|D| ≤ 10 · |OPT_CDS|` for unit disk graphs.
- The same construction is also a total dominating set within factor 10 of
  a minimum total dominating set.

---

## Exact algorithm steps (Figure 2 / Heuristic CDOM)

```text
1. Arbitrarily pick a vertex v ∈ V.
2. Construct the breadth-first spanning tree T of G rooted at v.
3. Let k be the depth of T.
4. Let S_i denote the nodes at level i in T, for all 0 ≤ i ≤ k.
5. Set IS_0 = {v};  NS_0 = ∅.
6. for i = 1 to k do
7.     DS_i = { u ∈ S_i | u is adjacent to some vertex in IS_{i-1} }.
8.     Pick a maximal independent set IS_i in G(S_i − DS_i).
9.     NS_i = { parent_T(u) | u ∈ IS_i }.   // note: NS_i ⊆ S_{i−1}
10. end
11. output (⋃ IS_i) ∪ (⋃ NS_i) as the connected dominating set.
```

### BFS behaviour

- Levels are graph distances from the root in `G` (equivalently, depths in `T`).
- The paper does not specify parent selection when a vertex has several
  neighbours on the previous level. See **Tie-breaking** below.

### Level processing order

- Process levels in increasing order `i = 1, 2, …, k`.
- `IS_0` is fixed to the root; no MIS is computed at level 0.

### MIS construction at level `i` (Step 8)

- The induced subgraph is `G(S_i − DS_i)`: only edges among remaining level-`i`
  vertices matter.
- Section 4.4.1 describes the generic linear-time MIS method used elsewhere in
  the paper: repeatedly select a vertex `u`, add it to the independent set, and
  delete `u` and `N(u)` from the remaining graph. We use that method for Step 8.
- The paper says “pick a maximal independent set” without naming a specific
  selection order among candidates. See **Tie-breaking**.

### Connector selection (Step 9)

- For each `u ∈ IS_i`, add its **unique parent in the BFS tree `T`**.
- Connectors therefore always sit on level `i − 1`.
- `NS_0` remains empty.

### Termination

- After processing level `k` (the deepest BFS level), output the union of all
  `IS_i` and `NS_i`.

---

## Radius-convention mapping

| Convention | Adjacent when |
| --- | --- |
| Paper intersection model (radius-1 disks) | centre distance ≤ **2** |
| Paper proximity model | distance ≤ a fixed bound |
| **This project** | Euclidean distance ≤ **1.0** |

CDOM is a **combinatorial** algorithm on an abstract graph. It does not use
disk radii inside its steps. We therefore run CDOM on the project’s implicit
UDG (`distance ≤ 1.0`) without rescaling coordinates.

The factor-10 guarantee relies on unit disk graphs being `K_{1,6}`-free
(Lemma 3.2), which holds for both the paper’s intersection model and our
proximity model with bound 1 (they are the same family up to global scale).
No algorithm change is required; only the neighbour oracle’s radius changes
with the project convention.

---

## Tie-breaking decisions (project-specific, required for reproducibility)

The paper leaves three choices arbitrary. For reproducible experiments we fix:

| Choice | Paper | Our rule |
| --- | --- | --- |
| Root `v` | “Arbitrarily pick” | Smallest input **index** (which equals the smallest id for our generators). |
| BFS parent | Unspecified | When dequeuing `u`, scan neighbours in ascending id order; the parent of a newly discovered `w` is the current `u` (standard BFS). Because the queue processes vertices in discovery order and neighbours are scanned by ascending id, the parent is uniquely determined. |
| MIS vertex selection inside `G(S_i − DS_i)` | “Arbitrary” / “pick” | Always select the remaining candidate with the **smallest id**. Then remove it and all of its neighbours that still lie in the remaining set. |

Never choose a random root or a random MIS pivot silently.

---

## Mapping graph operations → `SpatialIndex`

| Paper operation | Implementation |
| --- | --- |
| Neighbours of `u` in `G` | `index.radiusQuery(u.id, radius)` |
| BFS over `G` | Queue + visited bitmap + reused neighbour buffer; edges never stored. |
| “`u` dominated by some vertex in `IS_{i-1}`” | `u` is adjacent to at least one member of `IS_{i-1}` (one radius query on `u`, or equivalently mark neighbours when processing each IS vertex). |
| Induced edges inside `S_i − DS_i` | For candidate `u`, query neighbours and retain those still in the remaining level-`i` set. |
| Parent in `T` | Stored during BFS as an index array `parent[i]`. |

No adjacency matrix or permanent adjacency list is built.

---

## Pseudocode (project form)

```text
require G connected (caller / CLI responsibility)

root ← point with smallest input index
(parent[], level[], S[0..k], k) ← implicitBFS(root, index, radius)

IS[0] ← {root}
NS[0] ← ∅
selected ← {root}

for i ← 1 .. k:
    remaining ← { u ∈ S[i] | u has no neighbour in IS[i-1] }   # = S_i \ DS_i
    IS[i] ← ∅
    while remaining ≠ ∅:
        u ← min-id(remaining)
        IS[i] ← IS[i] ∪ {u}
        remaining ← remaining \ ({u} ∪ (N(u) ∩ remaining))
    NS[i] ← { parent[u] | u ∈ IS[i] }
    selected ← selected ∪ IS[i] ∪ NS[i]

return selected
```

---

## Correctness sketch (from the paper)

Lemma 4.4 proves by induction on tree depth that:

1. `⋃ IS_i` dominates all vertices processed so far, and
2. `G[(⋃ IS_i) ∪ (⋃ NS_i)]` remains connected,

because each new independent-set vertex is attached through its BFS parent
connector, and those parents are already dominated by earlier IS vertices.

Theorem 4.9: `IS = ⋃ IS_i` is a maximal independent set, hence
`|IS| ≤ 5|OPT_DS| ≤ 5|OPT_CDS|` (Theorem 4.8), and
`|NS| ≤ |IS|`, so `|IS ∪ NS| ≤ 10|OPT_CDS|`.

---

## Open ambiguities

None that block implementation. The three “arbitrary” choices above are fixed
explicitly for reproducibility and do not alter the paper’s correctness proof
or the factor-10 guarantee.
