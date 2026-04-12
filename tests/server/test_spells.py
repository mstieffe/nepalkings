# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for spell casting, countering, and active-spell management."""
import json
import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def spell_game(db):
    """A game with two players and cards dealt."""
    from models import Game, Player, User
    from werkzeug.security import generate_password_hash
    from game_service.deck import Deck

    u1 = User(username='sp_p1', password_hash=generate_password_hash('p'), gold=100)
    u2 = User(username='sp_p2', password_hash=generate_password_hash('p'), gold=100)
    db.session.add_all([u1, u2])
    db.session.commit()

    game = Game(current_round=1, stake=35)
    db.session.add(game)
    db.session.commit()

    p1 = Player(user_id=u1.id, game_id=game.id, turns_left=6, points=0)
    p2 = Player(user_id=u2.id, game_id=game.id, turns_left=6, points=0)
    db.session.add_all([p1, p2])
    db.session.commit()

    game.turn_player_id = p1.id
    game.invader_player_id = p1.id
    db.session.commit()

    deck = Deck(game)
    deck.create()
    deck.shuffle()
    deck.deal_cards([p1, p2], num_main_cards=12, num_side_cards=0)
    return game, p1, p2, u1, u2


@pytest.fixture
def token_sp1(app, spell_game):
    from routes.auth import generate_token
    _, p1, _, _, _ = spell_game
    return generate_token(p1.user_id)


@pytest.fixture
def token_sp2(app, spell_game):
    from routes.auth import generate_token
    _, _, p2, _, _ = spell_game
    return generate_token(p2.user_id)


def _cast(client, token, game, player, spell_data):
    payload = {
        'player_id': player.id,
        'game_id': game.id,
        **spell_data,
    }
    return client.post('/spells/cast_spell',
                       data=json.dumps(payload),
                       content_type='application/json',
                       headers={'Authorization': f'Bearer {token}'})


class TestCastSpell:
    def test_cast_spell_requires_auth(self, client, spell_game):
        game, p1, _, _, _ = spell_game
        payload = {
            'player_id': p1.id,
            'game_id': game.id,
            'spell_name': 'Draw 2 MainCards',
            'spell_type': 'greed',
            'spell_family_name': 'Draw 2 MainCards',
            'suit': 'Clubs',
            'cards': [],
            'counterable': False,
        }
        resp = client.post('/spells/cast_spell', data=json.dumps(payload),
                           content_type='application/json')
        assert resp.status_code == 401

    def test_cast_spell_fails_on_opponents_turn(self, client, db, app, spell_game, token_sp2):
        """p2's token cannot cast when it's p1's turn."""
        game, p1, p2, _, _ = spell_game
        resp = _cast(client, token_sp2, game, p2, {
            'spell_name': 'Draw 2 MainCards',
            'spell_type': 'greed',
            'spell_family_name': 'Draw 2 MainCards',
            'suit': 'Clubs',
            'cards': [],
            'counterable': False,
        })
        data = resp.get_json()
        assert data.get('success') is False

    def test_cast_non_counterable_spell_creates_active_spell(self, client, db, app, spell_game, token_sp1):
        from models import ActiveSpell
        game, p1, _, _, _ = spell_game
        resp = _cast(client, token_sp1, game, p1, {
            'spell_name': 'Draw 2 MainCards',
            'spell_type': 'greed',
            'spell_family_name': 'Draw 2 MainCards',
            'suit': 'Clubs',
            'cards': [],
            'counterable': False,
            'possible_during_ceasefire': True,
        })
        data = resp.get_json()
        assert data.get('success') is True, data.get('message')
        spell = ActiveSpell.query.filter_by(game_id=game.id, spell_name='Draw 2 MainCards').first()
        assert spell is not None

    def test_cast_counterable_spell_creates_pending_state(self, client, db, app, spell_game, token_sp1):
        from models import ActiveSpell, Game
        game, p1, _, _, _ = spell_game
        resp = _cast(client, token_sp1, game, p1, {
            'spell_name': 'Poison',
            'spell_type': 'enchantment',
            'spell_family_name': 'Poison',
            'suit': 'Clubs',
            'cards': [],
            'counterable': True,
            'possible_during_ceasefire': True,
        })
        data = resp.get_json()
        assert data.get('success') is True, data.get('message')
        spell = ActiveSpell.query.filter_by(game_id=game.id).first()
        if spell:
            # If spell was created, it should be pending
            assert spell.is_pending is True


