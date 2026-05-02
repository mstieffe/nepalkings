# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for KingdomScreen layout and activity-panel interactions."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _DummyFloatingText:
    def __init__(self, text, pos, color=None, duration_ms=0, rise_px=0, font=None, delay_ms=0):
        self.text = text
        self._x0, self._y0 = pos
        self._delay_ms = delay_ms


class TestKingdomLayout:
    def test_layout_regions_do_not_overlap(self):
        from game.screens.kingdom_screen import _compute_kingdom_layout

        layout = _compute_kingdom_layout()
        header = layout['header']
        map_frame = layout['map_frame']
        map_viewport = layout['map_viewport']
        activity = layout['activity']
        close = layout['close']

        assert not header.colliderect(map_frame)
        assert not header.colliderect(activity)
        assert not map_frame.colliderect(activity)
        assert map_frame.contains(map_viewport)
        assert header.contains(close)
        assert not close.colliderect(activity)

    def test_map_viewport_uses_frame_padding_without_legend_header(self):
        from game.screens.kingdom_screen import _compute_kingdom_layout
        from config import settings

        layout = _compute_kingdom_layout()
        map_frame = layout['map_frame']
        map_viewport = layout['map_viewport']

        assert map_viewport.top == map_frame.top + settings.KINGDOM_MAP_FRAME_PAD
        assert map_viewport.height == map_frame.height - 2 * settings.KINGDOM_MAP_FRAME_PAD


class _DummyHexMap:
    def __init__(self):
        self.focused = []
        self.focused_groups = []
        self.events = []
        self.drag_release = False
        self.zoom = 1.0

    def focus_land(self, land_id):
        self.focused.append(land_id)
        return SimpleNamespace(land_id=land_id)

    def focus_lands(self, land_ids):
        self.focused_groups.append(list(land_ids))
        if land_ids:
            self.focused.append(land_ids[0])
            return SimpleNamespace(land_id=land_ids[0])
        return None

    def is_drag_release(self, event):
        return self.drag_release

    def handle_event(self, event):
        self.events.append(event)
        return None

    def handle_minimap_click(self, sx, sy):
        return False

    def pan(self, dx, dy):
        return None


