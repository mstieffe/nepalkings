# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Geometry regressions for the shared figure/spell/tactics picker footer."""

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pygame


APP_DIR = Path(__file__).resolve().parents[2] / 'nepal_kings'


def _assert_footer_geometry():
    from config import settings
    from game.components.picker_ui import (
        footer_button_geometry,
        footer_rect,
        footer_rail_rects,
    )

    subscreen = SimpleNamespace(
        x=settings.SUB_SCREEN_X,
        y=settings.SUB_SCREEN_Y,
        scroll_x=settings.BUILD_FIGURE_INFO_BOX_SCROLL_X,
        scroll_w=settings.BUILD_FIGURE_INFO_BOX_SCROLL_WIDTH,
        sub_box_x=settings.BUILD_FIGURE_INFO_BOX_X,
        sub_box_background=pygame.Surface((
            settings.BUILD_FIGURE_INFO_BOX_WIDTH,
            settings.BUILD_FIGURE_INFO_BOX_HEIGHT,
        )),
    )
    footer = footer_rect(subscreen)
    action_rail, status_rail = footer_rail_rects(subscreen)
    frame = settings.SUB_SCREEN_BG_FRAME_W
    parchment = pygame.Rect(
        subscreen.x + frame,
        subscreen.y + frame,
        settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH - 2 * frame,
        settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT - 2 * frame,
    )
    assert parchment.contains(footer), (tuple(parchment), tuple(footer))
    assert footer.bottom < parchment.bottom
    assert footer.contains(action_rail)
    assert footer.contains(status_rail)
    assert action_rail.x == subscreen.scroll_x
    assert action_rail.w == subscreen.scroll_w
    assert status_rail.x == subscreen.sub_box_x
    assert status_rail.w == subscreen.sub_box_background.get_width()
    assert action_rail.right < status_rail.left

    for label, align in (
            ('Add to Attack', 'center'),
            ('Set Prelude', 'center'),
            ('Ready for Battle', 'right')):
        button = pygame.Rect(
            *footer_button_geometry(subscreen, label, align=align))
        assert footer.contains(button), (label, tuple(footer), tuple(button))
        owning_rail = status_rail if align == 'right' else action_rail
        assert owning_rail.contains(button), (
            label, tuple(owning_rail), tuple(button))
        if align == 'center':
            assert button.centerx == owning_rail.centerx

    content_bottoms = (
        settings.BUILD_FIGURE_INFO_BOX_Y
        + settings.BUILD_FIGURE_INFO_BOX_HEIGHT,
        settings.CAST_SPELL_INFO_BOX_Y
        + settings.CAST_SPELL_INFO_BOX_HEIGHT,
        settings.BATTLE_SHOP_INFO_BOX_Y
        + settings.BATTLE_SHOP_INFO_BOX_HEIGHT,
    )
    assert max(content_bottoms) + 2 <= footer.top, (
        content_bottoms, tuple(footer))


def test_picker_footer_stays_inside_desktop_subwindow():
    _assert_footer_geometry()


