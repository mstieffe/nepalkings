import pygame


def _small_sidebar():
    from game.screens.guide_book_screen import GuideBookScreen

    screen = object.__new__(GuideBookScreen)
    screen.window = pygame.Surface((360, 240))
    screen.sections = [
        {
            'title': f'Chapter {i}',
            'group': 'Basics' if i < 4 else 'Battles',
        }
        for i in range(12)
    ]
    screen.current_section = 0
    screen.sidebar_x = 10
    screen.sidebar_y = 10
    screen.sidebar_w = 150
    screen.sidebar_h = 100
    screen.menu_item_pad = 2
    screen.menu_scroll_offset = 0
    screen.menu_font = pygame.font.Font(None, 14)
    screen.menu_font_active = pygame.font.Font(None, 14)
    screen.small_body_font = pygame.font.Font(None, 12)
    screen._build_menu_rects()
    return screen


def test_short_rulebook_sidebar_scrolls_to_reveal_last_chapter():
    screen = _small_sidebar()

    assert screen._max_menu_scroll > 0
    assert screen.menu_rects[-1].bottom > screen.sidebar_y + screen.sidebar_h

    screen.current_section = len(screen.sections) - 1
    screen._build_menu_rects()

    last = screen._visible_menu_rect(screen.menu_rects[-1])
    assert screen.menu_scroll_offset > 0
    assert last.bottom <= screen.sidebar_y + screen.sidebar_h
    assert last.bottom > screen.sidebar_y


def test_rulebook_sidebar_wheel_does_not_scroll_article():
    screen = _small_sidebar()
    screen.scroll_offset = 37
    screen.scroll_text_list_shifter = None
    screen._close_rect = pygame.Rect(0, 0, 0, 0)
    screen._on_done = None
    screen.handle_rect = pygame.Rect(0, 0, 0, 0)
    screen.dragging = False
    screen._touch_scrolling = False
    screen._menu_touch_scrolling = False
    screen.content_x = 180
    screen.content_y = 10
    screen.content_w = 150
    screen.content_h = 100
    screen.scrollbar_rect = pygame.Rect(335, 10, 4, 100)

    event = pygame.event.Event(
        pygame.MOUSEWHEEL, y=-1, pos=(20, 40))
    screen.handle_events([event])

    assert screen.menu_scroll_offset > 0
    assert screen.scroll_offset == 37


def test_rulebook_sidebar_swipe_scrolls_without_selecting():
    screen = _small_sidebar()
    screen.scroll_text_list_shifter = None
    screen._close_rect = pygame.Rect(0, 0, 0, 0)
    screen._on_done = None
    screen.handle_rect = pygame.Rect(0, 0, 0, 0)
    screen.dragging = False
    screen._touch_scrolling = False
    screen._menu_touch_scrolling = False
    screen.content_x = 180
    screen.content_y = 10
    screen.content_w = 150
    screen.content_h = 100
    screen.scrollbar_rect = pygame.Rect(335, 10, 4, 100)

    events = [
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=(40, 80)),
        pygame.event.Event(
            pygame.MOUSEMOTION, pos=(40, 25)),
        pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1, pos=(40, 25)),
    ]
    screen.handle_events(events)

    assert screen.menu_scroll_offset > 0
    assert screen.current_section == 0


def test_rulebook_sidebar_drawing_is_clipped_to_its_box(monkeypatch):
    screen = _small_sidebar()
    screen.current_section = len(screen.sections) - 1
    screen.menu_scroll_offset = 0
    screen.window.fill((255, 0, 255))
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (-1, -1))

    screen._draw_sidebar()

    below_sidebar = (
        screen.sidebar_x + 10,
        screen.sidebar_y + screen.sidebar_h + 8,
    )
    assert screen.window.get_at(below_sidebar)[:3] == (255, 0, 255)
