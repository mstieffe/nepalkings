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

import logging
import os
import sys
from datetime import datetime

# ── Public API ──────────────────────────────────────────────────────

def setup(*, debug: bool = False, log_dir: str | None = None):
    """Initialise the root ``nk`` logger.

    Parameters
    ----------
    debug : bool
        If *True* the console level is set to DEBUG; otherwise INFO.
    log_dir : str | None
        Directory for a rotating log file.  When *None* (the default)
        only console output is produced — identical to the old ``print()``
        behaviour.  Pass ``~/.nepalkings`` for persistent file logging.
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

    # ── Optional file handler ──
    if log_dir:
        log_dir = os.path.expanduser(log_dir)
        os.makedirs(log_dir, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = os.path.join(log_dir, f'nepalkings_{stamp}.log')
        fh = logging.FileHandler(filepath, encoding='utf-8')
        fh.setLevel(logging.DEBUG)      # file always captures everything
        fh.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)-7s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        root.addHandler(fh)
        root.info(f"File logging enabled: {filepath}")
