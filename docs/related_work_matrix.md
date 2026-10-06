# Related-work matrix (living draft)

**Purpose.** Turn “looks novel from a web sweep” into a defensible literature-gap
argument. This is **not** a finished systematic review of IEEE Xplore / ACM DL /
Scopus / Web of Science. Rows are filled from papers we have actually inspected
(or whose abstracts we have seen). A `?` is no longer a legal cell value. Use `NR` or `NO_FULL_TEXT`. The audit is `docs/literature_search_log.xlsx`. Finish the database pass before any “to our knowledge, first …” claim.

**Working novelty statement (safe).**

> We conduct a controlled empirical study of classical approximation heuristics
> for MCDS on *implicit* Unit Disk Graphs, evaluating solution quality and
> computational cost under matched spatial instances across graph size, density,
> and geometric structure.

**Stronger claim (only after a formal database search confirms the gap).**

> To our knowledge, this is the first unified empirical comparison of Marathe
> CDOM, Wan–Alzoubi–Frieder, Funke et al., and S-MIS under a common implicit
> geometric infrastructure with instrumented neighbor-query cost.

Do **not** put “first” in a paper yet.

---

## Column legend

| Column | Meaning |
| --- | --- |
| Domain | `UDG-WSN` / `UDG-theory` / `general-MCDS` / `geom-alg` / `survey` |
| Algos | Algorithms compared or proposed |
| Marathe/Wan/Funke/S-MIS | Does it head-to-head those four? |
| UDG | Unit-disk / wireless geometric model? |
| Input | Points / adjacency / mixed |
| Implicit | Retains geometry; adjacency on demand? |
| Shared spatial backend | One range-query API for all algos? |
| Geometries | Beyond uniform-in-rectangle? |
| Density / radius controlled | Yes/no |
| Paired instances | Same graph run under every algo? |
| Reps | Reported repetitions |
| CDS size | Primary quality metric |
| Runtime | Wall-clock or asymptotic only |
| Memory | Peak memory reported |
| Query work | Neighbor / range-query counters |
| Exact OPT | Compared to OPT on (some) instances |
| Real data | Non-synthetic instances |
| Notes | Scope / what to steal |

Boolean cells: `Y` = yes in the full text, `N` = no, `P` = partial, `NR` = full text in hand and the metric is not reported, `NO_FULL_TEXT` = PDF not in the project library so the cell is not filled. Do not guess `N` from an abstract.

---

## Matrix

