#!/usr/bin/env python3
"""Optimize all game PNGs: cap at 4K, re-save with max compression, strip metadata."""
from PIL import Image, ImageFile
import os

Image.MAX_IMAGE_PIXELS = 200_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = True

img_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nepal_kings', 'img')
skip_dirs = {'figures_old', 'old_cards', 'app_icon'}
total_before = 0
total_after = 0
optimized = 0

for root, dirs, files in os.walk(img_dir):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    for f in files:
        if not f.lower().endswith('.png'):
            continue
        path = os.path.join(root, f)
        size_before = os.path.getsize(path)
        total_before += size_before

        try:
            img = Image.open(path)
            img.load()  # Force load before resize
            w, h = img.size

            max_dim = 3840
            if w > max_dim or h > max_dim:
                ratio = min(max_dim / w, max_dim / h)
                new_w = int(w * ratio)
                new_h = int(h * ratio)
                img = img.resize((new_w, new_h), Image.LANCZOS)
                print(f'  RESIZED {w}x{h} -> {new_w}x{new_h}: {f}')

            # compress_level=6 is a good balance of speed and size
            img.save(path, 'PNG', optimize=True, compress_level=6)

            size_after = os.path.getsize(path)
            total_after += size_after

            if size_before - size_after > 100_000:
                saved = (size_before - size_after) / 1_000_000
                print(f'  {saved:+.1f}MB  {f}')
            optimized += 1

        except Exception as e:
            total_after += size_before
            print(f'  ERROR: {f}: {e}')

saved_total = (total_before - total_after) / 1_000_000
print()
print(f'Processed {optimized} PNGs')
print(f'Before: {total_before / 1_000_000:.0f} MB')
print(f'After:  {total_after / 1_000_000:.0f} MB')
print(f'Saved:  {saved_total:.0f} MB ({saved_total / total_before * 100:.0f}%)')
