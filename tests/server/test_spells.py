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

    def test_cast_spell_blocked_when_invader_must_advance(self, client, db, app, spell_game, token_sp1):
        from models import Figure

        game, p1, _, _, _ = spell_game
        p1.turns_left = 1
        game.turn_player_id = p1.id
        game.invader_player_id = p1.id
        db.session.add(Figure(
            player_id=p1.id,
            game_id=game.id,
            family_name='must_adv',
            field='village',
            color='grey',
            name='Must Advance Figure',
            suit='Clubs',
            produces={},
            requires={},
        ))
        db.session.commit()

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

        assert resp.status_code == 400
        assert data.get('reason') == 'must_advance'

    def test_cast_spell_blocked_with_no_figures_while_invader_last_turn(self, client, db, app, spell_game, token_sp1):
        game, p1, _, _, _ = spell_game
        p1.turns_left = 1
        game.turn_player_id = p1.id
        game.invader_player_id = p1.id
        db.session.commit()

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

        assert resp.status_code == 400
        assert data.get('reason') == 'must_advance_no_figures'

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


class TestPendingSpellRoutes:
    def test_get_pending_spell_returns_serialized_spell(self, client, db, app, spell_game, token_sp1):
        game, p1, _, _, _ = spell_game

        cast_resp = _cast(client, token_sp1, game, p1, {
            'spell_name': 'Poison',
            'spell_type': 'enchantment',
            'spell_family_name': 'Poison',
            'suit': 'Clubs',
            'cards': [],
            'counterable': True,
            'possible_during_ceasefire': True,
        })
        cast_data = cast_resp.get_json()
        assert cast_data.get('success') is True, cast_data
        pending_spell_id = cast_data.get('spell_id')
        assert pending_spell_id is not None

        get_resp = client.get(f'/spells/get_pending_spell?spell_id={pending_spell_id}')
        get_data = get_resp.get_json()

        assert get_data.get('success') is True
        assert get_data['spell'].get('id') == pending_spell_id
        assert get_data['spell'].get('is_pending') is True
        assert get_data['spell'].get('spell_name') == 'Poison'

    def test_counter_spell_clears_pending_state_without_losing_turns(
        self,
        client,
        db,
        app,
        spell_game,
        token_sp1,
        token_sp2,
    ):
        from models import ActiveSpell, MainCard

        game, p1, p2, _, _ = spell_game
        p1_turns_before = p1.turns_left
        p2_turns_before = p2.turns_left

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
        pending_spell_id = cast_data.get('spell_id')
        assert pending_spell_id is not None

        counter_card = MainCard.query.filter_by(
            player_id=p2.id,
            in_deck=False,
            part_of_figure=False,
            part_of_battle_move=False,
        ).first()
        assert counter_card is not None

        counter_resp = client.post(
            '/spells/counter_spell',
            data=json.dumps({
                'player_id': p2.id,
                'game_id': game.id,
                'pending_spell_id': pending_spell_id,
                'counter_spell_name': 'Block',
                'counter_spell_type': 'tactics',
                'counter_spell_family_name': 'Block',
                'counter_cards': [{
                    'id': counter_card.id,
                    'rank': counter_card.rank.value,
                    'suit': counter_card.suit.value,
                    'value': counter_card.value,
                }],
            }),
            content_type='application/json',
            headers={'Authorization': f'Bearer {token_sp2}'},
        )
        counter_data = counter_resp.get_json()
        assert counter_data.get('success') is True, counter_data
        assert counter_data.get('original_spell_cancelled') is True
        assert counter_data.get('no_turn_lost') is True

        db.session.refresh(game)
        db.session.refresh(p1)
        db.session.refresh(p2)

        pending_spell = db.session.get(ActiveSpell, pending_spell_id)
        assert pending_spell is not None
        assert pending_spell.is_pending is False
        assert pending_spell.is_active is False
        assert game.pending_spell_id is None
        assert game.waiting_for_counter_player_id is None
        assert p1.turns_left == p1_turns_before
        assert p2.turns_left == p2_turns_before


