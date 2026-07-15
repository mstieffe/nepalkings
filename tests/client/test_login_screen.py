# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for login screen auth response helpers."""

import pytest
import pygame


class _FakeResponse:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    def json(self):
        if self._error:
            raise self._error
        return self._payload


def test_response_error_message_uses_server_message():
    from game.screens.login_screen import _response_error_message

    resp = _FakeResponse({
        'success': False,
        'message': 'Password must be at least 6 characters',
    })

    assert _response_error_message(resp, 'Request failed (400). Please try again.') == (
        'Password must be at least 6 characters'
    )


def test_response_error_message_falls_back_without_message():
    from game.screens.login_screen import _response_error_message

    assert _response_error_message(_FakeResponse({}), 'fallback') == 'fallback'
    assert _response_error_message(_FakeResponse(error=ValueError()), 'fallback') == 'fallback'


@pytest.mark.parametrize(
    ('width', 'height', 'ui_scale', 'touch_target'),
    [
        (854, 480, 1.6, 58),
        (1024, 576, 1.5, 60),
        (1280, 720, 1.4, 75),
    ],
)
def test_mobile_login_metrics_fit_supported_canvas_tiers(
        width, height, ui_scale, touch_target):
    from game.screens.login_screen import _mobile_login_metrics

    metrics = _mobile_login_metrics(width, height, ui_scale, touch_target)

    assert int(0.45 * width) <= metrics['form_w'] <= int(0.57 * width)
    assert metrics['form_w'] + 2 * metrics['panel_pad_x'] < width
    assert metrics['field_h'] >= touch_target
    assert metrics['button_h'] >= touch_target
    assert metrics['field_gap'] >= int(0.034 * height)
    assert metrics['button_gap'] >= int(0.034 * height)


def test_mobile_legal_document_supports_swipe_scrolling():
    from game.screens.login_screen import LoginScreen

    screen = object.__new__(LoginScreen)
    screen._mobile_ui = True
    screen._legal_doc = {
        'title': 'Terms',
        'lines': [],
        'scroll': 0,
        'max_scroll': 240,
    }
    screen._legal_doc_drag = None
    screen._legal_doc_dragged = False
    screen._legal_doc_close_rect = pygame.Rect(700, 20, 30, 30)
    screen._legal_doc_panel_rect = lambda: pygame.Rect(20, 20, 800, 420)
    screen._legal_doc_body_rect = lambda: pygame.Rect(40, 70, 760, 330)

    screen._handle_legal_doc_events([
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(200, 250)),
        pygame.event.Event(pygame.MOUSEMOTION, pos=(200, 150)),
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(200, 150)),
    ])

    assert screen._legal_doc['scroll'] == 100
    assert screen._legal_doc_drag is None
