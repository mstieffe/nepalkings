# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""One-time tutorial for conquer/defence card lock and loot rules."""

from pygame.locals import QUIT


LOOT_RISK_TUTORIAL_ID = 'loot_risk_intro'


def loot_risk_tutorial_seen(screen):
    state = getattr(screen, 'state', None)
    if getattr(state, 'user_dict', None) is None:
        return True
    onboarding = {}
    getter = getattr(screen, '_onboarding', None)
    if callable(getter):
        onboarding = getter() or {}
    if onboarding.get('onboarding_skipped'):
        return True
    seen_getter = getattr(screen, '_menu_coach_seen', None)
    seen = seen_getter() if callable(seen_getter) else set()
    return LOOT_RISK_TUTORIAL_ID in set(seen or [])


def build_loot_risk_tutorial(window):
    from game.components.tutorial_window import TutorialWindowDialogue
    from game.components import tutorial_diagrams as td

    return TutorialWindowDialogue(
        window,
        [
            {
                'title': 'Cards, Locks, and Loot',
                'layout': 'image_top',
                'image': lambda: td.loot_risk_diagram(),
                'image_caption': 'Committed cards are locked, not spent.',
                'lines': [
                    'Attack and defence cards stay locked while active.',
                    'Starting a battle or saving defence does not consume them.',
                    'If you lose, only looted cards are lost.',
                    'Every unlooted card returns to your collection.',
                    'Higher-tier lands and loot skills can increase how many cards are looted.',
                ],
            },
        ],
        title='Conquer Loot',
    )


def open_loot_risk_tutorial(screen, action):
    screen._loot_risk_tutorial_action = action
    screen._loot_risk_tutorial_dialogue = build_loot_risk_tutorial(screen.window)


def draw_loot_risk_tutorial(screen):
    win = getattr(screen, '_loot_risk_tutorial_dialogue', None)
    if win is not None:
        win.draw()


def handle_loot_risk_tutorial_events(screen, events):
    win = getattr(screen, '_loot_risk_tutorial_dialogue', None)
    if win is None:
        return None
    if any(getattr(event, 'type', None) == QUIT for event in events):
        return False
    if win.update(events) == 'done':
        screen._loot_risk_tutorial_dialogue = None
        marker = getattr(screen, '_mark_menu_coach_seen', None)
        if callable(marker):
            marker(LOOT_RISK_TUTORIAL_ID)
        action = getattr(screen, '_loot_risk_tutorial_action', None)
        screen._loot_risk_tutorial_action = None
        return action or True
    return True
