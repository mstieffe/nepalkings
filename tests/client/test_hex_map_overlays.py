# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the redesigned per-tile overlays on the kingdom hex map."""
import math

import pygame
import pytest


def _make_land(col=0, row=0, land_id=1, tier=1, gold_rate=5.0,
               suit='Hearts', bonus=2, owner=None, owner_style=None,
               is_mine=False, defence_incomplete=False,
               kingdom_id=None, kingdom_name=None,
               kingdom_component_id=None, kingdom_component_size=0,
               kingdom_level=0,
               kingdom_is_shielded=False, kingdom_shield_remaining=0,
               region=None):
    return {
        'id': land_id, 'col': col, 'row': row,
        'tier': tier, 'gold_rate': gold_rate,
        'suit_bonus_suit': suit, 'suit_bonus_value': bonus,
        'region': region,
        'owner': owner, 'owner_style': owner_style or {},
        'is_mine': is_mine,
        'defence_incomplete': defence_incomplete,
        'kingdom_id': kingdom_id, 'kingdom_name': kingdom_name,
        'kingdom_level': kingdom_level,
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
    hm._centre_camera()
    return hm


def _point_in_convex_polygon(point, polygon, eps=0.01):
    x, y = point
    signs = []
    for i, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(i + 1) % len(polygon)]
        cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        signs.append(cross)
    return (all(c >= -eps for c in signs)
            or all(c <= eps for c in signs))


# ───────────────────────── tier ribbon ─────────────────────────────

