# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom / hex-map visual settings."""

import math
from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, _FS, _UI_SCALE, _IS_MOBILE
from config.font_settings import FS_TITLE, FS_SUBTITLE, FS_HEADING, FS_BODY, FS_SMALL, FS_TINY

# ── Hex geometry ────────────────────────────────────────────────────
HEX_SIZE            = int(0.055 * SCREEN_HEIGHT)      # "radius" of flat-top hex
HEX_WIDTH           = HEX_SIZE * 2
HEX_HEIGHT          = int(HEX_SIZE * math.sqrt(3))
HEX_BORDER_W        = max(2, int(0.002 * SCREEN_HEIGHT))

# ── Hex colours ────────────────────────────────────────────────────
HEX_TIER_FILL = {
    1: (110, 140, 90),        # green — common
    2: (140, 130, 80),        # gold-ish — uncommon
    3: (130, 85, 110),        # purple-ish — rare
    4: (170, 60, 70),         # crimson — epic
    5: (150, 48, 60),         # deep red — legendary
    6: (128, 40, 54),         # burnished red — apex
}
HEX_TIER_BORDER = {
    1: (75, 100, 60),
    2: (105, 95, 55),
    3: (95, 55, 80),
    4: (120, 36, 44),
    5: (108, 30, 42),
    6: (86, 22, 34),
}
HEX_EMPTY_BORDER    = (90, 90, 90)         # unclaimed border
HEX_MINE_BORDER     = (250, 221, 0)        # gold border for own lands
HEX_HOVER_BRIGHTEN  = 35                   # added to each RGB channel on hover
HEX_HOVER_BRIGHTEN_KINGDOM = 28            # softer fill boost for the rest of
                                           # the hovered tile's connected kingdom
HEX_HOVER_TILE_OVERLAY_ALPHA = 80          # warm-white wash for the hovered
                                           # tile (stronger than siblings, so
                                           # the focal point stays obvious)
HEX_HOVER_KINGDOM_OVERLAY_ALPHA = 40       # warm-white wash for the rest of
                                           # the hovered tile's kingdom so the
                                           # highlight reads through cosmetics
HEX_SELECT_BORDER   = (255, 255, 255)      # white border for selected hex

# Suit-bonus semantic colours.  Hearts/Diamonds are green; Spades/Clubs are
# blue; neutral lands (no suit bonus) are grey.  Tier controls shade: light
# for tier 1, darker for the apex tier.
HEX_SUIT_TIER_FILL = {
    'green': {
        1: (112, 178, 118),
        2: (64, 135, 78),
        3: (28, 88, 46),
        4: (12, 60, 28),
        5: (14, 54, 28),
        6: (18, 48, 30),
    },
    'blue': {
        1: (104, 162, 206),
        2: (56, 116, 162),
        3: (24, 72, 116),
        4: (12, 46, 80),
        5: (14, 40, 72),
        6: (16, 34, 64),
    },
    'neutral': {
        1: (165, 165, 165),
        2: (130, 130, 130),
        3: (95, 95, 95),
        4: (70, 70, 70),
        5: (58, 58, 58),
        6: (50, 50, 50),
    },
}
HEX_SUIT_TIER_BORDER = {
    'green': {
        1: (76, 124, 80),
        2: (42, 94, 54),
        3: (18, 58, 32),
        4: (8, 38, 18),
        5: (8, 34, 18),
        6: (10, 30, 18),
    },
    'blue': {
        1: (72, 112, 146),
        2: (36, 78, 112),
        3: (16, 46, 78),
        4: (8, 28, 52),
        5: (8, 24, 46),
        6: (10, 22, 40),
    },
    'neutral': {
        1: (110, 110, 110),
        2: (85, 85, 85),
        3: (60, 60, 60),
        4: (40, 40, 40),
        5: (34, 34, 34),
        6: (30, 30, 30),
    },
}
HEX_STAR_FILL       = (255, 222, 78)
HEX_STAR_BORDER     = (100, 70, 20)
HEX_MINE_GLOW_CLR   = (255, 223, 80, 90)
HEX_MINE_GLOW_SOFT_CLR = (255, 210, 70, 45)
# Animated breathing pulse for owner glow.  Period (ms) and amplitude
# (alpha multiplier swing).  Quantized to ``HEX_MINE_GLOW_PULSE_STEPS`` so
# pre-rendered surfaces can be reused frame-to-frame.
HEX_MINE_GLOW_PULSE_PERIOD_MS = 2400
HEX_MINE_GLOW_PULSE_AMPLITUDE = 0.35
HEX_MINE_GLOW_PULSE_STEPS     = 8
HEX_MINE_BADGE_BG   = (80, 55, 10, 220)
HEX_MINE_BADGE_CLR  = (255, 238, 150)
HEX_MINE_BORDER_OUTER = (112, 78, 20)
HEX_MINE_BORDER_HIGHLIGHT = (255, 246, 196)

