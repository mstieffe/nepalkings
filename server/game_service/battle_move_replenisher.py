# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Helpers for rebuilding automated conquer-defender battle moves.

Conquer preludes/counters such as Forced Deal and Dump Cards intentionally
disrupt pre-built battle moves by moving or recycling their backing cards.
The human conquerer can re-select moves from the resulting hand cards, but an
automated defender cannot.  This module keeps the disruption intact and then
lets the automated defender reserve replacement moves from cards that are now
available in its runtime hand.
"""

import logging

from sqlalchemy import or_

from models import db, BattleMove, Figure, MainCard


logger = logging.getLogger('nepalkings.game_service.battle_move_replenisher')

MAX_CONQUER_BATTLE_MOVES = 3

_RANK_TO_FAMILY = {
    'J': 'Call Villager',
    'Q': 'Block',
    'A': 'Call Military',
    'K': 'Call King',
    '7': 'Dagger',
    '8': 'Dagger',
    '9': 'Dagger',
    '10': 'Dagger',
}

_CALL_FAMILY_TO_FIELD = {
    'Call Villager': 'village',
    'Call Military': 'military',
    'Call King': 'castle',
}

_SPECIAL_RANK_TIEBREAK = {
    'K': 40,
    'A': 30,
    'Q': 20,
    'J': 10,
}


def _choice_value(value):
    return value.value if hasattr(value, 'value') else value


def _card_rank(card):
    return str(_choice_value(card.rank))


def _card_suit(card):
    return str(_choice_value(card.suit))


def _family_for_rank(rank):
    return _RANK_TO_FAMILY.get(str(rank))


def _call_figure_id_for_family(game_id, player_id, family_name):
    field = _CALL_FAMILY_TO_FIELD.get(family_name)
    if not field:
        return None
    figure = Figure.query.filter_by(
        game_id=game_id,
        player_id=player_id,
        field=field,
    ).filter(
        Figure.checkmate.is_(False)
    ).order_by(Figure.id.asc()).first()
    return figure.id if figure else None


def _replacement_sort_key(card):
    """Prefer stronger deterministic replacement moves.

    Number cards use their battle value directly.  Call/Block cards have lower
    raw values in the database, so the tiebreak lets deterministic auto-picks
    prefer tactically richer cards when values are otherwise close.
    """
    rank = _card_rank(card)
    value = int(card.value or 0)
    tie = _SPECIAL_RANK_TIEBREAK.get(rank, value)
    return (-value, -tie, card.id)


def _eligible_replacement_cards(game_id, player_id):
    cards = MainCard.query.filter(
        MainCard.game_id == game_id,
        MainCard.player_id == player_id,
        MainCard.in_deck.is_(False),
        MainCard.part_of_figure.is_(False),
        or_(
            MainCard.part_of_battle_move.is_(False),
            MainCard.part_of_battle_move.is_(None),
        ),
    ).all()
    playable = [card for card in cards if _family_for_rank(_card_rank(card))]
    return sorted(playable, key=_replacement_sort_key)


def replenish_automated_conquer_defender_moves(
    game,
    defender_player,
    *,
    max_moves=MAX_CONQUER_BATTLE_MOVES,
    reason='spell',
):
    """Auto-reserve replacement battle moves for a conquer defender.

    Returns a small summary dict.  The caller owns transaction boundaries.
    The helper is intentionally a no-op once active battle rounds have started.
    """
    if not game or not defender_player or game.mode != 'conquer':
        return {'added': 0, 'before': 0, 'after': 0, 'moves': []}

    if game.battle_confirmed and game.battle_turn_player_id is not None:
        current = BattleMove.query.filter_by(
            game_id=game.id,
            player_id=defender_player.id,
        ).count()
        return {'added': 0, 'before': current, 'after': current, 'moves': []}

    before = BattleMove.query.filter_by(
        game_id=game.id,
        player_id=defender_player.id,
    ).count()
    needed = max(0, int(max_moves) - before)
    if needed <= 0:
        return {'added': 0, 'before': before, 'after': before, 'moves': []}

    replacements = []
    for card in _eligible_replacement_cards(game.id, defender_player.id)[:needed]:
        rank = _card_rank(card)
        family_name = _family_for_rank(rank)
        if not family_name:
            continue
        card.part_of_battle_move = True
        move = BattleMove(
            game_id=game.id,
            player_id=defender_player.id,
            family_name=family_name,
            card_id=card.id,
            card_type='main',
            suit=_card_suit(card),
            rank=rank,
            value=int(card.value or 0),
            call_figure_id=_call_figure_id_for_family(
                game.id,
                defender_player.id,
                family_name,
            ),
        )
        db.session.add(move)
        db.session.flush()
        replacements.append(move.serialize())

    after = before + len(replacements)
    if replacements:
        logger.info(
            '[CONQUER_BM_REPLENISH] game=%s defender=%s reason=%s before=%s after=%s added=%s',
            game.id,
            defender_player.id,
            reason,
            before,
            after,
            len(replacements),
        )
    return {
        'added': len(replacements),
        'before': before,
        'after': after,
        'moves': replacements,
    }
