# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Card validation and round-progression rules for Conquer tactics."""

from game_service.game_mode import is_tactics_hand_conquer
from models import (
    BattleMove,
    ConquerTactic,
    Figure,
    MainCard,
    SideCard,
    db,
)


_CONQUER_CALL_FIELD_MAP = {
    'Call Villager': 'village',
    'Call Military': 'military',
    'Call King': 'castle',
}

_CONQUER_RED_SUITS = {'Hearts', 'Diamonds'}
_CONQUER_BLACK_SUITS = {'Clubs', 'Spades'}
_CONQUER_TACTIC_FAMILY_BY_RANK = {
    '7': 'Dagger',
    '8': 'Dagger',
    '9': 'Dagger',
    '10': 'Dagger',
    'J': 'Call Villager',
    'Q': 'Block',
    'K': 'Call King',
    'A': 'Call Military',
}


def _is_tactics_hand_conquer(game):
    return is_tactics_hand_conquer(game)


def _get_tactic_card(tactic, *, secondary=False):
    card_id = tactic.card_id_b if secondary else tactic.card_id
    card_type = (tactic.card_type_b if secondary else tactic.card_type) or 'main'
    if card_id is None:
        return None
    if card_type == 'side':
        return db.session.get(SideCard, card_id)
    return db.session.get(MainCard, card_id)


def _conquer_tactic_rank(value):
    if value is None:
        return ''
    return str(value.value if hasattr(value, 'value') else value)


def _same_conquer_tactic_colour(suit_a, suit_b):
    return ((suit_a in _CONQUER_RED_SUITS and suit_b in _CONQUER_RED_SUITS)
            or (suit_a in _CONQUER_BLACK_SUITS and suit_b in _CONQUER_BLACK_SUITS))


def _validate_conquer_tactic_family_rank(tactic):
    def _validate_card(card):
        if not card:
            return 'Tactic card is missing'
        if card.game_id != tactic.game_id or card.player_id != tactic.player_id:
            return 'Tactic card does not belong to this player/game'
        if card.in_deck or card.part_of_figure:
            return 'Tactic card is not available'
        return None

    card = _get_tactic_card(tactic)
    card_err = _validate_card(card)
    if card_err:
        return card_err

    if tactic.family_name == 'Double Dagger':
        card_b = _get_tactic_card(tactic, secondary=True)
        card_b_err = _validate_card(card_b)
        if card_b_err:
            return card_b_err

        rank_a = _conquer_tactic_rank(card.rank)
        rank_b = _conquer_tactic_rank(card_b.rank)
        if (_CONQUER_TACTIC_FAMILY_BY_RANK.get(rank_a) != 'Dagger'
                or _CONQUER_TACTIC_FAMILY_BY_RANK.get(rank_b) != 'Dagger'):
            return 'Double Dagger requires two Dagger cards'
        if _conquer_tactic_rank(tactic.rank) != f'{rank_a}+{rank_b}':
            return 'Double Dagger rank does not match its cards'
        return None

    if tactic.card_id_b or tactic.card_type_b:
        return 'Only Double Dagger can use two cards'

    card_rank = _conquer_tactic_rank(card.rank)
    if _conquer_tactic_rank(tactic.rank) != card_rank:
        return 'Tactic rank does not match its card'
    expected_family = _CONQUER_TACTIC_FAMILY_BY_RANK.get(card_rank)
    if not expected_family:
        return 'Tactic rank is not playable in conquer'
    if tactic.family_name != expected_family:
        return 'Tactic family does not match its rank'
    return None


def _battle_player_skipped_round(game, player_id, round_idx):
    skipped = game.battle_skipped_rounds or {}
    rounds = skipped.get(str(player_id), [])
    try:
        round_key = str(int(round_idx))
    except (TypeError, ValueError):
        return False
    return any(str(raw_round) == round_key for raw_round in rounds or [])


def _battle_player_completed_round(game, player_id, round_idx):
    round_idx = int(round_idx or 0)
    if _battle_player_skipped_round(game, player_id, round_idx):
        return True
    if _is_tactics_hand_conquer(game):
        return ConquerTactic.query.filter_by(
            game_id=game.id,
            player_id=player_id,
            status='played',
            played_round=round_idx,
        ).first() is not None
    return BattleMove.query.filter_by(
        game_id=game.id,
        player_id=player_id,
        played_round=round_idx,
    ).first() is not None


def _battle_round_complete(game, round_idx):
    players = list(game.players or [])
    if len(players) < 2:
        return False
    return all(_battle_player_completed_round(game, p.id, round_idx) for p in players)


def _battle_all_rounds_complete(game):
    return all(_battle_round_complete(game, idx) for idx in (0, 1, 2))


def _advance_conquer_tactic_turn(game, player_id):
    other_player = next((p for p in game.players if p.id != player_id), None)
    if not other_player:
        return False

    current_round = int(game.battle_round or 0)
    other_played = ConquerTactic.query.filter_by(
        game_id=game.id,
        player_id=other_player.id,
        status='played',
        played_round=current_round,
    ).first()
    skipped = game.battle_skipped_rounds or {}
    other_skipped = (str(other_player.id) in skipped
                     and current_round in skipped[str(other_player.id)])

    if other_played or other_skipped:
        if current_round < 2:
            game.battle_round = current_round + 1
            game.battle_turn_player_id = game.invader_player_id
        else:
            game.battle_turn_player_id = None
    else:
        game.battle_turn_player_id = other_player.id
    return True


def _validate_conquer_tactic_call_figure(tactic, call_figure_id, player_id, game_id):
    if not call_figure_id:
        return None
    expected_field = _CONQUER_CALL_FIELD_MAP.get(tactic.family_name)
    if expected_field is None:
        return 'This tactic cannot call a figure'
    fig = db.session.get(Figure, call_figure_id)
    if not fig or fig.game_id != game_id or fig.player_id != player_id:
        return 'Call figure does not belong to this player/game'
    if fig.field != expected_field:
        return f'{tactic.family_name} can only call a {expected_field} figure'
    return None


# Keep the historical route-level repr and pickle lookup while routes.games
# re-exports these canonical implementations.
_advance_conquer_tactic_turn.__module__ = 'routes.games'
_battle_all_rounds_complete.__module__ = 'routes.games'
_battle_player_completed_round.__module__ = 'routes.games'
_battle_player_skipped_round.__module__ = 'routes.games'
_battle_round_complete.__module__ = 'routes.games'
_conquer_tactic_rank.__module__ = 'routes.games'
_get_tactic_card.__module__ = 'routes.games'
_is_tactics_hand_conquer.__module__ = 'routes.games'
_same_conquer_tactic_colour.__module__ = 'routes.games'
_validate_conquer_tactic_call_figure.__module__ = 'routes.games'
_validate_conquer_tactic_family_rank.__module__ = 'routes.games'
