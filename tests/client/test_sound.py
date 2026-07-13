# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the SFX engine (utils/sound.py)."""

import json
import os
import sys
import types
import wave

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
    monkeypatch.setattr(sound, '_variant_counters', {})
    yield


def test_every_event_has_a_generated_asset():
    """The committed sound set must cover the full event table."""
    missing = [
        f'{name}:{filename}'
        for name in sound.EVENTS
        for filename in sound.event_filenames(name)
        if not os.path.exists(os.path.join(sound._sound_dir(), filename))
    ]
    assert missing == [], f'missing SFX assets (run scripts/assets/generate_sfx.py): {missing}'


def test_every_event_has_a_web_ogg_companion():
    """pygbag/browser audio should use OGG companions, not WAV-only assets."""
    missing = []
    for name in sound.EVENTS:
        for filename in sound.event_filenames(name):
            stem, _ext = os.path.splitext(filename)
            if not os.path.exists(os.path.join(sound._sound_dir(), stem + '.ogg')):
                missing.append(f'{name}:{filename}')
    assert missing == [], f'missing web OGG SFX assets: {missing}'


def test_web_play_prefers_ogg_companion(tmp_path, monkeypatch):
    paths = []

    class FakeSound:
        def __init__(self, path):
            paths.append(os.path.basename(path))

        def set_volume(self, volume):
            self.volume = volume

        def play(self):
            self.played = True

    fake_pygame = types.SimpleNamespace(
        mixer=types.SimpleNamespace(Sound=FakeSound)
    )
    (tmp_path / 'ui_click.wav').write_bytes(b'wav')
    (tmp_path / 'ui_click.ogg').write_bytes(b'ogg')
    monkeypatch.setitem(sys.modules, 'pygame', fake_pygame)
    monkeypatch.setattr(sound, '_IS_WEB', True)
    monkeypatch.setattr(sound, '_sound_dir', lambda: str(tmp_path))
    monkeypatch.setattr(sound, '_ensure_mixer', lambda: True)
    monkeypatch.setattr(sound, 'EVENTS', {'ui_click': ('ui_click.wav', 1.0)})

    assert sound.play('ui_click') is True
    assert paths == ['ui_click.ogg']


def test_web_play_falls_back_to_wav_when_ogg_load_fails(tmp_path, monkeypatch):
    paths = []

    class FakeSound:
        def set_volume(self, volume):
            self.volume = volume

        def play(self):
            self.played = True

    def fake_sound(path):
        paths.append(os.path.basename(path))
        if path.endswith('.ogg'):
            raise RuntimeError('bad browser decode')
        return FakeSound()

    fake_pygame = types.SimpleNamespace(
        mixer=types.SimpleNamespace(Sound=fake_sound)
    )
    (tmp_path / 'ui_click.wav').write_bytes(b'wav')
    (tmp_path / 'ui_click.ogg').write_bytes(b'ogg')
    monkeypatch.setitem(sys.modules, 'pygame', fake_pygame)
    monkeypatch.setattr(sound, '_IS_WEB', True)
    monkeypatch.setattr(sound, '_sound_dir', lambda: str(tmp_path))
    monkeypatch.setattr(sound, '_ensure_mixer', lambda: True)
    monkeypatch.setattr(sound, 'EVENTS', {'ui_click': ('ui_click.wav', 1.0)})

    assert sound.play('ui_click') is True
    assert paths == ['ui_click.ogg', 'ui_click.wav']


def test_repeated_event_rotates_through_authored_variants(tmp_path, monkeypatch):
    loaded = []
    played = []

    class FakeSound:
        def __init__(self, path):
            self.name = os.path.basename(path)
            loaded.append(self.name)

        def set_volume(self, volume):
            self.volume = volume

        def play(self):
            played.append(self.name)

    fake_pygame = types.SimpleNamespace(
        mixer=types.SimpleNamespace(Sound=FakeSound)
    )
    for filename in ('tap_a.wav', 'tap_b.wav'):
        (tmp_path / filename).write_bytes(b'wav')
    monkeypatch.setitem(sys.modules, 'pygame', fake_pygame)
    monkeypatch.setattr(sound, '_sound_dir', lambda: str(tmp_path))
    monkeypatch.setattr(sound, '_ensure_mixer', lambda: True)
    monkeypatch.setattr(
        sound, 'EVENTS', {'tap': (('tap_a.wav', 'tap_b.wav'), 1.0)})

    assert sound.play('tap') is True
    assert sound.play('tap') is True
    assert sound.play('tap') is True
    assert played == ['tap_a.wav', 'tap_b.wav', 'tap_a.wav']
    assert loaded == ['tap_a.wav', 'tap_b.wav']


