# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Render smoke tests for the unified conquer tactics UI."""

from types import SimpleNamespace

import pygame


def _move(move_id, *, family='Dagger', suit='Hearts', rank='A', value=5,
          status='available', played_round=None, card_id_b=None, suit_b=None):
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
        'source': 'config',
    }


def _fighter(fig_id, name, value, player_id, color):
    icon = pygame.Surface((64, 64), pygame.SRCALPHA)
    icon.fill(color)
    frame = pygame.Surface((80, 80), pygame.SRCALPHA)
    pygame.draw.circle(frame, (238, 206, 111), (40, 40), 38, 4)
    return SimpleNamespace(
        id=fig_id,
        name=name,
        player_id=player_id,
        value=value,
        number_card=SimpleNamespace(value=value),
        get_value=lambda: value,
        family=SimpleNamespace(
            icon_img=icon,
            icon_img_small=icon,
            frame_img=frame,
        ),
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
    assert len(rail._cell_rects) == layout.cells_visible
    assert rail._scroll_down_rect is not None

    font = settings.get_font(settings.FS_SMALL, bold=True)
    fitted = ConquerTacticsRail._fit_text(
        'Very Long Tactical Dagger Name That Must Clip', font, 80)
    assert font.size(fitted)[0] <= 80
    assert fitted.endswith('...')


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
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {
        'field': SimpleNamespace(figures=[attacker, defender]),
    }

    ConquerGameScreen._draw_conquer_duel_lane(screen)

    lane_rect = compute_conquer_layout(
        settings.SCREEN_WIDTH,
        settings.SCREEN_HEIGHT,
        mode='battle',
    ).battlefield.duel_lane.rect
    player_figures, opponent_figures = ConquerGameScreen._conquer_lane_figures(screen)

    assert player_figures == [attacker]
    assert opponent_figures == [defender]
    assert _rect_has_non_background_pixel(window, lane_rect)