| ID | Paper | Year | Domain | Algos | M/W/F/S | UDG | Input | Implicit | Shared backend | Geometries | Dens/r | Paired | Reps | Size | Runtime | Mem | Queries | OPT | Real | Steal / notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01 | Marathe et al., *Networks* (arXiv math/9409226) | 1995 | UDG-theory | CDOM (+ other UDG heuristics) | M only | Y | Graph / geometric | N | N | N | N | N | N | theory | asymp | NR | NR | N | N | Local PDF, 19 pp: no simulation section. Source of CDOM (≤10). |
| 02 | Wan, Alzoubi, Frieder, INFOCOM | 2002 | UDG-theory | New distributed CDS vs Das/Wu/Stojmenovic | W only | Y | Wireless UDG | N | N | N | N | N | N | theory | asymp/msg | NR | NR | N | N | Local PDF, 8 pp: no simulation section. Message complexity is asymptotic. |
| 03 | Funke, Kesselman, Meyer, Segal, WiMob / TOSN | 2005/06 | UDG-theory | Improved MIS→CDS analysis + simple distributed algo | F only | Y | UDG | N | N | N | N | N | N | theory | asymp | NR | NR | N | N | Local 4-page PDF: no simulation section. Source of ~6.91 bound. |
| 04 | Li, Thai, Wang, Yi, Wan, Du, *WCMC* (S-MIS) | 2005 | UDG-theory | S-MIS vs rS-MIS only | S only | Y | random hosts in a square | N | N | uniform 1000×1000 | Y (N and R) | NR | 100 | blue/black ratio | NR | NR | NR | N | N | Local PDF §4. N=20–100, R in [200,800], connected only, averages. Not a four-algorithm study. |
| 05 | Blum, Ding, Thaeler, Cheng, CDS survey (handbook / CompNet) | 2004–12 | survey | Taxonomy of CDS methods | N | Y | mixed | N | N | N | N | N | N | multi | multi | N | N | N | N | Metric taxonomy: size, locality, time/msg, stability. |
| 06 | Yuanyuan et al. / related energy CDS surveys | 2006–10 | survey | Energy-aware CDS | N | Y | WSN | N | N | N | N | N | N | size/energy | msg | N | N | N | N | Cite for application motivation; out of v1 scope. |
| 07 | Huaping Li et al., CDS comparison platform | NO_FULL_TEXT | UDG-WSN | Alzoubi, Wu–Li, R-value | N | Y | random graphs | N | N | uniform | P | Y | batch | size | NO_FULL_TEXT | N | N | N | N | Slide excerpt only. Runtime cell not filled. |
| 08 | Jallu, Prasad, Das, *J. Parallel Distrib. Comput.* | 2017 | UDG-WSN | Proposed distributed CDS vs earlier | N | Y | points in R² (abstract) | P | N | NO_FULL_TEXT | Y | P | sim | size | time/msg | N | N | N | N | Full PDF not in library. Geometry cell not filled from the abstract. |
| 09 | DCMCDS (two-hop info), *ComNet* | 2017 | UDG-WSN | Proposed vs existing CDS | N | Y | WSN/UDG | N | N | uniform | Y | P | sim | size | construction cost | N | N | N | N | Size + construction cost methodology. |
| 10 | Sun, Yang, Ma, *Sensors* | 2019 | UDG-WSN | IC-MIS, IK-ST, ML-ST / Misra variants | N | Y | random UDG | N | N | **uniform rectangle** | Y (n,r) | P | **1000** | MIS/Steiner/CDS | N/weak | N | N | N | N | Closest empirical cousin. Steal replication spirit, not 1000 blindly. Reported n mostly ≤150. |
| 11 | Bouamama, Blum, ACO-RVNS, *Appl. Soft Comput.* | 2019 | general-MCDS | ACO-RVNS + exact CP | N | N/P | general graphs | N | N | benchmarks | N | Y | multi | size | yes | N | N | **Y** (≤~200) | biological net | Exact-small + real instances + hard benchmarks. Citation context only for v1. |
| 12 | Li et al., NuCDS, IJCAI | 2020 | general-MCDS | NuCDS vs MSLS, ACO-RVNS, RNS-TS | N | N | classic + massive (SNAP/DIMACS/NDR) | N | N | N | N | Y | 10 | size | cutoff | N | N | N | massive real graphs | Modern computational benchmarking practice. Out of v1 algo set. |
| 13 | Wu, Lü, Glover, FVW, *INFORMS JOC* | 2021/22 | general-MCDS | FVW vs SOTA | N | N | 112 public + 15 sparse | N | N | N | N | Y | multi | size | yes | N | N | N | N | Public benches + component ablation. Steal experiment hygiene. |
| 14 | FastCDS / related JAIR local search | 2021+ | general-MCDS | FastCDS vs NuCDS etc. | N | N | classic+massive | N | N | N | N | Y | 10 | size | cutoff | N | N | N | massive | Cite as continuing general-graph MCDS race. |
| 15 | Wang, Liang, Li, quality VB / diameter | 2024 | UDG-WSN | Proposed vs prior VB | N | Y | wireless | N | N | NO_FULL_TEXT | Y | P | sim | size + diameter (abstract) | NO_FULL_TEXT | N | N | N | N | Diameter idea kept as a steal candidate. Geometry and runtime not filled without the PDF. |
| 16 | Lam & Huynh, sleeping-model MCDS | 2024 | UDG-theory | New model + ≈8.399 | N | Y | WSN model | N | N | N | N | N | N | theory | asymp | N | N | N | N | Shows UDG MCDS still active; different model. |
| 17 | Hassan et al., D-CDS-TE, *CMC* | 2026 | UDG-WSN | Proposed vs clustering CDS | N | Y | IoT/6G+Wi‑Fi | N | N | NO_FULL_TEXT | Y | P | sim | size vs theory | msg/time asymp | N | N | N | N | Publisher PDF was viewed on the open web but is not in `papers/`. Geometry cell not filled. |
| 18 | da Fonseca et al., geometric MDS (TCS / arXiv) | 2012+ | geom-alg | Geometric dominating-set approx | N | Y | **coordinates** | **Y** | N | connected UDG | N | N | N | size (DS) | O(n log n) | N | grid cells | N | N | Implicit/grid is established CG practice — cite, don’t claim invention. |
| 19 | Location-aware local CDS (Kuhn/Wattenhofer/… line) | 2005–08 | UDG-theory | Local CDS via tiling | N | Y | coordinates | P | N | N | N | N | N | theory | local | N | N | N | N | Geometry used for locality, not our systems benchmark. |
| 20 | SWAT 2026 disk-graph geometry (implicit edges) | 2026 | geom-alg | Disk-graph algorithms | N | disk | geometric | **Y** | N | N | N | N | N | theory | asymp | N | on-demand | N | N | Explicit statement: Θ(n²) edges ⇒ retain geometry. Supports our design rhetoric. |
| 21 | Misra & Mandal, collaborative cover CDS | 2009 | UDG-WSN | Proposed vs prior | N | Y | WSN | N | N | uniform | Y | P | sim | size | NO_FULL_TEXT | N | N | N | N | Runtime not filled. PDF not in library. |
| 22 | Alzoubi / Cheng localized CDS | 2002–06 | UDG-theory | Localized MIS+connect | N | Y | UDG | N | N | N | N | N | N | theory | msg/time | N | N | N | N | Historical distributed lineage adjacent to Wan. |
| 23 | WASET SLS heuristic UDG MCDS | NO_FULL_TEXT | UDG-WSN | SLS vs NH, CCH | N | Y | random UDG (adj. matrix) | N | N | uniform | Y (n,r) | P | sim | size | N | N | N | N | Year not filled. Open-web text was seen earlier; PDF is not in `papers/`. |
| 24 | **This project (MCDS)** | 2026 | UDG-emp | Marathe, Wan, Funke, S-MIS | **Y** | Y | **points** | **Y** | **Y** | **5 synthetic + real** | **Y** | **Y** | pilot→CI | size | staged ms | peak | **Y** | exact_small | planned | Gap candidate: combination, not ingredients. |

