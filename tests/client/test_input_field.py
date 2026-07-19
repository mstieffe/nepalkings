# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for the shared text input field."""

import pickle
from unittest.mock import Mock

import pygame


def test_legacy_input_field_import_reexports_canonical_class():
    from game.components.inputs.input_field import InputField as CanonicalInputField
    from utils.utils import InputField as LegacyInputField

    assert LegacyInputField is CanonicalInputField
    assert CanonicalInputField.__module__ == "utils.utils"
    assert pickle.loads(pickle.dumps(CanonicalInputField)) is CanonicalInputField


def test_input_field_preserves_initial_cursor_and_edits_at_cursor():
    from utils.utils import InputField

    field = InputField(
        pygame.Surface((320, 160)),
        content="abcd",
        active=True,
        max_length=5,
    )

    assert field.cursor_pos == 0

    field.insert("X")
    assert field.content == "Xabcd"
    assert field.cursor_pos == 1

    field.backspace()
    assert field.content == "abcd"
    assert field.cursor_pos == 0

    field.empty()
    assert field.content == ""
    assert field.cursor_pos == 0


def test_input_field_handles_keyboard_and_text_events():
    from utils.utils import InputField

    field = InputField(
        pygame.Surface((320, 160)),
        content="ab",
        active=True,
        max_length=3,
    )
    field.cursor_pos = 2

    assert field.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)
    ) == "submit"
    assert field.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB)
    ) == "switch"

    assert field.handle_event(
        pygame.event.Event(pygame.TEXTINPUT, text="c")
    ) is None
    assert field.content == "abc"
    assert field.cursor_pos == 3

    field.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="d"))
    assert field.content == "abc"
    assert field.cursor_pos == 3

    field.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE)
    )
    assert field.content == "ab"
    assert field.cursor_pos == 2


def test_input_field_mouse_click_activates_or_deactivates():
    from utils.utils import InputField

    field = InputField(pygame.Surface((320, 160)))
    field.collide = Mock(side_effect=[True, False])
    field.activate = Mock()
    field.deactivate = Mock()
    click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)

    assert field.handle_event(click) is None
    field.activate.assert_called_once_with()
    field.deactivate.assert_not_called()

    assert field.handle_event(click) is None
    field.deactivate.assert_called_once_with()


def test_input_field_touch_hit_area_expands_on_both_axes(monkeypatch):
    from config import settings
    from utils.utils import InputField

    field = InputField(
        pygame.Surface((320, 160)),
        x=100,
        y=100,
        width=20,
        height=20,
    )
    monkeypatch.setattr(settings, "TOUCH_HIT_PAD", 8)

    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (95, 110))
    assert field.collide() is True

    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (110, 95))
    assert field.collide() is True

    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (91, 110))
    assert field.collide() is False


def test_input_field_draw_masks_password_content():
    from utils.utils import InputField

    field = InputField(
        pygame.Surface((320, 160)),
        name="Password",
        content="secret",
        pwd=True,
    )
    field.font = Mock()
    field.font.render.return_value = pygame.Surface((80, 20))
    field.font_title = Mock()
    field.font_title.render.return_value = pygame.Surface((80, 20))

    field.draw()

    field.font.render.assert_called_once_with(
        "******",
        True,
        field.color_text,
    )
