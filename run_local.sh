#!/bin/bash
# Run Nepal Kings against a LOCAL server (for development).
#
# This starts the Flask server in the background, then launches the client.
# When you close the client, the server is stopped automatically.
#
# Usage:
#   ./run_local.sh              # use saved resolution
#   ./run_local.sh -s           # open settings picker first

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Nepal Kings — Local Development ==="

if [ -z "${PYTHON:-}" ]; then
    if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
        PYTHON="$SCRIPT_DIR/.venv/bin/python"
    else
        PYTHON="python"
    fi
fi

# ── Start local server ─────────────────────────────────────────────
echo "Starting local server on http://localhost:5000 ..."
cd server
"$PYTHON" server.py &
SERVER_PID=$!
cd "$SCRIPT_DIR"

# Ensure the server is killed when the script exits
trap "echo 'Stopping server (PID $SERVER_PID)...'; kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null" EXIT

# Wait for server to be ready
for i in $(seq 1 10); do
    if curl -s http://localhost:5000/ > /dev/null 2>&1; then
        echo "Server ready."
        break
    fi
    sleep 0.5
done

# ── Launch client ──────────────────────────────────────────────────
echo "Launching client..."
cd nepal_kings
"$PYTHON" main.py --server-url http://localhost:5000 "$@"
