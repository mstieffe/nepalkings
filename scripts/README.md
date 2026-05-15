# Scripts

Developer and maintenance utilities. **Not** imported by the runtime.
Run from anywhere — each script resolves the repo root from its own
location.

## `assets/`
PNG / icon pipeline tools.

| Script | Purpose |
|---|---|
| `check_png_profiles.py` | Report PNGs with embedded ICC profiles. |
| `fix_png_profiles.py` | Strip ICC profiles using Pillow. |
| `fix_png_profiles.sh` | Strip ICC profiles using ImageMagick. |
| `find_unused_pngs.py` | Move PNGs unreferenced by source into `img/_legacy/`. |
| `list_oversized_pngs.py` | List PNGs by file size. |
| `optimize_pngs.py` | Downscale + recompress PNGs to per-folder maxima. |
| `generate_gold_grey.py` | One-off: greyed `gold_lost.png` from `gold.png`. |
| `generate_icons.sh` | Regenerate `.icns` / `.ico` from `app_icon.png`. |

## `debug/`
Local diagnostics. Never deploy these.

| Script | Purpose |
|---|---|
| `analyze_memory.py` | Estimate RGBA surface memory of game PNGs. |
| `poll_ai_debug.py` | Live-poll the AI debug endpoint during a game. |
| `print_database.py` | Print contents of the local SQLite DB. |

## Deploy / ops scripts (kept at repo root)

`deploy_server.sh`, `fetch_logs.sh`, `run_local.sh`, `run_remote.sh`,
`setup_pythonanywhere.sh`, `build_installer.sh`, and
`pythonanywhere_wsgi.py` remain at the repository root because they are
referenced by the production hosting configuration (PythonAnywhere WSGI
points at `pythonanywhere_wsgi.py`; `deploy_server.sh` rsyncs by
hard-coded path). Moving them is a deploy-config change and must be
coordinated with a hosting update.