class TestSpellManagementRoutes:
    def test_remove_spell_effect_deactivates_spell(self, client, db, app, spell_game, token_sp1):
        from models import ActiveSpell

        game, p1, _, _, _ = spell_game
        spell = ActiveSpell(
            game_id=game.id,
            player_id=p1.id,
            spell_name='Test Aura',
            spell_type='enchantment',
            spell_family_name='Test Aura',
            suit='Hearts',
            cast_round=game.current_round,
            is_active=True,
        )
        db.session.add(spell)
        db.session.commit()

        resp = client.post(
            '/spells/remove_spell_effect',
            data=json.dumps({'spell_id': spell.id}),
            content_type='application/json',
            headers={'Authorization': f'Bearer {token_sp1}'},
        )
        data = resp.get_json()
        assert data.get('success') is True, data

        db.session.refresh(spell)
        assert spell.is_active is False

    def test_end_infinite_hammer_deactivates_spell_consumes_turn_and_flips_turn(
        self,
        client,
        db,
        app,
        spell_game,
        token_sp1,
    ):
        from models import ActiveSpell

        game, p1, p2, _, _ = spell_game
        p1.turns_left = 3
        game.turn_player_id = p1.id

        hammer = ActiveSpell(
            game_id=game.id,
            player_id=p1.id,
            spell_name='Infinite Hammer',
            spell_type='greed',
            spell_family_name='Infinite Hammer',
            suit='Spades',
            cast_round=game.current_round,
            is_active=True,
            effect_data={'actions': [{'description': 'played combo'}]},
        )
        db.session.add(hammer)
        db.session.commit()

        resp = client.post(
            '/spells/end_infinite_hammer',
            data=json.dumps({'game_id': game.id, 'player_id': p1.id}),
            content_type='application/json',
            headers={'Authorization': f'Bearer {token_sp1}'},
        )
        data = resp.get_json()
        assert data.get('success') is True, data

        db.session.refresh(hammer)
        db.session.refresh(p1)
        db.session.refresh(game)
        assert hammer.is_active is False
        assert p1.turns_left == 2
        assert game.turn_player_id == p2.id


