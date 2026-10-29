"""
Downloads Folder Cleanup Tool - GUI
=====================================
Run: python cleanup_gui.py

Same features as the CLI (cleanup.py), same config.json, same engine.py
underneath - just a clickable window instead of a terminal.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox

import engine


# ---------------------------------------------------------------------------
# Small reusable widgets
# ---------------------------------------------------------------------------

class ScrollableCheckList(ttk.Frame):
    """A vertically scrollable list of checkboxes, one per item."""

    def __init__(self, parent, items, height=300):
        # items: list of (label_text, value)
        super().__init__(parent)
        canvas = tk.Canvas(self, height=height, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)

        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.vars = []
        self.values = []
        for label_text, value in items:
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(self.inner, text=label_text, variable=var)
            cb.pack(anchor="w", padx=4, pady=2)
            self.vars.append(var)
            self.values.append(value)

    def get_checked(self):
        return [v for var, v in zip(self.vars, self.values) if var.get()]


def center_window(win, width, height):
    win.update_idletasks()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


# ---------------------------------------------------------------------------
# Category folder dialog (the "where should these go?" ask)
# ---------------------------------------------------------------------------

class CategoryFolderDialog(tk.Toplevel):
    """Modal dialog asking where one category's files should go.
    Sets self.result to the resolved folder (str) or None (leave in Downloads).
    self.result stays as the sentinel NOT_ANSWERED if the window is closed
    without a decision (X button) - caller should treat that like 'leave'."""

    NOT_ANSWERED = object()

    def __init__(self, parent, category, files, config, session_top_names):
        super().__init__(parent)
        self.title(f"Where should {category} files go?")
        self.category = category
        self.config = config
        self.session_top_names = session_top_names
        self.result = self.NOT_ANSWERED

        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        pad = {"padx": 10, "pady": 6}

        ttk.Label(
            self, text=f"These are {category} files ({len(files)} found):",
            font=("", 10, "bold")
        ).pack(anchor="w", **pad)

        file_list = tk.Listbox(self, height=min(6, max(3, len(files))), width=50)
        for f in files:
            file_list.insert("end", os.path.basename(f))
        file_list.configure(state="disabled")
        file_list.pack(fill="x", padx=10)

        ttk.Label(self, text="Destination:", font=("", 10, "bold")).pack(
            anchor="w", **pad
        )

        self.mode = tk.StringVar(value="main")
        ttk.Radiobutton(
            self, text=f"Main folder - '{category}'", variable=self.mode,
            value="main", command=self._refresh_state
        ).pack(anchor="w", padx=20)
        ttk.Radiobutton(
            self, text="Custom folder name", variable=self.mode,
            value="custom", command=self._refresh_state
        ).pack(anchor="w", padx=20)
        ttk.Radiobutton(
            self, text="Leave in Downloads (don't move these)", variable=self.mode,
            value="leave", command=self._refresh_state
        ).pack(anchor="w", padx=20)

        custom_frame = ttk.Frame(self)
        custom_frame.pack(fill="x", padx=40, pady=(4, 0))
        ttk.Label(custom_frame, text="Folder name:").grid(row=0, column=0, sticky="w")
        self.custom_name = tk.StringVar()
        self.name_entry = ttk.Entry(custom_frame, textvariable=self.custom_name, width=25)
        self.name_entry.grid(row=0, column=1, padx=6)

        self.location = tk.StringVar(value="inside")
        self.inside_radio = ttk.Radiobutton(
            custom_frame, text=f"Inside {category}/", variable=self.location, value="inside"
        )
        self.top_radio = ttk.Radiobutton(
            custom_frame, text="Directly in Downloads", variable=self.location, value="top"
        )
        self.inside_radio.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.top_radio.grid(row=2, column=0, columnspan=2, sticky="w")
        self.custom_frame = custom_frame

        self.error_label = ttk.Label(self, text="", foreground="red")
        self.error_label.pack(anchor="w", padx=10)

        self.make_default = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self, text=f"Make this the permanent default for {category}",
            variable=self.make_default
        ).pack(anchor="w", **pad)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="OK", command=self._on_ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=5)

        self._refresh_state()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        center_window(self, 420, 480)
        self.wait_window(self)

    def _refresh_state(self):
        state = "normal" if self.mode.get() == "custom" else "disabled"
        self.name_entry.configure(state=state)
        self.inside_radio.configure(state=state)
        self.top_radio.configure(state=state)

    def _on_cancel(self):
        self.result = None  # treat window close as "leave in Downloads", not saved
        self.destroy()

    def _on_ok(self):
        mode = self.mode.get()

        if mode == "leave":
            resolved = None
            is_top_level = False
        elif mode == "main":
            resolved = self.category
            is_top_level = True
        else:
            name = self.custom_name.get().strip()
            if not name:
                self.error_label.configure(text="Enter a folder name, or pick a different option.")
                return
            if self.location.get() == "inside":
                resolved = f"{self.category}/{name}"
                is_top_level = False
            else:
                if engine.is_name_taken(name, self.config, self.session_top_names):
                    self.error_label.configure(
                        text=f"'{name}' is already used by another category or folder."
                    )
                    return
                resolved = name
                is_top_level = True

        engine.commit_category_folder(
            self.category, resolved, self.make_default.get(),
            self.config, self.session_top_names
        )
        self.result = resolved
        self.destroy()


# ---------------------------------------------------------------------------
# Preview / confirm dialog for organize moves
# ---------------------------------------------------------------------------

class MovePreviewDialog(tk.Toplevel):
    def __init__(self, parent, moves, downloads_path):
        super().__init__(parent)
        self.title("Proposed moves")
        self.transient(parent)
        self.grab_set()
        self.confirmed = False

        ttk.Label(
            self, text=f"Move these {len(moves)} file(s)?", font=("", 10, "bold")
        ).pack(anchor="w", padx=10, pady=(10, 4))

        columns = ("file", "destination")
        tree = ttk.Treeview(self, columns=columns, show="headings", height=12)
        tree.heading("file", text="File")
        tree.heading("destination", text="Destination")
        tree.column("file", width=220)
        tree.column("destination", width=260)
        for src, dest in moves:
            rel_dest = os.path.relpath(dest, downloads_path)
            tree.insert("", "end", values=(os.path.basename(src), rel_dest))
        tree.pack(fill="both", expand=True, padx=10, pady=4)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Move", command=self._confirm).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        center_window(self, 520, 420)
        self.wait_window(self)

    def _confirm(self):
        self.confirmed = True
        self.destroy()


class DeleteChecklistDialog(tk.Toplevel):
    """Generic 'tick items to delete/remember' dialog. Returns selected values
    via self.selected after the window closes. `items` is [(label, value), ...]."""

    def __init__(self, parent, title, prompt, items):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.selected = []

        ttk.Label(self, text=prompt, font=("", 10, "bold")).pack(
            anchor="w", padx=10, pady=(10, 4)
        )

        self.checklist = ScrollableCheckList(self, items, height=280)
        self.checklist.pack(fill="both", expand=True, padx=10, pady=4)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Confirm", command=self._confirm).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Skip (select nothing)", command=self.destroy).pack(
            side="left", padx=5
        )

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        center_window(self, 480, 420)
        self.wait_window(self)

    def _confirm(self):
        self.selected = self.checklist.get_checked()
        self.destroy()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class CleanupApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Downloads Cleanup Tool")
        self.resizable(False, False)

        self.config_data = engine.load_config()
        self.downloads_path = engine.get_downloads_path(self.config_data)

        if not os.path.isdir(self.downloads_path):
            messagebox.showerror(
                "Downloads folder not found",
                f"Could not find:\n{self.downloads_path}\n\n"
                f"Edit downloads_path in {engine.CONFIG_PATH} to fix this."
            )

        ttk.Label(
            self, text=f"Downloads folder:\n{self.downloads_path}",
            justify="left", padding=10
        ).pack(anchor="w")

        button_frame = ttk.Frame(self, padding=10)
        button_frame.pack(fill="x")

        ttk.Button(
            button_frame, text="1. Organize Downloads", width=32,
            command=self.run_organize
        ).pack(pady=4)
        ttk.Button(
            button_frame, text="2. Show Large Files", width=32,
            command=self.run_large_files
        ).pack(pady=4)
        ttk.Button(
            button_frame, text="3. Clean Up Old Archives", width=32,
            command=self.run_old_archives
        ).pack(pady=4)
        ttk.Button(
            button_frame, text="4. Run Everything", width=32,
            command=self.run_everything
        ).pack(pady=4)
        ttk.Button(
            button_frame, text="5. View Current Settings", width=32,
            command=self.run_view_settings
        ).pack(pady=4)
        ttk.Button(
            button_frame, text="Exit", width=32, command=self.destroy
        ).pack(pady=(12, 4))

        center_window(self, 380, 340)

    # -- Feature 1: Organize -------------------------------------------------

    def run_organize(self):
        config = self.config_data
        downloads_path = self.downloads_path
        files = engine.list_top_level_files(downloads_path, config)

        if not files:
            messagebox.showinfo("Organize", "Nothing to organize - Downloads root is already clean.")
            return

        by_cat, uncategorized = engine.group_files_by_category(files, config)

        session_top_names = set()
        resolved_folders = {}
        for category, srcs in by_cat.items():
            if category in config["category_folders"]:
                resolved_folders[category] = config["category_folders"][category]
            else:
                dlg = CategoryFolderDialog(self, category, srcs, config, session_top_names)
                resolved_folders[category] = dlg.result

        moves, duplicates, left_alone = engine.plan_moves(
            by_cat, uncategorized, resolved_folders, config, downloads_path
        )

        if moves:
            preview = MovePreviewDialog(self, moves, downloads_path)
            if preview.confirmed:
                summary = engine.execute_moves(moves, downloads_path)
                lines = [f"{folder:12s}: {count}" for folder, count in sorted(summary.items())]
                lines.append(f"\nTotal moved: {sum(summary.values())}")
                if left_alone:
                    lines.append(f"Left in Downloads (leave-as-is): {left_alone}")
                messagebox.showinfo("Cleanup Summary", "\n".join(lines))
            else:
                messagebox.showinfo("Organize", "Skipped - no files were moved.")
        else:
            messagebox.showinfo("Organize", "No new files need moving.")

        if duplicates:
            items = [
                (f"{os.path.basename(src)}  (identical copy already in "
                 f"{os.path.relpath(os.path.dirname(target), downloads_path)})", src)
                for src, target in duplicates
            ]
            dlg = DeleteChecklistDialog(
                self, "Duplicate files found",
                f"{len(duplicates)} file(s) already exist elsewhere with identical content.\n"
                "Tick any to delete from Downloads:",
                items
            )
            if dlg.selected:
                details = "\n".join(
                    f"{os.path.basename(p)}  ({engine.human_size(os.path.getsize(p))})"
                    for p in dlg.selected
                )
                if messagebox.askyesno("Confirm delete", f"Delete these {len(dlg.selected)} file(s)?\n\n{details}"):
                    engine.delete_files(dlg.selected)
                    messagebox.showinfo("Deleted", f"Deleted {len(dlg.selected)} duplicate file(s).")

    # -- Feature 2: Large files ----------------------------------------------

    def run_large_files(self):
        config = self.config_data
        large = engine.scan_large_files(config)

        if not large:
            messagebox.showinfo(
                "Large files",
                f"No files over {config['large_file_mb']} MB in Downloads."
            )
            return

        win = tk.Toplevel(self)
        win.title("Large files")
        win.transient(self)
        win.grab_set()   

        columns = ("file", "size", "age")
        tree = ttk.Treeview(win, columns=columns, show="headings", height=15)
        tree.heading("file", text="File")
        tree.heading("size", text="Size")
        tree.heading("age", text="Age")
        tree.column("file", width=320)
        tree.column("size", width=90)
        tree.column("age", width=90)
        for path, size, days in large:
            rel = os.path.relpath(path, self.downloads_path)
            tree.insert("", "end", values=(rel, engine.human_size(size), f"{days} days"))
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 10))
        center_window(win, 560, 420)
        win.wait_window(win)    

    # -- Feature 3: Old archives ---------------------------------------------

    def run_old_archives(self):
        config = self.config_data
        downloads_path = self.downloads_path
        candidates = engine.scan_old_archives(config)

        if not candidates:
            messagebox.showinfo(
                "Old archives",
                f"No archives older than {config['old_archive_days']} days to review."
            )
            return

        items = [
            (f"{os.path.relpath(p, downloads_path)}   {engine.human_size(s)}   ({d} days old)",
             (p, s, d, h))
            for p, s, d, h in candidates
        ]
        dlg = DeleteChecklistDialog(
            self, "Old archives",
            f"Archives older than {config['old_archive_days']} days - tick any to delete:",
            items
        )
        to_delete = dlg.selected
        delete_paths = {item[0] for item in to_delete}
        remaining = [c for c in candidates if c[0] not in delete_paths]

        to_ignore = []
        if remaining:
            ignore_items = [
                (f"{os.path.relpath(p, downloads_path)}   {engine.human_size(s)}   ({d} days old)",
                 (p, h))
                for p, s, d, h in remaining
            ]
            ignore_dlg = DeleteChecklistDialog(
                self, "Remember for next time",
                "Tick any to NEVER ask about again (remembered permanently):",
                ignore_items
            )
            to_ignore = ignore_dlg.selected

        if to_delete:
            details = "\n".join(
                f"{os.path.basename(p)}  ({engine.human_size(s)}, {d} days old)"
                for p, s, d, _ in to_delete
            )
            if messagebox.askyesno("Confirm delete", f"Delete these {len(to_delete)} file(s)?\n\n{details}"):
                engine.delete_files([p for p, _, _, _ in to_delete])
                messagebox.showinfo("Deleted", f"Deleted {len(to_delete)} archive(s).")

        if to_ignore:
            engine.add_to_ignore_list(to_ignore, config)
            messagebox.showinfo("Saved", f"Will never ask about {len(to_ignore)} file(s) again.")

    # -- Feature 4: Run everything --------------------------------------------

    def run_everything(self):
        self.run_organize()
        self.run_large_files()
        self.run_old_archives()

    # -- Feature 5: View settings ---------------------------------------------

    def run_view_settings(self):
        config = self.config_data
        lines = [
            f"Downloads folder : {self.downloads_path}",
            f"Config file      : {engine.CONFIG_PATH}",
            f"Large file limit : {config['large_file_mb']} MB",
            f"Old archive age  : {config['old_archive_days']} days",
            "",
            "Category destinations:",
        ]
        for category in config["categories"]:
            if category in config["category_folders"]:
                val = config["category_folders"][category]
                label = "Leave in Downloads (not moved)" if val is None else val
            else:
                label = "Not set yet - will ask next time"
            lines.append(f"  {category:12s}: {label}")
        lines.append("")
        lines.append(f"Unrecognized file types go to: {config['catch_all_folder']}")

        win = tk.Toplevel(self)
        win.title("Current settings")
        win.transient(self)
        text = tk.Text(win, width=60, height=len(lines) + 2, wrap="word")
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        text.pack(padx=10, pady=10)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 10))
        center_window(win, 480, 30 * (len(lines) + 3))


if __name__ == "__main__":
    app = CleanupApp()
    app.mainloop()
