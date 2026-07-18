# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for modal/detail-box pointer-event ownership."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame


class _Dialogue:
    def __init__(self, response=None):
        self.response = response
        self.events = []

    def update(self, events):
        self.events.extend(events)
        return self.response


class _Button:
    def __init__(self, collide=True):
        self._collide = collide

    def collide(self):
        return self._collide


def _screen_state():
    return SimpleNamespace(
        screen='defence',
        action={'task': 'confirm', 'content': None, 'status': 'open'},
        user='player',
        user_dict={'id': 1},
        game=object(),
        pending_spell_cast=None,
        pending_conquer_prelude_target=None,
        _notified_accepted_challenges=set(),
        _pending_accepted_challenge=None,
        set_msg=MagicMock(),
    )


def test_base_dialogue_captures_before_covered_legacy_control():
    from game.screens.screen import Screen

    state = _screen_state()
    screen = Screen.__new__(Screen)
    screen.state = state
    screen.dialogue_box = _Dialogue()
    screen.logout_button = _Button(collide=True)
    screen.home_button = _Button(collide=False)
    screen.control_buttons = [screen.logout_button, screen.home_button]

    event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20))

    captured = Screen.handle_events(screen, [event])

    assert captured is True
    assert state.screen == 'defence'
    assert state.user == 'player'
    assert screen.dialogue_box.events == [event]


def test_dialogue_action_release_is_not_reused_by_screen_below():
    from game.screens.screen import Screen

    state = _screen_state()
    screen = Screen.__new__(Screen)
    screen.state = state
    screen.dialogue_box = _Dialogue('confirm')
    screen.logout_button = _Button(collide=True)
    screen.home_button = _Button(collide=True)
    screen.control_buttons = [screen.logout_button, screen.home_button]

    captured = Screen.handle_events(screen, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20)),
    ])

    assert captured is True
    assert screen.dialogue_box is None
    assert state.action['status'] == 'confirm'
    assert state.screen == 'defence'


def test_base_dialogue_also_blocks_held_pointer_button_updates():
    from game.screens.screen import Screen

    screen = Screen.__new__(Screen)
    screen.dialogue_box = _Dialogue()
    screen.control_buttons = [MagicMock()]
    screen.game_buttons = [MagicMock()]
    screen.menu_buttons = [MagicMock()]

    Screen.update(screen)

    screen.control_buttons[0].update.assert_not_called()
    screen.game_buttons[0].update.assert_not_called()
    screen.menu_buttons[0].update.assert_not_called()


def test_menu_screen_does_not_continue_routing_captured_dialogue_click():
    from game.screens.settings_screen import SettingsScreen

    state = _screen_state()
    screen = SettingsScreen.__new__(SettingsScreen)
    screen.state = state
    screen.dialogue_box = _Dialogue()
    screen.control_buttons = []
    screen._handle_icon_events = MagicMock(return_value=False)

    SettingsScreen.handle_events(screen, [
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(20, 20)),
    ])

    screen._handle_icon_events.assert_not_called()


def test_duel_shell_dialogue_blocks_non_action_clicks():
    from game.screens.game_screen import GameScreen

    screen = GameScreen.__new__(GameScreen)
    screen.dialogue_box = _Dialogue()
    screen._ensure_duel_screen_game = lambda: True
    screen._handle_duel_coach_events = MagicMock(
        side_effect=AssertionError('dialogue click reached duel UI'))

    GameScreen.handle_events(screen, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(30, 30)),
    ])

    screen._handle_duel_coach_events.assert_not_called()


def test_conquer_shell_dialogue_blocks_non_action_clicks():
    from game.screens.conquer_game_screen import ConquerGameScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.dialogue_box = _Dialogue()
    screen._ensure_conquer_screen_game = lambda: True
    screen._is_battle_countdown_active = MagicMock(
        side_effect=AssertionError('dialogue click reached conquer UI'))

    ConquerGameScreen.handle_events(screen, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(30, 30)),
    ])

    screen._is_battle_countdown_active.assert_not_called()


def test_gameplay_overlay_detection_includes_hand_and_detail_boxes():
    from game.screens.game_screen import GameScreen

    screen = GameScreen.__new__(GameScreen)
    screen.dialogue_box = None
    screen.counter_spell_selector = None
    screen.main_hand = SimpleNamespace(dialogue_box=None)
    screen.side_hand = SimpleNamespace(dialogue_box=None)
    detail = SimpleNamespace(
        dialogue_box=None,
        figure_detail_box=object(),
        battle_move_detail_box=None,
    )
    screen.state = SimpleNamespace(subscreen='field')
    screen.subscreens = {'field': detail}

    assert GameScreen._gameplay_input_overlay_open(screen) is True

    detail.figure_detail_box = None
    screen.main_hand.dialogue_box = object()
    assert GameScreen._gameplay_input_overlay_open(screen) is True


def test_conquer_subscreen_detail_routes_before_parent_chrome():
    from game.screens.conquer_game_screen import ConquerGameScreen

    field = SimpleNamespace(
        dialogue_box=None,
        figure_detail_box=object(),
        battle_move_detail_box=None,
        handle_events=MagicMock(),
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(
        game=SimpleNamespace(mode='conquer'),
        subscreen='field',
    )
    screen.subscreens = {'field': field}
    screen.dialogue_box = None
    screen.counter_spell_selector = None
    screen.main_hand = SimpleNamespace(dialogue_box=None)
    screen.side_hand = SimpleNamespace(dialogue_box=None)
    screen._ensure_conquer_screen_game = lambda: True
    screen._is_battle_countdown_active = lambda: False
    screen._conquer_payoff_pending = None
    screen._handle_battle_intro_window_events = lambda _events: False
    screen._handle_conquer_battle_coach_events = lambda _events: False
    screen._handle_conquer_command_events = MagicMock(
        side_effect=AssertionError('detail click reached parent chrome'))

    event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20))
    ConquerGameScreen.handle_events(screen, [event])

    field.handle_events.assert_called_once_with([event])
    screen._handle_conquer_command_events.assert_not_called()