# Castle figure cap per land tier.  Mirrors server/server_settings.py.
CASTLE_FIGURE_LIMIT_BY_TIER = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}

# ── Kingdom cosmetic render presets ───────────────────────────────
HEX_DEFAULT_OWNER_STYLE = {
    'badge_key': 'badge_plain',
    'border_key': 'border_simple_gold',
    'surface_key': 'surface_plain',
    'color_key': 'color_royal_gold',
    'sigil_key': 'sigil_none',
}

# Owner color palette mirror.  Server source of truth lives in
# ``server/server_settings.py::KINGDOM_COLOR_PALETTE``; keep the two in sync.
# ``accent_rgb`` drives borders / chip accents; ``glow_rgb`` drives the
# breathing pulse around owned hexes.
KINGDOM_COLOR_PALETTE = {
    'color_royal_gold': {
        'name': 'Royal Gold',
        'accent_rgb': (255, 223, 80),
        'glow_rgb':   (255, 210, 70),
    },
    'color_royal_blue': {
        'name': 'Royal Blue',
        'accent_rgb': (84, 150, 255),
        'glow_rgb':   (54, 110, 220),
    },
    'color_crimson': {
        'name': 'Crimson',
        'accent_rgb': (224, 60, 80),
        'glow_rgb':   (200, 40, 60),
    },
    'color_emerald': {
        'name': 'Emerald',
        'accent_rgb': (60, 200, 130),
        'glow_rgb':   (40, 170, 105),
    },
    'color_amethyst': {
        'name': 'Amethyst',
        'accent_rgb': (180, 110, 220),
        'glow_rgb':   (150, 80, 200),
    },
    'color_copper': {
        'name': 'Copper',
        'accent_rgb': (212, 130, 64),
        'glow_rgb':   (180, 100, 40),
    },
    'color_jade': {
        'name': 'Jade',
        'accent_rgb': (110, 200, 170),
        'glow_rgb':   (80, 170, 140),
    },
    'color_ivory': {
        'name': 'Ivory',
        'accent_rgb': (240, 232, 208),
        'glow_rgb':   (220, 210, 180),
    },
    'color_obsidian': {
        'name': 'Obsidian',
        'accent_rgb': (110, 110, 130),
        'glow_rgb':   (70, 70, 90),
    },
    'color_sunset': {
        'name': 'Sunset',
        'accent_rgb': (255, 130, 80),
        'glow_rgb':   (230, 90, 60),
    },
    'color_ocean': {
        'name': 'Ocean',
        'accent_rgb': (70, 180, 220),
        'glow_rgb':   (40, 140, 200),
    },
}
KINGDOM_COLOR_DEFAULT_KEY = 'color_royal_gold'

# Kingdom sigil cosmetics (achievement-unlocked).  Each entry maps to a
# procedural glyph renderer in ``game.components.sigil_cosmetics``.  The
# server is the source of truth for unlock requirements / pricing — the
# client only needs the keys and human-readable names.  ``shape`` selects
# the drawing routine.
KINGDOM_SIGIL_STYLES = {
    'sigil_none':     {'name': 'No Sigil',     'shape': 'none'},
    'sigil_mountain': {'name': 'Mountain',     'shape': 'mountain'},
    'sigil_sword':    {'name': 'Sword',        'shape': 'sword'},
    'sigil_wolf':     {'name': 'Wolf',         'shape': 'wolf'},
    'sigil_lotus':    {'name': 'Lotus',        'shape': 'lotus'},
    'sigil_tower':    {'name': 'Tower',        'shape': 'tower'},
    'sigil_eagle':    {'name': 'Eagle',        'shape': 'eagle'},
    'sigil_sun':      {'name': 'Sun',          'shape': 'sun'},
    'sigil_crescent': {'name': 'Crescent',     'shape': 'crescent'},
    'sigil_lion':     {'name': 'Lion',         'shape': 'lion'},
    'sigil_phoenix':  {'name': 'Phoenix',      'shape': 'phoenix'},
    'sigil_dragon':   {'name': 'Dragon',       'shape': 'dragon'},
    'sigil_crown':    {'name': 'Crown',        'shape': 'crown'},
    'sigil_serpent':  {'name': 'Serpent',      'shape': 'serpent'},
    'sigil_yak':      {'name': 'Yak',          'shape': 'yak'},
    'sigil_stupa':    {'name': 'Stupa',        'shape': 'stupa'},
}
KINGDOM_SIGIL_DEFAULT_KEY = 'sigil_none'

