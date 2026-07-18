# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Geometry regressions for the duel resource panel."""

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / 'nepal_kings'


def test_mobile_duel_resource_values_stay_inside_panel():
    code = r'''
import pygame
pygame.init()
pygame.display.set_mode((854, 480))

from config import settings
from game.components.info_scroll import InfoScroll

data = [{
    'element': 'food',
    'icon_img': settings.RESOURCE_ICON_IMG_PATH_DICT['rice_meat'],
    'red': '34/70',
    'black': '28/35',
}]
panel = InfoScroll(
    pygame.display.get_surface(),
    settings.INFO_SCROLL_X,
    settings.INFO_SCROLL_Y,
    settings.INFO_SCROLL_WIDTH,
    settings.INFO_SCROLL_HEIGHT,
    'Resources',
    data,
    settings.INFO_SCROLL_BG_IMG_PATH,
)
icon, red, black = panel._resource_row_rects(
    panel.y + settings.INFO_SCROLL_Y_TITLE_MARGIN
    + settings.INFO_SCROLL_TITLE_SPACING
)

assert panel.rect.contains(icon), (tuple(panel.rect), tuple(icon))
assert panel.rect.contains(red), (tuple(panel.rect), tuple(red))
assert panel.rect.contains(black), (tuple(panel.rect), tuple(black))
assert red.right <= black.left
assert panel.rect.right < settings.SUB_SCREEN_X
for pill in (red, black):
    font = panel._font_for_pill('00/00', pill.w)
    assert font.size('00/00')[0] <= (
        pill.w - 2 * settings.INFO_SCROLL_TEXT_PADDING)
    assert font.get_height() >= 12
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
