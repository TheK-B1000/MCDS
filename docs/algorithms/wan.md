# Paper-to-code audit: Wan–Alzoubi–Frieder

Audit date: 2026-10-05. Code: `main` @ `06bf246`. No algorithm code was changed.

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
| Pruning rule | **Not implemented** |
| Output | Selected ids; role `core` if type-1, else `connector` |

`test_wan_level_mis` differentially checks the type-1 set against a separate WHITE/BLACK/GRAY reference of the same rank rule, and checks independence, maximality, and Li’s two-hop property. That suite does not execute the pruning rule and does not build the Cidon–Mokryn tree.

## Intentional adaptations

- Centralized. No messages, no `COMPLETE` reports, no asynchronous schedule.
- Leader is minimum id, which the paper explicitly allows.
- The spanning tree is a BFS tree, not the tree produced by [5]. The §VI counting argument uses whatever spanning tree phase 1 produced: type-1 nodes are an independent set (Lemma 9) and each non-root type-1 node contributes its tree parent as a type-2 node. A BFS tree is a spanning tree, so that algebra still applies.
- The pruning sentence is omitted. It fires only when every neighbour is already black, and the message it would send is `DOMINATOR` to neighbours that are already black, so it does not create new black nodes under the stated transitions. It only removes a node from the CDS. Our output is therefore the pre-pruning type-1 ∪ type-2 set, which is what the `8·opt + 1` count bounds. It can be a strict superset of a full §VI.A execution.

## Implementation-specific decisions

- Neighbours are queried on demand; ranks of neighbours are not stored globally.
- Union of parents is by vertex id, so several MIS children that share a parent contribute that parent once.

## Unresolved ambiguities

- The fourth colour rule is readable in this PDF (it is not an OCR fragment). Whether any published proof subtracts pruned nodes *before* applying `8·opt + 1` is not a separate lemma; the displayed sum is over type-1 and type-2 blacks. We treat `8·opt + 1` as the bound on that sum.
- Theorem 10 says “at most 8”. The displayed inequality is `8·opt + 1`, which is not ≤ `8·opt` for every positive `opt`. We do not claim a strict ratio of 8 on every finite instance.

## Theoretical guarantee

**Paper derivation that matches our set:** `|type-1 ∪ type-2| ≤ 8·opt + 1`.

**Applies to our implementation: yes, for that inequality**, because we output exactly those two types on a spanning tree, and Lemma 9 is a bound on any independent set.

**Not claimed:** `O(n)` time and `O(n log n)` messages (Theorem 10’s complexity clauses). We do not run the distributed protocol.

**Not claimed as identical output:** a complete execution of §VI.A that applies the pruning rule.

`IMPLEMENTATION VERIFIED: PARTIAL`
