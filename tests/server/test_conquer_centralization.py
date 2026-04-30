# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for the conquer-resolution centralization commit.

Covers:
- ``_resolve_conquer_battle`` idempotency (re-running does not double-consume
  cards, double-loot, or write a second LandAttackLog).
- attacker-loss loot details surface through the attack log without a duplicate
    ``KingdomNotification(kind='card_looted')``.
- ``_get_or_create_conquer_config`` re-entry safety net resolves a stale
  finished conquer game and yields a fresh config.
- ``sweep_stuck_conquer_games`` auto-forfeits a stale conquer game and
  skips games with NULL ``last_activity_at``.
"""
from datetime import datetime, timezone, timedelta

from models import (db, Game, Player, LandConfig, LandAttackLog,
                    CollectionCard, KingdomNotification)

# Reuse the helpers from the land-battle test suite.
from tests.server.test_land_battle import (  # noqa: E402
    _make_user, _make_land, _make_conquer_config, _make_defence_config,
    _auth_headers,
)


def _start_conquer_battle(app, db_, attacker, land):
    """Start a conquer battle via the public route and return the Game."""
    client = app.test_client()
    headers = _auth_headers(app, attacker)
    resp = client.post('/kingdom/conquer/start_battle',
                       json={'land_id': land.id}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    return db_.session.get(Game, data['game_id'])


class TestResolveConquerIdempotency:
    """Calling _resolve_conquer_battle twice must be a no-op the second time."""

    def test_attacker_loss_idempotent(self, app, db):
        from routes.games import _resolve_conquer_battle
        with app.app_context():
            attacker = _make_user(db, username='att_idem_loss')
            defender = _make_user(db, username='def_idem_loss')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            game = _start_conquer_battle(app, db, attacker, land)
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.id != atk_player.id][0]

            first = _resolve_conquer_battle(game, def_player, atk_player)
            db.session.commit()
            assert first['conquer_result'] == 'defender_won'

            # Snapshot side-effect state after first call
            log_count_1 = LandAttackLog.query.filter_by(land_id=land.id).count()
            attacker_card_count_1 = CollectionCard.query.filter_by(
                user_id=attacker.id).count()
            defender_card_count_1 = CollectionCard.query.filter_by(
                user_id=defender.id).count()
            atk_cfg_after = LandConfig.query.filter_by(
                user_id=attacker.id, config_type='conquer',
                land_id=land.id,
            ).first()

            # Second call must short-circuit via the cached payload.
            second = _resolve_conquer_battle(game, def_player, atk_player)
            db.session.commit()

            log_count_2 = LandAttackLog.query.filter_by(land_id=land.id).count()
            assert log_count_2 == log_count_1, \
                "Second resolve duplicated the LandAttackLog row"
            assert CollectionCard.query.filter_by(
                user_id=attacker.id).count() == attacker_card_count_1, \
                "Second resolve consumed additional attacker cards"
            assert CollectionCard.query.filter_by(
                user_id=defender.id).count() == defender_card_count_1, \
                "Second resolve transferred extra cards to defender"
            assert LandConfig.query.filter_by(
                user_id=attacker.id, config_type='conquer',
                land_id=land.id,
            ).first() is atk_cfg_after, \
                "Attacker cfg state changed on second resolve"

            # Cached payload exposes the same conquer_result.
            assert second.get('conquer_result') == first['conquer_result']
            assert second.get('attacker_won') == first['attacker_won']
            # And the game still carries the resolved marker.
            assert isinstance(game.last_battle_result, dict)
            assert game.last_battle_result.get('conquer_resolved') is True

    def test_attacker_win_idempotent(self, app, db):
        from routes.games import _resolve_conquer_battle
        with app.app_context():
            attacker = _make_user(db, username='att_idem_win')
            defender = _make_user(db, username='def_idem_win')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            game = _start_conquer_battle(app, db, attacker, land)
            atk_player = db.session.get(Player, game.invader_player_id)

            first = _resolve_conquer_battle(game, atk_player, atk_player)
            db.session.commit()
            assert first['conquer_result'] == 'attacker_won'

            log_count_1 = LandAttackLog.query.filter_by(land_id=land.id).count()
            attacker_card_count_1 = CollectionCard.query.filter_by(
                user_id=attacker.id).count()

            _resolve_conquer_battle(game, atk_player, atk_player)
            db.session.commit()

            assert LandAttackLog.query.filter_by(land_id=land.id).count() \
                == log_count_1
            # No extra reward card minted.
            assert CollectionCard.query.filter_by(
                user_id=attacker.id).count() == attacker_card_count_1

    def test_finished_payload_prefers_game_cached_card_details(self, app, db):
        """A later attack on the same land must not rewrite old payload details."""
        from routes.games import _serialize_finished_conquer_result
        with app.app_context():
            attacker = _make_user(db, username='att_cached_payload')
            defender = _make_user(db, username='def_cached_payload')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            game = Game(mode='conquer', land_id=land.id, state='finished')
            db.session.add(game)
            db.session.flush()
            atk_player = Player(user_id=attacker.id, game_id=game.id, turns_left=0)
            def_player = Player(user_id=defender.id, game_id=game.id, turns_left=0)
            db.session.add_all([atk_player, def_player])
            db.session.flush()
            game.invader_player_id = atk_player.id
            game.winner_player_id = def_player.id
            game.last_battle_result = {
                'conquer_resolved': True,
                'card_lost_suit': 'Hearts',
                'card_lost_rank': 'K',
                'conquer_loot_lost_cards': [{'suit': 'Hearts', 'rank': 'K'}],
            }
            db.session.add(LandAttackLog(
                land_id=land.id,
                attacker_user_id=attacker.id,
                defender_user_id=defender.id,
                result='defender_won',
                card_lost_suit='Spades',
                card_lost_rank='A',
            ))
            db.session.commit()

            payload = _serialize_finished_conquer_result(game)

            assert payload['conquer_result'] == 'defender_won'
            assert payload['card_lost_suit'] == 'Hearts'
            assert payload['card_lost_rank'] == 'K'
            assert payload['loot_lost_cards'] == [{'suit': 'Hearts', 'rank': 'K'}]

    def test_finished_draw_payload_uses_cached_consumed_cards(self, app, db):
        """Cached draw results report spent attack cards and ignore land logs."""
        from routes.games import _serialize_finished_conquer_result
        with app.app_context():
            attacker = _make_user(db, username='att_cached_draw')
            defender = _make_user(db, username='def_cached_draw')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            game = Game(mode='conquer', land_id=land.id, state='finished')
            db.session.add(game)
            db.session.flush()
            atk_player = Player(user_id=attacker.id, game_id=game.id, turns_left=0)
            def_player = Player(user_id=defender.id, game_id=game.id, turns_left=0)
            db.session.add_all([atk_player, def_player])
            db.session.flush()
            game.invader_player_id = atk_player.id
            game.last_battle_result = {
                'conquer_resolved': True,
                'conquer_result': 'draw',
                'attacker_won': False,
                'conquer_consumed_cards': [{'suit': 'Clubs', 'rank': '9'}],
                'conquer_loot_lost_cards': [],
                'cards_spent': 1,
            }
            db.session.add(LandAttackLog(
                land_id=land.id,
                attacker_user_id=attacker.id,
                defender_user_id=defender.id,
                result='attacker_won',
                card_won_suit='Spades',
                card_won_rank='A',
            ))
            db.session.commit()

            payload = _serialize_finished_conquer_result(game)

            assert payload['conquer_result'] == 'draw'
            assert payload['consumed_cards'] == [{'suit': 'Clubs', 'rank': '9'}]
            assert payload['cards_spent'] == 1
            assert payload.get('card_won_suit') is None
            assert payload.get('card_won_rank') is None


class TestConquerLootNotifications:
    """A human attacker losing a conquer battle gets one activity-feed row."""

    def test_human_attacker_loss_uses_attack_log_not_duplicate_notification(self, app, db):
        from routes.games import _resolve_conquer_battle
        with app.app_context():
            attacker = _make_user(db, username='att_notif')
            defender = _make_user(db, username='def_notif')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            game = _start_conquer_battle(app, db, attacker, land)
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.id != atk_player.id][0]

            result = _resolve_conquer_battle(game, def_player, atk_player)
            db.session.commit()
            assert result['conquer_result'] == 'defender_won'

            notes = KingdomNotification.query.filter_by(
                user_id=attacker.id, kind='card_looted',
            ).all()
            assert notes == []

            # Suit/rank match the loot row in the payload.
            loot = (result.get('loot_lost_cards') or [])
            assert len(loot) == 1
            log = LandAttackLog.query.filter_by(
                land_id=land.id, attacker_user_id=attacker.id,
            ).first()
            assert log is not None
            assert log.card_lost_suit == loot[0]['suit']
            assert log.card_lost_rank == loot[0]['rank']

            client = app.test_client()
            resp = client.get('/kingdom/notifications',
                              headers=_auth_headers(app, attacker))
            data = resp.get_json()
            assert resp.status_code == 200
            rows = data.get('notifications') or []
            assert len(rows) == 1
            assert rows[0]['source'] == 'attack_log'
            assert rows[0]['activity_detail'] == f"Card lost: {loot[0]['rank']} of {loot[0]['suit']}"

    def test_attacker_win_emits_no_card_looted(self, app, db):
        """No card_looted notification when the attacker wins."""
        from routes.games import _resolve_conquer_battle
        with app.app_context():
            attacker = _make_user(db, username='att_win_no_notif')
            defender = _make_user(db, username='def_win_no_notif')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            game = _start_conquer_battle(app, db, attacker, land)
            atk_player = db.session.get(Player, game.invader_player_id)

            _resolve_conquer_battle(game, atk_player, atk_player)
            db.session.commit()

            notes = KingdomNotification.query.filter_by(
                user_id=attacker.id, kind='card_looted',
            ).count()
            assert notes == 0


class TestConquerReentrySafetyNet:
    """Re-entering a land whose previous conquer game finished without
    running the resolver triggers a lazy resolve and yields a fresh cfg."""

    def test_reentry_resolves_stale_finished_game(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='att_reentry')
            defender = _make_user(db, username='def_reentry')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            game = _start_conquer_battle(app, db, attacker, land)
            stale_cfg_id = atk_cfg.id

            # Simulate the half-resolved bug: mark the game finished with
            # the defender as winner but DO NOT call _resolve_conquer_battle.
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.id != atk_player.id][0]
            game.state = 'finished'
            game.winner_player_id = def_player.id
            db.session.commit()

            # Sanity: no LandAttackLog yet, attacker cfg still alive.
            assert LandAttackLog.query.filter_by(land_id=land.id).count() == 0
            assert db.session.get(LandConfig, stale_cfg_id) is not None

            # Re-entering the land — via the public conquer config GET —
            # routes through _get_or_create_conquer_config and must lazy-
            # resolve the stale game.
            from routes.kingdom import _get_or_create_conquer_config
            new_cfg = _get_or_create_conquer_config(attacker.id, land.id)
            db.session.commit()

            # Stale cfg destroyed and replaced with a fresh row.
            assert db.session.get(LandConfig, stale_cfg_id) is None
            assert new_cfg is not None
            assert new_cfg.id != stale_cfg_id
            assert LandAttackLog.query.filter_by(land_id=land.id).count() == 1


class TestStuckConquerSweeper:
    def test_resolves_stale_conquer_game(self, app, db):
        from sweepers import sweep_stuck_conquer_games
        with app.app_context():
            attacker = _make_user(db, username='att_sweep')
            defender = _make_user(db, username='def_sweep')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            game = _start_conquer_battle(app, db, attacker, land)
            # Mark activity as 30 minutes old so it falls outside the
            # default 15-minute timeout.
            game.last_activity_at = (datetime.now(timezone.utc)
                                     - timedelta(minutes=30))
            db.session.commit()

            resolved = sweep_stuck_conquer_games()
            db.session.commit()

            assert resolved == 1
            db.session.refresh(game)
            assert game.state == 'finished'
            # Defender treated as the winner: one attack log should now exist
            # for the attacker. A separate card_looted event would duplicate it.
            assert LandAttackLog.query.filter_by(land_id=land.id).count() == 1
            assert KingdomNotification.query.filter_by(
                user_id=attacker.id, kind='card_looted',
            ).count() == 0

    def test_skips_recent_activity(self, app, db):
        from sweepers import sweep_stuck_conquer_games
        with app.app_context():
            attacker = _make_user(db, username='att_recent')
            defender = _make_user(db, username='def_recent')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            game = _start_conquer_battle(app, db, attacker, land)
            game.last_activity_at = datetime.now(timezone.utc)
            db.session.commit()

            assert sweep_stuck_conquer_games() == 0
            db.session.refresh(game)
            assert game.state != 'finished'

    def test_skips_null_last_activity(self, app, db):
        """Games with NULL last_activity_at must NOT be auto-forfeited.

        After the column is added but before any authenticated request has
        bumped the timestamp, last_activity_at can be NULL.  Falling back
        to game.date used to forfeit such games on the first sweep — the
        sweeper should now leave them alone.
        """
        from sweepers import sweep_stuck_conquer_games
        with app.app_context():
            attacker = _make_user(db, username='att_null_act')
            defender = _make_user(db, username='def_null_act')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            game = _start_conquer_battle(app, db, attacker, land)
            # Force NULL despite the model default
            game.last_activity_at = None
            # And backdate game.date so the OLD (broken) fallback would
            # have triggered a forfeit.
            game.date = datetime.now(timezone.utc) - timedelta(hours=1)
            db.session.commit()

            assert sweep_stuck_conquer_games() == 0
            db.session.refresh(game)
            assert game.state != 'finished'


class TestVerifyOwnershipActivityScope:
    """verify_player_ownership should bump last_activity_at only for conquer
    games, not duels / regular battles (sweeper only targets conquer)."""

    def test_conquer_game_activity_is_bumped(self, app, db):
        from routes.auth import verify_player_ownership
        from flask import g
        with app.app_context():
            attacker = _make_user(db, username='att_act_bump')
            defender = _make_user(db, username='def_act_bump')
            land = _make_land(db, tier=2, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)
            game = _start_conquer_battle(app, db, attacker, land)
            atk_player = db.session.get(Player, game.invader_player_id)

            # Backdate to a known value (naive — SQLite stores naive),
            # then verify it gets bumped.
            stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
            game.last_activity_at = stale
            db.session.commit()

            with app.test_request_context():
                g.user_id = attacker.id
                # Need a valid token-bound user for ownership; we set
                # g.user_id directly which is what require_token does.
                err = verify_player_ownership(atk_player.id)
            db.session.commit()

            assert err is None
            db.session.refresh(game)
            current = game.last_activity_at
            if current.tzinfo is not None:
                current = current.replace(tzinfo=None)
            assert current > stale

    def test_duel_game_activity_not_bumped(self, app, db):
        """A non-conquer game must NOT have last_activity_at touched."""
        from routes.auth import verify_player_ownership
        from flask import g
        with app.app_context():
            user = _make_user(db, username='duel_user')
            # Build a minimal duel game with one player owned by the user.
            game = Game(mode='duel', state='active', stake=10,
                        current_round=1, ceasefire_active=False,
                        battle_confirmed=False)
            db.session.add(game)
            db.session.flush()
            p = Player(user_id=user.id, game_id=game.id, turns_left=1,
                       points=0)
            db.session.add(p)
            db.session.commit()

            stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
            game.last_activity_at = stale
            db.session.commit()

            with app.test_request_context():
                g.user_id = user.id
                err = verify_player_ownership(p.id)
            db.session.commit()

            assert err is None
            db.session.refresh(game)
            current = game.last_activity_at
            if current is not None and current.tzinfo is not None:
                current = current.replace(tzinfo=None)
            # Same value (within DB rounding) — no bump.
            assert current == stale
