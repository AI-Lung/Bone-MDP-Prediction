from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from PIL import ImageTk

from .config import (
    ACQUISITION_VIEW_LABELS,
    ACQUISITION_VIEW_OPTIONS,
    CANVAS_HEIGHT,
    DEFAULT_OUTPUT_ROOT,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
    WINDOW_GEOMETRY,
    WINDOW_TITLE,
)
from .image_utils import build_render_bundle, build_render_bundle_from_array, describe_display_window, read_wbs_image
from .pipeline import PredictionRequest, run_prediction
from .runtime_utils import open_in_file_manager


class PredictorGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_GEOMETRY)
        self.root.minsize(1560, 940)
        self.root.configure(bg="#edf4f3")

        self.log_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.bundle = None
        self.default_display_window = None
        self.canvas_photo: ImageTk.PhotoImage | None = None
        self.active_tool: str | None = None
        self.drag_start: tuple[float, float] | None = None
        self.temp_shape_id: int | None = None
        self.circle_item_id: int | None = None
        self.rect_item_id: int | None = None
        self.circle_display: dict[str, float] | None = None
        self.rect_display: dict[str, float] | None = None
        self.last_output_dir: str | None = None

        self.file_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(DEFAULT_OUTPUT_ROOT))
        self.age_var = tk.StringVar()
        self.acquisition_view_var = tk.StringVar(value=list(ACQUISITION_VIEW_OPTIONS.keys())[0])
        self.gray_level_var = tk.DoubleVar(value=0.0)
        self.gray_width_var = tk.DoubleVar(value=1.0)
        self.gray_level_text_var = tk.StringVar(value="--")
        self.gray_width_text_var = tk.StringVar(value="--")
        self.status_var = tk.StringVar(value="Please choose a NIfTI file and load the image.")
        self._suspend_gray_updates = False

        self.diag_prob_var = tk.StringVar(value="--")
        self.diag_label_var = tk.StringVar(value="Awaiting prediction")
        self.radscore_var = tk.StringVar(value="--")
        self.total_points_var = tk.StringVar(value="--")
        self.overall_risk_var = tk.StringVar(value="--")
        self.solitary_risk_var = tk.StringVar(value="--")
        self.output_dir_var = tk.StringVar(value="--")

        self._apply_style()
        self._build_layout()
        self.root.after(150, self._drain_queue)

    def _apply_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("App.TFrame", background="#edf4f3")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("App.TLabel", background="#edf4f3", foreground="#18302f", font=("Helvetica", 11))
        style.configure("Title.TLabel", background="#edf4f3", foreground="#0f172a", font=("Helvetica", 24, "bold"))
        style.configure("Subtitle.TLabel", background="#edf4f3", foreground="#4b5d5b", font=("Helvetica", 11))
        style.configure("Section.TLabel", background="#ffffff", foreground="#0f172a", font=("Helvetica", 13, "bold"))
        style.configure("Hint.TLabel", background="#ffffff", foreground="#516463", font=("Helvetica", 10))
        style.configure(
            "Accent.TButton",
            background="#0f766e",
            foreground="#ffffff",
            padding=(12, 8),
            font=("Helvetica", 10, "bold"),
            borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", "#115e59")])
        style.configure(
            "Ghost.TButton",
            background="#d8ebe7",
            foreground="#134e4a",
            padding=(10, 8),
            font=("Helvetica", 10),
            borderwidth=0,
        )
        style.map("Ghost.TButton", background=[("active", "#c5e2dc")])
        style.configure("App.TEntry", fieldbackground="#f8fbfb", padding=7)
        style.configure("App.TCombobox", padding=6)

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=18)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer, style="App.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        ttk.Label(header, text="MDP Bone Scintigraphy Lesion Prediction Workstation", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Desktop app: load one NIfTI image, manually draw the ROI C circle and deep-learning bounding box, and generate malignancy probability, Radscore, and prognostic risk stratification.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        sidebar = ttk.Frame(outer, style="Card.TFrame", padding=18)
        sidebar.grid(row=1, column=0, sticky="nsw", padx=(0, 16))
        sidebar.configure(width=390)

        main = ttk.Frame(outer, style="App.TFrame")
        main.grid(row=1, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        self._build_sidebar(sidebar)
        self._build_main(main)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        row = 0
        parent.columnconfigure(0, weight=1)

        ttk.Label(parent, text="Case Input", style="Section.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Label(parent, text="NIfTI File", style="Hint.TLabel").grid(row=row, column=0, sticky="w", pady=(10, 4))
        row += 1
        path_frame = ttk.Frame(parent, style="Card.TFrame")
        path_frame.grid(row=row, column=0, sticky="ew")
        path_frame.columnconfigure(0, weight=1)
        ttk.Entry(path_frame, textvariable=self.file_var, style="App.TEntry").grid(row=0, column=0, sticky="ew")
        ttk.Button(path_frame, text="Browse", style="Ghost.TButton", command=self._choose_file).grid(row=0, column=1, padx=(8, 0))
        row += 1

        ttk.Button(parent, text="Load Image", style="Accent.TButton", command=self._load_image).grid(
            row=row, column=0, sticky="ew", pady=(12, 0)
        )
        row += 1

        ttk.Label(parent, text="Image Display", style="Section.TLabel").grid(row=row, column=0, sticky="w", pady=(22, 0))
        row += 1
        ttk.Label(parent, text="Gray Level", style="Hint.TLabel").grid(row=row, column=0, sticky="w", pady=(10, 4))
        row += 1
        level_frame = ttk.Frame(parent, style="Card.TFrame")
        level_frame.grid(row=row, column=0, sticky="ew")
        level_frame.columnconfigure(0, weight=1)
        self.gray_level_scale = ttk.Scale(
            level_frame,
            orient=tk.HORIZONTAL,
            from_=0.0,
            to=1.0,
            variable=self.gray_level_var,
            command=self._on_gray_control_change,
        )
        self.gray_level_scale.grid(row=0, column=0, sticky="ew")
        ttk.Label(level_frame, textvariable=self.gray_level_text_var, style="Hint.TLabel").grid(row=0, column=1, padx=(10, 0))
        row += 1

        ttk.Label(parent, text="Gray Width", style="Hint.TLabel").grid(row=row, column=0, sticky="w", pady=(10, 4))
        row += 1
        width_frame = ttk.Frame(parent, style="Card.TFrame")
        width_frame.grid(row=row, column=0, sticky="ew")
        width_frame.columnconfigure(0, weight=1)
        self.gray_width_scale = ttk.Scale(
            width_frame,
            orient=tk.HORIZONTAL,
            from_=1.0,
            to=2.0,
            variable=self.gray_width_var,
            command=self._on_gray_control_change,
        )
        self.gray_width_scale.grid(row=0, column=0, sticky="ew")
        ttk.Label(width_frame, textvariable=self.gray_width_text_var, style="Hint.TLabel").grid(row=0, column=1, padx=(10, 0))
        row += 1

        ttk.Button(parent, text="Reset Gray", style="Ghost.TButton", command=self._reset_gray_window).grid(
            row=row, column=0, sticky="ew", pady=(10, 0)
        )
        row += 1
        ttk.Label(
            parent,
            text="These controls only change on-screen grayscale for easier review and annotation. Prediction still uses the original NIfTI pipeline.",
            style="Hint.TLabel",
            wraplength=360,
        ).grid(row=row, column=0, sticky="w", pady=(8, 0))
        row += 1

        ttk.Label(parent, text="Output Directory", style="Hint.TLabel").grid(row=row, column=0, sticky="w", pady=(18, 4))
        row += 1
        out_frame = ttk.Frame(parent, style="Card.TFrame")
        out_frame.grid(row=row, column=0, sticky="ew")
        out_frame.columnconfigure(0, weight=1)
        ttk.Entry(out_frame, textvariable=self.output_var, style="App.TEntry").grid(row=0, column=0, sticky="ew")
        ttk.Button(out_frame, text="Browse", style="Ghost.TButton", command=self._choose_output_dir).grid(
            row=0, column=1, padx=(8, 0)
        )
        row += 1

        ttk.Label(parent, text="Clinical Input", style="Section.TLabel").grid(row=row, column=0, sticky="w", pady=(24, 0))
        row += 1
        ttk.Label(parent, text="Age", style="Hint.TLabel").grid(row=row, column=0, sticky="w", pady=(10, 4))
        row += 1
        ttk.Entry(parent, textvariable=self.age_var, style="App.TEntry").grid(row=row, column=0, sticky="ew")
        row += 1
        ttk.Label(parent, text="Acquisition View Code", style="Hint.TLabel").grid(row=row, column=0, sticky="w", pady=(12, 4))
        row += 1
        ttk.Combobox(
            parent,
            textvariable=self.acquisition_view_var,
            values=list(ACQUISITION_VIEW_OPTIONS.keys()),
            state="readonly",
            style="App.TCombobox",
        ).grid(row=row, column=0, sticky="ew")
        row += 1
        ttk.Label(
            parent,
            text="Confirmed mapping: code 1 = Anterior, code 2 = Posterior.",
            style="Hint.TLabel",
            wraplength=360,
        ).grid(row=row, column=0, sticky="w", pady=(8, 0))
        row += 1

        ttk.Label(parent, text="Annotation Guide", style="Section.TLabel").grid(row=row, column=0, sticky="w", pady=(24, 0))
        row += 1
        ttk.Label(
            parent,
            text="1. Click \"Draw ROI C Circle\" and drag outward from the lesion center.\n2. Click \"Draw Deep Learning Box\" and cover the lesion with some local context.\n3. Only the latest circle and box are kept; simply draw again to replace them.",
            style="Hint.TLabel",
            wraplength=360,
        ).grid(row=row, column=0, sticky="w", pady=(10, 0))
        row += 1

        ttk.Button(parent, text="Start Prediction", style="Accent.TButton", command=self._start_prediction).grid(
            row=row, column=0, sticky="ew", pady=(24, 0)
        )
        row += 1
        ttk.Label(parent, textvariable=self.status_var, style="Hint.TLabel", wraplength=360).grid(
            row=row, column=0, sticky="w", pady=(10, 0)
        )
        row += 1
        ttk.Button(parent, text="Open Output Folder", style="Ghost.TButton", command=self._open_last_output_dir).grid(
            row=row, column=0, sticky="ew", pady=(14, 0)
        )

    def _build_main(self, parent: ttk.Frame) -> None:
        summary = ttk.Frame(parent, style="App.TFrame")
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        for index in range(3):
            summary.columnconfigure(index, weight=1)

        self._build_card(summary, 0, "Malignancy Probability", self.diag_prob_var, self.diag_label_var, "#0f766e", "#ecfeff")
        self._build_card(summary, 1, "Radscore / Total points", self.radscore_var, self.total_points_var, "#1d4ed8", "#eff6ff")
        self._build_card(summary, 2, "Prognostic Risk", self.overall_risk_var, self.solitary_risk_var, "#c2410c", "#fff7ed")

        content = ttk.Frame(parent, style="App.TFrame")
        content.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        viewer_card = ttk.Frame(content, style="Card.TFrame", padding=14)
        viewer_card.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        viewer_card.columnconfigure(0, weight=1)
        viewer_card.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(viewer_card, style="Card.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        toolbar.columnconfigure(0, weight=1)
        ttk.Label(toolbar, text="Lesion Annotation Workspace", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            toolbar,
            text="The viewport is intentionally portrait-oriented for a more natural whole-body review workflow.",
            style="Hint.TLabel",
            wraplength=640,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 10))
        button_row = ttk.Frame(toolbar, style="Card.TFrame")
        button_row.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(button_row, text="Draw ROI C Circle", style="Ghost.TButton", command=lambda: self._set_tool("circle")).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(
            button_row,
            text="Draw Deep Learning Box",
            style="Ghost.TButton",
            command=lambda: self._set_tool("rect"),
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(button_row, text="Clear ROI C", style="Ghost.TButton", command=self._clear_circle).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(button_row, text="Clear Box", style="Ghost.TButton", command=self._clear_rect).pack(
            side=tk.LEFT, padx=6
        )

        canvas_frame = ttk.Frame(viewer_card, style="Card.TFrame")
        canvas_frame.grid(row=1, column=0, sticky="nsew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        self.image_canvas = tk.Canvas(
            canvas_frame,
            width=VIEWPORT_WIDTH,
            height=VIEWPORT_HEIGHT,
            background="#101828",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.image_canvas.grid(row=0, column=0, sticky="nsew")
        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.image_canvas.xview)
        h_scroll.grid(row=1, column=0, sticky="ew")
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.image_canvas.yview)
        v_scroll.grid(row=0, column=1, sticky="ns")
        self.image_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        self.image_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.image_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.image_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        side_panel = ttk.Frame(content, style="App.TFrame")
        side_panel.grid(row=0, column=1, sticky="nsew")
        side_panel.columnconfigure(0, weight=1)
        side_panel.rowconfigure(1, weight=1)

        info_card = ttk.Frame(side_panel, style="Card.TFrame", padding=14)
        info_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        info_card.columnconfigure(0, weight=1)
        ttk.Label(info_card, text="Workspace Notes", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            info_card,
            text="Use the center viewport for lesion marking. Reports and logs are shown on the right so the image area stays tall and easy to inspect.",
            style="Hint.TLabel",
            wraplength=420,
        ).grid(row=1, column=0, sticky="w", pady=(6, 10))
        ttk.Label(info_card, text="Latest Output Folder", style="Hint.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Label(info_card, textvariable=self.output_dir_var, style="Hint.TLabel", wraplength=420).grid(
            row=3, column=0, sticky="w", pady=(4, 0)
        )

        notebook = ttk.Notebook(side_panel)
        notebook.grid(row=1, column=0, sticky="nsew")

        report_tab = ttk.Frame(notebook, style="Card.TFrame", padding=12)
        log_tab = ttk.Frame(notebook, style="Card.TFrame", padding=12)
        notebook.add(report_tab, text="Prediction Report")
        notebook.add(log_tab, text="Run Log")

        self.report_text = ScrolledText(report_tab, height=12, wrap=tk.WORD, font=("Menlo", 11))
        self.report_text.pack(fill=tk.BOTH, expand=True)
        self.report_text.configure(state=tk.DISABLED)

        self.log_text = ScrolledText(log_tab, height=12, wrap=tk.WORD, font=("Menlo", 11))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.configure(state=tk.DISABLED)

    def _build_card(
        self,
        parent: ttk.Frame,
        column: int,
        title: str,
        primary_var: tk.StringVar,
        secondary_var: tk.StringVar,
        accent: str,
        background: str,
    ) -> None:
        card = tk.Frame(parent, bg=background, highlightthickness=0, padx=18, pady=16)
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 12, 0))
        tk.Label(card, text=title, bg=background, fg="#334155", font=("Helvetica", 11, "bold")).pack(anchor="w")
        tk.Label(card, textvariable=primary_var, bg=background, fg=accent, font=("Helvetica", 22, "bold")).pack(
            anchor="w", pady=(14, 4)
        )
        tk.Label(card, textvariable=secondary_var, bg=background, fg="#475569", font=("Helvetica", 10)).pack(anchor="w")

    @staticmethod
    def _is_nifti_path(file_path: str | Path) -> bool:
        name = Path(file_path).name.lower()
        return name.endswith(".nii") or name.endswith(".nii.gz")

    def _choose_file(self) -> None:
        # On macOS, certain native Tk file-type filters can crash the dialog.
        # We therefore open an unfiltered picker and validate the extension after
        # selection instead of relying on `filetypes`.
        file_path = filedialog.askopenfilename(title="Choose a NIfTI File")
        if not file_path:
            return
        if not self._is_nifti_path(file_path):
            messagebox.showerror("Unsupported File", "Please choose a `.nii` or `.nii.gz` file.")
            return
        self.file_var.set(file_path)

    def _choose_output_dir(self) -> None:
        folder_path = filedialog.askdirectory(title="Choose Output Directory")
        if folder_path:
            self.output_var.set(folder_path)

    def _load_image(self) -> None:
        file_path = self.file_var.get().strip()
        if not file_path:
            messagebox.showerror("Missing Input", "Please choose a NIfTI file first.")
            return
        if not self._is_nifti_path(file_path):
            messagebox.showerror("Unsupported File", "Please choose a `.nii` or `.nii.gz` file.")
            return

        try:
            image = read_wbs_image(Path(file_path).expanduser())
            self.bundle = build_render_bundle(image, max_display_height=CANVAS_HEIGHT)
            self._configure_gray_controls()
        except Exception as exc:
            messagebox.showerror("Load Failed", str(exc))
            return

        self._reset_annotations(redraw_only=False)
        self._render_bundle(preserve_annotations=False)
        self.status_var.set("Image loaded. You can adjust grayscale, then draw the ROI C circle and deep-learning box.")

    def _set_tool(self, tool_name: str) -> None:
        if self.bundle is None:
            messagebox.showinfo("Load Image First", "Please load an image before drawing annotations.")
            return
        self.active_tool = tool_name
        if tool_name == "circle":
            self.status_var.set("ROI C mode: drag outward from the lesion center.")
        else:
            self.status_var.set("Deep-learning box mode: drag to cover the lesion.")

    def _clip_to_canvas(self, x_value: float, y_value: float) -> tuple[float, float]:
        if self.bundle is None:
            return 0.0, 0.0
        x_value = max(0.0, min(x_value, self.bundle.display_width - 1))
        y_value = max(0.0, min(y_value, self.bundle.display_height - 1))
        return x_value, y_value

    def _on_canvas_press(self, event: tk.Event) -> None:
        if self.bundle is None or self.active_tool is None:
            return
        x_value = self.image_canvas.canvasx(event.x)
        y_value = self.image_canvas.canvasy(event.y)
        self.drag_start = self._clip_to_canvas(x_value, y_value)
        if self.temp_shape_id is not None:
            self.image_canvas.delete(self.temp_shape_id)
            self.temp_shape_id = None

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if self.bundle is None or self.active_tool is None or self.drag_start is None:
            return

        x_value = self.image_canvas.canvasx(event.x)
        y_value = self.image_canvas.canvasy(event.y)
        x_value, y_value = self._clip_to_canvas(x_value, y_value)
        x0, y0 = self.drag_start

        if self.temp_shape_id is not None:
            self.image_canvas.delete(self.temp_shape_id)

        if self.active_tool == "circle":
            radius = ((x_value - x0) ** 2 + (y_value - y0) ** 2) ** 0.5
            self.temp_shape_id = self.image_canvas.create_oval(
                x0 - radius,
                y0 - radius,
                x0 + radius,
                y0 + radius,
                outline="#f97316",
                width=3,
            )
        elif self.active_tool == "rect":
            self.temp_shape_id = self.image_canvas.create_rectangle(
                x0,
                y0,
                x_value,
                y_value,
                outline="#14b8a6",
                width=3,
            )

    def _on_canvas_release(self, event: tk.Event) -> None:
        if self.bundle is None or self.active_tool is None or self.drag_start is None:
            return

        x_value = self.image_canvas.canvasx(event.x)
        y_value = self.image_canvas.canvasy(event.y)
        x_value, y_value = self._clip_to_canvas(x_value, y_value)
        x0, y0 = self.drag_start

        if self.temp_shape_id is not None:
            self.image_canvas.delete(self.temp_shape_id)
            self.temp_shape_id = None

        if self.active_tool == "circle":
            radius = ((x_value - x0) ** 2 + (y_value - y0) ** 2) ** 0.5
            if radius < 3:
                self.status_var.set("ROI C is too small. Please draw it again.")
            else:
                self.circle_display = {"center_x": x0, "center_y": y0, "radius": radius}
                if self.circle_item_id is not None:
                    self.image_canvas.delete(self.circle_item_id)
                self.circle_item_id = self.image_canvas.create_oval(
                    x0 - radius,
                    y0 - radius,
                    x0 + radius,
                    y0 + radius,
                    outline="#f97316",
                    width=3,
                )
                self.status_var.set("ROI C updated.")

        elif self.active_tool == "rect":
            left = min(x0, x_value)
            top = min(y0, y_value)
            width = abs(x_value - x0)
            height = abs(y_value - y0)
            if width < 3 or height < 3:
                self.status_var.set("The bounding box is too small. Please draw it again.")
            else:
                self.rect_display = {"left": left, "top": top, "width": width, "height": height}
                if self.rect_item_id is not None:
                    self.image_canvas.delete(self.rect_item_id)
                self.rect_item_id = self.image_canvas.create_rectangle(
                    left,
                    top,
                    left + width,
                    top + height,
                    outline="#14b8a6",
                    width=3,
                )
                self.status_var.set("Deep-learning box updated.")

        self.drag_start = None

    def _clear_circle(self) -> None:
        self.circle_display = None
        if self.circle_item_id is not None:
            self.image_canvas.delete(self.circle_item_id)
            self.circle_item_id = None
        self.status_var.set("ROI C cleared.")

    def _clear_rect(self) -> None:
        self.rect_display = None
        if self.rect_item_id is not None:
            self.image_canvas.delete(self.rect_item_id)
            self.rect_item_id = None
        self.status_var.set("Deep-learning box cleared.")

    def _configure_gray_controls(self) -> None:
        if self.bundle is None:
            return
        self.default_display_window = describe_display_window(self.bundle.raw_array)
        self._suspend_gray_updates = True
        try:
            self.gray_level_scale.configure(
                from_=self.default_display_window.level_min,
                to=self.default_display_window.level_max,
            )
            self.gray_width_scale.configure(
                from_=self.default_display_window.width_min,
                to=self.default_display_window.width_max,
            )
            self.gray_level_var.set(self.default_display_window.center)
            self.gray_width_var.set(self.default_display_window.width)
            self._update_gray_labels()
        finally:
            self._suspend_gray_updates = False

    def _update_gray_labels(self) -> None:
        self.gray_level_text_var.set(f"{self.gray_level_var.get():.1f}")
        self.gray_width_text_var.set(f"{self.gray_width_var.get():.1f}")

    def _render_bundle(self, preserve_annotations: bool) -> None:
        if self.bundle is None:
            return
        self.canvas_photo = ImageTk.PhotoImage(self.bundle.display_image)
        self.image_canvas.delete("all")
        self.image_canvas.create_image(0, 0, anchor=tk.NW, image=self.canvas_photo)
        self.image_canvas.configure(scrollregion=(0, 0, self.bundle.display_width, self.bundle.display_height))
        if preserve_annotations:
            self._redraw_annotations()

    def _redraw_annotations(self) -> None:
        self.circle_item_id = None
        self.rect_item_id = None
        if self.circle_display is not None:
            x0 = self.circle_display["center_x"]
            y0 = self.circle_display["center_y"]
            radius = self.circle_display["radius"]
            self.circle_item_id = self.image_canvas.create_oval(
                x0 - radius,
                y0 - radius,
                x0 + radius,
                y0 + radius,
                outline="#f97316",
                width=3,
            )
        if self.rect_display is not None:
            left = self.rect_display["left"]
            top = self.rect_display["top"]
            width = self.rect_display["width"]
            height = self.rect_display["height"]
            self.rect_item_id = self.image_canvas.create_rectangle(
                left,
                top,
                left + width,
                top + height,
                outline="#14b8a6",
                width=3,
            )

    def _on_gray_control_change(self, _value: str = "") -> None:
        self._update_gray_labels()
        if self._suspend_gray_updates or self.bundle is None:
            return
        self.bundle = build_render_bundle_from_array(
            self.bundle.raw_array,
            image=self.bundle.image,
            max_display_height=CANVAS_HEIGHT,
            window_center=self.gray_level_var.get(),
            window_width=self.gray_width_var.get(),
        )
        self._render_bundle(preserve_annotations=True)
        self.status_var.set("Display grayscale updated. Prediction inputs remain unchanged.")

    def _reset_gray_window(self) -> None:
        if self.default_display_window is None:
            return
        self._suspend_gray_updates = True
        try:
            self.gray_level_var.set(self.default_display_window.center)
            self.gray_width_var.set(self.default_display_window.width)
            self._update_gray_labels()
        finally:
            self._suspend_gray_updates = False
        self._on_gray_control_change()

    def _reset_annotations(self, redraw_only: bool) -> None:
        self.circle_display = None
        self.rect_display = None
        self.active_tool = None
        self.drag_start = None
        self.temp_shape_id = None
        self.circle_item_id = None
        self.rect_item_id = None
        if not redraw_only:
            self.diag_prob_var.set("--")
            self.diag_label_var.set("Awaiting prediction")
            self.radscore_var.set("--")
            self.total_points_var.set("--")
            self.overall_risk_var.set("--")
            self.solitary_risk_var.set("--")
            self.output_dir_var.set("--")
            self._set_report("")

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_report(self, text: str) -> None:
        self.report_text.configure(state=tk.NORMAL)
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert("1.0", text)
        self.report_text.configure(state=tk.DISABLED)

    def _build_request(self) -> PredictionRequest:
        file_path = self.file_var.get().strip()
        if not file_path:
            raise ValueError("Please choose a NIfTI file first.")
        if self.bundle is None:
            raise ValueError("Please load the image first.")
        if self.circle_display is None:
            raise ValueError("Please draw the ROI C circle first.")
        if self.rect_display is None:
            raise ValueError("Please draw the deep-learning box first.")

        age_text = self.age_var.get().strip()
        if not age_text:
            raise ValueError("Please enter age.")
        age_value = float(age_text)

        output_root = Path(self.output_var.get().strip() or DEFAULT_OUTPUT_ROOT).expanduser()
        output_root.mkdir(parents=True, exist_ok=True)

        return PredictionRequest(
            nii_path=Path(file_path).expanduser(),
            output_root=output_root,
            age=age_value,
            acquisition_view=ACQUISITION_VIEW_OPTIONS[self.acquisition_view_var.get()],
            circle_display=dict(self.circle_display),
            rect_display=dict(self.rect_display),
        )

    def _start_prediction(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Task Running", "A prediction is already running. Please wait for it to finish.")
            return

        try:
            request = self._build_request()
        except Exception as exc:
            messagebox.showerror("Incomplete Input", str(exc))
            return

        self.status_var.set("Prediction is running. Please wait...")
        self._append_log("========== Starting a new prediction ==========")
        self.worker = threading.Thread(target=self._run_prediction_worker, args=(request,), daemon=True)
        self.worker.start()

    def _run_prediction_worker(self, request: PredictionRequest) -> None:
        try:
            result = run_prediction(request, logger=lambda message: self.log_queue.put(("log", message)))
            self.log_queue.put(("result", result))
        except Exception as exc:
            detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            self.log_queue.put(("error", detail))

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "result":
                    self._handle_result(payload)  # type: ignore[arg-type]
                elif kind == "error":
                    self._handle_error(str(payload))
        except queue.Empty:
            pass
        self.root.after(150, self._drain_queue)

    def _handle_result(self, result: dict) -> None:
        probability = float(result["diagnostic_probability"]) * 100.0
        self.diag_prob_var.set(f"{probability:.2f}%")
        self.diag_label_var.set(result["diagnostic_label"])
        self.radscore_var.set(f"{float(result['radscore']):.4f}")
        self.total_points_var.set(f"Total points {float(result['total_points']):.2f}")

        overall = result["prognosis_calls"]["overall_center1_youden"]
        solitary = result["prognosis_calls"]["solitary_center1_youden"]
        self.overall_risk_var.set(f"Overall cohort: {overall['label']}")
        self.solitary_risk_var.set(f"Solitary lesion: {solitary['label']}")
        self.output_dir_var.set(result["output_dir"])
        self.last_output_dir = result["output_dir"]

        self._set_report(self._format_report(result))
        self._append_log(f"Output folder: {result['output_dir']}")
        self.status_var.set("Prediction completed. You can review the report and open the output folder.")

    def _handle_error(self, detail: str) -> None:
        self._append_log(detail)
        self.status_var.set("Prediction failed. Please review the run log.")
        messagebox.showerror("Prediction Failed", detail)

    def _format_report(self, result: dict) -> str:
        overall = result["prognosis_calls"]["overall_center1_youden"]
        solitary = result["prognosis_calls"]["solitary_center1_youden"]
        top_radscore = result["radscore_contributions"][:5]
        top_diag = result["diagnostic_contributions"]
        acquisition_view = int(result["acquisition_view"])
        acquisition_view_label = ACQUISITION_VIEW_LABELS.get(acquisition_view, "Unknown")

        lines = [
            "MDP Bone Lesion Predictor Report",
            "",
            f"Input image: {result['input_image']}",
            f"Age: {result['age']}",
            f"Acquisition view: {acquisition_view_label} (code {acquisition_view})",
            "",
            f"Radscore: {result['radscore']:.6f}",
            f"Malignancy probability: {result['diagnostic_probability'] * 100.0:.2f}%",
            f"Diagnostic label: {result['diagnostic_label']}",
            f"Total points: {result['total_points']:.6f}",
            "",
            f"Overall cohort threshold {overall['threshold']:.8f}: {overall['label']}",
            f"Solitary-lesion threshold {solitary['threshold']:.8f}: {solitary['label']}",
            "",
            "Diagnostic model contributions:",
        ]
        for row in top_diag:
            lines.append(
                f"- {row['Predictor']}: value={row['Value']:.4f}, weight={row['Weight']:.4f}, contribution={row['Contribution']:.4f}"
            )

        lines.append("")
        lines.append("Top 5 Radscore contributions:")
        for row in top_radscore:
            lines.append(
                f"- {row['Feature']}: standardized={row['Standardized value']:.4f}, weight={row['Weight']:.4f}, contribution={row['Contribution']:.4f}"
            )

        lines.append("")
        lines.append(f"Output folder: {result['output_dir']}")
        return "\n".join(lines)

    def _open_last_output_dir(self) -> None:
        target = self.last_output_dir or self.output_var.get().strip()
        if not target:
            messagebox.showinfo("No Folder Available", "Please set an output directory or run a prediction first.")
            return
        open_in_file_manager(target)

    def run(self) -> None:
        self.root.mainloop()
