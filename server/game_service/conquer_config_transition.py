# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Card-lock transitions for conquer configurations."""

from models import db


# Conquer preludes that remain legal when a winning attack config becomes the
# new defence config.  Blitzkrieg and Invader Swap are attack-only; the legacy
# Fill up to 10 entry remains supported only for old battle-state replay.
_TRANSFERABLE_DEFENCE_PRELUDE_SPELLS = frozenset({
    'Draw 2 MainCards', 'Dump Cards', 'Forced Deal',
    'Poison', 'Health Boost', 'All Seeing Eye', 'Explosion',
    'Peasant War', 'Civil War',
    'Royal Decree', 'Copy Figure', 'Landslide', 'Draw 4 MainCards',
})


def snapshot_collection_cards(card_ids, include_id=False):
    """Snapshot collection-card suit and rank in requested ID order."""
    from models import CollectionCard

    unique_ids = []
    seen_ids = set()
    for card_id in card_ids or []:
        if not card_id or card_id in seen_ids:
            continue
        seen_ids.add(card_id)
        unique_ids.append(card_id)
    if not unique_ids:
        return []

    cards = CollectionCard.query.filter(CollectionCard.id.in_(unique_ids)).all()
    cards_by_id = {card.id: card for card in cards}
    snapshot = []
    for card_id in unique_ids:
        card = cards_by_id.get(card_id)
        if not card:
            continue
        data = {'suit': card.suit, 'rank': card.rank}
        if include_id:
            data['id'] = card.id
        snapshot.append(data)
    return snapshot


def snapshot_config_battle_cards(
    cfg,
    include_id=False,
    *,
    config_battle_card_ids,
    snapshot_cards,
):
    """Snapshot cards consumed with a config's battle and spell package."""
    return snapshot_cards(
        config_battle_card_ids(cfg),
        include_id=include_id,
    )


def consume_config_figure_cards(cfg, exclude_card_ids=None):
    """Delete a config's figure cards and figure rows, except exclusions."""
    from models import CollectionCard, LandConfigFigure

    excluded = set(exclude_card_ids or [])
    figures = LandConfigFigure.query.filter_by(config_id=cfg.id).all()
    card_ids = []
    for figure in figures:
        if figure.card_ids:
            card_ids.extend(
                card_id
                for card_id in figure.card_ids
                if card_id not in excluded
            )

    if card_ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(card_ids)
        ).delete(synchronize_session='fetch')

    for figure in figures:
        db.session.delete(figure)


def _config_battle_card_ids(cfg):
    """Return battle-move/modifier/spell card IDs referenced by a land config."""
    if not cfg:
        return []
    card_ids = []
    for move in cfg.battle_moves:
        if move.card_id:
            card_ids.append(move.card_id)
    for arr in (cfg.modifier_card_ids, cfg.spell_card_ids,
                cfg.prelude_spell_card_ids, cfg.counter_spell_card_ids):
        if arr:
            card_ids.extend(arr)
    return card_ids


def _consume_config_battle_cards(cfg):
    """Delete collection cards used for battle moves, modifiers, and spells.

    Spell cards (main, prelude, counter) are one-shot: they are consumed
    together with battle move and modifier cards.  Stale references on the
    config are cleared so the row can either be re-purposed or deleted
    safely afterwards.
    """
    from models import CollectionCard, LandConfigBattleMove

    moves = LandConfigBattleMove.query.filter_by(config_id=cfg.id).all()
    card_ids = _config_battle_card_ids(cfg)

    if card_ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(card_ids)
        ).delete(synchronize_session='fetch')

    # Delete the move records
    for m in moves:
        db.session.delete(m)

    # Clear stale references so the cfg cannot accidentally be reused
    cfg.modifier_card_ids = []
    cfg.spell_card_ids = []
    cfg.prelude_spell_card_ids = []
    cfg.counter_spell_card_ids = []
    cfg.spell_name = None
    cfg.spell_target_figure_id = None
    cfg.prelude_spell_name = None
    cfg.prelude_spell_data = None
    cfg.counter_spell_name = None
    cfg.counter_spell_data = None
    cfg.counter_spell_target_figure_id = None


