# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for the persisted Conquer resolution cache."""

from models import Game, LandAttackLog, Player
from tests.server.test_land_battle import (
    _make_conquer_config,
    _make_defence_config,
    _make_land,
    _make_user,
)


def _start_conquer_battle(app, db, attacker, land):
    from tests.server.test_land_battle import _auth_headers

    response = app.test_client().post(
        '/kingdom/conquer/start_battle',
        json={'land_id': land.id},
        headers=_auth_headers(app, attacker),
    )
    assert response.status_code == 200, response.get_json()
    return db.session.get(Game, response.get_json()['game_id'])


def test_resolver_cache_preserves_prior_metadata_and_matches_live_payload(app, db):
    from routes.games import _resolve_conquer_battle

    with app.app_context():
        attacker_user = _make_user(db, username='cache_attacker')
        defender_user = _make_user(db, username='cache_defender')
        land = _make_land(db, tier=2, owner_user_id=defender_user.id)
        _make_conquer_config(db, attacker_user, land)
        _make_defence_config(db, defender_user, land)
        game = _start_conquer_battle(app, db, attacker_user, land)
        attacker = db.session.get(Player, game.invader_player_id)
        defender = next(
            player for player in game.players if player.id != attacker.id
        )
        game.last_battle_result = {
            'points_awarded': 7,
            'destroyed_figure_name': 'Prior General',
            'battle_score_diff': -4,
            'battle_score_player_id': attacker.id,
            'custom_preserved_key': {'nested': True},
        }
        db.session.flush()

        payload = _resolve_conquer_battle(game, defender, attacker)
        db.session.flush()
        cache = game.last_battle_result

        assert cache['conquer_resolved'] is True
        assert cache['winner_player_id'] == defender.id
        assert cache['loser_player_id'] == attacker.id
        assert cache['conquer_attacker_player_id'] == attacker.id
        assert cache['conquer_attacker_user_id'] == attacker_user.id
        assert cache['conquer_defender_player_id'] == defender.id
        assert cache['conquer_defender_user_id'] == defender_user.id

        assert cache['custom_preserved_key'] == {'nested': True}
        assert cache['points_awarded'] == 7
        assert cache['destroyed_figure_name'] == 'Prior General'
        assert cache['battle_score_diff'] == -4
        assert cache['battle_score_player_id'] == attacker.id

        assert cache['conquer_consumed_cards'] == payload['consumed_cards']
        assert cache['defence_consumed_cards'] == payload['defence_consumed_cards']
        assert cache['conquer_loot_gained_cards'] == payload['loot_gained_cards']
        assert cache['conquer_loot_lost_cards'] == payload['loot_lost_cards']
        assert cache['cards_spent'] == payload['cards_spent']
        assert cache['cards_spent'] == len(cache['conquer_loot_lost_cards'])
        assert cache['card_won_suit'] == payload['card_won_suit']
        assert cache['card_won_rank'] == payload['card_won_rank']
        assert cache['card_lost_suit'] == payload['card_lost_suit']
        assert cache['card_lost_rank'] == payload['card_lost_rank']
        assert cache['is_ai_defender'] is False
        assert cache['attacker_first_conquest'] is False
        assert cache['victory_review_config_id'] is None
        assert cache['victory_review_land_id'] is None
        assert 'kingdom_split_transfer' not in cache

        assert payload['points_awarded'] == 7
        assert payload['destroyed_figure_name'] == 'Prior General'
        assert payload['conquer_result'] == 'defender_won'
        assert payload['attacker_won'] is False

        assert LandAttackLog.query.filter_by(land_id=land.id).count() == 1
