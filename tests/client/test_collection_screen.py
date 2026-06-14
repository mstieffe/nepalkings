# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for the client-side collection screen logic."""
import pytest
from types import SimpleNamespace


class TestSellPriceCalculation:
    """Verify the client-side sell price mirror matches expected values."""

    def test_number_card_sell_price(self):
        from game.screens.collection_screen import _sell_price
        assert _sell_price('7', 1) == 7

    def test_number_card_sell_quantity(self):
        from game.screens.collection_screen import _sell_price
        assert _sell_price('10', 3) == 30

    def test_key_card_jack(self):
        from game.screens.collection_screen import _sell_price
        # J value = 1, multiplier = 10 → 10
        assert _sell_price('J', 1) == 10

    def test_key_card_queen(self):
        from game.screens.collection_screen import _sell_price
        # Q value = 2, multiplier = 10 → 20
        assert _sell_price('Q', 1) == 20

    def test_key_card_king(self):
        from game.screens.collection_screen import _sell_price
        # K value = 4, multiplier = 10 → 40
        assert _sell_price('K', 1) == 40

    def test_key_card_ace(self):
        from game.screens.collection_screen import _sell_price
        # A value = 3, multiplier = 10 → 30
        assert _sell_price('A', 1) == 30

    def test_key_card_multiple(self):
        from game.screens.collection_screen import _sell_price
        assert _sell_price('K', 5) == 200

    def test_side_card_sell_price(self):
        from game.screens.collection_screen import _sell_price
        assert _sell_price('2', 1) == 2

    def test_side_card_6(self):
        from game.screens.collection_screen import _sell_price
        assert _sell_price('6', 2) == 12


class TestCollectionDataParsing:
    """Test the data transformation logic without requiring a full screen init."""

    def test_cards_dict_building(self):
        """_apply_collection_data should build the (suit,rank)->qty map."""
        data = {
            'cards': [
                {'suit': 'Hearts', 'rank': 'K', 'quantity': 3},
                {'suit': 'Clubs', 'rank': '7', 'quantity': 1},
            ],
            'gold': 500,
            'booster_packs': 2,
            'booster_packs_side': 1,
        }
        # Build the map manually (mirrors _apply_collection_data logic)
        cards = {}
        for c in data['cards']:
            cards[(c['suit'], c['rank'])] = c.get('quantity', 0)
        assert cards[('Hearts', 'K')] == 3
        assert cards[('Clubs', '7')] == 1
        assert ('Spades', 'A') not in cards

    def test_missing_card_defaults_to_zero(self):
        """Unowned cards should default to 0 in the dict."""
        cards = {}
        assert cards.get(('Hearts', 'A'), 0) == 0


class TestCardOrdering:
    """Test the rank ordering for main and side card tabs."""

    def test_main_ranks_order(self):
        """Main ranks should be displayed A, K, Q, J, 10, 9, 8, 7."""
        from config.card_settings import RANKS_MAIN_CARDS
        display_order = list(reversed(RANKS_MAIN_CARDS))
        assert display_order == ['A', 'K', 'Q', 'J', '10', '9', '8', '7']

    def test_side_ranks_order(self):
        """Side ranks should be displayed 6, 5, 4, 3, 2."""
        from config.card_settings import RANKS_SIDE_CARDS
        display_order = list(reversed(RANKS_SIDE_CARDS))
        assert display_order == ['6', '5', '4', '3', '2']

    def test_four_suits(self):
        from config.card_settings import SUITS
        assert len(SUITS) == 4
        assert 'Hearts' in SUITS
        assert 'Spades' in SUITS


class TestCollectionTierMapping:
    """Verify client rank-to-tier helpers mirror booster tables."""

    def test_main_card_tiers(self):
        from game.screens.collection_screen import _card_tier, _tier_label
        assert _card_tier('7', 'main') == 1
        assert _card_tier('J', 'main') == 2
        assert _card_tier('A', 'main') == 2
        assert _card_tier('Q', 'main') == 3
        assert _tier_label('K', 'main') == 'Rare'

    def test_side_card_tiers(self):
        from game.screens.collection_screen import _card_tier, _tier_label
        assert _card_tier('2', 'side') == 1
        assert _card_tier('4', 'side') == 2
        assert _card_tier('6', 'side') == 3
        assert _tier_label('6', 'side') == 'Rare'

    def test_pack_type_inference(self):
        from game.screens.collection_screen import _card_pack_type
        assert _card_pack_type('A') == 'main'
        assert _card_pack_type('6') == 'side'


