#!/bin/bash
# PythonAnywhere paid-account setup for Nepal Kings.
# Run only after creating and populating the private environment file:
#   bash ~/nepalkings/setup_pythonanywhere.sh production

set -e

ENVIRONMENT="${1:-}"
if [ "$ENVIRONMENT" != "staging" ] && [ "$ENVIRONMENT" != "production" ]; then
    echo "Usage: $0 staging|production"
    exit 2
fi

ENV_FILE="$HOME/.config/nepalkings/${ENVIRONMENT}.env"
if [ ! -s "$ENV_FILE" ]; then
    echo "Missing private environment file: $ENV_FILE"
    echo "See deploy/pythonanywhere/README.md"
    exit 1
fi

echo "=== Nepal Kings Server Setup ==="

# Create virtualenv if it doesn't exist
if [ ! -d "$HOME/.virtualenvs/nepalkings" ]; then
    echo "Creating virtualenv..."
    python3.11 -m venv "$HOME/.virtualenvs/nepalkings"
else
    echo "Virtualenv exists"
fi

# Use the virtualenv's pip directly (no activate script needed)
PIP="$HOME/.virtualenvs/nepalkings/bin/pip"
PYTHON="$HOME/.virtualenvs/nepalkings/bin/python"

# Install dependencies
echo "Installing server dependencies..."
"$PIP" install -r ~/nepalkings/server/requirements.txt

echo "Preparing ${ENVIRONMENT} database explicitly..."
cd ~/nepalkings/server
NEPAL_KINGS_ENV_FILE="$ENV_FILE" "$PYTHON" manage.py prepare-database

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Configure/reload the web app using deploy/pythonanywhere/README.md."
