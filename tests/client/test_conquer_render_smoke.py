# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Render smoke tests for the unified conquer tactics UI."""

from types import SimpleNamespace

import pygame


def _move(move_id, *, family='Dagger', suit='Hearts', rank='A', value=5,
          status='available', played_round=None, card_id_b=None, suit_b=None,
          call_figure_id=None):
    return {
        'id': move_id,
        'card_id': move_id + 100,
        'card_id_b': card_id_b,
        'family_name': family,
        'suit': suit,
        'suit_b': suit_b,
        'rank': rank,
        'value': value,
        'status': status,
        'played_round': played_round,
        'call_figure_id': call_figure_id,
        'source': 'config',
    }


def _fighter(fig_id, name, value, player_id, color, *, suit='Hearts',
             field='military', buffs_allies=False, buffs_allies_defence=False,
             blocks_bonus=False, distance_attack=False, battle_bonus=None):
    icon = pygame.Surface((64, 64), pygame.SRCALPHA)
    icon.fill(color)
    frame = pygame.Surface((80, 80), pygame.SRCALPHA)
    pygame.draw.circle(frame, (238, 206, 111), (40, 40), 38, 4)
    return SimpleNamespace(
        id=fig_id,
        name=name,
        player_id=player_id,
        suit=suit,
        field=field,
        value=value,
        number_card=SimpleNamespace(value=value),
        get_value=lambda: value,
        get_battle_bonus=lambda: value if battle_bonus is None else battle_bonus,
        family=SimpleNamespace(
            icon_img=icon,
            icon_img_small=icon,
            frame_img=frame,
            field=field,
        ),
        buffs_allies=buffs_allies,
        buffs_allies_defence=buffs_allies_defence,
        blocks_bonus=blocks_bonus,
        distance_attack=distance_attack,
    )


