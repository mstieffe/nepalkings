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
WEB_AUDIO_STAGE="$STAGING/web-audio"
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

# Native Web Audio needs URL-addressable files outside pygbag's mounted
# archive. Keep a staging copy that will be published beside index.html.
mkdir -p "$WEB_AUDIO_STAGE"
cp "$APP"/sound/*.ogg "$WEB_AUDIO_STAGE/"
WEB_AUDIO_COUNT=$(find "$WEB_AUDIO_STAGE" -type f -name '*.ogg' | wc -l | tr -d ' ')
if [ "$WEB_AUDIO_COUNT" -eq 0 ]; then
    echo "No browser audio assets found in $APP/sound" >&2
    exit 1
fi

# The browser always prefers OGG and every shipped WAV has a verified OGG
# companion. Keep lossless WAV masters in the desktop/source tree without
# making the web download carry both copies of the same audio.
PRUNED_WAVS=0
while IFS= read -r -d '' wav; do
    ogg="${wav%.wav}.ogg"
    if [ -f "$ogg" ]; then
        rm "$wav"
        PRUNED_WAVS=$((PRUNED_WAVS + 1))
    fi
done < <(find "$APP/sound" -type f -name '*.wav' -print0)
echo "   Web audio: OGG only (${PRUNED_WAVS} WAV masters omitted)"

# ── 2. Optimize the staged images for the web ────────────────────────
echo "🖼️  Optimizing images ${QUANTIZE_FLAG:+(quantize on)}..."
"$PYTHON" scripts/assets/optimize_web_pngs.py "$APP/img" $QUANTIZE_FLAG

# ── 3. Build with pygbag ─────────────────────────────────────────────
# The web client keeps OGG companions in the archive as a fallback. Leave
# pygbag's audio-format guard enabled so missing OGG files fail the build.
echo "🛠️  Running pygbag..."
"$PYTHON" -m pygbag --build "$APP"

# ── 4. Apply the custom branded index.html ───────────────────────────
WEB_OUT="$APP/build/web"
if [ -f nepal_kings/web/index.html ]; then
    cp nepal_kings/web/index.html "$WEB_OUT/index.html"
    echo "   Applied custom index.html"
fi

mkdir -p "$WEB_OUT/audio"
cp "$WEB_AUDIO_STAGE"/*.ogg "$WEB_OUT/audio/"
echo "   Published ${WEB_AUDIO_COUNT} native Web Audio assets"

# ── 5. Report final bundle size ──────────────────────────────────────
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
