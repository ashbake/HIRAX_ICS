"""
GUI for H4RPro Spectrometer with exposure control and averaging.
"""

import tkinter as tk
from tkinter import ttk
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import threading
from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "utils" ))
from cH4RPro import cH4RPro


class SpectrometerGUI:
    def __init__(self, root, h4rpro_class):
        self.root = root
        self.root.title("H4RPro Spectrometer")
        self.root.geometry("1200x800")
        self.root.configure(bg='#E6D5F5')  # Light purple
        
        # Store the H4RPro class reference
        self.h4rpro_class = h4rpro_class
        self.h4rpro = None
        
        # Parameters
        self.exposure_time = 0.02  # seconds
        self.num_spectra = 5
        self.wavelength_offset = 0.958  # nm (hardcoded, not user-adjustable)
        self.connected = False
        self.capturing = False
        self.continuous_mode = False
        
        # Wavelength range limits
        self.wl_min = None
        self.wl_max = None
        self.use_wl_limits = False
        
        # Data storage
        self.current_wl = None
        self.current_flux = None
        self.averaged_flux = None
        
        # Background subtraction
        self.background_file = None
        self.background_data = None
        self.use_background = False
        
        self._create_widgets()
        
    def _create_widgets(self):
        """Create all GUI widgets"""
        
        # Top info bar
        info_frame = ttk.Frame(self.root, padding=5)
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        # Date display
        current_date = datetime.utcnow().strftime("%Y%m%d")
        ttk.Label(info_frame, text="Night:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        self.date_label = ttk.Label(info_frame, text=current_date, font=("Arial", 10))
        self.date_label.pack(side=tk.LEFT, padx=5)
        
        # Source name
        ttk.Label(info_frame, text="Source:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(20, 5))
        self.source_var = tk.StringVar(value="dark")
        self.source_entry = ttk.Entry(info_frame, textvariable=self.source_var, width=20)
        self.source_entry.pack(side=tk.LEFT, padx=5)
        
        # Connection status
        ttk.Label(info_frame, text="Spectrometer:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(20, 5))
        self.connection_status = ttk.Label(
            info_frame,
            text="DISCONNECTED",
            foreground="red",
            font=("Arial", 10, "bold")
        )
        self.connection_status.pack(side=tk.LEFT, padx=5)
        
        self.connect_button = ttk.Button(
            info_frame,
            text="Connect",
            command=self.toggle_connection
        )
        self.connect_button.pack(side=tk.LEFT, padx=5)
        
        # Control Panel
        control_frame = ttk.LabelFrame(self.root, text="Acquisition Controls", padding=10)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        # Row 0: Exposure time
        ttk.Label(control_frame, text="Exposure Time (s):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.exposure_var = tk.DoubleVar(value=self.exposure_time)
        self.exposure_spinbox = ttk.Spinbox(
            control_frame,
            from_=0.001,
            to=10.0,
            increment=0.001,
            textvariable=self.exposure_var,
            width=10,
            format="%.3f"
        )
        self.exposure_spinbox.grid(row=0, column=1, padx=5, pady=5)
        
        # Number of spectra to average
        ttk.Label(control_frame, text="Spectra to Average:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.num_spectra_var = tk.IntVar(value=self.num_spectra)
        self.num_spectra_spinbox = ttk.Spinbox(
            control_frame,
            from_=1,
            to=100,
            increment=1,
            textvariable=self.num_spectra_var,
            width=10
        )
        self.num_spectra_spinbox.grid(row=0, column=3, padx=5, pady=5)
        
        # Acquire button
        self.acquire_button = ttk.Button(
            control_frame,
            text="Acquire Spectrum",
            command=self.acquire_spectrum,
            state=tk.DISABLED
        )
        self.acquire_button.grid(row=0, column=4, padx=10, pady=5)
        
        # Continuous mode checkbox
        self.continuous_var = tk.BooleanVar(value=False)
        self.continuous_check = ttk.Checkbutton(
            control_frame,
            text="Continuous",
            variable=self.continuous_var,
            command=self.toggle_continuous
        )
        self.continuous_check.grid(row=0, column=5, padx=5, pady=5)
        
        # Row 1: Wavelength range controls
        self.wl_range_var = tk.BooleanVar(value=False)
        self.wl_range_check = ttk.Checkbutton(
            control_frame,
            text="Limit Wavelength Range",
            variable=self.wl_range_var,
            command=self.toggle_wl_range
        )
        self.wl_range_check.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(control_frame, text="Min (nm):").grid(row=1, column=2, padx=5, pady=5, sticky=tk.E)
        self.wl_min_var = tk.DoubleVar(value=400)
        self.wl_min_spinbox = ttk.Spinbox(
            control_frame,
            from_=300,
            to=1000,
            increment=1,
            textvariable=self.wl_min_var,
            width=8,
            state=tk.DISABLED
        )
        self.wl_min_spinbox.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(control_frame, text="Max (nm):").grid(row=1, column=4, padx=5, pady=5, sticky=tk.E)
        self.wl_max_var = tk.DoubleVar(value=800)
        self.wl_max_spinbox = ttk.Spinbox(
            control_frame,
            from_=300,
            to=1000,
            increment=1,
            textvariable=self.wl_max_var,
            width=8,
            state=tk.DISABLED
        )
        self.wl_max_spinbox.grid(row=1, column=5, padx=5, pady=5, sticky=tk.W)
        
        self.apply_range_button = ttk.Button(
            control_frame,
            text="Apply Range",
            command=self.apply_wl_range,
            state=tk.DISABLED
        )
        self.apply_range_button.grid(row=1, column=6, padx=5, pady=5)
        
        # Row 2: Background subtraction controls
        self.background_var = tk.BooleanVar(value=False)
        self.background_check = ttk.Checkbutton(
            control_frame,
            text="Subtract Background",
            variable=self.background_var,
            command=self.toggle_background
        )
        self.background_check.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(control_frame, text="Background File:").grid(row=2, column=2, padx=5, pady=5, sticky=tk.E)
        self.background_file_var = tk.StringVar(value="")
        self.background_entry = ttk.Entry(
            control_frame,
            textvariable=self.background_file_var,
            width=30,
            state=tk.DISABLED
        )
        self.background_entry.grid(row=2, column=3, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        
        self.browse_button = ttk.Button(
            control_frame,
            text="Browse...",
            command=self.browse_background_file,
            state=tk.DISABLED
        )
        self.browse_button.grid(row=2, column=5, padx=5, pady=5)
        
        self.load_bg_button = ttk.Button(
            control_frame,
            text="Load Background",
            command=self.load_background,
            state=tk.DISABLED
        )
        self.load_bg_button.grid(row=2, column=6, padx=5, pady=5)
        
        # Statistics Frame
        stats_frame = ttk.LabelFrame(self.root, text="Spectrum Statistics", padding=10)
        stats_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        # Peak wavelength
        ttk.Label(stats_frame, text="Peak λ:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.peak_wl_label = ttk.Label(stats_frame, text="N/A", font=("Arial", 11, "bold"))
        self.peak_wl_label.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Peak flux
        ttk.Label(stats_frame, text="Peak Flux:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.peak_flux_label = ttk.Label(stats_frame, text="N/A", font=("Arial", 11))
        self.peak_flux_label.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)
        
        # Mean flux
        ttk.Label(stats_frame, text="Mean Flux:").grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        self.mean_flux_label = ttk.Label(stats_frame, text="N/A", font=("Arial", 11))
        self.mean_flux_label.grid(row=0, column=5, padx=5, pady=5, sticky=tk.W)
        
        # Background loaded status
        ttk.Label(stats_frame, text="Background:").grid(row=0, column=6, padx=5, pady=5, sticky=tk.W)
        self.background_status_label = ttk.Label(stats_frame, text="None", font=("Arial", 11))
        self.background_status_label.grid(row=0, column=7, padx=5, pady=5, sticky=tk.W)
        
        # Cursor readout
        ttk.Label(stats_frame, text="Cursor λ:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.cursor_wl_label = ttk.Label(stats_frame, text="N/A", font=("Arial", 10))
        self.cursor_wl_label.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(stats_frame, text="Cursor Flux:").grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        self.cursor_flux_label = ttk.Label(stats_frame, text="N/A", font=("Arial", 10))
        self.cursor_flux_label.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W)
        
        # Status label
        self.status_label = ttk.Label(stats_frame, text="Ready", foreground="green")
        self.status_label.grid(row=2, column=0, columnspan=6, padx=5, pady=5, sticky=tk.W)
        
        # Plot Frame
        plot_frame = ttk.Frame(self.root)
        plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create matplotlib figure
        self.figure = Figure(figsize=(10, 6), dpi=100, facecolor='#E6D5F5')
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor('#E6D5F5')
        self.ax.set_xlabel('Wavelength (nm)', fontsize=12)
        self.ax.set_ylabel('Flux', fontsize=12)
        self.ax.set_title('Spectrum', fontsize=14)
        self.ax.grid(True, alpha=0.3)
        
        # Embed figure
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Add navigation toolbar for zoom/pan
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()
        
        # Connect mouse motion for cursor readout
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        
        # Initial blank plot
        self.ax.plot([], [])
        self.canvas.draw()
        
    def toggle_background(self):
        """Toggle background subtraction"""
        if self.background_var.get():
            self.background_entry.config(state=tk.NORMAL)
            self.browse_button.config(state=tk.NORMAL)
            self.load_bg_button.config(state=tk.NORMAL)
        else:
            self.background_entry.config(state=tk.DISABLED)
            self.browse_button.config(state=tk.DISABLED)
            self.load_bg_button.config(state=tk.DISABLED)
            self.use_background = False
            self.background_status_label.config(text="None")
            # Replot without background subtraction
            if self.current_wl is not None:
                self._update_plot()
    
    def browse_background_file(self):
        """Open file dialog to select background file"""
        filename = tk.filedialog.askopenfilename(
            title="Select Background Spectrum File",
            filetypes=[
                ("CSV files", "*.csv"),
                ("NumPy files", "*.npy"),
                ("Text files", "*.txt *.dat"),
                ("All files", "*.*")
            ]
        )
        if filename:
            self.background_file_var.set(filename)
    
    def load_background(self):
        """Load background spectrum from file"""
        filename = self.background_file_var.get()
        
        if not filename:
            self.status_label.config(text="Error: No background file specified", foreground="red")
            return
        
        try:
            filepath = Path(filename)
            
            if not filepath.exists():
                self.status_label.config(text=f"Error: File not found: {filename}", foreground="red")
                return
            
            # Load based on file extension
            if filepath.suffix == '.npy':
                # NumPy binary format
                self.background_data = np.load(filepath)
            elif filepath.suffix == '.csv':
                # Text format (assume wavelength, flux columns)
                data = np.loadtxt(filepath,skiprows=1,delimiter=',')
                if data.ndim >= 2:
                    # Assume second column and after is flux. average if multiple
                    self.background_data = np.mean(data[:, 1:],axis=1)
                else:
                    # Single column - just flux
                    self.background_data = data
            else:
                self.status_label.config(text=f"Error: File format not supported: {filename}", foreground="red")
                return
            
            self.use_background = True
            self.background_file = filename
            self.background_status_label.config(text=f"Loaded ({len(self.background_data)} pts)")
            self.status_label.config(text=f"Background loaded: {filepath.name}", foreground="green")
            
            # Replot with background subtraction
            if self.current_wl is not None:
                self._update_plot()
                
        except Exception as e:
            self.status_label.config(text=f"Error loading background: {e}", foreground="red")
            self.use_background = False
            self.background_data = None
            self.background_status_label.config(text="Error")
    
    def toggle_wl_range(self):
        """Toggle wavelength range limiting"""
        if self.wl_range_var.get():
            self.wl_min_spinbox.config(state=tk.NORMAL)
            self.wl_max_spinbox.config(state=tk.NORMAL)
            self.apply_range_button.config(state=tk.NORMAL)
        else:
            self.wl_min_spinbox.config(state=tk.DISABLED)
            self.wl_max_spinbox.config(state=tk.DISABLED)
            self.apply_range_button.config(state=tk.DISABLED)
            self.use_wl_limits = False
            # Replot with full range
            if self.current_wl is not None:
                self._update_plot()
    
    def apply_wl_range(self):
        """Apply wavelength range limits"""
        self.wl_min = self.wl_min_var.get()
        self.wl_max = self.wl_max_var.get()
        
        if self.wl_min >= self.wl_max:
            self.status_label.config(text="Error: Min must be < Max", foreground="red")
            return
        
        self.use_wl_limits = True
        
        # Replot with new limits
        if self.current_wl is not None:
            self._update_plot()
    
    def toggle_continuous(self):
        """Toggle continuous acquisition mode"""
        self.continuous_mode = self.continuous_var.get()
        
        if self.continuous_mode:
            self.status_label.config(text="Continuous mode active", foreground="blue")
            # Start acquiring if connected
            if self.connected and not self.capturing:
                self.acquire_spectrum()
        else:
            self.status_label.config(text="Continuous mode stopped", foreground="orange")
    
    def toggle_connection(self):
        """Connect/disconnect spectrometer"""
        if self.connected:
            # Disconnect
            try:
                if self.h4rpro:
                    self.h4rpro.disconnect()
                self.connected = False
                self.connection_status.config(text="DISCONNECTED", foreground="red")
                self.connect_button.config(text="Connect")
                self.acquire_button.config(state=tk.DISABLED)
                self.status_label.config(text="Disconnected", foreground="orange")
            except Exception as e:
                self.status_label.config(text=f"Disconnect error: {e}", foreground="red")
        else:
            # Connect
            try:
                night = datetime.utcnow().strftime("%Y%m%d")
                source = self.source_var.get()
                self.h4rpro = self.h4rpro_class(night=night, source=source)
                self.h4rpro.connect()
                
                self.connected = True
                self.connection_status.config(text="CONNECTED", foreground="green")
                self.connect_button.config(text="Disconnect")
                self.acquire_button.config(state=tk.NORMAL)
                self.status_label.config(text="Connected successfully", foreground="green")
            except Exception as e:
                self.status_label.config(text=f"Connection error: {e}", foreground="red")
    
    def acquire_spectrum(self):
        """Acquire and average spectra"""
        if self.capturing or not self.connected:
            return
        
        self.capturing = True
        mode_text = "continuously" if self.continuous_mode else ""
        self.status_label.config(text=f"Acquiring spectra {mode_text}...", foreground="orange")
        self.acquire_button.config(state=tk.DISABLED)
        
        # Run in background thread
        thread = threading.Thread(target=self._acquire_thread)
        thread.daemon = True
        thread.start()
    
    def _acquire_thread(self):
        """Background thread for acquisition"""
        try:
            # Get parameters
            exposure_sec = self.exposure_var.get()
            integration_time_us = int(exposure_sec * 1e6)
            num_spectra = self.num_spectra_var.get()
            
            # Acquire spectra
            wl, flx = self.h4rpro.read_spectra(integration_time_us, num_spectra)
            
            # Apply wavelength offset (hardcoded)
            wl_corrected = wl - self.wavelength_offset
            
            # Calculate median (or mean)
            averaged_flux = np.median(flx, axis=0)
            
            # Store data
            self.current_wl = wl_corrected
            self.current_flux = flx
            self.averaged_flux = averaged_flux
            
            # Update GUI in main thread
            self.root.after(0, self._update_plot)
            
        except Exception as e:
            self.root.after(0, self._show_error, str(e))
    
    def _update_plot(self):
        """Update the plot with new data"""
        if self.current_wl is None or self.averaged_flux is None:
            return
        
        # Apply background subtraction if enabled
        plot_flux = self.averaged_flux.copy()
        
        if self.use_background and self.background_data is not None:
            # Check if dimensions match
            if len(self.background_data) == len(plot_flux):
                plot_flux = plot_flux - self.background_data
            else:
                self.status_label.config(
                    text=f"Warning: Background size mismatch ({len(self.background_data)} vs {len(plot_flux)})",
                    foreground="orange"
                )
        
        # Clear and plot
        self.ax.clear()
        self.ax.plot(self.current_wl, plot_flux, 'b-', linewidth=1.5)
        self.ax.set_xlabel('Wavelength (nm)', fontsize=12)
        self.ax.set_ylabel('Flux', fontsize=12)
        
        # Title with parameters
        source = self.source_var.get()
        exp_time = self.exposure_var.get()
        num_spec = self.num_spectra_var.get()
        title = f"{source} | Exposure: {exp_time:.3f}s | Averaged: {num_spec} spectra"
        if self.use_background:
            title += " | BG Subtracted"
        self.ax.set_title(title, fontsize=14)
        self.ax.grid(True, alpha=0.3)
        
        # Set x-axis limits if enabled
        if self.use_wl_limits and self.wl_min is not None and self.wl_max is not None:
            self.ax.set_xlim(self.wl_min, self.wl_max)
        
        # Calculate statistics (use background-subtracted data)
        peak_idx = np.argmax(plot_flux)
        peak_wl = self.current_wl[peak_idx]
        peak_flux = plot_flux[peak_idx]
        mean_flux = np.mean(plot_flux)
        
        # Update labels
        self.peak_wl_label.config(text=f"{peak_wl:.2f} nm")
        self.peak_flux_label.config(text=f"{peak_flux:.2f}")
        self.mean_flux_label.config(text=f"{mean_flux:.2f}")
        
        self.canvas.draw()
        
        # Update status
        status_text = "Continuous acquisition" if self.continuous_mode else "Acquisition complete"
        self.status_label.config(text=status_text, foreground="green")
        
        if not self.continuous_mode:
            self.acquire_button.config(state=tk.NORMAL)
        
        self.capturing = False
        
        # Continue acquiring if in continuous mode
        if self.continuous_mode and self.connected:
            self.root.after(100, self.acquire_spectrum)
    
    def _show_error(self, error_msg):
        """Show error message"""
        self.status_label.config(text=f"Error: {error_msg}", foreground="red")
        self.acquire_button.config(state=tk.NORMAL)
        self.capturing = False
    
    def on_mouse_move(self, event):
        """Handle mouse movement for cursor readout"""
        if event.inaxes != self.ax or self.current_wl is None or self.averaged_flux is None:
            return
        
        # Get cursor position
        cursor_wl = event.xdata
        
        # Find closest wavelength
        idx = np.argmin(np.abs(self.current_wl - cursor_wl))
        actual_wl = self.current_wl[idx]
        
        # Get flux (background-subtracted if enabled)
        if self.use_background and self.background_data is not None and len(self.background_data) == len(self.averaged_flux):
            actual_flux = self.averaged_flux[idx] - self.background_data[idx]
        else:
            actual_flux = self.averaged_flux[idx]
        
        # Update cursor labels
        self.cursor_wl_label.config(text=f"{actual_wl:.3f} nm")
        self.cursor_flux_label.config(text=f"{actual_flux:.2f}")


def main(h4rpro_class):
    """
    Main function to run the GUI
    
    Args:
        h4rpro_class: The cH4RPro class to use for spectrometer control
    """
    root = tk.Tk()
    app = SpectrometerGUI(root, h4rpro_class)
    root.mainloop()



# Example usage:
# from your_module import cH4RPro
if __name__ == "__main__":
    main(cH4RPro)