# Kingdom name badge cosmetics.  Each style controls the procedural
# background (fill colours / gradient), frame, and ornaments drawn behind
# the kingdom's name pill.  Renderers live in
# ``game.components.badge_cosmetics`` and aggressively cache the resulting
# surfaces by ``(badge_key, text, font_id, target_h, shimmer_phase_bucket)``
# so the per-frame work is a near-free blit.
HEX_BADGE_STYLES = {
    'badge_plain': {
        'rarity': 'default',
        'shape': 'pill',
        'fill': (80, 55, 10, 220),
        'border': (250, 221, 0),
        'text': (255, 238, 150),
    },
    'badge_parchment_scroll': {
        'rarity': 'common',
        'shape': 'scroll',
        'fill_top': (244, 232, 198, 235),
        'fill_bot': (220, 198, 154, 235),
        'curl_clr': (162, 122, 76),
        'fiber_clr': (180, 152, 110, 70),
        'border': (122, 92, 56),
        'text': (58, 36, 18),
    },
    'badge_iron_plank': {
        'rarity': 'common',
        'shape': 'plank',
        'fill_top': (148, 110, 70, 235),
        'fill_bot': (96, 64, 38, 235),
        'fiber_clr': (60, 36, 18, 90),
        'rivet_clr': (40, 36, 32),
        'rivet_highlight': (210, 200, 188),
        'border': (28, 22, 18),
        'text': (240, 224, 196),
    },
    'badge_stone_tablet': {
        'rarity': 'rare',
        'shape': 'tablet',
        'fill_top': (188, 188, 192, 235),
        'fill_bot': (132, 130, 134, 235),
        'highlight_clr': (224, 224, 226),
        'shadow_clr': (52, 50, 54),
        'border': (74, 72, 76),
        'text': (32, 30, 34),
        'text_highlight': (236, 236, 238),
    },
    'badge_banner_ribbon': {
        'rarity': 'rare',
        'shape': 'swallowtail',
        'fill_top': (188, 52, 60, 240),
        'fill_bot': (124, 28, 36, 240),
        'accent': (250, 220, 138),
        'fold_clr': (96, 22, 28, 110),
        'border': (60, 14, 18),
        'text': (255, 240, 198),
    },
    'badge_gilded_laurel': {
        'rarity': 'epic',
        'shape': 'pill',
        'fill_top': (252, 222, 130, 240),
        'fill_bot': (196, 154, 60, 240),
        'highlight_clr': (255, 244, 196, 220),
        'border': (124, 90, 28),
        'text': (62, 36, 8),
        'laurel_clr': (172, 132, 48),
        'laurel_highlight': (244, 222, 138),
        'shimmer': True,
    },
    'badge_obsidian_gems': {
        'rarity': 'epic',
        'shape': 'pill',
        'fill_top': (44, 44, 50, 245),
        'fill_bot': (12, 12, 18, 245),
        'highlight_clr': (130, 130, 142, 200),
        'border': (190, 190, 200),
        'text': (236, 232, 244),
        'gem_left':  (224, 46, 70),
        'gem_right': (90, 132, 232),
        'gem_glow_left':  (255, 96, 120, 0),
        'gem_glow_right': (140, 180, 255, 0),
        'shimmer': True,
    },
    'badge_marble_serpent': {
        'rarity': 'epic',
        'shape': 'plaque',
        'fill_top': (240, 236, 228, 240),
        'fill_bot': (210, 204, 192, 240),
        'vein_clr': (118, 108, 132, 180),
        'border': (124, 96, 36),
        'scrollwork_clr': (180, 144, 56),
        'serpent_clr': (132, 96, 36),
        'serpent_eye': (224, 64, 64),
        'text': (44, 30, 36),
        'shimmer': True,
    },
    'badge_wax_seal': {
        'rarity': 'rare',
        'shape': 'seal',
        'fill_top': (52, 40, 34, 242),
        'fill_bot': (28, 20, 16, 242),
        'border': (168, 128, 62),
        'text': (238, 214, 170),
        'wax_clr': (188, 40, 44),
        'wax_dark': (118, 18, 24),
        'wax_highlight': (255, 154, 150),
    },
}

HEX_BADGE_DEFAULT_KEY = 'badge_plain'

