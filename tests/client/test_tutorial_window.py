# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the paginated tutorial window and runtime teaching diagrams."""

import pygame


def _display():
    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    if not pygame.font.get_init():
        pygame.font.init()


def _click(rect):
    return pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=1, pos=rect.center)


def _window(pages):
    from game.components.tutorial_window import TutorialWindowDialogue
    _display()
    win = TutorialWindowDialogue(None, pages, title='Welcome')
    # Bypass the 200ms anti-double-click guard.
    win._created_at = pygame.time.get_ticks() - 1000
    return win


def test_window_navigates_next_back_and_done():
    pages = [
        {'title': 'Page 1', 'lines': ['a']},
        {'title': 'Page 2', 'lines': ['b']},
    ]
    win = _window(pages)
    assert win.page_index == 0
    assert win._btn_next.text == 'Next'  # set during draw, but default Next

    # Next advances.
    assert win.update([_click(win._btn_next.rect)]) is None
    assert win.page_index == 1

    # Back returns to page 0.
    assert win.update([_click(win._btn_back.rect)]) is None
    assert win.page_index == 0


def test_window_last_page_next_returns_done():
    win = _window([{'title': 'Only', 'lines': ['x']}])
    # Single page -> immediately last; Next returns done.
    assert win._is_last is True
    assert win.update([_click(win._btn_next.rect)]) == 'done'


def test_window_back_disabled_on_first_page():
    win = _window([{'lines': ['x']}, {'lines': ['y']}])
    win.update([])  # refresh button disabled state
    assert win._btn_back.disabled is True
    # Clicking where Back is does nothing on page 0.
    assert win.update([_click(win._btn_back.rect)]) is None
    assert win.page_index == 0


def test_window_ignores_clicks_within_200ms():
    from game.components.tutorial_window import TutorialWindowDialogue
    _display()
    win = TutorialWindowDialogue(None, [{'lines': ['x']}], title='T')
    # Fresh: clicks ignored.
    assert win.update([_click(win._btn_next.rect)]) is None


def test_diagrams_return_surfaces_and_cache():
    _display()
    from game.components import tutorial_diagrams
    tutorial_diagrams.clear_cache()
    combo = tutorial_diagrams.card_combo_to_figure(120)
    wheel = tutorial_diagrams.suit_advantage_wheel(200)
    assert isinstance(combo, pygame.Surface)
    assert isinstance(wheel, pygame.Surface)
    # Cached: same object returned on second call.
    assert tutorial_diagrams.card_combo_to_figure(120) is combo
    assert tutorial_diagrams.suit_advantage_wheel(200) is wheel


def _reveal(off='Hearts', deff='Spades'):
    from game.components.tutorial_window import StarterSuitRevealDialogue
    _display()
    r = StarterSuitRevealDialogue(None, off, deff)
    r._created_at = pygame.time.get_ticks() - 1000
    return r


def test_reveal_runs_offensive_then_defensive_then_done():
    from game.components import tutorial_window as tw
    r = _reveal('Diamonds', 'Clubs')
    # Force the offensive spin to finish.
    r._phase_started = pygame.time.get_ticks() - (tw._REEL_SPIN_MS + 50)
    assert r.update([]) is None
    assert r._phase == 'off_done'
    assert r._current_reel_suit() == 'Diamonds'

    # Clicking advances to the defensive spin.
    assert r.update([_click(r._btn.rect)]) is None
    assert r._phase == 'def_spin'

    # Finish the defensive spin, then acknowledge -> done.
    r._phase_started = pygame.time.get_ticks() - (tw._REEL_SPIN_MS + 50)
    assert r.update([]) is None
    assert r._phase == 'def_done'
    assert r._current_reel_suit() == 'Clubs'
    assert r.update([_click(r._btn.rect)]) == 'done'


def test_reveal_button_disabled_while_spinning():
    r = _reveal()
    r.update([])  # still spinning
    assert r._btn.disabled is True
    # A click while spinning is ignored.
    assert r.update([_click(r._btn.rect)]) is None


def _kinds(win, page):
    return [kind for _surf, kind, _gap in win._page_rows(page)]


