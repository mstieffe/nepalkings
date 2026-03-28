# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
#!/usr/bin/env python3
"""Analyze in-memory size of all active PNGs (RGBA surfaces)."""
from PIL import Image
import os
from collections import defaultdict

IMG_DIR = 'nepal_kings/img'
SKIP = {'_legacy', 'figures_old', 'old_cards', 'app_icon'}
results = []

for root, dirs, files in os.walk(IMG_DIR):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for f in files:
        if not f.lower().endswith('.png'):
            continue
        path = os.path.join(root, f)
        try:
            with Image.open(path) as img:
                w, h = img.size
                mem_mb = w * h * 4 / 1_000_000
                results.append((mem_mb, w, h, os.path.relpath(path, IMG_DIR)))
        except:
            pass

results.sort(reverse=True)
total = sum(m for m, _, _, _ in results)
print(f'Total in-memory (all PNGs loaded once): {total:.0f} MB')
print(f'Total file count: {len(results)}')
print()
print('Top 40 by memory consumption:')
for mem, w, h, path in results[:40]:
    print(f'  {mem:>8.1f} MB  {w:>6}x{h:<6}  {path}')
print()

dir_totals = defaultdict(lambda: [0, 0])
for mem, w, h, path in results:
    d = path.split('/')[0] if '/' in path else '.'
    dir_totals[d][0] += mem
    dir_totals[d][1] += 1
print('Memory by top-level directory:')
for d, (total_mem, count) in sorted(dir_totals.items(), key=lambda x: -x[1][0]):
    print(f'  {total_mem:>8.1f} MB  ({count:>3} files)  {d}/')
