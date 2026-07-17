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


def test_window_uses_specific_final_action_label_without_pause_button():
    from game.components.tutorial_window import TutorialWindowDialogue
    surf = _real_window()
    win = TutorialWindowDialogue(
        surf,
        [{'title': 'Only', 'lines': ['x'], 'button_label': 'Begin'}],
        title='Tutorial',
    )
    win._created_at = pygame.time.get_ticks() - 1000
    win.draw()

    assert win._btn_next.text == 'Begin'
    assert not hasattr(win, '_btn_pause')


def test_mobile_tutorial_uses_roomy_panel_and_visible_touch_buttons(monkeypatch):
    from config import settings
    from game.components.tutorial_window import TutorialWindowDialogue

    _display()
    monkeypatch.setattr(settings, 'SCREEN_WIDTH', 854)
    monkeypatch.setattr(settings, 'SCREEN_HEIGHT', 480)
    monkeypatch.setattr(settings, 'TOUCH_TARGET_MIN', 58)
    monkeypatch.setattr(settings, 'TOUCH_COMPACT_MIN', 34)
    win = TutorialWindowDialogue(
        pygame.Surface((854, 480)),
        [{'title': 'One', 'lines': ['A useful mobile lesson.']}],
        title='Tutorial',
    )

    assert win.rect.w >= int(0.92 * 854)
    assert win.rect.h >= int(0.85 * 480)
    assert win._btn_next.rect.h >= settings.TOUCH_TARGET_MIN
    assert win._btn_next.rect.centerx == win.rect.centerx
    assert win.rect.contains(win._btn_next.rect)


def test_mobile_map_sidecar_leaves_map_exposed_and_routes_pointer_by_panel(monkeypatch):
    from config import settings
    from game.components.tutorial_window import TutorialWindowDialogue

    _display()
    monkeypatch.setattr(settings, 'SCREEN_WIDTH', 854)
    monkeypatch.setattr(settings, 'SCREEN_HEIGHT', 480)
    monkeypatch.setattr(settings, 'TOUCH_TARGET_MIN', 58)
    monkeypatch.setattr(settings, 'TOUCH_COMPACT_MIN', 34)
    win = TutorialWindowDialogue(
        pygame.Surface((854, 480)),
        [{'title': 'Map', 'lines': ['Drag the exposed map while reading.']}],
        title='Your Kingdom',
        presentation='map_sidecar',
    )

    assert win.background_interactive is True
    assert win._overlay is None
    assert win.rect.left > int(0.45 * settings.SCREEN_WIDTH)
    assert win.rect.right < settings.SCREEN_WIDTH
    outside = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(win.rect.left - 40, win.rect.centery))
    inside = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=win.rect.center)
    assert win.captures_event(outside) is False
    assert win.captures_event(inside) is True


def test_tutorial_navigation_honours_expanded_touch_hit_rect(monkeypatch):
    from config import settings
    from game.components.tutorial_window import TutorialWindowDialogue

    _display()
    monkeypatch.setattr(settings, 'TOUCH_TARGET_MIN', 0)
    win = TutorialWindowDialogue(
        None, [{'title': 'Only', 'lines': ['x']}], title='Tutorial')
    win._created_at = pygame.time.get_ticks() - 1000
    monkeypatch.setattr(settings, 'TOUCH_TARGET_MIN', win._btn_next.rect.h + 20)
    monkeypatch.setattr(settings, 'TOUCH_COMPACT_MIN', win._btn_next.rect.w)
    pos = (win._btn_next.rect.centerx, win._btn_next.rect.top - 5)
    assert not win._btn_next.rect.collidepoint(pos)
    assert win._btn_next.hit_rect().collidepoint(pos)
    event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)
    assert win.update([event]) == 'done'


def test_window_back_disabled_on_first_page():
    win = _window([{'lines': ['x']}, {'lines': ['y']}])
    win.update([])  # refresh button disabled state
    assert win._btn_back.disabled is True
    # Clicking where Back is does nothing on page 0.
    assert win.update([_click(win._btn_back.rect)]) is None
    assert win.page_index == 0


