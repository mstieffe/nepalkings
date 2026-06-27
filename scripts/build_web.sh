#!/bin/bash
# Build the web (pygbag) bundle from a size-optimized staging copy.
#
# The committed source art in nepal_kings/img is full resolution and is
# NEVER modified by this script. Instead the app is staged into
# build/web-staging/, its images are downscaled + quantized for the web
# (scripts/assets/optimize_web_pngs.py), and pygbag builds from there.
#
# Usage:
#   scripts/build_web.sh                 # optimized build (quantize on)
#   scripts/build_web.sh --no-quantize   # downscale only, no palette step
#   NK_WEB_SERVE=1 scripts/build_web.sh  # serve locally after building
#
# Output: build/web-staging/nepal_kings/build/web/  (index.html + .apk)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
STAGING="build/web-staging"
APP="$STAGING/nepal_kings"
QUANTIZE_FLAG="--quantize"
for arg in "$@"; do
    [ "$arg" = "--no-quantize" ] && QUANTIZE_FLAG=""
done

echo "=== Nepal Kings — Web Bundle Build ==="

# ── 1. Stage a clean copy of the app (no legacy art, caches, builds) ──
echo "📦 Staging app to $APP ..."
rm -rf "$STAGING"
mkdir -p "$APP"
# rsync keeps this readable; excludes mirror pygbag.ini ignores + build cruft.
rsync -a \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'build' \
    --exclude 'dist' \
    --exclude 'img/_legacy' \
    --exclude 'img/figures_old' \
    --exclude 'img/old_cards' \
    --exclude 'img/_button' \
    --exclude 'img/app_icon' \
    nepal_kings/ "$APP/"

RAW_IMG_MB=$(du -sm "$APP/img" | cut -f1)
echo "   Staged image tree: ${RAW_IMG_MB} MB (before web optimization)"

# ── 2. Optimize the staged images for the web ────────────────────────
echo "🖼️  Optimizing images ${QUANTIZE_FLAG:+(quantize on)}..."
"$PYTHON" scripts/assets/optimize_web_pngs.py "$APP/img" $QUANTIZE_FLAG

# ── 3. Build with pygbag ─────────────────────────────────────────────
# --disable-sound-format-error: our SFX are tiny 16-bit PCM WAVs, which
# browsers decode fine via SDL; pygbag's OGG preference is just a warning.
echo "🛠️  Running pygbag..."
"$PYTHON" -m pygbag --build --disable-sound-format-error "$APP"

# ── 4. Apply the custom branded index.html ───────────────────────────
if [ -f nepal_kings/web/index.html ]; then
    cp nepal_kings/web/index.html "$APP/build/web/index.html"
    echo "   Applied custom index.html"
fi

# ── 5. Report final bundle size ──────────────────────────────────────
WEB_OUT="$APP/build/web"
echo ""
echo "✅ Web bundle ready: $WEB_OUT"
if [ -d "$WEB_OUT" ]; then
    du -sh "$WEB_OUT" | sed 's/^/   total: /'
    for f in "$WEB_OUT"/*.apk "$WEB_OUT"/*.tar.gz; do
        [ -f "$f" ] && du -h "$f" | sed 's/^/   /'
    done
fi

if [ "${NK_WEB_SERVE:-0}" = "1" ]; then
    echo ""
    echo "🌐 Serving at http://localhost:8000 (Ctrl+C to stop)"
    ( cd "$WEB_OUT" && "$PYTHON" -m http.server 8000 )
fi
