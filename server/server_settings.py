# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.

import os
import secrets

# Server and database configurations
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:5000')
DB_URL = os.getenv('DB_URL', 'sqlite:///test.db')

# Security
SECRET_KEY = os.getenv('SECRET_KEY', secrets.token_hex(32))
CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*')  # Comma-separated origins, or '*'

# Rate limiting (Flask-Limiter format)
RATE_LIMIT_DEFAULT = os.getenv('RATE_LIMIT_DEFAULT', '600 per minute')
RATE_LIMIT_LOGIN = os.getenv('RATE_LIMIT_LOGIN', '10 per minute')
RATE_LIMIT_REGISTER = os.getenv('RATE_LIMIT_REGISTER', '5 per minute')

# Database management
# Set to True to drop and recreate all tables on server startup (useful for schema changes)
# WARNING: This will delete all data! Set to False for production.
DROP_TABLES_ON_STARTUP = os.getenv('DROP_TABLES_ON_STARTUP', 'False').lower() == 'true'

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
INITIAL_GOLD = 1000

# Auth token settings
# Signed user tokens expire after TOKEN_EXPIRY_SECONDS (default 24 hours).
# Set a fixed SECRET_KEY env var in production so tokens survive restarts.
TOKEN_EXPIRY_SECONDS = int(os.getenv('TOKEN_EXPIRY_SECONDS', '86400'))

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
KINGDOM_MAP_COLS = 13
KINGDOM_MAP_ROWS = 7                        # ~91 hexes
LAND_TIER_PROBABILITIES = {1: 0.55, 2: 0.30, 3: 0.15}
LAND_GOLD_RATE_RANGES = {                   # Gold per hour (min, max) per tier
    1: (1, 3),
    2: (3, 7),
    3: (7, 15),
}
LAND_SUIT_BONUS_RANGES = {                  # Suit combat bonus (min, max) per tier
    1: (1, 3),
    2: (3, 6),
    3: (5, 10),
}
CONQUER_COOLDOWN_SECONDS = int(os.getenv('CONQUER_COOLDOWN_SECONDS', str(6 * 3600)))
GOLD_PRODUCTION_MAX_ACCUMULATION_HOURS = 7 * 24  # Cap at 7 days of uncollected gold