class _ConquerUiParent:
    def __init__(self, window, game, moves, opp_played=None):
        self.window = window
        self.state = SimpleNamespace(game=game)
        self.subscreens = {
            'battle': SimpleNamespace(opp_played=opp_played or []),
        }
        self._moves = list(moves)

    def _current_conquer_battle_moves(self):
        return list(self._moves)

    def _conquer_battle_move_icon_assets(self, icon_size):
        from config import settings

        return ({}, {}, {}, {}, settings.get_font(max(8, icon_size // 3), bold=True))


def _rect_has_non_background_pixel(surface, rect, background=(0, 0, 0)):
    bounds = pygame.Rect(rect).clip(surface.get_rect())
    step_x = max(1, bounds.width // 12)
    step_y = max(1, bounds.height // 12)
    for x in range(bounds.left, bounds.right, step_x):
        for y in range(bounds.top, bounds.bottom, step_y):
            if surface.get_at((x, y))[:3] != background:
                return True
    return False


def test_tactics_rail_draws_scrollable_long_tactics_without_blank_output():
    from config import settings
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=1,
        battle_turn_player_id=1,
        last_battle_result=None,
    )
    moves = [
        _move(1, family='Very Long Tactical Dagger Name That Must Clip', rank='A', value=9),
        _move(2, family='Block', suit='Spades', rank='K', value=0),
        _move(3, family='Sword', suit='Clubs', rank='Q', value=7),
        _move(4, family='Shield', suit='Diamonds', rank='J', value=4),
        _move(5, family='Lance', suit='Hearts', rank='10', value=6),
        _move(6, family='Dagger', suit='Diamonds', rank='9', value=5),
        _move(7, family='Double Dagger', suit='Hearts', suit_b='Diamonds',
              rank='8', value=10, card_id_b=207),
    ]
    parent = _ConquerUiParent(window, game, moves)
    rail = ConquerTacticsRail(parent)

    rail.draw()

    layout = rail._ensure_layout().tactics_rail
    assert _rect_has_non_background_pixel(window, rail.rect())
    outside_rail = pygame.Rect(rail.rect().right + 1, rail.rect().top, 8, rail.rect().height)
    assert not _rect_has_non_background_pixel(window, outside_rail)
    # Family headers between groups consume some vertical space, so the
    # rail may render slightly fewer cells than ``cells_visible`` —
    # require at least 1 and no more than the layout slot count.
    assert 1 <= len(rail._cell_rects) <= layout.cells_visible
    assert rail._scroll_down_rect is not None
    rail._scroll = 99
    rail._clamp_scroll()
    assert rail._scroll == len(moves) - layout.cells_visible
    # First cell corresponds to whichever move the rail rendered first
    # (the rail groups by family, so id=1 is no longer guaranteed first).
    first_id = rail._cell_move_ids[0]
    assert rail.move_cell_rect(first_id) == rail._cell_rects[0]
    rail._scroll = 0
    rail.draw()
    rail._hovered_id = rail._cell_move_ids[0]
    assert rail.preview_move()['id'] == rail._cell_move_ids[0]
    game.battle_turn_player_id = 2
    assert rail.preview_move() is None

    font = settings.get_font(settings.FS_SMALL, bold=True)
    fitted = ConquerTacticsRail._fit_text(
        'Very Long Tactical Dagger Name That Must Clip', font, 80)
    assert font.size(fitted)[0] <= 80
    assert fitted.endswith('...')


def test_tactics_rail_action_buttons_adapt_to_selected_tactic():
    from config import settings
    from game.components.conquer_tactics_rail import (
        ACTION_COMBINE,
        ACTION_DISMANTLE,
        ACTION_GAMBLE,
        ACTION_PLAY,
        ConquerTacticsRail,
    )

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=1,
        battle_turn_player_id=1,
        battle_confirmed=True,
        battle_gamble_counts={},
        last_battle_result=None,
    )
    moves = [
        _move(1, family='Call King', suit='Hearts', rank='K', value=4),
        _move(2, family='Dagger', suit='Hearts', rank='9', value=9),
        _move(3, family='Double Dagger', suit='Hearts', suit_b='Diamonds',
              rank='8+9', value=17, card_id_b=203),
    ]
    rail = ConquerTacticsRail(_ConquerUiParent(window, game, moves))

    rail._selected_id = 1
    rail.draw()
    assert set(rail._action_button_rects) == {ACTION_PLAY, ACTION_GAMBLE}

    rail._selected_id = 2
    rail.draw()
    assert set(rail._action_button_rects) == {ACTION_PLAY, ACTION_GAMBLE, ACTION_COMBINE}

    rail._selected_id = 3
    rail.draw()
    assert set(rail._action_button_rects) == {ACTION_PLAY, ACTION_GAMBLE, ACTION_DISMANTLE}


def test_round_ledger_draws_filled_rounds_and_result_click_target():
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=3,
        battle_turn_player_id=1,
        last_battle_result=None,
    )
    moves = [
        _move(11, family='Dagger', suit='Hearts', rank='A', value=5,
              status='played', played_round=0),
        _move(12, family='Block', suit='Spades', rank='K', value=0,
              status='played', played_round=1),
        _move(13, family='Sword', suit='Clubs', rank='Q', value=8,
              status='played', played_round=2),
    ]
    opp_played = [
        _move(21, family='Shield', suit='Clubs', rank='9', value=3, played_round=0),
        _move(22, family='Lance', suit='Diamonds', rank='8', value=7, played_round=1),
        _move(23, family='Dagger', suit='Spades', rank='7', value=4, played_round=2),
    ]
    parent = _ConquerUiParent(window, game, moves, opp_played=opp_played)
    ledger = ConquerRoundLedger(parent)

    ledger.draw()

    assert _rect_has_non_background_pixel(window, ledger.rect())
    assert ledger._total_circle_rect is not None
    assert ledger.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        button=1,
        pos=ledger._total_circle_rect.center,
    )) is None

    game.last_battle_result = {'outcome': 'win'}
    ledger.draw()

    assert ledger.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        button=1,
        pos=ledger._total_circle_rect.center,
    )) == 'open_result'


def test_round_ledger_draws_hover_preview_ghost_math():
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=2,
        battle_turn_player_id=1,
        last_battle_result=None,
    )
    preview = _move(14, family='Sword', suit='Hearts', rank='Q', value=9)
    moves = [
        _move(11, family='Dagger', suit='Hearts', rank='A', value=5,
              status='played', played_round=0),
        preview,
    ]
    opp_played = [
        _move(21, family='Shield', suit='Clubs', rank='9', value=3, played_round=0),
        _move(22, family='Lance', suit='Diamonds', rank='8', value=4, played_round=1),
        None,
    ]
    parent = _ConquerUiParent(window, game, moves, opp_played=opp_played)
    parent._tactics_rail = SimpleNamespace(preview_move=lambda: preview)
    ledger = ConquerRoundLedger(parent)

    you_per = ledger._player_played_per_round()
    opp_per = ledger._opp_played_per_round()
    ghost = ledger._ghost_preview(you_per)

    assert ghost == (1, preview)
    assert ledger._ghost_total_diff(you_per, opp_per, ghost) == 7

    ledger.draw()

    layout = ledger._ensure_layout().round_ledger
    assert _rect_has_non_background_pixel(window, layout.round_card_rects[1])
    assert _rect_has_non_background_pixel(window, layout.total_circle_rect)