def test_unknown_event_is_silent_noop():
    assert sound.play('definitely_not_an_event') is False


@pytest.mark.parametrize(('spell_name', 'event'), [
    ('Health Boost', 'spell_heal'),
    ('Poison', 'spell_poison'),
    ('All Seeing Eye', 'spell_reveal'),
    ('Forced Deal', 'spell_cards'),
    ('Explosion', 'spell_explosion'),
    ('Blitzkrieg', 'spell_cast'),
])
def test_spell_names_map_to_semantic_events(monkeypatch, spell_name, event):
    played = []
    monkeypatch.setattr(
        sound, 'play', lambda name, volume=1.0: played.append(name) or True)
    assert sound.play_spell(spell_name) is True
    assert played == [event]


def test_counter_spell_always_uses_counter_event(monkeypatch):
    played = []
    monkeypatch.setattr(
        sound, 'play', lambda name, volume=1.0: played.append(name) or True)
    sound.play_spell('Explosion', counter=True)
    assert played == ['counter_spell']


def test_mixkit_effects_are_compact_mono_runtime_edits():
    max_durations = {
        'spell_cast.wav': 1.6,
        'counter_spell.wav': 2.2,
        'spell_heal.wav': 2.1,
        'spell_poison.wav': 1.7,
        'spell_reveal.wav': 1.7,
        'spell_cards.wav': 1.6,
        'spell_explosion.wav': 1.7,
        'card_slide_4.wav': 0.3,
        'card_place_3.wav': 0.2,
        'coin_3.wav': 0.4,
        'booster_open.wav': 0.9,
        'booster_open_2.wav': 0.8,
        'rare_card_reveal.wav': 2.4,
        'reward_reveal.wav': 1.0,
        'quest_claim.wav': 1.3,
        'craft_success.wav': 1.3,
        'figure_place_2.wav': 0.5,
        'map_gain.wav': 1.0,
        'round_win.wav': 0.9,
        'battle_total.wav': 1.6,
        'battle_win.wav': 1.5,
        'battle_lose.wav': 2.1,
    }
    for filename, max_duration in max_durations.items():
        path = os.path.join(sound._sound_dir(), filename)
        with wave.open(path, 'rb') as wf:
            duration = wf.getnframes() / wf.getframerate()
            assert wf.getframerate() == 22050, filename
            assert wf.getnchannels() == 1, filename
            assert duration <= max_duration + 0.01, filename


def test_downloaded_card_and_build_cues_are_authored_variants():
    assert sound.event_filenames('card_slide')[-1] == 'card_slide_4.wav'
    assert sound.event_filenames('card_place')[-1] == 'card_place_3.wav'
    assert sound.event_filenames('coin')[-1] == 'coin_3.wav'
    assert sound.event_filenames('booster_open') == (
        'booster_open.wav', 'booster_open_2.wav')
    assert sound.event_filenames('figure_place')[-1] == 'figure_place_2.wav'


def test_mixkit_source_masters_are_not_in_runtime_sound_directory():
    assert not any(name.startswith('mixkit-')
                   for name in os.listdir(sound._sound_dir()))


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


def test_play_for_dialogue_covers_conquer_results(monkeypatch):
    """Conquer land outcomes must trigger win/lose stingers too — their
    titles are 'Land Conquered!' / 'Land Lost!' / 'Attack Failed' / etc."""
    cases = {
        'Land Conquered!': 'conquer_win',
        'Defence Successful!': 'conquer_win',
        'Land Lost!': 'battle_lose',
        'Attack Failed': 'battle_lose',
        'Draw!': 'ui_back',
    }
    for title, expected in cases.items():
        played = []
        monkeypatch.setattr(sound, 'play',
                            lambda name, volume=1.0: played.append(name) or True)
        sound.play_for_dialogue(title)
        assert played == [expected], (title, played)
