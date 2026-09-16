"""Tkinter GUI for generating points, running mcds, and visualizing results.

Orchestration only: generation uses ``generators.py``, solving uses the compiled
C++ executable, plotting uses ``visualization.py``.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import traceback
from pathlib import Path
import sys
import threading

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from generators import GENERATOR_TYPES, read_csv  # noqa: E402
from gui_support import (  # noqa: E402
    ALGORITHM_IDS_BY_LABEL,
    ALGORITHM_LABELS,
    ALGORITHMS,
    DISTRIBUTION_FIELDS,
    build_solver_command,
    dataset_paths,
    find_mcds_executable,
    find_repo_root,
    friendly_solver_error,
    map_generation_kwargs,
    run_solver,
    write_dataset_with_metadata,
)
from visualization import (  # noqa: E402
    VisualizationError,
    create_figure,
    load_metadata_sidecar,
    prepare_plot_data,
)


# GUI chrome colors. Plots use create_figure(dark=...).
_DARK = {
    "bg": "#1e1e1e",
    "panel": "#252526",
    "field": "#2d2d30",
    "fg": "#e6edf3",
    "muted": "#9da7b3",
    "border": "#3c4048",
    "accent": "#3a3d41",
    "select_bg": "#264f78",
    "select_fg": "#ffffff",
    "disabled": "#6e7681",
}
_LIGHT = {
    "bg": "#f3f3f3",
    "panel": "#ffffff",
    "field": "#ffffff",
    "fg": "#1f2933",
    "muted": "#4a5560",
    "border": "#cbd2d9",
    "accent": "#e8e8e8",
    "select_bg": "#cce4f7",
    "select_fg": "#1f2933",
    "disabled": "#9aa5b1",
}


class McdsGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MCDS on Implicit Unit Disk Graphs")
        self.geometry("1180x740")
        self.minsize(960, 640)

        self.repo_root = find_repo_root()
        self.work_dir = self.repo_root / "results" / "gui_session"
        self.csv_path, self.meta_path, self.result_path = dataset_paths(self.work_dir, "session")

        self._solver_thread: threading.Thread | None = None
        self._busy = False
        self._figure: Figure | None = None
        self._canvas: FigureCanvasTkAgg | None = None
        self._toolbar: NavigationToolbar2Tk | None = None
        self._style = ttk.Style(self)

        self._build_vars()
        self._apply_theme()
        self._build_layout()
        self._on_distribution_changed()
        self._set_status("Ready")

    def _build_vars(self) -> None:
        self.var_distribution = tk.StringVar(value="cluster_bridge")
        self.var_algorithm = tk.StringVar(value=ALGORITHM_LABELS["marathe"])
        self.var_n = tk.IntVar(value=300)
        self.var_seed = tk.IntVar(value=7)
        self.var_radius = tk.DoubleVar(value=1.0)
        self.var_density = tk.DoubleVar(value=2.0)
        self.var_width = tk.StringVar(value="")
        self.var_height = tk.StringVar(value="")
        self.var_clusters = tk.IntVar(value=3)
        self.var_spread = tk.DoubleVar(value=0.5)
        self.var_spacing = tk.StringVar(value="")
        self.var_jitter = tk.DoubleVar(value=0.2)
        self.var_corridor_width = tk.DoubleVar(value=2.0)
        self.var_bridge_fraction = tk.DoubleVar(value=0.15)
        self.var_bridge_width = tk.DoubleVar(value=0.5)
        self.var_show_edges = tk.BooleanVar(value=True)
        self.var_dark_mode = tk.BooleanVar(value=True)
        self.var_status = tk.StringVar(value="")

        self.metric_vars = {
            "n": tk.StringVar(value="—"),
            "distribution": tk.StringVar(value="—"),
            "seed": tk.StringVar(value="—"),
            "connected": tk.StringVar(value="—"),
            "components": tk.StringVar(value="—"),
            "cds_size": tk.StringVar(value="—"),
            "cds_ratio": tk.StringVar(value="—"),
            "algorithm_ms": tk.StringVar(value="—"),
            "neighbor_queries": tk.StringVar(value="—"),
            "candidates": tk.StringVar(value="—"),
            "dominating": tk.StringVar(value="—"),
            "connected_cds": tk.StringVar(value="—"),
        }

    def _build_layout(self) -> None:
        root = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        root.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left = ttk.Frame(root, width=340)
        right = ttk.Frame(root)
        root.add(left, weight=0)
        root.add(right, weight=1)

        controls = ttk.LabelFrame(left, text="Controls", padding=8)
        controls.pack(fill=tk.X)

        def row(label: str, widget: tk.Widget, r: int) -> None:
            ttk.Label(controls, text=label).grid(row=r, column=0, sticky="w", pady=2)
            widget.grid(row=r, column=1, sticky="ew", pady=2)

        controls.columnconfigure(1, weight=1)
        self.cmb_distribution = ttk.Combobox(
            controls, textvariable=self.var_distribution, values=list(GENERATOR_TYPES), state="readonly"
        )
        self.cmb_distribution.bind("<<ComboboxSelected>>", lambda _e: self._on_distribution_changed())
        row("Distribution", self.cmb_distribution, 0)
        row(
            "Algorithm",
            ttk.Combobox(
                controls,
                textvariable=self.var_algorithm,
                values=[ALGORITHM_LABELS[a] for a in ALGORITHMS],
                state="readonly",
            ),
            1,
        )
        row("Point count", ttk.Entry(controls, textvariable=self.var_n), 2)
        row("Seed", ttk.Entry(controls, textvariable=self.var_seed), 3)
        row("Radius", ttk.Entry(controls, textvariable=self.var_radius), 4)
        row("Density", ttk.Entry(controls, textvariable=self.var_density), 5)

        self.ent_width = ttk.Entry(controls, textvariable=self.var_width)
        self.ent_height = ttk.Entry(controls, textvariable=self.var_height)
        self.ent_clusters = ttk.Entry(controls, textvariable=self.var_clusters)
        self.ent_spread = ttk.Entry(controls, textvariable=self.var_spread)
        self.ent_spacing = ttk.Entry(controls, textvariable=self.var_spacing)
        self.ent_jitter = ttk.Entry(controls, textvariable=self.var_jitter)
        self.ent_corridor = ttk.Entry(controls, textvariable=self.var_corridor_width)
        self.ent_bridge_frac = ttk.Entry(controls, textvariable=self.var_bridge_fraction)
        self.ent_bridge_width = ttk.Entry(controls, textvariable=self.var_bridge_width)

        row("Width", self.ent_width, 6)
        row("Height", self.ent_height, 7)
        row("Clusters", self.ent_clusters, 8)
        row("Spread", self.ent_spread, 9)
        row("Spacing", self.ent_spacing, 10)
        row("Jitter", self.ent_jitter, 11)
        row("Corridor width", self.ent_corridor, 12)
        row("Bridge fraction", self.ent_bridge_frac, 13)
        row("Bridge width", self.ent_bridge_width, 14)
        ttk.Checkbutton(
            controls,
            text="Show CDS edges",
            variable=self.var_show_edges,
            command=self._on_show_edges_toggled,
        ).grid(row=15, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(
            controls,
            text="Dark mode",
            variable=self.var_dark_mode,
            command=self._on_theme_toggled,
        ).grid(row=16, column=0, columnspan=2, sticky="w", pady=2)

        buttons = ttk.LabelFrame(left, text="Actions", padding=8)
        buttons.pack(fill=tk.X, pady=(8, 0))
        self.btn_generate = ttk.Button(buttons, text="Generate Points", command=self.on_generate)
        self.btn_load = ttk.Button(buttons, text="Load CSV…", command=self.on_load_csv)
        self.btn_connect = ttk.Button(buttons, text="Check Connectivity", command=self.on_check_connectivity)
        self.btn_run = ttk.Button(buttons, text="Run MCDS", command=self.on_run)
        self.btn_reset = ttk.Button(buttons, text="Reset", command=self.on_reset)
        self.btn_save_plot = ttk.Button(buttons, text="Save Plot…", command=self.on_save_plot)
        self.btn_export = ttk.Button(buttons, text="Export Result…", command=self.on_export_result)
        for btn in (
            self.btn_generate,
            self.btn_load,
            self.btn_connect,
            self.btn_run,
            self.btn_reset,
            self.btn_save_plot,
            self.btn_export,
        ):
            btn.pack(fill=tk.X, pady=2)

        metrics = ttk.LabelFrame(left, text="Results", padding=8)
        metrics.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        labels = [
            ("n", "n"),
            ("distribution", "distribution"),
            ("seed", "seed"),
            ("connected", "connected input?"),
            ("components", "component count"),
            ("cds_size", "CDS size"),
            ("cds_ratio", "CDS ratio"),
            ("algorithm_ms", "algorithm runtime"),
            ("neighbor_queries", "neighbor queries"),
            ("candidates", "candidates examined"),
            ("dominating", "dominating?"),
            ("connected_cds", "connected CDS?"),
        ]
        for i, (key, label) in enumerate(labels):
            ttk.Label(metrics, text=label).grid(row=i, column=0, sticky="w")
            ttk.Label(metrics, textvariable=self.metric_vars[key]).grid(row=i, column=1, sticky="e")
        metrics.columnconfigure(1, weight=1)

        self.plot_frame = ttk.Frame(right)
        self.plot_frame.pack(fill=tk.BOTH, expand=True)
        self.status_label = ttk.Label(self, textvariable=self.var_status, anchor="w")
        self.status_label.pack(fill=tk.X, padx=8, pady=(0, 6))

        self._init_empty_plot()

    def _palette(self) -> dict[str, str]:
        return _DARK if self.var_dark_mode.get() else _LIGHT

    def _apply_theme(self) -> None:
        colors = self._palette()
        # clam is the most reliably recolorable ttk theme on Windows.
        try:
            self._style.theme_use("clam")
        except tk.TclError:
            pass

        self.configure(bg=colors["bg"])
        self._style.configure(".", background=colors["panel"], foreground=colors["fg"], fieldbackground=colors["field"])
        self._style.configure("TFrame", background=colors["panel"])
        self._style.configure("TLabel", background=colors["panel"], foreground=colors["fg"])
        self._style.configure("TCheckbutton", background=colors["panel"], foreground=colors["fg"])
        self._style.configure(
            "TLabelframe",
            background=colors["panel"],
            foreground=colors["fg"],
            bordercolor=colors["border"],
        )
        self._style.configure("TLabelframe.Label", background=colors["panel"], foreground=colors["fg"])
        self._style.configure(
            "TButton",
            background=colors["accent"],
            foreground=colors["fg"],
            bordercolor=colors["border"],
            focusthickness=1,
            focuscolor=colors["border"],
        )
        self._style.map(
            "TButton",
            background=[("active", colors["select_bg"]), ("disabled", colors["field"])],
            foreground=[("disabled", colors["disabled"])],
        )
        self._style.configure(
            "TEntry",
            fieldbackground=colors["field"],
            foreground=colors["fg"],
            insertcolor=colors["fg"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
        )
        self._style.map(
            "TEntry",
            fieldbackground=[("disabled", colors["accent"])],
            foreground=[("disabled", colors["disabled"])],
        )
        self._style.configure(
            "TCombobox",
            fieldbackground=colors["field"],
            foreground=colors["fg"],
            background=colors["accent"],
            arrowcolor=colors["fg"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
        )
        self._style.map(
            "TCombobox",
            fieldbackground=[("readonly", colors["field"]), ("disabled", colors["accent"])],
            foreground=[("disabled", colors["disabled"])],
            selectbackground=[("readonly", colors["select_bg"])],
            selectforeground=[("readonly", colors["select_fg"])],
        )
        self._style.configure("TPanedwindow", background=colors["bg"])
        self._style.configure("Sash", sashthickness=6, background=colors["border"])
        # Combobox dropdown list (tk Listbox, not ttk).
        self.option_add("*TCombobox*Listbox.background", colors["field"])
        self.option_add("*TCombobox*Listbox.foreground", colors["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", colors["select_bg"])
        self.option_add("*TCombobox*Listbox.selectForeground", colors["select_fg"])

    def _style_toolbar(self) -> None:
        if self._toolbar is None:
            return
        colors = self._palette()
        try:
            self._toolbar.configure(background=colors["panel"])
        except tk.TclError:
            pass
        for child in self._toolbar.winfo_children():
            try:
                child.configure(background=colors["panel"])
            except tk.TclError:
                pass

    def _on_theme_toggled(self) -> None:
        self._apply_theme()
        self._style_toolbar()
        if self.csv_path.is_file() and self.result_path.is_file():
            try:
                self._refresh_plot()
            except VisualizationError:
                self._init_empty_plot()
        else:
            self._init_empty_plot()

    def _on_show_edges_toggled(self) -> None:
        if self.csv_path.is_file() and self.result_path.is_file():
            try:
                self._refresh_plot()
            except VisualizationError:
                pass

    def _field_widgets(self) -> dict[str, ttk.Entry]:
        return {
            "width": self.ent_width,
            "height": self.ent_height,
            "density": self.ent_width,  # density always enabled via separate entry; placeholder unused
            "clusters": self.ent_clusters,
            "spread": self.ent_spread,
            "spacing": self.ent_spacing,
            "jitter": self.ent_jitter,
            "corridor_width": self.ent_corridor,
            "bridge_fraction": self.ent_bridge_frac,
            "bridge_width": self.ent_bridge_width,
        }

    def _on_distribution_changed(self) -> None:
        dist = self.var_distribution.get()
        enabled = set(DISTRIBUTION_FIELDS.get(dist, ()))
        mapping = {
            "width": self.ent_width,
            "height": self.ent_height,
            "clusters": self.ent_clusters,
            "spread": self.ent_spread,
            "spacing": self.ent_spacing,
            "jitter": self.ent_jitter,
            "corridor_width": self.ent_corridor,
            "bridge_fraction": self.ent_bridge_frac,
            "bridge_width": self.ent_bridge_width,
        }
        for name, widget in mapping.items():
            state = "normal" if name in enabled else "disabled"
            widget.configure(state=state)

    def _optional_float(self, var: tk.StringVar) -> float | None:
        text = var.get().strip()
        if not text:
            return None
        return float(text)

    def _generation_kwargs(self) -> dict:
        return map_generation_kwargs(
            self.var_distribution.get(),
            int(self.var_n.get()),
            int(self.var_seed.get()),
            radius=float(self.var_radius.get()),
            density=float(self.var_density.get()),
            width=self._optional_float(self.var_width),
            height=self._optional_float(self.var_height),
            clusters=int(self.var_clusters.get()),
            spread=float(self.var_spread.get()),
            spacing=self._optional_float(self.var_spacing),
            jitter=float(self.var_jitter.get()),
            corridor_width=float(self.var_corridor_width.get()),
            bridge_fraction=float(self.var_bridge_fraction.get()),
            bridge_width=float(self.var_bridge_width.get()),
        )

    def _set_status(self, text: str) -> None:
        self.var_status.set(text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for btn in (self.btn_generate, self.btn_load, self.btn_connect, self.btn_run, self.btn_reset):
            btn.configure(state=state)
        # Keep export/save available unless fully resetting mid-run.
        if busy:
            self.btn_run.configure(state=tk.DISABLED)

    def _init_empty_plot(self) -> None:
        colors = self._palette()
        fig = Figure(figsize=(6, 5), dpi=100)
        fig.patch.set_facecolor(colors["bg"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(colors["panel"])
        ax.text(
            0.5,
            0.5,
            "Generate or load points to begin",
            ha="center",
            va="center",
            color=colors["muted"],
        )
        ax.set_axis_off()
        self._replace_figure(fig)

    def _replace_figure(self, fig: Figure) -> None:
        if self._toolbar is not None:
            self._toolbar.destroy()
            self._toolbar = None
        if self._canvas is not None:
            self._canvas.get_tk_widget().destroy()
            self._canvas = None
        if self._figure is not None:
            import matplotlib.pyplot as plt

            plt.close(self._figure)
        self._figure = fig
        self._canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._toolbar = NavigationToolbar2Tk(self._canvas, self.plot_frame, pack_toolbar=False)
        self._toolbar.update()
        self._toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self._style_toolbar()

    def _clear_metrics(self) -> None:
        for var in self.metric_vars.values():
            var.set("—")

    def _update_metrics_from_result(self, result: dict, meta: dict | None = None) -> None:
        meta = meta or {}
        self.metric_vars["n"].set(str(result.get("n", "—")))
        self.metric_vars["distribution"].set(str(meta.get("distribution", self.var_distribution.get())))
        seed = meta.get("effective_seed", meta.get("seed", self.var_seed.get()))
        self.metric_vars["seed"].set(str(seed))
        connected = result.get("connected_input")
        self.metric_vars["connected"].set("yes" if connected else "no" if connected is not None else "—")
        self.metric_vars["components"].set(str(result.get("component_count", "—")))
        self.metric_vars["cds_size"].set(str(result.get("cds_size", "—")))
        ratio = result.get("cds_ratio")
        self.metric_vars["cds_ratio"].set(f"{100.0 * float(ratio):.2f}%" if ratio is not None else "—")
        ms = result.get("algorithm_ms")
        self.metric_vars["algorithm_ms"].set(f"{float(ms):.3f} ms" if ms is not None else "—")
        self.metric_vars["neighbor_queries"].set(str(result.get("algorithm_neighbor_queries", "—")))
        self.metric_vars["candidates"].set(str(result.get("algorithm_candidates_examined", "—")))
        dom = result.get("valid_dominating")
        con = result.get("valid_connected")
        self.metric_vars["dominating"].set("yes" if dom else "no" if dom is not None else "—")
        self.metric_vars["connected_cds"].set("yes" if con else "no" if con is not None else "—")

    def _refresh_plot(self) -> None:
        if not self.csv_path.is_file() or not self.result_path.is_file():
            return
        data = prepare_plot_data(self.csv_path, self.result_path)
        fig = create_figure(
            data,
            show_cds_edges=self.var_show_edges.get(),
            dark=self.var_dark_mode.get(),
        )
        self._replace_figure(fig)

    def on_generate(self) -> None:
        try:
            kwargs = self._generation_kwargs()
            dist = kwargs.pop("type")
            n = int(kwargs.pop("n"))
            seed = int(kwargs.pop("seed"))
            write_dataset_with_metadata(
                self.csv_path,
                self.meta_path,
                distribution=dist,
                n=n,
                seed=seed,
                **kwargs,
            )
            self._clear_metrics()
            self.metric_vars["n"].set(str(n))
            self.metric_vars["distribution"].set(dist)
            self.metric_vars["seed"].set(str(seed))
            self._write_preview_stub(n)
            self._refresh_plot()
            self._set_status(f"Generated {n} points → {self.csv_path.name}")
        except Exception as exc:  # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            messagebox.showerror("Generation failed", str(exc))

    def _write_preview_stub(self, n: int) -> None:
        """Write an empty selection so loaded/generated points can be plotted."""
        import json

        stub = {
            "algorithm": "none",
            "n": n,
            "radius": float(self.var_radius.get()),
            "cds_size": 0,
            "cds_ratio": 0.0,
            "algorithm_ms": 0.0,
            "selected_ids": [],
        }
        self.result_path.write_text(json.dumps(stub, indent=2), encoding="utf-8")

    def on_load_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Load point CSV",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            import shutil

            src = Path(path)
            shutil.copy2(src, self.csv_path)

            # Prefer a sidecar next to the chosen file; clear a stale session meta otherwise.
            src_meta = src.with_name(src.stem + ".meta.json")
            if src_meta.is_file():
                shutil.copy2(src_meta, self.meta_path)
            elif self.meta_path.exists():
                self.meta_path.unlink()

            rows = read_csv(str(self.csv_path))
            if not rows:
                raise ValueError(f"point CSV contains no points: {src.name}")
            n = len(rows)

            meta = load_metadata_sidecar(self.csv_path)
            self._clear_metrics()
            self.metric_vars["n"].set(str(meta.get("n", n)))
            if meta.get("distribution"):
                self.metric_vars["distribution"].set(str(meta["distribution"]))
                dist = str(meta["distribution"])
                if dist in GENERATOR_TYPES:
                    self.var_distribution.set(dist)
                    self._on_distribution_changed()
            seed = meta.get("effective_seed", meta.get("seed"))
            if seed is not None:
                self.metric_vars["seed"].set(str(seed))
                try:
                    self.var_seed.set(int(seed))
                except (TypeError, ValueError):
                    pass

            self._write_preview_stub(n)
            self._refresh_plot()
            self._set_status(f"Loaded {src.name} ({n} points) — click Run MCDS")
        except Exception as exc:  # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            messagebox.showerror("Load failed", str(exc))

    def _start_solver(self, check_only: bool) -> None:
        if self._busy:
            return
        if not self.csv_path.is_file():
            messagebox.showwarning("No points", "Generate or load a point set first.")
            return
        try:
            exe = find_mcds_executable(self.repo_root)
        except FileNotFoundError as exc:
            messagebox.showerror("Missing executable", str(exc))
            return

        invocation = build_solver_command(
            exe,
            self.csv_path,
            self.result_path,
            algorithm=ALGORITHM_IDS_BY_LABEL.get(self.var_algorithm.get(), self.var_algorithm.get()),
            radius=float(self.var_radius.get()),
            check_connectivity_only=check_only,
        )
        self._set_busy(True)
        self._set_status("Running C++ solver…")

        def worker() -> None:
            outcome = run_solver(invocation)
            self.after(0, lambda: self._on_solver_finished(outcome, check_only=check_only))

        self._solver_thread = threading.Thread(target=worker, daemon=True)
        self._solver_thread.start()

    def _on_solver_finished(self, outcome, *, check_only: bool) -> None:
        self._set_busy(False)
        if outcome.stdout.strip():
            print(outcome.stdout, end="")
        if outcome.stderr.strip():
            print(outcome.stderr, end="", file=sys.stderr)

        if outcome.exit_code != 0 or outcome.error:
            messagebox.showerror("Solver failed", friendly_solver_error(outcome))
            self._set_status("Solver failed")
            if outcome.result:
                meta = {}
                if self.meta_path.is_file():
                    import json

                    meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
                self._update_metrics_from_result(outcome.result, meta)
            return

        assert outcome.result is not None
        meta = {}
        if self.meta_path.is_file():
            import json

            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        self._update_metrics_from_result(outcome.result, meta)
        if not check_only:
            try:
                self._refresh_plot()
            except VisualizationError as exc:
                messagebox.showerror("Visualization failed", str(exc))
        status = "Connectivity check done" if check_only else "MCDS run complete"
        if outcome.result.get("valid_dominating") is False or outcome.result.get("valid_connected") is False:
            status += " (validation failed)"
        self._set_status(status)

    def on_check_connectivity(self) -> None:
        self._start_solver(check_only=True)

    def on_run(self) -> None:
        self._start_solver(check_only=False)

    def on_reset(self) -> None:
        if self._busy:
            return
        for path in (self.csv_path, self.meta_path, self.result_path):
            if path.exists():
                path.unlink()
        self._clear_metrics()
        self._init_empty_plot()
        self._set_status("Reset")

    def on_save_plot(self) -> None:
        if self._figure is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._figure.savefig(path, dpi=140, bbox_inches="tight")
            self._set_status(f"Saved plot → {Path(path).name}")
        except Exception as exc:  # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            messagebox.showerror("Save failed", str(exc))

    def on_export_result(self) -> None:
        if not self.result_path.is_file():
            messagebox.showwarning("No result", "Run the solver first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            import shutil

            shutil.copy2(self.result_path, path)
            self._set_status(f"Exported result → {Path(path).name}")
        except Exception as exc:  # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            messagebox.showerror("Export failed", str(exc))


def main() -> int:
    app = McdsGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
