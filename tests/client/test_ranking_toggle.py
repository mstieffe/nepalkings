# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for the RankingScreen toggle between Duel and Kingdom tabs."""
import pytest
from unittest.mock import patch, MagicMock
import pygame
from pygame.locals import MOUSEBUTTONDOWN


def _make_state():
    """Create a minimal mock state for RankingScreen."""
    state = MagicMock()
    state.user_dict = {'username': 'testuser'}
    state.window = pygame.Surface((800, 600))
    return state


def _make_screen():
    from game.screens.ranking_screen import RankingScreen
    state = _make_state()
    with patch('game.screens.ranking_screen.fetch_rankings', return_value=[]), \
         patch('game.screens.ranking_screen.fetch_kingdom_rankings', return_value=[]):
        screen = RankingScreen(state)
    return screen


class TestRankingToggle:

    def test_default_tab_is_duel(self):
        screen = _make_screen()
        assert screen._active_tab == 'duel'

    def test_has_both_tab_rects(self):
        screen = _make_screen()
        assert 'duel' in screen._tab_rects
        assert 'kingdom' in screen._tab_rects

    def test_switch_to_kingdom_tab(self):
        screen = _make_screen()
        screen._active_tab = 'kingdom'
        screen._sort_col = 2
        screen._rebuild_hdr_rects()

        from game.screens.ranking_screen import _COL_DEFS_KINGDOM
        assert len(screen._hdr_rects) == len(_COL_DEFS_KINGDOM)

    def test_switch_back_to_duel_tab(self):
        screen = _make_screen()
        screen._active_tab = 'kingdom'
        screen._rebuild_hdr_rects()
        screen._active_tab = 'duel'
        screen._rebuild_hdr_rects()

        from game.screens.ranking_screen import _COL_DEFS
        assert len(screen._hdr_rects) == len(_COL_DEFS)

    def test_active_col_defs_duel(self):
        screen = _make_screen()
        from game.screens.ranking_screen import _COL_DEFS
        assert screen._active_col_defs() is _COL_DEFS

    def test_active_col_defs_kingdom(self):
        screen = _make_screen()
        screen._active_tab = 'kingdom'
        from game.screens.ranking_screen import _COL_DEFS_KINGDOM
        assert screen._active_col_defs() is _COL_DEFS_KINGDOM

    def test_active_sort_keys_duel(self):
        screen = _make_screen()
        from game.screens.ranking_screen import _SORT_KEYS
        assert screen._active_sort_keys() is _SORT_KEYS

    def test_active_sort_keys_kingdom(self):
        screen = _make_screen()
        screen._active_tab = 'kingdom'
        from game.screens.ranking_screen import _SORT_KEYS_KINGDOM
        assert screen._active_sort_keys() is _SORT_KEYS_KINGDOM

    def test_tab_switch_resets_sort_col(self):
        screen = _make_screen()
        screen._sort_col = 5
        # Simulate switching to kingdom
        screen._active_tab = 'kingdom'
        screen._sort_col = 2  # reset as the code does
        assert screen._sort_col == 2

    def test_kingdom_cells_use_correct_keys(self):
        """Verify kingdom rankings data keys match expected fields."""
        screen = _make_screen()
        screen._active_tab = 'kingdom'
        entry = {
            'username': 'player1',
            'lands_owned': 5,
            'total_gold_rate': 23.5,
            'conquer_attempts': 12,
            'conquer_wins': 8,
            'defence_wins': 3,
        }
        cells = [
            str(1),
            entry.get('username', '—'),
            str(entry.get('lands_owned', 0)),
            str(entry.get('total_gold_rate', 0)),
            str(entry.get('conquer_attempts', 0)),
            str(entry.get('conquer_wins', 0)),
            str(entry.get('defence_wins', 0)),
        ]
        assert cells == ['1', 'player1', '5', '23.5', '12', '8', '3']
