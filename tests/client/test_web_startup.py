# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Web startup regressions."""

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pygame


def test_web_startup_defers_heavy_screens(monkeypatch):
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    os.environ.setdefault('NK_SCREEN_WIDTH', '854')
    os.environ.setdefault('NK_SCREEN_HEIGHT', '480')

    import nepal_kings as nk
    from config import settings

    created = []

    def screen_class(name):
        class DummyScreen:
            @staticmethod
            def _load_bg():
                return pygame.Surface(
                    (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))

            def __init__(self, state, *args, **kwargs):
                self.state = state
                created.append(name)

            def on_enter(self):
                pass

            def handle_events(self, events):
                pass

            def update(self, events):
                pass

            def render(self):
                pass

        return DummyScreen

    for name in (
            'LoginScreen',
            'GameMenuScreen',
            'DuelMenuScreen',
            'NewGameScreen',
            'LoadGameScreen',
            'RankingScreen',
            'SettingsScreen',
            'KingdomScreen',
            'KingdomConfigScreen',
            'ConquerScreen',
            'DefenceScreen',
            'CollectionScreen',
            'GameScreen',
            'ConquerGameScreen'):
        monkeypatch.setattr(nk, name, screen_class(name))
    monkeypatch.setattr(nk._sys, 'platform', 'emscripten')

    client = nk.Client()

    eager_keys = {'login'}
    lazy_keys = {
        'game_menu',
        'duel_menu',
        'new_game',
        'load_game',
        'rankings',
        'settings',
        'kingdom',
        'kingdom_config',
        'conquer',
        'defence',
        'collection',
        'game',
        'conquer_game',
    }

    assert set(client.screens) == eager_keys
    for key in lazy_keys:
        assert key not in client.screens
        assert key in client._screen_factories
    assert created == ['LoginScreen']
    assert 'ConquerScreen' not in created
    assert 'DefenceScreen' not in created
    assert 'GameScreen' not in created
    assert 'ConquerGameScreen' not in created

    client._create_screen('conquer')

    assert 'conquer' in client.screens
    assert 'ConquerScreen' in created


def test_web_loader_done_waits_for_first_rendered_frame(monkeypatch):
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    os.environ.setdefault('NK_SCREEN_WIDTH', '854')
    os.environ.setdefault('NK_SCREEN_HEIGHT', '480')

    import nepal_kings as nk
    from config import settings

    js_calls = []

    class LoginScreen:
        @staticmethod
        def _load_bg():
            return pygame.Surface(
                (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))

        def __init__(self, state, *args, **kwargs):
            self.state = state

        def on_enter(self):
            pass

        def handle_events(self, events):
            pass

        def update(self, events):
            pass

        def render(self):
            self.state.screen = 'done'

    class LazyScreen(LoginScreen):
        pass

    fake_embed = SimpleNamespace(js=js_calls.append)
    monkeypatch.setitem(sys.modules, 'embed', fake_embed)
    monkeypatch.setattr(nk._sys, 'platform', 'emscripten')
    monkeypatch.setattr(nk, 'LoginScreen', LoginScreen)
    for name in (
            'GameMenuScreen',
            'DuelMenuScreen',
            'NewGameScreen',
            'LoadGameScreen',
            'RankingScreen',
            'SettingsScreen',
            'KingdomScreen',
            'KingdomConfigScreen',
            'ConquerScreen',
            'DefenceScreen',
            'CollectionScreen',
            'GameScreen',
            'ConquerGameScreen'):
        monkeypatch.setattr(nk, name, LazyScreen)

    client = nk.Client()

    assert not any('nk_loader_done' in call for call in js_calls)

    asyncio.run(client.run_screen('login'))

    done_calls = [call for call in js_calls if 'nk_loader_done' in call]
    assert len(done_calls) == 1

    client._notify_web_loader_ready()
    assert [call for call in js_calls if 'nk_loader_done' in call] == done_calls


def test_web_loader_requires_python_ready_and_canvas_ready():
    repo_root = Path(__file__).resolve().parents[2]
    index_html = (repo_root / 'nepal_kings/web/index.html').read_text()

    assert 'if (pyReady && canvasUp) done = true;' in index_html


