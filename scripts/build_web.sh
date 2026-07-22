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
    --exclude 'img/figures/build_hierarchy/build_hierarchy2.png' \
    nepal_kings/ "$APP/"

RAW_IMG_MB=$(du -sm "$APP/img" | cut -f1)
echo "   Staged image tree: ${RAW_IMG_MB} MB (before web optimization)"

# Native Web Audio needs URL-addressable files outside pygbag's mounted
# archive. OGG is preferred; MP3 covers iOS versions without OGG containers.
mkdir -p "$WEB_AUDIO_STAGE"
WEB_OGG_COUNT=$(find "$APP/sound" -type f -name '*.ogg' | wc -l | tr -d ' ')
WEB_MP3_COUNT=$(find "$APP/sound" -type f -name '*.mp3' | wc -l | tr -d ' ')
if [ "$WEB_OGG_COUNT" -eq 0 ] || [ "$WEB_OGG_COUNT" -ne "$WEB_MP3_COUNT" ]; then
    echo "Browser audio needs matching OGG and MP3 assets" >&2
    exit 1
fi
for ogg in "$APP"/sound/*.ogg; do
    [ -f "${ogg%.ogg}.mp3" ] || {
        echo "Missing MP3 companion for $ogg" >&2
        exit 1
    }
done
cp "$APP"/sound/*.ogg "$APP"/sound/*.mp3 "$WEB_AUDIO_STAGE/"
WEB_AUDIO_COUNT=$((WEB_OGG_COUNT + WEB_MP3_COUNT))

# MP3 files are consumed directly by Web Audio and need not also be mounted
# inside pygbag's archive. Keep OGG there for its SDL fallback path.
find "$APP/sound" -type f -name '*.mp3' -delete

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
echo "   Archive audio: OGG only (${PRUNED_WAVS} WAV masters omitted)"

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
    WEB_BUILD_ID="${GITHUB_SHA:-}"
    if [ -z "$WEB_BUILD_ID" ]; then
        WEB_BUILD_ID="$(git rev-parse HEAD 2>/dev/null || printf 'dev')"
    fi
    WEB_BUILD_ID="${WEB_BUILD_ID:0:12}"
    WEB_SFX_MANIFEST="$("$PYTHON" -c '
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
names = sorted(
    path.name for path in root.glob("*.ogg")
    if not path.name.startswith("music_")
)
print(json.dumps(names, separators=(",", ":")))
' "$WEB_AUDIO_STAGE")"
    if [ "$WEB_SFX_MANIFEST" = "[]" ]; then
        echo "Browser SFX manifest is empty" >&2
        exit 1
    fi
    sed -i.bak \
        -e "s/__NK_WEB_BUNDLE_VERSION__/${WEB_BUILD_ID}/g" \
        -e "s/__NK_WEB_SFX_MANIFEST__/${WEB_SFX_MANIFEST}/g" \
        "$WEB_OUT/index.html"
    rm -f "$WEB_OUT/index.html.bak"
    if grep -Eq '__NK_WEB_(BUNDLE_VERSION|SFX_MANIFEST)__' \
            "$WEB_OUT/index.html"; then
        echo "Failed to stamp web audio metadata" >&2
        exit 1
    fi
    echo "   Applied custom index.html (bundle ${WEB_BUILD_ID}, SFX preloaded)"
fi

mkdir -p "$WEB_OUT/audio"
cp "$WEB_AUDIO_STAGE"/*.ogg "$WEB_AUDIO_STAGE"/*.mp3 "$WEB_OUT/audio/"
echo "   Published ${WEB_AUDIO_COUNT} native Web Audio assets "\
     "(${WEB_OGG_COUNT} OGG + ${WEB_MP3_COUNT} MP3)"

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
