# Real-world data in the MCDS experiment framework

This project supports two **separate** experiment categories.

## Controlled synthetic experiments

Generators in `python/generators.py`:

| Distribution | Role |
| --- | --- |
| `uniform` | baseline |
| `clustered` | deliberate spatial clusters under controlled parameters |
| `perturbed_grid` | regular, reliably connected |
| `corridor` | elongated near-worst-case CDS |
| `cluster_bridge` | clusters joined by thin bridges |

**Clustered synthetic data** means we *deliberately generate* spatial clusters
with knobs such as `clusters`, `spread`, and `density`. It is not a stand-in
for geography.

## Real-world experiments

Imported geographic or planar point sets. We do **not** force real data into
synthetic clusters. After conversion to the canonical CSV, algorithms cannot
tell the source apart.

```text
external file  →  import_dataset.py  →  canonical id,x,y CSV
                                        (+ .meta.json + SHA-256)
                                              ↓
                                    experiment runner / GUI / solver
```

---

## Canonical format

```csv
id,x,y
0,125.200000,880.400000
```

Coordinates must be **planar**. Latitude/longitude must be projected to meters
before any UDG distance is computed. Treating degrees as meters is an error.

---

## Import CLI

```bash
# Planar CSV
py -3 python/import_dataset.py \
    --type csv \
    --input data/raw/points.csv \
    --x-column x \
    --y-column y \
    --coordinates planar \
    --output datasets/real/points.csv

# Geographic CSV (lon/lat → local AEQD meters, or --target-crs)
py -3 python/import_dataset.py \
    --type csv \
    --input data/raw/locations.csv \
    --x-column longitude \
    --y-column latitude \
    --coordinates geographic \
    --bbox -81.8,30.2,-81.5,30.5 \
    --output datasets/real/locations_projected.csv

# Building footprints (GeoJSON Point / Polygon / MultiPolygon)
py -3 python/import_dataset.py \
    --type geojson \
    --input data/raw/buildings.geojson \
    --feature-point centroid \
    --coordinates geographic \
    --limit 1000000 \
    --sample random \
    --seed 42 \
    --output datasets/real/buildings_1m.csv
```

### Sampling notes

- `--sample first --limit N` keeps the first N accepted features. File order
  can introduce **spatial bias**.
- `--sample random --seed S --limit N` uses a deterministic reservoir sample.
- For nested scaling sizes (100k ⊂ 250k ⊂ 500k ⊂ 1M), prefer
  `prepare_real_dataset.py --nested-prefixes` on one imported source so every
  algorithm sees the same SHA for each size.

### Projection

- Default for small/local regions: **local azimuthal equidistant (AEQD)**
  centered on the bbox or data centroid, units meters (`pyproj`).
- Spans larger than about 5° require an explicit `--target-crs` (e.g. a UTM
  zone or other projected CRS).

Metadata records `input_crs`, `output_crs`, `projection_method`, and `units`.

---

## Prepare utilities (explicit only)

```bash
# Largest connected component — NEVER done silently inside the solver
py -3 python/prepare_real_dataset.py \
    --input datasets/real/florida.csv \
    --radius 100 \
    --largest-connected-component \
    --output datasets/real/florida_lcc.csv

# Nested deterministic prefixes from one shuffled order
py -3 python/prepare_real_dataset.py \
    --input datasets/real/florida.csv \
    --nested-prefixes 100000,250000,500000,1000000 \
    --seed 42 \
    --basename florida \
    --output-dir datasets/real

# Simple rectangular tiles
py -3 python/prepare_real_dataset.py \
    --input datasets/real/florida.csv \
    --tiles 2,2 \
    --basename region \
    --output-dir datasets/real/tiles
```

Disconnected real inputs are recorded with `status = input_disconnected` and
component diagnostics in `datasets.csv` / `failures.csv`; algorithms are not
run on them. Real data is never resampled, and the original CSV is not
modified. If a largest-connected-component rule is wanted, apply
`prepare_real_dataset.py --largest-connected-component` explicitly and declare
it in the protocol.

---

## Experiment configs

Both modes use the one runner, `python/run_study.py`
(see [experimental_methodology.md](experimental_methodology.md)).

Synthetic mode:

```json
{
  "study_id": "clustered_demo",
  "study_seed": 1,
  "synthetic": {"geometries": ["clustered"], "sizes": [1000], "densities": [8.0],
                "radius": 1.0, "replicates": 8}
}
```

Real-data mode — `external` replaces `synthetic`; **no** synthetic generation
occurs. Every dataset must declare its own `radii` (a list = radius sweep) and
`units`:

```json
{
  "study_id": "florida_buildings",
  "study_seed": 1,
  "algorithms": ["marathe", "wan", "funke", "li"],
  "external": {"datasets": [
    {"name": "florida_buildings_100k", "path": "datasets/real/florida_buildings_100k.csv",
     "radii": [50.0, 100.0, 200.0], "units": "meters",
     "source_path": "data/raw/florida_buildings.geojson"}
  ]}
}
```

Each (dataset, radius) is one graph; all algorithms run on it in one process
and share its `dataset_sha256` and points fingerprint. The import sidecar's
projection metadata and the raw source's `input_sha256` are copied into
`datasets.csv`.

Do **not** interpret a real radius in meters as comparable to synthetic
`radius = 1.0`.

Template study (paths are placeholders; do not launch until CSVs exist):

```bash
py -3 python/run_study.py plan --config experiments/real_world_scaling.json
```

---

## GUI

Import to canonical CSV first, then use **Load CSV…**. The GUI does not read
GeoJSON directly.

---

## Scientific rules

- Do not silently alter real datasets, change radius, drop components, or sample.
- Do not use lat/lon as Euclidean meters.
- Do not change MCDS algorithm semantics.
- Do not change synthetic `clustered` generator semantics.
- Do not compare algorithms on different samples of the “same” real source.
