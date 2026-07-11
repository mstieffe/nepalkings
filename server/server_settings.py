# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Aggregated server configuration.

Historically this module was the single home for every server setting.
New configuration should be added as a topic-specific module under
``server/`` (e.g. ``security_settings.py``, ``database_settings.py``)
and re-exported here so existing ``import server_settings as settings``
call sites keep working.

Currently extracted modules:

* :mod:`security_settings` -- ``SECRET_KEY``, ``CORS_ORIGINS``,
  ``RATE_LIMIT_*``, ``TOKEN_EXPIRY_SECONDS``.
* :mod:`database_settings` -- ``DB_URL``, ``DROP_TABLES_ON_STARTUP``.
"""

import os

# ── Re-exports from topic-specific settings modules ───────────────
from security_settings import (  # noqa: F401  (public re-export)
    SECRET_KEY,
    SECRET_KEY_FROM_ENV,
    CORS_ORIGINS,
    MAX_CONTENT_LENGTH,
    RATELIMIT_STORAGE_URI,
    RATE_LIMIT_DEFAULT,
    RATE_LIMIT_LOGIN,
    RATE_LIMIT_LOOKUP,
    RATE_LIMIT_REGISTER,
    TOKEN_EXPIRY_SECONDS,
    LEGAL_PRIVACY_VERSION,
    LEGAL_TERMS_VERSION,
)
from database_settings import (  # noqa: F401  (public re-export)
    DB_URL,
    DROP_TABLES_ON_STARTUP,
)

# Server URL is not security-critical; keep here for now.
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:5000')

# Debug logging
DEBUG_ENABLED = os.getenv('DEBUG_ENABLED', 'False').lower() == 'true'
DEBUG_LOG_PATH = os.getenv('DEBUG_LOG_PATH', '/tmp/nepalkings_debug.log')
DEBUG_LOG_TO_FILE = os.getenv('DEBUG_LOG_TO_FILE', 'False').lower() == 'true'
DEBUG_LOG_MAX_BYTES = int(os.getenv('DEBUG_LOG_MAX_BYTES', '5242880'))  # 5 MB
DEBUG_LOG_BACKUP_COUNT = int(os.getenv('DEBUG_LOG_BACKUP_COUNT', '3'))

# Game Logic
NUM_MAIN_CARDS_START = 12
NUM_SIDE_CARDS_START = 0

NUM_MIN_MAIN_CARDS = 5
NUM_MIN_SIDE_CARDS = 0

MAX_MAIN_HAND_SIZE = 12
MAX_SIDE_HAND_SIZE = 8

INITIAL_TURNS_DEFENDER = 6
INITIAL_TURNS_INVADER = 6

# Game wager / win condition
DEFAULT_GAME_STAKE = 35  # Default gold stake
DEFAULT_GAME_LIMIT = DEFAULT_GAME_STAKE  # Default point threshold to win
MAX_GAME_LIMIT = 100

# New player starting gold
INITIAL_GOLD = 2000

# Auth token settings: TOKEN_EXPIRY_SECONDS now lives in config/security.py
# and is re-exported above. Set a fixed SECRET_KEY env var in production
# so tokens survive restarts.

# First-party analytics (append-only Event table, no third parties).
# See server/analytics.py and scripts/funnel_report.py.
ANALYTICS_ENABLED = os.getenv('ANALYTICS_ENABLED', 'True').lower() == 'true'

# Email verification settings
# Set EMAIL_VERIFICATION_ENABLED=True and configure SMTP to send real emails.
# When disabled (default), the verification URL is logged server-side instead.
EMAIL_VERIFICATION_ENABLED = os.getenv('EMAIL_VERIFICATION_ENABLED', 'False').lower() == 'true'
SMTP_HOST = os.getenv('SMTP_HOST', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SMTP_FROM = os.getenv('SMTP_FROM', 'noreply@nepalkings.local')
SERVER_BASE_URL = os.getenv('SERVER_BASE_URL', SERVER_URL)

# Gameplay notification emails (your-turn / challenge received / result).
# Sent only to offline players who have an email and have not opted out;
# without SMTP_HOST configured the emails are logged instead of sent.
NOTIFY_EMAILS_ENABLED = os.getenv('NOTIFY_EMAILS_ENABLED', 'True').lower() == 'true'
# Public URL of the playable web client, included in notification emails.
WEB_CLIENT_URL = os.getenv('WEB_CLIENT_URL', '')

# Conquer move model rollout flag.
# When True (default), new conquer games are created with conquer_move_model='tactics_hand':
#   - configured battle moves become the player's starting tactics hand
#   - the legacy battle_shop "buy/confirm" phase is skipped
#   - /battle_shop/buy_battle_move and /battle_shop/return_battle_move are gated
# Set CONQUER_TACTICS_HAND_ENABLED=False to roll back to the legacy battle_shop flow.
# Existing open games keep whatever value they were created with.
CONQUER_TACTICS_HAND_ENABLED = os.getenv('CONQUER_TACTICS_HAND_ENABLED', 'True').lower() == 'true'

# AI Opponent settings
AI_USERNAMES = ['[AI] Strategos']  # AI player usernames created at startup
AI_INITIAL_GOLD = 999999  # AI starts with effectively infinite gold
AI_THINK_DELAY = 2  # Seconds of artificial "thinking" delay
AI_ENABLED = os.getenv('AI_ENABLED', 'True').lower() == 'true'

# Strategy planner (bounded multi-turn planning used by duel decision module)
AI_STRATEGY_PLANNER_ENABLED = os.getenv('AI_STRATEGY_PLANNER_ENABLED', 'True').lower() == 'true'
AI_STRATEGY_PLANNER_MAX_PLANS = int(os.getenv('AI_STRATEGY_PLANNER_MAX_PLANS', '5'))
# Base per-turn draw caps used by planner heuristics. Effective assumed draws
# can scale higher with larger free hands via adaptive cap logic.
AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN = int(os.getenv('AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN', '2'))
AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN = int(os.getenv('AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN', '1'))
AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS = float(os.getenv('AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS', '120.0'))

# Blocks non-battle actions when advance+defender are locked and game is waiting
# for fight/fold resolution. Enabled by default; set env var to False to disable.
BATTLE_RESOLUTION_HARD_LOCK_ENABLED = os.getenv('BATTLE_RESOLUTION_HARD_LOCK_ENABLED', 'True').lower() == 'true'

# Watchdog retries for failed AI loops while AI still owns the turn
AI_WATCHDOG_RETRY_DELAY = float(os.getenv('AI_WATCHDOG_RETRY_DELAY', '4.0'))
AI_WATCHDOG_MAX_RETRIES = int(os.getenv('AI_WATCHDOG_MAX_RETRIES', '3'))

# ── v2.0: Collection & Boosters ──
# A small WELCOME GIFT granted at registration and revealed (as gift boxes) in
# the third welcome window: gold (INITIAL_GOLD) + a few booster packs to seed
# the player's permanent collection. Larger amounts are still earned as tutorial
# milestone rewards (and the first conquest win grants its reward pack).
STARTER_BOOSTER_PACKS = 2                   # Welcome-gift main packs
STARTER_BOOSTER_PACKS_SIDE = 1             # Welcome-gift side pack

# Each new player is assigned a random OFFENSIVE (red) suit at registration and
# granted its starter set, so the first conquer attack is always buildable,
# independent of booster luck (see _preassemble_tutorial_conquer_attack in
# routes/kingdom.py). No defensive set is granted: a won conquest converts the
# conquer config into the land's defence config (see routes/games.py), so the
# first defence is "just the conquer config".
OFFENSIVE_SUITS = ('Hearts', 'Diamonds')
DEFENSIVE_SUITS = ('Clubs', 'Spades')

# Rank-based set templates; the suit is filled in per the assigned suit.
# Format: (rank, value).
# Offensive set (red suit): three figures + a Health Boost prelude + three
# tactics. The tactic TYPE follows the card rank (K->Call King, J->Call
# Villager, Q->Block; numbers->Dagger), so the tactic cards mirror the figures'
# key cards (a second K and J, plus a Q):
#   Djungle King (K)          -> villager_red x2, warrior_red x1
#   Small Rice Farm (J + 10)  -> food_red x10  (needs villager_red x1)
#   Gorkha Warriors (A + 9)   -> attacker      (needs warrior_red x1, food_red x9)
#   Health Boost prelude      -> two 3s (boosts the battle figure)
#   Call King (K) / Call Villager (J) / Block (Q)  -> one card each
STARTER_OFFENSIVE_SET = [
    ('K', 4), ('K', 4),       # Djungle King figure + Call King tactic
    ('J', 1), ('J', 1),       # Small Rice Farm figure + Call Villager tactic
    ('A', 3),                 # Gorkha Warriors figure (key)
    ('Q', 2),                 # Block tactic
    ('9', 9), ('10', 10),     # Warriors / Rice Farm number cards
    ('3', 3), ('3', 3),       # Health Boost prelude (two 3s)
]
# Defensive set (black suit): mirrors the offensive with defensive families
#   Himalaya King (K)        -> villager_black x2, warrior_black x1
#   Small Yack Farm (J + 7)  -> food_black x7  (needs villager_black x1)
#   Wooden Fortress (A + 7)  -> defender       (needs warrior_black x1, food_black x7)
#   3x Dagger                -> one number card each (8, 9, 10)
# The Health-Boost prelude uses two RED 3s (see below), independent of suit.
STARTER_DEFENSIVE_SET = [
    ('K', 4), ('A', 3), ('J', 1),
    ('7', 7), ('7', 7),
    ('8', 8), ('9', 9), ('10', 10),
]
# Two red 3s for the defensive Health-Boost prelude, granted in the (red)
# offensive suit so the spell is castable regardless of the black defence suit.
STARTER_DEFENSIVE_PRELUDE_RED_THREES = 2

# Legacy fixed Hearts deck, retained as a fallback when no suit is assigned.
# Format: (rank, suit, value).
STARTER_FIGURE_CARDS = [(_r, 'Hearts', _v) for (_r, _v) in STARTER_OFFENSIVE_SET]
BOOSTER_PACK_PRICE = 100                    # Gold cost per main pack
BOOSTER_PACK_SIDE_PRICE = 100               # Gold cost per side pack
BOOSTER_PACK_CARDS = 3                      # Cards drawn per pack (both types)
DUEL_WINNER_BOOSTER_PACKS = 2              # [DEPRECATED] Legacy: see DUEL_WINNER_REWARD_DRAWS
DUEL_LOSER_BOOSTER_PACKS = 1               # [DEPRECATED] Legacy: see DUEL_LOSER_REWARD_DRAWS
DUEL_BOOSTER_REWARD_PROBABILITIES = {       # [DEPRECATED] superseded by DUEL_REWARD_POOL_PROBABILITIES
    'main': 0.60,
    'side': 0.40,
}

# ── Maps ──
STARTER_MAPS = 0                            # Earned via the first-conquest reward

# ── Duel rewards (pool-based) ──
# Each duel awards N independent draws from a shared reward pool.
DUEL_WINNER_REWARD_DRAWS = 3
DUEL_LOSER_REWARD_DRAWS = 1
DUEL_REWARD_GOLD_AMOUNT = 80                # Gold awarded per 'gold' draw
DUEL_REWARD_POOL_PROBABILITIES = {          # Must sum to 1.0
    'main_booster': 0.25,
    'side_booster': 0.25,
    'map':          0.25,
    'gold':         0.25,
}

BOOSTER_TIER_PROBABILITIES = {              # Probability of drawing each tier (main)
    1: 0.50,   # common
    2: 0.30,   # uncommon
    3: 0.20,   # rare
}
BOOSTER_TIER_RANKS = {                      # Card ranks per tier (main)
    1: ['7', '8', '9'],
    2: ['J', '10', 'A'],
    3: ['K', 'Q'],
}

BOOSTER_SIDE_TIER_PROBABILITIES = {         # Probability of drawing each tier (side)
    1: 0.50,   # common
    2: 0.30,   # uncommon
    3: 0.20,   # rare
}
BOOSTER_SIDE_TIER_RANKS = {                 # Card ranks per tier (side)
    1: ['2', '3'],
    2: ['4', '5'],
    3: ['6'],
}

# Selling prices — key cards = value × multiplier, number cards = face value
KEY_CARD_RANKS = ['J', 'Q', 'K', 'A']
CARD_SELL_KEY_MULTIPLIER = 10               # J→10, Q→20, K→40, A→30

# ── v2.0: Kingdom ──
KINGDOM_MAP_COLS = 75
KINGDOM_MAP_ROWS = 50                        # = 3750 hexes

# Land tiers 1..KINGDOM_TIER_COUNT.  Higher = rarer / more valuable.  The map
# is generated as a "landscape" with one elevation peak per suit cluster, so
# the highest tier appears at the cluster centre.  Future increases of the
# tier count must extend LAND_TIER_PROBABILITIES, LAND_GOLD_RATE_RANGES,
# LAND_SUIT_BONUS_RANGES and ai.defence.config.AI_DEFENCE_GENERATION_RULES
# accordingly.
KINGDOM_TIER_COUNT = 6

# Castle figure cap per land tier.  Players: number of figures with
# ``family.field == 'castle'`` (Kings + Maharaja) must not exceed this on a
# tier-N land (including the pre-placed starting Maharaja).  AI defenders:
# generator emits EXACTLY this many castle figures per tier.
CASTLE_FIGURE_LIMIT_BY_TIER = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}

# Conquer loot bucket classification by card rank.  Every captured card is
# bucketed into either "number" or "key" based on the rank set below; quotas
# are tier-scaled (see ``_conquer_loot_base_quota``).  Must match the client
# constants in ``nepal_kings/config/card_settings.py``.
LOOT_NUMBER_RANKS = frozenset({'3', '6', '7', '8', '9', '10'})
LOOT_KEY_RANKS = frozenset({'2', '4', '5', 'J', 'Q', 'K', 'A', 'MK'})

# Voronoi-style suit clustering: each suit receives exactly this many clusters
# (seed hexes), so all suits always have the same cluster count.
KINGDOM_MAP_CLUSTERS_PER_SUIT = int(os.getenv('KINGDOM_MAP_CLUSTERS_PER_SUIT', '10'))

# Per-cluster radius is sampled from this inclusive range.  Radius is measured
# in anisotropic distance-space and controls how far suit terrain can spread
# before turning neutral.
KINGDOM_MAP_CLUSTER_RADIUS_RANGE = (4, 7)

# Hard cap for tier-1 outer-border thickness.  The seeder clamps sampled
# cluster radius so tier-1 bands never exceed this number of hex layers.
KINGDOM_MAP_TIER1_BORDER_MAX_HEXES = int(
    os.getenv('KINGDOM_MAP_TIER1_BORDER_MAX_HEXES', '3')
)

# Cluster anisotropy (major/minor axis ratio) sampled per cluster.
# 1.0 is circular; higher values produce elongated mountain-range shapes.
KINGDOM_MAP_CLUSTER_ANISOTROPY_RANGE = (1.2, 2.1)

# Deterministic boundary perturbation strength.  0 disables perturbation.
KINGDOM_MAP_BOUNDARY_NOISE_STRENGTH = float(
    os.getenv('KINGDOM_MAP_BOUNDARY_NOISE_STRENGTH', '0.35')
)

# Each cluster's apex is a "plateau" of N hexes (the seed plus a few of its
# neighbours), all at the top tier.  This adds shape variation so apex
# regions are not always a single hex.  Range is (min, max) inclusive.
KINGDOM_MAP_PEAK_PLATEAU_RANGE = (1, 10)

# Sentinel suit name used for neutral lands (no suit bonus).
LAND_NEUTRAL_SUIT = 'Neutral'

LAND_TIER_PROBABILITIES = {1: 0.29, 2: 0.23, 3: 0.18, 4: 0.13, 5: 0.10, 6: 0.07}

# Neutral lands never reach the apex tier; weights are the cluster weights
# minus tier KINGDOM_TIER_COUNT, renormalised to sum to 1.  Truncated to
# tiers 1..(KINGDOM_TIER_COUNT-1) = 1..5 and renormalised from
# LAND_TIER_PROBABILITIES (sum of weights 1..5 = 0.93).
LAND_NEUTRAL_TIER_PROBABILITIES = {
    1: 0.312,
    2: 0.247,
    3: 0.194,
    4: 0.140,
    5: 0.107,
}

LAND_GOLD_RATE_RANGES = {                   # Gold per hour (min, max) per tier
    1: (1, 10),
    2: (10, 20),
    3: (20, 30),
    4: (30, 40),
    5: (40, 50),
    6: (50, 80),
}
LAND_SUIT_BONUS_RANGES = {                  # Suit combat bonus (min, max) per tier
    1: (1, 2),
    2: (2, 4),
    3: (4, 6),
    4: (6, 10),
    5: (10, 14),
    6: (14, 20),
}
CONQUER_COOLDOWN_SECONDS = int(os.getenv('CONQUER_COOLDOWN_SECONDS', str(900)))#str(6 * 3600)))
LAND_CONQUER_PROTECTION_SECONDS = int(
    os.getenv('LAND_CONQUER_PROTECTION_SECONDS', str(5 * 60))
)
# Stuck-conquer-game sweeper: any conquer game still 'active' with no
# activity for this many seconds is auto-resolved with the defender as
# winner.
STUCK_CONQUER_TIMEOUT_SECONDS = int(
    os.getenv('STUCK_CONQUER_TIMEOUT_SECONDS', str(15 * 60))
)
STUCK_CONQUER_SWEEP_INTERVAL_SECONDS = int(
    os.getenv('STUCK_CONQUER_SWEEP_INTERVAL_SECONDS', str(60))
)
POST_BATTLE_CHOICE_TIMEOUT_SECONDS = int(
    os.getenv('POST_BATTLE_CHOICE_TIMEOUT_SECONDS', str(5 * 60))
)
GOLD_PRODUCTION_MAX_ACCUMULATION_HOURS = 7 * 24  # Cap at 7 days of uncollected gold

# ── Kingdom cosmetics ──────────────────────────────────────────────
# Permanent, preset-only cosmetic unlocks.  Each user equips one cosmetic per
# category; owned lands expose the equipped style in /kingdom/map so every
# client can render each kingdom's identity.
KINGDOM_DEFAULT_STYLE = {
    'badge_key': 'badge_plain',
    'border_key': 'border_simple_gold',
    'surface_key': 'surface_plain',
    'color_key': 'color_royal_gold',
    'sigil_key': 'sigil_none',
}

# Owner color palette: curated, gold-purchasable.  Each entry exposes accent
# and glow RGB triples that the client mirrors in
# ``nepal_kings/config/kingdom_settings.py::KINGDOM_COLOR_PALETTE``.
KINGDOM_COLOR_PALETTE = {
    'color_royal_gold': {
        'name': 'Royal Gold',
        'rarity': 'default',
        'price_gold': 0,
        'accent_rgb': (255, 223, 80),
        'glow_rgb':   (255, 210, 70),
    },
    'color_royal_blue': {
        'name': 'Royal Blue',
        'rarity': 'common',
        'price_gold': 300,
        'accent_rgb': (84, 150, 255),
        'glow_rgb':   (54, 110, 220),
    },
    'color_crimson': {
        'name': 'Crimson',
        'rarity': 'common',
        'price_gold': 300,
        'accent_rgb': (224, 60, 80),
        'glow_rgb':   (200, 40, 60),
    },
    'color_emerald': {
        'name': 'Emerald',
        'rarity': 'common',
        'price_gold': 350,
        'accent_rgb': (60, 200, 130),
        'glow_rgb':   (40, 170, 105),
    },
    'color_amethyst': {
        'name': 'Amethyst',
        'rarity': 'rare',
        'price_gold': 800,
        'accent_rgb': (180, 110, 220),
        'glow_rgb':   (150, 80, 200),
    },
    'color_copper': {
        'name': 'Copper',
        'rarity': 'rare',
        'price_gold': 800,
        'accent_rgb': (212, 130, 64),
        'glow_rgb':   (180, 100, 40),
    },
    'color_jade': {
        'name': 'Jade',
        'rarity': 'rare',
        'price_gold': 900,
        'accent_rgb': (110, 200, 170),
        'glow_rgb':   (80, 170, 140),
    },
    'color_ivory': {
        'name': 'Ivory',
        'rarity': 'rare',
        'price_gold': 950,
        'accent_rgb': (240, 232, 208),
        'glow_rgb':   (220, 210, 180),
    },
    'color_obsidian': {
        'name': 'Obsidian',
        'rarity': 'epic',
        'price_gold': 1500,
        'accent_rgb': (110, 110, 130),
        'glow_rgb':   (70, 70, 90),
    },
    'color_sunset': {
        'name': 'Sunset',
        'rarity': 'epic',
        'price_gold': 1600,
        'accent_rgb': (255, 130, 80),
        'glow_rgb':   (230, 90, 60),
    },
    'color_ocean': {
        'name': 'Ocean',
        'rarity': 'epic',
        'price_gold': 1600,
        'accent_rgb': (70, 180, 220),
        'glow_rgb':   (40, 140, 200),
    },
}

# Kingdom sigils: achievement-unlocked only (no gold purchase).  Each sigil
# is gated by a single threshold expressed via ``unlock_kind`` +
# ``unlock_value``.  The client renders procedural glyphs identified by
# ``asset_glyph``.
#
# unlock_kind values:
#   - 'free'                 (always unlocked; the default no-sigil entry)
#   - 'reach_level'          (kingdom.level >= value)
#   - 'conquer_lands'        (lifetime lands conquered >= value)
#   - 'win_battles'          (lifetime battles won >= value)
#   - 'win_conquer_battles'  (lifetime conquer-battles won >= value)
#   - 'own_all_suits'        (player owns at least one land per suit)
#   - 'reach_max_tier'       (owns at least one tier-6 land)
KINGDOM_SIGIL_CATALOG = {
    'sigil_none': {
        'name': 'No Sigil',
        'asset_glyph': 'none',
        'rarity': 'default',
        'unlock_kind': 'free',
        'unlock_value': 0,
    },
    'sigil_mountain': {
        'name': 'Mountain',
        'asset_glyph': 'mountain',
        'rarity': 'common',
        'unlock_kind': 'reach_level',
        'unlock_value': 5,
    },
    'sigil_sword': {
        'name': 'Crossed Swords',
        'asset_glyph': 'sword',
        'rarity': 'common',
        'unlock_kind': 'win_battles',
        'unlock_value': 10,
    },
    'sigil_wolf': {
        'name': 'Wolf',
        'asset_glyph': 'wolf',
        'rarity': 'common',
        'unlock_kind': 'conquer_lands',
        'unlock_value': 5,
    },
    'sigil_lotus': {
        'name': 'Lotus',
        'asset_glyph': 'lotus',
        'rarity': 'rare',
        'unlock_kind': 'reach_level',
        'unlock_value': 10,
    },
    'sigil_tower': {
        'name': 'Tower',
        'asset_glyph': 'tower',
        'rarity': 'rare',
        'unlock_kind': 'conquer_lands',
        'unlock_value': 10,
    },
    'sigil_eagle': {
        'name': 'Eagle',
        'asset_glyph': 'eagle',
        'rarity': 'rare',
        'unlock_kind': 'win_conquer_battles',
        'unlock_value': 10,
    },
    'sigil_sun': {
        'name': 'Sun',
        'asset_glyph': 'sun',
        'rarity': 'rare',
        'unlock_kind': 'own_all_suits',
        'unlock_value': 1,
    },
    'sigil_crescent': {
        'name': 'Crescent',
        'asset_glyph': 'crescent',
        'rarity': 'rare',
        'unlock_kind': 'reach_level',
        'unlock_value': 20,
    },
    'sigil_lion': {
        'name': 'Lion',
        'asset_glyph': 'lion',
        'rarity': 'epic',
        'unlock_kind': 'win_battles',
        'unlock_value': 50,
    },
    'sigil_phoenix': {
        'name': 'Phoenix',
        'asset_glyph': 'phoenix',
        'rarity': 'epic',
        'unlock_kind': 'reach_level',
        'unlock_value': 30,
    },
    'sigil_dragon': {
        'name': 'Dragon',
        'asset_glyph': 'dragon',
        'rarity': 'epic',
        'unlock_kind': 'reach_max_tier',
        'unlock_value': 1,
    },
    'sigil_crown': {
        'name': 'Crown',
        'asset_glyph': 'crown',
        'rarity': 'epic',
        'unlock_kind': 'reach_level',
        'unlock_value': 50,
    },
    'sigil_serpent': {
        'name': 'Serpent',
        'asset_glyph': 'serpent',
        'rarity': 'epic',
        'unlock_kind': 'conquer_lands',
        'unlock_value': 25,
    },
}

KINGDOM_COSMETIC_CATALOG = {
    'badge_plain': {
        'type': 'badge',
        'name': 'Plain Pill',
        'rarity': 'default',
        'price_gold': 0,
        'asset_key': 'badge_plain',
    },
    'badge_parchment_scroll': {
        'type': 'badge',
        'name': 'Parchment Scroll',
        'rarity': 'common',
        'price_gold': 250,
        'asset_key': 'badge_parchment_scroll',
    },
    'badge_iron_plank': {
        'type': 'badge',
        'name': 'Iron Riveted Plank',
        'rarity': 'common',
        'price_gold': 350,
        'asset_key': 'badge_iron_plank',
    },
    'badge_stone_tablet': {
        'type': 'badge',
        'name': 'Stone Tablet',
        'rarity': 'rare',
        'price_gold': 850,
        'asset_key': 'badge_stone_tablet',
    },
    'badge_banner_ribbon': {
        'type': 'badge',
        'name': 'Banner Ribbon',
        'rarity': 'rare',
        'price_gold': 1100,
        'asset_key': 'badge_banner_ribbon',
    },
    'badge_gilded_laurel': {
        'type': 'badge',
        'name': 'Gilded Laurel',
        'rarity': 'epic',
        'price_gold': 1600,
        'asset_key': 'badge_gilded_laurel',
    },
    'badge_obsidian_gems': {
        'type': 'badge',
        'name': 'Obsidian Gems',
        'rarity': 'epic',
        'price_gold': 1750,
        'asset_key': 'badge_obsidian_gems',
    },
    'badge_marble_serpent': {
        'type': 'badge',
        'name': 'Marble Serpent Plaque',
        'rarity': 'epic',
        'price_gold': 1900,
        'asset_key': 'badge_marble_serpent',
    },
    'border_simple_gold': {
        'type': 'border',
        'name': 'Simple Gold Border',
        'rarity': 'default',
        'price_gold': 0,
        'asset_key': 'border_simple_gold',
    },
    'border_royal_blue': {
        'type': 'border',
        'name': 'Royal Blue Border',
        'rarity': 'common',
        'price_gold': 350,
        'asset_key': 'border_royal_blue',
    },
    'border_emerald_carved': {
        'type': 'border',
        'name': 'Emerald Carved Border',
        'rarity': 'rare',
        'price_gold': 1000,
        'asset_key': 'border_emerald_carved',
    },
    'border_obsidian': {
        'type': 'border',
        'name': 'Obsidian Border',
        'rarity': 'rare',
        'price_gold': 1250,
        'asset_key': 'border_obsidian',
    },
    'border_ruby': {
        'type': 'border',
        'name': 'Ruby Border',
        'rarity': 'epic',
        'price_gold': 1750,
        'asset_key': 'border_ruby',
    },
    'border_silver': {
        'type': 'border',
        'name': 'Silver Border',
        'rarity': 'common',
        'price_gold': 450,
        'asset_key': 'border_silver',
    },
    'border_rope_braid': {
        'type': 'border',
        'name': 'Rope Braid Border',
        'rarity': 'common',
        'price_gold': 500,
        'asset_key': 'border_rope_braid',
    },
    'border_thorned': {
        'type': 'border',
        'name': 'Thorned Border',
        'rarity': 'epic',
        'price_gold': 2050,
        'asset_key': 'border_thorned',
    },
    'surface_plain': {
        'type': 'surface',
        'name': 'Plain Ground',
        'rarity': 'default',
        'price_gold': 0,
        'asset_key': 'surface_plain',
    },
    'surface_parchment': {
        'type': 'surface',
        'name': 'Parchment Wash',
        'rarity': 'common',
        'price_gold': 300,
        'asset_key': 'surface_parchment',
    },
    'surface_stone': {
        'type': 'surface',
        'name': 'Stone Pattern',
        'rarity': 'rare',
        'price_gold': 950,
        'asset_key': 'surface_stone',
    },
    'surface_snow': {
        'type': 'surface',
        'name': 'Snow Wash',
        'rarity': 'common',
        'price_gold': 400,
        'asset_key': 'surface_snow',
    },
    'surface_forest': {
        'type': 'surface',
        'name': 'Forest Canopy',
        'rarity': 'rare',
        'price_gold': 1150,
        'asset_key': 'surface_forest',
    },
    'surface_dusk': {
        'type': 'surface',
        'name': 'Dusk Veil',
        'rarity': 'epic',
        'price_gold': 1700,
        'asset_key': 'surface_dusk',
    },
    'surface_grass': {
        'type': 'surface',
        'name': 'Verdant Grass',
        'rarity': 'common',
        'price_gold': 350,
        'asset_key': 'surface_grass',
    },
    'surface_marble': {
        'type': 'surface',
        'name': 'Veined Marble',
        'rarity': 'rare',
        'price_gold': 1100,
        'asset_key': 'surface_marble',
    },
    'surface_lava': {
        'type': 'surface',
        'name': 'Molten Lava',
        'rarity': 'epic',
        'price_gold': 2100,
        'asset_key': 'surface_lava',
    },
}

# Programmatically extend the cosmetic catalog with owner-color SKUs so the
# existing buy/equip flow handles them uniformly with badges/borders/surfaces.
for _color_key, _color in KINGDOM_COLOR_PALETTE.items():
    KINGDOM_COSMETIC_CATALOG[_color_key] = {
        'type': 'color',
        'name': _color['name'],
        'rarity': _color['rarity'],
        'price_gold': int(_color['price_gold']),
        'asset_key': _color_key,
    }

# Sigils are part of the catalog for shop/listing purposes but cannot be
# purchased with gold (price_gold is omitted; client-side shop hides the buy
# button and shows the unlock requirement instead).
for _sigil_key, _sigil in KINGDOM_SIGIL_CATALOG.items():
    KINGDOM_COSMETIC_CATALOG[_sigil_key] = {
        'type': 'sigil',
        'name': _sigil['name'],
        'rarity': _sigil['rarity'],
        'price_gold': 0 if _sigil['unlock_kind'] == 'free' else None,
        'asset_key': _sigil_key,
        'unlock_kind': _sigil['unlock_kind'],
        'unlock_value': _sigil['unlock_value'],
    }

# ── Persistent kingdom configuration ───────────────────────────────
KINGDOM_SHIELD_PRICE_PER_HOUR_PER_LAND = int(
    os.getenv('KINGDOM_SHIELD_PRICE_PER_HOUR_PER_LAND', '6')
)
KINGDOM_SHIELD_DURATION_OPTIONS_HOURS = [6, 12, 24]
KINGDOM_SHIELD_MAX_HOURS = int(os.getenv('KINGDOM_SHIELD_MAX_HOURS', '24'))
KINGDOM_SHIELD_EXTENSION_ENABLED = os.getenv(
    'KINGDOM_SHIELD_EXTENSION_ENABLED', 'True'
).lower() == 'true'

KINGDOM_RENAME_PRICE_GOLD = int(os.environ.get('KINGDOM_RENAME_PRICE_GOLD', '150'))
# Per-user rate limit window for kingdom rename attempts.
KINGDOM_RENAME_RATE_LIMIT_PER_HOUR = int(os.environ.get('KINGDOM_RENAME_RATE_LIMIT_PER_HOUR', '10'))
# Per-user rate limit for any single kingdom mutation (skills, cosmetics, shield).
KINGDOM_MUTATE_RATE_LIMIT = os.environ.get('KINGDOM_MUTATE_RATE_LIMIT', '30 per minute')

# Kingdom progression (levels, XP, skills, gold vault) lives in
# kingdom_progression.py and is re-exported here for ``import server_settings``
# call sites.  Skill definitions are data-driven; add new skills there.
from kingdom_progression import (  # noqa: F401  (public re-export)
    KINGDOM_LEVEL_MAX,
    KINGDOM_SKILL_POINTS_PER_LEVEL,
    KINGDOM_LEVEL_XP_BASE,
    KINGDOM_LEVEL_XP_GROWTH,
    KINGDOM_TIER_XP,
    KINGDOM_SKILL_BASE_COST_CURVE,
    KINGDOM_VAULT_DEFAULT_CAP,
    KINGDOM_MAIN_BOOSTER_PRODUCTION_BASE_HOURS,
    KINGDOM_MAIN_BOOSTER_PRODUCTION_HALVING_FACTOR,
    KINGDOM_MAIN_BOOSTER_PRODUCTION_CAPACITY,
    KINGDOM_SIDE_BOOSTER_PRODUCTION_BASE_HOURS,
    KINGDOM_SIDE_BOOSTER_PRODUCTION_HALVING_FACTOR,
    KINGDOM_SIDE_BOOSTER_PRODUCTION_CAPACITY,
    KINGDOM_MAP_PRODUCTION_BASE_HOURS,
    KINGDOM_MAP_PRODUCTION_HALVING_FACTOR,
    KINGDOM_ATLAS_DEFAULT_CAPACITY,
    KingdomSkillDef,
    KINGDOM_SKILL_DEFINITIONS,
    booster_production_interval_hours,
    booster_production_effect_values,
    map_pending_capacity_for_atlas_level,
    atlas_capacity_effect_values,
    skill_definition,
    skill_keys,
    skill_cost_to_buy_level,
    skill_total_cost_for_level,
    skill_effect_at_level,
    vault_cap_for_skill_level,
    kingdom_xp_required_for_level,
    kingdom_total_xp_for_level,
    kingdom_level_for_total_xp,
    xp_for_land_tier,
)

# AI defence generation rules and safe fallbacks live in ai/defence/config.py.
