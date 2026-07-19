# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Direct land and configuration mutations after a Conquer victory."""

from datetime import timedelta

from models import LandConfig, db


def apply_attacker_land_config_transition(
    game,
    land,
    attacker_user,
    defender_user,
    defender_looted_ids,
    *,
    now,
    protection_seconds,
    return_config_attack_only_cards,
    rekey_config_lock_types,
    wipe_land_config_return_unlooted,
    wipe_defence_drafts_for_lost_land,
):
    """Transfer the land and convert the winning config into its defence."""
    if land:
        land.owner_user_id = attacker_user.id
        land.kingdom_id = None
        land.owned_since = now()
        protect_seconds = max(int(protection_seconds()), 0)
        if protect_seconds > 0:
            land.conquer_cooldown_until = now() + timedelta(
                seconds=protect_seconds
            )
        else:
            land.conquer_cooldown_until = None

    victory_review_config_id = None
    if game.conquer_config_id:
        attack_config = db.session.get(
            LandConfig,
            game.conquer_config_id,
        )
        if attack_config:
            return_config_attack_only_cards(attack_config)
            attack_config.config_type = 'defence'
            attack_config.land_id = game.land_id
            rekey_config_lock_types(attack_config, 'defence')
            if land:
                land.defence_config_id = attack_config.id
            victory_review_config_id = attack_config.id

    if game.defence_config_id:
        defence_config = db.session.get(
            LandConfig,
            game.defence_config_id,
        )
        if defence_config:
            wipe_land_config_return_unlooted(
                defence_config,
                defender_looted_ids,
            )
    if defender_user:
        wipe_defence_drafts_for_lost_land(
            defender_user.id,
            game.land_id,
        )

    return victory_review_config_id
