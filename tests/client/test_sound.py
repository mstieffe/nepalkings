# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the SFX engine (utils/sound.py)."""

import json
import os

import pytest

from utils import sound


@pytest.fixture(autouse=True)
def _reset_module_state(tmp_path, monkeypatch):
    """Isolate preference file and module globals per test."""
    cfg_dir = tmp_path / '.nepalkings'
    monkeypatch.setattr(sound, '_CFG_DIR', str(cfg_dir))
    monkeypatch.setattr(sound, '_CFG_FILE', str(cfg_dir / 'resolution.json'))
    monkeypatch.setattr(sound, '_enabled', True)
    monkeypatch.setattr(sound, '_mixer_failed', False)
    monkeypatch.setattr(sound, '_cache', {})
    yield


def test_every_event_has_a_generated_asset():
    """The committed sound set must cover the full event table."""
    missing = [name for name, (filename, _gain) in sound.EVENTS.items()
               if not os.path.exists(os.path.join(sound._sound_dir(), filename))]
    assert missing == [], f'missing SFX assets (run scripts/assets/generate_sfx.py): {missing}'


def test_unknown_event_is_silent_noop():
    assert sound.play('definitely_not_an_event') is False


def test_disabled_never_plays(monkeypatch):
    called = []
    monkeypatch.setattr(sound, '_ensure_mixer', lambda: called.append(1) or True)
    sound.set_enabled(False)
    assert sound.play('ui_click') is False
    assert called == []  # short-circuits before touching the mixer


def test_mixer_failure_is_remembered(monkeypatch):
    attempts = []

    def _failing_mixer_init(**kwargs):
        attempts.append(1)
        raise RuntimeError('no audio device')

    import pygame
    monkeypatch.setattr(pygame.mixer, 'get_init', lambda: None)
    monkeypatch.setattr(pygame.mixer, 'init', _failing_mixer_init)
    assert sound.play('ui_click') is False
    assert sound.play('ui_click') is False
    assert len(attempts) == 1  # second call short-circuits on _mixer_failed


def test_preference_persists_roundtrip():
    sound.set_enabled(False)
    assert os.path.exists(sound._CFG_FILE)
    with open(sound._CFG_FILE) as f:
        assert json.load(f)['sound_enabled'] is False
    # init() reads it back
    sound._enabled = True
    sound.init()
    assert sound.is_enabled() is False


def test_set_enabled_preserves_other_settings():
    os.makedirs(sound._CFG_DIR, exist_ok=True)
    with open(sound._CFG_FILE, 'w') as f:
        json.dump({'width': 1280, 'height': 720}, f)
    sound.set_enabled(False)
    with open(sound._CFG_FILE) as f:
        data = json.load(f)
    assert data == {'width': 1280, 'height': 720, 'sound_enabled': False}


def test_play_for_dialogue_title_mapping(monkeypatch):
    played = []
    monkeypatch.setattr(sound, 'play', lambda name, volume=1.0: played.append(name) or True)
    sound.play_for_dialogue('Victory!')
    sound.play_for_dialogue('Defeat')
    sound.play_for_dialogue('To Battle!')
    assert sound.play_for_dialogue('Your Prelude') is False
    assert played == ['battle_win', 'battle_lose', 'battle_start']
