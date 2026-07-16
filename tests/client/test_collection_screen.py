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
            ('Diamonds', 'MK'): 1,
        }
        locked = {
            ('Hearts', 'A'): 1,
            ('Clubs', '2'): 2,
        }
        stats = _collection_stats(cards, locked)
        assert stats['owned_total'] == 7
        assert stats['unique_owned'] == 4
        assert stats['unique_total'] == 56
        assert stats['missing_total'] == 52
        assert stats['locked_total'] == 3
        assert stats['available_total'] == 4


class TestBoosterImpactAnnotations:
    """Booster reveals should explain how copy stock actually changed."""

    def test_duplicate_draws_advance_owned_and_free_counts_in_order(self):
        from game.screens.collection_screen import _annotate_booster_impact

        drawn = [
            {'suit': 'Hearts', 'rank': 'A', 'tier': 2},
            {'suit': 'Hearts', 'rank': 'A', 'tier': 2},
            {'suit': 'Spades', 'rank': 'K', 'tier': 3},
        ]
        annotated = _annotate_booster_impact(
            drawn,
            {('Hearts', 'A'): 2},
            {('Hearts', 'A'): 1},
        )

        assert annotated[0]['_impact_new_type'] is False
        assert annotated[0]['_impact_owned_before'] == 2
        assert annotated[0]['_impact_owned_after'] == 3
        assert annotated[0]['_impact_free_after'] == 2
        assert annotated[1]['_impact_owned_before'] == 3
        assert annotated[1]['_impact_owned_after'] == 4
        assert annotated[1]['_impact_free_after'] == 3
        assert annotated[2]['_impact_new_type'] is True
        assert annotated[2]['_impact_owned_after'] == 1
        assert '_impact_new_type' not in drawn[0]


class TestCollectionVisibilityFilter:
    """Verify the collection grid defaults to free cards only."""

    def test_free_card_count_ignores_locked_copies(self):
        from game.screens.collection_screen import _free_card_count

        cards = {('Hearts', 'A'): 3}
        locked = {('Hearts', 'A'): 2}

        assert _free_card_count(cards, locked, 'Hearts', 'A') == 1
        assert _free_card_count(cards, locked, 'Spades', 'A') == 0

    def test_default_view_keeps_slots_and_darkens_fully_locked_cards(self):
        from game.screens.collection_screen import (
            _collection_card_display_state,
            _collection_card_visible,
            _owned_card_fully_locked,
        )

        cards = {
            ('Hearts', 'A'): 3,
            ('Clubs', 'K'): 1,
        }
        locked = {
            ('Hearts', 'A'): 2,
            ('Clubs', 'K'): 1,
        }

        assert _collection_card_visible(cards, locked, 'Hearts', 'A') is True
        assert _collection_card_visible(cards, locked, 'Clubs', 'K') is True
        assert _collection_card_visible(cards, locked, 'Spades', 'Q') is True
        assert _collection_card_display_state(
            cards, locked, 'Hearts', 'A') == 'owned'
        assert _collection_card_display_state(
            cards, locked, 'Clubs', 'K') == 'locked_placeholder'
        assert _collection_card_display_state(
            cards, locked, 'Spades', 'Q') == 'missing'
        assert _collection_card_display_state(
            cards, locked, 'Clubs', 'K', show_locked=True) == 'owned'
        assert _owned_card_fully_locked(cards, locked, 'Spades', 'Q') is False
        assert _owned_card_fully_locked(cards, locked, 'Clubs', 'K') is True

    def test_show_locked_visibility_includes_owned_locked_cards(self):
        from game.screens.collection_screen import _collection_card_visible

        cards = {('Clubs', 'K'): 1}
        locked = {('Clubs', 'K'): 1}

        assert _collection_card_visible(
            cards, locked, 'Clubs', 'K', show_locked=True) is True
        assert _collection_card_visible(
            cards, locked, 'Spades', 'Q', show_locked=True) is True

    def test_card_positions_stay_stable_across_locked_visibility_toggle(self):
        import pygame
        from game.screens.collection_screen import CollectionScreen

        screen = object.__new__(CollectionScreen)
        screen._panel_rect = pygame.Rect(0, 0, 1000, 600)
        screen._main_ranks = ['A', 'K']
        screen._side_ranks = ['2']
        screen._cards = {
            ('Hearts', 'A'): 2,
            ('Clubs', 'K'): 1,
            ('Spades', '2'): 3,
        }
        screen._locked = {
            ('Clubs', 'K'): 1,
            ('Spades', '2'): 1,
        }
        screen._show_locked_cards = False

        positions = screen._compute_card_positions()
        keys = {(suit, rank) for _x, _y, suit, rank, _section in positions}

        assert ('Hearts', 'A') in keys
        assert ('Spades', '2') in keys
        assert ('Diamonds', 'K') in keys
        assert ('Clubs', 'K') in keys
        assert len(screen._card_rects) == 12

        screen._show_locked_cards = True
        positions = screen._compute_card_positions()
        keys = {(suit, rank) for _x, _y, suit, rank, _section in positions}

        assert ('Clubs', 'K') in keys
        assert len(screen._card_rects) == 12

    def test_empty_collection_still_lays_out_full_catalogue(self):
        import pygame
        from config import settings
        from game.screens.collection_screen import CollectionScreen, _collection_sort_key

        screen = object.__new__(CollectionScreen)
        screen._panel_rect = pygame.Rect(0, 0, 2000, 1000)
        screen._main_ranks = sorted(
            settings.RANKS_MAIN_CARDS,
            key=lambda r: _collection_sort_key(r, 'main'),
        )
        screen._side_ranks = sorted(
            settings.RANKS_SIDE_CARDS,
            key=lambda r: _collection_sort_key(r, 'side'),
        )
        screen._cards = {}
        screen._locked = {}
        screen._show_locked_cards = False

        positions = screen._compute_card_positions()

        assert len(positions) == len(settings.SUITS) * (
            len(settings.RANKS_MAIN_CARDS) + len(settings.RANKS_SIDE_CARDS))
        assert len(screen._card_rects) == len(positions)


