# Nepal Kings

[![Play in browser](https://img.shields.io/badge/play-browser-2f855a)](https://mstieffe.github.io/nepalkings/)
[![Tests](https://github.com/mstieffe/nepalkings/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/mstieffe/nepalkings/actions/workflows/tests.yml)
[![Security scans](https://github.com/mstieffe/nepalkings/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/mstieffe/nepalkings/actions/workflows/security.yml)
[![License](https://img.shields.io/badge/license-proprietary-lightgrey)](LICENSE)

**Build a kingdom, conquer the land, and duel for the crown.**

<p align="center">
  <img
    src="https://github.com/user-attachments/assets/4cb61d47-3d65-4f5d-96d9-faed1051bafa"
    alt="Nepal Kings gameplay"
    width="100%"
  />
</p>

Nepal Kings is a tactical card game that combines a persistent conquest map,
collectible cards, configurable armies, and head-to-head duels. Start against
AI-held lands, grow a kingdom, prepare its defences, and challenge other
rulers when you are ready.

> Nepal Kings is currently available as a public beta. Player data on the EU
> production service is separate from staging and from the retired development
> server.

## Play

**[Play Nepal Kings in your browser](https://mstieffe.github.io/nepalkings/)**

The browser client runs on desktop and mobile and connects to the production
API automatically. Current source builds and newly generated desktop packages
use the same production service. Older desktop binaries may retain an earlier
baked-in server address and should be rebuilt before distribution.

For gameplay or account help, see [SUPPORT.md](SUPPORT.md). Report security
issues through the private-contact process in [SECURITY.md](SECURITY.md).

## Game modes

### Conquest

Build an attack from your Collection, fight a single-land battle, and turn a
victory into territory. Unclaimed lands are defended by deterministic AI;
player-owned lands use the defence their ruler prepared. Conquest is playable
solo from the first session.

### Duels

Challenge the AI or another ruler to a longer tactical match. Both players use
a shared deck, build figures over several rounds, cast spells, advance, and
fight for points. Quick, Standard, and Epic presets provide convenient score
targets, while custom targets remain available.

The detailed flow and card vocabulary live in the [gameplay guide](docs/gameplay.md).
The in-game Guide is the authoritative reference for the exact rules shipped
with a particular client build.

## Highlights

- Persistent 4,800-land kingdom map with AI and player defences.
- Collection, booster, figure-building, spell, tactic, and progression systems.
- Solo Conquest plus AI and player-versus-player Duels.
- Browser, macOS, Windows, and Linux client targets from one Pygame codebase.
- Account lifecycle, session revocation, export, deletion, player blocking,
  reporting, and audited moderation controls.
- Separate production and staging environments with PostgreSQL, health checks,
  backups, external probes, and a dedicated background worker.

## Technology

| Area | Technology |
|---|---|
| Client | Python, Pygame, pygbag/WebAssembly |
| API | Flask, SQLAlchemy |
| Production data | PostgreSQL |
| Local data | SQLite |
| Hosting | GitHub Pages and PythonAnywhere EU |
| Automation | GitHub Actions, pytest, pip-audit, gitleaks |

See [docs/architecture.md](docs/architecture.md) for component boundaries and
runtime data flow.

## Local development

Nepal Kings uses Python 3.11 for the client, server, and test suite.

```bash
git clone https://github.com/mstieffe/nepalkings.git
cd nepalkings

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r server/requirements.txt

./run_local.sh
```

`run_local.sh` starts the local Flask API on `http://localhost:5000`, launches
the game against it, and stops the server when the client exits. On Windows,
or when running the two processes independently, follow the
[development guide](docs/development.md).

Run the test suite with:

```bash
.venv/bin/python -m pytest -q
```

Authorized contributors should also read [CONTRIBUTING.md](CONTRIBUTING.md).

## Repository layout

```text
nepal_kings/           Pygame client, UI, assets, and web shell
server/                Flask API, domain services, models, and migrations
tests/                 Client, server, database, and operational tests
scripts/               Build, verification, backup, load, and asset tools
deploy/pythonanywhere/ Production hosting templates and runbook
docs/                  Player, developer, architecture, and operations docs
.github/workflows/     Tests, security scans, web deploy, installers, probes
```

## Documentation

[docs/README.md](docs/README.md) is the documentation home and source-of-truth
map. The most useful entry points are:

| Audience | Start here |
|---|---|
| Players | [Gameplay](docs/gameplay.md) · [Support](SUPPORT.md) · [Legal](docs/legal/README.md) |
| Developers | [Development](docs/development.md) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md) · [Scripts](scripts/README.md) |
| Release maintainers | [Distribution](docs/distribution.md) · [Deployment](docs/deployment.md) |
| Operators | [Environment matrix](docs/environments.md) · [Beta operations](docs/operations/BETA_OPERATIONS.md) |
| Project planning | [Plans index](docs/plans/README.md) · [Changelog](CHANGELOG.md) |

## Branches and releases

- `main` is the public release branch and the source for GitHub Pages.
- `develop` is the integration branch for the next release.
- Version tags (`v*`) trigger cross-platform desktop builds.
- Server deployments use immutable commit directories and are promoted through
  staging before production.

Operational changes must update their runbook and deployment evidence in the
same change. Feature plans are design records; once code ships, current guides,
tests, and runtime behavior take precedence.

## License

Copyright © 2026 Marc Stieffenhofer. All rights reserved.

This repository is proprietary software. Use, modification, redistribution,
and contribution are permitted only with the copyright holder's written
authorization. See [LICENSE](LICENSE).
