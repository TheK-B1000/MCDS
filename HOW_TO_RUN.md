# How to run MCDS

Hand-off instructions for Windows. Two different entry points:

```text
python/gui.py
    = interactive demonstration / visualization

python/run_study.py
    = controlled research experiments
```

**Do not use the GUI for the real research experiments.** Batch studies go through `run_study.py`.

Short explanation for a professor or teammate:

> We run experiments through `run_study.py`, not through the GUI. The experiment runner generates the locked point sets, runs all four algorithms on the same graphs under the same CGAL infrastructure, records runtime / quality / memory / query metrics, validates every CDS, and then produces the analysis and figures.

---

## What this program is

**MCDS** (Minimum Connected Dominating Set on Implicit Unit Disk Graphs):

1. Generates or loads points in the plane
2. Treats them as a **unit disk graph** (neighbors if distance ≤ 1) **without building the full graph**
3. Runs MCDS heuristics: Marathe, Wan, Funke, Li
4. Records metrics and/or shows the selected backbone

You need **Python 3.10+** and a **Release C++ build** (`mcds.exe` for the GUI; studies also need `mcds_bench.exe` / `mcds_bench_mem.exe` from the same build).

---

## Shared setup (GUI and experiments)

### What you need installed

| Tool | Notes |
| --- | --- |
| **Git** | Clone / checkout the frozen commit |
| **Python 3.10+** | From [python.org](https://www.python.org/); prefer the `py` launcher |
| **Visual Studio 2022 Build Tools** | “Desktop development with C++” (MSVC + CMake) |
| **Miniconda / Anaconda** | For CGAL headers used by the C++ build |
| **Disk / RAM** | Final study is long-running; use a quiet, plugged-in machine |

### Get the code

```powershell
cd "$env:USERPROFILE\Desktop"
git clone <REPO_URL> MCDS
cd MCDS
```

All commands below assume the **repo root** (folder with `cpp/`, `python/`, `experiments/`).

### Python packages

```powershell
py -3 -m pip install -r python/requirements.txt
py -3 python/check_env.py
```

### Build the C++ solvers (Release + CGAL)

```powershell
conda create -n mcds-cgal -c conda-forge cgal-cpp=6.1.2 libboost-headers=1.88

$cmake = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
& $cmake -S cpp -B cpp/build-msvc -DCMAKE_PREFIX_PATH="$env:USERPROFILE/miniconda3/envs/mcds-cgal/Library"
& $cmake --build cpp/build-msvc --config Release --parallel
```

Confirm at least:

```text
cpp\build-msvc\Release\mcds.exe
cpp\build-msvc\Release\mcds_bench.exe
cpp\build-msvc\Release\mcds_bench_mem.exe
```

Adjust `$cmake` / `CMAKE_PREFIX_PATH` if your VS or Miniconda paths differ.

---

# Part A — GUI / demo (not for the final study)

```powershell
py -3 python/gui.py
```

Typical flow: choose a distribution (or load CSV) → generate → pick algorithm → run → inspect the plot. Optional color modes: Final CDS vs Algorithm roles (when the result JSON includes roles).

Optional one-off CLI (still not the batch study):

```powershell
py -3 python/generators.py --type perturbed_grid --n 200 --seed 42 --output datasets/e2e_grid_200.csv
.\cpp\build-msvc\Release\mcds.exe --input datasets/e2e_grid_200.csv --algorithm marathe --radius 1.0 --output results/e2e_grid_200.json --pretty
py -3 python/visualization.py --points datasets/e2e_grid_200.csv --result results/e2e_grid_200.json --save results/e2e_grid_200.png --no-show
```

---

# Part B — Final research experiment (`run_study.py`)

Locked config: `experiments/final.json`

```text
50 experimental cells
× 20 independent graphs per cell
= 1,000 graphs
```

Each graph is shared across Marathe, Wan, Funke, and Li, with the frozen **CGAL** backend and balanced execution order. Protocol detail: `docs/final_experiment_protocol.md`.

### 1. Start from the frozen experiment state

From the repo root:

```powershell
git status --short
git rev-parse --short HEAD
git describe --tags --exact-match
```

For the final study you want a **clean tree** at commit `c61711c` with tag:

```text
v1.0-final-experiment
```

Checkout example (once the tag exists on the remote / locally):

```powershell
git fetch --tags
git checkout v1.0-final-experiment
git status --short
```

`final: true` refuses a dirty git tree or a non-Release build. Do not edit or rebuild the repo while timing is in progress.

### 2. Prepare the computer for timing

- Plug into **AC power**
- Use the Windows **High performance** power plan
- Close games, AI workloads, builds, downloads, Cursor agents, and other CPU/disk-heavy work
- Leave the machine alone for the duration of the run

### 3. Run the final experiment

```powershell
py -3 python/run_study.py run --config experiments/final.json
```

Outputs land under:

```text
results/studies/final/
```

### 4. Leave the machine alone while it runs

If the terminal stops visually updating, do **not** assume the study stopped. Check that the process is still alive and that completed files under `results/studies/final/` keep appearing.

If Windows or the process genuinely interrupts, rerun the **same command on the same tagged commit**. The runner resumes completed work; it does not casually overwrite a finished study with a different config.

### 5. Check integrity before interpreting results

Before talking about winners, confirm:

- No unexplained failures (`failures.csv`)
- Expected graphs / runs are present
- Validity passed (`validity.csv`)
- Fairness report has **no violations** (`fairness_report.json`)

Do **not** start changing code because a result looks surprising.

### 6. Analysis and figures

```powershell
py -3 python/run_study.py analyze --config experiments/final.json
py -3 python/run_study.py figures --config experiments/final.json
```

Optional combined path for smaller configs (smoke, etc.):

```powershell
py -3 python/run_study.py reproduce --config experiments/smoke.json
```

(`reproduce` = run + analyze + figures + manifest; still resumable.)

### 7. Only after fairness and integrity pass — interpret

Main questions:

```text
Which algorithms always return valid CDSs?
Which produce the smallest CDSs?
Which are fastest?
How does performance scale with n?
How do density and geometry affect them?
What memory / neighbour-query work do they require?
```

---

## Smaller studies (practice / smoke)

Before burning a machine on `final.json`, you can exercise the pipeline:

```powershell
py -3 python/run_study.py plan      --config experiments/smoke.json
py -3 python/run_study.py reproduce --config experiments/smoke.json
```

Other configs live in `experiments/` (`pilot`, `precision_pilot`, …). See `README.md`.

---

## Troubleshooting

| Problem | What to try |
| --- | --- |
| `C++ mcds executable not found` | Finish the Release build; confirm `mcds.exe` under `cpp/build-msvc/Release` |
| Study cannot find `mcds_bench` | Same build directory; rebuild Release |
| Dirty tree / final refused | `git status`; checkout the tagged commit; do not edit during the run |
| Environment / machine change on resume | Same machine + same tagged commit; or start a new `study_id` / copy finished results |
| `No module named matplotlib` | `py -3 -m pip install -r python/requirements.txt` |
| CGAL configure fails | Recreate `mcds-cgal`; fix `CMAKE_PREFIX_PATH` |

---

## Where things are saved

| Path | Purpose |
| --- | --- |
| `results/studies/<study_id>/` | Study outputs (gitignored) |
| `config.json`, `environment.json` | Frozen config + machine snapshot |
| `raw_runs.csv`, `datasets.csv`, … | Tables rebuilt from per-graph JSON |
| `fairness_report.json` | Automatic fairness checks |
| `figures/` | Plots after `figures` / `reproduce` |

Studies are local filesystem artifacts, not a shared cloud store. One study folder ↔ one config ↔ one machine unless you explicitly allow an environment change or start a new `study_id`.

More detail: `README.md`, `docs/experimental_methodology.md`, `docs/final_experiment_protocol.md`.
