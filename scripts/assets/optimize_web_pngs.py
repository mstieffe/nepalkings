# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
#!/usr/bin/env python3
"""Downscale + recompress PNGs in a directory tree for the web bundle.

This is the *web* optimizer: it is more aggressive than
scripts/assets/optimize_pngs.py because the browser build is the
load-time-sensitive front door and most web players run at <= 1280x720.
It is meant to run against a STAGING COPY of the image tree (see
scripts/build_web.sh), never the committed source art — by default it
refuses to touch nepal_kings/img directly.

What it does, per PNG:
- Downscales (high-quality Lanczos) so the longest side is within a
  per-directory web target, never upscales.
- With --quantize: collapses *opaque* images to a 256-colour palette PNG
  (a large win on the painterly figure/background art). Images with real
  per-pixel alpha (card frames, icons) are left as RGBA and only
  downscaled, so soft edges never fringe.
- Re-saves with max zlib compression, metadata stripped.

Usage:
    python scripts/assets/optimize_web_pngs.py <img_dir>
    python scripts/assets/optimize_web_pngs.py <img_dir> --quantize
    python scripts/assets/optimize_web_pngs.py <img_dir> --allow-source
"""

import argparse
import os
import sys

from PIL import Image, ImageFile

Image.MAX_IMAGE_PIXELS = 200_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Directories never needed by the runtime — drop them from the bundle.
SKIP_DIRS = {'_legacy', 'figures_old', 'old_cards', 'app_icon',
             '_button', 'figures_greyscale', 'icons_greyscale',
             'icons_small_greyscale', 'frames_greyscale',
             'frames_hidden_greyscale'}

# Longest-side pixel budget per path substring (first match wins,
# most-specific first). Tuned for a <=1280x720 canvas with light retina
# headroom; painterly art tolerates the rest.
WEB_MAX_DIM_RULES = [
    ('background/',          1536),   # full-screen, painterly
    ('figures/frames',        384),   # figure cards render ~150px
    ('figures/icons',         192),   # small icons render ~40-60px
    ('figures/build_hierarchy', 256),
    ('figures/',              384),
    ('spells/frames',         384),
    ('spells/icons',          192),
    ('spells/',               384),
    ('battle/frames',         384),
    ('battle/icons',          192),
    ('battle/',               384),
    ('game_button/glow',      384),
    ('game_button/',          320),
    ('cards/',                256),   # cards shown larger in reveal/collection
    ('dialogue_box/',         384),
    ('sub_screen/',           512),   # scroll/parchment panels stretch wide
    ('menu_button/',          384),
    ('button/',               320),
    ('kingdom/',              320),
    ('resource_icons/',       192),
    ('status_icons/',         192),
    ('slot_icons/',           192),
    ('suits/',                192),
    ('glow/',                 384),
    ('icons/',                192),
    ('utils/',                384),
]
DEFAULT_MAX_DIM = 384


def _target_for(rel_path):
    norm = rel_path.replace(os.sep, '/')
    for needle, dim in WEB_MAX_DIM_RULES:
        if needle in norm:
            return dim
    return DEFAULT_MAX_DIM


def _is_opaque(im):
    """True if the image has no per-pixel transparency worth keeping."""
    if im.mode not in ('RGBA', 'LA', 'PA') and 'transparency' not in im.info:
        return True
    try:
        alpha = im.convert('RGBA').getchannel('A')
        return alpha.getextrema()[0] >= 255
    except Exception:
        return False


def optimize_tree(img_dir, quantize=False, colors=256):
    img_dir = os.path.abspath(img_dir)
    before = after = 0
    files = scaled = quantized = removed = 0

    for root, dirs, names in os.walk(img_dir, topdown=True):
        pruned = [d for d in dirs if d in SKIP_DIRS]
        for d in pruned:
            import shutil
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
            removed += 1
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for name in names:
            if not name.lower().endswith('.png'):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, img_dir)
            orig_size = os.path.getsize(path)
            before += orig_size
            try:
                with Image.open(path) as im:
                    im.load()
                    if im.mode in ('P', 'LA'):
                        im = im.convert('RGBA')
                    target = _target_for(rel)
                    w, h = im.size
                    longest = max(w, h)
                    if longest > target:
                        ratio = target / longest
                        im = im.resize((max(1, int(w * ratio)),
                                        max(1, int(h * ratio))),
                                       Image.LANCZOS)
                        scaled += 1
                    # Quantize only fully-opaque art → palette PNG. Alpha art
                    # stays RGBA so soft edges never fringe.
                    if quantize and _is_opaque(im):
                        rgb = im.convert('RGB')
                        pal = rgb.quantize(colors=colors,
                                           method=Image.FASTOCTREE,
                                           dither=Image.FLOYDSTEINBERG)
                        pal.save(path, 'PNG', optimize=True)
                        quantized += 1
                    else:
                        im.save(path, 'PNG', optimize=True)
                after += os.path.getsize(path)
                files += 1
            except Exception as exc:  # pragma: no cover — keep going
                print(f'  ! skipped {rel}: {exc}', file=sys.stderr)
                after += orig_size

    return {'files': files, 'scaled': scaled, 'quantized': quantized,
            'removed_dirs': removed, 'before': before, 'after': after}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('img_dir', help='Image directory to optimize in place')
    parser.add_argument('--allow-source', action='store_true',
                        help='Permit running against the committed nepal_kings/img')
    parser.add_argument('--quantize', action='store_true',
                        help='Collapse opaque images to a palette PNG (big win, '
                             'slight quality loss on gradients)')
    parser.add_argument('--quantize-colors', type=int, default=256,
                        help='Palette size for --quantize (default 256)')
    args = parser.parse_args(argv)

    norm = os.path.abspath(args.img_dir).replace(os.sep, '/')
    parts = norm.split('/')
    # The committed source is "<repo>/nepal_kings/img". A staging copy lives
    # under a build/ directory (e.g. build/web-staging/nepal_kings/img), so
    # only refuse when this looks like the real source tree.
    looks_like_source = (norm.endswith('nepal_kings/img')
                         and 'build' not in parts
                         and 'web-staging' not in parts)
    if looks_like_source and not args.allow_source:
        print('Refusing to optimize the committed source art '
              '(nepal_kings/img). This tool is for a staging copy — see '
              'scripts/build_web.sh. Pass --allow-source to override.',
              file=sys.stderr)
        return 2

    if not os.path.isdir(args.img_dir):
        print(f'Not a directory: {args.img_dir}', file=sys.stderr)
        return 1

    print(f'Optimizing PNGs in {args.img_dir} for web '
          f"(quantize={'on' if args.quantize else 'off'}) ...")
    stats = optimize_tree(args.img_dir, quantize=args.quantize,
                          colors=args.quantize_colors)
    mb = 1_000_000
    saved = stats['before'] - stats['after']
    pct = (100 * saved / stats['before']) if stats['before'] else 0
    print(f"  processed {stats['files']} PNGs, downscaled {stats['scaled']}, "
          f"quantized {stats['quantized']}, removed {stats['removed_dirs']} "
          f"unused dirs")
    print(f"  {stats['before']/mb:.1f} MB -> {stats['after']/mb:.1f} MB "
          f"({saved/mb:.1f} MB / {pct:.0f}% smaller)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
