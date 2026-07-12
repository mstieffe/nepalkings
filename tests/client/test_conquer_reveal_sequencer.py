# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the staged conquer round-reveal sequencer."""

from types import SimpleNamespace

import pygame


def _move(move_id, *, family='Dagger', suit='Hearts', rank='9', value=5,
          played_round=None, skipped=False, player_id=1):
    move = {
        'id': move_id,
        'card_id': move_id + 100,
        'card_id_b': None,
        'family_name': 'Skip' if skipped else family,
        'suit': suit,
        'rank': rank,
        'value': 0 if skipped else value,
        'status': 'played',
        'played_round': played_round,
        'player_id': player_id,
    }
    if skipped:
        move['_skipped'] = True
    return move


class _SequencerParent:
    """Minimal ConquerGameScreen stand-in for sequencer unit tests."""

    def __init__(self, game=None):
        self.state = SimpleNamespace(game=game or SimpleNamespace(
            game_id=7, player_id=1, battle_round=0,
            battle_turn_player_id=1, last_battle_result=None,
        ))
        self.player_slots = [None, None, None]
        self.opponent_slots = [None, None, None]
        self.events = []

    def _conquer_lane_played_tactics_raw(self):
        return list(self.player_slots), list(self.opponent_slots)

    def _on_conquer_round_reveal_event(self, round_idx, event, payload):
        self.events.append((round_idx, event))


def _sequencer(parent=None):
    from game.components.conquer_reveal_sequencer import ConquerRevealSequencer

    parent = parent or _SequencerParent()
    return ConquerRevealSequencer(parent), parent


def test_seed_marks_existing_complete_rounds_revealed_without_animation(monkeypatch):
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)
    seq, parent = _sequencer()
    parent.player_slots = [_move(1, played_round=0), None, None]
    parent.opponent_slots = [_move(11, played_round=0, player_id=2), None, None]

    seq.pump()

    assert seq.is_round_revealed(0)
    assert not seq.is_active()
    assert parent.events == []


def test_new_round_completion_animates_and_gates_opponent_slot(monkeypatch):
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer()
    # Seed with an empty battle, then the player commits.
    seq.pump()
    parent.player_slots[0] = _move(1, played_round=0)
    seq.pump()
    # Opponent completes the round on a later poll.
    parent.opponent_slots[0] = _move(11, played_round=0, player_id=2)
    now['ms'] += 16
    seq.pump()

    assert seq.is_active()
    assert not seq.is_round_revealed(0)
    _, gated_opp = seq.gate_slots(parent.player_slots, parent.opponent_slots)
    assert gated_opp[0] is None  # withheld before the flip

    stage = seq.stage_for_round(0)
    assert stage is not None
    assert stage['stage'] == 'hold'

    # Run the clock past HOLD and half of FLIP → identity becomes visible.
    from game.components import conquer_reveal_sequencer as mod
    now['ms'] += mod.STAGE_DURATIONS_MS['hold'] + mod.STAGE_DURATIONS_MS['flip'] * 3 // 4
    seq.pump()
    stage = seq.stage_for_round(0)
    assert stage is not None and stage['opp_visible']
    _, gated_opp = seq.gate_slots(parent.player_slots, parent.opponent_slots)
    assert gated_opp[0] is not None
    assert (0, 'flip') in parent.events

    # Run past the whole sequence → revealed, done event fired.
    now['ms'] += sum(mod.STAGE_DURATIONS_MS.values())
    seq.pump()
    seq.pump()
    assert seq.is_round_revealed(0)
    assert not seq.is_active()
    assert (0, 'impact') in parent.events
    assert (0, 'done') in parent.events


def test_fast_forward_reveals_instantly(monkeypatch):
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer()
    seq.pump()
    parent.player_slots[0] = _move(1, played_round=0)
    seq.pump()
    parent.opponent_slots[0] = _move(11, played_round=0, player_id=2)
    now['ms'] += 16
    seq.pump()
    assert seq.is_active()

    assert seq.fast_forward() is True

    assert not seq.is_active()
    assert seq.is_round_revealed(0)
    assert (0, 'done') in parent.events
    _, gated_opp = seq.gate_slots(parent.player_slots, parent.opponent_slots)
    assert gated_opp[0] is not None


def test_round_completing_without_prior_observation_reveals_instantly(monkeypatch):
    """History arriving complete after seeding (first battle-state poll on a
    reloaded client) must never replay reveal choreography."""
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)
    seq, parent = _sequencer()
    seq.pump()  # seeds on an empty battle (caches not yet primed)

    parent.player_slots = [_move(1, played_round=0),
                           _move(2, played_round=1), None]
    parent.opponent_slots = [_move(11, played_round=0, player_id=2),
                             _move(12, played_round=1, player_id=2), None]
    # Round 1 was never observed incomplete → both reveal instantly.
    # (battle_round=0 means only round 0 could have been eligible, and it
    # arrived complete in the same poll.)
    seq.pump()

    assert seq.is_round_revealed(0)
    assert seq.is_round_revealed(1)
    assert not seq.is_active()
    assert all(event != 'flip' for _, event in parent.events)


