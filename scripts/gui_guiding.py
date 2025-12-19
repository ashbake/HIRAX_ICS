"""
Simple GUI for displaying camera images with exposure control and peak flux display.
Includes subframe selection and guiding controls.

Curtesy of Claude
Need to put in run_guiding.py functionality into this
"""

import tkinter as tk
from tkinter import ttk
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
import threading
import time


class CameraGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Camera Image Viewer with Guiding")
        self.root.geometry("1000x750")
        
        # Camera simulation parameters
        self.exposure_time = 2.0
        self.capturing = False
        self.guiding_active = False
        self.current_image = None
        
        # Subframe parameters (x, y, width, height)
        self.subframe_enabled = False
        self.subframe = [128, 128, 256, 256]  # Default subframe
        self.full_frame_size = 512
        
        # Create GUI elements
        self._create_widgets()
        
    def _create_widgets(self):
        """Create all GUI widgets"""
        
        # Control Panel Frame
        control_frame = ttk.LabelFrame(self.root, text="Controls", padding=10)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        # Row 0: Exposure time control
        ttk.Label(control_frame, text="Exposure Time (s):").grid(row=0, column=0, padx=5, pady=5)
        
        self.exposure_var = tk.DoubleVar(value=self.exposure_time)
        self.exposure_spinbox = ttk.Spinbox(
            control_frame, 
            from_=0.1, 
            to=10.0, 
            increment=0.1,
            textvariable=self.exposure_var,
            width=10
        )
        self.exposure_spinbox.grid(row=0, column=1, padx=5, pady=5)
        
        # Capture button
        self.capture_button = ttk.Button(
            control_frame, 
            text="Capture Image", 
            command=self.capture_image
        )
        self.capture_button.grid(row=0, column=2, padx=5, pady=5)
        
        # Continuous capture checkbox
        self.continuous_var = tk.BooleanVar(value=False)
        self.continuous_check = ttk.Checkbutton(
            control_frame,
            text="Continuous Capture",
            variable=self.continuous_var,
            command=self.toggle_continuous
        )
        self.continuous_check.grid(row=0, column=3, padx=5, pady=5)
        
        # Row 1: Subframe controls
        self.subframe_var = tk.BooleanVar(value=False)
        self.subframe_check = ttk.Checkbutton(
            control_frame,
            text="Use Subframe",
            variable=self.subframe_var,
            command=self.toggle_subframe
        )
        self.subframe_check.grid(row=1, column=0, padx=5, pady=5)
        
        ttk.Label(control_frame, text="X:").grid(row=1, column=1, padx=2, pady=5, sticky=tk.E)
        self.subframe_x = ttk.Spinbox(control_frame, from_=0, to=512, width=6, 
                                       command=self.update_subframe_display)
        self.subframe_x.set(self.subframe[0])
        self.subframe_x.grid(row=1, column=2, padx=2, pady=5, sticky=tk.W)
        
        ttk.Label(control_frame, text="Y:").grid(row=1, column=3, padx=2, pady=5, sticky=tk.E)
        self.subframe_y = ttk.Spinbox(control_frame, from_=0, to=512, width=6,
                                       command=self.update_subframe_display)
        self.subframe_y.set(self.subframe[1])
        self.subframe_y.grid(row=1, column=4, padx=2, pady=5, sticky=tk.W)
        
        ttk.Label(control_frame, text="W:").grid(row=1, column=5, padx=2, pady=5, sticky=tk.E)
        self.subframe_w = ttk.Spinbox(control_frame, from_=64, to=512, width=6,
                                       command=self.update_subframe_display)
        self.subframe_w.set(self.subframe[2])
        self.subframe_w.grid(row=1, column=6, padx=2, pady=5, sticky=tk.W)
        
        ttk.Label(control_frame, text="H:").grid(row=1, column=7, padx=2, pady=5, sticky=tk.E)
        self.subframe_h = ttk.Spinbox(control_frame, from_=64, to=512, width=6,
                                       command=self.update_subframe_display)
        self.subframe_h.set(self.subframe[3])
        self.subframe_h.grid(row=1, column=8, padx=2, pady=5, sticky=tk.W)
        
        # Row 2: Guiding controls
        self.guiding_button = ttk.Button(
            control_frame,
            text="Start Guiding",
            command=self.toggle_guiding,
            style="Accent.TButton"
        )
        self.guiding_button.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        
        self.guiding_status_label = ttk.Label(
            control_frame,
            text="Guiding: OFF",
            foreground="red",
            font=("Arial", 10, "bold")
        )
        self.guiding_status_label.grid(row=2, column=2, columnspan=2, padx=5, pady=5, sticky=tk.W)
        
        # Row 3: Colorbar scale controls
        ttk.Label(control_frame, text="Scale:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.E)
        
        self.scale_var = tk.StringVar(value="Auto (99%)")
        self.scale_combo = ttk.Combobox(
            control_frame,
            textvariable=self.scale_var,
            values=["Auto (99%)", "Auto (95%)", "Min-Max", "Custom"],
            state="readonly",
            width=12
        )
        self.scale_combo.grid(row=3, column=1, padx=5, pady=5)
        self.scale_combo.bind("<<ComboboxSelected>>", self.on_scale_change)
        
        ttk.Label(control_frame, text="Min:").grid(row=3, column=2, padx=2, pady=5, sticky=tk.E)
        self.vmin_var = tk.StringVar(value="Auto")
        self.vmin_entry = ttk.Entry(control_frame, textvariable=self.vmin_var, width=8, state=tk.DISABLED)
        self.vmin_entry.grid(row=3, column=3, padx=2, pady=5)
        
        ttk.Label(control_frame, text="Max:").grid(row=3, column=4, padx=2, pady=5, sticky=tk.E)
        self.vmax_var = tk.StringVar(value="Auto")
        self.vmax_entry = ttk.Entry(control_frame, textvariable=self.vmax_var, width=8, state=tk.DISABLED)
        self.vmax_entry.grid(row=3, column=5, padx=2, pady=5)
        
        self.apply_scale_button = ttk.Button(
            control_frame,
            text="Apply Scale",
            command=self.apply_custom_scale,
            state=tk.DISABLED
        )
        self.apply_scale_button.grid(row=3, column=6, padx=5, pady=5)
        
        # Status Frame
        status_frame = ttk.LabelFrame(self.root, text="Image Statistics", padding=10)
        status_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        # Peak flux display
        ttk.Label(status_frame, text="Peak Flux:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.peak_flux_label = ttk.Label(status_frame, text="N/A", font=("Arial", 12, "bold"))
        self.peak_flux_label.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Mean flux display
        ttk.Label(status_frame, text="Mean Flux:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.mean_flux_label = ttk.Label(status_frame, text="N/A", font=("Arial", 12))
        self.mean_flux_label.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)
        
        # Min flux display
        ttk.Label(status_frame, text="Min Flux:").grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        self.min_flux_label = ttk.Label(status_frame, text="N/A", font=("Arial", 12))
        self.min_flux_label.grid(row=0, column=5, padx=5, pady=5, sticky=tk.W)
        
        # Guide error display (if guiding)
        ttk.Label(status_frame, text="Guide Error:").grid(row=0, column=6, padx=5, pady=5, sticky=tk.W)
        self.guide_error_label = ttk.Label(status_frame, text="N/A", font=("Arial", 12))
        self.guide_error_label.grid(row=0, column=7, padx=5, pady=5, sticky=tk.W)
        
        # Pixel readout display
        ttk.Label(status_frame, text="Pixel:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.pixel_coord_label = ttk.Label(status_frame, text="(x, y)", font=("Arial", 10))
        self.pixel_coord_label.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(status_frame, text="Flux:").grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        self.pixel_flux_label = ttk.Label(status_frame, text="N/A", font=("Arial", 10, "bold"))
        self.pixel_flux_label.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W)
        
        # Status message
        self.status_label = ttk.Label(status_frame, text="Ready", foreground="green")
        self.status_label.grid(row=2, column=0, columnspan=8, padx=5, pady=5, sticky=tk.W)
        
        # Image display frame
        image_frame = ttk.Frame(self.root)
        image_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create matplotlib figure
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("Camera Image")
        self.ax.set_xlabel("X (pixels)")
        self.ax.set_ylabel("Y (pixels)")
        
        # Embed figure in tkinter
        self.canvas = FigureCanvasTkAgg(self.figure, master=image_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Connect mouse motion event for pixel readout
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        
        # Rectangle for subframe visualization
        self.subframe_rect = None
        
        # Initialize with blank image
        self._display_blank_image()
        
    def on_mouse_move(self, event):
        """Handle mouse movement over image to display pixel coordinates and flux"""
        if event.inaxes != self.ax or self.current_image is None:
            return
        
        # Get pixel coordinates
        x, y = int(event.xdata + 0.5), int(event.ydata + 0.5)
        
        # Check if coordinates are within image bounds
        height, width = self.current_image.shape
        if 0 <= x < width and 0 <= y < height:
            flux = self.current_image[y, x]
            self.pixel_coord_label.config(text=f"({x}, {y})")
            self.pixel_flux_label.config(text=f"{flux:.1f}")
        else:
            self.pixel_coord_label.config(text="(-, -)")
            self.pixel_flux_label.config(text="N/A")
    
    def _display_blank_image(self):
        """Display a blank placeholder image"""
        blank = np.zeros((512, 512))
        self.ax.clear()
        self.ax.imshow(blank, cmap='gray', origin='lower')
        self.ax.set_title("No Image - Click 'Capture Image'")
        self.ax.set_xlabel("X (pixels)")
        self.ax.set_ylabel("Y (pixels)")
        self.canvas.draw()
        
    def on_scale_change(self, event=None):
        """Handle scale mode change"""
        scale_mode = self.scale_var.get()
        
        if scale_mode == "Custom":
            self.vmin_entry.config(state=tk.NORMAL)
            self.vmax_entry.config(state=tk.NORMAL)
            self.apply_scale_button.config(state=tk.NORMAL)
            # Set current values as starting point
            if self.current_image is not None:
                self.vmin_var.set(str(int(np.min(self.current_image))))
                self.vmax_var.set(str(int(np.percentile(self.current_image, 99))))
        else:
            self.vmin_entry.config(state=tk.DISABLED)
            self.vmax_entry.config(state=tk.DISABLED)
            self.apply_scale_button.config(state=tk.DISABLED)
            self.vmin_var.set("Auto")
            self.vmax_var.set("Auto")
            # Redraw with new scale
            if self.current_image is not None:
                self._update_display(self.current_image)
    
    def apply_custom_scale(self):
        """Apply custom scale values"""
        try:
            vmin = float(self.vmin_var.get())
            vmax = float(self.vmax_var.get())
            if vmin >= vmax:
                self.status_label.config(text="Error: Min must be < Max", foreground="red")
                return
            # Redraw with custom scale
            if self.current_image is not None:
                self._update_display(self.current_image)
        except ValueError:
            self.status_label.config(text="Error: Invalid scale values", foreground="red")
    
    def _get_scale_limits(self, image):
        """Get vmin and vmax based on selected scale mode"""
        scale_mode = self.scale_var.get()
        
        if scale_mode == "Custom":
            try:
                vmin = float(self.vmin_var.get())
                vmax = float(self.vmax_var.get())
                return vmin, vmax
            except ValueError:
                # Fall back to Auto if invalid
                return 0, np.percentile(image, 99)
        elif scale_mode == "Auto (99%)":
            return 0, np.percentile(image, 99)
        elif scale_mode == "Auto (95%)":
            return 0, np.percentile(image, 95)
        elif scale_mode == "Min-Max":
            return np.min(image), np.max(image)
        else:
            return 0, np.percentile(image, 99)
    
    def toggle_subframe(self):
        """Toggle subframe mode"""
        self.subframe_enabled = self.subframe_var.get()
        if self.subframe_enabled:
            self.status_label.config(text="Subframe mode enabled", foreground="blue")
            self.update_subframe_display()
        else:
            self.status_label.config(text="Full frame mode", foreground="green")
            # Remove subframe rectangle if exists
            if self.subframe_rect:
                self.subframe_rect.remove()
                self.subframe_rect = None
                self.canvas.draw()
    
    def update_subframe_display(self):
        """Update the subframe rectangle on the display"""
        if not self.subframe_var.get():
            return
            
        # Get current subframe values
        x = int(self.subframe_x.get())
        y = int(self.subframe_y.get())
        w = int(self.subframe_w.get())
        h = int(self.subframe_h.get())
        
        self.subframe = [x, y, w, h]
        
        # Redraw current image with subframe overlay
        if self.current_image is not None:
            self._update_display(self.current_image)
    
    def toggle_guiding(self):
        """Toggle guiding on/off"""
        self.guiding_active = not self.guiding_active
        
        if self.guiding_active:
            self.guiding_button.config(text="Stop Guiding")
            self.guiding_status_label.config(text="Guiding: ON", foreground="green")
            self.status_label.config(text="Guiding active", foreground="green")
            
            # Start continuous capture if not already running
            if not self.continuous_var.get():
                self.continuous_var.set(True)
                self.capture_image()
        else:
            self.guiding_button.config(text="Start Guiding")
            self.guiding_status_label.config(text="Guiding: OFF", foreground="red")
            self.status_label.config(text="Guiding stopped", foreground="orange")
            self.guide_error_label.config(text="N/A")
        
    def simulate_camera_capture(self, exposure_time):
        """
        Simulate camera image capture.
        Replace this with your actual camera capture code.
        """
        # Simulate capture delay
        time.sleep(min(exposure_time * 0.1, 0.5))
        
        # Determine image size based on subframe setting
        if self.subframe_enabled:
            x, y, w, h = self.subframe
            size_x, size_y = w, h
        else:
            size_x, size_y = self.full_frame_size, self.full_frame_size
        
        # Generate simulated image with stars
        image = np.random.normal(100, 10, (size_y, size_x))  # Background noise
        
        # Add some simulated stars with flux proportional to exposure
        num_stars = 20 if not self.subframe_enabled else 5
        for _ in range(num_stars):
            star_x = np.random.randint(10, size_x - 10)
            star_y = np.random.randint(10, size_y - 10)
            intensity = np.random.uniform(500, 2000) * exposure_time
            
            # Create gaussian star
            y_grid, x_grid = np.ogrid[:size_y, :size_x]
            sigma = np.random.uniform(2, 4)
            star = intensity * np.exp(-((x_grid - star_x)**2 + (y_grid - star_y)**2) / (2 * sigma**2))
            image += star
        
        return image
        
    def capture_image(self):
        """Capture a single image"""
        if self.capturing:
            return
            
        self.capturing = True
        self.status_label.config(text="Capturing...", foreground="orange")
        self.capture_button.config(state=tk.DISABLED)
        
        # Get exposure time
        self.exposure_time = self.exposure_var.get()
        
        # Capture in background thread
        thread = threading.Thread(target=self._capture_thread)
        thread.daemon = True
        thread.start()
        
    def _capture_thread(self):
        """Background thread for image capture"""
        try:
            # Simulate or actual camera capture
            image = self.simulate_camera_capture(self.exposure_time)
            
            # Update GUI in main thread
            self.root.after(0, self._update_display, image)
            
        except Exception as e:
            self.root.after(0, self._show_error, str(e))
            
    def _update_display(self, image):
        """Update the display with new image"""
        self.current_image = image
        
        # Calculate statistics
        peak_flux = np.max(image)
        mean_flux = np.mean(image)
        min_flux = np.min(image)
        
        # Update labels
        self.peak_flux_label.config(text=f"{peak_flux:.1f}")
        self.mean_flux_label.config(text=f"{mean_flux:.1f}")
        self.min_flux_label.config(text=f"{min_flux:.1f}")
        
        # Simulate guide error if guiding active
        if self.guiding_active:
            guide_error = np.random.uniform(0.1, 2.0)  # Simulated guide error in pixels
            self.guide_error_label.config(text=f"{guide_error:.2f} px")
        
        # Display image
        if hasattr(self, 'colorbar'):
            self.colorbar.remove()
        self.ax.clear()
        
        # Get scale limits based on mode
        vmin, vmax = self._get_scale_limits(image)
        
        im = self.ax.imshow(image, cmap='gray', origin='lower', vmin=vmin, vmax=vmax)
        
        # Add subframe rectangle if in full frame mode
        if not self.subframe_enabled and self.subframe_var.get():
            x, y, w, h = self.subframe
            self.subframe_rect = Rectangle((x, y), w, h, linewidth=2, 
                                          edgecolor='red', facecolor='none')
            self.ax.add_patch(self.subframe_rect)
        
        title_text = f"Exposure: {self.exposure_time:.1f}s | Peak: {peak_flux:.1f}"
        if self.subframe_enabled:
            title_text += f" | Subframe: {self.subframe[2]}x{self.subframe[3]}"
        if self.guiding_active:
            title_text += " | GUIDING"
            
        self.ax.set_title(title_text)
        self.ax.set_xlabel("X (pixels)")
        self.ax.set_ylabel("Y (pixels)")
        
        # Add colorbar

        self.colorbar = self.figure.colorbar(im, ax=self.ax, label='Counts')
        
        self.canvas.draw()
        
        # Update status
        status_text = "Guiding active" if self.guiding_active else "Ready"
        self.status_label.config(text=status_text, foreground="green")
        self.capture_button.config(state=tk.NORMAL)
        self.capturing = False
        
        # Continue if continuous mode or guiding
        if self.continuous_var.get() or self.guiding_active:
            self.root.after(100, self.capture_image)
            
    def _show_error(self, error_msg):
        """Show error message"""
        self.status_label.config(text=f"Error: {error_msg}", foreground="red")
        self.capture_button.config(state=tk.NORMAL)
        self.capturing = False
        
    def toggle_continuous(self):
        """Toggle continuous capture mode"""
        if self.continuous_var.get():
            self.status_label.config(text="Continuous mode - capturing...", foreground="blue")
            self.capture_image()
        else:
            if not self.guiding_active:
                self.status_label.config(text="Ready", foreground="green")


def main():
    """Main function to run the GUI"""
    root = tk.Tk()
    app = CameraGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()