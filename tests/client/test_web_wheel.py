"""Tests for the pygbag raw wheel-event bridge."""

import pygame


def test_pixel_wheel_samples_keep_small_deltas_precise():
    from utils import web_wheel

    events = web_wheel._events_from_samples([
        {'dy': -2, 'mode': 0, 'x': 120, 'y': 80},
    ])

    assert len(events) == 1
    event = events[0]
    assert event.type == pygame.MOUSEWHEEL
    assert event.y == 0
    assert event.precise_y > 0
    assert event.pos == (120, 80)


def test_merge_events_replaces_native_wheel_when_synthetic_exists(monkeypatch):
    from utils import web_wheel

    native_wheel = pygame.event.Event(pygame.MOUSEWHEEL, y=1)
    native_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5))
    synthetic = pygame.event.Event(
        pygame.MOUSEWHEEL,
        y=0,
        precise_y=0.08,
        pos=(120, 80),
    )
    monkeypatch.setattr(web_wheel, 'drain_events', lambda: [synthetic])

    merged = web_wheel.merge_events([native_wheel, native_click])

    assert merged == [native_click, synthetic]


def test_merge_events_keeps_native_events_without_synthetic(monkeypatch):
    from utils import web_wheel

    native_wheel = pygame.event.Event(pygame.MOUSEWHEEL, y=1)
    monkeypatch.setattr(web_wheel, 'drain_events', lambda: [])

    assert web_wheel.merge_events([native_wheel]) == [native_wheel]