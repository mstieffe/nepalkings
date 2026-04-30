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
    RATE_LIMIT_DEFAULT,
    RATE_LIMIT_LOGIN,
    RATE_LIMIT_REGISTER,
    TOKEN_EXPIRY_SECONDS,
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

# Game win condition
DEFAULT_GAME_STAKE = 35  # Default gold stake / point threshold to win

# New player starting gold
INITIAL_GOLD = 100000

# Auth token settings: TOKEN_EXPIRY_SECONDS now lives in config/security.py
# and is re-exported above. Set a fixed SECRET_KEY env var in production
# so tokens survive restarts.

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

# AI Opponent settings
AI_USERNAMES = ['[AI] Strategos']  # AI player usernames created at startup
AI_INITIAL_GOLD = 999999  # AI starts with effectively infinite gold
AI_THINK_DELAY = 2  # Seconds of artificial "thinking" delay
AI_OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')  # OpenAI API key
AI_MODEL = os.getenv('AI_MODEL', 'gpt-4.1-mini')  # LLM model name
AI_PROVIDER = os.getenv('AI_PROVIDER', 'openai')  # LLM provider
AI_ENABLED = os.getenv('AI_ENABLED', 'True').lower() == 'true'
AI_CHAT_ENABLED = os.getenv('AI_CHAT_ENABLED', 'True').lower() == 'true'
AI_CHAT_CHANCE = float(os.getenv('AI_CHAT_CHANCE', '0.22'))
AI_CHAT_MIN_SECONDS_BETWEEN = float(os.getenv('AI_CHAT_MIN_SECONDS_BETWEEN', '35'))
AI_CHAT_MAX_PER_GAME = int(os.getenv('AI_CHAT_MAX_PER_GAME', '12'))
AI_CHAT_LLM_TEMPERATURE = float(os.getenv('AI_CHAT_LLM_TEMPERATURE', '0.75'))
AI_CHAT_LLM_MAX_TOKENS = int(os.getenv('AI_CHAT_LLM_MAX_TOKENS', '90'))

# Strategy planner (bounded multi-turn planning context for the LLM)
AI_STRATEGY_PLANNER_ENABLED = os.getenv('AI_STRATEGY_PLANNER_ENABLED', 'True').lower() == 'true'
AI_STRATEGY_PLANNER_MAX_PLANS = int(os.getenv('AI_STRATEGY_PLANNER_MAX_PLANS', '5'))
# Base per-turn draw caps used by planner heuristics. Effective assumed draws
# can scale higher with larger free hands via adaptive cap logic.
AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN = int(os.getenv('AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN', '2'))
AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN = int(os.getenv('AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN', '1'))
AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK = (
    os.getenv('AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK', 'True').lower() == 'true'
)
AI_STRATEGY_PLANNER_SHADOW_MODE = os.getenv('AI_STRATEGY_PLANNER_SHADOW_MODE', 'False').lower() == 'true'
AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS = float(os.getenv('AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS', '120.0'))

# Blocks non-battle actions when advance+defender are locked and game is waiting
# for fight/fold resolution. Enabled by default; set env var to False to disable.
BATTLE_RESOLUTION_HARD_LOCK_ENABLED = os.getenv('BATTLE_RESOLUTION_HARD_LOCK_ENABLED', 'True').lower() == 'true'

# LLM reliability
AI_LLM_TIMEOUT_SECONDS = float(os.getenv('AI_LLM_TIMEOUT_SECONDS', '12'))
AI_LLM_MAX_RETRIES = int(os.getenv('AI_LLM_MAX_RETRIES', '2'))
AI_LLM_RETRY_BACKOFF_SECONDS = float(os.getenv('AI_LLM_RETRY_BACKOFF_SECONDS', '1.0'))

# Watchdog retries for failed AI loops while AI still owns the turn
AI_WATCHDOG_RETRY_DELAY = float(os.getenv('AI_WATCHDOG_RETRY_DELAY', '4.0'))
AI_WATCHDOG_MAX_RETRIES = int(os.getenv('AI_WATCHDOG_MAX_RETRIES', '3'))

