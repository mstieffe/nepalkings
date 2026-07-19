# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Post-battle entity cleanup and transient-state reset operations."""

from models import (
    ActiveSpell,
    CardToFigure,
    Figure,
    MainCard,
    SideCard,
    db,
)


def destroy_figure_and_collect_cards(figure):
    """Delete a figure and detach its cards for caller-directed recovery."""
    card_associations = CardToFigure.query.filter_by(figure_id=figure.id).all()
    cards = []
    for association in card_associations:
        if association.card_type == 'main':
            card = db.session.get(MainCard, association.card_id)
        else:
            card = db.session.get(SideCard, association.card_id)
        if card:
            card.part_of_figure = False
            card.player_id = None
            cards.append((card, association.card_type))

    CardToFigure.query.filter_by(figure_id=figure.id).delete()
    db.session.delete(figure)
    return cards


def clear_battle_state(game):
    """Reset all battle and advance state after resolution."""
    game.advancing_figure_id = None
    game.advancing_figure_id_2 = None
    game.advancing_player_id = None
    game.defending_figure_id = None
    game.defending_figure_id_2 = None
    game.battle_modifier = []
    game.battle_confirmed = False
    game.battle_decisions = None
    game.battle_moves_confirmed = None
    game.fold_outcome = None
    game.fold_winner_id = None
    game.auto_loss_reason = None
    game.auto_loss_detail = None
    game.battle_round = 0
    game.battle_turn_player_id = None
    game.battle_skipped_rounds = None
    game.battle_round_deadline_round = None
    game.battle_round_deadline_at = None
    game.battle_gamble_counts = None
    game.battle_gamble_previews = None


def collect_resting_figure_ids(game):
    """Return resting battle-participant IDs in battle-slot order."""
    resting = []
    for figure_id in (
        game.advancing_figure_id,
        game.advancing_figure_id_2,
        game.defending_figure_id,
        game.defending_figure_id_2,
    ):
        if figure_id is not None:
            figure = db.session.get(Figure, figure_id)
            if figure and figure.rest_after_attack:
                resting.append(figure_id)
    return resting or None


def deactivate_all_spells(game):
    """Deactivate every active spell belonging to a game."""
    active_spells = ActiveSpell.query.filter_by(
        game_id=game.id,
        is_active=True,
    ).all()
    for spell in active_spells:
        spell.is_active = False
