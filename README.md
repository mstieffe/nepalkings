# nepalkings

<img width="1908" height="1068" alt="image" src="https://github.com/user-attachments/assets/4cb61d47-3d65-4f5d-96d9-faed1051bafa" />

# Nepal Kings

**Nepal Kings** is a two-player online card game. Some call it *the chess of cards*.  
It is a strategic duel built around the principle of **attack and defense**, played in two main phases:

1. **Build Phase** – players prepare their field, set up figures, and ready their battle cards.  
2. **Battle Phase** – the actual fight takes place, points are awarded, and attacker/defender roles may switch.  

The first player to reach the pre-set score (21, 35, or 49 points) wins the game.  

---

## Game Start

- At the beginning, roles are assigned: one **attacker**, one **defender**.  
- This is determined by cutting the deck:  
  - The revealed **symbol** defines the **Ur-King**.  
  - The revealed **color** defines the **role** (black = defender, red = attacker).  
- Each player receives **12 hand cards** (hand limit).  
  - In the first round hands are always refilled to 12 cards.  
  - In later rounds only up to 5.  

---

## Build Phase

- The phase consists of **5 regular turns**, followed by:  
  - an **advance move** from the attacker  
  - a **reaction move** from the defender  
- On a turn, a player may:  
  - exchange cards  
  - play an action card  
  - place, pick up, or modify a figure on the field  

### Sub-Phases
- **Passive Build Phase** – only passive action cards allowed, no advancing.  
- **Active Build Phase** – all action cards allowed, advancing possible.  

---

## Battle Phase

1. Both players secretly select their fighting figures and 3 battle cards.  
2. Figures are revealed, combat strength is calculated (including bonuses).  
3. Players take **3 battle turns** each to play their battle cards.  
4. The winner scores points based on the defeated figure, modified by special rules.  

### Special Battles
- **Direct Battle** – no advancing required, free choice of figures (triggered by Jacks, Queens, or Aces).  
- **Peasants’ War** – only operators may fight.  
- **King’s Battle** – forced duel with the King, featuring unique high-stakes rules.  
- **Blitzkrieg** – triggered by two Queens; attacker chooses the target.  

---

## Bonus System

- Fighting figures can receive bonus support from other field cards:  
  - Only once per donor figure.  
  - Only with matching symbols.  
- Symbol clashes follow a rock-paper-scissors pattern:  
  - hearts beats clubs
  - clubs beats diamonds
  - diamonds beats spades
  - spades beats hearts

- The losing symbol costs **–1 point**.  

---

## Game Modes

- **Limited** – only one active action card per phase (counterplay allowed).  
- **Free for all** – unlimited active action cards in sequence, all effects stack.  

---

## Card Values

| Card   | Value |
|--------|-------|
| Jack   | 1     |
| Queen  | 2     |
| Ace    | 3     |
| King   | 4     |
| Ur-King | 5 (value 15 when fighting as a figure) |
| Number Cards (ZK) | face value |

---

## Card Types

- **Action Cards** – change the course of setup or battle (e.g. Peasants’ War, Blitzkrieg, draw cards).  
- **Field Cards** – build farms, armies, towers, or upgrades.  
- **Battle Cards** – played during battle turns to shift the outcome.  

---

## Victory

The winner is the first player to reach the agreed score.  
Victory requires **careful field management, tactical card play, and strategic timing**.  

The one who succeeds earns the title of **King of Nepal**.  

---
---

# Operations Guide

Everything you need to run, build, deploy, and maintain Nepal Kings.

---

## Table of Contents (Ops)

