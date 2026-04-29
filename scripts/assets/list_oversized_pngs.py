# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
#!/usr/bin/env python3
"""List all active PNGs sorted by file size, showing dimensions."""
from PIL import Image
import os
from pathlib import Path

IMG_DIR = Path(__file__).resolve().parents[2] / "nepal_kings" / "img"
SKIP = {"_legacy", "figures_old", "old_cards", "app_icon"}
results = []

for root, dirs, files in os.walk(IMG_DIR):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for f in files:
        if not f.lower().endswith(".png"):
            continue
        path = os.path.join(root, f)
        size_mb = os.path.getsize(path) / 1_000_000
        try:
            with Image.open(path) as img:
                w, h = img.size
        except Exception:
            w, h = 0, 0
        results.append((size_mb, w, h, os.path.relpath(path, IMG_DIR)))

# Sort by file size descending
results.sort(reverse=True)

header = "{:<55} {:>8} {:>15}".format("File", "Size", "Dimensions")
print(header)
print("-" * 82)
for size_mb, w, h, path in results:
    if size_mb >= 1.0:
        dim = "{}x{}".format(w, h)
        print("{:<55} {:>6.1f}MB  {:>12}".format(path, size_mb, dim))

count = sum(1 for s, _, _, _ in results if s >= 1.0)
total_big = sum(s for s, _, _, _ in results if s >= 1.0)
total_all = sum(s for s, _, _, _ in results)
print()
print("Files >= 1 MB: {}".format(count))
print("Size of files >= 1 MB: {:.0f} MB".format(total_big))
print("Total all active PNGs: {:.0f} MB".format(total_all))

# Also flag images with excessive dimensions (> 4K)
print()
print("=== Images exceeding 4K (3840x2160) — candidates for downscaling ===")
for size_mb, w, h, path in results:
    if w > 3840 or h > 3840:
        dim = "{}x{}".format(w, h)
        print("  {:<55} {:>6.1f}MB  {:>12}".format(path, size_mb, dim))
