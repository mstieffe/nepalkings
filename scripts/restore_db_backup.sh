#!/bin/bash
# Restore a database backup to the PythonAnywhere production server.
#
# Usage:
#   scripts/restore_db_backup.sh backups/nepalkings-20260612-120000.db
#
# This OVERWRITES the live production database with the given backup and
# reloads the web app. Players lose any progress made after the backup
# was taken — use only to recover from a bad deploy or data corruption.

set -e

PA_USER="nepalkings"
PA_HOST="www.pythonanywhere.com"
PA_DOMAIN="${PA_USER}.pythonanywhere.com"
PA_BASE="/home/${PA_USER}/nepalkings"
REMOTE_DB_PATH="${PA_BASE}/server/instance/nepalkings.db"
CURL_TIMEOUT="--connect-timeout 15 --max-time 120"

BACKUP_FILE="$1"
if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup-file>"
    echo "Available backups:"
    ls -lh backups/nepalkings-*.db 2>/dev/null || echo "  (none found in backups/)"
    exit 1
fi

# ── Resolve API token (same convention as deploy_server.sh) ────────
if [ -z "$PA_API_TOKEN" ]; then
    TOKEN_FILE="$HOME/.nepalkings_pa_token"
    if [ -f "$TOKEN_FILE" ]; then
        PA_API_TOKEN=$(cat "$TOKEN_FILE" | tr -d '[:space:]')
    else
        echo "❌ No API token found (set PA_API_TOKEN or ~/.nepalkings_pa_token)"
        exit 1
    fi
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "=== Nepal Kings — RESTORE PRODUCTION DATABASE ==="
echo ""
echo "  Backup:      $BACKUP_FILE ($SIZE)"
echo "  Destination: ${PA_DOMAIN}:${REMOTE_DB_PATH}"
echo ""
echo "⚠️  This OVERWRITES the live database. Progress made after this"
echo "    backup was taken will be PERMANENTLY LOST."
echo ""
read -r -p "Type RESTORE to continue: " CONFIRM
if [ "$CONFIRM" != "RESTORE" ]; then
    echo "Aborted."
    exit 1
fi

echo "⬆️  Uploading backup..."
UPLOAD_URL="https://${PA_HOST}/api/v0/user/${PA_USER}/files/path${REMOTE_DB_PATH}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" $CURL_TIMEOUT \
    -X POST \
    -H "Authorization: Token ${PA_API_TOKEN}" \
    -F "content=@${BACKUP_FILE}" \
    "$UPLOAD_URL")
if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "201" ]; then
    echo "❌ Upload failed (HTTP $HTTP_CODE)"
    exit 1
fi
echo "   ✅ Database uploaded"

echo "🔄 Reloading web app..."
RELOAD_URL="https://${PA_HOST}/api/v0/user/${PA_USER}/webapps/${PA_DOMAIN}/reload/"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 15 --max-time 180 \
    -X POST \
    -H "Authorization: Token ${PA_API_TOKEN}" \
    "$RELOAD_URL")
if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✅ Web app reloaded"
else
    echo "   ⚠️  Reload returned HTTP $HTTP_CODE — reload manually in the Web tab"
fi

echo ""
echo "✅ Restore complete"