def test_round_ledger_uses_revealed_opponent_tactics_and_icons(monkeypatch):
    from config import settings
    from game.components import conquer_round_ledger as ledger_module
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=2,
        battle_turn_player_id=1,
        last_battle_result=None,
    )
    moves = [
        _move(11, family='Dagger', suit='Hearts', rank='A', value=5,
              status='played', played_round=0),
    ]
    opponent_move = _move(
        21,
        family='Shield',
        suit='Clubs',
        rank='9',
        value=3,
        status='played',
        played_round=0,
    )
    parent = _ConquerUiParent(window, game, moves, opp_played=[])
    parent._current_conquer_opponent_tactics = lambda: [opponent_move]
    calls = []

    def capture_icon(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(ledger_module, 'draw_battle_move_icon', capture_icon)
    ledger = ConquerRoundLedger(parent)

    assert ledger._opp_played_per_round()[0] == opponent_move

    ledger.draw()

    assert len(calls) >= 2


def test_tactics_hand_field_overlay_does_not_dim_idle_figures():
    from config import settings
    from game.screens.field_screen import FieldScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((255, 255, 255))
    before = window.get_at((100, 100))
    figure = SimpleNamespace(
        id=99,
        player_id=2,
        family=SimpleNamespace(name='Scout'),
    )
    field = FieldScreen.__new__(FieldScreen)
    field.window = window
    field.game = SimpleNamespace(player_id=1)
    field._is_tactics_hand_battle_field_view_only = lambda: True
    field._is_tactics_hand_battle_fighter = lambda _figure: False
    field._conquer_preview_called_figure_ids = lambda: set()
    field._conquer_called_figure_ids = lambda: set()
    field._figure_active_skill_keys = lambda _figure: set()
    field._conquer_hover_source_figure_id = None

    FieldScreen._draw_tactics_hand_battle_context_overlays(
        field,
        [(SimpleNamespace(figure=figure), 100, 100)],
    )

    assert window.get_at((100, 100)) == before


def test_tactics_hand_reveals_opponent_support_sources(monkeypatch):
    from game.screens import field_screen as field_module
    from game.screens.field_screen import FieldScreen

    class FakeFieldFigureIcon:
        def __init__(self, *, figure, is_visible, **_kwargs):
            self.figure = figure
            self.is_visible = is_visible
            self.has_deficit = False
            self.rect_frame = pygame.Rect(0, 0, 40, 48)

        def _calculate_battle_bonus_received(self, _figures):
            return 0

        def _check_resource_deficit(self, _resources):
            return False

    monkeypatch.setattr(field_module, 'FieldFigureIcon', FakeFieldFigureIcon)

    attacker = _fighter(10, 'Attacker', 8, 1, (80, 160, 210), suit='Hearts')
    defender = _fighter(20, 'Defender', 5, 2, (200, 105, 90), suit='Hearts')
    opponent_support = _fighter(
        30,
        'Hidden Support',
        4,
        2,
        (180, 120, 90),
        suit='Hearts',
        field='castle',
    )
    hidden_non_support = _fighter(
        31,
        'Hidden Idle',
        4,
        2,
        (120, 120, 120),
        suit='Spades',
        field='village',
    )

    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_turn_player_id=1,
        player_id=1,
        calculate_resources=lambda *_args, **_kwargs: None,
        has_active_all_seeing_eye=lambda: False,
    )

    class Parent:
        def request_conquer_figure_confirmation(self):
            return None

        def _conquer_lane_figures(self):
            return [attacker], [defender]

        def _conquer_lane_support_entries(self, _player_figures, _opponent_figures, *, is_player):
            if is_player:
                return []
            return [{
                'kind': 'support_bonus',
                'label': 'Support',
                'value': '+4',
                'figure': opponent_support,
            }]

    field = FieldScreen.__new__(FieldScreen)
    field.window = pygame.Surface((200, 200))
    field.game = game
    field.state = SimpleNamespace(parent_screen=Parent())
    field.figure_manager = SimpleNamespace(families={})
    field.categorized_figures = {
        'self': {'military': [attacker], 'village': [], 'castle': []},
        'opponent': {
            'military': [defender],
            'village': [hidden_non_support],
            'castle': [opponent_support],
        },
    }
    field.icon_cache = {}
    field.cached_all_seeing_eye_status = None
    field.last_all_seeing_eye_check = 0
    field.all_seeing_eye_check_interval = 1000

    FieldScreen._generate_figure_icons(field)

    assert field.icon_cache[opponent_support.id].is_visible is True
    assert field.icon_cache[hidden_non_support.id].is_visible is False
    assert FieldScreen._conquer_battle_context_kind(field, opponent_support) is None
    assert FieldScreen._tactics_hand_revealed_support_figure_ids(field) == {opponent_support.id}