def test_opponent_first_round_never_ungates_visible_identity(monkeypatch):
    """Invader Swap: the opponent commits first; their revealed tactic must
    stay visible while the round is open and must not blink out when the
    player completes the round."""
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer()
    seq.pump()
    parent.opponent_slots[0] = _move(11, played_round=0, player_id=2)
    seq.pump()

    _, gated_opp = seq.gate_slots(parent.player_slots, parent.opponent_slots)
    assert gated_opp[0] is not None  # incomplete round is never gated

    parent.player_slots[0] = _move(1, played_round=0)
    now['ms'] += 16
    seq.pump()
    _, gated_opp = seq.gate_slots(parent.player_slots, parent.opponent_slots)
    assert gated_opp[0] is not None  # opp_seen sequences skip the flip


def test_skipped_round_uses_short_beat(monkeypatch):
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer()
    seq.pump()
    parent.player_slots[0] = _move(1, played_round=0)
    seq.pump()
    parent.opponent_slots[0] = _move(11, played_round=0, player_id=2,
                                     skipped=True)
    now['ms'] += 16
    seq.pump()
    assert seq.is_active()

    from game.components import conquer_reveal_sequencer as mod
    now['ms'] += sum(mod.SKIP_STAGE_DURATIONS_MS.values()) + 32
    seq.pump()
    seq.pump()
    assert seq.is_round_revealed(0)


def test_finished_battle_drains_pending_reveals(monkeypatch):
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer()
    seq.pump()
    parent.player_slots[0] = _move(1, played_round=0)
    seq.pump()
    parent.opponent_slots[0] = _move(11, played_round=0, player_id=2)
    now['ms'] += 16
    seq.pump()
    assert seq.is_active()

    parent.state.game.last_battle_result = {'outcome': 'win'}
    now['ms'] += 16
    seq.pump()

    assert not seq.is_active()
    assert seq.is_round_revealed(0)


def test_display_version_bumps_on_gate_changes(monkeypatch):
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer()
    seq.pump()
    v0 = seq.display_version()
    parent.player_slots[0] = _move(1, played_round=0)
    seq.pump()  # round observed incomplete → eligible
    parent.opponent_slots[0] = _move(11, played_round=0, player_id=2)
    now['ms'] += 16
    seq.pump()
    v1 = seq.display_version()
    assert v1 > v0
    assert seq.is_active()
    seq.fast_forward()
    assert seq.display_version() > v1


def test_game_key_change_resets_state(monkeypatch):
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)
    seq, parent = _sequencer()
    parent.player_slots[0] = _move(1, played_round=0)
    parent.opponent_slots[0] = _move(11, played_round=0, player_id=2)
    seq.pump()
    assert seq.is_round_revealed(0)

    parent.state.game = SimpleNamespace(
        game_id=8, player_id=1, battle_round=0,
        battle_turn_player_id=1, last_battle_result=None,
    )
    parent.player_slots = [None, None, None]
    parent.opponent_slots = [None, None, None]
    seq.pump()
    assert not seq.is_round_revealed(0)


# ---------------------------------------------------------------------------
# Reveal pacing: start payload, final-round beat, fast-forward flag
# ---------------------------------------------------------------------------

class _PayloadParent(_SequencerParent):
    """Sequencer parent that also records full event payloads."""

    def __init__(self, game=None):
        super().__init__(game)
        self.payloads = []

    def _on_conquer_round_reveal_event(self, round_idx, event, payload):
        super()._on_conquer_round_reveal_event(round_idx, event, payload)
        self.payloads.append((round_idx, event, dict(payload)))


def _complete_round(seq, parent, now, idx, *, skipped=False):
    parent.player_slots[idx] = _move(idx * 2 + 1, played_round=idx)
    seq.pump()
    parent.opponent_slots[idx] = _move(idx * 2 + 11, played_round=idx,
                                       player_id=2, skipped=skipped)
    now['ms'] += 16
    seq.pump()


def test_start_event_carries_hold_ms(monkeypatch):
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer(_PayloadParent())
    seq.pump()
    _complete_round(seq, parent, now, 0)

    from game.components import conquer_reveal_sequencer as mod
    starts = [(idx, p) for idx, event, p in parent.payloads if event == 'start']
    assert starts == [(0, {'hold_ms': mod.STAGE_DURATIONS_MS['hold']})]