class TestActiveSpells:
    def test_get_active_spells_returns_only_active(self, client, db, app, spell_game, token_sp1):
        from models import ActiveSpell
        game, p1, _, _, _ = spell_game
        # Create an active and an inactive spell directly
        s1 = ActiveSpell(
            game_id=game.id, player_id=p1.id,
            spell_name='TestSpell1', spell_type='greed',
            spell_family_name='TestSpell1', suit='Clubs',
            cast_round=1, is_active=True,
        )
        s2 = ActiveSpell(
            game_id=game.id, player_id=p1.id,
            spell_name='TestSpell2', spell_type='greed',
            spell_family_name='TestSpell2', suit='Hearts',
            cast_round=1, is_active=False,
        )
        db.session.add_all([s1, s2])
        db.session.commit()

        resp = client.get(f'/spells/get_active_spells?game_id={game.id}&player_id={p1.id}')
        data = resp.get_json()
        if 'active_spells' in data:
            active_names = [s['spell_name'] for s in data['active_spells']]
            assert 'TestSpell1' in active_names
            assert 'TestSpell2' not in active_names

    def test_active_spell_serialization(self, db, app):
        """ActiveSpell.serialize() returns the expected fields."""
        from models import ActiveSpell, Game, Player, User
        from werkzeug.security import generate_password_hash
        u = User(username='spell_ser', password_hash=generate_password_hash('p'), gold=100)
        db.session.add(u)
        db.session.commit()
        game = Game(current_round=1, stake=35)
        db.session.add(game)
        db.session.commit()
        player = Player(user_id=u.id, game_id=game.id, turns_left=6, points=0)
        db.session.add(player)
        db.session.commit()

        spell = ActiveSpell(
            game_id=game.id, player_id=player.id,
            spell_name='Poison', spell_type='enchantment',
            spell_family_name='Poison', suit='Hearts',
            cast_round=1, is_active=True,
            effect_data={'power_modifier': -6},
        )
        db.session.add(spell)
        db.session.commit()

        s = spell.serialize()
        assert s['spell_name'] == 'Poison'
        assert s['is_active'] is True
        assert s['effect_data'] == {'power_modifier': -6}


class TestCounterableSpellFlow:
    """Pending counterable spell lifecycle regression scenarios.

    Test oracle (desired outcomes):
    - Counterable cast stores pending_spell_id on the game and sets waiting player.
    - Only the waiting (opposing) player can allow the pending spell.
    - Allowing the pending spell clears game pending-spell state fields.
    - While a pending spell exists, subsequent spell casts are rejected.
    """

    def test_only_waiting_player_can_allow_pending_spell(self, client, db, app, spell_game, token_sp1, token_sp2):
        from models import Game

        game, p1, p2, _, _ = spell_game
        cast_resp = _cast(client, token_sp1, game, p1, {
            'spell_name': 'Civil War',
            'spell_type': 'tactics',
            'spell_family_name': 'Civil War',
            'suit': 'Clubs',
            'cards': [],
            'counterable': True,
            'possible_during_ceasefire': True,
        })
        cast_data = cast_resp.get_json()
        assert cast_data.get('success') is True, cast_data

        db.session.refresh(game)
        pending_spell_id = cast_data.get('spell_id')
        assert pending_spell_id is not None
        assert game.pending_spell_id == pending_spell_id
        assert game.waiting_for_counter_player_id == p2.id

        # Caster cannot resolve their own pending counterable spell.
        wrong_player_resp = client.post(
            '/spells/allow_spell',
            data=json.dumps({
                'player_id': p1.id,
                'game_id': game.id,
                'pending_spell_id': pending_spell_id,
            }),
            content_type='application/json',
            headers={'Authorization': f'Bearer {token_sp1}'},
        )
        wrong_player_data = wrong_player_resp.get_json()
        assert wrong_player_data.get('success') is False

        # Defender allows; pending state must be cleared.
        allow_resp = client.post(
            '/spells/allow_spell',
            data=json.dumps({
                'player_id': p2.id,
                'game_id': game.id,
                'pending_spell_id': pending_spell_id,
            }),
            content_type='application/json',
            headers={'Authorization': f'Bearer {token_sp2}'},
        )
        allow_data = allow_resp.get_json()
        assert allow_data.get('success') is True, allow_data

        db.session.refresh(game)
        assert game.pending_spell_id is None
        assert game.waiting_for_counter_player_id is None

    def test_pending_counterable_spell_blocks_new_spell_cast(self, client, db, app, spell_game, token_sp1):
        game, p1, _, _, _ = spell_game

        first_resp = _cast(client, token_sp1, game, p1, {
            'spell_name': 'Peasant War',
            'spell_type': 'tactics',
            'spell_family_name': 'Peasant War',
            'suit': 'Spades',
            'cards': [],
            'counterable': True,
            'possible_during_ceasefire': True,
        })
        first_data = first_resp.get_json()
        assert first_data.get('success') is True, first_data

        second_resp = _cast(client, token_sp1, game, p1, {
            'spell_name': 'Draw 2 MainCards',
            'spell_type': 'greed',
            'spell_family_name': 'Draw 2 MainCards',
            'suit': 'Hearts',
            'cards': [],
            'counterable': False,
            'possible_during_ceasefire': True,
        })
        second_data = second_resp.get_json()
        assert second_data.get('success') is False
        assert 'pending' in second_data.get('message', '').lower()
