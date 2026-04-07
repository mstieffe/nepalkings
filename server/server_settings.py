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
INITIAL_GOLD = 100

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



