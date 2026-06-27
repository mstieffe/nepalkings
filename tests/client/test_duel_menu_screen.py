# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the duel menu tutorial entry window."""

from types import SimpleNamespace

import pygame


def _duel_menu_screen(*, seen=None, completed=None, skipped=False, pending=False):
    from game.screens.duel_menu_screen import DuelMenuScreen

    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    if not pygame.font.get_init():
        pygame.font.init()

    screen = DuelMenuScreen.__new__(DuelMenuScreen)
    screen.window = pygame.Surface((900, 600))
    screen.dialogue_box = None
    screen._onboarding_guide_open = False
    screen._duel_tutorial_intro_dialogue = None
    screen.state = SimpleNamespace(
        user_dict={'onboarding': {
            'menu_hints_seen': list(seen or []),
            'completed_steps': list(completed or []),
            'onboarding_skipped': skipped,
        }},
        pending_duel_tutorial_intro=pending,
    )
    return DuelMenuScreen, screen


def test_duel_tutorial_intro_pages_explain_core_loop():
    _cls, screen = _duel_menu_screen()

    parts = []
    images = []
    for page in screen._duel_tutorial_intro_pages():
        parts.append(page.get('title', ''))
        parts.extend(page.get('lines', []))
        images.append(page.get('image')())
    text = ' '.join(parts)

    assert 'heart' in text.lower()
    assert 'chess-like' in text
    assert 'building phases' in text
    assert 'battle phases' in text
    assert 'same pool of cards' in text
    assert 'agreed point goal' in text
    assert all(isinstance(image, pygame.Surface) for image in images)


def test_duel_menu_auto_opens_intro_on_first_visit():
    DuelMenuScreen, screen = _duel_menu_screen()

    DuelMenuScreen._maybe_show_duel_tutorial_intro_window(screen)

    assert screen._duel_tutorial_intro_dialogue is not None


def test_duel_menu_intro_suppressed_after_seen_or_completion():
    for kwargs in (
        {'seen': ['duel_tutorial_start_window']},
        {'completed': ['finish_first_duel']},
        {'skipped': True},
    ):
        DuelMenuScreen, screen = _duel_menu_screen(**kwargs)

        DuelMenuScreen._maybe_show_duel_tutorial_intro_window(screen)

        assert screen._duel_tutorial_intro_dialogue is None


def test_pending_duel_intro_forces_window_even_if_already_seen():
    DuelMenuScreen, screen = _duel_menu_screen(
        seen=['duel_tutorial_start_window'],
        pending=True,
    )

    DuelMenuScreen._maybe_show_duel_tutorial_intro_window(screen)

    assert screen._duel_tutorial_intro_dialogue is not None


def test_duel_intro_done_marks_seen_and_clears_pending():
    DuelMenuScreen, screen = _duel_menu_screen(pending=True)
    marked = []
    screen._duel_tutorial_intro_dialogue = SimpleNamespace(
        update=lambda events: 'done',
    )
    screen._mark_menu_coach_seen = lambda step_id: marked.append(step_id)

    handled = DuelMenuScreen._handle_duel_tutorial_intro_events(screen, [])

    assert handled is True
    assert screen._duel_tutorial_intro_dialogue is None
    assert screen.state.pending_duel_tutorial_intro is False
    assert marked == ['duel_tutorial_start_window']
