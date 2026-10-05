# Paper-to-code audit: Wan–Alzoubi–Frieder

Audit date: 2026-10-05. Code: `main` @ `06bf246`; pruning rule added afterwards (same date), see mapping.

## Citation

Peng-Jun Wan, Khaled M. Alzoubi, Ophir Frieder, “Distributed Construction of
Connected Dominating Set in Wireless Ad Hoc Networks,” IEEE INFOCOM 2002.

| Item | Value |
| --- | --- |
| Local paper | `papers/primary/wan_alzoubi_frieder_2002.pdf` (gitignored) |
| SHA-256 | `B7400584C3F6F63458142E61F59D663F2DFB484C44B9F6DD07D15BE60DC0D3E4` |
| Pages | 8 |
| Exact section used | §VI, “A Better Distributed Algorithm”; §VI.A; Figure 5; Theorem 8; Lemma 9; the counting argument ending in Theorem 10 |

## Model

The paper’s network is a unit-disk graph. Our adjacency rule is
`distance(p, q) ≤ R` with `R = 1`. Disks of radius `1/2` that intersect
describe the same edges. Scale is not treated as an algorithm discrepancy.
The construction assumes a connected network (a spanning tree of the whole
graph). Our BFS throws if some vertex is unreached.

## Paper algorithm (§VI.A)

Three phases.

1. **Leader election.** Elect a leader `v` and build a spanning tree `T` rooted at `v`, using the distributed algorithm of Cidon–Mokryn [5]. Leadership may be defined by ID, or by degree and ID. Each node learns its parent and children. `O(n)` time, `O(n log n)` messages as cited.
2. **Level calculation.** Root announces level 0. A node sets its level to one more than its parent’s and records the levels of its unit-disk neighbours. Rank is the lexicographic pair `(level, ID)`. The leader has the lowest rank.
3. **Colour marking.** Nodes start white and end black (dominator) or gray (dominatee). The root marks itself black and sends `DOMINATOR`. Then:
   - A white node that receives `DOMINATOR` for the first time marks itself gray and sends `DOMINATEE`.
   - A white node that has received `DOMINATEE` from every lower-rank neighbour marks itself black, sends `DOMINATOR`, and records its tree parent as its dominator (type-1 black).
   - A gray node that receives `DOMINATOR` for the first time from a **child in `T` that has never sent `DOMINATEE`** marks itself black and sends `DOMINATOR` (type-2 black).
   - **Pruning:** if a black node has rank higher than every neighbour and every neighbour is black, it marks itself gray and sends `DOMINATOR`.

Theorem 8: the final black nodes form a CDS. Lemma 9: any independent set has size at most `4·opt + 1`. The counting argument then shows that the number of type-1 blacks plus type-2 blacks is at most `2(4·opt + 1) − 1 = 8·opt + 1`. Theorem 10 summarizes this as an approximation factor of at most 8, with `O(n)` time and `O(n log n)` messages.

## Source code

| Piece | Location |
| --- | --- |
| CDS | `WanAlgorithm::solve` in `cpp/src/algorithms/Wan.cpp` |
| Declaration | `cpp/include/algorithms/Wan.hpp` |
| BFS | `buildWanBfsTree` |
| Type-1 MIS | rank-order scan in `solve` |
| Same MIS, shared with Li | `computeWanLevelBasedMis` in `cpp/src/algorithms/WanLevelMis.cpp` |
| Tests | `cpp/tests/test_wan.cpp`, `cpp/tests/test_wan_level_mis.cpp` |

## Paper-to-code mapping

| Paper step | Code |
| --- | --- |
| Leader by ID | Smallest point id |
| Spanning tree from [5] | Deterministic BFS: ascending neighbour-id scan; first discoverer is parent |
| Rank `(level, ID)` | `rankLess` on BFS depth and point id |
| Type-1 black | Greedy first-fit: in increasing rank, select `u` iff no neighbour is already selected. This is the sequential form of “lower-rank neighbours have all sent `DOMINATEE`” |
| Type-2 black | For every selected vertex except the leader, add `tree.parent` |
| Pruning rule | Implemented in `solve` (2026-10-05): a selected vertex with ≥ 1 neighbour, all neighbours selected, and rank higher than every neighbour is removed. Evaluated on the type-1 ∪ type-2 set; its radius queries are inside `T_algorithm` |
| Output | Selected ids; role `core` if type-1, else `connector` |

`test_wan_level_mis` differentially checks the type-1 set against a separate WHITE/BLACK/GRAY reference of the same rank rule, and checks independence, maximality, and Li’s two-hop property. It does not build the Cidon–Mokryn tree. `test_wan` checks the pruning against an independent reconstruction of the pre-pruning set with the §VI.A rule applied asynchronously (random orders, to a fixpoint) on ≥ 1,000 random connected UDGs: identical output, pruned vertices are always type-1, every result is a valid CDS.

## Intentional adaptations

- Centralized. No messages, no `COMPLETE` reports, no asynchronous schedule.
- Leader is minimum id, which the paper explicitly allows.
- The spanning tree is a BFS tree, not the tree produced by [5]. The §VI counting argument uses whatever spanning tree phase 1 produced: type-1 nodes are an independent set (Lemma 9) and each non-root type-1 node contributes its tree parent as a type-2 node. A BFS tree is a spanning tree, so that algebra still applies.
- The pruning rule (fourth bullet of §VI.A; black→gray edge of Fig. 5) is applied once to the final type-1 ∪ type-2 set. This equals any asynchronous execution order: an eligible node outranks all its neighbours, so none of them is eligible, and removing it never changes another node's eligibility. Why it cannot break the CDS (argument from the Theorem 8 proof, not a lemma in the paper): an eligible node has no tree children (a child would be a higher-ranked neighbour), so it is never the parent `u₂` on a black path; it turned black only after all lower-ranked neighbours were already gray, so it is never the `u₃` that first grayed a node; and all its neighbours are black, so it dominates nobody exclusively.
- Vacuous case: a node with no neighbours (n = 1) is not pruned, so the CDS stays nontrivial as Theorem 8 states.

## Implementation-specific decisions

- Neighbours are queried on demand; ranks of neighbours are not stored globally.
- Union of parents is by vertex id, so several MIS children that share a parent contribute that parent once.

## Unresolved ambiguities

- The fourth colour rule is readable in this PDF (it is not an OCR fragment). Whether any published proof subtracts pruned nodes *before* applying `8·opt + 1` is not a separate lemma; the displayed sum is over type-1 and type-2 blacks. We treat `8·opt + 1` as the bound on that sum.
- Theorem 10 says “at most 8”. The displayed inequality is `8·opt + 1`, which is not ≤ `8·opt` for every positive `opt`. We do not claim a strict ratio of 8 on every finite instance.

## Theoretical guarantee

**Paper derivation that matches our set:** `|type-1 ∪ type-2| ≤ 8·opt + 1`.

**Applies to our implementation: yes.** Before pruning we hold exactly those two types on a spanning tree, and Lemma 9 bounds any independent set; pruning only removes vertices, so the output also satisfies `|D| ≤ 8·opt + 1`.

**Not claimed:** `O(n)` time and `O(n log n)` messages (Theorem 10’s complexity clauses). We do not run the distributed protocol.

**Not claimed as identical output:** a distributed execution on the Cidon–Mokryn tree. With a different spanning tree, levels and ranks differ, so the selected vertices can differ.

`IMPLEMENTATION VERIFIED: YES` (selection rules incl. pruning; spanning tree is BFS — see adaptations)
