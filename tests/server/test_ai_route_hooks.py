# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Route-hook tests for AI trigger behavior and recursion guard header."""

import pytest


@pytest.fixture
def enable_ai_hooks(monkeypatch):
    import routes.games as games_routes
    import routes.battle_shop as battle_shop_routes
    import routes.spells as spells_routes
    import routes.figures as figures_routes

    monkeypatch.setattr(games_routes.settings, 'AI_ENABLED', True)
    monkeypatch.setattr(battle_shop_routes.settings, 'AI_ENABLED', True)
    monkeypatch.setattr(spells_routes.settings, 'AI_ENABLED', True)
    monkeypatch.setattr(figures_routes.settings, 'AI_ENABLED', True)


@pytest.fixture
def trigger_calls(monkeypatch):
    import ai.ai_worker as ai_worker

    calls = []

    def fake_trigger(game_id, app=None):
        calls.append(game_id)

    monkeypatch.setattr(ai_worker, 'trigger_ai_if_needed', fake_trigger)
    return calls


def test_games_hook_triggers_ai_when_post_has_game_id(client, enable_ai_hooks, trigger_calls):
    resp = client.post('/games/start_turn', json={'game_id': 101, 'player_id': 1})

    assert resp.status_code in {200, 400, 401, 404}
    assert trigger_calls == [101]


def test_games_hook_skips_trigger_for_internal_ai_header(client, enable_ai_hooks, trigger_calls):
    resp = client.post(
        '/games/start_turn',
        json={'game_id': 102, 'player_id': 1},
        headers={'X-NepalKings-AI-Internal': '1'},
    )

    assert resp.status_code in {200, 400, 401, 404}
    assert trigger_calls == []


def test_battle_shop_hook_triggers_ai_when_post_has_game_id(client, enable_ai_hooks, trigger_calls):
    resp = client.post('/battle_shop/buy_battle_move', json={'game_id': 201, 'player_id': 1})

    assert resp.status_code in {200, 400, 401, 404}
    assert trigger_calls == [201]


def test_battle_shop_hook_skips_trigger_for_internal_ai_header(client, enable_ai_hooks, trigger_calls):
    resp = client.post(
        '/battle_shop/buy_battle_move',
        json={'game_id': 202, 'player_id': 1},
        headers={'X-NepalKings-AI-Internal': '1'},
    )

    assert resp.status_code in {200, 400, 401, 404}
    assert trigger_calls == []


def test_spells_hook_triggers_ai_when_post_has_game_id(client, enable_ai_hooks, trigger_calls):
    resp = client.post('/spells/cast_spell', json={'game_id': 301, 'player_id': 1})

    assert resp.status_code in {200, 400, 401, 404}
    assert trigger_calls == [301]


def test_spells_hook_skips_trigger_for_internal_ai_header(client, enable_ai_hooks, trigger_calls):
    resp = client.post(
        '/spells/cast_spell',
        json={'game_id': 302, 'player_id': 1},
        headers={'X-NepalKings-AI-Internal': '1'},
    )

    assert resp.status_code in {200, 400, 401, 404}
    assert trigger_calls == []


def test_figures_hook_triggers_ai_when_post_has_game_id(client, enable_ai_hooks, trigger_calls):
    resp = client.post('/figures/create_figure', json={'game_id': 401, 'player_id': 1})

    assert resp.status_code in {200, 400, 401, 404}
    assert trigger_calls == [401]


def test_figures_hook_skips_trigger_for_internal_ai_header(client, enable_ai_hooks, trigger_calls):
    resp = client.post(
        '/figures/create_figure',
        json={'game_id': 402, 'player_id': 1},
        headers={'X-NepalKings-AI-Internal': '1'},
    )

    assert resp.status_code in {200, 400, 401, 404}
    assert trigger_calls == []