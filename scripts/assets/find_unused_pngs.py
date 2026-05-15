# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
#!/usr/bin/env python3
"""
Identify unused PNGs in nepal_kings/img/ by scanning all Python source files
for image path references, then move unused files to img/_legacy/.
"""
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMG_DIR = ROOT / 'nepal_kings' / 'img'
LEGACY_DIR = IMG_DIR / '_legacy'
SRC_DIRS = [ROOT / 'nepal_kings']

# Directories already known to be unused (skip entirely)
SKIP_DIRS = {'figures_old', 'old_cards', '_legacy', 'app_icon'}


def collect_all_pngs():
    """Return set of all PNG paths relative to IMG_DIR."""
    pngs = set()
    for root, dirs, files in os.walk(IMG_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.lower().endswith('.png'):
                rel = os.path.relpath(os.path.join(root, f), IMG_DIR)
                pngs.add(rel)
    return pngs


def collect_referenced_filenames():
    """Scan all .py files and extract referenced image filenames/paths."""
    referenced = set()

    # Collect all string literals from Python source
    all_strings = set()
    for src_dir in SRC_DIRS:
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for f in files:
                if not f.endswith('.py'):
                    continue
                path = os.path.join(root, f)
                try:
                    content = open(path, encoding='utf-8').read()
                except Exception:
                    continue
                # Find all string literals (single line only – avoids
                # docstrings swallowing inner quoted paths)
                for match in re.findall(r"""(?:'([^'\n]*)'|"([^"\n]*)")""", content):
                    for s in match:
                        if s:
                            all_strings.add(s)

    # Extract any string that looks like a .png filename or img/ path
    for s in all_strings:
        s = s.strip().strip('/')
        # Normalise ./img/ to img/
        if s.startswith('./img/'):
            s = s[2:]
        if s.endswith('.png'):
            # Could be a full path like img/cards/s02.png
            if s.startswith('img/'):
                referenced.add(s[4:])  # strip img/ prefix
            else:
                # Just a filename like 'back.png'
                referenced.add(s)
        elif 'img/' in s:
            # Directory reference like 'img/cards/'
            if s.startswith('img/'):
                referenced.add(s[4:].rstrip('/'))

    return referenced, all_strings


def is_png_used(png_rel_path, referenced, all_strings):
    """Check if a PNG file is referenced in source code."""
    filename = os.path.basename(png_rel_path)
    name_no_ext = os.path.splitext(filename)[0]
    dirname = os.path.dirname(png_rel_path)

    # Direct full path match (e.g., "cards/s02.png")
    if png_rel_path in referenced:
        return True

    # Filename match (e.g., "back.png")
    if filename in referenced:
        return True

    # Check if filename without extension appears in code strings
    # (for dynamic construction like prefix + '_active.png')
    if name_no_ext in all_strings:
        return True

    # Check if any string is a substring of the filename
    # (catches dynamic construction like f"{suit}{rank}.png")
    # Only for card-style filenames
    if dirname.startswith('cards'):
        # Cards are always used (dynamic suit+rank construction)
        return True

    # Check if the directory is referenced and file follows naming patterns
    if dirname in referenced:
        # Directory is loaded as a whole (e.g., glob or listdir)
        # Conservative: mark as used
        return True

    # Check for dynamic name construction patterns:
    # name_active.png / name_passive.png
    for suffix in ['_active', '_passive', '_greyscale']:
        if name_no_ext.endswith(suffix):
            base = name_no_ext[:-len(suffix)]
            if base in all_strings or (base + suffix) in all_strings:
                return True

    # Check if parent+filename combo appears
    parent_file = os.path.join(dirname, filename)
    for s in all_strings:
        s = s.strip().strip('/')
        if s.startswith('img/'):
            s = s[4:]
        if parent_file == s:
            return True

    # Check if the base name (without prefix _ or suffix _gray etc) is referenced
    clean_name = name_no_ext.lstrip('_')
    for suffix in ['_gray', '_gray2', '_grey', '_greyscale', '_hidden', '__']:
        clean_name = clean_name.rstrip('_').removesuffix(suffix) if hasattr(str, 'removesuffix') else clean_name
    if clean_name in all_strings:
        return True

    return False


def main():
    all_pngs = collect_all_pngs()
    referenced, all_strings = collect_referenced_filenames()

    print(f"Total PNGs found: {len(all_pngs)}")
    print(f"Total string literals: {len(all_strings)}")
    print(f"Image-related references: {len(referenced)}")
    print()

    used = set()
    unused = set()

    for png in sorted(all_pngs):
        if is_png_used(png, referenced, all_strings):
            used.add(png)
        else:
            unused.add(png)

    print(f"PNGs referenced in code: {len(used)}")
    print(f"PNGs NOT referenced: {len(unused)}")
    print()

    # Calculate sizes
    unused_size = sum(os.path.getsize(IMG_DIR / p) for p in unused)
    used_size = sum(os.path.getsize(IMG_DIR / p) for p in used)

    print(f"Used PNGs total size: {used_size / 1_000_000:.1f} MB")
    print(f"Unused PNGs total size: {unused_size / 1_000_000:.1f} MB")
    print()

    # List unused files
    print("=== UNUSED PNGs (will be moved to _legacy/) ===")
    for png in sorted(unused):
        size = os.path.getsize(IMG_DIR / png)
        print(f"  {size / 1_000_000:.1f}MB  {png}")

    return unused


if __name__ == '__main__':
    unused = main()

    if unused:
        print()
        resp = input(f"\nMove {len(unused)} unused PNGs to img/_legacy/? [y/N] ")
        if resp.strip().lower() == 'y':
            for png in sorted(unused):
                src = IMG_DIR / png
                dst = LEGACY_DIR / png
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                print(f"  Moved: {png}")
            print(f"\nDone! Moved {len(unused)} files to img/_legacy/")
        else:
            print("Aborted.")
