# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for HexMap coordinate math, tile lookup, and camera."""
import math
import pytest
from types import SimpleNamespace


def _make_land(col, row, land_id=None, tier=1, gold_rate=5.0,
               suit='Hearts', bonus=2, owner=None, owner_style=None,
               is_mine=False, kingdom_component_id=None,
               kingdom_component_size=0, kingdom_level=0,
               kingdom_tier_name=None, kingdom_bonuses=None,
               kingdom_id=None, kingdom_name=None):
    """Create a minimal land dict matching the server serialization."""
    land = {
        'id': land_id or (col * 100 + row),
        'col': col, 'row': row,
        'tier': tier, 'gold_rate': gold_rate,
        'suit_bonus_suit': suit, 'suit_bonus_value': bonus,
        'owner': owner, 'is_mine': is_mine,
        'kingdom_component_id': kingdom_component_id,
        'kingdom_component_size': kingdom_component_size,
        'kingdom_level': kingdom_level,
        'kingdom_tier_name': kingdom_tier_name,
        'kingdom_bonuses': kingdom_bonuses or {},
        'kingdom_id': kingdom_id,
        'kingdom_name': kingdom_name,
    }
    if owner_style is not None:
        land['owner_style'] = owner_style
    return land


# ═══════════════════════════════════════════════════════════════════
#  HexTile
# ═══════════════════════════════════════════════════════════════════

class TestHexTile:

    def test_basic_properties(self):
        from game.components.hex_map import HexTile
        ld = _make_land(3, 5, land_id=42, tier=2, gold_rate=7.5,
                        suit='Spades', bonus=4, is_mine=True,
                        owner={'user_id': 10, 'username': 'alice',
                               'owned_since': '2026-01-01T00:00:00'})
        tile = HexTile(ld, cx=100.0, cy=200.0)
        assert tile.land_id == 42
        assert tile.col == 3
        assert tile.row == 5
        assert tile.tier == 2
        assert tile.gold_rate == 7.5
        assert tile.suit_bonus_suit == 'Spades'
        assert tile.suit_bonus_value == 4
        assert tile.is_mine is True
        assert tile.owner_user_id == 10
        assert tile.owner_username == 'alice'

    def test_owner_style_payload_is_preserved(self):
        from game.components.hex_map import HexTile
        style = {
            'flag_key': 'flag_sun',
            'border_key': 'border_royal_blue',
            'surface_key': 'surface_stone',
        }
        ld = _make_land(0, 0, owner={'user_id': 10, 'username': 'alice'},
                        owner_style=style)
        tile = HexTile(ld, cx=0, cy=0)
        assert tile.owner_style == style

    def test_connected_kingdom_payload_is_preserved(self):
        from game.components.hex_map import HexTile
        ld = _make_land(0, 0, owner={'user_id': 10, 'username': 'alice'},
                        kingdom_component_id='10:1', kingdom_component_size=4,
                        kingdom_level=2, kingdom_tier_name='Fortified Domain',
                        kingdom_bonuses={'defence_power_bonus': 1},
                        kingdom_id=7, kingdom_name='High Garden')
        tile = HexTile(ld, cx=0, cy=0)
        assert tile.kingdom_component_id == '10:1'
        assert tile.kingdom_component_size == 4
        assert tile.kingdom_level == 2
        assert tile.kingdom_bonuses['defence_power_bonus'] == 1
        assert tile.kingdom_id == 7
        assert tile.kingdom_name == 'High Garden'

    def test_unclaimed_tile(self):
        from game.components.hex_map import HexTile
        ld = _make_land(0, 0)
        tile = HexTile(ld, 0, 0)
        assert tile.owner is None
        assert tile.owner_user_id is None
        assert tile.owner_username is None
        assert tile.is_mine is False


# ═══════════════════════════════════════════════════════════════════
#  Hex coordinate math
# ═══════════════════════════════════════════════════════════════════

