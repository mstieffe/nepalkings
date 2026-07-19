# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Cleanup and notification helpers for Conquer ownership transfers."""

import logging

from game_service.conquer_config_transition import _wipe_land_config
from models import KingdomNotification, Land, LandConfig, db


logger = logging.getLogger('nepalkings.routes.games')


def _wipe_defence_drafts_for_lost_land(user_id, land_id):
    """Delete editable defence drafts for a land that changed owner.

    AI lands carry no drafts, so this is a no-op for them.  Logged at INFO
    so we have an audit trail when a player's in-progress edits are dropped.
    """
    if not user_id or not land_id:
        return
    drafts = LandConfig.query.filter_by(
        user_id=user_id,
        land_id=land_id,
        config_type='defence',
        status='draft',
    ).all()
    if not drafts:
        return
    logger.info(
        "Wiping %d defence draft(s) for user_id=%s land_id=%s after land changed owner",
        len(drafts), user_id, land_id,
    )
    for draft in drafts:
        _wipe_land_config(draft)


def _clear_split_transfer_defences(old_owner_id, split_summary):
    """Remove old-owner defence configs from collateral split-transfer lands."""
    if not old_owner_id or not split_summary:
        return []
    cleared_config_ids = []
    seen_config_ids = set()
    for land_id in split_summary.get('transferred_land_ids') or []:
        land = db.session.get(Land, land_id)
        if not land:
            continue
        configs = []
        active_config = (db.session.get(LandConfig, land.defence_config_id)
                         if land.defence_config_id else None)
        if (active_config and active_config.user_id == old_owner_id
                and active_config.config_type == 'defence'):
            configs.append(active_config)
        configs.extend(LandConfig.query.filter_by(
            user_id=old_owner_id,
            land_id=land_id,
            config_type='defence',
            status='active',
        ).all())
        for config_row in configs:
            if not config_row or config_row.id in seen_config_ids:
                continue
            seen_config_ids.add(config_row.id)
            cleared_config_ids.append(config_row.id)
            _wipe_land_config(config_row)
        land.defence_config_id = None
        _wipe_defence_drafts_for_lost_land(old_owner_id, land_id)
    return cleared_config_ids


def _split_transfer_payload(split_summary, land, attacker_user, defender_user):
    samples = list((split_summary or {}).get('transferred_lands') or [])[:3]
    return {
        'kingdom_id': (split_summary or {}).get('source_kingdom_id'),
        'kingdom_name': (split_summary or {}).get('source_kingdom_name'),
        'land_id': land.id if land else (split_summary or {}).get('split_land_id'),
        'land_col': land.col if land else None,
        'land_row': land.row if land else None,
        'split_land_id': (split_summary or {}).get('split_land_id'),
        'split_land_col': land.col if land else None,
        'split_land_row': land.row if land else None,
        'component_count': int((split_summary or {}).get('component_count') or 0),
        'lost_component_count': int((split_summary or {}).get('lost_component_count') or 0),
        'kept_land_count': int((split_summary or {}).get('kept_land_count') or 0),
        'transferred_land_count': int((split_summary or {}).get('transferred_land_count') or 0),
        'lost_land_count': int((split_summary or {}).get('transferred_land_count') or 0),
        'gained_land_count': int((split_summary or {}).get('transferred_land_count') or 0),
        'transferred_land_ids': list((split_summary or {}).get('transferred_land_ids') or []),
        'land_samples': samples,
        'conqueror_user_id': attacker_user.id if attacker_user else None,
        'conqueror_username': attacker_user.username if attacker_user else None,
        'defender_user_id': defender_user.id if defender_user else None,
        'defender_username': defender_user.username if defender_user else None,
    }


def _record_split_transfer_notifications(split_summary, land, attacker_user, defender_user):
    if not split_summary or int(split_summary.get('transferred_land_count') or 0) <= 0:
        return
    base_payload = _split_transfer_payload(split_summary, land, attacker_user, defender_user)
    old_owner_id = split_summary.get('old_owner_id')
    if old_owner_id:
        db.session.add(KingdomNotification(
            user_id=old_owner_id,
            kingdom_id=split_summary.get('source_kingdom_id'),
            kind='kingdom_split_lost',
            payload=base_payload,
        ))
    if attacker_user:
        attacker_payload = dict(base_payload)
        attacker_payload['gained_kingdom_id'] = land.kingdom_id if land else None
        db.session.add(KingdomNotification(
            user_id=attacker_user.id,
            kingdom_id=land.kingdom_id if land else None,
            kind='kingdom_split_claimed',
            payload=attacker_payload,
        ))


# Keep the historical route-level repr and pickle lookup while routes.games
# re-exports these canonical implementations.
_clear_split_transfer_defences.__module__ = 'routes.games'
_record_split_transfer_notifications.__module__ = 'routes.games'
_split_transfer_payload.__module__ = 'routes.games'
_wipe_defence_drafts_for_lost_land.__module__ = 'routes.games'