class TestKingdomActivityPanel:
    def _screen(self):
        from game.screens.kingdom_screen import KingdomScreen

        screen = KingdomScreen.__new__(KingdomScreen)
        screen._activity_rect = pygame.Rect(10, 10, 300, 400)
        screen._activity_tab = 'alerts'
        screen._messages = []
        screen._message_unread_count = 0
        screen._message_compose = None
        screen._activity_tab_rects = {
            'alerts': pygame.Rect(20, 20, 80, 30),
            'history': pygame.Rect(105, 20, 80, 30),
            'messages': pygame.Rect(190, 20, 80, 30),
        }
        screen._mark_read_rect = None
        screen._mark_read_kind = None
        screen._activity_row_rects = []
        screen._activity_scroll_offsets = {'alerts': 0, 'history': 0, 'messages': 0}
        screen._activity_scrollbar_rect = None
        screen._hex_map = _DummyHexMap()
        screen.state = SimpleNamespace(set_msg=MagicMock(), user_dict={'id': 7})
        return KingdomScreen, screen

    def test_tab_click_switches_activity_tab(self):
        KingdomScreen, screen = self._screen()

        handled = KingdomScreen._handle_activity_click(screen, (110, 25))

        assert handled is True
        assert screen._activity_tab == 'history'

    def test_row_click_focuses_related_land(self):
        KingdomScreen, screen = self._screen()
        screen._activity_row_rects = [(
            pygame.Rect(20, 80, 260, 50),
            {'land_id': 42, 'land_col': 3, 'land_row': 5},
        )]

        handled = KingdomScreen._handle_activity_click(screen, (30, 90))

        assert handled is True
        assert screen._hex_map.focused == [42]
        screen.state.set_msg.assert_called_once()

    def test_message_row_click_opens_reply_compose(self):
        KingdomScreen, screen = self._screen()
        message = {
            'id': 1,
            'sender_user_id': 8,
            'recipient_user_id': 7,
            'sender_username': 'rival',
            'recipient_username': 'me',
            'message': 'Nice border.',
            'land_id': 42,
        }
        screen._activity_row_rects = [(pygame.Rect(20, 80, 260, 50), message)]

        handled = KingdomScreen._handle_activity_click(screen, (30, 90))

        assert handled is True
        assert screen._message_compose['recipient_user_id'] == 8
        assert screen._message_compose['recipient_username'] == 'rival'
        assert screen._message_compose['land_id'] == 42

    def test_history_formatting_is_role_aware(self):
        KingdomScreen, screen = self._screen()
        screen._notifications = []

        own_win = {
            'attacker_user_id': 7,
            'defender_user_id': 8,
            'attacker_username': 'me',
            'defender_username': 'rival',
            'result': 'attacker_won',
            'card_won_suit': 'Spades',
            'card_won_rank': 'A',
        }
        defence_win = {
            'attacker_user_id': 8,
            'defender_user_id': 7,
            'attacker_username': 'rival',
            'defender_username': 'me',
            'result': 'defender_won',
            'card_lost_suit': 'Hearts',
            'card_lost_rank': 'K',
        }

        title, detail, good = KingdomScreen._format_activity_item(screen, own_win)
        assert title == 'You conquered rival'
        assert detail == 'Key card won: A of Spades'
        assert good is True

        title, detail, good = KingdomScreen._format_activity_item(screen, defence_win)
        assert title == 'rival failed to conquer you'
        assert detail == 'Key card won: K of Hearts'
        assert good is True

    def test_alert_formatting_uses_server_role_not_list_membership(self):
        KingdomScreen, screen = self._screen()
        own_attack_unseen = {
            'attacker_user_id': 7,
            'defender_user_id': 8,
            'attacker_username': 'me',
            'defender_username': 'rival',
            'result': 'attacker_won',
            'role': 'attacker',
            'seen': False,
        }
        incoming_loss = {
            'attacker_user_id': 8,
            'defender_user_id': 7,
            'attacker_username': 'rival',
            'defender_username': 'me',
            'result': 'attacker_won',
            'role': 'defender',
            'seen': False,
            'card_won_suit': 'Clubs',
            'card_won_rank': 'Q',
        }
        screen._notifications = [own_attack_unseen, incoming_loss]

        title, _detail, good = KingdomScreen._format_activity_item(screen, own_attack_unseen)
        assert title == 'You conquered rival'
        assert good is True

        title, detail, good = KingdomScreen._format_activity_item(screen, incoming_loss)
        assert title == 'rival conquered your land'
        assert detail == 'Key card lost: Q of Clubs'
        assert good is False

    def test_visible_notifications_excludes_seen_rows(self):
        KingdomScreen, screen = self._screen()
        unseen = {'id': 1, 'seen': False}
        legacy_without_seen = {'id': 2}
        seen = {'id': 3, 'seen': True}
        screen._notifications = [unseen, legacy_without_seen, seen]

        assert KingdomScreen._visible_notifications(screen) == [unseen, legacy_without_seen]

    def test_kingdom_event_formatting_covers_loot_and_shield(self):
        KingdomScreen, screen = self._screen()
        looted = {
            'id': 1,
            'source': 'kingdom_notification',
            'kind': 'card_looted',
            'payload': {
                'rank': 'K',
                'suit': 'Hearts',
                'defender_name': 'rival',
                'land_id': 42,
            },
            'seen': False,
        }
        shield = {
            'id': 2,
            'source': 'kingdom_notification',
            'kind': 'shield_expired',
            'payload': {'kingdom_name': 'High Garden'},
            'seen': False,
        }

        title, detail, good = KingdomScreen._format_activity_item(screen, looted)
        assert title == 'Card looted'
        assert detail == 'K of Hearts lost to rival.'
        assert good is False
        assert KingdomScreen._activity_land_label(screen, looted) == 'Land #42'

        title, detail, good = KingdomScreen._format_activity_item(screen, shield)
        assert title == 'Shield expired'
        assert detail == 'High Garden can be attacked again.'
        assert good is False
        assert KingdomScreen._activity_land_label(screen, shield) == 'High Garden'

    def test_activity_formatting_prefers_server_presentation_contract(self):
        KingdomScreen, screen = self._screen()
        item = {
            'attacker_user_id': 8,
            'defender_user_id': 7,
            'attacker_username': 'rival',
            'defender_username': 'me',
            'result': 'attacker_won',
            'role': 'defender',
            'activity_title': 'Server normalized title',
            'activity_detail': 'Server normalized detail.',
            'activity_tone': 'neutral',
            'activity_land_label': 'Borderland',
        }

        title, detail, good = KingdomScreen._format_activity_item(screen, item)

        assert title == 'Server normalized title'
        assert detail == 'Server normalized detail.'
        assert good is True
        assert KingdomScreen._activity_land_label(screen, item) == 'Borderland'

    def test_activity_panel_scrolls_beyond_first_page(self):
        from game.screens.kingdom_screen import KingdomScreen
        from config import settings

        screen = KingdomScreen.__new__(KingdomScreen)
        screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        screen._activity_rect = pygame.Rect(10, 10, 360, 230)
        screen._activity_tab = 'alerts'
        screen._attack_history = []
        screen._messages = []
        screen._message_unread_count = 0
        screen._activity_scroll_offsets = {'alerts': 2, 'history': 0, 'messages': 0}
        screen._activity_title_font = settings.get_font(settings.FS_SMALL, bold=True)
        screen._activity_font = settings.get_font(settings.FS_TINY)
        screen._activity_small_font = settings.get_font(int(settings.FS_TINY * 0.86))
        visible_count = KingdomScreen._activity_visible_count(screen)
        screen._notifications = [
            {
                'id': idx,
                'seen': False,
                'land_id': idx,
                'activity_title': f'Alert {idx}',
                'activity_detail': 'detail',
                'activity_tone': 'neutral',
            }
            for idx in range(visible_count + 4)
        ]

        KingdomScreen._draw_activity_panel(screen)

        assert screen._activity_row_rects[0][1]['id'] == 2
        assert len(screen._activity_row_rects) == visible_count
        assert screen._activity_scrollbar_rect is not None

        assert KingdomScreen._scroll_activity_tab(screen, -99) is True
        assert screen._activity_scroll_offsets['alerts'] == 0

    def test_message_formatting_is_role_aware(self):
        KingdomScreen, screen = self._screen()

        received = {
            'sender_user_id': 8,
            'recipient_user_id': 7,
            'sender_username': 'rival',
            'recipient_username': 'me',
            'message': 'Hello',
        }
        sent = {
            'sender_user_id': 7,
            'recipient_user_id': 8,
            'sender_username': 'me',
            'recipient_username': 'rival',
            'message': 'Reply',
        }

        title, detail, good = KingdomScreen._format_activity_item(screen, received)
        assert title == 'From rival'
        assert detail == 'Hello'
        assert good is True

        title, detail, good = KingdomScreen._format_activity_item(screen, sent)
        assert title == 'To rival'
        assert detail == 'Reply'
        assert good is True

    def test_wrap_text_keeps_lines_inside_width(self):
        from config import settings

        KingdomScreen, screen = self._screen()
        font = settings.get_font(settings.FS_TINY)
        max_width = 110

        lines = KingdomScreen._wrap_text(
            screen,
            'Messages will appear here after the kingdom messenger is added.',
            font,
            max_width,
        )

        assert len(lines) > 1
        assert all(font.size(line)[0] <= max_width for line in lines)

    def test_activity_panel_renders_without_unread_messages(self):
        from game.screens.kingdom_screen import KingdomScreen
        from config import settings

        screen = KingdomScreen.__new__(KingdomScreen)
        screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        screen._activity_rect = pygame.Rect(10, 10, 360, 500)
        screen._activity_tab = 'alerts'
        screen._notifications = []
        screen._attack_history = []
        screen._messages = []
        screen._message_unread_count = 0
        screen._activity_title_font = settings.get_font(settings.FS_SMALL, bold=True)
        screen._activity_font = settings.get_font(settings.FS_TINY)
        screen._activity_small_font = settings.get_font(int(settings.FS_TINY * 0.86))

        KingdomScreen._draw_activity_panel(screen)

        assert 'alerts' in screen._activity_tab_rects
        assert 'messages' in screen._activity_tab_rects
        assert 'cosmetics' not in screen._activity_tab_rects