class TestHexCoordinates:

    def test_hex_corners_count(self):
        from game.components.hex_map import _hex_corners
        corners = _hex_corners(0, 0, 50)
        assert len(corners) == 6

    def test_hex_corners_first_is_right(self):
        """First corner of flat-top hex should be at (cx + size, cy)."""
        from game.components.hex_map import _hex_corners
        corners = _hex_corners(100, 200, 50)
        # Corner 0 is at angle 0° → (cx + size, cy)
        assert abs(corners[0][0] - 150) < 0.01
        assert abs(corners[0][1] - 200) < 0.01

    def test_hex_corners_symmetry(self):
        """Hex corners should be symmetric about the centre."""
        from game.components.hex_map import _hex_corners
        corners = _hex_corners(0, 0, 50)
        # Opposite corners should be equidistant from centre
        for i in range(3):
            x1, y1 = corners[i]
            x2, y2 = corners[i + 3]
            # They should be mirrored through origin
            assert abs(x1 + x2) < 0.01
            assert abs(y1 + y2) < 0.01


# ═══════════════════════════════════════════════════════════════════
#  HexMap tile layout
# ═══════════════════════════════════════════════════════════════════

class TestHexMapTileLayout:

    def test_tile_positions_col_0(self):
        """Tiles in column 0 should have regular vertical spacing."""
        from game.components.hex_map import HexMap
        from config import settings
        import pygame
        window = pygame.display.get_surface()
        size = settings.HEX_SIZE

        lands = [_make_land(0, r) for r in range(3)]
        hm = HexMap(lands, window)

        # Col 0: x = 0, y spacing = sqrt(3) * size
        expected_dy = math.sqrt(3) * size
        assert abs(hm.tiles[0].cx - 0) < 0.01
        assert abs(hm.tiles[1].cy - hm.tiles[0].cy - expected_dy) < 0.01
        assert abs(hm.tiles[2].cy - hm.tiles[1].cy - expected_dy) < 0.01

    def test_tile_positions_odd_col_offset(self):
        """Odd columns are shifted down by sqrt(3)/2 * size."""
        from game.components.hex_map import HexMap
        from config import settings
        import pygame
        window = pygame.display.get_surface()
        size = settings.HEX_SIZE

        lands = [_make_land(0, 0), _make_land(1, 0)]
        hm = HexMap(lands, window)

        col0 = hm.tiles[0]
        col1 = hm.tiles[1]
        # Column spacing: x = col * 1.5 * size
        assert abs(col1.cx - 1.5 * size) < 0.01
        # Odd column y offset
        expected_y_offset = math.sqrt(3) / 2 * size
        assert abs(col1.cy - col0.cy - expected_y_offset) < 0.01


# ═══════════════════════════════════════════════════════════════════
#  Camera transforms
# ═══════════════════════════════════════════════════════════════════