class TestTierRibbon:

    @pytest.mark.parametrize('tier', [1, 2, 3, 4, 5, 6])
    def test_ribbon_renders_one_star_per_tier(self, tier, monkeypatch):
        import pygame
        from config import settings
        hm = _new_map([_make_land(tier=tier)])
        polys = []
        real_polygon = pygame.draw.polygon

        def spy(surf, color, points, width=0):
            polys.append((tuple(color), tuple(tuple(p) for p in points)))
            return real_polygon(surf, color, points, width)

        monkeypatch.setattr(pygame.draw, 'polygon', spy)
        hm._draw_tier_ribbon(hm.tiles[0], 100, 100, 60)
        star_fills = [p for color, p in polys
                      if color == tuple(settings.HEX_STAR_FILL)]
        assert len(star_fills) == tier

    @pytest.mark.parametrize('tier', [5, 6])
    @pytest.mark.parametrize('size', [30, 60])
    def test_high_tier_ribbon_stays_inside_hex(self, tier, size, monkeypatch):
        import pygame
        from config import settings
        from game.components.hex_map import _hex_corners
        hm = _new_map([_make_land(tier=tier)])
        star_points = []
        star_colors = {
            (16, 12, 4),
            tuple(settings.HEX_STAR_FILL),
            tuple(settings.HEX_STAR_BORDER),
        }
        real_polygon = pygame.draw.polygon

        def spy(surf, color, points, width=0):
            if tuple(color) in star_colors:
                star_points.extend(tuple(p) for p in points)
            return real_polygon(surf, color, points, width)

        monkeypatch.setattr(pygame.draw, 'polygon', spy)
        hm._draw_tier_ribbon(hm.tiles[0], 100, 100, size)
        hex_points = _hex_corners(100, 100, size)
        assert star_points
        assert all(_point_in_convex_polygon(p, hex_points)
                   for p in star_points)

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

    def test_suit_resolution_progresses_region_cluster_land(self):
        from config import settings
        overview_zoom = settings.REGION_CLUSTER_ICON_START_ZOOM - 0.01
        hm = _new_map([_make_land()], zoom=overview_zoom)

        assert hm._region_main_suit_factor() == 1.0
        assert hm._suit_cluster_icon_factor() == 0.0

        hm.zoom = settings.REGION_CLUSTER_ICON_FULL_ZOOM
        assert hm._region_main_suit_factor() == 0.0
        assert hm._suit_cluster_icon_factor() == 1.0

        hm.zoom = settings.HEX_MAP_LAND_NUMBERS_MIN_ZOOM
        assert hm._region_main_suit_factor() == 0.0
        assert hm._suit_cluster_icon_factor() == 0.0

    def test_region_main_suit_icon_is_drawn_below_name(self):
        from config import settings
        hm = _new_map([
            _make_land(region='karnali', suit='Spades'),
        ], zoom=settings.REGION_CLUSTER_ICON_START_ZOOM - 0.01)
        hm._suit_icon_raw['Spades'] = pygame.Surface(
            (20, 20), pygame.SRCALPHA)
        label_rect = pygame.Rect(120, 90, 100, 20)

        icon_rect = hm._draw_region_main_suit_icon(
            {'dominant_suit': 'Spades'},
            {'dominant_suit': 'Spades'},
            label_rect,
            18,
            1.0,
        )

        assert icon_rect is not None
        assert icon_rect.centerx == label_rect.centerx
        assert icon_rect.top > label_rect.bottom

    def test_region_without_main_suit_has_no_overview_icon(self):
        from config import settings
        hm = _new_map([
            _make_land(region='kathmandu', suit='Neutral'),
        ], zoom=settings.REGION_CLUSTER_ICON_START_ZOOM - 0.01)

        icon_rect = hm._draw_region_main_suit_icon(
            {'dominant_suit': None},
            {'dominant_suit': None},
            pygame.Rect(120, 90, 100, 20),
            18,
            1.0,
        )

        assert icon_rect is None

    def test_cluster_icons_only_draw_in_intermediate_zoom(self, monkeypatch):
        from config import settings
        hm = _new_map([
            _make_land(col=0, row=0, land_id=1, suit='Hearts'),
            _make_land(col=1, row=0, land_id=2, suit='Hearts'),
        ])
        hm._suit_icon_raw['Hearts'] = pygame.Surface(
            (20, 20), pygame.SRCALPHA)
        calls = []

        def scaled(cache_key, raw, size):
            calls.append((cache_key, size))
            return pygame.Surface((size, size), pygame.SRCALPHA)

        monkeypatch.setattr(hm, '_get_scaled_icon', scaled)

        hm.zoom = settings.REGION_CLUSTER_ICON_START_ZOOM - 0.01
        hm._draw_suit_cluster_icons(60)
        assert calls == []

        hm.zoom = settings.REGION_CLUSTER_ICON_FULL_ZOOM
        hm._draw_suit_cluster_icons(60)
        assert len(calls) == 1

        calls.clear()
        hm.zoom = settings.HEX_MAP_LAND_NUMBERS_MIN_ZOOM
        hm._draw_suit_cluster_icons(60)
        assert calls == []

    def test_touching_same_suit_peaks_remain_separate_clusters(self):
        tiers = [6, 5, 4, 3, 4, 5, 6]
        hm = _new_map([
            _make_land(
                col=0, row=row, land_id=row + 1,
                suit='Spades', tier=tier, region='karnali')
            for row, tier in enumerate(tiers)
        ])

        clusters = hm._suit_clusters()

        assert len(clusters) == 2
        assert {cluster['suit'] for cluster in clusters} == {'Spades'}
        assert sorted(cluster['tile_count'] for cluster in clusters) == [3, 4]

    def test_touching_cluster_with_lower_local_peak_stays_separate(self):
        tiers = [6, 5, 4, 3, 4, 5, 5]
        hm = _new_map([
            _make_land(
                col=0, row=row, land_id=row + 1,
                suit='Hearts', tier=tier, region='lumbini')
            for row, tier in enumerate(tiers)
        ])

        clusters = hm._suit_clusters()

        assert len(clusters) == 2
        assert sorted(cluster['tile_count'] for cluster in clusters) == [3, 4]

    def test_terrain_landmarks_follow_large_clusters_and_scale_with_size(
            self, monkeypatch):
        from config import settings

        lands = []
        land_id = 1
        for row in range(4):
            lands.append(_make_land(
                col=0, row=row, land_id=land_id,
                suit='Spades', tier=6 if row == 0 else 5,
                region='karnali'))
            land_id += 1
        for row in range(4):
            lands.append(_make_land(
                col=4, row=row, land_id=land_id,
                suit='Hearts', tier=6 if row == 0 else 5,
                region='karnali'))
            land_id += 1
        for row in range(8):
            lands.append(_make_land(
                col=8, row=row, land_id=land_id,
                suit='Clubs', tier=6 if row == 0 else 5,
                region='kirat'))
            land_id += 1
        for row in range(4):
            lands.append(_make_land(
                col=12, row=row, land_id=land_id,
                suit='Diamonds', region='kathmandu'))
            land_id += 1

        hm = _new_map(lands)
        monkeypatch.setattr(
            settings, 'REGION_SCENERY_CLUSTER_MIN_TILES', 3)
        monkeypatch.setattr(
            settings, 'REGION_SCENERY_CLUSTER_REFERENCE_TILES', 4)
        monkeypatch.setattr(
            settings, 'REGION_SCENERY_CLUSTER_SCALE_MIN', 0.5)
        monkeypatch.setattr(
            settings, 'REGION_SCENERY_CLUSTER_SCALE_MAX', 2.0)
        hm._terrain_landmarks_cache = None

        landmarks = hm._terrain_landmarks()
        outer = {item[0]: item for item in landmarks
                 if item[0] != 'kathmandu'}
        kathmandu = [item for item in landmarks
                     if item[0] == 'kathmandu']

        assert set(outer) == {'karnali', 'kirat'}
        assert [item[0] for item in landmarks].count('karnali') == 1
        assert len(kathmandu) == 1
        assert kathmandu[0][4] == 1.0
        assert outer['karnali'][4] == pytest.approx(1.0)
        assert outer['kirat'][4] == pytest.approx(math.sqrt(2))

        tile_centers = {
            (tile.region, tile.cx, tile.cy) for tile in hm.tiles
        }
        assert all(
            (region, wx, wy) in tile_centers
            for region, wx, wy, _variant, _scale in outer.values()
        )