# ── v2.0: AI Defence Templates ──
# Each template defines a pre-built defence configuration for unowned (AI) lands.
# Templates are lists of dicts per tier; one is randomly assigned to each land at
# map seeding time.  Full template schema is defined in kingdom_service.py.
AI_DEFENCE_TEMPLATES = {
    1: [  # Tier 1 — weak: one farm figure, basic dagger moves
        {
            'ai_name': 'Village Guard',
            'figures': [
                {'family_name': 'Small Rice Farm', 'name': 'Small Rice Farm',
                 'suit': 'Hearts', 'color': 'offensive', 'field': 'village',
                 'produces': {'food_red': 8}, 'requires': {'villager_red': 1},
                 'card_ids': [], 'card_roles': ['key', 'number'],
                 'cards': [{'rank': 'J', 'suit': 'Hearts', 'role': 'key'},
                           {'rank': '8', 'suit': 'Hearts', 'role': 'number'}]},
            ],
            'battle_moves': [
                {'family_name': 'Dagger', 'rank': '7', 'suit': 'Spades',
                 'value': 7, 'round_index': 0, 'card_type': 'main'},
                {'family_name': 'Dagger', 'rank': '8', 'suit': 'Hearts',
                 'value': 8, 'round_index': 1, 'card_type': 'main'},
                {'family_name': 'Dagger', 'rank': '7', 'suit': 'Clubs',
                 'value': 7, 'round_index': 2, 'card_type': 'main'},
            ],
            'battle_figure_index': 0,
            'battle_modifier': None,
            'spell': None,
            'auto_gamble': False,
        },
    ],
    2: [  # Tier 2 — medium: king + farm, auto-gamble, one Call King move
        {
            'ai_name': 'Mountain Warden',
            'figures': [
                {'family_name': 'Himalaya King', 'name': 'Himalaya King',
                 'suit': 'Spades', 'color': 'defensive', 'field': 'castle',
                 'produces': {'villager_black': 2, 'warrior_black': 1}, 'requires': {},
                 'card_ids': [], 'card_roles': ['key'],
                 'cards': [{'rank': 'K', 'suit': 'Spades', 'role': 'key'}]},
                {'family_name': 'Small Yack Farm', 'name': 'Small Yack Farm',
                 'suit': 'Clubs', 'color': 'defensive', 'field': 'village',
                 'produces': {'food_black': 8}, 'requires': {'villager_black': 1},
                 'card_ids': [], 'card_roles': ['key', 'number'],
                 'cards': [{'rank': 'J', 'suit': 'Clubs', 'role': 'key'},
                           {'rank': '8', 'suit': 'Clubs', 'role': 'number'}]},
            ],
            'battle_moves': [
                {'family_name': 'Call King', 'rank': 'K', 'suit': 'Spades',
                 'value': 4, 'round_index': 0, 'card_type': 'main'},
                {'family_name': 'Dagger', 'rank': '10', 'suit': 'Clubs',
                 'value': 10, 'round_index': 1, 'card_type': 'main'},
                {'family_name': 'Dagger', 'rank': '8', 'suit': 'Spades',
                 'value': 8, 'round_index': 2, 'card_type': 'main'},
            ],
            'battle_figure_index': 0,
            'battle_modifier': None,
            'spell': None,
            'auto_gamble': True,
        },
    ],
    3: [  # Tier 3 — strong: king + warriors + farm, Call Military move
        {
            'ai_name': 'Djungle Warlord',
            'figures': [
                {'family_name': 'Djungle King', 'name': 'Djungle King',
                 'suit': 'Hearts', 'color': 'offensive', 'field': 'castle',
                 'produces': {'villager_red': 2, 'warrior_red': 1}, 'requires': {},
                 'card_ids': [], 'card_roles': ['key'],
                 'cards': [{'rank': 'K', 'suit': 'Hearts', 'role': 'key'}]},
                {'family_name': 'Gorkha Warriors', 'name': 'Gorkha Warriors',
                 'suit': 'Hearts', 'color': 'offensive', 'field': 'military',
                 'produces': {}, 'requires': {'warrior_red': 1, 'food_red': 10},
                 'card_ids': [], 'card_roles': ['key', 'number'],
                 'cards': [{'rank': 'A', 'suit': 'Hearts', 'role': 'key'},
                           {'rank': '10', 'suit': 'Hearts', 'role': 'number'}]},
                {'family_name': 'Small Rice Farm', 'name': 'Small Rice Farm',
                 'suit': 'Diamonds', 'color': 'offensive', 'field': 'village',
                 'produces': {'food_red': 9}, 'requires': {'villager_red': 1},
                 'card_ids': [], 'card_roles': ['key', 'number'],
                 'cards': [{'rank': 'J', 'suit': 'Diamonds', 'role': 'key'},
                           {'rank': '9', 'suit': 'Diamonds', 'role': 'number'}]},
            ],
            'battle_moves': [
                {'family_name': 'Call Military', 'rank': 'A', 'suit': 'Hearts',
                 'value': 3, 'round_index': 0, 'card_type': 'main'},
                {'family_name': 'Dagger', 'rank': '9', 'suit': 'Diamonds',
                 'value': 9, 'round_index': 1, 'card_type': 'main'},
                {'family_name': 'Dagger', 'rank': '10', 'suit': 'Diamonds',
                 'value': 10, 'round_index': 2, 'card_type': 'main'},
            ],
            'battle_figure_index': 1,
            'battle_modifier': None,
            'spell': None,
            'auto_gamble': True,
        },
    ],
}