def test_web_audio_gate_requires_real_user_gesture():
    repo_root = Path(__file__).resolve().parents[2]
    index_html = (repo_root / 'nepal_kings/web/index.html').read_text()

    assert 'ume_block : 1' in index_html
    assert 'window.nk_prepare_audio_gate' in index_html
    assert "new URL('audio/ui_click.mp3', document.baseURI)" in index_html
    assert 'Promise.resolve(window.nk_audio_unlock())' in index_html
    assert 'Promise.all([nativeAttempt, mediaAttempt])' in index_html
    assert "ctx.state === 'running'" in index_html
    assert 'while not platform.window.MM.UME:' in index_html
    assert "document.getElementById('canvas').click()" not in index_html


def test_web_audio_gate_arms_only_after_loading_bar_is_full():
    repo_root = Path(__file__).resolve().parents[2]
    index_html = (repo_root / 'nepal_kings/web/index.html').read_text()

    assert "loader.dataset.audioGate = 'filling';" in index_html
    assert 'window.nk_fill_before_audio_gate(armGate);' in index_html
    assert 'if (loader.dataset.audioGate !== \'ready\') return;' in index_html
    assert 'shown = 1;' in index_html
    assert 'if (armGate) armGate();' in index_html


def test_web_uses_native_audio_manager_and_publishes_direct_assets():
    repo_root = Path(__file__).resolve().parents[2]
    index_html = (repo_root / 'nepal_kings/web/index.html').read_text()
    build_script = (repo_root / 'scripts/build_web.sh').read_text()
    deploy_workflow = (
        repo_root / '.github/workflows/deploy-web.yml').read_text()
    login_screen = (
        repo_root / 'nepal_kings/game/screens/login_screen.py').read_text()

    assert "new AudioContextClass({latencyHint: 'playback'})" in index_html
    assert "new AudioContextClass();" in index_html
    assert 'WEB_BUNDLE_VERSION = "__NK_WEB_BUNDLE_VERSION__"' in index_html
    assert 'versioned_bundle_url("nepal_kings.apk")' in index_html
    assert 'versioned_bundle_url("nepal_kings.tar.gz")' in index_html
    assert "'audio/' + encodeURIComponent(candidate)" in index_html
    assert "url.searchParams.set('v', webBuildId);" in index_html
    assert "var webBuildId = '__NK_WEB_BUNDLE_VERSION__';" in index_html
    assert 'buildId: webBuildId' in index_html
    assert "preferredExtension = supportsOgg ? '.ogg' : '.mp3'" in index_html
    assert "navigator.audioSession.type = 'playback';" in index_html
    assert 'audioSessionType: audioSessionType' in index_html
    assert 'return loadCandidate(ctx, filenames, index + 1);' in index_html
    assert 'window.nk_audio_status' in index_html
    assert 'musicFilename: currentMusic ? currentMusic.filename : null' in index_html
    assert 'window.nk_audio_play_sfx' in index_html
    assert 'window.nk_audio_play_music' in index_html
    assert 'window.nk_audio_resume' in index_html
    assert 'source.loop = true;' in index_html
    assert 'window.nk_keyboard_register' in index_html
    assert 'window.nk_keyboard_focus' in index_html
    assert 'window.nk_keyboard_poll' in index_html
    assert 'window.nk_keyboard_set_value' in index_html
    assert 'window.nk_keyboard_set_enabled' in index_html
    assert 'if (!record || !record.dirty) return null;' in index_html
    assert 'id="nk-keyboard-layer"' in index_html
    assert 'id="nk-keyboard-overlay"' not in index_html
    assert 'id="nk-keyboard-done"' not in index_html
    assert 'function keepKeyboardEventLocal(event)' in index_html
    assert 'event.stopPropagation();' in index_html
    assert 'event.stopImmediatePropagation();' in index_html
    assert "['keypress', 'keyup'].forEach" in index_html
    assert "input.addEventListener('keydown'" in index_html
    assert "['click', 'pointerup', 'touchend', 'keydown', 'focusin']" in index_html
    assert login_screen.count('web_overlay=True') == 2
    assert '_register_mobile_web_inputs()' in login_screen
    assert 'field_username.sync_web_input()' in login_screen
    assert 'field_pwd.sync_web_input()' in login_screen
    assert 'WEB_AUDIO_STAGE=' in build_script
    assert 'WEB_BUILD_ID="${GITHUB_SHA:-}"' in build_script
    assert 's/__NK_WEB_BUNDLE_VERSION__/${WEB_BUILD_ID}/g' in build_script
    assert "'*.mp3'" in build_script
    assert 'WEB_OGG_COUNT' in build_script
    assert 'WEB_MP3_COUNT' in build_script
    assert '"$WEB_OUT/audio"' in build_script
    assert "- 'scripts/build_web.sh'" in deploy_workflow
