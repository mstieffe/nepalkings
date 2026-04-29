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


def _edge_neighbour_coords(col, row):
    """Return neighbour coordinates for each hex edge in corner order.

    Edge ``i`` spans corner ``i`` to ``i + 1``. Coordinates use the same
    odd-q flat-top layout as the server-side kingdom component logic.
    """
    if col % 2 == 0:
        return [
            (col + 1, row),
            (col, row + 1),
            (col - 1, row),
            (col - 1, row - 1),
            (col, row - 1),
            (col + 1, row - 1),
        ]
    return [
        (col + 1, row + 1),
        (col, row + 1),
        (col - 1, row + 1),
        (col - 1, row),
        (col, row - 1),
        (col + 1, row),
    ]


def _owner_color(user_id):
    """Deterministic colour from *user_id* for owner tinting."""
    if user_id is None:
        return None
    h = hash(user_id) & 0xFFFFFF
    r = 80 + ((h >> 16) & 0xFF) % 150
    g = 80 + ((h >> 8) & 0xFF) % 150
    b = 80 + (h & 0xFF) % 150
    return (r, g, b)


def _suit_bonus_group(suit):
    """Return the semantic colour group for a suit bonus."""
    if suit in ('Spades', 'Clubs'):
        return 'blue'
    if suit in ('Hearts', 'Diamonds'):
        return 'green'
    if suit == 'Neutral':
        return 'neutral'
    return 'green'


def _tile_fill_color(tile):
    """Return the map fill colour for a tile's suit bonus and tier."""
    group = _suit_bonus_group(getattr(tile, 'suit_bonus_suit', None))
    tier = getattr(tile, 'tier', 1)
    return settings.HEX_SUIT_TIER_FILL.get(group, {}).get(
        tier,
        settings.HEX_TIER_FILL.get(tier, (100, 100, 100)),
    )


def _tile_border_color(tile):
    """Return the default border colour for a tile's suit bonus and tier."""
    group = _suit_bonus_group(getattr(tile, 'suit_bonus_suit', None))
    tier = getattr(tile, 'tier', 1)
    return settings.HEX_SUIT_TIER_BORDER.get(group, {}).get(
        tier,
        settings.HEX_TIER_BORDER.get(tier, settings.HEX_EMPTY_BORDER),
    )


def _star_points(cx, cy, outer_r, inner_r, points=5):
    """Return polygon points for a small vector star."""
    pts = []
    start = -math.pi / 2
    step = math.pi / points
    for i in range(points * 2):
        r = outer_r if i % 2 == 0 else inner_r
        a = start + i * step
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


# ═══════════════════════════════════════════════════════════════════
#  HexTile — data object for a single hex
# ═══════════════════════════════════════════════════════════════════

