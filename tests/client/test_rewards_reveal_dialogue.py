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