class TestKingdomDragRelease:
    def _screen(self):
        from game.screens.kingdom_screen import KingdomScreen

        screen = KingdomScreen.__new__(KingdomScreen)
        screen.state = SimpleNamespace(
            screen='kingdom',
            set_msg=MagicMock(),
            user_dict={'id': 7},
        )
        screen.control_buttons = []
        screen.dialogue_box = None
        screen._detail_box = None
        screen._message_compose = None
        screen._btn_close_rect = pygame.Rect(0, 0, 20, 20)
        screen._box_rect = pygame.Rect(100, 100, 400, 300)
        screen._activity_rect = pygame.Rect(550, 120, 220, 240)
        screen._activity_tab_rects = {}
        screen._mark_read_rect = None
        screen._mark_read_kind = None
        screen._activity_row_rects = []
        screen._nav_rects = {}
        screen._handle_icon_events = MagicMock(return_value=False)
        screen._hex_map = _DummyHexMap()
        screen._collect_all_rect = None
        return KingdomScreen, screen

    def test_drag_release_outside_box_does_not_close_screen(self):
        KingdomScreen, screen = self._screen()
        screen._hex_map.drag_release = True
        event = SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1, pos=(20, 20))

        KingdomScreen.handle_events(screen, [event])

        assert screen.state.screen == 'kingdom'
        assert screen._hex_map.events == [event]

    def test_non_drag_release_outside_box_still_closes_screen(self):
        KingdomScreen, screen = self._screen()
        screen._hex_map.drag_release = False
        event = SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1, pos=(20, 20))

        KingdomScreen.handle_events(screen, [event])

        assert screen.state.screen == 'game_menu'
        assert screen._hex_map.events == []


