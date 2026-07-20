# PNG Asset Pipeline

This guide covers source PNG validation and maintenance. Browser-size
optimization is separate and always operates on a staged copy.

## Check embedded profiles

Some editors attach invalid or unnecessary ICC profiles that cause libpng
warnings and add decoding overhead. Scan the committed image tree from the
repository root:

```bash
.venv/bin/python scripts/assets/check_png_profiles.py
```

Warnings do not normally change game rules, but they clutter logs and can make
large image sets slower to load.

## Remove problematic profiles

Use the Pillow implementation:

```bash
.venv/bin/python scripts/assets/fix_png_profiles.py
```

Or, with ImageMagick installed:

```bash
scripts/assets/fix_png_profiles.sh
```

After either command:

1. rerun `check_png_profiles.py`;
2. inspect the changed images in the game;
3. run relevant visual tests and the full suite;
4. review `git diff --stat` before committing a large binary rewrite.

Profile removal should not change pixel dimensions or visible colour. Do not
accept a mechanical rewrite without checking the actual output.

## Find large or unused images

```bash
.venv/bin/python scripts/assets/list_oversized_pngs.py
.venv/bin/python scripts/assets/find_unused_pngs.py
```

Treat the unused-image report as evidence, not permission to delete. Dynamic
paths, data-driven names, packaging references, and documentation may not be
visible to a simple source scan.

## Source optimization

`scripts/assets/optimize_pngs.py` can resize or recompress source assets. Use it
only for an intentional source-art change with visual review. Preserve original
masters outside the runtime tree when future editing may require them.

## Browser optimization

The browser build uses `scripts/assets/optimize_web_pngs.py` inside
`scripts/build_web.sh`. It:

- copies the application to `build/web-staging/`;
- excludes legacy and non-runtime art;
- downsizes and optionally quantizes only the staged images;
- leaves `nepal_kings/img/` untouched;
- enforces final bundle budgets before deployment.

Build the browser artifact through [distribution.md](distribution.md). Never
copy optimized staging output back over the source assets.

## Icon generation

The canonical icon assets live under `nepal_kings/img/app_icon/`. Regenerate
platform formats with:

```bash
scripts/assets/generate_icons.sh
```

Confirm macOS, Windows, Linux, and browser outputs after changing the source
icon; operating-system icon caches can make an old icon appear after a correct
build.

## Asset documentation

When adding generated or externally sourced art, record provenance, license,
commercial-use rights, modification rights, and any attribution requirement.
Update [legal/ATTRIBUTION.md](legal/ATTRIBUTION.md) before distribution.
