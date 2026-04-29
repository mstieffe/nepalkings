# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for KingdomScreen layout and activity-panel interactions."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame


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
        }
        defence_win = {
            'attacker_user_id': 8,
            'defender_user_id': 7,
            'attacker_username': 'rival',
            'defender_username': 'me',
            'result': 'defender_won',
        }

        title, _detail, good = KingdomScreen._format_activity_item(screen, own_win)
        assert title == 'You conquered rival'
        assert good is True

        title, _detail, good = KingdomScreen._format_activity_item(screen, defence_win)
        assert title == 'rival failed to conquer you'
        assert good is True

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
        screen._notif_dialogue = None
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
