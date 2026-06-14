# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the persistent KingdomConfigScreen."""

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame


APP_DIR = Path(__file__).resolve().parents[2] / 'nepal_kings'


def _run_mobile_geometry_check(code):
    env = os.environ.copy()
    env.update({
        'SDL_VIDEODRIVER': 'dummy',
        'SDL_AUDIODRIVER': 'dummy',
        'NK_SCREEN_WIDTH': '854',
        'NK_SCREEN_HEIGHT': '480',
        'NK_IS_MOBILE': '1',
        'NK_UI_SCALE': '1.6',
    })
    subprocess.run(
        [sys.executable, '-c', code],
        cwd=APP_DIR,
        env=env,
        check=True,
    )


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _screen_base():
    from config import settings
    from game.screens.kingdom_config_screen import KingdomConfigScreen

    screen = KingdomConfigScreen.__new__(KingdomConfigScreen)
    screen.state = SimpleNamespace(
        screen='kingdom_config',
        kingdom_config_land_id=12,
        kingdom_config_id=None,
        message_lines=[],
        user_dict={
            'gold': 0,
            'booster_packs': 0,
            'booster_packs_side': 0,
            'maps': 0,
            'onboarding': {'menu_hints_seen': [], 'completed_steps': []},
        },
        set_msg=MagicMock(),
    )
    screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen.dialogue_box = None
    screen.control_buttons = []
    screen.game_buttons = []
    screen.menu_buttons = []
    screen._title_font = settings.get_font(settings.FS_TITLE, bold=True)
    screen._heading_font = settings.get_font(settings.FS_HEADING, bold=True)
    screen._body_font = settings.get_font(settings.FS_BODY)
    screen._button_font = settings.get_font(settings.FS_BUTTON, bold=True)
    screen._small_font = settings.get_font(settings.FS_SMALL)
    screen._tiny_font = settings.get_font(settings.FS_TINY)
    screen._data = None
    screen._kingdom = None
    screen._catalog = {}
    screen._gold = 0
    screen._selected_hours = 6
    screen._quote = None
    screen._message = ''
    screen._loading = False
    screen._buttons = []
    screen._box_rect = pygame.Rect(0, 0, settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)
    screen._btn_close_rect = None
    screen._cosmetic_scroll = {'badge': 0, 'border': 0, 'surface': 0,
                               'color': 0, 'sigil': 0}
    screen._cosmetic_sort = {key: 'default' for key in screen._cosmetic_scroll}
    screen._cosmetic_filter = {key: 'all' for key in screen._cosmetic_scroll}
    screen._cosmetic_scroll_areas = {}
    screen._cosmetics_panel_scroll = 0
    screen._cosmetics_scroll_area = None
    screen._cosmetics_content_h = 0
    screen._content_scroll = 0
    screen._content_scroll_area = None
    screen._content_content_h = 0
    screen._button_clip_rect = None
    screen._rename_dialog = None
    screen._rename_input_rect = None
    screen._rename_confirm_rect = None
    screen._rename_cancel_rect = None
    screen._pending_purchase = None
    screen._icons = {}
    screen._shield_icon = None
    screen._edit_icon = None
    screen._edit_icon_size = 18
    screen._rename_icon_rect = None
    from game.components.floating_text import FloatingTextLayer
    screen._floating_text = FloatingTextLayer()
    screen._last_render_ms = 0
    screen._last_seen_level = None
    screen._collect_btn_rect = None
    screen._menu_coach_buttons = []
    screen._menu_coach_step = None
    screen._menu_coach_pressed_button_action = None
    screen._menu_coach_font = settings.get_font(settings.FS_SMALL)
    screen._menu_coach_title_font = settings.get_font(settings.FS_BODY, bold=True)
    screen._onboarding_guide_open = False
    screen._logout_dialogue = None
    screen._welcome_present_dialogue = None
    screen._kingdom_config_header_rect = None
    screen._kingdom_config_cosmetics_rect = None
    screen._kingdom_config_shield_rect = None
    screen._kingdom_config_vault_rect = None
    screen._kingdom_config_loot_rect = None
    screen._kingdom_config_skills_rect = None
    screen._kingdom_config_skill_button_rect = None
    screen._draw_menu_chrome = MagicMock()
    screen._draw_menu_overlay = MagicMock()
    screen._handle_icon_events = MagicMock(return_value=False)
    screen._update_icon_buttons = MagicMock()
    return KingdomConfigScreen, screen


def _kingdom_payload():
    return {
        'id': 4,
        'name': 'North Pass',
        'style': {
            'badge_key': 'badge_plain',
            'border_key': 'border_simple_gold',
            'surface_key': 'surface_plain',
            'color_key': 'color_royal_gold',
            'sigil_key': 'sigil_none',
        },
        'land_ids': [12, 13],
        'lands_count': 2,
        'unlocked_cosmetics': [
            'badge_plain', 'border_simple_gold', 'surface_plain',
            'color_royal_gold', 'sigil_none',
        ],
        'shield_remaining': 0,
        'skill_points_total': 2,
        'skill_points_spent': 0,
        'skill_points_available': 2,
        'raw_gold_rate': 20.0,
        'effective_gold_rate': 22.0,
        'gold_bonus_rate': 2.0,
        'skills': {
            'gold_production': {
                'name': 'Gold Production',
                'description': 'More gold.',
                'level': 0,
                'max_level': 5,
                'next_cost': 1,
            },
        },
    }


