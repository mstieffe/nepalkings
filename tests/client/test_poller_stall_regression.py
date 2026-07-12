# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for the conquer pre-battle stall (production game 140).

The stall chain was:

1. On entering a conquer game the 850ms battle-state poller's first result
   bumped ``_game_data_version`` while the first full game poll was in
   flight, so ``update_game`` discarded that poll as "stale".
2. The async poller had already stored the poll's response signature, and
   the server state never changed while the player was idle — so every
   subsequent poll short-circuited to ``None`` and the discarded state was
   never re-delivered.
3. ``game.turn`` therefore stayed at its constructor seed ``False`` and the
   invader was never prompted to advance ("Waiting for opponent" forever),
   until an unrelated action response (combining two Daggers) ran
   ``update_from_dict`` and healed ``turn``.

These tests pin the three fixes: signature invalidation on discard, no
signature poisoning from undelivered results, and the conquer ``turn`` seed.
"""
from types import SimpleNamespace

import pygame

pygame.display.set_mode((1, 1))


def _resp(body_text, game=None, status=200):
    return SimpleNamespace(
        status_code=status,
        text=body_text,
        json=lambda: {'game': game, 'log_entries': [], 'chat_messages': [],
                      'active_spells': []},
    )


def _responses(game_dict, marker='a'):
    return {
        'game': _resp(f'game-{marker}', game=game_dict),
        'logs': _resp(f'logs-{marker}'),
        'chats': _resp(f'chats-{marker}'),
        'spells': _resp(f'spells-{marker}'),
    }


def _mk_game_dict(**overrides):
    data = {
        'id': 140,
        'state': 'open',
        'mode': 'conquer',
        'conquer_move_model': 'tactics_hand',
        'date': '2026-07-11T09:59:00',
        'players': [
            {'id': 279, 'user_id': 1, 'username': 'KingMerk',
             'turns_left': 1, 'points': 0, 'is_online': True},
            {'id': 280, 'user_id': 2, 'username': '[AI] Strategos',
             'turns_left': 1, 'points': 0, 'is_online': True},
        ],
        'main_cards': [],
        'side_cards': [],
        'current_round': 1,
        'invader_player_id': 279,
        'turn_player_id': 279,
        'ceasefire_active': False,
        'ceasefire_start_turn': None,
        'pending_spell_id': None,
        'battle_modifier': [{'type': 'Royal Decree', 'caster_id': 279}],
        'waiting_for_counter_player_id': None,
        'advancing_figure_id': None,
        'advancing_figure_id_2': None,
        'advancing_player_id': None,
        'defending_figure_id': None,
        'defending_figure_id_2': None,
        'battle_decisions': None,
        'battle_confirmed': False,
        'battle_moves_confirmed': None,
        'fold_outcome': None,
        'fold_winner_id': None,
        'battle_round': 0,
        'battle_turn_player_id': None,
        'battle_skipped_rounds': {},
        'post_battle_drawn_cards': None,
        'last_battle_result': None,
        'winner_player_id': None,
        'finished_at': None,
        'resting_figure_ids': [],
    }
    data.update(overrides)
    return data


class TestPollerSignatureInvalidation:
    def _make_poller(self):
        from utils.background_poller import BackgroundPoller
        return BackgroundPoller(lambda: None)

    def test_identical_bodies_short_circuit_after_delivery(self):
        poller = self._make_poller()
        poller._async_responses = _responses(_mk_game_dict())
        assert poller._assemble_server_data() is not None

        poller._async_responses = _responses(_mk_game_dict())
        assert poller._assemble_server_data() is None

    def test_invalidate_cache_forces_redelivery(self):
        """A discarded delivery must be recoverable while the server is idle."""
        poller = self._make_poller()
        poller._async_responses = _responses(_mk_game_dict())
        assert poller._assemble_server_data() is not None
        # The screen discarded that result (version race) and invalidated.
        poller.invalidate_cache()

        poller._async_responses = _responses(_mk_game_dict())
        result = poller._assemble_server_data()
        assert result is not None
        assert result['game']['turn_player_id'] == 279

    def test_invalidate_cache_clears_simple_text_cache(self):
        poller = self._make_poller()
        poller._prev_simple_text = '{"cached": true}'
        poller.invalidate_cache()
        assert poller._prev_simple_text is None

    def test_malformed_game_payload_does_not_poison_signature(self):
        """An undelivered (game-less) response must not suppress the next one."""
        poller = self._make_poller()
        responses = _responses(_mk_game_dict())
        responses['game'] = _resp('game-a', game=None)
        poller._async_responses = responses
        assert poller._assemble_server_data() is None
        assert getattr(poller, '_prev_response_sig', None) is None

        # Same body text, now with a usable game payload — must deliver.
        poller._async_responses = _responses(_mk_game_dict())
        assert poller._assemble_server_data() is not None


class TestConquerTurnSeed:
    def _user(self):
        return {'id': 1, 'username': 'KingMerk'}

    def test_conquer_invader_turn_seeded_from_snapshot(self):
        from game.core.game import Game
        game = Game(_mk_game_dict(), self._user(), lightweight=True)
        assert game.turn is True
        assert game.invader is True

    def test_conquer_defender_turn_stays_false(self):
        from game.core.game import Game
        game = Game(_mk_game_dict(turn_player_id=280), self._user(),
                    lightweight=True)
        assert game.turn is False

    def test_duel_turn_seed_unchanged(self):
        """Duel keeps the False seed so first-poll turn detection fires."""
        from game.core.game import Game
        game = Game(_mk_game_dict(mode='duel'), self._user(), lightweight=True)
        assert game.turn is False


class TestGameScreenDiscardInvalidatesPoller:
    def _screen_with_poller(self, poller_version, game_version):
        from game.screens.game_screen import GameScreen

        calls = []

        class _FakePoller:
            def has_result(self):
                return True

            @property
            def result(self):
                return {'game': {}}

            def invalidate_cache(self):
                calls.append('invalidated')

        screen = GameScreen.__new__(GameScreen)
        screen._game_poller = _FakePoller()
        screen._poller_data_version = poller_version
        game = SimpleNamespace(
            _game_data_version=game_version,
            apply_server_data=lambda *_a: calls.append('applied'),
        )
        screen.state = SimpleNamespace(game=game)
        return screen, calls

    def test_discarded_poll_invalidates_poller_signature(self):
        """The stale-version discard must invalidate the poller's signature."""
        screen, calls = self._screen_with_poller(poller_version=1,
                                                 game_version=2)
        screen._consume_game_poll_result()
        assert calls == ['invalidated']

    def test_matching_versions_apply_without_invalidation(self):
        screen, calls = self._screen_with_poller(poller_version=3,
                                                 game_version=3)
        screen._consume_game_poll_result()
        assert calls == ['applied']

    def test_intentional_discard_invalidates_poller_signature(self):
        """Spell/action handlers must not strand an already-delivered body."""
        screen, calls = self._screen_with_poller(poller_version=1,
                                                 game_version=1)
        assert screen._discard_game_poll_result() is True
        assert calls == ['invalidated']
