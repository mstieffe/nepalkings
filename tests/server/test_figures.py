# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for figure building, picking up, and resource management."""
import pytest


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def game_with_players(db):
    """Set up a minimal game with two players and a full shuffled deck."""
    from models import Game, Player, User
    from werkzeug.security import generate_password_hash
    from game_service.deck import Deck

    u1 = User(username='fig_p1', password_hash=generate_password_hash('p'), gold=100)
    u2 = User(username='fig_p2', password_hash=generate_password_hash('p'), gold=100)
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
def auth_token_p1(app, game_with_players):
    from routes.auth import generate_token
    _, p1, _, _, _ = game_with_players
    return generate_token(p1.user_id)


def _headers(token):
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def _get_hand_card(db, game_id, player_id, rank=None, suit=None, exclude_ids=None):
    """Get a card from a player's hand (not in deck, not part of figure)."""
    from models import MainCard

    q = MainCard.query.filter_by(
        player_id=player_id,
        in_deck=False,
        part_of_figure=False,
        part_of_battle_move=False,
    )
    if rank:
        q = q.filter(MainCard.rank == rank)
    if suit:
        q = q.filter(MainCard.suit == suit)
    if exclude_ids:
        q = q.filter(~MainCard.id.in_(exclude_ids))
    card = q.first()
    if card:
        return card

    # Deterministic fallback: pull a valid card from this game's card pool.
    q = MainCard.query.filter_by(
        game_id=game_id,
        part_of_figure=False,
        part_of_battle_move=False,
    )
    if rank:
        q = q.filter(MainCard.rank == rank)
    if suit:
        q = q.filter(MainCard.suit == suit)
    if exclude_ids:
        q = q.filter(~MainCard.id.in_(exclude_ids))
    card = q.first()
    if not card:
        return None

    card.player_id = player_id
    card.in_deck = False
    db.session.commit()
    return card


def _build_king_figure(
    client,
    db,
    game,
    player,
    token,
    suit='Clubs',
    name='Himalaya King',
    upgrade_family_name=None,
):
    """Helper: place a king-type castle figure using the /figures/create_figure endpoint."""
    king_card = _get_hand_card(db, game.id, player.id, rank='K', suit=suit)
    assert king_card is not None, f"No {suit} King available"

    payload = {
        'player_id': player.id,
        'game_id': game.id,
        'family_name': name,
        'field': 'castle',
        'color': 'defensive',
        'name': name,
        'suit': suit,
        'description': '',
        'upgrade_family_name': upgrade_family_name,
        'produces': {'villager_black': 2, 'warrior_black': 1},
        'requires': {},
        'cards': [{'id': king_card.id, 'type': 'main', 'role': 'key'}],
    }
    import json
    return client.post('/figures/create_figure', data=json.dumps(payload),
                       content_type='application/json',
                       headers={'Authorization': f'Bearer {token}'})


