# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for the dedicated conquer battle screen shell."""

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

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
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=APP_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _conquer_screen_class():
    from game.screens.conquer_game_screen import ConquerGameScreen

    return ConquerGameScreen


def _game_screen_class():
    from game.screens.game_screen import GameScreen

    return GameScreen


def test_conquer_game_screen_constructs_with_lightweight_game():
    code = r'''
import pygame
from config import settings
pygame.init()
pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
from game.core.state import State
from game.core.game import Game
from game.screens.conquer_game_screen import ConquerGameScreen

def figure(fid, player_id):
    return {
        'id': fid,
        'player_id': player_id,
        'game_id': 999,
        'name': 'Castle',
        'family_name': 'Castle',
        'suit': 'black',
        'field': 'castle',
        'cards': [],
        'is_visible': True,
        'is_secret': False,
        'points': 0,
        'level': 1,
        'health': 10,
        'max_health': 10,
    }

game_dict = {
    'id': 999,
    'state': 'open',
    'mode': 'conquer',
    'conquer_move_model': 'tactics_hand',
    'land_id': 123,
    'land_tier': 1,
    'date': '2026-06-27T00:00:00',
    'stake': 0,
    'game_limit': 45,
    'turn_time_limit': None,
    'winner_player_id': None,
    'finished_at': None,
    'last_battle_result': {},
    'players': [
        {'id': 10, 'user_id': 1, 'username': 'Player', 'turns_left': 0, 'points': 0, 'status': 'active', 'is_online': True, 'main_hand': [], 'side_hand': [], 'figures': [figure(100, 10)]},
        {'id': 20, 'user_id': 2, 'username': '[AI] Defender', 'turns_left': 0, 'points': 0, 'status': 'active', 'is_online': False, 'main_hand': [], 'side_hand': [], 'figures': [figure(200, 20)]},
    ],
    'main_cards': [],
    'side_cards': [],
    'current_round': 1,
    'invader_player_id': 10,
    'turn_player_id': 10,
    'ceasefire_active': False,
    'ceasefire_start_turn': None,
    'pending_spell_id': None,
    'battle_modifier': None,
    'waiting_for_counter_player_id': None,
    'advancing_figure_id': None,
    'advancing_figure_id_2': None,
    'advancing_player_id': None,
    'defending_figure_id': None,
    'defending_figure_id_2': None,
    'battle_decisions': None,
    'battle_confirmed': False,
    'fold_outcome': None,
    'fold_winner_id': None,
    'auto_loss_reason': None,
    'auto_loss_detail': None,
    'resting_figure_ids': [],
    'battle_moves_confirmed': None,
    'battle_round': 0,
    'battle_turn_player_id': None,
    'battle_skipped_rounds': {},
    'conquer_round_deadline_ts': None,
    'conquer_round_timeout_sec': None,
    'conquer_resolution_step': 0,
    'conquer_tactics': [],
    'battle_gamble_counts': {},
    'post_battle_drawn_cards': None,
    'battle_moves': [],
    'active_spells': [],
}
state = State()
state.user_dict = {'id': 1, 'username': 'Player'}
state.game = Game(game_dict, state.user_dict, lightweight=True)
state.screen = 'conquer_game'
state.subscreen = 'field'
screen = ConquerGameScreen(state)
screen.on_enter()
screen.update([])
screen.render()
print('ok')
'''
    _run_mobile_geometry_check(code)


def _base_conquer_screen(game=None):
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(
        screen='conquer_game',
        subscreen='field',
        game=game or SimpleNamespace(mode='conquer'),
        pending_conquer_prelude_target=None,
    )
    screen.subscreens = {
        'field': SimpleNamespace(conquer_own_defender_mode=False),
        'battle_shop': SimpleNamespace(bought_moves=[]),
        'battle': SimpleNamespace(),
    }
    screen._last_conquer_auto_route_key = None
    screen._conquer_auto_ready_attempt_key = None
    return ConquerGameScreen, screen


def _battle_coach_screen(*, move_model='tactics_hand', menu_seen=None,
                         completed_steps=None, skipped=False):
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(
        screen='conquer_game',
        subscreen='field',
        user_dict={
            'onboarding': {
                'menu_hints_seen': list(menu_seen or []),
                'completed_steps': list(completed_steps or []),
                'onboarding_skipped': bool(skipped),
            },
        },
        game=SimpleNamespace(mode='conquer', conquer_move_model=move_model),
    )
    screen.subscreens = {
        'field': SimpleNamespace(dialogue_box=None),
        'battle_shop': SimpleNamespace(dialogue_box=None),
        'battle': SimpleNamespace(dialogue_box=None),
    }
    screen.dialogue_box = None
    screen._withdraw_dialogue_open = False
    screen.waiting_for_counter_response = False
    screen.need_to_respond_to_spell = False
    screen.counter_spell_selector = None
    screen._conquer_timeline_info_rect = pygame.Rect(10, 10, 300, 80)
    screen._conquer_collapsed_header_rect = pygame.Rect(10, 10, 500, 100)
    screen._conquer_objective_action_rects = {}
    screen._conquer_duel_lane_target_rect = lambda: pygame.Rect(320, 150, 260, 180)
    screen._conquer_tactics_rail_target_rect = lambda: pygame.Rect(10, 120, 180, 320)
    screen._round_ledger = SimpleNamespace(rect=lambda: pygame.Rect(220, 460, 520, 110))
    screen._tactics_rail = SimpleNamespace(
        _action_button_rects={},
        _dyn_hand_list_rect=pygame.Rect(18, 140, 164, 220),
    )
    screen._conquer_finish_available = lambda: False
    screen._is_tactics_hand_game = lambda: move_model == 'tactics_hand'
    screen.active_conquer_timeline_step = lambda: SimpleNamespace(kind='overview')
    return ConquerGameScreen, screen


def test_conquer_support_link_targets_halo_edge_not_icon_center():
    ConquerGameScreen = _conquer_screen_class()
    source = pygame.Rect(100, 100, 44, 56)

    halo = ConquerGameScreen._conquer_source_halo_rect(source)
    edge = ConquerGameScreen._conquer_rect_edge_point(halo, (20, halo.centery))

    assert edge == (halo.left, halo.centery)
    assert edge != source.center


def test_conquer_support_link_targets_marker_midpoint():
    """Round 12: the support/block link line ends at the side-marker midpoint
    of the source figure (not the figure center / halo edge)."""
    from game.screens.field_screen import FieldScreen

    ConquerGameScreen = _conquer_screen_class()
    icon = SimpleNamespace(
        hovered=False,
        clicked=False,
        rect_frame=pygame.Rect(0, 0, 44, 56),
        rect_frame_big=pygame.Rect(0, 0, 72, 88),
    )
    icon.rect_frame.center = (200, 300)
    icon.rect_frame_big.center = (200, 300)

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.subscreens = {
        'field': SimpleNamespace(
            icon_cache={42: icon},
            _conquer_icon_marker_geometry=FieldScreen._conquer_icon_marker_geometry,
        ),
    }

    own_endpoint = screen._conquer_support_source_marker_endpoint(42, is_own=True)
    opp_endpoint = screen._conquer_support_source_marker_endpoint(42, is_own=False)

    own_marker = FieldScreen._conquer_icon_marker_geometry(
        icon, (200, 300), is_own=True)
    opp_marker = FieldScreen._conquer_icon_marker_geometry(
        icon, (200, 300), is_own=False)

    # Endpoints match the marker midpoints (not the figure center).
    assert own_endpoint == own_marker['midpoint']
    assert opp_endpoint == opp_marker['midpoint']
    assert own_endpoint != (200, 300)
    # Own marker sits to the right of the figure, opponent marker to the left.
    assert own_endpoint[0] > 200
    assert opp_endpoint[0] < 200


def test_field_icon_click_refreshes_hover_from_event_pos():
    from game.screens.field_screen import FieldScreen

    screen = FieldScreen.__new__(FieldScreen)
    opened = []
    icon = SimpleNamespace(
        hovered=False,
        clicked=False,
        is_visible=True,
        rect_frame=pygame.Rect(40, 40, 30, 30),
        figure=SimpleNamespace(id=5, name='Gorkha Soldier'),
    )
    screen.figure_icons = [icon]
    screen.figure_detail_box = None
    screen.dialogue_box = None
    screen.scroll_text_list_shifter = None
    screen._close_rect = pygame.Rect(999, 999, 1, 1)
    screen._on_done = None
    screen._sync_field_compartments_layout = lambda: None
    screen._is_tactics_hand_battle_field_view_only = lambda: True
    screen._force_immediate_redraw = lambda: None
    screen._open_tactics_hand_battle_detail = lambda clicked: opened.append(clicked)

    event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=icon.rect_frame.center)

    FieldScreen.handle_events(screen, [event])

    assert opened == [icon]
    assert icon.clicked is True


def test_passive_timeline_still_allows_field_inspection_clicks():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    handled = []
    field = SimpleNamespace(
        dialogue_box=None,
        _is_tactics_hand_battle_field_view_only=lambda: True,
        handle_events=lambda events: handled.extend(events),
    )
    screen.state = SimpleNamespace(
        game=SimpleNamespace(mode='conquer'),
        subscreen='field',
    )
    screen.subscreens = {'field': field}
    screen.dialogue_box = None
    screen.need_to_respond_to_spell = False
    screen.waiting_for_counter_response = False
    screen._ensure_conquer_screen_game = lambda: True
    screen._handle_conquer_command_events = lambda events: False
    screen._handle_collapsed_header_events = lambda events: False
    screen._is_tactics_hand_game = lambda: True
    screen._round_ledger = SimpleNamespace(handle_event=lambda event: None)
    screen._tactics_rail = SimpleNamespace(handle_event=lambda event: False)
    screen._conquer_nav_buttons = lambda: []
    screen._normalize_conquer_subscreen = lambda: None
    screen.active_conquer_timeline_step = lambda: SimpleNamespace(interactive=False)

    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(50, 50))

    ConquerGameScreen.handle_events(screen, [event])

    assert handled == [event]


def test_conquer_battle_coach_starts_with_tactics_pointer():
    # Concepts moved to the 'How Battles Work' window; the anchored coach now
    # begins with the Play-a-tactic pointer.
    ConquerGameScreen, screen = _battle_coach_screen()

    step = ConquerGameScreen._current_conquer_battle_coach_step(screen)

    assert step['id'] == 'conquer_battle_tactics'


def _ensure_display_for_window():
    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    if not pygame.font.get_init():
        pygame.font.init()
    return pygame.display.get_surface()


def test_battle_intro_window_shows_once_then_suppressed():
    ConquerGameScreen, screen = _battle_coach_screen()
    screen.window = _ensure_display_for_window()
    screen.state.game.battle_round = 1  # battle phase active

    ConquerGameScreen._maybe_show_battle_intro_window(screen)
    assert screen._battle_intro_dialogue is not None
    pages = screen._battle_intro_dialogue.pages
    assert [page['title'] for page in pages] == ['Battle Phases', 'Tactics Choices']
    assert any('Gamble' in line and 'Combine' in line for line in pages[1]['lines'])
    # While the window is up, the anchored coach is suppressed and the intro
    # is considered paused.
    assert ConquerGameScreen._conquer_battle_coach_allowed(screen) is False
    assert ConquerGameScreen._conquer_battle_intro_paused(screen) is True

    # Mark it seen → no re-show.
    screen.state.user_dict['onboarding']['menu_hints_seen'].append('battle_intro_window')
    screen._battle_intro_dialogue = None
    ConquerGameScreen._maybe_show_battle_intro_window(screen)
    assert screen._battle_intro_dialogue is None


def test_battle_intro_window_suppressed_when_skipped_or_done():
    for kwargs in ({'skipped': True},
                   {'completed_steps': ['finish_first_conquer_battle']}):
        ConquerGameScreen, screen = _battle_coach_screen(**kwargs)
        screen.window = _ensure_display_for_window()
        screen._battle_intro_dialogue = None
        screen.state.game.battle_round = 1
        ConquerGameScreen._maybe_show_battle_intro_window(screen)
        assert screen._battle_intro_dialogue is None


def test_on_enter_primes_conquer_game_start_summary_immediately():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    started = []
    polls = []
    game = SimpleNamespace(
        game_id=77,
        player_id=11,
        mode='conquer',
        conquer_move_model='tactics_hand',
        state='open',
        game_over=False,
        pending_game_over=None,
        game_over_shown=False,
        _conquer_game_entered=False,
        start_game_start_notification_if_needed=lambda: started.append('start'),
    )
    screen.state = SimpleNamespace(
        screen='conquer_game',
        subscreen='battle',
        game=game,
    )
    screen.subscreens = {'field': SimpleNamespace()}
    screen._ensure_conquer_screen_game = lambda: True
    screen._normalize_conquer_subscreen = lambda: None
    screen._reset_game_screen_state = lambda: None
    screen._is_tactics_hand_game = lambda: True
    screen._request_battle_state_poll = lambda force=False: polls.append(force)

    ConquerGameScreen.on_enter(screen)

    assert started == ['start']
    assert polls == [True]
    assert screen.state.subscreen == 'field'


def test_conquer_battle_coach_hidden_after_first_conquer_completion():
    ConquerGameScreen, screen = _battle_coach_screen(
        completed_steps=['finish_first_conquer_battle'])

    step = ConquerGameScreen._current_conquer_battle_coach_step(screen)

    assert step is None


def test_conquer_battle_coach_hidden_when_tutorial_paused():
    ConquerGameScreen, screen = _battle_coach_screen(skipped=True)

    step = ConquerGameScreen._current_conquer_battle_coach_step(screen)

    assert step is None


def test_conquer_battle_coach_shows_tactics_after_timeline():
    ConquerGameScreen, screen = _battle_coach_screen(
        menu_seen={'conquer_battle_timeline_intro',
                   'conquer_battle_figure_power'})
    screen.active_conquer_timeline_step = lambda: SimpleNamespace(kind='attacker')
    screen._tactics_rail._action_button_rects = {
        'play': pygame.Rect(24, 370, 72, 28),
        'skip': pygame.Rect(104, 370, 72, 28),
    }

    step = ConquerGameScreen._current_conquer_battle_coach_step(screen)

    assert step['id'] == 'conquer_battle_tactics'
    assert step['action'] == 'next'
    # Rect set unions the tactic action buttons with the rail target.
    assert len(step['rects']) >= 1


def test_conquer_battle_coach_next_marks_seen_without_advancing_timeline():
    ConquerGameScreen, screen = _battle_coach_screen()
    seen = []
    advanced = []
    screen._conquer_battle_coach_step = {
        'id': 'conquer_battle_timeline_intro',
        'rect': pygame.Rect(10, 10, 300, 80),
        'action': 'next',
    }
    screen._conquer_battle_coach_buttons = [
        (pygame.Rect(600, 40, 80, 32), ('next', 'conquer_battle_timeline_intro')),
    ]
    screen._mark_conquer_battle_coach_seen = seen.append
    screen._advance_active_timeline_step = lambda: advanced.append(True)

    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(620, 50))
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(620, 50))

    handled = ConquerGameScreen._handle_conquer_battle_coach_events(screen, [down])
    handled = ConquerGameScreen._handle_conquer_battle_coach_events(screen, [up]) or handled

    assert handled is True
    assert seen == ['conquer_battle_timeline_intro']
    assert advanced == []


def test_conquer_battle_coach_click_step_marks_seen_and_passes_click_through():
    ConquerGameScreen, screen = _battle_coach_screen()
    seen = []
    screen._conquer_battle_coach_step = {
        'id': 'conquer_battle_tactics',
        'rect': pygame.Rect(320, 150, 260, 180),
        'action': 'click',
    }
    screen._conquer_battle_coach_buttons = []
    screen._mark_conquer_battle_coach_seen = seen.append

    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(340, 170))
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(340, 170))

    handled = ConquerGameScreen._handle_conquer_battle_coach_events(screen, [down, up])

    assert handled is False
    assert seen == ['conquer_battle_tactics']


