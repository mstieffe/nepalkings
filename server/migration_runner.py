# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Versioned, ordered, idempotent schema migrations.

This formalizes the pre-existing ``ensure_*()`` pattern:

- ``db.create_all()`` (run by server.py before this) creates missing
  *tables* for brand-new models.
- The MIGRATIONS list below handles everything else: added columns,
  backfills, data fixes. Applied versions are recorded in the
  ``schema_version`` table so each migration runs exactly once per
  database, in order.

Adding a migration:

1. Append ``(version, description, callable)`` to MIGRATIONS with the next
   integer version. Never renumber, edit, or remove an applied entry.
2. The callable runs inside an app context. Make it idempotent anyway —
   databases that predate this runner get all historical migrations
   replayed against an already-current schema, and idempotence makes
   that (and any partial-failure rerun) safe.
3. For SQLite-compatible column adds, follow the existing helpers in
   kingdom_service.py: inspect the table, ``ALTER TABLE ... ADD COLUMN``
   only when missing.

Production: back up the live database, upload/install the release, then run
``python manage.py prepare-database`` before reloading the PythonAnywhere web
app. WSGI imports never run this migration path. NEVER "migrate" production by
resetting the database.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, text

from models import db

logger = logging.getLogger('nepalkings.migrations')


def _utcnow_iso():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=' ',
                                                                     timespec='seconds')


# ── Migration callables ────────────────────────────────────────────
# 0001–0007 wrap the historical ensure_* helpers (all idempotent).

def _m_kingdom_production_columns():
    from kingdom_service import ensure_kingdom_production_columns
    ensure_kingdom_production_columns()


def _m_game_ai_seed_column():
    from kingdom_service import ensure_game_ai_seed_column
    ensure_game_ai_seed_column()


def _m_game_victory_reviewed_at_column():
    from kingdom_service import ensure_game_victory_reviewed_at_column
    ensure_game_victory_reviewed_at_column()


def _m_duel_game_limit_columns():
    from kingdom_service import ensure_duel_game_limit_columns
    ensure_duel_game_limit_columns()


def _m_conquer_tactics_schema():
    from kingdom_service import ensure_conquer_tactics_schema
    ensure_conquer_tactics_schema()


def _m_onboarding_state_column():
    from onboarding_service import ensure_onboarding_state_column
    ensure_onboarding_state_column()


def _m_user_legal_columns():
    from user_schema_service import ensure_user_legal_columns
    ensure_user_legal_columns()


def _add_column_if_missing(table, column, ddl_type):
    """Portable ALTER TABLE helper. Returns True when a column is added."""
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(db.engine)
    if table not in inspector.get_table_names():
        return False
    existing = {col['name'] for col in inspector.get_columns(table)}
    if column in existing:
        return False
    quoted = f'"{table}"' if table == 'user' else table
    db.session.execute(text(f'ALTER TABLE {quoted} ADD COLUMN {column} {ddl_type}'))
    db.session.commit()
    return True


def _boolean_column_ddl(*, default):
    if db.engine.dialect.name.startswith('postgres'):
        default_value = 'TRUE' if default else 'FALSE'
    else:
        default_value = '1' if default else '0'
    return f'BOOLEAN NOT NULL DEFAULT {default_value}'


def _m_user_notify_emails_enabled():
    _add_column_if_missing('user', 'notify_emails_enabled',
                           _boolean_column_ddl(default=True))


def _m_game_turn_email_log():
    _add_column_if_missing('game', 'turn_email_log', 'JSON')


def _m_game_battle_gamble_previews():
    _add_column_if_missing('game', 'battle_gamble_previews', 'JSON')


def _m_duel_turn_time_limit_columns():
    _add_column_if_missing('challenge', 'turn_time_limit', 'INTEGER')
    _add_column_if_missing('game', 'turn_time_limit', 'INTEGER')


def _m_figure_is_clone_column():
    _add_column_if_missing('figure', 'is_clone',
                           _boolean_column_ddl(default=False))


