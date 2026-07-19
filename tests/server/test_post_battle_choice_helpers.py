# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for post-battle pending-choice route helpers."""

from datetime import datetime, timedelta, timezone
import importlib
import inspect
from types import SimpleNamespace

import pytest


games = importlib.import_module('routes.games')


class _SerializableCard:
    def __init__(self, payload):
        self.payload = payload

    def serialize(self):
        return self.payload


def test_post_battle_helper_route_api_is_stable():
    expected_signatures = {
        '_serialize_battle_card': '(card, card_type)',
        '_post_battle_choice_timeout_seconds': '()',
        '_make_post_battle_pending_choice': '(choice_type, player_id, default)',
        '_parse_pending_choice_deadline': '(pending)',
        '_pending_choice_expired': '(pending)',
        '_set_post_battle_pending_choice': '(game, choice_type, player_id, default)',
        '_clear_post_battle_pending_choice': '(game, *, defaulted=False, choice=None)',
    }

    for name, expected_signature in expected_signatures.items():
        helper = getattr(games, name)
        assert str(inspect.signature(helper)) == expected_signature
        assert helper.__module__ == 'routes.games'


def test_serialize_battle_card_mutates_and_returns_serialized_payload():
    payload = {'id': 42, 'name': 'General'}

    result = games._serialize_battle_card(_SerializableCard(payload), 'main')

    assert result is payload
    assert payload == {'id': 42, 'name': 'General', 'card_type': 'main'}


def test_serialize_battle_card_without_serializer_returns_card_type_only():
    assert games._serialize_battle_card(object(), 'side') == {'card_type': 'side'}


@pytest.mark.parametrize(
    ('configured', 'expected'),
    [
        (15, 15),
        ('9', 9),
        (0, 0),
        (-5, 0),
    ],
)
def test_post_battle_choice_timeout_normalizes_configured_value(
    monkeypatch,
    configured,
    expected,
):
    monkeypatch.setattr(
        games.settings,
        'POST_BATTLE_CHOICE_TIMEOUT_SECONDS',
        configured,
    )

    assert games._post_battle_choice_timeout_seconds() == expected


def test_post_battle_choice_timeout_rejects_invalid_configured_value(monkeypatch):
    monkeypatch.setattr(
        games.settings,
        'POST_BATTLE_CHOICE_TIMEOUT_SECONDS',
        'not-a-number',
    )

    with pytest.raises(ValueError):
        games._post_battle_choice_timeout_seconds()


def test_make_post_battle_pending_choice_uses_route_clock_and_settings(monkeypatch):
    now = datetime(2026, 7, 19, 10, 30, 15)
    monkeypatch.setattr(games, '_utcnow', lambda: now)
    monkeypatch.setattr(games.settings, 'POST_BATTLE_CHOICE_TIMEOUT_SECONDS', 45)

    result = games._make_post_battle_pending_choice(
        'winner_pick',
        17,
        {'action': 'start_round'},
    )

    assert result == {
        'type': 'winner_pick',
        'player_id': 17,
        'default': {'action': 'start_round'},
        'created_at': '2026-07-19T10:30:15',
        'deadline_at': '2026-07-19T10:31:00',
        'timeout_seconds': 45,
    }


@pytest.mark.parametrize('pending', [None, {}, {'deadline_at': ''}, {'deadline_at': 'invalid'}])
def test_parse_pending_choice_deadline_returns_none_for_missing_or_invalid_values(pending):
    assert games._parse_pending_choice_deadline(pending) is None


def test_parse_pending_choice_deadline_preserves_timezone_information():
    deadline = games._parse_pending_choice_deadline(
        {'deadline_at': '2026-07-19T12:30:00+02:00'}
    )

    assert deadline == datetime(
        2026,
        7,
        19,
        12,
        30,
        tzinfo=timezone(timedelta(hours=2)),
    )
    assert deadline.utcoffset().total_seconds() == 7200


def test_pending_choice_expired_short_circuits_for_absent_pending(monkeypatch):
    monkeypatch.setattr(
        games,
        '_post_battle_choice_timeout_seconds',
        lambda: pytest.fail('timeout should not be read'),
    )
    monkeypatch.setattr(games, '_utcnow', lambda: pytest.fail('clock should not be read'))

    assert games._pending_choice_expired(None) is False