# Border skins.  Each skin has an edge ``style`` that controls *structural*
# drawing (single line, double rope braid, carved notches, spikes, gem
# cabochons, dashed double-line, thorned vine).  Rarity gates premium polish
# (vertex ornaments are added at rare+ tier).
HEX_BORDER_SKINS = {
    'border_simple_gold': {
        'outer': (112, 78, 20),
        'main': (250, 221, 0),
        'highlight': (255, 246, 196),
        'width_bonus': 0,
        'style': 'simple',
        'rarity': 'default',
    },
    'border_royal_blue': {
        'outer': (18, 46, 100),
        'main': (84, 150, 255),
        'highlight': (210, 232, 255),
        'width_bonus': 1,
        'style': 'rope_braid',
        'rarity': 'common',
    },
    'border_silver': {
        'outer': (86, 92, 100),
        'main': (206, 216, 226),
        'highlight': (255, 255, 255),
        'width_bonus': 0,
        'style': 'dashed_double',
        'rarity': 'common',
    },
    'border_rope_braid': {
        'outer': (60, 36, 18),
        'main': (188, 132, 70),
        'highlight': (244, 210, 152),
        'width_bonus': 1,
        'style': 'rope_braid',
        'rarity': 'common',
    },
    'border_emerald_carved': {
        'outer': (10, 66, 42),
        'main': (58, 220, 128),
        'highlight': (212, 255, 225),
        'width_bonus': 1,
        'style': 'carved_notches',
        'rarity': 'rare',
    },
    'border_obsidian': {
        'outer': (8, 8, 12),
        'main': (52, 54, 68),
        'highlight': (176, 176, 194),
        'width_bonus': 1,
        'style': 'spikes',
        'rarity': 'rare',
    },
    'border_ruby': {
        # Deep jewel tones — bright pink reads as candy, not ruby.
        'outer': (64, 6, 16),
        'main': (178, 26, 48),
        'highlight': (255, 172, 186),
        'width_bonus': 1,
        'style': 'gem_cabochons',
        'rarity': 'epic',
    },
    'border_thorned': {
        'outer': (38, 24, 18),
        'main': (132, 88, 60),
        'highlight': (228, 200, 168),
        'width_bonus': 1,
        'style': 'thorned_vine',
        'rarity': 'epic',
    },
    'border_bamboo': {
        'outer': (44, 68, 30),
        'main': (150, 178, 94),
        'highlight': (222, 238, 170),
        'width_bonus': 1,
        'style': 'bamboo_stalks',
        'rarity': 'common',
    },
    'border_prayer_flags': {
        # Rope palette; the five traditional flag colours live in the
        # ``prayer_flags`` edge renderer.
        'outer': (66, 48, 30),
        'main': (172, 138, 92),
        'highlight': (240, 220, 180),
        'width_bonus': 1,
        'style': 'prayer_flags',
        'rarity': 'epic',
    },
}

# Surface skins.  ``style`` selects the procedural pattern; the renderer
# (`game.components.hex_cosmetics`) caches the rendered hex art per
# (skin_key, hex_size).  Surfaces at rare+ rarity get a faint center emblem.
HEX_SURFACE_SKINS = {
    'surface_plain': {
        'style': 'starter',
        'rarity': 'default',
        # Subtle warm parchment-like wash + faint diagonal cross-hatch so a
        # newly-claimed hex reads as "yours" even without a premium surface.
        # Alphas are kept low so the underlying suit-bonus fill stays primary.
        'base_clr_top':  (236, 220, 184, 95),
        'base_clr_bot':  (196, 174, 128, 95),
        'hatch_clr':     (96, 72, 36, 32),
        'vignette_clr':  (32, 22, 12, 70),
        'emblem': None,
    },
    'surface_parchment': {
        'style': 'parchment',
        'rarity': 'common',
        'base_clr_top':  (250, 232, 188, 215),
        'base_clr_bot':  (228, 198, 144, 215),
        'ink_clr':       (118, 76, 32, 175),
        'stain_clr':     (96, 56, 22, 95),
        'emblem': 'feather',
    },
    'surface_grass': {
        'style': 'grass',
        'rarity': 'common',
        'base_clr':      (86, 142, 64, 210),
        'blade_dark':    (44, 96, 36, 220),
        'blade_light':   (164, 200, 110, 220),
        'flower_clrs':   ((250, 244, 200, 220), (242, 198, 220, 220),
                          (240, 240, 240, 220)),
        'emblem': None,
    },
    'surface_snow': {
        'style': 'snow',
        'rarity': 'common',
        'base_clr_center': (246, 252, 255, 220),
        'base_clr_rim':    (188, 220, 240, 220),
        'flake_clr':       (255, 255, 255, 235),
        'halo_clr':        (255, 255, 255, 80),
        'emblem': None,
    },
    'surface_stone': {
        'style': 'cobblestone',
        'rarity': 'rare',
        'base_clr':      (180, 178, 172, 210),
        'mortar_clr':    (52, 50, 48, 230),
        'highlight_clr': (220, 218, 210, 200),
        'shadow_clr':    (110, 108, 102, 180),
        'emblem': 'arch',
    },
    'surface_forest': {
        'style': 'forest_canopy',
        'rarity': 'rare',
        'base_clr':      (32, 78, 44, 215),
        'leaf_dark':     (52, 116, 64, 230),
        'leaf_light':    (108, 184, 102, 230),
        'dapple_clr':    (224, 240, 158, 145),
        'emblem': 'leaf',
    },
    'surface_marble': {
        'style': 'marble',
        'rarity': 'rare',
        'base_clr':      (240, 236, 228, 215),
        'vein_clr':      (118, 108, 132, 165),
        'vein_dark':     (78, 70, 92, 145),
        'highlight_clr': (255, 252, 244, 130),
        'emblem': 'column',
    },
    'surface_dusk': {
        'style': 'dusk_stars',
        'rarity': 'epic',
        'base_clr_center': (90, 50, 156, 225),
        'base_clr_rim':    (20, 14, 52, 230),
        'star_clr':        (250, 226, 132, 230),
        'star_clr_alt':    (200, 180, 240, 220),
        'emblem': 'crescent',
    },
    'surface_lava': {
        'style': 'lava',
        'rarity': 'epic',
        'base_clr_center': (132, 36, 16, 230),
        'base_clr_rim':    (28, 10, 8, 235),
        'crack_clr':       (255, 156, 60, 235),
        'crack_core_clr':  (255, 232, 140, 230),
        'ember_clr':       (255, 196, 96, 230),
        'emblem': 'flame',
    },
    'surface_sand': {
        'style': 'dunes',
        'rarity': 'common',
        'base_clr_top':    (232, 202, 142, 215),
        'base_clr_bot':    (198, 158, 96, 215),
        'ridge_clr':       (156, 116, 62, 190),
        'ridge_highlight': (250, 228, 176, 200),
        'emblem': None,
    },
    'surface_crystal': {
        'style': 'crystal',
        'rarity': 'epic',
        'base_clr_center': (36, 66, 110, 225),
        'base_clr_rim':    (14, 26, 52, 235),
        'face_light':      (150, 214, 255, 215),
        'face_dark':       (74, 132, 208, 205),
        'edge_clr':        (226, 246, 255, 235),
        'sparkle_clr':     (255, 255, 255, 220),
        'emblem': 'shard',
    },
}