def test_final_round_uses_long_beat(monkeypatch):
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer(_PayloadParent())
    seq.pump()
    _complete_round(seq, parent, now, 2)
    assert seq.is_active()

    from game.components import conquer_reveal_sequencer as mod
    starts = [p for _, event, p in parent.payloads if event == 'start']
    assert starts == [{'hold_ms': mod.FINAL_STAGE_DURATIONS_MS['hold']}]

    # Still animating after the default-beat length has elapsed…
    now['ms'] += sum(mod.STAGE_DURATIONS_MS.values()) + 32
    seq.pump()
    assert seq.is_active()
    # …and revealed once the longer final-round beat fully lapses.
    now['ms'] += (sum(mod.FINAL_STAGE_DURATIONS_MS.values())
                  - sum(mod.STAGE_DURATIONS_MS.values()))
    seq.pump()
    seq.pump()
    assert seq.is_round_revealed(2)


def test_final_round_skip_still_uses_short_beat(monkeypatch):
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer(_PayloadParent())
    seq.pump()
    _complete_round(seq, parent, now, 2, skipped=True)

    from game.components import conquer_reveal_sequencer as mod
    starts = [p for _, event, p in parent.payloads if event == 'start']
    assert starts == [{'hold_ms': mod.SKIP_STAGE_DURATIONS_MS['hold']}]


def test_fast_forward_impact_payload_flags_fast_forwarded(monkeypatch):
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer(_PayloadParent())
    seq.pump()
    _complete_round(seq, parent, now, 0)
    assert seq.is_active()

    seq.fast_forward()

    impacts = [p for _, event, p in parent.payloads if event == 'impact']
    assert impacts == [{'fast_forwarded': True}]


def test_natural_impact_payload_not_flagged(monkeypatch):
    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    seq, parent = _sequencer(_PayloadParent())
    seq.pump()
    _complete_round(seq, parent, now, 0)

    from game.components import conquer_reveal_sequencer as mod
    d = mod.STAGE_DURATIONS_MS
    now['ms'] += d['hold'] + d['flip'] + d['tally'] + d['impact'] // 2
    seq.pump()

    impacts = [p for _, event, p in parent.payloads if event == 'impact']
    assert impacts == [{}]


# ---------------------------------------------------------------------------
# Ledger integration: staged reveal drawing
# ---------------------------------------------------------------------------