def test_collection_basics_window_teaches_cards_recipes_then_roulette():
    import pygame
    from game.components import tutorial_diagrams as td
    from game.screens.collection_screen import CollectionScreen

    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))

    screen = object.__new__(CollectionScreen)
    screen.window = None
    screen._data_loaded = True
    screen._collection_basics_dialogue = None
    screen._menu_coach_allowed_common = lambda: True
    screen._onboarding_completed_steps = lambda: set()
    screen._menu_coach_seen = lambda: set()
    screen._booster_poller = None
    screen._reveal_overlay = None
    screen._sell_dialogue = None
    screen._trade_dialogue = None
    screen._profile_dialogue = None
    screen.dialogue_box = None

    screen._maybe_show_collection_basics()

    dialogue = screen._collection_basics_dialogue
    assert dialogue is not None
    assert [page['title'] for page in dialogue.pages] == [
        'Cards become actions',
        'Your starter set',
    ]
    recipe_page = dialogue.pages[0]
    assert recipe_page['image']() is td.card_recipe_examples()
    recipe_copy = ' '.join(recipe_page['lines']).lower()
    assert 'figure' in recipe_copy
    assert "don't worry about memorizing recipes" in recipe_copy
    starter_copy = ' '.join(dialogue.pages[1]['lines']).lower()
    assert 'spin the roulette' in starter_copy
    assert dialogue.pages[1]['button_label'] == 'Spin Roulette'


def test_finishing_collection_lesson_starts_roulette_immediately(monkeypatch):
    from game.screens.collection_screen import CollectionScreen

    onboarding = {
        'welcome_seen': True,
        'starter_suits': {},
        'completed_steps': [],
        'menu_hints_seen': [],
        'onboarding_skipped': False,
        'starter_set_granted': False,
    }
    screen = object.__new__(CollectionScreen)
    screen.state = SimpleNamespace(
        user_dict={'onboarding': onboarding},
        set_msg=lambda _msg: None,
    )
    screen.window = None
    screen._collection_basics_dialogue = SimpleNamespace(
        update=lambda _events: 'done')
    screen._starter_reveal_dialogue = None
    screen._starter_reveal_prepare_attempted = False
    screen._data_loaded = True
    screen._cards = {}
    screen._locked = {}
    screen._reveal_overlay = None
    screen._booster_poller = None
    screen._sell_dialogue = None
    screen._trade_dialogue = None
    screen._profile_dialogue = None
    screen.dialogue_box = None
    screen._menu_coach_allowed_common = lambda: True
    screen._onboarding = lambda: screen.state.user_dict['onboarding']
    screen._menu_coach_seen = lambda: set(
        screen._onboarding().get('menu_hints_seen') or [])
    screen._mark_menu_coaches_seen = lambda ids: screen._onboarding().update({
        'menu_hints_seen': list(ids)})
    screen._apply_onboarding_payload = lambda data: screen.state.user_dict.update(
        {'onboarding': data['onboarding']})
    monkeypatch.setattr(
        'game.screens.collection_screen.onboarding_service.prepare_starter_reveal',
        lambda: {
            'suit': 'Diamonds',
            'onboarding': {
                **screen._onboarding(),
                'starter_suits': {
                    'offensive': 'Diamonds', 'defensive': 'Spades'},
            },
        })

    assert screen._handle_collection_basics_events([]) is True

    assert screen._collection_basics_dialogue is None
    assert screen._starter_reveal_dialogue is not None
    assert screen._starter_reveal_dialogue.suit == 'Diamonds'