def test_picker_footer_stays_inside_mobile_subwindow():
    code = r'''
import pygame
pygame.init()
pygame.display.set_mode((854, 480))
from tests.client.test_picker_ui import _assert_footer_geometry
_assert_footer_geometry()
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
            (str(APP_DIR), str(APP_DIR.parent),
             env.get('PYTHONPATH', ''))),
    })
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=APP_DIR, env=env, capture_output=True, text=True,
        timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_picker_footer_can_collapse_unused_rails():
    from config import settings
    from game.components.picker_ui import draw_footer, footer_rail_rects

    subscreen = SimpleNamespace(
        x=settings.SUB_SCREEN_X,
        y=settings.SUB_SCREEN_Y,
        scroll_x=settings.BUILD_FIGURE_INFO_BOX_SCROLL_X,
        scroll_w=settings.BUILD_FIGURE_INFO_BOX_SCROLL_WIDTH,
        sub_box_x=settings.BUILD_FIGURE_INFO_BOX_X,
        sub_box_background=pygame.Surface((
            settings.BUILD_FIGURE_INFO_BOX_WIDTH,
            settings.BUILD_FIGURE_INFO_BOX_HEIGHT,
        )),
    )
    action_rail, status_rail = footer_rail_rects(subscreen)
    canvas = pygame.Surface(
        (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT), pygame.SRCALPHA)

    draw_footer(
        canvas, subscreen, '',
        show_action=True, show_status=False)

    assert canvas.get_at(action_rail.center).a > 0
    assert canvas.get_at(status_rail.center).a == 0


def test_build_resources_share_footer_without_covering_action():
    from config import settings
    from game.components.picker_ui import (
        footer_button_geometry,
        footer_rect,
        footer_rail_rects,
    )
    from game.screens.build_figure_screen import BuildFigureScreen

    screen = BuildFigureScreen.__new__(BuildFigureScreen)
    screen.x = settings.SUB_SCREEN_X
    screen.y = settings.SUB_SCREEN_Y
    screen._layout_offset_x = 0
    screen._layout_offset_y = 0
    screen._sx = lambda value: value
    screen._sy = lambda value: value
    button_rect = pygame.Rect(*footer_button_geometry(
        screen, 'Add to Attack', align='center'))
    screen.confirm_button = SimpleNamespace(rect=button_rect)

    resource_rect = BuildFigureScreen._resource_strip_rect(screen)
    footer = footer_rect(screen)
    action_rail, status_rail = footer_rail_rects(screen)

    assert footer.contains(resource_rect)
    assert status_rail.contains(resource_rect)
    assert action_rail.contains(button_rect)
    assert not resource_rect.colliderect(button_rect)


def test_battle_shop_has_no_expanded_variant_card_strip():
    from game.screens.battle_shop_screen import BattleShopScreen

    assert not hasattr(BattleShopScreen, '_draw_variant_card_choices')


def test_build_dialogue_click_does_not_reach_figure_buttons():
    from game.screens.build_figure_screen import BuildFigureScreen

    handled = []
    screen = BuildFigureScreen.__new__(BuildFigureScreen)
    screen.scroll_text_list_shifter = SimpleNamespace(
        get_current_selected=lambda: object())
    screen.dialogue_box = SimpleNamespace(update=lambda _events: 'cancel')
    screen._visible_family_buttons = lambda: [
        SimpleNamespace(
            handle_events=lambda _events: handled.append('figure'))]

    BuildFigureScreen.handle_events(screen, [
        pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1, pos=(400, 240)),
    ])

    assert handled == []
    assert screen.dialogue_box is None


def test_pressed_figure_icon_draws_its_caption_only_once():
    from game.components.figures.figure_icon import FigureIcon

    class BlitSpy:
        def __init__(self):
            self.sources = []

        def blit(self, source, _position):
            self.sources.append(source)

    icon = FigureIcon.__new__(FigureIcon)
    icon.window = BlitSpy()
    icon.clicked = False
    icon.hovered = True
    icon.is_active = True
    icon.text_surface = pygame.Surface((17, 7))
    icon.text_rect = pygame.Rect(0, 0, 17, 7)

    for name in (
            'icon_img', 'icon_gray_img', 'icon_img_big',
            'icon_gray_img_big', 'frame_img', 'frame_closed_img',
            'frame_img_big', 'frame_closed_img_big', 'glow_yellow',
            'glow_black', 'glow_yellow_big', 'glow_white_big',
            'glow_yellow_dark', 'glow_white', 'glow_yellow_dark_big'):
        setattr(icon, name, pygame.Surface((5, 5)))
    for name in (
            'rect_icon', 'rect_icon_big', 'rect_frame', 'rect_frame_big',
            'rect_glow', 'rect_glow_big'):
        setattr(icon, name, pygame.Rect(0, 0, 5, 5))

    caption_calls = []
    icon.draw_text_with_background = (
        lambda **kwargs: caption_calls.append(kwargs))

    with patch(
            'game.components.figures.figure_icon._get_pressed',
            return_value=(1, 0, 0)):
        FigureIcon.draw(icon)

    assert caption_calls == [{'y_offset': 0}]
    assert icon.text_surface not in icon.window.sources


def test_duel_build_footer_omits_redundant_hand_status():
    from game.screens.build_figure_screen import BuildFigureScreen

    class FooterDrawn(Exception):
        pass

    calls = []

    def capture_footer(*args, **kwargs):
        calls.append((args, kwargs))
        raise FooterDrawn

    screen = BuildFigureScreen.__new__(BuildFigureScreen)
    screen.window = object()
    screen.mode = 'duel'
    screen.scroll_text_list_shifter = SimpleNamespace(
        get_current_selected=lambda: object())

    with (
            patch(
                'game.screens.build_figure_screen.SubScreen.draw',
                return_value=None),
            patch(
                'game.screens.build_figure_screen.draw_footer',
                side_effect=capture_footer),
    ):
        try:
            BuildFigureScreen.draw(screen)
        except FooterDrawn:
            pass

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[2] == ''
    assert kwargs['show_action'] is True
    assert kwargs['show_status'] is False


def test_target_action_labels_use_render_safe_ascii():
    from game.screens.cast_spell_screen import CastSpellScreen
    from game.screens.prelude_spell_screen import PreludeSpellScreen

    target_spell = SimpleNamespace(requires_target=True)
    assert CastSpellScreen._confirm_action_label(target_spell) == 'Choose Target'

    prelude = PreludeSpellScreen.__new__(PreludeSpellScreen)
    prelude._is_counter_picker = False
    assert prelude._confirm_action_label(target_spell) == 'Choose Target'


def test_missing_spell_details_do_not_repeat_visible_card_state():
    from game.screens.cast_spell_screen import CastSpellScreen
    from game.screens.prelude_spell_screen import PreludeSpellScreen

    family = SimpleNamespace(
        name='Test Spell', type='greed', description='Test description')
    spell = SimpleNamespace(
        name='Test Spell',
        family=family,
        cards=[],
        counterable=True,
        possible_during_ceasefire=False,
        requires_target=False,
    )

    duel = CastSpellScreen.__new__(CastSpellScreen)
    duel.format_spell_type = lambda _spell_type: 'Greed Spell'
    duel_item = duel._spell_detail_item(
        spell, content=None, cards=[], missing_cards=[])

    prelude = PreludeSpellScreen.__new__(PreludeSpellScreen)
    prelude._is_counter_picker = False
    prelude.description_overrides = {}
    prelude_item = prelude._detail_item(
        spell, content=None, cards=[], missing_cards=[])

    assert 'availability_reason' not in duel_item
    assert 'availability_reason' not in prelude_item
