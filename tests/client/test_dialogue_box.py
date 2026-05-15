# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for DialogueBox grouped card presentation."""


def test_grouped_card_sections_wrap_rows_and_draw():
    from config import settings
    from game.components.dialogue_box import DialogueBox
    import pygame

    pygame.display.set_mode((1, 1))
    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    cards = [pygame.Surface((70, 100), pygame.SRCALPHA) for _ in range(13)]

    box = DialogueBox(
        window,
        'Review cards before confirming.',
        actions=['Confirm', 'Cancel'],
        title='Card Costs',
        image_groups=[{
            'key': 'locked',
            'title': 'Locked while configured',
            'description': 'These cards stay in your deck, but cannot be used elsewhere.',
            'icon': 'lock',
            'badge_icon': 'lock',
            'items': cards,
        }],
    )

    assert len(box.image_groups) == 1
    group = box.image_groups[0]
    assert group['key'] == 'locked'
    assert group['icon'] is not None
    assert group['badge_icon'] is not None
    assert len(group['rows']) >= 2
    assert box.image_captions == []

    for row in group['rows']:
        assert box._row_width(row) <= box._group_max_w

    box.draw()


def test_grouped_card_sections_use_more_tile_for_large_groups():
    from config import settings
    from game.components.dialogue_box import DialogueBox
    import pygame

    pygame.display.set_mode((1, 1))
    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    cards = [pygame.Surface((70, 100), pygame.SRCALPHA) for _ in range(20)]

    box = DialogueBox(
        window,
        'Review cards before confirming.',
        actions=['OK'],
        title='Card Costs',
        image_groups=[{
            'key': 'consumed',
            'title': 'Consumed now',
            'description': 'These cards are removed when you confirm.',
            'icon': 'remove',
            'badge_icon': 'remove',
            'items': cards,
        }],
    )

    flattened = [item for row in box.image_groups[0]['rows'] for item in row]
    assert any(item['kind'] == 'more' and item['text'] == '+4' for item in flattened)


def test_dialogue_ignores_mouse_wheel_release_for_actions(monkeypatch):
    from config import settings
    from game.components.dialogue_box import DialogueBox
    import pygame

    pygame.display.set_mode((1, 1))
    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))

    box = DialogueBox(
        window,
        'Sell selected cards?',
        actions=['Sell', 'Cancel'],
        title='Sell Card',
    )

    # Hover over the first button so event filtering is the only gate.
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: box.buttons[0].rect.center)
    box._created_at = pygame.time.get_ticks() - 500

    wheel_release = pygame.event.Event(
        pygame.MOUSEBUTTONUP,
        {'button': 4, 'pos': box.buttons[0].rect.center},
    )
    left_release = pygame.event.Event(
        pygame.MOUSEBUTTONUP,
        {'button': 1, 'pos': box.buttons[0].rect.center},
    )

    assert box.update([wheel_release]) is None
    assert box.update([left_release]) == 'sell'