# ── Owner colouring ────────────────────────────────────────────────
HEX_OWNER_ALPHA     = 110                  # overlay alpha for owner tint

# ── Camera / viewport ──────────────────────────────────────────────
HEX_MAP_ZOOM_MIN    = 0.04   # permits a complete 96x50 fit in portrait
HEX_MAP_ZOOM_MAX    = 4.0
HEX_MAP_ZOOM_FACTOR = 1.35  # proportional per wheel/button notch
HEX_MAP_DRAG_THRESHOLD = 5                 # px before drag starts
# Progressive disclosure thresholds for per-tile overlays.
HEX_MAP_LAND_INFO_MIN_ZOOM       = 1.5    # icons (stat strip, tier ribbon)
HEX_MAP_LAND_NUMBERS_MIN_ZOOM    = 2.0    # numeric labels appear here and above
HEX_MAP_OWNER_NAME_MIN_ZOOM      = 2.0    # below this owner chip is dot only

# ── Historic regions / progressive map presentation ────────────────
# Geography is intentionally quieter than ownership.  Tints and procedural
# landmarks are overview aids; they fade before per-land information appears.
KINGDOM_REGIONS = {
    'karnali': {
        'name': 'Karnali',
        'dominant_suit': 'Spades',
        'tint': (112, 133, 154),
        'label': (224, 234, 240),
        'terrain': 'mountain',
    },
    'kirat': {
        'name': 'Kirat',
        'dominant_suit': 'Clubs',
        'tint': (93, 130, 103),
        'label': (220, 236, 218),
        'terrain': 'foothill',
    },
    'kathmandu': {
        'name': 'Kathmandu Valley',
        'dominant_suit': None,
        'tint': (180, 151, 104),
        'label': (248, 226, 184),
        'terrain': 'valley',
    },
    'lumbini': {
        'name': 'Lumbini',
        'dominant_suit': 'Hearts',
        'tint': (157, 109, 118),
        'label': (244, 218, 222),
        'terrain': 'forest',
    },
    'mithila': {
        'name': 'Mithila',
        'dominant_suit': 'Diamonds',
        'tint': (173, 132, 82),
        'label': (248, 224, 183),
        'terrain': 'fields',
    },
}
REGION_TINT_ALPHA_MAX = 118
REGION_PRESENTATION_FULL_ZOOM = 0.90
REGION_PRESENTATION_END_ZOOM = 1.35
REGION_BOUNDARY_CLR = (255, 231, 174, 215)
REGION_BOUNDARY_SHADOW_CLR = (42, 31, 20, 145)
REGION_BOUNDARY_ANALYTIC_CLR = (232, 222, 205, 105)
REGION_LABEL_SHADOW_CLR = (10, 8, 6, 185)
REGION_SCENERY_ALPHA = 92
# Outer-region scenery follows the larger connected suit clusters. Symbol
# area scales with cluster area; Kathmandu retains its one fixed valley mark.
REGION_SCENERY_CLUSTER_MIN_TILES = 20
REGION_SCENERY_CLUSTER_REFERENCE_TILES = 80
REGION_SCENERY_CLUSTER_SCALE_MIN = 0.65
REGION_SCENERY_CLUSTER_SCALE_MAX = 1.45
# Crossfade from one dominant suit icon per historic region to one icon per
# connected suit cluster. Per-land suit icons take over at
# HEX_MAP_LAND_NUMBERS_MIN_ZOOM.
REGION_CLUSTER_ICON_START_ZOOM = 0.82
REGION_CLUSTER_ICON_FULL_ZOOM = 1.00

