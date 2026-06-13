#!/bin/bash
# Package the web build as an itch.io-ready HTML5 zip.
#
# itch.io serves an HTML5 game from a zip whose index.html sits at the
# archive root. This script (re)builds the optimized web bundle and zips
# it into dist/nepal_kings-itch.zip, ready to upload as the game files
# (set "This file will be played in the browser" on itch).
#
# Usage:
#   scripts/package_itch.sh            # build + package
#   scripts/package_itch.sh --skip-build   # reuse the last web build

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

WEB_OUT="build/web-staging/nepal_kings/build/web"
OUT_ZIP="dist/nepal_kings-itch.zip"

SKIP_BUILD=false
for arg in "$@"; do
    [ "$arg" = "--skip-build" ] && SKIP_BUILD=true
done

if [ "$SKIP_BUILD" = false ]; then
    bash "$SCRIPT_DIR/build_web.sh"
fi

if [ ! -f "$WEB_OUT/index.html" ]; then
    echo "❌ No web build found at $WEB_OUT — run without --skip-build first."
    exit 1
fi

echo "📦 Packaging $WEB_OUT for itch.io ..."
mkdir -p dist
rm -f "$OUT_ZIP"
# Zip the CONTENTS of the web dir so index.html is at the archive root.
( cd "$WEB_OUT" && zip -r -q "$ROOT/$OUT_ZIP" . -x '*.DS_Store' )

SIZE=$(du -h "$OUT_ZIP" | cut -f1)
echo ""
echo "✅ itch.io package ready: $OUT_ZIP ($SIZE)"
echo "   Upload it on itch, tick 'This file will be played in the browser',"
echo "   set the viewport to 1280x720 (or larger), and enable fullscreen."
