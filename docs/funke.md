# Funke–Kesselman–Meyer–Segal CDS Algorithm

## Bibliographic source

Stefan Funke, Alexander Kesselman, Ulrich Meyer, Michael Segal.  
“A Simple Improved Distributed Algorithm for Minimum CDS in Unit Disk Graphs.”  
*ACM Transactions on Sensor Networks*, Volume 2, Issue 3, 2006, pp. 444–453.  
DOI: [10.1145/1167935.1167941](https://doi.org/10.1145/1167935.1167941)

Earlier conference version (WiMob 2005):

- IEEE: [10.1109/WIMOB.2005.1512873](https://doi.org/10.1109/wimob.2005.1512873)
- Public PDF (Stanford; **not** committed):  
  http://graphics.stanford.edu/~sfunke/Papers/WIMOB05/WIMOB05.pdf

Prefer the journal version when details differ. Algorithmic description below follows
Section II / Figure 1 of the publicly available WiMob text, which matches the
journal abstract’s stated bound and construction.

This document is based on that paper. Secondary summaries must not override it.

---

## 1. Problem definition and geometry convention

**Paper (§I).** Nodes lie in the Euclidean plane with equal transmission range
**2**. The network is a unit-disk graph: edge `{u,v}` iff Euclidean distance
`≤ 2` (equivalently: unit disks of radius 1 centered at the nodes intersect).

The paper states explicitly that this is a **scaling choice** to simplify
proofs, and that results hold for any constant unit (including transmission
range 1) after uniform scaling.

**Project mapping (do not change default radius).**

| Paper | Project |
| --- | --- |
| Vertices | Input points in `PointSet` |
| Edge `{u,v}` | `distance(u,v) ≤ radius` |
| Paper’s “unit” scale | Transmission range 2 |
| **Our default radius** | **`1.0` (unchanged)** |
| Neighbor discovery | `SpatialIndex::radiusQuery` |

We interpret every geometric argument under uniform scaling. We **do not**
set project radius to `2.0`.

CDS / OPT definitions match the usual Dominating + Connected Dominating Set
notions used elsewhere in this repository.

---

## 2. What we implement

| Section | Content | Role here |
| --- | --- | --- |
| §I | Motivation, UDG definition (range 2), prior work including Wan ≤8 | Context |
| **§II / Fig. 1** | **Distributed colouring / growing CDS algorithm** | **Implemented** |
| §II.A | Correctness invariants + Theorem 2.1 (≤6.91) | Bound documentation |
| **§III** | Area / Voronoi analysis of MIS vs OPT | **Analysis only** (source of 6.91) |
| §IV | Conclusions | Context |

We implement **only** the construction in Section II (Figure 1). We do **not**
implement D2-colouring / interference slotting; that is a distributed scheduling
mechanism for message delivery, not part of the combinatorial selection rule.

---

## 3. Algorithm stages (Section II)

The paper builds a connected set `S` and an independent set `I ⊆ S` using node
colours:

| Colour | Meaning |
| --- | --- |
| **black** | In `I` (MIS member) |
| **grey** | In `S` but not in `I` (connector) |
| **blue** | Not in `S`, but adjacent to some black |
| **red** | Not black/grey/blue; adjacent to a grey or blue; competing to join `I` |
| **white** | Not black/grey/blue and not adjacent to grey or blue |

**Final CDS:** `S` = black ∪ grey.

### Stage 0 — Initialization

| Item | Paper |
| --- | --- |
| Input | Connected UDG |
| Action | Elect one leader; colour it **red**; all others **white** |
| Parent | Each red node except the first keeps a parent (initially a blue recruiter) |
| Output | One red seed; no blacks/greys/blues yet |

**Centralized adaptation.** Leader = **smallest point ID**. Leader has
`parent = none`.

### Stage 1 — Rounds until no white or red remain

Each **round** has three phases (paper Fig. 1). With D2-colouring, phases use
conflict-free slots; we centralize the same state transitions without simulating
slots.

#### Phase I — APPLY

| Item | Paper |
| --- | --- |
| Who | Every **red** node |
| Action | Send `APPLY-MSG` carrying its ID |
| Local info | Own ID |

#### Phase II — CONFIRM

| Item | Paper |
| --- | --- |
| Who (join `I`) | Each red that, among APPLY messages from **red neighbours**, saw **only larger IDs** (or no such APPLY) |
| Action | Colour itself **black**; send `CONFIRM-MSG(black)` with own ID and **parent ID** |
| Connector | Each **blue** that receives CONFIRM with `parent ID = own ID` colours itself **grey** |
| Output | New blacks in `I`; some blues promoted to grey connectors |

Nutschell (paper): each red with **minimum ID among its red neighbours** joins
`I`, and its blue parent joins `S`.

#### Phase III — UPDATE

| Item | Paper |
| --- | --- |
| Become blue | Each **red or white** that received ≥1 `CONFIRM-MSG(black)` colours **blue** and sends `UPDATE-MSG(blue)` |
| Become red | Each **white** that receives `UPDATE-MSG(blue)` from `v` colours **red** and sets **parent = v** |
| Termination of round | Frontier advances |

**Global termination.** No white or red nodes remain. Then every vertex is
black, grey, or blue, so `I` dominates and `S` is a CDS (paper invariants).

---

## 4. MIS construction

Funke’s independent set `I` is **not** computed by BFS rank order.

```text
I grows from the red frontier:

while red nodes exist:
    winners ← { u red | id(u) < id(v) for every red neighbour v of u }
    colour each winner black  (join I)
    // then UPDATE expands blue / red frontier
```

Required neighbourhood information:

- one-hop neighbour IDs and colours
- for a red node: which neighbours are currently red
- for CONFIRM→grey: parent pointer of the new black (a former blue)

State per node: colour, parent (or none), ID.

Termination of MIS growth: coupled to global colour termination (no red/white).

---

## 5. Connector construction

Connectors are **grey** nodes:

```text
when red u becomes black:
    if u has parent p:   # p was blue
        colour p grey    # p joins S
```

- Parent of a non-leader red is the **blue** node `v` that sent the UPDATE which
  recruited it (paper Phase III).
- The leader / first red has **no** parent → first black adds no grey.
- Paper analysis: each grey associates with a **unique** black child ⇒
  `|S| ≤ 2|I|`.

This is **not** “add BFS-tree parent of every MIS node” (Wan). The parent is a
frontier recruiter on the growing MIS wave, not a spanning-tree parent.

---

## 6. Approximation result

**Theorem 2.1 (paper):** the algorithm computes a CDS `S` with

```text
|S| ≤ 6.91 · |OPT| + 16.58
```

(plus distributed runtime/message claims under their model).

**Source of the improvement (Section III, not a different connector trick):**

1. Theorem 3.1: area of union of radius-3 disks about OPT ≤ `|OPT|·11.774 + 9π`
2. Theorem 3.2: any independent set satisfies  
   `|I| ≤ 3.453 · |OPT| + 8.291`
3. Algorithm invariant `|S| ≤ 2|I|` ⇒ `|S| ≤ 6.906·|OPT| + …` ≈ **6.91**

Wan et al. used a looser MIS-vs-OPT relation leading to factor **8**. Funke’s
**main contribution** is this refined geometric analysis; the paper notes it
also improves stated guarantees for **many prior algorithms**, including Wan.

**Do not claim:** Funke produces a smaller CDS than Wan on every instance.
A better worst-case factor does not imply per-instance dominance.

**Do not claim:** our C++ binary has the paper’s distributed round/message
complexity.

---

## 7. Complexity claims (paper vs our code)

| Claim | Applies to |
| --- | --- |
| Approximation ≤ 6.91 (+ additive) | Solution quality of the **selection logic** on UDGs |
| Time `O(|OPT|·q)` with D2-colouring; `O(n)` ignoring interference | Original **distributed** algorithm |
| Messages `O(|OPT|·n)` / `O(n²)` | Original **distributed** algorithm |

Our implementation reports:

```text
actual centralized runtime (algorithm_ms)
SpatialIndex neighbor queries
candidates examined
peak process memory
```

These must **not** be relabelled as distributed rounds or messages.

---

## 8. Differences from Wan–Alzoubi–Frieder

| Aspect | Wan (INFOCOM 2002) | Funke (TOSN 2006) |
| --- | --- | --- |
| Leader / root | Leader + **spanning tree** | Leader coloured **red**; **no** spanning tree |
| Ranking | Rank = `(level, ID)` on tree | No level rank; **local min ID among red neighbours** |
| MIS rule | Greedy MIS in global rank order | Growing frontier: only **red** nodes compete each round |
| Tree usage | BFS/spanning tree parents = connectors | No tree; parent = **blue recruiter** |
| Connector selection | Parent in spanning tree of each MIS node | Blue parent of newly black node → **grey** |
| Node colours | white / gray / black (Wan marking) | white / red / blue / grey / black |
| Pruning | Optional gray→black prune (we omit) | None in Fig. 1 |
| Messages | DOMINATOR / DOMINATEE | APPLY / CONFIRM / UPDATE |
| Final CDS | MIS ∪ tree parents | black ∪ grey (`I` ∪ connectors) |
| Source of ≤6.91 vs ≤8 | — | Refined **MIS vs OPT analysis** (§III); construction also differs |

### Hard research-gate conclusion

**Selection logic is not equivalent to Wan.**

Under our centralized deterministic mapping:

- Wan: one BFS tree, global rank-order MIS, connectors = tree parents.
- Funke: iterative red-frontier MIS, connectors = blue recruiters.

They can agree on some instances and diverge on others. We **must not** invent
fake differences, but we also **must not** treat Funke as “Wan with a better
label.” Implement Funke’s Fig. 1 transitions as a separate algorithm.

(The improved 6.91 analysis can also be read as strengthening Wan’s *guarantee*
without changing Wan’s *code*; that does not make the Funke *procedure*
identical to Wan.)

---

## 9. Distributed → centralized mapping

| Paper | Centralized implementation |
| --- | --- |
| Leader election | Smallest point ID → colour RED |
| APPLY among reds | Inspect colours of one-hop neighbours via `radiusQuery` |
| “Min ID among red neighbours” | Compare IDs of red neighbours; winners in a round computed from a snapshot |
| CONFIRM → black | Set colour BLACK on winners |
| CONFIRM → grey parent | If `parent[u] ≥ 0`, set colour GREY |
| UPDATE → blue | Nodes (red/white) adjacent to **new** blacks → BLUE |
| UPDATE → red | Whites adjacent to **new** blues → RED with parent = recruiting blue |
| D2-colouring / slots | **Not simulated**; simultaneous round semantics from colour snapshots |
| Message complexity | **Not claimed** for C++ |

Round semantics (project): within one round, compute the set of winners from
the colouring at the start of the round; apply BLACK/GREY; then apply BLUE;
then apply RED. Do not interleave mid-round.

---

## 10. SpatialIndex mapping

| Need | How |
| --- | --- |
| One-hop neighbours | `radiusQuery(id, radius)` |
| Red neighbours of a red node | Query + filter by colour |
| Adjacency to new blacks (→ blue) | Query + filter |
| Adjacency to new blues (→ red) | Query + filter |
| Parent / connector | Integer parent index array (O(n)), not a second graph |
| Two-hop | **Not** required as a precomputed structure; only lazy one-hop queries |

Forbidden: global adjacency list, global edge list, all-pairs distances,
precomputed two-hop graph.

---

## 11. Determinism (project-added)

| Choice | Paper | Project rule |
| --- | --- | --- |
| Leader | “Leader election” | **Smallest point ID** |
| Simultaneous red winners | Local min ID among red neighbours | Same; use colour snapshot |
| Multiple UPDATE blues recruiting one white | Unspecified | Parent = **smallest ID** among blues that send UPDATE to that white in the round |
| Neighbour scan order | Unspecified | Ascending neighbour ID (affects only iteration, not winners) |
| Point ID uniqueness | Assumed | Enforced by `PointSet` |

---

## 12. Expected output / interface

```cpp
class FunkeAlgorithm : public MCDSAlgorithm {
    MCDSResult solve(
        const PointSet& points,
        const SpatialIndex& index,
        double radius
    ) override;
};
```

Result: selected point IDs (`S` = black ∪ grey). No timing, validation, I/O,
or visualization inside the algorithm.

Stable CLI / runner name: `funke`.

---

## 13. Executable pseudocode (centralized)

```text
n ← |points|
colour[0..n) ← WHITE
parent[0..n) ← none
leader ← argmin id
colour[leader] ← RED

while ∃ u with colour[u] ∈ {RED, WHITE}:
    # Phase I–II snapshot
    winners ← ∅
    for each u with colour[u] = RED:
        if ∀ red neighbour v of u: id(u) < id(v):
            winners ← winners ∪ {u}

    newBlacks ← winners
    newGreys ← ∅
    for u in winners:
        colour[u] ← BLACK
        if parent[u] ≠ none:
            colour[parent[u]] ← GREY
            newGreys ← newGreys ∪ {parent[u]}

    # Phase III — blues
    newBlues ← ∅
    for each u with colour[u] ∈ {RED, WHITE}:
        if adjacent to some v ∈ newBlacks:
            colour[u] ← BLUE
            newBlues ← newBlues ∪ {u}

    # Phase III — reds
    for each u with colour[u] = WHITE:
        blueNbrs ← neighbours of u with colour BLUE that are in newBlues
                    (or any BLUE that sent UPDATE this round = newBlues)
        if blueNbrs ≠ ∅:
            colour[u] ← RED
            parent[u] ← argmin id among blueNbrs

S ← { u | colour[u] ∈ {BLACK, GREY} }
return IDs of S
```

Refuse disconnected inputs (same policy as Marathe/Wan).

---

## Ambiguities

1. **Journal vs WiMob text.** Algorithmic Figure 1 text is taken from the
   public WiMob PDF; journal abstract and bound match. If a future journal PDF
   check shows a material selection-rule change, update this doc and the code.
2. **Parent when multiple blues UPDATE one white.** Paper silent → smallest
   blue ID (documented above).
3. **D2-colouring.** Scheduling only; omitted in centralized adaptation.
4. **“Parent grey node” wording vs blue parent.** Nutshell says blue parent
   joins `S` (becomes grey). We follow Fig. 1: parent is blue until CONFIRM.

None of these block implementation of a deterministic Fig. 1 adaptation.
