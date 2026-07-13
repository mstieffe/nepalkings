# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the Python-to-Web-Audio bridge."""

import sys
import types

from utils import web_audio


def test_non_web_bridge_is_a_noop(monkeypatch):
    monkeypatch.setattr(web_audio, '_IS_WEB', False)
    assert web_audio.play_sfx('ui_click.ogg', 0.5) is False


def test_web_bridge_serializes_audio_calls(monkeypatch):
    calls = []
    fake_embed = types.SimpleNamespace(
        js=lambda script: calls.append(script) or True)
    monkeypatch.setitem(sys.modules, 'embed', fake_embed)
    monkeypatch.setattr(web_audio, '_IS_WEB', True)

    assert web_audio.play_sfx('spell_cast.ogg', 0.75) is True
    assert web_audio.play_music('music_battle.ogg', 0.2, 700) is True
    assert web_audio.stop_music(350) is True

    assert calls == [
        'window.nk_audio_play_sfx&&window.nk_audio_play_sfx('
        '"spell_cast.ogg",0.75)',
        'window.nk_audio_play_music&&window.nk_audio_play_music('
        '"music_battle.ogg",0.2,700)',
        'window.nk_audio_stop_music&&window.nk_audio_stop_music(350)',
    ]
