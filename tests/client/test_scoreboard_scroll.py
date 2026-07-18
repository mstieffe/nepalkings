# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Mobile layout regressions for the duel scoreboard panel."""

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / 'nepal_kings'


def test_mobile_duel_scoreboard_uses_bounded_full_width_rows():
    code = r'''
from types import SimpleNamespace

import pygame
pygame.init()
pygame.display.set_mode((854, 480))

from config import settings
from game.components.scoreboard_scroll import ScoreboardScroll

game = SimpleNamespace(
    mode='duel',
    opponent_name='KathmanduKing',
    date='2026-07-18',
    current_player={'turns_left': 3, 'points': 12},
    opponent_player={'points': 9},
    current_round=2,
    game_limit=45,
    stake=45,
    in_battle_phase=False,
    battle_confirmed=False,
    battle_turn_player_id=None,
    battle_turns_left=2,
)
panel = ScoreboardScroll(
    pygame.display.get_surface(),
    game,
    settings.SCOREBOARD_SCROLL_X,
    settings.SCOREBOARD_SCROLL_Y,
    settings.SCOREBOARD_SCROLL_WIDTH,
    settings.SCOREBOARD_SCROLL_HEIGHT,
    settings.SCOREBOARD_SCROLL_BG_IMG_PATH,
)

your_row, opponent_row, meta_row = panel._mobile_duel_row_rects()
for row in (your_row, opponent_row, meta_row):
    assert panel.rect.contains(row), (tuple(panel.rect), tuple(row))
assert your_row.bottom == opponent_row.top
assert opponent_row.bottom == meta_row.top

for row, label, value, color in (
    (your_row, 'You', 12, settings.COLOR_GREEN),
    (opponent_row, 'KathmanduKing', 9, settings.COLOR_RED),
):
    label_rect, value_rect = panel._draw_mobile_score_row(
        row, label, value, color)
    assert panel.rect.contains(label_rect)
    assert panel.rect.contains(value_rect)
    assert label_rect.right <= value_rect.left

meta = panel._draw_mobile_duel_meta(meta_row, in_battle=False)
assert [text for text, _ in meta] == ['Turns 3', 'R2', '/45']
for (_, rect), (_, next_rect) in zip(meta, meta[1:]):
    assert panel.rect.contains(rect)
    assert rect.right <= next_rect.left
assert panel.rect.contains(meta[-1][1])

game.in_battle_phase = True
battle_meta = panel._draw_mobile_duel_meta(meta_row, in_battle=True)
assert [text for text, _ in battle_meta] == ['Battle 2', 'R2', '/45']
for text, rect in battle_meta:
    assert text
    assert panel.rect.contains(rect)

panel.draw()
print('OK')
'''
    env = os.environ.copy()
    env.update({
        'SDL_VIDEODRIVER': 'dummy',
        'SDL_AUDIODRIVER': 'dummy',
        'NK_SCREEN_WIDTH': '854',
        'NK_SCREEN_HEIGHT': '480',
        'NK_IS_MOBILE': '1',
        'NK_UI_SCALE': '1.6',
        'PYTHONPATH': os.pathsep.join(
            (str(APP_DIR), str(ROOT), env.get('PYTHONPATH', ''))),
    })
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=APP_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
