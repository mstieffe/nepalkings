#!/bin/bash
# Regenerate all icon files from nepal_kings/img/app_icon/app_icon.png
#
# Usage:
#   ./generate_icons.sh
#
# Prerequisites:
#   - Pillow: pip install Pillow
#   - iconutil (macOS only, built-in)

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ICON_DIR="$SCRIPT_DIR/nepal_kings/img/app_icon"
SRC="$ICON_DIR/app_icon.png"

if [ ! -f "$SRC" ]; then
    echo "❌ Source icon not found: $SRC"
    exit 1
fi

echo "=== Generating icons from app_icon.png ==="

# ── Find Python with Pillow ───────────────────────────────────────
if conda run -n nepalkings python -c "from PIL import Image" 2>/dev/null; then
    PY="conda run -n nepalkings python"
elif python3 -c "from PIL import Image" 2>/dev/null; then
    PY="python3"
elif python -c "from PIL import Image" 2>/dev/null; then
    PY="python"
else
    echo "❌ Pillow not found. Install it first:"
    echo "   pip install Pillow"
    exit 1
fi

# ── Generate sized PNGs + Windows .ico ────────────────────────────
$PY -c "
from PIL import Image

src = Image.open('$SRC').convert('RGBA')
w, h = src.size
size = max(w, h)
square = Image.new('RGBA', (size, size), (0, 0, 0, 0))
square.paste(src, ((size - w) // 2, (size - h) // 2))
print(f'   Source: {w}x{h}, canvas: {size}x{size}')

for s in [16, 32, 48, 64, 128, 256, 512, 1024]:
    out = '$ICON_DIR/icon_' + str(s) + 'x' + str(s) + '.png'
    square.resize((s, s), Image.LANCZOS).save(out)
    print(f'   {out.split(\"/\")[-1]}')

ico_sizes = [16, 32, 48, 64, 128, 256]
ico_images = [square.resize((s, s), Image.LANCZOS) for s in ico_sizes]
ico_images[0].save('$ICON_DIR/app_icon.ico', format='ICO',
    sizes=[(s, s) for s in ico_sizes], append_images=ico_images[1:])
print('   app_icon.ico')
"

# ── Generate macOS .icns ──────────────────────────────────────────
if command -v iconutil &>/dev/null; then
    ICONSET="$ICON_DIR/app_icon.iconset"
    rm -rf "$ICONSET" && mkdir "$ICONSET"
    cp "$ICON_DIR/icon_16x16.png"     "$ICONSET/icon_16x16.png"
    cp "$ICON_DIR/icon_32x32.png"     "$ICONSET/icon_16x16@2x.png"
    cp "$ICON_DIR/icon_32x32.png"     "$ICONSET/icon_32x32.png"
    cp "$ICON_DIR/icon_64x64.png"     "$ICONSET/icon_32x32@2x.png"
    cp "$ICON_DIR/icon_128x128.png"   "$ICONSET/icon_128x128.png"
    cp "$ICON_DIR/icon_256x256.png"   "$ICONSET/icon_128x128@2x.png"
    cp "$ICON_DIR/icon_256x256.png"   "$ICONSET/icon_256x256.png"
    cp "$ICON_DIR/icon_512x512.png"   "$ICONSET/icon_256x256@2x.png"
    cp "$ICON_DIR/icon_512x512.png"   "$ICONSET/icon_512x512.png"
    cp "$ICON_DIR/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png"
    iconutil -c icns "$ICONSET" -o "$ICON_DIR/app_icon.icns"
    echo "   app_icon.icns"
else
    echo "   ⚠ iconutil not found (not macOS?) — skipping .icns generation"
fi

echo ""
echo "✅ All icons regenerated!"
echo "   Now rebuild the app:  ./build_installer.sh"
