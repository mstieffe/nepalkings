#!/bin/bash
# Fetch and display Nepal Kings server logs from PythonAnywhere.
#
# Usage:
#   ./fetch_logs.sh                   # Show last 200 lines of error log
#   ./fetch_logs.sh error             # error log (default)
#   ./fetch_logs.sh server            # server/access log
#   ./fetch_logs.sh -n 500            # last 500 lines
#   ./fetch_logs.sh error -n 100      # last 100 lines of error log
#   ./fetch_logs.sh --follow          # poll every 5s (like tail -f)
#
# Setup: same API token as deploy_server.sh
#   export PA_API_TOKEN="your-token"   OR   echo "token" > ~/.nepalkings_pa_token

set -e

PA_USER="nepalkings"
PA_HOST="www.pythonanywhere.com"
PA_DOMAIN="${PA_USER}.pythonanywhere.com"
CURL_TIMEOUT="--connect-timeout 10 --max-time 30"

# ── Resolve API token ──────────────────────────────────────────────
if [ -z "$PA_API_TOKEN" ]; then
    TOKEN_FILE="$HOME/.nepalkings_pa_token"
    if [ -f "$TOKEN_FILE" ]; then
        PA_API_TOKEN=$(cat "$TOKEN_FILE" | tr -d '[:space:]')
    else
        echo "❌ No API token found."
        echo "   Set PA_API_TOKEN env var or create ~/.nepalkings_pa_token"
        exit 1
    fi
fi

# ── Parse arguments ───────────────────────────────────────────────
LOG_TYPE="error"
NUM_LINES=200
FOLLOW=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        error|server)
            LOG_TYPE="$1"; shift ;;
        -n)
            NUM_LINES="$2"; shift 2 ;;
        --follow|-f)
            FOLLOW=true; shift ;;
        *)
            echo "Usage: $0 [error|server] [-n LINES] [--follow]"
            exit 1 ;;
    esac
done

# ── Build log file path ──────────────────────────────────────────
if [ "$LOG_TYPE" = "error" ]; then
    LOG_PATH="/var/log/${PA_DOMAIN}.error.log"
else
    LOG_PATH="/var/log/${PA_DOMAIN}.server.log"
fi

fetch_log() {
    curl -s $CURL_TIMEOUT \
        -H "Authorization: Token ${PA_API_TOKEN}" \
        "https://${PA_HOST}/api/v0/user/${PA_USER}/files/path${LOG_PATH}" \
    | tail -n "$NUM_LINES"
}

# ── Fetch and display ────────────────────────────────────────────
echo "📋 Fetching ${LOG_TYPE} log (last ${NUM_LINES} lines)..."
echo "   Source: ${LOG_PATH}"
echo "────────────────────────────────────────────────────────────"

if [ "$FOLLOW" = true ]; then
    PREV=""
    while true; do
        CURRENT=$(fetch_log)
        if [ "$CURRENT" != "$PREV" ]; then
            # Show only new lines
            if [ -z "$PREV" ]; then
                echo "$CURRENT"
            else
                diff <(echo "$PREV") <(echo "$CURRENT") | grep '^>' | sed 's/^> //'
            fi
            PREV="$CURRENT"
        fi
        sleep 5
    done
else
    fetch_log
fi
