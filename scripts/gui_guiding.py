
import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from pathlib import Path
import threading
import time, sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "utils"))
from cFLIR import cFLIR
from cGuider import cGuider


# ── Extended guider that exposes centroid and accepts a custom target ─────────

class EnhancedGuider(cGuider):
    """Overrides run() to store centroid and accept a target pixel."""

    def run(self, data, target=None, subframe=None):
        """
        target: (col, row) in image coords for desired star position.
                Defaults to image center if None.
        """
        if subframe is not None:
            x0, xf, y0, yf = subframe
            self.subdata = data[x0:xf, y0:yf]
        else:
            self.subdata = data

        Nx, Ny = np.shape(self.subdata)   # nrows, ncols

        if target is not None:
            col_t, row_t = target
            self.xref = col_t - Nx // 2
            self.yref = row_t - Ny // 2
        else:
            self.xref, self.yref = 0, 0

        self.xcentroid, self.ycentroid = self._find_centroid(self.subdata)
        dx, dy = self._calc_offset(self.xcentroid, self.ycentroid, Nx, Ny,
                                   self.xref, self.yref)
        self.dx_px, self.dy_px = dx, dy
        self.dx_arcs, self.dy_arcs = self._pixel_to_arcsec(dx, dy)

        # Fix upstream bug: second condition was checking dx_arcs twice.
        # Guard session: cGuider.connect() swallows telnet failures so session
        # may not exist if the TCS is unreachable.
        if (np.abs(self.dx_arcs) < 10 and np.abs(self.dy_arcs) < 10
                and hasattr(self, 'session')):
            self.offset_to_TCS(np.round(self.dx_arcs, 2), np.round(self.dy_arcs, 2))


# ── Target pixel dialog ───────────────────────────────────────────────────────

class SetTargetDialog(tk.Toplevel):
    """Modal dialog for manually entering the guide target pixel."""

    # Sentinel values returned in self.result:
    #   'cancel'  -> user dismissed without change
    #   None      -> user reset to center
    #   (col,row) -> user set explicit target

    def __init__(self, parent, current_target, image_shape):
        super().__init__(parent)
        self.title("Set Guide Target")
        self.resizable(False, False)
        self.result = 'cancel'

        nrows, ncols = image_shape if image_shape else (256, 256)
        default_col = current_target[0] if current_target else ncols // 2
        default_row = current_target[1] if current_target else nrows // 2

        pad = dict(padx=10, pady=5)

        ttk.Label(self, text="Pixel position the star should be locked to.",
                  wraplength=280).grid(row=0, column=0, columnspan=3, **pad)

        ttk.Label(self, text="Target X (col):").grid(row=1, column=0, sticky=tk.E, **pad)
        self.x_var = tk.IntVar(value=int(default_col))
        ttk.Spinbox(self, from_=0, to=ncols - 1, textvariable=self.x_var,
                    width=8).grid(row=1, column=1, **pad)

        ttk.Label(self, text="Target Y (row):").grid(row=2, column=0, sticky=tk.E, **pad)
        self.y_var = tk.IntVar(value=int(default_row))
        ttk.Spinbox(self, from_=0, to=nrows - 1, textvariable=self.y_var,
                    width=8).grid(row=2, column=1, **pad)

        ttk.Label(self, text="Tip: you can also click the image to set target.",
                  font=("Arial", 8), foreground="gray").grid(row=3, column=0, columnspan=3, **pad)

        btn = ttk.Frame(self)
        btn.grid(row=4, column=0, columnspan=3, pady=10)
        ttk.Button(btn, text="Reset to Center", command=self._reset).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text="Cancel",          command=self._cancel).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text="Set Target",      command=self._ok).pack(side=tk.LEFT, padx=5)

        self.grab_set()
        self.transient(parent)
        self.wait_window(self)

    def _ok(self):
        self.result = (self.x_var.get(), self.y_var.get())
        self.destroy()

    def _reset(self):
        self.result = None          # caller interprets None as "use center"
        self.destroy()

    def _cancel(self):
        self.result = 'cancel'
        self.destroy()


# ── Main GUI ──────────────────────────────────────────────────────────────────

