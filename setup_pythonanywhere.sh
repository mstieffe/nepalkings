#!/bin/bash
# PythonAnywhere setup script for Nepal Kings server
# Run: bash ~/nepalkings/setup_pythonanywhere.sh

set -e

echo "=== Nepal Kings Server Setup ==="

# Create virtualenv if it doesn't exist
if [ ! -d "$HOME/.virtualenvs/nepalkings" ]; then
    echo "Creating virtualenv..."
    mkvirtualenv nepalkings --python=python3.10
else
    echo "Virtualenv exists, activating..."
    source ~/.virtualenvs/nepalkings/bin/activate
fi

# Install dependencies
echo "Installing server dependencies..."
pip install -r ~/nepalkings/server/requirements.txt

# Create database directory
mkdir -p ~/nepalkings/server/instance

# Initialize database
echo "Initializing database..."
cd ~/nepalkings/server
DROP_TABLES_ON_STARTUP=True DB_URL="sqlite:///$(pwd)/instance/nepalkings.db" python -c "from wsgi import application; print('DB initialized')"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Now do these manual steps in the PythonAnywhere Web tab:"
echo "1. Add a new web app -> Manual configuration -> Python 3.10"
echo "2. Source code: /home/nepalkings/nepalkings/server"
echo "3. Virtualenv: /home/nepalkings/.virtualenvs/nepalkings"
echo "4. Edit the WSGI file (replace ALL contents with):"
echo ""
echo "   import sys, os"
echo "   path = '/home/nepalkings/nepalkings/server'"
echo "   if path not in sys.path:"
echo "       sys.path.insert(0, path)"
echo "   os.environ['DROP_TABLES_ON_STARTUP'] = 'False'"
echo "   os.environ['DB_URL'] = f'sqlite:///{path}/instance/nepalkings.db'"
echo "   os.environ['SERVER_URL'] = 'https://nepalkings.pythonanywhere.com'"
echo "   from wsgi import application"
echo ""
echo "5. Click Reload"
echo "6. Test: visit https://nepalkings.pythonanywhere.com/auth/login"
