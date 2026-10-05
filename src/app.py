"""Survey Tabulator: desktop application.

Pick an SPSS .sav file, choose and order the variables, and export their
weighted frequency tables to Excel and PDF.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.constants import *

import pandas as pd
import pyreadstat

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
    TTKBOOTSTRAP_OK = True
except ImportError:
    from tkinter import ttk
    TTKBOOTSTRAP_OK = False

from config import DEFAULT_CHUNK_SIZE, SPECIAL_CODES, YEAR_COLUMN
from excel_export import write_excel
from pdf_export import write_pdf
from tabulation import accumulate


def bootstyle(name):
    """Keyword arguments for a ttkbootstrap style, or none with plain ttk."""
    return {"bootstyle": name} if TTKBOOTSTRAP_OK else {}


class App:
    _MODIFIER_KEYS = {
        'Control_L', 'Control_R', 'Shift_L', 'Shift_R', 'Alt_L', 'Alt_R',
        'Caps_Lock', 'Tab', 'Super_L', 'Super_R', 'Meta_L', 'Meta_R'
    }

    def __init__(self, root):
        self.root = root
        self.root.title("Survey Tabulator · .sav")
        self.root.geometry("1000x820")
        self.root.minsize(920, 700)

        self.file_path = None
        self.meta = None
        self.busy = False
        self.all_variables = []
        self.special_checkboxes = {}
        self.year_checkboxes = {}
        self.is_longitudinal = False

        self._reset_drag()

        if TTKBOOTSTRAP_OK:
            self.style = ttk.Style(theme="flatly")
        else:
            self.style = ttk.Style()
            self.style.theme_use('clam')

        self.output_format = tk.StringVar(value='excel')
        self.show_total = tk.BooleanVar(value=True)
        self.show_stats = tk.BooleanVar(value=True)

        self._build_ui()

    # ============================================================
    # LAYOUT
    # ============================================================

    def _build_ui(self):
        pad = 16

        frame_top = ttk.Frame(self.root, padding=pad)
        frame_top.pack(fill=X)
        ttk.Label(frame_top, text="Survey Tabulator", font=('Segoe UI', 16, 'bold')).pack(side=LEFT)
        ttk.Button(frame_top, text="📂  Open data file (.sav)", command=self.browse_file,
                   **bootstyle("primary")).pack(side=RIGHT)

        frame_info = ttk.Frame(self.root, padding=(pad, 0))
        frame_info.pack(fill=X)
        self.label_file = ttk.Label(frame_info, text="No file loaded", font=('Segoe UI', 10, 'italic'))
        self.label_file.pack(side=LEFT)

        ttk.Separator(self.root).pack(fill=X, pady=(pad, 0))

        # Packed before the notebook so that a small window never pushes it off screen
        frame_bottom = ttk.Frame(self.root, padding=(pad, 0, pad, pad))
        frame_bottom.pack(side=BOTTOM, fill=X)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True, padx=pad, pady=(10, pad))

        self.tab_variables = ttk.Frame(self.notebook, padding=pad)
        self.notebook.add(self.tab_variables, text="📊 Variables")
        self._build_variables_tab()

        self.tab_settings = ttk.Frame(self.notebook, padding=pad)
        self.notebook.add(self.tab_settings, text="⚙️ Settings")
        self._build_settings_tab()

        self.progress = ttk.Progressbar(frame_bottom, orient=tk.HORIZONTAL, mode='determinate',
                                        **bootstyle("success-striped"))
        self.progress.pack(fill=X, pady=(0, 8))
        frame_status = ttk.Frame(frame_bottom)
        frame_status.pack(fill=X)
        self.label_status = ttk.Label(frame_status, text="Ready")
        self.label_status.pack(side=LEFT)
        self.btn_generate = ttk.Button(frame_status, text="⚙  Generate tables", command=self.start_generation,
                                       **bootstyle("success"))
        self.btn_generate.pack(side=RIGHT)

    def _build_variables_tab(self):
        tab = self.tab_variables
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(2, weight=1)
        tab.rowconfigure(1, weight=1)

        ttk.Label(tab, text="Available variables", font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 4))
        self.entry_search = ttk.Entry(tab)
        self.entry_search.grid(row=0, column=0, sticky='e', pady=(0, 4))
        self.entry_search.bind('<KeyRelease>', self._filter_available)

        frame_left = ttk.Frame(tab)
        frame_left.grid(row=1, column=0, sticky='nsew', padx=(0, 8))
        self.list_available = tk.Listbox(frame_left, selectmode=tk.EXTENDED, exportselection=False,
                                         activestyle='none', borderwidth=0, highlightthickness=1)
        scroll_left = ttk.Scrollbar(frame_left, orient=tk.VERTICAL, command=self.list_available.yview)
        self.list_available.configure(yscrollcommand=scroll_left.set)
        self.list_available.pack(side=LEFT, fill=BOTH, expand=True)
        scroll_left.pack(side=RIGHT, fill=Y)

        frame_buttons = ttk.Frame(tab, padding=8)
        frame_buttons.grid(row=1, column=1, sticky='nsew')
        inner = ttk.Frame(frame_buttons)
        inner.pack(expand=True)

        primary = bootstyle("primary")
        secondary = bootstyle("secondary-outline")
        ttk.Button(inner, text="Add  ▶", command=self.add_selected, width=16, **primary).pack(pady=4)
        ttk.Button(inner, text="Add all  ▶▶", command=self.add_all, width=16, **secondary).pack(pady=(4, 24))
        ttk.Button(inner, text="◀  Remove", command=self.remove_selected, width=16, **primary).pack(pady=4)
        ttk.Button(inner, text="◀◀  Clear", command=self.remove_all, width=16, **secondary).pack(pady=4)

        ttk.Label(tab, text="Selected variables", font=('Segoe UI', 10, 'bold')).grid(row=0, column=2, sticky='w', pady=(0, 4))
        frame_right = ttk.Frame(tab)
        frame_right.grid(row=1, column=2, sticky='nsew', padx=(8, 0))
        self.list_selected = tk.Listbox(frame_right, selectmode=tk.EXTENDED, exportselection=False,
                                        activestyle='none', borderwidth=0, highlightthickness=1)
        scroll_right = ttk.Scrollbar(frame_right, orient=tk.VERTICAL, command=self.list_selected.yview)
        self.list_selected.configure(yscrollcommand=scroll_right.set)
        self.list_selected.pack(side=LEFT, fill=BOTH, expand=True)
        scroll_right.pack(side=RIGHT, fill=Y)

        for listbox in (self.list_available, self.list_selected):
            listbox.bind('<Button-1>', self._on_click)
            listbox.bind('<B1-Motion>', self._on_drag_motion)
            listbox.bind('<ButtonRelease-1>', self._on_drag_release)
            listbox.bind('<<ListboxSelect>>', lambda e: self._update_counters())

        self.label_counter = ttk.Label(tab, text="")
        self.label_counter.grid(row=2, column=0, columnspan=3, sticky='e', pady=(4, 0))

    def _build_settings_tab(self):
        frame_output = ttk.LabelFrame(self.tab_settings, text=" Output ")
        frame_output.pack(fill=X, pady=(0, 15), ipadx=8, ipady=8)

        ttk.Label(frame_output, text="Export format:", font=('Segoe UI', 9, 'bold')).grid(row=0, column=0, sticky='w', padx=8, pady=8)
        radio = bootstyle("primary")
        ttk.Radiobutton(frame_output, text="Excel (.xlsx)", variable=self.output_format, value='excel', **radio).grid(row=0, column=1, padx=4)
        ttk.Radiobutton(frame_output, text="PDF (.pdf)", variable=self.output_format, value='pdf', **radio).grid(row=0, column=2, padx=4)
        ttk.Radiobutton(frame_output, text="Both", variable=self.output_format, value='both', **radio).grid(row=0, column=3, padx=4)

        ttk.Label(frame_output, text="Rows read per block:", font=('Segoe UI', 9, 'bold')).grid(row=1, column=0, sticky='w', padx=8, pady=8)
        self.entry_chunk_size = ttk.Entry(frame_output, width=12)
        self.entry_chunk_size.insert(0, str(DEFAULT_CHUNK_SIZE))
        self.entry_chunk_size.grid(row=1, column=1, sticky='w', padx=4)

        toggle = bootstyle("round-toggle")
        ttk.Checkbutton(frame_output, text="Show the overall 'Total' column/row in the tables",
                        variable=self.show_total, **toggle).grid(row=2, column=0, columnspan=4, sticky='w', padx=8, pady=(8, 0))
        ttk.Checkbutton(frame_output, text="Compute mean and standard deviation for 0-10 and 1-10 scales",
                        variable=self.show_stats, **toggle).grid(row=3, column=0, columnspan=4, sticky='w', padx=8, pady=(8, 0))

        frame_years = ttk.LabelFrame(self.tab_settings, text=" Year filter ")
        frame_years.pack(fill=X, pady=(0, 15), ipadx=8, ipady=8)
        ttk.Label(frame_years, text="Tick the years to include in the document.",
                  font=('Segoe UI', 9), foreground="gray").pack(anchor="w", padx=8, pady=(8, 4))
        self.frame_years_inner = ttk.Frame(frame_years)
        self.frame_years_inner.pack(fill=X, padx=8)
        ttk.Label(self.frame_years_inner, text="Load a .sav file to detect the available years...",
                  font=('Segoe UI', 9, 'italic')).pack(anchor="w")

        frame_special = ttk.LabelFrame(self.tab_settings, text=" Special values ")
        frame_special.pack(fill=BOTH, expand=True, ipadx=8, ipady=8)
        ttk.Label(frame_special,
                  text="Tick the answers (2222, 4444...) to INCLUDE explicitly in the document.\n"
                       "Unticked ones are left out so that they do not distort the valid percentages.",
                  font=('Segoe UI', 9), foreground="gray").pack(anchor="w", padx=8, pady=(8, 12))
        self.frame_codes_inner = ttk.Frame(frame_special)
        self.frame_codes_inner.pack(fill=BOTH, expand=True, padx=8)
        ttk.Label(self.frame_codes_inner, text="Load a .sav file to see the codes it uses...",
                  font=('Segoe UI', 9, 'italic')).pack(anchor="w")

    # ============================================================
    # SELECTION AND DRAG & DROP BETWEEN THE TWO LISTS
    # ============================================================

    def _reset_drag(self):
        self._drag = {
            "widget": None, "indices": [], "items": [], "window": None,
            "dragging": False, "start_x": 0, "start_y": 0, "original_state": {},
            "preview_target": None, "preview_pos": -1, "pending_click": None
        }

    def _snapshot_lists(self):
        return {
            self.list_available: list(self.list_available.get(0, tk.END)),
            self.list_selected: list(self.list_selected.get(0, tk.END))
        }

    def _on_click(self, event):
        widget = event.widget
        try:
            return self._handle_click(widget, event)
        except tk.TclError:
            widget.selection_clear(0, tk.END)
            self._reset_drag()
            self._update_counters()
            return "break"

    def _handle_click(self, widget, event):
        widget.focus_set()
        idx = widget.nearest(event.y)

        other = self.list_selected if widget == self.list_available else self.list_available
        other.selection_clear(0, tk.END)

        # A click below the last item clears the selection
        bbox = widget.bbox(idx)
        if idx == -1 or (bbox and event.y > bbox[1] + bbox[3]):
            widget.selection_clear(0, tk.END)
            self._update_counters()
            return "break"

        is_ctrl = (event.state & 0x0004) != 0
        is_shift = (event.state & 0x0001) != 0

        if not is_ctrl and not is_shift:
            # Clicking inside an existing selection keeps it, so it can be dragged
            if idx not in widget.curselection():
                widget.selection_clear(0, tk.END)
                widget.selection_set(idx)
                widget.activate(idx)
                widget.selection_anchor(idx)
        elif is_ctrl:
            if idx in widget.curselection():
                widget.selection_clear(idx)
            else:
                widget.selection_set(idx)
                widget.activate(idx)
                widget.selection_anchor(idx)
        elif is_shift:
            anchor = self._safe_anchor(widget, idx)
            widget.selection_clear(0, tk.END)
            start, end = sorted([anchor, idx])
            for i in range(start, end + 1):
                widget.selection_set(i)

        self._reset_drag()
        self._drag.update({
            "widget": widget,
            "start_x": event.x_root,
            "start_y": event.y_root,
            "items": [widget.get(i) for i in widget.curselection()],
            "indices": list(widget.curselection()),
            "original_state": self._snapshot_lists(),
        })

        return "break"

    def _on_drag_motion(self, event):
        widget = self._drag.get("widget")
        if not widget:
            return

        if not self._drag["dragging"]:
            dx = abs(event.x_root - self._drag["start_x"])
            dy = abs(event.y_root - self._drag["start_y"])

            if dx > 5 or dy > 5:
                self._drag["dragging"] = True
                self._drag["pending_click"] = None

                selection = sorted(widget.curselection())
                if not selection:
                    idx = widget.nearest(event.y)
                    widget.selection_set(idx)
                    widget.activate(idx)
                    widget.selection_anchor(idx)
                    selection = [idx]

                self._drag["indices"] = selection
                self._drag["items"] = [widget.get(i) for i in selection]
                self._drag["original_state"] = self._snapshot_lists()

                # Floating copy of the dragged items that follows the pointer
                top = tk.Toplevel(self.root)
                top.overrideredirect(True)
                try:
                    top.attributes('-alpha', 0.85)
                except tk.TclError:
                    pass

                ghost = tk.Listbox(top, activestyle='none', borderwidth=1, relief="solid",
                                   font=widget.cget("font"), bg=widget.cget("bg"), fg=widget.cget("fg"),
                                   selectbackground="#0078D7", selectforeground="white")
                for item in self._drag["items"]:
                    ghost.insert(tk.END, item)
                    ghost.selection_set(tk.END)
                ghost.pack(fill=BOTH, expand=True)

                top.geometry(f"250x{len(self._drag['items']) * 18 + 4}")
                self._drag["window"] = top

        if self._drag["dragging"]:
            top = self._drag["window"]
            if top:
                top.geometry(f"+{event.x_root + 15}+{event.y_root + 15}")

            self._update_preview(event, self._get_target_list(event))
            return "break"

    def _get_target_list(self, event):
        target = event.widget.winfo_containing(event.x_root, event.y_root)
        if target in (self.list_available.master, self.list_available):
            return self.list_available
        if target in (self.list_selected.master, self.list_selected):
            return self.list_selected
        return None

    def _update_preview(self, event, target):
        """Redraw both lists as they would look if the items were dropped here."""
        source = self._drag["widget"]
        items = self._drag["items"]

        available = list(self._drag["original_state"][self.list_available])
        selected = list(self._drag["original_state"][self.list_selected])

        if source == self.list_selected:
            selected = [x for x in selected if x not in items]

        pos = -1
        if target == self.list_selected:
            target.delete(0, tk.END)
            for item in selected:
                target.insert(tk.END, item)

            relative_y = event.y_root - target.winfo_rooty()
            if target.size() == 0:
                pos = 0
            else:
                pos = target.nearest(relative_y)
                bbox = target.bbox(pos)
                if bbox and relative_y > bbox[1] + bbox[3] / 2:
                    pos += 1

        changed = (target != self._drag["preview_target"] or pos != self._drag["preview_pos"])
        self._drag["preview_target"] = target
        self._drag["preview_pos"] = pos

        preview = list(selected)
        if target == self.list_selected:
            preview = preview[:pos] + items + preview[pos:]

        self.list_selected.delete(0, tk.END)
        for i, item in enumerate(preview):
            self.list_selected.insert(tk.END, item)
            # The items being dragged are greyed out at the drop position
            if target == self.list_selected and item in items:
                self.list_selected.itemconfig(i, {'fg': '#A0A0A0'})
            else:
                self.list_selected.itemconfig(i, {'fg': 'black'})

        if not changed:
            return

        self.list_available.delete(0, tk.END)
        for item in available:
            self.list_available.insert(tk.END, item)

        if source == self.list_available:
            self.list_available.selection_clear(0, tk.END)
            first_idx = -1
            for i in range(self.list_available.size()):
                if self.list_available.get(i) in items:
                    self.list_available.selection_set(i)
                    if first_idx == -1:
                        first_idx = i
            if first_idx != -1:
                self.list_available.activate(first_idx)
                self.list_available.selection_anchor(first_idx)

        elif source == self.list_selected and target == self.list_selected:
            self.list_selected.selection_clear(0, tk.END)
            for i in range(pos, pos + len(items)):
                self.list_selected.selection_set(i)
            self.list_selected.activate(pos)
            self.list_selected.selection_anchor(pos)

    def _on_drag_release(self, event):
        if not self._drag.get("dragging", False):
            pending = self._drag.get("pending_click")
            widget = self._drag.get("widget")
            if pending is not None and widget:
                widget.selection_clear(0, tk.END)
                widget.selection_set(pending)
                widget.activate(pending)
                widget.selection_anchor(pending)
                self._update_counters()
            return

        if self._drag["window"]:
            self._drag["window"].destroy()
            self._drag["window"] = None

        target = self._get_target_list(event)

        # Only drop where the preview was last drawn
        if target != self._drag["preview_target"]:
            target = None
        else:
            pos = self._drag["preview_pos"]

        source = self._drag["widget"]
        items = self._drag["items"]

        # Undo the preview, then apply the real move
        for listbox, contents in self._drag["original_state"].items():
            listbox.delete(0, tk.END)
            for item in contents:
                listbox.insert(tk.END, item)

        if target == self.list_selected:
            current = [x for x in self.list_selected.get(0, tk.END) if x not in items]
            self.list_selected.delete(0, tk.END)
            for item in current[:pos] + items + current[pos:]:
                self.list_selected.insert(tk.END, item)

            target.focus_set()

            def apply_selection():
                try:
                    target.selection_clear(0, tk.END)
                    for i in range(pos, pos + len(items)):
                        target.selection_set(i)
                    target.activate(pos)
                    target.selection_anchor(pos)
                    target.see(pos)
                except tk.TclError:
                    pass
            self.root.after(50, apply_selection)

        elif target == self.list_available and source == self.list_selected:
            for item in items:
                idx = self.list_selected.get(0, tk.END).index(item)
                self.list_selected.delete(idx)

        self._filter_available()
        self._update_counters()
        self._reset_drag()

        return "break"

    def _filter_available(self, event=None):
        if event is not None and getattr(event, 'keysym', None) in self._MODIFIER_KEYS:
            return

        text = self.entry_search.get().strip().lower()
        selected = set(self.list_selected.get(0, tk.END))

        self.list_available.selection_clear(0, tk.END)
        self.list_available.delete(0, tk.END)
        for variable in self.all_variables:
            if variable in selected:
                continue
            if text in variable.lower():
                self.list_available.insert(tk.END, variable)

        self._reset_drag()
        self._update_counters()

    def _safe_anchor(self, widget, fallback_idx):
        try:
            return int(widget.index(tk.ANCHOR))
        except (tk.TclError, ValueError):
            widget.selection_anchor(fallback_idx)
            return fallback_idx

    def _update_counters(self):
        n_available = self.list_available.size()
        n_selected = self.list_selected.size()
        self.label_counter.config(text=f"{n_available} available · {n_selected} selected")

    def add_selected(self):
        indices = sorted(self.list_available.curselection())
        for variable in [self.list_available.get(idx) for idx in indices]:
            if variable not in self.list_selected.get(0, tk.END):
                self.list_selected.insert(tk.END, variable)
        for idx in reversed(indices):
            self.list_available.delete(idx)
        self._update_counters()

    def add_all(self):
        for variable in self.list_available.get(0, tk.END):
            if variable not in self.list_selected.get(0, tk.END):
                self.list_selected.insert(tk.END, variable)
        self.list_available.delete(0, tk.END)
        self._update_counters()

    def remove_selected(self):
        for idx in sorted(self.list_selected.curselection(), reverse=True):
            self.list_selected.delete(idx)
        self._filter_available()

    def remove_all(self):
        self.list_selected.delete(0, tk.END)
        self._filter_available()

    # ============================================================
    # LOADING A FILE
    # ============================================================

    def browse_file(self):
        path = filedialog.askopenfilename(
            title="Open .sav file",
            filetypes=[("SPSS .sav", "*.sav"), ("All files", "*.*")]
        )
        if path:
            self.load_file(path)

    def load_file(self, path):
        try:
            # Only the dictionary is read here: variable names, labels and value labels
            _, meta = pyreadstat.read_sav(path, metadataonly=True)
            self.file_path = path
            self.meta = meta
            self.all_variables = list(meta.column_names)

            self.list_available.delete(0, tk.END)
            self.list_selected.delete(0, tk.END)
            for variable in self.all_variables:
                self.list_available.insert(tk.END, variable)

            n_rows = getattr(meta, 'number_rows', '?')
            self.label_file.config(
                text=f"📄 {os.path.basename(path)}   ·   {n_rows} rows   ·   {len(self.all_variables)} variables")

            self.is_longitudinal = YEAR_COLUMN in self.all_variables
            # The total column only makes sense next to the per-year columns
            self.show_total.set(self.is_longitudinal)

            if self.is_longitudinal:
                self.label_status.config(text="Scanning the years in the file...")
                self.root.update()

                years = set()
                reader = pyreadstat.read_file_in_chunks(pyreadstat.read_sav, path, chunksize=100000,
                                                        usecols=[YEAR_COLUMN])
                for chunk, _ in reader:
                    years.update(pd.to_numeric(chunk[YEAR_COLUMN], errors='coerce').dropna().astype(int).unique())
                self._show_years(sorted(int(year) for year in years))
            else:
                self._show_years(None)

            found_codes = {}
            for labels in meta.variable_value_labels.values():
                for value, label in labels.items():
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        continue
                    if value in SPECIAL_CODES and value not in found_codes:
                        found_codes[value] = label
            self._show_special_codes(found_codes)

            self.progress['value'] = 0
            self.label_status.config(text="Ready")
            self._update_counters()
            self.notebook.select(self.tab_variables)

        except Exception as e:
            messagebox.showerror("Error", f"The file could not be read:\n{str(e)}")
            self.label_status.config(text="Loading failed")

    def _show_years(self, years):
        for widget in self.frame_years_inner.winfo_children():
            widget.destroy()
        self.year_checkboxes.clear()

        if years is None:
            ttk.Label(self.frame_years_inner,
                      text=f"Single-wave file (no '{YEAR_COLUMN}' column). It will be processed as one block.",
                      font=('Segoe UI', 9, 'italic')).pack(anchor="w")
            self.year_checkboxes[0] = tk.BooleanVar(value=True)
            return

        if not years:
            ttk.Label(self.frame_years_inner, text=f"The '{YEAR_COLUMN}' column has no valid data.",
                      font=('Segoe UI', 9, 'italic')).pack(anchor="w")
            return

        for year in years:
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(self.frame_years_inner, text=str(year), variable=var,
                            **bootstyle("success")).pack(side=LEFT, padx=(0, 20), pady=6)
            self.year_checkboxes[year] = var

    def _show_special_codes(self, found_codes):
        for widget in self.frame_codes_inner.winfo_children():
            widget.destroy()
        self.special_checkboxes.clear()

        if not found_codes:
            ttk.Label(self.frame_codes_inner, text="This file does not use any of the usual special codes.",
                      font=('Segoe UI', 9, 'italic')).pack(anchor="w")
            return

        # Scrollable area with a fixed height, so a long list does not push the layout
        canvas = tk.Canvas(self.frame_codes_inner, borderwidth=0, highlightthickness=0, height=140)
        scrollbar = ttk.Scrollbar(self.frame_codes_inner, orient=VERTICAL, command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        for value, label in sorted(found_codes.items()):
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(scrollable, text=f"{label} ({int(value)})", variable=var,
                            **bootstyle("round-toggle")).pack(anchor="w", pady=4, padx=5)
            self.special_checkboxes[value] = var

    # ============================================================
    # GENERATING THE DOCUMENTS
    # ============================================================

    def start_generation(self):
        if self.busy:
            return
        if self.meta is None:
            messagebox.showerror("Error", "Load a .sav file first")
            return
        if not self.list_selected.size():
            messagebox.showwarning("Warning", "There are no selected variables to process")
            return
        if self._read_chunk_size() is None:
            messagebox.showwarning("Warning", "The block size must be a positive integer")
            return
        if self.year_checkboxes and not any(var.get() for var in self.year_checkboxes.values()):
            messagebox.showwarning("Warning", "Select at least one year.")
            return

        output_format = self.output_format.get()
        if output_format == 'pdf':
            filetypes, extension = [("PDF files", "*.pdf")], ".pdf"
        elif output_format == 'excel':
            filetypes, extension = [("Excel files", "*.xlsx")], ".xlsx"
        else:
            filetypes, extension = [("Excel + PDF (both are written)", "*.xlsx")], ".xlsx"

        output_path = filedialog.asksaveasfilename(
            title="Save as",
            defaultextension=extension,
            filetypes=filetypes + [("All files", "*.*")]
        )
        if output_path:
            self.generate(output_path)

    def _read_chunk_size(self):
        try:
            chunk_size = int(self.entry_chunk_size.get())
        except ValueError:
            return None
        return chunk_size if chunk_size > 0 else None

    def generate(self, output_path):
        """Tabulate the selected variables in a worker thread and write the documents."""
        variables = list(self.list_selected.get(0, tk.END))
        chunk_size = self._read_chunk_size()
        excluded_codes = [value for value, var in self.special_checkboxes.items() if not var.get()]
        selected_years = [year for year, var in self.year_checkboxes.items() if var.get()]
        show_total = self.show_total.get()
        show_stats = self.show_stats.get()
        output_format = self.output_format.get()

        base, _ext = os.path.splitext(output_path)
        excel_path = base + ".xlsx"
        pdf_path = base + ".pdf"

        self.busy = True
        self.btn_generate.config(state=tk.DISABLED)
        self.label_status.config(text="Generating...")
        self.progress['value'] = 0
        self.root.config(cursor="wait")
        self.root.update()

        def worker():
            try:
                # Tk is not thread-safe: progress is handed over to the main loop
                def on_progress(idx, total, message):
                    self.root.after(0, lambda: self._update_progress(idx, total, message))

                data = accumulate(self.file_path, self.meta, variables, excluded_codes, selected_years,
                                  chunk_size=chunk_size, on_progress=on_progress)

                written = []
                if output_format in ('excel', 'both'):
                    write_excel(data, self.meta, variables, excel_path, show_total, show_stats,
                                on_progress=on_progress)
                    written.append(excel_path)
                if output_format in ('pdf', 'both'):
                    write_pdf(data, self.meta, variables, pdf_path, show_total,
                              show_stats=show_stats, on_progress=on_progress)
                    written.append(pdf_path)

                self.root.after(0, self._generation_done, written)
            except Exception as e:
                self.root.after(0, self._generation_failed, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, idx, total, message):
        self.progress['value'] = min(int((idx / total) * 100) if total else 0, 100)
        self.label_status.config(text=f"{message} ({min(idx + 1, total)}/{total})" if total else message)
        self.root.update_idletasks()

    def _generation_done(self, paths):
        self.busy = False
        self.btn_generate.config(state=tk.NORMAL)
        self.progress['value'] = 100
        names = ", ".join(os.path.basename(p) for p in paths)
        self.label_status.config(text=f"✔ Generated: {names}")
        self.root.config(cursor="")
        messagebox.showinfo("Done", "File(s) generated:\n" + "\n".join(paths))

    def _generation_failed(self, error):
        self.busy = False
        self.btn_generate.config(state=tk.NORMAL)
        self.progress['value'] = 0
        self.label_status.config(text="✖ Generation failed")
        self.root.config(cursor="")
        messagebox.showerror("Error", f"Generation failed:\n{error}")


def main():
    if TTKBOOTSTRAP_OK:
        root = ttk.Window(themename="flatly")
    else:
        root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