class CameraGUI:
    # Color palette
    BG       = '#1C2733'
    BG_MID   = '#253545'
    ACCENT   = '#3498DB'
    C_GOOD   = '#2ECC71'
    C_WARN   = '#E67E22'
    C_BAD    = '#E74C3C'
    C_INFO   = '#3498DB'
    C_DIM    = '#7F8C8D'

    def __init__(self, root):
        self.root = root
        self.root.title("HIRAX Guiding Camera v2")
        self.root.geometry("1100x840")
        self.root.configure(bg=self.BG)

        self.exposure_time    = 0.01
        self.guide_interval   = 1.0
        self.guide_avg_frames = 1
        self.capturing        = False
        self.guiding_active   = False
        self.current_image    = None
        self.camera_connected = False
        self.source_name      = ""
        self.guide_target     = None   # None = image center; always in full-frame coords
        self.last_centroid    = None   # cached for redraws (image/subframe coords)
        self.last_target      = None
        self._img_x_min       = 0     # full-frame col offset of displayed image origin
        self._img_y_min       = 0     # full-frame row offset of displayed image origin

        self.subframe_enabled = False
        self.subframe         = [2048, 1080, 256, 256]   # [x_col_center, y_row_center, w, h]
        self.full_frame_size  = [4096, 2160]

        self.current_night = datetime.now(timezone.utc).strftime("%Y%m%d")

        self._apply_style()
        self._build_ui()

    # ── Style ─────────────────────────────────────────────────────────────────

    def _apply_style(self):
        s = ttk.Style()
        try:
            s.theme_use('clam')
        except Exception:
            pass
        s.configure('TFrame',           background=self.BG)
        s.configure('TLabel',           background=self.BG, foreground='white')
        s.configure('TLabelframe',      background=self.BG)
        s.configure('TLabelframe.Label',background=self.BG, foreground=self.ACCENT,
                    font=('Arial', 9, 'bold'))
        s.configure('TButton',          background=self.BG_MID, foreground='white')
        s.configure('TCheckbutton',     background=self.BG, foreground='white')
        s.configure('TSpinbox',         background=self.BG_MID, foreground='white',
                    fieldbackground=self.BG_MID)
        s.configure('TEntry',           fieldbackground=self.BG_MID, foreground='white')
        s.configure('TCombobox',        fieldbackground=self.BG_MID, foreground='white')
        s.configure('Accent.TButton',   background=self.ACCENT, foreground='white')
        s.map('Accent.TButton', background=[('active', '#2980B9')])

    # ── Widget construction ───────────────────────────────────────────────────

    def _build_ui(self):
        # ── Info bar ──
        info = ttk.Frame(self.root, padding=5)
        info.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(8, 2))

        ttk.Label(info, text="Date:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        ttk.Label(info, text=self.current_night).pack(side=tk.LEFT, padx=5)

        ttk.Label(info, text="Source:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(20, 5))
        self.source_var = tk.StringVar()
        ttk.Entry(info, textvariable=self.source_var, width=20).pack(side=tk.LEFT, padx=5)

        ttk.Label(info, text="Camera:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(20, 5))
        self.camera_status_label = ttk.Label(info, text="DISCONNECTED",
                                             foreground=self.C_BAD, font=("Arial", 10, "bold"))
        self.camera_status_label.pack(side=tk.LEFT, padx=5)
        self.connect_button = ttk.Button(info, text="Connect Camera",
                                         command=self.toggle_camera_connection)
        self.connect_button.pack(side=tk.LEFT, padx=5)

        # ── Controls ──
        ctrl = ttk.LabelFrame(self.root, text="Controls", padding=8)
        ctrl.pack(side=tk.TOP, fill=tk.X, padx=10, pady=4)

        # Row 0: exposure / capture / continuous / write
        ttk.Label(ctrl, text="Exposure (s):").grid(row=0, column=0, padx=5, pady=3, sticky=tk.E)
        self.exposure_var = tk.DoubleVar(value=self.exposure_time)
        ttk.Spinbox(ctrl, from_=0.1, to=60.0, increment=0.1,
                    textvariable=self.exposure_var, width=8).grid(row=0, column=1, padx=4, pady=3)

        self.capture_button = ttk.Button(ctrl, text="Capture Image", command=self.capture_image)
        self.capture_button.grid(row=0, column=2, padx=5, pady=3)

        self.continuous_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Continuous", variable=self.continuous_var,
                        command=self.toggle_continuous).grid(row=0, column=3, padx=5, pady=3)

        self.write_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Write to File",
                        variable=self.write_var).grid(row=0, column=4, padx=5, pady=3)

        # Row 1: subframe
        self.subframe_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Subframe", variable=self.subframe_var,
                        command=self.toggle_subframe).grid(row=1, column=0, padx=5, pady=3)

        sf_fields = [("X:", 'subframe_x', self.subframe[0], 4096),   # col center, max = frame width
                     ("Y:", 'subframe_y', self.subframe[1], 2160),   # row center, max = frame height
                     ("W:", 'subframe_w', self.subframe[2], 512),
                     ("H:", 'subframe_h', self.subframe[3], 512)]
        for i, (lbl, attr, val, mx) in enumerate(sf_fields):
            ttk.Label(ctrl, text=lbl).grid(row=1, column=1 + i*2, padx=2, pady=3, sticky=tk.E)
            sb = ttk.Spinbox(ctrl, from_=0, to=mx, width=6, command=self.update_subframe_display)
            sb.set(val)
            sb.grid(row=1, column=2 + i*2, padx=2, pady=3, sticky=tk.W)
            sb.bind('<Return>',   lambda _e: self.update_subframe_display())
            sb.bind('<FocusOut>', lambda _e: self.update_subframe_display())
            setattr(self, attr, sb)

        # Row 2: guiding + guide target
        self.guiding_button = ttk.Button(ctrl, text="Start Guiding",
                                         command=self.toggle_guiding, style="Accent.TButton")
        self.guiding_button.grid(row=2, column=0, columnspan=2, padx=5, pady=3, sticky=tk.EW)

        self.guiding_status_label = ttk.Label(ctrl, text="Guiding: OFF",
                                              foreground=self.C_BAD, font=("Arial", 10, "bold"))
        self.guiding_status_label.grid(row=2, column=2, padx=5, pady=3, sticky=tk.W)

        ttk.Button(ctrl, text="Set Guide Target",
                   command=self.open_target_dialog).grid(row=2, column=3, padx=5, pady=3)

        self.target_label = ttk.Label(ctrl, text="Target: image center", foreground=self.C_DIM)
        self.target_label.grid(row=2, column=4, columnspan=2, padx=5, pady=3, sticky=tk.W)

        ttk.Label(ctrl, text="Centroid:").grid(row=2, column=6, padx=(15, 2), pady=3, sticky=tk.E)
        self.centroid_method_var = tk.StringVar(value="Marginal Std")
        self.centroid_combo = ttk.Combobox(
            ctrl, textvariable=self.centroid_method_var,
            values=["Marginal Std", "Center of Mass"],
            state="readonly", width=14
        )
        self.centroid_combo.grid(row=2, column=7, padx=5, pady=3)
        self.centroid_combo.bind("<<ComboboxSelected>>", self._on_centroid_method_change)

        ttk.Label(ctrl, text="Interval (s):").grid(row=2, column=8, padx=(15, 2), pady=3, sticky=tk.E)
        self.interval_var = tk.DoubleVar(value=self.guide_interval)
        ttk.Spinbox(ctrl, from_=0.0, to=30.0, increment=0.5,
                    textvariable=self.interval_var, width=6).grid(row=2, column=9, padx=5, pady=3)

        ttk.Label(ctrl, text="Avg frames:").grid(row=2, column=10, padx=(10, 2), pady=3, sticky=tk.E)
        self.avg_frames_var = tk.IntVar(value=self.guide_avg_frames)
        ttk.Spinbox(ctrl, from_=1, to=20, increment=1,
                    textvariable=self.avg_frames_var, width=4).grid(row=2, column=11, padx=5, pady=3)

        # Row 3: scale
        ttk.Label(ctrl, text="Scale:").grid(row=3, column=0, padx=5, pady=3, sticky=tk.E)
        self.scale_var = tk.StringVar(value="Auto (99%)")
        self.scale_combo = ttk.Combobox(ctrl, textvariable=self.scale_var,
                                        values=["Auto (99%)", "Auto (95%)", "Min-Max", "Custom"],
                                        state="readonly", width=12)
        self.scale_combo.grid(row=3, column=1, padx=5, pady=3)
        self.scale_combo.bind("<<ComboboxSelected>>", self.on_scale_change)

        ttk.Label(ctrl, text="Min:").grid(row=3, column=2, padx=2, pady=3, sticky=tk.E)
        self.vmin_var = tk.StringVar(value="Auto")
        self.vmin_entry = ttk.Entry(ctrl, textvariable=self.vmin_var, width=8, state=tk.DISABLED)
        self.vmin_entry.grid(row=3, column=3, padx=2, pady=3)

        ttk.Label(ctrl, text="Max:").grid(row=3, column=4, padx=2, pady=3, sticky=tk.E)
        self.vmax_var = tk.StringVar(value="Auto")
        self.vmax_entry = ttk.Entry(ctrl, textvariable=self.vmax_var, width=8, state=tk.DISABLED)
        self.vmax_entry.grid(row=3, column=5, padx=2, pady=3)

        self.apply_scale_button = ttk.Button(ctrl, text="Apply Scale",
                                             command=self.apply_custom_scale, state=tk.DISABLED)
        self.apply_scale_button.grid(row=3, column=6, padx=5, pady=3)

        # ── Stats bar ──
        stats = ttk.LabelFrame(self.root, text="Image Statistics", padding=6)
        stats.pack(side=tk.TOP, fill=tk.X, padx=10, pady=4)

        def _stat(parent, label, row, col, bold=False):
            ttk.Label(parent, text=label).grid(row=row, column=col, padx=5, pady=2, sticky=tk.W)
            lbl = ttk.Label(parent, text="N/A",
                            font=("Arial", 11, "bold") if bold else ("Arial", 11))
            lbl.grid(row=row, column=col+1, padx=5, pady=2, sticky=tk.W)
            return lbl

        self.peak_flux_label   = _stat(stats, "Peak:",     0, 0, bold=True)
        self.mean_flux_label   = _stat(stats, "Mean:",     0, 2)
        self.min_flux_label    = _stat(stats, "Min:",      0, 4)
        self.guide_error_label = _stat(stats, "Guide Err:",0, 6)
        self.centroid_label    = _stat(stats, "Centroid:", 1, 0)
        self.pixel_coord_label = _stat(stats, "Cursor:",   1, 2)
        self.pixel_flux_label  = _stat(stats, "Flux:",     1, 4)

        self.status_label = ttk.Label(stats, text="Ready", foreground=self.C_GOOD)
        self.status_label.grid(row=2, column=0, columnspan=8, padx=5, pady=2, sticky=tk.W)

        # ── Image canvas ──
        img_frame = ttk.Frame(self.root)
        img_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.figure = Figure(figsize=(9, 5.5), dpi=100, facecolor='#0D1117')
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor('#0D1117')

        self.canvas = FigureCanvasTkAgg(self.figure, master=img_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.canvas.mpl_connect('button_press_event', self.on_image_click)

        self._display_blank()

    # ── Camera ────────────────────────────────────────────────────────────────

    def toggle_camera_connection(self):
        if self.camera_connected:
            if self.guiding_active:
                self.toggle_guiding()
            self.camera.disconnect()
            try:
                self.guider.disconnect()
            except Exception:
                pass
            self.camera_connected = False
            self.camera_status_label.config(text="DISCONNECTED", foreground=self.C_BAD)
            self.connect_button.config(text="Connect Camera")
            self.capture_button.config(state=tk.DISABLED)
            self.status_label.config(text="Camera disconnected", foreground=self.C_WARN)
        else:
            try:
                self.camera = cFLIR(self.current_night)
                self.camera.connect()
                self.camera_connected = True
                self.camera_status_label.config(text="CONNECTED", foreground=self.C_GOOD)
                self.connect_button.config(text="Disconnect Camera")
                self.capture_button.config(state=tk.NORMAL)
            except Exception as e:
                self.status_label.config(text=f"Connection failed: {e}", foreground=self.C_BAD)
                return
            # Connect to TCS independently of guiding state
            self.guider = EnhancedGuider(self.current_night)
            self.guider.connect()
            if self.guider.session is not None:
                self.status_label.config(text="Camera + TCS connected", foreground=self.C_GOOD)
            else:
                self.status_label.config(text="Camera connected (TCS unavailable)", foreground=self.C_WARN)

    # ── Mouse events ──────────────────────────────────────────────────────────

    def on_mouse_move(self, event):
        if event.inaxes != self.ax or self.current_image is None:
            return
        # event coords are in full-frame space (because of imshow extent)
        x, y = int(event.xdata + 0.5), int(event.ydata + 0.5)
        # Convert to image array indices
        ix, iy = x - self._img_x_min, y - self._img_y_min
        h, w = self.current_image.shape
        if 0 <= ix < w and 0 <= iy < h:
            self.pixel_coord_label.config(text=f"({x}, {y})")
            self.pixel_flux_label.config(text=f"{self.current_image[iy, ix]:.1f}")
        else:
            self.pixel_coord_label.config(text="(-, -)")
            self.pixel_flux_label.config(text="N/A")

    def on_image_click(self, event):
        """Left-click on image to propose a new guide target (stores full-frame coords).

        Requires explicit confirmation before the guider position is actually
        changed, since an accidental click during active guiding would
        otherwise silently redirect the TCS.
        """
        if event.inaxes != self.ax or self.current_image is None or event.button != 1:
            return
        # event coords are full-frame because of imshow extent
        x, y = int(event.xdata + 0.5), int(event.ydata + 0.5)
        ix, iy = x - self._img_x_min, y - self._img_y_min
        h, w = self.current_image.shape
        if not (0 <= ix < w and 0 <= iy < h):
            return

        confirmed = messagebox.askyesno(
            "Confirm Guide Target Change",
            f"Set guide target to pixel ({x}, {y})?\n\n"
            "This will change the position the guider locks the star to.",
            icon="warning",
            parent=self.root,
        )
        if not confirmed:
            self.status_label.config(text="Guide target change cancelled", foreground=self.C_WARN)
            return

        self.guide_target = (x, y)   # full-frame coords
        self.target_label.config(text=f"Target: ({x}, {y})")
        self.status_label.config(text=f"Guide target set to ({x}, {y}) — click again to change",
                                 foreground=self.C_INFO)
        self._redraw()

    # ── Display helpers ───────────────────────────────────────────────────────

    def _display_blank(self):
        self.ax.clear()
        self.ax.imshow(np.zeros((256, 256)), cmap='inferno', origin='lower')
        self.ax.set_title("No Image — Click 'Capture Image'", color='white')
        self._style_axes()
        self.canvas.draw()

    def _style_axes(self):
        """Apply dark theme and N/S/E/W labels to current axes.

        Orientation (from TCS offset_to_TCS sign convention):
          X axis (columns): right = North,  left = South
          Y axis (rows, origin=lower): up = East, down = West
        """
        self.ax.set_xlabel("X Pixel      S ←——→ N", color='#AAB7B8', fontsize=9)
        self.ax.set_ylabel("Y Pixel      W ↓      ↑ E", color='#AAB7B8', fontsize=9)
        self.ax.tick_params(colors='#AAB7B8', labelsize=8)
        for sp in self.ax.spines.values():
            sp.set_edgecolor('#2C3E50')
        self.ax.title.set_color('white')

    def _redraw(self):
        """Redraw current image keeping cached overlay state."""
        if self.current_image is not None:
            self._update_display(self.current_image, self.last_centroid, self.last_target)

    # ── Scale ─────────────────────────────────────────────────────────────────

    def on_scale_change(self, event=None):
        if self.scale_var.get() == "Custom":
            self.vmin_entry.config(state=tk.NORMAL)
            self.vmax_entry.config(state=tk.NORMAL)
            self.apply_scale_button.config(state=tk.NORMAL)
            if self.current_image is not None:
                self.vmin_var.set(str(int(np.min(self.current_image))))
                self.vmax_var.set(str(int(np.percentile(self.current_image, 99))))
        else:
            self.vmin_entry.config(state=tk.DISABLED)
            self.vmax_entry.config(state=tk.DISABLED)
            self.apply_scale_button.config(state=tk.DISABLED)
            self.vmin_var.set("Auto")
            self.vmax_var.set("Auto")
            self._redraw()

    def apply_custom_scale(self):
        try:
            vmin, vmax = float(self.vmin_var.get()), float(self.vmax_var.get())
            if vmin >= vmax:
                self.status_label.config(text="Error: Min must be < Max", foreground=self.C_BAD)
                return
            self._redraw()
        except ValueError:
            self.status_label.config(text="Error: Invalid scale values", foreground=self.C_BAD)

    def _get_scale_limits(self, image):
        mode = self.scale_var.get()
        if mode == "Custom":
            try:
                return float(self.vmin_var.get()), float(self.vmax_var.get())
            except ValueError:
                pass
        if mode == "Auto (95%)":
            return 0, np.percentile(image, 95)
        if mode == "Min-Max":
            return np.min(image), np.max(image)
        return 0, np.percentile(image, 99)   # default Auto 99%

    # ── Subframe ──────────────────────────────────────────────────────────────

    def toggle_subframe(self):
        self.subframe_enabled = self.subframe_var.get()
        msg = "Subframe mode enabled" if self.subframe_enabled else "Full frame mode"
        self.status_label.config(text=msg,
                                 foreground=self.C_INFO if self.subframe_enabled else self.C_GOOD)
        self._redraw()

    def update_subframe_display(self):
        try:
            self.subframe = [int(self.subframe_x.get()), int(self.subframe_y.get()),
                             int(self.subframe_w.get()), int(self.subframe_h.get())]
        except ValueError:
            return
        if self.subframe_var.get():
            self._redraw()

    def _on_centroid_method_change(self, _event=None):
        method = 'com' if self.centroid_method_var.get() == "Center of Mass" else 'std'
        if self.guiding_active and hasattr(self, 'guider'):
            self.guider.centroid_method = method

    # ── Guiding ───────────────────────────────────────────────────────────────

    def toggle_guiding(self):
        self.guiding_active = not self.guiding_active
        if self.guiding_active:
            self.guiding_button.config(text="Stop Guiding")
            self.guiding_status_label.config(text="Guiding: ON", foreground=self.C_GOOD)
            self.status_label.config(text="Guiding active", foreground=self.C_GOOD)
            if not self.continuous_var.get():
                self.continuous_var.set(True)
                self.capture_image()
        else:
            self.guiding_button.config(text="Start Guiding")
            self.guiding_status_label.config(text="Guiding: OFF", foreground=self.C_BAD)
            self.status_label.config(text="Guiding stopped", foreground=self.C_WARN)
            self.guide_error_label.config(text="N/A")
            self.last_centroid = None
            self.last_target   = None
            self._redraw()

    def open_target_dialog(self):
        shape = self.current_image.shape if self.current_image is not None else (256, 256)
        dlg = SetTargetDialog(self.root, self.guide_target, shape)
        if dlg.result == 'cancel':
            return
        if dlg.result is None:
            self.guide_target = None
            self.target_label.config(text="Target: image center")
        else:
            self.guide_target = dlg.result
            self.target_label.config(text=f"Target: {self.guide_target}")
        self._redraw()

    # ── Capture ───────────────────────────────────────────────────────────────

    def capture_image(self):
        if self.capturing or not self.camera_connected:
            if not self.camera_connected:
                self.status_label.config(text="Error: Camera not connected", foreground=self.C_BAD)
            return
        self.capturing = True
        self.status_label.config(text="Capturing...", foreground=self.C_WARN)
        self.capture_button.config(state=tk.DISABLED)
        self.exposure_time = self.exposure_var.get()
        # Sync spinbox values on main thread — background thread must not read widgets
        try:
            self.subframe = [int(self.subframe_x.get()), int(self.subframe_y.get()),
                             int(self.subframe_w.get()), int(self.subframe_h.get())]
        except ValueError:
            pass
        threading.Thread(target=self._capture_thread, daemon=True).start()

    def _capture_thread(self):
        try:
            header_keys = {}
            if hasattr(self, 'guider') and self.guider.session is not None:
                try:
                    header_keys = self.guider.get_telemetry()
                except Exception as e:
                    print(f"[telemetry ERROR] {type(e).__name__}: {e}")
            
            header_keys['EXPTIME'] = self.exposure_time

            # Centroid from the previous guide cycle (lag of one cycle by necessity,
            # since the centroid is computed after the frames are saved).
            if (self.guiding_active and hasattr(self, 'guider')
                    and hasattr(self.guider, 'xcentroid')):
                header_keys['GDRXCEN'] = float(self.guider.xcentroid)
                header_keys['GDRYCEN'] = float(self.guider.ycentroid)

            n_avg      = int(self.avg_frames_var.get()) if self.guiding_active else 1
            write_file = self.write_var.get()
            source     = self.source_var.get()
            use_sub    = self.subframe_var.get()
            sub        = self.subframe if use_sub else None

            accumulated = None
            for _ in range(n_avg):
                self.camera.expose(self.exposure_time * 1e6,
                                   source=source,
                                   writeToFile=write_file,
                                   subframe=sub,
                                   header_keys=header_keys)
                if use_sub:
                    x, y, w, h = self.subframe
                    frame = self.camera.raw_data[y - h//2:y + h//2, x - w//2:x + w//2]
                else:
                    frame = self.camera.raw_data
                accumulated = frame.astype(float) if accumulated is None else accumulated + frame

            image = (accumulated / n_avg).astype(frame.dtype)

            centroid = None
            target   = None

            if self.guiding_active:
                nrows, ncols = image.shape
                # guide_target is in full-frame coords; guider needs image (subframe) coords
                x_min = self.subframe[0] - self.subframe[2] // 2 if self.subframe_enabled else 0
                y_min = self.subframe[1] - self.subframe[3] // 2 if self.subframe_enabled else 0
                if self.guide_target is not None:
                    target = (self.guide_target[0] - x_min, self.guide_target[1] - y_min)
                else:
                    target = (ncols // 2, nrows // 2)
                self.guider.run(image, target=target)
                centroid = (self.guider.xcentroid, self.guider.ycentroid)

            self.root.after(0, self._update_display, image, centroid, target)

        except Exception as e:
            self.root.after(0, self._show_error, str(e))

    # ── Main display update ───────────────────────────────────────────────────

    def _update_display(self, image, centroid=None, target=None):
        self.current_image = image
        # Cache for redraws (scale change, subframe toggle, etc.)
        if centroid is not None:
            self.last_centroid = centroid
        if target is not None:
            self.last_target = target

        nrows, ncols = image.shape
        peak = np.max(image)
        mean = np.mean(image)
        mn   = np.min(image)

        self.peak_flux_label.config(text=f"{peak:.1f}")
        self.mean_flux_label.config(text=f"{mean:.1f}")
        self.min_flux_label.config(text=f"{mn:.1f}")

        if self.guiding_active and hasattr(self, 'guider'):
            dx_a = getattr(self.guider, 'dx_arcs', None)
            dy_a = getattr(self.guider, 'dy_arcs', None)
            if dx_a is not None and dy_a is not None:
                # EW = dy_arcs, NS = -dx_arcs  (from offset_to_TCS)
                self.guide_error_label.config(text=f"EW {dy_a:+.2f}\"  NS {-dx_a:+.2f}\"")
        if centroid:
            self.centroid_label.config(text=f"({centroid[0]}, {centroid[1]})")

        # ── Clear axes and draw image ──
        if hasattr(self, 'colorbar'):
            self.colorbar.remove()
        self.ax.clear()

        vmin, vmax = self._get_scale_limits(image)

        # Determine extent from the ACTUAL image shape, not the checkbox state.
        # This prevents mismatches when _redraw fires before the next capture
        # (e.g. right after toggling the subframe checkbox).
        ff_ncols, ff_nrows = self.full_frame_size   # [4096, 2160]
        image_is_subframe = (ncols < ff_ncols or nrows < ff_nrows)

        if image_is_subframe:
            sf_x, sf_y, sf_w, sf_h = self.subframe
            x_min = sf_x - sf_w // 2
            y_min = sf_y - sf_h // 2
            x_max = sf_x + sf_w // 2
            y_max = sf_y + sf_h // 2
        else:
            x_min, y_min = 0, 0
            x_max, y_max = ncols, nrows
        self._img_x_min = x_min
        self._img_y_min = y_min

        im = self.ax.imshow(image, cmap='inferno', origin='lower', vmin=vmin, vmax=vmax,
                            extent=[x_min, x_max, y_min, y_max])

        # ── Subframe box overlay on full-frame view ──
        if not image_is_subframe:
            sf_x, sf_y, sf_w, sf_h = self.subframe
            self.ax.add_patch(Rectangle((sf_x - sf_w // 2, sf_y - sf_h // 2),
                                        sf_w, sf_h, linewidth=2,
                                        edgecolor='cyan', facecolor='none'))

        # ── Guide target marker (green circle + crosshair) ──
        # guide_target is in full-frame coords — plot directly.
        # Fallback: show guiding center (image coords) shifted to full-frame.
        if self.guide_target is not None:
            disp_target = self.guide_target
        elif target is not None:
            disp_target = (target[0] + x_min, target[1] + y_min)
        else:
            disp_target = None

        if disp_target is not None:
            tx, ty = disp_target
            self.ax.plot(tx, ty, '+', color=self.C_GOOD, markersize=16,
                         markeredgewidth=2, zorder=5, label='Guide target')
            self.ax.plot(tx, ty, 'o', color=self.C_GOOD, markersize=16,
                         markeredgewidth=2, fillstyle='none', zorder=5)

        # ── Centroid X and correction arrow ──
        # centroid is in image (subframe) coords — shift to full-frame for display.
        if centroid is not None:
            cx = centroid[0] + x_min
            cy = centroid[1] + y_min
            self.ax.plot(cx, cy, 'x', color=self.C_BAD, markersize=18,
                         markeredgewidth=2.5, zorder=6, label='Centroid')

            if disp_target is not None:
                tx, ty = disp_target
                ddx, ddy = tx - cx, ty - cy
                dist = np.sqrt(ddx**2 + ddy**2)
                if dist > 0.5:
                    self.ax.annotate(
                        '', xy=(tx, ty), xytext=(cx, cy),
                        arrowprops=dict(arrowstyle='->', color='#F39C12',
                                        lw=2.0, mutation_scale=20),
                        zorder=7
                    )
                    # Distance label at midpoint
                    self.ax.text((cx + tx) / 2 + 3, (cy + ty) / 2 + 3,
                                 f"{dist:.1f} px", color='#F39C12', fontsize=8, zorder=7,
                                 bbox=dict(boxstyle='round,pad=0.2', fc='#0D1117', alpha=0.75,
                                           ec='none'))

        # ── Title ──
        parts = []
        if self.source_var.get():
            parts.append(self.source_var.get())
        parts.append(f"Exp: {self.exposure_time:.1f}s  Peak: {peak:.0f}")
        if self.subframe_enabled:
            parts.append(f"Subframe {self.subframe[2]}×{self.subframe[3]}")
        if self.guiding_active:
            parts.append("● GUIDING")
        self.ax.set_title("   ".join(parts) if parts else "Camera Image")

        self._style_axes()

        # ── Legend (only when overlay is active) ──
        legend_items = []
        if centroid is not None:
            legend_items.append(
                plt.Line2D([0], [0], marker='x', linestyle='None', color='w',
                           markeredgecolor=self.C_BAD, markersize=10, label='Centroid'))
        if disp_target is not None:
            legend_items.append(
                plt.Line2D([0], [0], marker='o', linestyle='None', color='w',
                           markeredgecolor=self.C_GOOD, markerfacecolor='none',
                           markersize=10, label='Guide target'))
        if legend_items:
            leg = self.ax.legend(handles=legend_items, loc='upper right', fontsize=8,
                                 facecolor='#1C2733', edgecolor='#2C3E50', labelcolor='white')

        # ── Colorbar ──
        self.colorbar = self.figure.colorbar(im, ax=self.ax, label='Counts')
        self.colorbar.ax.yaxis.label.set_color('#AAB7B8')
        self.colorbar.ax.tick_params(colors='#AAB7B8', labelsize=8)

        self.canvas.draw()

        self.status_label.config(text="Guiding active" if self.guiding_active else "Ready",
                                 foreground=self.C_GOOD)
        self.capture_button.config(state=tk.NORMAL)
        self.capturing = False

        if self.continuous_var.get() or self.guiding_active:
            delay = int(self.interval_var.get() * 1000) if self.guiding_active else 100
            self.root.after(delay, self.capture_image)

    def _show_error(self, error_msg):
        self.status_label.config(text=f"Error: {error_msg}", foreground=self.C_BAD)
        self.capture_button.config(state=tk.NORMAL)
        self.capturing = False

    # ── Continuous ────────────────────────────────────────────────────────────

    def toggle_continuous(self):
        if self.continuous_var.get():
            self.status_label.config(text="Continuous — capturing...", foreground=self.C_INFO)
            self.capture_image()
        elif not self.guiding_active:
            self.status_label.config(text="Ready", foreground=self.C_GOOD)


def main():
    root = tk.Tk()
    app = CameraGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
