# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Layout regressions for the shared clickable-reward dialogue."""

import pygame


def _display():
    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    if not pygame.font.get_init():
        pygame.font.init()


def test_tutorial_kicker_adds_two_level_header_and_body_clearance(monkeypatch):
    from config import settings
    from game.components import rewards_reveal_dialogue as reward_dialogue

    _display()
    monkeypatch.setattr(
        reward_dialogue,
        '_load_chest_image',
        lambda: pygame.Surface((64, 64), pygame.SRCALPHA),
    )
    surface = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    kwargs = {
        'window': surface,
        'title': 'Your Welcome Gift',
        'icon': None,
        'summary_lines': ['Every kingdom is built on cards.'],
        'items': [],
    }

    regular = reward_dialogue.RewardsRevealDialogueBox(**kwargs)
    tutorial = reward_dialogue.RewardsRevealDialogueBox(
        **kwargs,
        kicker='Welcome to Nepal Kings',
    )

    assert tutorial.kicker == 'Welcome to Nepal Kings'
    assert tutorial._header_h > regular._header_h
    regular_body_top = (
        regular.rect.y
        + settings.DIALOGUE_BOX_TEXT_MARGIN_Y
        + regular._header_h
    )
    tutorial_body_top = (
        tutorial.rect.y
        + settings.DIALOGUE_BOX_TEXT_MARGIN_Y
        + tutorial._header_h
    )
    assert tutorial_body_top > regular_body_top
    tutorial.draw()  # The opt-in header remains renderable as a full dialogue.


def test_revealed_reward_captions_wrap_inside_their_slots(monkeypatch):
    from config import settings
    from game.components import rewards_reveal_dialogue as reward_dialogue

    _display()
    icon = pygame.Surface((64, 64), pygame.SRCALPHA)
    monkeypatch.setattr(reward_dialogue, '_load_chest_image', lambda: icon)
    monkeypatch.setattr(reward_dialogue, '_load_reward_icon', lambda kind: icon)
    surface = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    dialogue = reward_dialogue.RewardsRevealDialogueBox(
        surface,
        title='Your Welcome Gift',
        icon=None,
        summary_lines=['Every kingdom is built on cards.'],
        items=[
            {'kind': 'gold', 'label': '2000 gold', 'description': 'Gold.'},
            {'kind': 'main_booster', 'label': '2 main boosters',
             'description': 'Main cards.'},
            {'kind': 'side_booster', 'label': '1 side booster',
             'description': 'Side cards.'},
        ],
        kicker='Welcome to Nepal Kings',
    )

    for item in dialogue.items:
        item.revealed = True
        assert 1 <= len(item.caption_lines) <= 2
        assert all(
            dialogue.caption_font.size(line)[0] <= dialogue._caption_max_w
            for line in item.caption_lines
        )

    # Neighbouring captions retain a real gutter instead of touching.
    first_row = dialogue._chest_rows[0]
    for left, right in zip(first_row, first_row[1:]):
        left_w = max(dialogue.caption_font.size(line)[0]
                     for line in left.caption_lines)
        right_w = max(dialogue.caption_font.size(line)[0]
                      for line in right.caption_lines)
        clear_space = (
            right.rect.centerx - left.rect.centerx - (left_w + right_w) / 2)
        assert clear_space >= 2

    dialogue._last_revealed_item = dialogue.items[-1]
    dialogue.draw()


def test_completion_reward_keeps_chest_reveal_with_specific_action(monkeypatch):
    from config import settings
    from game.components import rewards_reveal_dialogue as reward_dialogue

    _display()
    icon = pygame.Surface((64, 64), pygame.SRCALPHA)
    monkeypatch.setattr(reward_dialogue, '_load_chest_image', lambda: icon)
    monkeypatch.setattr(reward_dialogue, '_load_reward_icon', lambda kind: icon)
    dialogue = reward_dialogue.RewardsRevealDialogueBox(
        pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)),
        title='First Journey Complete!',
        icon=None,
        summary_lines=['Well played.'],
        items=[{'kind': 'map', 'label': '4 maps'}],
        ok_label='Finish tutorial',
    )
    dialogue._created_at = pygame.time.get_ticks() - 1000

    assert all(not item.revealed for item in dialogue.items)
    assert dialogue._ok_button.text == 'Finish tutorial'
    dialogue.update([])
    assert dialogue._ok_button.disabled is True
    dialogue.items[0].revealed = True
    event = pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=1, pos=dialogue._ok_button.rect.center)
    assert dialogue.update([event]) == 'ok'