class HexTile:
    """Lightweight data holder for a single hex on the map."""

    __slots__ = (
        'land_id', 'col', 'row', 'tier', 'gold_rate',
        'suit_bonus_suit', 'suit_bonus_value',
        'owner', 'owner_style', 'is_mine', 'defence_incomplete',
        'kingdom_component_id', 'kingdom_component_size', 'kingdom_level',
        'kingdom_tier_name', 'kingdom_bonuses', 'kingdom_name',
        'kingdom_id', 'kingdom_shield_remaining', 'kingdom_shield_reason',
        'kingdom_is_shielded',
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
        self.owner_style = land_dict.get('owner_style') or {}
        self.is_mine = land_dict.get('is_mine', False)
        self.defence_incomplete = land_dict.get('defence_incomplete', False)
        self.kingdom_component_id = land_dict.get('kingdom_component_id')
        self.kingdom_component_size = land_dict.get('kingdom_component_size', 0)
        self.kingdom_level = land_dict.get('kingdom_level', 0)
        self.kingdom_tier_name = land_dict.get('kingdom_tier_name')
        self.kingdom_bonuses = land_dict.get('kingdom_bonuses') or {}
        self.kingdom_name = land_dict.get('kingdom_name')
        self.kingdom_id = land_dict.get('kingdom_id')
        self.kingdom_shield_remaining = land_dict.get('kingdom_shield_remaining', 0) or 0
        self.kingdom_shield_reason = land_dict.get('kingdom_shield_reason')
        self.kingdom_is_shielded = bool(land_dict.get('kingdom_is_shielded', False))
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

    def __init__(self, lands_data, window, viewport_rect=None):
        self.window = window
        self._size = settings.HEX_SIZE
        self._border_w = settings.HEX_BORDER_W
        self.viewport_rect = pygame.Rect(
            viewport_rect or (0, 0, settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)
        )

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
        self._tile_by_coord = {}
        self._world_min_x = 0.0
        self._world_max_x = 0.0
        self._world_min_y = 0.0
        self._world_max_y = 0.0
        self._build_tiles(lands_data)

        # Pre-load suit icons as raw surfaces and scale lazily per size.
        self._suit_icon_raw = {}
        self._scaled_icon_cache = {}
        for suit, path in settings.SUIT_ICON_PATHS.items():
            try:
                self._suit_icon_raw[suit] = pygame.image.load(path).convert_alpha()
            except Exception:
                logger.warning(f'Could not load suit icon: {path}')

        # Pre-load gold icon as raw surface and scale lazily per size.
        self._gold_icon_raw = None
        try:
            gold_icon_path = getattr(
                settings,
                'HEX_GOLD_ICON_PATH',
                settings.GAME_MENU_GOLD_ICON_PATH,
            )
            self._gold_icon_raw = pygame.image.load(
                gold_icon_path).convert_alpha()
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

        self._shield_icon_raw = None
        try:
            shield_path = os.path.join(settings.RESOURCE_BASE,
                                       settings.KINGDOM_SHIELD_ICON_PATH)
            self._shield_icon_raw = pygame.image.load(shield_path).convert_alpha()
        except Exception:
            logger.warning('Could not load kingdom shield icon for hex map')

        # Fonts
        self._label_font = settings.get_font(settings.HEX_LABEL_FONT_SIZE)
        self._tier_font = settings.get_font(settings.HEX_LABEL_FONT_SIZE, bold=True)

        # Centre camera on the grid
        self._centre_camera()

    def _get_scaled_icon(self, cache_key, raw_icon, icon_sz):
        """Return a cached icon surface at icon_sz with crisper downscaling."""
        if not raw_icon or icon_sz <= 0:
            return None
        k = (cache_key, int(icon_sz))
        cached = self._scaled_icon_cache.get(k)
        if cached is not None:
            return cached
        src_w, src_h = raw_icon.get_size()
        # Nearest-neighbour downscale keeps tiny UI icons sharper.
        if icon_sz <= min(src_w, src_h):
            scaled = pygame.transform.scale(raw_icon, (icon_sz, icon_sz))
        else:
            scaled = pygame.transform.smoothscale(raw_icon, (icon_sz, icon_sz))
        self._scaled_icon_cache[k] = scaled
        return scaled

    def _owner_style_key(self, tile, field_name):
        style = getattr(tile, 'owner_style', None) or {}
        default_style = getattr(settings, 'HEX_DEFAULT_OWNER_STYLE', {})
        return style.get(field_name) or default_style.get(field_name)

    def _same_owner_neighbour(self, tile, coord):
        neighbour = self._tile_by_coord.get(coord)
        return bool(neighbour and tile.owner_user_id and
                    neighbour.owner_user_id == tile.owner_user_id)

    # ── Grid construction ───────────────────────────────────────────

    def _build_tiles(self, lands_data):
        """Build HexTile objects with world-space centre positions."""
        self.tiles = []
        self._tile_by_coord = {}
        s = self._size
        for ld in lands_data:
            col, row = ld['col'], ld['row']
            cx = col * 1.5 * s
            cy = row * math.sqrt(3) * s + (col % 2) * math.sqrt(3) / 2 * s
            tile = HexTile(ld, cx, cy)
            self.tiles.append(tile)
            self._tile_by_coord[(tile.col, tile.row)] = tile
        self._update_world_bounds()

    def _update_world_bounds(self):
        """Cache world bounds including hex extents for camera clamping."""
        if not self.tiles:
            self._world_min_x = 0.0
            self._world_max_x = 0.0
            self._world_min_y = 0.0
            self._world_max_y = 0.0
            return
        self._world_min_x = min(t.cx for t in self.tiles) - self._size
        self._world_max_x = max(t.cx for t in self.tiles) + self._size
        self._world_min_y = min(t.cy for t in self.tiles) - self._size
        self._world_max_y = max(t.cy for t in self.tiles) + self._size

    def _clamp_camera(self):
        """Clamp camera so viewport cannot be dragged beyond map borders."""
        if not self.tiles:
            return

        min_wx = self._world_min_x
        max_wx = self._world_max_x
        min_wy = self._world_min_y
        max_wy = self._world_max_y

        world_w = max_wx - min_wx
        world_h = max_wy - min_wy
        view_w = self.viewport_rect.w / self.zoom
        view_h = self.viewport_rect.h / self.zoom

        if view_w >= world_w:
            self.camera_x = min_wx - (view_w - world_w) / 2.0
        else:
            self.camera_x = max(min_wx, min(self.camera_x, max_wx - view_w))

        if view_h >= world_h:
            self.camera_y = min_wy - (view_h - world_h) / 2.0
        else:
            self.camera_y = max(min_wy, min(self.camera_y, max_wy - view_h))

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
        vw = self.viewport_rect.w
        vh = self.viewport_rect.h
        self.camera_x = grid_cx - vw / (2 * self.zoom)
        self.camera_y = grid_cy - vh / (2 * self.zoom)
        self._clamp_camera()

    def set_viewport(self, viewport_rect):
        """Set the screen-space viewport used for render clipping and input gating."""
        self.viewport_rect = pygame.Rect(viewport_rect)
        self._clamp_camera()

    # ── Coordinate transforms ──────────────────────────────────────

    def world_to_screen(self, wx, wy):
        """Convert world coordinates to screen pixel coordinates."""
        sx = self.viewport_rect.x + (wx - self.camera_x) * self.zoom
        sy = self.viewport_rect.y + (wy - self.camera_y) * self.zoom
        return (sx, sy)

    def screen_to_world(self, sx, sy):
        """Convert screen pixel coordinates to world coordinates."""
        wx = (sx - self.viewport_rect.x) / self.zoom + self.camera_x
        wy = (sy - self.viewport_rect.y) / self.zoom + self.camera_y
        return (wx, wy)

    def _in_viewport(self, pos):
        return self.viewport_rect.collidepoint(pos)

    def _should_draw_land_info(self, sz):
        """Return whether tile info labels should be rendered at current zoom."""
        min_zoom = float(getattr(
            settings,
            'HEX_MAP_LAND_INFO_MIN_ZOOM',
            settings.HEX_MAP_ZOOM_MIN,
        ))
        return self.zoom >= min_zoom and sz >= 20

    def _zoom_at_screen_pos(self, sx, sy, zoom_delta):
        """Zoom around a screen-space point while keeping that world point anchored."""
        old_zoom = self.zoom
        wx, wy = self.screen_to_world(sx, sy)
        self.zoom = max(
            settings.HEX_MAP_ZOOM_MIN,
            min(settings.HEX_MAP_ZOOM_MAX, self.zoom + zoom_delta),
        )
        if self.zoom == old_zoom:
            return

        local_x = sx - self.viewport_rect.x
        local_y = sy - self.viewport_rect.y
        self.camera_x = wx - local_x / self.zoom
        self.camera_y = wy - local_y / self.zoom
        self._clamp_camera()

    def is_drag_release(self, event):
        """Return True if *event* is the release of an active drag gesture."""
        return bool(
            event.type == pygame.MOUSEBUTTONUP
            and getattr(event, 'button', None) == 1
            and self._dragging
            and self._did_drag
        )

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
            if not self._in_viewport(event.pos):
                return None
            self._dragging = True
            self._drag_start = event.pos
            self._drag_cam_start = (self.camera_x, self.camera_y)
            self._did_drag = False
            return None

        if event.type == pygame.MOUSEMOTION:
            # Update hover
            if self._in_viewport(event.pos):
                self.hovered_tile = self.tile_at_screen_pos(*event.pos)
            else:
                self.hovered_tile = None
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
                    self._clamp_camera()
            return None

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_drag = self._did_drag
            self._dragging = False
            self._drag_start = None
            self._drag_cam_start = None
            self._did_drag = False
            if not was_drag:
                if not self._in_viewport(event.pos):
                    return None
                clicked = self.tile_at_screen_pos(*event.pos)
                if clicked:
                    self.selected_tile = clicked
                    return clicked
            return None

        if event.type == pygame.MOUSEWHEEL:
            # Zoom centred on cursor
            mx, my = pygame.mouse.get_pos()
            if not self._in_viewport((mx, my)):
                return None
            if event.y > 0:
                self._zoom_at_screen_pos(mx, my, settings.HEX_MAP_ZOOM_STEP)
            elif event.y < 0:
                self._zoom_at_screen_pos(mx, my, -settings.HEX_MAP_ZOOM_STEP)
            return None

        return None

    # ── Zoom via navigation buttons ─────────────────────────────────

    def zoom_in(self):
        cx, cy = self.viewport_rect.center
        self._zoom_at_screen_pos(cx, cy, settings.HEX_MAP_ZOOM_STEP)

    def zoom_out(self):
        cx, cy = self.viewport_rect.center
        self._zoom_at_screen_pos(cx, cy, -settings.HEX_MAP_ZOOM_STEP)

    def pan(self, dx_world, dy_world):
        self.camera_x += dx_world
        self.camera_y += dy_world
        self._clamp_camera()

    # ── Rendering ───────────────────────────────────────────────────

    def render(self):
        """Draw all visible hexes, labels, and minimap."""
        sz = self._size * self.zoom
        vp = self.viewport_rect

        old_clip = self.window.get_clip()
        self.window.set_clip(vp)

        for tile in self.tiles:
            scx, scy = self.world_to_screen(tile.cx, tile.cy)

            # Frustum culling
            if scx < vp.left - sz * 2 or scx > vp.right + sz * 2:
                continue
            if scy < vp.top - sz * 2 or scy > vp.bottom + sz * 2:
                continue

            corners = _hex_corners(scx, scy, sz)
            self._draw_hex(tile, corners, scx, scy, sz)

        self._draw_kingdom_badges(sz)

        self.window.set_clip(old_clip)

        self._draw_minimap()

    def _draw_hex(self, tile, corners, scx, scy, sz):
        """Draw a single hex with fill, border, and labels."""
        # Fill colour follows suit-bonus colour; tier controls intensity.
        fill = list(_tile_fill_color(tile))

        # Hover brighten
        if tile is self.hovered_tile:
            b = settings.HEX_HOVER_BRIGHTEN
            fill = [min(255, c + b) for c in fill]

        if tile.is_mine:
            xs = [p[0] for p in corners]
            ys = [p[1] for p in corners]
            glow_rect = pygame.Rect(
                int(min(xs)) - 4,
                int(min(ys)) - 4,
                int(max(xs) - min(xs)) + 8,
                int(max(ys) - min(ys)) + 8,
            )
            glow_surf = pygame.Surface((glow_rect.w, glow_rect.h), pygame.SRCALPHA)
            local_corners = [(x - glow_rect.x, y - glow_rect.y) for x, y in corners]
            soft_local = [
                (x - glow_rect.x + (x - scx) * 0.10,
                 y - glow_rect.y + (y - scy) * 0.10)
                for x, y in corners
            ]
            pygame.draw.polygon(glow_surf, settings.HEX_MINE_GLOW_SOFT_CLR, soft_local)
            pygame.draw.polygon(glow_surf, settings.HEX_MINE_GLOW_CLR, local_corners)
            self.window.blit(glow_surf, glow_rect.topleft)

        pygame.draw.polygon(self.window, fill, corners)

        if tile.owner:
            self._draw_surface_skin(tile, corners, scx, scy, sz)

        # Border
        if tile.owner:
            self._draw_owner_border(tile, corners)
            if tile is self.selected_tile:
                pygame.draw.polygon(self.window, settings.HEX_SELECT_BORDER, corners,
                                    max(1, int((self._border_w + 1) * self.zoom)))
        else:
            border_clr = _tile_border_color(tile)
            bw = self._border_w
            pygame.draw.polygon(self.window, border_clr, corners,
                                max(1, int(bw * self.zoom / 1.0)))
            if tile is self.selected_tile:
                pygame.draw.polygon(self.window, settings.HEX_SELECT_BORDER, corners,
                                    max(1, int((self._border_w + 1) * self.zoom)))

        show_land_info = self._should_draw_land_info(sz)

        # Gold-rate and suit-bonus icon size scales with zoom.
        icon_sz = int(settings.HEX_ICON_SIZE * self.zoom)

        # Tier stars (top of hex), drawn as vector shapes to avoid missing glyphs.
        if show_land_info:
            self._draw_tier_stars(scx, scy - sz * 0.47, tile.tier, sz)

        # Gold rate (centre-left with icon)
        if show_land_info and icon_sz > 6 and self._gold_icon_raw:
            gold_icon = self._get_scaled_icon('gold', self._gold_icon_raw, icon_sz)
            gold_text = self._label_font.render(f'{tile.gold_rate:.0f}', True, (250, 221, 0))
            total_w = icon_sz + 2 + gold_text.get_width()
            start_x = scx - total_w // 2
            self.window.blit(gold_icon, (start_x, scy - icon_sz // 2))
            self.window.blit(gold_text, (start_x + icon_sz + 2,
                                         scy - gold_text.get_height() // 2))

        # Suit bonus (bottom, with suit icon)
        suit_icon = self._suit_icon_raw.get(tile.suit_bonus_suit)
        if show_land_info and icon_sz > 6 and suit_icon:
            s_icon = self._get_scaled_icon(tile.suit_bonus_suit, suit_icon, icon_sz)
            bonus_text = self._label_font.render(f'+{tile.suit_bonus_value}', True, (220, 210, 195))
            total_w = icon_sz + 2 + bonus_text.get_width()
            start_x = scx - total_w // 2
            iy = scy + sz * 0.15
            self.window.blit(s_icon, (start_x, iy))
            self.window.blit(bonus_text, (start_x + icon_sz + 2,
                                          iy + (icon_sz - bonus_text.get_height()) // 2))

        # Owner name (bottom of hex).  Own lands use the clearer YOURS badge below.
        if tile.owner_username and not tile.is_mine and sz > 30:
            name_surf = self._label_font.render(tile.owner_username, True, (200, 200, 200))
            name_rect = name_surf.get_rect(centerx=scx, bottom=scy + sz * 0.75)
            self.window.blit(name_surf, name_rect)

        if tile.owner and sz > 24:
            self._draw_owner_flag(tile, scx, scy, sz)

        # Broken icon for incomplete defence (only on player's own tiles)
        if tile.defence_incomplete and self._broken_icon_raw and icon_sz > 6:
            broken_sz = int(icon_sz * 2)
            b_icon = pygame.transform.smoothscale(
                self._broken_icon_raw, (broken_sz, broken_sz))
            bx = int(scx + sz * 0.20)
            by = int(scy - sz * 0.65)
            self.window.blit(b_icon, (bx, by))

        if tile.kingdom_is_shielded and sz > 24:
            self._draw_shield_badge(tile, scx, scy, sz)

    def _kingdom_badges(self):
        """Return grouped badge descriptors for all visible owned kingdoms."""
        groups = {}
        for tile in self.tiles:
            if not tile.owner_user_id:
                continue

            if tile.kingdom_id is not None:
                group_key = ('kingdom', tile.kingdom_id)
            elif tile.kingdom_component_id is not None:
                group_key = ('component', tile.owner_user_id, tile.kingdom_component_id)
            else:
                # No persistent kingdom/component information available.
                # Keep per-tile owner labels as the fallback in this case.
                continue

            group = groups.setdefault(group_key, {
                'tiles': [],
                'name': None,
                'kingdom_id': tile.kingdom_id,
                'owner_username': tile.owner_username,
            })
            group['tiles'].append(tile)
            if not group['name']:
                name = str(tile.kingdom_name or '').strip()
                if name:
                    group['name'] = name

        badges = []
        for group in groups.values():
            tiles = group['tiles']
            if not tiles:
                continue
            center_x = sum(tile.cx for tile in tiles) / len(tiles)
            center_y = sum(tile.cy for tile in tiles) / len(tiles)
            name = group['name']
            if not name:
                if group['kingdom_id'] is not None:
                    name = f'Kingdom #{group["kingdom_id"]}'
                elif group.get('owner_username'):
                    name = str(group['owner_username'])
                else:
                    name = 'Kingdom'
            badges.append({
                'name': name,
                'center_x': center_x,
                'center_y': center_y,
                'tile_count': len(tiles),
            })
        return badges

    def _draw_kingdom_badges(self, sz):
        """Draw one centered badge per owned kingdom/component."""
        if sz <= 26:
            return

        vp = self.viewport_rect
        pad_x = max(3, int(4 * self.zoom))
        pad_y = max(1, int(2 * self.zoom))
        font = self._label_font

        for badge_data in self._kingdom_badges():
            scx, scy = self.world_to_screen(
                badge_data['center_x'],
                badge_data['center_y'],
            )
            # Keep badge rendering scoped to visible map area.
            if scx < vp.left - 80 or scx > vp.right + 80:
                continue
            if scy < vp.top - 30 or scy > vp.bottom + 30:
                continue

            badge = font.render(
                str(badge_data['name']),
                True,
                settings.HEX_MINE_BADGE_CLR,
            )
            br = badge.get_rect(center=(scx, scy))
            bg = pygame.Rect(
                br.x - pad_x,
                br.y - pad_y,
                br.w + pad_x * 2,
                br.h + pad_y * 2,
            )
            pygame.draw.rect(
                self.window,
                settings.HEX_MINE_BADGE_BG,
                bg,
                border_radius=max(2, int(3 * self.zoom)),
            )
            pygame.draw.rect(
                self.window,
                settings.HEX_MINE_BORDER,
                bg,
                1,
                border_radius=max(2, int(3 * self.zoom)),
            )
            self.window.blit(badge, br)

    def _format_countdown(self, seconds):
        if int(seconds or 0) < 0:
            return 'Core'
        seconds = max(0, int(seconds or 0))
        if seconds >= 3600:
            return f'{seconds // 3600}h'
        if seconds >= 60:
            return f'{seconds // 60}m'
        return f'{seconds}s'

    def _draw_shield_badge(self, tile, scx, scy, sz):
        icon_sz = max(10, int(sz * 0.25))
        x = int(scx - sz * 0.58)
        y = int(scy - sz * 0.58)
        bg = pygame.Rect(x - 2, y - 2, int(icon_sz * 2.2), icon_sz + 4)
        pygame.draw.rect(self.window, (24, 38, 70, 210), bg,
                         border_radius=max(2, int(3 * self.zoom)))
        pygame.draw.rect(self.window, (140, 190, 255), bg, 1,
                         border_radius=max(2, int(3 * self.zoom)))
        if self._shield_icon_raw:
            icon = pygame.transform.smoothscale(self._shield_icon_raw, (icon_sz, icon_sz))
            self.window.blit(icon, (x, y))
        else:
            pygame.draw.polygon(self.window, (140, 190, 255), [
                (x + icon_sz // 2, y), (x + icon_sz, y + icon_sz // 3),
                (x + icon_sz // 2, y + icon_sz), (x, y + icon_sz // 3),
            ])
        txt = self._label_font.render(self._format_countdown(tile.kingdom_shield_remaining),
                                      True, (220, 235, 255))
        self.window.blit(txt, (x + icon_sz + 3, y + max(0, (icon_sz - txt.get_height()) // 2)))

    def _draw_surface_skin(self, tile, corners, scx, scy, sz):
        """Draw a subtle cosmetic surface overlay for owned lands."""
        key = self._owner_style_key(tile, 'surface_key')
        skin = settings.HEX_SURFACE_SKINS.get(
            key, settings.HEX_SURFACE_SKINS.get('surface_plain', {}))
        overlay = skin.get('overlay')
        pattern = skin.get('pattern')
        if not overlay and not pattern:
            return

        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        rect = pygame.Rect(int(min(xs)), int(min(ys)),
                           max(1, int(max(xs) - min(xs)) + 1),
                           max(1, int(max(ys) - min(ys)) + 1))
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        local = [(x - rect.x, y - rect.y) for x, y in corners]
        if overlay:
            pygame.draw.polygon(surf, overlay, local)

        pattern_clr = skin.get('pattern_clr', (0, 0, 0, 36))
        if pattern == 'speckles':
            seed = (tile.land_id or 0) * 17
            for i in range(8):
                px = int((seed + i * 19) % max(1, rect.w))
                py = int((seed // 2 + i * 23) % max(1, rect.h))
                pygame.draw.circle(surf, pattern_clr, (px, py), 1)
        elif pattern == 'stone_lines':
            for i in range(3):
                x1 = int(rect.w * (0.20 + i * 0.18))
                y1 = int(rect.h * (0.28 + (i % 2) * 0.18))
                x2 = int(rect.w * (0.48 + i * 0.13))
                y2 = int(rect.h * (0.36 + (i % 2) * 0.22))
                pygame.draw.line(surf, pattern_clr, (x1, y1), (x2, y2), 1)

        self.window.blit(surf, rect.topleft)

    def _draw_owner_border(self, tile, corners):
        """Draw cosmetic kingdom outline on only external component edges."""
        key = self._owner_style_key(tile, 'border_key')
        skin = settings.HEX_BORDER_SKINS.get(
            key, settings.HEX_BORDER_SKINS.get('border_simple_gold', {}))
        width_bonus = int(skin.get('width_bonus', 0) or 0)
        outer_w = max(1, int((self._border_w + 4 + width_bonus) * self.zoom / 1.0))
        main_w = max(1, int((self._border_w + 2 + width_bonus) * self.zoom / 1.0))
        inner_w = max(1, int(self._border_w * self.zoom / 1.0))
        edge_neighbours = _edge_neighbour_coords(tile.col, tile.row)
        for edge_idx, coord in enumerate(edge_neighbours):
            if self._same_owner_neighbour(tile, coord):
                continue
            start = corners[edge_idx]
            end = corners[(edge_idx + 1) % len(corners)]
            pygame.draw.line(self.window, skin.get('outer', settings.HEX_MINE_BORDER_OUTER),
                             start, end, outer_w)
            pygame.draw.line(self.window, skin.get('main', settings.HEX_MINE_BORDER),
                             start, end, main_w)
            pygame.draw.line(self.window,
                             skin.get('highlight', settings.HEX_MINE_BORDER_HIGHLIGHT),
                             start, end, inner_w)

    def _draw_owner_flag(self, tile, scx, scy, sz):
        """Draw the owner's equipped flag/badge cosmetic."""
        key = self._owner_style_key(tile, 'flag_key')
        style = settings.HEX_FLAG_STYLES.get(
            key, settings.HEX_FLAG_STYLES.get('flag_plain', {}))
        pole_h = max(8, int(sz * 0.34))
        flag_w = max(8, int(sz * 0.26))
        flag_h = max(6, int(sz * 0.17))
        pole_x = int(scx + sz * 0.35)
        pole_y = int(scy - sz * 0.42)
        pole_clr = style.get('pole', (150, 120, 72))
        fill = style.get('fill', (230, 214, 158))
        accent = style.get('accent', (116, 86, 46))
        pygame.draw.line(self.window, pole_clr, (pole_x, pole_y),
                         (pole_x, pole_y + pole_h), max(1, int(2 * self.zoom)))

        shape = style.get('shape')
        if shape == 'banner':
            flag = pygame.Rect(pole_x, pole_y, flag_w, flag_h)
            pygame.draw.rect(self.window, fill, flag, border_radius=max(1, int(2 * self.zoom)))
            pygame.draw.line(self.window, accent, flag.midleft, flag.midright, 1)
            pygame.draw.rect(self.window, accent, flag, 1, border_radius=max(1, int(2 * self.zoom)))
        elif shape == 'swallowtail':
            pts = [(pole_x, pole_y), (pole_x + flag_w, pole_y),
                   (pole_x + int(flag_w * 0.74), pole_y + flag_h // 2),
                   (pole_x + flag_w, pole_y + flag_h), (pole_x, pole_y + flag_h)]
            pygame.draw.polygon(self.window, fill, pts)
            pygame.draw.polygon(self.window, accent, pts, 1)
        else:
            pts = [(pole_x, pole_y), (pole_x + flag_w, pole_y + flag_h // 2),
                   (pole_x, pole_y + flag_h)]
            pygame.draw.polygon(self.window, fill, pts)
            pygame.draw.polygon(self.window, accent, pts, 1)

    def _draw_tier_stars(self, cx, cy, tier, sz):
        """Draw one star per tier level."""
        max_count = len(getattr(settings, 'TIER_LABELS', {1: '', 2: '', 3: ''})) or 4
        count = max(1, min(max_count, int(tier or 1)))
        outer = max(4, int(sz * 0.112))
        inner = max(2, int(outer * 0.50))
        gap = max(2, int(outer * 0.56))
        total_w = count * outer * 2 + (count - 1) * gap
        start_x = cx - total_w / 2 + outer
        outline_w = 2 if outer >= 7 else 1
        for i in range(count):
            sx = start_x + i * (outer * 2 + gap)
            shadow = _star_points(sx + 1, cy + 1, outer, inner)
            pts = _star_points(sx, cy, outer, inner)
            pygame.draw.polygon(self.window, (36, 24, 8), shadow)
            pygame.draw.polygon(self.window, settings.HEX_STAR_FILL, pts)
            pygame.draw.polygon(self.window, settings.HEX_STAR_BORDER, pts, outline_w)

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
            clr = _tile_fill_color(tile)
            border = _tile_border_color(tile)
            if tile.is_mine:
                pygame.draw.circle(mm_surf, settings.HEX_MINE_BORDER,
                                   (int(tx), int(ty)), dot_r + 2)
                border = (255, 245, 190)
            pygame.draw.circle(mm_surf, clr, (int(tx), int(ty)), dot_r)
            pygame.draw.circle(mm_surf, border, (int(tx), int(ty)), dot_r, 1)

        # Draw viewport rectangle
        vp_left = off_x + (self.camera_x - min_wx) * scale
        vp_top = off_y + (self.camera_y - min_wy) * scale
        vp_w = self.viewport_rect.w / self.zoom * scale
        vp_h = self.viewport_rect.h / self.zoom * scale
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

    def focus_land(self, land_id):
        """Select and centre the map on a land id. Returns the tile if found."""
        for tile in self.tiles:
            if tile.land_id == land_id:
                self.selected_tile = tile
                self.camera_x = tile.cx - self.viewport_rect.w / (2 * self.zoom)
                self.camera_y = tile.cy - self.viewport_rect.h / (2 * self.zoom)
                self._clamp_camera()
                return tile
        return None

    def focus_lands(self, land_ids):
        """Centre the camera on a set of land IDs. Returns selected tile or None."""
        if not land_ids:
            return None

        wanted = {land_id for land_id in land_ids if land_id is not None}
        if not wanted:
            return None

        targets = [tile for tile in self.tiles if tile.land_id in wanted]
        if not targets:
            return None

        center_x = sum(tile.cx for tile in targets) / len(targets)
        center_y = sum(tile.cy for tile in targets) / len(targets)
        self.camera_x = center_x - self.viewport_rect.w / (2 * self.zoom)
        self.camera_y = center_y - self.viewport_rect.h / (2 * self.zoom)
        self._clamp_camera()

        selected = min(
            targets,
            key=lambda tile: (
                (tile.cx - center_x) ** 2 + (tile.cy - center_y) ** 2,
                tile.land_id,
            ),
        )
        self.selected_tile = selected
        return selected

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
        self.camera_x = wx - self.viewport_rect.w / (2 * self.zoom)
        self.camera_y = wy - self.viewport_rect.h / (2 * self.zoom)
        self._clamp_camera()
        return True

    def update_data(self, lands_data):
        """Refresh tile data (e.g. after ownership change) without resetting camera."""
        old_cam = (self.camera_x, self.camera_y, self.zoom)
        self._build_tiles(lands_data)
        self.camera_x, self.camera_y, self.zoom = old_cam
        self.selected_tile = None
        self.hovered_tile = None
