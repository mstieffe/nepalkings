"""Helpers for keeping conquer tactics in sync after card mutations."""

import logging

from sqlalchemy import or_

from models import db, ConquerTactic, Figure, MainCard, SideCard


logger = logging.getLogger('nepalkings.game_service.conquer_tactics_service')

MAX_CONQUER_TACTICS = 10
STANDARD_CONQUER_TACTICS = 3

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


def is_tactics_hand_conquer(game):
    return bool(
        game
        and game.mode == 'conquer'
        and (getattr(game, 'conquer_move_model', None) or 'battle_move') == 'tactics_hand'
    )


def _choice_value(value):
    return value.value if hasattr(value, 'value') else value


def _card_rank(card):
    return str(_choice_value(card.rank))


def _card_suit(card):
    return str(_choice_value(card.suit))


def _family_for_rank(rank):
    return _RANK_TO_FAMILY.get(str(rank))


def _replacement_sort_key(card):
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


def _tactic_count(game_id, player_id):
    return ConquerTactic.query.filter_by(
        game_id=game_id,
        player_id=player_id,
    ).filter(
        ConquerTactic.status != 'discarded'
    ).count()


def _empty_result(current=0):
    return {'added': 0, 'before': current, 'after': current, 'tactics': [], 'moves': []}


def _get_card(card_id, card_type):
    if not card_id:
        return None
    card_model = SideCard if card_type == 'side' else MainCard
    return db.session.get(card_model, card_id)


def _restore_source_tactic_if_valid(source_tactic_id, game_id, player_id):
    source = db.session.get(ConquerTactic, source_tactic_id) if source_tactic_id else None
    if not source or source.game_id != game_id or source.player_id != player_id:
        return None
    if source.status != 'discarded':
        return None

    card = _get_card(source.card_id, source.card_type or 'main')
    if not card or card.game_id != game_id or card.player_id != player_id:
        return None
    if card.in_deck or card.part_of_figure:
        return None

    card.part_of_battle_move = True
    source.status = 'available'
    source.played_round = None
    source.call_figure_id = None
    return source.serialize()


def purge_conquer_tactics_referencing_card(game_id, card_id, card_type):
    """Delete ConquerTactic rows tied to a card being moved/recycled."""
    if not card_id:
        return {'deleted': 0, 'restored': []}

    primary = ConquerTactic.query.filter_by(
        game_id=game_id,
        card_id=card_id,
        card_type=card_type,
    ).all()
    secondary = ConquerTactic.query.filter_by(
        game_id=game_id,
        card_id_b=card_id,
        card_type_b=card_type,
    ).all()
    affected = {tactic.id: tactic for tactic in primary}
    affected.update({tactic.id: tactic for tactic in secondary})
    restored = []

    for tactic in affected.values():
        triggered_primary = tactic.card_id == card_id and tactic.card_type == card_type
        triggered_secondary = tactic.card_id_b == card_id and tactic.card_type_b == card_type

        if tactic.source == 'combine':
            partner_card_id = tactic.card_id_b if triggered_primary else tactic.card_id
            partner_card_type = tactic.card_type_b if triggered_primary else tactic.card_type
            partner = _get_card(partner_card_id, partner_card_type or 'main')
            if partner:
                partner.part_of_battle_move = False
                partner.in_deck = False

            partner_source_id = (
                tactic.source_tactic_id_b if triggered_primary else tactic.source_tactic_id_a
            )
            restored_source = _restore_source_tactic_if_valid(
                partner_source_id,
                game_id,
                tactic.player_id,
            )
            if restored_source:
                restored.append(restored_source)

        logger.info(
            '[CONQUER_TACTIC_PURGE] game=%s tactic=%s family=%s player=%s trigger=%s#%s',
            game_id,
            tactic.id,
            tactic.family_name,
            tactic.player_id,
            card_type,
            card_id,
        )
        db.session.delete(tactic)

    return {'deleted': len(affected), 'restored': restored}


def auto_convert_conquer_tactic_cards(
    game,
    player,
    cards,
    *,
    max_tactics=MAX_CONQUER_TACTICS,
    reason='spell',
):
    """Reserve newly gained main cards as available conquer tactics."""
    if not is_tactics_hand_conquer(game) or not player:
        return _empty_result()

    if game.battle_confirmed and game.battle_turn_player_id is not None:
        return _empty_result(_tactic_count(game.id, player.id))

    before = _tactic_count(game.id, player.id)
    remaining = max(0, int(max_tactics) - before)
    if remaining <= 0:
        return _empty_result(before)

    added = []
    seen_card_ids = set()
    next_order = (db.session.query(db.func.max(ConquerTactic.sort_order))
                  .filter_by(game_id=game.id, player_id=player.id).scalar() or 0) + 1
    for card in cards or []:
        if remaining <= 0:
            break
        if not isinstance(card, MainCard):
            continue
        if card.id in seen_card_ids:
            continue
        seen_card_ids.add(card.id)
        if card.game_id != game.id or card.player_id != player.id:
            continue
        if card.in_deck or card.part_of_figure or card.part_of_battle_move:
            continue

        rank = _card_rank(card)
        family_name = _family_for_rank(rank)
        if not family_name:
            continue

        existing = ConquerTactic.query.filter_by(
            game_id=game.id,
            player_id=player.id,
            card_id=card.id,
            card_type='main',
        ).filter(
            ConquerTactic.status != 'discarded'
        ).first()
        if existing:
            card.part_of_battle_move = True
            continue

        card.part_of_battle_move = True
        tactic = ConquerTactic(
            game_id=game.id,
            player_id=player.id,
            card_id=card.id,
            card_type='main',
            family_name=family_name,
            suit=_card_suit(card),
            rank=rank,
            value=int(card.value or 0),
            source='spell',
            status='available',
            call_figure_id=_call_figure_id_for_family(
                game.id,
                player.id,
                family_name,
            ),
            sort_order=next_order,
        )
        db.session.add(tactic)
        db.session.flush()
        serialized = tactic.serialize()
        added.append(serialized)
        next_order += 1
        remaining -= 1

    after = before + len(added)
    if added:
        logger.info(
            '[CONQUER_TACTIC_AUTO] game=%s player=%s reason=%s before=%s after=%s added=%s',
            game.id,
            player.id,
            reason,
            before,
            after,
            len(added),
        )
    return {
        'added': len(added),
        'before': before,
        'after': after,
        'tactics': added,
        'moves': added,
    }


def replenish_automated_conquer_defender_tactics(
    game,
    defender_player,
    *,
    max_tactics=STANDARD_CONQUER_TACTICS,
    reason='spell',
):
    """Auto-reserve replacement tactics for an automated conquer defender."""
    if not is_tactics_hand_conquer(game) or not defender_player:
        return _empty_result()

    if game.battle_confirmed and game.battle_turn_player_id is not None:
        return _empty_result(_tactic_count(game.id, defender_player.id))

    before = _tactic_count(game.id, defender_player.id)
    needed = max(0, int(max_tactics) - before)
    if needed <= 0:
        return _empty_result(before)

    cards = _eligible_replacement_cards(game.id, defender_player.id)[:needed]
    return auto_convert_conquer_tactic_cards(
        game,
        defender_player,
        cards,
        max_tactics=max_tactics,
        reason=reason,
    )
