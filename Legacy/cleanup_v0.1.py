"""
Downloads Folder Cleanup Tool
==============================
Run manually whenever you want: python cleanup.py

Features:
  1. Organize  - sorts loose files into type folders (preview + confirm)
  2. Large files - reports files >= threshold size (informational)
  3. Old archives - finds zip/rar/etc older than N days, lets you tick
                     which to delete, and "never ask again" per file
  4. Run everything - does all three in sequence

Config lives in config.json next to this script. Edit it anytime to
change the download path, thresholds, or which extension goes to which
folder (folders can be nested, e.g. "Videos/Movies").
"""

import os
import sys
import json
import shutil
import hashlib
from datetime import datetime

try:
    import questionary
except ImportError:
    print("This tool needs the 'questionary' package.")
    print("Install it with:  pip install questionary")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

DEFAULT_CONFIG = {
    "downloads_path": "AUTO",
    "large_file_mb": 1024,
    "old_archive_days": 15,
    "archive_extensions": [".zip", ".rar", ".7z", ".tar", ".gz", ".tgz"],
    "skip_extensions": [".crdownload", ".part", ".tmp", ".download"],
    "folder_mapping": {
        ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
        ".txt": "Documents", ".xls": "Documents", ".xlsx": "Documents",
        ".ppt": "Documents", ".pptx": "Documents", ".csv": "Documents",
        ".jpg": "Images", ".jpeg": "Images", ".png": "Images",
        ".gif": "Images", ".bmp": "Images", ".webp": "Images", ".svg": "Images",
        ".mp4": "Videos/Movies", ".mkv": "Videos/Movies", ".mov": "Videos/Clips",
        ".avi": "Videos/Movies", ".webm": "Videos/Clips",
        ".mp3": "Audio", ".wav": "Audio", ".flac": "Audio", ".m4a": "Audio",
        ".zip": "Archives", ".rar": "Archives", ".7z": "Archives",
        ".tar": "Archives", ".gz": "Archives", ".tgz": "Archives",
        ".exe": "Installers", ".msi": "Installers"
    },
    "catch_all_folder": "Others",
    "ignore_list": {}
}


# ---------------------------------------------------------------------------
# Config handling
# ---------------------------------------------------------------------------

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_downloads_path(config):
    path = config.get("downloads_path", "AUTO")
    if path == "AUTO":
        return os.path.join(os.path.expanduser("~"), "Downloads")
    return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def human_size(num_bytes):
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def age_in_days(mtime):
    return (datetime.now() - datetime.fromtimestamp(mtime)).days


def hash_file(path, chunk_size=1 << 20):
    """Full SHA-256 hash, read in chunks so large files don't blow up memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def list_top_level_files(downloads_path, config):
    """Only files directly inside Downloads (not subfolders already organized).
    Used by organize() so it doesn't re-shuffle already-sorted files."""
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
    """Files anywhere under Downloads, including already-organized subfolders.
    Used by large_files_report() and old_archive_cleanup() so files don't
    'disappear' from checks once organize() has moved them into subfolders."""
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
    """For summary counts: 'Videos/Movies/x.mp4' -> 'Videos'."""
    rel = os.path.relpath(path, downloads_path)
    return rel.split(os.sep)[0]


def get_destination_folder(filename, config):
    ext = os.path.splitext(filename)[1].lower()
    return config["folder_mapping"].get(ext, config["catch_all_folder"])


# ---------------------------------------------------------------------------
# Feature 1: Organize
# ---------------------------------------------------------------------------

