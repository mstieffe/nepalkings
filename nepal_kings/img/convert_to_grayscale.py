import os
from PIL import Image
from pathlib import Path

for p in Path('./game_button/symbol/').glob('*.png'):
    print(f"Processing {p}...")
    img = Image.open(p).convert('L')
    #new_path = Path(f"./figures/icons_greyscale/{p.stem}_gray.png")
    new_path = Path(f"./game_button/symbol_greyscale/{p.stem}.png")
    img.save(str(new_path))
