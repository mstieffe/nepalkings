# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Persistence and progression updates for a resolved Conquer outcome."""

from models import Kingdom, LandAttackLog, db


def record_conquer_outcome(
    game,
    land,
    attacker_user,
    defender_user,
    *,
    attacker_won,
    is_ai_defender,
    attacker_first_conquest_attempt,
    card_won_suit,
    card_won_rank,
    card_lost_suit,
    card_lost_rank,
    deleted_kingdom_id,
    deleted_kingdom_name,
    loot_gained_cards,
    lost_kingdom_id,
    create_kingdom_loot_events,
    now,
    logger,
):
    """Record the attack, progression, and paired loot inbox events."""
    try:
        from onboarding_service import ensure_daily_quest

        ensure_daily_quest(attacker_user)
        if defender_user and not is_ai_defender:
            ensure_daily_quest(defender_user)
    except Exception:
        logger.exception("Failed to refresh daily quest before conquer result")

    log = LandAttackLog(
        land_id=game.land_id,
        attacker_user_id=attacker_user.id,
        defender_user_id=(
            defender_user.id
            if defender_user and not is_ai_defender
            else None
        ),
        result='attacker_won' if attacker_won else 'defender_won',
        card_won_suit=card_won_suit,
        card_won_rank=card_won_rank,
        card_lost_suit=card_lost_suit,
        card_lost_rank=card_lost_rank,
        kingdom_deleted_id=deleted_kingdom_id,
        kingdom_deleted_name=deleted_kingdom_name,
        seen_by_attacker=False,
        seen_by_defender=False,
    )
    db.session.add(log)
    db.session.flush()

    attacker_first_conquest = False
    try:
        from onboarding_service import mark_step

        if attacker_user and attacker_won:
            # Base "first conquest" on prior WINS only, so a no-penalty
            # tutorial loss does not disqualify the eventual retry win.
            prior_attacker_wins = LandAttackLog.query.filter(
                LandAttackLog.attacker_user_id == attacker_user.id,
                LandAttackLog.result == 'attacker_won',
                LandAttackLog.id != log.id,
            ).count()
            attacker_first_conquest = prior_attacker_wins == 0

        # The first tutorial loss keeps the retry path open. All other battles
        # complete the onboarding step as before.
        if attacker_user and (
            attacker_won or not attacker_first_conquest_attempt
        ):
            mark_step(attacker_user, 'finish_first_conquer_battle')
        if defender_user and not is_ai_defender:
            mark_step(defender_user, 'finish_first_conquer_battle')
    except Exception:
        logger.exception("Failed to update conquer onboarding progress")

    if attacker_won:
        gained_kingdom_id = land.kingdom_id if land else None
        if attacker_first_conquest and gained_kingdom_id:
            try:
                from kingdom_service import seed_first_conquest_production

                seeded_kingdom = db.session.get(
                    Kingdom,
                    gained_kingdom_id,
                )
                if (
                    seeded_kingdom
                    and seeded_kingdom.owner_user_id == attacker_user.id
                ):
                    seed_first_conquest_production(
                        seeded_kingdom,
                        now=now(),
                    )
            except Exception:
                logger.exception("Failed to seed first-conquest production")

        lost_user_for_event = (
            None
            if is_ai_defender
            else (defender_user.id if defender_user else None)
        )
        create_kingdom_loot_events(
            attack_log_id=log.id,
            land_id=game.land_id,
            gained_user_id=attacker_user.id if attacker_user else None,
            lost_user_id=lost_user_for_event,
            gained_kingdom_id=gained_kingdom_id,
            lost_kingdom_id=lost_kingdom_id,
            source='attacker_win',
            cards=loot_gained_cards,
        )
    else:
        create_kingdom_loot_events(
            attack_log_id=log.id,
            land_id=game.land_id,
            gained_user_id=(
                defender_user.id
                if defender_user and not is_ai_defender
                else None
            ),
            lost_user_id=attacker_user.id if attacker_user else None,
            gained_kingdom_id=lost_kingdom_id,
            lost_kingdom_id=None,
            source='defender_win',
            cards=loot_gained_cards,
        )

    return log, attacker_first_conquest
