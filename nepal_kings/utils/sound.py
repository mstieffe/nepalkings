# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Lightweight SFX engine (companion to utils/haptics.py).

Design goals, mirroring the haptics bridge:

- Callers never need a platform guard: every entry point is a cheap
  no-op when sound is disabled, the mixer is unavailable, or an asset
  is missing.
- Web builds route playback through the browser-native Web Audio manager;
  desktop builds initialize Pygame's mixer lazily on the first play().
- The on/off preference persists in ~/.nepalkings/resolution.json next
  to the resolution; on web (no filesystem) it lives for the session.

Usage:

    from utils import sound
    sound.init()                 # once at startup (reads preference)
    sound.play('ui_click')       # anywhere; never raises

Assets are tiny synthesized WAVs in nepal_kings/sound/, with OGG companions
for the pygbag web build, produced by scripts/assets/generate_sfx.py.
"""

import json
import logging
import os
import sys

from utils import web_audio

logger = logging.getLogger('nk.utils.sound')

_IS_WEB = sys.platform == 'emscripten'

_CFG_DIR = os.path.join(os.path.expanduser('~'), '.nepalkings')
_CFG_FILE = os.path.join(_CFG_DIR, 'resolution.json')

# Master volume applied to every sound (each event also has its own gain).
MASTER_VOLUME = 0.7

# Event name → (filename or filename variants, relative gain).
# Variants rotate deterministically so repeated actions feel less mechanical
# without making tests or recordings nondeterministic.
EVENTS = {
    'ui_click':       (('ui_click.wav', 'ui_click_2.wav', 'ui_click_3.wav'), 1.0),
    'ui_back':        ('ui_back.wav', 1.0),
    'card_slide':     (('card_slide.wav', 'card_slide_2.wav',
                        'card_slide_3.wav', 'card_slide_4.wav'), 1.0),
    'card_place':     (('card_place.wav', 'card_place_2.wav',
                        'card_place_3.wav'), 1.0),
    'coin':           (('coin.wav', 'coin_2.wav', 'coin_3.wav'), 0.9),
    'booster_open':   (('booster_open.wav', 'booster_open_2.wav'), 1.0),
    'booster_reveal': ('booster_reveal.wav', 0.9),
    'rare_card_reveal': ('rare_card_reveal.wav', 0.9),
    # Reward chests are often opened several times in quick succession, so
    # keep this gentler than one-off celebration cues.
    'reward_reveal':  ('reward_reveal.wav', 0.8),
    'quest_claim':    ('quest_claim.wav', 0.9),
    'craft_success':  ('craft_success.wav', 1.0),
    'figure_place':   (('figure_place.wav', 'figure_place_2.wav'), 1.0),
    'land_select':    ('land_select.wav', 0.8),
    'map_gain':       ('map_gain.wav', 0.9),
    'defence_set':    ('defence_set.wav', 0.9),
    'spell_cast':     ('spell_cast.wav', 0.9),
    'counter_spell':  ('counter_spell.wav', 0.9),
    'spell_heal':     ('spell_heal.wav', 0.9),
    'spell_poison':   ('spell_poison.wav', 0.85),
    'spell_reveal':   ('spell_reveal.wav', 0.9),
    'spell_cards':    ('spell_cards.wav', 0.8),
    'spell_explosion': ('spell_explosion.wav', 1.0),
    'attack_launch':  ('attack_launch.wav', 1.0),
    'battle_start':   ('battle_start.wav', 1.0),
    'round_win':      ('round_win.wav', 0.8),
    'round_loss':     ('round_loss.wav', 0.75),
    'battle_total':   ('battle_total.wav', 0.9),
    'battle_win':     ('battle_win.wav', 1.0),
    'battle_lose':    ('battle_lose.wav', 1.0),
    'conquer_win':    ('conquer_win.wav', 1.0),
    'your_turn':      ('your_turn.wav', 0.9),
    'error':          ('error.wav', 0.8),
    'reveal_hold':    ('reveal_hold.wav', 0.8),
    'tally_tick':     (('tally_tick.wav', 'tally_tick_2.wav'), 0.6),
}

SPELL_EVENTS = {
    'Health Boost': 'spell_heal',
    'Ceasefire': 'spell_heal',
    'Poison': 'spell_poison',
    'All Seeing Eye': 'spell_reveal',
    'Royal Decree': 'spell_reveal',
    'Draw 2 SideCards': 'spell_cards',
    'Draw 2 MainCards': 'spell_cards',
    'Draw 4 MainCards': 'spell_cards',
    'Fill up to 10': 'spell_cards',
    'Forced Deal': 'spell_cards',
    'Dump Cards': 'spell_cards',
    'Copy Figure': 'spell_cards',
    'Invader Swap': 'spell_cards',
    'Explosion': 'spell_explosion',
    'Landslide': 'spell_explosion',
}

_enabled = True
_mixer_failed = False
_cache = {}
_variant_counters = {}


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

def _candidate_filenames(filename):
    """Return load candidates for an event asset, preferring web-safe OGG."""
    if _IS_WEB:
        stem, _ext = os.path.splitext(filename)
        return (stem + '.ogg', filename)
    return (filename,)


def event_filenames(name):
    """Return every authored filename for an event."""
    entry = EVENTS.get(name)
    if entry is None:
        return ()
    filenames = entry[0]
    if isinstance(filenames, (tuple, list)):
        return tuple(filenames)
    return (filenames,)


def _next_event_filename(name):
    filenames = event_filenames(name)
    if not filenames:
        return None
    index = _variant_counters.get(name, 0)
    _variant_counters[name] = index + 1
    return filenames[index % len(filenames)]


def _ensure_mixer():
    """Lazy mixer init; remembers permanent failure so we stop retrying."""
    global _mixer_failed
    if _mixer_failed:
        return False
    try:
        import pygame
        if pygame.mixer.get_init():
            return True
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
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
    filename = _next_event_filename(name)
    if filename is None:
        return False
    playback_volume = max(
        0.0, min(1.0, MASTER_VOLUME * entry[1] * volume))
    if _IS_WEB:
        stem, _ext = os.path.splitext(filename)
        if web_audio.play_sfx(stem + '.ogg', playback_volume):
            return True
    if not _ensure_mixer():
        return False
    try:
        import pygame
        cache_key = (name, filename)
        snd = _cache.get(cache_key)
        if snd is None:
            for candidate in _candidate_filenames(filename):
                path = os.path.join(_sound_dir(), candidate)
                if not os.path.exists(path):
                    continue
                try:
                    snd = pygame.mixer.Sound(path)
                    break
                except Exception:
                    continue
            if snd is None:
                return False
            _cache[cache_key] = snd
        snd.set_volume(playback_volume)
        snd.play()
        return True
    except Exception:
        return False


def play_spell(spell_name, *, counter=False, volume=1.0):
    """Play the semantic cue for a spell family, with a generic fallback."""
    event = 'counter_spell' if counter else SPELL_EVENTS.get(
        spell_name, 'spell_cast')
    return play(event, volume=volume)


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
    # Invalid-action feedback (the duel action screens title these dialogs
    # consistently: "Action Blocked", "Not Your Turn", "... Failed", ...).
    if ('failed' in t or 'error' in t or 'invalid' in t or 'blocked' in t
            or 'cannot' in t or 'wrong' in t or 'not your turn' in t
            or 'must advance' in t or 'already selected' in t
            or 'no valid target' in t or 'target required' in t
            or 'resource deficit' in t or 'ceasefire active' in t
            or 'resting' in t or 'immune' in t):
        return play('error')
    return False