class TestKingdomLargestComponentFocus:
    def test_focuses_largest_connected_component(self):
        from game.screens.kingdom_screen import KingdomScreen

        screen = KingdomScreen.__new__(KingdomScreen)
        screen._hex_map = _DummyHexMap()
        screen._map_data = {
            'my_kingdom': {
                'components': [
                    {'size': 2, 'land_ids': [100, 101]},
                    {'size': 4, 'land_ids': [200, 201, 202, 203]},
                ]
            }
        }

        tile = KingdomScreen._focus_largest_kingdom_component(screen)

        assert tile.land_id == 200
        assert screen._hex_map.focused_groups == [[200, 201, 202, 203]]

    def test_focus_noop_without_components(self):
        from game.screens.kingdom_screen import KingdomScreen

        screen = KingdomScreen.__new__(KingdomScreen)
        screen._hex_map = _DummyHexMap()
        screen._map_data = {'my_kingdom': {'components': []}}

        tile = KingdomScreen._focus_largest_kingdom_component(screen)

        assert tile is None
        assert screen._hex_map.focused_groups == []


class TestKingdomCollectAllFloater:
    def _screen(self):
        from game.screens.kingdom_screen import KingdomScreen
        from game.components.floating_text import FloatingTextLayer
        from config import settings

        screen = KingdomScreen.__new__(KingdomScreen)
        screen._collect_all_rect = pygame.Rect(200, 120, 140, 34)
        screen._floating_text = FloatingTextLayer()
        screen._floating_text_last_tick = 0
        screen._collect_float_font = settings.get_font(
            getattr(settings, 'COLLECT_FLOAT_FONT_SIZE', settings.FS_HEADING),
            bold=True,
        )
        screen._suppress_next_gold_floater = MagicMock()
        screen._load_map = MagicMock()
        screen.state = SimpleNamespace(user_dict={'gold': 100}, set_msg=MagicMock())
        return KingdomScreen, screen

    def test_collect_all_spawns_floater_from_collect_button_center(self, monkeypatch):
        import game.screens.kingdom_screen as module
        KingdomScreen, screen = self._screen()
        monkeypatch.setattr(module, 'FloatingText', _DummyFloatingText)

        monkeypatch.setattr(
            module.requests,
            'post',
            lambda url, timeout=0: _Response({'gold': 125, 'collected_total': 25}),
        )

        KingdomScreen._collect_all_gold(screen)

        assert screen.state.user_dict['gold'] == 125
        assert len(screen._floating_text._items) == 1
        item = screen._floating_text._items[0]
        assert (item._x0, item._y0) == screen._collect_all_rect.center
        screen._suppress_next_gold_floater.assert_called_once_with()
        screen._load_map.assert_called_once_with()

    def test_collect_all_updates_floater_tick_after_reload(self, monkeypatch):
        import game.screens.kingdom_screen as module
        KingdomScreen, screen = self._screen()
        monkeypatch.setattr(module, 'FloatingText', _DummyFloatingText)

        monkeypatch.setattr(module.pygame.time, 'get_ticks', lambda: 12345)
        monkeypatch.setattr(
            module.requests,
            'post',
            lambda url, timeout=0: _Response({'gold': 103, 'collected_total': 3}),
        )

        KingdomScreen._collect_all_gold(screen)

        assert screen._floating_text_last_tick == 12345

    def test_collect_all_breakdown_uses_single_total_floater(self, monkeypatch):
        import game.screens.kingdom_screen as module
        KingdomScreen, screen = self._screen()
        monkeypatch.setattr(module, 'FloatingText', _DummyFloatingText)

        monkeypatch.setattr(
            module.requests,
            'post',
            lambda url, timeout=0: _Response({
                'gold': 170,
                'collected': 70,
                'kingdoms': [
                    {'collected': 20},
                    {'collected': 0},
                    {'collected': 50},
                ],
            }),
        )

        KingdomScreen._collect_all_gold(screen)

        assert screen.state.user_dict['gold'] == 170
        assert len(screen._floating_text._items) == 1
        item = screen._floating_text._items[0]
        assert item.text == '+70g'
        assert (item._x0, item._y0) == screen._collect_all_rect.center
        assert item._delay_ms == 0

    def test_collect_all_syncs_booster_counts(self, monkeypatch):
        import game.screens.kingdom_screen as module
        KingdomScreen, screen = self._screen()
        monkeypatch.setattr(module, 'FloatingText', _DummyFloatingText)

        requested = []
        monkeypatch.setattr(
            module.requests,
            'post',
            lambda url, timeout=0: requested.append(url) or _Response({
                'gold': 100,
                'collected_gold_total': 0,
                'collected_main_boosters_total': 1,
                'collected_side_boosters_total': 2,
                'booster_packs': 4,
                'booster_packs_side': 5,
            }),
        )

        KingdomScreen._collect_all_gold(screen)

        assert requested and requested[0].endswith('/kingdom/collect_production_all')
        assert screen.state.user_dict['booster_packs'] == 4
        assert screen.state.user_dict['booster_packs_side'] == 5
        screen.state.set_msg.assert_called_once()


