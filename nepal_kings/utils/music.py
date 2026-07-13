# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Low-volume background music on a channel reserved from one-shot SFX.

The tracks are compact runtime loops prepared alongside the SFX. They may be
procedural or derived from an approved source master. Using a
``pygame.mixer.Sound`` channel instead of ``pygame.mixer.music`` keeps the web
and desktop asset-loading paths identical, including OGG preference on web.
"""

import json
import os
import sys

from utils import sound

_IS_WEB = sys.platform == 'emscripten'
_CFG_DIR = os.path.join(os.path.expanduser('~'), '.nepalkings')
_CFG_FILE = os.path.join(_CFG_DIR, 'resolution.json')

MASTER_VOLUME = 0.28

TRACKS = {
    'menu': ('music_menu.wav', 0.72),
    'kingdom': ('music_kingdom.wav', 0.78),
    'battle': ('music_battle.wav', 0.72),
}

SCREEN_TRACKS = {
    'login': 'menu',
    'game_menu': 'menu',
    'duel_menu': 'menu',
    'new_game': 'menu',
    'load_game': 'menu',
    'rankings': 'menu',
    'settings': 'menu',
    'collection': 'menu',
    'kingdom_config': 'menu',
    'kingdom': 'kingdom',
    'conquer': 'kingdom',
    'defence': 'kingdom',
    'game': 'battle',
    'conquer_game': 'battle',
}

_enabled = True
_channel = None
_cache = {}
_current_track = None
_requested_track = None


def init():
    """Read the persisted music preference. Web keeps it session-local."""
    global _enabled
    if _IS_WEB:
        return
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, 'r') as f:
                _enabled = bool(json.load(f).get('music_enabled', True))
    except Exception:
        _enabled = True


def _persist_enabled():
    if _IS_WEB:
        return
    try:
        os.makedirs(_CFG_DIR, exist_ok=True)
        existing = {}
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, 'r') as f:
                existing = json.load(f)
        existing['music_enabled'] = _enabled
        with open(_CFG_FILE, 'w') as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass


def set_enabled(value):
    """Enable or disable music independently from sound effects."""
    global _enabled
    _enabled = bool(value)
    _persist_enabled()
    if not _enabled:
        stop()
    elif _requested_track:
        play(_requested_track)


def is_enabled():
    return _enabled


def _track_candidates(filename):
    return sound._candidate_filenames(filename)


def _get_channel():
    global _channel
    if _channel is not None:
        return _channel
    if not sound._ensure_mixer():
        return None
    try:
        import pygame
        pygame.mixer.set_reserved(1)
        _channel = pygame.mixer.Channel(0)
        return _channel
    except Exception:
        return None


def _load_track(name):
    cached = _cache.get(name)
    if cached is not None:
        return cached
    entry = TRACKS.get(name)
    if entry is None:
        return None
    try:
        import pygame
        for filename in _track_candidates(entry[0]):
            path = os.path.join(sound._sound_dir(), filename)
            if not os.path.exists(path):
                continue
            try:
                track = pygame.mixer.Sound(path)
                _cache[name] = track
                return track
            except Exception:
                continue
    except Exception:
        pass
    return None


def play(name, fade_ms=700):
    """Loop a named track; repeated calls for the same track are cheap."""
    global _current_track, _requested_track
    if name not in TRACKS:
        return False
    _requested_track = name
    if not _enabled:
        return False
    if _current_track == name:
        return True
    channel = _get_channel()
    track = _load_track(name)
    if channel is None or track is None:
        return False
    try:
        channel.set_volume(max(0.0, min(
            1.0, MASTER_VOLUME * TRACKS[name][1])))
        channel.play(track, loops=-1, fade_ms=max(0, int(fade_ms)))
        _current_track = name
        return True
    except Exception:
        return False


def stop(fade_ms=350):
    """Fade the current track out while retaining the requested screen track."""
    global _current_track
    if _channel is not None:
        try:
            if fade_ms:
                _channel.fadeout(max(0, int(fade_ms)))
            else:
                _channel.stop()
        except Exception:
            pass
    _current_track = None


def play_for_screen(screen_name):
    """Select the restrained theme associated with a top-level screen."""
    track = SCREEN_TRACKS.get(screen_name)
    if track is None:
        stop()
        return False
    return play(track)