class TestCameraTransforms:

    def _make_map(self, lands=None):
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()
        if lands is None:
            lands = [_make_land(0, 0)]
        return HexMap(lands, window)

    def test_world_to_screen_default(self):
        """With zoom=1 and camera at (0,0), world == screen."""
        hm = self._make_map()
        hm.camera_x = 0
        hm.camera_y = 0
        hm.zoom = 1.0
        sx, sy = hm.world_to_screen(100, 200)
        assert abs(sx - 100) < 0.01
        assert abs(sy - 200) < 0.01

    def test_world_to_screen_with_pan(self):
        hm = self._make_map()
        hm.camera_x = 50
        hm.camera_y = 30
        hm.zoom = 1.0
        sx, sy = hm.world_to_screen(100, 200)
        assert abs(sx - 50) < 0.01
        assert abs(sy - 170) < 0.01

    def test_world_to_screen_with_zoom(self):
        hm = self._make_map()
        hm.camera_x = 0
        hm.camera_y = 0
        hm.zoom = 2.0
        sx, sy = hm.world_to_screen(100, 200)
        assert abs(sx - 200) < 0.01
        assert abs(sy - 400) < 0.01

    def test_screen_to_world_roundtrip(self):
        """screen_to_world(world_to_screen(w)) == w."""
        hm = self._make_map()
        hm.camera_x = 123
        hm.camera_y = 456
        hm.zoom = 1.7
        wx, wy = 300, 400
        sx, sy = hm.world_to_screen(wx, wy)
        wx2, wy2 = hm.screen_to_world(sx, sy)
        assert abs(wx - wx2) < 0.01
        assert abs(wy - wy2) < 0.01

    def test_viewport_offset_is_applied_to_transforms(self):
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()
        viewport = pygame.Rect(100, 50, 400, 300)
        hm = HexMap([_make_land(0, 0)], window, viewport_rect=viewport)
        hm.camera_x = 0
        hm.camera_y = 0
        hm.zoom = 1.0

        sx, sy = hm.world_to_screen(20, 30)
        assert (sx, sy) == (120, 80)
        wx, wy = hm.screen_to_world(120, 80)
        assert (wx, wy) == (20, 30)

    def test_mouse_wheel_zoom_keeps_cursor_world_point_with_viewport(self, monkeypatch):
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()
        viewport = pygame.Rect(100, 50, 400, 300)
        cursor = (260, 170)
        lands = [_make_land(c, r) for r in range(10) for c in range(18)]
        hm = HexMap(lands, window, viewport_rect=viewport)
        assert (hm._world_max_x - hm._world_min_x) > viewport.w
        assert (hm._world_max_y - hm._world_min_y) > viewport.h
        hm.camera_x = 40
        hm.camera_y = 70
        hm.zoom = 1.0
        before = hm.screen_to_world(*cursor)

        monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: cursor)
        hm.handle_event(SimpleNamespace(type=pygame.MOUSEWHEEL, y=1))

        after = hm.screen_to_world(*cursor)
        assert abs(before[0] - after[0]) < 0.01
        assert abs(before[1] - after[1]) < 0.01

    def test_nav_button_zoom_uses_viewport_center(self):
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()
        viewport = pygame.Rect(100, 50, 400, 300)
        lands = [_make_land(c, r) for r in range(10) for c in range(18)]
        hm = HexMap(lands, window, viewport_rect=viewport)
        assert (hm._world_max_x - hm._world_min_x) > viewport.w
        assert (hm._world_max_y - hm._world_min_y) > viewport.h
        hm.camera_x = 25
        hm.camera_y = 45
        hm.zoom = 1.0
        before = hm.screen_to_world(*viewport.center)

        hm.zoom_in()

        after = hm.screen_to_world(*viewport.center)
        assert abs(before[0] - after[0]) < 0.01
        assert abs(before[1] - after[1]) < 0.01

    def test_pan_is_clamped_to_world_bounds(self):
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()
        lands = [_make_land(c, r) for r in range(12) for c in range(20)]
        viewport = pygame.Rect(100, 50, 320, 220)
        hm = HexMap(lands, window, viewport_rect=viewport)

        world_w = hm._world_max_x - hm._world_min_x
        world_h = hm._world_max_y - hm._world_min_y
        assert world_w > hm.viewport_rect.w / hm.zoom
        assert world_h > hm.viewport_rect.h / hm.zoom

        hm.pan(-10000, -10000)
        assert abs(hm.camera_x - hm._world_min_x) < 0.01
        assert abs(hm.camera_y - hm._world_min_y) < 0.01

        max_x = hm._world_max_x - hm.viewport_rect.w / hm.zoom
        max_y = hm._world_max_y - hm.viewport_rect.h / hm.zoom
        hm.pan(10000, 10000)
        assert abs(hm.camera_x - max_x) < 0.01
        assert abs(hm.camera_y - max_y) < 0.01


# ═══════════════════════════════════════════════════════════════════
#  Tile hit-testing
# ═══════════════════════════════════════════════════════════════════

