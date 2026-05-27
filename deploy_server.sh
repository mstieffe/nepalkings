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
#   1. Finds all deployable files (server/, pythonanywhere_wsgi.py, etc.)
#   2. Uploads each file directly to PythonAnywhere via the Files API
#   3. Verifies the deploy by checking server_settings.py
#   4. Reloads the web app so changes take effect

set -e

PA_USER="nepalkings"
PA_HOST="www.pythonanywhere.com"
PA_DOMAIN="${PA_USER}.pythonanywhere.com"
PA_BASE="/home/${PA_USER}/nepalkings"
CURL_TIMEOUT="--connect-timeout 15 --max-time 60"

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

# ── 1. Collect files to deploy ────────────────────────────────────
echo "📦 Collecting files..."
FILES=$(find server/ -type f \
    ! -path "*__pycache__*" \
    ! -path "server/instance/*" \
    ! -name "*.DS_Store" \
    ! -name "*.pyc")
# Also include root-level deploy helpers
for extra in pythonanywhere_wsgi.py setup_pythonanywhere.sh; do
    [ -f "$extra" ] && FILES="$FILES"$'\n'"$extra"
done
FILE_COUNT=$(echo "$FILES" | wc -l | tr -d ' ')
echo "   Found $FILE_COUNT files to upload"

# ── 2. Upload each file via Files API ─────────────────────────────
echo "⬆️  Uploading files..."
FAIL_COUNT=0
OK_COUNT=0

while IFS= read -r filepath; do
    [ -z "$filepath" ] && continue
    REMOTE_PATH="${PA_BASE}/${filepath}"
    UPLOAD_URL="https://${PA_HOST}/api/v0/user/${PA_USER}/files/path${REMOTE_PATH}"
    HTTP_CODE=""
    DELAY=3
    for ATTEMPT in 1 2 3 4 5; do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" $CURL_TIMEOUT \
            -X POST \
            -H "Authorization: Token ${PA_API_TOKEN}" \
            -F "content=@${filepath}" \
            "$UPLOAD_URL")
        if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
            break
        fi
        if [ "$HTTP_CODE" = "429" ] && [ "$ATTEMPT" -lt 5 ]; then
            echo "   ⏳ Rate limited: $filepath (retry $ATTEMPT/5 in ${DELAY}s)"
            sleep "$DELAY"
            DELAY=$((DELAY * 2))
            continue
        fi
        break
    done
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
        OK_COUNT=$((OK_COUNT + 1))
    else
        echo "   ⚠️  Failed: $filepath (HTTP $HTTP_CODE)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
    sleep 0.25
done <<< "$FILES"

echo "   Uploaded $OK_COUNT/$FILE_COUNT files"
if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "   ❌ $FAIL_COUNT files failed to upload"
    exit 1
fi

# ── 3. Verify deploy ─────────────────────────────────────────────
echo "🔍 Verifying deploy..."
VERIFY_URL="https://${PA_HOST}/api/v0/user/${PA_USER}/files/path${PA_BASE}/server/server_settings.py"
REMOTE_CONTENT=$(curl -s $CURL_TIMEOUT \
    -H "Authorization: Token ${PA_API_TOKEN}" \
    "$VERIFY_URL")
LOCAL_CONTENT=$(cat server/server_settings.py)

if [ "$REMOTE_CONTENT" = "$LOCAL_CONTENT" ]; then
    echo "   ✅ server_settings.py verified"
else
    echo "   ❌ server_settings.py does NOT match local!"
    exit 1
fi

# ── 4. Reload the web app ────────────────────────────────────────
echo "🔄 Reloading web app (this may take up to 2 minutes)..."
RELOAD_URL="https://${PA_HOST}/api/v0/user/${PA_USER}/webapps/${PA_DOMAIN}/reload/"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 15 --max-time 180 \
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