def test_round_ledger_hover_completed_round_draws_recap(monkeypatch):
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=2,
        battle_turn_player_id=2,
        last_battle_result=None,
    )
    moves = [
        _move(11, family='Dagger', suit='Hearts', rank='A', value=5,
              status='played', played_round=0),
    ]
    opp_played = [
        _move(21, family='Shield', suit='Clubs', rank='9', value=3, played_round=0),
        None,
        None,
    ]
    parent = _ConquerUiParent(window, game, moves, opp_played=opp_played)
    ledger = ConquerRoundLedger(parent)
    layout = ledger._ensure_layout().round_ledger
    hover_pos = pygame.Rect(*layout.round_card_rects[0]).center
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: hover_pos)

    ledger.draw()

    assert ledger._hover_round_idx == 0
    assert ledger._hover_popover_rect is not None
    assert _rect_has_non_background_pixel(window, ledger._hover_popover_rect)


def test_round_ledger_animates_newly_completed_round_reveal(monkeypatch):
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=2,
        battle_turn_player_id=2,
        last_battle_result=None,
    )
    moves = [
        _move(11, family='Dagger', suit='Hearts', rank='A', value=5,
              status='played', played_round=0),
    ]
    opp_played = [
        _move(21, family='Shield', suit='Clubs', rank='9', value=3, played_round=0),
        None,
        None,
    ]
    parent = _ConquerUiParent(window, game, moves, opp_played=opp_played)
    ledger = ConquerRoundLedger(parent)
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)

    ledger.draw()

    assert 0 in ledger._round_reveal_animations
    layout = ledger._ensure_layout().round_ledger
    assert _rect_has_non_background_pixel(window, layout.round_card_rects[0])

    monkeypatch.setattr(
        pygame.time,
        'get_ticks',
        lambda: 1001 + ConquerRoundLedger.REVEAL_REPLAY_MS,
    )
    ledger.draw()

    assert 0 not in ledger._round_reveal_animations


def test_conquer_duel_lane_draws_current_battle_fighters():
    from config import settings
    from game.components.conquer_layout import compute_conquer_layout
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    attacker = _fighter(10, 'Attacking Guard', 8, 1, (80, 160, 210))
    defender = _fighter(20, 'Defending Guard', 5, 2, (200, 105, 90))
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        player_id=1,
        advancing_player_id=1,
        advancing_figure_id=10,
        defending_figure_id=20,
        advancing_figure_id_2=None,
        defending_figure_id_2=None,
        battle_turn_player_id=1,
        battle_round=1,
        last_battle_result=None,
        opponent_name='Bhaktapur',
        conquer_tactics=[
            _move(11, family='Sword', suit='Hearts', rank='Q', value=8,
                  status='played', played_round=0),
        ],
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {
        'field': SimpleNamespace(figures=[attacker, defender]),
        'battle': SimpleNamespace(opp_played=[
            _move(21, family='Shield', suit='Clubs', rank='9', value=3,
                  status='played', played_round=0),
        ]),
    }

    ConquerGameScreen._draw_conquer_duel_lane(screen)

    lane = compute_conquer_layout(
        settings.SCREEN_WIDTH,
        settings.SCREEN_HEIGHT,
        mode='battle',
    ).battlefield.duel_lane
    player_figures, opponent_figures = ConquerGameScreen._conquer_lane_figures(screen)

    assert player_figures == [attacker]
    assert opponent_figures == [defender]
    assert _rect_has_non_background_pixel(window, lane.rect)
    assert _rect_has_non_background_pixel(window, lane.you_support_badge_rail)
    assert _rect_has_non_background_pixel(window, lane.opp_support_badge_rail)
    assert _rect_has_non_background_pixel(window, lane.diff_band)


