# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""DuelSlotAnimator contract tests + BattleScreen reveal wiring.

Test oracle (desired outcomes):
- First note_slots call seeds silently (no replay on reconnect), including
  marking already-complete rounds as beaten.
- Newly-filled slots emit ('slot', side, r); a round's second arrival emits
  ('round_complete', r) exactly once, including skipped-round entries.
- slot_anim reports 0..1 progress during POP_MS, then None.
- is_active() self-expires by time; fast_forward() ends it immediately.
- BattleScreen._handle_battle_action refuses user actions while the reveal
  is active and never calls the server.
"""

from types import SimpleNamespace

import pygame


def _animator():
    from game.components.duel_battle_animator import DuelSlotAnimator

    return DuelSlotAnimator()


def _move(mid, family='Dagger'):
    return {'id': mid, 'family_name': family, 'value': 3}


SKIP = {'family_name': 'Skip', 'value': 0, 'suit': '', '_skipped': True}


class TestDuelSlotAnimator:
    def test_first_sight_seeds_silently(self):
        anim = _animator()
        events = anim.note_slots([_move(1), None, None], [_move(2), None, None], now=100)
        assert events == []
        # The same board again → still nothing.
        assert anim.note_slots([_move(1), None, None], [_move(2), None, None], now=200) == []

    def test_seeded_complete_round_never_beats(self):
        anim = _animator()
        anim.note_slots([_move(1), None, None], [_move(2), None, None], now=100)
        # Round 0 was complete at seed time — later diffs must not re-beat it.
        events = anim.note_slots([_move(1), _move(3), None], [_move(2), None, None], now=200)
        assert events == [('slot', 'player', 1)]

    def test_slot_and_round_complete_events(self):
        anim = _animator()
        anim.note_slots([None] * 3, [None] * 3, now=0)

        events = anim.note_slots([_move(1), None, None], [None] * 3, now=100)
        assert events == [('slot', 'player', 0)]

        events = anim.note_slots([_move(1), None, None], [_move(2), None, None], now=200)
        assert events == [('slot', 'opponent', 0), ('round_complete', 0)]

    def test_skipped_round_counts_for_completion(self):
        anim = _animator()
        anim.note_slots([None] * 3, [None] * 3, now=0)
        events = anim.note_slots([SKIP, None, None], [_move(9), None, None], now=50)
        assert ('round_complete', 0) in events
        assert ('slot', 'player', 0) in events
        assert ('slot', 'opponent', 0) in events

    def test_slot_anim_progress_then_none(self):
        anim = _animator()
        anim.note_slots([None] * 3, [None] * 3, now=0)
        anim.note_slots([_move(1), None, None], [None] * 3, now=1000)

        t_mid = anim.slot_anim('player', 0, now=1000 + anim.POP_MS // 2)
        assert t_mid is not None and 0.0 < t_mid < 1.0
        assert anim.slot_anim('player', 0, now=1000 + anim.POP_MS + 1) is None
        assert anim.slot_anim('opponent', 0, now=1000) is None

    def test_is_active_expires_by_time(self):
        anim = _animator()
        anim.note_slots([None] * 3, [None] * 3, now=0)
        anim.note_slots([_move(1), None, None], [_move(2), None, None], now=1000)

        assert anim.is_active(now=1000 + 50) is True
        # Longest record is the round beat (BEAT_MS).
        assert anim.is_active(now=1000 + max(anim.POP_MS, anim.BEAT_MS) + 1) is False

    def test_fast_forward_ends_animations_immediately(self):
        anim = _animator()
        anim.note_slots([None] * 3, [None] * 3, now=0)
        anim.note_slots([_move(1), None, None], [_move(2), None, None], now=1000)
        assert anim.is_active(now=1010) is True

        anim.fast_forward()

        assert anim.is_active(now=1010) is False
        assert anim.slot_anim('player', 0, now=1010) is None
        # Seen state survives — no replay on the next diff.
        assert anim.note_slots([_move(1), None, None], [_move(2), None, None], now=1100) == []

    def test_reset_forgets_everything(self):
        anim = _animator()
        anim.note_slots([_move(1), None, None], [_move(2), None, None], now=0)
        anim.reset()
        # Post-reset first call seeds silently again.
        assert anim.note_slots([_move(3), None, None], [None] * 3, now=100) == []


class TestBattleScreenRevealWiring:
    def _bare_battle_screen(self):
        from game.screens.battle_screen import BattleScreen
        from game.components.duel_battle_animator import DuelSlotAnimator
        from game.components.conquer_effects import EffectsLayer

        screen = BattleScreen.__new__(BattleScreen)
        screen.game = SimpleNamespace(mode='duel', game_over=False)
        fx = EffectsLayer(pygame.Surface((320, 200)), lambda _id: None)
        screen.state = SimpleNamespace(parent_screen=SimpleNamespace(_fx=fx))
        screen._slot_animator = DuelSlotAnimator()
        screen.player_played = [None, None, None]
        screen.opponent_played = [None, None, None]
        return screen, fx

    def test_pump_emits_round_pulse_effects(self, monkeypatch):
        from game.screens.battle_screen import BattleScreen
        from utils import sound

        screen, fx = self._bare_battle_screen()
        slot_rect = pygame.Rect(10, 10, 40, 40)
        screen._round_slot_rect = lambda side, r: pygame.Rect(slot_rect)
        screen._get_round_diff = lambda r: 4
        played = []
        monkeypatch.setattr(
            sound, 'play', lambda name, **kwargs: played.append(name))

        # Seed empty board, then fill round 0 on both sides.
        BattleScreen._pump_slot_reveal_events(screen)
        screen.player_played[0] = _move(1)
        screen.opponent_played[0] = _move(2)
        BattleScreen._pump_slot_reveal_events(screen)

        assert len(fx._impacts) == 2       # one pulse per slot
        assert len(fx._floats) == 1        # the +4 diff floater
        assert fx._floats[0]['text'] == '+4'
        assert played == ['card_place', 'card_place', 'round_win']

    def test_pump_uses_loss_and_tie_cues(self, monkeypatch):
        from game.screens.battle_screen import BattleScreen
        from utils import sound

        played = []
        monkeypatch.setattr(
            sound, 'play', lambda name, **kwargs: played.append(name))
        for diff, expected in ((-3, 'round_loss'), (0, 'tally_tick')):
            screen, _fx = self._bare_battle_screen()
            screen.state.parent_screen._fx = None
            screen._slot_animator = SimpleNamespace(
                note_slots=lambda *_args: [('round_complete', 0)])
            screen._get_round_diff = lambda _r, value=diff: value

            BattleScreen._pump_slot_reveal_events(screen)

            assert played[-1] == expected

    def test_handle_battle_action_blocked_during_reveal(self, monkeypatch):
        from game.screens.battle_screen import BattleScreen

        screen, _fx = self._bare_battle_screen()
        screen._rounds_panel_rect = lambda: pygame.Rect(0, 0, 100, 100)
        started = []
        screen._start_use = lambda *a, **k: started.append('use')

        # Activate the reveal (slot arrival just now).
        screen._slot_animator.note_slots([None] * 3, [None] * 3)
        screen.player_played[0] = _move(1)
        screen._slot_animator.note_slots(screen.player_played, screen.opponent_played)
        assert screen._slot_animator.is_active() is True

        BattleScreen._handle_battle_action(
            screen, {'action': 'use', 'move_index': 0})

        assert started == []  # blocked — the starter was never reached

    def test_handle_battle_action_passes_when_idle(self):
        from game.screens.battle_screen import BattleScreen

        screen, _fx = self._bare_battle_screen()
        started = []
        screen._start_use = lambda *a, **k: started.append('use')

        BattleScreen._handle_battle_action(
            screen, {'action': 'use', 'move_index': 0})

        assert started == ['use']

    def test_block_reason_empty_in_conquer(self):
        screen, _fx = self._bare_battle_screen()
        screen.game.mode = 'conquer'
        screen.player_played[0] = _move(1)
        screen._slot_animator.note_slots([None] * 3, [None] * 3)
        screen._slot_animator.note_slots(screen.player_played, screen.opponent_played)

        from game.screens.battle_screen import BattleScreen
        assert BattleScreen.duel_action_block_reason(screen) == ''