class TestBuildFigure:
    def test_build_castle_figure_creates_figure_record(self, client, db, app, game_with_players, auth_token_p1):
        from models import Figure
        game, p1, _, _, _ = game_with_players
        initial_count = Figure.query.filter_by(game_id=game.id, player_id=p1.id).count()
        resp = _build_king_figure(client, db, game, p1, auth_token_p1)
        data = resp.get_json()
        assert data.get('success') is True, data.get('message')
        count_after = Figure.query.filter_by(game_id=game.id, player_id=p1.id).count()
        assert count_after == initial_count + 1

    def test_build_figure_marks_card_as_part_of_figure(self, client, db, app, game_with_players, auth_token_p1):
        from models import MainCard
        game, p1, _, _, _ = game_with_players
        resp = _build_king_figure(client, db, game, p1, auth_token_p1)
        data = resp.get_json()
        assert data.get('success') is True, data.get('message')
        # The king card used should now be marked as part of figure
        figure = data['figure']
        card_id = figure['cards'][0]['card_id']
        card = db.session.get(MainCard, card_id)
        assert card.part_of_figure is True

    def test_build_figure_consumes_player_turn(self, client, db, app, game_with_players, auth_token_p1):
        from models import Player
        game, p1, _, _, _ = game_with_players
        turns_before = p1.turns_left
        _build_king_figure(client, db, game, p1, auth_token_p1)
        db.session.refresh(p1)
        assert p1.turns_left == turns_before - 1

    def test_build_figure_requires_auth(self, client, db, app, game_with_players):
        import json
        game, p1, _, _, _ = game_with_players
        king_card = _get_hand_card(db, game.id, p1.id, rank='K')
        assert king_card is not None
        payload = {
            'player_id': p1.id,
            'game_id': game.id,
            'family_name': 'Himalaya King',
            'field': 'castle',
            'color': 'defensive',
            'name': 'Himalaya King',
            'suit': king_card.suit.value,
            'description': '',
            'upgrade_family_name': None,
            'produces': {},
            'requires': {},
            'cards': [{'id': king_card.id, 'type': 'main', 'role': 'key'}],
        }
        resp = client.post('/figures/create_figure', data=json.dumps(payload),
                           content_type='application/json')
        assert resp.status_code == 401

    def test_build_figure_produces_field_stored(self, client, db, app, game_with_players, auth_token_p1):
        from models import Figure
        game, p1, _, _, _ = game_with_players
        _build_king_figure(client, db, game, p1, auth_token_p1)
        fig = Figure.query.filter_by(game_id=game.id, player_id=p1.id, field='castle').first()
        assert fig is not None
        assert fig.produces is not None
        assert len(fig.produces) > 0


class TestPickUpFigure:
    def test_pick_up_figure_returns_cards_to_hand(self, client, db, app, game_with_players, auth_token_p1):
        import json
        from models import Figure, MainCard
        game, p1, _, _, _ = game_with_players
        _build_king_figure(client, db, game, p1, auth_token_p1)
        fig = Figure.query.filter_by(game_id=game.id, player_id=p1.id).order_by(Figure.id.desc()).first()
        assert fig is not None
        # The card should currently be part of figure
        ctf = fig.cards[0]
        card = db.session.get(MainCard, ctf.card_id)
        assert card.part_of_figure is True

        payload = {'player_id': p1.id, 'game_id': game.id, 'figure_id': fig.id}
        resp = client.post('/figures/pickup_figure', data=json.dumps(payload),
                           content_type='application/json',
                           headers={'Authorization': f'Bearer {auth_token_p1}'})
        data = resp.get_json()
        assert data.get('success') is True, data.get('message')
        db.session.refresh(card)
        assert card.part_of_figure is False

    def test_pick_up_figure_deletes_figure_record(self, client, db, app, game_with_players, auth_token_p1):
        import json
        from models import Figure
        game, p1, _, _, _ = game_with_players
        _build_king_figure(client, db, game, p1, auth_token_p1)
        fig = Figure.query.filter_by(game_id=game.id, player_id=p1.id).order_by(Figure.id.desc()).first()
        fig_id = fig.id

        payload = {'player_id': p1.id, 'game_id': game.id, 'figure_id': fig_id}
        client.post('/figures/pickup_figure', data=json.dumps(payload),
                    content_type='application/json',
                    headers={'Authorization': f'Bearer {auth_token_p1}'})
        assert db.session.get(Figure, fig_id) is None

    def test_pick_up_figure_fails_when_not_found(self, client, db, app, game_with_players, auth_token_p1):
        import json
        game, p1, _, _, _ = game_with_players
        payload = {'player_id': p1.id, 'game_id': game.id, 'figure_id': 9999}
        resp = client.post('/figures/pickup_figure', data=json.dumps(payload),
                           content_type='application/json',
                           headers={'Authorization': f'Bearer {auth_token_p1}'})
        data = resp.get_json()
        assert data.get('success') is False