def test_conquer_duel_lane_uses_hovered_tactic_as_preview(monkeypatch):
    from config import settings
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    attacker = _fighter(10, 'Attacking Guard', 8, 1, (80, 160, 210))
    defender = _fighter(20, 'Defending Guard', 5, 2, (200, 105, 90))
    preview = _move(11, family='Sword', suit='Hearts', rank='Q', value=9)
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        player_id=1,
        advancing_player_id=1,
        advancing_figure_id=10,
        defending_figure_id=20,
        advancing_figure_id_2=None,
        defending_figure_id_2=None,
        battle_turn_player_id=1,
        battle_round=1,
        last_battle_result=None,
        opponent_name='Bhaktapur',
        conquer_tactics=[preview],
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {
        'field': SimpleNamespace(figures=[attacker, defender]),
        'battle': SimpleNamespace(opp_played=[
            _move(21, family='Shield', suit='Clubs', rank='9', value=3,
                  status='played', played_round=0),
        ]),
    }
    screen._tactics_rail = SimpleNamespace(preview_move=lambda: preview)
    captured = {'diff': None}

    def capture_diff(_self, _rect, _player_figures, _opponent_figures,
                     player_move=None, opponent_move=None, round_idx=0):
        captured['diff'] = (player_move, opponent_move, round_idx)

    monkeypatch.setattr(ConquerGameScreen, '_draw_conquer_lane_diff', capture_diff)

    assert ConquerGameScreen._conquer_lane_preview_move(
        screen, [None, None, None], 0) == preview

    ConquerGameScreen._draw_conquer_duel_lane(screen)

    assert captured['diff'][0] == preview


def test_conquer_duel_lane_draws_real_support_badges_and_chips(monkeypatch):
    from config import settings
    from game.components.conquer_layout import compute_conquer_layout
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    attacker = _fighter(10, 'Village Guard', 8, 1, (80, 160, 210),
                        suit='Hearts', field='village')
    defender = _fighter(20, 'Defending Guard', 5, 2, (200, 105, 90),
                        suit='Hearts', field='military')
    healer = _fighter(30, 'Djungle Healer', 4, 1, (90, 190, 120),
                      suit='Hearts', field='village', buffs_allies=True)
    archer = _fighter(31, 'Spades Archer', 3, 1, (90, 120, 200),
                      suit='Spades', field='military', distance_attack=True)
    castle_support = _fighter(32, 'King Support', 4, 1, (130, 180, 120),
                              suit='Hearts', field='castle', battle_bonus=4)
    wall = _fighter(40, 'Stone Wall', 6, 2, (180, 140, 110),
                    suit='Clubs', field='military', buffs_allies_defence=True)
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        player_id=1,
        opponent_id=2,
        advancing_player_id=1,
        advancing_figure_id=10,
        defending_figure_id=20,
        advancing_figure_id_2=None,
        defending_figure_id_2=None,
        battle_turn_player_id=1,
        battle_round=1,
        last_battle_result=None,
        opponent_name='Bhaktapur',
        land_suit_bonus_suit='Hearts',
        land_suit_bonus_value=2,
        conquer_tactics=[
            _move(11, family='Sword', suit='Hearts', rank='Q', value=8,
                  status='played', played_round=0, call_figure_id=30),
        ],
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {
        'field': SimpleNamespace(
            figures=[attacker, defender, healer, archer, castle_support, wall],
            icon_cache={
                30: SimpleNamespace(rect_frame=pygame.Rect(180, 200, 44, 56)),
                32: SimpleNamespace(rect_frame=pygame.Rect(230, 200, 44, 56)),
            },
            _conquer_hover_source_figure_id=None,
        ),
        'battle': SimpleNamespace(opp_played=[
            _move(21, family='Shield', suit='Clubs', rank='9', value=3,
                  status='played', played_round=0),
        ]),
    }

    player_support = ConquerGameScreen._conquer_lane_support_entries(
        screen, [attacker], [defender], is_player=True)
    opponent_support = ConquerGameScreen._conquer_lane_support_entries(
        screen, [attacker], [defender], is_player=False)

    # 'called' may also appear when the test fixture includes a played
    # tactic with call_figure_id (#1 — show called figures in the lane).
    kinds = [entry['kind'] for entry in player_support]
    assert kinds[:3] == ['support_bonus', 'buffs_allies', 'distance_attack']
    assert set(kinds) - {'support_bonus', 'buffs_allies', 'distance_attack', 'land_bonus', 'called'} == set()
    assert [entry['kind'] for entry in opponent_support] == ['buffs_allies_defence', 'land_bonus']
    player_rows, player_total = ConquerGameScreen._conquer_lane_receipt_components(
        screen,
        [attacker],
        game.conquer_tactics[0],
        player_support,
        opponent_support,
    )
    opponent_rows, opponent_total = ConquerGameScreen._conquer_lane_receipt_components(
        screen,
        [defender],
        screen.subscreens['battle'].opp_played[0],
        opponent_support,
        player_support,
    )

    player_row_values = {(row['label'], row['value']) for row in player_rows}
    opponent_row_values = {(row['label'], row['value']) for row in opponent_rows}
    assert ('Called', 16) in player_row_values
    assert ('Support', 4) in player_row_values
    assert ('Buffs', 4) in player_row_values
    assert ('Land', 2) in player_row_values
    assert ('Wall', 6) in opponent_row_values
    assert ('Land', 2) in opponent_row_values
    assert ('Range', -3) in opponent_row_values
    called_row = next(row for row in player_rows if row['label'] == 'Called')
    support_row = next(row for row in player_rows if row['label'] == 'Support')
    range_row = next(row for row in opponent_rows if row['label'] == 'Range')
    assert called_row['source_figure_ids'] == [healer.id]
    assert support_row['source_figure_ids'] == [castle_support.id]
    assert range_row['source_figure_ids'] == [archer.id]
    assert player_total == 34
    assert opponent_total == 13

    ConquerGameScreen._draw_conquer_duel_lane(screen)

    lane = compute_conquer_layout(
        settings.SCREEN_WIDTH,
        settings.SCREEN_HEIGHT,
        mode='battle',
    ).battlefield.duel_lane
    assert _rect_has_non_background_pixel(window, lane.you_support_badge_rail)
    assert _rect_has_non_background_pixel(window, lane.opp_support_badge_rail)
    assert lane.you_support_chip_rail[2] == 0

    first_badge = screen._conquer_support_badge_rects[0]
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: first_badge['rect'].center)
    hovered = ConquerGameScreen._update_conquer_support_hover_state(screen)
    assert hovered['figure_id'] == castle_support.id
    assert screen.subscreens['field']._conquer_hover_source_figure_id == castle_support.id
    assert ConquerGameScreen._conquer_support_source_rect(screen, castle_support.id) == pygame.Rect(230, 200, 44, 56)

    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: pygame.Rect(230, 200, 44, 56).center)
    hovered = ConquerGameScreen._update_conquer_support_hover_state(screen)
    assert hovered['figure_id'] == castle_support.id
    assert screen.subscreens['field']._conquer_hover_source_figure_id == castle_support.id


