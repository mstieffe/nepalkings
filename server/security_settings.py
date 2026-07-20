# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Security & auth-related runtime configuration.

All values are sourced from environment variables. Defaults are chosen to
be safe for local development; production deployments must override the
sensitive ones (see ``.env.example``).
"""
import os
import secrets

# ── Secret key ────────────────────────────────────────────────────
# A random per-process default is acceptable for local dev: it means tokens
# do not survive a restart. In production, set SECRET_KEY explicitly so
# tokens (and any other signing) survive across restarts and replicas.
SECRET_KEY = os.getenv('SECRET_KEY', secrets.token_hex(32))
SECRET_KEY_FROM_ENV = bool(os.getenv('SECRET_KEY'))

# ── CORS ──────────────────────────────────────────────────────────
# Comma-separated list of allowed origins. Default is locked down to local
# development origins. Set CORS_ORIGINS='*' explicitly only when you really
# want to allow any origin (e.g. for a public web client).
CORS_ORIGINS = os.getenv(
    'CORS_ORIGINS',
    'http://localhost,http://localhost:5000,http://127.0.0.1,http://127.0.0.1:5000',
)

# ── Request size limit ────────────────────────────────────────────
# Hard cap on request body size (bytes). All API payloads are small
# JSON/form bodies, so 256 KB leaves generous headroom while blocking
# memory-exhaustion via oversized uploads.
MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', str(256 * 1024)))

# ── Rate limiting (Flask-Limiter format) ──────────────────────────
# NOTE: with the default in-memory storage each worker process keeps its
# own counters, so the effective limit is roughly limit × worker_count.
# Set RATELIMIT_STORAGE_URI (e.g. redis://...) for shared counters.
RATELIMIT_STORAGE_URI = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')
RATE_LIMIT_DEFAULT = os.getenv('RATE_LIMIT_DEFAULT', '600 per minute')
RATE_LIMIT_LOGIN = os.getenv('RATE_LIMIT_LOGIN', '10 per minute')
RATE_LIMIT_REGISTER = os.getenv('RATE_LIMIT_REGISTER', '5 per minute')
RATE_LIMIT_LOOKUP = os.getenv('RATE_LIMIT_LOOKUP', '60 per minute')
RATE_LIMIT_CHAT = os.getenv('RATE_LIMIT_CHAT', '12 per minute')
RATE_LIMIT_REPORT = os.getenv('RATE_LIMIT_REPORT', '5 per hour')

# ── Auth token settings ───────────────────────────────────────────
# Signed user tokens expire after TOKEN_EXPIRY_SECONDS (default 24 hours).
TOKEN_EXPIRY_SECONDS = int(os.getenv('TOKEN_EXPIRY_SECONDS', '86400'))

# ── Legal acceptance versions ─────────────────────────────────────
LEGAL_TERMS_VERSION = os.getenv('LEGAL_TERMS_VERSION', '2026-07-20')
LEGAL_PRIVACY_VERSION = os.getenv('LEGAL_PRIVACY_VERSION', '2026-07-20')
