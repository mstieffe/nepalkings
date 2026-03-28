# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""One-time script to generate the greyed-out gold icon with red cross."""
import subprocess, sys

try:
    from PIL import Image, ImageDraw
    import numpy as np
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'Pillow', 'numpy'])
    from PIL import Image, ImageDraw
    import numpy as np

src = 'nepal_kings/img/dialogue_box/icons/gold.png'
dst = 'nepal_kings/img/dialogue_box/icons/gold_lost.png'

img = Image.open(src).convert('RGBA')
arr = np.array(img)
lum = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]).astype(np.uint8)
grey_rgba = np.stack([lum, lum, lum, arr[:, :, 3]], axis=2)
grey_img = Image.fromarray(grey_rgba, 'RGBA')

# Draw red cross
draw = ImageDraw.Draw(grey_img)
w, h = grey_img.size
margin = int(min(w, h) * 0.15)
thickness = max(6, int(min(w, h) * 0.06))
draw.line([(margin, margin), (w - margin, h - margin)], fill=(220, 40, 40, 255), width=thickness)
draw.line([(w - margin, margin), (margin, h - margin)], fill=(220, 40, 40, 255), width=thickness)

grey_img.save(dst)
print(f'Saved to {dst} ({w}x{h})')