def test_conquer_support_rail_overflow_registers_hover_popover(monkeypatch):
    from config import settings
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen._conquer_support_badge_rects = []
    screen._conquer_support_overflow_rects = []
    entries = [
        {'kind': 'support_bonus', 'label': 'Support', 'value': '+4', 'numeric_value': 4,
         'suit': 'Hearts', 'figure': _fighter(100, 'Supporter 0', 4, 1, (90, 150, 120), suit='Hearts')},
        {'kind': 'land_bonus', 'label': 'Land', 'value': '+2', 'numeric_value': 2,
         'suit': 'Hearts', 'figure': None, 'source_figure_ids': [100]},
        {'kind': 'buffs_allies', 'label': 'Buff', 'value': '+4', 'numeric_value': 4,
         'figure': _fighter(101, 'Supporter 1', 4, 1, (90, 150, 120), suit='Hearts')},
        {'kind': 'buffs_allies_defence', 'label': 'Wall', 'value': '+5', 'numeric_value': 5,
         'figure': _fighter(102, 'Supporter 2', 5, 1, (90, 150, 120), suit='Clubs')},
        {'kind': 'blocks_bonus', 'label': 'Block', 'value': 'Block', 'numeric_value': 0,
         'figure': _fighter(103, 'Supporter 3', 4, 1, (90, 150, 120), suit='Spades')},
        {'kind': 'distance_attack', 'label': 'Range', 'value': '-3', 'numeric_value': 3,
         'figure': _fighter(104, 'Supporter 4', 3, 1, (90, 150, 120), suit='Spades')},
    ]
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (0, 0))

    ConquerGameScreen._draw_conquer_lane_support_rail(
        screen,
        pygame.Rect(300, 160, 56, 240),
        entries,
        is_player=True,
    )

    assert len(screen._conquer_support_badge_rects) == 1
    assert len(screen._conquer_support_overflow_rects) == 1
    overflow = screen._conquer_support_overflow_rects[0]
    assert len(overflow['entries']) == len(entries) - 1
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: overflow['rect'].center)
    assert ConquerGameScreen._current_conquer_support_overflow_entry(screen) == overflow
    ConquerGameScreen._draw_conquer_support_overflow_popover(screen)


