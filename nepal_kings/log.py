# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
Centralised logging configuration for the Nepal Kings client.

Usage in any client module::

    import logging
    logger = logging.getLogger('nk.screens.battle')
    logger.info("[BATTLE] Round started")

Call ``setup()`` once at application startup (e.g. in main.py) before
any other module logs.  After that every module simply creates its own
``logging.getLogger(...)`` — the handler / format / level propagate
through the hierarchy automatically.
"""

import glob
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from typing import Optional

# ── Tunables ────────────────────────────────────────────────────────
_MAX_LOG_BYTES   = 5 * 1024 * 1024   # 5 MB per log file
_BACKUP_COUNT    = 3                  # keep current + 3 rotated files
_OLD_LOG_MAX_AGE = 7 * 86400         # delete log files older than 7 days

_IS_WEB = sys.platform == "emscripten"

# ── Public API ──────────────────────────────────────────────────────

def setup(*, debug: bool = False, log_dir: Optional[str] = None):
    """Initialise the root ``nk`` logger.

    Parameters
    ----------
    debug : bool
        If *True* the console level is set to DEBUG; otherwise INFO.
    log_dir : str | None
        Directory for a rotating log file.  When *None* (the default)
        only console output is produced — identical to the old ``print()``
        behaviour.  Pass ``~/.nepalkings`` for persistent file logging.
        Ignored on web/emscripten (no real filesystem).
    """
    root = logging.getLogger('nk')
    if root.handlers:          # already configured — avoid duplicate handlers
        return
    root.setLevel(logging.DEBUG)

    # ── Console handler (replaces print()) ──
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname).1s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    ))
    root.addHandler(console)

    # ── Rotating file handler (desktop only) ──
    if log_dir and not _IS_WEB:
        log_dir = os.path.expanduser(log_dir)
        os.makedirs(log_dir, exist_ok=True)

        # Purge old session log files before creating a new one
        _purge_old_logs(log_dir)

        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = os.path.join(log_dir, f'nepalkings_{stamp}.log')
        fh = logging.handlers.RotatingFileHandler(
            filepath,
            maxBytes=_MAX_LOG_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding='utf-8',
        )
        fh.setLevel(logging.DEBUG)      # file always captures everything
        fh.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)-7s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        root.addHandler(fh)
        root.info(f"File logging enabled: {filepath}")


def _purge_old_logs(log_dir: str):
    """Delete ``nepalkings_*.log*`` files older than ``_OLD_LOG_MAX_AGE``."""
    now = datetime.now().timestamp()
    for path in glob.glob(os.path.join(log_dir, 'nepalkings_*.log*')):
        try:
            if now - os.path.getmtime(path) > _OLD_LOG_MAX_AGE:
                os.remove(path)
        except OSError:
            pass
