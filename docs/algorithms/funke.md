# Paper-to-code audit: Funke–Kesselman–Meyer–Segal

Audit date: 2026-10-05. Code: `main` @ `06bf246`. No algorithm code was changed.

## Citation

Stefan Funke, Alexander Kesselman, Ulrich Meyer, Michael Segal, “A Simple
Improved Distributed Algorithm for Minimum CDS in Unit Disk Graphs.”

| Item | Value |
| --- | --- |
| Local paper | `papers/primary/funke_kesselman_meyer_segal.pdf` (gitignored) |
| SHA-256 | `BDBC527E03B3D3EF92BDCAB9304F3E9502DFC6FE1819536AEE85B03161C84688` |
| Pages | 4 |
| Exact section used | §II, Figure 1, Theorem 2.1; §III, Theorems 3.1 and 3.2 |

The local file is the **4-page** version (Figure 1, Theorem 2.1, references
including Wan INFOCOM 2002 as [8] and Marathe *Networks* 1995 as [7]). It is
the conference text, not the 10-page *ACM TOSN* 2(3):444–453, 2006 article.
`Funke.hpp` now names this 4-page paper as the implementation source. **TOSN was not in
the local paper set and was not checked; it is not cited as the implementation source.** This audit verifies the code
against the 4-page PDF only.

## Model

§I: nodes lie in the plane with equal transmission range **2**. Two nodes are
adjacent when their distance is at most 2. The authors state that any other
constant unit, including range 1, is the same after scaling. Our `R = 1` is
that normalization, not an algorithm discrepancy.

The algorithm assumes a connected unit-disk graph (a CDS of `G`). Connectivity
is verified once, untimed, for all four algorithms by the runner / CLI. Since
2026-10-05 `solve` no longer runs its own `isConnected` BFS (that traversal
had been charged to Funke's algorithm-stage counters only). A disconnected
input is still rejected: the red frontier dies out while white vertices remain,
and `solve` throws `std::invalid_argument`. Selected sets are unchanged on
connected inputs; Funke's algorithm-stage queries drop by exactly `n`.

## Paper algorithm (Figure 1)

Colours: **black** = in the independent set `I`; **blue** = adjacent to `I` but not in the CDS `S`; **grey** = in `S` but not in `I`; **red** = not black/grey/blue, but adjacent to a grey or blue node; **white** = none of the above.

Initialization: one node is red (by a leader election); every other node is white. Each red node except the first keeps a parent, which is a grey node in the prose and a blue node at the moment it is recruited (Figure 1 sets the parent to the blue node `v` that sent `UPDATE-MSG`).

Each round has three phases, assuming a conflict-free slot assignment from a D2-colouring so that interference is handled. Ignoring that schedule, the combinatorial rule is:

1. **Apply.** Every red node announces its ID.
2. **Confirm.** A red node that received only larger IDs (equivalently: minimum ID among its red neighbours; §II prose) becomes black and announces itself and its parent. The blue node whose ID is that parent becomes grey.
3. **Update.** A red or white node that received a confirm from a new black becomes blue and announces that. A white node that receives such an announcement from `v` becomes red and sets its parent to `v`.

Termination (§II.A): no white or red nodes remain. Invariants: black nodes are independent and dominate grey and blue; black ∪ grey is connected; if black is not yet dominating, some red remains; each round turns at least one red black.

`S` is the final black ∪ grey set. Each grey node is the parent of at least one black node, and each black node except the leader has one parent, so `|S| ≤ 2|I|`.

## Source code

| Piece | Location |
| --- | --- |
| Entry | `FunkeAlgorithm::solve` in `cpp/src/algorithms/Funke.cpp` |
| Declaration | `cpp/include/algorithms/Funke.hpp` |
| Tests | `cpp/tests/test_funke.cpp` |

## Paper-to-code mapping

| Paper step | Code |
| --- | --- |
| One initial red node | Minimum point id, coloured red; `parent = -1` |
| Apply / confirm winner | A red node whose red neighbours all have larger ids |
| Parent becomes grey | `colour[parent[u]] = Grey` when `u` turns black, if a parent exists |
| Red/white next to a new black becomes blue | Scan using `isNewBlack` from this round only |
| White next to a new blue becomes red | Parent stored; if several new blues are adjacent, the **minimum id** is kept |
| Output `S` | Black → role `core`; grey → role `connector`. Blue and white/red are not selected |
| D2-colouring and time slots | Not implemented |

## Intentional adaptations

- Centralized rounds over colour snapshots. No slotting, no interference model.
- Leader is minimum id. The paper allows any leader election.
- When several new blues recruit the same white node, Figure 1 says the parent is “`v`” and does not say which `v`. We take the smallest id. Each black node still has at most one parent, and every grey node is that parent for some black node, so `|S| ≤ 2|I|` still holds. Which connector is chosen can differ from another legal reading.

## Implementation-specific decisions

- A safety loop bound of `n + 2` rounds throws if the red frontier stalls. The paper’s invariant says that does not happen on a connected graph.
- Neighbourhood is a radius query, not a received-message buffer. A node “hears” exactly its current geometric neighbours.

## Unresolved ambiguities

- Whether the TOSN 2006 text changes Figure 1 or Theorem 2.1 is **unchecked**.
- The parent tie-break is unspecified in Figure 1.

## Theoretical guarantee

**Paper (this PDF), Theorem 2.1:** the algorithm computes a CDS `S` with

`|S| ≤ 6.91 · |OPT| + 16.58`,

because `|I| ≤ 3.453 · |OPT| + 8.291` (Theorem 3.2, any independent set) and `|S| ≤ 2|I|`. The abstract’s “at most 6.91” drops the additive term. Theorem 3.2 is geometric and does not depend on the message schedule.

**Applies to our implementation: yes, for the size bound**, on the scale-normalized unit-disk graph. Our `I` is an independent set of the Figure 1 process, and `|S| ≤ 2|I|` holds with the min-id parent rule.

**Not claimed:** running time `O(|OPT| · q)` and message complexity `O(|OPT| · n)`, or the interference-free corollary `O(n)` / `O(n²)`. We do not build the D2-colouring.

`IMPLEMENTATION VERIFIED: YES`
