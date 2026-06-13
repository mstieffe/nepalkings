# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Lightweight SFX engine (companion to utils/haptics.py).

Design goals, mirroring the haptics bridge:

- Callers never need a platform guard: every entry point is a cheap
  no-op when sound is disabled, the mixer is unavailable, or an asset
  is missing.
- The mixer initializes lazily on the first play() so the web build
  starts audio only after a user gesture (required by browsers).
- The on/off preference persists in ~/.nepalkings/resolution.json next
  to the resolution; on web (no filesystem) it lives for the session.

Usage:

    from utils import sound
    sound.init()                 # once at startup (reads preference)
    sound.play('ui_click')       # anywhere; never raises

Assets are tiny synthesized WAVs in nepal_kings/sound/, produced by
scripts/assets/generate_sfx.py.
"""

import json
import logging
import os
import sys

logger = logging.getLogger('nk.utils.sound')

_IS_WEB = sys.platform == 'emscripten'

_CFG_DIR = os.path.join(os.path.expanduser('~'), '.nepalkings')
_CFG_FILE = os.path.join(_CFG_DIR, 'resolution.json')

# Master volume applied to every sound (each event also has its own gain).
MASTER_VOLUME = 0.7

# Event name → (filename, relative gain). Files live in nepal_kings/sound/.
EVENTS = {
    'ui_click':       ('ui_click.wav', 1.0),
    'ui_back':        ('ui_back.wav', 1.0),
    'card_slide':     ('card_slide.wav', 1.0),
    'card_place':     ('card_place.wav', 1.0),
    'coin':           ('coin.wav', 0.9),
    'booster_open':   ('booster_open.wav', 1.0),
    'booster_reveal': ('booster_reveal.wav', 0.9),
    'figure_place':   ('figure_place.wav', 1.0),
    'battle_start':   ('battle_start.wav', 1.0),
    'battle_win':     ('battle_win.wav', 1.0),
    'battle_lose':    ('battle_lose.wav', 1.0),
    'conquer_win':    ('conquer_win.wav', 1.0),
    'your_turn':      ('your_turn.wav', 0.9),
    'error':          ('error.wav', 0.8),
}

_enabled = True
_mixer_failed = False
_cache = {}


def _sound_dir():
    try:
        from config import settings
        return os.path.join(settings.RESOURCE_BASE, 'sound')
    except Exception:
        return os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'sound')


# ── Preference persistence ─────────────────────────────────────────

def init():
    """Read the persisted on/off preference. Safe to call anywhere."""
    global _enabled
    if _IS_WEB:
        return  # session-only on web; default stays on
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, 'r') as f:
                _enabled = bool(json.load(f).get('sound_enabled', True))
    except Exception:
        _enabled = True


def set_enabled(value):
    """Enable/disable all SFX and persist the choice (desktop only)."""
    global _enabled
    _enabled = bool(value)
    if _IS_WEB:
        return
    try:
        os.makedirs(_CFG_DIR, exist_ok=True)
        existing = {}
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, 'r') as f:
                existing = json.load(f)
        existing['sound_enabled'] = _enabled
        with open(_CFG_FILE, 'w') as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass


def is_enabled():
    return _enabled


# ── Playback ───────────────────────────────────────────────────────

def _ensure_mixer():
    """Lazy mixer init; remembers permanent failure so we stop retrying."""
    global _mixer_failed
    if _mixer_failed:
        return False
    try:
        import pygame
        if pygame.mixer.get_init():
            return True
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        return True
    except Exception:
        _mixer_failed = True
        logger.info('Sound mixer unavailable — SFX disabled for this run')
        return False


def play(name, volume=1.0):
    """Play one SFX by event name. Returns True if playback started."""
    if not _enabled:
        return False
    entry = EVENTS.get(name)
    if entry is None:
        return False
    if not _ensure_mixer():
        return False
    try:
        import pygame
        snd = _cache.get(name)
        if snd is None:
            path = os.path.join(_sound_dir(), entry[0])
            if not os.path.exists(path):
                return False
            snd = pygame.mixer.Sound(path)
            _cache[name] = snd
        snd.set_volume(max(0.0, min(1.0, MASTER_VOLUME * entry[1] * volume)))
        snd.play()
        return True
    except Exception:
        return False


def tap_edge(obj, name='ui_click', volume=0.7):
    """Play a click on the rising edge of ``obj.clicked`` (mirrors
    haptics.tap_edge). Stores the previous state on the object so a held
    press fires exactly once. Call once per frame, after the button's
    ``clicked`` flag is refreshed. Cheap no-op when sound is disabled."""
    now = bool(getattr(obj, 'clicked', False))
    if now and not getattr(obj, '_sound_prev_click', False):
        play(name, volume=volume)
    obj._sound_prev_click = now


def play_for_dialogue(title):
    """Outcome stinger for notification dialogs, keyed off their title.

    Central hook used by the screens' make_dialogue_box() paths so every
    win/lose/draw dialog gets the right sound without per-site wiring —
    covers both duel battle results and conquer-battle land outcomes.
    """
    t = (title or '').lower()
    # Losses first so "... conquered your land" is not read as a win.
    if ('defeat' in t or 'you lost' in t or 'land lost' in t
            or 'attack failed' in t or 'your land' in t):
        return play('battle_lose')
    # Conquest wins get the bigger fanfare; duel/battle wins the win stinger.
    if 'conquered' in t or 'defence successful' in t or 'defended' in t:
        return play('conquer_win')
    if 'victory' in t or t.startswith('you won') or 'you win' in t:
        return play('battle_win')
    if 'draw' in t:
        return play('ui_back')
    if 'battle' in t and ('begin' in t or 'start' in t or t == 'to battle!'):
        return play('battle_start')
    return False
