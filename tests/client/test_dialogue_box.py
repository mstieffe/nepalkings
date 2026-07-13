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


def test_grouped_dialogue_keeps_a_lead_image_beside_message():
    from config import settings
    from game.components.dialogue_box import DialogueBox
    import pygame

    pygame.display.set_mode((1, 1))
    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    card = pygame.Surface((60, 90), pygame.SRCALPHA)
    use_icon = pygame.Surface((48, 48), pygame.SRCALPHA)

    box = DialogueBox(
        window,
        'Uncommon Main Card\n3 owned  ·  2 free  ·  1 in use',
        actions=['Close'],
        title='Hearts A',
        images=[card],
        image_groups=[{
            'title': 'Figures',
            'items': [use_icon],
            'item_tooltips': ['Gorkha Warriors'],
        }],
    )

    assert box._lead_items
    assert box.ordered_items == []
    assert box.text_height >= box.lead_height
    box.draw()


def test_grouped_dialogue_supports_single_feature_item_layout():
    from config import settings
    from game.components.dialogue_box import DialogueBox
    import pygame

    pygame.display.set_mode((1, 1))
    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    icon = pygame.Surface((48, 48), pygame.SRCALPHA)

    box = DialogueBox(
        window,
        'Premium Castle Card',
        actions=['Close'],
        title='Maharaja',
        image_groups=[{
            'title': 'Builds',
            'items': [icon],
            'item_tooltips': ['Maharaja figure'],
            'count': 1,
            'item_unit': 'figure',
            'feature_item': True,
            'description': 'Power 16 castle with extra support slots.',
        }],
    )

    group = box.image_groups[0]
    assert group['feature_item'] is True
    assert len(group['rows']) == 1
    assert group['height'] < (
        settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT
        + settings.DIALOGUE_BOX_GROUP_HEADER_GAP
        + settings.DIALOGUE_BOX_GROUP_PADDING_Y * 2
        + settings.FS_SMALL
    )
    box.draw()


def test_grouped_dialogue_rewraps_message_beside_lead_image():
    from config import settings
    from game.components.dialogue_box import DialogueBox
    import pygame

    pygame.display.set_mode((1, 1))
    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    lead = pygame.Surface((120, 180), pygame.SRCALPHA)
    item = pygame.Surface((48, 48), pygame.SRCALPHA)
    message = (
        'Trade one free copy of every Hearts rank (2-A) for the card that '
        'builds your Djungle Maharaja.')

    box = DialogueBox(
        window,
        message,
        actions=['Craft', 'cancel'],
        images=[lead],
        image_groups=[{
            'title': 'Builds',
            'items': [item],
            'feature_item': True,
        }],
    )

    # The lead image reduces the available text column enough to require a
    # tighter wrap than the normal full-width dialogue message.
    full_width_lines = DialogueBox._wrap_text(
        message,
        box.font,
        settings.DIALOGUE_BOX_WIDTH - int(0.08 * settings.SCREEN_WIDTH),
    )
    assert box.lines != full_width_lines
    assert box.lines[0].endswith('for the')
    box.draw()


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


def test_dialogue_actions_use_release_position_when_mouse_pos_is_stale(monkeypatch):
    from config import settings
    from game.components.dialogue_box import DialogueBox
    import pygame

    pygame.display.set_mode((1, 1))
    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))

    box = DialogueBox(
        window,
        'Start conquer battle?',
        actions=['Confirm', 'Cancel'],
        title='To Battle!',
    )

    # Mobile web touch releases can carry the correct event position while the
    # global pygame mouse position still points elsewhere.
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (0, 0))
    box._created_at = pygame.time.get_ticks() - 500

    release = pygame.event.Event(
        pygame.MOUSEBUTTONUP,
        {'button': 1, 'pos': box.buttons[0].rect.center},
    )

    assert box.update([release]) == 'confirm'
