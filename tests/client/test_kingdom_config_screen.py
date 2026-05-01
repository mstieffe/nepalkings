# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the persistent KingdomConfigScreen."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame


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
        user_dict={'gold': 0, 'booster_packs': 0, 'booster_packs_side': 0},
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
    screen._cosmetic_scroll = {'badge': 0, 'border': 0, 'surface': 0}
    screen._cosmetic_scroll_areas = {}
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
        },
        'land_ids': [12, 13],
        'lands_count': 2,
        'unlocked_cosmetics': ['badge_plain', 'border_simple_gold', 'surface_plain'],
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

    def test_init_uses_menu_chrome_without_legacy_controls(self, monkeypatch):
        from game.screens.kingdom_config_screen import KingdomConfigScreen

        state = SimpleNamespace(
            screen='kingdom_config',
            kingdom_config_land_id=12,
            kingdom_config_id=None,
            message_lines=[],
            user_dict={'gold': 0, 'booster_packs': 0, 'booster_packs_side': 0},
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
        assert screen._collect_btn_rect is not None

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
        assert 'buy_shield' in actions
        assert 'select_hours' in actions
        assert 'upgrade_skill' in actions
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