def test_tactic_flight_overlay_draws_nonblank_pill(monkeypatch):
    from config import settings
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen._tactic_flight_animation = {
        'move': {'id': 7, 'family_name': 'Sword', 'value': 9},
        'source': pygame.Rect(40, 80, 120, 50),
        'target': pygame.Rect(800, 880, 160, 70),
        'started_at': 1000,
        'duration': ConquerGameScreen.TACTIC_FLIGHT_MS,
    }
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1120)

    ConquerGameScreen._draw_tactic_flight_animation(screen)

    assert screen._tactic_flight_animation is not None
    assert _rect_has_non_background_pixel(window, pygame.Rect(520, 560, 140, 90))

    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1400)
    ConquerGameScreen._draw_tactic_flight_animation(screen)

    assert screen._tactic_flight_animation is None


def test_conquer_lane_figure_full_power_includes_modifiers():
    from game.screens.conquer_game_screen import ConquerGameScreen

    fighter = _fighter(10, 'Hero', 8, 1, (200, 200, 200),
                       suit='Hearts', field='village')
    healer = _fighter(20, 'Healer', 4, 1, (90, 190, 120),
                      suit='Hearts', field='village', buffs_allies=True)
    enemy = _fighter(30, 'Foe', 5, 2, (200, 90, 90),
                    suit='Spades', field='military')
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(
        mode='conquer', conquer_move_model='tactics_hand',
        player_id=1, opponent_id=2,
        advancing_player_id=1, advancing_figure_id=10,
        defending_figure_id=30,
        advancing_figure_id_2=None, defending_figure_id_2=None,
        battle_turn_player_id=1, battle_round=1, last_battle_result=None,
        opponent_name='Foes', land_suit_bonus_suit=None,
        land_suit_bonus_value=None, conquer_tactics=[],
    ))
    screen.subscreens = {
        'field': SimpleNamespace(figures=[fighter, healer, enemy], icon_cache={}),
        'battle': SimpleNamespace(opp_played=[]),
    }

    diff = ConquerGameScreen._conquer_lane_figure_diff(screen)
    # Player Hero (8) + buffs from healer (+4) - opponent Foe (5) = 7
    assert diff == 7

    p_support = ConquerGameScreen._conquer_lane_support_entries(
        screen, [fighter], [enemy], is_player=True)
    o_support = ConquerGameScreen._conquer_lane_support_entries(
        screen, [fighter], [enemy], is_player=False)
    full = ConquerGameScreen._conquer_lane_figure_full_power(
        screen, fighter, support_entries=p_support,
        enemy_support_entries=o_support, is_player=True)
    assert full == 12  # 8 + 4 buff


def test_handle_conquer_lane_figure_click_opens_detail_box():
    from game.screens.conquer_game_screen import ConquerGameScreen

    fighter = _fighter(10, 'Hero', 8, 1, (200, 200, 200))
    opened = {'icon': None}

    def opener(icon):
        opened['icon'] = icon

    icon_obj = SimpleNamespace(figure=fighter)
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace())
    screen.subscreens = {
        'field': SimpleNamespace(
            icon_cache={10: icon_obj},
            figure_icons=[icon_obj],
            _open_tactics_hand_battle_detail=opener,
        ),
    }
    screen._conquer_lane_figure_rects = [
        {'rect': pygame.Rect(100, 100, 50, 50), 'figure': fighter, 'is_player': True},
    ]
    handled = ConquerGameScreen._handle_conquer_lane_figure_click(screen, (110, 110))
    assert handled is True
    assert opened['icon'] is icon_obj

    # Outside click does nothing.
    opened['icon'] = None
    assert ConquerGameScreen._handle_conquer_lane_figure_click(screen, (10, 10)) is False
    assert opened['icon'] is None


