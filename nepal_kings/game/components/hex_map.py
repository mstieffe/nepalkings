# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Hex-grid map renderer for the Kingdom screen."""

import math
import os
import pygame
from config import settings
import logging

logger = logging.getLogger('nk.components.hex_map')

# ── Flat-top hexagon helpers ────────────────────────────────────────────────

def _hex_corner(cx, cy, size, i):
    """Return the (x, y) of the *i*-th corner of a flat-top hex centred at (cx, cy)."""
    angle_rad = math.pi / 180 * (60 * i)
    return (cx + size * math.cos(angle_rad),
            cy + size * math.sin(angle_rad))


def _hex_corners(cx, cy, size):
    """Return list of 6 corner points for a flat-top hex."""
    return [_hex_corner(cx, cy, size, i) for i in range(6)]


def _owner_color(user_id):
    """Deterministic colour from *user_id* for owner tinting."""
    if user_id is None:
        return None
    h = hash(user_id) & 0xFFFFFF
    r = 80 + ((h >> 16) & 0xFF) % 150
    g = 80 + ((h >> 8) & 0xFF) % 150
    b = 80 + (h & 0xFF) % 150
    return (r, g, b)


# ═══════════════════════════════════════════════════════════════════
#  HexTile — data object for a single hex
# ═══════════════════════════════════════════════════════════════════

class HexTile:
    """Lightweight data holder for a single hex on the map."""

    __slots__ = (
        'land_id', 'col', 'row', 'tier', 'gold_rate',
        'suit_bonus_suit', 'suit_bonus_value',
        'owner', 'is_mine', 'defence_incomplete',
        'conquer_cooldown_remaining', 'cx', 'cy',
    )

    def __init__(self, land_dict, cx, cy):
        self.land_id = land_dict['id']
        self.col = land_dict['col']
        self.row = land_dict['row']
        self.tier = land_dict['tier']
        self.gold_rate = land_dict['gold_rate']
        self.suit_bonus_suit = land_dict['suit_bonus_suit']
        self.suit_bonus_value = land_dict['suit_bonus_value']
        self.owner = land_dict.get('owner')
        self.is_mine = land_dict.get('is_mine', False)
        self.defence_incomplete = land_dict.get('defence_incomplete', False)
        self.conquer_cooldown_remaining = land_dict.get(
            'conquer_cooldown_remaining', 0)
        self.cx = cx
        self.cy = cy

    @property
    def owner_user_id(self):
        return self.owner['user_id'] if self.owner else None

    @property
    def owner_username(self):
        return self.owner['username'] if self.owner else None


# ═══════════════════════════════════════════════════════════════════
#  HexMap — the main renderable hex grid
# ═══════════════════════════════════════════════════════════════════

