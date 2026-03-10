# Nepal Kings — Deployment Guide

## Server Deployment (PythonAnywhere)

### 1. Create your account
- Go to [pythonanywhere.com](https://www.pythonanywhere.com) and sign up (free tier works)
- Note your username — your server will be at `https://USERNAME.pythonanywhere.com`

### 2. Upload the code
Open a **Bash console** on PythonAnywhere:
```bash
cd ~
git clone <your-repo-url> nepalkings
# Or upload a .zip and unzip it
```

### 3. Create a virtual environment
```bash
mkvirtualenv nepalkings --python=python3.10
pip install -r ~/nepalkings/server/requirements.txt
```

### 4. Configure the Web App
- Go to the **Web** tab → **Add a new web app**
- Choose **Manual configuration** → **Python 3.10**
- Set **Source code** to: `/home/USERNAME/nepalkings/server`
- Set **Virtualenv** to: `/home/USERNAME/.virtualenvs/nepalkings`

### 5. Edit the WSGI configuration file
PythonAnywhere gives you a WSGI file to edit. Replace its contents with:
```python
import sys
import os

path = '/home/USERNAME/nepalkings/server'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DROP_TABLES_ON_STARTUP'] = 'False'
os.environ['DB_URL'] = f'sqlite:///{path}/instance/nepalkings.db'

from wsgi import application
```
Replace `USERNAME` with your PythonAnywhere username.

### 6. Create the database directory
```bash
mkdir -p ~/nepalkings/server/instance
```

### 7. Initialize the database (first time only)
Open a Bash console:
```bash
workon nepalkings
cd ~/nepalkings/server
DROP_TABLES_ON_STARTUP=True python -c "from wsgi import application"
```
This creates the tables. They persist across reloads.

### 8. Reload and test
- Click **Reload** on the Web tab
- Visit `https://USERNAME.pythonanywhere.com/auth/login` — should return a JSON response

---

## Client Distribution

### For technical testers (easiest)
Share the repo + instructions:
```bash
git clone <repo-url>
cd nepalkings/nepal_kings
pip install -r requirements.txt
python main.py --server-url https://USERNAME.pythonanywhere.com
```
The server URL is saved to `~/.nepalkings/resolution.json` and remembered.

### For non-technical testers (bundled app)
Build platform-specific executables using PyInstaller.

#### macOS
```bash
cd nepal_kings
pip install pyinstaller
pyinstaller nepal_kings.spec
```
Produces `dist/NepalKings.app` — zip it and share.

#### Windows (must be built on Windows)
```cmd
cd nepal_kings
pip install pyinstaller
pyinstaller nepal_kings.spec
```
Produces `dist/NepalKings.exe`.

#### Automated builds (GitHub Actions)
Push to GitHub and the CI workflow builds macOS + Windows + Linux
executables automatically. Download them from the GitHub Releases page.

---

## Configuration

All settings are stored in `~/.nepalkings/resolution.json`:
```json
{
  "width": 1920,
  "height": 1080,
  "server_url": "https://USERNAME.pythonanywhere.com"
}
```

### CLI flags
| Flag | Description |
|------|-------------|
| `--server-url URL` | Set the server URL |
| `--pick-resolution` / `-r` | Force the resolution picker |

### Environment variables (override config file)
| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_URL` | `http://localhost:5000` | Server base URL |
| `NK_SCREEN_WIDTH` | `1920` | Game window width |
| `NK_SCREEN_HEIGHT` | `1080` | Game window height |
