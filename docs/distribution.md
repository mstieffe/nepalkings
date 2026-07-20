# Distribution Guide

This guide covers player-facing build artifacts. Server promotion is documented
separately in [deployment.md](deployment.md).

## Browser release

The public browser client is hosted at:

<https://mstieffe.github.io/nepalkings/>

GitHub Actions workflow `.github/workflows/deploy-web.yml` builds and publishes
the client when relevant client or web-build files change on `main`. The build:

1. stages a clean copy of `nepal_kings/` under `build/web-staging/`;
2. optimizes staged images without changing source art;
3. builds with pygbag 0.9.3;
4. publishes matching browser audio assets;
5. enforces the archive and external-audio size budgets;
6. uploads and deploys the GitHub Pages artifact.

The production API default is embedded at build time. Verify it inside the
published archive before announcing a release.

### Build locally

Use the same basic environment as CI:

```bash
python3.12 -m venv .pygbag_venv
source .pygbag_venv/bin/activate
python -m pip install pygbag==0.9.3 Pillow

PYTHON=.pygbag_venv/bin/python scripts/build_web.sh
```

Output:

```text
build/web-staging/nepal_kings/build/web/
```

Serve the result locally:

```bash
NK_WEB_SERVE=1 PYTHON=.pygbag_venv/bin/python scripts/build_web.sh
```

The release budget check can be rerun explicitly:

```bash
.pygbag_venv/bin/python scripts/report_web_bundle.py \
  build/web-staging/nepal_kings/build/web \
  --max-archive-mib 52 \
  --max-audio-mib 15
```

## itch.io package

Build and package an HTML5 zip with `index.html` at its root:

```bash
scripts/package_itch.sh
```

Output:

```text
dist/nepal_kings-itch.zip
```

Use `scripts/package_itch.sh --skip-build` only when reusing a web build that
was already produced from the intended commit. Storefront copy is maintained in
[launch/itch_page.md](launch/itch_page.md).

## Desktop packages

Build the current platform locally:

```bash
python -m pip install pyinstaller
./build_installer.sh
```

Outputs are placed under `nepal_kings/dist/`. PyInstaller does not
cross-compile; build each operating system on that operating system or use the
GitHub Actions installer workflow.

### Automated desktop builds

`.github/workflows/build.yml` builds macOS, Windows, and Linux artifacts:

- manually through `workflow_dispatch`; or
- automatically for tags matching `v*`.

A version tag also creates the corresponding GitHub release after all platform
builds succeed.

### Server routing in desktop builds

Desktop packages bake in a default API URL. A build can override it with:

```bash
./build_installer.sh \
  --server-url https://api-nepalkingz.eu.pythonanywhere.com
```

Old packages do not update this value automatically. If the public API hostname
changes, keep the prior hostname working during the client-upgrade window and
publish fresh installers.

## Icons and source assets

The canonical application icon lives under `nepal_kings/img/app_icon/`.
Regenerate platform variants with:

```bash
scripts/assets/generate_icons.sh
```

The web build optimizes a staging copy. Do not downscale, quantize, or overwrite
the committed source art merely to reduce the browser bundle. Asset-specific
workflows are documented in [png_pipeline.md](png_pipeline.md),
[audio_generation.md](audio_generation.md), and [scripts/README.md](../scripts/README.md).

## Release checklist

Before distributing a player build:

1. Start from a clean, committed release candidate.
2. Run the full tests, PostgreSQL compatibility job, dependency audit, and
   security scan.
3. Promote and smoke the same application release on staging and production.
4. Build the browser or desktop artifact from the intended commit.
5. Verify the embedded production API, version metadata, and legal versions.
6. Smoke registration/login, Collection, kingdom map, and Conquer configuration.
7. Record hashes and release evidence in the appropriate operational log.
8. Publish release notes and monitor support, probes, logs, and backups.

The current launch checklist and optional follow-ups are in
[plans/PUBLIC_LAUNCH_PRODUCTION_PLAN.md](plans/PUBLIC_LAUNCH_PRODUCTION_PLAN.md).