def test_starter_reveal_starts_without_booster_or_pregranted_cards(monkeypatch):
    import pygame
    from game.screens.collection_screen import CollectionScreen

    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    screen = object.__new__(CollectionScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'starter_suits': {},
        'completed_steps': [],
        'menu_hints_seen': ['collection_basics_window'],
        'onboarding_skipped': False,
        'starter_set_granted': False,
    }}, set_msg=lambda _msg: None)
    screen.window = None
    screen._starter_reveal_dialogue = None
    screen._menu_coach_allowed_common = lambda: True
    screen._starter_reveal_prepare_attempted = False
    screen._data_loaded = True
    screen._cards = {}
    screen._locked = {}
    screen._reveal_overlay = None
    screen._collection_basics_dialogue = None
    screen._booster_poller = None
    screen._sell_dialogue = None
    screen._trade_dialogue = None
    screen._profile_dialogue = None
    screen.dialogue_box = None
    screen._apply_onboarding_payload = lambda data: screen.state.user_dict.update(
        {'onboarding': data['onboarding']})
    monkeypatch.setattr(
        'game.screens.collection_screen.onboarding_service.prepare_starter_reveal',
        lambda: {
            'suit': 'Hearts',
            'onboarding': {
                **screen.state.user_dict['onboarding'],
                'starter_suits': {'offensive': 'Hearts', 'defensive': 'Clubs'},
            },
        })

    screen._maybe_show_starter_reveal()

    assert screen._starter_reveal_dialogue is not None
    assert screen._starter_reveal_dialogue.done_label == 'Go to Kingdom'
    assert screen._cards == {}