class TestKingdomConfigLoading:

    def test_fetch_config_selects_land_kingdom_and_quotes_shield(self, monkeypatch):
        import game.screens.kingdom_config_screen as module
        KingdomConfigScreen, screen = _screen_base()
        calls = []

        def fake_get(url, timeout=0):
            calls.append(('get', url))
            return _Response({
                'success': True,
                'catalog': {},
                'gold': 321,
                'shield_options_hours': [6, 12, 24],
                'selected_kingdom_id': 4,
                'kingdoms': [_kingdom_payload()],
            })

        def fake_post(url, json=None, timeout=0):
            calls.append(('post', url, json))
            return _Response({'success': True, 'quote': {'price_gold': 108}})

        monkeypatch.setattr(module.requests, 'get', fake_get)
        monkeypatch.setattr(module.requests, 'post', fake_post)

        KingdomConfigScreen._fetch_config(screen)

        assert screen._kingdom['id'] == 4
        assert screen._gold == 321
        assert screen.state.user_dict['gold'] == 321
        assert screen._quote['price_gold'] == 108
        assert calls[0][1].endswith('/kingdom/config?land_id=12')
        assert calls[1][1].endswith('/kingdom/config/4/shield/quote')

    def test_post_action_updates_kingdom_and_gold(self, monkeypatch):
        import game.screens.kingdom_config_screen as module
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()

        updated = _kingdom_payload()
        updated['skill_points_available'] = 1

        monkeypatch.setattr(
            module.requests,
            'post',
            lambda url, json=None, timeout=0: _Response({
                'success': True,
                'kingdom': updated,
                'gold': 77,
            }),
        )

        data = KingdomConfigScreen._post_action(screen, 'skills/upgrade', {'skill_key': 'gold_production'})

        assert data['success'] is True
        assert screen._kingdom['skill_points_available'] == 1
        assert screen._gold == 77
        assert screen.state.user_dict['gold'] == 77