---

## Gap summary (what nobody in this draft matrix does all at once)

Checked across the rows above, **no inspected paper simultaneously** has:

1. Head-to-head **Marathe + Wan + Funke + S-MIS**
2. **Matched** point instances for all algorithms
3. **Implicit** adjacency through one spatial-query backend
4. Multiple deliberate **spatial geometries** (not only uniform)
5. Controlled **density / n**
6. **Runtime + CDS size + memory**
7. **Geometric query workload** counters
8. **Exact OPT** on small UDGs
9. **Real spatial** point sets

Individual cells appear elsewhere. The **bundle** is the candidate contribution.

---

## What to steal for v1 (and what not)

### Steal

| Idea | From | Action |
| --- | --- | --- |
| Exact OPT on small instances | ACO-RVNS 2019 | Keep `exact_small`; report \|D\|/OPT |
| Replication with CI discipline | Sun 2019 (spirit) | Pilot variance; target ~30 seeds/cell if runtime allows |
| Paired differences | experimental algorithmics | Analyze Wi−Mi etc., not unrelated means |
| CDS diameter (offline) | Wang et al. 2024 | Secondary metric; never in `algorithm_ms` |
| Raw one-row-per-run evidence | NuCDS / FVW | Preserve JSON/CSV schema |
| Diverse geometries as factor | contrast to Sun’s uniform square | Headline RQ: does ranking depend on geometry? |
| Implicit geometry rhetoric | da Fonseca; SWAT 2026 | Cite as standard CG practice |

### Do **not** add to v1

NuCDS, FVW, ACO-RVNS, DCMCDS, Hassan 2026, energy/mobility/6G stacks — cite in related work only. They change the research question and force fairness / representation issues.

---

## Formal search checklist (before any “first” claim)

Search each venue/database with (adapt Boolean as needed):

```
("connected dominating set" OR MCDS OR "virtual backbone")
AND ("unit disk" OR UDG OR "unit-disk")
AND (Marathe OR Wan OR Funke OR "S-MIS" OR "maximal independent")
AND (experiment OR simulation OR empirical OR benchmark)
```

Also run separate queries for:

- `implicit` / `geometric representation` / `range query` / `spatial hash`
- `CDS diameter` / `backbone diameter`
- algorithm names pairwise: `Marathe AND Wan`, `Funke AND Marathe`, etc.

Record in a spreadsheet: query, date, hits reviewed, relevant IDs, rejection reason.

Venues to cover: **IEEE Xplore, ACM DL, Scopus or WoS, SpringerLink, Elsevier, Google Scholar** (last for recall only).

---

## Status

| Item | Status |
| --- | --- |
| Living matrix (≥20 rows) | Draft present |
| PDF-level fill for every former `?` | Done for PDFs in `papers/primary/`. Remaining open cells are `NO_FULL_TEXT`, not guesses. |
| Search log | `docs/literature_search_log.xlsx`. Open-web queries from 2026-10-05 are logged. IEEE Xplore, ACM DL, Scopus/WoS, Springer, and Elsevier rows are `NOT_RUN`. |
| Safe novelty paragraph locked for paper | Yes (see top). The stronger “across our documented searches” sentence is **not** earned until the `NOT_RUN` databases are executed. |
| “First …” claim | **Blocked** |
| Related-work expansion | **Stop**, unless a later database search hits a paper that runs Marathe, Wan, Funke, and S-MIS on matched implicit UDGs. |

Open-web query 3 screened Guibas, Milosavljevic, and Motskin (CCCG 2010), which maintain an approximate CDS with range queries. Exclusion code: `NO_EMPIRICAL_EVAL`. It does not close the empirical gap and is not added as a v1 baseline.