# ───────────────────── kingdom badge cluster gating ───────────────

class TestKingdomBadge:

    def test_badge_drawn_at_all_zoom_levels(self, monkeypatch):
        owner = {'user_id': 7, 'username': 'rex'}
        lands = [
            _make_land(col=0, row=0, land_id=1, owner=owner, kingdom_id=4,
                        kingdom_name='Realm', kingdom_level=2),
            _make_land(col=1, row=0, land_id=2, owner=owner, kingdom_id=4,
                        kingdom_name='Realm', kingdom_level=2),
        ]
        from game.components import badge_cosmetics
        from config import settings
        original = badge_cosmetics.render_badge_with_subtitle

        def spy(*a, **kw):
            called['n'] += 1
            return original(*a, **kw)

        monkeypatch.setattr(badge_cosmetics, 'render_badge_with_subtitle', spy)

        # Badges are drawn at all zoom levels when sz > 8.
        for zoom in (0.25, 1.0, settings.HEX_MAP_OWNER_NAME_MIN_ZOOM + 0.5, 4.0):
            called = {'n': 0}
            hm = _new_map(lands, zoom=zoom)
            hm._draw_kingdom_badges(60)
            assert called['n'] >= 1, f'badge not drawn at zoom={zoom}'

    def test_region_champion_medal_is_attached_to_players_kingdom_badge(
            self, monkeypatch):
        owner = {'user_id': 7, 'username': 'rex'}
        hm = _new_map([
            _make_land(col=0, row=0, land_id=1, owner=owner, kingdom_id=4,
                       kingdom_name='Realm', kingdom_level=2),
        ], zoom=1.0)
        hm.set_regions([{
            'key': 'kirat',
            'champions': [{'user_id': 7, 'username': 'rex'}],
        }])
        rendered_sizes = []

        def champion_icon(size):
            rendered_sizes.append(size)
            return pygame.Surface((size, size), pygame.SRCALPHA)

        monkeypatch.setattr(hm, '_render_champion_icon', champion_icon)

        hm._draw_kingdom_badges(60)

        assert hm._region_champion_users == {7}
        assert rendered_sizes


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
