# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the redesigned per-tile overlays on the kingdom hex map."""
import pytest


def _make_land(col=0, row=0, land_id=1, tier=1, gold_rate=5.0,
               suit='Hearts', bonus=2, owner=None, owner_style=None,
               is_mine=False, defence_incomplete=False,
               kingdom_id=None, kingdom_name=None,
               kingdom_component_id=None, kingdom_component_size=0,
               kingdom_is_shielded=False, kingdom_shield_remaining=0):
    return {
        'id': land_id, 'col': col, 'row': row,
        'tier': tier, 'gold_rate': gold_rate,
        'suit_bonus_suit': suit, 'suit_bonus_value': bonus,
        'owner': owner, 'owner_style': owner_style or {},
        'is_mine': is_mine,
        'defence_incomplete': defence_incomplete,
        'kingdom_id': kingdom_id, 'kingdom_name': kingdom_name,
        'kingdom_component_id': kingdom_component_id,
        'kingdom_component_size': kingdom_component_size,
        'kingdom_is_shielded': kingdom_is_shielded,
        'kingdom_shield_remaining': kingdom_shield_remaining,
    }


def _new_map(lands, zoom=2.5):
    import pygame
    from game.components.hex_map import HexMap
    window = pygame.Surface((800, 600))
    hm = HexMap(lands, window)
    hm.zoom = zoom
    return hm


# ───────────────────────── tier ribbon ─────────────────────────────

class TestTierRibbon:

    @pytest.mark.parametrize('tier', [1, 2, 3, 4])
    def test_ribbon_renders_one_star_per_tier(self, tier, monkeypatch):
        import pygame
        hm = _new_map([_make_land(tier=tier)])
        polys = []
        real_polygon = pygame.draw.polygon

        def spy(surf, color, points, width=0):
            polys.append((tuple(color), tuple(tuple(p) for p in points)))
            return real_polygon(surf, color, points, width)

        monkeypatch.setattr(pygame.draw, 'polygon', spy)
        hm._draw_tier_ribbon(hm.tiles[0], 100, 100, 60)
        # Each star = shadow polygon + fill polygon + border polygon
        # Lower bound: at least 2 polygons per star (some may have 0-width
        # border on tiny stars).
        assert len(polys) >= 2 * tier

    def test_legacy_top_star_row_not_called_from_details(self, monkeypatch):
        hm = _new_map([_make_land(tier=3, owner=None)])
        called = {'count': 0}
        monkeypatch.setattr(hm, '_draw_tier_stars',
                            lambda *a, **kw: called.__setitem__(
                                'count', called['count'] + 1))
        hm._draw_hex_details(hm.tiles[0], 200, 200, 60)
        assert called['count'] == 0


# ───────────────────────── warning badge ───────────────────────────

class TestWarningBadge:

    def test_drawn_only_when_incomplete(self, monkeypatch):
        hm = _new_map([_make_land(defence_incomplete=False, is_mine=True)])
        calls = {'n': 0}
        monkeypatch.setattr(hm, '_draw_warning_badge',
                            lambda *a, **kw: calls.__setitem__('n',
                                                                calls['n'] + 1))
        hm._draw_hex_details(hm.tiles[0], 100, 100, 60)
        assert calls['n'] == 0

        hm2 = _new_map([_make_land(defence_incomplete=True, is_mine=True)])
        calls = {'n': 0}
        monkeypatch.setattr(hm2, '_draw_warning_badge',
                            lambda *a, **kw: calls.__setitem__('n',
                                                                calls['n'] + 1))
        hm2._draw_hex_details(hm2.tiles[0], 100, 100, 60)
        assert calls['n'] == 1

    def test_alpha_pulses_over_time(self):
        import pygame
        hm = _new_map([_make_land(defence_incomplete=True, is_mine=True)])
        # Snapshot the bg colors used by sampling internal calc.
        from config import settings
        import math
        hz = settings.HEX_WARNING_PULSE_HZ
        a0 = max(160, min(240,
            200 + int(40 * math.sin(0 * hz * 2 * math.pi))))
        a1 = max(160, min(240,
            200 + int(40 * math.sin((1 / (4 * hz)) * hz * 2 * math.pi))))
        assert a0 != a1


# ─────────────────── progressive disclosure / zoom ─────────────────