def _m_regenerate_kingdom_map_into_regions():
    """One-time, value-preserving reset into the 96x50 regional map."""
    _add_column_if_missing('land', 'region', 'VARCHAR(20)')
    _add_column_if_missing('region_champion', 'champion_user_ids', 'JSON')
    _add_column_if_missing('region_champion', 'pending_gold_by_user', 'JSON')
    _add_column_if_missing('region_champion', 'since_by_user', 'JSON')
    db.session.execute(text(
        'CREATE INDEX IF NOT EXISTS ix_land_region ON land (region)'))
    db.session.flush()

    from models import (
        CollectionCard, Game, Kingdom, KingdomCosmeticUnlock,
        KingdomLootEvent, KingdomMessage, KingdomNotification,
        KingdomSkillAllocation, Land, LandAttackLog, LandConfig,
        LandConfigBattleMove, LandConfigFigure, RegionChampion, User,
        UserKingdomCosmeticEntitlement,
    )

    # Fresh databases are seeded by server.py immediately after migrations.
    if Land.query.first() is None:
        return

    active_games = Game.query.filter(
        Game.mode == 'conquer',
        Game.state.in_(('open', 'active')),
    ).count()
    if active_games:
        raise RuntimeError(
            'Historic-region map reset requires zero open/active Conquer games; '
            f'found {active_games}')

    from kingdom_service import collect_kingdom_production, seed_kingdom_map
    import server_settings as config

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    former_owner_ids = {
        user_id for (user_id,) in db.session.query(Land.owner_user_id)
        .filter(Land.owner_user_id.isnot(None)).distinct().all()
    }
    preservation = {
        user_id: {
            'gold': 0,
            'main_boosters': 0,
            'side_boosters': 0,
            'maps': 0,
            'shield_refund': 0,
            'cosmetics': set(),
        }
        for user_id in former_owner_ids
    }

    kingdoms = Kingdom.query.order_by(Kingdom.id).all()
    land_counts = dict(db.session.query(
        Land.kingdom_id, func.count(Land.id)
    ).filter(Land.kingdom_id.isnot(None)).group_by(Land.kingdom_id).all())

    # Preserve every paid/earned cosmetic as an account entitlement.
    existing_entitlements = {
        (row.user_id, row.cosmetic_key)
        for row in UserKingdomCosmeticEntitlement.query.all()
    }
    for kingdom in kingdoms:
        user = db.session.get(User, kingdom.owner_user_id)
        if not user:
            continue
        info = preservation.setdefault(user.id, {
            'gold': 0, 'main_boosters': 0, 'side_boosters': 0, 'maps': 0,
            'shield_refund': 0, 'cosmetics': set(),
        })
        unlocks = KingdomCosmeticUnlock.query.filter_by(
            kingdom_id=kingdom.id).all()
        for unlock in unlocks:
            info['cosmetics'].add(unlock.cosmetic_key)
            key = (user.id, unlock.cosmetic_key)
            if key not in existing_entitlements:
                db.session.add(UserKingdomCosmeticEntitlement(
                    user_id=user.id, cosmetic_key=unlock.cosmetic_key,
                    granted_at=now))
                existing_entitlements.add(key)

        collected = collect_kingdom_production(kingdom, user, now=now)
        info['gold'] += int(collected.get('collected_gold') or 0)
        info['main_boosters'] += int(
            collected.get('collected_main_boosters') or 0)
        info['side_boosters'] += int(
            collected.get('collected_side_boosters') or 0)
        info['maps'] += int(collected.get('collected_maps') or 0)

        if kingdom.shield_until and kingdom.shield_until > now:
            remaining_hours = max(
                0.0, (kingdom.shield_until - now).total_seconds() / 3600.0)
            refund = int(
                remaining_hours
                * int(config.KINGDOM_SHIELD_PRICE_PER_HOUR_PER_LAND)
                * int(land_counts.get(kingdom.id, 0) or 0)
            )
            if refund:
                user.gold = int(user.gold or 0) + refund
                info['shield_refund'] += refund

    db.session.flush()

    defence_ids = [config_id for (config_id,) in db.session.query(
        LandConfig.id).filter(LandConfig.config_type == 'defence').all()]
    if defence_ids:
        # Release every defence-held collection card, including legacy rows
        # whose child JSON no longer contains the lock reference.
        CollectionCard.query.filter(
            CollectionCard.lock_type.like('defence%')
        ).update({
            CollectionCard.locked: False,
            CollectionCard.lock_type: None,
            CollectionCard.lock_ref_id: None,
        }, synchronize_session=False)

        Land.query.filter(Land.defence_config_id.in_(defence_ids)).update(
            {Land.defence_config_id: None}, synchronize_session=False)
        Game.query.filter(Game.defence_config_id.in_(defence_ids)).update(
            {Game.defence_config_id: None}, synchronize_session=False)
        Game.query.filter(Game.conquer_config_id.in_(defence_ids)).update(
            {Game.conquer_config_id: None}, synchronize_session=False)
        LandConfig.query.filter(
            LandConfig.base_config_id.in_(defence_ids)).update(
                {LandConfig.base_config_id: None}, synchronize_session=False)
        LandConfig.query.filter(LandConfig.id.in_(defence_ids)).update({
            LandConfig.battle_figure_id: None,
            LandConfig.battle_figure_id_2: None,
            LandConfig.base_config_id: None,
        }, synchronize_session=False)
        LandConfigBattleMove.query.filter(
            LandConfigBattleMove.config_id.in_(defence_ids)).delete(
                synchronize_session=False)
        LandConfigFigure.query.filter(
            LandConfigFigure.config_id.in_(defence_ids)).delete(
                synchronize_session=False)
        LandConfig.query.filter(LandConfig.id.in_(defence_ids)).delete(
            synchronize_session=False)

    old_kingdom_ids = [kingdom.id for kingdom in kingdoms]
    KingdomLootEvent.query.update({
        KingdomLootEvent.land_id: None,
        KingdomLootEvent.attack_log_id: None,
        KingdomLootEvent.kingdom_id: None,
    }, synchronize_session=False)
    KingdomMessage.query.update(
        {KingdomMessage.land_id: None}, synchronize_session=False)
    Game.query.update({
        Game.land_id: None,
        Game.defence_config_id: None,
    }, synchronize_session=False)
    KingdomNotification.query.filter(
        KingdomNotification.kingdom_id.in_(old_kingdom_ids)
    ).update({KingdomNotification.kingdom_id: None}, synchronize_session=False)

    LandAttackLog.query.delete(synchronize_session=False)
    Land.query.delete(synchronize_session=False)
    KingdomCosmeticUnlock.query.delete(synchronize_session=False)
    KingdomSkillAllocation.query.delete(synchronize_session=False)
    Kingdom.query.delete(synchronize_session=False)
    RegionChampion.query.delete(synchronize_session=False)
    # The production-like database may already contain stale optional links
    # from old finished games/spells.  Nulling them here makes the required
    # post-reset foreign-key integrity check meaningful and restorable.
    db.session.execute(text(
        'UPDATE game SET conquer_config_id = NULL '
        'WHERE conquer_config_id IS NOT NULL AND conquer_config_id NOT IN '
        '(SELECT id FROM land_config)'))
    db.session.execute(text(
        'UPDATE active_spell SET target_figure_id = NULL '
        'WHERE target_figure_id IS NOT NULL AND target_figure_id NOT IN '
        '(SELECT id FROM figure)'))
    db.session.flush()

    seed_kingdom_map(commit=False)
    from region_service import reconcile_region_champions
    reconcile_region_champions(now=now, commit=False)

    for user_id in sorted(former_owner_ids):
        info = preservation.get(user_id) or {}
        db.session.add(KingdomNotification(
            user_id=user_id,
            kingdom_id=None,
            kind='map_regenerated',
            payload={
                'map_cols': int(config.KINGDOM_MAP_COLS),
                'map_rows': int(config.KINGDOM_MAP_ROWS),
                'preserved_gold': int(info.get('gold') or 0),
                'preserved_main_boosters': int(
                    info.get('main_boosters') or 0),
                'preserved_side_boosters': int(
                    info.get('side_boosters') or 0),
                'preserved_maps': int(info.get('maps') or 0),
                'shield_refund': int(info.get('shield_refund') or 0),
                'preserved_cosmetics': sorted(info.get('cosmetics') or []),
            },
        ))