def test_page_rows_order_respects_layout():
    from game.components.tutorial_window import TutorialWindowDialogue
    _display()
    img = pygame.Surface((40, 20))
    win = TutorialWindowDialogue(None, [{'lines': ['x']}], title='T')

    top = {'title': 'H', 'layout': 'image_top', 'image': img,
           'image_caption': 'c', 'lines': ['a', 'b']}
    assert _kinds(win, top) == ['headline', 'image', 'caption', 'text', 'text']

    bottom = {'title': 'H', 'layout': 'image_bottom', 'image': img,
              'lines': ['a']}
    assert _kinds(win, bottom) == ['headline', 'text', 'image']

    text_only = {'title': 'H', 'layout': 'text_only', 'image': img,
                 'lines': ['a', 'b']}
    assert _kinds(win, text_only) == ['headline', 'text', 'text']

    image_only = {'title': 'H', 'layout': 'image_only', 'image': img,
                  'lines': ['a']}
    assert _kinds(win, image_only) == ['headline', 'image']


def _real_window():
    _display()
    import pygame as pg
    return pg.Surface((pg.display.get_surface().get_width() or 1280,
                       pg.display.get_surface().get_height() or 800))


def test_window_draw_runs_for_each_layout():
    from game.components import tutorial_diagrams
    from game.components.tutorial_window import TutorialWindowDialogue
    win_surf = _real_window()
    pages = [
        {'title': 'A Chess of Cards', 'layout': 'image_bottom',
         'lines': ['hook line one', 'hook line two'],
         'image': lambda: tutorial_diagrams.card_combo_to_figure(),
         'image_caption': 'Jack + 7 build a Farm.'},
        {'title': 'Suits Win Battles', 'layout': 'image_top',
         'image': lambda: tutorial_diagrams.suit_advantage_wheel(),
         'lines': ['attack and defend']},
        {'title': 'Text Only', 'layout': 'text_only', 'lines': ['just text']},
    ]
    win = TutorialWindowDialogue(win_surf, pages, title='Welcome to Nepal Kings')
    for _ in range(len(pages)):
        win.draw()  # must not raise
        win.page_index = min(win.page_index + 1, len(pages) - 1)


def test_reveal_draw_runs_through_phases():
    from game.components.tutorial_window import StarterSuitRevealDialogue
    win_surf = _real_window()
    r = StarterSuitRevealDialogue(win_surf, 'Hearts', 'Spades')
    r.draw()                       # off_spin
    r._phase = 'off_done'
    r.draw()                       # off_done
    r._phase = 'def_spin'
    r.draw()                       # def_spin
    r._phase = 'def_done'
    r.draw()                       # def_done


def test_figure_button_and_dagger_diagrams_build_and_cache():
    _display()
    from game.components import tutorial_diagrams
    tutorial_diagrams.clear_cache()
    off = tutorial_diagrams.figure_buttons('offensive', 120)
    deff = tutorial_diagrams.figure_buttons('defensive', 120)
    dag = tutorial_diagrams.daggers_diagram(140)
    assert isinstance(off, pygame.Surface)
    assert isinstance(deff, pygame.Surface)
    assert isinstance(dag, pygame.Surface)
    assert tutorial_diagrams.figure_buttons('offensive', 120) is off
    assert tutorial_diagrams.daggers_diagram(140) is dag


def test_new_recipe_and_land_diagrams_build():
    _display()
    from game.components import tutorial_diagrams as td
    td.clear_cache()
    assert isinstance(td.card_recipe_examples(), pygame.Surface)
    assert isinstance(td.figure_anatomy_diagram(), pygame.Surface)
    assert isinstance(td.land_hex_diagram(), pygame.Surface)
    assert isinstance(td.starter_set_breakdown('offensive', 'Hearts'), pygame.Surface)
    assert isinstance(td.starter_set_breakdown('defensive', 'Spades'), pygame.Surface)


def test_field_compartments_and_recipe_alignment():
    _display()
    from game.components import tutorial_diagrams as td
    td.clear_cache()
    assert isinstance(td.field_compartments_diagram(), pygame.Surface)
    # Recipe examples now show one figure + one spell (King removed).
    examples = td.card_recipe_examples()
    assert isinstance(examples, pygame.Surface)