class TestTileHitTest:

    def test_hit_centre_of_tile(self):
        """Clicking the exact centre of a tile should return that tile."""
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()

        lands = [_make_land(0, 0, land_id=1), _make_land(1, 0, land_id=2)]
        hm = HexMap(lands, window)
        hm.camera_x = 0
        hm.camera_y = 0
        hm.zoom = 1.0

        # Screen position of tile 0's centre
        sx, sy = hm.world_to_screen(hm.tiles[0].cx, hm.tiles[0].cy)
        tile = hm.tile_at_screen_pos(sx, sy)
        assert tile is not None
        assert tile.land_id == 1

    def test_hit_no_tile(self):
        """Clicking far from any tile should return None."""
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()

        lands = [_make_land(0, 0)]
        hm = HexMap(lands, window)
        hm.camera_x = 0
        hm.camera_y = 0
        hm.zoom = 1.0

        tile = hm.tile_at_screen_pos(9999, 9999)
        assert tile is None

    def test_update_data_preserves_camera(self):
        """update_data() should refresh tiles but keep camera position."""
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()

        lands = [_make_land(0, 0)]
        hm = HexMap(lands, window)
        hm.camera_x = 100
        hm.camera_y = 200
        hm.zoom = 1.5

        new_lands = [_make_land(0, 0, owner={'user_id': 1, 'username': 'x',
                                              'owned_since': None},
                                is_mine=True)]
        hm.update_data(new_lands)

        assert hm.camera_x == 100
        assert hm.camera_y == 200
        assert hm.zoom == 1.5
        assert hm.tiles[0].is_mine is True


class TestViewportEventGating:

    def test_drag_cannot_start_outside_viewport(self):
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()
        hm = HexMap([_make_land(0, 0)], window,
                    viewport_rect=pygame.Rect(100, 100, 300, 200))
        old_camera = (hm.camera_x, hm.camera_y)

        hm.handle_event(SimpleNamespace(
            type=pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20)))
        hm.handle_event(SimpleNamespace(
            type=pygame.MOUSEMOTION, pos=(250, 250)))

        assert hm._dragging is False
        assert (hm.camera_x, hm.camera_y) == old_camera

    def test_click_outside_viewport_does_not_select_tile(self):
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()
        hm = HexMap([_make_land(0, 0, land_id=1)], window,
                    viewport_rect=pygame.Rect(100, 100, 300, 200))
        hm.camera_x = 0
        hm.camera_y = 0
        hm.zoom = 1.0

        clicked = hm.handle_event(SimpleNamespace(
            type=pygame.MOUSEBUTTONUP, button=1, pos=(20, 20)))

        assert clicked is None
        assert hm.selected_tile is None

    def test_drag_is_clamped_to_world_bounds(self):
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()
        lands = [_make_land(c, 0) for c in range(20)]
        viewport = pygame.Rect(100, 100, 320, 220)
        hm = HexMap(lands, window, viewport_rect=viewport)

        world_w = hm._world_max_x - hm._world_min_x
        assert world_w > hm.viewport_rect.w / hm.zoom

        start = viewport.center
        hm.handle_event(SimpleNamespace(
            type=pygame.MOUSEBUTTONDOWN, button=1, pos=start))
        hm.handle_event(SimpleNamespace(
            type=pygame.MOUSEMOTION, pos=(start[0] + 10000, start[1])))
        assert abs(hm.camera_x - hm._world_min_x) < 0.01

        hm.handle_event(SimpleNamespace(
            type=pygame.MOUSEMOTION, pos=(start[0] - 10000, start[1])))
        max_x = hm._world_max_x - hm.viewport_rect.w / hm.zoom
        assert abs(hm.camera_x - max_x) < 0.01

    def test_drag_release_detection_for_parent_screen_guard(self):
        from game.components.hex_map import HexMap
        from config import settings
        import pygame
        window = pygame.display.get_surface()
        viewport = pygame.Rect(100, 100, 300, 200)
        hm = HexMap([_make_land(0, 0), _make_land(8, 0)], window,
                    viewport_rect=viewport)
        start = viewport.center

        hm.handle_event(SimpleNamespace(
            type=pygame.MOUSEBUTTONDOWN, button=1, pos=start))
        hm.handle_event(SimpleNamespace(
            type=pygame.MOUSEMOTION,
            pos=(start[0] + settings.HEX_MAP_DRAG_THRESHOLD + 5, start[1])))

        release = SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1, pos=(10, 10))
        assert hm.is_drag_release(release) is True


