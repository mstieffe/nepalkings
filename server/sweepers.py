# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Background sweepers for stuck game state.

The stuck-conquer sweeper auto-resolves abandoned conquer battles.  A conquer
game is treated as abandoned when its ``state`` is still ``'active'`` (or
``'open'``) and ``last_activity_at`` (falling back to ``date``) is older
than :data:`server_settings.STUCK_CONQUER_TIMEOUT_SECONDS`.

The defender is treated as the winner: the attacker forfeits.  This calls
``_resolve_conquer_battle`` which is idempotent and writes a LandAttackLog
entry surfaced by the unified kingdom notification feed.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc)


def sweep_stuck_conquer_games(timeout_seconds=None):
    """Resolve stuck conquer games once.  Returns the number resolved.

    Safe to call from inside a Flask app context.  Does its own commits.
    """
    from models import db, Game, Player
    import server_settings as settings

    if timeout_seconds is None:
        timeout_seconds = settings.STUCK_CONQUER_TIMEOUT_SECONDS

    cutoff = _utcnow() - timedelta(seconds=timeout_seconds)

    candidates = (
        Game.query
        .filter(Game.mode == 'conquer')
        .filter(Game.state.in_(['active', 'open']))
        .all()
    )

    resolved = 0
    for game in candidates:
        # Require an explicit last_activity_at signal.  Games predating the
        # column (or never touched by an authenticated request) report
        # NULL and are left alone — better to leak a stuck row for one
        # player to revisit than to forfeit a possibly-active battle the
        # first time the sweeper runs after a deploy.
        last_active = game.last_activity_at
        if last_active is None:
            continue
        # Normalize to aware datetime for comparison
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
        if last_active >= cutoff:
            continue

        # Determine the defender — they win on attacker abandonment.
        from routes.games import _conquer_attacker_player, _resolve_conquer_battle
        atk_player = _conquer_attacker_player(game)
        if atk_player is None and game.invader_player_id:
            atk_player = db.session.get(Player, game.invader_player_id)
        defender = None
        if atk_player is not None:
            defender = next(
                (p for p in game.players if p.id != atk_player.id),
                None,
            )
        if defender is None:
            logger.warning(
                "[STUCK_SWEEP] could not determine defender for game %s; skipping",
                game.id,
            )
            continue

        try:
            _resolve_conquer_battle(game, defender, defender)
            db.session.commit()
            resolved += 1
            logger.info(
                "[STUCK_SWEEP] auto-forfeited conquer game %s (land=%s, attacker=%s) — "
                "no activity since %s",
                game.id, game.land_id, atk_player.id if atk_player else None,
                last_active.isoformat(),
            )
        except Exception:
            db.session.rollback()
            logger.exception(
                "[STUCK_SWEEP] failed to auto-resolve game %s", game.id,
            )

    return resolved


def start_stuck_conquer_sweeper(app, interval_seconds=None):
    """Start a daemon thread that periodically runs the sweeper."""
    import server_settings as settings

    if interval_seconds is None:
        interval_seconds = settings.STUCK_CONQUER_SWEEP_INTERVAL_SECONDS

    if interval_seconds <= 0:
        logger.info("[STUCK_SWEEP] disabled (interval=%s)", interval_seconds)
        return None

    def _loop():
        while True:
            try:
                with app.app_context():
                    sweep_stuck_conquer_games()
            except Exception:
                logger.exception("[STUCK_SWEEP] iteration failed")
            time.sleep(interval_seconds)

    thread = threading.Thread(
        target=_loop, name='stuck-conquer-sweeper', daemon=True,
    )
    thread.start()
    logger.info(
        "[STUCK_SWEEP] daemon started (interval=%ss, timeout=%ss)",
        interval_seconds, settings.STUCK_CONQUER_TIMEOUT_SECONDS,
    )
    return thread
