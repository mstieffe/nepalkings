from types import SimpleNamespace

import pygame


def _tile(**overrides):
    data = {
        'col': 2,
        'row': 3,
        'tier': 1,
        'gold_rate': 1.0,
        'suit_bonus_suit': 'Neutral',
        'suit_bonus_value': 0,
        'owner': {'owned_since': '2026-05-11T00:00:00'},
        'owner_username': 'rival',
        'owner_user_id': 42,
        'is_mine': False,
        'defence_incomplete': False,
        'kingdom_component_size': 0,
        'kingdom_bonuses': {},
        'kingdom_shield_remaining': 0,
        'kingdom_shield_reason': None,
        'land_id': 7,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _box(tile, **kwargs):
    from config import settings
    from game.components.land_detail_box import LandDetailBox

    pygame.display.set_mode((1, 1))
    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    return LandDetailBox(window, tile, **kwargs)


def _button(box, action):
    return next(btn for name, btn in box._buttons if name == action)


def test_conquer_button_allows_click_during_player_cooldown(monkeypatch):
    called = []
    tile = _tile()
    box = _box(tile, cooldown=3600, on_conquer=lambda clicked: called.append(clicked))
    button = _button(box, 'conquer')

    assert button.disabled is False
    assert button.sub_text is None

    box._created_at = pygame.time.get_ticks() - 500
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: button.rect.center)
    event = pygame.event.Event(
        pygame.MOUSEBUTTONUP,
        button=1,
        pos=button.rect.center,
    )

    assert box.handle_event(event) == 'conquer'
    assert called == [tile]


def test_conquer_button_remains_disabled_by_kingdom_shield(monkeypatch):
    called = []
    tile = _tile(kingdom_shield_remaining=300)
    box = _box(tile, cooldown=0, on_conquer=lambda clicked: called.append(clicked))
    button = _button(box, 'conquer')

    assert button.disabled is True
    assert button.sub_text == 'Shield: 5m 0s'

    box._created_at = pygame.time.get_ticks() - 500
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: button.rect.center)
    event = pygame.event.Event(
        pygame.MOUSEBUTTONUP,
        button=1,
        pos=button.rect.center,
    )

    assert box.handle_event(event) is None
    assert called == []