def test_tactics_rail_gamble_combine_dismantle_enabled_outside_my_turn():
    from game.components.conquer_tactics_rail import (
        ACTION_COMBINE, ACTION_DISMANTLE, ACTION_GAMBLE, ConquerTacticsRail,
    )

    dagger_a = _move(1, family='Dagger', suit='Hearts', rank='3', value=3)
    dagger_b = _move(2, family='Dagger', suit='Diamonds', rank='5', value=5)
    double = _move(3, family='Dagger', suit='Hearts', rank='3', value=8,
                   card_id_b=99, suit_b='Diamonds')
    moves = [dagger_a, dagger_b, double]
    parent = SimpleNamespace(
        window=pygame.Surface((100, 100)),
        state=SimpleNamespace(game=SimpleNamespace(
            battle_turn_player_id=999,  # not my turn
            player_id=1, battle_round=2, last_battle_result=None,
        )),
        _current_conquer_tactics=lambda: list(moves),
    )
    rail = ConquerTacticsRail(parent)

    # Gamble while it's not my turn:
    rail._selected_id = dagger_a['id']
    rail._trigger_action(ACTION_GAMBLE)
    pending = rail.consume_pending_action()
    assert pending and pending['action'] == ACTION_GAMBLE

    # Dismantle a double dagger while it's not my turn:
    rail._selected_id = double['id']
    rail._trigger_action(ACTION_DISMANTLE)
    pending = rail.consume_pending_action()
    assert pending and pending['action'] == ACTION_DISMANTLE

    # Combine two single daggers:
    rail._selected_id = dagger_a['id']
    rail._combine_partner_id = dagger_b['id']
    rail._combine_pending = True
    rail._trigger_action(ACTION_COMBINE)
    pending = rail.consume_pending_action()
    assert pending and pending['action'] == ACTION_COMBINE
    assert pending['partner']['id'] == dagger_b['id']


def test_round_ledger_total_includes_figure_diff():
    from game.components.conquer_round_ledger import ConquerRoundLedger

    parent = SimpleNamespace(
        window=pygame.Surface((100, 100)),
        state=SimpleNamespace(game=SimpleNamespace()),
        _conquer_lane_figure_diff=lambda: 6,
    )
    ledger = ConquerRoundLedger(parent)
    you_per = [_move(1, value=5), None, None]
    opp_per = [_move(2, value=3), None, None]
    total = ledger._total_diff(you_per, opp_per)
    # round1 diff (5-3=2) + figure diff (6) = 8
    assert total == 8


def test_current_conquer_tactics_filters_by_displayed_step(monkeypatch):
    """Spell-driven tactics with revealed_step_index ahead of the displayed
    step are hidden, and spell_purged tactics whose discarded_step_index is
    still in the future are replayed as available."""
    from game.screens.conquer_game_screen import ConquerGameScreen
    from utils import game_service

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(
        game_id=42, player_id=7, conquer_tactics=[],
        battle_turn_player_id=None, battle_round=0,
        _game_data_version=0, conquer_resolution_step=3,
    ))
    screen._is_tactics_hand_game = lambda: True
    screen._conquer_timeline_panel = SimpleNamespace(
        currently_resolved_step_index=lambda *a, **kw: 1,
    )

    fake_state = {
        'player_tactics': [
            {'id': 1, 'status': 'available', 'revealed_step_index': None,
             'discarded_step_index': None, 'family_name': 'Dagger'},
            # Newer than displayed_step (=1) → hidden.
            {'id': 2, 'status': 'available', 'revealed_step_index': 2,
             'discarded_step_index': None, 'family_name': 'Sword'},
            # Purged at step 5 — still alive at displayed_step=1 → replayed.
            {'id': 3, 'status': 'spell_purged', 'revealed_step_index': None,
             'discarded_step_index': 5, 'family_name': 'Bow'},
            # Purged at step 1 (≤ displayed) → hidden.
            {'id': 4, 'status': 'spell_purged', 'revealed_step_index': None,
             'discarded_step_index': 1, 'family_name': 'Staff'},
        ],
        'opponent_tactics': [],
        'conquer_resolution_step': 3,
    }
    monkeypatch.setattr(game_service, 'get_battle_state',
                        lambda *a, **kw: fake_state)

    visible = screen._current_conquer_tactics()
    visible_ids = {t['id'] for t in visible}
    assert visible_ids == {1, 3}
    replayed = next(t for t in visible if t['id'] == 3)
    assert replayed['status'] == 'available'


def test_timeline_panel_currently_resolved_step_index():
    """Timeline panel mirrors the server step minus the in-flight offset."""
    from game.components.conquer_timeline_panel import ConquerTimelinePanel

    panel = ConquerTimelinePanel(pygame.Surface((10, 10)))
    screen = SimpleNamespace(
        _conquer_resolution_step_server=4,
        state=SimpleNamespace(game=SimpleNamespace(conquer_resolution_step=4)),
    )
    assert panel.currently_resolved_step_index(screen) == 4
    panel._displayed_step_offset = 1
    assert panel.currently_resolved_step_index(screen) == 3
    panel._displayed_step_offset = 99
    assert panel.currently_resolved_step_index(screen) == 0  # clamped