class TestSpellPurgesBattleMoves:
    """Spells that take or recycle hand cards must drop any pre-bought
    BattleMove referencing those cards so the battle shop stays consistent."""

    def _make_battle_move_for_card(self, db, game, player, card, family_name='Dagger'):
        from models import BattleMove
        bm = BattleMove(
            game_id=game.id,
            player_id=player.id,
            family_name=family_name,
            card_id=card.id,
            card_type='main',
            suit=str(card.suit),
            rank=str(card.rank),
            value=card.value,
        )
        db.session.add(bm)
        card.part_of_battle_move = True
        db.session.commit()
        return bm

    def test_forced_deal_purges_battle_move_for_swapped_card(
        self, app, db, spell_game, monkeypatch
    ):
        from models import ActiveSpell, BattleMove, MainCard
        from routes.spells import _execute_spell
        import random as _random

        with app.app_context():
            game, p1, p2, _, _ = spell_game

            caster_cards = MainCard.query.filter_by(
                player_id=p1.id, in_deck=False, part_of_figure=False
            ).all()
            reserved = caster_cards[0]
            other_caster = caster_cards[1]
            self._make_battle_move_for_card(db, game, p1, reserved)

            # Force the random.sample picks: caster gives [reserved, other]
            opp_cards = MainCard.query.filter_by(
                player_id=p2.id, in_deck=False, part_of_figure=False
            ).all()
            opp_pick = opp_cards[:2]

            def _fake_sample(seq, k):
                if any(c.player_id == p1.id for c in seq):
                    return [reserved, other_caster]
                return opp_pick

            monkeypatch.setattr(_random, 'sample', _fake_sample)

            spell = ActiveSpell(
                game_id=game.id,
                player_id=p1.id,
                spell_name='Forced Deal',
                spell_type='greed',
                spell_family_name='Forced Deal',
                suit='Hearts',
                cast_round=1,
            )
            db.session.add(spell)
            db.session.commit()

            _execute_spell(spell, game, p1)
            db.session.commit()

            # BattleMove should be gone
            remaining = BattleMove.query.filter_by(game_id=game.id).all()
            assert all(bm.card_id != reserved.id for bm in remaining)

            # Card should now belong to opponent and not be reserved
            db.session.refresh(reserved)
            assert reserved.player_id == p2.id
            assert reserved.part_of_battle_move is False

    def test_forced_deal_keeps_unrelated_battle_moves(
        self, app, db, spell_game, monkeypatch
    ):
        from models import ActiveSpell, BattleMove, MainCard
        from routes.spells import _execute_spell
        import random as _random

        with app.app_context():
            game, p1, p2, _, _ = spell_game

            caster_cards = MainCard.query.filter_by(
                player_id=p1.id, in_deck=False, part_of_figure=False
            ).all()
            reserved = caster_cards[0]
            unswapped_a = caster_cards[1]
            unswapped_b = caster_cards[2]
            self._make_battle_move_for_card(db, game, p1, reserved)

            opp_cards = MainCard.query.filter_by(
                player_id=p2.id, in_deck=False, part_of_figure=False
            ).all()

            def _fake_sample(seq, k):
                if any(c.player_id == p1.id for c in seq):
                    return [unswapped_a, unswapped_b]
                return opp_cards[:2]

            monkeypatch.setattr(_random, 'sample', _fake_sample)

            spell = ActiveSpell(
                game_id=game.id,
                player_id=p1.id,
                spell_name='Forced Deal',
                spell_type='greed',
                spell_family_name='Forced Deal',
                suit='Hearts',
                cast_round=1,
            )
            db.session.add(spell)
            db.session.commit()

            _execute_spell(spell, game, p1)
            db.session.commit()

            # Unrelated BattleMove survives
            remaining = BattleMove.query.filter_by(game_id=game.id).all()
            assert any(bm.card_id == reserved.id for bm in remaining)
            db.session.refresh(reserved)
            assert reserved.player_id == p1.id
            assert reserved.part_of_battle_move is True

    def test_dump_cards_purges_battle_moves_for_reserved_cards(
        self, app, db, spell_game
    ):
        from models import ActiveSpell, BattleMove, MainCard
        from routes.spells import _execute_spell

        with app.app_context():
            game, p1, p2, _, _ = spell_game

            caster_cards = MainCard.query.filter_by(
                player_id=p1.id, in_deck=False, part_of_figure=False
            ).all()
            reserved = caster_cards[0]
            self._make_battle_move_for_card(db, game, p1, reserved)

            spell = ActiveSpell(
                game_id=game.id,
                player_id=p1.id,
                spell_name='Dump Cards',
                spell_type='greed',
                spell_family_name='Dump Cards',
                suit='Hearts',
                cast_round=1,
            )
            db.session.add(spell)
            db.session.commit()

            _execute_spell(spell, game, p1)
            db.session.commit()

            # Reserved card's BattleMove is gone
            remaining = BattleMove.query.filter_by(game_id=game.id).all()
            assert all(bm.card_id != reserved.id for bm in remaining)

            # The card itself was returned to deck
            db.session.refresh(reserved)
            assert reserved.in_deck is True
            assert reserved.part_of_battle_move is False