def test_window_scrolls_when_content_overflows():
    from game.components.tutorial_window import TutorialWindowDialogue
    win_surf = _real_window()
    pages = [{'title': 'Tall', 'layout': 'text_only',
              'lines': [f'line {i}' for i in range(40)]}]
    win = TutorialWindowDialogue(win_surf, pages, title='T')
    win._created_at = pygame.time.get_ticks() - 1000
    win.draw()  # computes _max_scroll from the content height
    assert win._max_scroll > 0

    before = win._scroll
    win.update([pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1)])  # wheel down
    assert win._scroll > before
    win.draw()  # rendering while scrolled must not raise

    # Scroll clamps at the bottom.
    for _ in range(200):
        win.update([pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1)])
    assert win._scroll == win._max_scroll
    # Wheel up returns toward the top.
    win.update([pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=5)])
    assert win._scroll < win._max_scroll


def test_short_window_does_not_scroll():
    from game.components.tutorial_window import TutorialWindowDialogue
    win_surf = _real_window()
    win = TutorialWindowDialogue(win_surf, [{'title': 'S', 'lines': ['a']}], title='T')
    win.draw()
    assert win._max_scroll == 0


def test_window_ignores_clicks_within_200ms():
    from game.components.tutorial_window import TutorialWindowDialogue
    _display()
    win = TutorialWindowDialogue(None, [{'lines': ['x']}], title='T')
    # Fresh: clicks ignored.
    assert win.update([_click(win._btn_next.rect)]) is None


def _scrollable_window():
    from config import settings
    from game.components.tutorial_window import TutorialWindowDialogue
    if not pygame.display.get_init():
        pygame.display.init()
    surf = pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    if not pygame.font.get_init():
        pygame.font.init()
    pages = [{'title': 'Scroll Test', 'layout': 'text_only',
              'lines': [f'line {i}' for i in range(60)]}]
    win = TutorialWindowDialogue(surf, pages, title='T')
    win._created_at = pygame.time.get_ticks() - 1000
    win.draw()
    return win


def _evt(kind, **kw):
    return pygame.event.Event(kind, **kw)


def test_scrollbar_thumb_drag_follows_cursor():
    win = _scrollable_window()
    assert win._max_scroll > 0
    track = win._scroll_track_rect
    assert track is not None

    # Grab the thumb and drag DOWN → scroll increases (view goes down).
    win._scroll = 0.0
    win.draw()
    y0 = win._scroll_thumb_top + 2
    win.update([_evt(pygame.MOUSEBUTTONDOWN, button=1, pos=(track.centerx, y0)),
                _evt(pygame.MOUSEMOTION, pos=(track.centerx, y0 + 90))])
    assert win._scroll > 0
    down_scroll = win._scroll
    win.update([_evt(pygame.MOUSEBUTTONUP, button=1, pos=(track.centerx, y0 + 90))])

    # Grab the thumb and drag UP → scroll decreases.
    win.draw()
    y1 = win._scroll_thumb_top + 2
    win.update([_evt(pygame.MOUSEBUTTONDOWN, button=1, pos=(track.centerx, y1)),
                _evt(pygame.MOUSEMOTION, pos=(track.centerx, y1 - 150))])
    assert win._scroll < down_scroll
    win.update([_evt(pygame.MOUSEBUTTONUP, button=1, pos=(track.centerx, y1 - 150))])


def test_content_grab_scroll_still_works():
    win = _scrollable_window()
    win._scroll = 0.0
    win.draw()
    cx, cy = win.rect.centerx, win.rect.centery
    # Touch-style: drag content UP → scroll increases.
    win.update([_evt(pygame.MOUSEBUTTONDOWN, button=1, pos=(cx, cy)),
                _evt(pygame.MOUSEMOTION, pos=(cx, cy - 60))])
    assert win._scroll > 0