class TestHexMapVisualSemantics:

    def test_suit_bonus_groups_map_to_blue_and_green(self):
        from game.components.hex_map import _suit_bonus_group

        assert _suit_bonus_group('Spades') == 'blue'
        assert _suit_bonus_group('Clubs') == 'blue'
        assert _suit_bonus_group('Hearts') == 'green'
        assert _suit_bonus_group('Diamonds') == 'green'

    def test_tile_fill_uses_suit_bonus_and_tier_intensity(self):
        from game.components.hex_map import HexTile, _tile_fill_color

        blue_t1 = HexTile(_make_land(0, 0, tier=1, suit='Spades'), 0, 0)
        blue_t3 = HexTile(_make_land(0, 1, tier=3, suit='Spades'), 0, 0)
        green_t2 = HexTile(_make_land(1, 0, tier=2, suit='Hearts'), 0, 0)

        assert _tile_fill_color(blue_t1)[2] > _tile_fill_color(blue_t1)[1]
        assert sum(_tile_fill_color(blue_t1)) > sum(_tile_fill_color(blue_t3))
        assert _tile_fill_color(green_t2)[1] > _tile_fill_color(green_t2)[2]

    def test_vector_star_points_have_outer_and_inner_vertices(self):
        from game.components.hex_map import _star_points

        pts = _star_points(10, 10, 8, 4)

        assert len(pts) == 10
        distances = [math.hypot(x - 10, y - 10) for x, y in pts]
        assert max(distances) > min(distances)

    def test_focus_land_selects_and_centres_tile(self):
        from game.components.hex_map import HexMap
        import pygame
        window = pygame.display.get_surface()
        lands = [_make_land(c, r, land_id=(r * 20 + c + 1))
                 for r in range(12) for c in range(20)]
        hm = HexMap(lands, window, viewport_rect=pygame.Rect(100, 100, 300, 200))
        # Pick a central land to avoid clamping at map borders.
        target_id = (6 * 20 + 10 + 1)
        tile = hm.focus_land(target_id)

        assert tile is not None
        assert hm.selected_tile is tile
        sx, sy = hm.world_to_screen(tile.cx, tile.cy)
        assert abs(sx - hm.viewport_rect.centerx) < 0.01
        assert abs(sy - hm.viewport_rect.centery) < 0.01

    def test_owner_style_key_falls_back_to_client_default(self):
        from game.components.hex_map import HexMap
        from config import settings
        import pygame
        window = pygame.display.get_surface()
        land = _make_land(0, 0, owner={'user_id': 2, 'username': 'bob'})
        hm = HexMap([land], window)

        assert hm._owner_style_key(hm.tiles[0], 'flag_key') == \
            settings.HEX_DEFAULT_OWNER_STYLE['flag_key']

    def test_minimap_click_centres_camera_in_viewport(self):
        from game.components.hex_map import HexMap
        from config import settings
        import pygame
        window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        viewport = pygame.Rect(100, 100, 300, 200)
        hm = HexMap([_make_land(0, 0, land_id=1), _make_land(4, 2, land_id=2)], window,
                    viewport_rect=viewport)
        hm.render()

        handled = hm.handle_minimap_click(hm._minimap_rect.centerx,
                                          hm._minimap_rect.centery)

        assert handled is True
        wx, wy = hm.screen_to_world(*viewport.center)
        local_x = hm._minimap_rect.centerx - hm._mm_x
        local_y = hm._minimap_rect.centery - hm._mm_y
        expected_wx = (local_x - hm._mm_off_x) / hm._mm_scale + hm._mm_min_wx
        expected_wy = (local_y - hm._mm_off_y) / hm._mm_scale + hm._mm_min_wy
        assert abs(wx - expected_wx) < 0.01
        assert abs(wy - expected_wy) < 0.01

    def test_same_owner_neighbour_detects_connected_edge(self):
        from game.components.hex_map import HexMap, _edge_neighbour_coords
        from config import settings
        import pygame
        owner = {'user_id': 7, 'username': 'owner'}
        rival = {'user_id': 8, 'username': 'rival'}
        window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        hm = HexMap([
            _make_land(0, 0, land_id=1, owner=owner),
            _make_land(1, 0, land_id=2, owner=owner),
            _make_land(0, 1, land_id=3, owner=rival),
        ], window)
        tile = hm.tiles[0]

        assert (1, 0) in _edge_neighbour_coords(0, 0)
        assert hm._same_owner_neighbour(tile, (1, 0)) is True
        assert hm._same_owner_neighbour(tile, (0, 1)) is False

    def test_land_info_visibility_uses_zoom_threshold(self):
        from game.components.hex_map import HexMap
        from config import settings
        import pygame
        window = pygame.display.get_surface()
        hm = HexMap([_make_land(0, 0, tier=3, suit='Spades')], window)

        hm.zoom = settings.HEX_MAP_LAND_INFO_MIN_ZOOM - 0.01
        assert hm._should_draw_land_info(25) is False

        hm.zoom = settings.HEX_MAP_LAND_INFO_MIN_ZOOM
        assert hm._should_draw_land_info(25) is True

    def test_draw_hex_hides_stars_until_zoom_threshold(self):
        from game.components.hex_map import HexMap, _hex_corners
        from config import settings
        import pygame
        window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        hm = HexMap([_make_land(0, 0, tier=3, suit='Spades')], window)
        tile = hm.tiles[0]
        scx, scy = hm.world_to_screen(tile.cx, tile.cy)

        called = {'stars': False}

        def _mark_stars(*_args, **_kwargs):
            called['stars'] = True

        hm._draw_tier_stars = _mark_stars
        hm.zoom = settings.HEX_MAP_LAND_INFO_MIN_ZOOM - 0.01
        sz = hm._size * hm.zoom
        corners = _hex_corners(scx, scy, sz)
        hm._draw_hex(tile, corners, scx, scy, sz)
        assert called['stars'] is False

        hm.zoom = settings.HEX_MAP_LAND_INFO_MIN_ZOOM
        sz = hm._size * hm.zoom
        corners = _hex_corners(scx, scy, sz)
        hm._draw_hex(tile, corners, scx, scy, sz)
        assert called['stars'] is True

    def test_kingdom_badges_group_tiles_once_per_kingdom_for_all_players(self):
        from game.components.hex_map import HexMap
        import pygame
        owner = {'user_id': 7, 'username': 'me'}
        rival = {'user_id': 8, 'username': 'rival'}
        window = pygame.display.get_surface()
        hm = HexMap([
            _make_land(0, 0, land_id=1, owner=owner, is_mine=True,
                       kingdom_id=101, kingdom_name='North Pass'),
            _make_land(1, 0, land_id=2, owner=owner, is_mine=True,
                       kingdom_id=101, kingdom_name='North Pass'),
            _make_land(6, 0, land_id=3, owner=owner, is_mine=True,
                       kingdom_id=202, kingdom_name='South Reach'),
            _make_land(7, 0, land_id=4, owner=owner, is_mine=True,
                       kingdom_id=202, kingdom_name='South Reach'),
            _make_land(9, 2, land_id=5, owner=rival, is_mine=False,
                       kingdom_id=303, kingdom_name='Iron Vale'),
            _make_land(10, 2, land_id=6, owner=rival, is_mine=False,
                       kingdom_id=303, kingdom_name='Iron Vale'),
            _make_land(12, 2, land_id=7, owner=None, is_mine=False),
        ], window)

        badges = hm._kingdom_badges()

        assert len(badges) == 3
        names = {badge['name'] for badge in badges}
        assert names == {'North Pass', 'South Reach', 'Iron Vale'}
        for badge in badges:
            assert badge['tile_count'] == 2
