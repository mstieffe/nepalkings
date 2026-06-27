# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the web-bundle PNG optimizer (scripts/assets/optimize_web_pngs.py)."""

import importlib.util
import os
from pathlib import Path

import pytest

PIL = pytest.importorskip('PIL')
from PIL import Image  # noqa: E402

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / 'scripts' / 'assets' / 'optimize_web_pngs.py')
_spec = importlib.util.spec_from_file_location('optimize_web_pngs', _MODULE_PATH)
owp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(owp)


def _write_png(path, size, opaque=True, color=(120, 80, 40)):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 'RGBA'
    alpha = 255 if opaque else 0
    img = Image.new(mode, size, color + (alpha,))
    img.save(path, 'PNG')


class TestTargetSelection:
    def test_figure_frame_uses_small_target(self):
        assert owp._target_for('figures/frames/_military.png') == 384

    def test_icon_uses_smallest_target(self):
        assert owp._target_for('figures/icons/army1.png') == 192

    def test_background_keeps_large_target(self):
        assert owp._target_for('background/menu_background.png') == 1536

    def test_unknown_dir_falls_back_to_default(self):
        assert owp._target_for('mystery/thing.png') == owp.DEFAULT_MAX_DIM


class TestOpacity:
    def test_fully_opaque_detected(self, tmp_path):
        p = tmp_path / 'op.png'
        _write_png(p, (32, 32), opaque=True)
        with Image.open(p) as im:
            assert owp._is_opaque(im) is True

    def test_transparent_detected(self, tmp_path):
        p = tmp_path / 'tr.png'
        _write_png(p, (32, 32), opaque=False)
        with Image.open(p) as im:
            assert owp._is_opaque(im) is False


class TestOptimizeTree:
    def test_downscales_and_prunes_skip_dirs(self, tmp_path):
        img = tmp_path / 'img'
        _write_png(img / 'background' / 'bg.png', (4096, 4096))
        _write_png(img / 'figures' / 'frames' / 'f.png', (1024, 1024), opaque=False)
        _write_png(img / '_legacy' / 'old.png', (512, 512))  # should be removed

        stats = owp.optimize_tree(str(img), quantize=True)

        # Skip dir gone
        assert not (img / '_legacy').exists()
        assert stats['removed_dirs'] == 1
        # Background downscaled to its 1536 target
        with Image.open(img / 'background' / 'bg.png') as im:
            assert max(im.size) == 1536
        # Alpha frame downscaled to 384 and kept as RGBA (not quantized)
        with Image.open(img / 'figures' / 'frames' / 'f.png') as im:
            assert max(im.size) == 384
            assert im.mode == 'RGBA'

    def test_opaque_image_quantized_to_palette(self, tmp_path):
        img = tmp_path / 'img'
        _write_png(img / 'figures' / 'military' / 'army.png', (512, 512), opaque=True)
        owp.optimize_tree(str(img), quantize=True)
        with Image.open(img / 'figures' / 'military' / 'army.png') as im:
            assert im.mode == 'P'  # palette PNG

    def test_keeps_runtime_greyscale_asset_dirs(self, tmp_path):
        img = tmp_path / 'img'
        runtime_assets = [
            img / 'figures' / 'icons_greyscale' / 'castle_black.png',
            img / 'figures' / 'icons_small_greyscale' / 'castle_black.png',
            img / 'figures' / 'frames_greyscale' / 'castle.png',
            img / 'figures' / 'frames_hidden_greyscale' / 'castle.png',
            img / 'battle' / 'icons_greyscale' / 'dagger.png',
            img / 'spells' / 'icons_greyscale' / 'eye.png',
        ]
        for path in runtime_assets:
            _write_png(path, (512, 512), opaque=False)

        stats = owp.optimize_tree(str(img), quantize=True)

        assert stats['removed_dirs'] == 0
        for path in runtime_assets:
            assert path.exists()
            with Image.open(path) as im:
                assert max(im.size) <= 384

    def test_no_quantize_keeps_rgba(self, tmp_path):
        img = tmp_path / 'img'
        _write_png(img / 'figures' / 'military' / 'army.png', (512, 512), opaque=True)
        owp.optimize_tree(str(img), quantize=False)
        with Image.open(img / 'figures' / 'military' / 'army.png') as im:
            assert im.mode in ('RGB', 'RGBA')


class TestSourceGuard:
    def test_refuses_source_tree(self, capsys):
        rc = owp.main(['nepal_kings/img'])
        assert rc == 2
        assert 'Refusing' in capsys.readouterr().err

    def test_allows_staging_path(self, tmp_path):
        staged = tmp_path / 'build' / 'web-staging' / 'nepal_kings' / 'img'
        _write_png(staged / 'cards' / 'c.png', (64, 64))
        rc = owp.main([str(staged)])
        assert rc == 0