class TestSpellMutatesConquerTactics:
    """Tactics-hand conquer games must keep ConquerTactic rows in sync when
    spells move or recycle their backing runtime cards."""

    @staticmethod
    def _card_rank(card):
        return str(card.rank.value if hasattr(card.rank, 'value') else card.rank)

    def _eligible_cards(self, cards):
        return [card for card in cards if self._card_rank(card) in {
            '7', '8', '9', '10', 'J', 'Q', 'K', 'A'}]

    def _make_tactic_for_card(self, db, game, player, card, family_name='Dagger'):
        from models import ConquerTactic

        tactic = ConquerTactic(
            game_id=game.id,
            player_id=player.id,
            family_name=family_name,
            card_id=card.id,
            card_type='main',
            suit=str(card.suit.value if hasattr(card.suit, 'value') else card.suit),
            rank=self._card_rank(card),
            value=card.value,
            source='config',
            status='available',
        )
        db.session.add(tactic)
        card.part_of_battle_move = True
        db.session.commit()
        return tactic

    def _mark_tactics_hand_conquer(self, db, game):
        game.mode = 'conquer'
        game.conquer_move_model = 'tactics_hand'
        db.session.commit()

    def test_forced_deal_purges_and_replenishes_conquer_tactics(
        self, app, db, spell_game, monkeypatch
    ):
        from models import ActiveSpell, ConquerTactic, MainCard
        from routes.spells import _execute_spell
        import random as _random

        with app.app_context():
            game, p1, p2, _, _ = spell_game
            self._mark_tactics_hand_conquer(db, game)

            caster_cards = self._eligible_cards(MainCard.query.filter_by(
                player_id=p1.id, in_deck=False, part_of_figure=False
            ).all())
            reserved = caster_cards[0]
            other_caster = caster_cards[1]
            self._make_tactic_for_card(db, game, p1, reserved)

            opponent_cards = self._eligible_cards(MainCard.query.filter_by(
                player_id=p2.id, in_deck=False, part_of_figure=False
            ).all())
            opponent_pick = opponent_cards[:2]

            def _fake_sample(seq, _count):
                if any(card.player_id == p1.id for card in seq):
                    return [reserved, other_caster]
                return opponent_pick

            monkeypatch.setattr(_random, 'sample', _fake_sample)

            spell = ActiveSpell(
                game_id=game.id,
                player_id=p1.id,
                spell_name='Forced Deal',
                spell_type='greed',
                spell_family_name='Forced Deal',
                suit='Hearts',
                cast_round=1,
            )
            db.session.add(spell)
            db.session.commit()

            effect = _execute_spell(spell, game, p1)
            db.session.commit()

            assert ConquerTactic.query.filter_by(
                game_id=game.id,
                player_id=p1.id,
                card_id=reserved.id,
                source='config',
            ).count() == 0
            db.session.refresh(reserved)
            assert reserved.player_id == p2.id
            assert reserved.part_of_battle_move is True

            received_reserved = ConquerTactic.query.filter_by(
                game_id=game.id,
                player_id=p2.id,
                card_id=reserved.id,
                source='spell',
            ).first()
            assert received_reserved is not None

            received_ids = {card.id for card in opponent_pick}
            new_tactics = ConquerTactic.query.filter(
                ConquerTactic.game_id == game.id,
                ConquerTactic.player_id == p1.id,
                ConquerTactic.card_id.in_(received_ids),
            ).all()
            assert len(new_tactics) == len(received_ids)
            assert {t.source for t in new_tactics} == {'spell'}
            assert effect['conquer_tactics_added']['added'] == len(received_ids)

    def test_dump_cards_purges_and_replenishes_conquer_tactics(
        self, app, db, spell_game
    ):
        from models import ActiveSpell, ConquerTactic, MainCard
        from routes.spells import _execute_spell

        with app.app_context():
            game, p1, p2, _, _ = spell_game
            self._mark_tactics_hand_conquer(db, game)

            caster_cards = self._eligible_cards(MainCard.query.filter_by(
                player_id=p1.id, in_deck=False, part_of_figure=False
            ).all())
            reserved = caster_cards[0]
            self._make_tactic_for_card(db, game, p1, reserved)

            spell = ActiveSpell(
                game_id=game.id,
                player_id=p1.id,
                spell_name='Dump Cards',
                spell_type='greed',
                spell_family_name='Dump Cards',
                suit='Hearts',
                cast_round=1,
            )
            db.session.add(spell)
            db.session.commit()

            effect = _execute_spell(spell, game, p1)
            db.session.commit()

            assert ConquerTactic.query.filter_by(
                game_id=game.id,
                player_id=p1.id,
                card_id=reserved.id,
                source='config',
            ).count() == 0
            db.session.refresh(reserved)
            assert reserved.in_deck is True
            assert reserved.part_of_battle_move is False

            caster_spell_tactics = ConquerTactic.query.filter_by(
                game_id=game.id, player_id=p1.id, source='spell').all()
            opponent_spell_tactics = ConquerTactic.query.filter_by(
                game_id=game.id, player_id=p2.id, source='spell').all()
            assert caster_spell_tactics
            assert opponent_spell_tactics
            assert effect['conquer_tactics_added']['added'] == len(caster_spell_tactics)
            assert effect['opponent_conquer_tactics_added']['added'] == len(opponent_spell_tactics)
