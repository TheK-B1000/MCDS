# Source / paper audit

Audit date: 2026-10-05.
Code audited: `main` @ `06bf246`.
No algorithm implementation was modified.

The four primary PDFs live in `papers/primary/` on this machine. They are
gitignored. Citations, relative paths, and SHA-256 hashes are in
`papers/README.md` and the per-algorithm audits.
`SOURCE_NOT_VERIFIED` is no longer the status merely because a PDF was absent
from git.

Detailed paper-to-code maps:

- [Marathe CDOM](algorithms/marathe.md)
- [Wan–Alzoubi–Frieder](algorithms/wan.md)
- [Funke et al.](algorithms/funke.md)
- [Li et al. S-MIS](algorithms/li_smis.md)

Geometric scale: papers that use intersecting disks of radius 1 (center
distance ≤ 2), or transmission range 2, describe the same unit-disk family
as our proximity rule `distance ≤ R` with `R = 1`, after a global scale.
That difference is not counted as an algorithm discrepancy.

---

## Headline

| Algorithm | Primary paper present | Implementation verified |
| --- | --- | --- |
| Marathe CDOM | **YES** — arXiv:math/9409226v1 (preprint of the *Networks* 1995 paper). The *Networks* typeset PDF was not a second file. | **YES** |
| Wan–Alzoubi–Frieder | **YES** — INFOCOM 2002, 8 pages | **PARTIAL** |
| Funke–Kesselman–Meyer–Segal | **YES** — the 4-page paper with this title (Figure 1, Theorem 2.1). The TOSN 2006 journal PDF was not in the local set and was not checked. | **YES** (against that 4-page PDF) |
| Li et al. S-MIS | **YES** — WCMC 5(8):927–932, 2005, DOI 10.1002/wcm.356. This is the S-MIS paper, not a different Li paper. | **PARTIAL** |

---

## What “verified” means here

Each status is from reading that local PDF and the current C++ sources.
A paper guarantee is not assumed to transfer.

| Algorithm | What matches | What does not | Guarantee for our code |
| --- | --- | --- | --- |
| Marathe | Figure 2 (CDOM): BFS levels, `DS_i`, MIS on `S_i − DS_i`, tree parents | Root, BFS parent, and MIS pivot are fixed (smallest index / ascending id) instead of “arbitrary”. Those are legal instances of the paper’s arbitrary choices. | Theorem 4.9, factor 10, **applies** |
| Wan | §VI.A type-1 rank MIS and type-2 tree parents; leader by minimum id, which the paper allows | Spanning tree is BFS, not Cidon–Mokryn [5]. The black→gray pruning rule in §VI.A is omitted, so the output can be a strict superset of a full execution. Message complexity is not implemented. | The counting bound `\|type-1 ∪ type-2\| ≤ 8·opt + 1` **applies**. Theorem 10’s complexity clauses do **not**. A strict ratio of 8 on every finite instance is **not** claimed: the paper’s displayed inequality is `8·opt + 1`. |
| Funke | Figure 1 colour rounds: min-id red wins, parent becomes grey, new blacks recruit blues, new blues recruit reds. `S` = black ∪ grey | No D2-colouring / slotting. If several blues recruit one white node, the parent is the minimum id (Figure 1 does not specify which). Initial red node is the minimum id. | Theorem 2.1 size bound `\|S\| ≤ 6.91·\|OPT\| + 16.58` **applies**. Time and message bounds do **not**. |
| Li S-MIS | §3 Algorithm A: thresholds 5→2, `y` from black neighbours only, blue–blue edges ignored, grey→blue. Tie-break is the §5 order (larger `y`, then smaller id). | MIS is our centralized Wan level-based construction, not Cheng [5], and not a message-level replay of Wan. rS-MIS (§4) is not implemented. Lemma 2 is assumed by the paper and only empirically checked here (6,000 UDGs plus hand cases in `test_wan_level_mis`). | **THEORETICAL GUARANTEE NOT CLAIMED FOR IMPLEMENTATION** as an unconditional theorem. Theorem 1 needs Lemma 2 on the MIS. Algorithm A itself matches the paper. |

---

## Discrepancies (no code changes)

1. **Wan pruning.** §VI.A includes a rule: a black node whose rank is higher than every neighbour, and whose neighbours are all black, becomes gray. `Wan.cpp` does not implement it. The `8·opt + 1` count is on type-1 plus type-2 nodes, which is what we return, so the upper bound still covers our set. The returned set is not always the paper’s post-pruning set.
2. **Wan tree.** Phase 1 cites Cidon–Mokryn. We build a deterministic BFS tree. The size argument uses any spanning tree; BFS qualifies. The selected set can differ from [5]’s tree.
3. **Li MIS vs Theorem 1.** Algorithm A matches. The `(4.8 + ln 5)·opt + 1.2` bound is conditional on Lemma 2. `LiSMIS.hpp` states that bound with no condition. The comment is stronger than the audit.
4. **Funke venue.** The checked PDF is the 4-page version. `Funke.hpp` also cites TOSN 2006. TOSN was not compared.
5. **Marathe venue.** Checked text is arXiv:math/9409226v1. `Marathe.hpp` cites *Networks* 1995, §4.4.2. The preprint uses those numbers; the journal PDF was not opened separately.
6. **Marathe.hpp comment.** It says connectivity is not checked inside the algorithm. `Marathe.cpp` throws if the BFS does not reach every vertex.
7. **Funke query accounting.** `Funke.cpp` runs `isConnected` inside `solve`, so those neighbourhood queries are counted in Funke’s algorithm stage. The other algorithms discover disconnection inside a BFS they need anyway.

Older notes under `docs/research_v2/` that still say `SOURCE_NOT_VERIFIED` are historical. This file and `docs/algorithms/` supersede them for source status.