def _m_clear_fill_up_to_10_preludes():
    """'Fill up to 10' left the conquer/defence prelude pool — clear saved
    configs that still reference it and unlock their locked 10-cards."""
    from models import LandConfig, CollectionCard
    configs = LandConfig.query.filter(
        LandConfig.prelude_spell_name == 'Fill up to 10',
        LandConfig.config_type.in_(('conquer', 'defence')),
    ).all()
    for cfg in configs:
        card_ids = cfg.prelude_spell_card_ids or []
        if card_ids:
            CollectionCard.query.filter(
                CollectionCard.id.in_(card_ids)
            ).update({
                CollectionCard.locked: False,
                CollectionCard.lock_type: None,
                CollectionCard.lock_ref_id: None,
            }, synchronize_session='fetch')
        cfg.prelude_spell_name = None
        cfg.prelude_spell_data = None
        cfg.prelude_spell_card_ids = None
    db.session.commit()


def _m_clear_finished_game_orphan_config_refs():
    """Clear legacy pointers to already-deleted ephemeral configurations."""
    db.session.execute(text(
        'UPDATE game '
        'SET conquer_config_id = NULL '
        "WHERE state = 'finished' "
        'AND conquer_config_id IS NOT NULL '
        'AND NOT EXISTS ('
        '  SELECT 1 FROM land_config '
        '  WHERE land_config.id = game.conquer_config_id'
        ')'
    ))
    db.session.execute(text(
        'UPDATE game '
        'SET defence_config_id = NULL '
        "WHERE state = 'finished' "
        'AND defence_config_id IS NOT NULL '
        'AND NOT EXISTS ('
        '  SELECT 1 FROM land_config '
        '  WHERE land_config.id = game.defence_config_id'
        ')'
    ))
    db.session.commit()


