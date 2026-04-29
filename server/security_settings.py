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

# ── Rate limiting (Flask-Limiter format) ──────────────────────────
RATE_LIMIT_DEFAULT = os.getenv('RATE_LIMIT_DEFAULT', '600 per minute')
RATE_LIMIT_LOGIN = os.getenv('RATE_LIMIT_LOGIN', '10 per minute')
RATE_LIMIT_REGISTER = os.getenv('RATE_LIMIT_REGISTER', '5 per minute')

# ── Auth token settings ───────────────────────────────────────────
# Signed user tokens expire after TOKEN_EXPIRY_SECONDS (default 24 hours).
TOKEN_EXPIRY_SECONDS = int(os.getenv('TOKEN_EXPIRY_SECONDS', '86400'))
