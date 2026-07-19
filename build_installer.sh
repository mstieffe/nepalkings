#!/bin/bash
# Build a standalone Nepal Kings installer/app for distribution.
#
# This creates a single-file executable (or macOS .app bundle) that
# users can run without installing Python, Pygame, or opening a terminal.
#
# The build defaults to the remote PythonAnywhere server so recipients
# can play immediately.
#
# Usage:
#   ./build_installer.sh                  # build for current platform
#   ./build_installer.sh --server-url URL # bake in a custom server URL
#
# Prerequisites (one-time):
#   pip install pyinstaller
#
# Output:
#   macOS   → nepal_kings/dist/NepalKings.app   (drag to /Applications)
#   Windows → nepal_kings/dist/NepalKings.exe
#   Linux   → nepal_kings/dist/NepalKings

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/nepal_kings"

# ── Parse optional server URL override ────────────────────────────
SERVER_URL="https://api-nepalkingz.eu.pythonanywhere.com"
for i in "$@"; do
    if [ "$prev" = "--server-url" ]; then
        SERVER_URL="$i"
    fi
    prev="$i"
done

echo "=== Nepal Kings — Build Installer ==="
echo "   Platform:   $(uname -s) $(uname -m)"
echo "   Server URL: $SERVER_URL"
echo ""

# ── Patch default server URL into main.py for this build ──────────
# We temporarily set it so the built app defaults to the remote server.
ORIG_DEFAULT=$(grep "^_DEFAULT_SERVER_URL" main.py)
sed -i.bak "s|^_DEFAULT_SERVER_URL = .*|_DEFAULT_SERVER_URL = '${SERVER_URL}'|" main.py

# Restore on exit
trap "mv main.py.bak main.py; echo 'Restored main.py'" EXIT

# ── Check for PyInstaller ─────────────────────────────────────────
if command -v pyinstaller &>/dev/null; then
    PYINSTALLER="pyinstaller"
elif conda run -n nepalkings pyinstaller --version &>/dev/null 2>&1; then
    PYINSTALLER="conda run -n nepalkings pyinstaller"
else
    echo "❌ PyInstaller not found. Install it first:"
    echo "   pip install pyinstaller"
    exit 1
fi

# ── Build ─────────────────────────────────────────────────────────
echo "Building with PyInstaller..."
$PYINSTALLER nepal_kings.spec --clean --noconfirm 2>&1 | tail -5

echo ""
echo "✅ Build complete!"
if [ "$(uname -s)" = "Darwin" ]; then
    echo "   Output: $(pwd)/dist/NepalKings.app"
    echo ""
    echo "   To distribute:"
    echo "     1. Drag NepalKings.app to /Applications to install"
    echo "     2. Or zip it:  cd dist && zip -r NepalKings-macOS.zip NepalKings.app"
    echo "     3. Share the .zip — recipients unzip and double-click"
elif [ "$(uname -s)" = "Linux" ]; then
    echo "   Output: $(pwd)/dist/NepalKings"
    echo "   Share this single file — recipients chmod +x and run it."
else
    echo "   Output: $(pwd)/dist/NepalKings.exe"
    echo "   Share the .exe — recipients double-click to play."
fi
