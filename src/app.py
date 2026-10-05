"""Survey Tabulator: desktop application.

Pick an SPSS .sav file, choose and order the variables, and export their
weighted frequency tables to Excel and PDF.
"""

import multiprocessing
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.constants import *

import pyreadstat

import settings

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
    TTKBOOTSTRAP_OK = True
except ImportError:
    from tkinter import ttk
    TTKBOOTSTRAP_OK = False

from config import DEFAULT_CHUNK_SIZE, SPECIAL_CODES
from excel_export import write_excel
from i18n import LANGUAGES, load_language, save_language, ui_texts
from pdf_export import write_pdf
from tabulation import Cancelled, accumulate, default_columns, scan_years


def bootstyle(name):
    """Keyword arguments for a ttkbootstrap style, or none with plain ttk."""
    return {"bootstyle": name} if TTKBOOTSTRAP_OK else {}


class App:
    _MODIFIER_KEYS = {
        'Control_L', 'Control_R', 'Shift_L', 'Shift_R', 'Alt_L', 'Alt_R',
        'Caps_Lock', 'Tab', 'Super_L', 'Super_R', 'Meta_L', 'Meta_R'
    }

    def __init__(self, root, language=None):
        self.root = root
        # As tall as the settings tab needs, but never taller than the screen
        height = max(680, min(900, self.root.winfo_screenheight() - 90))
        self.root.geometry(f"1000x{height}")
        self.root.minsize(920, 660)

        self.language = language or load_language()
        self.texts = ui_texts(self.language)

        self.file_path = None
        self.meta = None
        self.busy = False
        self.scanning = False
        self.all_variables = []
        # Which columns of the loaded file hold the wave and the weights
        self.columns = {'year': None, 'weight': None, 'online_weight': None}
        self.column_boxes = {}
        # What the loaded file declares; the settings tab is drawn from these
        self.years = None            # None: single wave, []: no valid data, [..]: the waves
        self.special_codes = {}
        self.year_checkboxes = {}
        self.special_checkboxes = {}
        self._status = ('ready', {})

        self._reset_drag()

        if TTKBOOTSTRAP_OK:
            self.style = ttk.Style(theme="flatly")
        else:
            self.style = ttk.Style()
            self.style.theme_use('clam')

        self.output_format = tk.StringVar(value='excel')
        self.show_total = tk.BooleanVar(value=True)
        self.show_stats = tk.BooleanVar(value=True)
        self.chunk_size = tk.StringVar(value=str(DEFAULT_CHUNK_SIZE))
        self.language_var = tk.StringVar(value=self.language)

        # Worker threads never touch the widgets: they leave their updates here
        # and the main loop applies them.
        self._inbox = queue.Queue()
        self._cancel = threading.Event()
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self._build_ui()
        self.root.after(40, self._drain_inbox)

    def tr(self, key, **values):
        text = self.texts[key]
        return text.format(**values) if values else text

    def _post(self, function, *args):
        self._inbox.put((function, args))

    def _drain_inbox(self):
        try:
            while True:
                function, args = self._inbox.get_nowait()
                function(*args)
        except queue.Empty:
            pass
        self.root.after(40, self._drain_inbox)

    def _on_close(self):
        # Stops a job under way, so that no worker process outlives the window
        self._cancel.set()
        self.root.destroy()

    def _set_status(self, key, **values):
        self._status = (key, values)
        self.label_status.config(text=self.tr(key, **values))

    # ============================================================
    # LAYOUT
    # ============================================================

    def _build_ui(self):
        pad = 16
        self.root.title(self.tr('window_title'))

        self.container = ttk.Frame(self.root)
        self.container.pack(fill=BOTH, expand=True)

        frame_top = ttk.Frame(self.container, padding=pad)
        frame_top.pack(fill=X)
        ttk.Label(frame_top, text=self.tr('app_title'), font=('Segoe UI', 16, 'bold')).pack(side=LEFT)
        ttk.Button(frame_top, text=self.tr('open_file'), command=self.browse_file,
                   **bootstyle("primary")).pack(side=RIGHT)

        frame_info = ttk.Frame(self.container, padding=(pad, 0))
        frame_info.pack(fill=X)
        self.label_file = ttk.Label(frame_info, font=('Segoe UI', 10, 'italic'))
        self.label_file.pack(side=LEFT)
        self._show_file_info()

        ttk.Separator(self.container).pack(fill=X, pady=(pad, 0))

        # Packed before the notebook so that a small window never pushes it off screen
        frame_bottom = ttk.Frame(self.container, padding=(pad, 0, pad, pad))
        frame_bottom.pack(side=BOTTOM, fill=X)

        self.notebook = ttk.Notebook(self.container)
        self.notebook.pack(fill=BOTH, expand=True, padx=pad, pady=(10, pad))

        self.tab_variables = ttk.Frame(self.notebook, padding=pad)
        self.notebook.add(self.tab_variables, text=self.tr('tab_variables'))
        self._build_variables_tab()

        self.tab_settings = ttk.Frame(self.notebook, padding=pad)
        self.notebook.add(self.tab_settings, text=self.tr('tab_settings'))
        self._build_settings_tab()

        self.progress = ttk.Progressbar(frame_bottom, orient=tk.HORIZONTAL, mode='determinate',
                                        **bootstyle("success-striped"))
        self.progress.pack(fill=X, pady=(0, 8))
        frame_status = ttk.Frame(frame_bottom)
        frame_status.pack(fill=X)
        self.label_status = ttk.Label(frame_status)
        self.label_status.pack(side=LEFT)
        self._set_status(*self._status[:1], **self._status[1])
        self.btn_generate = ttk.Button(frame_status, command=self._on_generate_button)
        self.btn_generate.pack(side=RIGHT)
        self._show_generate_button()

    def _show_generate_button(self):
        # While a job runs, the same button cancels it
        if self.busy:
            self.btn_generate.config(text=self.tr('cancel'), **bootstyle("danger"))
        else:
            self.btn_generate.config(text=self.tr('generate'), state=tk.NORMAL, **bootstyle("success"))

    def _on_generate_button(self):
        if self.busy:
            self._cancel.set()
            self.btn_generate.config(state=tk.DISABLED)
            self._set_status('cancelling')
        else:
            self.start_generation()

    def _build_variables_tab(self):
        tab = self.tab_variables
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(2, weight=1)
        tab.rowconfigure(1, weight=1)

        ttk.Label(tab, text=self.tr('available'), font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 4))
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
        ttk.Button(inner, text=self.tr('add'), command=self.add_selected, width=16, **primary).pack(pady=4)
        ttk.Button(inner, text=self.tr('add_all'), command=self.add_all, width=16, **secondary).pack(pady=(4, 24))
        ttk.Button(inner, text=self.tr('remove'), command=self.remove_selected, width=16, **primary).pack(pady=4)
        ttk.Button(inner, text=self.tr('clear'), command=self.remove_all, width=16, **secondary).pack(pady=4)

        ttk.Label(tab, text=self.tr('selected'), font=('Segoe UI', 10, 'bold')).grid(row=0, column=2, sticky='w', pady=(0, 4))
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
        frame_language = ttk.LabelFrame(self.tab_settings, text=self.tr('language_frame'))
        frame_language.pack(fill=X, pady=(0, 8), ipadx=8, ipady=2)
        radio = bootstyle("primary")
        for column, (code, name) in enumerate(LANGUAGES.items()):
            ttk.Radiobutton(frame_language, text=name, variable=self.language_var, value=code,
                            command=self._on_language_change, **radio).grid(row=0, column=column, padx=(8, 12), pady=6)
        ttk.Label(frame_language, text=self.tr('language_hint'), font=('Segoe UI', 9),
                  foreground="gray").grid(row=0, column=len(LANGUAGES), sticky='w', padx=(12, 8))

        frame_output = ttk.LabelFrame(self.tab_settings, text=self.tr('output_frame'))
        frame_output.pack(fill=X, pady=(0, 8), ipadx=8, ipady=4)

        ttk.Label(frame_output, text=self.tr('export_format'), font=('Segoe UI', 9, 'bold')).grid(row=0, column=0, sticky='w', padx=8, pady=6)
        ttk.Radiobutton(frame_output, text="Excel (.xlsx)", variable=self.output_format, value='excel', **radio).grid(row=0, column=1, padx=4)
        ttk.Radiobutton(frame_output, text="PDF (.pdf)", variable=self.output_format, value='pdf', **radio).grid(row=0, column=2, padx=4)
        ttk.Radiobutton(frame_output, text=self.tr('both'), variable=self.output_format, value='both', **radio).grid(row=0, column=3, padx=4)

        ttk.Label(frame_output, text=self.tr('rows_per_block'), font=('Segoe UI', 9, 'bold')).grid(row=1, column=0, sticky='w', padx=8, pady=6)
        ttk.Entry(frame_output, width=12, textvariable=self.chunk_size).grid(row=1, column=1, sticky='w', padx=4)

        toggle = bootstyle("round-toggle")
        ttk.Checkbutton(frame_output, text=self.tr('show_total'),
                        variable=self.show_total, **toggle).grid(row=2, column=0, columnspan=4, sticky='w', padx=8, pady=(6, 0))
        ttk.Checkbutton(frame_output, text=self.tr('show_stats'),
                        variable=self.show_stats, **toggle).grid(row=3, column=0, columnspan=4, sticky='w', padx=8, pady=(6, 0))

        # The wave and weight columns are picked from the variables of the file
        frame_columns = ttk.LabelFrame(self.tab_settings, text=self.tr('columns_frame'))
        frame_columns.pack(fill=X, pady=(0, 8), ipadx=8, ipady=2)
        self.column_boxes = {}
        for position, role in enumerate(('year', 'weight', 'online_weight')):
            ttk.Label(frame_columns, text=self.tr('column_' + role), font=('Segoe UI', 9, 'bold')).grid(
                row=0, column=2 * position, sticky='w', padx=(8, 4), pady=6)
            box = ttk.Combobox(frame_columns, state='readonly', width=20)
            box.grid(row=0, column=2 * position + 1, sticky='w', padx=(0, 12))
            box.bind('<<ComboboxSelected>>', lambda event, role=role: self._on_column_change(role))
            self.column_boxes[role] = box
        self._show_columns()

        frame_years = ttk.LabelFrame(self.tab_settings, text=self.tr('year_frame'))
        frame_years.pack(fill=X, pady=(0, 8), ipadx=8, ipady=2)
        self.frame_years_inner = ttk.Frame(frame_years)
        self.frame_years_inner.pack(side=LEFT, padx=8, pady=4)
        ttk.Label(frame_years, text=self.tr('year_hint'),
                  font=('Segoe UI', 9), foreground="gray").pack(side=LEFT, padx=(12, 8))

        frame_special = ttk.LabelFrame(self.tab_settings, text=self.tr('special_frame'))
        frame_special.pack(fill=BOTH, expand=True, ipadx=8, ipady=6)
        ttk.Label(frame_special, text=self.tr('special_hint'),
                  font=('Segoe UI', 9), foreground="gray").pack(anchor="w", padx=8, pady=(4, 6))
        self.frame_codes_inner = ttk.Frame(frame_special)
        self.frame_codes_inner.pack(fill=BOTH, expand=True, padx=8)

        self._show_years()
        self._show_special_codes()

    def _show_columns(self):
        none = self.tr('column_none')
        for role, box in self.column_boxes.items():
            box.config(values=[none] + self.all_variables, state='readonly' if self.meta is not None else 'disabled')
            box.set(self.columns[role] or none)

    def _on_column_change(self, role):
        if self.busy:
            self._show_columns()
            return
        chosen = self.column_boxes[role].get()
        self.columns[role] = chosen if chosen in self.all_variables else None
        # Remembered, so that files with the same layout open ready to use
        settings.update(columns=dict(self.columns))
        if role == 'year':
            self._refresh_years()

    def _on_language_change(self):
        language = self.language_var.get()
        if language == self.language:
            return
        if self.busy:
            # The running job keeps the language it started with
            self.language_var.set(self.language)
            return
        self.language = language
        self.texts = ui_texts(language)
        save_language(language)
        self._rebuild_ui()

    def _rebuild_ui(self):
        """Redraw the whole window in the current language, keeping its state."""
        selected = list(self.list_selected.get(0, tk.END))
        search = self.entry_search.get()
        tab = self.notebook.index(self.notebook.select())
        progress = self.progress['value']

        self.container.destroy()
        self._reset_drag()
        self._build_ui()

        for variable in selected:
            self.list_selected.insert(tk.END, variable)
        self.entry_search.insert(0, search)
        self._filter_available()
        self.notebook.select(tab)
        self.progress['value'] = progress

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
        if not self.all_variables:
            self.label_counter.config(text="")
            return
        self.label_counter.config(text=self.tr('counter', available=self.list_available.size(),
                                               selected=self.list_selected.size()))

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
        if self.busy:
            return
        path = filedialog.askopenfilename(
            title=self.tr('open_title'),
            filetypes=[(self.tr('type_sav'), "*.sav"), (self.tr('type_all'), "*.*")]
        )
        if path:
            self.load_file(path)

    def _show_file_info(self):
        if self.meta is None:
            self.label_file.config(text=self.tr('no_file'))
            return
        self.label_file.config(text=self.tr(
            'file_info', name=os.path.basename(self.file_path),
            rows=getattr(self.meta, 'number_rows', '?'), variables=len(self.all_variables)))

    def load_file(self, path):
        try:
            # Only the dictionary is read here: variable names, labels and value labels
            _, meta = pyreadstat.read_sav(path, metadataonly=True)
        except Exception as e:
            messagebox.showerror(self.tr('error'), self.tr('read_failed', error=str(e)))
            self._set_status('load_failed')
            return

        self.file_path = path
        self.meta = meta
        self.all_variables = list(meta.column_names)

        self.list_selected.delete(0, tk.END)
        self.entry_search.delete(0, tk.END)
        self._filter_available()
        self._show_file_info()

        self.columns = default_columns(self.all_variables, settings.load().get('columns'))
        self._show_columns()

        self.special_codes = {}
        for labels in meta.variable_value_labels.values():
            for value, label in labels.items():
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                if value in SPECIAL_CODES and value not in self.special_codes:
                    self.special_codes[value] = label
        self.special_checkboxes = {value: tk.BooleanVar(value=False) for value in self.special_codes}
        self._show_special_codes()

        self.progress['value'] = 0
        self.notebook.select(self.tab_variables)
        self._refresh_years()

    def _refresh_years(self):
        """Find the waves of the file in the column currently chosen for them."""
        path, year_column = self.file_path, self.columns['year']
        is_longitudinal = year_column is not None
        # The total column only makes sense next to the per-year columns
        self.show_total.set(is_longitudinal)

        self.years = None
        self.year_checkboxes = {0: tk.BooleanVar(value=True)} if not is_longitudinal else {}
        self.scanning = is_longitudinal
        self._show_years()
        self._set_status('year_scanning' if is_longitudinal else 'ready')

        if is_longitudinal:
            # Finding the waves means a pass over the whole file: done in the
            # background so that the window stays usable meanwhile.
            def scan():
                try:
                    years = scan_years(path, year_column)
                except Exception:
                    years = []
                self._post(self._years_scanned, path, year_column, years)

            threading.Thread(target=scan, daemon=True).start()

    def _years_scanned(self, path, year_column, years):
        if path != self.file_path or year_column != self.columns['year']:
            return      # another file or another column was chosen in the meantime
        self.scanning = False
        self.years = years
        self.year_checkboxes = {year: tk.BooleanVar(value=True) for year in years}
        self._show_years()
        if not self.busy:
            self._set_status('ready')

    def _show_years(self):
        for widget in self.frame_years_inner.winfo_children():
            widget.destroy()

        def note(key, **values):
            ttk.Label(self.frame_years_inner, text=self.tr(key, **values),
                      font=('Segoe UI', 9, 'italic')).pack(anchor="w")

        if self.meta is None:
            note('year_placeholder')
        elif self.scanning:
            note('year_scanning')
        elif self.years is None:
            note('year_single')
        elif not self.years:
            note('year_empty', column=self.columns['year'])
        else:
            for year in self.years:
                ttk.Checkbutton(self.frame_years_inner, text=str(year), variable=self.year_checkboxes[year],
                                **bootstyle("success")).pack(side=LEFT, padx=(0, 20), pady=6)

    def _show_special_codes(self):
        for widget in self.frame_codes_inner.winfo_children():
            widget.destroy()

        if not self.special_codes:
            key = 'special_placeholder' if self.meta is None else 'special_none'
            ttk.Label(self.frame_codes_inner, text=self.tr(key), font=('Segoe UI', 9, 'italic')).pack(anchor="w")
            return

        # Scrollable area with a fixed height, so a long list does not push the layout
        canvas = tk.Canvas(self.frame_codes_inner, borderwidth=0, highlightthickness=0, height=130)
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

        for value, label in sorted(self.special_codes.items()):
            ttk.Checkbutton(scrollable, text=f"{label} ({int(value)})", variable=self.special_checkboxes[value],
                            **bootstyle("round-toggle")).pack(anchor="w", pady=4, padx=5)

    # ============================================================
    # GENERATING THE DOCUMENTS
    # ============================================================

    def start_generation(self):
        if self.busy:
            return
        if self.meta is None:
            messagebox.showerror(self.tr('error'), self.tr('need_file'))
            return
        if self.scanning:
            messagebox.showwarning(self.tr('warning'), self.tr('wait_scan'))
            return
        if not self.list_selected.size():
            messagebox.showwarning(self.tr('warning'), self.tr('need_variables'))
            return
        if self._read_chunk_size() is None:
            messagebox.showwarning(self.tr('warning'), self.tr('need_chunk_size'))
            return
        if self.year_checkboxes and not any(var.get() for var in self.year_checkboxes.values()):
            messagebox.showwarning(self.tr('warning'), self.tr('need_year'))
            return

        # Unweighted tables are a legitimate choice, but never a silent one
        if self.columns['weight'] is None and not messagebox.askyesno(
                self.tr('warning'), self.tr('confirm_unweighted')):
            self.notebook.select(self.tab_settings)
            return

        output_format = self.output_format.get()
        if output_format == 'pdf':
            filetypes, extension = [(self.tr('type_pdf'), "*.pdf")], ".pdf"
        elif output_format == 'excel':
            filetypes, extension = [(self.tr('type_excel'), "*.xlsx")], ".xlsx"
        else:
            filetypes, extension = [(self.tr('type_both'), "*.xlsx")], ".xlsx"

        output_path = filedialog.asksaveasfilename(
            title=self.tr('save_title'),
            defaultextension=extension,
            filetypes=filetypes + [(self.tr('type_all'), "*.*")]
        )
        if output_path:
            self.generate(output_path)

    def _read_chunk_size(self):
        try:
            chunk_size = int(self.chunk_size.get())
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
        language = self.language
        path, meta, columns = self.file_path, self.meta, dict(self.columns)

        base, _ext = os.path.splitext(output_path)
        excel_path = base + ".xlsx"
        pdf_path = base + ".pdf"

        self.busy = True
        self._cancel.clear()
        self._show_generate_button()
        self._set_status('generating')
        self.progress['value'] = 0
        self.root.config(cursor="wait")
        self.root.update()

        def worker():
            try:
                def on_progress(stage, done, total, detail):
                    if self._cancel.is_set():
                        raise Cancelled()
                    self._post(self._update_progress, stage, done, total, detail)

                data = accumulate(path, meta, variables, excluded_codes, selected_years,
                                  chunk_size=chunk_size, on_progress=on_progress, columns=columns)

                written = []
                if output_format in ('excel', 'both'):
                    write_excel(data, meta, variables, excel_path, show_total, show_stats,
                                on_progress=on_progress, language=language)
                    written.append(excel_path)
                if output_format in ('pdf', 'both'):
                    write_pdf(data, meta, variables, pdf_path, show_total, show_stats=show_stats,
                              on_progress=on_progress, language=language)
                    written.append(pdf_path)

                self._post(self._generation_done, written)
            except Cancelled:
                self._post(self._generation_cancelled)
            except Exception as e:
                self._post(self._generation_failed, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, stage, done, total, detail):
        if not self.busy or self._cancel.is_set():
            return
        self.progress['value'] = min(int(done / total * 100) if total else 0, 100)
        self._set_status('stage_' + stage, done=done, total=total, detail=detail)

    def _generation_finished(self, progress):
        self.busy = False
        self._show_generate_button()
        self.progress['value'] = progress
        self.root.config(cursor="")

    def _generation_done(self, paths):
        self._generation_finished(100)
        self._set_status('generated', names=", ".join(os.path.basename(p) for p in paths))
        messagebox.showinfo(self.tr('done'), self.tr('generated_message', paths="\n".join(paths)))

    def _generation_cancelled(self):
        self._generation_finished(0)
        self._set_status('cancelled')

    def _generation_failed(self, error):
        self._generation_finished(0)
        self._set_status('generation_failed')
        messagebox.showerror(self.tr('error'), self.tr('generation_failed_message', error=error))


def main():
    # Needed for the worker processes when running as a frozen executable
    multiprocessing.freeze_support()

    # With arguments, the same tabulation runs without the window (see cli.py)
    if len(sys.argv) > 1:
        import cli
        return cli.main()

    if TTKBOOTSTRAP_OK:
        root = ttk.Window(themename="flatly")
    else:
        root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
