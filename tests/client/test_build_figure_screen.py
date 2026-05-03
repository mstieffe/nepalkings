# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for kingdom-mode figure building display filters."""

from types import SimpleNamespace


def _make_instant_charge_figure():
    family = SimpleNamespace(
        name='Gorkha Warriors',
        description=(
            'The Gorkha Warriors is an offensive military figure that charges instantly into battle '
            'when placed on the field. Requires food equal to its number-card value.'
        ),
        field='military',
    )
    return SimpleNamespace(
        name='Gorkha Warriors',
        description=family.description,
        family=family,
        instant_charge=True,
        checkmate=False,
    )


class TestBuildFigureScreenModeFiltering:
    def test_conquer_builder_hides_instant_advance_on_display_figure(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        screen = BuildFigureScreen.__new__(BuildFigureScreen)
        screen.mode = 'conquer'
        figure = _make_instant_charge_figure()

        display = BuildFigureScreen._display_figure_for_mode(screen, figure)

        assert display is not figure
        assert display.instant_charge is False
        assert 'charges instantly into battle' not in display.description.lower()
        assert 'charges instantly into battle' not in display.family.description.lower()

    def test_duel_builder_keeps_instant_advance_display_unchanged(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        screen = BuildFigureScreen.__new__(BuildFigureScreen)
        screen.mode = 'duel'
        figure = _make_instant_charge_figure()

        display = BuildFigureScreen._display_figure_for_mode(screen, figure)

        assert display is figure
        assert display.instant_charge is True

    def test_kingdom_builder_disables_instant_charge_advance_action(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        screen = BuildFigureScreen.__new__(BuildFigureScreen)
        screen.mode = 'defence'
        screen.game = SimpleNamespace(
            ceasefire_active=False,
            advancing_figure_id=None,
            advancing_player_id=None,
            player_id=1,
            battle_modifier=[],
            figures=[],
        )

        can_charge, is_counter, reason = BuildFigureScreen._can_instant_charge_advance(
            screen,
            _make_instant_charge_figure(),
        )

        assert can_charge is False
        assert is_counter is False
        assert reason == 'disabled_in_kingdom_config'
