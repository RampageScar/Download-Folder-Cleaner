"""
engine.py - Shared logic for the Downloads cleanup tool.

Pure functions only: no print(), no input(), no questionary, no tkinter.
Both cleanup.py (CLI) and cleanup_gui.py (GUI) can import from here so the
actual file-handling logic only exists in one place.
"""

import os
import json
import shutil
import hashlib
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")

DEFAULT_CONFIG = {
    "downloads_path": "AUTO",
    "large_file_mb": 1024,
    "old_archive_days": 15,
    "archive_extensions": [".zip", ".rar", ".7z", ".tar", ".gz", ".tgz"],
    "skip_extensions": [".crdownload", ".part", ".tmp", ".download"],
    "categories": {
        "Documents": [".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"],
        "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
        "Videos": [".mp4", ".mkv", ".mov", ".avi", ".webm"],
        "Audio": [".mp3", ".wav", ".flac", ".m4a"],
        "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".tgz"],
        "Installers": [".exe", ".msi"],
        "Code": [".py", ".ps1", ".bat", ".cmd", ".sh", ".js", ".ts", ".java", ".c",
                 ".cpp", ".h", ".html", ".css", ".json", ".xml", ".yaml", ".yml", ".md"]
    },
    "category_folders": {},
    "top_level_names_used": [],
    "catch_all_folder": "Others",
    "ignore_list": {}
}


# ---------------------------------------------------------------------------
# Config handling
# ---------------------------------------------------------------------------

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, value)
    return config


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_downloads_path(config):
    path = config.get("downloads_path", "AUTO")
    if path == "AUTO":
        return os.path.join(os.path.expanduser("~"), "Downloads")
    return path


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def human_size(num_bytes):
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def age_in_days(timestamp):
    return (datetime.now() - datetime.fromtimestamp(timestamp)).days


