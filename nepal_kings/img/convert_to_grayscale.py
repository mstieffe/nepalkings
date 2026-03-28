# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import os
from PIL import Image
from pathlib import Path

for p in Path('./battle/icons/').glob('*.png'):
    print(f"Processing {p}...")
    img = Image.open(p).convert('L')
    #new_path = Path(f"./figures/icons_greyscale/{p.stem}_gray.png")
    new_path = Path(f"./battle/icons_greyscale/{p.stem}.png")
    img.save(str(new_path))