def _rect_has_non_background_pixel(surface, rect, background=(0, 0, 0)):
    bounds = pygame.Rect(rect).clip(surface.get_rect())
    step_x = max(1, bounds.width // 12)
    step_y = max(1, bounds.height // 12)
    for x in range(bounds.left, bounds.right, step_x):
        for y in range(bounds.top, bounds.bottom, step_y):
            if surface.get_at((x, y))[:3] != background:
                return True
    return False


class _LedgerParent:
    """Ledger parent exposing the gated lane helper + reveal stage."""

    def __init__(self, window, game, you_per, opp_per, stage_by_round=None):
        self.window = window
        self.state = SimpleNamespace(game=game)
        self.subscreens = {'battle': SimpleNamespace(opp_played=[])}
        self._you = you_per
        self._opp = opp_per
        self._stages = stage_by_round or {}

    def _conquer_lane_played_tactics(self):
        return list(self._you), list(self._opp)

    def conquer_round_reveal_stage(self, idx):
        return self._stages.get(idx)

    def _conquer_battle_move_icon_assets(self, icon_size):
        from config import settings

        return ({}, {}, {}, {}, settings.get_font(max(8, icon_size // 3), bold=True))


def test_ledger_draws_face_down_chip_and_vs_during_hold(monkeypatch):
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 5000)
    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(mode='conquer', player_id=1, battle_round=0,
                           battle_turn_player_id=2, last_battle_result=None)
    you = [_move(1, played_round=0), None, None]
    # The gated helper hides the opponent identity pre-flip.
    opp = [None, None, None]
    stage = {0: {'stage': 'hold', 'progress': 0.4,
                 'opp_visible': False, 'diff_factor': 0.0}}
    parent = _LedgerParent(window, game, you, opp, stage_by_round=stage)
    ledger = ConquerRoundLedger(parent)

    ledger.draw()

    layout = ledger._ensure_layout().round_ledger
    card = pygame.Rect(*layout.round_card_rects[0])
    assert _rect_has_non_background_pixel(window, card)
    # The gold sweep must not start while the staged reveal is active.
    assert 0 not in ledger._round_reveal_animations


def test_ledger_tally_stage_counts_diff_up(monkeypatch):
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 5000)
    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(mode='conquer', player_id=1, battle_round=0,
                           battle_turn_player_id=None, last_battle_result=None)
    you = [_move(1, played_round=0, value=9), None, None]
    opp = [_move(11, played_round=0, value=3, player_id=2), None, None]
    stage = {0: {'stage': 'tally', 'progress': 0.5,
                 'opp_visible': True, 'diff_factor': 0.5}}
    parent = _LedgerParent(window, game, you, opp, stage_by_round=stage)
    ledger = ConquerRoundLedger(parent)

    ledger.draw()

    layout = ledger._ensure_layout().round_ledger
    card = pygame.Rect(*layout.round_card_rects[0])
    assert _rect_has_non_background_pixel(window, card)


def test_ledger_prefers_parent_gated_slots():
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(mode='conquer', player_id=1, battle_round=1,
                           battle_turn_player_id=1, last_battle_result=None)
    you = [_move(1, played_round=0), None, None]
    opp = [None, None, None]  # gated by the sequencer
    parent = _LedgerParent(window, game, you, opp)
    ledger = ConquerRoundLedger(parent)

    you_per, opp_per = ledger._played_per_round_pair()

    assert you_per[0] is not None
    assert opp_per == [None, None, None]


# ---------------------------------------------------------------------------
# Round banner label + gamble UX
# ---------------------------------------------------------------------------

def test_round_banner_label_is_one_based_with_final_round_callout():
    from game.screens.conquer_game_screen import ConquerGameScreen

    # battle_round is zero-indexed on the server (0..2).
    assert ConquerGameScreen._conquer_round_banner_label(0) == 'Round 1'
    assert ConquerGameScreen._conquer_round_banner_label(1) == 'Round 2'
    assert ConquerGameScreen._conquer_round_banner_label(2) == 'Final Round'
    assert ConquerGameScreen._conquer_round_banner_label(3) == 'Final Round'


def _rail_parent(game, moves):
    from config import settings

    return SimpleNamespace(
        window=pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)),
        state=SimpleNamespace(game=game),
        _current_conquer_tactics=lambda: list(moves),
        _conquer_battle_move_icon_assets=lambda size: (
            {}, {}, {}, {}, settings.get_font(max(8, size // 3), bold=True)),
    )


def test_gamble_strip_reports_last_gamble_state():
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    game = SimpleNamespace(
        player_id=1, battle_round=1, battle_turn_player_id=1,
        battle_confirmed=True, last_battle_result=None,
        battle_gamble_counts={'1': {'count': 2, 'rounds': [0]}},
    )
    rail = ConquerTacticsRail(_rail_parent(game, []))

    text, state = rail._gamble_status_for_strip(game)

    assert state == 'last'
    assert 'ast gamble' in text  # 'Last gamble…' in either display mode


def test_gamble_pips_reflect_used_count(monkeypatch):
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 4000)
    game = SimpleNamespace(
        player_id=1, battle_round=1, battle_turn_player_id=1,
        battle_confirmed=True, last_battle_result=None,
        battle_gamble_counts={'1': {'count': 1, 'rounds': [0]}},
    )
    parent = _rail_parent(game, [])
    rail = ConquerTacticsRail(parent)
    strip = pygame.Rect(10, 10, 220, 64)
    parent.window.fill((0, 0, 0))

    rail._draw_gamble_pips(strip, game)

    assert _rect_has_non_background_pixel(parent.window, strip)
    assert rail._gamble_counts_state(game) == (1, [0])


def test_gamble_two_step_confirm_expires(monkeypatch):
    from game.components.conquer_tactics_rail import (
        ACTION_GAMBLE,
        ConquerTacticsRail,
    )

    now = {'ms': 1000}
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: now['ms'])
    move = _move(1, played_round=None)
    move['status'] = 'available'
    game = SimpleNamespace(
        player_id=1, battle_round=0, battle_turn_player_id=1,
        battle_confirmed=True, last_battle_result=None,
        battle_gamble_counts={},
    )
    rail = ConquerTacticsRail(_rail_parent(game, [move]))
    rail._selected_id = move['id']

    rail._trigger_action(ACTION_GAMBLE)
    assert rail.consume_pending_action() is None
    assert rail._gamble_armed_for(move['id'])

    # The confirm window lapses → the next click re-arms instead of firing.
    now['ms'] += ConquerTacticsRail.GAMBLE_CONFIRM_MS + 50
    assert not rail._gamble_armed_for(move['id'])
    rail._trigger_action(ACTION_GAMBLE)
    assert rail.consume_pending_action() is None
    rail._trigger_action(ACTION_GAMBLE)
    pending = rail.consume_pending_action()
    assert pending and pending['action'] == ACTION_GAMBLE