def _return_config_attack_only_cards(cfg):
    """Unlock and clear the attack-only cards from a surviving config.

    Used when a winning attacker's conquer config becomes the new defence: its
    figures, battle-move tactics, and defence-compatible prelude carry over to
    the defence (so the conquered land is defended automatically), while the
    battle modifier, in-battle spell, counter spell, and any conquer-only
    prelude are unlocked and returned to the collection.
    """
    from models import CollectionCard

    keep_prelude = (
        cfg.prelude_spell_name in _TRANSFERABLE_DEFENCE_PRELUDE_SPELLS
    )
    card_ids = []
    returned_card_arrays = [
        cfg.modifier_card_ids,
        cfg.spell_card_ids,
        cfg.counter_spell_card_ids,
    ]
    if not keep_prelude:
        returned_card_arrays.append(cfg.prelude_spell_card_ids)
    for arr in returned_card_arrays:
        if arr:
            card_ids.extend(arr)
    if card_ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(card_ids)
        ).update({
            CollectionCard.locked: False,
            CollectionCard.lock_type: None,
            CollectionCard.lock_ref_id: None,
        }, synchronize_session='fetch')
    cfg.battle_modifier = None
    cfg.modifier_card_ids = []
    cfg.spell_name = None
    cfg.spell_target_figure_id = None
    cfg.spell_card_ids = []
    if not keep_prelude:
        cfg.prelude_spell_name = None
        cfg.prelude_spell_data = None
        cfg.prelude_spell_card_ids = []
    cfg.counter_spell_name = None
    cfg.counter_spell_data = None
    cfg.counter_spell_card_ids = []
    cfg.counter_spell_target_figure_id = None


def _rekey_config_lock_types(cfg, new_config_type):
    """Re-key the lock_type of every CollectionCard locked by this config.

    Used when a winning attacker's conquer config is converted into the
    new defence config: every 'conquer_*' lock_type must become 'defence_*'
    so subsequent unlock/wipe logic recognises them.
    """
    from models import CollectionCard

    mapping = {
        'conquer_figure':   f'{new_config_type}_figure',
        'conquer_move':     f'{new_config_type}_move',
        'conquer_modifier': f'{new_config_type}_modifier',
        'conquer_spell':    f'{new_config_type}_spell',
        'conquer_prelude':  f'{new_config_type}_prelude',
        'conquer_counter':  f'{new_config_type}_counter',
    }

    # Gather every card id still locked by this cfg. Attack-only cards have
    # already been returned, while a defence-compatible prelude remains.
    card_ids = []
    for fig in cfg.figures:
        if fig.card_ids:
            card_ids.extend(fig.card_ids)
    for move in cfg.battle_moves:
        if move.card_id:
            card_ids.append(move.card_id)
    for arr in (cfg.modifier_card_ids, cfg.spell_card_ids,
                cfg.prelude_spell_card_ids, cfg.counter_spell_card_ids):
        if arr:
            card_ids.extend(arr)
    if not card_ids:
        return

    cards = CollectionCard.query.filter(
        CollectionCard.id.in_(card_ids)
    ).all()
    for cc in cards:
        new_lt = mapping.get(cc.lock_type)
        if new_lt:
            cc.lock_type = new_lt


