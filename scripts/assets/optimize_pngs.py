# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
#!/usr/bin/env python3
"""
Optimize all game PNGs: downscale to sensible max dimensions per directory,
re-save with max compression, strip metadata.

Target dimensions are chosen so no image is larger than it ever appears
on a 1920×1080 screen (with generous headroom for future 4K support).

Directory-specific max pixel dimensions:
  background/          → 2048  (full-screen backgrounds, scaled to 1920×1080)
  glow/rect/           →  512  (scoreboard glow effects ≈ 250×180 on screen)
  game_button/glow_rect/ → 512
  game_button/glow/    →  512
  game_button/symbol*  →  256
  spells/frames*/      →  512  (spell card frames ≈ 150×150 on screen)
  spells/icons*/       →  256
  figures/frames*/     →  512  (figure card frames ≈ 150×150 on screen)
  figures/icons*/      →  256
  battle/frames*/      →  512
  battle/icons*/       →  256
  resource_icons/      →  256
  slot_icons/          →  256
  status_icons/        →  256
  icons/               →  256
  button/              →  512
  menu_button/         →  512
  dialogue_box/        →  512
  sub_screen/          →  512
  suits/               →  256
  cards/               →  256
  (everything else)    →  512
"""
from PIL import Image, ImageFile
import os
import sys

Image.MAX_IMAGE_PIXELS = 200_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = True

IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'nepal_kings', 'img')
SKIP_DIRS = {'_legacy', 'figures_old', 'old_cards', 'app_icon'}

# ── Max pixel dimension per path substring ──────────────────────
# First match wins; order from most-specific to least-specific.
MAX_DIM_RULES = [
    # Backgrounds (full screen – keep up to 2048 for 4K headroom)
    ('background/',          2048),
    # Glow rectangles (rendered at ~250px)
    ('glow/rect/',           512),
    ('game_button/glow_rect/', 512),
    ('game_button/glow/',    512),
    ('game_button/symbol',   256),
    # Spells & figures – frames ≈ 150px on screen, icons ≈ 40px
    ('spells/frames',        512),
    ('spells/icons',         256),
    ('figures/frames',       512),
    ('figures/icons',        256),
    # Battle
    ('battle/frames',        512),
    ('battle/icons',         256),
    # Small UI elements
    ('resource_icons/',      256),
    ('slot_icons/',          256),
    ('status_icons/',        256),
    ('icons/',               256),
    ('suits/',               256),
    ('cards/',               256),
    ('new_cards/',           256),
    # Medium UI elements
    ('button/',              512),
    ('menu_button/',         512),
    ('dialogue_box/',        512),
    ('sub_screen/',          512),
]
DEFAULT_MAX_DIM = 512


def max_dim_for(rel_path: str) -> int:
    """Return the max pixel dimension for a given relative path."""
    rel_path = rel_path.replace(os.sep, '/')
    for pattern, limit in MAX_DIM_RULES:
        if pattern in rel_path:
            return limit
    return DEFAULT_MAX_DIM


def main():
    dry_run = '--dry-run' in sys.argv
    total_before = 0
    total_after = 0
    optimized = 0
    resized_count = 0
    total_mem_before = 0
    total_mem_after = 0

    for root, dirs, files in os.walk(IMG_DIR):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            if not f.lower().endswith('.png'):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, IMG_DIR)
            size_before = os.path.getsize(path)
            total_before += size_before

            try:
                img = Image.open(path)
                img.load()
                w, h = img.size
                mem_before = w * h * 4
                total_mem_before += mem_before

                max_px = max_dim_for(rel)
                if w > max_px or h > max_px:
                    ratio = min(max_px / w, max_px / h)
                    new_w = int(w * ratio)
                    new_h = int(h * ratio)
                    mem_after = new_w * new_h * 4
                    saved_mem = (mem_before - mem_after) / 1_000_000
                    print(f'  RESIZE {w}x{h} -> {new_w}x{new_h}  '
                          f'(saves {saved_mem:.0f} MB surface)  {rel}')
                    if not dry_run:
                        img = img.resize((new_w, new_h), Image.LANCZOS)
                    resized_count += 1
                    total_mem_after += mem_after
                else:
                    total_mem_after += mem_before

                if not dry_run:
                    img.save(path, 'PNG', optimize=True, compress_level=6)

                size_after = os.path.getsize(path) if not dry_run else size_before
                total_after += size_after
                optimized += 1

            except Exception as e:
                total_after += size_before
                total_mem_after += 0
                print(f'  ERROR: {rel}: {e}')

    saved_disk = (total_before - total_after) / 1_000_000
    saved_mem = (total_mem_before - total_mem_after) / 1_000_000
    pct_disk = (saved_disk / (total_before / 1_000_000) * 100) if total_before else 0
    pct_mem = (saved_mem / (total_mem_before / 1_000_000) * 100) if total_mem_before else 0

    prefix = '[DRY RUN] ' if dry_run else ''
    print()
    print(f'{prefix}Processed {optimized} PNGs, resized {resized_count}')
    print(f'{prefix}Disk:   {total_before / 1_000_000:.0f} MB -> {total_after / 1_000_000:.0f} MB  '
          f'(saved {saved_disk:.0f} MB, {pct_disk:.0f}%)')
    print(f'{prefix}Memory: {total_mem_before / 1_000_000:.0f} MB -> {total_mem_after / 1_000_000:.0f} MB  '
          f'(saved {saved_mem:.0f} MB, {pct_mem:.0f}%)')


if __name__ == '__main__':
    main()
