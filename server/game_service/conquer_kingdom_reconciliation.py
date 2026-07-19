# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom topology and progression reconciliation after Conquer."""

from models import Kingdom, KingdomNotification, Land, db


def _reconcile_affected_regions(land, split_transfer_summary, now):
    affected_regions = {land.region} if land and land.region else set()
    transferred_ids = (
        (split_transfer_summary or {}).get('transferred_land_ids')
        or []
    )
    for transferred_id in transferred_ids:
        transferred_land = db.session.get(Land, transferred_id)
        if transferred_land and transferred_land.region:
            affected_regions.add(transferred_land.region)

    if not affected_regions:
        return

    from region_service import reconcile_region_champion

    champion_now = now()
    for affected_region in sorted(affected_regions):
        reconcile_region_champion(
            affected_region,
            now=champion_now,
            commit=False,
        )


def _award_land_transfer_xp(
    land,
    attacker_user,
    split_transfer_summary,
    *,
    award_kingdom_xp,
    xp_for_land_tier,
):
    if not land or not land.kingdom_id:
        return

    joined_kingdom = db.session.get(Kingdom, land.kingdom_id)
    if (
        not joined_kingdom
        or joined_kingdom.owner_user_id != attacker_user.id
    ):
        return

    award_kingdom_xp(
        joined_kingdom,
        xp_for_land_tier(int(land.tier or 0)),
        reason='conquer',
    )
    collateral_ids = set(
        (split_transfer_summary or {}).get('transferred_land_ids')
        or []
    )
    for collateral_id in collateral_ids:
        collateral_land = db.session.get(Land, collateral_id)
        if (
            collateral_land
            and collateral_land.owner_user_id == attacker_user.id
        ):
            award_kingdom_xp(
                joined_kingdom,
                xp_for_land_tier(int(collateral_land.tier or 0)),
                reason='conquer_split',
            )


def _record_dissolved_kingdom(
    lost_kingdom_id,
    lost_kingdom_name,
    old_land_owner_id,
    *,
    logger,
):
    if (
        not lost_kingdom_id
        or db.session.get(Kingdom, lost_kingdom_id) is not None
    ):
        return None, None

    deleted_kingdom_name = (
        lost_kingdom_name
        or f'Kingdom #{lost_kingdom_id}'
    )
    if old_land_owner_id:
        try:
            db.session.add(KingdomNotification(
                user_id=old_land_owner_id,
                kind='kingdom_dissolved',
                kingdom_id=lost_kingdom_id,
                payload={'kingdom_name': deleted_kingdom_name},
            ))
        except Exception as notification_error:
            logger.warning(
                'Failed to record kingdom_dissolved notification: %s',
                notification_error,
            )
    return lost_kingdom_id, deleted_kingdom_name


def reconcile_conquered_land_kingdom(
    land,
    attacker_user,
    defender_user,
    *,
    land_id,
    old_land_owner_id,
    lost_kingdom_id,
    lost_kingdom_name,
    now,
    clear_split_transfer_defences,
    record_split_transfer_notifications,
    logger,
):
    """Reconcile topology, regions, XP, and notices after land transfer."""
    try:
        from kingdom_service import (
            award_kingdom_xp,
            reconcile_after_land_transfer,
            transfer_split_off_kingdom_lands,
        )
        from kingdom_progression import xp_for_land_tier

        split_transfer_summary = transfer_split_off_kingdom_lands(
            old_owner_id=old_land_owner_id,
            new_owner_id=attacker_user.id if attacker_user else None,
            source_kingdom_id=lost_kingdom_id,
            split_land_id=land_id,
            now=land.owned_since if land else now(),
            commit=False,
        )
        if split_transfer_summary:
            cleared_ids = clear_split_transfer_defences(
                old_land_owner_id,
                split_transfer_summary,
            )
            if cleared_ids:
                split_transfer_summary[
                    'cleared_defence_config_ids'
                ] = cleared_ids

        reconcile_after_land_transfer(
            old_owner_id=old_land_owner_id,
            new_owner_id=attacker_user.id,
            commit=False,
        )
        _reconcile_affected_regions(
            land,
            split_transfer_summary,
            now,
        )
        _award_land_transfer_xp(
            land,
            attacker_user,
            split_transfer_summary,
            award_kingdom_xp=award_kingdom_xp,
            xp_for_land_tier=xp_for_land_tier,
        )
        (
            deleted_kingdom_id,
            deleted_kingdom_name,
        ) = _record_dissolved_kingdom(
            lost_kingdom_id,
            lost_kingdom_name,
            old_land_owner_id,
            logger=logger,
        )
        if split_transfer_summary:
            record_split_transfer_notifications(
                split_transfer_summary,
                land,
                attacker_user,
                defender_user,
            )
        return (
            split_transfer_summary,
            deleted_kingdom_id,
            deleted_kingdom_name,
        )
    except Exception as reconciliation_error:
        logger.exception(
            'Persistent kingdom reconciliation failed after conquer: %s',
            reconciliation_error,
        )
        raise