def _wipe_land_config_return_unlooted(cfg, looted_card_ids=None):
    """Delete a config, deleting only looted cards and unlocking the rest."""
    from models import CollectionCard, LandConfigFigure, LandConfigBattleMove

    looted = set(looted_card_ids or [])
    card_ids = []
    for fig in cfg.figures:
        if fig.card_ids:
            card_ids.extend(fig.card_ids)
    for move in cfg.battle_moves:
        if move.card_id:
            card_ids.append(move.card_id)
    for arr in (cfg.modifier_card_ids, cfg.spell_card_ids,
                cfg.prelude_spell_card_ids, cfg.counter_spell_card_ids):
        if arr:
            card_ids.extend(arr)

    unlock_ids = [cid for cid in card_ids if cid not in looted]
    if unlock_ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(unlock_ids)
        ).update({
            CollectionCard.locked: False,
            CollectionCard.lock_type: None,
            CollectionCard.lock_ref_id: None,
        }, synchronize_session='fetch')
    if looted:
        CollectionCard.query.filter(
            CollectionCard.id.in_(looted)
        ).delete(synchronize_session='fetch')

    LandConfigBattleMove.query.filter_by(config_id=cfg.id).delete()
    LandConfigFigure.query.filter_by(config_id=cfg.id).delete()
    db.session.delete(cfg)


def _destroy_land_config(cfg, exclude_card_ids=None):
    """Delete a land config and DELETE every collection card it referenced.

    Used when an attacker loses: all cards committed to the attack are
    consumed.  `exclude_card_ids` lets the caller protect cards that have
    already been transferred elsewhere (e.g. looted by the defender).
    """
    from models import CollectionCard, LandConfigFigure, LandConfigBattleMove

    excluded = set(exclude_card_ids or [])
    card_ids = []
    for fig in cfg.figures:
        if fig.card_ids:
            card_ids.extend(cid for cid in fig.card_ids if cid not in excluded)
    for move in cfg.battle_moves:
        if move.card_id and move.card_id not in excluded:
            card_ids.append(move.card_id)
    for arr in (cfg.modifier_card_ids, cfg.spell_card_ids,
                cfg.prelude_spell_card_ids, cfg.counter_spell_card_ids):
        if arr:
            card_ids.extend(cid for cid in arr if cid not in excluded)

    if card_ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(card_ids)
        ).delete(synchronize_session='fetch')

    LandConfigBattleMove.query.filter_by(config_id=cfg.id).delete()
    LandConfigFigure.query.filter_by(config_id=cfg.id).delete()
    db.session.delete(cfg)


def _wipe_land_config(cfg):
    """Delete a land config and all its figures, moves, and unlock cards."""
    from models import CollectionCard, LandConfigFigure, LandConfigBattleMove

    # Collect all card IDs to unlock
    card_ids = []
    for fig in cfg.figures:
        if fig.card_ids:
            card_ids.extend(fig.card_ids)
    for move in cfg.battle_moves:
        if move.card_id:
            card_ids.append(move.card_id)
    if cfg.modifier_card_ids:
        card_ids.extend(cfg.modifier_card_ids)
    if cfg.spell_card_ids:
        card_ids.extend(cfg.spell_card_ids)
    if cfg.prelude_spell_card_ids:
        card_ids.extend(cfg.prelude_spell_card_ids)
    if cfg.counter_spell_card_ids:
        card_ids.extend(cfg.counter_spell_card_ids)

    # Unlock all cards
    if card_ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(card_ids)
        ).update({
            CollectionCard.locked: False,
            CollectionCard.lock_type: None,
            CollectionCard.lock_ref_id: None,
        }, synchronize_session='fetch')

    # Delete figures and moves
    LandConfigBattleMove.query.filter_by(config_id=cfg.id).delete()
    LandConfigFigure.query.filter_by(config_id=cfg.id).delete()
    db.session.delete(cfg)


# Keep the historical route-level repr and pickle lookup while routes.games
# re-exports this canonical implementation.
_return_config_attack_only_cards.__module__ = 'routes.games'
_rekey_config_lock_types.__module__ = 'routes.games'
_wipe_land_config_return_unlooted.__module__ = 'routes.games'
_destroy_land_config.__module__ = 'routes.games'
_wipe_land_config.__module__ = 'routes.games'
_config_battle_card_ids.__module__ = 'routes.games'
_consume_config_battle_cards.__module__ = 'routes.games'