def test_tiny_overflow_is_not_scrolled_but_large_overflow_is():
    _display()
    from config import settings
    from game.components.tutorial_window import TutorialWindowDialogue

    surf = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    win = TutorialWindowDialogue(surf, [{'title': 'T', 'lines': ['x']}],
                                 title='Welcome')
    _, avail_h = win._content_region()

    def _rows(height):
        return lambda page: [
            (pygame.Surface((10, height), pygame.SRCALPHA), 'text', 0)]

    # A sliver of overflow must not produce a (near-empty) scrollbar.
    win._page_rows = _rows(avail_h + 6)
    win.draw()
    assert win._max_scroll == 0

    # A genuine overflow still scrolls.
    win._page_rows = _rows(avail_h + 240)
    win.draw()
    assert win._max_scroll > 0


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


def _reveal(suit='Hearts'):
    from game.components.tutorial_window import StarterSuitRevealDialogue
    _display()
    r = StarterSuitRevealDialogue(None, suit)
    r._created_at = pygame.time.get_ticks() - 1000
    return r


def test_reveal_runs_spin_then_done():
    from game.components import tutorial_window as tw
    r = _reveal('Diamonds')
    # Force the spin to finish.
    r._phase_started = pygame.time.get_ticks() - (tw._REEL_SPIN_MS + 50)
    assert r.update([]) == 'revealed'
    assert r._phase == 'done'
    assert r._current_reel_suit() == 'Diamonds'
    # Acknowledge -> done.
    assert r.update([_click(r._btn.rect)]) == 'done'


def test_reveal_supports_direct_kingdom_button_label():
    from game.components.tutorial_window import StarterSuitRevealDialogue
    _display()
    r = StarterSuitRevealDialogue(
        pygame.display.get_surface(), 'Hearts', done_label='Go to Kingdom')
    r._phase = 'done'
    r._reveal_notified = True
    r.draw()
    assert r._btn.text == 'Go to Kingdom'


def test_reveal_waits_for_server_grant_and_exposes_retry():
    from game.components import tutorial_window as tw
    from game.components.tutorial_window import StarterSuitRevealDialogue
    _display()
    r = StarterSuitRevealDialogue(
        pygame.display.get_surface(), 'Hearts',
        done_label='Go to Kingdom', wait_for_grant=True)
    r._created_at = pygame.time.get_ticks() - 1000
    r._phase_started = pygame.time.get_ticks() - (tw._REEL_SPIN_MS + 50)

    assert r.update([]) == 'revealed'
    r.draw()
    assert r._btn.disabled is True
    assert r._btn.text == '…'

    r.set_grant_result(False)
    r.update([])
    r.draw()
    assert r._btn.text == 'Retry'
    assert r.update([_click(r._btn.rect)]) == 'retry'

    r.set_grant_result(True)
    r.update([])
    r.draw()
    assert r._btn.text == 'Go to Kingdom'


def test_reveal_button_disabled_while_spinning():
    r = _reveal()
    r.update([])  # still spinning
    assert r._btn.disabled is True
    # A click while spinning is ignored.
    assert r.update([_click(r._btn.rect)]) is None


