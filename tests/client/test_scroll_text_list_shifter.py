# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for scroll list option indicators."""

import pygame


def _make_shifter(monkeypatch, option_count):
    from game.components.scroll_text_list_shifter import ScrollTextListShifter

    monkeypatch.setattr(ScrollTextListShifter, 'initialize_card_imgs', lambda self: {})
    monkeypatch.setattr(ScrollTextListShifter, '_load_resource_icons', lambda self: {})
    monkeypatch.setattr(ScrollTextListShifter, '_load_check_icons', lambda self: {})
    monkeypatch.setattr(ScrollTextListShifter, '_load_skill_icons', lambda self: {})

    pygame.display.set_mode((1, 1))
    window = pygame.Surface((240, 180), pygame.SRCALPHA)
    items = [
        {'title': f'Option {idx + 1}', 'content': object()}
        for idx in range(option_count)
    ]
    shifter = ScrollTextListShifter(
        window,
        items,
        12,
        12,
        scroll_rect=pygame.Rect(0, 0, 240, 180),
    )
    shifter.draw_text_in_scroll = lambda _text, _x, y: y + 10
    return shifter


class _CounterFont:
    def __init__(self):
        self.rendered = []

    def render(self, text, _antialias, _color):
        self.rendered.append(text)
        return pygame.Surface((44, 14), pygame.SRCALPHA)


def test_scroll_shifter_uses_dots_through_five_options(monkeypatch):
    shifter = _make_shifter(monkeypatch, 5)
    counter_font = _CounterFont()
    shifter.counter_font = counter_font
    circle_calls = []
    original_circle = pygame.draw.circle

    def spy_circle(*args, **kwargs):
        circle_calls.append(args)
        return original_circle(*args, **kwargs)

    monkeypatch.setattr(pygame.draw, 'circle', spy_circle)

    shifter.draw()

    assert len(circle_calls) == 5
    assert counter_font.rendered == []


def test_scroll_shifter_uses_numeric_counter_after_five_options(monkeypatch):
    shifter = _make_shifter(monkeypatch, 6)
    counter_font = _CounterFont()
    shifter.counter_font = counter_font
    circle_calls = []

    monkeypatch.setattr(
        pygame.draw,
        'circle',
        lambda *args, **kwargs: circle_calls.append(args),
    )

    shifter.draw()

    assert circle_calls == []
    assert counter_font.rendered == ['1 / 6']
