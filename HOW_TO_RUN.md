# How to run MCDS (GUI)

Hand-off instructions for running this project on another Windows PC.

---

## What this program is

**MCDS** (Minimum Connected Dominating Set on Implicit Unit Disk Graphs) is a research / demo tool that:

1. Generates or loads a set of points in the plane
2. Treats them as a **unit disk graph** (two points are “neighbors” if they are within distance 1) **without building the full graph**
3. Runs one of several MCDS heuristics (Marathe, Wan, Funke, Li)
4. Shows the selected backbone on a plot

The **GUI** (`python/gui.py`) is a desktop window (Tkinter + Matplotlib). It calls a compiled **C++** solver (`mcds.exe`) under the hood. You need both Python and a successful C++ build.

Window title: **MCDS on Implicit Unit Disk Graphs**

---

## What you need installed

| Tool | Notes |
| --- | --- |
| **Git** | To clone / get the repo |
| **Python 3.10+** | On Windows, install from [python.org](https://www.python.org/) and tick “Add python.exe to PATH”. Prefer the `py` launcher. |
| **Visual Studio 2022 Build Tools** | With “Desktop development with C++” (MSVC + CMake) |
| **Miniconda / Anaconda** | Used only to install CGAL for the C++ build |
| **Disk / RAM** | A few GB free; small demos are fine on a laptop |

You do **not** need a GPU.

---

## 1. Get the code

Open **PowerShell** and go to where you want the project:

```powershell
cd "$env:USERPROFILE\Desktop"
git clone <REPO_URL> MCDS
cd MCDS
```

If you received a zip instead of git:

```powershell
cd path\to\MCDS
```

All later commands assume your current directory is the **repo root** (the folder that contains `cpp/`, `python/`, and this file).

---

## 2. Install Python packages

```powershell
py -3 -m pip install -r python/requirements.txt
```

That installs Matplotlib and a few libraries used by plots / data tools. The GUI also needs **Tkinter**, which ships with the official Windows Python installer.

Check that Python can import the GUI stack:

```powershell
py -3 -c "import tkinter, matplotlib; print('ok')"
```

---

## 3. Install CGAL (via conda) and build the C++ solver

The GUI will not run algorithms until `mcds.exe` exists.

### 3a. Create the conda env with CGAL

```powershell
conda create -n mcds-cgal -c conda-forge cgal-cpp=6.1.2 libboost-headers=1.88
```

(Use those versions if a newer CGAL solve fails on Windows.)

### 3b. Configure and build (Release)

Adjust the CMake path if your Visual Studio / Build Tools install is elsewhere:

```powershell
$cmake = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"

& $cmake -S cpp -B cpp/build-msvc -DCMAKE_PREFIX_PATH="$env:USERPROFILE/miniconda3/envs/mcds-cgal/Library"
& $cmake --build cpp/build-msvc --config Release --parallel
```

If Miniconda is installed somewhere else, change `CMAKE_PREFIX_PATH` to that env’s `Library` folder.

### 3c. Confirm the executable

You should have something like:

```text
cpp\build-msvc\Release\mcds.exe
```

The GUI looks for `mcds` / `mcds.exe` in common build folders (`cpp/build-msvc/Release`, `cpp/build`, `build`, etc.).

---

## 4. Run the GUI

From the **repo root**:

```powershell
py -3 python/gui.py
```

A window should open. Leave that PowerShell window open while you use the app; closing it may kill the GUI.

---

## 5. Quick tour (in the GUI)

Typical flow:

1. Choose a **distribution** (or load an existing CSV)
2. Set **n** (number of points) and a **seed**
3. **Generate** points
4. Pick an **algorithm**
5. **Run** — the C++ solver runs; results appear on the plot
6. Optionally switch **color mode** (Final CDS vs Algorithm roles when available)
7. Save / export if you need a figure

Point CSVs use this format:

```csv
id,x,y
0,1.250000,4.700000
1,1.800000,4.320000
```

---

## Optional: CLI without the GUI

Generate points:

```powershell
py -3 python/generators.py --type perturbed_grid --n 200 --seed 42 --output datasets/e2e_grid_200.csv
```

Run the solver (path to `mcds.exe` may differ):

```powershell
.\cpp\build-msvc\Release\mcds.exe --input datasets/e2e_grid_200.csv --algorithm marathe --radius 1.0 --output results/e2e_grid_200.json --pretty
```

Plot:

```powershell
py -3 python/visualization.py --points datasets/e2e_grid_200.csv --result results/e2e_grid_200.json --save results/e2e_grid_200.png --no-show
```

---

## Troubleshooting

| Problem | What to try |
| --- | --- |
| `C++ mcds executable not found` | Finish step 3; confirm `mcds.exe` exists under `cpp/build-msvc/Release` |
| `cmake` not found | Install VS 2022 Build Tools with C++ / CMake, or set `$cmake` to the full path |
| CGAL / configure fails | Activate or recreate `mcds-cgal`; check `CMAKE_PREFIX_PATH` points at that env’s `Library` |
| `No module named matplotlib` / similar | Re-run `py -3 -m pip install -r python/requirements.txt` |
| Tkinter / GUI fails to start | Reinstall Python from python.org (include Tcl/Tk); avoid stripped embeddable builds |
| Wrong Python | Always use `py -3` from the repo root so the same interpreter has the packages |

---

## What you do *not* need for a GUI demo

- Running the full experiment study (`run_study.py`) — that is for batch research runs
- Committing results — `datasets/` and `results/` are local / gitignored
- Linux / Mac setup — this guide is for **Windows**, matching the verified build path

More detail (algorithms, studies, methodology) lives in `README.md` and `docs/`.