# ── Minimap ─────────────────────────────────────────────────────────
_KINGDOM_PORTRAIT_UI = _IS_MOBILE and SCREEN_HEIGHT > SCREEN_WIDTH
MINIMAP_W           = int((0.23 if _KINGDOM_PORTRAIT_UI else 0.12) * SCREEN_WIDTH)
MINIMAP_H           = int((0.07 if _KINGDOM_PORTRAIT_UI else 0.11) * SCREEN_HEIGHT)
MINIMAP_MARGIN      = int(0.015 * SCREEN_HEIGHT)
MINIMAP_BG_CLR      = (20, 20, 20, 180)
MINIMAP_BORDER_CLR  = (180, 160, 130)
MINIMAP_BORDER_W    = 1
MINIMAP_VIEWPORT_CLR = (255, 255, 255, 120)

# ── Leaderboard panel (top-left of map viewport) ───────────────────
# Width matches the minimap so the two anchored corners read as siblings;
# height fits two 3-row sections plus optional "You: #N" lines.
LEADERBOARD_PANEL_W = int(0.155 * SCREEN_WIDTH)
LEADERBOARD_PANEL_H = int((0.46 if _IS_MOBILE else 0.24) * SCREEN_HEIGHT)

# ── Info panel (top of screen) ──────────────────────────────────────
KINGDOM_INFO_FONT_SIZE  = FS_BODY
KINGDOM_INFO_CLR        = (250, 221, 0)
KINGDOM_INFO_BG_CLR     = (20, 20, 20, 140)
KINGDOM_INFO_PAD_X      = int(0.012 * SCREEN_WIDTH)
KINGDOM_INFO_PAD_Y      = int(0.008 * SCREEN_HEIGHT)

# ── Kingdom map frame / activity panel ─────────────────────────────
KINGDOM_PANEL_GAP       = int(0.014 * SCREEN_WIDTH)
KINGDOM_HEADER_H        = int(0.105 * SCREEN_HEIGHT)
KINGDOM_ACTIVITY_W      = int(0.215 * SCREEN_WIDTH)
KINGDOM_MAP_FRAME_PAD   = int(0.010 * SCREEN_HEIGHT)
KINGDOM_MAP_FRAME_BG    = (42, 31, 22, 150)
KINGDOM_MAP_FRAME_BORDER = (166, 142, 96)
KINGDOM_MAP_FRAME_BORDER_W = 2
KINGDOM_ACTIVITY_BG     = (22, 20, 28, 205)
KINGDOM_ACTIVITY_BORDER = (160, 150, 180)
KINGDOM_ACTIVITY_TAB_BG = (46, 43, 58, 220)
KINGDOM_ACTIVITY_TAB_ACTIVE_BG = (80, 72, 102, 235)
KINGDOM_ACTIVITY_ROW_BG = (36, 34, 45, 175)
KINGDOM_ACTIVITY_ROW_H  = (
    max(int(0.072 * SCREEN_HEIGHT), int(0.165 * SCREEN_HEIGHT))
    if _IS_MOBILE else int(0.072 * SCREEN_HEIGHT)
)
KINGDOM_ACTIVITY_TEXT_CLR = (222, 218, 205)
KINGDOM_ACTIVITY_DIM_CLR = (155, 148, 135)
KINGDOM_ACTIVITY_GOOD_CLR = (130, 215, 135)
KINGDOM_ACTIVITY_BAD_CLR = (230, 120, 105)

# ── Kingdom config / skills icons ─────────────────────────────────
# These are deliberately client-configured so future custom artwork can be
# swapped in without changing the kingdom skill logic.
KINGDOM_SHIELD_ICON_PATH = 'img/battle/icons/block.png'
KINGDOM_SKILL_ICON_PATHS = {
    'gold_production': 'img/kingdom/skill_icons/gold.png',
    'gold_vault': 'img/kingdom/skill_icons/gold_vault.png',
    'main_booster_production': 'img/kingdom/skill_icons/main_booster_production.png',
    'side_booster_production': 'img/kingdom/skill_icons/side_booster_production.png',
    'map_production': 'img/kingdom/skill_icons/map_production.png',
    'atlas': 'img/kingdom/skill_icons/atlas.png',
    'shield_cost_reduction': 'img/kingdom/skill_icons/shield.png',
    'core_protection': 'img/kingdom/skill_icons/core_protection.png',
    'loot_chance': 'img/kingdom/skill_icons/loot_chance.png',
}