# ── v2.0: Collection & Boosters ──
STARTER_BOOSTER_PACKS = 5                   # Free main-card packs on registration
STARTER_BOOSTER_PACKS_SIDE = 2              # Free side-card packs on registration
BOOSTER_PACK_PRICE = 100                    # Gold cost per main pack
BOOSTER_PACK_SIDE_PRICE = 100               # Gold cost per side pack
BOOSTER_PACK_CARDS = 3                      # Cards drawn per pack (both types)
DUEL_WINNER_BOOSTER_PACKS = 2              # Packs awarded to duel winner
DUEL_LOSER_BOOSTER_PACKS = 1              # Packs awarded to duel loser
DUEL_BOOSTER_REWARD_PROBABILITIES = {       # Probability of reward type per pack
    'main': 0.60,
    'side': 0.40,
}

BOOSTER_TIER_PROBABILITIES = {              # Probability of drawing each tier (main)
    1: 0.30,   # common
    2: 0.30,   # uncommon
    3: 0.40,   # rare
}
BOOSTER_TIER_RANKS = {                      # Card ranks per tier (main)
    1: ['7', '8', '9', '10'],
    2: ['J', 'Q'],
    3: ['K', 'A'],
}

BOOSTER_SIDE_TIER_PROBABILITIES = {         # Probability of drawing each tier (side)
    1: 0.60,   # common
    2: 0.30,   # uncommon
    3: 0.10,   # rare
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
KINGDOM_TIER_COUNT = 4

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

LAND_TIER_PROBABILITIES = {1: 0.4, 2: 0.30, 3: 0.2, 4: 0.1}

# Neutral lands never reach the apex tier; weights are the cluster weights
# minus tier KINGDOM_TIER_COUNT, renormalised to sum to 1.
LAND_NEUTRAL_TIER_PROBABILITIES = {1: 0.484, 2: 0.323, 3: 0.193}

LAND_GOLD_RATE_RANGES = {                   # Gold per hour (min, max) per tier
    1: (1, 3),
    2: (3, 7),
    3: (7, 15),
    4: (15, 28),
}
LAND_SUIT_BONUS_RANGES = {                  # Suit combat bonus (min, max) per tier
    1: (1, 2),
    2: (2, 4),
    3: (4, 6),
    4: (6, 10),
}
CONQUER_COOLDOWN_SECONDS = int(os.getenv('CONQUER_COOLDOWN_SECONDS', str(10)))#str(6 * 3600)))
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
    'flag_key': 'flag_plain',
    'border_key': 'border_simple_gold',
    'surface_key': 'surface_plain',
}

KINGDOM_COSMETIC_CATALOG = {
    'flag_plain': {
        'type': 'flag',
        'name': 'Plain Pennant',
        'rarity': 'default',
        'price_gold': 0,
        'asset_key': 'flag_plain',
    },
    'flag_crimson': {
        'type': 'flag',
        'name': 'Crimson Banner',
        'rarity': 'common',
        'price_gold': 250,
        'asset_key': 'flag_crimson',
    },
    'flag_sun': {
        'type': 'flag',
        'name': 'Sun Banner',
        'rarity': 'rare',
        'price_gold': 850,
        'asset_key': 'flag_sun',
    },
    'flag_raven': {
        'type': 'flag',
        'name': 'Raven Banner',
        'rarity': 'rare',
        'price_gold': 1100,
        'asset_key': 'flag_raven',
    },
    'flag_lotus': {
        'type': 'flag',
        'name': 'Lotus Banner',
        'rarity': 'epic',
        'price_gold': 1600,
        'asset_key': 'flag_lotus',
    },
    'flag_mountain': {
        'type': 'flag',
        'name': 'Mountain Banner',
        'rarity': 'epic',
        'price_gold': 1900,
        'asset_key': 'flag_mountain',
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
    KingdomSkillDef,
    KINGDOM_SKILL_DEFINITIONS,
    booster_production_interval_hours,
    booster_production_effect_values,
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