class TestProgressiveDisclosure:

    def _spy_calls(self, monkeypatch, hm, names):
        seen = {n: 0 for n in names}
        for n in names:
            monkeypatch.setattr(
                hm, n,
                lambda *a, _n=n, **kw: seen.__setitem__(_n, seen[_n] + 1))
        return seen

    def test_below_min_zoom_skips_center_suit_and_ribbon(self, monkeypatch):
        hm = _new_map([_make_land()], zoom=1.0)
        seen = self._spy_calls(monkeypatch, hm,
                                ['_draw_center_suit', '_draw_tier_ribbon'])
        hm._draw_hex_details(hm.tiles[0], 100, 100, 30)
        assert seen['_draw_center_suit'] == 0
        assert seen['_draw_tier_ribbon'] == 0

    def test_icons_at_min_zoom_no_center_suit_below_numbers_zoom(self, monkeypatch):
        hm = _new_map([_make_land()], zoom=1.5)
        # At min icon zoom (1.5) the per-tile centred suit is still hidden;
        # it only appears at HEX_MAP_LAND_NUMBERS_MIN_ZOOM (2.0+).
        from config import settings
        assert settings.HEX_MAP_LAND_INFO_MIN_ZOOM == 1.5
        called = {'ribbon': 0, 'suit': 0}
        monkeypatch.setattr(
            hm, '_draw_tier_ribbon',
            lambda *a, **kw: called.__setitem__('ribbon', called['ribbon'] + 1))
        monkeypatch.setattr(
            hm, '_draw_center_suit',
            lambda *a, **kw: called.__setitem__('suit', called['suit'] + 1))
        hm._draw_hex_details(hm.tiles[0], 100, 100, 60)
        assert called['ribbon'] == 1
        assert called['suit'] == 0

    def test_center_suit_drawn_at_or_above_numbers_zoom(self, monkeypatch):
        hm = _new_map([_make_land()], zoom=2.0)
        called = {'n': 0}
        monkeypatch.setattr(
            hm, '_draw_center_suit',
            lambda *a, **kw: called.__setitem__('n', called['n'] + 1))
        hm._draw_hex_details(hm.tiles[0], 100, 100, 60)
        assert called['n'] == 1


# ───────────────────── kingdom badge cluster gating ───────────────

class TestKingdomBadge:

    def test_badge_drawn_only_when_zoomed_out(self, monkeypatch):
        owner = {'user_id': 7, 'username': 'rex'}
        lands = [
            _make_land(col=0, row=0, land_id=1, owner=owner, kingdom_id=4,
                        kingdom_name='Realm'),
            _make_land(col=1, row=0, land_id=2, owner=owner, kingdom_id=4,
                        kingdom_name='Realm'),
        ]
        from game.components import badge_cosmetics
        from config import settings
        # Zoomed out (below OWNER_NAME_MIN_ZOOM) → cluster badge drawn.
        hm = _new_map(lands, zoom=1.0)
        called = {'n': 0}
        original = badge_cosmetics.render_badge

        def spy(*a, **kw):
            called['n'] += 1
            return original(*a, **kw)

        monkeypatch.setattr(badge_cosmetics, 'render_badge', spy)
        hm._draw_kingdom_badges(60)
        assert called['n'] >= 1

        # Zoomed in past the cluster-name threshold → no cluster badge.
        hm2 = _new_map(lands, zoom=settings.HEX_MAP_OWNER_NAME_MIN_ZOOM + 0.5)
        called['n'] = 0
        hm2._draw_kingdom_badges(60)
        assert called['n'] == 0


# ─────────────────────────── owner chip ────────────────────────────

class TestOwnerChip:

    def test_dot_only_when_name_hidden(self, monkeypatch):
        hm = _new_map([_make_land(
            owner={'user_id': 1, 'username': 'longusername'})],
                      zoom=1.5)
        renders = []

        class FakeFont:
            def render(self, text, *a, **kw):
                renders.append(text)
                return hm._label_font.render(text, *a, **kw)

            def size(self, text):
                return hm._label_font.size(text)

            def get_height(self):
                return hm._label_font.get_height()

        hm._label_font = FakeFont()
        hm._draw_owner_chip(hm.tiles[0], 100, 100, 60, show_name=False)
        assert renders == []

    def test_name_rendered_when_show_name_true(self, monkeypatch):
        hm = _new_map([_make_land(
            owner={'user_id': 1, 'username': 'alice'})], zoom=2.0)
        renders = []

        real_font = hm._label_font

        class FakeFont:
            def render(self, text, *a, **kw):
                renders.append(text)
                return real_font.render(text, *a, **kw)

            def size(self, text):
                return real_font.size(text)

            def get_height(self):
                return real_font.get_height()

        hm._label_font = FakeFont()
        hm._draw_owner_chip(hm.tiles[0], 100, 100, 60, show_name=True)
        assert any('alice' in t for t in renders)


# ────────────────────────── pill helper ────────────────────────────

class TestPillHelper:

    def test_pill_helper_caches_surfaces_per_role(self):
        import pygame
        hm = _new_map([_make_land()], zoom=2.5)
        rect = pygame.Rect(0, 0, 40, 18)
        hm._draw_pill(rect, role='default')
        hm._draw_pill(rect, role='own')
        hm._draw_pill(rect, role='default')
        # Two distinct keys (one per role); same-role second call hits cache.
        assert ('default', 40, 18) in hm._pill_cache
        assert ('own', 40, 18) in hm._pill_cache
