# Nepal Kings — Deployment Guide

## Server deployment (PythonAnywhere EU)

The public-launch layout uses the paid PythonAnywhere EU account, managed WSGI
workers, PostgreSQL, a separate staging database, private environment files,
and explicit pre-reload migrations. Follow the authoritative runbook:

[PythonAnywhere EU production layout](../deploy/pythonanywhere/README.md)

Important boundaries:

- Use Python 3.11 for the server.
- Do not install packages or migrate the schema during a WSGI import.
- Do not put secrets in the repository or provider WSGI file.
- Do not use SQLite for staging or production.
- Allow the GitHub Pages origin as `https://mstieffe.github.io`; CORS origins
  never contain the `/nepalkings/` path.
- Check both `/healthz` and `/readyz` after every reload.

The exact pre-upgrade single-worker SQLite deployment remains available on
`backup/pythonanywhere-free-eu-2026-07-19` as an emergency free-plan fallback.
Its database is not interchangeable with the new PostgreSQL database.

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