class HexMap:
    """Flat-top hex grid with camera pan / zoom and minimap.

    Coordinate system: odd-column offset.
      pixel_x = col * 1.5 * size
      pixel_y = row * sqrt(3) * size + (col % 2) * sqrt(3)/2 * size
    """

    def __init__(self, lands_data, window):
        self.window = window
        self._size = settings.HEX_SIZE
        self._border_w = settings.HEX_BORDER_W

        # Camera state (world coordinates, before zoom)
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.zoom = 1.0

        # Drag state
        self._dragging = False
        self._drag_start = None
        self._drag_cam_start = None
        self._did_drag = False

        # Hover / selection
        self.hovered_tile = None
        self.selected_tile = None

        # Build tiles
        self.tiles = []
        self._build_tiles(lands_data)

        # Pre-load suit icons
        self._suit_icons = {}
        icon_sz = settings.HEX_ICON_SIZE
        for suit, path in settings.SUIT_ICON_PATHS.items():
            try:
                raw = pygame.image.load(path).convert_alpha()
                self._suit_icons[suit] = pygame.transform.smoothscale(raw, (icon_sz, icon_sz))
            except Exception:
                logger.warning(f'Could not load suit icon: {path}')

        # Pre-load gold icon
        self._gold_icon = None
        try:
            raw = pygame.image.load(settings.GAME_MENU_GOLD_ICON_PATH).convert_alpha()
            self._gold_icon = pygame.transform.smoothscale(raw, (icon_sz, icon_sz))
        except Exception:
            logger.warning('Could not load gold icon for hex map')

        # Pre-load broken/warning icon for incomplete defences
        # Load at higher resolution to avoid blurriness when scaled up on tiles
        self._broken_icon_raw = None
        self._broken_icon = None
        try:
            broken_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))),
                'img', 'figures', 'state_icons', 'broken.png')
            self._broken_icon_raw = pygame.image.load(broken_path).convert_alpha()
            self._broken_icon = self._broken_icon_raw
        except Exception:
            logger.warning('Could not load broken icon for hex map')

        # Fonts
        self._label_font = settings.get_font(settings.HEX_LABEL_FONT_SIZE)
        self._tier_font = settings.get_font(settings.HEX_LABEL_FONT_SIZE, bold=True)

        # Centre camera on the grid
        self._centre_camera()

    # ── Grid construction ───────────────────────────────────────────

    def _build_tiles(self, lands_data):
        """Build HexTile objects with world-space centre positions."""
        self.tiles = []
        s = self._size
        for ld in lands_data:
            col, row = ld['col'], ld['row']
            cx = col * 1.5 * s
            cy = row * math.sqrt(3) * s + (col % 2) * math.sqrt(3) / 2 * s
            self.tiles.append(HexTile(ld, cx, cy))

    def _centre_camera(self):
        """Set camera so the grid is centred in the viewport."""
        if not self.tiles:
            return
        min_x = min(t.cx for t in self.tiles)
        max_x = max(t.cx for t in self.tiles)
        min_y = min(t.cy for t in self.tiles)
        max_y = max(t.cy for t in self.tiles)
        grid_cx = (min_x + max_x) / 2
        grid_cy = (min_y + max_y) / 2
        vw = settings.SCREEN_WIDTH
        vh = settings.SCREEN_HEIGHT
        self.camera_x = grid_cx - vw / (2 * self.zoom)
        self.camera_y = grid_cy - vh / (2 * self.zoom)

    # ── Coordinate transforms ──────────────────────────────────────

    def world_to_screen(self, wx, wy):
        """Convert world coordinates to screen pixel coordinates."""
        sx = (wx - self.camera_x) * self.zoom
        sy = (wy - self.camera_y) * self.zoom
        return (sx, sy)

    def screen_to_world(self, sx, sy):
        """Convert screen pixel coordinates to world coordinates."""
        wx = sx / self.zoom + self.camera_x
        wy = sy / self.zoom + self.camera_y
        return (wx, wy)

    # ── Hit testing ─────────────────────────────────────────────────

    def tile_at_screen_pos(self, sx, sy):
        """Return the HexTile under screen position (sx, sy), or None."""
        wx, wy = self.screen_to_world(sx, sy)
        best = None
        best_dist = float('inf')
        sz = self._size
        # Quick radius check (hex inscribed circle radius = size * sqrt(3)/2)
        max_r = sz
        for tile in self.tiles:
            dx = wx - tile.cx
            dy = wy - tile.cy
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < max_r and dist < best_dist:
                best = tile
                best_dist = dist
        return best

    # ── Event handling ──────────────────────────────────────────────

    def handle_event(self, event):
        """Process a single pygame event. Returns clicked HexTile or None."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._dragging = True
            self._drag_start = event.pos
            self._drag_cam_start = (self.camera_x, self.camera_y)
            self._did_drag = False
            return None

        if event.type == pygame.MOUSEMOTION:
            # Update hover
            self.hovered_tile = self.tile_at_screen_pos(*event.pos)
            # Handle drag
            if self._dragging and self._drag_start:
                dx = event.pos[0] - self._drag_start[0]
                dy = event.pos[1] - self._drag_start[1]
                if abs(dx) > settings.HEX_MAP_DRAG_THRESHOLD or \
                   abs(dy) > settings.HEX_MAP_DRAG_THRESHOLD:
                    self._did_drag = True
                if self._did_drag:
                    self.camera_x = self._drag_cam_start[0] - dx / self.zoom
                    self.camera_y = self._drag_cam_start[1] - dy / self.zoom
            return None

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_drag = self._did_drag
            self._dragging = False
            self._drag_start = None
            self._drag_cam_start = None
            self._did_drag = False
            if not was_drag:
                clicked = self.tile_at_screen_pos(*event.pos)
                if clicked:
                    self.selected_tile = clicked
                    return clicked
            return None

        if event.type == pygame.MOUSEWHEEL:
            # Zoom centred on cursor
            mx, my = pygame.mouse.get_pos()
            wx, wy = self.screen_to_world(mx, my)
            if event.y > 0:
                self.zoom = min(settings.HEX_MAP_ZOOM_MAX,
                                self.zoom + settings.HEX_MAP_ZOOM_STEP)
            elif event.y < 0:
                self.zoom = max(settings.HEX_MAP_ZOOM_MIN,
                                self.zoom - settings.HEX_MAP_ZOOM_STEP)
            # Adjust camera so the world point under cursor stays put
            self.camera_x = wx - mx / self.zoom
            self.camera_y = wy - my / self.zoom
            return None

        return None

    # ── Zoom via navigation buttons ─────────────────────────────────

    def zoom_in(self):
        cx = settings.SCREEN_WIDTH / 2
        cy = settings.SCREEN_HEIGHT / 2
        wx, wy = self.screen_to_world(cx, cy)
        self.zoom = min(settings.HEX_MAP_ZOOM_MAX,
                        self.zoom + settings.HEX_MAP_ZOOM_STEP)
        self.camera_x = wx - cx / self.zoom
        self.camera_y = wy - cy / self.zoom

    def zoom_out(self):
        cx = settings.SCREEN_WIDTH / 2
        cy = settings.SCREEN_HEIGHT / 2
        wx, wy = self.screen_to_world(cx, cy)
        self.zoom = max(settings.HEX_MAP_ZOOM_MIN,
                        self.zoom - settings.HEX_MAP_ZOOM_STEP)
        self.camera_x = wx - cx / self.zoom
        self.camera_y = wy - cy / self.zoom

    def pan(self, dx_world, dy_world):
        self.camera_x += dx_world
        self.camera_y += dy_world

    # ── Rendering ───────────────────────────────────────────────────

    def render(self):
        """Draw all visible hexes, labels, and minimap."""
        sz = self._size * self.zoom
        vw = settings.SCREEN_WIDTH
        vh = settings.SCREEN_HEIGHT

        for tile in self.tiles:
            scx, scy = self.world_to_screen(tile.cx, tile.cy)

            # Frustum culling
            if scx < -sz * 2 or scx > vw + sz * 2:
                continue
            if scy < -sz * 2 or scy > vh + sz * 2:
                continue

            corners = _hex_corners(scx, scy, sz)
            self._draw_hex(tile, corners, scx, scy, sz)

        self._draw_minimap()

    def _draw_hex(self, tile, corners, scx, scy, sz):
        """Draw a single hex with fill, border, and labels."""
        # Fill colour (tier-based)
        fill = list(settings.HEX_TIER_FILL.get(tile.tier, (100, 100, 100)))

        # Owner tint overlay
        owner_clr = _owner_color(tile.owner_user_id)
        if owner_clr:
            a = settings.HEX_OWNER_ALPHA / 255.0
            fill[0] = int(fill[0] * (1 - a) + owner_clr[0] * a)
            fill[1] = int(fill[1] * (1 - a) + owner_clr[1] * a)
            fill[2] = int(fill[2] * (1 - a) + owner_clr[2] * a)

        # Hover brighten
        if tile is self.hovered_tile:
            b = settings.HEX_HOVER_BRIGHTEN
            fill = [min(255, c + b) for c in fill]

        pygame.draw.polygon(self.window, fill, corners)

        # Border
        if tile is self.selected_tile:
            border_clr = settings.HEX_SELECT_BORDER
            bw = self._border_w + 1
        elif tile.is_mine:
            border_clr = settings.HEX_MINE_BORDER
            bw = self._border_w + 1
        else:
            border_clr = settings.HEX_TIER_BORDER.get(tile.tier, settings.HEX_EMPTY_BORDER)
            bw = self._border_w
        pygame.draw.polygon(self.window, border_clr, corners, max(1, int(bw * self.zoom / 1.0)))

        # Only draw labels when zoomed in enough to read
        if sz < 20:
            return

        # Tier stars (top of hex)
        tier_text = settings.TIER_LABELS.get(tile.tier, '')
        star_surf = self._tier_font.render(tier_text, True, settings.LAND_DETAIL_TITLE_CLR)
        star_rect = star_surf.get_rect(centerx=scx, top=scy - sz * 0.55)
        self.window.blit(star_surf, star_rect)

        # Gold rate (centre-left with icon)
        icon_sz = int(settings.HEX_ICON_SIZE * self.zoom)
        if icon_sz > 6 and self._gold_icon:
            gold_icon = pygame.transform.smoothscale(self._gold_icon, (icon_sz, icon_sz))
            gold_text = self._label_font.render(f'{tile.gold_rate:.0f}', True, (250, 221, 0))
            total_w = icon_sz + 2 + gold_text.get_width()
            start_x = scx - total_w // 2
            self.window.blit(gold_icon, (start_x, scy - icon_sz // 2))
            self.window.blit(gold_text, (start_x + icon_sz + 2,
                                         scy - gold_text.get_height() // 2))

        # Suit bonus (bottom, with suit icon)
        suit_icon = self._suit_icons.get(tile.suit_bonus_suit)
        if icon_sz > 6 and suit_icon:
            s_icon = pygame.transform.smoothscale(suit_icon, (icon_sz, icon_sz))
            bonus_text = self._label_font.render(f'+{tile.suit_bonus_value}', True, (220, 210, 195))
            total_w = icon_sz + 2 + bonus_text.get_width()
            start_x = scx - total_w // 2
            iy = scy + sz * 0.15
            self.window.blit(s_icon, (start_x, iy))
            self.window.blit(bonus_text, (start_x + icon_sz + 2,
                                          iy + (icon_sz - bonus_text.get_height()) // 2))

        # Owner name (bottom of hex)
        if tile.owner_username and sz > 30:
            name_surf = self._label_font.render(tile.owner_username, True, (200, 200, 200))
            name_rect = name_surf.get_rect(centerx=scx, bottom=scy + sz * 0.75)
            self.window.blit(name_surf, name_rect)

        # Broken icon for incomplete defence (only on player's own tiles)
        if tile.defence_incomplete and self._broken_icon_raw and icon_sz > 6:
            broken_sz = int(icon_sz * 2)
            b_icon = pygame.transform.smoothscale(
                self._broken_icon_raw, (broken_sz, broken_sz))
            bx = int(scx + sz * 0.20)
            by = int(scy - sz * 0.65)
            self.window.blit(b_icon, (bx, by))

    # ── Minimap ─────────────────────────────────────────────────────

    def _draw_minimap(self):
        """Draw a small overview map in the bottom-right corner."""
        if not self.tiles:
            return

        mm_w = settings.MINIMAP_W
        mm_h = settings.MINIMAP_H
        margin = settings.MINIMAP_MARGIN
        if hasattr(self, 'minimap_origin') and self.minimap_origin:
            mm_x, mm_y = self.minimap_origin
        else:
            mm_x = settings.SCREEN_WIDTH - mm_w - margin
            mm_y = settings.SCREEN_HEIGHT - mm_h - margin

        # Background
        mm_surf = pygame.Surface((mm_w, mm_h), pygame.SRCALPHA)
        mm_surf.fill(settings.MINIMAP_BG_CLR)

        # Compute world bounds
        min_wx = min(t.cx for t in self.tiles) - self._size
        max_wx = max(t.cx for t in self.tiles) + self._size
        min_wy = min(t.cy for t in self.tiles) - self._size
        max_wy = max(t.cy for t in self.tiles) + self._size
        world_w = max_wx - min_wx
        world_h = max_wy - min_wy
        if world_w == 0 or world_h == 0:
            return

        scale = min((mm_w - 8) / world_w, (mm_h - 8) / world_h)
        off_x = (mm_w - world_w * scale) / 2
        off_y = (mm_h - world_h * scale) / 2

        # Draw hex dots
        for tile in self.tiles:
            tx = off_x + (tile.cx - min_wx) * scale
            ty = off_y + (tile.cy - min_wy) * scale
            dot_r = max(2, int(self._size * scale * 0.5))
            clr = settings.HEX_TIER_FILL.get(tile.tier, (100, 100, 100))
            if tile.is_mine:
                clr = settings.HEX_MINE_BORDER
            pygame.draw.circle(mm_surf, clr, (int(tx), int(ty)), dot_r)

        # Draw viewport rectangle
        vp_left = off_x + (self.camera_x - min_wx) * scale
        vp_top = off_y + (self.camera_y - min_wy) * scale
        vp_w = settings.SCREEN_WIDTH / self.zoom * scale
        vp_h = settings.SCREEN_HEIGHT / self.zoom * scale
        vp_rect = pygame.Rect(int(vp_left), int(vp_top), int(vp_w), int(vp_h))
        pygame.draw.rect(mm_surf, settings.MINIMAP_VIEWPORT_CLR, vp_rect, 1)

        # Border
        pygame.draw.rect(mm_surf, settings.MINIMAP_BORDER_CLR,
                         mm_surf.get_rect(), settings.MINIMAP_BORDER_W)

        self.window.blit(mm_surf, (mm_x, mm_y))
        self._minimap_rect = pygame.Rect(mm_x, mm_y, mm_w, mm_h)
        # Store minimap transform info for click handling
        self._mm_scale = scale
        self._mm_off_x = off_x
        self._mm_off_y = off_y
        self._mm_min_wx = min_wx
        self._mm_min_wy = min_wy
        self._mm_x = mm_x
        self._mm_y = mm_y

    def handle_minimap_click(self, sx, sy):
        """If (sx, sy) is inside the minimap, jump camera there. Returns True if handled."""
        if not hasattr(self, '_minimap_rect') or not self._minimap_rect.collidepoint(sx, sy):
            return False
        # Convert minimap pixel to world coordinate
        local_x = sx - self._mm_x
        local_y = sy - self._mm_y
        wx = (local_x - self._mm_off_x) / self._mm_scale + self._mm_min_wx
        wy = (local_y - self._mm_off_y) / self._mm_scale + self._mm_min_wy
        # Centre camera on that world point
        self.camera_x = wx - settings.SCREEN_WIDTH / (2 * self.zoom)
        self.camera_y = wy - settings.SCREEN_HEIGHT / (2 * self.zoom)
        return True

    def update_data(self, lands_data):
        """Refresh tile data (e.g. after ownership change) without resetting camera."""
        old_cam = (self.camera_x, self.camera_y, self.zoom)
        self._build_tiles(lands_data)
        self.camera_x, self.camera_y, self.zoom = old_cam
        self.selected_tile = None
        self.hovered_tile = None