def test_reveal_has_no_pause_button():
    from game.components.tutorial_window import StarterSuitRevealDialogue
    _display()
    reveal = StarterSuitRevealDialogue(None, 'Hearts')
    assert not hasattr(reveal, '_btn_pause')


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

    own_frame = {'title': 'H', 'layout': 'image_top', 'image': img,
                 'image_frame': False}
    assert _kinds(win, own_frame) == ['headline', 'image_plain']


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
        {'title': 'Cards Become Recipes', 'layout': 'image_bottom',
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
    r = StarterSuitRevealDialogue(win_surf, 'Hearts')
    r.draw()                       # spin
    r._phase = 'done'
    r.draw()                       # done


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
    assert isinstance(td.card_rarity_code_diagram(), pygame.Surface)
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
    # Recipe examples show one figure, one spell, and one tactic.
    examples = td.card_recipe_examples()
    assert isinstance(examples, pygame.Surface)


def test_kingdom_and_offdef_diagrams_build():
    _display()
    from game.components import tutorial_diagrams as td
    td.clear_cache()
    for fn in (td.offensive_vs_defensive_diagram, td.map_legend_diagram,
               td.growth_loop_diagram, td.attack_defend_diagram,
               td.kingdom_journey_diagram, td.battle_flow_diagram,
               td.kingdom_map_diagram, td.suit_roulette_diagram,
               td.conquer_start_image, td.duel_start_image,
               td.collection_growth_start_image,
               td.build_attack_start_image,
               td.run_kingdom_start_image,
               td.defend_land_start_image,
               td.duel_shared_card_pool_image, td.duel_loop_diagram,
               td.duel_build_battle_diagram, td.shared_card_pool_diagram,
               td.battle_matchup_diagram, td.starter_tactics_diagram,
               td.tactics_actions_diagram, td.loot_risk_diagram,
               td.two_pack_jobs_diagram, td.key_number_cards_diagram,
               td.collection_capacity_diagram):
        surf = fn()
        assert isinstance(surf, pygame.Surface)
        assert fn() is surf  # cached


def test_battle_flow_stacks_two_objects_in_each_phase(monkeypatch):
    _display()
    from game.components import tutorial_diagrams as td

    calls = []
    real_matchup_card = td._vertical_matchup_card

    def record_matchup(title, own_art, rival_art, card_w, card_h, accent):
        calls.append((title, own_art, rival_art))
        return real_matchup_card(
            title, own_art, rival_art, card_w, card_h, accent)

    monkeypatch.setattr(td, '_vertical_matchup_card', record_matchup)
    td.clear_cache()
    diagram = td.battle_flow_diagram(220)

    assert isinstance(diagram, pygame.Surface)
    assert [title for title, _, _ in calls] == [
        'Prelude Spell',
        'Battle Figure',
        'Tactic I',
        'Tactic II',
        'Tactic III',
    ]
    assert all(
        isinstance(own, pygame.Surface) and isinstance(rival, pygame.Surface)
        for _, own, rival in calls
    )

    own = pygame.Surface((28, 36), pygame.SRCALPHA)
    own.fill((250, 10, 20, 255))
    rival = pygame.Surface((28, 36), pygame.SRCALPHA)
    rival.fill((10, 30, 250, 255))
    card = real_matchup_card('Tactic I', own, rival, 116, 220)

    def color_bounds(color):
        points = [
            (x, y)
            for y in range(card.get_height())
            for x in range(card.get_width())
            if card.get_at((x, y))[:3] == color
        ]
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        return min(xs), min(ys), max(xs), max(ys)

    own_bounds = color_bounds((250, 10, 20))
    rival_bounds = color_bounds((10, 30, 250))
    own_center_x = (own_bounds[0] + own_bounds[2]) / 2
    rival_center_x = (rival_bounds[0] + rival_bounds[2]) / 2
    assert abs(own_center_x - rival_center_x) <= 1
    assert own_bounds[3] < rival_bounds[1]


def test_run_kingdom_uses_original_start_art(monkeypatch):
    from game.components import tutorial_diagrams as td

    requested = []
    marker = object()
    monkeypatch.setattr(
        td,
        '_tutorial_banner',
        lambda name: requested.append(name) or marker,
    )

    assert td.run_kingdom_start_image() is marker
    assert requested == ['run_kingdom_start.png']


def test_follow_up_lessons_begin_with_framed_generated_art():
    _display()
    from game import tutorial_content

    for pages_fn in (
            tutorial_content.collection_growth_pages,
            tutorial_content.build_attack_intro_pages,
            tutorial_content.kingdom_management_pages,
            tutorial_content.defend_land_intro_pages):
        first = pages_fn()[0]
        image = first['image']()
        assert first['layout'] == 'image_top'
        assert first['image_frame'] is False
        assert isinstance(image, pygame.Surface)
        assert image.get_width() >= 600
        assert pages_fn()[-1]['button_label'] == 'Begin Lesson'


def test_collection_growth_explains_pack_pools_and_card_roles_then_recaps_capacity():
    _display()
    from game import tutorial_content
    from game.components import tutorial_diagrams as td

    pages = tutorial_content.collection_growth_pages()
    role_page = pages[1]
    pack_page = pages[2]
    rarity_page = pages[3]
    recap_page = tutorial_content.collection_growth_recap_pages()[0]

    assert role_page['title'] == 'Key cards and number cards'
    assert pack_page['title'] == 'Two packs, two jobs'
    assert rarity_page['title'] == 'Card borders show rarity'
    assert pack_page.get('button_label') is None
    assert rarity_page['button_label'] == 'Begin Lesson'

    pack_text = ' '.join(pack_page['lines'])
    assert '7–Ace' in pack_text
    assert '2–6' in pack_text
    assert isinstance(pack_page['image'](), pygame.Surface)
    assert pack_page['image']() is td.two_pack_jobs_diagram()

    role_text = ' '.join(role_page['lines'])
    assert 'Key cards have jewels' in role_text
    assert 'fixed core of every figure' in role_text
    assert 'Number cards are the variable part' in role_text
    assert 'resource cost and production' in role_text
    assert role_page['image']() is td.key_number_cards_diagram()

    rarity_text = ' '.join(rarity_page['lines'])
    assert 'border color' in rarity_text
    assert 'chances of drawing a card from a booster pack' in rarity_text
    assert 'value of the card in trade' in rarity_text
    assert rarity_page['image']() is td.card_rarity_code_diagram()

    recap_text = ' '.join(recap_page['lines'])
    assert recap_page['title'] == 'Your cards build the kingdom'
    assert 'defence figures' in recap_text
    assert 'lock your active cards' in recap_text
    assert 'More copies' in recap_text
    assert 'expand your kingdom' in recap_text
    assert recap_page['image_max_height_ratio'] == 0.30
    assert recap_page['button_label'] == 'Complete Lesson'
    assert 'image_caption' not in recap_page
    assert recap_page['image']() is td.collection_capacity_diagram()


def test_two_pack_jobs_uses_named_main_and_side_examples(monkeypatch):
    _display()
    from game.components import tutorial_diagrams as td

    figure_names = []
    spell_names = []
    labels_by_panel = {}
    marker = pygame.Surface((12, 12), pygame.SRCALPHA)

    monkeypatch.setattr(
        td,
        'field_figure_icon',
        lambda family, *args, **kwargs: (
            figure_names.append(family) or marker),
    )
    monkeypatch.setattr(
        td,
        '_spell_chip',
        lambda name, box: spell_names.append(name) or marker,
    )

    def fake_panel(**kwargs):
        labels_by_panel[kwargs['title']] = [
            label for _, label in kwargs['outcomes'](20)]
        return pygame.Surface((80, 60), pygame.SRCALPHA)

    monkeypatch.setattr(td, '_pack_job_panel', fake_panel)
    td.clear_cache()
    td.two_pack_jobs_diagram(target_h=60)

    assert labels_by_panel['MAIN CARDS  ·  7–ACE'] == [
        'King', 'Farm', 'Blitzkrieg']
    assert labels_by_panel['SIDE CARDS  ·  2–6'] == [
        'Archer', 'Wall', 'Poison']
    assert figure_names == [
        'Djungle King', 'Small Rice Farm', 'Himalya Archer', 'Wall']
    assert spell_names == ['Blitzkrieg', 'Poison']


def test_starter_roulette_keeps_four_suit_presentation_contract():
    from game.components.tutorial_window import _ALL_SUITS
    from game.tutorial_content import starter_present_pages

    assert _ALL_SUITS == ('Hearts', 'Diamonds', 'Clubs', 'Spades')
    page = starter_present_pages()[0]
    text = ' '.join([page.get('image_caption', ''), *(page.get('lines') or [])])
    assert 'four suits' in text
    assert 'Hearts' not in text and 'Diamonds' not in text
