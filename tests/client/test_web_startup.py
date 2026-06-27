# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Web startup regressions."""

import os

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