def organize(config):
    downloads_path = get_downloads_path(config)
    files = list_top_level_files(downloads_path, config)

    if not files:
        print("Nothing to organize - Downloads root is already clean.")
        return

    moves = []       # (src, dest_path) - straightforward moves / renamed moves
    duplicates = []  # (src, existing_target) - identical content already there

    for src in files:
        filename = os.path.basename(src)
        dest_folder = get_destination_folder(filename, config)
        dest_dir = os.path.join(downloads_path, dest_folder)
        dest_path = os.path.join(dest_dir, filename)

        if os.path.exists(dest_path):
            if hash_file(src) == hash_file(dest_path):
                duplicates.append((src, dest_path))
                continue
            else:
                # Same name, different content -> timestamp suffix so it's
                # identifiable later, instead of a meaningless "(1)"
                stamp = datetime.fromtimestamp(os.path.getmtime(src)).strftime("%Y-%m-%d_%H%M")
                name, ext = os.path.splitext(filename)
                new_name = f"{name}_{stamp}{ext}"
                dest_path = os.path.join(dest_dir, new_name)

        moves.append((src, dest_path))

    if moves:
        print("\nProposed moves:")
        print("-" * 60)
        for src, dest_path in moves:
            rel_dest = os.path.relpath(dest_path, downloads_path)
            print(f"  {os.path.basename(src):40s} -> {rel_dest}")
        print("-" * 60)

        proceed = questionary.confirm(f"Move these {len(moves)} file(s)?").ask()
        if proceed:
            summary = {}
            for src, dest_path in moves:
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.move(src, dest_path)
                folder = top_level_folder(dest_path, downloads_path)
                summary[folder] = summary.get(folder, 0) + 1
            print(f"Moved {len(moves)} file(s).")
            print_cleanup_summary(summary)
        else:
            print("Skipped organizing.")
    else:
        print("\nNo new files need moving.")

    if duplicates:
        print(f"\nFound {len(duplicates)} file(s) already organized with identical content:")
        choices = [
            questionary.Choice(
                title=f"{os.path.basename(src)}  (identical copy already in "
                      f"{os.path.relpath(os.path.dirname(target), downloads_path)})",
                value=(src, target)
            )
            for src, target in duplicates
        ]
        print("(Press arrow keys to navigate, space/enter to toggle, "
              "Enter with none ticked = delete nothing)")
        to_delete = questionary.checkbox(
            "Tick any duplicate leftovers in Downloads to delete:",
            choices=choices,
        ).ask() or []

        if to_delete:
            print("\nAbout to delete:")
            for src, _ in to_delete:
                size = human_size(os.path.getsize(src))
                mtime = datetime.fromtimestamp(os.path.getmtime(src)).strftime("%Y-%m-%d %H:%M")
                print(f"  {os.path.basename(src):40s} {size:>10s}  (modified {mtime})")
            for src, _ in to_delete:
                os.remove(src)
            print(f"Deleted {len(to_delete)} duplicate file(s).")
        left = len(duplicates) - len(to_delete)
        if left:
            print(f"Left {left} duplicate(s) untouched in Downloads.")


def print_cleanup_summary(folder_counts):
    print("\nCleanup Summary")
    print("-" * 32)
    for folder, count in sorted(folder_counts.items()):
        print(f"{folder:12s}: {count}")
    print("-" * 32)
    print(f"Total moved: {sum(folder_counts.values())}")


# ---------------------------------------------------------------------------
# Feature 2: Large files report
# ---------------------------------------------------------------------------

def large_files_report(config):
    downloads_path = get_downloads_path(config)
    threshold_bytes = config["large_file_mb"] * 1024 * 1024
    files = list_all_files_recursive(downloads_path, config)

    large = []
    for path in files:
        size = os.path.getsize(path)
        if size >= threshold_bytes:
            large.append((path, size))

    if not large:
        print(f"\nNo files over {config['large_file_mb']} MB in Downloads (including subfolders).")
        return

    large.sort(key=lambda x: x[1], reverse=True)
    print(f"\nFiles over {config['large_file_mb']} MB:")
    print("-" * 70)
    for path, size in large:
        days = age_in_days(os.path.getctime(path))
        rel = os.path.relpath(path, downloads_path)
        print(f"  {rel:45s} {human_size(size):>10s}  ({days} days old)")
    print("-" * 70)