def _m_widen_password_hash_for_scrypt():
    """Allow current Werkzeug scrypt hashes on length-enforcing databases."""
    if db.engine.dialect.name.startswith('postgres'):
        db.session.execute(text(
            'ALTER TABLE "user" '
            'ALTER COLUMN password_hash TYPE VARCHAR(255)'
        ))
        db.session.commit()


def _m_multiworker_conquer_coordination():
    """Persist the Conquer round clock shared by every web worker."""
    _add_column_if_missing(
        'game',
        'battle_round_deadline_round',
        'INTEGER',
    )
    _add_column_if_missing(
        'game',
        'battle_round_deadline_at',
        'TIMESTAMP',
    )


# ── Registry ───────────────────────────────────────────────────────

MIGRATIONS = [
    (1, 'kingdom production columns', _m_kingdom_production_columns),
    (2, 'game.ai_seed column', _m_game_ai_seed_column),
    (3, 'game.victory_reviewed_at column', _m_game_victory_reviewed_at_column),
    (4, 'duel game_limit columns', _m_duel_game_limit_columns),
    (5, 'conquer tactics schema', _m_conquer_tactics_schema),
    (6, 'user.onboarding_state column', _m_onboarding_state_column),
    (7, 'user legal columns', _m_user_legal_columns),
    (8, 'user.notify_emails_enabled column', _m_user_notify_emails_enabled),
    (9, 'game.turn_email_log column', _m_game_turn_email_log),
    (10, 'game.battle_gamble_previews column', _m_game_battle_gamble_previews),
    (11, 'clear Fill up to 10 prelude configs', _m_clear_fill_up_to_10_preludes),
    (12, 'duel turn_time_limit columns', _m_duel_turn_time_limit_columns),
    (13, 'figure.is_clone column', _m_figure_is_clone_column),
    (14, 'regenerate kingdom map into historic regions',
     _m_regenerate_kingdom_map_into_regions),
    (15, 'clear finished-game orphan configuration references',
     _m_clear_finished_game_orphan_config_refs),
    (16, 'widen user password hashes for scrypt',
     _m_widen_password_hash_for_scrypt),
    (17, 'persist multi-worker Conquer coordination',
     _m_multiworker_conquer_coordination),
]

CURRENT_SCHEMA_VERSION = max(version for version, _description, _fn in MIGRATIONS)


# ── Runner ─────────────────────────────────────────────────────────

def _ensure_version_table():
    db.session.execute(text(
        'CREATE TABLE IF NOT EXISTS schema_version ('
        ' version INTEGER PRIMARY KEY,'
        ' description VARCHAR(200),'
        ' applied_at VARCHAR(32))'
    ))
    db.session.commit()


def applied_versions():
    _ensure_version_table()
    rows = db.session.execute(text('SELECT version FROM schema_version')).fetchall()
    return {row[0] for row in rows}


def run_migrations():
    """Apply all pending migrations in order. Returns list of applied versions.

    Stops at the first failing migration (after rollback) so later
    migrations never run against an unexpected intermediate schema.
    """
    applied = applied_versions()
    ran = []
    for version, description, fn in sorted(MIGRATIONS, key=lambda m: m[0]):
        if version in applied:
            continue
        try:
            fn()
            db.session.execute(
                text('INSERT INTO schema_version (version, description, applied_at)'
                     ' VALUES (:v, :d, :t)'),
                {'v': version, 'd': description, 't': _utcnow_iso()})
            db.session.commit()
            ran.append(version)
            logger.info('Migration %04d applied: %s', version, description)
        except Exception:
            db.session.rollback()
            logger.exception('Migration %04d FAILED: %s — halting migration run',
                             version, description)
            raise
    return ran
