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


def _first_overflowing_line(box):
    """Return the first row whose rendered text exceeds the box, or None."""
    from config import settings
    inner = box._box_rect.w - 2 * settings.LAND_DETAIL_PAD
    for kind, text in box._lines:
        if kind in ('spacer', 'tier'):
            continue
        width = (box._line_font(kind).size(str(text))[0]
                 + box._line_icon_allowance(kind))
        if width > inner:
            return (kind, width, inner, text)
    return None


def _box_on_screen(box):
    from config import settings
    r = box._box_rect
    return (r.x >= 0 and r.y >= 0
            and r.right <= settings.SCREEN_WIDTH
            and r.bottom <= settings.SCREEN_HEIGHT)


def test_land_detail_box_grows_so_long_rows_never_overflow():
    tile = _tile(owner_username='Averylongkingdomownerusername',
                 kingdom_component_size=8, kingdom_bonuses={'loot_chance': 0.2})
    box = _box(tile, on_conquer=lambda *_: None,
               on_message=lambda *_: None)
    assert _first_overflowing_line(box) is None
    assert _box_on_screen(box)


def test_land_detail_box_ellipsizes_rows_wider_than_the_viewport():
    huge = 'Kathmandu Valley Historic Region ' * 20
    region = {'name': huge, 'champions': [], 'champion': None,
              'my_land_count': 0, 'lands_to_champion': 3}
    box = _box(_tile(), on_conquer=lambda *_: None,
               on_message=lambda *_: None, region_info=region)
    assert _first_overflowing_line(box) is None
    assert _box_on_screen(box)
    region_line = next(text for kind, text in box._lines if kind == 'region')
    assert region_line.endswith('…')


def test_land_detail_button_widens_to_fit_its_label():
    from config import settings
    # 'Configure Defence' / 'Configure Kingdom' are the widest labels.
    box = _box(_tile(is_mine=True, defence_incomplete=False),
               on_defence=lambda *_: None, on_config=lambda *_: None)
    defence_btn = _button(box, 'defence')
    label_w = defence_btn.font.size('Configure Defence')[0]
    assert defence_btn.rect.w >= label_w
    assert defence_btn.rect.right <= box._box_rect.right - settings.LAND_DETAIL_PAD // 2 + 1
    assert defence_btn.rect.left >= box._box_rect.left - 1


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


def test_conquer_button_uses_release_position_when_mouse_pos_is_stale(monkeypatch):
    called = []
    tile = _tile()
    box = _box(tile, cooldown=0, on_conquer=lambda clicked: called.append(clicked))
    button = _button(box, 'conquer')

    box._created_at = pygame.time.get_ticks() - 500
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (0, 0))
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
