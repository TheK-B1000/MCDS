# Paper-to-code audit: Li et al. — S-MIS

Audit date: 2026-10-05. Code: `main` @ `06bf246`. No algorithm code was changed.

This is the Li–Thai–Wang–Yi–Wan–Du paper. It is not a different Li CDS paper.

## Citation

Yingshu Li, My T. Thai, Feng Wang, Chih-Wei Yi, Peng-Jun Wan, Ding-Zhu Du,
“On Greedy Construction of Connected Dominating Sets in Wireless Networks,”
*Wireless Communications and Mobile Computing* 5(8):927–932, 2005.
DOI: [10.1002/wcm.356](https://doi.org/10.1002/wcm.356).

| Item | Value |
| --- | --- |
| Local paper | `papers/primary/li_thai_wang_yi_wan_du_2005_smis.pdf` (gitignored) |
| SHA-256 | `451E80F7E213D09331831A4B30B821974ECE8820103DB97561C21CAC9715D254` |
| Pages | 6 (journal pages 927–932) |
| Exact section used | §3 (S-MIS, Algorithm A, Lemma 1, Lemma 2, Theorem 1, Theorem 2); §5 only for the grey-node ranking used as a tie-break. §4 (rS-MIS) is **not** implemented |

## Model

§1: hosts in the plane with equal maximum transmission range; the topology is an undirected unit disk graph, cited to Clark–Colbourn–Johnson. The paper does not restate a numeric radius. Our rule is `distance ≤ R` with `R = 1`. That is the proximity form of the same unit-disk model and is not treated as an algorithm discrepancy.

The construction assumes the UDG is connected (otherwise no CDS). `computeWanLevelBasedMis` throws if the BFS does not reach every vertex.

## Paper algorithm (§3)

S-MIS has two steps.

**Step 1 — MIS.** Construct a maximal independent set. The paper does not reprint the MIS procedure. It says an MIS with Lemma 2 can be built by the method of Wan [16] or Cheng [5], and “we assume throughout this paper that the MIS satisfies Lemma 2.”

- **Lemma 1.** In a unit disk graph, every MIS has size at most `3.8·opt + 1.2`, citing [20]. This is stated for every MIS, not only Wan’s.
- **Lemma 2.** Any pair of complementary subsets of the MIS are at distance exactly two hops. In particular any two MIS nodes are at most two hops apart.

Mark MIS nodes black and all other nodes grey.

**Step 2 — Algorithm A.** A black-blue component is a connected component of the subgraph induced by black and blue nodes **ignoring edges between blue nodes**.

```text
for i = 5, 4, 3, 2 do
    while there exists a grey node adjacent to at least i black
          nodes in different black-blue components do
        colour that grey node blue
return all blue nodes
```

The CDS is the black nodes together with the blue nodes. Theorem 2: the number of blue nodes is at most `(1 + ln 5)` times the number of Steiner nodes in an optimal ST-MSN tree for the MIS. Theorem 1: the CDS has size at most `(4.8 + ln 5)·opt + 1.2`. The arithmetic is Lemma 1 plus Theorem 2, using that an MCDS is a feasible way to connect the MIS so the Steiner cost is at most `opt`.

The centralized loop says “there exists”: it does not rank grey nodes that all meet the same threshold `i`. §5 (distributed implementation) ranks a grey node by `y` first, then by ID: larger `y` is higher, and equal `y` prefers the smaller ID. `y` is the number of adjacent black nodes that lie in different black-blue components. A grey node is adjacent to a component only through a **black** node in it.

§4 defines rS-MIS, which does count blue–blue edges. The paper reports that it occasionally yields a slightly smaller CDS and does not claim the Theorem 2 proof for it. We do not implement it.

## Source code

| Piece | Location |
| --- | --- |
| Step 2 and assembly | `LiSMISAlgorithm::solve` in `cpp/src/algorithms/LiSMIS.cpp` |
| Declaration | `cpp/include/algorithms/LiSMIS.hpp` |
| Step 1 | `computeWanLevelBasedMis` in `cpp/src/algorithms/WanLevelMis.cpp` |
| Score | `computeY` (black neighbours only) |
| Merge | `mergeTouchedBlackComponents` |
| Tests | `cpp/tests/test_li_smis.cpp` (CDS validity); `cpp/tests/test_wan_level_mis.cpp` (MIS vs a WHITE/BLACK/GRAY reference, independence, maximality, Lemma 2 on the distance-2 graph) |

## Paper-to-code mapping

| Paper step | Code |
| --- | --- |
| MIS via Wan [16] or Cheng [5] | Wan level-based MIS only: min-id leader, BFS, first-fit by `(level, ID)`. Cheng’s degree-based MIS is not implemented |
| Black / grey initialization | MIS ids set to `Colour::Black`; everyone else starts `Colour::Grey` |
| Black-blue components, blue–blue ignored | Union-find on vertex indices; `unite` only through **black** neighbours of the newly blue vertex |
| `y(g)` | `computeY`: distinct `find` roots among black neighbours |
| Loop `i = 5..2` | `for (threshold = 5; threshold >= 2; --threshold)` |
| “There exists” a grey with `y ≥ i` | Among greys with `y ≥ threshold`, pick larger `y`, then smaller id (§5 ranking) |
| Colour grey → blue and merge | `colour[best] = Blue`, then `mergeTouchedBlackComponents` |
| CDS | Black and blue ids. Roles: black `core`, blue `connector` |

## Intentional adaptations

- Centralized. The §5 message protocol (black lists, competitor lists, `UPDATE`) is not simulated. Only its ranking rule is used, and that rule is a refinement of Algorithm A’s unspecified choice among greys that meet the current threshold. Theorem 2’s set-cover argument needs a node whose `y` is at least the current `a_i / C(T*)` while higher thresholds are exhausted; it does not need a particular grey among those that qualify. The max-`y` / min-id rule stays inside that argument.
- The MIS is our centralized reading of Wan’s level-based type-1 set, not Cheng’s construction, and not a message-level replay of INFOCOM 2002.

## Implementation-specific decisions

- Union-find parent is the smaller index.
- Neighbour buffers are reused. No explicit graph is stored.

## Unresolved ambiguities

- Lemma 2 is an assumption the paper places on the MIS, citing Wan [16] and Cheng [5]. `test_wan_level_mis` checked it on hand-built graphs and on 6,000 generated connected UDGs, differentially against a paper-literal rank simulation. That is strong empirical evidence. It is not a proof for every unit disk graph.
- Lemma 1 is cited from [20] and is not proved in this PDF. We did not re-derive `3.8·opt + 1.2`.
- The abstract’s “factor of `4.8 + ln 5`” drops the additive `+1.2` that Theorem 1 states.

## Theoretical guarantee

**Paper, Theorem 1:** `|CDS| ≤ (4.8 + ln 5)·opt + 1.2`, if the MIS satisfies Lemma 2 and Lemma 1 applies.

**Algorithm A, as coded: the procedure matches §3**, including ignored blue–blue edges and the `5→2` thresholds.

**THEORETICAL GUARANTEE NOT CLAIMED FOR IMPLEMENTATION** as an unconditional theorem. It applies only if our MIS meets Lemma 2 on every connected UDG we run. We have differential and empirical support for that, not a formal proof. `LiSMIS.hpp` now states the bound as conditional and names the implementation an adaptation: **“S-MIS connector phase with centralized Wan-level MIS.”**

**Project argument (not in the paper; offered for review, not yet adopted as a claim): our MIS satisfies Lemma 2 on every connected graph.** Let `v` be a non-leader MIS vertex and `p` its BFS parent. `p` is one level above `v`, so `rank(p) < rank(v)` and the greedy scan processes `p` first. `p` is adjacent to `v`, which is selected, so `p` is not in the MIS; hence when `p` was processed some already-selected neighbour `u` blocked it, with `rank(u) < rank(p) < rank(v)`. So `v` has a 2-hop path `v–p–u` to an MIS vertex of strictly lower rank. By induction on rank, every MIS vertex reaches the leader in the graph whose edges join MIS vertices at distance 2. That graph is therefore connected, so any split of the MIS into two non-empty parts has a cross pair at distance ≤ 2, and since the MIS is independent that distance is exactly 2 — Lemma 2. If this argument is accepted, Theorem 1 applies to our implementation conditional only on Lemma 1, which the paper states for every MIS.

`IMPLEMENTATION VERIFIED: PARTIAL`