class TestCollectionStats:
    """Verify collection summary helper values used by the stats strip."""

    def test_collection_stats_counts_owned_unique_missing_locked(self):
        from game.screens.collection_screen import _collection_stats
        cards = {
            ('Hearts', 'A'): 2,
            ('Spades', '7'): 1,
            ('Clubs', '2'): 3,
        }
        locked = {
            ('Hearts', 'A'): 1,
            ('Clubs', '2'): 2,
        }
        stats = _collection_stats(cards, locked)
        assert stats['owned_total'] == 6
        assert stats['unique_owned'] == 3
        assert stats['unique_total'] == 52
        assert stats['missing_total'] == 49
        assert stats['locked_total'] == 3
        assert stats['available_total'] == 3


class TestCollectionSettings:
    """Verify collection settings are importable and reasonable."""

    def test_card_dimensions_positive(self):
        from config.collection_settings import COLLECTION_CARD_W, COLLECTION_CARD_H
        assert COLLECTION_CARD_W > 0
        assert COLLECTION_CARD_H > 0

    def test_desktop_card_dimensions_keep_legacy_ratios(self):
        from config.collection_settings import COLLECTION_CARD_H, COLLECTION_CARD_GAP_Y
        from config.screen_settings import SCREEN_HEIGHT, _IS_MOBILE
        if _IS_MOBILE:
            pytest.skip('desktop ratio guard only applies outside mobile web')
        assert COLLECTION_CARD_H == int(0.120 * SCREEN_HEIGHT)
        assert COLLECTION_CARD_GAP_Y == int(0.010 * SCREEN_HEIGHT)

    def test_panel_bounds(self):
        from config.collection_settings import (
            COLLECTION_PANEL_X, COLLECTION_PANEL_Y,
            COLLECTION_PANEL_W, COLLECTION_PANEL_BOTTOM)
        assert COLLECTION_PANEL_X >= 0
        assert COLLECTION_PANEL_Y >= 0
        assert COLLECTION_PANEL_W > 0
        assert COLLECTION_PANEL_BOTTOM > COLLECTION_PANEL_Y

    def test_toggle_dimensions(self):
        from config.collection_settings import COLLECTION_TOGGLE_W, COLLECTION_TOGGLE_H
        assert COLLECTION_TOGGLE_W > 0
        assert COLLECTION_TOGGLE_H > 0

    def test_booster_prices(self):
        from config.collection_settings import BOOSTER_PACK_PRICE, BOOSTER_PACK_SIDE_PRICE
        assert BOOSTER_PACK_PRICE == 100
        assert BOOSTER_PACK_SIDE_PRICE == 100

    def test_grey_alpha_in_range(self):
        from config.collection_settings import COLLECTION_GREY_ALPHA
        assert 0 <= COLLECTION_GREY_ALPHA <= 255

    def test_badge_colors(self):
        from config.collection_settings import COLLECTION_BADGE_CLR, COLLECTION_BADGE_BG_CLR
        assert len(COLLECTION_BADGE_CLR) == 3
        assert len(COLLECTION_BADGE_BG_CLR) == 4  # RGBA

    def test_common_tier_color_is_neutral_gray(self):
        from config.collection_settings import COLLECTION_TIER_COLORS
        common = COLLECTION_TIER_COLORS[1]
        assert common[0] == common[1] == common[2]

    def test_pack_preview_metadata_has_no_odds_or_contents(self):
        from config.collection_settings import COLLECTION_PACK_PREVIEWS
        assert set(COLLECTION_PACK_PREVIEWS['main']) == {'title'}
        assert set(COLLECTION_PACK_PREVIEWS['side']) == {'title'}

    def test_mobile_collection_layout_clears_chrome_and_fits_grid(self):
        """iPhone SE mobile canvas keeps the collection panel out of HUD chrome."""
        import os
        from pathlib import Path
        import subprocess
        import sys

        root = Path(__file__).resolve().parents[2]
        app_dir = root / 'nepal_kings'
        env = os.environ.copy()
        env.update({
            'SDL_VIDEODRIVER': 'dummy',
            'SDL_AUDIODRIVER': 'dummy',
            'NK_SCREEN_WIDTH': '854',
            'NK_SCREEN_HEIGHT': '480',
            'NK_UI_SCALE': '1.6',
            'NK_IS_MOBILE': '1',
            'PYTHONPATH': str(app_dir),
        })
        code = r'''
import pygame
pygame.init()
pygame.display.set_mode((1, 1))
from config import settings
from game.screens import collection_screen

hud_bottom = (
    settings.GAME_MENU_GOLD_MARGIN_Y
    + 2 * settings.GAME_MENU_GOLD_BOX_PAD_Y
    + max(settings.GAME_MENU_GOLD_ICON_SZ, settings.GAME_MENU_GOLD_FONT_SIZE)
)
rail_left = (
    settings.SCREEN_WIDTH
    - settings.GAME_MENU_ICON_RIGHT_MARGIN
    - settings.GAME_MENU_ICON_STONE_SZ
)
assert collection_screen._BOX_Y >= hud_bottom + 6, (
    collection_screen._BOX_Y, hud_bottom)
assert collection_screen._BOX_X + collection_screen._BOX_W <= rail_left - 8, (
    collection_screen._BOX_X + collection_screen._BOX_W, rail_left)

title_h = settings.get_font(
    settings.COLLECTION_TITLE_FONT_SIZE, bold=True).render(
        'Collection', True, settings.COLLECTION_TITLE_CLR).get_height()
pack_y = (
    collection_screen._BOX_BOTTOM
    - collection_screen._BOX_PAD
    - settings.COLLECTION_PACK_PANEL_H
)
stats_top = (
    collection_screen._BOX_Y
    + collection_screen._BOX_PAD
    + title_h
    + int(0.012 * settings.SCREEN_HEIGHT)
)
panel_top = (
    stats_top
    + settings.COLLECTION_STATS_STRIP_H
    + int(0.012 * settings.SCREEN_HEIGHT)
)
panel_bottom = pack_y - int(0.014 * settings.SCREEN_HEIGHT)
panel_h = panel_bottom - panel_top
grid_h = (
    settings.COLLECTION_PANEL_PAD_Y
    + int(0.035 * settings.SCREEN_HEIGHT)
    + 4 * settings.COLLECTION_CARD_H
    + 3 * settings.COLLECTION_CARD_GAP_Y
    + 2
)
assert grid_h <= panel_h, (grid_h, panel_h)

pack_margin_x = int(0.020 * settings.SCREEN_WIDTH)
pack_gap = settings.COLLECTION_PACK_PANEL_GAP
pack_w = (
    collection_screen._BOX_W
    - pack_margin_x * 2
    - pack_gap * 2
) // 3
pack_x = collection_screen._BOX_X + pack_margin_x
pack_rect = pygame.Rect(
    pack_x, pack_y, pack_w, settings.COLLECTION_PACK_PANEL_H)
icon_sz = min(9999, int(pack_rect.h * 0.32))
title_x = (
    pack_rect.x
    + settings.COLLECTION_PACK_PANEL_PAD_X
    + icon_sz
    + int(0.008 * settings.SCREEN_WIDTH)
)
title_y = (
    pack_rect.y
    + settings.COLLECTION_PACK_PANEL_PAD_Y
    - int(0.001 * settings.SCREEN_HEIGHT)
)
title_font = settings.get_font(settings.COLLECTION_PACK_PANEL_TITLE_FONT_SIZE, bold=True)
detail_font = settings.get_font(settings.COLLECTION_PACK_PANEL_DETAIL_FONT_SIZE)
title_surf = title_font.render('Main Pack', True, settings.COLLECTION_PACK_PANEL_TITLE_CLR)
owned_surf = detail_font.render('Owned: 999', True, settings.COLLECTION_PACK_PANEL_TEXT_CLR)
gap = max(4, int(0.006 * settings.SCREEN_WIDTH))
max_row_w = pack_rect.right - settings.COLLECTION_PACK_PANEL_PAD_X - title_x
assert title_surf.get_width() + gap + owned_surf.get_width() <= max_row_w
row_bottom = title_y + max(title_surf.get_height(), owned_surf.get_height())
button_top = (
    pack_rect.bottom
    - settings.COLLECTION_PACK_PANEL_PAD_Y
    - settings.COLLECTION_PACK_PANEL_BTN_H
)
assert row_bottom + 2 <= button_top, (row_bottom, button_top)
'''
        result = subprocess.run(
            [sys.executable, '-c', code],
            cwd=app_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestBoosterRevealLayout:
    """Guard against visual regressions in the booster reveal overlay."""

    def test_reveal_uses_same_simple_back_for_all_cards(self):
        import pygame
        from config import settings
        from game.components.booster_reveal import BoosterRevealOverlay

        window = pygame.display.get_surface() or pygame.display.set_mode(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay = BoosterRevealOverlay(window, [
            {'suit': 'Hearts', 'rank': '7', 'value': 7, 'tier': 1},
            {'suit': 'Clubs', 'rank': 'J', 'value': 1, 'tier': 2},
            {'suit': 'Spades', 'rank': 'A', 'value': 3, 'tier': 3},
        ])

        encoded_backs = [pygame.image.tobytes(img, 'RGBA') for img in overlay._back_imgs]
        assert len(set(encoded_backs)) == 1

    def test_reveal_close_button_does_not_overlap_card_labels(self):
        import pygame
        from config import settings
        from game.components.booster_reveal import BoosterRevealOverlay

        window = pygame.display.get_surface() or pygame.display.set_mode(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay = BoosterRevealOverlay(window, [
            {'suit': 'Hearts', 'rank': '7', 'value': 7, 'tier': 1},
            {'suit': 'Clubs', 'rank': 'J', 'value': 1, 'tier': 2},
            {'suit': 'Spades', 'rank': 'A', 'value': 3, 'tier': 3},
        ])

        label_band = pygame.Rect(
            overlay._slots[0].x,
            overlay._slots[0].bottom,
            overlay._slots[0].w,
            int(0.055 * settings.SCREEN_HEIGHT),
        )
        assert overlay._close_rect.top > label_band.bottom


class TestCollectionService:
    """Verify collection_service module structure."""

    def test_module_importable(self):
        from utils import collection_service
        assert hasattr(collection_service, 'fetch_collection_cards')
        assert hasattr(collection_service, 'sell_card')
        assert hasattr(collection_service, 'buy_booster')
        assert hasattr(collection_service, 'buy_booster_side')
        assert hasattr(collection_service, 'open_booster')
        assert hasattr(collection_service, 'open_booster_side')


class TestCollectionCoach:
    """Verify post-duel collection tour step selection."""

    def _screen(self, completed=None, seen=None):
        import pygame
        from game.screens.collection_screen import CollectionScreen

        screen = object.__new__(CollectionScreen)
        screen.state = SimpleNamespace(user_dict={'onboarding': {
            'completed_steps': list(completed or []),
            'menu_hints_seen': list(seen or []),
        }})
        screen._onboarding_guide_open = False
        screen._welcome_present_dialogue = None
        screen.dialogue_box = None
        screen._booster_poller = None
        screen._reveal_overlay = None
        screen._sell_dialogue = None
        screen._trade_dialogue = None
        screen._profile_dialogue = None
        screen._panel_rect = pygame.Rect(20, 120, 280, 160)
        screen._btn_open_main_rect = pygame.Rect(10, 20, 80, 32)
        screen._btn_open_side_rect = pygame.Rect(10, 70, 80, 32)
        screen._icon_home = SimpleNamespace(rect=pygame.Rect(200, 20, 40, 40))
        return screen

    def test_coach_requires_main_then_side_then_home(self):
        screen = self._screen(completed=['finish_first_duel'])
        step = screen._current_collection_coach_step()
        assert step['id'] == 'collection_starter_cards'
        assert step['action'] == 'next'
        assert step['button_label'] == 'Got it'

        screen.state.user_dict['onboarding']['menu_hints_seen'].append('collection_starter_cards')
        assert screen._current_collection_coach_step()['id'] == 'collection_open_main_booster'

        screen.state.user_dict['onboarding']['completed_steps'].append('open_first_main_booster')
        assert screen._current_collection_coach_step()['id'] == 'collection_open_side_booster'

        screen.state.user_dict['onboarding']['completed_steps'].append('open_first_side_booster')
        assert screen._current_collection_coach_step()['id'] == 'collection_return_home'

    def test_open_booster_result_marks_local_onboarding_step(self, monkeypatch):
        from game.screens.collection_screen import CollectionScreen
        from game.components import booster_reveal

        screen = object.__new__(CollectionScreen)
        screen.window = None
        screen.state = SimpleNamespace(user_dict={'onboarding': {'completed_steps': []}})
        screen._boosters = 1
        screen._boosters_side = 1
        screen._cards = {}
        monkeypatch.setattr(
            booster_reveal,
            'BoosterRevealOverlay',
            lambda window, cards, pack_type='main': SimpleNamespace(cards=cards, pack_type=pack_type),
        )

        screen._apply_open_booster_result('main', {
            'booster_packs': 0,
            'cards': [{'suit': 'Hearts', 'rank': '7'}],
        })

        assert 'open_first_main_booster' in screen.state.user_dict['onboarding']['completed_steps']
        assert screen.state.user_dict['booster_packs'] == 0
        assert screen._cards[('Hearts', '7')] == 1


class TestConvertRatio:
    """Client-side mirror of server convert ratios (suit colour rules)."""

    def _settings(self):
        from config import settings
        return settings

    def test_same_colour_red_red_is_2(self):
        s = self._settings()
        assert s.COLLECTION_CONVERT_RATIO_SAME_COLOR == 2
        assert 'Hearts' in s.COLLECTION_RED_SUITS
        assert 'Diamonds' in s.COLLECTION_RED_SUITS

    def test_same_colour_black_black_is_2(self):
        s = self._settings()
        assert 'Clubs' in s.COLLECTION_BLACK_SUITS
        assert 'Spades' in s.COLLECTION_BLACK_SUITS

    def test_different_colour_is_4(self):
        s = self._settings()
        assert s.COLLECTION_CONVERT_RATIO_DIFF_COLOR == 4

    def test_red_and_black_disjoint(self):
        s = self._settings()
        assert not (set(s.COLLECTION_RED_SUITS) & set(s.COLLECTION_BLACK_SUITS))


class TestServerConvertRatioHelper:
    """Verify the server's _convert_ratio function matches the spec."""

    def test_same_colour_returns_2(self):
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'server'))
        from routes.collection import _convert_ratio  # noqa: E402
        assert _convert_ratio('Hearts', 'Diamonds') == 2
        assert _convert_ratio('Diamonds', 'Hearts') == 2
        assert _convert_ratio('Clubs', 'Spades') == 2
        assert _convert_ratio('Spades', 'Clubs') == 2

    def test_different_colour_returns_4(self):
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'server'))
        from routes.collection import _convert_ratio  # noqa: E402
        assert _convert_ratio('Hearts', 'Spades') == 4
        assert _convert_ratio('Diamonds', 'Clubs') == 4
        assert _convert_ratio('Clubs', 'Hearts') == 4
        assert _convert_ratio('Spades', 'Diamonds') == 4

    def test_same_suit_returns_none(self):
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'server'))
        from routes.collection import _convert_ratio  # noqa: E402
        assert _convert_ratio('Hearts', 'Hearts') is None

    def test_invalid_suit_returns_none(self):
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'server'))
        from routes.collection import _convert_ratio  # noqa: E402
        assert _convert_ratio('Hearts', 'Bogus') is None
        assert _convert_ratio('Bogus', 'Hearts') is None