def test_conquer_battle_tactics_step_follows_timeline():
    ConquerGameScreen, screen = _battle_coach_screen(menu_seen=[
        'conquer_battle_timeline_intro',
        'conquer_battle_figure_power',
    ])
    screen.active_conquer_timeline_step = lambda: SimpleNamespace(kind='overview')

    step = ConquerGameScreen._current_conquer_battle_coach_step(screen)

    assert step['id'] == 'conquer_battle_tactics'
    assert step['action'] == 'next'


def test_conquer_battle_coach_ends_after_tactics_pointer():
    ConquerGameScreen, screen = _battle_coach_screen(menu_seen=[
        'conquer_battle_tactics',
    ])

    step = ConquerGameScreen._current_conquer_battle_coach_step(screen)

    assert step is None


def test_conquer_battle_tactics_step_independent_of_timeline_kind():
    ConquerGameScreen, screen = _battle_coach_screen(menu_seen=[
        'conquer_battle_timeline_intro',
        'conquer_battle_figure_power',
    ])
    screen.active_conquer_timeline_step = lambda: SimpleNamespace(kind='overview')

    step = ConquerGameScreen._current_conquer_battle_coach_step(screen)
    assert step['id'] == 'conquer_battle_tactics'

    screen.active_conquer_timeline_step = lambda: SimpleNamespace(
        kind='attacker',
        primary_action='select_advance',
    )

    step = ConquerGameScreen._current_conquer_battle_coach_step(screen)
    assert step['id'] == 'conquer_battle_tactics'


def test_conquer_result_breakdown_line_attacker_perspective():
    ConquerGameScreen = _conquer_screen_class()
    line = ConquerGameScreen._conquer_result_breakdown_line(
        None, {'fig_diff': 5, 'round_diff': 3}, True)
    assert 'Figures +5' in line
    assert 'Tactics +3' in line
    assert 'Total +8' in line


def test_conquer_result_breakdown_line_flips_for_defender():
    ConquerGameScreen = _conquer_screen_class()
    line = ConquerGameScreen._conquer_result_breakdown_line(
        None, {'fig_diff': 5, 'round_diff': 3}, False)
    assert 'Figures -5' in line
    assert 'Tactics -3' in line
    assert 'Total -8' in line


def test_conquer_result_breakdown_line_absent_without_breakdown():
    ConquerGameScreen = _conquer_screen_class()
    # Auto-loss / withdrawal payloads have no figure/tactic split → no line.
    assert ConquerGameScreen._conquer_result_breakdown_line(None, {}, True) == ''
    assert ConquerGameScreen._conquer_result_breakdown_line(
        None, {'fig_diff': 2}, True) == ''


def test_conquer_battle_intro_pauses_until_overview_seen():
    ConquerGameScreen, screen = _battle_coach_screen()

    assert ConquerGameScreen._conquer_battle_intro_paused(screen) is True

    screen.state.user_dict['onboarding']['menu_hints_seen'] = list(
        ConquerGameScreen._conquer_battle_intro_step_ids())

    assert ConquerGameScreen._conquer_battle_intro_paused(screen) is False


def test_conquer_battle_coach_skip_button_pauses_tutorial():
    ConquerGameScreen, screen = _battle_coach_screen()
    paused = []
    screen._conquer_battle_coach_step = {
        'id': 'conquer_battle_timeline_intro',
        'rect': pygame.Rect(10, 10, 300, 80),
        'action': 'next',
    }
    skip_rect = pygame.Rect(600, 40, 120, 32)
    screen._conquer_battle_coach_buttons = [
        (skip_rect, ('skip_tutorial', 'conquer_battle_timeline_intro')),
    ]
    screen._pause_onboarding_tutorial = lambda: paused.append(True)

    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=skip_rect.center)
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=skip_rect.center)

    handled = ConquerGameScreen._handle_conquer_battle_coach_events(screen, [down])
    handled = ConquerGameScreen._handle_conquer_battle_coach_events(screen, [up]) or handled

    assert handled is True
    assert paused == [True]


def test_conquer_explosion_missing_target_gets_ghost_rect_and_animation():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    spell = {
        'spell_name': 'Explosion',
        'target_figure_id': 77,
        'effect_data': {
            'target_figure_id': 77,
            'target_figure_snapshot': {
                'id': 77,
                'player_id': 20,
                'name': 'Target Knight',
                'family_name': 'Knight',
                'field': 'military',
                'suit': 'Hearts',
                'cards': [{'rank': '6', 'suit': 'Hearts', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = []
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 160, 48)
    field = SimpleNamespace(
        icon_cache={},
        figure_icons=[],
        categorized_figures={
            'self': {'castle': [], 'village': [], 'military': []},
            'opponent': {'castle': [], 'village': [], 'military': []},
        },
        compartments={
            'self': {'military': pygame.Rect(20, 120, 120, 360)},
            'opponent': {'military': pygame.Rect(740, 120, 120, 360)},
        },
        figure_manager=SimpleNamespace(families={}),
    )
    screen.subscreens = {'field': field}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='prelude_own',
                icon_payload='Explosion',
                owner='you',
                active=True,
                completed=False,
            )]

    class _Effects:
        def __init__(self):
            self.spawned = []
            self.cleared = False

        def clear(self):
            self.cleared = True

        def spawn_explosion(self, anchor, target_id):
            self.spawned.append(('explosion', pygame.Rect(anchor), target_id))

        def spawn_banner(self, *args, **kwargs):
            self.spawned.append(('banner', args, kwargs))

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    assert effects.spawned
    assert effects.spawned[0][0] == 'explosion'
    assert effects.spawned[0][2] == 77
    ghost_rect = ConquerGameScreen._lookup_conquer_figure_rect(screen, 77)
    assert ghost_rect is not None
    assert ghost_rect.centerx == field.compartments['opponent']['military'].centerx


def test_conquer_health_boost_missing_target_uses_snapshot_anchor():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    spell = {
        'spell_name': 'Health Boost',
        'target_figure_id': 88,
        'effect_data': {
            'target_figure_id': 88,
            'target_figure_snapshot': {
                'id': 88,
                'player_id': 10,
                'name': 'Boosted Guard',
                'family_name': 'Guard',
                'field': 'village',
                'suit': 'Diamonds',
                'cards': [{'rank': '7', 'suit': 'Diamonds', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = []
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 160, 48)
    field = SimpleNamespace(
        icon_cache={},
        figure_icons=[],
        categorized_figures={
            'self': {'castle': [], 'village': [], 'military': []},
            'opponent': {'castle': [], 'village': [], 'military': []},
        },
        compartments={
            'self': {'village': pygame.Rect(20, 120, 120, 360)},
            'opponent': {'village': pygame.Rect(740, 120, 120, 360)},
        },
        figure_manager=SimpleNamespace(families={}),
    )
    screen.subscreens = {'field': field}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='prelude_own',
                icon_payload='Health Boost',
                owner='you',
                active=True,
                completed=False,
            )]

    class _Effects:
        def __init__(self):
            self.spawned = []

        def clear(self):
            pass

        def spawn_spell_cast(self, spell_name, anchor, target_id, **kwargs):
            self.spawned.append((spell_name, pygame.Rect(anchor), target_id, kwargs))

        def spawn_banner(self, *args, **kwargs):
            self.spawned.append(('banner', args, kwargs))

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    assert effects.spawned
    assert effects.spawned[0][0] == 'Health Boost'
    assert effects.spawned[0][2] == 88
    assert effects.spawned[0][3]['floating_text'] == '+ Health'


def test_conquer_counter_poison_timeline_step_spawns_target_animation():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    active_spell = {
        'id': 501,
        'player_id': 20,
        'spell_name': 'Poison',
        'target_figure_id': 77,
        'effect_data': {
            'counter_origin': True,
            'counter_status': 'executed',
            'target_figure_id': 77,
            'target_figure_snapshot': {
                'id': 77,
                'player_id': 10,
                'name': 'Advancing Guard',
                'family_name': 'Guard',
                'field': 'military',
                'suit': 'Hearts',
            },
            'power_modifier': -6,
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        cached_active_spells=[active_spell],
        battle_modifier=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = [{
        'figure': SimpleNamespace(id=77),
        'rect': pygame.Rect(300, 240, 48, 64),
    }]
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 160, 48)
    screen.subscreens = {'field': SimpleNamespace(icon_cache={}, figure_icons=[])}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='counter',
                icon_payload='Poison',
                owner='Rival',
                active=True,
                completed=False,
            )]

    class _Effects:
        def __init__(self):
            self.spawned = []

        def clear(self):
            pass

        def spawn_spell_cast(self, spell_name, anchor, target_id, **kwargs):
            self.spawned.append((spell_name, pygame.Rect(anchor), target_id, kwargs))

        def spawn_banner(self, *args, **kwargs):
            self.spawned.append(('banner', args, kwargs))

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    assert effects.spawned
    assert effects.spawned[0][0] == 'Poison'
    assert effects.spawned[0][2] == 77
    assert effects.spawned[0][3]['floating_text'] == '-6 power'


def test_conquer_counter_poison_does_not_replay_when_owner_label_changes():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)
    replay_key = ('spell', 'counter', '501')
    active_spell = {
        'id': 501,
        'player_id': 20,
        'spell_name': 'Poison',
        'target_figure_id': 77,
        'effect_data': {
            'counter_origin': True,
            'counter_status': 'executed',
            'target_figure_id': 77,
        },
    }
    screen.state = SimpleNamespace(game=SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        cached_active_spells=[active_spell],
        battle_modifier=[],
    ))
    screen._conquer_lane_figure_rects = [{
        'figure': SimpleNamespace(id=77),
        'rect': pygame.Rect(300, 240, 48, 64),
    }]
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 160, 48)
    screen.subscreens = {'field': SimpleNamespace(icon_cache={}, figure_icons=[])}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def __init__(self):
            self.owner = 'Defender'
            self.completed = False

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='counter',
                icon_payload='Poison',
                owner=self.owner,
                active=not self.completed,
                completed=self.completed,
                replay_key=replay_key,
            )]

    class _Effects:
        def __init__(self):
            self.spawned = []

        def clear(self):
            pass

        def spawn_spell_cast(self, spell_name, anchor, target_id, **kwargs):
            self.spawned.append((spell_name, target_id, kwargs))

        def spawn_banner(self, *args, **kwargs):
            self.spawned.append(('banner', args, kwargs))

    panel = _Panel()
    effects = _Effects()
    screen._conquer_timeline_panel = panel
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)
    panel.owner = 'Rival'
    panel.completed = True
    ConquerGameScreen._pump_conquer_spell_animations(screen)

    assert [event[0] for event in effects.spawned] == ['Poison']


def test_conquer_counter_poison_does_not_replay_after_pending_churn():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)
    replay_key = ('spell', 'counter', '501')
    active_spell = {
        'id': 501,
        'player_id': 20,
        'spell_name': 'Poison',
        'target_figure_id': 77,
        'effect_data': {
            'counter_origin': True,
            'counter_status': 'executed',
            'target_figure_id': 77,
        },
    }
    screen.state = SimpleNamespace(game=SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        cached_active_spells=[active_spell],
        battle_modifier=[],
    ))
    screen._conquer_lane_figure_rects = [{
        'figure': SimpleNamespace(id=77),
        'rect': pygame.Rect(300, 240, 48, 64),
    }]
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 160, 48)
    screen.subscreens = {'field': SimpleNamespace(icon_cache={}, figure_icons=[])}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def __init__(self):
            self.phase = 'active'

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='counter',
                icon_payload='Poison',
                owner='Rival',
                active=self.phase == 'active',
                completed=self.phase == 'completed',
                replay_key=replay_key,
            )]

    class _Effects:
        def __init__(self):
            self.spawned = []

        def clear(self):
            pass

        def spawn_spell_cast(self, spell_name, anchor, target_id, **kwargs):
            self.spawned.append((spell_name, target_id, kwargs))

        def spawn_banner(self, *args, **kwargs):
            self.spawned.append(('banner', args, kwargs))

    panel = _Panel()
    effects = _Effects()
    screen._conquer_timeline_panel = panel
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)
    panel.phase = 'pending'
    ConquerGameScreen._pump_conquer_spell_animations(screen)
    panel.phase = 'completed'
    ConquerGameScreen._pump_conquer_spell_animations(screen)

    assert [event[0] for event in effects.spawned] == ['Poison']


def test_conquer_both_player_prelude_spell_flies_to_both_hands():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    spell = {
        'spell_name': 'Dump Cards',
        'effect_data': {
            'caster_dumped': 4,
            'opponent_dumped': 3,
            'drawn_cards': [{'rank': '7', 'suit': 'Hearts'}],
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = []
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    rail_rect = pygame.Rect(640, 120, 180, 320)
    strip_rect = pygame.Rect(840, 120, 40, 320)
    screen._tactics_rail = SimpleNamespace(_dyn_hand_list_rect=rail_rect)
    screen._conquer_opponent_hand_strip_rect = strip_rect
    screen.subscreens = {'field': SimpleNamespace(icon_cache={}, figure_icons=[])}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='prelude_own',
                icon_payload='Dump Cards',
                owner='you',
                active=True,
                completed=False,
            )]

    class _Effects:
        def __init__(self):
            self.to_rect = []

        def clear(self):
            pass

        def spawn_spell_to_rect(self, spell_name, anchor, target_rect, **kwargs):
            self.to_rect.append((spell_name, pygame.Rect(anchor), pygame.Rect(target_rect), kwargs))

        def spawn_banner(self, *args, **kwargs):
            pass

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    # Dump Cards mutates BOTH hands -> flies to the player rail AND the
    # opponent hand strip.
    assert [(e[0], e[2]) for e in effects.to_rect] == [
        ('Dump Cards', rail_rect), ('Dump Cards', strip_rect)]
    assert all(e[3]['floating_text'] == 'redraw' for e in effects.to_rect)


def test_conquer_forced_deal_flies_to_both_hands():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    active_spell = {
        'id': 502,
        'player_id': 20,
        'spell_name': 'Forced Deal',
        'effect_data': {
            'counter_origin': True,
            'cards_given': [{'rank': '8', 'suit': 'Clubs'}],
            'cards_received': [{'rank': '9', 'suit': 'Spades'}],
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        cached_active_spells=[active_spell],
        battle_modifier=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = []
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    rail_rect = pygame.Rect(640, 120, 180, 320)
    strip_rect = pygame.Rect(840, 120, 40, 320)
    screen._tactics_rail = SimpleNamespace(_dyn_hand_list_rect=rail_rect)
    screen._conquer_opponent_hand_strip_rect = strip_rect
    screen.subscreens = {'field': SimpleNamespace(icon_cache={}, figure_icons=[])}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='counter',
                icon_payload='Forced Deal',
                owner='Rival',
                active=True,
                completed=False,
            )]

    class _Effects:
        def __init__(self):
            self.to_rect = []

        def clear(self):
            pass

        def spawn_spell_to_rect(self, spell_name, anchor, target_rect, **kwargs):
            self.to_rect.append((spell_name, pygame.Rect(target_rect), kwargs))

        def spawn_banner(self, *args, **kwargs):
            pass

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    # Forced Deal mutates BOTH hands -> flies to the player rail AND the
    # opponent hand strip.
    assert effects.to_rect == [
        ('Forced Deal', rail_rect, {'floating_text': 'swap'}),
        ('Forced Deal', strip_rect, {'floating_text': 'swap'}),
    ]


def test_conquer_card_spell_target_routing():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    rail = pygame.Rect(640, 120, 180, 320)
    strip = pygame.Rect(840, 120, 40, 320)
    screen._tactics_rail = SimpleNamespace(_dyn_hand_list_rect=rail)
    screen._conquer_opponent_hand_strip_rect = strip

    def route(name, kind):
        return ConquerGameScreen._conquer_card_spell_target_rects(screen, name, kind)

    # Single-player spells fly only to the caster's hand.
    assert route('Draw 2 MainCards', 'prelude_own') == [rail]
    assert route('Draw 2 MainCards', 'prelude_opp') == [strip]
    assert route('Fill up to 10', 'prelude_own') == [rail]
    # Both-player spells fly to both hands regardless of caster.
    assert route('Dump Cards', 'prelude_own') == [rail, strip]
    assert route('Forced Deal', 'prelude_opp') == [rail, strip]


