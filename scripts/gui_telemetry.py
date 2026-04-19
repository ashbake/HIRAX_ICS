"""
thermal_gui.py  —  Tkinter GUI for continuous thermal data collection
Wraps cThermal with a live-updating plot, latest temperature readout,
filename display, and a Start / Stop button.

Usage:
    python thermal_gui.py [--interval 0.5]

Dependencies (beyond stdlib):
    matplotlib, tkinter (usually bundled with Python)
    cThermal  (your existing utility, must be importable)
"""

import sys
import time
import threading
import argparse
from pathlib import Path
from datetime import datetime, timezone

import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use("TkAgg")                          # must come before pyplot import
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# ── Locate cThermal the same way the original script did ──────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "utils"))
from cThermal import cThermal

# ── CLI args (interval only; plot is always on in the GUI) ────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--interval", type=float, default=0.5,
                    help="Seconds between captures (default 0.5)")
args = parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
class ThermalApp(tk.Tk):
    """Main application window."""

    POLL_MS = 100          # how often the GUI polls for new data (ms)
    BG       = "#1a1a2e"   # deep navy background
    PANEL    = "#16213e"   # slightly lighter panel
    ACCENT   = "#e94560"   # vivid red accent
    TEXT     = "#eaeaea"
    DIM      = "#8888aa"
    GREEN    = "#00d4aa"
    AMBER    = "#f5a623"
    BLUE     = "#4fc3f7"

    def __init__(self):
        super().__init__()
        self.title("Thermal Monitor")
        self.configure(bg=self.BG)
        self.resizable(True, True)

        # ── State ─────────────────────────────────────────────────────────────
        night = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.thermal   = cThermal(night)
        self.running   = False
        self._thread   = None
        self._lock     = threading.Lock()
        self._iter     = 0

        # ── Build UI ──────────────────────────────────────────────────────────
        self._build_header()
        self._build_plot()
        self._build_readout()
        self._build_controls()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Connect once at startup
        self._status("Connecting to device…")
        ok = self.thermal.connect()
        if ok:
            self._status("Connected  •  Ready")
        else:
            self._status(
                f"⚠  No device at {self.thermal.config.get('COM_Port', '?')}",
                error=True
            )

        # Start the GUI polling loop
        self.after(self.POLL_MS, self._poll)

    # ── UI builders ───────────────────────────────────────────────────────────

    def _build_header(self):
        header = tk.Frame(self, bg=self.BG)
        header.pack(fill="x", padx=18, pady=(16, 4))

        tk.Label(
            header, text="THERMAL MONITOR",
            font=("Courier New", 18, "bold"),
            fg=self.ACCENT, bg=self.BG
        ).pack(side="left")

        self._status_var = tk.StringVar(value="Initialising…")
        tk.Label(
            header, textvariable=self._status_var,
            font=("Courier New", 10),
            fg=self.DIM, bg=self.BG
        ).pack(side="right", pady=6)

    def _build_plot(self):
        plot_frame = tk.Frame(self, bg=self.PANEL, bd=0, highlightthickness=0)
        plot_frame.pack(fill="both", expand=True, padx=18, pady=6)

        self.fig = Figure(figsize=(9, 5), facecolor=self.PANEL)
        self.fig.subplots_adjust(hspace=0.35, left=0.08, right=0.97,
                                  top=0.93, bottom=0.1)

        self.ax_temp  = self.fig.add_subplot(2, 1, 1)
        self.ax_power = self.fig.add_subplot(2, 1, 2)
        self._style_axes()

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _style_axes(self):
        for ax in (self.ax_temp, self.ax_power):
            ax.set_facecolor(self.BG)
            ax.tick_params(colors=self.DIM, labelsize=8)
            for spine in ax.spines.values():
                spine.set_edgecolor("#2a2a4e")
            ax.grid(color="#2a2a4e", linewidth=0.6, linestyle="--")
            ax.title.set_color(self.TEXT)

        self.ax_temp.set_title("Temperature  (°C)", fontsize=9,
                                color=self.DIM, loc="left")
        self.ax_power.set_title("Power  (%)", fontsize=9,
                                 color=self.DIM, loc="left")
        self.ax_power.set_xlabel("Elapsed time (s)", fontsize=8, color=self.DIM)

    def _build_readout(self):
        """Row showing the latest temperatures and the save filename."""
        row = tk.Frame(self, bg=self.BG)
        row.pack(fill="x", padx=18, pady=4)

        # Temperature tiles
        tile_cfg = [
            ("Input 1", self.GREEN),
            ("Input 2", self.AMBER),
            ("Input 3", self.BLUE),
            ("Room", self.TEXT),
        ]
        self._temp_vars = []
        for label, color in tile_cfg:
            tile = tk.Frame(row, bg=self.PANEL, padx=14, pady=8)
            tile.pack(side="left", padx=(0, 10))
            tk.Label(tile, text=label, font=("Courier New", 8),
                     fg=self.DIM, bg=self.PANEL).pack(anchor="w")
            var = tk.StringVar(value="— °C")
            tk.Label(tile, textvariable=var,
                     font=("Courier New", 18, "bold"),
                     fg=color, bg=self.PANEL).pack(anchor="w")
            self._temp_vars.append(var)

        # Filename display
        fname_frame = tk.Frame(row, bg=self.PANEL, padx=14, pady=8)
        fname_frame.pack(side="left", fill="x", expand=True)
        tk.Label(fname_frame, text="Saving to",
                 font=("Courier New", 8),
                 fg=self.DIM, bg=self.PANEL).pack(anchor="w")
        self._fname_var = tk.StringVar(value="(not started)")
        tk.Label(fname_frame, textvariable=self._fname_var,
                 font=("Courier New", 10),
                 fg=self.TEXT, bg=self.PANEL,
                 wraplength=420, justify="left").pack(anchor="w")

        # Iteration counter
        ctr_frame = tk.Frame(row, bg=self.PANEL, padx=14, pady=8)
        ctr_frame.pack(side="right")
        tk.Label(ctr_frame, text="Reads",
                 font=("Courier New", 8),
                 fg=self.DIM, bg=self.PANEL).pack(anchor="e")
        self._iter_var = tk.StringVar(value="0")
        tk.Label(ctr_frame, textvariable=self._iter_var,
                 font=("Courier New", 18, "bold"),
                 fg=self.ACCENT, bg=self.PANEL).pack(anchor="e")

    def _build_controls(self):
        ctrl = tk.Frame(self, bg=self.BG)
        ctrl.pack(fill="x", padx=18, pady=(4, 16))

        self._btn_var = tk.StringVar(value="▶  START")
        self._btn = tk.Button(
            ctrl,
            textvariable=self._btn_var,
            font=("Courier New", 12, "bold"),
            fg=self.BG, bg=self.GREEN,
            activebackground=self.ACCENT,
            activeforeground=self.BG,
            relief="flat", padx=24, pady=10,
            cursor="hand2",
            command=self._toggle
        )
        self._btn.pack(side="left")

        tk.Label(
            ctrl,
            text=f"interval  {args.interval} s",
            font=("Courier New", 9),
            fg=self.DIM, bg=self.BG
        ).pack(side="left", padx=16)

    # ── Control logic ─────────────────────────────────────────────────────────

    def _toggle(self):
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self):
        self.running = True
        self._btn_var.set("■  STOP")
        self._btn.config(bg=self.ACCENT)
        self._status("Collecting data…")
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()

    def _stop(self):
        self.running = False
        self._btn_var.set("▶  START")
        self._btn.config(bg=self.GREEN)
        self._status(f"Stopped after {self._iter} reads")

    def _collect_loop(self):
        """Background thread: repeatedly read data and sleep."""
        while self.running:
            try:
                self.thermal.read_data()
                with self._lock:
                    self._iter += 1
                time.sleep(args.interval)
            except Exception as exc:
                self._status(f"Error: {exc}", error=True)
                self.running = False
                break

    # ── GUI polling ───────────────────────────────────────────────────────────

    def _poll(self):
        """Called every POLL_MS ms on the main thread to refresh the GUI."""
        if self._iter > 0:
            self._refresh_ui()
        self.after(self.POLL_MS, self._poll)

    def _refresh_ui(self):
        alldata = self.thermal.alldata        # dict of lists

        # ── Temperature tiles ─────────────────────────────────────────────────
        keys = ["input1", "input2", "input3", "temp5"]
        for var, key in zip(self._temp_vars, keys):
            vals = alldata.get(key, [])
            if vals:
                var.set(f"{vals[-1]:.2f} °C")

        # ── Filename ─────────────────────────────────────────────────────────
        data_dir = getattr(self.thermal, "data_dir", None)
        if data_dir:
            self._fname_var.set(str(data_dir))

        # ── Iteration counter ─────────────────────────────────────────────────
        with self._lock:
            self._iter_var.set(str(self._iter))

        # ── Plot ─────────────────────────────────────────────────────────────
        t = alldata.get("elapsed_time", [])
        if len(t) < 2:
            return

        self.ax_temp.cla()
        self.ax_power.cla()
        self._style_axes()

        colors_temp  = [self.GREEN, self.AMBER, self.BLUE]
        colors_power = [self.GREEN, self.AMBER, self.BLUE]

        for i, (key, color) in enumerate(
                zip(["input1", "input2", "input3"], colors_temp)):
            vals = alldata.get(key, [])
            if vals:
                self.ax_temp.plot(t, vals, color=color, linewidth=1.4,
                                  label=f"Input {i+1}")

        for i, (key, color) in enumerate(
                zip(["pct_power1", "pct_power2", "pct_power3"], colors_power)):
            vals = alldata.get(key, [])
            if vals:
                self.ax_power.plot(t, vals, color=color, linewidth=1.4,
                                   label=f"Power {i+1}", linestyle="--")

        for ax in (self.ax_temp, self.ax_power):
            leg = ax.legend(fontsize=7, facecolor=self.PANEL,
                            edgecolor="#2a2a4e", labelcolor=self.TEXT,
                            loc="upper left")

        self.canvas.draw_idle()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _status(self, msg: str, error: bool = False):
        self._status_var.set(msg)
        self._status_var.set(msg)   # force refresh
        color = self.ACCENT if error else self.DIM

        # find the status label and recolor it
        for w in self.winfo_children():
            if isinstance(w, tk.Frame):
                for child in w.winfo_children():
                    if isinstance(child, tk.Label) and \
                            child.cget("textvariable") == str(self._status_var):
                        child.config(fg=color)

    def _on_close(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)
        self.thermal.disconnect()
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ThermalApp()
    app.mainloop()