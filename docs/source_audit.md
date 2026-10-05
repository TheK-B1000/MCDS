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
| Wan–Alzoubi–Frieder | **YES** — INFOCOM 2002, 8 pages | **YES** (pruning rule added 2026-10-05; tree is BFS) |
| Funke–Kesselman–Meyer–Segal | **YES** — the 4-page paper with this title (Figure 1, Theorem 2.1). The TOSN 2006 journal PDF was not in the local set and was not checked. | **YES** (against that 4-page PDF) |
| Li et al. S-MIS | **YES** — WCMC 5(8):927–932, 2005, DOI 10.1002/wcm.356. This is the S-MIS paper, not a different Li paper. | **PARTIAL** |

---

## What “verified” means here

Each status is from reading that local PDF and the current C++ sources.
A paper guarantee is not assumed to transfer.

| Algorithm | What matches | What does not | Guarantee for our code |
| --- | --- | --- | --- |
| Marathe | Figure 2 (CDOM): BFS levels, `DS_i`, MIS on `S_i − DS_i`, tree parents | Root, BFS parent, and MIS pivot are fixed (smallest index / ascending id) instead of “arbitrary”. Those are legal instances of the paper’s arbitrary choices. | Theorem 4.9, factor 10, **applies** |
| Wan | §VI.A type-1 rank MIS and type-2 tree parents; leader by minimum id, which the paper allows | Spanning tree is BFS, not Cidon–Mokryn [5]. The §VI.A black→gray pruning rule is implemented (applied to the type-1 ∪ type-2 set; order-independent, tested against an asynchronous reference). Message complexity is not implemented. | The counting bound `\|type-1 ∪ type-2\| ≤ 8·opt + 1` **applies**, and pruning only removes vertices. Theorem 10’s complexity clauses do **not**. A strict ratio of 8 on every finite instance is **not** claimed: the paper’s displayed inequality is `8·opt + 1`. |
| Funke | Figure 1 colour rounds: min-id red wins, parent becomes grey, new blacks recruit blues, new blues recruit reds. `S` = black ∪ grey | No D2-colouring / slotting. If several blues recruit one white node, the parent is the minimum id (Figure 1 does not specify which). Initial red node is the minimum id. | Theorem 2.1 size bound `\|S\| ≤ 6.91·\|OPT\| + 16.58` **applies**. Time and message bounds do **not**. |
| Li S-MIS | §3 Algorithm A: thresholds 5→2, `y` from black neighbours only, blue–blue edges ignored, grey→blue. Tie-break is the §5 order (larger `y`, then smaller id). | MIS is our centralized Wan level-based construction, not Cheng [5], and not a message-level replay of Wan. rS-MIS (§4) is not implemented. Lemma 2 is assumed by the paper and only empirically checked here (6,000 UDGs plus hand cases in `test_wan_level_mis`). | **THEORETICAL GUARANTEE NOT CLAIMED FOR IMPLEMENTATION** as an unconditional theorem. Theorem 1 needs Lemma 2 on the MIS. Algorithm A itself matches the paper. |

---

## Discrepancies (no code changes)

1. **Wan pruning — resolved.** The §VI.A rule (a black node whose rank is higher than every neighbour, and whose neighbours are all black, becomes gray) is now implemented in `Wan.cpp` inside the timed `solve()`. On the pre-upgrade pilot graphs (n ≤ 1000) it removed 0 vertices on perturbed-grid and cluster-bridge, mean 0.19 (max 1) on uniform, 0.93 (max 5) on clustered, 0.96 (max 4) on corridor.
2. **Wan tree.** Phase 1 cites Cidon–Mokryn. We build a deterministic BFS tree. The size argument uses any spanning tree; BFS qualifies. The selected set can differ from [5]’s tree.
3. **Li MIS vs Theorem 1.** Algorithm A matches. The `(4.8 + ln 5)·opt + 1.2` bound is conditional on Lemma 2. `LiSMIS.hpp` now states it as conditional and labels the implementation “S-MIS connector phase with centralized Wan-level MIS”. A proof that our MIS satisfies Lemma 2 is proposed in `algorithms/li_smis.md` and awaits a decision before any claim is made.
4. **Funke venue — resolved by citation.** The checked PDF is the 4-page version, and it is now the only implementation source cited (`Funke.hpp`, reports). TOSN 2006 was not compared and must not be cited as the implementation source unless audited.
5. **Marathe venue.** Checked text is arXiv:math/9409226v1. `Marathe.hpp` cites *Networks* 1995, §4.4.2. The preprint uses those numbers; the journal PDF was not opened separately.
6. **Marathe.hpp comment.** It says connectivity is not checked inside the algorithm. `Marathe.cpp` throws if the BFS does not reach every vertex.
7. **Funke query accounting — resolved.** The private `isConnected` call was removed from the timed `solve()`; connectivity is checked once, untimed, for every algorithm. Output identical on connected inputs; algorithm-stage queries drop by exactly `n`.

The design notes `docs/{marathe,wan,funke,li}.md` predate this audit and are kept for history only. This file and `docs/algorithms/` are authoritative for source status.