# ---------------------------------------------------------------------------
# Feature 3: Old archive cleanup
# ---------------------------------------------------------------------------

def old_archive_cleanup(config):
    downloads_path = get_downloads_path(config)
    archive_ext = set(e.lower() for e in config["archive_extensions"])
    min_days = config["old_archive_days"]
    ignore_list = config.get("ignore_list", {})

    files = list_all_files_recursive(downloads_path, config)
    candidates = []  # (path, size, days, filehash)

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

    if not candidates:
        print(f"\nNo archives older than {min_days} days to review.")
        return

    print(f"\nFiles older than {min_days} days:")

    choices = [
        questionary.Choice(
            title=f"{os.path.relpath(p, downloads_path):45s} {human_size(s):>10s}  ({d} days old)",
            value=(p, s, d, h)
        )
        for p, s, d, h in candidates
        ] + [
        questionary.Choice(title="Skip", value="SKIP")
    ]

    print("(Press arrow keys to navigate, space/enter to toggle, "
          "Enter with none ticked = delete nothing)")
    to_delete = questionary.checkbox(
        "Tick files to delete now:",
        choices=choices,
    ).ask() or []

    delete_set = set(item[0] for item in to_delete)
    remaining = [c for c in candidates if c[0] not in delete_set]

    to_ignore = []
    if remaining:
        ignore_choices = [
            questionary.Choice(
                title=f"{os.path.relpath(p, downloads_path):45s} {human_size(s):>10s}  ({d} days old)",
                value=(p, s, d, h)
            )
            for p, s, d, h in remaining
            ] + [
            questionary.Choice(title="Skip", value="SKIP")
        ]
        print("(Press arrow keys to navigate, space/enter to toggle, "
              "Enter with none ticked = remember nothing)")
        to_ignore = questionary.checkbox(
            "Tick any to NEVER ask about again (remembered permanently):",
            choices=ignore_choices,
        ).ask() or []

    if to_delete:
        print("\nAbout to delete:")
        for path, size, days, _ in to_delete:
            print(f"  {os.path.basename(path):35s} {human_size(size):>10s}  ({days} days old)")
        confirm_delete = questionary.confirm(f"Proceed with deleting these {len(to_delete)} file(s)?").ask()
        if confirm_delete:
            for path, _, _, _ in to_delete:
                os.remove(path)
            print(f"Deleted {len(to_delete)} archive(s).")
        else:
            print("Skipped deleting - no files were removed.")

    for path, _, _, filehash in to_ignore:
        ignore_list[filehash] = {
            "name": os.path.basename(path),
            "added_on": datetime.now().strftime("%Y-%m-%d")
        }
    if to_ignore:
        config["ignore_list"] = ignore_list
        save_config(config)
        print(f"Will never ask about {len(to_ignore)} file(s) again.")


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

def main():
    config = load_config()
    downloads_path = get_downloads_path(config)

    if not os.path.isdir(downloads_path):
        print(f"Downloads folder not found at: {downloads_path}")
        print(f"Edit downloads_path in {CONFIG_PATH} to point to the right folder.")
        sys.exit(1)

    print(f"Downloads folder: {downloads_path}")

    while True:
        choice = questionary.select(
            "What do you want to do?",
            choices=[
                "1. Organize Downloads (preview + confirm)",
                "2. Show large files (>= {} MB)".format(config["large_file_mb"]),
                "3. Clean up old archives (>= {} days)".format(config["old_archive_days"]),
                "4. Run everything",
                "5. Exit",
            ]
        ).ask()

        if choice is None or choice.startswith("5"):
            break
        elif choice.startswith("1"):
            organize(config)
        elif choice.startswith("2"):
            large_files_report(config)
        elif choice.startswith("3"):
            old_archive_cleanup(config)
        elif choice.startswith("4"):
            organize(config)
            large_files_report(config)
            old_archive_cleanup(config)

        print()  # spacing before menu re-shows


if __name__ == "__main__":
    main()
