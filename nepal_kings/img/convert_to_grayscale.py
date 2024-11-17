import os
from PIL import Image
from pathlib import Path

for p in Path('./figures_new/castle/').glob('*.png'):
    print(f"Processing {p}...")
    img = Image.open(p).convert('L')
    new_path = Path(f"./figures_new/castle/{p.name}_gray.png")
    img.save(str(new_path))