class TestFigureRouteCoverage:
    def test_get_figure_returns_serialized_figure(self, client, db, app, game_with_players, auth_token_p1):
        from models import Figure

        game, p1, _, _, _ = game_with_players
        _build_king_figure(client, db, game, p1, auth_token_p1)
        figure = Figure.query.filter_by(game_id=game.id, player_id=p1.id).order_by(Figure.id.desc()).first()
        assert figure is not None

        resp = client.get(
            f'/figures/get_figure?figure_id={figure.id}',
            headers={'Authorization': f'Bearer {auth_token_p1}'},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True
        assert data.get('figure', {}).get('id') == figure.id

    def test_get_figures_returns_players_figures(self, client, db, app, game_with_players, auth_token_p1):
        from models import Figure

        game, p1, _, _, _ = game_with_players
        _build_king_figure(client, db, game, p1, auth_token_p1)
        created = Figure.query.filter_by(game_id=game.id, player_id=p1.id).order_by(Figure.id.desc()).first()
        assert created is not None

        resp = client.get(
            f'/figures/get_figures?player_id={p1.id}',
            headers={'Authorization': f'Bearer {auth_token_p1}'},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True
        assert any(fig.get('id') == created.id for fig in data.get('figures', []))

    def test_update_figure_changes_name_and_consumes_turn(self, client, db, app, game_with_players, auth_token_p1):
        from models import Figure

        game, p1, _, _, _ = game_with_players
        turns_before = p1.turns_left

        _build_king_figure(client, db, game, p1, auth_token_p1)
        figure = Figure.query.filter_by(game_id=game.id, player_id=p1.id).order_by(Figure.id.desc()).first()
        assert figure is not None

        resp = client.post(
            '/figures/update_figure',
            json={
                'figure_id': figure.id,
                'name': 'Updated Himalaya King',
                'description': 'updated description',
            },
            headers={'Authorization': f'Bearer {auth_token_p1}'},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True, data

        db.session.refresh(figure)
        db.session.refresh(p1)
        assert figure.name == 'Updated Himalaya King'
        assert p1.turns_left == turns_before - 2  # one build action + one update action

    def test_delete_figure_removes_figure_and_returns_cards_to_deck(
        self,
        client,
        db,
        app,
        game_with_players,
        auth_token_p1,
    ):
        from models import Figure, MainCard

        game, p1, _, _, _ = game_with_players
        _build_king_figure(client, db, game, p1, auth_token_p1)
        figure = Figure.query.filter_by(game_id=game.id, player_id=p1.id).order_by(Figure.id.desc()).first()
        assert figure is not None

        figure_card_id = figure.cards[0].card_id

        resp = client.post(
            '/figures/delete_figure',
            json={
                'figure_id': figure.id,
                'player_id': p1.id,
                'game_id': game.id,
            },
            headers={'Authorization': f'Bearer {auth_token_p1}'},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True, data
        assert db.session.get(Figure, figure.id) is None

        card = db.session.get(MainCard, figure_card_id)
        assert card is not None
        assert card.part_of_figure is False
        assert card.in_deck is True

    def test_upgrade_figure_creates_upgraded_family_figure(
        self,
        client,
        db,
        app,
        game_with_players,
        auth_token_p1,
    ):
        from models import Figure, MainCard

        game, p1, _, _, _ = game_with_players
        build_resp = _build_king_figure(
            client,
            db,
            game,
            p1,
            auth_token_p1,
            name='Himalaya King',
            upgrade_family_name='Himalaya Emperor',
        )
        build_data = build_resp.get_json()
        assert build_data.get('success') is True, build_data

        figure = Figure.query.filter_by(game_id=game.id, player_id=p1.id).order_by(Figure.id.desc()).first()
        assert figure is not None
        key_card_id = figure.cards[0].card_id

        upgrade_card = _get_hand_card(db, game.id, p1.id, exclude_ids=[key_card_id])
        assert upgrade_card is not None
        assert isinstance(upgrade_card, MainCard)

        resp = client.post(
            '/figures/upgrade_figure',
            json={
                'figure_id': figure.id,
                'player_id': p1.id,
                'game_id': game.id,
                'upgrade_card_id': upgrade_card.id,
                'upgrade_card_type': 'main',
                'produces': {'villager_black': 3},
                'requires': {},
            },
            headers={'Authorization': f'Bearer {auth_token_p1}'},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True, data
        new_figure = data.get('new_figure', {})
        assert new_figure.get('family_name') == 'Himalaya Emperor'
        assert new_figure.get('name') == 'Himalaya Emperor'
        assert len(new_figure.get('cards', [])) == 2
