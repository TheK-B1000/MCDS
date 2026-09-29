# Li–Thai–Wang–Yi–Wan–Du S-MIS Algorithm

## Bibliographic source

Yingshu Li, My T. Thai, Feng Wang, Chih-Wei Yi, Peng-Jun Wan, Ding-Zhu Du.  
“On Greedy Construction of Connected Dominating Sets in Wireless Networks.”  
*Wireless Communications and Mobile Computing*, 5(8):927–932, 2005.  
DOI: [10.1002/wcm.356](https://doi.org/10.1002/wcm.356)

Public PDF (IIT Wan archive; **not** committed):

- http://csam.iit.edu/~wan/Journal/wcmc05.pdf

This document follows that paper. Secondary summaries must not override it.

**Primary algorithm implemented:** **S-MIS** (Section 3, Algorithm A).  
**Not implemented:** rS-MIS (Section 4 variation), distributed message protocol (Section 5) beyond combinatorial equivalence.

---

## 1. Input assumptions

| Paper | Project |
| --- | --- |
| Connected undirected UDG | Connected `PointSet` under `radius` |
| Edge `{u,v}` | `distance(u,v) ≤ radius` (default `1.0`) |
| Output | CDS = black (MIS) ∪ blue (Steiner / connectors) |

Refuse disconnected inputs (same policy as Marathe / Wan / Funke).

---

## 2. S-MIS stages (Section 3)

S-MIS has **two steps**:

### Step 1 — Maximal independent set (black)

Construct an MIS that satisfies **Lemma 2** (Wan [16] / Cheng [5] property):

> Any pair of complementary subsets of the MIS have distance exactly two hops  
> ⇒ any two MIS nodes are at most two hops apart in the UDG.

Paper: *“We can use the method in Reference [16] or Cheng [5] to construct a MIS.”*  
Reference [16] = Wan–Alzoubi–Frieder INFOCOM 2002.  
Cheng [5] is an **alternative** MIS construction (degree/`(d*, ID)` based); we do **not** claim Cheng equivalence.

**Project choice.** Centralized implementation of **Wan’s level-based MIS**:

1. Leader = smallest point ID  
2. Deterministic BFS spanning tree  
3. Greedy first-fit MIS by increasing rank `(level, id)`  

Mark MIS nodes **black**. All other nodes **grey**.

Do **not** add Wan’s tree-parent connectors here. Connection is Step 2.

Verified in `test_wan_level_mis`: production MIS ≡ paper-literal WHITE/BLACK/GRAY reference; independence; maximality; Lemma 2 via connectivity of the distance-2 graph on MIS vertices.

### Step 2 — Steiner interconnection (Algorithm A)

Interconnect black terminals by greedily selecting **Steiner (blue)** nodes — a greedy approximation for **ST-MSN** (Steiner tree with minimum number of Steiner nodes).

```text
mark MIS black; others grey
black-blue component := connected component of the subgraph induced by
    black ∪ blue nodes, IGNORING edges between blue nodes

for i = 5, 4, 3, 2 do
    while ∃ grey g adjacent to ≥ i black nodes that lie in
          pairwise-different black-blue components:
        colour g blue   # merges those components
return all blue nodes
```

**Output CDS:** all black ∪ all blue.

---

## 3. Exact MIS rule

| Item | Rule |
| --- | --- |
| Method | Wan level-based spanning-tree MIS (Lemma 2), not Cheng / not arbitrary ID-MIS |
| Priority | Rank `(BFS level, point ID)`, lexicographic |
| Join MIS | Node joins if no neighbour already in MIS (scan in rank order) |
| Degree / uncovered count | **Not** used in Step 1 |
| Unavailable | Neighbours of selected MIS nodes cannot join |
| Termination | All vertices processed in rank order |

**Project tie-breaks (same as `docs/wan.md`):** leader = min ID; BFS parent = first discoverer with neighbours scanned by ascending ID.

---

## 4. Steiner connection stage (Algorithm A) — detail

| Item | Paper |
| --- | --- |
| Terminals | Black MIS nodes |
| Steiner candidates | Grey nodes |
| Selected Steiner | Blue nodes |
| Objective (greedy) | Merge black-blue components; prefer greys touching many components |
| Outer loop | `i = 5 → 2` (UDG: a node neighbours ≤ 5 independent blacks) |
| Inner rule | While a grey touches ≥ `i` blacks in **distinct** components → blue it |
| Component graph | Induced on black∪blue **without blue–blue edges** |
| Stop | After `i = 2` finishes (one component expected on connected UDG + Lemma 2 MIS) |

**What a grey’s score is.**  
`y(g)` = number of **distinct black-blue components** represented among **black** neighbours of `g`.  
(Adjacency to blue alone does not count toward `y`.)

**Effect of selecting blue `g`.**  
Union the components of all black neighbours of `g`.

**Not used:** BFS-tree parents, Funke recruiter parents, full geometric Steiner tree in the plane.

---

## 5. S-MIS vs rS-MIS (Section 4)

| | **S-MIS** (implement) | **rS-MIS** (do not implement) |
| --- | --- | --- |
| Role | Primary greedy algorithm of the paper | Simulation variation |
| Black-blue components | **Ignore** blue–blue edges | **Include** blue–blue edges |
| Why compared | Submodularity / proof of Theorem 2 needs ignoring blue–blue | Empirical: sizes almost identical |
| Paper conclusion | Theoretical PR proved for S-MIS | Occasional tiny empirical improvement |

---

## 6. Approximation guarantee

**Theorem 1.** S-MIS produces a CDS of size at most

```text
(4.8 + ln 5) · opt + 1.2
```

where `opt = |MCDS|`. Numerically `4.8 + ln 5 ≈ 6.409` (document as `4.8 + ln 5`, not bare `6.4`).

**Proof structure (paper):**

| Piece | Bound | Source |
| --- | --- | --- |
| MIS size | `≤ 3.8 · opt + 1.2` | Lemma 1 |
| Blue Steiner nodes | `≤ (1 + ln 5) · C(T) ≤ (1 + ln 5) · opt` | Theorem 2 (greedy set-cover style on components) |
| Total | `≤ (4.8 + ln 5) · opt + 1.2` | Theorem 1 |

**Separate carefully:**

```text
paper theoretical guarantee:  (4.8 + ln 5) opt + 1.2
our measured empirical CDS/OPT:  from ExactSmall experiments only
```

**Known later critique (limitation, not our code bug):** some subsequent papers argue the published `4.8 + ln 5` analysis should be corrected (e.g. toward `5.8 + ln 5`). We still report the **original paper’s stated** guarantee in tables, and note the debate under Known limitations.

---

## 7. How S-MIS differs from prior algorithms

### vs Marathe

| | Marathe CDOM | S-MIS |
| --- | --- | --- |
| MIS | Per-level MIS in BFS tree | Global Wan level-based MIS |
| Connection | Tree parents of level MIS nodes | Greedy Steiner Algorithm A |
| Tree dependence | Essential for both phases | Tree only to build Lemma-2 MIS |
| Bound (paper era) | Classic CDOM analyses | `4.8 + ln 5` |

### vs Wan–Alzoubi–Frieder

| | Wan | S-MIS |
| --- | --- | --- |
| MIS | Rank-order MIS (same family) | **Same MIS family** (Wan level-based) |
| Connection | **Tree parents** of MIS nodes | **Steiner greedy blues** (Algorithm A) |
| Tree dependence | Parents become CDS | Tree discarded after MIS |
| Bound | ≤ 8 (INFOCOM’02) | `4.8 + ln 5` |

S-MIS is **not** “Wan with a better label”: the connector stage is different and can select different (and differently many) nodes.

### vs Funke–Kesselman–Meyer–Segal

| | Funke | S-MIS |
| --- | --- | --- |
| MIS | Growing red-frontier local-min-ID | Wan level-based rank MIS |
| Connection | Blue recruiter → grey | Multi-component grey→blue Steiner |
| Frontier dependence | Essential | None in Step 2 |
| Bound | ≤ 6.91 (TOSN’06 analysis) | `4.8 + ln 5` |

---

## 8. Distributed → centralized mapping

| Paper | Centralized |
| --- | --- |
| Wan level-based MIS messages | State arrays + BFS + rank MIS (as Wan) |
| Grey `y`-value | `radiusQuery` + count distinct DSU roots among black neighbours |
| Pick next blue | Among greys with `y ≥ i`, choose max `(y, −id)` i.e. highest `y`, then smallest ID |
| Merge components | Union-Find on black indices |
| Section 5 UPDATE messages | Not simulated |

Complexity claims of the distributed Section 5 protocol are **not** claimed for our C++ binary. We report centralized `algorithm_ms`, SpatialIndex queries, candidates, peak memory.

---

## 9. SpatialIndex / auxiliary structures

| Need | Mechanism |
| --- | --- |
| One-hop neighbours | `SpatialIndex::radiusQuery` |
| MIS neighbour checks | Colour / bitmap + query |
| Grey score `y` | Query blacks; map to DSU roots |
| Component tracking | Union-Find over **MIS blacks only** — `O(|MIS|) ⊆ O(n)` |
| Blue set | Colour vector `O(n)` |

**Forbidden:** global UDG adjacency, all-pairs distances, precomputed k-hop graph.

**Memory.** Production state is `O(n)` plus DSU of size `|MIS|`. No auxiliary graph on all edges. Temporary neighbour buffers only.

Optional instrumentation: track `|MIS|` and number of blues selected (already implied by CDS size − MIS size).

---

## 10. Determinism (project-added)

| Choice | Paper | Project |
| --- | --- | --- |
| MIS construction | Wan [16] (or Cheng) | Wan level-based MIS (min-ID leader, BFS, rank) |
| Which grey when several have `y ≥ i` | Distributed: larger `y`, then smaller ID | Same: maximize `y`, then minimize ID |
| DSU union parent | Unspecified | Smaller component root ID (or smaller black ID) |
| Neighbour scan order | Unspecified | Ascending neighbour ID |

---

## 11. Interface

```cpp
class LiSMISAlgorithm : public MCDSAlgorithm {
    MCDSResult solve(const PointSet&, const SpatialIndex&, double radius) override;
    std::string name() const override { return "li"; }
};
```

Result: selected IDs = black ∪ blue. No I/O / timing / validation inside the algorithm.

---

## 12. Executable pseudocode (centralized)

```text
# Step 1 — Lemma-2 MIS (Wan level-based)
T ← BFS tree from min-ID leader
MIS ← greedy independent set by increasing (level_T, id)
colour[u] ← BLACK if u ∈ MIS else GREY

# DSU over black indices
for each black b: make_set(b)

# Step 2 — Algorithm A
for i in (5, 4, 3, 2):
    loop:
        best ← none
        for each grey g:
            comps ← { find(b) | b black neighbour of g }
            y ← |comps|
            if y ≥ i and (best is none or y > best.y or (y = best.y and id(g) < id(best))):
                best ← g with score y
        if best is none: break
        colour[best] ← BLUE
        for each black neighbour b of best:
            union components of those blacks

return IDs of all BLACK ∪ BLUE
```

---

## Ambiguities

1. **Cheng [5] vs Wan [16] MIS.** Both cited for Lemma 2. We implement **Wan level-based MIS only** (Cheng uses different selection mechanics).  
2. **Centralized grey selection order** within equal `i`. Resolved via distributed ranking `(y, ID)`.  
3. **Later corrections to `4.8 + ln 5`.** Documented as external debate; we still cite Theorem 1 as stated.

None block a faithful Algorithm A + Wan level-based MIS implementation.
