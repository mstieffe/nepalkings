# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the independent background-music channel."""

import json
import os
import sys
import types
import wave

import pytest

from utils import music, sound


@pytest.fixture(autouse=True)
def _reset_music(tmp_path, monkeypatch):
    cfg_dir = tmp_path / '.nepalkings'
    monkeypatch.setattr(music, '_CFG_DIR', str(cfg_dir))
    monkeypatch.setattr(music, '_CFG_FILE', str(cfg_dir / 'resolution.json'))
    monkeypatch.setattr(music, '_IS_WEB', False)
    monkeypatch.setattr(music, '_enabled', True)
    monkeypatch.setattr(music, '_channel', None)
    monkeypatch.setattr(music, '_cache', {})
    monkeypatch.setattr(music, '_current_track', None)
    monkeypatch.setattr(music, '_requested_track', None)
    yield


def test_every_track_has_desktop_and_web_assets():
    missing = []
    for name, (filename, _gain) in music.TRACKS.items():
        stem, _ext = os.path.splitext(filename)
        for candidate in (filename, stem + '.ogg'):
            if not os.path.exists(os.path.join(sound._sound_dir(), candidate)):
                missing.append(f'{name}:{candidate}')
    assert missing == []


@pytest.mark.parametrize(('track_name', 'expected_duration'), [
    ('menu', 60.0),
    ('kingdom', 60.0),
    ('battle', 45.0),
])
def test_music_is_high_quality_stereo_runtime_edit(track_name, expected_duration):
    path = os.path.join(sound._sound_dir(), music.TRACKS[track_name][0])
    with wave.open(path, 'rb') as wf:
        duration = wf.getnframes() / wf.getframerate()
        assert wf.getframerate() == 44100
        assert wf.getnchannels() == 2
    assert duration == pytest.approx(expected_duration, abs=0.05)
    assert os.path.getsize(path) < 12 * 1024 * 1024


def test_full_music_sources_are_not_in_runtime_sound_directory():
    names = os.listdir(sound._sound_dir())
    assert 'Kora Gate Loop.wav' not in names
    assert 'Kora Gate Loop.mp3' not in names
    assert 'menu.wav' not in names
    assert 'kingdom.wav' not in names
    assert 'battle.wav' not in names


def _install_fake_mixer(monkeypatch, tmp_path):
    loaded = []
    channel = types.SimpleNamespace(
        plays=[], volumes=[], fadeouts=[], stopped=0,
    )

    def set_volume(value):
        channel.volumes.append(value)

    def play(track, loops=0, fade_ms=0):
        channel.plays.append((track.name, loops, fade_ms))

    def fadeout(ms):
        channel.fadeouts.append(ms)

    def stop():
        channel.stopped += 1

    channel.set_volume = set_volume
    channel.play = play
    channel.fadeout = fadeout
    channel.stop = stop

    class FakeSound:
        def __init__(self, path):
            self.name = os.path.basename(path)
            loaded.append(self.name)

    mixer = types.SimpleNamespace(
        Sound=FakeSound,
        Channel=lambda _index: channel,
        set_reserved=lambda _count: None,
    )
    monkeypatch.setitem(sys.modules, 'pygame', types.SimpleNamespace(mixer=mixer))
    monkeypatch.setattr(sound, '_ensure_mixer', lambda: True)
    monkeypatch.setattr(sound, '_sound_dir', lambda: str(tmp_path))
    return channel, loaded


def test_screen_mapping_loops_track_without_restarting_it(tmp_path, monkeypatch):
    (tmp_path / 'music_menu.wav').write_bytes(b'wav')
    channel, loaded = _install_fake_mixer(monkeypatch, tmp_path)

    assert music.play_for_screen('login') is True
    assert music.play_for_screen('settings') is True
    assert loaded == ['music_menu.wav']
    assert channel.plays == [('music_menu.wav', -1, 700)]
    assert channel.volumes == [pytest.approx(
        music.MASTER_VOLUME * music.TRACKS['menu'][1])]


def test_web_track_prefers_ogg(tmp_path, monkeypatch):
    (tmp_path / 'music_menu.wav').write_bytes(b'wav')
    (tmp_path / 'music_menu.ogg').write_bytes(b'ogg')
    _channel, loaded = _install_fake_mixer(monkeypatch, tmp_path)
    monkeypatch.setattr(music, '_IS_WEB', True)
    monkeypatch.setattr(sound, '_IS_WEB', True)

    assert music.play('menu') is True
    assert loaded == ['music_menu.ogg']


def test_disabled_music_remembers_screen_and_resumes(tmp_path, monkeypatch):
    (tmp_path / 'music_battle.wav').write_bytes(b'wav')
    channel, _loaded = _install_fake_mixer(monkeypatch, tmp_path)

    music.set_enabled(False)
    assert music.play_for_screen('game') is False
    assert channel.plays == []
    music.set_enabled(True)
    assert channel.plays == [('music_battle.wav', -1, 700)]


def test_music_preference_preserves_sfx_and_resolution_settings():
    os.makedirs(music._CFG_DIR, exist_ok=True)
    with open(music._CFG_FILE, 'w') as f:
        json.dump({'width': 1280, 'sound_enabled': False}, f)

    music.set_enabled(False)
    with open(music._CFG_FILE) as f:
        assert json.load(f) == {
            'width': 1280,
            'sound_enabled': False,
            'music_enabled': False,
        }
