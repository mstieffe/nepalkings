# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for the RankingScreen toggle between Duel and Conquer tabs."""
from unittest.mock import patch, MagicMock
import pygame


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
        screen._sort_desc = False

        screen._switch_tab('kingdom')

        assert screen._active_tab == 'kingdom'
        assert screen._sort_col == 2
        assert screen._sort_desc is True

    def test_tab_switch_uses_cached_rows_without_empty_flash(self):
        screen = _make_screen()
        cached = [{'username': 'builder', 'lands_owned': 3}]
        screen._rankings_by_tab['kingdom'] = cached
        screen._loaded_tabs.add('kingdom')

        screen._switch_tab('kingdom')

        assert screen.rankings == cached
        assert screen._loading is False

    def test_ai_rows_are_filtered_from_current_and_legacy_payloads(self):
        screen = _make_screen()
        screen._apply_rankings([
            {'username': 'human', 'gold': 10, 'wins': 1, 'losses': 1},
            {'username': 'bot', 'gold': 999, 'wins': 8, 'losses': 0,
             'is_ai': True},
            {'username': '[AI] Strategos', 'gold': 999, 'wins': 8,
             'losses': 0},
            {'username': '{AI} Strategos', 'gold': 999, 'wins': 8,
             'losses': 0},
        ])

        assert [row['username'] for row in screen.rankings] == ['human']

    def test_sort_header_toggles_direction_without_refetching(self):
        screen = _make_screen()
        screen._apply_rankings([
            {'username': 'rich', 'gold': 20, 'wins': 0, 'losses': 0},
            {'username': 'poor', 'gold': 5, 'wins': 0, 'losses': 0},
        ])
        assert [row['username'] for row in screen.rankings] == ['rich', 'poor']

        with patch('game.screens.ranking_screen.fetch_rankings') as fetch:
            screen._select_sort_column(2)

        fetch.assert_not_called()
        assert screen._sort_desc is False
        assert [row['username'] for row in screen.rankings] == ['poor', 'rich']

    def test_conquer_tab_uses_player_facing_label(self):
        from game.screens.ranking_screen import _TAB_LABELS

        assert _TAB_LABELS['kingdom'] == 'Conquer'

    def test_long_cell_text_is_ellipsized(self):
        screen = _make_screen()

        fitted = screen._fit_text(screen._cell_font, 'A very long player name', 30)

        assert fitted.endswith('…')
        assert screen._cell_font.size(fitted)[0] <= 30

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
