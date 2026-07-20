#!/usr/bin/env python3
# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Nepal Kings server management commands."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv


def _load_private_environment():
    env_file = os.environ.get('NEPAL_KINGS_ENV_FILE')
    if not env_file:
        return
    path = Path(env_file).expanduser()
    if not path.is_file():
        raise RuntimeError(f'NEPAL_KINGS_ENV_FILE does not exist: {path}')
    load_dotenv(path, override=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'command',
        choices=(
            'prepare-database',
            'run-worker',
            'moderation-list',
            'moderation-action',
        ),
    )
    parser.add_argument('report_id', nargs='?', type=int)
    parser.add_argument(
        'action',
        nargs='?',
        choices=(
            'close',
            'dismiss',
            'mute',
            'unmute',
            'suspend',
            'ban',
            'unban',
        ),
    )
    parser.add_argument('--status', default='open', choices=('open', 'closed', 'all'))
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--hours', type=int, default=24)
    parser.add_argument('--reason', default='')
    parser.add_argument(
        '--actor',
        default=os.environ.get('MODERATOR_ACTOR', 'operator'),
    )
    args = parser.parse_args()

    _load_private_environment()

    # This command owns database preparation. Never let importing the WSGI
    # application perform the same work first, even if a local environment
    # file enables the historical development convenience.
    os.environ['STARTUP_MAINTENANCE_ENABLED'] = 'False'
    os.environ['BACKGROUND_SERVICES_ENABLED'] = 'False'

    # Import only after the private environment has been loaded.
    from server import app
    if args.command == 'prepare-database':
        from startup import prepare_database

        prepare_database(app)
        print('Database preparation completed successfully')
        return 0
    if args.command == 'run-worker':
        from background_worker import run_forever

        run_forever(app)
        return 0
    if args.command == 'moderation-list':
        from models import SafetyReport

        with app.app_context():
            query = SafetyReport.query
            if args.status != 'all':
                query = query.filter_by(status=args.status)
            rows = query.order_by(
                SafetyReport.created_at.asc(),
            ).limit(max(1, min(args.limit, 100))).all()
            payload = [
                {
                    'id': row.id,
                    'status': row.status,
                    'created_at': (
                        row.created_at.isoformat() if row.created_at else None),
                    'reporter': (
                        row.reporter.username if row.reporter else None),
                    'reported': (
                        row.reported.username if row.reported else None),
                    'reason': row.reason,
                    'details': row.details,
                    'context_type': row.context_type,
                    'context_id': row.context_id,
                    'evidence': row.evidence,
                    'resolution': row.resolution,
                }
                for row in rows
            ]
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == 'moderation-action':
        if args.report_id is None or args.action is None:
            parser.error(
                'moderation-action requires REPORT_ID and ACTION')
        from models import db, ModerationAction, SafetyReport

        with app.app_context():
            report = db.session.get(SafetyReport, args.report_id)
            if report is None:
                parser.error(f'report {args.report_id} does not exist')
            target = report.reported
            if target is None:
                parser.error(
                    f'report {args.report_id} has no target account')

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            hours = max(1, min(int(args.hours), 24 * 365))
            action = args.action
            if action == 'mute':
                target.chat_muted_until = now + timedelta(hours=hours)
            elif action == 'unmute':
                target.chat_muted_until = None
            elif action == 'suspend':
                target.account_status = 'suspended'
                target.suspended_until = now + timedelta(hours=hours)
                target.token_version = int(target.token_version or 0) + 1
            elif action == 'ban':
                target.account_status = 'banned'
                target.suspended_until = None
                target.token_version = int(target.token_version or 0) + 1
            elif action == 'unban':
                target.account_status = 'active'
                target.suspended_until = None
                target.token_version = int(target.token_version or 0) + 1

            reason = (args.reason or '').strip()[:1000]
            db.session.add(ModerationAction(
                report_id=report.id,
                target_user_id=target.id,
                actor_label=str(args.actor or 'operator')[:120],
                action=action,
                reason=reason or None,
                metadata_json={
                    'hours': hours if action in {'mute', 'suspend'} else None,
                },
            ))
            report.status = 'closed'
            report.closed_at = now
            report.resolution = reason or action
            db.session.commit()
            print(json.dumps({
                'success': True,
                'report_id': report.id,
                'target_user_id': target.id,
                'target_username': target.username,
                'action': action,
                'account_status': target.account_status,
                'suspended_until': (
                    target.suspended_until.isoformat()
                    if target.suspended_until else None),
                'chat_muted_until': (
                    target.chat_muted_until.isoformat()
                    if target.chat_muted_until else None),
            }, indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
