# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Render-smoke tests for the duel polish draw paths.

Test oracle: the new draw-only helpers never raise on a headless surface
and spawn the expected effect primitives.
"""

from types import SimpleNamespace

import pygame


def _fx_layer(surface):
    from game.components.conquer_effects import EffectsLayer

    return EffectsLayer(surface, lambda _id: None)


class TestDuelShellDrawHelpers:
    def _bare_game_screen(self):
        from game.screens.game_screen import GameScreen

        screen = GameScreen.__new__(GameScreen)
        screen.window = pygame.Surface((640, 400))
        screen.state = SimpleNamespace(subscreen='field')
        return screen

    def test_subscreen_switch_veil_draws_and_expires(self, monkeypatch):
        screen = self._bare_game_screen()
        monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)
        screen._subscreen_switched_at = 1000

        screen._draw_subscreen_switch_veil()   # mid-fade: must not raise
        assert screen._subscreen_veil_surface is not None

        monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000 + 200)
        screen._draw_subscreen_switch_veil()   # past 160ms: early return

        screen._subscreen_switched_at = 0
        screen._draw_subscreen_switch_veil()   # unset: no-op

    def test_battle_unlock_pulse_fires_once_on_edge(self):
        screen = self._bare_game_screen()
        screen._fx = _fx_layer(screen.window)
        screen.battle_button = SimpleNamespace(
            locked=False, rect_hit=pygame.Rect(10, 10, 40, 40))
        screen._battle_unlock_prev_locked = True

        screen._pump_battle_unlock_pulse()
        assert len(screen._fx._impacts) == 1   # unlock edge → one pulse

        screen._pump_battle_unlock_pulse()
        assert len(screen._fx._impacts) == 1   # still unlocked → no repeat

        # Re-lock, then unlock again → a second pulse.
        screen.battle_button.locked = True
        screen._pump_battle_unlock_pulse()
        screen.battle_button.locked = False
        screen._pump_battle_unlock_pulse()
        assert len(screen._fx._impacts) == 2

    def test_effects_layer_full_draw_cycle_headless(self):
        surface = pygame.Surface((640, 400))
        fx = _fx_layer(surface)
        rect = pygame.Rect(100, 100, 48, 48)
        fx.spawn_banner('YOUR TURN', (238, 206, 130))
        fx.spawn_burst(rect, (238, 206, 130), secondary=(255, 245, 200))
        fx.spawn_confetti(pygame.Rect(0, 0, 640, 400), [(238, 206, 130)])
        fx.spawn_rect_pulse(rect, (150, 230, 170))
        fx.spawn_floating_text_at_rect(rect, '+4', (150, 230, 170))
        fx.spawn_copy_ghost(rect, pygame.Rect(300, 300, 48, 48))
        fx.spawn_spell_to_rect('Poison', rect, pygame.Rect(200, 60, 48, 48))
        fx.spawn_shake(amplitude=4, duration_ms=200)

        fx.draw()  # must not raise on a headless surface

        from game.components.conquer_effects import apply_screen_shake
        apply_screen_shake(surface, fx.screen_shake_offset())