1. [Project Structure](#project-structure)
2. [Prerequisites](#prerequisites)
3. [Initial Setup](#initial-setup)
4. [Running the Game](#running-the-game)
   - [Local development (local server)](#local-development-local-server)
   - [Remote server (PythonAnywhere)](#remote-server-pythonanywhere)
   - [Switching servers via the UI](#switching-servers-via-the-ui)
   - [CLI flags reference](#cli-flags-reference)
5. [Web Client (Browser)](#web-client-browser)
6. [Running the Server Independently](#running-the-server-independently)
7. [Deploying / Updating the Server on PythonAnywhere](#deploying--updating-the-server-on-pythonanywhere)
   - [First-time PythonAnywhere setup](#first-time-pythonanywhere-setup)
   - [Deploying updates](#deploying-updates)
8. [Building Installers for Distribution](#building-installers-for-distribution)
   - [Local build (macOS)](#local-build-macos)
   - [Cross-platform builds (GitHub Actions)](#cross-platform-builds-github-actions)
   - [Distributing to users](#distributing-to-users)
9. [Changing the App Icon](#changing-the-app-icon)
10. [Configuration & Settings](#configuration--settings)
11. [Troubleshooting](#troubleshooting)
12. [AI Opponent Internals](#ai-opponent-internals)

---

## Project Structure

```
nepalkings/
├── nepal_kings/              # Pygame client application
│   ├── main.py               # Entry point (resolution picker + launcher)
│   ├── nepal_kings.py         # Client class (game loop)
│   ├── nepal_kings.spec       # PyInstaller build spec
│   ├── requirements.txt      # Client Python dependencies
│   ├── config/               # Game settings & constants
│   ├── game/                 # Game logic, screens, components
│   │   ├── core/             # Game state, state machine
│   │   ├── screens/          # All game screens (login, menu, battle, etc.)
│   │   └── components/       # UI components (cards, figures, buttons, etc.)
│   ├── img/                  # All game images & assets
│   │   └── app_icon/         # App icon source + generated files
│   └── utils/                # Service modules (auth, game, spells, etc.)
│
├── server/                   # Flask API server
│   ├── server.py             # Flask app entry point
│   ├── models.py             # SQLAlchemy database models
│   ├── server_settings.py    # Server configuration
│   ├── requirements.txt      # Server Python dependencies
│   ├── wsgi.py               # WSGI entry point (PythonAnywhere)
│   └── routes/               # API route handlers
│
├── run_local.sh              # Run client + local server together
├── run_remote.sh             # Run client against PythonAnywhere server
├── deploy_server.sh          # Deploy server to PythonAnywhere
├── build_installer.sh        # Build standalone .app / .exe
├── pythonanywhere_wsgi.py    # WSGI config for PythonAnywhere
├── setup_pythonanywhere.sh   # First-time PythonAnywhere setup
└── .github/workflows/
    └── build.yml             # GitHub Actions: build for macOS/Windows/Linux
```

---

## Prerequisites

- **Python 3.8+** (3.8 recommended for local dev, 3.11 used in CI)
- **Conda** (recommended) or virtualenv
- **Git**

### One-time environment setup

```bash
# Create conda environment
conda create -n nepalkings python=3.8 -y
conda activate nepalkings

# Install client dependencies
pip install -r nepal_kings/requirements.txt

# Install server dependencies
pip install -r server/requirements.txt

# Install PyInstaller (only needed for building installers)
pip install pyinstaller
```

---

## Running the Game

### Local development (local server)

The easiest way — starts a Flask server on `localhost:5000` in the background, launches the client, and auto-stops the server when you close the game:

```bash
./run_local.sh
```

To open the settings picker first:

```bash
./run_local.sh -s
```

### Remote server (PythonAnywhere)

Connect to the live server at `https://nepalkings.pythonanywhere.com`:

```bash
./run_remote.sh
```

### Switching servers via the UI

Run the client with the `-s` or `--settings` flag to open the settings picker, which lets you choose between **Local (dev)** and **PythonAnywhere**:

```bash
cd nepal_kings
python main.py -s
```

Your choice is saved to `~/.nepalkings/resolution.json` and remembered for subsequent launches.

### CLI flags reference

| Flag | Short | Description |
|------|-------|-------------|
| `--settings` | `-s` | Open the resolution & server picker |
| `--pick-resolution` | `-r` | Same as `--settings` |
| `--server-url URL` | — | Override the server URL for this session |

Examples:

```bash
# Use a custom server
python main.py --server-url http://192.168.1.50:5000

# Force the settings picker
python main.py -s
```

---

## Web Client (Browser)

Nepal Kings can be played directly in the browser — no installation required. The web client is built with [pygbag](https://pygame-web.github.io/) and hosted on GitHub Pages.

**Play now:** [https://mstieffe.github.io/nepalkings/](https://mstieffe.github.io/nepalkings/)

- Works on desktop and mobile browsers
- Connects to the PythonAnywhere server automatically
- Mobile devices get a scaled UI optimised for touch input

### How it's deployed

The web client is built and deployed automatically via GitHub Actions whenever changes are pushed to the `web-client` branch (see `.github/workflows/deploy-web.yml`). The workflow:

1. Builds the pygame app into a WebAssembly bundle using `pygbag 0.9.3`
2. Applies the custom `nepal_kings/web/index.html`
3. Deploys to GitHub Pages

After a push, the live site updates within a few minutes (build + CDN cache).

### Running the web client locally

```bash
pip install pygbag==0.9.3
python -m pygbag nepal_kings
```

Then open `http://localhost:8000` in your browser.

> **Note:** Do not log in as the same player from multiple clients (desktop + web) simultaneously. This can cause state conflicts during battles.

---

## Running the Server Independently

If you want to run the server separately (e.g., to keep it running while restarting the client):

```bash
cd server
python server.py
```

The server runs on `http://localhost:5000` by default. Then launch the client in a separate terminal:

```bash
cd nepal_kings
python main.py --server-url http://localhost:5000
```

**Environment variables** for the server:

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_URL` | `http://localhost:5000` | Server bind address |
| `DB_URL` | `sqlite:///test.db` | Database connection string |
| `DEBUG_ENABLED` | `False` | Enable debug logging |

---

## Deploying / Updating the Server on PythonAnywhere

### First-time PythonAnywhere setup

1. **Create a free account** at [pythonanywhere.com](https://www.pythonanywhere.com) (username: `nepalkings`)

2. **Get your API token**: Go to Account → API Token → Create/copy it

3. **Save the token locally**:
   ```bash
   echo "your-token-here" > ~/.nepalkings_pa_token
   ```

4. **Run initial setup** (creates virtualenv, installs deps, configures the web app):
   ```bash
   ./setup_pythonanywhere.sh
   ```

5. **On PythonAnywhere**, configure the web app:
   - Go to Web tab → Add a new web app → Manual configuration → Python 3.10
   - Set source code directory: `/home/nepalkings/nepalkings`
   - Set virtualenv: `/home/nepalkings/.virtualenvs/nepalkings`
   - Set WSGI file to point to: `/home/nepalkings/nepalkings/pythonanywhere_wsgi.py`

### Deploying updates

After making changes to the `server/` directory, deploy with a single command:

```bash
./deploy_server.sh
```

**What this does:**
1. Zips `server/` (excluding caches)
2. Uploads to PythonAnywhere via API
3. Unzips on the server (overwrites existing files)
4. Reloads the web app so changes take effect

**The whole process takes ~5 seconds.**

> **Note:** Only server code is deployed. Client changes don't need server deployment — they're built into the installer or run locally.

---

## Building Installers for Distribution

### Local build (macOS)

Build a standalone `.app` bundle:

```bash
./build_installer.sh
```

Output: `nepal_kings/dist/NepalKings.app`

The build automatically:
- Bakes in the PythonAnywhere server URL as the default
- Bundles all images and game assets
- Sets the app icon
- Creates a windowed app (no terminal window)
- Restores `main.py` to its original state after building

To distribute:
```bash
cd nepal_kings/dist
zip -r NepalKings-macOS.zip NepalKings.app
# Share the .zip file
```

### Cross-platform builds (GitHub Actions)

The GitHub Actions workflow builds for **macOS, Windows, and Linux** automatically.

**Trigger a build:**

Option A — Push a version tag:
```bash
git tag v0.1.0
git push origin v0.1.0
```

Option B — Manual trigger:
1. Go to your GitHub repo → Actions tab
2. Select "Build Installers"
3. Click "Run workflow"

**Download the artifacts:**
1. Go to the completed workflow run
2. Scroll to "Artifacts"
3. Download `NepalKings-macOS`, `NepalKings-Windows`, or `NepalKings-Linux`

> **Why GitHub Actions?** PyInstaller is platform-specific — a macOS build only produces macOS binaries. GitHub Actions provides free Windows and Linux runners so each platform builds natively.

### Distributing to users

| Platform | File | Instructions for recipients |
|----------|------|---------------------------|
| macOS | `NepalKings.app` (in .zip) | Unzip → drag to `/Applications` → double-click |
| Windows | `NepalKings.exe` | Double-click to play. May need to click "Run anyway" on SmartScreen. |
| Linux | `NepalKings` | `chmod +x NepalKings && ./NepalKings` |

All builds default to the PythonAnywhere server. On first launch, users see the settings picker to choose their resolution.

---

## Changing the App Icon

1. **Replace the source image:**
   ```
   nepal_kings/img/app_icon/app_icon.png
   ```
   Use a square PNG (or it will be padded with transparency). Recommended: 1024×1024 or larger.

2. **Regenerate all icon formats and rebuild:**
   ```bash
   ./generate_icons.sh
   ./build_installer.sh
   ```

   That's it — `generate_icons.sh` handles everything:
   - Resizes the source to 16, 32, 48, 64, 128, 256, 512, 1024 px PNGs
   - Creates `app_icon.ico` for Windows (multi-size)
   - Creates `app_icon.icns` for macOS (via `iconutil`)
   - Requires Pillow (`pip install Pillow`)

> **macOS icon caching:** If Finder still shows the old icon after rebuilding, clear the cache:
> ```bash
> sudo rm -rf /Library/Caches/com.apple.iconservices.store
> sudo find /private/var/folders/ -name com.apple.dock.iconcache -exec rm -rf {} +
> sudo find /private/var/folders/ -name com.apple.iconservices -exec rm -rf {} +
> sudo killall Dock && killall Finder
> ```
> Also right-click the app → **Get Info** to confirm the real icon.

### Manual icon generation (if needed)

<details>
<summary>Step-by-step commands without the script</summary>

**Generate sized PNGs + .ico** (requires Pillow):
```bash
cd nepal_kings/img/app_icon
conda run -n nepalkings python -c "
from PIL import Image

src = Image.open('app_icon.png').convert('RGBA')
w, h = src.size
size = max(w, h)
square = Image.new('RGBA', (size, size), (0, 0, 0, 0))
square.paste(src, ((size - w) // 2, (size - h) // 2))

for s in [16, 32, 48, 64, 128, 256, 512, 1024]:
    square.resize((s, s), Image.LANCZOS).save(f'icon_{s}x{s}.png')

ico_sizes = [16, 32, 48, 64, 128, 256]
ico_images = [square.resize((s, s), Image.LANCZOS) for s in ico_sizes]
ico_images[0].save('app_icon.ico', format='ICO',
    sizes=[(s, s) for s in ico_sizes], append_images=ico_images[1:])
print('Done!')
"
```

**Generate macOS .icns** (macOS only — uses built-in `iconutil`):
```bash
rm -rf app_icon.iconset && mkdir app_icon.iconset
cp icon_16x16.png    app_icon.iconset/icon_16x16.png
cp icon_32x32.png    app_icon.iconset/icon_16x16@2x.png
cp icon_32x32.png    app_icon.iconset/icon_32x32.png
cp icon_64x64.png    app_icon.iconset/icon_32x32@2x.png
cp icon_128x128.png  app_icon.iconset/icon_128x128.png
cp icon_256x256.png  app_icon.iconset/icon_128x128@2x.png
cp icon_256x256.png  app_icon.iconset/icon_256x256.png
cp icon_512x512.png  app_icon.iconset/icon_256x256@2x.png
cp icon_512x512.png  app_icon.iconset/icon_512x512.png
cp icon_1024x1024.png app_icon.iconset/icon_512x512@2x.png
iconutil -c icns app_icon.iconset -o app_icon.icns
```

</details>

### Icon files reference

| File | Used by | Purpose |
|------|---------|---------|
| `app_icon.icns` | PyInstaller (macOS) | .app bundle icon — Dock, Finder, Launchpad |
| `app_icon.ico` | PyInstaller (Windows) | .exe icon — taskbar, Explorer |
| `icon_128x128.png` | Pygame at runtime | Window title bar icon |
| `icon_*.png` | `iconutil` / source | Intermediate sizes for icon generation |

---

## Configuration & Settings

### Client config file

Stored at `~/.nepalkings/resolution.json`:

```json
{
  "width": 1920,
  "height": 1080,
  "server_url": "https://nepalkings.pythonanywhere.com"
}
```

Delete this file to reset all settings and show the picker on next launch.

### Crash logs

If the app crashes, a log is written to `~/.nepalkings/crash.log` with a timestamp and full traceback.

### Server URL priority

The client resolves the server URL in this order (first match wins):
1. `--server-url` CLI flag
2. `SERVER_URL` environment variable
3. Saved value in `~/.nepalkings/resolution.json`
4. Default: `http://localhost:5000`

---

## Troubleshooting

### macOS: "NepalKings.app is damaged and can't be opened"
This happens because the app isn't code-signed. Fix:
```bash
xattr -cr /Applications/NepalKings.app
```

### macOS: App icon doesn't update in Dock after rebuild
macOS caches app icons aggressively. Clear the cache:
```bash
sudo killall Dock
```
Or remove the old `.app` from Applications, empty Trash, then copy the new one.

### Windows: SmartScreen warning ("Der Computer wurde durch Windows geschützt")
The exe is not code-signed, so Windows SmartScreen blocks it by default.
To run:
1. Click **"More info"** (or "Weitere Informationen")
2. Click **"Run anyway"** (or "Trotzdem ausführen")

This only needs to be done once — Windows remembers your choice.

### Windows: "Pfad zu lang" / path too long when extracting
Windows has a 260-character path limit. If you extract the zip to a deeply nested
folder, some file paths may exceed this limit. **Fix:** Extract to a short path, e.g.:
- `C:\Games\NepalKings\` ✅
- `C:\Users\YourName\Downloads\NepalKings-Windows\NepalKings\subfolder\` ❌ (too deep)

### Server: "502 Bad Gateway" on PythonAnywhere
Redeploy and reload:
```bash
./deploy_server.sh
```
If it persists, check the error log on PythonAnywhere: Web tab → Error log.

### Client: Lag when playing remotely
The client uses background polling (2s interval for game state, 1s for battles). If you experience lag:
- Check your internet connection
- The PythonAnywhere free tier has limited CPU; response times may vary

### Resetting the database (server)
```bash
cd server
./RESET_DATABASE.sh
```
**Warning:** This deletes all game data.

---

## AI Opponent Internals

For a complete technical deep dive of the AI opponent architecture, planning system,
chat explain commands, telemetry endpoints, and troubleshooting, see:

- [AI_OPPONENT_README.md](AI_OPPONENT_README.md)
