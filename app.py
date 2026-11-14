"""Desktop interface for the clipper command-line tool."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any


BG = "#111827"
PANEL = "#1f2937"
PANEL_LIGHT = "#273449"
TEXT = "#f3f4f6"
MUTED = "#9ca3af"
ACCENT = "#38bdf8"
SUCCESS = "#34d399"
ERROR = "#fb7185"


class ClipperApp(tk.Tk):
    """Provide a focused desktop workflow for creating and reviewing clips."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Clipper Studio")
        self.geometry("1080x760")
        self.minsize(900, 650)
        self.configure(bg=BG)

        self.process: subprocess.Popen[str] | None = None
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "clips_output"))
        self.source = tk.StringVar()
        self.clip_count = tk.IntVar(value=8)
        self.minimum = tk.IntVar(value=20)
        self.maximum = tk.IntVar(value=55)
        self.model = tk.StringVar(value="small")
        self.format = tk.StringVar(value="vertical")
        self.captions = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Ready to create clips")
        self.progress = tk.DoubleVar(value=0)
        self.log_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self._configure_styles()
        self._build_ui()
        self.after(100, self._drain_queue)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL_LIGHT)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Heading.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 22, "bold"))
        style.configure("Section.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 11, "bold"))
        style.configure("TButton", background=PANEL_LIGHT, foreground=TEXT, borderwidth=0, padding=(12, 8))
        style.map("TButton", background=[("active", "#334155")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#082f49", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#7dd3fc")])
        style.configure("TEntry", borderwidth=0, padding=8)
        style.configure("TSpinbox", borderwidth=0, padding=6)
        style.configure("TCombobox", borderwidth=0, padding=6)
        style.configure("Horizontal.TProgressbar", troughcolor=PANEL_LIGHT, background=ACCENT, borderwidth=0)
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=32, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL_LIGHT, foreground=MUTED, relief="flat")
        style.map("Treeview", background=[("selected", "#075985")])

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=28)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 20))
        ttk.Label(header, text="Clipper Studio", style="Heading.TLabel").pack(side="left")
        ttk.Label(header, text="Find the moments worth sharing", style="Muted.TLabel").pack(side="left", padx=16, pady=(8, 0))
        self.open_folder_button = ttk.Button(header, text="Open output folder", command=self._open_output)
        self.open_folder_button.pack(side="right")

        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=0, minsize=330)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        settings = ttk.Frame(content, style="Panel.TFrame", padding=20)
        settings.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        self._build_settings(settings)

        results = ttk.Frame(content)
        results.grid(row=0, column=1, sticky="nsew")
        results.rowconfigure(1, weight=1)
        results.columnconfigure(0, weight=1)
        ttk.Label(results, text="Rendered clips", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.clips = ttk.Treeview(results, columns=("title", "duration", "score", "file"), show="headings", selectmode="browse")
        self.clips.heading("title", text="Title")
        self.clips.heading("duration", text="Duration")
        self.clips.heading("score", text="Score")
        self.clips.heading("file", text="File")
        self.clips.column("title", width=290, anchor="w")
        self.clips.column("duration", width=85, anchor="center")
        self.clips.column("score", width=80, anchor="center")
        self.clips.column("file", width=220, anchor="w")
        self.clips.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(results, orient="vertical", command=self.clips.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.clips.configure(yscrollcommand=scrollbar.set)
        self.clips.bind("<Double-1>", self._open_selected_clip)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(18, 0))
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel").pack(side="left")
        self.progress_bar = ttk.Progressbar(footer, variable=self.progress, maximum=100, length=230)
        self.progress_bar.pack(side="right", padx=(12, 0))
        self.start_button = ttk.Button(footer, text="Create clips", style="Accent.TButton", command=self._start)
        self.start_button.pack(side="right")

    def _build_settings(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Create a new batch", style="Section.TLabel").pack(anchor="w", pady=(0, 18))
        ttk.Label(parent, text="Video source").pack(anchor="w")
        source_row = ttk.Frame(parent, style="Panel.TFrame")
        source_row.pack(fill="x", pady=(5, 16))
        ttk.Entry(source_row, textvariable=self.source).pack(side="left", fill="x", expand=True)
        ttk.Button(source_row, text="Browse", command=self._browse_source).pack(side="right", padx=(8, 0))

        ttk.Label(parent, text="Output folder").pack(anchor="w")
        output_row = ttk.Frame(parent, style="Panel.TFrame")
        output_row.pack(fill="x", pady=(5, 16))
        ttk.Entry(output_row, textvariable=self.output_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(output_row, text="Browse", command=self._browse_output).pack(side="right", padx=(8, 0))

        grid = ttk.Frame(parent, style="Panel.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)
        self._field(grid, "Clips", self.clip_count, 0, 0, 1, 8)
        self._field(grid, "Min seconds", self.minimum, 0, 2, 1, 20)
        self._field(grid, "Max seconds", self.maximum, 1, 0, 1, 55)
        ttk.Label(grid, text="Model").grid(row=1, column=2, sticky="w", pady=(14, 0))
        ttk.Combobox(grid, textvariable=self.model, values=("tiny", "base", "small", "medium", "large-v3"), state="readonly", width=10).grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=(14, 0))

        ttk.Label(parent, text="Video format").pack(anchor="w", pady=(22, 5))
        format_row = ttk.Frame(parent, style="Panel.TFrame")
        format_row.pack(fill="x")
        ttk.Radiobutton(format_row, text="Vertical 9:16", variable=self.format, value="vertical").pack(side="left")
        ttk.Radiobutton(format_row, text="Original", variable=self.format, value="original").pack(side="left", padx=18)
        ttk.Checkbutton(parent, text="Burn in captions", variable=self.captions).pack(anchor="w", pady=(13, 0))

        ttk.Label(parent, text="Activity", style="Section.TLabel").pack(anchor="w", pady=(28, 10))
        self.log = tk.Text(parent, height=8, bg="#0f172a", fg=MUTED, insertbackground=TEXT, relief="flat", wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)

    @staticmethod
    def _field(parent: ttk.Frame, label: str, variable: tk.Variable, row: int, label_column: int, entry_column: int, default: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=label_column, sticky="w", pady=(0 if row == 0 else 14, 0))
        ttk.Spinbox(parent, textvariable=variable, from_=1, to=999, width=8).grid(row=row, column=entry_column, sticky="ew", padx=(8, 18), pady=(0 if row == 0 else 14, 0))

    def _browse_source(self) -> None:
        path = filedialog.askopenfilename(title="Choose a video")
        if path:
            self.source.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.output_dir.set(path)

    def _start(self) -> None:
        if self.process is not None:
            return
        source = self.source.get().strip()
        if not source:
            messagebox.showwarning("Source required", "Choose a video file or enter a video URL.")
            return
        if self.minimum.get() <= 0 or self.maximum.get() < self.minimum.get() or self.clip_count.get() <= 0:
            messagebox.showwarning("Invalid settings", "Check the clip count and duration range.")
            return
        command = [
            sys.executable, str(Path(__file__).with_name("clipper.py")), source,
            "--out", self.output_dir.get(), "--num", str(self.clip_count.get()),
            "--min", str(self.minimum.get()), "--max", str(self.maximum.get()),
            "--format", self.format.get(), "--model", self.model.get(),
        ]
        if not self.captions.get():
            command.append("--no-captions")
        self._clear_results()
        self._write_log("$ " + " ".join(command))
        self.progress.set(0)
        self.status.set("Preparing...")
        self.start_button.configure(state="disabled")
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self._read_process, args=(self.process,), daemon=True).start()

    def _read_process(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            self.log_queue.put(("log", line.rstrip()))
            if line.startswith("[") and "/4]" in line:
                try:
                    stage = int(line[1])
                    self.log_queue.put(("progress", (stage - 1) * 25))
                except ValueError:
                    pass
        code = process.wait()
        self.log_queue.put(("finished", code))

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, value = self.log_queue.get_nowait()
                if kind == "log":
                    self._write_log(str(value))
                    if value.startswith("[") and "/4]" in value:
                        self.status.set(str(value)[5:])
                elif kind == "progress":
                    self.progress.set(float(value))
                else:
                    self.process = None
                    self.start_button.configure(state="normal")
                    if value == 0:
                        self.progress.set(100)
                        self.status.set("Complete")
                        self._load_results()
                    else:
                        self.status.set("Failed - see activity log")
                        messagebox.showerror("Clip creation failed", "The clipper process failed. See the activity log for details.")
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _load_results(self) -> None:
        path = Path(self.output_dir.get()) / "clips.json"
        if not path.exists():
            return
        try:
            results = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._write_log(f"Could not read results: {exc}")
            return
        for item in results:
            self.clips.insert("", "end", values=(
                item.get("title_suggestion", "Clip"),
                f"{float(item.get('duration', 0)):.1f}s",
                f"{float(item.get('score', 0)):.2f}",
                Path(str(item.get("file", ""))).name,
            ), tags=(str(item.get("file", "")),))

    def _clear_results(self) -> None:
        for item in self.clips.get_children():
            self.clips.delete(item)

    def _write_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _open_selected_clip(self, _event: tk.Event[tk.Misc]) -> None:
        selection = self.clips.selection()
        if not selection:
            return
        path = self.clips.item(selection[0], "tags")
        if path and Path(path[0]).exists():
            os.startfile(path[0])

    def _open_output(self) -> None:
        path = Path(self.output_dir.get())
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)


if __name__ == "__main__":
    ClipperApp().mainloop()