# ── Kingdom level / XP / vault UI constants ───────────────────────
KINGDOM_LEVEL_HEADER_FONT_SIZE = FS_HEADING
KINGDOM_LEVEL_HEADER_CLR       = (242, 222, 156)
KINGDOM_XP_BAR_H               = max(8, int(0.011 * SCREEN_HEIGHT))
KINGDOM_XP_BAR_TRACK_CLR       = (52, 48, 60)
KINGDOM_XP_BAR_FILL_CLR        = (104, 196, 232)
KINGDOM_XP_BAR_BORDER_CLR      = (172, 152, 102)
KINGDOM_XP_BAR_TEXT_CLR        = (226, 218, 204)

KINGDOM_VAULT_BAR_H            = max(10, int(0.014 * SCREEN_HEIGHT))
KINGDOM_VAULT_BAR_TRACK_CLR    = (40, 36, 28)
KINGDOM_VAULT_BAR_FILL_CLR     = (240, 200, 80)
KINGDOM_VAULT_BAR_NEAR_CLR     = (236, 156, 60)   # ≥80%
KINGDOM_VAULT_BAR_FULL_CLR     = (224, 92, 76)    # at cap
KINGDOM_VAULT_BAR_BORDER_CLR   = (172, 152, 102)
KINGDOM_VAULT_NEAR_FULL_RATIO  = 0.80

# Floating "+amount" collect text
COLLECT_FLOAT_DURATION_MS      = 900
COLLECT_FLOAT_RISE_PX          = int(0.07 * SCREEN_HEIGHT)
COLLECT_FLOAT_FONT_SIZE        = FS_HEADING
COLLECT_FLOAT_GOLD_CLR         = (250, 224, 110)
COLLECT_FLOAT_XP_CLR           = (132, 210, 244)
COLLECT_FLOAT_LEVEL_CLR        = (250, 196, 92)
COLLECT_FLOAT_STAGGER_MS       = 80

# ── Kingdom config screen layout ──────────────────────────────────
KINGDOM_CONFIG_MARGIN = int(0.035 * SCREEN_WIDTH)
KINGDOM_CONFIG_TOP = int(0.105 * SCREEN_HEIGHT)
KINGDOM_CONFIG_PANEL_GAP = int(0.018 * SCREEN_WIDTH)
KINGDOM_CONFIG_LEFT_W = int(0.39 * SCREEN_WIDTH)
KINGDOM_CONFIG_CARD_H = int(0.155 * SCREEN_HEIGHT)
KINGDOM_CONFIG_SHIELD_H = (
    max(int(0.17 * SCREEN_HEIGHT), int(0.285 * SCREEN_HEIGHT))
    if _IS_MOBILE else int(0.17 * SCREEN_HEIGHT)
)
KINGDOM_CONFIG_SKILL_ROW_H = int(0.105 * SCREEN_HEIGHT)
KINGDOM_CONFIG_PANEL_BG = (24, 21, 28, 225)
KINGDOM_CONFIG_PANEL_BORDER = (176, 154, 108)
KINGDOM_CONFIG_CARD_BG = (38, 34, 46, 220)
KINGDOM_CONFIG_CARD_ACTIVE_BG = (62, 54, 76, 235)
KINGDOM_CONFIG_TEXT_CLR = (226, 218, 204)
KINGDOM_CONFIG_DIM_CLR = (156, 146, 132)
KINGDOM_CONFIG_HIGHLIGHT = (232, 190, 104)
KINGDOM_CONFIG_GOOD_CLR = (132, 220, 142)
KINGDOM_CONFIG_BAD_CLR = (226, 112, 96)

# Rarity accents for cosmetic shop rows / chip frames.  Warm-shifted so
# they sit inside the game's parchment-and-gold palette.
COSMETIC_RARITY_COLORS = {
    'default':   (150, 142, 128),
    'common':    (184, 172, 148),
    'uncommon':  (150, 196, 140),
    'rare':      (118, 170, 222),
    'epic':      (194, 128, 236),
    'legendary': (250, 196, 92),
}
COSMETIC_RARITY_LABELS = {
    'default':   'Standard',
    'common':    'Common',
    'uncommon':  'Uncommon',
    'rare':      'Rare',
    'epic':      'Epic',
    'legendary': 'Legendary',
}

# ── Hex labels ──────────────────────────────────────────────────────
HEX_LABEL_FONT_SIZE     = FS_BODY
HEX_ICON_SIZE           = int(0.028 * SCREEN_HEIGHT)
HEX_GOLD_ICON_PATH      = 'img/dialogue_box/icons/coin.png'

