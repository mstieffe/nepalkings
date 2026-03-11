#!/bin/bash
# Run Nepal Kings against the REMOTE PythonAnywhere server.
#
# Usage:
#   ./run_remote.sh             # use saved resolution
#   ./run_remote.sh -s          # open settings picker first

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/nepal_kings"

echo "=== Nepal Kings — Remote Server ==="
echo "Connecting to https://nepalkings.pythonanywhere.com"
echo ""

python main.py --server-url https://nepalkings.pythonanywhere.com "$@"
