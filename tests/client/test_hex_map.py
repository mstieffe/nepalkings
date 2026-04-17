# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for HexMap coordinate math, tile lookup, and camera."""
import math
import pytest


def _make_land(col, row, land_id=None, tier=1, gold_rate=5.0,
               suit='Hearts', bonus=2, owner=None, is_mine=False):
    """Create a minimal land dict matching the server serialization."""
    return {
        'id': land_id or (col * 100 + row),
        'col': col, 'row': row,
        'tier': tier, 'gold_rate': gold_rate,
        'suit_bonus_suit': suit, 'suit_bonus_value': bonus,
        'owner': owner, 'is_mine': is_mine,
    }


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