class TestKingdomInfoBarHeader:
    def test_info_bar_uses_requested_header_format_and_green_bonus(self):
        from game.screens.kingdom_screen import KingdomScreen
        from config import settings

        screen = KingdomScreen.__new__(KingdomScreen)
        screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        screen._header_rect = pygame.Rect(40, 40, 900, 120)
        screen._btn_close_rect = pygame.Rect(screen._header_rect.right - 30, 42, 28, 28)
        title_font = settings.get_font(settings.SUB_SCREEN_TITLE_FONT_SIZE, bold=True)
        screen._title_surf = title_font.render('Kingdom', True, settings.SUB_SCREEN_TITLE_CLR)
        screen._cooldown = 0
        screen._collect_all_rect = None
        screen._collect_all_enabled = False
        screen._map_data = {
            'my_total_gold_rate': 20.0,
            'my_effective_gold_rate': 23.0,
            'my_lands_count': 9,
            'my_kingdoms': [
                {'pending_gold': 5.0, 'vault_cap': 50.0},
                {'pending_gold': 0.0, 'vault_cap': 60.0},
            ],
        }

        captured = []
        original_info_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE)

        class _RecordingInfoFont:
            def render(self, text, antialias, color):
                captured.append((text, tuple(color)))
                return original_info_font.render(text, antialias, color)

        screen._info_font = _RecordingInfoFont()
        screen._nav_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE, bold=True)

        KingdomScreen._draw_info_bar(screen)

        assert ('kingdoms: 2  lands: 9  gold: 20.0/hr', tuple(settings.KINGDOM_INFO_CLR)) in captured
        assert (' +3.0', tuple(settings.KINGDOM_CONFIG_GOOD_CLR)) in captured
        assert screen._collect_all_enabled is True

    def test_info_bar_collect_all_uses_per_kingdom_whole_gold(self):
        from game.screens.kingdom_screen import KingdomScreen
        from config import settings

        screen = KingdomScreen.__new__(KingdomScreen)
        screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        screen._header_rect = pygame.Rect(40, 40, 900, 120)
        screen._btn_close_rect = pygame.Rect(screen._header_rect.right - 30, 42, 28, 28)
        title_font = settings.get_font(settings.SUB_SCREEN_TITLE_FONT_SIZE, bold=True)
        screen._title_surf = title_font.render('Kingdom', True, settings.SUB_SCREEN_TITLE_CLR)
        screen._cooldown = 0
        screen._collect_all_rect = None
        screen._collect_all_enabled = False
        screen._map_data = {
            'my_total_gold_rate': 10.0,
            'my_effective_gold_rate': 10.0,
            'my_lands_count': 4,
            'my_kingdoms': [
                {'pending_gold': 0.6, 'vault_cap': 50.0},
                {'pending_gold': 0.6, 'vault_cap': 50.0},
            ],
        }

        info_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE)
        screen._info_font = info_font
        captured_nav = []
        original_nav_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE, bold=True)

        class _RecordingNavFont:
            def render(self, text, antialias, color):
                captured_nav.append((text, tuple(color)))
                return original_nav_font.render(text, antialias, color)

        screen._nav_font = _RecordingNavFont()

        KingdomScreen._draw_info_bar(screen)

        assert ('Collect All', (240, 230, 180)) in captured_nav
        assert screen._collect_all_enabled is False

    def test_info_bar_collect_all_enables_for_ready_booster(self):
        from game.screens.kingdom_screen import KingdomScreen
        from config import settings

        screen = KingdomScreen.__new__(KingdomScreen)
        screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        screen._header_rect = pygame.Rect(40, 40, 900, 120)
        screen._btn_close_rect = pygame.Rect(screen._header_rect.right - 30, 42, 28, 28)
        title_font = settings.get_font(settings.SUB_SCREEN_TITLE_FONT_SIZE, bold=True)
        screen._title_surf = title_font.render('Kingdom', True, settings.SUB_SCREEN_TITLE_CLR)
        screen._cooldown = 0
        screen._collect_all_rect = None
        screen._collect_all_enabled = False
        screen._map_data = {
            'my_total_gold_rate': 0.0,
            'my_effective_gold_rate': 0.0,
            'my_lands_count': 1,
            'my_kingdoms': [
                {
                    'pending_gold': 0.0,
                    'vault_cap': 50.0,
                    'production': {
                        'main_booster': {'pending': 1, 'full': True},
                        'side_booster': {'pending': 0},
                    },
                },
            ],
        }

        screen._info_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE)
        captured_nav = []
        original_nav_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE, bold=True)

        class _RecordingNavFont:
            def render(self, text, antialias, color):
                captured_nav.append((text, tuple(color)))
                return original_nav_font.render(text, antialias, color)

        screen._nav_font = _RecordingNavFont()

        KingdomScreen._draw_info_bar(screen)

        assert any(text == 'Collect All: 1 main' for text, _ in captured_nav)
        assert screen._collect_all_enabled is True
