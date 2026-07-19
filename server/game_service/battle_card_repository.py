# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Persistence operations for cards reserved by battle moves."""

from models import BattleMove, ConquerTactic, Game, MainCard, SideCard, db


def collect_battle_move_cards(
    game_id,
    *,
    is_tactics_hand_conquer,
    get_tactic_card,
):
    """Collect cards reserved by battle move records."""
    game = db.session.get(Game, game_id)
    if is_tactics_hand_conquer(game):
        tactics = ConquerTactic.query.filter_by(
            game_id=game_id,
            status='played',
        ).all()
        cards = []
        for tactic in tactics:
            card = get_tactic_card(tactic)
            if card:
                cards.append((card, tactic.card_type or 'main'))
            card_b = get_tactic_card(tactic, secondary=True)
            if card_b:
                cards.append((card_b, tactic.card_type_b or 'main'))
        return cards, tactics

    moves = BattleMove.query.filter_by(game_id=game_id).all()
    cards = []
    for move in moves:
        if move.card_type == 'side':
            card = db.session.get(SideCard, move.card_id)
        else:
            card = db.session.get(MainCard, move.card_id)
        if card:
            cards.append((card, move.card_type))

        if move.card_id_b is not None:
            card_type_b = move.card_type_b or 'main'
            if card_type_b == 'side':
                card_b = db.session.get(SideCard, move.card_id_b)
            else:
                card_b = db.session.get(MainCard, move.card_id_b)
            if card_b:
                cards.append((card_b, card_type_b))
    return cards, moves


def return_unplayed_battle_move_cards(
    game_id,
    *,
    is_tactics_hand_conquer,
    get_tactic_card,
    logger,
):
    """Return unplayed move cards to their owners and delete their move rows."""
    game = db.session.get(Game, game_id)
    if is_tactics_hand_conquer(game):
        unplayed_tactics = ConquerTactic.query.filter_by(
            game_id=game_id,
            status='available',
        ).all()
        if unplayed_tactics:
            logger.info(
                f"[RETURN_UNPLAYED_TACTICS] game={game_id} returning "
                f"{len(unplayed_tactics)} unplayed tactic cards"
            )
        for tactic in unplayed_tactics:
            card = get_tactic_card(tactic)
            if card:
                card.part_of_battle_move = False
                card.in_deck = False
            card_b = get_tactic_card(tactic, secondary=True)
            if card_b:
                card_b.part_of_battle_move = False
                card_b.in_deck = False
            db.session.delete(tactic)
        return

    unplayed = BattleMove.query.filter_by(game_id=game_id).filter(
        BattleMove.played_round.is_(None)
    ).all()
    if unplayed:
        logger.info(
            f"[RETURN_UNPLAYED] game={game_id} returning "
            f"{len(unplayed)} unplayed BM cards to owners"
        )
    for move in unplayed:
        if move.card_type == 'side':
            card = db.session.get(SideCard, move.card_id)
        else:
            card = db.session.get(MainCard, move.card_id)
        if card:
            card.part_of_battle_move = False
            card.in_deck = False
            logger.debug(
                f"[RETURN_UNPLAYED] bm_id={move.id} card_id={card.id} "
                f"({move.family_name}/{move.suit}) → player {move.player_id}"
            )

        if move.card_id_b is not None:
            card_type_b = move.card_type_b or 'main'
            if card_type_b == 'side':
                card_b = db.session.get(SideCard, move.card_id_b)
            else:
                card_b = db.session.get(MainCard, move.card_id_b)
            if card_b:
                card_b.part_of_battle_move = False
                card_b.in_deck = False

        db.session.delete(move)


def delete_all_battle_moves(game_id):
    """Remove all battle-move and conquer-tactic rows for a game."""
    ConquerTactic.query.filter_by(game_id=game_id).delete()
    BattleMove.query.filter_by(game_id=game_id).delete()


def first_deterministic_returnable_card(game_id, *, collect_cards):
    """Return the stable first battle or orphan card available for recovery."""
    battle_cards, _ = collect_cards(game_id)
    orphaned_main = MainCard.query.filter_by(
        game_id=game_id,
        in_deck=False,
        part_of_figure=False,
        player_id=None,
    ).all()
    orphaned_side = SideCard.query.filter_by(
        game_id=game_id,
        in_deck=False,
        part_of_figure=False,
        player_id=None,
    ).all()
    candidates = (
        battle_cards
        + [(card, 'main') for card in orphaned_main]
        + [(card, 'side') for card in orphaned_side]
    )
    if not candidates:
        return None, None
    return sorted(candidates, key=lambda pair: (pair[1], pair[0].id))[0]
