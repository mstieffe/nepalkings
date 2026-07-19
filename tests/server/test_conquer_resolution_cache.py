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
        assert set(payload) == {
            'success',
            'message',
            'conquer_result',
            'attacker_won',
            'conquer_attacker_player_id',
            'conquer_defender_player_id',
            'conquer_attacker_user_id',
            'conquer_defender_user_id',
            'land_id',
            'land_gold_rate',
            'land_tier',
            'points_awarded',
            'destroyed_figure_name',
            'card_won_suit',
            'card_won_rank',
            'card_lost_suit',
            'card_lost_rank',
            'is_ai_defender',
            'attacker_first_conquest',
            'loot_lost_cards',
            'loot_gained_cards',
            'consumed_cards',
            'defence_consumed_cards',
            'cards_spent',
            'kingdom_split_transfer',
            'victory_review_available',
            'victory_review_config_id',
            'victory_review_land_id',
            'game',
            'onboarding',
        }
        assert payload['success'] is True
        assert payload['message'] == (
            'Conquer battle resolved: defender_won'
        )
        assert payload['conquer_result'] == 'defender_won'
        assert payload['attacker_won'] is False
        assert payload['conquer_attacker_player_id'] == attacker.id
        assert payload['conquer_attacker_user_id'] == attacker_user.id
        assert payload['conquer_defender_player_id'] == defender.id
        assert payload['conquer_defender_user_id'] == defender_user.id
        assert payload['land_id'] == land.id
        assert payload['land_gold_rate'] == 5.0
        assert payload['land_tier'] == 2
        assert payload['is_ai_defender'] is False
        assert payload['attacker_first_conquest'] is False
        assert payload['kingdom_split_transfer'] is None
        assert payload['victory_review_available'] is False
        assert payload['victory_review_config_id'] is None
        assert payload['victory_review_land_id'] is None
        assert isinstance(payload['game'], dict)
        assert isinstance(payload['onboarding'], dict)

        assert LandAttackLog.query.filter_by(land_id=land.id).count() == 1