def hash_file(path, chunk_size=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def list_top_level_files(downloads_path, config):
    skip_ext = set(e.lower() for e in config.get("skip_extensions", []))
    results = []
    with os.scandir(downloads_path) as it:
        for entry in it:
            if not entry.is_file():
                continue
            if entry.name.startswith("."):
                continue
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in skip_ext:
                continue
            results.append(entry.path)
    return results


def list_all_files_recursive(downloads_path, config):
    skip_ext = set(e.lower() for e in config.get("skip_extensions", []))
    results = []
    for root, dirs, files in os.walk(downloads_path):
        for name in files:
            if name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in skip_ext:
                continue
            results.append(os.path.join(root, name))
    return results


def top_level_folder(path, downloads_path):
    rel = os.path.relpath(path, downloads_path)
    return rel.split(os.sep)[0]


def find_category(ext, config):
    for category, extensions in config["categories"].items():
        if ext in extensions:
            return category
    return None


def group_files_by_category(files, config):
    """Returns (files_by_category: {category: [paths]}, uncategorized: [paths])"""
    files_by_category = {}
    uncategorized = []
    for src in files:
        ext = os.path.splitext(src)[1].lower()
        category = find_category(ext, config)
        if category is None:
            uncategorized.append(src)
        else:
            files_by_category.setdefault(category, []).append(src)
    return files_by_category, uncategorized


def unresolved_categories(files_by_category, config):
    """Categories present this run that don't have a saved destination yet."""
    return [c for c in files_by_category if c not in config["category_folders"]]


def is_name_taken(name, config, session_top_names):
    permanent = set(config.get("top_level_names_used", []))
    return name in (permanent | session_top_names)


def commit_category_folder(category, resolved, make_default, config, session_top_names):
    """Record a resolved destination for a category. `resolved` is a relative
    folder path (e.g. 'Documents', 'Images/Screenshots') or None for
    'leave in Downloads'. If it's a top-level name, reserve it for this
    session (and permanently too, if make_default). Saves config to disk
    when make_default is True."""
    is_top_level = resolved is not None and "/" not in resolved
    if is_top_level:
        session_top_names.add(resolved)
    if make_default:
        config["category_folders"][category] = resolved
        if is_top_level and resolved not in config["top_level_names_used"]:
            config["top_level_names_used"].append(resolved)
        save_config(config)


# ---------------------------------------------------------------------------
# Organize planning + execution
# ---------------------------------------------------------------------------

def plan_moves(files_by_category, uncategorized, resolved_folders, config, downloads_path):
    """Returns (moves, duplicates, left_alone_count).
    moves: [(src, dest_path), ...]
    duplicates: [(src, existing_identical_target), ...]
    """
    moves = []
    duplicates = []
    left_alone = 0

    def plan_move(src, dest_folder):
        filename = os.path.basename(src)
        dest_dir = os.path.join(downloads_path, dest_folder)
        dest_path = os.path.join(dest_dir, filename)

        if os.path.exists(dest_path):
            if hash_file(src) == hash_file(dest_path):
                duplicates.append((src, dest_path))
                return
            else:
                stamp = datetime.fromtimestamp(os.path.getmtime(src)).strftime("%Y-%m-%d_%H%M")
                name, ext = os.path.splitext(filename)
                dest_path = os.path.join(dest_dir, f"{name}_{stamp}{ext}")

        moves.append((src, dest_path))

    for category, srcs in files_by_category.items():
        dest_folder = resolved_folders.get(category)
        if dest_folder is None:
            left_alone += len(srcs)
            continue
        for src in srcs:
            plan_move(src, dest_folder)

    for src in uncategorized:
        plan_move(src, config["catch_all_folder"])

    return moves, duplicates, left_alone


def execute_moves(moves, downloads_path):
    """Performs the moves on disk. Returns a {top_level_folder: count} summary."""
    summary = {}
    for src, dest_path in moves:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.move(src, dest_path)
        folder = top_level_folder(dest_path, downloads_path)
        summary[folder] = summary.get(folder, 0) + 1
    return summary


def delete_files(paths):
    for p in paths:
        os.remove(p)


# ---------------------------------------------------------------------------
# Large files / old archives scans
# ---------------------------------------------------------------------------

def scan_large_files(config):
    """Returns [(path, size_bytes, age_days), ...] sorted largest first."""
    downloads_path = get_downloads_path(config)
    threshold_bytes = config["large_file_mb"] * 1024 * 1024
    files = list_all_files_recursive(downloads_path, config)

    large = []
    for path in files:
        size = os.path.getsize(path)
        if size >= threshold_bytes:
            days = age_in_days(os.path.getctime(path))
            large.append((path, size, days))
    large.sort(key=lambda x: x[1], reverse=True)
    return large


def scan_old_archives(config):
    """Returns [(path, size_bytes, age_days, sha256_hash), ...] for archives
    older than the configured threshold, excluding anything already on the
    ignore list."""
    downloads_path = get_downloads_path(config)
    archive_ext = set(e.lower() for e in config["archive_extensions"])
    min_days = config["old_archive_days"]
    ignore_list = config.get("ignore_list", {})

    files = list_all_files_recursive(downloads_path, config)
    candidates = []
    for path in files:
        ext = os.path.splitext(path)[1].lower()
        if ext not in archive_ext:
            continue
        days = age_in_days(os.path.getctime(path))
        if days < min_days:
            continue
        filehash = hash_file(path)
        if filehash in ignore_list:
            continue
        candidates.append((path, os.path.getsize(path), days, filehash))
    return candidates


def add_to_ignore_list(items, config):
    """items: [(path, filehash), ...]"""
    ignore_list = config.get("ignore_list", {})
    for path, filehash in items:
        ignore_list[filehash] = {
            "name": os.path.basename(path),
            "added_on": datetime.now().strftime("%Y-%m-%d")
        }
    config["ignore_list"] = ignore_list
    save_config(config)
