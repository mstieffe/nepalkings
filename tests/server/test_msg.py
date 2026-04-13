# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for message and chat endpoints.

Test oracle (desired outcomes):
- Authenticated players can create chat/log entries for their own player ids.
- Player ownership is enforced for chat sender_id and optional log player_id.
- Messages are truncated to configured maximum lengths.
- GET endpoints return persisted entries for a game in API shape expected by clients.
"""

import json

import pytest


@pytest.fixture
def msg_game(db):
    from game_service.deck import Deck
    from models import Game, Player, User
    from werkzeug.security import generate_password_hash

    u1 = User(username='msg_p1', password_hash=generate_password_hash('p'), gold=120)
    u2 = User(username='msg_p2', password_hash=generate_password_hash('p'), gold=120)
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

    # Keep fixture aligned with real game setup where cards exist.
    deck = Deck(game)
    deck.create()
    deck.shuffle()
    deck.deal_cards([p1, p2], num_main_cards=12, num_side_cards=0)

    return game, p1, p2


@pytest.fixture
def msg_ai_game(db):
    from game_service.deck import Deck
    from models import Game, Player, User
    from werkzeug.security import generate_password_hash

    human = User(username='msg_human_ai', password_hash=generate_password_hash('p'), gold=120)
    ai_user = User(username='[AI] msg_bot', password_hash=generate_password_hash('p'), gold=120, is_ai=True)
    db.session.add_all([human, ai_user])
    db.session.commit()

    game = Game(current_round=1, stake=35)
    db.session.add(game)
    db.session.commit()

    p_human = Player(user_id=human.id, game_id=game.id, turns_left=6, points=0)
    p_ai = Player(user_id=ai_user.id, game_id=game.id, turns_left=6, points=0)
    db.session.add_all([p_human, p_ai])
    db.session.commit()

    game.turn_player_id = p_human.id
    game.invader_player_id = p_human.id
    db.session.commit()

    deck = Deck(game)
    deck.create()
    deck.shuffle()
    deck.deal_cards([p_human, p_ai], num_main_cards=12, num_side_cards=0)

    return game, p_human, p_ai


@pytest.fixture
def msg_token_p1(app, msg_game):
    from routes.auth import generate_token

    _, p1, _ = msg_game
    return generate_token(p1.user_id)


@pytest.fixture
def msg_token_p2(app, msg_game):
    from routes.auth import generate_token

    _, _, p2 = msg_game
    return generate_token(p2.user_id)


@pytest.fixture
def msg_token_human_vs_ai(app, msg_ai_game):
    from routes.auth import generate_token

    _, p_human, _ = msg_ai_game
    return generate_token(p_human.user_id)


class TestChatMessages:
    def test_add_and_get_chat_messages_enforces_ownership_and_truncates(
        self,
        client,
        msg_game,
        msg_token_p1,
        msg_token_p2,
    ):
        game, p1, p2 = msg_game

        # Sender ownership is required: p1 token cannot send as p2.
        forbidden_resp = client.post(
            '/msg/add_chat_message',
            data=json.dumps(
                {
                    'game_id': game.id,
                    'sender_id': p2.id,
                    'receiver_id': p1.id,
                    'message': 'forbidden',
                }
            ),
            content_type='application/json',
            headers={'Authorization': f'Bearer {msg_token_p1}'},
        )
        forbidden_data = forbidden_resp.get_json()
        assert forbidden_resp.status_code == 403
        assert forbidden_data.get('success') is False

        long_msg = 'x' * 1205
        ok_resp = client.post(
            '/msg/add_chat_message',
            data=json.dumps(
                {
                    'game_id': game.id,
                    'sender_id': p1.id,
                    'receiver_id': p2.id,
                    'message': long_msg,
                }
            ),
            content_type='application/json',
            headers={'Authorization': f'Bearer {msg_token_p1}'},
        )
        ok_data = ok_resp.get_json()
        assert ok_data.get('success') is True
        assert len(ok_data['chat_message']['message']) == 1000

        get_resp = client.get(f'/msg/get_chat_messages?game_id={game.id}')
        get_data = get_resp.get_json()
        assert get_data.get('success') is True
        assert len(get_data['chat_messages']) == 1
        assert get_data['chat_messages'][0]['sender_id'] == p1.id
        assert get_data['chat_messages'][0]['receiver_id'] == p2.id
        assert len(get_data['chat_messages'][0]['message']) == 1000

    def test_add_chat_message_to_ai_explain_command_appends_ai_auto_messages(
        self,
        client,
        msg_ai_game,
        msg_token_human_vs_ai,
        monkeypatch,
    ):
        game, p_human, p_ai = msg_ai_game

        monkeypatch.setattr(
            'ai.ai_worker.handle_explain_chat_control',
            lambda **_kwargs: [
                'Explain settings updated. cadence=turn, depth=extensive.',
                'Tactical explain (manual, extensive): Candidate 1: advance strongest.',
            ],
        )

        add_resp = client.post(
            '/msg/add_chat_message',
            data=json.dumps(
                {
                    'game_id': game.id,
                    'sender_id': p_human.id,
                    'receiver_id': p_ai.id,
                    'message': 'explain yourself mode turn depth extensive',
                }
            ),
            content_type='application/json',
            headers={'Authorization': f'Bearer {msg_token_human_vs_ai}'},
        )
        add_data = add_resp.get_json()

        assert add_data.get('success') is True
        assert len(add_data.get('ai_auto_messages') or []) == 2
        assert all(m['sender_id'] == p_ai.id for m in add_data['ai_auto_messages'])
        assert all(m['receiver_id'] == p_human.id for m in add_data['ai_auto_messages'])

        get_resp = client.get(f'/msg/get_chat_messages?game_id={game.id}')
        get_data = get_resp.get_json()

        assert get_data.get('success') is True
        assert len(get_data['chat_messages']) == 3
        sender_ids = [m['sender_id'] for m in get_data['chat_messages']]
        assert sender_ids.count(p_human.id) == 1
        assert sender_ids.count(p_ai.id) == 2


class TestLogEntries:
    def test_add_and_get_log_entries_with_truncation(
        self,
        client,
        msg_game,
        msg_token_p1,
    ):
        game, p1, _ = msg_game

        long_log = 'L' * 760
        add_resp = client.post(
            '/msg/add_log_entry',
            data=json.dumps(
                {
                    'game_id': game.id,
                    'player_id': p1.id,
                    'round_number': 1,
                    'turn_number': 1,
                    'message': long_log,
                    'author': 'msg_p1',
                    'type': 'turn_summary',
                }
            ),
            content_type='application/json',
            headers={'Authorization': f'Bearer {msg_token_p1}'},
        )
        add_data = add_resp.get_json()
        assert add_data.get('success') is True
        assert len(add_data['log_entry']['message']) == 500

        # System entries may omit player_id and should still be accepted.
        system_resp = client.post(
            '/msg/add_log_entry',
            data=json.dumps(
                {
                    'game_id': game.id,
                    'round_number': 1,
                    'turn_number': 2,
                    'message': 'system entry',
                    'author': 'System',
                    'type': 'system',
                }
            ),
            content_type='application/json',
            headers={'Authorization': f'Bearer {msg_token_p1}'},
        )
        system_data = system_resp.get_json()
        assert system_data.get('success') is True

        get_resp = client.get(f'/msg/get_log_entries?game_id={game.id}')
        get_data = get_resp.get_json()
        assert get_data.get('success') is True
        assert len(get_data['log_entries']) == 2
        assert get_data['log_entries'][0]['turn_number'] == 1
        assert len(get_data['log_entries'][0]['message']) == 500

    def test_get_log_entries_requires_game_id(self, client):
        resp = client.get('/msg/get_log_entries')
        data = resp.get_json()
        assert resp.status_code == 400
        assert data.get('success') is False