def test_starter_cards_are_added_on_reel_settle_then_routes_to_kingdom(monkeypatch):
    from game.screens.collection_screen import CollectionScreen

    screen = object.__new__(CollectionScreen)
    onboarding = {
        'starter_suits': {'offensive': 'Hearts', 'defensive': 'Clubs'},
        'completed_steps': [],
        'menu_hints_seen': ['collection_basics_window'],
        'onboarding_skipped': False,
        'starter_set_granted': False,
    }
    screen.state = SimpleNamespace(
        user_dict={'onboarding': onboarding},
        screen='collection',
        set_msg=lambda _msg: None,
    )
    screen._cards = {}
    screen._locked = {}
    results = iter(['revealed', 'done'])
    screen._starter_reveal_dialogue = SimpleNamespace(
        update=lambda _events: next(results),
        set_grant_result=lambda _success: None,
    )
    screen._apply_onboarding_payload = lambda data: screen.state.user_dict.update(
        {'onboarding': data['onboarding']})
    monkeypatch.setattr(
        'game.screens.collection_screen.onboarding_service.complete_starter_reveal',
        lambda: {
            'onboarding': {
                **onboarding,
                'starter_set_granted': True,
                'menu_hints_seen': [
                    'collection_basics_window', 'starter_suit_reveal'],
            },
            'starter_cards': [
                {'suit': 'Hearts', 'rank': 'K', 'total': 2, 'locked': 0},
                {'suit': 'Hearts', 'rank': 'J', 'total': 2, 'locked': 0},
            ],
        })

    assert screen._cards == {}
    assert screen._handle_starter_reveal_events([]) is True
    assert screen._cards == {('Hearts', 'K'): 2, ('Hearts', 'J'): 2}
    assert screen.state.screen == 'collection'

    assert screen._handle_starter_reveal_events([]) is True
    assert screen._starter_reveal_dialogue is None
    assert screen.state.screen == 'kingdom'


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

    def test_maharaja_palette_sits_above_rare_gold(self):
        from config.collection_settings import (
            COLLECTION_MAHARAJA_BORDER_CLR,
            COLLECTION_MAHARAJA_GLOW_CLR,
            COLLECTION_MAHARAJA_TIER,
            COLLECTION_TIER_BORDER_COLORS,
            COLLECTION_TIER_COLORS,
            COLLECTION_TIER_GLOW_TINTS,
            COLLECTION_TIER_LABELS,
        )
        rare_tier = 3

        assert COLLECTION_MAHARAJA_TIER > max(COLLECTION_TIER_LABELS)
        assert COLLECTION_MAHARAJA_BORDER_CLR != COLLECTION_TIER_BORDER_COLORS[rare_tier][:3]
        assert COLLECTION_MAHARAJA_GLOW_CLR != COLLECTION_TIER_COLORS[rare_tier]
        assert COLLECTION_MAHARAJA_GLOW_CLR[2] > 240
        assert COLLECTION_MAHARAJA_GLOW_CLR[1] < COLLECTION_MAHARAJA_GLOW_CLR[0]
        assert COLLECTION_MAHARAJA_GLOW_CLR[1] < COLLECTION_MAHARAJA_GLOW_CLR[2]
        assert (COLLECTION_TIER_GLOW_TINTS[COLLECTION_MAHARAJA_TIER]
                != COLLECTION_TIER_GLOW_TINTS[rare_tier])

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
owned_surf = detail_font.render('×999', True, settings.COLLECTION_PACK_PANEL_TEXT_CLR)
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

    def test_hidden_cards_use_their_tier_glow(self):
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

        calls = []
        overlay._draw_tier_glow = lambda _slot, tier, pulse=False: calls.append(
            (tier, pulse))

        for i, slot in enumerate(overlay._slots):
            overlay._draw_hidden_card(i, slot, hovered=(i == 1))

        assert calls == [(1, False), (2, True), (3, False)]

    def test_maharaja_reveal_uses_premium_tier_even_if_marked_rare(self):
        import pygame
        from config import settings
        from game.components.booster_reveal import BoosterRevealOverlay

        window = pygame.display.get_surface() or pygame.display.set_mode(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay = BoosterRevealOverlay(window, [
            {'suit': 'Hearts', 'rank': 'MK', 'value': 4, 'tier': 3},
        ], title='Hearts Maharaja Crafted!')

        assert overlay._tiers == [settings.COLLECTION_MAHARAJA_TIER]
        assert settings.COLLECTION_MAHARAJA_TIER in overlay._tier_glows

        calls = []
        overlay._draw_tier_glow = lambda _slot, tier, pulse=False: calls.append(
            (tier, pulse))
        overlay._draw_hidden_card(0, overlay._slots[0], hovered=False)

        assert calls == [(settings.COLLECTION_MAHARAJA_TIER, False)]

        calls.clear()
        overlay._draw_revealed_card(0, overlay._slots[0], hovered=False)
        assert calls == [(settings.COLLECTION_MAHARAJA_TIER, True)]

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

    def test_bulk_reveal_keeps_all_cards_and_paginates(self):
        import pygame
        from config import settings
        from game.components.booster_reveal import BoosterRevealOverlay

        window = pygame.display.get_surface() or pygame.display.set_mode(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        cards = [
            {'suit': 'Hearts', 'rank': '7', 'value': 7, 'tier': 1}
            for _ in range(15)
        ]
        overlay = BoosterRevealOverlay(window, cards)

        assert len(overlay._cards) == 15
        assert overlay._page_count >= 2
        assert len(list(overlay._visible_indices())) <= overlay._page_size
        overlay.draw()  # must not raise

    def test_bulk_reveal_all_button_animates_every_card(self, monkeypatch):
        import pygame
        from config import settings
        from game.components.booster_reveal import BoosterRevealOverlay

        window = pygame.display.get_surface() or pygame.display.set_mode(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        cards = [
            {'suit': 'Hearts', 'rank': '7', 'value': 7, 'tier': 1}
            for _ in range(9)
        ]
        overlay = BoosterRevealOverlay(window, cards)
        monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)

        assert overlay.all_revealed is False
        assert overlay.handle_click(overlay._reveal_all_rect.center) is False
        assert overlay.all_revealed is False
        assert set(overlay._states) == {'revealing'}
        starts = list(overlay._reveal_started_at)
        assert starts[0] == 1000
        assert starts[-1] > starts[0]

        monkeypatch.setattr(
            pygame.time,
            'get_ticks',
            lambda: starts[-1] + settings.COLLECTION_REVEAL_FLIP_MS + 1,
        )
        overlay.update()
        assert overlay.all_revealed is True

    def test_special_card_celebration_tracks_uncommon_and_rare(self, monkeypatch):
        import pygame
        from config import settings
        from game.components.booster_reveal import BoosterRevealOverlay

        window = pygame.display.get_surface() or pygame.display.set_mode(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay = BoosterRevealOverlay(window, [
            {'suit': 'Hearts', 'rank': '7', 'value': 7, 'tier': 1},
            {'suit': 'Clubs', 'rank': 'J', 'value': 1, 'tier': 2},
            {'suit': 'Spades', 'rank': 'K', 'value': 10, 'tier': 3},
        ])
        overlay._reveal_started_at = [1000, 1000, 1000]
        monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1100)

        assert overlay._celebration_progress(0) is None
        assert overlay._celebration_progress(1) is not None
        assert overlay._celebration_progress(2) is not None

    def test_reveal_summary_reports_new_types_and_usable_copies(self):
        import pygame
        from config import settings
        from game.components.booster_reveal import BoosterRevealOverlay

        window = pygame.display.get_surface() or pygame.display.set_mode(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay = BoosterRevealOverlay(window, [
            {'suit': 'Hearts', 'rank': '7', 'tier': 1,
             '_impact_new_type': True, '_impact_owned_after': 1},
            {'suit': 'Clubs', 'rank': 'J', 'tier': 2,
             '_impact_new_type': False, '_impact_owned_after': 4},
            {'suit': 'Spades', 'rank': 'K', 'tier': 3,
             '_impact_new_type': True, '_impact_owned_after': 1},
        ])

        assert overlay._impact_summary_text() == (
            '3 free copies added  ·  2 new card types')

    def test_duplicate_reveals_have_no_redundant_plus_one_badge(self):
        from game.components.booster_reveal import _impact_badge_label

        assert _impact_badge_label({
            '_impact_new_type': True,
            '_impact_owned_after': 1,
        }) == 'NEW'
        assert _impact_badge_label({
            '_impact_new_type': False,
            '_impact_owned_after': 4,
        }) == ''


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
        assert hasattr(collection_service, 'craft_maharaja')

    def test_craft_maharaja_posts_suit_payload(self, monkeypatch):
        from utils import collection_service

        captured = {}

        class _Resp:
            def json(self):
                return {'success': True,
                        'card': {'suit': 'Hearts', 'rank': 'MK', 'value': 4},
                        'consumed': 13}

        def _fake_post(url, json=None, timeout=None, **kwargs):
            captured['url'] = url
            captured['json'] = json
            return _Resp()

        monkeypatch.setattr(collection_service.requests, 'post', _fake_post)

        result = collection_service.craft_maharaja('Hearts')

        assert captured['json'] == {'suit': 'Hearts'}
        assert captured['url'].endswith('/collection/craft_maharaja')
        assert result['success'] is True
        assert result['card']['rank'] == 'MK'


class TestMaharajaCraft:
    """Verify the crafted Maharaja ('MK') collection logic."""

    def test_main_ranks_lead_with_maharaja(self):
        from config import settings
        from game.screens.collection_screen import _ordered_main_ranks
        ranks = _ordered_main_ranks()
        assert ranks[0] == settings.RANK_MAHARAJA
        assert set(ranks[1:]) == set(settings.RANKS_MAIN_CARDS)

    def test_craft_progress_ready_when_all_free(self):
        from config import settings
        from game.screens.collection_screen import _maharaja_craft_progress
        cards = {('Hearts', r): 1 for r in settings.RANKS}
        ready, total, missing = _maharaja_craft_progress(cards, {}, 'Hearts')
        assert (ready, total, missing) == (13, 13, [])

    def test_craft_progress_not_ready_when_rank_fully_locked(self):
        from config import settings
        from game.screens.collection_screen import _maharaja_craft_progress
        cards = {('Hearts', r): 1 for r in settings.RANKS}
        locked = {('Hearts', 'A'): 1}  # the only copy is locked → not ready
        ready, total, missing = _maharaja_craft_progress(cards, locked, 'Hearts')
        assert ready == 12
        assert total == 13
        assert 'A' in missing

    def test_maharaja_never_sellable(self):
        from game.screens.collection_screen import _sell_price
        assert _sell_price('MK') == 0
        assert _sell_price('MK', 5) == 0

    def test_maharaja_gets_dedicated_tier_label(self):
        from config import settings
        from game.screens.collection_screen import _tier_label, _card_pack_type
        assert _tier_label('MK') == settings.COLLECTION_MAHARAJA_LABEL
        assert _tier_label('MK') != 'Common'
        assert _card_pack_type('MK') == 'main'

    def test_maharaja_craftable_tracks_free_copies(self):
        from config import settings
        from game.screens.collection_screen import CollectionScreen

        screen = object.__new__(CollectionScreen)
        screen._cards = {('Hearts', r): 1 for r in settings.RANKS}
        screen._locked = {}
        assert screen._maharaja_craftable('Hearts') is True

        # Locking the only copy of one rank turns the highlight off again.
        screen._locked = {('Hearts', 'A'): 1}
        assert screen._maharaja_craftable('Hearts') is False

    def test_craft_ready_pill_draws_on_card_bottom(self):
        import pygame
        from config import settings
        from game.screens.collection_screen import CollectionScreen

        window = pygame.display.get_surface() or pygame.display.set_mode(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        screen = object.__new__(CollectionScreen)
        screen.window = window
        screen._badge_font = settings.get_font(
            settings.COLLECTION_BADGE_FONT_SIZE, bold=True)

        card_rect = pygame.Rect(100, 100, settings.COLLECTION_CARD_W,
                                settings.COLLECTION_CARD_H)
        blits = []
        real_blit = window.blit
        screen.window = type('W', (), {
            'blit': lambda _self, surf, dest, *a, **kw: blits.append(
                (surf, dest)) or real_blit(surf, dest, *a, **kw)})()

        screen._draw_maharaja_craft_ready_pill(card_rect)

        assert len(blits) == 1
        pill, dest = blits[0]
        pill_rect = pill.get_rect(topleft=(dest.x, dest.y))
        assert card_rect.contains(pill_rect)
        assert pill_rect.centerx == card_rect.centerx

    def test_craft_reveal_overlay_uses_craft_headline(self):
        import pygame
        from config import settings
        from game.components.booster_reveal import BoosterRevealOverlay

        window = pygame.display.get_surface() or pygame.display.set_mode(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay = BoosterRevealOverlay(
            window,
            [{'suit': 'Hearts', 'rank': 'MK', 'value': 4, 'tier': 3}],
            pack_type='main',
            title='Hearts Maharaja Crafted!')

        captured = []
        real_font = overlay._title_font

        class _CaptureFont:
            def render(self, text, *args, **kwargs):
                captured.append(text)
                return real_font.render(text, *args, **kwargs)

        overlay._title_font = _CaptureFont()
        overlay.draw()

        assert captured == ['Hearts Maharaja Crafted!']

    def test_reveal_overlay_defaults_to_pack_headline(self):
        import pygame
        from config import settings
        from game.components.booster_reveal import BoosterRevealOverlay

        window = pygame.display.get_surface() or pygame.display.set_mode(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        overlay = BoosterRevealOverlay(window, [
            {'suit': 'Hearts', 'rank': '7', 'value': 7, 'tier': 1},
        ])

        captured = []
        real_font = overlay._title_font

        class _CaptureFont:
            def render(self, text, *args, **kwargs):
                captured.append(text)
                return real_font.render(text, *args, **kwargs)

        overlay._title_font = _CaptureFont()
        overlay.draw()

        assert captured == ['Main Booster Pack']


def test_maharaja_click_routes_to_craft_not_sell_or_trade():
    import pygame
    from config import settings
    from game.screens.collection_screen import CollectionScreen
    from game.components.cards.card_img import CardImg

    window = pygame.display.get_surface() or pygame.display.set_mode(
        (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen = object.__new__(CollectionScreen)
    screen.window = window
    screen._cards = {('Hearts', r): 1 for r in settings.RANKS}
    screen._locked = {}
    screen._card_imgs = {
        ('Hearts', 'MK'): CardImg(window, 'Hearts', 'MK', 60, 90)}
    screen._profile_dialogue = None
    screen._profile_card = None
    screen._profile_pinned_tooltip = None
    screen._craft_dialogue = None
    screen._craft_suit = None

    # A click on an MK cell normally routes through _open_profile_dialogue.
    screen._open_profile_dialogue('Hearts', 'MK')

    # It must open the craft dialogue — never the sell/convert profile.
    assert screen._profile_dialogue is None
    assert screen._craft_dialogue is not None
    assert screen._craft_suit == 'Hearts'
    actions = [button.text for button in screen._craft_dialogue.buttons]
    assert actions == ['Craft', 'cancel']
    action_names = {a.lower() for a in actions}
    assert 'sell copies' not in action_names
    assert 'convert' not in action_names
    # All 13 ranks free → the craft button is enabled.
    craft_btn = next(b for b in screen._craft_dialogue.buttons
                     if b.text.lower() == 'craft')
    assert craft_btn.disabled is False


def test_maharaja_craft_button_disabled_when_not_ready():
    import pygame
    from config import settings
    from game.screens.collection_screen import CollectionScreen
    from game.components.cards.card_img import CardImg

    window = pygame.display.get_surface() or pygame.display.set_mode(
        (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen = object.__new__(CollectionScreen)
    screen.window = window
    screen._cards = {('Spades', r): 1 for r in settings.RANKS}
    screen._locked = {('Spades', 'K'): 1}  # one rank fully locked
    screen._card_imgs = {
        ('Spades', 'MK'): CardImg(window, 'Spades', 'MK', 60, 90)}
    screen._profile_dialogue = None
    screen._profile_card = None
    screen._profile_pinned_tooltip = None
    screen._craft_dialogue = None
    screen._craft_suit = None

    screen._open_craft_dialogue('Spades')

    craft_btn = next(b for b in screen._craft_dialogue.buttons
                     if b.text.lower() == 'craft')
    assert craft_btn.disabled is True
    assert screen._craft_ready == 12
    assert screen._craft_total == 13
    assert screen._craft_missing == ['K']
    assert screen._craft_dialogue.message_after_images == '\n\n\n'


def test_maharaja_craft_dialogue_promotes_single_figure_use(monkeypatch):
    import pygame
    from config import settings
    from game.screens.collection_screen import CollectionScreen
    from utils import card_uses

    window = pygame.display.get_surface() or pygame.display.set_mode(
        (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    icon = pygame.Surface((48, 48), pygame.SRCALPHA)
    screen = object.__new__(CollectionScreen)
    screen.window = window
    screen._cards = {('Hearts', r): 1 for r in settings.RANKS}
    screen._locked = {}
    screen._card_imgs = {
        ('Hearts', 'MK'): SimpleNamespace(
            front_img=pygame.Surface((60, 90), pygame.SRCALPHA))
    }
    screen._profile_dialogue = None
    screen._profile_card = None
    screen._profile_pinned_tooltip = None

    monkeypatch.setattr(card_uses, 'get_card_uses', lambda _suit, _rank: {
        'figures': [('Djungle Maharaja', icon, 'Primordial offensive king.')],
        'spells': [],
        'battle_moves': [],
    })

    screen._open_craft_dialogue('Hearts')

    dialogue = screen._craft_dialogue
    assert dialogue.title == 'Craft Hearts Maharaja'
    assert 'Legendary Castle Card' in dialogue.message
    assert 'Djungle Maharaja' in dialogue.message
    assert dialogue._lead_items
    assert dialogue.message_after_images == '\n\n\n'
    assert screen._craft_ready == 13
    assert screen._craft_total == 13
    assert screen._craft_missing == []
    assert len(dialogue.image_groups) == 1

    group = dialogue.image_groups[0]
    assert group['title'] == 'Builds: 1 figure'
    assert group['note_prefix'] == 'Djungle Maharaja'
    assert group['feature_item'] is True
    assert group['badge_icon'] is None
    assert 'Power 16 castle' in group['description']
    assert 'Supports 3 village slots and 2 military slots' in group['description']
    assert 'villagers +' not in group['description']
    assert 'warriors' not in group['description']
    assert 'checkmate' not in group['description'].lower()


def test_maharaja_craft_progress_overlay_draws_missing_card_thumbnails():
    import pygame
    from config import settings
    from game.screens.collection_screen import CollectionScreen
    from game.components.cards.card_img import CardImg

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT), pygame.SRCALPHA)
    screen = object.__new__(CollectionScreen)
    screen.window = window
    screen._cards = {('Spades', r): 1 for r in settings.RANKS}
    screen._locked = {('Spades', 'K'): 1}
    screen._card_imgs = {
        ('Spades', rank): CardImg(window, 'Spades', rank, 60, 90)
        for rank in settings.RANKS + [settings.RANK_MAHARAJA]
    }
    screen._profile_dialogue = None
    screen._profile_card = None
    screen._profile_pinned_tooltip = None

    screen._open_craft_dialogue('Spades')
    area = screen._craft_progress_area(screen._craft_dialogue)
    before = pygame.image.tobytes(window.subsurface(area).copy(), 'RGBA')

    screen._draw_craft_progress_overlay()

    after = pygame.image.tobytes(window.subsurface(area).copy(), 'RGBA')
    assert before != after


def test_open_booster_confirmation_offers_open_all_for_multiple_packs():
    import pygame
    from game.screens.collection_screen import CollectionScreen

    window = pygame.display.get_surface() or pygame.display.set_mode((1, 1))
    screen = object.__new__(CollectionScreen)
    screen.window = window
    screen._pending_booster_type = 'main'
    screen._boosters = 4
    screen._boosters_side = 1
    screen._booster_icon_dialog = pygame.Surface((24, 24), pygame.SRCALPHA)
    screen._booster_side_icon_dialog = pygame.Surface((24, 24), pygame.SRCALPHA)

    screen._confirm_open_booster('main')

    assert screen.dialogue_box.actions == ['Open', 'Open all', 'cancel']


def test_open_all_status_starts_bulk_booster_request():
    from types import SimpleNamespace
    from game.screens.collection_screen import CollectionScreen

    screen = object.__new__(CollectionScreen)
    screen.state = SimpleNamespace(
        screen='collection',
        action={'task': None, 'content': None, 'status': 'open all'},
        set_msg=lambda _msg: None,
    )
    screen.control_buttons = []
    screen.dialogue_box = None
    screen._pending_booster_type = 'main'
    screen._boosters = 5
    screen._boosters_side = 2
    calls = []
    screen._start_booster_request = lambda action, pack_type, quantity=1: calls.append(
        (action, pack_type, quantity))

    CollectionScreen.handle_events(screen, [])

    assert calls == [('open', 'main', 5)]


def test_card_profile_keeps_card_art_and_contextual_copy_actions(monkeypatch):
    import pygame
    from config import settings
    from game.screens.collection_screen import CollectionScreen
    from utils import card_uses

    window = pygame.display.get_surface() or pygame.display.set_mode(
        (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen = object.__new__(CollectionScreen)
    screen.window = window
    screen._cards = {('Hearts', 'A'): 3}
    screen._locked = {('Hearts', 'A'): 1}
    screen._card_imgs = {
        ('Hearts', 'A'): SimpleNamespace(
            front_img=pygame.Surface((60, 90), pygame.SRCALPHA))
    }
    monkeypatch.setattr(card_uses, 'get_card_uses', lambda _suit, _rank: {
        'figures': [], 'spells': [], 'battle_moves': [],
    })

    screen._open_profile_dialogue('Hearts', 'A')

    dialogue = screen._profile_dialogue
    assert dialogue.title == 'Hearts A'
    assert [button.text for button in dialogue.buttons] == [
        'Sell copies', 'Convert', 'Close']
    assert dialogue._lead_items
    assert all(button.disabled is False for button in dialogue.buttons)
    assert all(group['icon'] is not None for group in dialogue.image_groups)
    assert all(group['badge_icon'] is None for group in dialogue.image_groups)
    assert '3 owned' in dialogue.message
    assert '2 free' in dialogue.message
    assert '1 in use' in dialogue.message


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

    def test_coach_routes_starter_reveal_then_kingdom_then_loop(self):
        screen = self._screen()
        # The modal owns the starter reveal; no booster coach interrupts it.
        assert screen._current_collection_coach_step() is None

        # Once revealed, the roulette button routes directly to Kingdom; no
        # coach is attached to the global Home icon.
        screen.state.user_dict['onboarding']['menu_hints_seen'].append(
            'starter_suit_reveal')
        assert screen._current_collection_coach_step() is None

        # After the first conquest the collection screen no longer nudges back
        # and forth (the reward-pack round-trip is gone); the kingdom and menu
        # coaches steer the player to collect production, so collection coaching
        # goes quiet here.
        screen.state.user_dict['onboarding']['completed_steps'].append(
            'finish_first_conquer_battle')
        assert screen._current_collection_coach_step() is None

        # After the tutorial completes the collection screen has no further
        # coaching (the side-booster nudge was removed).
        screen.state.user_dict['onboarding']['completed_steps'].extend([
            'collect_first_kingdom_production', 'finish_tutorial'])
        assert screen._current_collection_coach_step() is None

    def test_coach_never_routes_to_duel_during_tutorial(self):
        # Reward pack opened, tutorial unfinished: the collection coach must
        # never navigate to the duel. With the round-trip removed it simply goes
        # quiet here (the kingdom/menu coaches steer back to production).
        screen = self._screen(
            completed=['finish_first_conquer_battle'],
            seen=['collection_starter_cards'])
        step = screen._current_collection_coach_step()
        assert step is None or step.get('navigate_screen') != 'duel_menu'

    def test_coach_never_requires_main_booster_during_first_journey(self):
        screen = self._screen(completed=[
            'finish_first_conquer_battle',
        ])
        screen.state.user_dict['onboarding']['next_action'] = {
            'screen': 'collection',
            'label': 'Open Reward Pack',
            'target_id': 'collection_open_main_booster',
        }
        screen.state.user_dict['onboarding']['menu_hints_seen'].append(
            'collection_starter_cards')

        step = screen._current_collection_coach_step()

        assert step is None

    def test_open_booster_result_does_not_mark_removed_tutorial_step(self, monkeypatch):
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

        assert 'open_first_main_booster' not in screen.state.user_dict['onboarding']['completed_steps']
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
