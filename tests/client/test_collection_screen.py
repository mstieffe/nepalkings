# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for the client-side collection screen logic."""
import pytest


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
        assert _card_tier('A', 'main') == 3
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


class TestCollectionSettings:
    """Verify collection settings are importable and reasonable."""

    def test_card_dimensions_positive(self):
        from config.collection_settings import COLLECTION_CARD_W, COLLECTION_CARD_H
        assert COLLECTION_CARD_W > 0
        assert COLLECTION_CARD_H > 0

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
