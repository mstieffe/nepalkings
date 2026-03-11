#!/bin/bash
# Deploy Nepal Kings server to PythonAnywhere.
#
# Usage:
#   ./deploy_server.sh
#
# First-time setup:
#   1. Get your API token from https://www.pythonanywhere.com/user/nepalkings/account/#api_token
#   2. Either export it:  export PA_API_TOKEN="your-token-here"
#      Or create a file:  echo "your-token-here" > ~/.nepalkings_pa_token
#
# What this script does:
#   1. Zips the server/ directory (no cache files, ~65KB)
#   2. Uploads it to PythonAnywhere via their API
#   3. Unzips it on PythonAnywhere (overwrites existing files)
#   4. Reloads the web app so changes take effect

set -e

PA_USER="nepalkings"
PA_HOST="www.pythonanywhere.com"
PA_DOMAIN="${PA_USER}.pythonanywhere.com"

# ── Resolve API token ──────────────────────────────────────────────
if [ -z "$PA_API_TOKEN" ]; then
    TOKEN_FILE="$HOME/.nepalkings_pa_token"
    if [ -f "$TOKEN_FILE" ]; then
        PA_API_TOKEN=$(cat "$TOKEN_FILE" | tr -d '[:space:]')
    else
        echo "❌ No API token found."
        echo "   Set PA_API_TOKEN env var or create ~/.nepalkings_pa_token"
        echo "   Get your token: https://www.pythonanywhere.com/user/${PA_USER}/account/#api_token"
        exit 1
    fi
fi

# ── Navigate to repo root ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Nepal Kings — Deploy Server to PythonAnywhere ==="
echo ""

# ── 1. Create zip ─────────────────────────────────────────────────
ZIP_FILE="/tmp/nepalkings_server.zip"
echo "📦 Zipping server files..."
rm -f "$ZIP_FILE"
zip -r "$ZIP_FILE" server/ pythonanywhere_wsgi.py setup_pythonanywhere.sh \
    -x "*__pycache__*" "server/instance/*" "*.DS_Store" -q
ZIP_SIZE=$(ls -lh "$ZIP_FILE" | awk '{print $5}')
echo "   Created $ZIP_FILE ($ZIP_SIZE)"

# ── 2. Upload to PythonAnywhere ───────────────────────────────────
echo "⬆️  Uploading to PythonAnywhere..."
UPLOAD_URL="https://${PA_HOST}/api/v0/user/${PA_USER}/files/path/home/${PA_USER}/nepalkings_server.zip"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Authorization: Token ${PA_API_TOKEN}" \
    -F "content=@${ZIP_FILE}" \
    "$UPLOAD_URL")

if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "201" ]; then
    echo "❌ Upload failed (HTTP $HTTP_CODE). Check your API token."
    exit 1
fi
echo "   Upload OK"

# ── 3. Unzip on PythonAnywhere ────────────────────────────────────
echo "📂 Unzipping on PythonAnywhere..."
CONSOLE_URL="https://${PA_HOST}/api/v0/user/${PA_USER}/consoles/"

# Create a temporary console to run the unzip command
CONSOLE_RESPONSE=$(curl -s \
    -X POST \
    -H "Authorization: Token ${PA_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"executable": "bash", "arguments": "", "working_directory": "/home/'"${PA_USER}"'"}' \
    "$CONSOLE_URL")

CONSOLE_ID=$(echo "$CONSOLE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

if [ -z "$CONSOLE_ID" ]; then
    echo "⚠️  Could not create console automatically."
    echo "   Please run this in a PythonAnywhere Bash console:"
    echo ""
    echo "   cd ~ && mkdir -p nepalkings && cd nepalkings && unzip -o ~/nepalkings_server.zip && rm ~/nepalkings_server.zip"
    echo ""
else
    # Send commands to the console
    SEND_URL="https://${PA_HOST}/api/v0/user/${PA_USER}/consoles/${CONSOLE_ID}/send_input/"
    curl -s -o /dev/null \
        -X POST \
        -H "Authorization: Token ${PA_API_TOKEN}" \
        -d "input=cd ~ && mkdir -p nepalkings && cd nepalkings && unzip -o ~/nepalkings_server.zip && rm ~/nepalkings_server.zip\n" \
        "$SEND_URL"
    echo "   Unzip command sent"

    # Wait a moment for it to complete
    sleep 3

    # Kill the temporary console
    curl -s -o /dev/null \
        -X DELETE \
        -H "Authorization: Token ${PA_API_TOKEN}" \
        "https://${PA_HOST}/api/v0/user/${PA_USER}/consoles/${CONSOLE_ID}/"
fi

# ── 4. Reload the web app ────────────────────────────────────────
echo "🔄 Reloading web app..."
RELOAD_URL="https://${PA_HOST}/api/v0/user/${PA_USER}/webapps/${PA_DOMAIN}/reload/"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Authorization: Token ${PA_API_TOKEN}" \
    "$RELOAD_URL")

if [ "$HTTP_CODE" = "200" ]; then
    echo "   Web app reloaded"
else
    echo "   ⚠️  Reload returned HTTP $HTTP_CODE (web app may not be configured yet)"
fi

echo ""
echo "✅ Deploy complete!"
echo "   Server: https://${PA_DOMAIN}"
