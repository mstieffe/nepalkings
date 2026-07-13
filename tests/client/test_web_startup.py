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
    assert "new Audio(cdn + 'empty.ogg')" in index_html
    assert 'while not platform.window.MM.UME:' in index_html
    assert "document.getElementById('canvas').click()" not in index_html
