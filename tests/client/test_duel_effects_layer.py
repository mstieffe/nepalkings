# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Duel effects-layer plumbing contract tests.

Test oracle (desired outcomes):
- ``EffectsLayer`` is the mode-neutral alias of ``ConquerEffectsLayer``.
- ``any_active()`` reflects whether any animation primitive is alive.
- ``apply_screen_shake`` is a no-op on (0, 0) and never raises, even on
  extreme offsets (clamped to ±8).
- ``SubScreen._fx_layer()`` resolves the duel shell's ``_fx`` and returns
  ``None`` when the parent screen has no ``_fx`` (conquer mode).
- ``GameScreen._lookup_duel_figure_rect`` is fail-soft: ``None`` for missing
  figures/subscreens, a real rect when the field icon is present.
"""

from types import SimpleNamespace

import pygame


def _make_layer(size=(64, 48)):
    from game.components.conquer_effects import EffectsLayer

    return EffectsLayer(pygame.Surface(size), lambda _id: None)


class TestEffectsLayerAdditions:
    def test_alias_is_conquer_effects_layer(self):
        from game.components.conquer_effects import ConquerEffectsLayer, EffectsLayer

        assert EffectsLayer is ConquerEffectsLayer

    def test_any_active_false_on_fresh_layer(self):
        assert _make_layer().any_active() is False

    def test_any_active_true_after_spawn_and_false_after_clear(self):
        layer = _make_layer()
        layer.spawn_banner('TEST', (200, 200, 200))
        assert layer.any_active() is True
        layer.spawn_shake()
        layer.spawn_floating_text_at_rect(pygame.Rect(4, 4, 10, 10), '+1')
        assert layer.any_active() is True
        layer.clear()
        assert layer.any_active() is False

    def test_any_active_false_after_animations_expire(self, monkeypatch):
        layer = _make_layer()
        monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)
        layer.spawn_banner('TEST', (200, 200, 200), duration_ms=100)
        layer.spawn_shake(duration_ms=100)
        # Long after expiry: draw() prunes dead primitives.
        monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 60000)
        layer.draw()
        assert layer.any_active() is False


class TestApplyScreenShake:
    def test_zero_offset_leaves_surface_untouched(self):
        from game.components.conquer_effects import apply_screen_shake

        surface = pygame.Surface((32, 24))
        surface.fill((10, 20, 30))
        pygame.draw.rect(surface, (200, 100, 50), pygame.Rect(4, 4, 8, 8))
        before = pygame.image.tostring(surface, 'RGB')
        apply_screen_shake(surface, (0, 0))
        assert pygame.image.tostring(surface, 'RGB') == before

    def test_offset_shifts_content(self):
        from game.components.conquer_effects import apply_screen_shake

        surface = pygame.Surface((32, 24))
        surface.fill((0, 0, 0))
        surface.set_at((10, 10), (255, 255, 255))
        apply_screen_shake(surface, (3, 2))
        assert surface.get_at((13, 12))[:3] == (255, 255, 255)

    def test_extreme_offsets_do_not_raise(self):
        from game.components.conquer_effects import apply_screen_shake

        surface = pygame.Surface((32, 24))
        apply_screen_shake(surface, (500, -500))
        apply_screen_shake(surface, (-1, 1))


class TestSubScreenFxAccessor:
    def _bare_subscreen(self, state):
        from game.screens.sub_screen import SubScreen

        sub = object.__new__(SubScreen)
        sub.state = state
        return sub

    def test_returns_layer_from_duel_shell(self):
        layer = _make_layer()
        parent = SimpleNamespace(_fx=layer)
        sub = self._bare_subscreen(SimpleNamespace(parent_screen=parent))
        assert sub._fx_layer() is layer

    def test_returns_none_when_parent_has_no_fx(self):
        # ConquerGameScreen owns _conquer_effects, not _fx → inert.
        parent = SimpleNamespace(_conquer_effects=object())
        sub = self._bare_subscreen(SimpleNamespace(parent_screen=parent))
        assert sub._fx_layer() is None

    def test_returns_none_without_parent_or_state(self):
        from game.screens.sub_screen import SubScreen

        sub = self._bare_subscreen(SimpleNamespace())
        assert sub._fx_layer() is None
        bare = object.__new__(SubScreen)
        assert bare._fx_layer() is None


class TestLookupDuelFigureRect:
    def _bare_game_screen(self, subscreen='field', field=None):
        from game.screens.game_screen import GameScreen

        screen = GameScreen.__new__(GameScreen)
        screen.state = SimpleNamespace(subscreen=subscreen)
        screen.subscreens = {} if field is None else {'field': field}
        return screen

    def test_none_figure_id_returns_none(self):
        assert self._bare_game_screen()._lookup_duel_figure_rect(None) is None

    def test_non_field_subscreen_returns_none(self):
        field = SimpleNamespace(
            icon_cache={7: SimpleNamespace(rect_frame=pygame.Rect(1, 2, 3, 4))},
            figure_icons=[])
        screen = self._bare_game_screen(subscreen='battle', field=field)
        assert screen._lookup_duel_figure_rect(7) is None

    def test_missing_field_screen_returns_none(self):
        assert self._bare_game_screen(field=None)._lookup_duel_figure_rect(7) is None

    def test_resolves_rect_from_icon_cache(self):
        rect = pygame.Rect(5, 6, 40, 40)
        field = SimpleNamespace(
            icon_cache={7: SimpleNamespace(rect_frame=rect, rect_icon=None)},
            figure_icons=[])
        screen = self._bare_game_screen(field=field)
        assert screen._lookup_duel_figure_rect(7) == rect

    def test_resolves_rect_from_figure_icons_fallback(self):
        rect = pygame.Rect(9, 9, 30, 30)
        icon = SimpleNamespace(
            figure=SimpleNamespace(id=3), rect_frame=None, rect_icon=rect)
        field = SimpleNamespace(icon_cache={}, figure_icons=[icon])
        screen = self._bare_game_screen(field=field)
        assert screen._lookup_duel_figure_rect(3) == rect

    def test_unknown_figure_returns_none(self):
        field = SimpleNamespace(icon_cache={}, figure_icons=[])
        screen = self._bare_game_screen(field=field)
        assert screen._lookup_duel_figure_rect(42) is None


class TestFieldScreenEntranceHelpers:
    def _bare_field(self):
        from game.screens.field_screen import FieldScreen

        field = object.__new__(FieldScreen)
        field.icon_cache = {}
        field.figure_icons = []
        field._figure_entrance_anims = {}
        return field

    def test_note_new_figures_stamps_staggered_records(self, monkeypatch):
        field = self._bare_field()
        monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)

        field.note_new_figures([7, 9, None, 11])

        anims = field._figure_entrance_anims
        assert set(anims) == {'7', '9', '11'}
        stagger = field.FIGURE_ENTRANCE_STAGGER_MS
        assert anims['7']['started_at'] == 1000
        assert anims['9']['started_at'] == 1000 + stagger
        assert anims['11']['started_at'] == 1000 + 3 * stagger

    def test_note_new_figures_keeps_existing_records(self, monkeypatch):
        field = self._bare_field()
        field._figure_entrance_anims = {'3': {'started_at': 500}}
        monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)

        field.note_new_figures([7])

        assert set(field._figure_entrance_anims) == {'3', '7'}
        assert field._figure_entrance_anims['3']['started_at'] == 500

    def test_figure_icon_rect_prefers_cache_then_falls_back(self):
        field = self._bare_field()
        cached_rect = pygame.Rect(1, 2, 30, 30)
        field.icon_cache = {5: SimpleNamespace(rect_frame=cached_rect, rect_icon=None)}
        fallback_rect = pygame.Rect(8, 8, 20, 20)
        field.figure_icons = [SimpleNamespace(
            figure=SimpleNamespace(id=6), rect_frame=None, rect_icon=fallback_rect)]

        assert field._figure_icon_rect(5) == cached_rect
        assert field._figure_icon_rect(6) == fallback_rect
        assert field._figure_icon_rect(99) is None