# ── Shared pill design tokens (for stat strip, badges, owner chip) ─
HEX_PILL_BG_CLR         = (18, 16, 13, 215)
HEX_PILL_BORDER_CLR     = (166, 142, 96)
HEX_PILL_BORDER_OWN     = (250, 221, 0)
HEX_PILL_RADIUS_PX      = max(2, int(0.004 * SCREEN_HEIGHT))
HEX_PILL_PAD_X          = max(3, int(0.004 * SCREEN_WIDTH))
HEX_PILL_PAD_Y          = max(1, int(0.003 * SCREEN_HEIGHT))

# ── Tier ribbon (top-left corner) ──────────────────────────────────
HEX_TIER_RIBBON_BG      = (24, 20, 12, 220)
HEX_TIER_RIBBON_TIER_TINT = {
    1: (124, 188, 132),
    2: (216, 188, 96),
    3: (188, 132, 220),
    4: (224, 92, 96),
}
HEX_TIER_RIBBON_STAR_SZ_FACTOR = 0.11   # of hex sz; clamped to >= 4 px

# ── Defence-incomplete warning badge ───────────────────────────────
HEX_WARNING_BG_CLR      = (188, 36, 36, 230)
HEX_WARNING_BORDER_CLR  = (255, 220, 200)
HEX_WARNING_TEXT_CLR    = (255, 255, 255)
HEX_WARNING_PULSE_HZ    = 1.4   # alpha pulse cycles per second

# ── Owner chip (colored dot + name pill) ───────────────────────────
HEX_OWNER_CHIP_BG       = (22, 20, 16, 210)
HEX_OWNER_CHIP_BORDER   = (140, 130, 110)
HEX_OWNER_CHIP_OWN_TXT  = (255, 238, 150)
HEX_OWNER_CHIP_OTHER_TXT = (220, 215, 200)
HEX_OWNER_CHIP_DOT_R_FACTOR = 0.07   # of hex sz

# ── Hover ring ─────────────────────────────────────────────────────
HEX_HOVER_RING_CLR      = (255, 255, 255, 165)
HEX_HOVER_RING_W        = 2

# ── Kingdom group badge polish ─────────────────────────────────────
# Positive offset means *below* the cluster centre (nameplate plinth).  An
# extra gap factor (relative to hex sz) keeps the badge clear of the suit
# cluster icon's silhouette.
HEX_GROUP_BADGE_OFFSET_Y = 0.55     # fraction of hex sz below geometric center
HEX_GROUP_BADGE_GAP_FACTOR = 0.10
HEX_GROUP_BADGE_SHADOW_CLR = (0, 0, 0, 140)
HEX_GROUP_BADGE_SHADOW_OFFSET = (1, 2)

# ── Land detail box ────────────────────────────────────────────────
LAND_DETAIL_W           = int(0.28 * SCREEN_WIDTH)
LAND_DETAIL_PAD         = int(0.018 * SCREEN_HEIGHT)
LAND_DETAIL_BG_CLR      = (30, 25, 20, 230)
LAND_DETAIL_BORDER_CLR  = (180, 160, 130)
LAND_DETAIL_BORDER_W    = 2
LAND_DETAIL_CORNER_R    = int(0.008 * SCREEN_HEIGHT)
LAND_DETAIL_TITLE_FONT  = FS_SUBTITLE
LAND_DETAIL_BODY_FONT   = FS_BODY
LAND_DETAIL_SMALL_FONT  = FS_SMALL
LAND_DETAIL_TITLE_CLR   = (250, 221, 0)
LAND_DETAIL_TEXT_CLR     = (220, 210, 195)
LAND_DETAIL_DIM_CLR      = (140, 130, 120)
LAND_DETAIL_BTN_W       = int(0.18 * SCREEN_WIDTH)
LAND_DETAIL_BTN_H       = int(0.045 * SCREEN_HEIGHT)

# ── Suit icon paths (reused from card settings) ────────────────────
SUIT_ICON_PATHS = {
    'Hearts':   'img/suits/hearts.png',
    'Diamonds': 'img/suits/diamonds.png',
    'Clubs':    'img/suits/clubs.png',
    'Spades':   'img/suits/spades.png',
}

# ── Tier star labels ────────────────────────────────────────────────
TIER_LABELS = {
    1: '\u2605',
    2: '\u2605\u2605',
    3: '\u2605\u2605\u2605',
    4: '\u2605\u2605\u2605\u2605',
}

# ── Navigation buttons ─────────────────────────────────────────────
NAV_BTN_SIZE        = int(0.04 * SCREEN_HEIGHT)
NAV_BTN_MARGIN      = int(0.012 * SCREEN_HEIGHT)
NAV_BTN_BG_CLR      = (40, 35, 30, 200)
NAV_BTN_BORDER_CLR  = (160, 140, 110)
NAV_BTN_TEXT_CLR    = (220, 210, 195)
NAV_BTN_HOVER_CLR   = (250, 221, 0)
