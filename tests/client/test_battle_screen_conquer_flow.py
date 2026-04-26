# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for conquer end-flow handling in BattleScreen."""

from types import SimpleNamespace


def _battle_screen_class():
    from game.screens.battle_screen import BattleScreen

    return BattleScreen


class TestBattleScreenConquerFlow:
    def test_conquer_defeat_ack_queries_finish_battle_and_sets_fallback_game_over(self, monkeypatch):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        updates = []
        conquer_results = []
        resets = []
        finish_calls = []

        game = SimpleNamespace(
            mode='conquer',
            game_id=91,
            player_id=17,
            pending_game_over=None,
            game_over=False,
            update_from_dict=lambda data: updates.append(data),
        )

        screen.game = game
        screen._handle_conquer_end = lambda result: conquer_results.append(result)
        screen._reset_after_battle = lambda: resets.append(True)

        def fake_finish(game_id, player_id, total_diff):
            finish_calls.append({
                'game_id': game_id,
                'player_id': player_id,
                'total_diff': total_diff,
            })
            return {
                'success': True,
                'outcome': 'win',
                'winner_player_id': 99,
                'game': {'id': game_id},
            }

        def fail_pick(*_args, **_kwargs):
            raise AssertionError('loser flow must never call finish_battle_pick_card')

        monkeypatch.setattr('game.screens.battle_screen.game_service.finish_battle', fake_finish)
        monkeypatch.setattr('game.screens.battle_screen.game_service.finish_battle_pick_card', fail_pick)

        BattleScreen._on_defeat_acknowledged(screen, 'ok')

        assert len(finish_calls) == 1
        assert finish_calls[0]['game_id'] == 91
        assert finish_calls[0]['player_id'] == 17
        assert finish_calls[0]['total_diff'] == 0

        assert updates == [{'id': 91}]
        assert conquer_results == []
        assert game.pending_game_over == {'winner_player_id': 99}
        assert game.game_over is True
        assert resets == [True]

    def test_conquer_defeat_ack_routes_directly_when_conquer_result_is_ready(self, monkeypatch):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        conquer_results = []
        resets = []

        game = SimpleNamespace(
            mode='conquer',
            game_id=47,
            player_id=5,
            pending_game_over=None,
            game_over=False,
            update_from_dict=lambda _data: None,
        )

        screen.game = game
        screen._handle_conquer_end = lambda result: conquer_results.append(result)
        screen._reset_after_battle = lambda: resets.append(True)

        def fake_finish(game_id, player_id, total_diff):
            return {
                'success': True,
                'conquer_result': 'defender_won',
                'attacker_won': False,
            }

        monkeypatch.setattr('game.screens.battle_screen.game_service.finish_battle', fake_finish)

        BattleScreen._on_defeat_acknowledged(screen, 'ok')

        assert len(conquer_results) == 1
        assert conquer_results[0]['conquer_result'] == 'defender_won'
        assert resets == []

    def test_conquer_draw_fallback_payload_routes_to_conquer_end(self):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        handled = []
        screen.game = SimpleNamespace(mode='conquer')
        screen._handle_conquer_end = lambda result: handled.append(result)

        BattleScreen._show_draw_result(screen, {'outcome': 'draw'})

        assert len(handled) == 1
        assert handled[0]['conquer_result'] == 'draw'
        assert handled[0]['attacker_won'] is False

    def test_conquer_attacker_loss_dialogue_lists_looted_and_consumed_cards(self, monkeypatch):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        class _DummyCardImg:
            def __init__(self, *_args, **_kwargs):
                self.front_img = None

        monkeypatch.setattr('game.components.cards.card_img.CardImg', _DummyCardImg)

        captured = {}
        screen.window = object()
        screen.game = SimpleNamespace(invader=True, game_over=False, mode='conquer')
        screen.make_dialogue_box = lambda message, **kwargs: captured.update({
            'message': message,
            'kwargs': kwargs,
        })

        BattleScreen._handle_conquer_end(screen, {
            'conquer_result': 'defender_won',
            'attacker_won': False,
            'loot_lost_cards': [
                {'suit': 'Hearts', 'rank': 'K'},
            ],
            'consumed_cards': [
                {'suit': 'Clubs', 'rank': '7'},
                {'suit': 'Spades', 'rank': '10'},
            ],
            'cards_spent': 3,
        })

        msg = captured.get('message', '')
        assert 'Looted by defender:' in msg
        assert 'K of Hearts' in msg
        assert 'Consumed cards:' in msg
        assert '7 of Clubs' in msg
        assert '10 of Spades' in msg

    def test_conquer_defender_loss_dialogue_lists_consumed_defence_cards(self, monkeypatch):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        class _DummyCardImg:
            def __init__(self, *_args, **_kwargs):
                self.front_img = None

        monkeypatch.setattr('game.components.cards.card_img.CardImg', _DummyCardImg)

        captured = {}
        screen.window = object()
        screen.game = SimpleNamespace(invader=False, game_over=False, mode='conquer')
        screen.make_dialogue_box = lambda message, **kwargs: captured.update({
            'message': message,
            'kwargs': kwargs,
        })

        BattleScreen._handle_conquer_end(screen, {
            'conquer_result': 'attacker_won',
            'attacker_won': True,
            'card_lost_suit': 'Hearts',
            'card_lost_rank': 'K',
            'defence_consumed_cards': [
                {'suit': 'Spades', 'rank': '8'},
                {'suit': 'Hearts', 'rank': '3'},
            ],
        })

        msg = captured.get('message', '')
        assert 'Card lost as loot:' in msg
        assert 'Defence cards consumed:' in msg
        assert '8 of Spades' in msg
        assert '3 of Hearts' in msg