def test_opponent_hidden_hand_count_counts_available_only():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        game_id=1,
        player_id=10,
        conquer_tactics=[
            {'player_id': 10, 'status': 'available', 'played_round': None},  # yours
            {'player_id': 20, 'status': 'available', 'played_round': None},  # opp hand
            {'player_id': 20, 'status': 'available', 'played_round': None},  # opp hand
            {'player_id': 20, 'status': 'played', 'played_round': 0},        # opp played
            {'player_id': 20, 'status': 'discarded', 'played_round': None},  # opp spent
        ],
    ))
    assert ConquerGameScreen._opponent_hidden_hand_count(screen) == 2


def test_conquer_modifier_prelude_spawns_banner_and_duel_lane_pulse():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    spell = {'spell_name': 'Civil War', 'effect_data': {'battle_modifier_added': 'Civil War'}}
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = []
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    lane_rect = pygame.Rect(180, 130, 420, 240)
    screen._conquer_duel_lane_last_rect = lane_rect
    screen.subscreens = {'field': SimpleNamespace(icon_cache={}, figure_icons=[])}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='prelude_own',
                icon_payload='Civil War',
                owner='you',
                active=True,
                completed=False,
            )]

    class _Effects:
        def __init__(self):
            self.banners = []
            self.pulses = []

        def clear(self):
            pass

        def spawn_banner(self, text, color, **kwargs):
            self.banners.append((text, color, kwargs))

        def spawn_rect_pulse(self, target_rect, color, **kwargs):
            self.pulses.append((pygame.Rect(target_rect), color, kwargs))

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    assert effects.banners[0][0] == 'Civil War'
    assert effects.pulses[0][0] == lane_rect


def test_conquer_modifier_counter_spawns_banner_and_duel_lane_pulse():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    active_spell = {
        'id': 503,
        'player_id': 20,
        'spell_name': 'Blitzkrieg',
        'effect_data': {
            'counter_origin': True,
            'battle_modifier_added': 'Blitzkrieg',
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        cached_active_spells=[active_spell],
        battle_modifier=[{'type': 'Blitzkrieg', 'caster_id': 20, 'spell_id': 503}],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = []
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    lane_rect = pygame.Rect(180, 130, 420, 240)
    screen._conquer_duel_lane_last_rect = lane_rect
    screen.subscreens = {'field': SimpleNamespace(icon_cache={}, figure_icons=[])}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='counter',
                icon_payload='Blitzkrieg',
                owner='Rival',
                active=True,
                completed=False,
            )]

    class _Effects:
        def __init__(self):
            self.banners = []
            self.pulses = []

        def clear(self):
            pass

        def spawn_banner(self, text, color, **kwargs):
            self.banners.append((text, color, kwargs))

        def spawn_rect_pulse(self, target_rect, color, **kwargs):
            self.pulses.append((pygame.Rect(target_rect), color, kwargs))

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    assert effects.banners[0][0] == 'Blitzkrieg'
    assert effects.pulses[0][0] == lane_rect