class TestKingdomConfigInteractions:

    def test_current_coach_step_follows_post_conquer_config_order(self):
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen.state.user_dict['onboarding'] = {
            'menu_hints_seen': [],
            'completed_steps': ['finish_first_conquer_battle'],
        }
        screen._kingdom_config_header_rect = pygame.Rect(20, 20, 360, 72)
        screen._kingdom_config_vault_rect = pygame.Rect(420, 120, 280, 120)
        screen._kingdom_config_skills_rect = pygame.Rect(420, 380, 280, 240)
        screen._kingdom_config_loot_rect = pygame.Rect(420, 250, 280, 110)
        screen._kingdom_config_cosmetics_rect = pygame.Rect(20, 120, 320, 220)
        screen._kingdom_config_shield_rect = pygame.Rect(20, 350, 320, 150)
        screen._collect_btn_rect = pygame.Rect(610, 200, 80, 28)
        screen._kingdom_config_skill_button_rect = pygame.Rect(580, 420, 104, 30)
        screen._loot_gained_rect = pygame.Rect(440, 276, 120, 60)

        step = KingdomConfigScreen._current_kingdom_config_coach_step(screen)
        assert step['id'] == 'kingdom_config_essentials'
        # Essentials points at the production/skills controls (collect first).
        assert step['rect'] == screen._collect_btn_rect

        screen.state.user_dict['onboarding']['menu_hints_seen'] = ['kingdom_config_essentials']
        step = KingdomConfigScreen._current_kingdom_config_coach_step(screen)
        assert step['id'] == 'kingdom_config_shields_style'

    def test_coach_visibility_helper_scrolls_shields_panel_into_view(self):
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen.state.user_dict['onboarding'] = {
            'menu_hints_seen': ['kingdom_config_essentials'],
            'completed_steps': ['finish_first_conquer_battle'],
        }
        layout = {
            'content_viewport': pygame.Rect(30, 140, 700, 240),
            'content_h': 900,
            'gap': 16,
            'vault_h': 140,
            'loot_h': 120,
            'skills_h': 360,
            'cosmetics_h': 260,
            'shield_h': 150,
        }
        screen._content_scroll = 0

        # Shields/cosmetics sit below the fold, so the helper scrolls down.
        KingdomConfigScreen._ensure_kingdom_config_coach_visible(screen, layout)

        assert screen._content_scroll > 0

    def test_coach_visibility_helper_does_not_oscillate_for_oversized_panel(self):
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        layout = {
            'content_viewport': pygame.Rect(30, 140, 700, 240),
            'content_h': 900,
            'gap': 16,
            'vault_h': 140,
            'loot_h': 120,
            'skills_h': 360,
            'cosmetics_h': 260,
            'shield_h': 360,  # taller than the viewport
        }
        screen._content_scroll = 0

        KingdomConfigScreen._ensure_kingdom_config_coach_visible(
            screen, layout, step_id='kingdom_config_shields_style')
        first_scroll = screen._content_scroll
        KingdomConfigScreen._ensure_kingdom_config_coach_visible(
            screen, layout, step_id='kingdom_config_shields_style')

        # Oversized panel pins to its top and stays put (no oscillation).
        assert first_scroll == 276
        assert screen._content_scroll == first_scroll

    def test_coach_step_clips_scrolled_content_rects_to_visible_viewport(self):
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen.state.user_dict['onboarding'] = {
            'menu_hints_seen': [],
            'completed_steps': ['finish_first_conquer_battle'],
        }
        screen._content_scroll_area = pygame.Rect(20, 100, 360, 120)
        screen._collect_btn_rect = pygame.Rect(60, 82, 90, 42)
        screen._kingdom_config_vault_rect = pygame.Rect(40, 82, 300, 180)

        step = KingdomConfigScreen._current_kingdom_config_coach_step(screen)

        assert step['id'] == 'kingdom_config_essentials'
        assert step['rect'] == pygame.Rect(60, 100, 90, 24)
        assert step['rects'][1] == pygame.Rect(40, 100, 300, 120)

    def test_handle_events_checks_coach_before_registered_buttons(self):
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._buttons = [('upgrade_skill', 'gold_production', pygame.Rect(90, 90, 120, 30))]
        screen._current_kingdom_config_coach_step = lambda: {
            'id': 'kingdom_config_header',
            'rect': pygame.Rect(10, 10, 200, 60),
            'title': 'Header',
            'body': 'Body',
        }
        screen._handle_menu_coach_events = MagicMock(return_value=True)
        screen._upgrade_skill = MagicMock()

        event = SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1, pos=(100, 100))

        KingdomConfigScreen.handle_events(screen, [event])

        screen._handle_menu_coach_events.assert_called_once()
        screen._upgrade_skill.assert_not_called()

    def test_init_uses_menu_chrome_without_legacy_controls(self, monkeypatch):
        from game.screens.kingdom_config_screen import KingdomConfigScreen

        state = SimpleNamespace(
            screen='kingdom_config',
            kingdom_config_land_id=12,
            kingdom_config_id=None,
            message_lines=[],
            user_dict={'gold': 0, 'booster_packs': 0, 'booster_packs_side': 0, 'maps': 0},
            set_msg=MagicMock(),
        )
        chrome_calls = []
        monkeypatch.setattr(KingdomConfigScreen, '_init_menu_chrome',
                            lambda self: chrome_calls.append(True))

        screen = KingdomConfigScreen(state)

        assert chrome_calls == [True]
        assert screen.control_buttons == []
        assert screen.logout_button not in screen.control_buttons
        assert screen.home_button not in screen.control_buttons

    def test_clicking_registered_button_dispatches_action(self, monkeypatch):
        KingdomConfigScreen, screen = _screen_base()
        screen._buttons = [('buy_shield', None, pygame.Rect(90, 90, 80, 30))]
        bought = []
        monkeypatch.setattr(KingdomConfigScreen, '_buy_shield', lambda self: bought.append(True))

        event = SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1, pos=(100, 100))
        KingdomConfigScreen.handle_events(screen, [event])

        assert bought == [True]

    def test_escape_returns_to_kingdom_map(self):
        KingdomConfigScreen, screen = _screen_base()

        event = SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_ESCAPE)
        KingdomConfigScreen.handle_events(screen, [event])

        assert screen.state.screen == 'kingdom'

    def test_switch_kingdom_cycles_and_refreshes_quote(self, monkeypatch):
        KingdomConfigScreen, screen = _screen_base()
        first = _kingdom_payload()
        second = _kingdom_payload()
        second['id'] = 9
        second['name'] = 'South Reach'
        screen._data = {'kingdoms': [first, second]}
        screen._kingdom = first
        quote_calls = []
        monkeypatch.setattr(KingdomConfigScreen, '_fetch_quote',
                            lambda self, silent=False: quote_calls.append(silent))

        KingdomConfigScreen._switch_kingdom(screen, 1)

        assert screen._kingdom['id'] == 9
        assert screen.state.kingdom_config_id == 9
        assert quote_calls == [True]

    def test_collect_kingdom_gold_updates_local_and_shared_gold(self, monkeypatch):
        import game.screens.kingdom_config_screen as module
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._kingdom['pending_gold'] = 12.0
        screen._kingdom['vault_cap'] = 50
        screen._gold = 100
        screen.state.user_dict['gold'] = 100
        screen._collect_btn_rect = pygame.Rect(10, 10, 80, 30)
        screen._suppress_next_gold_floater = MagicMock()
        quote_calls = []

        monkeypatch.setattr(
            module.requests,
            'post',
            lambda url, json=None, timeout=0: _Response({
                'success': True,
                'collected': 12,
                'collected_gold': 12,
                'collected_main_boosters': 1,
                'collected_side_boosters': 1,
                'pending_gold': 0.5,
                'vault_cap': 50,
                'gold': 112,
                'booster_packs': 3,
                'booster_packs_side': 2,
                'production': {
                    'main_booster': {'pending': 0},
                    'side_booster': {'pending': 0},
                },
            }),
        )
        monkeypatch.setattr(KingdomConfigScreen, '_fetch_quote',
                            lambda self, silent=False: quote_calls.append(silent))

        KingdomConfigScreen._collect_kingdom_gold(screen)

        assert screen._gold == 112
        assert screen.state.user_dict['gold'] == 112
        assert screen.state.user_dict['booster_packs'] == 3
        assert screen.state.user_dict['booster_packs_side'] == 2
        assert screen._kingdom['pending_gold'] == 0.5
        assert screen._kingdom['production']['main_booster']['pending'] == 0
        screen._suppress_next_gold_floater.assert_called_once_with()
        assert quote_calls == [True]

    def test_cosmetic_section_scrolls_all_catalog_items(self):
        from config import settings
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._gold = 5000
        screen._catalog = {
            f'badge_{idx}': {
                'type': 'badge',
                'name': f'Badge {idx}',
                'price_gold': idx * 100,
            }
            for idx in range(6)
        }
        screen._catalog['badge_plain'] = {
            'type': 'badge',
            'name': 'Plain',
            'price_gold': 0,
        }

        rect = pygame.Rect(20, 20, settings.KINGDOM_CONFIG_LEFT_W, settings.KINGDOM_CONFIG_CARD_H)
        KingdomConfigScreen._draw_cosmetic_section(screen, rect, 'badge', 'Kingdom Badge')

        actions = [action for action, _value, _rect in screen._buttons]
        assert 'cosmetic_page_next' not in actions
        assert 'badge' in screen._cosmetic_scroll_areas

        KingdomConfigScreen._scroll_cosmetic_section(screen, 'badge', -1)
        assert screen._cosmetic_scroll['badge'] > 0

    def test_main_config_scrolls_expanded_panels_and_inner_cosmetic_lists(self):
        from config import settings
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._gold = 5000
        screen._catalog = {}
        for cosmetic_type in ('badge', 'border', 'surface', 'color', 'sigil'):
            for idx in range(8):
                key = f'{cosmetic_type}_{idx}'
                screen._catalog[key] = {
                    'type': cosmetic_type,
                    'name': f'{cosmetic_type.title()} {idx}',
                    'price_gold': idx * 100,
                }
        screen._catalog.update({
            'badge_plain': {'type': 'badge', 'name': 'Plain', 'price_gold': 0},
            'border_simple_gold': {'type': 'border', 'name': 'Gold', 'price_gold': 0},
            'surface_plain': {'type': 'surface', 'name': 'Plain', 'price_gold': 0},
            'color_royal_gold': {'type': 'color', 'name': 'Gold', 'price_gold': 0},
            'sigil_none': {'type': 'sigil', 'name': 'No Sigil', 'price_gold': 0},
        })
        screen._kingdom['skills'] = {
            f'skill_{idx}': {
                'name': f'Skill {idx}',
                'description': 'Improves the kingdom configuration.',
                'level': idx % 3,
                'max_level': 5,
                'next_cost': 1,
            }
            for idx in range(8)
        }

        KingdomConfigScreen.render(screen)

        assert screen._content_scroll_area is not None
        assert screen._content_content_h > screen._content_scroll_area.h
        assert screen._cosmetics_scroll_area is None
        assert screen._skills_scroll_area is None
        assert screen._cosmetics_panel_scroll == 0
        assert 'badge' in screen._cosmetic_scroll_areas
        item_h = max(30, min(38, int(0.038 * settings.SCREEN_HEIGHT)))
        assert screen._cosmetic_scroll_areas['badge'].h >= item_h * 2

        assert KingdomConfigScreen._scroll_cosmetics_panel(screen, -1) is False
        assert KingdomConfigScreen._scroll_config_content(screen, -1) is True
        assert screen._content_scroll > 0
        assert KingdomConfigScreen._scroll_cosmetic_section(screen, 'badge', -1) is True
        assert screen._cosmetic_scroll['badge'] > 0
        page_actions = {'back', 'kingdom_prev', 'kingdom_next', 'rename_start'}
        for action, _value, rect in screen._buttons:
            if action not in page_actions:
                assert screen._content_scroll_area.contains(rect)

    def test_iphone_se_cosmetics_and_shield_controls_do_not_overlap(self):
        _run_mobile_geometry_check("""
import pygame
from config import settings
from game.screens.kingdom_config_screen import _BOX_W

pygame.font.init()
left_w = min(settings.KINGDOM_CONFIG_LEFT_W, int(_BOX_W * 0.43))

# Embedded cosmetic cards use the panel viewport width and drop the preview
# on small mobile, leaving a full-width item list.
card_w = left_w - 20
assert card_w < int(0.42 * settings.SCREEN_WIDTH)
list_w = card_w - 14 - 18
row_w = list_w - 8
compact = row_w < 235
chip_w = 28 if compact else 32
btn_w = 58 if compact else 66
price_w = 54 if compact else 72
gap = 6
btn_x = row_w - gap - btn_w
price_x = btn_x - gap - price_w
label_x = 6 + chip_w + 6
label_w = price_x - label_x - gap
assert label_w >= 34
assert label_x + label_w + gap <= price_x
assert price_x + price_w + gap <= btn_x

# Shield hour buttons and Buy Shield share one row without crossing.
shield_w = left_w
pad_x = 14
btn_h = 30
btn_y = settings.KINGDOM_CONFIG_SHIELD_H - 14 - btn_h
content_y = 42
buy_w = 96
btn_gap = 6
options = [6, 12, 24]
inner_w = shield_w - pad_x * 2
option_w = min(58, max(44, (inner_w - buy_w - btn_gap * len(options)) // len(options)))
last_option_right = pad_x + len(options) * option_w + (len(options) - 1) * btn_gap
buy_x = shield_w - pad_x - buy_w
assert last_option_right + btn_gap <= buy_x

body_font = settings.get_font(settings.FS_BODY)
small_font = settings.get_font(settings.FS_SMALL)
quote_bottom = content_y + body_font.get_height() + 4 + small_font.get_height()
assert quote_bottom + 4 <= btn_y
""")

    def test_paid_cosmetic_purchase_requires_confirmation(self, monkeypatch):
        KingdomConfigScreen, screen = _screen_base()
        screen._catalog = {
            'surface_stone': {
                'type': 'surface',
                'name': 'Stone Pattern',
                'price_gold': 950,
            },
        }
        bought = []
        dialogues = []

        def fake_dialogue(self, message, actions=None, title=''):
            dialogues.append((message, actions, title))
            self.dialogue_box = SimpleNamespace(update=lambda _events: None)

        monkeypatch.setattr(KingdomConfigScreen, 'make_dialogue_box', fake_dialogue)
        monkeypatch.setattr(KingdomConfigScreen, '_buy_cosmetic',
                            lambda self, key: bought.append(key))

        KingdomConfigScreen._confirm_cosmetic_purchase(screen, 'surface_stone')

        assert bought == []
        assert screen._pending_purchase['kind'] == 'cosmetic'
        assert screen._pending_purchase['key'] == 'surface_stone'
        assert 'Stone Pattern' in dialogues[0][0]
        assert dialogues[0][1] == ['Confirm', 'Cancel']
        assert dialogues[0][2] == 'Confirm Purchase'

        screen.dialogue_box = SimpleNamespace(update=lambda _events: 'confirm')
        assert KingdomConfigScreen._handle_pending_purchase_dialogue(screen, []) is True
        assert bought == ['surface_stone']
        assert screen._pending_purchase is None

    def test_paid_shield_purchase_requires_confirmation(self, monkeypatch):
        KingdomConfigScreen, screen = _screen_base()
        screen._quote = {'price_gold': 108, 'hours': 6}
        bought = []
        dialogues = []

        def fake_dialogue(self, message, actions=None, title=''):
            dialogues.append((message, actions, title))
            self.dialogue_box = SimpleNamespace(update=lambda _events: None)

        monkeypatch.setattr(KingdomConfigScreen, 'make_dialogue_box', fake_dialogue)
        monkeypatch.setattr(KingdomConfigScreen, '_buy_shield',
                            lambda self: bought.append(True))

        KingdomConfigScreen._confirm_shield_purchase(screen)

        assert bought == []
        assert screen._pending_purchase['kind'] == 'shield'
        assert screen._pending_purchase['hours'] == 6
        assert '108 gold' in dialogues[0][0]

        screen.dialogue_box = SimpleNamespace(update=lambda _events: 'cancel')
        assert KingdomConfigScreen._handle_pending_purchase_dialogue(screen, []) is True
        assert bought == []
        assert screen._pending_purchase is None
        screen.state.set_msg.assert_called_with('Purchase cancelled')

    def test_rename_submit_posts_name_and_updates_gold(self, monkeypatch):
        import game.screens.kingdom_config_screen as module
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._data = {'rename_price_gold': 150, 'kingdoms': [screen._kingdom]}
        screen._gold = 500
        screen._rename_dialog = {'text': 'High Garden', 'error': ''}
        calls = []

        def fake_post(url, json=None, timeout=0):
            calls.append((url, json))
            updated = _kingdom_payload()
            updated['name'] = 'High Garden'
            return _Response({'success': True, 'kingdom': updated, 'gold': 350})

        monkeypatch.setattr(module.requests, 'post', fake_post)
        monkeypatch.setattr(KingdomConfigScreen, '_fetch_config', lambda self: None)

        assert KingdomConfigScreen._submit_rename(screen) is True
        assert calls[0][0].endswith('/kingdom/config/4/rename')
        assert calls[0][1] == {'name': 'High Garden'}
        assert screen._gold == 350
        assert screen.state.user_dict['gold'] == 350
        assert screen._rename_dialog is None

    def test_rename_modal_accepts_textinput_after_keydown(self):
        KingdomConfigScreen, screen = _screen_base()
        screen._rename_dialog = {'text': 'North Pass', 'error': ''}

        events = [
            SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_a),
            SimpleNamespace(type=pygame.TEXTINPUT, text='a'),
        ]

        KingdomConfigScreen.handle_events(screen, events)

        assert screen._rename_dialog['text'] == 'North Passa'

    def test_start_and_close_rename_manage_text_input(self, monkeypatch):
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()

        calls = []
        monkeypatch.setattr(pygame.key, 'start_text_input', lambda: calls.append('start'))
        monkeypatch.setattr(pygame.key, 'stop_text_input', lambda: calls.append('stop'))

        KingdomConfigScreen._start_rename(screen)
        assert screen._rename_dialog is not None

        KingdomConfigScreen._close_rename_dialog(screen)
        assert screen._rename_dialog is None
        assert calls == ['start', 'stop']

    def test_skill_effect_text_uses_current_and_next_increment_values(self):
        KingdomConfigScreen, screen = _screen_base()

        text = KingdomConfigScreen._skill_effect_text(screen, 'gold_production', {
            'level': 1,
            'max_level': 5,
            'increments': {'1': 0.03, '2': 0.06},
        })

        assert '+3% gold' in text
        assert '+6% gold' in text

    def test_skill_effect_text_falls_back_to_current_and_next_bonus(self):
        KingdomConfigScreen, screen = _screen_base()

        text = KingdomConfigScreen._skill_effect_text(screen, 'shield_cost_reduction', {
            'level': 1,
            'max_level': 5,
            'current_bonus': 0.05,
            'next_bonus': 0.10,
        })

        assert '-5% shield cost' in text
        assert '-10% shield cost' in text

    def test_skill_effect_text_gold_vault_uses_default_cap_at_level_zero(self):
        KingdomConfigScreen, screen = _screen_base()
        screen._data = {'vault_default_cap': 50}

        text = KingdomConfigScreen._skill_effect_text(screen, 'gold_vault', {
            'level': 0,
            'max_level': 5,
            'effect_values': [100, 250, 500, 1000, 2000],
        })

        assert 'Current: cap 50' in text
        assert 'Next: cap 100' in text

    def test_skill_effect_text_booster_production_uses_intervals(self):
        KingdomConfigScreen, screen = _screen_base()

        text = KingdomConfigScreen._skill_effect_text(screen, 'main_booster_production', {
            'level': 0,
            'max_level': 5,
            'effect_values': [96, 48, 24, 12, 6],
        })

        assert 'Current: disabled' in text
        assert 'Next: every 96h' in text

    def test_production_panel_collects_when_booster_ready_without_gold(self):
        from config import settings
        KingdomConfigScreen, screen = _screen_base()
        kingdom = _kingdom_payload()
        kingdom['pending_gold'] = 0.0
        kingdom['vault_cap'] = 50
        kingdom['production_items'] = [
            {'key': 'gold', 'kind': 'gold', 'label': 'Gold Vault', 'pending': 0.0,
             'capacity': 50, 'progress_ratio': 0.0},
            {'key': 'main_booster', 'kind': 'booster', 'label': 'Main Booster Pack',
             'skill_key': 'main_booster_production', 'enabled': True, 'pending': 1,
             'capacity': 1, 'full': True, 'progress_ratio': 1.0},
            {'key': 'side_booster', 'kind': 'booster', 'label': 'Side Booster Pack',
             'skill_key': 'side_booster_production', 'enabled': False, 'pending': 0,
             'capacity': 1, 'progress_ratio': 0.0},
        ]
        screen._kingdom = kingdom
        screen._data = {'vault_default_cap': 50}

        rect = pygame.Rect(20, 20, settings.KINGDOM_CONFIG_LEFT_W, 230)
        KingdomConfigScreen._draw_vault_panel(screen, rect)

        actions = {action for action, _value, _rect in screen._buttons}
        assert 'collect_kingdom_production' in actions
        assert 'collect_kingdom_production_item' in actions
        assert screen._collect_btn_rect is not None

    def test_production_panel_registers_only_ready_item_compartments(self):
        from config import settings
        KingdomConfigScreen, screen = _screen_base()
        kingdom = _kingdom_payload()
        kingdom['production_items'] = [
            {'key': 'gold', 'kind': 'gold', 'label': 'Gold Vault', 'pending': 0.4,
             'capacity': 50, 'progress_ratio': 0.01},
            {'key': 'main_booster', 'kind': 'booster', 'label': 'Main Booster Pack',
             'skill_key': 'main_booster_production', 'enabled': True, 'pending': 1,
             'capacity': 1, 'full': True, 'progress_ratio': 1.0},
            {'key': 'side_booster', 'kind': 'booster', 'label': 'Side Booster Pack',
             'skill_key': 'side_booster_production', 'enabled': True, 'pending': 0,
             'capacity': 1, 'progress_ratio': 0.5},
        ]
        screen._kingdom = kingdom

        rect = pygame.Rect(20, 20, settings.KINGDOM_CONFIG_LEFT_W, 230)
        KingdomConfigScreen._draw_vault_panel(screen, rect)

        item_actions = [(action, value) for action, value, _rect in screen._buttons
                        if action == 'collect_kingdom_production_item']
        assert item_actions == [('collect_kingdom_production_item', 'main_booster')]

    def test_render_registers_skill_and_shield_actions(self):
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._data = {'shield_options_hours': [6, 12, 24]}
        screen._catalog = {
            'badge_plain': {'type': 'badge', 'name': 'Plain', 'price_gold': 0},
            'border_simple_gold': {'type': 'border', 'name': 'Gold', 'price_gold': 0},
            'surface_plain': {'type': 'surface', 'name': 'Plain', 'price_gold': 0},
        }
        screen._gold = 500
        screen._quote = {'price_gold': 108}

        KingdomConfigScreen.render(screen)

        actions = {action for action, _value, _rect in screen._buttons}
        assert 'upgrade_skill' in actions
        assert 'rename_start' in actions
        assert 'back' in actions

        screen._content_scroll = (
            screen._content_content_h - screen._content_scroll_area.h
        )
        KingdomConfigScreen.render(screen)

        actions = {action for action, _value, _rect in screen._buttons}
        assert 'buy_shield' in actions
        assert 'select_hours' in actions
        assert 'rename_start' in actions
        assert 'back' in actions

    def test_render_uses_menu_chrome_and_overlay(self):
        KingdomConfigScreen, screen = _screen_base()
        screen._loading = True

        KingdomConfigScreen.render(screen)

        screen._draw_menu_chrome.assert_called_once_with()
        screen._draw_menu_overlay.assert_called_once_with()

    def test_render_does_not_draw_header_gold_pill(self, monkeypatch):
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._data = {'shield_options_hours': [6, 12, 24]}
        screen._catalog = {
            'badge_plain': {'type': 'badge', 'name': 'Plain', 'price_gold': 0},
            'border_simple_gold': {'type': 'border', 'name': 'Gold', 'price_gold': 0},
            'surface_plain': {'type': 'surface', 'name': 'Plain', 'price_gold': 0},
        }
        screen._gold = 500
        screen._quote = {'price_gold': 108}

        status_calls = []
        monkeypatch.setattr(KingdomConfigScreen, '_draw_status_pill',
                            lambda *_args, **_kwargs: status_calls.append(True))

        KingdomConfigScreen.render(screen)

        assert status_calls == []

    def test_rendered_button_actions_are_handled(self):
        import game.screens.kingdom_config_screen as module
        KingdomConfigScreen, screen = _screen_base()
        first = _kingdom_payload()
        second = _kingdom_payload()
        second['id'] = 9
        screen._kingdom = first
        screen._data = {'shield_options_hours': [6, 12, 24], 'kingdoms': [first, second]}
        screen._catalog = {
            'badge_plain': {'type': 'badge', 'name': 'Plain', 'price_gold': 0},
            'border_simple_gold': {'type': 'border', 'name': 'Gold', 'price_gold': 0},
            'surface_plain': {'type': 'surface', 'name': 'Plain', 'price_gold': 0},
        }
        screen._gold = 500
        screen._quote = {'price_gold': 108}

        KingdomConfigScreen.render(screen)

        actions = {action for action, _value, _rect in screen._buttons}
        assert actions <= module.HANDLED_KINGDOM_CONFIG_ACTIONS
        assert {'kingdom_prev', 'kingdom_next'} <= actions

    def test_render_header_uses_kingdom_name_not_generic_label(self):
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._data = {'shield_options_hours': [6, 12, 24]}
        screen._catalog = {}
        screen._gold = 500
        screen._quote = {'price_gold': 108}

        rendered_titles = []
        original_font = screen._title_font

        class _RecordingFont:
            def render(self, text, antialias, color):
                rendered_titles.append(text)
                return original_font.render(text, antialias, color)

            def size(self, text):
                return original_font.size(text)

        screen._title_font = _RecordingFont()

        KingdomConfigScreen.render(screen)

        assert 'North Pass' in rendered_titles
        assert 'Kingdom Config' not in rendered_titles
        actions = [action for action, _value, _rect in screen._buttons]
        assert actions.count('rename_start') == 1
        assert screen._rename_icon_rect is not None

    def test_render_vault_panel_reads_pending_gold_and_rate(self):
        from config import settings
        KingdomConfigScreen, screen = _screen_base()
        kingdom = _kingdom_payload()
        kingdom['pending_gold'] = 17.5
        kingdom['vault_cap'] = 80
        kingdom['gold_rate_per_hour'] = 24.5
        screen._kingdom = kingdom
        screen._data = {'vault_default_cap': 50, 'shield_options_hours': [6, 12, 24]}
        screen._catalog = {}
        screen._gold = 100
        screen._quote = {'price_gold': 0}

        rendered_tiny = []
        original_tiny = screen._tiny_font

        class _RecordingTinyFont:
            def render(self, text, antialias, color):
                rendered_tiny.append((text, tuple(color)))
                return original_tiny.render(text, antialias, color)

            def size(self, text):
                return original_tiny.size(text)

            def get_height(self):
                return original_tiny.get_height()

        screen._tiny_font = _RecordingTinyFont()

        KingdomConfigScreen.render(screen)

        # Collect button is present and enabled when pending > 0.
        actions = {action for action, _value, _rect in screen._buttons}
        assert 'collect_kingdom_production' in actions
        assert screen._collect_btn_rect is not None
        assert ('20.0 g/hr (+4.5)', tuple(settings.KINGDOM_CONFIG_HIGHLIGHT)) in rendered_tiny

    def test_collect_single_production_item_posts_item_key_and_updates_maps(self, monkeypatch):
        import game.screens.kingdom_config_screen as module
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._collect_btn_rect = pygame.Rect(10, 10, 80, 30)
        origin_rect = pygame.Rect(120, 120, 80, 80)
        quote_calls = []

        calls = []

        def fake_post(url, json=None, timeout=0):
            calls.append((url, json, timeout))
            return _Response({
                'success': True,
                'collected_gold': 0,
                'collected_main_boosters': 0,
                'collected_side_boosters': 0,
                'collected_maps': 1,
                'gold': 77,
                'maps': 4,
                'pending_gold': 0.0,
                'pending_main_boosters': 0,
                'pending_side_boosters': 0,
                'pending_maps': 0,
                'production': {},
                'production_items': [],
            })

        monkeypatch.setattr(module.requests, 'post', fake_post)
        monkeypatch.setattr(KingdomConfigScreen, '_fetch_quote',
                            lambda self, silent=False: quote_calls.append(silent))

        KingdomConfigScreen._collect_kingdom_production(
            screen, item_key='map', origin_rect=origin_rect)

        assert calls[0][0].endswith('/kingdom/4/collect_production')
        assert calls[0][1] == {'item_key': 'map'}
        assert screen.state.user_dict['maps'] == 4
        assert screen._message == 'Collected +1 map'
        assert len(screen._floating_text) == 1
        assert quote_calls == [True]

    def test_loot_cards_from_events_flattens_valid_cards_only(self):
        KingdomConfigScreen, screen = _screen_base()

        cards = KingdomConfigScreen._loot_cards_from_events(screen, [
            {
                'cards': [
                    {'rank': 'A', 'suit': 'Hearts'},
                    {'rank': None, 'suit': 'Spades'},
                    'bad-row',
                ]
            },
            {
                'cards': [
                    {'rank': '10', 'suit': 'Clubs', 'source': 'battle_move'},
                ]
            },
            None,
        ])

        assert [(card['rank'], card['suit']) for card in cards] == [
            ('A', 'Hearts'),
            ('10', 'Clubs'),
        ]

    def test_loot_stack_layout_overlaps_cards_to_fit_width(self):
        KingdomConfigScreen, screen = _screen_base()

        layout = KingdomConfigScreen._loot_stack_layout(
            screen, card_count=10, card_w=42, max_width=140)

        assert layout['step'] < 42
        assert layout['step'] >= 0
        assert layout['total_w'] <= 140

    def test_draw_loot_inbox_panel_uses_card_images_for_both_compartments(self, monkeypatch):
        from config import settings
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._kingdom['loot_inbox'] = {
            'gained': [{
                'cards': [
                    {'rank': 'A', 'suit': 'Hearts'},
                    {'rank': '10', 'suit': 'Clubs'},
                ],
            }],
            'lost': [{
                'cards': [
                    {'rank': '7', 'suit': 'Spades'},
                ],
            }],
            'gained_card_count': 2,
            'lost_card_count': 1,
        }

        requested = []

        def fake_surface(self, suit, rank, size):
            requested.append((suit, rank, size))
            return pygame.Surface(size, pygame.SRCALPHA)

        monkeypatch.setattr(KingdomConfigScreen, '_get_loot_card_surface', fake_surface)

        rect = pygame.Rect(20, 20, settings.KINGDOM_CONFIG_LEFT_W, 150)
        KingdomConfigScreen._draw_loot_inbox_panel(screen, rect)

        actions = {action for action, _value, _rect in screen._buttons}
        assert {'collect_loot', 'acknowledge_loot'} <= actions
        button_rects = {action: button_rect for action, _value, button_rect in screen._buttons}
        panel_mid_x = rect.x + 14 + (rect.w - 28) // 2
        assert button_rects['collect_loot'].centerx < panel_mid_x
        assert button_rects['acknowledge_loot'].centerx > panel_mid_x
        assert button_rects['collect_loot'].width > 100
        assert button_rects['acknowledge_loot'].width > 100
        assert button_rects['collect_loot'].height > 60
        assert button_rects['acknowledge_loot'].height > 60
        assert [(suit, rank) for suit, rank, _size in requested] == [
            ('Hearts', 'A'),
            ('Clubs', '10'),
            ('Spades', '7'),
        ]
        assert max(size[0] for _suit, _rank, size in requested) < settings.CARD_WIDTH

    def test_draw_loot_inbox_panel_inactive_compartments_do_not_register_actions(self):
        from config import settings
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._kingdom['loot_inbox'] = {
            'gained': [],
            'lost': [],
            'gained_card_count': 0,
            'lost_card_count': 0,
        }

        rect = pygame.Rect(20, 20, settings.KINGDOM_CONFIG_LEFT_W, 150)
        KingdomConfigScreen._draw_loot_inbox_panel(screen, rect)

        actions = {action for action, _value, _rect in screen._buttons}
        assert 'collect_loot' not in actions
        assert 'acknowledge_loot' not in actions

    def test_inactive_loot_compartment_uses_grey_frame(self, monkeypatch):
        import game.screens.kingdom_config_screen as module
        from config import settings
        KingdomConfigScreen, screen = _screen_base()
        rect = pygame.Rect(20, 20, 140, 100)
        draw_calls = []
        original_draw_rect = module.pygame.draw.rect

        def fake_draw_rect(surface, color, draw_rect, width=0, border_radius=0):
            draw_calls.append((tuple(color), pygame.Rect(draw_rect), width, border_radius))
            return original_draw_rect(surface, color, draw_rect, width, border_radius)

        monkeypatch.setattr(module.pygame.draw, 'rect', fake_draw_rect)

        KingdomConfigScreen._draw_loot_compartment(
            screen,
            rect,
            title='Gained',
            subtitle='Pending collection',
            cards=[],
            card_count=0,
            accent=settings.KINGDOM_CONFIG_GOOD_CLR,
            empty_text='No gained cards waiting here.',
            action='collect_loot',
            active=False,
        )

        assert any(
            color == tuple(settings.KINGDOM_CONFIG_DIM_CLR) and
            width == 1 and
            call_rect == rect
            for color, call_rect, width, _border_radius in draw_calls
        )

    def test_collect_loot_spawns_card_floater(self, monkeypatch):
        KingdomConfigScreen, screen = _screen_base()
        screen._kingdom = _kingdom_payload()
        screen._loot_gained_rect = pygame.Rect(100, 120, 150, 90)

        monkeypatch.setattr(
            KingdomConfigScreen,
            '_post_action',
            lambda self, path, payload=None: {
                'success': True,
                'collected_count': 3,
            },
        )

        KingdomConfigScreen._collect_loot(screen)

        assert len(screen._floating_text) == 1
        assert screen._message == 'Collected 3 looted cards'
