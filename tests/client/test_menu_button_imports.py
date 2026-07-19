# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Compatibility coverage for the menu-button module extraction."""


def test_legacy_menu_button_imports_reexport_canonical_classes():
    from game.components.buttons.menu_button import (
        Button as CanonicalButton,
        ControlButton as CanonicalControlButton,
    )
    from utils.utils import (
        Button as LegacyButton,
        ControlButton as LegacyControlButton,
    )

    assert LegacyButton is CanonicalButton
    assert LegacyControlButton is CanonicalControlButton
    assert issubclass(CanonicalControlButton, CanonicalButton)
    assert CanonicalButton.__module__ == 'utils.utils'
    assert CanonicalControlButton.__module__ == 'utils.utils'
