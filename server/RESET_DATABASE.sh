#!/bin/bash
# DESTRUCTIVE: drop and recreate every database table (local development only).
#
# This is NOT a migration tool. Schema changes ship via
# server/migration_runner.py and apply automatically at server startup;
# production data must never be reset. Production deploys also take an
# automatic backup first (see deploy_server.sh / scripts/restore_db_backup.sh).

set -e

case "$(echo "${FLASK_ENV:-}" | tr '[:upper:]' '[:lower:]')" in
    ""|dev|development|local|test) ;;
    *)
        echo "❌ FLASK_ENV='${FLASK_ENV}' looks like production."
        echo "   Refusing to drop tables. Use migrations instead"
        echo "   (server/migration_runner.py), or restore a backup with"
        echo "   scripts/restore_db_backup.sh."
        exit 1
        ;;
esac

echo "⚠️  WARNING: This will DELETE ALL DATA in the database!"
echo "   DB_URL=${DB_URL:-sqlite:///test.db (default)}"
echo ""
if [ "$CONFIRM_RESET" != "RESET" ]; then
    read -r -p "Type RESET to continue: " CONFIRM
    if [ "$CONFIRM" != "RESET" ]; then
        echo "Aborted."
        exit 1
    fi
fi

echo ""
echo "Starting server with DROP_TABLES_ON_STARTUP=True..."
export DROP_TABLES_ON_STARTUP=True
python3 server.py