def test_conquer_health_boost_refires_when_pending_target_resolves():
    """When a pending-target Health Boost first becomes active without a
    resolved target_figure_id, the pump should only emit a banner.  Once
    the target is resolved on a later frame, the real spell-cast
    animation must fire — even though the timeline step has already
    transitioned past ``pending``."""
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    spell = {
        'spell_name': 'Health Boost',
        # Target unresolved on the first frame.
        'target_figure_id': None,
        'effect_data': {
            'target_figure_id': None,
            'target_figure_snapshot': {
                'id': 99,
                'player_id': 10,
                'name': 'Pending Guard',
                'family_name': 'Guard',
                'field': 'village',
                'suit': 'Diamonds',
                'cards': [{'rank': '7', 'suit': 'Diamonds', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = []
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 160, 48)
    field = SimpleNamespace(
        icon_cache={},
        figure_icons=[],
        categorized_figures={
            'self': {'castle': [], 'village': [], 'military': []},
            'opponent': {'castle': [], 'village': [], 'military': []},
        },
        compartments={
            'self': {'village': pygame.Rect(20, 120, 120, 360)},
            'opponent': {'village': pygame.Rect(740, 120, 120, 360)},
        },
        figure_manager=SimpleNamespace(families={}),
    )
    screen.subscreens = {'field': field}

    step = SimpleNamespace(
        kind='prelude_own',
        icon_payload='Health Boost',
        owner='you',
        active=True,
        completed=False,
    )

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [step]

    class _Effects:
        def __init__(self):
            self.spawned = []

        def clear(self):
            pass

        def spawn_spell_cast(self, spell_name, anchor, target_id, **kwargs):
            self.spawned.append(('spell_cast', spell_name, target_id, kwargs))

        def spawn_banner(self, *args, **kwargs):
            self.spawned.append(('banner', args, kwargs))

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    # First-frame seed: pending target → banner only, no spell_cast.
    ConquerGameScreen._pump_conquer_spell_animations(screen)
    assert effects.spawned, "first pump should still emit a banner"
    assert all(kind != 'spell_cast' for kind, *_rest in effects.spawned)

    # Server resolves the target.  Step transitions active → completed.
    spell['target_figure_id'] = 99
    spell['effect_data']['target_figure_id'] = 99
    step.active = False
    step.completed = True

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    spell_casts = [row for row in effects.spawned if row[0] == 'spell_cast']
    assert spell_casts, "spell_cast must fire after the target resolves"
    assert spell_casts[-1][1] == 'Health Boost'
    assert spell_casts[-1][2] == 99


def test_conquer_visual_ghost_spec_persists_during_overview():
    """Bug regression: the Explosion victim must remain visible (and a
    normal field figure) during the overview / pre-prelude window so the
    player can see the destroyed-by reveal."""
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)

    spell = {
        'spell_name': 'Explosion',
        'target_figure_id': 77,
        'effect_data': {
            'target_figure_id': 77,
            'target_figure_snapshot': {
                'id': 77,
                'player_id': 20,
                'name': 'Doomed Knight',
                'family_name': 'Knight',
                'field': 'military',
                'suit': 'Hearts',
                'cards': [{'rank': '6', 'suit': 'Hearts', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)

    class _Panel:
        # Overview holds active.  Sequence gates have demoted prelude_own
        # to a non-active, non-completed state in real game flow, but in
        # other timelines the prelude step can still be reported as
        # completed (auto-resolved) — we cover that case below.
        def derive_display_steps(self, _screen):
            return [
                SimpleNamespace(kind='overview', active=True, completed=False,
                                icon_payload=None, owner=''),
                SimpleNamespace(kind='prelude_own', active=False, completed=True,
                                icon_payload='Explosion', owner='you'),
            ]

    screen._conquer_timeline_panel = _Panel()
    screen._field_explosion_ghost_hold_until = {}

    specs = ConquerGameScreen.conquer_field_visual_ghost_specs(screen)

    assert len(specs) == 1
    spec = specs[0]
    assert spec['target_id'] == 77
    assert spec['spell_name'] == 'Explosion'
    # Snapshot must remain a normal (selectable) field figure during the
    # pre-battle window, regardless of the underlying step phase.
    assert spec['visual_only'] is False
    assert spec['force_visible'] is True


def test_conquer_visual_ghost_spec_is_removed_when_explosion_executes():
    """Explosion victims are replay figures only until their spell executes."""
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)

    spell = {
        'spell_name': 'Explosion',
        'target_figure_id': 77,
        'effect_data': {
            'target_figure_id': 77,
            'target_figure_snapshot': {
                'id': 77,
                'player_id': 20,
                'name': 'Doomed Knight',
                'family_name': 'Knight',
                'field': 'military',
                'suit': 'Hearts',
                'cards': [{'rank': '6', 'suit': 'Hearts', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._field_explosion_ghost_hold_until = {}

    phase_steps = {
        'pending': SimpleNamespace(kind='prelude_own', active=False,
                                   completed=False, icon_payload='Explosion',
                                   owner='you'),
        'active': SimpleNamespace(kind='prelude_own', active=True,
                                  completed=False, icon_payload='Explosion',
                                  owner='you'),
        'completed': SimpleNamespace(kind='prelude_own', active=False,
                                     completed=True, icon_payload='Explosion',
                                     owner='you'),
    }

    class _Panel:
        def __init__(self, step):
            self._step = step

        def derive_display_steps(self, _screen):
            return [self._step]

    captured = {}
    for label, step in phase_steps.items():
        screen._conquer_timeline_panel = _Panel(step)
        specs = ConquerGameScreen.conquer_field_visual_ghost_specs(screen)
        captured[label] = specs

    assert len(captured['pending']) == 1
    assert captured['pending'][0]['visual_only'] is False
    assert captured['pending'][0]['phase'] == 'pending'
    assert captured['active'] == []
    assert captured['completed'] == []


def test_conquer_explosion_visual_ghost_uses_active_spell_fallback():
    """The Explosion victim is visible before game_start summary snapshots land."""
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)

    active_spell = {
        'id': 500,
        'player_id': 10,
        'spell_name': 'Explosion',
        'spell_type': 'enchantment',
        'cast_round': 1,
        'target_figure_id': None,
        'effect_data': {
            'prelude_origin': True,
            'prelude_status': 'executed',
            'destroyed_figure_id': 77,
            'destroyed_figure_snapshot': {
                'id': 77,
                'player_id': 20,
                'name': 'Doomed Knight',
                'family_name': 'Knight',
                'field': 'military',
                'suit': 'Hearts',
                'cards': [{'rank': '6', 'suit': 'Hearts', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[],
        conquer_opp_prelude_spells=[],
        cached_active_spells=[active_spell],
    )
    screen.state = SimpleNamespace(game=game)

    class _Panel:
        def derive_display_steps(self, _screen):
            return [
                SimpleNamespace(kind='overview', active=True, completed=False,
                                icon_payload=None, owner=''),
            ]

    screen._conquer_timeline_panel = _Panel()

    specs = ConquerGameScreen.conquer_field_visual_ghost_specs(screen)

    assert len(specs) == 1
    assert specs[0]['target_id'] == 77
    assert specs[0]['spell_name'] == 'Explosion'
    assert specs[0]['visual_only'] is False


def test_conquer_prelude_enchantment_hidden_until_step_active():
    ConquerGameScreen = _conquer_screen_class()
    from game.screens.field_screen import FieldScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    spell = {
        'spell_name': 'Poison',
        'target_figure_id': 77,
        'effect_data': {'target_figure_id': 77},
    }
    health_spell = {
        'spell_name': 'Health Boost',
        'target_figure_id': 88,
        'effect_data': {'target_figure_id': 88},
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell, health_spell],
        conquer_opp_prelude_spells=[],
        cached_active_spells=[],
    )
    screen.state = SimpleNamespace(game=game)

    class _Panel:
        def __init__(self, steps):
            self._steps = steps

        def derive_display_steps(self, _screen):
            return self._steps

    field = FieldScreen.__new__(FieldScreen)
    field.game = game
    field.state = SimpleNamespace(parent_screen=screen)

    figure = SimpleNamespace(id=77, active_enchantments=[{
        'spell_name': 'Poison',
        'spell_icon': 'poisson_portion.png',
        'power_modifier': -6,
    }])
    boosted = SimpleNamespace(id=88, active_enchantments=[{
        'spell_name': 'Health Boost',
        'spell_icon': 'health_portion.png',
        'power_modifier': 6,
    }])

    screen._conquer_timeline_panel = _Panel([
        SimpleNamespace(kind='overview', active=True, completed=False),
        # Base game state may already mark the prelude complete; the active
        # overview still means this effect is not the leading timeline beat.
        SimpleNamespace(kind='prelude_own', active=False, completed=True),
    ])
    FieldScreen._filter_conquer_timeline_enchantments(field, [figure, boosted])
    assert figure.active_enchantments == []
    assert boosted.active_enchantments == []

    figure.active_enchantments = [{
        'spell_name': 'Poison',
        'spell_icon': 'poisson_portion.png',
        'power_modifier': -6,
    }]
    boosted.active_enchantments = [{
        'spell_name': 'Health Boost',
        'spell_icon': 'health_portion.png',
        'power_modifier': 6,
    }]
    screen._conquer_timeline_panel = _Panel([
        SimpleNamespace(kind='overview', active=False, completed=True),
        SimpleNamespace(kind='prelude_own', active=True, completed=False),
    ])
    FieldScreen._filter_conquer_timeline_enchantments(field, [figure, boosted])
    assert figure.active_enchantments
    assert boosted.active_enchantments


def test_conquer_counter_poison_enchantment_hidden_until_counter_step_active():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    spell = {
        'id': 501,
        'player_id': 20,
        'spell_name': 'Poison',
        'target_figure_id': 77,
        'effect_data': {
            'counter_origin': True,
            'counter_status': 'executed',
            'target_figure_id': 77,
            'power_modifier': -6,
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        battle_turn_player_id=None,
        cached_active_spells=[spell],
        battle_modifier=[],
    )
    screen.state = SimpleNamespace(game=game)

    class _Panel:
        def __init__(self, counter_active):
            self._counter_active = counter_active

        def derive_display_steps(self, _screen):
            return [
                SimpleNamespace(kind='attacker', active=not self._counter_active,
                                completed=False, icon_payload=None, owner=''),
                SimpleNamespace(kind='counter', active=self._counter_active,
                                completed=False, icon_payload='Poison', owner='Rival'),
            ]

    screen._conquer_timeline_panel = _Panel(counter_active=False)
    hidden = ConquerGameScreen.conquer_prelude_enchantment_visibility(screen)
    assert ('Poison', 77) in hidden['tracked']
    assert ('Poison', 77) not in hidden['revealed']

    screen._conquer_timeline_panel = _Panel(counter_active=True)
    revealed = ConquerGameScreen.conquer_prelude_enchantment_visibility(screen)
    assert ('Poison', 77) in revealed['revealed']


def test_conquer_explosion_pending_snapshot_is_normal_field_figure(monkeypatch):
    from game.components.cards.card import Card
    from game.components.figures.figure import Figure
    from game.screens.field_screen import FieldScreen

    family = SimpleNamespace(
        name='Target Knight',
        field='military',
        color='offensive',
        figures=[],
    )
    family.figures = [Figure(
        name='Target Knight',
        sub_name='Hearts 6',
        suit='Hearts',
        family=family,
        key_cards=[Card('K', 'Hearts', 13)],
        number_card=Card('6', 'Hearts', 6),
    )]
    live_figure = Figure(
        name='Live Guard',
        sub_name='Hearts 7',
        suit='Hearts',
        family=family,
        key_cards=[Card('Q', 'Hearts', 12)],
        number_card=Card('7', 'Hearts', 7),
        id=21,
        player_id=20,
    )
    snapshot = {
        'id': 77,
        'player_id': 20,
        'name': 'Target Knight',
        'family_name': 'Target Knight',
        'field': 'military',
        'suit': 'Hearts',
        'cards': [
            {'rank': 'K', 'suit': 'Hearts', 'value': 13, 'role': 'key'},
            {'rank': '6', 'suit': 'Hearts', 'value': 6, 'role': 'number'},
        ],
    }
    parent = SimpleNamespace(
        conquer_field_visual_ghost_specs=lambda: [{
            'target_id': 77,
            'snapshot': snapshot,
            'step_kind': 'prelude_own',
            'spell_name': 'Explosion',
            'phase': 'pending',
            'visual_only': False,
            'force_visible': True,
        }]
    )
    game = SimpleNamespace(
        mode='conquer',
        player_id=10,
        opponent_player={'id': 20},
        get_figures=lambda _families, is_opponent=False: [live_figure] if is_opponent else [],
        calculate_resources=lambda *_args, **_kwargs: {'produces': {}, 'requires': {}},
        has_active_all_seeing_eye=lambda: False,
    )
    field = FieldScreen.__new__(FieldScreen)
    field.window = pygame.Surface((900, 620), pygame.SRCALPHA)
    field.state = SimpleNamespace(parent_screen=parent)
    field.game = game
    field.figure_manager = SimpleNamespace(families={'Target Knight': family})
    field.icon_cache = {}
    field.last_figure_ids = set()
    field.last_enchantment_state = {}
    field.last_player_id = None
    field.cached_all_seeing_eye_status = None
    field._last_all_seeing_eye_status = None
    field._conquer_visual_ghost_ids = set()
    monkeypatch.setattr(FieldScreen, '_generate_figure_icons', lambda self: None)

    FieldScreen.load_figures(field)

    military_figures = field.categorized_figures['opponent']['military']
    assert [figure.id for figure in military_figures] == [21, 77]
    timeline_figure = military_figures[1]
    assert getattr(timeline_figure, '_conquer_timeline_snapshot', False) is True
    assert getattr(timeline_figure, '_conquer_visual_only', False) is False
    assert timeline_figure in field.figures
    assert 77 in field.last_figure_ids


def test_conquer_explosion_active_snapshot_is_visual_only_hold(monkeypatch):
    from game.components.cards.card import Card
    from game.components.figures.figure import Figure
    from game.screens.field_screen import FieldScreen

    family = SimpleNamespace(
        name='Target Knight',
        field='military',
        color='offensive',
        figures=[],
    )
    family.figures = [Figure(
        name='Target Knight',
        sub_name='Hearts 6',
        suit='Hearts',
        family=family,
        key_cards=[Card('K', 'Hearts', 13)],
        number_card=Card('6', 'Hearts', 6),
    )]
    snapshot = {
        'id': 77,
        'player_id': 20,
        'name': 'Target Knight',
        'family_name': 'Target Knight',
        'field': 'military',
        'suit': 'Hearts',
        'cards': [
            {'rank': 'K', 'suit': 'Hearts', 'value': 13, 'role': 'key'},
            {'rank': '6', 'suit': 'Hearts', 'value': 6, 'role': 'number'},
        ],
    }
    parent = SimpleNamespace(
        conquer_field_visual_ghost_specs=lambda: [{
            'target_id': 77,
            'snapshot': snapshot,
            'step_kind': 'prelude_own',
            'spell_name': 'Explosion',
            'phase': 'active',
            'visual_only': True,
            'force_visible': True,
        }]
    )
    game = SimpleNamespace(
        mode='conquer',
        player_id=10,
        opponent_player={'id': 20},
        get_figures=lambda _families, is_opponent=False: [],
        calculate_resources=lambda *_args, **_kwargs: {'produces': {}, 'requires': {}},
        has_active_all_seeing_eye=lambda: False,
    )
    field = FieldScreen.__new__(FieldScreen)
    field.window = pygame.Surface((900, 620), pygame.SRCALPHA)
    field.state = SimpleNamespace(parent_screen=parent)
    field.game = game
    field.figure_manager = SimpleNamespace(families={'Target Knight': family})
    field.icon_cache = {}
    field.last_figure_ids = set()
    field.last_enchantment_state = {}
    field.last_player_id = None
    field.cached_all_seeing_eye_status = None
    field._last_all_seeing_eye_status = None
    field._conquer_visual_ghost_ids = set()
    monkeypatch.setattr(FieldScreen, '_generate_figure_icons', lambda self: None)

    FieldScreen.load_figures(field)

    ghost = field.categorized_figures['opponent']['military'][0]
    assert getattr(ghost, '_conquer_timeline_snapshot', False) is True
    assert getattr(ghost, '_conquer_visual_only', False) is True
    assert ghost not in field.figures
    assert 77 in field.last_figure_ids


def test_conquer_skipped_tactics_fill_lanes_and_enable_finish():
    game = SimpleNamespace(
        mode='conquer',
        player_id=10,
        players=[{'id': 10}, {'id': 20}],
        battle_round=2,
        battle_turn_player_id=None,
        battle_skipped_rounds={'10': [1], '20': [2]},
        last_battle_result=None,
        game_over=False,
    )
    ConquerGameScreen, screen = _base_conquer_screen(game)
    screen._current_conquer_tactics = lambda: [
        {'id': 1, 'player_id': 10, 'family_name': 'Dagger', 'value': 3, 'played_round': 0},
        {'id': 2, 'player_id': 10, 'family_name': 'Wall', 'value': 4, 'played_round': 2},
    ]
    screen._current_conquer_opponent_tactics = lambda: [
        {'id': 3, 'player_id': 20, 'family_name': 'Block', 'value': 0, 'played_round': 0},
        {'id': 4, 'player_id': 20, 'family_name': 'Dagger', 'value': 2, 'played_round': 1},
    ]

    player_slots, opponent_slots = ConquerGameScreen._conquer_lane_played_tactics(screen)

    assert player_slots[1]['_skipped'] is True
    assert player_slots[1]['played_round'] == 1
    assert opponent_slots[2]['_skipped'] is True
    assert opponent_slots[2]['played_round'] == 2
    assert ConquerGameScreen._conquer_finish_available(screen) is True


def test_conquer_support_link_arrow_draws_over_existing_pixels():
    """Support leader arrows are drawn as a final overlay so the endpoint
    stays visible even if it crosses an already-rendered field icon."""
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((240, 160))
    screen.window.fill((32, 28, 24))

    badge_rect = pygame.Rect(150, 70, 24, 20)
    endpoint = (80, 80)
    icon_color = (150, 40, 40)
    pygame.draw.rect(screen.window, icon_color, pygame.Rect(68, 66, 28, 28))

    assert screen.window.get_at(endpoint)[:3] == icon_color
    screen._draw_conquer_lane_source_link(
        badge_rect, endpoint, is_player=True)

    assert screen.window.get_at(endpoint)[:3] != icon_color
    assert screen.window.get_at(endpoint).b > icon_color[2]


def test_conquer_support_hover_tracks_all_source_figures(monkeypatch):
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    field = SimpleNamespace()
    screen.subscreens = {'field': field}
    screen._conquer_receipt_row_rects = []
    screen._conquer_support_badge_rects = [{
        'rect': pygame.Rect(10, 10, 40, 32),
        'entry': {'kind': 'support_bonus'},
        'figure_id': None,
        'source_figure_ids': [101, 102, 103],
        'is_player': True,
    }]
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (20, 20))

    hovered = screen._update_conquer_support_hover_state()

    assert hovered is screen._conquer_support_badge_rects[0]
    assert field._conquer_hover_source_figure_ids == {101, 102, 103}
    # The legacy single-id attribute remains as a compatibility fallback,
    # but field rendering now uses the full set so every source is marked
    # consistently.
    assert field._conquer_hover_source_figure_id == 101


def test_field_support_ids_use_parent_cached_lane_context():
    from game.screens.field_screen import FieldScreen

    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_turn_player_id=1,
        both_battle_moves_ready=False,
        last_battle_result=None,
    )
    calls = []
    parent = SimpleNamespace(
        request_conquer_figure_confirmation=lambda *args, **kwargs: None,
        conquer_active_support_figure_ids=lambda opponent_only=False: calls.append(opponent_only) or ({20} if opponent_only else {10, 20}),
    )
    field = FieldScreen.__new__(FieldScreen)
    field.game = game
    field.state = SimpleNamespace(parent_screen=parent)

    assert FieldScreen._tactics_hand_active_support_figure_ids(field) == {10, 20}
    assert FieldScreen._tactics_hand_active_support_figure_ids(field, opponent_only=True) == {20}
    assert calls == [False, True]


def test_field_support_visibility_syncs_cached_icons_without_reload():
    from game.screens.field_screen import FieldScreen

    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_turn_player_id=1,
        battle_round=1,
        both_battle_moves_ready=False,
        last_battle_result=None,
        game_id=7,
        player_id=1,
        _figures_data_version=1,
    )
    support_ids = {'20'}
    parent = SimpleNamespace(
        request_conquer_figure_confirmation=lambda *args, **kwargs: None,
        _conquer_tactic_cache_key=('round', 1),
        _conquer_opponent_tactic_cache_key=('round', 1),
        conquer_active_support_figure_ids=lambda opponent_only=False: set(support_ids),
    )
    figure = SimpleNamespace(id=20, player_id=2, name='Support Soldier')
    icon = SimpleNamespace(figure=figure, is_visible=False)
    field = FieldScreen.__new__(FieldScreen)
    field.game = game
    field.state = SimpleNamespace(parent_screen=parent)
    field.figure_icons = [icon]
    field.cached_all_seeing_eye_status = False
    field._last_tactics_hand_support_visibility_key = ()

    FieldScreen._sync_tactics_hand_support_visibility(field)

    assert icon.is_visible is True

    support_ids.clear()
    parent._conquer_tactic_cache_key = ('round', 2)
    parent._conquer_opponent_tactic_cache_key = ('round', 2)
    FieldScreen._sync_tactics_hand_support_visibility(field)

    assert icon.is_visible is False


def test_field_support_visibility_key_tracks_support_ids_without_cache_key_change():
    from game.screens.field_screen import FieldScreen

    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_turn_player_id=1,
        battle_round=1,
        both_battle_moves_ready=False,
        last_battle_result=None,
        game_id=7,
        player_id=1,
        _figures_data_version=1,
    )
    support_ids = set()
    parent = SimpleNamespace(
        request_conquer_figure_confirmation=lambda *args, **kwargs: None,
        _conquer_tactic_cache_key=('same',),
        _conquer_opponent_tactic_cache_key=('same',),
        conquer_active_support_figure_ids=lambda opponent_only=False: set(support_ids),
    )
    figure = SimpleNamespace(id=20, player_id=2, name='Support Soldier')
    icon = SimpleNamespace(figure=figure, is_visible=False)
    field = FieldScreen.__new__(FieldScreen)
    field.game = game
    field.state = SimpleNamespace(parent_screen=parent)
    field.figure_icons = [icon]
    field.cached_all_seeing_eye_status = False
    field._last_tactics_hand_support_visibility_key = ()

    FieldScreen._sync_tactics_hand_support_visibility(field)
    assert icon.is_visible is False

    support_ids.add('20')
    FieldScreen._sync_tactics_hand_support_visibility(field)

    assert icon.is_visible is True


def test_conquer_dim_flags_compare_normalized_figure_ids():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    support_icon = SimpleNamespace(
        figure=SimpleNamespace(id=20),
        conquer_battle_dimmed=True,
    )
    idle_icon = SimpleNamespace(
        figure=SimpleNamespace(id=30),
        conquer_battle_dimmed=False,
    )
    screen.subscreens = {
        'field': SimpleNamespace(figure_icons=[support_icon, idle_icon]),
    }
    screen._is_battle_phase_active = lambda: True
    screen._conquer_battle_involved_figure_ids = lambda: {'20'}

    ConquerGameScreen._update_conquer_battle_dim_flags(screen)

    assert support_icon.conquer_battle_dimmed is False
    assert idle_icon.conquer_battle_dimmed is True


def test_battle_state_poll_infers_confirmed_from_active_turn():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    game = SimpleNamespace(
        battle_confirmed=False,
        battle_turn_player_id=None,
        battle_round=0,
        conquer_resolution_step=0,
    )
    screen.state = SimpleNamespace(game=game)

    ConquerGameScreen._apply_battle_state_result(screen, {
        'success': True,
        'battle_round': 0,
        'battle_turn_player_id': 1,
        'player_tactics': [],
        'opponent_tactics': [],
    })

    assert game.battle_confirmed is True
    assert game.battle_turn_player_id == 1


def test_battle_state_poll_applies_timer_and_active_spells():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    game = SimpleNamespace(
        battle_confirmed=True,
        battle_turn_player_id=1,
        battle_round=0,
        conquer_resolution_step=0,
        cached_active_spells=[],
        _game_data_version=7,
        _figures_data_version=3,
        battle_modifier=[],
    )
    screen.state = SimpleNamespace(game=game)

    active_spell = {
        'id': 9,
        'spell_name': 'Poison',
        'target_figure_id': 44,
        'effect_data': {'power_modifier': -6},
    }
    ConquerGameScreen._apply_battle_state_result(screen, {
        'success': True,
        'battle_round': 0,
        'battle_turn_player_id': 1,
        'player_tactics': [],
        'opponent_tactics': [],
        'conquer_round_deadline_ts': 1234.5,
        'conquer_round_timeout_sec': 60,
        'active_spells': [active_spell],
        'battle_modifier': [{'type': 'Blitzkrieg'}],
    })

    assert game.conquer_round_deadline_ts == 1234.5
    assert game.conquer_round_timeout_sec == 60
    assert game.cached_active_spells == [active_spell]
    assert game.battle_modifier == [{'type': 'Blitzkrieg'}]
    assert game._game_data_version == 8
    assert game._figures_data_version == 4


def test_battle_state_poll_skips_game_version_bump_when_snapshot_is_unchanged():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    active_spell = {
        'id': 9,
        'spell_name': 'Poison',
        'target_figure_id': 44,
        'effect_data': {'power_modifier': -6},
    }
    game = SimpleNamespace(
        battle_confirmed=True,
        battle_turn_player_id=1,
        battle_round=0,
        conquer_resolution_step=0,
        cached_active_spells=[active_spell],
        battle_modifier=[{'type': 'Blitzkrieg'}],
        conquer_round_deadline_ts=1234.5,
        conquer_round_timeout_sec=60,
        _game_data_version=7,
        _figures_data_version=3,
    )
    screen.state = SimpleNamespace(game=game)

    ConquerGameScreen._apply_battle_state_result(screen, {
        'success': True,
        'battle_round': 0,
        'battle_turn_player_id': 1,
        'battle_confirmed': True,
        'player_tactics': [],
        'opponent_tactics': [],
        'conquer_round_deadline_ts': 1234.5,
        'conquer_round_timeout_sec': 60,
        'active_spells': [active_spell],
        'battle_modifier': [{'type': 'Blitzkrieg'}],
        'conquer_resolution_step': 0,
    })

    assert game._game_data_version == 7
    assert game._figures_data_version == 3


def test_active_battle_clears_stale_single_option_auto_action():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    game = SimpleNamespace(
        battle_turn_player_id=1,
        battle_round=0,
        last_battle_result=None,
        action_in_progress=False,
    )
    field = SimpleNamespace(
        defender_selection_mode=True,
        selectable_defender_figure_ids=lambda: [22],
    )
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {'field': field}
    screen.dialogue_box = None
    screen._auto_single_option_pending = (('defender', 22), 0)

    ConquerGameScreen._maybe_auto_advance_single_option_step(screen)

    assert screen._auto_single_option_pending is None


def test_active_battle_sync_clears_stale_defender_modes():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    game = SimpleNamespace(
        battle_turn_player_id=1,
        battle_round=0,
        last_battle_result=None,
    )
    reset_calls = []
    field = SimpleNamespace(
        defender_selection_mode=True,
        conquer_own_defender_mode=True,
        _reset_defender_selectable=lambda: reset_calls.append(True),
    )
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {'field': field}
    screen._auto_single_option_pending = (('defender', 22), 0)

    ConquerGameScreen._sync_conquer_action_modes(screen)

    assert field.defender_selection_mode is False
    assert field.conquer_own_defender_mode is False
    assert screen._auto_single_option_pending is None
    assert len(reset_calls) == 2


def test_no_attacker_sync_clears_stale_defender_modes_and_flags():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    game = SimpleNamespace(
        mode='conquer',
        battle_turn_player_id=None,
        battle_round=0,
        last_battle_result=None,
        advancing_figure_id=None,
        pending_defender_selection=True,
        defender_selection_dialogue_shown=True,
        pending_waiting_for_defender_pick=True,
        waiting_for_defender_pick_shown=True,
        pending_conquer_own_defender_selection=True,
        conquer_own_defender_selection_shown=True,
        civil_war_awaiting_second=True,
        civil_war_defender_second=True,
        civil_war_required_color='offensive',
    )
    reset_calls = []
    field = SimpleNamespace(
        defender_selection_mode=True,
        conquer_own_defender_mode=True,
        _reset_defender_selectable=lambda: reset_calls.append(True),
    )
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {'field': field}
    screen._auto_single_option_pending = (('defender', 22), 0)

    ConquerGameScreen._sync_conquer_action_modes(screen)

    assert field.defender_selection_mode is False
    assert field.conquer_own_defender_mode is False
    assert game.pending_defender_selection is False
    assert game.defender_selection_dialogue_shown is False
    assert game.pending_waiting_for_defender_pick is False
    assert game.waiting_for_defender_pick_shown is False
    assert game.pending_conquer_own_defender_selection is False
    assert game.conquer_own_defender_selection_shown is False
    assert game.civil_war_awaiting_second is False
    assert game.civil_war_defender_second is False
    assert game.civil_war_required_color is None
    assert screen._auto_single_option_pending is None
    assert len(reset_calls) == 2


def test_lane_context_support_ids_normalize_live_payload_ids():
    ConquerGameScreen = _conquer_screen_class()
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        game_id=9,
        player_id='1',
        opponent_player={'id': 2},
        battle_turn_player_id=1,
        battle_round=0,
        last_battle_result=None,
        advancing_player_id=1,
        advancing_figure_id='100',
        advancing_figure_id_2=None,
        defending_figure_id='200',
        defending_figure_id_2=None,
        land_suit_bonus_suit=None,
        land_suit_bonus_value=None,
        battle_skipped_rounds={},
        conquer_tactics=[],
        conquer_resolution_step=0,
        _game_data_version=1,
        _figures_data_version=1,
    )
    ConquerGameScreen, screen = _base_conquer_screen(game)

    def figure(fig_id, player_id, field):
        return SimpleNamespace(
            id=fig_id,
            player_id=player_id,
            suit='red',
            name=f'Figure {fig_id}',
            family=SimpleNamespace(field=field),
            has_deficit=False,
            value=3,
        )

    screen.subscreens['field'].figures = [
        figure(100, 1, 'military'),
        figure(101, 1, 'castle'),
        figure(200, 2, 'military'),
        figure(201, 2, 'castle'),
    ]
    screen._conquer_lane_context_cache_key = None
    screen._conquer_lane_context_fast_cache_key = None
    screen._conquer_lane_context_cache = None

    context = ConquerGameScreen._conquer_lane_context(screen)

    assert context['player_support_ids'] == {101}
    assert context['opponent_support_ids'] == {201}
    assert {str(fig_id) for fig_id in context['involved_ids']} == {
        '100', '101', '200', '201'}


def test_pre_battle_hides_automated_defence_battle_figure_from_duel_lane():
    ConquerGameScreen = _conquer_screen_class()
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        game_id=10,
        player_id=1,
        opponent_player={'id': 2},
        battle_turn_player_id=None,
        battle_round=0,
        last_battle_result=None,
        advancing_player_id=1,
        advancing_figure_id=200,
        advancing_figure_id_2=None,
        defending_figure_id=None,
        defending_figure_id_2=None,
        land_suit_bonus_suit=None,
        land_suit_bonus_value=None,
        battle_skipped_rounds={},
        conquer_tactics=[],
        conquer_resolution_step=0,
        _game_data_version=1,
        _figures_data_version=1,
    )
    ConquerGameScreen, screen = _base_conquer_screen(game)
    screen.subscreens['field'].figures = [SimpleNamespace(
        id=200,
        player_id=2,
        suit='red',
        name='Automated Guard',
        family=SimpleNamespace(field='military'),
        has_deficit=False,
        value=4,
    )]
    screen._current_conquer_tactics = lambda: []
    screen._current_conquer_opponent_tactics = lambda: []

    context = ConquerGameScreen._conquer_lane_context(screen)

    assert context['player_figures'] == []
    assert context['opponent_figures'] == []
    assert context['involved_ids'] == set()


def test_duel_lane_does_not_mirror_opponent_figure_as_player_fighter():
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        player_id=1,
        opponent_player={'id': 2},
        battle_turn_player_id=1,
        battle_round=1,
        last_battle_result=None,
        advancing_player_id=1,
        advancing_figure_id=200,
        advancing_figure_id_2=None,
        defending_figure_id=None,
        defending_figure_id_2=None,
    )
    ConquerGameScreen, screen = _base_conquer_screen(game)
    opponent_figure = SimpleNamespace(id=200, player_id=2)
    screen.subscreens['field'].figures = [opponent_figure]

    player_figures, opponent_figures = ConquerGameScreen._conquer_lane_figures(screen)

    assert player_figures == []
    assert opponent_figures == []


def _minimal_update_screen(game):
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(
        screen='conquer_game',
        subscreen='field',
        game=game,
    )
    screen.subscreens = {'field': SimpleNamespace(update=lambda _game: None)}
    screen.update_interval = 0
    screen.last_update_time = 0
    screen._refresh_conquer_tab_locks = lambda: None
    screen._request_battle_state_poll = lambda force=False: None
    screen._check_battle_cycle_reset = lambda: None
    screen._sync_conquer_action_modes = lambda: None
    screen._auto_route_conquer_once = lambda: None
    screen._sync_pending_confirmation_state = lambda: None
    screen._enforce_battle_shop_during_moves = lambda: None
    screen._maybe_auto_trigger_finish_battle = lambda: None
    screen._maybe_auto_advance_single_option_step = lambda: None
    return ConquerGameScreen, screen


def test_active_tactics_hand_battle_skips_broad_game_poll():
    calls = []
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        battle_confirmed=False,
        battle_turn_player_id=1,
        battle_round=1,
        last_battle_result=None,
        game_over=False,
        drain_pending_start_turn=lambda: None,
    )
    ConquerGameScreen, screen = _minimal_update_screen(game)
    screen.update_game = lambda: calls.append('full_poll')

    ConquerGameScreen.update(screen, [])

    assert calls == []


def test_lane_context_fast_key_tracks_tactic_cache_payload():
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        game_id=7,
        player_id=1,
        _game_data_version=1,
        _figures_data_version=1,
        conquer_tactics=[],
        battle_turn_player_id=1,
        battle_round=1,
        last_battle_result=None,
        advancing_player_id=1,
        advancing_figure_id=10,
        advancing_figure_id_2=None,
        defending_figure_id=20,
        defending_figure_id_2=None,
        land_suit_bonus_suit=None,
        land_suit_bonus_value=None,
        conquer_resolution_step=0,
    )
    ConquerGameScreen, screen = _base_conquer_screen(game)
    screen.subscreens['field'] = SimpleNamespace(figures=[])
    screen._conquer_tactic_cache_key = ('tactics', 7, 1, 1, 1, False, 0)
    screen._conquer_opponent_tactic_cache_key = screen._conquer_tactic_cache_key
    screen._conquer_tactic_cache = [
        {'id': 1, 'player_id': 1, 'status': 'played', 'played_round': 0},
    ]
    screen._conquer_opponent_tactic_cache = []

    first = ConquerGameScreen._conquer_lane_context_fast_key(screen)

    screen._conquer_tactic_cache = [
        {
            'id': 1,
            'player_id': 1,
            'status': 'played',
            'played_round': 0,
            'call_figure_id': 30,
        },
    ]
    second = ConquerGameScreen._conquer_lane_context_fast_key(screen)

    assert second != first


def test_conquer_result_state_still_allows_broad_game_poll():
    calls = []
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_turn_player_id=None,
        battle_round=3,
        last_battle_result={'winner': 1},
        game_over=False,
        drain_pending_start_turn=lambda: None,
    )
    ConquerGameScreen, screen = _minimal_update_screen(game)
    screen.update_game = lambda: calls.append('full_poll')

    ConquerGameScreen.update(screen, [])

    assert calls == ['full_poll']


class TestGameplayScreenRouting:
    def test_conquer_games_route_to_conquer_game_screen(self):
        from game.core.screen_routing import gameplay_screen_for

        assert gameplay_screen_for(SimpleNamespace(mode='conquer')) == 'conquer_game'

    def test_duel_games_route_to_duel_game_screen(self):
        from game.core.screen_routing import gameplay_screen_for

        assert gameplay_screen_for(SimpleNamespace(mode='duel')) == 'game'
        assert gameplay_screen_for(SimpleNamespace()) == 'game'

    def test_duel_game_screen_redirects_accidental_conquer_game(self):
        GameScreen = _game_screen_class()
        screen = GameScreen.__new__(GameScreen)
        screen.state = SimpleNamespace(
            screen='game',
            game=SimpleNamespace(mode='conquer'),
        )

        assert GameScreen._ensure_duel_screen_game(screen) is False
        assert screen.state.screen == 'conquer_game'

    def test_conquer_game_screen_redirects_accidental_duel_game(self):
        ConquerGameScreen, screen = _base_conquer_screen(
            SimpleNamespace(mode='duel'))

        assert ConquerGameScreen._ensure_conquer_screen_game(screen) is False
        assert screen.state.screen == 'game'

    def test_game_screens_set_active_parent_on_enter(self):
        GameScreen = _game_screen_class()
        duel = GameScreen.__new__(GameScreen)
        duel.state = SimpleNamespace(
            screen='game',
            game=SimpleNamespace(mode='duel'),
        )

        GameScreen.on_enter(duel)
        assert duel.state.parent_screen is duel

        ConquerGameScreen, conquer = _base_conquer_screen(
            SimpleNamespace(mode='conquer'))
        ConquerGameScreen.on_enter(conquer)

        assert conquer.state.parent_screen is conquer
        assert conquer.state.subscreen == 'field'


class TestConquerGameShell:
    def test_initializes_only_three_conquer_tab_buttons(self):
        from config import settings

        ConquerGameScreen = _conquer_screen_class()
        screen = ConquerGameScreen.__new__(ConquerGameScreen)
        screen.window = pygame.Surface((1200, 800))
        screen.state = SimpleNamespace(game=SimpleNamespace(turn=True), subscreen='field')

        ConquerGameScreen.initialize_buttons(screen)

        names = [button.name for button in screen.game_buttons]
        # Battle-shop is no longer surfaced as a tab — the user is auto-routed
        # there during the moves phase by the timeline panel.
        assert names == [
            'conquer_view_field',
            'conquer_view_battle',
        ]
        assert all('build' not in name for name in names)
        assert all('spell' not in name for name in names)
        assert all('log' not in name for name in names)
        assert screen.battle_button.locked is False
        assert screen.field_button.x == screen.battle_button.x
        assert screen.field_button.y < screen.battle_button.y
        sub_x, _sub_y = ConquerGameScreen._conquer_subscreen_origin(screen)
        assert screen.field_button.x + settings.FIELD_BUTTON_WIDTH < sub_x

    def test_normalizes_hidden_duel_subscreen_to_field(self):
        ConquerGameScreen, screen = _base_conquer_screen()
        screen.state.subscreen = 'build_figure'

        ConquerGameScreen._normalize_conquer_subscreen(screen)

        assert screen.state.subscreen == 'field'

    def test_tactics_hand_always_normalizes_to_unified_field_canvas(self):
        game = SimpleNamespace(mode='conquer', conquer_move_model='tactics_hand')
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'battle'

        ConquerGameScreen._normalize_conquer_subscreen(screen)

        assert screen.state.subscreen == 'field'
        assert ConquerGameScreen._conquer_nav_buttons(screen) == []

    def test_tactics_hand_getters_do_not_start_polling(self):
        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            game_id=44,
            player_id=10,
            battle_turn_player_id=10,
            battle_round=1,
            last_battle_result=None,
            conquer_resolution_step=0,
            conquer_tactics=[
                {'id': 1, 'player_id': 10, 'family_name': 'Dagger', 'status': 'available'},
                {'id': 2, 'player_id': 20, 'family_name': 'Wall', 'status': 'available'},
            ],
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen._conquer_tactic_cache = []
        screen._conquer_opponent_tactic_cache = []
        screen._conquer_tactic_cache_key = None
        screen._conquer_opponent_tactic_cache_key = None
        calls = []
        screen._request_battle_state_poll = lambda force=False: calls.append(force)

        player_tactics = ConquerGameScreen._current_conquer_tactics(screen)
        opponent_tactics = ConquerGameScreen._current_conquer_opponent_tactics(screen)

        assert calls == []
        assert [move['id'] for move in player_tactics] == [1]
        assert [move['id'] for move in opponent_tactics] == [2]
        assert opponent_tactics[0]['played_round'] is None

    def test_lane_context_reuses_support_graph_for_same_snapshot(self):
        ConquerGameScreen, screen = _base_conquer_screen(SimpleNamespace(mode='conquer'))
        screen._conquer_lane_context_cache_key = None
        screen._conquer_lane_context_fast_cache_key = None
        screen._conquer_lane_context_cache = None
        screen._conquer_tactic_power_cache_key = None
        screen._conquer_tactic_power_cache = {}
        key_calls = []
        screen._conquer_lane_context_fast_key = lambda: ('fast', 1)
        screen._conquer_lane_context_key = lambda: key_calls.append(True) or ('battle', 1)
        screen._conquer_lane_figures = lambda: (['player_fig'], ['opp_fig'])
        screen._conquer_lane_played_tactics = lambda: ([None, None, None], [None, None, None])
        calls = []

        def support_entries(player_figures, opponent_figures, *, is_player, played_slots=None):
            calls.append((tuple(player_figures), tuple(opponent_figures), is_player, played_slots is not None))
            return [{
                'figure': SimpleNamespace(id=1 if is_player else 2),
                'source_figure_ids': [10 if is_player else 20],
            }]

        screen._conquer_lane_support_entries = support_entries

        first = ConquerGameScreen._conquer_lane_context(screen)
        second = ConquerGameScreen._conquer_lane_context(screen)

        assert first is second
        assert len(key_calls) == 1
        assert len(calls) == 2
        assert calls == [
            (('player_fig',), ('opp_fig',), True, True),
            (('player_fig',), ('opp_fig',), False, True),
        ]
        assert first['player_support_ids'] == {1, 10}
        assert first['opponent_support_ids'] == {2, 20}
        assert {1, 2, 10, 20}.issubset(first['involved_ids'])

    def test_conquer_subscreen_origin_is_centered_below_header(self):
        from config import settings

        ConquerGameScreen, screen = _base_conquer_screen()

        x, y = ConquerGameScreen._conquer_subscreen_origin(screen)

        assert x == (settings.SCREEN_WIDTH - settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH) // 2
        assert y > int(settings.SCREEN_HEIGHT * ConquerGameScreen.HEADER_H_FACTOR)
        assert y > settings.SUB_SCREEN_Y

    def test_auto_routes_to_field_once_for_required_field_action(self):
        game = SimpleNamespace(
            mode='conquer',
            pending_conquer_prelude_target=True,
            pending_spell_id=99,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'battle'

        ConquerGameScreen._auto_route_conquer_once(screen)
        assert screen.state.subscreen == 'field'

        screen.state.subscreen = 'battle'
        ConquerGameScreen._auto_route_conquer_once(screen)
        assert screen.state.subscreen == 'battle'

    def test_auto_routes_to_battle_shop_once_for_move_confirmation(self):
        # The auto_route helper itself does not move the user to the
        # battle_shop subscreen anymore — that is handled by
        # ``_enforce_battle_shop_during_moves`` so the user is forced there
        # during the moves phase.
        game = SimpleNamespace(
            mode='conquer',
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            battle_confirmed=False,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.battle_button = SimpleNamespace(locked=False)
        screen.state.subscreen = 'field'
        screen._conquer_left_battle_shop_at = 0
        screen.BATTLE_SHOP_SNAPBACK_MS = 0  # snap immediately for the test.

        ConquerGameScreen._enforce_battle_shop_during_moves(screen)
        # First call records the timestamp.  Second call snaps back.
        ConquerGameScreen._enforce_battle_shop_during_moves(screen)

        assert screen.state.subscreen == 'battle_shop'

    def test_auto_routes_to_battle_when_battle_has_started(self):
        game = SimpleNamespace(
            mode='conquer',
            battle_confirmed=True,
            battle_turn_player_id=20,
            battle_round=1,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'field'

        ConquerGameScreen._auto_route_conquer_once(screen)

        assert screen.state.subscreen == 'battle'

    def test_auto_routes_tactics_hand_battle_to_field(self):
        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=1,
            player_id=42,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'battle'

        ConquerGameScreen._auto_route_conquer_once(screen)

        assert screen.state.subscreen == 'field'

    def test_attention_counts_mark_required_tabs(self):
        game = SimpleNamespace(
            mode='conquer',
            pending_forced_advance=True,
            advancing_figure_id=None,
            battle_confirmed=True,
            battle_turn_player_id=20,
            pending_conquer_prelude_target=False,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            civil_war_awaiting_second=False,
            civil_war_defender_second=False,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)

        counts = ConquerGameScreen._conquer_attention_counts(screen)

        # battle_shop no longer has a dedicated tab — its attention is
        # surfaced via the timeline panel + auto-routing instead.
        assert counts == {'field': 1, 'battle': 1}

    def test_attention_counts_keep_tactics_hand_battle_on_field(self):
        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=20,
            pending_conquer_prelude_target=False,
            pending_forced_advance=False,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            civil_war_awaiting_second=False,
            civil_war_defender_second=False,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)

        counts = ConquerGameScreen._conquer_attention_counts(screen)

        assert counts == {'field': 1, 'battle': 0}

    def test_confirming_figure_selection_acknowledges_selection_step(self):
        ConquerGameScreen, screen = _base_conquer_screen()
        screen._conquer_pending_confirmation = {'kind': 'advance'}
        screen._conquer_acknowledged_step_kinds = set()
        screen._conquer_timeline_step_started_at = {}
        screen.subscreens['field'] = SimpleNamespace(
            confirm_pending_advance=lambda: True)

        handled = ConquerGameScreen._handle_conquer_objective_action(
            screen, 'confirm')

        assert handled is True
        assert 'attacker' in screen._conquer_acknowledged_step_kinds

    def test_auto_confirms_conquer_moves_when_shop_has_no_changes(self, monkeypatch):
        game = SimpleNamespace(
            mode='conquer',
            game_id=12,
            player_id=3,
            battle_confirmed=True,
            battle_turn_player_id=None,
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            _game_data_version=1,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'field'
        screen.subscreens['battle_shop'] = SimpleNamespace(
            bought_moves=[{'id': 1}, {'id': 2}, {'id': 3}],
            card_source=None,
            game=game,
            _load_bought_moves=lambda: None,
            _can_ready_for_battle=lambda: True,
            has_available_battle_move_changes=lambda: False,
        )

        monkeypatch.setattr(
            'utils.battle_shop_service.confirm_battle_moves',
            lambda game_id, player_id: {'success': True, 'both_ready': True},
        )

        handled = ConquerGameScreen._auto_confirm_conquer_battle_moves_if_no_changes(screen)

        assert handled is True
        assert screen.state.subscreen == 'battle'
        assert game.battle_moves_phase is False
        assert game.both_battle_moves_ready is True

    def test_keeps_conquer_shop_when_move_changes_exist(self, monkeypatch):
        game = SimpleNamespace(
            mode='conquer',
            game_id=12,
            player_id=3,
            battle_confirmed=True,
            battle_turn_player_id=None,
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            _game_data_version=1,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.battle_button = SimpleNamespace(locked=False)
        screen.subscreens['battle_shop'] = SimpleNamespace(
            bought_moves=[{'id': 1}, {'id': 2}, {'id': 3}],
            card_source=None,
            game=game,
            _load_bought_moves=lambda: None,
            _can_ready_for_battle=lambda: True,
            has_available_battle_move_changes=lambda: True,
        )
        called = []
        monkeypatch.setattr(
            'utils.battle_shop_service.confirm_battle_moves',
            lambda game_id, player_id: called.append((game_id, player_id)),
        )

        handled = ConquerGameScreen._auto_confirm_conquer_battle_moves_if_no_changes(screen)

        assert handled is False
        assert called == []

    def test_battle_shop_reloads_moves_when_game_data_version_changes(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        game = SimpleNamespace(
            game_id=12,
            player_id=3,
            _game_data_version=2,
            battle_moves_phase=True,
            battle_confirmed=True,
        )
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.game = game
        screen.mode = 'duel'
        screen.card_source = SimpleNamespace(game=game)
        screen.buttons = []
        screen.scroll_text_list_shifter = None
        screen._loaded_game_key = (12, 3)
        screen._loaded_bought_moves_key = (12, 3, 1)
        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        screen._battle_moves_confirmed = False
        screen._waiting_for_opponent = False
        screen.confirm_button = SimpleNamespace(disabled=True, update=lambda: None)
        screen.ready_button = SimpleNamespace(disabled=True, update=lambda: None)
        screen.move_family_buttons = []
        screen._can_ready_for_battle = lambda: True
        screen._update_icon_states = lambda: None
        figure_loads = []
        screen._load_player_figures = lambda: figure_loads.append('figures')
        move_loads = []

        def _reload_moves():
            move_loads.append('moves')
            screen.bought_moves = [{'id': 1}, {'id': 2}]
            screen._loaded_game_key = BattleShopScreen._game_identity_key(screen, game)
            screen._loaded_bought_moves_key = BattleShopScreen._bought_moves_cache_key(screen, game)

        screen._load_bought_moves = _reload_moves

        BattleShopScreen.update(screen, game)

        assert move_loads == ['moves']
        assert figure_loads == []
        assert screen.confirm_button.disabled is False

    def test_battle_shop_config_ready_requires_three_moves(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        game = SimpleNamespace(
            game_id=None,
            player_id=None,
            battle_moves_phase=False,
            battle_confirmed=False,
        )
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.game = game
        screen.mode = 'conquer'
        screen.card_source = SimpleNamespace(game=game)
        screen.buttons = []
        screen.scroll_text_list_shifter = None
        screen._loaded_game_key = (None, None)
        screen._loaded_bought_moves_key = (None, None)
        screen._battle_moves_confirmed = False
        screen._waiting_for_opponent = False
        screen.confirm_button = SimpleNamespace(disabled=False, update=lambda: None)
        screen.ready_button = SimpleNamespace(
            disabled=False, active=True, update=lambda: None)
        screen.move_family_buttons = []
        screen._update_icon_states = lambda: None

        screen.bought_moves = [{'id': 1}, {'id': 2}]
        BattleShopScreen.update(screen, game)

        assert screen.ready_button.disabled is True
        assert screen.ready_button.active is False

        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        BattleShopScreen.update(screen, game)

        assert screen.ready_button.disabled is False
        assert screen.ready_button.active is True

    def test_battle_shop_config_ready_hover_changes_glow_state(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        class HoverButton:
            def __init__(self):
                self.disabled = False
                self.active = True
                self.hovered = False

            def update(self):
                self.hovered = True

        game = SimpleNamespace(
            game_id=None,
            player_id=None,
            battle_moves_phase=False,
            battle_confirmed=False,
        )
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.game = game
        screen.mode = 'conquer'
        screen.card_source = SimpleNamespace(game=game)
        screen.buttons = []
        screen.scroll_text_list_shifter = None
        screen._loaded_game_key = (None, None)
        screen._loaded_bought_moves_key = (None, None)
        screen._battle_moves_confirmed = False
        screen._waiting_for_opponent = False
        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        screen.confirm_button = SimpleNamespace(disabled=False, update=lambda: None)
        screen.ready_button = HoverButton()
        screen.move_family_buttons = []
        screen._update_icon_states = lambda: None

        BattleShopScreen.update(screen, game)

        assert screen.ready_button.disabled is False
        assert screen.ready_button.hovered is True
        assert screen.ready_button.active is False

    def test_battle_shop_config_ready_closes_subscreen_when_full(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        called = []
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.mode = 'defence_draft'
        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        screen._on_done = lambda: called.append('closed')

        handled = BattleShopScreen._on_config_ready(screen)

        assert handled is True
        assert called == ['closed']

        screen.bought_moves = [{'id': 1}, {'id': 2}]
        called.clear()

        handled = BattleShopScreen._on_config_ready(screen)

        assert handled is False
        assert called == []

    def test_battle_shop_config_ready_closes_on_mouseup_not_mousedown(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        called = []
        slot_clicks = []
        ready_rect = pygame.Rect(20, 20, 90, 42)
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.mode = 'conquer'
        screen.game = SimpleNamespace(
            game_over=False,
            battle_moves_phase=False,
            battle_confirmed=False,
        )
        screen.scroll_text_list_shifter = None
        screen.battle_move_detail_box = None
        screen.dialogue_box = None
        screen.move_family_buttons = []
        screen.confirm_button = SimpleNamespace(collide=lambda: False, disabled=True)
        screen.ready_button = SimpleNamespace(disabled=False, rect=ready_rect)
        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        screen._config_ready_pressed = False
        screen._on_done = lambda: called.append('closed')
        screen._close_rect = pygame.Rect(500, 500, 20, 20)
        screen._handle_slot_click = lambda event: slot_clicks.append(event.pos)

        BattleShopScreen.handle_events(screen, [pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=ready_rect.center)])

        assert called == []
        assert slot_clicks == []
        assert screen._config_ready_pressed is True

        BattleShopScreen.handle_events(screen, [pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1, pos=ready_rect.center)])

        assert called == ['closed']
        assert screen._config_ready_pressed is False

    def test_invader_swap_own_defender_mode_uses_own_selectable_update(self):
        game = SimpleNamespace(
            mode='conquer',
            player_id=1,
            invader=True,
            advancing_figure_id=10,
            advancing_player_id=2,
            pending_defender_selection=False,
            defender_selection_dialogue_shown=False,
            pending_conquer_own_defender_selection=False,
            conquer_own_defender_selection_shown=False,
            civil_war_defender_second=True,
            cached_active_spells=[{
                'spell_name': 'Invader Swap',
                'effect_data': {
                    'conquer_invader_swap': True,
                    'old_invader_id': 1,
                },
            }],
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        calls = []
        field = SimpleNamespace(
            defender_selection_mode=False,
            conquer_own_defender_mode=False,
            _update_defender_selectable=lambda: calls.append('opponent'),
            _update_conquer_own_defender_selectable=lambda: calls.append('own'),
            _reset_defender_selectable=lambda: calls.append('reset'),
        )
        screen.subscreens['field'] = field

        ConquerGameScreen._sync_conquer_action_modes(screen)

        assert field.conquer_own_defender_mode is True
        assert calls == ['own']

    def test_own_defender_selectability_excludes_first_civil_war_pick(self):
        from game.screens.field_screen import FieldScreen

        def figure(fig_id, *, player_id=1, color='offensive', field='village'):
            return SimpleNamespace(
                id=fig_id,
                player_id=player_id,
                name=f'Figure {fig_id}',
                family=SimpleNamespace(color=color, field=field),
            )

        first = figure(20)
        second = figure(21)
        wrong_color = figure(22, color='defensive')
        opponent = figure(23, player_id=2)
        icons = [
            SimpleNamespace(
                figure=f,
                has_deficit=False,
                defender_selectable=None,
                in_defender_selection_mode=False,
            )
            for f in (first, second, wrong_color, opponent)
        ]
        field = FieldScreen.__new__(FieldScreen)
        field.game = SimpleNamespace(
            player_id=1,
            battle_modifier=[{'type': 'Civil War'}],
            defending_figure_id=20,
            civil_war_defender_second=True,
            civil_war_required_color='offensive',
        )
        field.figure_icons = icons

        FieldScreen._update_conquer_own_defender_selectable(field)

        assert [icon.defender_selectable for icon in icons] == [False, True, False, False]

    def test_own_defender_selectability_includes_fortress_and_alternates(self):
        from game.screens.field_screen import FieldScreen

        fortress = SimpleNamespace(
            id=30,
            player_id=1,
            name='Stone Fortress',
            family=SimpleNamespace(color='defensive', field='military'),
            cannot_attack=True,
            must_be_attacked=True,
        )
        normal = SimpleNamespace(
            id=31,
            player_id=1,
            name='Himalaya King',
            family=SimpleNamespace(color='defensive', field='castle'),
        )
        deficit_fortress = SimpleNamespace(
            id=32,
            player_id=1,
            name='Deficit Fortress',
            family=SimpleNamespace(color='defensive', field='military'),
            cannot_attack=True,
            must_be_attacked=True,
        )
        opponent = SimpleNamespace(
            id=33,
            player_id=2,
            name='Opponent',
            family=SimpleNamespace(color='offensive', field='village'),
        )
        icons = [
            SimpleNamespace(
                figure=figure,
                has_deficit=(figure.id == 32),
                defender_selectable=None,
                in_defender_selection_mode=False,
            )
            for figure in (fortress, normal, deficit_fortress, opponent)
        ]
        field = FieldScreen.__new__(FieldScreen)
        field.game = SimpleNamespace(
            player_id=1,
            battle_modifier=[],
            defending_figure_id=None,
            civil_war_defender_second=False,
            civil_war_required_color=None,
        )
        field.figure_icons = icons

        FieldScreen._update_conquer_own_defender_selectable(field)

        assert [icon.defender_selectable for icon in icons] == [True, True, False, False]

    def test_conquer_selection_greys_non_village_forced_advance_under_peasant_war(self):
        from game.screens.field_screen import FieldScreen

        def figure(fig_id, *, player_id=1, field='village'):
            return SimpleNamespace(
                id=fig_id,
                player_id=player_id,
                name=f'Figure {fig_id}',
                family=SimpleNamespace(color='offensive', field=field),
            )

        village = figure(40)
        military = figure(41, field='military')
        opponent = figure(42, player_id=2)
        deficit = figure(43)
        icons = [
            SimpleNamespace(figure=village, has_deficit=False),
            SimpleNamespace(figure=military, has_deficit=False),
            SimpleNamespace(figure=opponent, has_deficit=False),
            SimpleNamespace(figure=deficit, has_deficit=True),
        ]
        field = FieldScreen.__new__(FieldScreen)
        field.game = SimpleNamespace(
            player_id=1,
            battle_modifier=[{'type': 'Peasant War'}],
            pending_forced_advance=True,
            forced_advance_dialogue_shown=True,
            advancing_figure_id=None,
            resting_figure_ids=[],
        )
        field.state = SimpleNamespace(pending_conquer_prelude_target=None)
        field.figure_icons = icons
        field.figures = [village, military, opponent, deficit]
        field.defender_selection_mode = False
        field.conquer_own_defender_mode = False
        field._is_conquer_selection_active = lambda: True

        FieldScreen._sync_conquer_selection_icon_states(field)

        assert [icon.conquer_selection_selectable for icon in icons] == [
            True, False, False, False,
        ]

    def test_opponent_defender_selectability_ignores_stale_cache_under_peasant_war(self):
        from game.screens.field_screen import FieldScreen

        village = SimpleNamespace(
            id=50,
            player_id=2,
            name='Village Defender',
            family=SimpleNamespace(color='offensive', field='village'),
        )
        military = SimpleNamespace(
            id=51,
            player_id=2,
            name='Military Defender',
            family=SimpleNamespace(color='offensive', field='military'),
        )
        icons = [
            SimpleNamespace(figure=village, defender_selectable=True),
            SimpleNamespace(figure=military, defender_selectable=True),
        ]
        field = FieldScreen.__new__(FieldScreen)
        field.game = SimpleNamespace(
            player_id=1,
            battle_modifier=[{'type': 'Peasant War'}],
            advancing_figure_id=99,
            civil_war_defender_second=False,
            civil_war_required_color=None,
        )
        field.figures = [village, military]
        field.figure_icons = icons
        field.defender_selection_mode = True
        field.conquer_own_defender_mode = False
        field._is_conquer_selection_active = lambda: True

        FieldScreen._sync_conquer_selection_icon_states(field)

        assert FieldScreen._icon_is_selectable_for_current_mode(field, icons[0]) is True
        assert FieldScreen._icon_is_selectable_for_current_mode(field, icons[1]) is False
        assert FieldScreen.selectable_defender_figure_ids(field) == [50]
        assert [icon.conquer_selection_selectable for icon in icons] == [True, False]

    def test_conquer_prelude_selection_visuals_honor_valid_target_ids(self):
        from game.screens.field_screen import FieldScreen

        valid = SimpleNamespace(
            id=60,
            player_id=1,
            name='Valid',
            family=SimpleNamespace(color='offensive', field='village'),
        )
        invalid = SimpleNamespace(
            id=61,
            player_id=1,
            name='Invalid',
            family=SimpleNamespace(color='offensive', field='village'),
        )
        icons = [
            SimpleNamespace(figure=valid),
            SimpleNamespace(figure=invalid),
        ]
        field = FieldScreen.__new__(FieldScreen)
        field.game = SimpleNamespace(player_id=1, battle_modifier=[])
        field.state = SimpleNamespace(
            pending_conquer_prelude_target={
                'target_scope': 'own',
                'valid_target_ids': ['60'],
            }
        )
        field.figure_icons = icons
        field.figures = [valid, invalid]
        field.defender_selection_mode = False
        field.conquer_own_defender_mode = False
        field._is_conquer_selection_active = lambda: True

        FieldScreen._sync_conquer_selection_icon_states(field)

        assert [icon.conquer_selection_selectable for icon in icons] == [True, False]

    def test_battle_result_attack_failed_is_shown_once(self):
        from game.screens.battle_screen import BattleScreen

        game = SimpleNamespace(
            player_id=1,
            invader=True,
            cached_active_spells=[],
            _conquer_result_dialogue_shown=False,
        )
        battle = BattleScreen.__new__(BattleScreen)
        battle.game = game
        battle.window = pygame.Surface((100, 100))
        shown = []

        def fake_dialogue(message, actions, icon, title, images=None):
            shown.append({
                'message': message,
                'actions': actions,
                'icon': icon,
                'title': title,
                'images': images,
            })

        battle.make_dialogue_box = fake_dialogue

        result = {
            'attacker_won': False,
            'conquer_result': 'defender_won',
            'conquer_attacker_player_id': 1,
        }

        BattleScreen._handle_conquer_end(battle, result)
        BattleScreen._handle_conquer_end(battle, result)

        assert len(shown) == 1
        assert shown[0]['title'] == 'Attack Failed'
        assert 'defender held their ground' not in shown[0]['message'].lower()
        assert game._conquer_result_dialogue_shown is True


class TestConquerSubscreenLayout:
    def test_field_compartments_translate_with_conquer_subscreen_origin(self):
        from config import settings
        from game.screens.field_screen import FieldScreen

        ConquerGameScreen, conquer = _base_conquer_screen()
        sub_x, sub_y = ConquerGameScreen._conquer_subscreen_origin(conquer)

        field = FieldScreen.__new__(FieldScreen)
        field._layout_offset_x = sub_x - settings.SUB_SCREEN_X
        field._layout_offset_y = sub_y - settings.SUB_SCREEN_Y

        FieldScreen.init_field_compartments(field)

        assert field.compartments['self']['castle'].topleft == (
            settings.FIELD_SELF_X + field._layout_offset_x,
            settings.FIELD_Y + field._layout_offset_y,
        )

        bg_rect = pygame.Rect(
            sub_x, sub_y,
            settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH,
            settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT,
        )
        all_compartments = [
            rect
            for player in field.compartments.values()
            for rect in player.values()
        ]
        layout_rect = all_compartments[0].unionall(all_compartments[1:])

        assert bg_rect.contains(layout_rect)

    def test_tactics_hand_field_uses_unified_battlefield_columns(self):
        from config import settings
        from game.components.conquer_layout import compute_conquer_layout
        from game.screens.field_screen import FieldScreen

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_round=0,
            battle_turn_player_id=None,
            last_battle_result=None,
        )
        field = FieldScreen.__new__(FieldScreen)
        field.game = game
        field._layout_offset_x = 0
        field._layout_offset_y = 0

        FieldScreen.init_field_compartments(field)

        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode='pre_battle',
        )
        assert field.compartments['self']['castle'] == pygame.Rect(
            layout.battlefield.columns.you_castle)
        assert field.compartments['opponent']['castle'] == pygame.Rect(
            layout.battlefield.columns.opp_castle)
        assert layout.tactics_rail.rect[0] + layout.tactics_rail.rect[2] <= layout.battlefield.rect[0]

    def test_tactics_hand_battle_field_identifies_fighters_and_sources(self):
        from game.screens.field_screen import FieldScreen

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=1,
            battle_round=1,
            player_id=1,
            advancing_figure_id=10,
            advancing_figure_id_2=None,
            defending_figure_id=20,
            defending_figure_id_2=None,
            last_battle_result=None,
            conquer_tactics=[{
                'status': 'played',
                'played_round': 0,
                'call_figure_id': 30,
            }],
        )
        field = FieldScreen.__new__(FieldScreen)
        field.game = game
        field.state = SimpleNamespace(parent_screen=None)

        attacker = SimpleNamespace(id=10, player_id=1)
        defender = SimpleNamespace(id=20, player_id=2)
        called = SimpleNamespace(id=30, player_id=1)
        support = SimpleNamespace(id=40, player_id=1, buffs_allies=True)
        plain = SimpleNamespace(id=50, player_id=1)

        assert FieldScreen._is_tactics_hand_battle_fighter(field, attacker) is True
        assert FieldScreen._is_tactics_hand_battle_fighter(field, defender) is True
        # Persistent 'called' ring was retired — the support lane already
        # surfaces called figures, so the field icon no longer rings them.
        assert FieldScreen._conquer_battle_context_kind(field, called) is None
        assert FieldScreen._conquer_battle_context_kind(field, support) is None
        assert FieldScreen._conquer_battle_context_kind(field, plain) is None

    def test_tactics_hand_battle_field_identifies_preview_called_source(self):
        from game.screens.field_screen import FieldScreen

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=1,
            battle_round=1,
            player_id=1,
            advancing_figure_id=10,
            defending_figure_id=20,
            last_battle_result=None,
            conquer_tactics=[],
        )
        preview = {
            'status': 'available',
            'played_round': None,
            'call_figure_id': 60,
        }
        parent = SimpleNamespace(
            request_conquer_figure_confirmation=lambda *_args, **_kwargs: None,
            _tactics_rail=SimpleNamespace(preview_move=lambda: preview),
        )
        field = FieldScreen.__new__(FieldScreen)
        field.game = game
        field.state = SimpleNamespace(parent_screen=parent)

        source = SimpleNamespace(id=60, player_id=1)

        assert FieldScreen._conquer_battle_context_kind(field, source) == 'preview'

    def test_tactics_hand_battle_context_overlay_draws_rings(self):
        from config import settings
        from game.screens.field_screen import FieldScreen

        window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        window.fill((0, 0, 0))
        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=1,
            battle_round=1,
            player_id=1,
            advancing_figure_id=10,
            defending_figure_id=20,
            last_battle_result=None,
            conquer_tactics=[],
        )
        field = FieldScreen.__new__(FieldScreen)
        field.window = window
        field.game = game
        support = SimpleNamespace(id=40, player_id=1, buffs_allies=True)

        class Parent:
            def request_conquer_figure_confirmation(self):
                return None

            def _conquer_lane_figures(self):
                return [], []

            def _conquer_lane_support_entries(
                    self, _player_figures, _opponent_figures, *, is_player):
                if is_player:
                    return [{
                        'kind': 'buffs_allies',
                        'label': 'Buff',
                        'value': '+4',
                        'figure': support,
                    }]
                return []

        field.state = SimpleNamespace(parent_screen=Parent())
        icon = SimpleNamespace(figure=support)
        field._conquer_hover_source_figure_id = support.id

        FieldScreen._draw_tactics_hand_battle_context_overlays(
            field,
            [(icon, 400, 400)],
        )

        radius = int(settings.FRAME_FIGURE_SCALE * settings.FIGURE_ICON_HEIGHT * 0.56)
        sample = pygame.Rect(400 - radius - 16, 400 - radius - 16,
                             (radius + 16) * 2, (radius + 16) * 2)
        has_ring_pixel = False
        for x in range(sample.left, sample.right, 4):
            for y in range(sample.top, sample.bottom, 4):
                if window.get_at((x, y))[:3] != (0, 0, 0):
                    has_ring_pixel = True
                    break
            if has_ring_pixel:
                break
        assert has_ring_pixel is True

    def test_field_compartments_keep_duel_coordinates_at_default_origin(self):
        from config import settings
        from game.screens.field_screen import FieldScreen

        field = FieldScreen.__new__(FieldScreen)
        field._layout_offset_x = 0
        field._layout_offset_y = 0

        FieldScreen.init_field_compartments(field)

        assert field.compartments['self']['castle'].topleft == (
            settings.FIELD_SELF_X,
            settings.FIELD_Y,
        )

    def test_battle_panels_translate_with_conquer_subscreen_origin(self):
        from config import settings
        from game.screens.battle_screen import BattleScreen

        ConquerGameScreen, conquer = _base_conquer_screen()
        sub_x, sub_y = ConquerGameScreen._conquer_subscreen_origin(conquer)

        battle = BattleScreen.__new__(BattleScreen)
        battle._layout_offset_x = sub_x - settings.SUB_SCREEN_X
        battle._layout_offset_y = sub_y - settings.SUB_SCREEN_Y

        bg_rect = pygame.Rect(
            sub_x, sub_y,
            settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH,
            settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT,
        )

        panel_rects = [
            BattleScreen._battle_panel_rect(battle),
            BattleScreen._figures_panel_rect(battle),
            BattleScreen._rounds_panel_rect(battle),
        ]
        for rect in panel_rects:
            assert bg_rect.contains(rect)

        total_radius = settings.TOTAL_CIRCLE_RADIUS
        total_rect = pygame.Rect(
            BattleScreen._sx(battle, settings.TOTAL_CIRCLE_X) - total_radius,
            BattleScreen._sy(battle, settings.TOTAL_CIRCLE_Y) - total_radius,
            total_radius * 2,
            total_radius * 2,
        )
        finish_rect = pygame.Rect(
            BattleScreen._sx(battle, settings.FINISH_BTN_X) - settings.FINISH_BTN_W // 2,
            BattleScreen._sy(battle, settings.FINISH_BTN_Y),
            settings.FINISH_BTN_W,
            settings.FINISH_BTN_H,
        )

        assert bg_rect.contains(total_rect)
        assert bg_rect.contains(finish_rect)

    def test_battle_panel_helpers_keep_duel_coordinates_at_default_origin(self):
        from config import settings
        from game.screens.battle_screen import BattleScreen

        battle = BattleScreen.__new__(BattleScreen)
        battle._layout_offset_x = 0
        battle._layout_offset_y = 0

        assert BattleScreen._battle_panel_rect(battle).topleft == (
            settings.BATTLE_PANEL_X,
            settings.BATTLE_PANEL_Y,
        )
        assert BattleScreen._battle_panel_icon_center(battle, 2) == (
            settings.BATTLE_PANEL_X + settings.BATTLE_PANEL_W // 2,
            settings.BATTLE_PANEL_ICON_START_Y + 2 * settings.BATTLE_PANEL_ICON_DELTA_Y,
        )


class TestTacticsHandRouting:
    """Phase 9-10 redesign: tactics-hand games never visit ``battle_shop``."""

    def _make_screen(self, *, conquer_move_model='tactics_hand', battle_confirmed=False,
                     battle_moves_phase=False, battle_turn_player_id=None,
                     battle_round=0, last_battle_result=None):
        ConquerGameScreen, screen = _base_conquer_screen(SimpleNamespace(
            mode='conquer',
            conquer_move_model=conquer_move_model,
            battle_confirmed=battle_confirmed,
            battle_turn_player_id=battle_turn_player_id,
            battle_round=battle_round,
            battle_moves_phase=battle_moves_phase,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            pending_battle_ready=False,
            last_battle_result=last_battle_result,
            game_id=1,
            player_id=42,
            opponent_name='Defender',
            land_tier=2,
            land_suit_bonus_suit='Hearts',
            land_suit_bonus_value=2,
        ))
        screen._conquer_left_battle_shop_at = 0
        screen._conquer_collapsed_header_rect = None
        return ConquerGameScreen, screen

    def test_is_tactics_hand_game_true_for_tactics_hand_marker(self):
        ConquerGameScreen, screen = self._make_screen(conquer_move_model='tactics_hand')
        assert ConquerGameScreen._is_tactics_hand_game(screen) is True

    def test_is_tactics_hand_game_false_for_legacy_battle_move_marker(self):
        ConquerGameScreen, screen = self._make_screen(conquer_move_model='battle_move')
        assert ConquerGameScreen._is_tactics_hand_game(screen) is False

    def test_required_tab_never_returns_battle_shop_for_tactics_hand(self):
        ConquerGameScreen, screen = self._make_screen(battle_moves_phase=True)
        tab, _key = ConquerGameScreen._conquer_required_tab(screen)
        assert tab != 'battle_shop'

    def test_required_tab_still_returns_battle_shop_for_legacy_games(self):
        ConquerGameScreen, screen = self._make_screen(
            conquer_move_model='battle_move', battle_moves_phase=True)
        tab, _key = ConquerGameScreen._conquer_required_tab(screen)
        assert tab == 'battle_shop'

    def test_enforce_battle_shop_during_moves_is_noop_for_tactics_hand(self):
        ConquerGameScreen, screen = self._make_screen(battle_moves_phase=True)
        screen.state.subscreen = 'field'
        ConquerGameScreen._enforce_battle_shop_during_moves(screen)
        # Must NOT yank the user onto the (gone) battle_shop subscreen.
        assert screen.state.subscreen == 'field'

    def test_header_uses_full_timeline_before_battle(self):
        ConquerGameScreen, screen = self._make_screen()

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'pre_battle'
        # Tactics-hand games use the persistent two-row header in every
        # mode (pre-battle included) so the top row stays constant.
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is True

    def test_header_collapses_when_battle_turn_starts(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'battle'
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is True

    def test_header_stays_collapsed_for_result_mode(self):
        ConquerGameScreen, screen = self._make_screen(
            last_battle_result={'winner_name': 'Attacker', 'loser_name': 'Defender'},
        )

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'result'
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is True

    def test_tactics_hand_result_dialogue_opens_without_battle_tab_route(self):
        result = {'conquer_result': 'attacker_won', 'attacker_won': True}
        ConquerGameScreen, screen = self._make_screen(last_battle_result=result)
        screen.state.subscreen = 'field'
        calls = []
        screen._handle_conquer_result_response = lambda payload: calls.append(payload)

        ConquerGameScreen._open_tactics_hand_result_dialogue(screen)

        assert calls == [result]
        assert screen.state.subscreen == 'field'

    def test_legacy_games_keep_full_timeline_header_during_battle(self):
        ConquerGameScreen, screen = self._make_screen(
            conquer_move_model='battle_move',
            battle_turn_player_id=42,
            battle_round=1,
        )

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'battle'
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is False

    def test_toggle_opens_and_closes_timeline_overlay(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 240, 64)

        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is False
        ConquerGameScreen._toggle_conquer_timeline_overlay(screen)
        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is True
        ConquerGameScreen._toggle_conquer_timeline_overlay(screen)
        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is False
        assert screen._conquer_timeline_expanded_rect is None

    def test_open_timeline_overlay_syncs_expanded_rect(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        ConquerGameScreen._toggle_conquer_timeline_overlay(screen)

        ConquerGameScreen._sync_conquer_timeline_hover_state(screen)

        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is True
        assert screen._conquer_timeline_expanded_rect == (
            ConquerGameScreen._conquer_timeline_overlay_rect(screen))

    def test_battle_start_keeps_timeline_collapsed_until_user_expands(self):
        # The overlay must never open on its own: auto-opening at battle
        # start compressed the battle layout until the player found the
        # chevron. Only the explicit toggle opens (and closes) it.
        ConquerGameScreen, screen = self._make_screen()
        ConquerGameScreen._sync_conquer_timeline_hover_state(screen)
        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is False

        screen.state.game.battle_turn_player_id = 42
        screen.state.game.battle_round = 1
        ConquerGameScreen._sync_conquer_timeline_hover_state(screen)

        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is False
        assert screen._conquer_timeline_expanded_rect is None

        ConquerGameScreen._toggle_conquer_timeline_overlay(screen)
        ConquerGameScreen._sync_conquer_timeline_hover_state(screen)

        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is True
        assert screen._conquer_timeline_expanded_rect == (
            ConquerGameScreen._conquer_timeline_overlay_rect(screen))

        ConquerGameScreen._toggle_conquer_timeline_overlay(screen)
        ConquerGameScreen._sync_conquer_timeline_hover_state(screen)

        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is False
        assert screen._conquer_timeline_expanded_rect is None

    def test_expanded_timeline_uses_prebattle_content_layout(self):
        from config import settings
        from game.components.conquer_layout import compute_conquer_layout

        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        ConquerGameScreen._toggle_conquer_timeline_overlay(screen)
        ConquerGameScreen._sync_conquer_timeline_hover_state(screen)

        timeline_row = pygame.Rect(
            *ConquerGameScreen._conquer_header_layout(screen).timeline_row_rect
        )
        expanded = ConquerGameScreen._conquer_timeline_overlay_rect(screen)
        pre_header = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode='pre_battle',
        ).header.full_rect
        assert ConquerGameScreen._conquer_effective_layout_mode(screen) == 'pre_battle'
        assert expanded.top == timeline_row.top
        assert expanded.bottom == pre_header[1] + pre_header[3]

    def test_combined_status_label_tracks_active_timeline_step(self):
        from game.screens.conquer_flow import TimelineStep

        ConquerGameScreen, screen = self._make_screen()
        screen._conquer_timeline_panel = SimpleNamespace(
            derive_display_steps=lambda _screen: [TimelineStep(
                kind='prelude_own',
                title='Your Prelude',
                completed=False,
                active=True,
                interactive=False,
                primary_action='next',
            )]
        )

        label = ConquerGameScreen._conquer_combined_status_label(screen)

        assert label == 'Next · Your Prelude'

    def test_battle_timeline_steps_include_round_tactics(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=1,
        )
        you = {
            'id': 11,
            'family_name': 'Dagger',
            'suit': 'Hearts',
            'value': 5,
            'status': 'played',
            'played_round': 0,
        }
        opponent = {
            'id': 21,
            'family_name': 'Shield',
            'suit': 'Clubs',
            'value': 3,
            'status': 'played',
            'played_round': 0,
        }
        screen._current_conquer_tactics = lambda: [you]
        screen._current_conquer_opponent_tactics = lambda: [opponent]

        steps = ConquerGameScreen._conquer_battle_timeline_steps(screen, [])

        # Each round splits into a player + opponent step (in that order).
        kinds = [step.kind for step in steps]
        assert kinds == [
            'battle_round_1_player', 'battle_round_1_opponent',
            'battle_round_2_player', 'battle_round_2_opponent',
        ]
        you_step = steps[0]
        opp_step = steps[1]
        assert you_step.icon_kind == 'tactic'
        assert you_step.icon_payload == {'move': you, 'side': 'you'}
        assert you_step.owner == 'you'
        assert you_step.completed is True
        assert opp_step.icon_payload == {'move': opponent, 'side': 'opp'}
        assert opp_step.owner == 'opp'
        assert opp_step.completed is True
        assert 'You played Dagger' in you_step.info_body
        assert 'Defender played Shield' in opp_step.info_body
        # Round 2 is the active one; battle_round is zero-indexed.
        round2_player = steps[2]
        assert round2_player.active is True
        assert round2_player.completed is False
        assert round2_player.info_body == 'Pick a tactic to commit.'

    def test_collapsed_header_clears_stale_actions_and_exposes_withdraw(self):
        from config import settings

        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        screen._conquer_header_font = settings.get_font(settings.FS_HEADING, bold=True)
        screen._conquer_hint_font = settings.get_font(settings.FS_SMALL)
        screen._conquer_badge_font = settings.get_font(settings.FS_TINY, bold=True)
        screen._conquer_status_font = settings.get_font(settings.FS_SMALL, bold=True)
        screen._conquer_objective_action_rects = {'next': pygame.Rect(1, 1, 10, 10)}
        screen._withdraw_dialogue_open = False
        screen._is_current_player_conquer_attacker = lambda: True

        ConquerGameScreen._draw_conquer_collapsed_header(screen)

        assert 'next' not in screen._conquer_objective_action_rects
        assert 'withdraw' in screen._conquer_objective_action_rects

    def test_mobile_timeline_has_no_next_button_in_inert_states(self):
        # The timeline Next button only does something for held sequence beats
        # (it skips their countdown). In battle rounds and the game-start hold,
        # advancing is driven by game state, so the button is inert and must not
        # be drawn. The held-beat geometry is covered in test_conquer_timeline.
        _run_mobile_geometry_check(r'''
import pygame
pygame.mouse.set_cursor = lambda *args, **kwargs: None
from nepal_kings import Client

client = Client()
client._init_perf_conquer_fixture(lambda *_args, **_kwargs: None)
screen = client.screens['conquer_game']

def assert_no_next_button(label):
    screen.render()
    assert screen._conquer_objective_action_rects.get('next') is None, label

# Battle overlay (a round beat): inert -> no Next button.
assert_no_next_button('battle overlay')

# Pre-battle game-start hold: also inert -> no Next button.
game = screen.state.game
game.battle_turn_player_id = None
game.battle_round = 0
game.battle_confirmed = False
game.battle_moves_phase = False
game.in_battle_phase = False
game._game_start_pending = True
game.game_start_notification_checked = False
screen._conquer_timeline_hover_open = False
assert_no_next_button('pre-battle inline')
pygame.quit()
''')

    def test_mobile_tactics_rail_actions_are_readable_and_separated(self):
        _run_mobile_geometry_check(r'''
import pygame
pygame.mouse.set_cursor = lambda *args, **kwargs: None
from nepal_kings import Client
from config import settings
from game.components.conquer_tactics_rail import ACTION_GAMBLE, ACTION_PLAY

client = Client()
client._init_perf_conquer_fixture(lambda *_args, **_kwargs: None)
screen = client.screens['conquer_game']
rail = screen._tactics_rail
hand = rail._hand_moves()
assert hand, 'fixture must expose at least one tactic'
rail._selected_id = hand[0]['id']

screen.render()

action_tray = rail._dyn_action_tray_rect
hand_list = rail._dyn_hand_list_rect
assert action_tray is not None
assert hand_list is not None
assert hand_list.bottom <= action_tray.top

for key in (ACTION_PLAY, ACTION_GAMBLE):
    rect = rail._action_button_rects.get(key)
    assert rect is not None, key
    assert action_tray.contains(rect), (key, tuple(action_tray), tuple(rect))
    assert rect.h >= settings.TOUCH_COMPACT_MIN, (key, rect.h, settings.TOUCH_COMPACT_MIN)

assert not rail._action_button_rects[ACTION_PLAY].colliderect(
    rail._action_button_rects[ACTION_GAMBLE])

game = screen.state.game
assert rail._gamble_status_for_strip(game)[0] == 'Gamble ready'
game.battle_gamble_counts = {
    str(game.player_id): {
        'count': 1,
        'rounds': [int(game.battle_round or 0)],
    },
}
assert rail._gamble_status_for_strip(game)[0] == 'Gamble used'
pygame.quit()
''')

    def test_mobile_battle_shop_ready_banner_clears_ready_button(self):
        _run_mobile_geometry_check(r'''
import pygame
pygame.mouse.set_cursor = lambda *args, **kwargs: None
from nepal_kings import Client

client = Client()
client._init_perf_conquer_fixture(lambda *_args, **_kwargs: None)
client.state.screen = 'conquer_game'
client.state.subscreen = 'battle_shop'
screen = client.screens['conquer_game']
game = client.state.game
game.turn = True
game.conquer_move_model = 'battle_move'
game.battle_confirmed = True
game.battle_moves_phase = True
game.battle_turn_player_id = None
game.in_battle_phase = False
game.battle_round = 0
for subscreen_obj in screen.subscreens.values():
    if hasattr(subscreen_obj, 'game'):
        subscreen_obj.game = game

shop = screen.subscreens['battle_shop']
shop.bought_moves = [
    {'id': 901, 'card_id': 5901, 'round_index': 0,
     'family_name': 'Call Military', 'suit': 'Hearts', 'rank': 'A',
     'value': 3, 'card_type': 'main'},
    {'id': 902, 'card_id': 5902, 'round_index': 1,
     'family_name': 'Block', 'suit': 'Clubs', 'rank': 'Q',
     'value': 2, 'card_type': 'main'},
    {'id': 903, 'card_id': 5903, 'round_index': 2,
     'family_name': 'Dagger', 'suit': 'Diamonds', 'rank': '9',
     'value': 9, 'card_type': 'main'},
]
shop._loaded_game_key = (game.game_id, game.player_id)
shop._loaded_bought_moves_key = shop._bought_moves_cache_key(game)

screen.render()
banner_rect = getattr(shop, '_phase_banner_rect', None)
ready_rect = shop.ready_button.rect
assert banner_rect is not None
assert not banner_rect.colliderect(ready_rect), (
    tuple(banner_rect), tuple(ready_rect))
assert banner_rect.top >= ready_rect.bottom + 2 or banner_rect.bottom <= ready_rect.top - 2
pygame.quit()
''')

    def test_tactics_hand_gamble_uses_conquer_tactic_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_GAMBLE

        ConquerGameScreen, screen = self._make_screen()
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.gamble_conquer_tactic',
            lambda game_id, player_id, tactic_id: called.append((game_id, player_id, tactic_id)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.gamble_battle_move',
            lambda *_args: called.append(('legacy',)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_GAMBLE, 'move': {'id': 7}},
        )

        assert called == [(1, 42, 7)]

    def test_tactics_hand_gamble_failure_shows_banner(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_GAMBLE

        ConquerGameScreen, screen = self._make_screen()
        banners = []
        resets = []
        rail = SimpleNamespace(
            _gamble_anim={'move_id': 7},
            reset_after_action=lambda: resets.append(True),
            set_result_banner=lambda *args, **kwargs: banners.append((args, kwargs)),
        )
        screen._tactics_rail = rail
        monkeypatch.setattr(
            'utils.game_service.gamble_conquer_tactic',
            lambda *_args: {
                'success': False,
                'message': 'You can only gamble once per battle round',
            },
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_GAMBLE, 'move': {'id': 7}},
        )

        assert banners[0][0][0] == 'You can only gamble once per battle round'
        assert resets == []
        assert rail._gamble_anim is None

    def test_duel_lane_preview_uses_zero_indexed_round(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=1,
        )
        preview = {'id': 12, 'status': 'available', 'played_round': None}
        screen._tactics_rail = SimpleNamespace(preview_move=lambda: preview)
        player_slots = [
            {'id': 11, 'status': 'played', 'played_round': 0},
            None,
            None,
        ]
        opponent_slots = [
            {'id': 21, 'status': 'played', 'played_round': 0},
            {'id': 22, 'status': 'played', 'played_round': 1},
            None,
        ]

        assert ConquerGameScreen._conquer_lane_focus_round(
            screen, player_slots, opponent_slots) == 1
        assert ConquerGameScreen._conquer_lane_preview_move(
            screen, player_slots, 1) is preview

    def test_tactics_hand_play_starts_flight_animation(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_PLAY

        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        source_rect = pygame.Rect(20, 30, 80, 40)
        screen._tactics_rail = SimpleNamespace(
            reset_after_action=lambda: None,
            move_cell_rect=lambda _move_id: source_rect,
        )
        called = []

        def fake_play(game_id, player_id, tactic_id):
            called.append((game_id, player_id, tactic_id))
            return {'success': True}

        monkeypatch.setattr(
            'utils.game_service.play_conquer_tactic',
            fake_play,
        )
        monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1234)

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {
                'action': ACTION_PLAY,
                'move': {'id': 7, 'family_name': 'Sword', 'value': 9},
            },
        )

        assert called == [(1, 42, 7)]
        animation = screen._tactic_flight_animation
        assert animation['move']['id'] == 7
        assert animation['source'] == source_rect
        assert animation['target'].width > 0
        from config import settings
        from game.components.conquer_layout import compute_conquer_layout
        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode='battle',
        )
        second_round = pygame.Rect(*layout.round_ledger.round_card_rects[1])
        first_round = pygame.Rect(*layout.round_ledger.round_card_rects[0])
        assert second_round.collidepoint(animation['target'].center)
        assert not first_round.collidepoint(animation['target'].center)
        assert animation['started_at'] == 1234

    def test_tactics_hand_dismantle_uses_conquer_tactic_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_DISMANTLE

        ConquerGameScreen, screen = self._make_screen()
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.dismantle_conquer_tactic',
            lambda game_id, player_id, tactic_id: called.append((game_id, player_id, tactic_id)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.dismantle_battle_move',
            lambda *_args: called.append(('legacy',)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_DISMANTLE, 'move': {'id': 8}},
        )

        assert called == [(1, 42, 8)]

    def test_legacy_gamble_still_uses_battle_shop_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_GAMBLE

        ConquerGameScreen, screen = self._make_screen(conquer_move_model='battle_move')
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.gamble_conquer_tactic',
            lambda *_args: called.append(('tactics',)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.gamble_battle_move',
            lambda game_id, player_id, move_id: called.append((game_id, player_id, move_id)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_GAMBLE, 'move': {'id': 9}},
        )

        assert called == [(1, 42, 9)]

    def test_legacy_dismantle_still_uses_battle_shop_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_DISMANTLE

        ConquerGameScreen, screen = self._make_screen(conquer_move_model='battle_move')
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.dismantle_conquer_tactic',
            lambda *_args: called.append(('tactics',)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.dismantle_battle_move',
            lambda game_id, player_id, move_id: called.append((game_id, player_id, move_id)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_DISMANTLE, 'move': {'id': 10}},
        )

        assert called == [(1, 42, 10)]


class TestConquerObjectiveTacticsHand:
    """Objective derivation never aims at battle_shop for tactics-hand."""

    def test_moves_objective_targets_field_for_tactics_hand(self):
        from game.screens.conquer_flow import derive_conquer_objective

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            battle_confirmed=False,
            pending_battle_ready=False,
            advancing_figure_id=None,
            defending_figure_id=None,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            pending_forced_advance=False,
            pending_conquer_prelude_target=False,
            pending_spell_id=None,
            current_round=1,
            game_over=False,
            game_state='active',
            state='active',
            mode_attribute=None,
            last_battle_result=None,
        )
        objective = derive_conquer_objective(
            game=game,
            field_screen=None,
            battle_shop_screen=None,
        )
        assert objective is not None
        assert objective.target_tab == 'field'
        assert objective.primary_action == 'play_tactic'

    def test_battle_objective_targets_field_for_tactics_hand(self):
        from game.screens.conquer_flow import derive_conquer_objective

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=1,
            player_id=42,
            both_battle_moves_ready=False,
            game_over=False,
            pending_game_over=False,
            pending_conquer_prelude_target=False,
            pending_forced_advance=False,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            civil_war_awaiting_second=False,
            civil_war_defender_second=False,
        )
        objective = derive_conquer_objective(
            game=game,
            field_screen=None,
            battle_shop_screen=None,
        )

        assert objective.target_tab == 'field'
        assert objective.primary_action == 'play_tactic'

    def test_moves_objective_targets_battle_shop_for_legacy_games(self):
        from game.screens.conquer_flow import derive_conquer_objective

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='battle_move',
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            battle_confirmed=False,
            pending_battle_ready=False,
            advancing_figure_id=None,
            defending_figure_id=None,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            pending_forced_advance=False,
            pending_conquer_prelude_target=False,
            pending_spell_id=None,
            current_round=1,
            game_over=False,
            game_state='active',
            state='active',
            mode_attribute=None,
            last_battle_result=None,
        )
        objective = derive_conquer_objective(
            game=game,
            field_screen=None,
            battle_shop_screen=SimpleNamespace(bought_moves=[]),
        )
        assert objective is not None
        assert objective.target_tab == 'battle_shop'
