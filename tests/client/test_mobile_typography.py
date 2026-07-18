# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression coverage for the mobile-only typography scale and safety floor."""

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "nepal_kings"


def _font_snapshot(*, mobile):
    env = os.environ.copy()
    env.update({
        "SDL_VIDEODRIVER": "dummy",
        "SDL_AUDIODRIVER": "dummy",
        "NK_SCREEN_WIDTH": "854",
        "NK_SCREEN_HEIGHT": "480",
        "NK_IS_MOBILE": "1" if mobile else "0",
        "NK_UI_SCALE": "1.6" if mobile else "1.0",
    })
    script = """
import json
import pygame
pygame.init()
from config import settings

tiny = settings.get_font(7)
floor = settings.get_font(settings.FS_FLOOR)
decorative = settings.get_font(7, allow_small=True)
named_font_sizes = [
    value
    for name, value in vars(settings).items()
    if isinstance(value, int) and (
        name.startswith("FS_") or "FONT_SIZE" in name
    )
]
print(json.dumps({
    "body": settings.FS_BODY,
    "small": settings.FS_SMALL,
    "tiny": settings.FS_TINY,
    "floor": settings.FS_FLOOR,
    "collection_badge": settings.COLLECTION_BADGE_FONT_SIZE,
    "battle_move_big": settings.BATTLE_MOVE_ICON_FONT_BIG_SIZE,
    "spell_big": settings.SPELL_ICON_FONT_BIG_SIZE,
    "scoreboard_text": settings.SCOREBOARD_SCROLL_FONT_SIZE,
    "scoreboard_subtitle": settings.SCOREBOARD_SUBTITLE_FONT_SIZE,
    "tiny_height": tiny.get_height(),
    "floor_height": floor.get_height(),
    "decorative_height": decorative.get_height(),
    "minimum_named_font": min(named_font_sizes),
}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=APP_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_mobile_semantic_fonts_keep_badges_counts_and_detail_readable():
    snapshot = _font_snapshot(mobile=True)

    assert snapshot["body"] >= 26
    assert snapshot["small"] >= 23
    assert snapshot["tiny"] >= 22
    assert snapshot["floor"] >= 18
    assert snapshot["collection_badge"] >= snapshot["small"]
    assert snapshot["battle_move_big"] >= snapshot["body"]
    assert snapshot["spell_big"] >= snapshot["body"]
    assert snapshot["scoreboard_text"] >= snapshot["tiny"]
    assert snapshot["scoreboard_subtitle"] >= snapshot["floor"]
    assert snapshot["minimum_named_font"] >= snapshot["floor"]


def test_mobile_font_cache_clamps_legacy_sizes_but_allows_decorative_opt_out():
    snapshot = _font_snapshot(mobile=True)

    assert snapshot["tiny_height"] == snapshot["floor_height"]
    assert snapshot["decorative_height"] < snapshot["floor_height"]


def test_desktop_font_requests_are_not_clamped_to_the_mobile_floor():
    snapshot = _font_snapshot(mobile=False)

    assert snapshot["tiny_height"] == snapshot["decorative_height"]
    assert snapshot["tiny_height"] < snapshot["floor_height"]
