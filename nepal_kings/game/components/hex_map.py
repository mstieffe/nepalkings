# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Hex-grid map renderer for the Kingdom screen."""

import math
import os
from collections import deque

import pygame
from config import settings
from game.components import hex_cosmetics, badge_cosmetics, sigil_cosmetics
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


def _scale_alpha(clr, factor):
    """Return ``clr`` with its alpha component scaled by ``factor`` (0..1+)."""
    if len(clr) < 4:
        return clr
    a = max(0, min(255, int(clr[3] * factor)))
    return (clr[0], clr[1], clr[2], a)


def _blend_rgb(base, tint, weight):
    """Blend two RGB colours without changing the caller's alpha model."""
    weight = max(0.0, min(1.0, float(weight)))
    return tuple(int(round(base[i] * (1.0 - weight) + tint[i] * weight))
                 for i in range(3))


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


def _draw_capped_line(surface, color, start, end, width):
    """Draw a thick anti-aliased line with round caps.

    The border skins are drawn after all hex fills, so this helper favours
    smooth local supersampling over raw ``pygame.draw.line``.  It avoids the
    jagged stair-steps that are especially visible on diagonal hex edges.
    """
    width = max(1, int(width or 1))
    scale = 2
    pad = width + 3
    min_x = int(math.floor(min(start[0], end[0]) - pad))
    min_y = int(math.floor(min(start[1], end[1]) - pad))
    max_x = int(math.ceil(max(start[0], end[0]) + pad))
    max_y = int(math.ceil(max(start[1], end[1]) + pad))
    surf_w = max(1, max_x - min_x)
    surf_h = max(1, max_y - min_y)
    line_surf = pygame.Surface((surf_w * scale, surf_h * scale), pygame.SRCALPHA)
    local_start = (
        int(round((start[0] - min_x) * scale)),
        int(round((start[1] - min_y) * scale)),
    )
    local_end = (
        int(round((end[0] - min_x) * scale)),
        int(round((end[1] - min_y) * scale)),
    )
    scaled_w = max(1, width * scale)
    pygame.draw.line(line_surf, color, local_start, local_end, scaled_w)
    radius = max(1, scaled_w // 2)
    pygame.draw.circle(line_surf, color, local_start, radius)
    pygame.draw.circle(line_surf, color, local_end, radius)
    if scale > 1:
        line_surf = pygame.transform.smoothscale(line_surf, (surf_w, surf_h))
    surface.blit(line_surf, (min_x, min_y))


def _clip_line_to_convex_polygon(pts, p1, p2):
    """Cyrus-Beck parametric clip of segment p1→p2 to a convex polygon.

    Works for any winding order: each edge's inward normal is oriented toward
    the polygon centroid.  Returns (q1, q2) or None if fully outside.
    """
    n = len(pts)
    if n < 3:
        return None
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    t_enter, t_exit = 0.0, 1.0
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        # Left-hand perpendicular; flip if it points away from centroid.
        nx, ny = -ey, ex
        if nx * (cx - ax) + ny * (cy - ay) < 0:
            nx, ny = -nx, -ny
        numer = nx * (p1[0] - ax) + ny * (p1[1] - ay)
        denom = nx * dx + ny * dy
        if abs(denom) < 1e-10:
            if numer < 0:
                return None
        elif denom > 0:            # entering the half-plane
            t = -numer / denom
            if t > t_enter:
                t_enter = t
        else:                      # exiting the half-plane
            t = -numer / denom
            if t < t_exit:
                t_exit = t
        if t_enter >= t_exit:
            return None
    if t_enter >= t_exit:
        return None
    return (
        (p1[0] + t_enter * dx, p1[1] + t_enter * dy),
        (p1[0] + t_exit  * dx, p1[1] + t_exit  * dy),
    )


def _draw_surface_pattern(*_args, **_kwargs):
    """Deprecated stub kept only as a monkey-patch hook for legacy tests.

    Real cosmetic surface art is generated by ``hex_cosmetics.render_surface_art``.
    """
    return None


def draw_border_edge(window, style, start, end, palette,
                     outer_w, main_w, inner_w):
    """Render one hex edge in the requested cosmetic border style.

    Module-level so non-map surfaces (e.g. the kingdom-config style
    showcase) can render true border art without a HexMap instance.
    """
    outer_clr, main_clr, highlight_clr = palette
    if style == 'simple':
        _draw_capped_line(window, outer_clr, start, end, outer_w)
        _draw_capped_line(window, main_clr, start, end, main_w)
        _draw_capped_line(window, highlight_clr, start, end, inner_w)
        return

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 0:
        _draw_capped_line(window, main_clr, start, end, main_w)
        return
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux  # left-perpendicular unit vector

    def at(t, off=0.0):
        return (start[0] + dx * t + nx * off,
                start[1] + dy * t + ny * off)

    if style == 'rope_braid':
        offset = main_w * 0.55
        strand_w = max(1, int(main_w * 0.55))
        outer_strand_w = max(1, int(outer_w * 0.55))
        tick_w = max(1, int(inner_w * 0.85))
        # Outer dark wash beneath the two strands.
        _draw_capped_line(window, outer_clr,
                          at(0, -offset), at(1, -offset), outer_strand_w)
        _draw_capped_line(window, outer_clr,
                          at(0, offset), at(1, offset), outer_strand_w)
        _draw_capped_line(window, main_clr,
                          at(0, -offset), at(1, -offset), strand_w)
        _draw_capped_line(window, main_clr,
                          at(0, offset), at(1, offset), strand_w)
        # 5 alternating diagonal ticks simulating the braid.
        ticks = 5
        for i in range(ticks):
            t1 = (i + 0.15) / ticks
            t2 = (i + 0.85) / ticks
            if i % 2 == 0:
                a, b = at(t1, -offset), at(t2, offset)
            else:
                a, b = at(t1, offset), at(t2, -offset)
            _draw_capped_line(window, highlight_clr, a, b, tick_w)
        return

    if style == 'dashed_double':
        offset = main_w * 0.55
        dash_w = max(1, int(main_w * 0.55))
        outer_dash_w = max(1, int(outer_w * 0.55))
        dashes = 6
        for i in range(dashes):
            t1 = (i + 0.05) / dashes
            t2 = (i + 0.65) / dashes
            _draw_capped_line(window, outer_clr,
                              at(t1, -offset), at(t2, -offset), outer_dash_w)
            _draw_capped_line(window, outer_clr,
                              at(t1, offset), at(t2, offset), outer_dash_w)
            _draw_capped_line(window, main_clr,
                              at(t1, -offset), at(t2, -offset), dash_w)
            _draw_capped_line(window, main_clr,
                              at(t1, offset), at(t2, offset), dash_w)
        return

    if style == 'carved_notches':
        # Single thick line interrupted by inward notches.
        _draw_capped_line(window, outer_clr, start, end, outer_w)
        _draw_capped_line(window, main_clr, start, end, main_w)
        notch_depth = main_w * 0.55
        notch_w = max(1, int(main_w * 0.40))
        for t in (0.18, 0.36, 0.54, 0.72, 0.90):
            p1 = at(t)
            p2 = at(t, notch_depth)
            _draw_capped_line(window, outer_clr, p1, p2, notch_w)
        _draw_capped_line(window, highlight_clr,
                          at(0, -inner_w * 0.30),
                          at(1, -inner_w * 0.30), max(1, inner_w))
        return

    if style == 'spikes':
        # Zig-zag main line: alternates above/below the edge axis.
        steps = 8
        amp = main_w * 0.65
        polyline = [start]
        for i in range(1, steps):
            t = i / steps
            off = amp if i % 2 == 1 else -amp
            polyline.append(at(t, off))
        polyline.append(end)
        for i in range(len(polyline) - 1):
            _draw_capped_line(window, outer_clr,
                              polyline[i], polyline[i + 1], outer_w)
        for i in range(len(polyline) - 1):
            _draw_capped_line(window, main_clr,
                              polyline[i], polyline[i + 1], main_w)
        for i in range(len(polyline) - 1):
            _draw_capped_line(window, highlight_clr,
                              polyline[i], polyline[i + 1], inner_w)
        return

    if style == 'gem_cabochons':
        # Thick metal bar with a single inset cabochon per edge.  One
        # small deep-toned gem reads as jewellery; chains of large ones
        # read as a candy necklace around the kingdom.
        _draw_capped_line(window, outer_clr, start, end, outer_w)
        _draw_capped_line(window, main_clr, start, end, main_w)
        _draw_capped_line(window, highlight_clr,
                          at(0, -main_w * 0.30),
                          at(1, -main_w * 0.30), max(1, inner_w))
        gem_r = max(2, int(main_w * 0.55))
        rim_clr = (max(0, outer_clr[0] - 30), max(0, outer_clr[1] - 30),
                   max(0, outer_clr[2] - 30))
        cx, cy = at(0.5)
        pygame.draw.circle(window, rim_clr,
                           (int(round(cx)), int(round(cy))), gem_r + 2)
        pygame.draw.circle(window, outer_clr,
                           (int(round(cx)), int(round(cy))), gem_r + 1)
        pygame.draw.circle(window, main_clr,
                           (int(round(cx)), int(round(cy))), gem_r)
        hx = cx + nx * gem_r * 0.30 - ux * gem_r * 0.15
        hy = cy + ny * gem_r * 0.30 - uy * gem_r * 0.15
        pygame.draw.circle(window, highlight_clr,
                           (int(round(hx)), int(round(hy))),
                           max(1, gem_r // 3))
        return

    if style == 'thorned_vine':
        _draw_capped_line(window, outer_clr, start, end, outer_w)
        _draw_capped_line(window, main_clr, start, end, main_w)
        thorn_h = main_w * 1.2
        thorn_half = main_w * 0.35
        for t in (0.18, 0.36, 0.54, 0.72, 0.90):
            base_pt = at(t)
            left = at(t - 0.04)
            right = at(t + 0.04)
            tip = at(t, -thorn_h)
            pygame.draw.polygon(window, outer_clr, [
                (int(round(left[0])), int(round(left[1]))),
                (int(round(right[0])), int(round(right[1]))),
                (int(round(tip[0])), int(round(tip[1]))),
            ])
            # Thin inner highlight on the thorn.
            pygame.draw.line(window, highlight_clr,
                             (int(round(base_pt[0])), int(round(base_pt[1]))),
                             (int(round(tip[0])), int(round(tip[1]))),
                             max(1, int(thorn_half)))
        return

    if style == 'bamboo_stalks':
        # Segmented cane: solid stalk interrupted by node joints.
        _draw_capped_line(window, outer_clr, start, end, outer_w)
        _draw_capped_line(window, main_clr, start, end, main_w)
        node_w = max(1, int(main_w * 0.7))
        node_half = main_w * 0.85
        for t in (0.25, 0.50, 0.75):
            _draw_capped_line(window, outer_clr,
                              at(t, -node_half), at(t, node_half), node_w)
            _draw_capped_line(window, highlight_clr,
                              at(t + 0.02, -node_half * 0.55),
                              at(t + 0.02, node_half * 0.55),
                              max(1, node_w // 2))
        # Sunlit sheen along one side of the cane.
        _draw_capped_line(window, highlight_clr,
                          at(0.06, -main_w * 0.28),
                          at(0.94, -main_w * 0.28), max(1, inner_w))
        return

    if style == 'prayer_flags':
        # Rope with five traditional flags (blue, white, red, green,
        # yellow) hanging toward the hex interior.
        rope_outer = max(1, int(outer_w * 0.55))
        rope_main = max(1, int(main_w * 0.55))
        _draw_capped_line(window, outer_clr, start, end, rope_outer)
        _draw_capped_line(window, main_clr, start, end, rope_main)
        flag_clrs = ((64, 118, 214), (238, 238, 232), (204, 58, 52),
                     (58, 158, 92), (236, 196, 66))
        flag_len = max(3.0, main_w * 1.6)
        for i, clr in enumerate(flag_clrs):
            t0 = (i + 0.5) / len(flag_clrs)
            base_a = at(t0 - 0.055)
            base_b = at(t0 + 0.055)
            tip = at(t0, flag_len)
            pygame.draw.polygon(window, clr, [base_a, base_b, tip])
            pygame.draw.polygon(window, outer_clr, [base_a, base_b, tip], 1)
        return

    # Unknown style → simple fallback.
    _draw_capped_line(window, outer_clr, start, end, outer_w)
    _draw_capped_line(window, main_clr, start, end, main_w)
    _draw_capped_line(window, highlight_clr, start, end, inner_w)


# ═══════════════════════════════════════════════════════════════════
#  HexTile — data object for a single hex
# ═══════════════════════════════════════════════════════════════════

class HexTile:
    """Lightweight data holder for a single hex on the map."""

    __slots__ = (
        'land_id', 'col', 'row', 'tier', 'gold_rate',
        'suit_bonus_suit', 'suit_bonus_value', 'region',
        'owner', 'owner_style', 'is_mine', 'defence_incomplete',
        'kingdom_component_id', 'kingdom_component_size', 'kingdom_level',
        'kingdom_tier_name', 'kingdom_bonuses', 'kingdom_name',
        'kingdom_id', 'kingdom_shield_remaining', 'kingdom_shield_reason',
        'kingdom_is_shielded',
        'is_recommended_tutorial_land',
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
        self.region = land_dict.get('region')
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
        self.is_recommended_tutorial_land = bool(
            land_dict.get('is_recommended_tutorial_land', False))
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

        # Map scan mode ('terrain' = the default rich view; other modes wash
        # each tile with a data-driven colour so the map is playful to scan).
        self.map_mode = 'terrain'
        self._gold_range = None

        # Build tiles
        self.tiles = []
        self._tile_by_coord = {}
        self._world_min_x = 0.0
        self._world_max_x = 0.0
        self._world_min_y = 0.0
        self._world_max_y = 0.0
        # Cosmetic caches that only depend on tile data (ownership / suit /
        # kingdom) — refreshed on _build_tiles / update_data, then reused
        # every frame.
        self._suit_clusters_cache = None
        self._kingdom_badges_cache = None
        self._minimap_static_cache_key = None
        self._minimap_static_cache = None
        self._minimap_data_version = 0
        self._regions_data = []
        self._regions_by_key = {}
        self._region_champion_users = set()
        self._region_geometry_cache = None
        self._terrain_landmarks_cache = None
        self._render_cache_key = None
        self._render_cache = None
        # Crown leaderboards (set via set_leaderboards from KingdomScreen).
        # Crown leaderboards: group_key -> rank (1/2/3) for the largest
        # single connected kingdom; user_id -> rank for the greatest total
        # realm.  Populated via ``set_leaderboards``; empty dicts by default
        # so the badge renderer's ``.get(...)`` calls are always safe.
        self._gold_crown_groups = {}
        self._silver_wreath_users = {}
        self._crown_icon_cache = {}
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
            # Hex map uses a richer shield art than the in-battle block
            # icon — load it directly so we keep the battle icon path
            # untouched for other consumers.
            hex_shield_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))),
                'img', 'kingdom', 'skill_icons', 'shield.png')
            self._shield_icon_raw = pygame.image.load(
                hex_shield_path).convert_alpha()
        except Exception:
            try:
                shield_path = os.path.join(settings.RESOURCE_BASE,
                                           settings.KINGDOM_SHIELD_ICON_PATH)
                self._shield_icon_raw = pygame.image.load(
                    shield_path).convert_alpha()
            except Exception:
                logger.warning('Could not load kingdom shield icon for hex map')

        # Fonts
        self._label_font = settings.get_font(settings.HEX_LABEL_FONT_SIZE)
        self._tier_font = settings.get_font(settings.HEX_LABEL_FONT_SIZE, bold=True)

        # A production-sized map opens as a true overview.  Tiny maps used by
        # tutorials/tests retain the familiar 1:1 zoom.
        if len(self.tiles) >= 1000:
            self._fit_overview_zoom()
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
        if len(self._scaled_icon_cache) > 96:
            try:
                self._scaled_icon_cache.pop(next(iter(self._scaled_icon_cache)))
            except Exception:
                self._scaled_icon_cache.clear()
        return scaled

    def _cached_text(self, text, font_px, color, *, bold=False):
        """Return a cached ``font.render`` result.

        Font rendering is one of pygame's most expensive primitives; the same
        text/colour/size combo is requested by ~100 tiles every frame
        (bonus numbers, owner names, shield countdowns), so a small dict cache
        eliminates almost all of the per-frame cost.
        """
        cache = getattr(self, '_text_cache', None)
        if cache is None:
            cache = self._text_cache = {}
        key = (text, int(font_px), bool(bold), tuple(color))
        surf = cache.get(key)
        if surf is None:
            font = settings.get_font(int(font_px), bold=bold)
            surf = font.render(text, True, color)
            # Bound the cache to avoid unbounded growth across zoom levels.
            if len(cache) > 256:
                cache.pop(next(iter(cache)))
            cache[key] = surf
        return surf

    def _owner_style_key(self, tile, field_name):
        style = getattr(tile, 'owner_style', None) or {}
        default_style = getattr(settings, 'HEX_DEFAULT_OWNER_STYLE', {})
        return style.get(field_name) or default_style.get(field_name)

    def _same_owner_neighbour(self, tile, coord):
        neighbour = self._tile_by_coord.get(coord)
        return bool(neighbour and tile.owner_user_id and
                    neighbour.owner_user_id == tile.owner_user_id)

    def _tile_in_hovered_component(self, tile):
        """True if *tile* shares the hovered tile's connected kingdom component."""
        h = self.hovered_tile
        if h is None or tile is h:
            return False
        h_comp = getattr(h, 'kingdom_component_id', None)
        if h_comp is None:
            return False
        if getattr(tile, 'kingdom_component_id', None) != h_comp:
            return False
        return getattr(tile, 'owner_user_id', None) == getattr(h, 'owner_user_id', None)

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
        self._precompute_conquest_outcomes()
        # Data changed — drop derived caches.
        self._suit_clusters_cache = None
        self._kingdom_badges_cache = None
        self._minimap_static_cache_key = None
        self._minimap_static_cache = None
        self._minimap_data_version = getattr(self, '_minimap_data_version', 0) + 1
        self._region_geometry_cache = None
        self._terrain_landmarks_cache = None
        self._render_cache_key = None
        self._render_cache = None

    def _precompute_conquest_outcomes(self):
        """Pre-compute whether each non-player tile would expand an existing kingdom
        or start a new isolated one.  Stored as {land_id: 'expand' | 'new'}."""
        my_coords = frozenset(
            (t.col, t.row) for t in self.tiles if t.is_mine
        )
        outcomes = {}
        if my_coords:
            for tile in self.tiles:
                if tile.is_mine:
                    continue
                neighbours = _edge_neighbour_coords(tile.col, tile.row)
                outcomes[tile.land_id] = (
                    'expand' if any(n in my_coords for n in neighbours) else 'new'
                )
        self._conquest_outcomes = outcomes
        self._conquest_ovl_cache = {}
        # Cache the player's surface skin key so the hover preview can use it.
        self._player_surface_key = None
        for t in self.tiles:
            if t.is_mine:
                self._player_surface_key = self._owner_style_key(t, 'surface_key')
                break

    def conquest_outcome_for(self, tile):
        """Return 'expand', 'new', or None for a non-player tile."""
        if tile.is_mine:
            return None
        return getattr(self, '_conquest_outcomes', {}).get(tile.land_id)

    def _get_conquest_overlay(self, sz, inner_sz, outcome):
        """Return a cached hex-shaped alpha surface for conquest outcome overlays.

        Both outcomes use mathematically clipped hatch lines so pixels between
        the lines are guaranteed fully transparent — the tile's own colour is
        completely unaffected outside the line strokes.

        'new'    → grey  \\ lines (slope +1, 45°)
        'expand' → golden / lines (slope −1, 135°)
        """
        key = (int(sz), int(inner_sz), outcome)
        cache = getattr(self, '_conquest_ovl_cache', None)
        if cache is None:
            cache = {}
            self._conquest_ovl_cache = cache
        surf = cache.get(key)
        if surf is None:
            pad = 2
            w = int(sz * 2) + pad * 2
            h = int(sz * math.sqrt(3)) + pad * 2
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            lcx, lcy = w // 2, h // 2
            pts = _hex_corners(lcx, lcy, inner_sz)

            if outcome == 'new':
                gap = max(4, int(inner_sz * 0.28))
                lw  = max(1, int(inner_sz * 0.07))
                # Keep the strategic hint legible at detail zoom without
                # turning the whole mid-zoom map into a field of stripes.
                clr = (120, 120, 120, 110)
                # Lines y = x + c  (slope +1, \\ direction)
                for c in range(-w, h + gap, gap):
                    seg = _clip_line_to_convex_polygon(
                        pts, (0.0, float(c)), (float(w), float(c + w)))
                    if seg:
                        pygame.draw.line(surf, clr,
                            (int(round(seg[0][0])), int(round(seg[0][1]))),
                            (int(round(seg[1][0])), int(round(seg[1][1]))), lw)
            else:  # 'expand'
                gap = max(4, int(inner_sz * 0.28))
                lw  = max(1, int(inner_sz * 0.07))
                clr = (210, 165, 45, 115)
                # Lines y = -x + c  (slope −1, / direction)
                for c in range(-gap, w + h + 2 * gap, gap):
                    seg = _clip_line_to_convex_polygon(
                        pts, (0.0, float(c)), (float(w), float(c - w)))
                    if seg:
                        pygame.draw.line(surf, clr,
                            (int(round(seg[0][0])), int(round(seg[0][1]))),
                            (int(round(seg[1][0])), int(round(seg[1][1]))), lw)

            cache[key] = surf
        return surf

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

    def _overview_fit_zoom(self, padding_px=None):
        """Return the closest zoom that still contains the complete world."""
        if not self.tiles:
            return settings.HEX_MAP_ZOOM_MIN
        padding = (padding_px if padding_px is not None else
                   max(8, int(0.025 * min(
                       self.viewport_rect.w, self.viewport_rect.h))))
        world_w = max(1.0, self._world_max_x - self._world_min_x)
        world_h = max(1.0, self._world_max_y - self._world_min_y)
        usable_w = max(1.0, self.viewport_rect.w - padding * 2)
        usable_h = max(1.0, self.viewport_rect.h - padding * 2)
        return max(
            settings.HEX_MAP_ZOOM_MIN,
            min(settings.HEX_MAP_ZOOM_MAX,
                min(usable_w / world_w, usable_h / world_h)),
        )

    def _minimum_zoom(self):
        """Avoid postage-stamp zoom on production-sized kingdom maps."""
        if len(self.tiles) >= 1000:
            return self._overview_fit_zoom()
        return settings.HEX_MAP_ZOOM_MIN

    def _fit_overview_zoom(self, padding_px=None):
        """Fit the complete world into the current viewport."""
        self.zoom = self._overview_fit_zoom(padding_px)
        return self.zoom

    def set_viewport(self, viewport_rect):
        """Resize the viewport while preserving its world-space centre."""
        old_center = (
            self.camera_x + self.viewport_rect.w / (2 * self.zoom),
            self.camera_y + self.viewport_rect.h / (2 * self.zoom),
        )
        self.viewport_rect = pygame.Rect(viewport_rect)
        self.zoom = max(self.zoom, self._minimum_zoom())
        self.camera_x = old_center[0] - self.viewport_rect.w / (2 * self.zoom)
        self.camera_y = old_center[1] - self.viewport_rect.h / (2 * self.zoom)
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

    def _zoom_at_screen_pos(self, sx, sy, zoom_steps):
        """Zoom proportionally while keeping the cursor's world point anchored."""
        old_zoom = self.zoom
        wx, wy = self.screen_to_world(sx, sy)
        factor = max(1.01, float(getattr(
            settings, 'HEX_MAP_ZOOM_FACTOR', 1.35)))
        target_zoom = old_zoom * (factor ** float(zoom_steps))
        self.zoom = max(
            self._minimum_zoom(),
            min(settings.HEX_MAP_ZOOM_MAX, target_zoom),
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

    def cancel_drag(self):
        """Clear any in-progress pan gesture without changing the camera."""
        self._dragging = False
        self._drag_start = None
        self._drag_cam_start = None
        self._did_drag = False

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
        # SDL exposes two-finger pinch as MULTIGESTURE on supported mobile
        # browsers. Mouse/touch emulation remains the fallback.
        multi_gesture = getattr(pygame, 'MULTIGESTURE', None)
        if multi_gesture is not None and event.type == multi_gesture:
            fingers = int(getattr(event, 'num_fingers', 0) or 0)
            pinch = float(getattr(event, 'pinched', 0.0) or 0.0)
            if fingers >= 2 and abs(pinch) > 0.0001:
                raw_x = getattr(event, 'x', 0.5)
                raw_y = getattr(event, 'y', 0.5)
                nx = max(0.0, min(1.0, float(
                    0.5 if raw_x is None else raw_x)))
                ny = max(0.0, min(1.0, float(
                    0.5 if raw_y is None else raw_y)))
                sx = self.viewport_rect.x + nx * self.viewport_rect.w
                sy = self.viewport_rect.y + ny * self.viewport_rect.h
                steps = max(-1.0, min(1.0, pinch * 12.0))
                self._zoom_at_screen_pos(sx, sy, steps)
            return None

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

        if (event.type == pygame.MOUSEWHEEL or
                (event.type == pygame.MOUSEBUTTONDOWN
                 and getattr(event, 'button', None) in (4, 5))):
            pos = getattr(event, 'pos', None) or pygame.mouse.get_pos()
            mx, my = pos
            if not self._in_viewport((mx, my)):
                return None

            if event.type == pygame.MOUSEWHEEL:
                wheel_y = getattr(event, 'precise_y', None)
                if wheel_y is None or wheel_y == 0:
                    wheel_y = getattr(event, 'y', 0)
                wheel_y = float(wheel_y or 0)
            elif event.button == 4:
                wheel_y = 1.0
            else:
                wheel_y = -1.0

            wheel_y = max(-1.0, min(1.0, wheel_y))
            if wheel_y:
                self._zoom_at_screen_pos(mx, my, wheel_y)
            return None

        return None

    # ── Zoom via navigation buttons ─────────────────────────────────

    def zoom_in(self):
        cx, cy = self.viewport_rect.center
        self._zoom_at_screen_pos(cx, cy, 1.0)

    def zoom_out(self):
        cx, cy = self.viewport_rect.center
        self._zoom_at_screen_pos(cx, cy, -1.0)

    def pan(self, dx_world, dy_world):
        self.camera_x += dx_world
        self.camera_y += dy_world
        self._clamp_camera()

    # ── Rendering ───────────────────────────────────────────────────

    def _owner_glow_pulse(self):
        """Return the current alpha-multiplier for the owner-glow breathing pulse.

        Quantized to ``HEX_MINE_GLOW_PULSE_STEPS`` so callers can rely on a
        small finite set of values per frame, enabling cheap caching.
        """
        period = max(1, int(getattr(settings, 'HEX_MINE_GLOW_PULSE_PERIOD_MS', 2400)))
        amp = float(getattr(settings, 'HEX_MINE_GLOW_PULSE_AMPLITUDE', 0.35))
        steps = max(2, int(getattr(settings, 'HEX_MINE_GLOW_PULSE_STEPS', 8)))
        t = (pygame.time.get_ticks() % period) / period  # 0..1
        # Cosine ease so the pulse breathes smoothly.
        wave = 0.5 - 0.5 * math.cos(2 * math.pi * t)     # 0..1
        # Quantize to ``steps`` discrete levels.
        wave = round(wave * (steps - 1)) / (steps - 1)
        return (1.0 - amp) + amp * wave

    # ── Historic-region presentation ────────────────────────────

    def set_regions(self, regions):
        """Attach the five read-only region snapshots returned by the API."""
        self._regions_data = [r for r in (regions or []) if isinstance(r, dict)]
        self._regions_by_key = {
            r.get('key'): r for r in self._regions_data if r.get('key')
        }
        self._region_champion_users = {
            champion.get('user_id')
            for region in self._regions_data
            for champion in (region.get('champions') or
                             ([region.get('champion')]
                              if region.get('champion') else []))
            if isinstance(champion, dict)
            and champion.get('user_id') is not None
        }
        self._region_geometry_cache = None
        self._terrain_landmarks_cache = None
        self._minimap_static_cache_key = None
        self._minimap_static_cache = None
        self._render_cache_key = None
        self._render_cache = None

    def focus_region(self, region_key):
        """Fit an entire historic region within the active viewport."""
        ids = [t.land_id for t in self.tiles if t.region == region_key]
        return self.focus_lands(ids, fit=True, max_zoom=1.15)

    def _region_presentation_factor(self):
        """Return overview presentation opacity for the current zoom."""
        if getattr(self, 'map_mode', 'terrain') != 'terrain':
            return 0.0
        full = float(getattr(settings, 'REGION_PRESENTATION_FULL_ZOOM', 0.90))
        end = float(getattr(settings, 'REGION_PRESENTATION_END_ZOOM', 1.35))
        if self.zoom <= full:
            return 1.0
        if self.zoom >= end:
            return 0.0
        return 1.0 - (self.zoom - full) / max(0.01, end - full)

    def _region_main_suit_factor(self):
        """Return opacity for the overview's one-suit-per-region marks."""
        start = float(getattr(
            settings, 'REGION_CLUSTER_ICON_START_ZOOM', 0.82))
        full = float(getattr(
            settings, 'REGION_CLUSTER_ICON_FULL_ZOOM', 1.00))
        if self.zoom <= start:
            return 1.0
        if self.zoom >= full:
            return 0.0
        return 1.0 - (self.zoom - start) / max(0.01, full - start)

    def _suit_cluster_icon_factor(self):
        """Return opacity for the intermediate one-icon-per-cluster view."""
        start = float(getattr(
            settings, 'REGION_CLUSTER_ICON_START_ZOOM', 0.82))
        full = float(getattr(
            settings, 'REGION_CLUSTER_ICON_FULL_ZOOM', 1.00))
        if self.zoom < start:
            return 0.0
        if self.zoom >= settings.HEX_MAP_LAND_NUMBERS_MIN_ZOOM:
            return 0.0
        return min(1.0, max(0.0, (self.zoom - start) /
                            max(0.01, full - start)))

    def _region_style(self, region_key):
        return (getattr(settings, 'KINGDOM_REGIONS', {}) or {}).get(
            region_key, {})

    def _draw_region_main_suit_icon(
            self, meta, style, label_rect, font_px, presentation_factor):
        """Draw a region's dominant suit icon directly below its name."""
        phase_factor = self._region_main_suit_factor()
        opacity = max(0.0, min(
            1.0, float(presentation_factor) * phase_factor))
        if opacity <= 0.0:
            return None

        if 'dominant_suit' in meta:
            suit = meta.get('dominant_suit')
        else:
            suit = style.get('dominant_suit')
        raw = self._suit_icon_raw.get(suit) if suit else None
        if raw is None:
            return None

        icon_sz = max(12, min(24, int(font_px * 0.95)))
        icon = self._get_scaled_icon(
            ('region-main-suit', suit), raw, icon_sz)
        if icon is None:
            return None

        icon = icon.copy()
        icon.set_alpha(max(1, int(225 * opacity)))

        gap = max(3, font_px // 5)
        icon_rect = icon.get_rect(
            midtop=(label_rect.centerx, label_rect.bottom + gap))
        self.window.blit(icon, icon_rect)
        return icon_rect

    def _region_geometry(self):
        """Cached centres/bounds used by labels and landmarks."""
        cached = self._region_geometry_cache
        if cached is not None:
            return cached
        grouped = {}
        for tile in self.tiles:
            if not tile.region:
                continue
            grouped.setdefault(tile.region, []).append(tile)
        result = {}
        for key, tiles in grouped.items():
            min_x = min(t.cx for t in tiles) - self._size
            max_x = max(t.cx for t in tiles) + self._size
            half_h = self._size * math.sqrt(3) / 2
            min_y = min(t.cy for t in tiles) - half_h
            max_y = max(t.cy for t in tiles) + half_h
            avg_x = sum(t.cx for t in tiles) / len(tiles)
            avg_y = sum(t.cy for t in tiles) / len(tiles)
            # Use an actual tile nearest the centroid so labels never land in
            # another organically perturbed region.
            anchor = min(
                tiles,
                key=lambda t: ((t.cx - avg_x) ** 2 + (t.cy - avg_y) ** 2,
                               t.land_id),
            )
            result[key] = {
                'tiles': tiles,
                'bounds': (min_x, min_y, max_x, max_y),
                'center': (anchor.cx, anchor.cy),
            }
        self._region_geometry_cache = result
        return result

    def _terrain_landmarks(self):
        """Return one scaled terrain mark per larger outer-region suit cluster.

        Kathmandu deliberately keeps its single valley mark at the historic
        region centre. Outer-region marks instead follow the actual suit
        geography, using a central member tile so symbols stay inside even
        irregularly shaped clusters.
        """
        if self._terrain_landmarks_cache is not None:
            return self._terrain_landmarks_cache
        landmarks = []
        min_tiles = max(2, int(getattr(
            settings, 'REGION_SCENERY_CLUSTER_MIN_TILES', 20)))
        reference_tiles = max(1.0, float(getattr(
            settings, 'REGION_SCENERY_CLUSTER_REFERENCE_TILES', 80)))
        min_scale = max(0.1, float(getattr(
            settings, 'REGION_SCENERY_CLUSTER_SCALE_MIN', 0.65)))
        max_scale = max(min_scale, float(getattr(
            settings, 'REGION_SCENERY_CLUSTER_SCALE_MAX', 1.45)))
        region_order = {
            key: idx for idx, key in enumerate(
                (getattr(settings, 'KINGDOM_REGIONS', {}) or {}).keys())
        }
        clusters = [
            cluster for cluster in self._suit_clusters()
            if cluster['suit'] != 'Neutral'
            and cluster.get('region')
            and cluster.get('region') != 'kathmandu'
            and cluster['suit'] == self._region_style(
                cluster['region']).get('dominant_suit')
            and cluster['tile_count'] >= min_tiles
        ]
        clusters.sort(key=lambda cluster: (
            region_order.get(cluster['region'], 99),
            cluster['anchor_y'],
            cluster['anchor_x'],
            cluster['suit'],
        ))
        for idx, cluster in enumerate(clusters):
            scale = math.sqrt(cluster['tile_count'] / reference_tiles)
            scale = max(min_scale, min(max_scale, scale))
            landmarks.append((
                cluster['region'],
                cluster['anchor_x'],
                cluster['anchor_y'],
                idx,
                scale,
            ))

        geometry = self._region_geometry()
        kathmandu = geometry.get('kathmandu')
        if kathmandu:
            cx, cy = kathmandu['center']
            landmarks.append(('kathmandu', cx, cy, 0, 1.0))
        self._terrain_landmarks_cache = landmarks
        return self._terrain_landmarks_cache

    def _draw_terrain_landmarks(self):
        factor = self._region_presentation_factor()
        if factor <= 0.0:
            return
        vp = self.viewport_rect
        layer = pygame.Surface(vp.size, pygame.SRCALPHA)
        alpha = int(getattr(settings, 'REGION_SCENERY_ALPHA', 52) * factor)
        if alpha <= 0:
            return
        base_unit = max(11, int(self._size * self.zoom * 3.7))

        def local(wx, wy):
            sx, sy = self.world_to_screen(wx, wy)
            return int(sx - vp.x), int(sy - vp.y)

        for key, wx, wy, variant, cluster_scale in self._terrain_landmarks():
            unit = max(7, int(base_unit * cluster_scale))
            x, y = local(wx, wy)
            if x < -unit * 3 or x > vp.w + unit * 3:
                continue
            if y < -unit * 2 or y > vp.h + unit * 2:
                continue
            style = self._region_style(key)
            tint = style.get('label', (230, 220, 195))
            line = (*tint, alpha)
            soft = (*tint, max(8, alpha // 2))
            terrain = style.get('terrain')
            if terrain in ('mountain', 'foothill'):
                peaks = []
                for j, scale in enumerate((0.72, 1.0, 0.62)):
                    px = x + int((j - 1) * unit * 0.82)
                    base_y = y + int(unit * 0.40)
                    peak_y = y - int(unit * scale)
                    pts = [(px - unit, base_y), (px, peak_y),
                           (px + unit, base_y)]
                    pygame.draw.polygon(layer, soft, pts)
                    pygame.draw.lines(layer, line, False, pts, max(1, unit // 12))
                    peaks.append((px, peak_y))
                if terrain == 'foothill':
                    for j in range(4):
                        tx = x + int((j - 1.5) * unit * 0.55)
                        ty = y + int(unit * (0.25 + (j % 2) * 0.20))
                        pygame.draw.polygon(
                            layer, line,
                            [(tx, ty - unit // 3),
                             (tx - unit // 4, ty + unit // 4),
                             (tx + unit // 4, ty + unit // 4)])
            elif terrain in ('forest', 'fields'):
                if terrain == 'forest':
                    for j in range(5):
                        cx = x + int((j - 2) * unit * 0.48)
                        cy = y + int((j % 2) * unit * 0.24)
                        pygame.draw.circle(layer, soft, (cx, cy),
                                           max(3, int(unit * 0.42)))
                        pygame.draw.circle(layer, line, (cx, cy),
                                           max(3, int(unit * 0.42)),
                                           max(1, unit // 14))
                else:
                    for j in range(-2, 3):
                        yy = y + int(j * unit * 0.25)
                        pygame.draw.arc(
                            layer, line,
                            pygame.Rect(x - unit * 2, yy - unit // 3,
                                        unit * 4, unit),
                            math.pi, math.pi * 2, max(1, unit // 14))
            elif terrain == 'valley':
                for j in range(3):
                    rect = pygame.Rect(
                        x - int(unit * (2.0 - j * 0.38)),
                        y - int(unit * (0.80 - j * 0.13)),
                        int(unit * (4.0 - j * 0.76)),
                        int(unit * (1.60 - j * 0.26)),
                    )
                    pygame.draw.ellipse(layer, soft if j == 0 else line,
                                        rect, max(1, unit // 16))
        self.window.blit(layer, vp.topleft)

    def _draw_region_boundaries(self, visible_hexes):
        if not visible_hexes:
            return
        analytical = getattr(self, 'map_mode', 'terrain') != 'terrain'
        clr = (getattr(settings, 'REGION_BOUNDARY_ANALYTIC_CLR',
                       (232, 222, 205, 42)) if analytical else
               getattr(settings, 'REGION_BOUNDARY_CLR',
                       (244, 225, 184, 80)))
        layer = pygame.Surface(self.viewport_rect.size, pygame.SRCALPHA)
        # A broad dark under-stroke separates similarly coloured terrain;
        # the warm inner stroke supplies the historic-region identity.  The
        # later ownership layers still sit above both strokes.
        width = max(2, min(6, int(self._size * self.zoom * 0.18)))
        shadow = getattr(
            settings, 'REGION_BOUNDARY_SHADOW_CLR', (42, 31, 20, 145))
        if analytical and len(shadow) >= 4:
            shadow = (*shadow[:3], max(30, int(shadow[3] * 0.48)))
        ox, oy = self.viewport_rect.topleft
        for tile, corners, _scx, _scy in visible_hexes:
            if not tile.region:
                continue
            for i, coord in enumerate(_edge_neighbour_coords(tile.col, tile.row)):
                neighbour = self._tile_by_coord.get(coord)
                if neighbour is None or neighbour.region == tile.region:
                    continue
                # Draw each shared edge once.
                if (tile.col, tile.row) > coord:
                    continue
                p0, p1 = corners[i], corners[(i + 1) % 6]
                start = (int(p0[0] - ox), int(p0[1] - oy))
                end = (int(p1[0] - ox), int(p1[1] - oy))
                pygame.draw.line(layer, shadow, start, end, width + 3)
                pygame.draw.line(layer, clr, start, end, width)
        self.window.blit(layer, self.viewport_rect.topleft)

    def _draw_region_labels(self):
        analytical = getattr(self, 'map_mode', 'terrain') != 'terrain'
        factor = 0.48 if analytical else self._region_presentation_factor()
        if factor <= 0.0:
            return
        geometry = self._region_geometry()
        order = list((getattr(settings, 'KINGDOM_REGIONS', {}) or {}).keys())
        for key in order:
            geo = geometry.get(key)
            if not geo:
                continue
            sx, sy = self.world_to_screen(*geo['center'])
            if not self.viewport_rect.inflate(160, 80).collidepoint(sx, sy):
                continue
            meta = self._regions_by_key.get(key, {})
            style = self._region_style(key)
            name = meta.get('name') or style.get('name') or key.title()
            font_px = max(
                16,
                min(28, int(self.viewport_rect.w * 0.016)),
                min(26, int(self._size * self.zoom * 0.92)),
            )
            color = style.get('label', (242, 228, 198))
            label = self._cached_text(name.upper(), font_px, color, bold=True).copy()
            label.set_alpha(max(45, int(235 * factor)))
            shadow = self._cached_text(
                name.upper(), font_px,
                getattr(settings, 'REGION_LABEL_SHADOW_CLR', (10, 8, 6, 185))[:3],
                bold=True).copy()
            shadow.set_alpha(max(35, int(185 * factor)))
            rect = label.get_rect(center=(int(sx), int(sy)))
            self.window.blit(shadow, rect.move(1, 2))
            self.window.blit(label, rect)
            self._draw_region_main_suit_icon(
                meta, style, rect, font_px, factor)
            if meta.get('champions') or meta.get('champion'):
                crown_w = max(8, int(font_px * 0.72))
                cx, cy = rect.centerx, rect.top - max(5, crown_w // 2)
                crown = [
                    (cx - crown_w, cy - crown_w // 3),
                    (cx - crown_w // 2, cy),
                    (cx, cy - crown_w // 2),
                    (cx + crown_w // 2, cy),
                    (cx + crown_w, cy - crown_w // 3),
                    (cx + int(crown_w * 0.72), cy + crown_w // 2),
                    (cx - int(crown_w * 0.72), cy + crown_w // 2),
                ]
                pygame.draw.polygon(self.window, (242, 205, 92), crown)

    def render(self):
        """Draw all visible hexes, labels, and minimap."""
        sz = self._size * self.zoom
        vp = self.viewport_rect

        has_mine = any(tile.is_mine for tile in self.tiles)
        # At full-map scale the glow is sub-pixel; keeping it static avoids
        # rebuilding the entire 4,800-tile overview for an invisible pulse.
        pulse_step = (round(self._owner_glow_pulse(), 3)
                      if has_mine and self.zoom >= 0.22 else None)
        warning_step = (
            pygame.time.get_ticks() // 250
            if (self.zoom >= settings.HEX_MAP_LAND_INFO_MIN_ZOOM
                and any(tile.defence_incomplete for tile in self.tiles))
            else None
        )
        cache_key = (
            vp.x, vp.y, vp.w, vp.h,
            round(self.camera_x, 3), round(self.camera_y, 3),
            round(self.zoom, 5), self.map_mode,
            getattr(self, '_minimap_data_version', 0),
            getattr(self.selected_tile, 'land_id', None),
            getattr(self.hovered_tile, 'land_id', None),
            tuple(getattr(self, 'minimap_origin', ()) or ()),
            pulse_step, warning_step,
        )
        cached_frame = getattr(self, '_render_cache', None)
        if (cached_frame is not None
                and cache_key == getattr(self, '_render_cache_key', None)
                and cached_frame.get_size() == vp.size):
            self.window.blit(cached_frame, vp.topleft)
            self._draw_recommended_tutorial_marker()
            return

        old_clip = self.window.get_clip()
        self.window.set_clip(vp)

        visible_hexes = []
        for tile in self.tiles:
            scx, scy = self.world_to_screen(tile.cx, tile.cy)

            # Frustum culling
            if scx < vp.left - sz * 2 or scx > vp.right + sz * 2:
                continue
            if scy < vp.top - sz * 2 or scy > vp.bottom + sz * 2:
                continue

            corners = _hex_corners(scx, scy, sz)
            visible_hexes.append((tile, corners, scx, scy))

        # Layered rendering fixes borders being overwritten by neighbouring
        # hex fills (most visible on lower/right edges with thick skins).
        for tile, corners, scx, scy in visible_hexes:
            self._draw_hex_base(tile, corners, scx, scy, sz)
        self._draw_terrain_landmarks()
        self._draw_region_boundaries(visible_hexes)
        # At overview zoom ordinary per-land borders and details are hidden.
        # Avoid thousands of no-op Python calls on the enlarged 4,800-land
        # map while preserving selection/tutorial/hover affordances.
        if self.zoom >= 0.22:
            for tile, corners, scx, scy in visible_hexes:
                self._draw_hex_border(tile, corners)
        else:
            for tile, corners, _scx, _scy in visible_hexes:
                if (tile is self.selected_tile or
                        getattr(tile, 'is_recommended_tutorial_land', False)):
                    self._draw_hex_border(tile, corners)
        self._draw_cluster_outlines(visible_hexes, sz)
        if self.zoom >= settings.HEX_MAP_LAND_INFO_MIN_ZOOM:
            for tile, _corners, scx, scy in visible_hexes:
                self._draw_hex_details(tile, scx, scy, sz)
        elif self.hovered_tile is not None:
            for tile, _corners, scx, scy in visible_hexes:
                if tile is self.hovered_tile:
                    self._draw_hex_details(tile, scx, scy, sz)
                    break

        # Suit cluster icons (drawn before kingdom badges so the kingdom
        # name pill always sits on top of the suit icon).
        self._draw_suit_cluster_icons(sz)
        self._draw_region_labels()
        self._draw_kingdom_badges(sz)

        self.window.set_clip(old_clip)

        self._draw_minimap()
        try:
            self._render_cache = self.window.subsurface(vp).copy()
            self._render_cache_key = cache_key
        except (ValueError, pygame.error):
            self._render_cache = None
            self._render_cache_key = None
        self._draw_recommended_tutorial_marker()

    def _draw_recommended_tutorial_marker(self):
        """Draw a high-contrast tap halo over the marked onboarding land.

        The production map can fit thousands of lands on screen, making the
        underlying hex only a few pixels wide.  This overlay stays at least as
        large as a mobile touch target and is drawn after the cached map frame
        so its gentle pulse remains animated without rebuilding every tile.
        """
        tile = next(
            (item for item in self.tiles
             if getattr(item, 'is_recommended_tutorial_land', False)),
            None,
        )
        if tile is None:
            return
        cx, cy = self.world_to_screen(tile.cx, tile.cy)
        if not self.viewport_rect.collidepoint(cx, cy):
            return
        sz = self._size * self.zoom
        touch_radius = (getattr(settings, 'TOUCH_TARGET_MIN', 0) or 0) / 2
        pulse = (pygame.time.get_ticks() % 900) / 900.0
        breathe = 0.5 + 0.5 * math.sin(pulse * math.tau)
        radius = int(max(sz * 1.22, touch_radius, 12) + breathe * 4)
        pad = 5
        diameter = (radius + pad) * 2
        halo = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        center = (diameter // 2, diameter // 2)
        pygame.draw.circle(halo, (255, 215, 52, 34), center, radius)
        pygame.draw.circle(halo, (255, 232, 104, 225), center, radius,
                           max(2, int(0.006 * settings.SCREEN_HEIGHT)))
        pygame.draw.circle(halo, (255, 247, 190, 150), center,
                           max(3, radius - 5), 1)
        old_clip = self.window.get_clip()
        self.window.set_clip(self.viewport_rect)
        self.window.blit(
            halo,
            (int(cx) - center[0], int(cy) - center[1]),
        )
        self.window.set_clip(old_clip)

    def _draw_hex(self, tile, corners, scx, scy, sz):
        """Draw a single hex with fill, border, and labels."""
        self._draw_hex_base(tile, corners, scx, scy, sz)
        self._draw_hex_border(tile, corners)
        self._draw_hex_details(tile, scx, scy, sz)

    # ── Map scan modes ─────────────────────────────────────────────

    def set_map_mode(self, mode):
        """Switch the map scan mode ('terrain'/'ownership'/'gold'/'vulnerable')."""
        self.map_mode = mode or 'terrain'

    def _ensure_gold_range(self):
        """Cache (min, max) gold rate across tiles for the gold heatmap."""
        if self._gold_range is None:
            rates = [t.gold_rate for t in self.tiles] if self.tiles else [0.0]
            lo, hi = min(rates), max(rates)
            self._gold_range = (lo, hi if hi > lo else lo + 1.0)
        return self._gold_range

    def _mode_overlay_color(self, tile):
        """Return an (r, g, b, a) wash for the active scan mode, or None.

        ``terrain`` (default) returns None so the rich suit/tier art shows
        through unchanged; the other modes tint every tile by one dimension
        so the whole map can be scanned at a glance.
        """
        mode = getattr(self, 'map_mode', 'terrain')
        if mode == 'terrain':
            return None
        if mode == 'ownership':
            if tile.is_mine:
                return (70, 200, 120, 120)
            if tile.owner:
                return (210, 90, 80, 120)
            return (120, 132, 150, 95)
        if mode == 'gold':
            lo, hi = self._ensure_gold_range()
            t = (tile.gold_rate - lo) / (hi - lo) if hi > lo else 0.0
            t = max(0.0, min(1.0, t))
            # dark slate → bright gold
            return (int(58 + t * 197), int(50 + t * 168), int(74 - t * 44), 152)
        if mode == 'vulnerable':
            if tile.is_mine:
                return (60, 90, 150, 70)
            shield = getattr(tile, 'kingdom_shield_remaining', 0) or 0
            reason = getattr(tile, 'kingdom_shield_reason', None)
            cooldown = getattr(tile, 'conquer_cooldown_remaining', 0) or 0
            if reason == 'core_protection' or shield != 0:
                return (200, 70, 70, 135)
            if cooldown > 0:
                return (210, 162, 72, 130)
            return (70, 205, 110, 140)
        return None

    def _draw_mode_wash(self, tile, corners):
        """Blit the active scan-mode colour over a tile (under hover)."""
        mode_clr = self._mode_overlay_color(tile)
        if mode_clr is None:
            return
        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        min_x = int(min(xs)) - 1
        min_y = int(min(ys)) - 1
        ow = int(max(xs)) - min_x + 2
        oh = int(max(ys)) - min_y + 2
        ovl = pygame.Surface((ow, oh), pygame.SRCALPHA)
        local = [(p[0] - min_x, p[1] - min_y) for p in corners]
        pygame.draw.polygon(ovl, mode_clr, local)
        self.window.blit(ovl, (min_x, min_y))

    def _draw_hex_base(self, tile, corners, scx, scy, sz):
        """Draw glow, fill, and owned-land surface cosmetics."""
        # Fill colour follows suit-bonus colour; tier controls intensity.
        fill = list(_tile_fill_color(tile))
        region_factor = self._region_presentation_factor()
        region_style = self._region_style(getattr(tile, 'region', None))
        region_tint = region_style.get('tint')
        if region_tint and region_factor > 0:
            alpha = float(getattr(settings, 'REGION_TINT_ALPHA_MAX', 48)) / 255.0
            fill = list(_blend_rgb(fill, region_tint,
                                   alpha * region_factor))

        # Hover brighten — tiered: the hovered tile gets the full boost,
        # every other tile in the same connected kingdom-component gets a
        # softer boost so the kingdom reads as one unit at a glance.  The
        # fill brighten is only one of two layers — both the hovered tile
        # and its kingdom siblings also get a warm-white overlay polygon
        # painted on top of the surface skin so the highlight stays
        # visible through opaque cosmetics.  ``hover_overlay_alpha``
        # selects which layer applies and at what intensity.
        hover_overlay_alpha = 0
        if self.hovered_tile is not None:
            if tile is self.hovered_tile:
                b = settings.HEX_HOVER_BRIGHTEN
                fill = [min(255, c + b) for c in fill]
                hover_overlay_alpha = int(getattr(
                    settings, 'HEX_HOVER_TILE_OVERLAY_ALPHA', 95))
            elif self._tile_in_hovered_component(tile):
                b = getattr(settings, 'HEX_HOVER_BRIGHTEN_KINGDOM',
                            max(8, settings.HEX_HOVER_BRIGHTEN // 2))
                fill = [min(255, c + b) for c in fill]
                hover_overlay_alpha = int(getattr(
                    settings, 'HEX_HOVER_KINGDOM_OVERLAY_ALPHA', 55))

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
            pulse = self._owner_glow_pulse()
            # Tint glow in owner color when an owner palette is set.
            owner_clr = self._tile_owner_color(tile, kind='glow')
            if owner_clr:
                base_alpha = settings.HEX_MINE_GLOW_CLR[3] if len(settings.HEX_MINE_GLOW_CLR) >= 4 else 90
                soft_alpha = settings.HEX_MINE_GLOW_SOFT_CLR[3] if len(settings.HEX_MINE_GLOW_SOFT_CLR) >= 4 else 45
                soft_clr = _scale_alpha((*owner_clr, soft_alpha), pulse)
                main_clr = _scale_alpha((*owner_clr, base_alpha), pulse)
            else:
                soft_clr = _scale_alpha(settings.HEX_MINE_GLOW_SOFT_CLR, pulse)
                main_clr = _scale_alpha(settings.HEX_MINE_GLOW_CLR, pulse)
            pygame.draw.polygon(glow_surf, soft_clr, soft_local)
            pygame.draw.polygon(glow_surf, main_clr, local_corners)
            self.window.blit(glow_surf, glow_rect.topleft)

        pygame.draw.polygon(self.window, fill, corners)

        if tile.owner:
            self._draw_surface_skin(tile, corners, scx, scy, sz)
            # Enemy-claimed wash: subtle diagonal hatch overlay tinted in the
            # enemy's owner color so enemy land reads distinct from neutral
            # without competing with the player's own territory.
            if not tile.is_mine:
                self._draw_enemy_wash(tile, corners, scx, scy, sz)

        # Conquest territory hint: dark overlay for isolated new-kingdom tiles,
        # warm golden tint for tiles adjacent to the player's existing kingdom.
        # The polygon is inset so it stays within the border and leaves the
        # border edges visually unaffected.
        if not tile.is_mine:
            outcome = getattr(self, '_conquest_outcomes', {}).get(tile.land_id)
            # Region presentation and cluster icons own the mid-zoom band.
            # Reveal the all-map conquest hatch only once the player is close
            # enough to inspect individual lands; hover feedback remains
            # available at every zoom.
            if (self.zoom >= 1.30 and outcome == 'new'
                    and tile is not self.hovered_tile):
                # Reducing circumradius by `inset` shrinks the perpendicular
                # distance to each flat edge by inset * sqrt(3)/2, so to clear
                # a border of `border_px` screen pixels the correct inset is
                # border_px * 2/sqrt(3).  An extra +1 adds a 1-px safety gap.
                border_px = max(1, int(self._border_w * self.zoom))
                border_inset = int(border_px * 2.0 / math.sqrt(3)) + 1
                inner_sz = max(4, sz - border_inset)
                ovl = self._get_conquest_overlay(sz, inner_sz, outcome)
                self.window.blit(ovl, ovl.get_rect(center=(int(scx), int(scy))))

            # Hover expansion preview: ghost the player's own kingdom skin over
            # the tile so the player can see how it would look if conquered.
            if (outcome == 'expand' and tile is self.hovered_tile):
                psk = getattr(self, '_player_surface_key', None)
                if psk and psk != 'surface_plain':
                    sz_int = max(8, int(sz))
                    art = hex_cosmetics.render_surface_art(psk, sz_int)
                    if art is not None:
                        try:
                            ghost = art.copy()
                            ghost.set_alpha(140)
                            self.window.blit(ghost,
                                             (int(scx) - sz_int, int(scy) - sz_int))
                        except Exception:
                            pass

        # Map scan-mode wash (ownership / gold / vulnerable) painted over the
        # base art, but under the hover highlight so hovering still reads.
        self._draw_mode_wash(tile, corners)

        # Warm-white hover wash painted on top of fill + surface skin so the
        # highlight reads clearly even through opaque cosmetics (parchment,
        # stone, snow).  Both the hovered tile and its kingdom siblings get
        # this layer — the hovered tile uses a stronger alpha so it still
        # reads as the focal point.
        if hover_overlay_alpha > 0:
            xs = [p[0] for p in corners]
            ys = [p[1] for p in corners]
            min_x = int(min(xs)) - 1
            min_y = int(min(ys)) - 1
            ow = int(max(xs)) - min_x + 2
            oh = int(max(ys)) - min_y + 2
            ovl = pygame.Surface((ow, oh), pygame.SRCALPHA)
            local = [(p[0] - min_x, p[1] - min_y) for p in corners]
            pygame.draw.polygon(ovl, (255, 248, 220, hover_overlay_alpha), local)
            self.window.blit(ovl, (min_x, min_y))

    def _draw_hex_border(self, tile, corners):
        """Draw selection and border cosmetics after all hex fills."""
        # At full-map scale a one-pixel line is proportionally wider than the
        # tile itself and turns the terrain into visual static.  Region seams,
        # ownership cluster outlines, and selections remain on their later
        # layers; ordinary per-land borders arrive as the player zooms in.
        if (self.zoom < 0.22 and tile is not self.selected_tile
                and not getattr(tile, 'is_recommended_tutorial_land', False)):
            return
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
            if getattr(tile, 'is_recommended_tutorial_land', False):
                pulse = 2 + int((pygame.time.get_ticks() // 260) % 2)
                pygame.draw.polygon(self.window, (255, 226, 96), corners,
                                    max(pulse, int((bw + 2) * self.zoom)))
            if tile is self.selected_tile:
                pygame.draw.polygon(self.window, settings.HEX_SELECT_BORDER, corners,
                                    max(1, int((self._border_w + 1) * self.zoom)))

    def _draw_hex_details(self, tile, scx, scy, sz):
        """Draw the per-tile overlays.

        Layout (high zoom):
          - top edge:      tier stars (no frame), straddling the flat top
          - centre:        suit icon with the bonus number on top
          - bottom-centre: core/timed shield (when shielded)
          - bottom edge:   owner chip (badge cosmetic + colored dot + name)
          - top-right:     pulsing warning badge (if defences incomplete)

        At low zoom per-tile suit icon is suppressed; a single suit icon
        is rendered at the cluster centre and a single name badge is
        rendered below it by ``_draw_kingdom_badges``.
        """
        zoom = self.zoom
        sz_ok_icons = (zoom >= settings.HEX_MAP_LAND_INFO_MIN_ZOOM
                       and sz >= 18)
        per_tile_suit = (zoom >= settings.HEX_MAP_LAND_NUMBERS_MIN_ZOOM
                         and sz >= 24)

        if sz_ok_icons:
            self._draw_tier_ribbon(tile, scx, scy, sz)

        if per_tile_suit:
            self._draw_center_suit(tile, scx, scy, sz)

        if tile.kingdom_is_shielded and sz > 24:
            self._draw_shield_badge(tile, scx, scy, sz)

        if tile.defence_incomplete and sz_ok_icons:
            self._draw_warning_badge(tile, scx, scy, sz,
                                     pygame.time.get_ticks())

        if tile is self.hovered_tile:
            self._draw_hover_ring(scx, scy, sz)
            if not tile.is_mine and sz >= 22:
                outcome = getattr(self, '_conquest_outcomes', {}).get(tile.land_id)
                if outcome:
                    self._draw_conquest_hover_label(scx, scy, sz, outcome)

    def _draw_conquest_hover_label(self, scx, scy, sz, outcome):
        """Small pill label above the hovered tile indicating conquest outcome."""
        if outcome == 'expand':
            text = '+ Add to kingdom'
            bg_clr = (20, 70, 20, 215)
            border_clr = (100, 185, 100)
            text_clr = (175, 240, 175)
        else:
            text = '+ New kingdom'
            bg_clr = (55, 42, 12, 215)
            border_clr = (185, 150, 70)
            text_clr = (225, 190, 105)

        font_px = max(8, int(sz * 0.27))
        txt_surf = self._cached_text(text, font_px, text_clr)
        pad_x = max(5, int(sz * 0.11))
        pad_y = max(2, int(sz * 0.05))
        pill_w = txt_surf.get_width() + pad_x * 2
        pill_h = txt_surf.get_height() + pad_y * 2

        top_y = int(scy - sz * (math.sqrt(3) / 2))
        pill_y = top_y - pill_h - 3
        pill_x = int(scx - pill_w / 2)

        pill = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        r = pill_h // 2
        pygame.draw.rect(pill, bg_clr, pill.get_rect(), border_radius=r)
        pygame.draw.rect(pill, border_clr, pill.get_rect(), 1, border_radius=r)
        pill.blit(txt_surf, (pad_x, pad_y))
        self.window.blit(pill, (pill_x, pill_y))

    # ── Pill / overlay helpers ─────────────────────────────────────

    def _draw_pill(self, rect, *, role='default'):
        """Render a rounded pill background+border. Returns the rect drawn."""
        bg = settings.HEX_PILL_BG_CLR
        if role == 'own':
            border = settings.HEX_PILL_BORDER_OWN
        elif role == 'warn':
            border = settings.HEX_WARNING_BORDER_CLR
        elif role == 'shield':
            border = (140, 190, 255)
        else:
            border = settings.HEX_PILL_BORDER_CLR
        radius = settings.HEX_PILL_RADIUS_PX
        cache = getattr(self, '_pill_cache', None)
        if cache is None:
            cache = {}
            self._pill_cache = cache
        key = (role, rect.w, rect.h)
        surf = cache.get(key)
        if surf is None:
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=radius)
            pygame.draw.rect(surf, border, surf.get_rect(), 1,
                             border_radius=radius)
            cache[key] = surf
        self.window.blit(surf, rect.topleft)
        return rect

    def _draw_tier_ribbon(self, tile, scx, scy, sz, *, y_offset=0):
        """One frameless star per tier level, centred on the hex's flat
        top edge so the stars visually click into the tile silhouette.
        No background pill — just stars + a soft drop shadow for legibility.
        """
        tier = max(1, min(6, int(getattr(tile, 'tier', 1) or 1)))
        min_star_r = 3 if sz >= 28 else 2
        star_r = max(min_star_r,
                     int(sz * settings.HEX_TIER_RIBBON_STAR_SZ_FACTOR))
        inner_r = max(1, int(star_r * 0.5))
        gap = max(1, int(star_r * 0.45))
        rows = [tier] if tier <= 4 else [3, tier - 3]
        row_step = star_r * 2 + max(1, int(gap * 0.5))
        # Top flat edge of the flat-top hex sits at y = scy - sz*sqrt(3)/2.
        # Nudge stars inside the tile; at tiers 5–6 the row wraps so the
        # symbols stay legible without spilling beyond the angled shoulders.
        top_edge_y = int(scy - sz * (math.sqrt(3) / 2))
        edge_inset = max(star_r + 1, int(sz * 0.27))
        first_cy = top_edge_y + edge_inset + int(y_offset)
        outline_w = 1 if star_r >= 5 else 0
        for row_idx, row_count in enumerate(rows):
            total_w = row_count * (star_r * 2) + (row_count - 1) * gap
            start_x = int(scx - total_w / 2) + star_r
            cy = first_cy + row_idx * row_step
            for i in range(row_count):
                sx = start_x + i * (star_r * 2 + gap)
                shadow = _star_points(sx + 1, cy + 2, star_r, inner_r)
                pts = _star_points(sx, cy, star_r, inner_r)
                pygame.draw.polygon(self.window, (16, 12, 4), shadow)
                pygame.draw.polygon(self.window, settings.HEX_STAR_FILL, pts)
                if outline_w:
                    pygame.draw.polygon(self.window, settings.HEX_STAR_BORDER,
                                        pts, outline_w)

    def _draw_center_suit(self, tile, scx, scy, sz):
        """Large centred suit icon with the bonus number rendered on top.

        Replaces the bottom stat strip: gold rate is now only shown in the
        land detail box. The bonus number is drawn without a leading ``+``
        per the latest design.
        """
        suit = getattr(tile, 'suit_bonus_suit', None)
        suit_raw = self._suit_icon_raw.get(suit)
        if suit_raw is None:
            return
        icon_sz = max(14, int(sz * 0.62))
        icon = self._get_scaled_icon(suit, suit_raw, icon_sz)
        if icon is None:
            return
        # Slight transparency so the suit doesn't overpower the tile fill.
        try:
            ghost = icon.copy()
            ghost.set_alpha(190)
            icon = ghost
        except Exception:
            pass
        rect = icon.get_rect(center=(int(scx), int(scy)))
        self.window.blit(icon, rect)

        bonus = int(getattr(tile, 'suit_bonus_value', 0) or 0)
        if bonus <= 0:
            return
        # Bonus number in a bold tier-style font, sized relative to icon.
        font_px = max(10, int(icon_sz * 0.55))
        bonus_str = str(bonus)
        text = self._cached_text(bonus_str, font_px, (255, 244, 200), bold=True)
        # Crisp dark outline for legibility on bright tile fills.
        outline = self._cached_text(bonus_str, font_px, (24, 16, 4), bold=True)
        cx_i, cy_i = int(scx), int(scy)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            self.window.blit(outline,
                             outline.get_rect(center=(cx_i + dx, cy_i + dy)))
        self.window.blit(text, text.get_rect(center=(cx_i, cy_i)))

    def _draw_warning_badge(self, tile, scx, scy, sz, now_ms):
        """Pulsing red badge with the broken icon for incomplete defences.
        Anchored to the hex's top-right flat corner."""
        r = max(8, int(sz * 0.20))
        # Anchor to the top-right flat corner of the flat-top hex.
        cx = int(scx + sz * 0.50) - max(1, int(self.zoom))
        cy = int(scy - sz * (math.sqrt(3) / 2)) + r + max(1, int(self.zoom))
        phase = (now_ms / 1000.0) * settings.HEX_WARNING_PULSE_HZ * 2 * math.pi
        alpha = 200 + int(40 * math.sin(phase))
        alpha = max(160, min(240, alpha))
        # Build the badge once per (r, has_icon) combo and modulate alpha for
        # the pulse — avoids allocating a fresh Surface every frame per tile.
        cache = getattr(self, '_warning_badge_cache', None)
        if cache is None:
            cache = self._warning_badge_cache = {}
        cache_key = (r, bool(self._broken_icon_raw))
        surf = cache.get(cache_key)
        if surf is None:
            size = r * 2 + 4
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            base_bg = (*settings.HEX_WARNING_BG_CLR[:3], 255)
            pygame.draw.circle(surf, base_bg, (r + 2, r + 2), r)
            pygame.draw.circle(surf, settings.HEX_WARNING_BORDER_CLR,
                               (r + 2, r + 2), r, 1)
            if self._broken_icon_raw:
                icon_sz = max(6, int(r * 1.7))
                icon = self._get_scaled_icon('broken', self._broken_icon_raw,
                                              icon_sz)
                if icon is not None:
                    surf.blit(icon, icon.get_rect(center=(r + 2, r + 2)))
            else:
                txt = self._tier_font.render('!', True,
                                              settings.HEX_WARNING_TEXT_CLR)
                surf.blit(txt, txt.get_rect(center=(r + 2, r + 2)))
            if len(cache) > 32:
                cache.pop(next(iter(cache)))
            cache[cache_key] = surf
        surf.set_alpha(alpha)
        self.window.blit(surf, (cx - r - 2, cy - r - 2))

    def _draw_owner_chip(self, tile, scx, scy, sz, *, show_name):
        """Colored owner dot (+ truncated username) anchored on the bottom
        flat edge of the hex.

        The pill behind the name inherits the kingdom's equipped *badge*
        cosmetic so the player's identity is visually consistent across
        zoom levels.  The colored dot sits to the left of the badge
        surface and remains a quick suit-agnostic owner indicator.
        """
        dot_r = max(4, int(sz * settings.HEX_OWNER_CHIP_DOT_R_FACTOR))
        is_mine = tile.is_mine
        owner_clr = (settings.HEX_MINE_BORDER if is_mine
                     else (_owner_color(tile.owner_user_id) or (180, 180, 180)))
        font = self._label_font
        name = tile.owner_username or ''
        if is_mine:
            name = 'You'
        if show_name and name:
            max_text_w = max(20, int(sz * 1.4))
            # Truncate to the chip's text budget before sending to the
            # badge renderer so the cache keys cleanly per truncation.
            truncated = name
            if font.size(name)[0] > max_text_w:
                while truncated and font.size(truncated + '…')[0] > max_text_w:
                    truncated = truncated[:-1]
                truncated = (truncated + '…') if truncated else '…'
            badge_key = (self._owner_style_key(tile, 'badge_key')
                         or settings.HEX_BADGE_DEFAULT_KEY)
            target_h = font.get_height() + max(2, settings.HEX_PILL_PAD_Y * 2)
            shimmer_phase = badge_cosmetics.shimmer_phase_for(
                pygame.time.get_ticks())
            badge_surf = badge_cosmetics.render_badge(
                badge_key, truncated, font,
                target_h=target_h, shimmer_phase=shimmer_phase,
            )
        else:
            badge_surf = None

        gap = max(2, int(2 * self.zoom))
        badge_w = badge_surf.get_width() if badge_surf else 0
        badge_h = badge_surf.get_height() if badge_surf else dot_r * 2
        rect_w = dot_r * 2 + (gap + badge_w if badge_surf else 0)
        rect_h = max(dot_r * 2, badge_h)
        # Sit straddling the hex bottom edge: half above, half below, so
        # the chip visually clicks onto the tile boundary.
        y = int(scy + sz * (math.sqrt(3) / 2)) - rect_h // 2
        x = int(scx - rect_w / 2)
        mid_y = y + rect_h // 2
        pygame.draw.circle(self.window, owner_clr,
                           (x + dot_r, mid_y), dot_r)
        pygame.draw.circle(self.window, (12, 10, 8),
                           (x + dot_r, mid_y), dot_r, 1)
        if badge_surf:
            bx = x + dot_r * 2 + gap
            by = mid_y - badge_surf.get_height() // 2
            self.window.blit(badge_surf, (bx, by))

    def _draw_hover_ring(self, scx, scy, sz):
        """Thin white-alpha inner ring around the hovered hex."""
        inner_sz = max(4, sz - max(2, int(2 * self.zoom)))
        pts = _hex_corners(scx, scy, inner_sz)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        min_x = int(min(xs)) - 2
        min_y = int(min(ys)) - 2
        max_x = int(max(xs)) + 2
        max_y = int(max(ys)) + 2
        surf = pygame.Surface((max_x - min_x, max_y - min_y),
                              pygame.SRCALPHA)
        local = [(p[0] - min_x, p[1] - min_y) for p in pts]
        pygame.draw.polygon(surf, settings.HEX_HOVER_RING_CLR, local,
                            settings.HEX_HOVER_RING_W)
        self.window.blit(surf, (min_x, min_y))

    # ── Suit clusters ──────────────────────────────────────────────

    def _split_suit_component_at_peaks(self, members):
        """Split touching same-suit terrain around separate peak plateaus.

        The map generator deliberately allows neighbouring seed clusters of
        the same suit to touch. Their original seed IDs are not persisted in
        the land payload. Usually each generated cluster retains a tier-six
        plateau, but neutral seams can remove an apex and leave a lower local
        maximum. A deterministic multi-source flood from every local-maximum
        plateau recovers one visual cluster per peak without altering map
        data.
        """
        if len(members) < 2:
            return [members]

        member_by_coord = {(tile.col, tile.row): tile for tile in members}
        plateau_coords = []
        visited = set()
        for start in sorted(
                member_by_coord,
                key=lambda coord: (
                    -int(getattr(
                        member_by_coord[coord], 'tier', 0) or 0),
                    member_by_coord[coord].land_id,
                )):
            if start in visited:
                continue
            tier = int(getattr(member_by_coord[start], 'tier', 0) or 0)
            stack = [start]
            visited.add(start)
            plateau = []
            touches_higher = False
            while stack:
                coord = stack.pop()
                plateau.append(coord)
                for neighbour in _edge_neighbour_coords(*coord):
                    neighbour_tile = member_by_coord.get(neighbour)
                    if neighbour_tile is None:
                        continue
                    neighbour_tier = int(
                        getattr(neighbour_tile, 'tier', 0) or 0)
                    if neighbour_tier > tier:
                        touches_higher = True
                    elif neighbour_tier == tier and neighbour not in visited:
                        visited.add(neighbour)
                        stack.append(neighbour)
            if not touches_higher:
                plateau_coords.append(plateau)

        if len(plateau_coords) <= 1:
            return [members]

        plateau_coords.sort(key=lambda plateau: min(
            member_by_coord[coord].land_id for coord in plateau))
        assignment = {}
        queue = deque()
        for plateau_idx, plateau in enumerate(plateau_coords):
            for coord in sorted(
                    plateau,
                    key=lambda item: member_by_coord[item].land_id):
                assignment[coord] = (0, plateau_idx)
                queue.append(coord)

        while queue:
            coord = queue.popleft()
            distance, plateau_idx = assignment[coord]
            candidate = (distance + 1, plateau_idx)
            for neighbour in _edge_neighbour_coords(*coord):
                if neighbour not in member_by_coord:
                    continue
                current = assignment.get(neighbour)
                if current is None or candidate < current:
                    assignment[neighbour] = candidate
                    queue.append(neighbour)

        groups = [[] for _ in plateau_coords]
        for coord, tile in member_by_coord.items():
            _distance, plateau_idx = assignment[coord]
            groups[plateau_idx].append(tile)
        return [group for group in groups if group]

    @staticmethod
    def _suit_cluster_descriptor(members, suit):
        """Build the cached rendering descriptor for one visual cluster."""
        cx = sum(tile.cx for tile in members) / len(members)
        cy = sum(tile.cy for tile in members) / len(members)
        region_counts = {}
        for tile in members:
            if tile.region:
                region_counts[tile.region] = (
                    region_counts.get(tile.region, 0) + 1)
        primary_region = (
            min(
                region_counts,
                key=lambda region: (
                    -region_counts[region],
                    region,
                ),
            )
            if region_counts else None
        )
        anchor_candidates = [
            tile for tile in members
            if primary_region is None or tile.region == primary_region
        ]
        anchor = min(
            anchor_candidates,
            key=lambda tile: (
                (tile.cx - cx) ** 2 + (tile.cy - cy) ** 2,
                tile.land_id,
            ),
        )
        return {
            'suit': suit,
            'center_x': cx,
            'center_y': cy,
            'anchor_x': anchor.cx,
            'anchor_y': anchor.cy,
            'anchor_land_id': anchor.land_id,
            'region': primary_region,
            'tile_count': len(members),
        }

    def _suit_clusters(self):
        """Return one descriptor per peak-defined same-suit cluster.

        First collect connected same-suit terrain, then split touching seed
        clusters around their separate highest-tier plateaus. Tiles without a
        suit bonus are skipped entirely.

        The result depends only on tile data (suit + neighbours), so it is
        cached and only recomputed when _build_tiles/update_data fires.
        """
        cached = self._suit_clusters_cache
        if cached is not None:
            return cached
        coord_to_tile = {(t.col, t.row): t for t in self.tiles}
        visited = set()
        clusters = []
        for start in self.tiles:
            if start.land_id in visited:
                continue
            suit = getattr(start, 'suit_bonus_suit', None)
            if not suit or suit == 'Neutral':
                visited.add(start.land_id)
                continue
            stack = [start]
            members = []
            while stack:
                cur = stack.pop()
                if cur.land_id in visited:
                    continue
                if getattr(cur, 'suit_bonus_suit', None) != suit:
                    continue
                visited.add(cur.land_id)
                members.append(cur)
                for ncoord in _edge_neighbour_coords(cur.col, cur.row):
                    nb = coord_to_tile.get(ncoord)
                    if nb is None or nb.land_id in visited:
                        continue
                    if getattr(nb, 'suit_bonus_suit', None) == suit:
                        stack.append(nb)
            if not members:
                continue
            for cluster_members in self._split_suit_component_at_peaks(
                    members):
                clusters.append(self._suit_cluster_descriptor(
                    cluster_members, suit))
        self._suit_clusters_cache = clusters
        return clusters

    # ── Cluster perimeter outline ──────────────────────────────────

    def _get_enemy_wash_overlay(self, sz_int):
        """Return a cached translucent diagonal-hatch hex overlay for enemies."""
        cache = getattr(self, '_enemy_wash_cache', None)
        if cache is None:
            cache = self._enemy_wash_cache = {}
        if sz_int in cache:
            return cache[sz_int]
        surf = pygame.Surface((sz_int * 2, sz_int * 2), pygame.SRCALPHA)
        cx, cy = sz_int, sz_int
        # Faint diagonal hatch — white tint, low alpha; the wash sits on top
        # of the suit fill but stays subtle compared to mine-glow.
        line_clr = (40, 30, 30, 55)
        step = max(3, int(sz_int * 0.22))
        bound = int(sz_int * 1.05)
        thick = max(1, int(sz_int * 0.04))
        for i in range(-bound, bound + 1, step):
            pygame.draw.line(
                surf, line_clr,
                (cx - bound, cy + i - bound),
                (cx + bound, cy + i + bound),
                thick,
            )
        # Mask to hex shape so the wash doesn't bleed into neighbours.
        mask = pygame.Surface((sz_int * 2, sz_int * 2), pygame.SRCALPHA)
        pygame.draw.polygon(
            mask, (255, 255, 255, 255), _hex_corners(cx, cy, sz_int),
        )
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        cache[sz_int] = surf
        return surf

    def _draw_enemy_wash(self, tile, corners, scx, scy, sz):
        """Faint hatch overlay for enemy-claimed (non-mine) tiles."""
        if sz < 6:
            return
        sz_int = max(8, int(sz))
        ovl = self._get_enemy_wash_overlay(sz_int)
        self.window.blit(ovl, ovl.get_rect(center=(int(scx), int(scy))))
    def _tile_owner_color(self, tile, kind='accent'):
        """Return RGB owner color for ``tile`` (palette + fallback).

        ``kind`` is either ``'accent'`` (used for borders, chip, outline) or
        ``'glow'`` (used for the mine glow).  Falls back to deterministic
        per-user color, then to gold for the local player.
        """
        if not tile.owner_user_id:
            return None
        palette = getattr(settings, 'KINGDOM_COLOR_PALETTE', {})
        color_key = self._owner_style_key(tile, 'color_key')
        if color_key and color_key in palette:
            entry = palette[color_key]
            if kind == 'glow':
                return entry.get('glow_rgb') or entry.get('accent_rgb')
            return entry.get('accent_rgb') or entry.get('glow_rgb')
        if tile.is_mine:
            return settings.HEX_MINE_BORDER_HIGHLIGHT
        return _owner_color(tile.owner_user_id)

    def _draw_cluster_outlines(self, visible_hexes, sz):
        """Stroke the outer perimeter of each owner's hex cluster.

        For every visible owned tile we draw only the edges that face a
        differently-owned (or empty) neighbour, in the owner's color.
        Owned-by-player clusters get a thicker accent stroke; enemy
        clusters get a thinner muted stroke.
        """
        if sz < 8:
            return
        # Width scales with zoom but with a clamp so it remains visible at
        # low zoom and not absurd at very high zoom.
        bw_own = max(2, int(sz * 0.10))
        bw_enemy = max(1, int(sz * 0.055))
        for tile, corners, scx, scy in visible_hexes:
            if not tile.owner_user_id:
                continue
            clr = self._tile_owner_color(tile)
            if not clr:
                continue
            edges = _edge_neighbour_coords(tile.col, tile.row)
            width = bw_own if tile.is_mine else bw_enemy
            # Accent alpha: own clusters more prominent.
            alpha = 230 if tile.is_mine else 150
            stroke = (clr[0], clr[1], clr[2], alpha)
            for i, coord in enumerate(edges):
                if self._same_owner_neighbour(tile, coord):
                    continue
                p0 = corners[i]
                p1 = corners[(i + 1) % 6]
                # Draw onto a per-edge alpha surface so RGBA respected.
                xs = (p0[0], p1[0])
                ys = (p0[1], p1[1])
                pad = width + 2
                rect = pygame.Rect(
                    int(min(xs)) - pad,
                    int(min(ys)) - pad,
                    int(max(xs) - min(xs)) + pad * 2,
                    int(max(ys) - min(ys)) + pad * 2,
                )
                if rect.w <= 0 or rect.h <= 0:
                    continue
                edge_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                pygame.draw.line(
                    edge_surf, stroke,
                    (p0[0] - rect.x, p0[1] - rect.y),
                    (p1[0] - rect.x, p1[1] - rect.y),
                    width,
                )
                self.window.blit(edge_surf, rect.topleft)

    def _draw_suit_cluster_icons(self, sz):
        """Draw one large suit icon at the centre of every connected
        same-suit region. This is the middle resolution between the
        overview's regional main suit and the per-land suit display."""
        if sz <= 8:
            return
        fade = self._suit_cluster_icon_factor()
        if fade <= 0.0:
            return
        vp = self.viewport_rect
        icon_sz = max(20, int(sz * 1.05))
        for cluster in self._suit_clusters():
            # Tiny single-tile clusters can rely on the per-tile icon at
            # higher zoom; skip the cluster overlay so it doesn't fight
            # with the regular tile fill.
            if cluster['tile_count'] < 2:
                continue
            scx, scy = self.world_to_screen(
                cluster['center_x'], cluster['center_y'])
            if scx < vp.left - 100 or scx > vp.right + 100:
                continue
            if scy < vp.top - 100 or scy > vp.bottom + 100:
                continue
            suit = cluster['suit']
            suit_raw = self._suit_icon_raw.get(suit)
            if suit_raw is None:
                continue
            icon = self._get_scaled_icon(
                f'cluster_{suit}', suit_raw, icon_sz)
            if icon is None:
                continue
            try:
                ghost = icon.copy()
                ghost.set_alpha(max(1, int(190 * fade)))
                icon = ghost
            except Exception:
                pass
            self.window.blit(
                icon,
                icon.get_rect(center=(int(scx), int(scy))))

    def _kingdom_badges(self):
        """Return grouped badge descriptors for all visible owned kingdoms.

        Depends only on tile ownership/kingdom data; cached and invalidated
        when _build_tiles/update_data refreshes the tile list.
        """
        cached = self._kingdom_badges_cache
        if cached is not None:
            return cached
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
                'owner_user_id': tile.owner_user_id,
                'owner_username': tile.owner_username,
                'badge_keys': {},
                'suit_keys': {},
                'levels': {},
            })
            group['tiles'].append(tile)
            if not group['name']:
                name = str(tile.kingdom_name or '').strip()
                if name:
                    group['name'] = name
            try:
                level = int(getattr(tile, 'kingdom_level', 0) or 0)
            except (TypeError, ValueError):
                level = 0
            if level > 0:
                group['levels'][level] = group['levels'].get(level, 0) + 1
            bk = (self._owner_style_key(tile, 'badge_key')
                  or settings.HEX_BADGE_DEFAULT_KEY)
            group['badge_keys'][bk] = group['badge_keys'].get(bk, 0) + 1
            sk = getattr(tile, 'suit_bonus_suit', None)
            if sk:
                group['suit_keys'][sk] = group['suit_keys'].get(sk, 0) + 1

        badges = []
        for gk, group in groups.items():
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
            badge_key = (max(group['badge_keys'].items(),
                             key=lambda kv: kv[1])[0]
                         if group['badge_keys']
                         else settings.HEX_BADGE_DEFAULT_KEY)
            suit_key = (max(group['suit_keys'].items(), key=lambda kv: kv[1])[0]
                        if group['suit_keys'] else None)
            level = (max(group['levels'].items(), key=lambda kv: (kv[1], kv[0]))[0]
                     if group['levels'] else 0)
            subtitle = f'Lv {level}' if level > 0 else None
            sigil_key = (self._owner_style_key(tiles[0], 'sigil_key')
                         or getattr(settings, 'KINGDOM_SIGIL_DEFAULT_KEY',
                                    'sigil_none'))
            badges.append({
                'name': name,
                'level': level,
                'subtitle': subtitle,
                'center_x': center_x,
                'center_y': center_y,
                'tile_count': len(tiles),
                'badge_key': badge_key,
                'suit_key': suit_key,
                'sigil_key': sigil_key,
                'representative_tile': tiles[0],
                'group_key': gk,
                'owner_user_id': group.get('owner_user_id'),
            })
        self._kingdom_badges_cache = badges
        return badges

    def _draw_kingdom_badges(self, sz):
        """Draw the kingdom name badge as a nameplate plinth below each
        owned cluster's suit icon.

        The badge background, ornaments and text are produced as a single
        cached surface by ``badge_cosmetics.render_badge`` so per-frame
        cost is one ``blit`` per visible kingdom.
        """
        if sz <= 8:
            return

        vp = self.viewport_rect
        # Scale badge font proportionally to the hex size so the badge
        # remains legible at all zoom levels (zoomed in and zoomed out).
        badge_scale = max(
            0.76,
            min(1.22, (sz / max(1, settings.HEX_SIZE)) * 0.72),
        )
        scaled_font_size = max(
            9, int(settings.HEX_LABEL_FONT_SIZE * badge_scale))
        font = settings.get_font(scaled_font_size)
        subtitle_font = settings.get_font(
            max(8, int(scaled_font_size * 0.68)), bold=True)
        offset_y = sz * settings.HEX_GROUP_BADGE_OFFSET_Y
        gap_px = max(1, int(sz * settings.HEX_GROUP_BADGE_GAP_FACTOR))
        subtitle_h = subtitle_font.get_height()
        target_h = max(font.get_height() + subtitle_h + 8,
                       int((font.get_height() + subtitle_h) * 1.25))
        # Rival nameplates shrink at overview zoom so a cluster of
        # neighbouring kingdoms' badges stops hiding the land shapes.
        owner_name_zoom = float(getattr(
            settings, 'HEX_MAP_OWNER_NAME_MIN_ZOOM', 2.0))
        compact_font_size = max(8, int(scaled_font_size * 0.74))
        compact_font = settings.get_font(compact_font_size)
        compact_subtitle_font = settings.get_font(
            max(7, int(compact_font_size * 0.68)), bold=True)
        compact_subtitle_h = compact_subtitle_font.get_height()
        compact_target_h = max(
            compact_font.get_height() + compact_subtitle_h + 6,
            int((compact_font.get_height() + compact_subtitle_h) * 1.20))
        # Suit cluster icon footprint (matches _draw_suit_cluster_icons).
        cluster_icon_sz = max(20, int(sz * 1.05))
        shimmer_phase = badge_cosmetics.shimmer_phase_for(
            pygame.time.get_ticks())
        placed_badge_rects = []

        for badge_data in self._kingdom_badges():
            cx_w, cy_w = badge_data['center_x'], badge_data['center_y']
            scx, scy = self.world_to_screen(cx_w, cy_w)
            # Keep cluster rendering scoped to visible map area.
            if scx < vp.left - 100 or scx > vp.right + 100:
                continue
            if scy < vp.top - 60 or scy > vp.bottom + 100:
                continue

            rep_tile = badge_data.get('representative_tile')
            compact = (self.zoom < owner_name_zoom
                       and not bool(getattr(rep_tile, 'is_mine', False)))
            b_font = compact_font if compact else font
            b_subtitle_font = compact_subtitle_font if compact else subtitle_font
            b_target_h = compact_target_h if compact else target_h

            badge_key = (badge_data.get('badge_key')
                         or settings.HEX_BADGE_DEFAULT_KEY)
            subtitle = badge_data.get('subtitle')
            if subtitle:
                badge_surf = badge_cosmetics.render_badge_with_subtitle(
                    badge_key,
                    str(badge_data['name']),
                    str(subtitle),
                    b_font,
                    subtitle_font=b_subtitle_font,
                    target_h=b_target_h,
                    shimmer_phase=shimmer_phase,
                )
            else:
                badge_surf = badge_cosmetics.render_badge(
                    badge_key,
                    str(badge_data['name']),
                    b_font,
                    target_h=b_target_h,
                    shimmer_phase=shimmer_phase,
                )

            # Look up crowns for this badge group BEFORE positioning the
            # badge so we can carve out a full crown row above the name.
            kingdom_rank = self._gold_crown_groups.get(
                badge_data.get('group_key'))
            lands_rank = self._silver_wreath_users.get(
                badge_data.get('owner_user_id'))
            crown_icons = []
            if kingdom_rank in (1, 2, 3):
                ico = self._render_crown_icon(
                    'kingdom', kingdom_rank,
                    max(12, int(badge_surf.get_height() * 0.58)))
                if ico is not None:
                    crown_icons.append(ico)
            # At overview zoom one compact medal is enough.  Revealing the
            # secondary realm medal only at close zoom prevents ranking art
            # from obscuring the actual land shapes.
            if (lands_rank in (1, 2, 3)
                    and (self.zoom >= 2.0 or not crown_icons)):
                ico = self._render_crown_icon(
                    'lands', lands_rank,
                    max(12, int(badge_surf.get_height() * 0.58)))
                if ico is not None:
                    crown_icons.append(ico)
            # Region titles follow the player, like Greatest Realm medals:
            # every kingdom badge owned by a current Champion receives the
            # shared Champion medal in the same dedicated ranking row.
            if badge_data.get('owner_user_id') in getattr(
                    self, '_region_champion_users', set()):
                ico = self._render_champion_icon(
                    max(12, int(badge_surf.get_height() * 0.58)))
                if ico is not None:
                    crown_icons.append(ico)

            crown_row_h = 0
            crown_row_gap = 0
            if crown_icons:
                crown_row_h = max(ic.get_height() for ic in crown_icons)
                # Small breathing space between the crown row and the name
                # pill so the two read as stacked rows of one nameplate.
                crown_row_gap = max(2, int(self.zoom * 2))

            # Anchor the badge below the suit cluster icon.  When a crown
            # row applies, shift the name pill DOWN by the crown-row
            # footprint so the crowns occupy a dedicated row above the
            # name (and clear the suit cluster icon above).
            base_label_y = scy + offset_y + cluster_icon_sz * 0.55 + gap_px
            label_y = base_label_y + (crown_row_h + crown_row_gap) / 2
            br = badge_surf.get_rect(center=(int(scx), int(label_y)))

            # Dense neighbouring kingdoms often put long names on almost the
            # same baseline.  Try nearby vertical lanes before accepting an
            # overlap; the identity sigil remains anchored to the cluster so
            # the shifted nameplate still has a clear visual owner.
            base_br = br.copy()
            lane_step = max(b_target_h + 4, int(sz * 0.42))
            candidates = [0, -lane_step, lane_step,
                          -2 * lane_step, 2 * lane_step]
            for dy in candidates:
                candidate = base_br.move(0, dy)
                if candidate.top < vp.top + 4 or candidate.bottom > vp.bottom - 4:
                    continue
                collision_rect = candidate.inflate(6, 4)
                if not any(collision_rect.colliderect(other)
                           for other in placed_badge_rects):
                    br = candidate
                    break
            placed_badge_rects.append(br.inflate(6, 4))

            shadow_dx, shadow_dy = settings.HEX_GROUP_BADGE_SHADOW_OFFSET
            shadow_radius = max(2, int(3 * self.zoom))
            shadow = self._shadow_for(badge_surf.get_size(), shadow_radius)
            self.window.blit(shadow,
                             (br.x + shadow_dx, br.y + shadow_dy))
            self.window.blit(badge_surf, br)

            # Crown row sits directly above the name pill, centred on x.
            # Multiple crowns stack horizontally with a small gap.
            if crown_icons:
                crown_gap = max(2, int(self.zoom * 3))
                total_w = (sum(ic.get_width() for ic in crown_icons)
                           + crown_gap * max(0, len(crown_icons) - 1))
                row_top = br.y - crown_row_gap - crown_row_h
                cur_x = br.centerx - total_w // 2
                for ic in crown_icons:
                    iy = row_top + (crown_row_h - ic.get_height()) // 2
                    self.window.blit(ic, (int(cur_x), int(iy)))
                    cur_x += ic.get_width() + crown_gap

            # Kingdom sigil glyph drawn above the suit cluster icon as the
            # cluster's identity marker.  Tinted with the kingdom's owner
            # accent so it reads as part of the same visual identity.
            sigil_key = badge_data.get('sigil_key')
            if sigil_key and sigil_key != 'sigil_none':
                rep_tile = badge_data.get('representative_tile')
                accent = (self._tile_owner_color(rep_tile, kind='accent')
                          if rep_tile is not None
                          else settings.HEX_MINE_BORDER_HIGHLIGHT)
                sigil_sz = max(14, int(cluster_icon_sz * 0.85))
                sigil_surf = sigil_cosmetics.render_sigil(
                    sigil_key, sigil_sz, accent)
                if sigil_surf is not None:
                    sigil_y = scy + offset_y - cluster_icon_sz * 0.65
                    rect = sigil_surf.get_rect(
                        center=(int(scx), int(sigil_y)))
                    self.window.blit(sigil_surf, rect)

    def _shadow_for(self, size, radius):
        """Return a cached drop-shadow surface for the given pixel size."""
        cache = getattr(self, '_badge_shadow_cache', None)
        if cache is None:
            cache = {}
            self._badge_shadow_cache = cache
        key = (size, radius)
        surf = cache.get(key)
        if surf is None:
            surf = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.rect(surf, settings.HEX_GROUP_BADGE_SHADOW_CLR,
                             surf.get_rect(), border_radius=radius)
            # Bound cache so it never grows without limit.
            if len(cache) > 32:
                cache.pop(next(iter(cache)))
            cache[key] = surf
        return surf

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
        """Shield icon anchored at the lower bottom-center of the hex.

        Core kingdoms (``remaining < 0``) are permanently shielded; the
        shield is drawn without a number. Timed shields overlay the
        remaining time *on top* of the shield (centred over the icon).
        """
        remaining = int(tile.kingdom_shield_remaining or 0)
        is_core = remaining < 0
        # Larger than before so the shield reads clearly and a number can
        # sit legibly on top of it.
        icon_sz = max(20, int(sz * (0.55 if is_core else 0.50)))
        cx = int(scx)
        # Bottom of icon sits slightly above the hex bottom edge.
        bottom_y = int(round(scy + sz * (math.sqrt(3) / 2) - sz * 0.10))
        icon_center = (cx, bottom_y - icon_sz // 2)
        if self._shield_icon_raw:
            icon = self._get_scaled_icon('shield', self._shield_icon_raw,
                                         icon_sz)
            if icon is not None:
                rect = icon.get_rect(midbottom=(cx, bottom_y))
                icon_center = rect.center
                self.window.blit(icon, rect)
        else:
            r = icon_sz // 2
            cy = icon_center[1]
            pygame.draw.polygon(self.window, (140, 190, 255), [
                (cx, cy - r),
                (cx + r, cy - r // 3),
                (cx, cy + r),
                (cx - r, cy - r // 3),
            ])
        if is_core:
            return
        # Overlay the remaining duration *on top* of the shield, slightly
        # below centre so it visually sits inside the shield's body.
        label = self._format_countdown(remaining)
        font_px = max(10, int(icon_sz * 0.42))
        txt = self._cached_text(label, font_px, (255, 248, 220), bold=True)
        outline = self._cached_text(label, font_px, (16, 12, 4), bold=True)
        center = (icon_center[0], icon_center[1] + int(icon_sz * 0.05))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (1, -1), (-1, 1), (1, 1)):
            self.window.blit(outline,
                             outline.get_rect(center=(center[0] + dx,
                                                      center[1] + dy)))
        self.window.blit(txt, txt.get_rect(center=center))

    def _draw_surface_skin(self, tile, corners, scx, scy, sz):
        """Blit cached cosmetic surface art (and emblem) for owned lands."""
        key = self._owner_style_key(tile, 'surface_key')
        if not key or key == 'surface_plain':
            return
        sz_int = max(8, int(sz))
        art = hex_cosmetics.render_surface_art(key, sz_int)
        if art is None:
            return
        self.window.blit(art, (int(scx) - sz_int, int(scy) - sz_int))
        emblem = hex_cosmetics.render_center_emblem(key, sz_int)
        if emblem is not None:
            erect = emblem.get_rect(center=(int(scx), int(scy)))
            self.window.blit(emblem, erect)

    def _draw_owner_border(self, tile, corners):
        """Draw cosmetic kingdom borders without overpainting neighbours.

        Per-edge drawing dispatches to the skin's ``style`` so each border
        cosmetic has a distinct *structural* identity (rope braid, carved
        notches, spikes, gem cabochons, dashed double-line, thorned vine).
        Same-owner internal edges are skipped, and edges shared with another
        visible land are drawn inset toward the hex centre so two adjacent
        kingdoms' borders meet cleanly without overpainting.
        """
        key = self._owner_style_key(tile, 'border_key')
        skin = settings.HEX_BORDER_SKINS.get(
            key, settings.HEX_BORDER_SKINS.get('border_simple_gold', {}))
        style = skin.get('style', 'simple')
        width_bonus = int(skin.get('width_bonus', 0) or 0)
        outer_w = max(1, int((self._border_w + 4 + width_bonus) * self.zoom / 1.0))
        main_w = max(1, int((self._border_w + 2 + width_bonus) * self.zoom / 1.0))
        inner_w = max(1, int(self._border_w * self.zoom / 1.0))
        outer_clr = skin.get('outer', settings.HEX_MINE_BORDER_OUTER)
        main_clr = skin.get('main', settings.HEX_MINE_BORDER)
        highlight_clr = skin.get('highlight', settings.HEX_MINE_BORDER_HIGHLIGHT)
        palette = (outer_clr, main_clr, highlight_clr)
        center_x = sum(x for x, _y in corners) / len(corners)
        center_y = sum(y for _x, y in corners) / len(corners)
        edge_neighbours = _edge_neighbour_coords(tile.col, tile.row)
        external_edges = []
        shared_edges = []
        drawn_vertex_indices = set()
        for edge_idx, coord in enumerate(edge_neighbours):
            start = corners[edge_idx]
            end = corners[(edge_idx + 1) % len(corners)]
            if self._same_owner_neighbour(tile, coord):
                continue
            drawn_vertex_indices.add(edge_idx)
            drawn_vertex_indices.add((edge_idx + 1) % len(corners))
            if self._tile_by_coord.get(coord):
                shared_edges.append((start, end))
            else:
                external_edges.append((start, end))

        def _inset_shared_edge(start, end):
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = math.hypot(dx, dy)
            if length <= 0:
                return start, end
            ux = dx / length
            uy = dy / length
            mid_x = (start[0] + end[0]) / 2.0
            mid_y = (start[1] + end[1]) / 2.0
            nx = center_x - mid_x
            ny = center_y - mid_y
            n_len = math.hypot(nx, ny) or 1.0
            nx /= n_len
            ny /= n_len
            inset = max(1.0, outer_w * 0.58)
            shorten = max(0.0, outer_w * 0.32)
            return (
                (start[0] + nx * inset + ux * shorten,
                 start[1] + ny * inset + uy * shorten),
                (end[0] + nx * inset - ux * shorten,
                 end[1] + ny * inset - uy * shorten),
            )

        # External edges: full-thickness style drawing.
        for start, end in external_edges:
            self._draw_border_edge(style, start, end, palette,
                                   outer_w, main_w, inner_w)

        # Shared edges (inset, slightly slimmer so two kingdoms fit cleanly).
        shared_outer = max(1, int(outer_w * 0.70))
        shared_main = max(1, int(main_w * 0.66))
        shared_inner = max(1, int(inner_w * 0.62))
        for start, end in shared_edges:
            ist, iend = _inset_shared_edge(start, end)
            self._draw_border_edge(style, ist, iend, palette,
                                   shared_outer, shared_main, shared_inner)

        # Premium polish: vertex ornaments at every drawn corner.
        if (hex_cosmetics.border_rarity(key) in ('rare', 'epic')
                and self.zoom >= 0.7):
            ornament = hex_cosmetics.render_vertex_ornament(
                key, max(10, int(self._size * self.zoom)))
            if ornament is not None:
                for vidx in drawn_vertex_indices:
                    vx, vy = corners[vidx]
                    rect = ornament.get_rect(center=(int(vx), int(vy)))
                    self.window.blit(ornament, rect)

    def _draw_border_edge(self, style, start, end, palette,
                          outer_w, main_w, inner_w):
        """Render a single owned-hex edge in the requested cosmetic style."""
        draw_border_edge(self.window, style, start, end, palette,
                         outer_w, main_w, inner_w)

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

        min_wx = self._world_min_x
        max_wx = self._world_max_x
        min_wy = self._world_min_y
        max_wy = self._world_max_y
        world_w = max_wx - min_wx
        world_h = max_wy - min_wy
        if world_w == 0 or world_h == 0:
            return

        scale = min((mm_w - 8) / world_w, (mm_h - 8) / world_h)
        off_x = (mm_w - world_w * scale) / 2
        off_y = (mm_h - world_h * scale) / 2

        static_key = (
            mm_w, mm_h, round(scale, 6), round(off_x, 3), round(off_y, 3),
            round(min_wx, 3), round(min_wy, 3),
            getattr(self, '_minimap_data_version', 0),
        )
        if static_key != getattr(self, '_minimap_static_cache_key', None):
            mm_surf = pygame.Surface((mm_w, mm_h), pygame.SRCALPHA)
            mm_surf.fill(settings.MINIMAP_BG_CLR)
            mine_centers = []
            for tile in self.tiles:
                tx = off_x + (tile.cx - min_wx) * scale
                ty = off_y + (tile.cy - min_wy) * scale
                dot_r = max(2, int(self._size * scale * 0.5))
                if tile.owner_user_id:
                    accent = self._tile_owner_color(tile, kind='accent')
                    clr = accent or _tile_fill_color(tile)
                    border = settings.HEX_MINE_BORDER if tile.is_mine else (40, 40, 40)
                else:
                    clr = _tile_fill_color(tile)
                    region_tint = self._region_style(tile.region).get('tint')
                    if region_tint:
                        clr = _blend_rgb(clr, region_tint, 0.48)
                    border = _tile_border_color(tile)
                if tile.is_mine:
                    pygame.draw.circle(mm_surf, settings.HEX_MINE_BORDER,
                                       (int(tx), int(ty)), dot_r + 2)
                    border = (255, 245, 190)
                    mine_centers.append((tx, ty))
                pygame.draw.circle(mm_surf, clr, (int(tx), int(ty)), dot_r)
                pygame.draw.circle(mm_surf, border, (int(tx), int(ty)), dot_r, 1)

            # Simplified historic-region seams.  These stay one pixel wide so
            # player ownership dots remain the strongest minimap signal.
            seam_clr = (234, 216, 178, 105)
            for tile in self.tiles:
                if not tile.region:
                    continue
                corners = _hex_corners(tile.cx, tile.cy, self._size)
                for i, coord in enumerate(_edge_neighbour_coords(
                        tile.col, tile.row)):
                    neighbour = self._tile_by_coord.get(coord)
                    if (neighbour is None or neighbour.region == tile.region
                            or (tile.col, tile.row) > coord):
                        continue
                    p0, p1 = corners[i], corners[(i + 1) % 6]
                    pygame.draw.line(
                        mm_surf, seam_clr,
                        (int(off_x + (p0[0] - min_wx) * scale),
                         int(off_y + (p0[1] - min_wy) * scale)),
                        (int(off_x + (p1[0] - min_wx) * scale),
                         int(off_y + (p1[1] - min_wy) * scale)), 1)

            # Explicit dominant-suit marks make the regional reading survive
            # at minimap scale.  They sit below the player's own sigil and use
            # restrained opacity so ownership remains the primary signal.
            mark_sz = max(9, min(20, int(min(mm_w, mm_h) * 0.16)))
            for region_key, geo in self._region_geometry().items():
                style = self._region_style(region_key)
                suit = style.get('dominant_suit')
                wx, wy = geo['center']
                mx = int(off_x + (wx - min_wx) * scale)
                my = int(off_y + (wy - min_wy) * scale)
                raw = self._suit_icon_raw.get(suit) if suit else None
                if raw is not None:
                    pygame.draw.circle(mm_surf, (28, 21, 14, 188),
                                       (mx, my), max(5, int(mark_sz * 0.58)))
                    pygame.draw.circle(mm_surf, (231, 210, 163, 150),
                                       (mx, my), max(5, int(mark_sz * 0.58)), 1)
                    icon = self._get_scaled_icon(
                        ('minimap-region', suit), raw, mark_sz)
                    if icon is not None:
                        icon = icon.copy()
                        icon.set_alpha(205)
                        mm_surf.blit(icon, icon.get_rect(center=(mx, my)))
                elif region_key == 'kathmandu':
                    neutral_clr = (*style.get('label', (235, 218, 184)), 185)
                    pygame.draw.circle(mm_surf, (35, 27, 18, 180),
                                       (mx, my), max(4, mark_sz // 3 + 2))
                    pygame.draw.circle(mm_surf, neutral_clr, (mx, my),
                                       max(3, mark_sz // 3), 2)

            if mine_centers:
                cx = sum(p[0] for p in mine_centers) / len(mine_centers)
                cy = sum(p[1] for p in mine_centers) / len(mine_centers)
                marker_r = max(3, int(min(mm_w, mm_h) * 0.025))
                mine_tile = next((t for t in self.tiles if t.is_mine), None)
                sigil_key = (self._owner_style_key(mine_tile, 'sigil_key')
                             if mine_tile is not None else None)
                sigil_surf = None
                if sigil_key and sigil_key != 'sigil_none':
                    sigil_surf = sigil_cosmetics.render_sigil(
                        sigil_key, marker_r * 4,
                        settings.HEX_MINE_BORDER_HIGHLIGHT)
                if sigil_surf is not None:
                    rect = sigil_surf.get_rect(center=(int(cx), int(cy)))
                    mm_surf.blit(sigil_surf, rect)
                else:
                    pts = [
                        (cx, cy - marker_r * 1.4),
                        (cx + marker_r, cy),
                        (cx, cy + marker_r * 1.4),
                        (cx - marker_r, cy),
                    ]
                    pygame.draw.polygon(mm_surf, (40, 30, 10), pts)
                    pygame.draw.polygon(mm_surf,
                                        settings.HEX_MINE_BORDER_HIGHLIGHT,
                                        pts, 1)

            pygame.draw.rect(mm_surf, settings.MINIMAP_BORDER_CLR,
                             mm_surf.get_rect(), settings.MINIMAP_BORDER_W)
            self._minimap_static_cache_key = static_key
            self._minimap_static_cache = mm_surf
            mm_surf = mm_surf.copy()
        else:
            mm_surf = self._minimap_static_cache.copy()

        # Draw viewport rectangle
        vp_left = off_x + (self.camera_x - min_wx) * scale
        vp_top = off_y + (self.camera_y - min_wy) * scale
        vp_w = self.viewport_rect.w / self.zoom * scale
        vp_h = self.viewport_rect.h / self.zoom * scale
        vp_rect = pygame.Rect(int(vp_left), int(vp_top), int(vp_w), int(vp_h))
        pygame.draw.rect(mm_surf, settings.MINIMAP_VIEWPORT_CLR, vp_rect, 1)

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

    def land_screen_rect(self, land_id):
        """Return the on-screen bounding Rect of a land's hex, or None.

        Returns None when the land is unknown or its centre currently sits
        outside the map viewport, so callers (e.g. tutorial coaching) can fall
        back to a viewport-wide anchor when the land is panned off-screen.
        """
        for tile in self.tiles:
            if tile.land_id != land_id:
                continue
            cx, cy = self.world_to_screen(tile.cx, tile.cy)
            if not self.viewport_rect.collidepoint(cx, cy):
                return None
            half_w = self._size * self.zoom
            half_h = (math.sqrt(3) / 2) * self._size * self.zoom
            return pygame.Rect(int(cx - half_w), int(cy - half_h),
                               int(half_w * 2), int(half_h * 2))
        return None

    def focus_land(self, land_id, *, screen_offset_y=0):
        """Select and centre the map on a land id. Returns the tile if found.

        ``screen_offset_y`` shifts the tile that many pixels *above* the
        viewport centre — used to keep a selected hex visible above the
        anchored land inspector sheet.
        """
        for tile in self.tiles:
            if tile.land_id == land_id:
                self.selected_tile = tile
                self.camera_x = tile.cx - self.viewport_rect.w / (2 * self.zoom)
                self.camera_y = tile.cy - (
                    self.viewport_rect.h / 2 - screen_offset_y) / self.zoom
                self._clamp_camera()
                return tile
        return None

    def focus_lands(self, land_ids, *, fit=False, max_zoom=1.5, padding_px=None):
        """Centre the camera on a set of land IDs and optionally zoom to fit.

        ``fit`` is used for explicit navigation (kingdom chip, leaderboard,
        recenter).  Ordinary refreshes leave camera state untouched.
        """
        if not land_ids:
            return None

        wanted = {land_id for land_id in land_ids if land_id is not None}
        if not wanted:
            return None

        targets = [tile for tile in self.tiles if tile.land_id in wanted]
        if not targets:
            return None

        if fit:
            padding = (padding_px if padding_px is not None
                       else max(20, int(0.06 * min(
                           self.viewport_rect.w, self.viewport_rect.h))))
            min_x = min(tile.cx for tile in targets) - self._size
            max_x = max(tile.cx for tile in targets) + self._size
            half_h = self._size * math.sqrt(3) / 2
            min_y = min(tile.cy for tile in targets) - half_h
            max_y = max(tile.cy for tile in targets) + half_h
            target_w = max(1.0, max_x - min_x)
            target_h = max(1.0, max_y - min_y)
            usable_w = max(1.0, self.viewport_rect.w - padding * 2)
            usable_h = max(1.0, self.viewport_rect.h - padding * 2)
            fit_zoom = min(usable_w / target_w, usable_h / target_h)
            zoom_cap = (settings.HEX_MAP_ZOOM_MAX if max_zoom is None
                        else min(settings.HEX_MAP_ZOOM_MAX, float(max_zoom)))
            self.zoom = max(
                settings.HEX_MAP_ZOOM_MIN,
                min(zoom_cap, fit_zoom),
            )

        if fit:
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
        else:
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

    def focus_on_kingdom(self, *, kingdom_id=None, component_id=None, user_id=None):
        """Pan the camera to a kingdom-component identified by id(s).

        Accepts any combination of ``kingdom_id`` (persistent kingdom), or
        ``component_id`` + ``user_id`` (transient connected component).
        Returns the selected tile if a match was found, else ``None``.
        """
        matches = []
        for tile in self.tiles:
            if kingdom_id is not None and getattr(tile, 'kingdom_id', None) == kingdom_id:
                matches.append(tile)
                continue
            if (component_id is not None
                    and getattr(tile, 'kingdom_component_id', None) == component_id
                    and (user_id is None
                         or getattr(tile, 'owner_user_id', None) == user_id)):
                matches.append(tile)
        if not matches:
            return None
        land_ids = [t.land_id for t in matches]
        return self.focus_lands(land_ids)

    def set_leaderboards(self, top_largest=None, top_realms=None):
        """Register the server-wide top-3 leaderboards for crown overlays.

        ``top_largest`` entries decorate the matching badge group with a
        ``kingdom_{tier}`` icon (largest single connected kingdom).
        ``top_realms`` entries decorate every badge owned by that user with
        a ``lands_{tier}`` icon (greatest total realm).  The dicts map the
        match key to the rank (1, 2 or 3) so the correct icon tier
        (gold/silver/bronce) can be selected at draw time.
        """
        kingdom_ranks = {}
        for entry in (top_largest or []):
            if not isinstance(entry, dict):
                continue
            rank = entry.get('rank')
            if rank not in (1, 2, 3):
                continue
            kid = entry.get('kingdom_id')
            cid = entry.get('kingdom_component_id')
            uid = entry.get('user_id')
            if kid is not None:
                kingdom_ranks[('kingdom', kid)] = rank
            if cid is not None and uid is not None:
                kingdom_ranks[('component', uid, cid)] = rank

        lands_ranks = {}
        for entry in (top_realms or []):
            if not isinstance(entry, dict):
                continue
            rank = entry.get('rank')
            uid = entry.get('user_id')
            if uid is not None and rank in (1, 2, 3):
                lands_ranks[uid] = rank

        # Names kept (``_gold_crown_groups``, ``_silver_wreath_users``) for
        # backward-compat with existing callers; semantics are now
        # ``group_key -> rank`` and ``user_id -> rank`` respectively.
        self._gold_crown_groups = kingdom_ranks
        self._silver_wreath_users = lands_ranks
        # Invalidate the badge cache so crown decoration appears next frame.
        self._kingdom_badges_cache = None
        self._render_cache_key = None
        self._render_cache = None

    _CROWN_TIER_BY_RANK = {1: 'gold', 2: 'silver', 3: 'bronce'}

    def _render_crown_icon(self, category, rank_or_size, size=None):
        """Return a ranking icon surface (cached per category + rank + size).

        Two call forms are supported so the leaderboard panel and the badge
        renderer share one entry point:

        - ``_render_crown_icon('kingdom', 1, 24)`` or
          ``_render_crown_icon('lands', 3, 18)`` — explicit rank.
        - ``_render_crown_icon('gold', 24)`` (legacy two-arg form, kept for
          the leaderboard panel's section header) treats the first arg as a
          tier name and returns the rank-1 ``kingdom`` icon of that tier so
          existing call sites keep working.
        """
        # Legacy two-arg signature: (tier, size).
        if size is None:
            tier = category if category in ('gold', 'silver', 'bronce') else 'gold'
            return self._load_ranking_icon('kingdom', tier, int(rank_or_size))

        rank = int(rank_or_size)
        tier = self._CROWN_TIER_BY_RANK.get(rank)
        if tier is None:
            return None
        cat = category if category in ('kingdom', 'lands') else 'kingdom'
        return self._load_ranking_icon(cat, tier, int(size))

    def _load_ranking_icon(self, category, tier, size):
        """Load + cache one of ``img/kingdom/ranking/{category}_{tier}.png``."""
        s = max(8, int(size))
        key = (category, tier, s)
        cached = self._crown_icon_cache.get(key)
        if cached is not None:
            return cached

        # Lazy raw-asset load.  Failures fall back to ``None`` so callers
        # gracefully skip the icon rather than crashing the map render.
        raw_cache = getattr(self, '_crown_icon_raw_cache', None)
        if raw_cache is None:
            raw_cache = {}
            self._crown_icon_raw_cache = raw_cache
        raw_key = (category, tier)
        raw = raw_cache.get(raw_key)
        if raw is None and raw_key not in raw_cache:
            path = os.path.join('img', 'kingdom', 'ranking',
                                f'{category}_{tier}.png')
            try:
                raw = pygame.image.load(path).convert_alpha()
            except Exception:
                raw = None
                logger.warning(f'Could not load ranking icon: {path}')
            raw_cache[raw_key] = raw
        if raw is None:
            return None

        scaled = pygame.transform.smoothscale(raw, (s, s))
        if len(self._crown_icon_cache) > 32:
            self._crown_icon_cache.pop(next(iter(self._crown_icon_cache)))
        self._crown_icon_cache[key] = scaled
        return scaled

    def _render_champion_icon(self, size):
        """Load/cache the shared Region Champion medal for kingdom badges."""
        s = max(8, int(size))
        key = ('champion', 'fixed', s)
        cached = self._crown_icon_cache.get(key)
        if cached is not None:
            return cached

        raw_cache = getattr(self, '_crown_icon_raw_cache', None)
        if raw_cache is None:
            raw_cache = self._crown_icon_raw_cache = {}
        raw_key = ('champion', 'fixed')
        raw = raw_cache.get(raw_key)
        if raw is None and raw_key not in raw_cache:
            path = os.path.join('img', 'kingdom', 'ranking', 'champion.png')
            try:
                raw = pygame.image.load(path).convert_alpha()
            except Exception:
                raw = None
                logger.warning(f'Could not load ranking icon: {path}')
            raw_cache[raw_key] = raw
        if raw is None:
            return None

        scaled = pygame.transform.smoothscale(raw, (s, s))
        if len(self._crown_icon_cache) > 32:
            self._crown_icon_cache.pop(next(iter(self._crown_icon_cache)))
        self._crown_icon_cache[key] = scaled
        return scaled

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
        self._gold_range = None