def test_pending_choice_expired_short_circuits_when_timeout_is_disabled(monkeypatch):
    monkeypatch.setattr(games, '_post_battle_choice_timeout_seconds', lambda: 0)
    monkeypatch.setattr(games, '_utcnow', lambda: pytest.fail('clock should not be read'))

    assert games._pending_choice_expired({'deadline_at': 'invalid'}) is True


@pytest.mark.parametrize(
    ('now', 'expected'),
    [
        (datetime(2026, 7, 19, 10, 29, 59), False),
        (datetime(2026, 7, 19, 10, 30, 0), True),
        (datetime(2026, 7, 19, 10, 30, 1), True),
    ],
)
def test_pending_choice_expired_compares_route_clock_to_deadline(
    monkeypatch,
    now,
    expected,
):
    monkeypatch.setattr(games, '_post_battle_choice_timeout_seconds', lambda: 30)
    monkeypatch.setattr(games, '_utcnow', lambda: now)

    assert games._pending_choice_expired(
        {'deadline_at': '2026-07-19T10:30:00'}
    ) is expected


def test_pending_choice_expired_returns_false_without_valid_deadline(monkeypatch):
    monkeypatch.setattr(games, '_post_battle_choice_timeout_seconds', lambda: 30)
    monkeypatch.setattr(games, '_utcnow', lambda: pytest.fail('clock should not be read'))

    assert games._pending_choice_expired({'deadline_at': 'invalid'}) is False


def test_set_post_battle_pending_choice_preserves_state_and_flags_json(monkeypatch):
    game = SimpleNamespace(last_battle_result={'winner_id': 3})
    now = datetime(2026, 7, 19, 10, 30, 15)
    flagged = []
    monkeypatch.setattr(games, '_utcnow', lambda: now)
    monkeypatch.setattr(games.settings, 'POST_BATTLE_CHOICE_TIMEOUT_SECONDS', 10)
    monkeypatch.setattr(
        games,
        'flag_modified',
        lambda target, attribute: flagged.append((target, attribute)),
    )

    result = games._set_post_battle_pending_choice(
        game,
        'draw_choice',
        12,
        'defender_points',
    )

    assert result is None
    assert game.last_battle_result == {
        'winner_id': 3,
        'post_battle_pending_choice': {
            'type': 'draw_choice',
            'player_id': 12,
            'default': 'defender_points',
            'created_at': '2026-07-19T10:30:15',
            'deadline_at': '2026-07-19T10:30:25',
            'timeout_seconds': 10,
        },
    }
    assert flagged == [(game, 'last_battle_result')]


def test_set_post_battle_pending_choice_replaces_non_dict_state(monkeypatch):
    game = SimpleNamespace(last_battle_result='legacy-value')
    monkeypatch.setattr(
        games,
        '_make_post_battle_pending_choice',
        lambda *args: {'type': args[0]},
    )
    monkeypatch.setattr(games, 'flag_modified', lambda *_args: None)

    games._set_post_battle_pending_choice(game, 'winner_pick', 5, 'first_card')

    assert game.last_battle_result == {
        'post_battle_pending_choice': {'type': 'winner_pick'}
    }


def test_clear_post_battle_pending_choice_records_truthy_outcome_and_flags_json(
    monkeypatch,
):
    game = SimpleNamespace(
        last_battle_result={
            'winner_id': 3,
            'post_battle_pending_choice': {'type': 'winner_pick'},
        }
    )
    flagged = []
    monkeypatch.setattr(
        games,
        'flag_modified',
        lambda target, attribute: flagged.append((target, attribute)),
    )

    result = games._clear_post_battle_pending_choice(
        game,
        defaulted=True,
        choice='first_card',
    )

    assert result is None
    assert game.last_battle_result == {
        'winner_id': 3,
        'post_battle_choice_defaulted': True,
        'post_battle_choice': 'first_card',
    }
    assert flagged == [(game, 'last_battle_result')]


def test_clear_post_battle_pending_choice_ignores_falsey_markers(monkeypatch):
    game = SimpleNamespace(last_battle_result=None)
    monkeypatch.setattr(games, 'flag_modified', lambda *_args: None)

    games._clear_post_battle_pending_choice(game, defaulted=False, choice='')

    assert game.last_battle_result == {}
