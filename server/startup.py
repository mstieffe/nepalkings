# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Explicit database preparation and optional local background services.

Production WSGI imports must stay lightweight and read-only. Deployments call
``python manage.py prepare-database`` before reloading the web app. Local
development can retain the historical convenience through
STARTUP_MAINTENANCE_ENABLED=True.
"""

import logging
import os
import sys

from models import db
import server_settings as settings


logger = logging.getLogger('nepalkings.startup')


def _release_orphan_collection_locks():
    """Release collection locks whose owning configuration row disappeared."""
    from models import (
        CollectionCard,
        LandConfig,
        LandConfigBattleMove,
        LandConfigFigure,
    )

    figure_ids = {
        figure_id
        for (figure_id,) in db.session.query(LandConfigFigure.id).all()
    }
    move_ids = {
        move_id
        for (move_id,) in db.session.query(LandConfigBattleMove.id).all()
    }
    config_ids = {
        config_id
        for (config_id,) in db.session.query(LandConfig.id).all()
    }
    valid_by_lock_type = {
        'conquer_figure': figure_ids,
        'defence_figure': figure_ids,
        'defence_draft_figure': figure_ids,
        'conquer_move': move_ids,
        'defence_move': move_ids,
        'defence_draft_move': move_ids,
        'conquer_modifier': config_ids,
        'defence_modifier': config_ids,
        'defence_draft_modifier': config_ids,
        'conquer_spell': config_ids,
        'defence_spell': config_ids,
        'defence_draft_spell': config_ids,
        'conquer_prelude': config_ids,
        'defence_prelude': config_ids,
        'defence_draft_prelude': config_ids,
        'conquer_counter': config_ids,
        'defence_counter': config_ids,
        'defence_draft_counter': config_ids,
    }

    orphan_count = 0
    for card in CollectionCard.query.filter_by(locked=True).all():
        valid_ids = valid_by_lock_type.get(card.lock_type)
        if valid_ids is None or card.lock_ref_id not in valid_ids:
            card.locked = False
            card.lock_type = None
            card.lock_ref_id = None
            orphan_count += 1

    if orphan_count:
        db.session.commit()
        logger.warning(
            'Orphan-lock sweep released %d stale card lock(s)',
            orphan_count,
        )
    else:
        logger.info('Orphan-lock sweep found no stale locks')


def prepare_database(app):
    """Create a fresh schema, apply migrations, and run data maintenance."""
    with app.app_context():
        if settings.DROP_TABLES_ON_STARTUP:
            logger.warning(
                'Dropping all database tables '
                '(DROP_TABLES_ON_STARTUP=True)'
            )
            db.drop_all()
            logger.info('All tables dropped')

        logger.info('Creating missing database tables')
        db.create_all()

        try:
            from migration_runner import run_migrations

            applied = run_migrations()
            if applied:
                logger.info(
                    'Applied schema migrations: %s',
                    ', '.join(f'{version:04d}' for version in applied),
                )
        except Exception as exc:
            db.session.rollback()
            logger.exception('Schema migration failed: %s', exc)
            raise RuntimeError(
                'Required database migration failed; database preparation '
                'aborted'
            ) from exc

        try:
            _release_orphan_collection_locks()
        except Exception as exc:
            db.session.rollback()
            logger.exception('Orphan-lock sweep failed: %s', exc)

        from kingdom_service import seed_kingdom_map

        seed_kingdom_map()
        logger.info('Kingdom map seeding checked')

        try:
            from kingdom_service import reconcile_all_kingdoms

            reconcile_all_kingdoms(commit=True)
            logger.info('Persistent kingdom reconciliation checked')
        except Exception as exc:
            db.session.rollback()
            logger.exception(
                'Persistent kingdom reconciliation failed: %s',
                exc,
            )

        if settings.RECONCILE_REGION_CHAMPIONS_ON_STARTUP:
            try:
                from region_service import reconcile_region_champions

                reconcile_region_champions(commit=True)
                logger.info('Historic region Champion reconciliation checked')
            except Exception as exc:
                db.session.rollback()
                logger.exception(
                    'Historic region Champion reconciliation failed: %s',
                    exc,
                )
        else:
            logger.info(
                'Historic region Champion startup reconciliation skipped'
            )

        if settings.AI_ENABLED:
            from ai import init_ai_users

            init_ai_users()

        logger.info('Database preparation complete')


def start_background_services(app):
    """Start local-only in-process services when explicitly enabled."""
    if not settings.BACKGROUND_SERVICES_ENABLED:
        logger.info('In-process background services disabled')
        return False
    if (
        'pytest' in sys.modules
        or os.environ.get('PYTEST_CURRENT_TEST') is not None
        or os.environ.get('DISABLE_BACKGROUND_SWEEPERS') == '1'
    ):
        logger.info('In-process background services skipped for tests')
        return False

    try:
        from sweepers import start_stuck_conquer_sweeper

        start_stuck_conquer_sweeper(app)
    except Exception:
        logger.exception('Failed to start stuck-conquer sweeper')
        return False
    return True
