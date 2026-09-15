# Wan–Alzoubi–Frieder CDS Algorithm

## Bibliographic source

Peng-Jun Wan, Khaled M. Alzoubi, Ophir Frieder.  
“Distributed Construction of Connected Dominating Set in Wireless Ad Hoc Networks.”  
*IEEE INFOCOM 2002*, pp. 1597–1604.  
DOI: [10.1109/INFCOM.2002.1019411](https://doi.org/10.1109/INFCOM.2002.1019411)

Public PDF (Georgetown CS IR; **not** committed to this repository):

- https://ir.cs.georgetown.edu/publications/downloads/infocom02.pdf
- https://ir.cs.georgetown.edu/downloads/infocom02.pdf

This document is based on that paper. Secondary summaries must not override it.

---

## 1. Problem definition (paper → project)

**Paper (§I).** Nodes lie in the plane with equal transmission range one unit.
The network is a **unit-disk graph**: edge `{u,v}` iff Euclidean distance
`≤ 1`. A **dominating set** `V'` meets every vertex outside `V'` by an edge.
A **connected dominating set (CDS)** is a dominating set that induces a
connected subgraph. Finding a minimum CDS is NP-hard on unit disk graphs.

**Project mapping.**

| Paper | Project |
| --- | --- |
| Vertices | Input points in `PointSet` |
| Edge `{u,v}` | `distance(u,v) ≤ radius` |
| Default radius | `1.0` |
| Neighbor discovery | `SpatialIndex::radiusQuery` |

---

## 2. What we implement vs what the paper only reviews

| Section | Content | Role here |
| --- | --- | --- |
| §III | Das / Bharghavan / Sivakumar greedy spine | **Not** implemented |
| §IV | Wu–Li prune-from-CDS | **Not** implemented |
| §V | Stojmenovic cluster-heads + all border-nodes | **Not** implemented |
| **§VI** | **Wan–Alzoubi–Frieder three-phase algorithm** | **Implemented** |

The algorithm we implement is **only** the construction in **Section VI
(“A Better Distributed Algorithm”)**, with correctness in Theorem 8 and
approximation in Theorem 10 / Lemma 9.

---

## 3. Algorithm stages (Section VI.A)

The paper’s algorithm has **three phases**.

### Phase 1 — Leader election + spanning tree

| Item | Paper |
| --- | --- |
| Input | Connected UDG |
| Action | Elect a leader `v`; build a spanning tree `T` rooted at `v` |
| Reference | Distributed leader election of Cidon–Mokryn [5] |
| Leadership criteria | “Any criteria… such as ID or the combination of degree and ID” |
| Output | Each node knows parent and children in `T` |
| Complexity (paper) | `O(n)` time, `O(n log n)` messages |

**Centralized adaptation.** We do **not** simulate [5]’s message protocol.
We elect the leader as the vertex of **smallest point ID**, then build a
**BFS spanning tree** rooted at that leader (deterministic parent selection:
when discovering a vertex, scan neighbors in ascending ID order; first
discoverer is the parent). Any spanning tree yields a valid rank system;
BFS is a simple deterministic choice that matches our existing tree tooling.

### Phase 2 — Level calculation

| Item | Paper |
| --- | --- |
| Input | Rooted tree `T` |
| Action | Root announces level `0`; each child sets `level = parent.level + 1` |
| Extra | Each node records levels of its **UDG** neighbors |
| Rank | Pair `(level, ID)`, lexicographic order; root has lowest rank |
| Output | Every node knows its rank and neighbors’ ranks |
| Messages | `O(n)` |

**Centralized adaptation.** Levels are depths in the BFS tree. Neighbor
ranks are obtained on demand via `radiusQuery` + the level array (no global
two-hop graph).

### Phase 3 — Color marking

All nodes start **white (unmarked)** and end **black** (dominator / CDS member)
or **gray** (dominatee).

Messages (distributed):

- `DOMINATOR` — sent after marking **black** (carries sender ID)
- `DOMINATEE` — sent after marking **gray** (carries sender ID)

**Initiation.** Root marks itself **black** and broadcasts `DOMINATOR`.

**Rules for other nodes** (paper §VI.A, Figure 5, and the worked example
in Figure 6):

1. **White → gray (dominated):**  
   On first receipt of `DOMINATOR`, mark **gray** and broadcast `DOMINATEE`.

2. **White → black (type-1 / MIS):**  
   When a white node has received `DOMINATEE` from **every neighbor of lower
   rank**, mark **black**, broadcast `DOMINATOR`, and record its tree parent
   as “its own dominator” (bookkeeping for the connection stage).

3. **Gray → black (type-2 / connector):**  
   When a gray node receives `DOMINATOR` for the first time from a **child
   in `T` that has never sent `DOMINATEE`**, remark **black** and broadcast
   `DOMINATOR`.  
   (Example note: if that child previously sent `DOMINATEE`, the parent
   does **not** flip gray→black.)

4. **Black → gray (pruning) — OCR / wording ambiguous:**  
   The PDF extract contains a sentence of the form: if a black node has
   higher rank than all neighbors and all neighbors are black, remark gray…
   The wording conflicts with normal message types (it says broadcast
   `DOMINATOR` while becoming gray) and is not used in the Theorem 8
   connectivity argument. **See Ambiguities.** We **omit** this pruning
   from the implementation; the CDS remains correct and the factor-8
   analysis still upper-bounds `|black|` (pruning can only shrink).

**Termination.** Every node is black or gray. Optional `COMPLETE` reporting
up the tree is irrelevant centrally.

---

## 4. MIS construction (type-1 blacks)

Type-1 blacks are exactly a **greedy maximal independent set under rank
order**.

Equivalent sequential rule (centralized):

```text
MIS ← ∅
for u in vertices sorted by increasing rank (level, id):
    if no neighbor of u is already in MIS:
        MIS ← MIS ∪ {u}
```

Why this matches the paper:

- A lower-rank black neighbor would have sent `DOMINATOR` earlier → `u`
  would already be gray (rule 1), so `u` cannot become type-1 black.
- If every lower-rank neighbor is gray (sent `DOMINATEE`), rule 2 fires →
  `u` becomes type-1 black.
- Root (lowest rank) is always type-1 black.

**Neighborhood needed.** Open one-hop UDG neighborhood.

**State.** Color; whether the node ever sent `DOMINATEE` (for connector
gate); parent in `T`; level; rank.

---

## 5. Connection stage (type-2 blacks)

Connectors are **not** Marathe’s `NS_i` construction.

Paper rule: a gray parent becomes black when a **child** joins the MIS
(type-1) without ever having been a dominatee.

Centralized equivalent:

```text
CDS ← MIS
for each v in MIS \ {root}:
    p ← parent_T(v)
    CDS ← CDS ∪ {p}
```

Notes:

- Only the **immediate tree parent** is forced in as a connector
  (Theorem 8’s path `v — parent — earlier black` argument).
- If the parent is already in `MIS`, the union is unchanged.
- Multiple MIS children may share one parent connector.

---

## 6. Approximation result

**Theorem 10 (§VI.C).** Approximation factor **at most 8**, with
`|CDS| ≤ 8·opt + 1` in the analysis (`2(4opt+1)−1`).

Supporting **Lemma 9:** any independent set has size `≤ 4·opt + 1`.

Type-1 blacks form an independent set; type-2 blacks are at most one per
type-1 black except the root, yielding the factor 8.

---

## 7. Complexity claims (paper vs our code)

| Claim | Paper (distributed) | Our C++ adaptation |
| --- | --- | --- |
| Approximation | ≤ 8 | Same **selection logic** → same quality guarantee applies to the returned set |
| Time | `O(n)` | Measured wall-clock `algorithm_ms` (centralized) |
| Messages | `O(n log n)` (optimal vs Ω(n log n) lower bound §II) | **Not simulated** — we must **not** claim message complexity |

We may compare CDS quality and centralized runtime / SpatialIndex query
counts. We must **not** claim our executable has the paper’s distributed
message complexity unless we explicitly simulate that model.

---

## 8. Distributed → centralized mapping

| Paper operation | Centralized equivalent |
| --- | --- |
| Leader election [5] | Smallest point ID |
| Spanning tree construction | Deterministic BFS tree from leader |
| Level announcement along `T` | Depth array from BFS |
| Learn neighbor levels | `radiusQuery` + level lookup |
| Rank `(level, ID)` | Pair compare |
| Broadcast `DOMINATOR` / `DOMINATEE` | Direct state updates (no packet queue) |
| “Received DOMINATEE from all lower-rank neighbors” | Greedy MIS scan in rank order |
| Gray←DOMINATOR from child that never sent DOMINATEE | Add `parent_T(v)` for each MIS vertex `v ≠ root` |
| COMPLETE reporting | Unnecessary |

---

## 9. SpatialIndex mapping

| Need | Implementation |
| --- | --- |
| One-hop neighbors | `index.radiusQuery(id, radius)` |
| Two-hop | **Not** required globally. Rank MIS only needs one-hop. |
| Selected / MIS neighbor checks | Bitmap over point indices + one-hop query |
| Connector lookup | Parent array from BFS (tree edge, not a new geometric query) |

Temporary neighbor buffers only. No adjacency matrix / permanent edge list.

---

## 10. Deterministic tie-breaking (project)

| Choice | Paper | Our rule |
| --- | --- | --- |
| Leader | ID or degree+ID | **Smallest point ID** |
| Spanning tree | From [5] | **BFS**; on discovery, scan neighbors by **ascending ID**; first discoverer is parent |
| Rank ties at same level | Lower ID wins (lexicographic) | Same: `(level, id)` |
| MIS among equal-rank | Impossible (IDs unique) | — |
| Connector among children | Each MIS child invites its own parent | Same |

Never choose a random leader or random MIS pivot.

---

## 11. Expected output / interface

```cpp
class WanAlgorithm : public MCDSAlgorithm {
  MCDSResult solve(const PointSet&, const SpatialIndex&, double radius) override;
  std::string name() const override;  // "wan"
};
```

Returns selected point IDs only. Timing, validation, JSON, and plotting stay
in the runner / Python layers.

**Precondition.** Input UDG must be connected (same as Marathe / CLI policy).

---

## Executable pseudocode (centralized)

```text
require connected UDG

leader ← argmin_id(points)
(parent[], level[], depth) ← bfsTree(leader)   # SpatialIndex neighbors

rank(u) = (level[u], id[u])

# Phase 3a — type-1 blacks = greedy MIS by rank
color[·] ← WHITE
MIS ← ∅
for u in points sorted by rank ascending:
    if ∃ neighbor v of u with v ∈ MIS:
        color[u] ← GRAY          # would have received DOMINATOR
    else:
        color[u] ← BLACK_TYPE1
        MIS ← MIS ∪ {u}

# Phase 3b — type-2 connectors
CDS ← MIS
for v in MIS:
    if v ≠ leader and parent[v] ≥ 0:
        CDS ← CDS ∪ {parent[v]}
        color[parent[v]] ← BLACK  # type2 if it was gray

return CDS as selected IDs
```

---

## Ambiguities

1. **Black→gray pruning sentence in §VI.A** — wording from the PDF extract
   is inconsistent (broadcasting `DOMINATOR` while becoming gray) and unused
   by Theorem 8. **Decision: omit pruning.** Documented above.
2. **Exact tree of Cidon–Mokryn [5]** — not reproduced. **Decision: BFS
   tree from min-ID leader.** Levels still induce a total rank order; the
   MIS+parent CDS argument does not depend on which spanning tree is used.
3. **Asynchronous message interleaving** — many valid executions exist
   distributedly. **Decision: sequential rank-order MIS + parent union**,
   which is the standard sequentialization of this protocol and matches
   Figure 6’s outcomes for type-1/type-2 membership under our tie-breaks.

No remaining ambiguity blocks a faithful implementation of the **selection
logic** (MIS by rank + tree-parent connectors).