def test_subscreen_overlay_shields_shared_scroll_and_close_controls():
    from game.screens.sub_screen import SubScreen

    screen = SubScreen.__new__(SubScreen)
    screen.dialogue_box = None
    screen.figure_detail_box = object()
    screen.battle_move_detail_box = None
    screen.scroll_text_list_shifter = MagicMock()
    screen._close_rect = pygame.Rect(0, 0, 60, 60)
    screen._close_hit_rect = screen._close_rect
    screen._on_done = MagicMock()

    SubScreen.handle_events(screen, [
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(20, 20)),
    ])

    screen.scroll_text_list_shifter.handle_events.assert_not_called()
    screen._on_done.assert_not_called()


def test_hand_dialogue_click_does_not_toggle_covered_card():
    from game.components.cards.hand import Hand

    slot = SimpleNamespace(
        card=SimpleNamespace(part_of_battle_move=False),
        rec_card=pygame.Rect(0, 0, 80, 80),
        clicked=False,
    )
    hand = Hand.__new__(Hand)
    hand.dialogue_box = _Dialogue('cancel')
    hand.discard_mode = False
    hand.cards = [slot.card]
    hand.card_slots = [slot]

    Hand.handle_events(hand, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20)),
    ])

    assert hand.dialogue_box is None
    assert slot.clicked is False


def test_field_detail_box_wins_over_pending_target_selection():
    from game.screens.field_screen import FieldScreen

    detail = SimpleNamespace(handle_events=MagicMock(return_value=None))
    screen = FieldScreen.__new__(FieldScreen)
    screen.dialogue_box = None
    screen.figure_detail_box = detail
    screen.battle_move_detail_box = None
    screen.scroll_text_list_shifter = None
    screen.update_hover_state = lambda _pos: None
    screen._is_tactics_hand_battle_field_view_only = lambda: False
    screen.state = SimpleNamespace(
        pending_spell_cast={'spell': 'Health Boost'},
        pending_conquer_prelude_target=None,
    )
    screen._handle_target_selection = MagicMock()

    event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20))
    FieldScreen.handle_events(screen, [event])

    detail.handle_events.assert_called_once_with([event])
    screen._handle_target_selection.assert_not_called()


def test_figure_detail_uses_touch_event_position(monkeypatch):
    from game.components.figure_detail_box import FigureDetailBox

    box = FigureDetailBox.__new__(FigureDetailBox)
    box.buttons = []
    box.close_button_rect = pygame.Rect(10, 10, 40, 40)
    box.border_rect = pygame.Rect(0, 0, 200, 200)
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (500, 500))

    response = FigureDetailBox.update(box, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20)),
    ])

    assert response == 'close'


def test_battle_move_detail_uses_touch_event_position(monkeypatch):
    from game.components.battle_moves.battle_move_detail_box import (
        BattleMoveDetailBox,
    )

    box = BattleMoveDetailBox.__new__(BattleMoveDetailBox)
    box.is_battle_context = False
    box.return_button = None
    box.replace_button = None
    box.fig_arrow_left = None
    box.fig_arrow_right = None
    box.dagger_arrow_left = None
    box.dagger_arrow_right = None
    box.close_button_rect = pygame.Rect(10, 10, 40, 40)
    box.border_rect = pygame.Rect(0, 0, 200, 200)
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (500, 500))

    response = BattleMoveDetailBox.update(box, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20)),
    ])

    assert response == 'close'


def test_confirm_button_can_hit_test_touch_event_position(monkeypatch):
    from game.components.buttons.confirm_button import ConfirmButton

    button = ConfirmButton.__new__(ConfirmButton)
    button.rect = pygame.Rect(10, 10, 40, 40)
    button.hit_pad = 0
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (500, 500))

    assert button.collide((20, 20)) is True
    assert button.collide() is False


def test_battle_move_action_uses_touch_event_position(monkeypatch):
    from game.components.battle_moves.battle_move_detail_box import (
        BattleMoveDetailBox,
    )
    from game.components.buttons.confirm_button import ConfirmButton

    button = ConfirmButton.__new__(ConfirmButton)
    button.rect = pygame.Rect(10, 10, 60, 40)
    button.hit_pad = 0
    button.disabled = False
    box = BattleMoveDetailBox.__new__(BattleMoveDetailBox)
    box.is_battle_context = True
    box.action_buttons = [('use', button)]
    box.fig_arrow_left = None
    box.fig_arrow_right = None
    box.dagger_arrow_left = None
    box.dagger_arrow_right = None
    box.close_button_rect = pygame.Rect(150, 150, 20, 20)
    box.border_rect = pygame.Rect(0, 0, 200, 200)
    box.is_call_move = False
    box.is_dagger_move = False
    box.move_index = 2
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (500, 500))

    response = BattleMoveDetailBox.update(box, [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20)),
    ])

    assert response == {
        'action': 'use',
        'move_index': 2,
        'selected_figure': None,
        'selected_dagger': None,
    }
