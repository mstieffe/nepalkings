# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import math

import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import (
    MenuScreenMixin,
    menu_chrome_safe_top,
    menu_chrome_safe_width,
)
from game.components.floating_text import FloatingText, FloatingTextLayer
from game.components.cards.card_img import CardImg
from game.components.dialogue_box import DialogueBox
from config import settings
from utils.utils import Button
from utils.background_poller import BackgroundPoller
from utils import collection_service
import logging

logger = logging.getLogger('nk.screens.collection')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# ── Overall box ─────────────────────────────────────────────────────
_BOX_PAD    = int(0.025 * _SH)
_BOX_X      = int(0.04 * _SW)
_BOX_Y      = menu_chrome_safe_top(int(0.10 * _SH))
_BOX_W      = menu_chrome_safe_width(_BOX_X, int(0.87 * _SW))
_BOX_BOTTOM = int(0.92 * _SH)
_BOX_H      = _BOX_BOTTOM - _BOX_Y

# Sell price helpers (mirror server logic so we can preview locally)
_KEY_RANKS = ['J', 'Q', 'K', 'A']
_KEY_MULTIPLIER = 10

def _sell_price(rank, quantity=1):
    # Maharaja cards are crafted, never sellable.
    if rank == settings.RANK_MAHARAJA:
        return 0
    value = settings.RANK_TO_VALUE.get(rank, 0)
    if rank in _KEY_RANKS:
        return value * _KEY_MULTIPLIER * quantity
    return value * quantity


def _card_pack_type(rank):
    """Return the collection pack family for a rank."""
    if rank in settings.RANKS_SIDE_CARDS:
        return 'side'
    return 'main'


def _card_tier(rank, pack_type=None):
    """Return a booster tier for *rank*, inferred from main/side pack tables."""
    if pack_type == 'side':
        return settings.COLLECTION_SIDE_RANK_TO_TIER.get(rank, 1)
    if pack_type == 'main':
        return settings.COLLECTION_MAIN_RANK_TO_TIER.get(rank, 1)
    return (settings.COLLECTION_MAIN_RANK_TO_TIER.get(rank)
            or settings.COLLECTION_SIDE_RANK_TO_TIER.get(rank)
            or 1)


def _tier_label(rank, pack_type=None):
    # Maharaja has no booster rarity tier; it gets its own crafted label.
    if rank == settings.RANK_MAHARAJA:
        return settings.COLLECTION_MAHARAJA_LABEL
    return settings.COLLECTION_TIER_LABELS.get(_card_tier(rank, pack_type), 'Common')


def _collection_sort_key(rank, pack_type):
    """Sort key for the collection grid.

    Order: tier desc → key cards before number cards → higher card value first.
    The crafted Maharaja always sorts leftmost.
    """
    if rank == settings.RANK_MAHARAJA:
        return (-99, 0, 0)
    tier = _card_tier(rank, pack_type)
    is_number = 1 if rank in settings.NUMBER_CARDS else 0  # key (0) before number (1)
    value = settings.RANK_TO_VALUE.get(rank, 0)
    return (-tier, is_number, -value)


def _ordered_main_ranks():
    """Main-card columns for the grid: the crafted Maharaja slot leads, then the
    regular ranks sorted tier → key → value."""
    return [settings.RANK_MAHARAJA] + sorted(
        settings.RANKS_MAIN_CARDS,
        key=lambda r: _collection_sort_key(r, 'main'),
    )


def _maharaja_craft_progress(cards, locked, suit):
    """Return (ready_count, total, missing_ranks) for crafting *suit*'s Maharaja.

    A rank is ready when the suit has at least one free (unlocked) copy. Only the
    regular ranks (2..A) can be traded into the crafted card.
    """
    ranks = settings.MAHARAJA_CRAFT_RANKS
    ready = 0
    missing = []
    for rank in ranks:
        if _free_card_count(cards, locked, suit, rank) >= 1:
            ready += 1
        else:
            missing.append(rank)
    return ready, len(ranks), missing


def _collection_stats(cards, locked=None):
    """Return compact collection summary values for the UI header."""
    locked = locked or {}
    valid_keys = {
        (suit, rank)
        for suit in settings.SUITS
        for rank in settings.RANKS_MAIN_CARDS + settings.RANKS_SIDE_CARDS
    }
    owned_total = sum(max(0, int(qty or 0)) for key, qty in cards.items() if key in valid_keys)
    unique_owned = sum(1 for key, qty in cards.items() if key in valid_keys and int(qty or 0) > 0)
    locked_total = sum(max(0, int(qty or 0)) for key, qty in locked.items() if key in valid_keys)
    unique_total = len(valid_keys)
    return {
        'owned_total': owned_total,
        'unique_owned': unique_owned,
        'unique_total': unique_total,
        'missing_total': max(0, unique_total - unique_owned),
        'locked_total': locked_total,
        'available_total': max(0, owned_total - locked_total),
    }


def _free_card_count(cards, locked, suit, rank):
    """Return how many owned copies are not locked in defence/conquer use."""
    key = (suit, rank)
    total = max(0, int(cards.get(key, 0) or 0))
    locked_qty = max(0, int((locked or {}).get(key, 0) or 0))
    return max(0, total - locked_qty)


def _owned_card_fully_locked(cards, locked, suit, rank):
    """Return True only for owned cards that have no free copies."""
    total = max(0, int(cards.get((suit, rank), 0) or 0))
    return total > 0 and _free_card_count(cards, locked, suit, rank) <= 0


def _collection_card_visible(cards, locked, suit, rank, show_locked=False):
    """Catalogue slots stay visible even when their owned copy is filtered."""
    return True


def _collection_card_display_state(cards, locked, suit, rank, show_locked=False):
    """Return owned, missing, or a dark placeholder for fully locked stock."""
    total = max(0, int(cards.get((suit, rank), 0) or 0))
    if total <= 0:
        return 'missing'
    if (not show_locked
            and _owned_card_fully_locked(cards, locked, suit, rank)):
        return 'locked_placeholder'
    return 'owned'


def _annotate_booster_impact(drawn_cards, cards, locked=None):
    """Return reveal cards annotated with truthful before/after stock values.

    Counts advance card-by-card so duplicate draws in the same bulk opening
    show the quantity the player will actually own after each reveal.
    """
    running = dict(cards or {})
    locked = locked or {}
    annotated = []
    for raw in drawn_cards or []:
        card = dict(raw)
        key = (card.get('suit'), card.get('rank'))
        before = max(0, int(running.get(key, 0) or 0))
        after = before + 1
        locked_qty = max(0, int(locked.get(key, 0) or 0))
        card['_impact_new_type'] = before == 0
        card['_impact_owned_before'] = before
        card['_impact_owned_after'] = after
        card['_impact_free_after'] = max(0, after - locked_qty)
        annotated.append(card)
        running[key] = after
    return annotated


def _draw_panel(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


class CollectionScreen(MenuScreenMixin, Screen):
    """Full collection screen — card grid, sell dialogue, buy/open booster."""

    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── Title ───────────────────────────────────────────────────
        self._title_font = settings.get_font(settings.COLLECTION_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Collection', True, settings.COLLECTION_TITLE_CLR)
        self._title_y = _BOX_Y + _BOX_PAD
        self._suit_font = settings.get_font(settings.COLLECTION_SUIT_LABEL_FONT_SIZE)
        self._badge_font = settings.get_font(settings.COLLECTION_BADGE_FONT_SIZE, bold=True)
        self._section_font = settings.get_font(settings.COLLECTION_SUIT_LABEL_FONT_SIZE, bold=True)
        self._action_font = settings.get_font(settings.COLLECTION_ACTION_BTN_FONT_SIZE)
        self._stats_font = settings.get_font(settings.COLLECTION_STATS_FONT_SIZE)
        self._pack_title_font = settings.get_font(settings.COLLECTION_PACK_PANEL_TITLE_FONT_SIZE, bold=True)
        self._pack_detail_font = settings.get_font(settings.COLLECTION_PACK_PANEL_DETAIL_FONT_SIZE)
        self._sell_control_font = settings.get_font(settings.COLLECTION_SELL_FONT_SIZE, bold=True)
        _lock_badge_sz = max(7, int(0.014 * _SH))
        _lock_badge_raw = settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT.get('lock')
        self._lock_badge_icon = (
            pygame.transform.smoothscale(
                _lock_badge_raw, (_lock_badge_sz, _lock_badge_sz))
            if _lock_badge_raw is not None else None
        )
        _lock_placeholder_sz = max(
            12, int(min(settings.COLLECTION_CARD_W,
                        settings.COLLECTION_CARD_H) * 0.30))
        self._lock_placeholder_icon = (
            pygame.transform.smoothscale(
                _lock_badge_raw,
                (_lock_placeholder_sz, _lock_placeholder_sz))
            if _lock_badge_raw is not None else None
        )

        # ── Card ranks ──────────────────────────────────────────────
        # Sort: tier desc → key cards before number cards → value desc.
        # The crafted Maharaja ('MK') slot leads the Main Cards section.
        self._main_ranks = _ordered_main_ranks()
        self._side_ranks = sorted(
            settings.RANKS_SIDE_CARDS,
            key=lambda r: _collection_sort_key(r, 'side'),
        )

        # ── Card data from server ───────────────────────────────────
        self._cards = {}       # {(suit,rank): quantity}
        self._locked = {}      # {(suit,rank): locked_quantity}
        self._gold = 0
        self._boosters = 0
        self._boosters_side = 0
        self._data_loaded = False

        # Seed from state so counts display immediately while fetch is in flight
        ud = getattr(self.state, 'user_dict', None) or {}
        self._gold = ud.get('gold', 0)
        self._boosters = ud.get('booster_packs', 0)
        self._boosters_side = ud.get('booster_packs_side', 0)

        # ── Build CardImg cache ─────────────────────────────────────
        # The crafted Maharaja ('MK') is not in RANKS, so add it explicitly.
        cw, ch = settings.COLLECTION_CARD_W, settings.COLLECTION_CARD_H
        self._card_imgs = {}   # {(suit,rank): CardImg}
        for suit in settings.SUITS:
            for rank in settings.RANKS + [settings.RANK_MAHARAJA]:
                self._card_imgs[(suit, rank)] = CardImg(self.window, suit, rank, cw, ch)

        # ── Grey overlay for unowned cards ──────────────────────────
        self._grey_overlay = pygame.Surface((cw, ch), pygame.SRCALPHA)
        self._grey_overlay.fill((0, 0, 0, settings.COLLECTION_GREY_ALPHA))

        # ── Booster pack panels (computed first so card panel stops above them) ──
        _pack_h = settings.COLLECTION_PACK_PANEL_H
        _pack_gap = settings.COLLECTION_PACK_PANEL_GAP
        _pack_margin_x = int(0.020 * _SW)
        _pack_y = _BOX_BOTTOM - _BOX_PAD - _pack_h
        _pack_w = (_BOX_W - _pack_margin_x * 2 - _pack_gap * 2) // 3
        _pack_x = _BOX_X + _pack_margin_x
        self._pack_panel_rects = {
            'main': pygame.Rect(_pack_x, _pack_y, _pack_w, _pack_h),
            'side': pygame.Rect(_pack_x + _pack_w + _pack_gap, _pack_y, _pack_w, _pack_h),
        }
        # Third panel beside the two booster panels explains the safe default
        # card interaction. Sell/convert actions live inside the card profile.
        self._actions_panel_rect = pygame.Rect(
            _pack_x + (_pack_w + _pack_gap) * 2, _pack_y, _pack_w, _pack_h)
        self._pack_button_rects = {}
        for _ptype, _panel in self._pack_panel_rects.items():
            _btn_h = settings.COLLECTION_PACK_PANEL_BTN_H
            _btn_gap = settings.COLLECTION_PACK_PANEL_BTN_GAP
            _btn_w = min(
                settings.COLLECTION_PACK_PANEL_BTN_W,
                (_panel.w - settings.COLLECTION_PACK_PANEL_PAD_X * 2 - _btn_gap) // 2,
            )
            _btn_y = _panel.bottom - settings.COLLECTION_PACK_PANEL_PAD_Y - _btn_h
            _btn_x = _panel.centerx - (_btn_w * 2 + _btn_gap) // 2
            self._pack_button_rects[_ptype] = {
                'open': pygame.Rect(_btn_x, _btn_y, _btn_w, _btn_h),
                'buy': pygame.Rect(_btn_x + _btn_w + _btn_gap, _btn_y, _btn_w, _btn_h),
            }
        self._btn_open_main_rect = self._pack_button_rects['main']['open']
        self._btn_buy_main_rect = self._pack_button_rects['main']['buy']
        self._btn_open_side_rect = self._pack_button_rects['side']['open']
        self._btn_buy_side_rect = self._pack_button_rects['side']['buy']

        # ── X close button (top-right of box) ──
        _xsz = int(0.028 * _SH)
        _xmargin = int(0.012 * _SW)
        self._btn_close_rect = pygame.Rect(
            _BOX_X + _BOX_W - _xsz - _xmargin,
            _BOX_Y + _xmargin,
            _xsz, _xsz)
        self._close_font = settings.get_font(int(settings.FONT_SIZE * 0.85), bold=True)

        # ── Card grid panel (inside the subscreen box, below title) ──
        _panel_pad = int(0.02 * _SW)   # inset from outer box edges
        _title_h = self._title_surf.get_height()
        _stats_top = _BOX_Y + _BOX_PAD + _title_h + int(0.012 * _SH)
        self._stats_rect = pygame.Rect(
            _BOX_X + _panel_pad,
            _stats_top,
            _BOX_W - _panel_pad * 2,
            settings.COLLECTION_STATS_STRIP_H,
        )
        _locked_toggle_w = min(
            int(0.132 * _SW),
            max(int(0.104 * _SW), self._stats_rect.w // 5),
        )
        _locked_toggle_h = min(
            settings.COLLECTION_PACK_PANEL_BTN_H,
            max(14, self._stats_rect.h - int(0.008 * _SH)),
        )
        self._locked_toggle_rect = pygame.Rect(
            self._stats_rect.right - int(0.008 * _SW) - _locked_toggle_w,
            self._stats_rect.centery - _locked_toggle_h // 2,
            _locked_toggle_w,
            _locked_toggle_h,
        )
        self._show_locked_cards = False
        _panel_top = self._stats_rect.bottom + int(0.012 * _SH)
        _panel_bottom = _pack_y - int(0.014 * _SH)
        self._panel_rect = pygame.Rect(
            _BOX_X + _panel_pad,
            _panel_top,
            _BOX_W - _panel_pad * 2,
            _panel_bottom - _panel_top,
        )

        # Pre-render panel background
        self._panel_surf = pygame.Surface(
            (self._panel_rect.w, self._panel_rect.h), pygame.SRCALPHA)
        self._panel_surf.fill((20, 20, 25, 180))
        pygame.draw.rect(self._panel_surf, (80, 75, 65, 200),
                         self._panel_surf.get_rect(), 2)
        _retry_w = min(int(0.18 * _SW), max(120, self._panel_rect.w // 4))
        _retry_h = max(settings.COLLECTION_PACK_PANEL_BTN_H,
                       getattr(settings, 'TOUCH_COMPACT_MIN', 0))
        self._retry_rect = pygame.Rect(0, 0, _retry_w, _retry_h)
        self._retry_rect.center = (
            self._panel_rect.centerx,
            self._panel_rect.centery + int(0.055 * _SH),
        )

        # ── Card click rects (computed per frame based on tab) ──────
        self._card_rects = []  # [(rect, suit, rank), ...]

        # ── Background poller for fetching data ─────────────────────
        self._poller = None
        self._refreshing = False
        self._load_error = None
        self._fetch_collection()

        # ── Sell dialogue state ─────────────────────────────────────
        self._sell_card = None         # (suit, rank)
        self._sell_qty = 1
        self._sell_max = 0
        self._sell_dialogue = None
        self._sell_qty_rects = {}

        # ── Trade dialogue state ────────────────────────────────────
        self._trade_card = None         # (suit, rank) source
        self._trade_target_suit = None  # selected target suit
        self._trade_qty = 1             # number of OUTPUT cards to produce
        self._trade_max = 0             # max output for current target
        self._trade_dialogue = None
        self._trade_qty_rects = {}
        self._trade_target_rects = {}   # {suit: pygame.Rect}

        # ── Profile dialogue (default click) ────────────────────────
        self._profile_dialogue = None
        self._profile_card = None
        self._profile_pinned_tooltip = None
        self._profile_pinned_tooltip_pos = None

        # ── Maharaja craft dialogue (MK click — never sell/trade) ────
        self._craft_dialogue = None
        self._craft_suit = None

        # ── Booster reveal overlay ──────────────────────────────────
        self._reveal_overlay = None
        self._pending_booster_type = 'main'  # tracks which type for dialogue flow
        self._booster_poller = None
        self._booster_action = None
        self._booster_pack_type = None
        self._pending_reveal_gains = {}
        self._recent_card_gains = {}
        self._recent_gains_started_at = None
        # First-visit "collection basics" teaching window (onboarding).
        self._collection_basics_dialogue = None
        # Second welcome-present explainer, shown after the first booster card
        # reveal and before the starter-suit roulette.
        self._starter_present_dialogue = None
        # Starter-suit reveal, shown after the first booster open (the deferred
        # starter set), just before the player is sent to the Kingdom.
        self._starter_reveal_dialogue = None

        # ── Custom button glow ──────────────────────────────────────
        glow_w = int(settings.COLLECTION_PACK_PANEL_BTN_W * 1.3)
        glow_h = int(settings.COLLECTION_PACK_PANEL_BTN_H * 2.2)
        self._action_glows = {}
        for colour in ('yellow', 'white', 'orange'):
            raw = pygame.image.load(settings.GAME_MENU_GLOW_DIR + colour + '.png').convert_alpha()
            self._action_glows[colour] = pygame.transform.smoothscale(raw, (glow_w, glow_h))

        # Hover tracking for action buttons
        self._hovered_btn = None
        self._clicked_btn = None

        # ── Floating text layer ──────────────────────────────────────
        self._floating_text = FloatingTextLayer()
        self._last_render_ms = pygame.time.get_ticks()

    # ── Lifecycle ────────────────────────────────────────────────────

    def on_enter(self):
        """Refresh while keeping the last truthful collection snapshot visible."""
        ud = getattr(self.state, 'user_dict', None) or {}
        self._gold = ud.get('gold', 0)
        self._boosters = ud.get('booster_packs', 0)
        self._boosters_side = ud.get('booster_packs_side', 0)
        self._sell_card = None
        self._sell_dialogue = None
        self._reveal_overlay = None
        self._booster_poller = None
        self._booster_action = None
        self._booster_pack_type = None
        self._trade_card = None
        self._trade_dialogue = None
        self._profile_dialogue = None
        self._profile_card = None
        self._profile_pinned_tooltip = None
        self._craft_dialogue = None
        self._craft_suit = None
        self._fetch_collection()

    # ── data fetching ───────────────────────────────────────────────

    def _fetch_collection(self):
        """Start a background fetch of the collection data."""
        if self._poller and self._poller.busy:
            return
        self._load_error = None
        self._refreshing = True
        self._poller = BackgroundPoller(collection_service.fetch_collection_cards)
        self._poller.poll()

    def _apply_collection_data(self, data):
        """Apply fetched collection data dicts."""
        self._cards = {}
        self._locked = {}
        for c in data.get('cards', []):
            key = (c['suit'], c['rank'])
            self._cards[key] = c.get('total', c.get('quantity', 0))
            self._locked[key] = c.get('locked', 0)
        self._gold = data.get('gold', 0)
        self._boosters = data.get('booster_packs', 0)
        self._boosters_side = data.get('booster_packs_side', 0)
        self._data_loaded = True
        self._refreshing = False
        self._load_error = None
        # Sync gold into state so chrome displays correctly
        if self.state.user_dict:
            self.state.user_dict['gold'] = self._gold
            self.state.user_dict['booster_packs'] = self._boosters
            self.state.user_dict['booster_packs_side'] = self._boosters_side
            self.state.user_dict['maps'] = int(data.get('maps', 0))

    # ── grid layout helpers ─────────────────────────────────────────

    def _compute_card_positions(self):
        """Compute (x, y, suit, rank, section) for each card — side-by-side layout."""
        suits = settings.SUITS
        cw = settings.COLLECTION_CARD_W
        ch = settings.COLLECTION_CARD_H
        gx = settings.COLLECTION_CARD_GAP_X
        gy = settings.COLLECTION_CARD_GAP_Y
        px = self._panel_rect.x + settings.COLLECTION_PANEL_PAD_X
        py = self._panel_rect.y + settings.COLLECTION_PANEL_PAD_Y

        section_header_h = int(0.035 * _SH)
        section_gap_x = int(0.02 * _SW)   # horizontal gap between main and side sections

        positions = []
        self._card_rects = []
        self._section_headers = []  # [(x, y, text), ...]

        # X origin for cards (no suit labels)
        cards_x = px

        # Main section header & side section header on same row
        header_y = py
        main_header_x = cards_x
        main_right_edge = cards_x + len(self._main_ranks) * (cw + gx) - gx
        side_x = main_right_edge + section_gap_x
        side_header_x = side_x

        self._section_headers.append((main_header_x, header_y, 'Main Cards'))
        self._section_headers.append((side_header_x, header_y, 'Side Cards'))

        # Card rows start below headers
        cur_y = header_y + section_header_h

        for row_i, suit in enumerate(suits):
            row_y = cur_y + row_i * (ch + gy)

            # Main cards
            for col_i, rank in enumerate(self._main_ranks):
                if not _collection_card_visible(
                        self._cards, self._locked, suit, rank,
                        getattr(self, '_show_locked_cards', False)):
                    continue
                cx = cards_x + col_i * (cw + gx)
                positions.append((cx, row_y, suit, rank, 'main'))
                self._card_rects.append((pygame.Rect(cx, row_y, cw, ch), suit, rank, 'main'))

            # Side cards (same row, to the right)
            for col_i, rank in enumerate(self._side_ranks):
                if not _collection_card_visible(
                        self._cards, self._locked, suit, rank,
                        getattr(self, '_show_locked_cards', False)):
                    continue
                cx = side_x + col_i * (cw + gx)
                positions.append((cx, row_y, suit, rank, 'side'))
                self._card_rects.append((pygame.Rect(cx, row_y, cw, ch), suit, rank, 'side'))

        return positions

    def _card_at_pos(self, pos):
        """Return the closest visible card, forgiving narrow mobile gaps."""
        for rect, suit, rank, section in self._card_rects:
            if rect.collidepoint(pos):
                return suit, rank, section
        pad = getattr(settings, 'TOUCH_HIT_PAD', 0)
        if pad <= 0:
            return None
        candidates = []
        for rect, suit, rank, section in self._card_rects:
            if rect.inflate(pad * 2, pad * 2).collidepoint(pos):
                distance = ((rect.centerx - pos[0]) ** 2
                            + (rect.centery - pos[1]) ** 2)
                candidates.append((distance, suit, rank, section))
        if not candidates:
            return None
        _distance, suit, rank, section = min(candidates, key=lambda item: item[0])
        return suit, rank, section

    # ── render ──────────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        # Outer box
        box_rect = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        _draw_panel(self.window, box_rect)

        # Title (centred inside box)
        tx = _BOX_X + (_BOX_W - self._title_surf.get_width()) // 2
        self.window.blit(self._title_surf, (tx, self._title_y))

        # Summary stats strip
        self._draw_collection_stats()

        # Card grid panel
        self.window.blit(self._panel_surf, self._panel_rect.topleft)

        # Clip to panel area for scrollable content
        self.window.set_clip(self._panel_rect)
        if self._data_loaded:
            self._draw_card_grid()
        else:
            self._draw_collection_load_state()
        self.window.set_clip(None)

        # Booster controls
        self._draw_pack_panel('main')
        self._draw_pack_panel('side')
        self._draw_actions_panel()

        self._draw_close_x_button()

        # Sell dialogue
        if self._sell_dialogue:
            self._sell_dialogue.draw()
            self._draw_sell_qty_overlay()

        # Trade dialogue
        if self._trade_dialogue:
            self._trade_dialogue.draw()
            self._draw_trade_overlay()

        # Profile dialogue
        if self._profile_dialogue:
            self._profile_dialogue.draw()
            # Tooltip for hovered figure/spell/move icon
            _tt = self._profile_dialogue.get_tooltip(pygame.mouse.get_pos())
            if _tt:
                self._draw_profile_tooltip(_tt)
            elif self._profile_pinned_tooltip:
                self._draw_profile_tooltip(
                    self._profile_pinned_tooltip,
                    anchor=self._profile_pinned_tooltip_pos,
                )

        # Craft dialogue (Maharaja)
        if self._craft_dialogue:
            self._craft_dialogue.draw()

        # Booster reveal overlay
        if self._reveal_overlay:
            self._reveal_overlay.draw()

        # Floating text (buy booster animation)
        now_ms = pygame.time.get_ticks()
        dt_ms = max(0, now_ms - self._last_render_ms)
        self._last_render_ms = now_ms
        self._floating_text.update(dt_ms)
        self._floating_text.draw(self.window)

        # Icon buttons + messages overlay
        self._draw_menu_overlay()
        self._draw_menu_coach(self._current_collection_coach_step())
        if getattr(self, '_collection_basics_dialogue', None):
            self._collection_basics_dialogue.draw()
        if getattr(self, '_starter_present_dialogue', None):
            self._starter_present_dialogue.draw()
        if getattr(self, '_starter_reveal_dialogue', None):
            self._starter_reveal_dialogue.draw()

    def _draw_collection_stats(self):
        """Draw a compact, player-facing stock summary strip."""
        r = self._stats_rect
        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.COLLECTION_STATS_BG_CLR, surf.get_rect(), border_radius=8)
        pygame.draw.rect(surf, settings.COLLECTION_STATS_BORDER_CLR, surf.get_rect(), 1, border_radius=8)
        self.window.blit(surf, r.topleft)

        if not self._data_loaded:
            label = 'Could not load collection' if self._load_error else 'Loading your collection...'
            color = ((235, 180, 145) if self._load_error
                     else settings.COLLECTION_PACK_PANEL_MUTED_CLR)
            text_surf = self._stats_font.render(label, True, color)
            self.window.blit(text_surf, text_surf.get_rect(center=r.center))
            return

        stats = _collection_stats(self._cards, self._locked)
        if settings.TOUCH_TARGET_MIN > 0:
            labels = ('Types', 'Owned', 'In use', 'Free')
        else:
            labels = ('Card types', 'Owned copies', 'In use', 'Free copies')
        items = [
            (labels[0], f"{stats['unique_owned']}/{stats['unique_total']}"),
            (labels[1], str(stats['owned_total'])),
            (labels[2], str(stats['locked_total'])),
            (labels[3], str(stats['available_total'])),
        ]

        rendered = []
        for label, value in items:
            label_surf = self._stats_font.render(f'{label}: ', True, settings.COLLECTION_STATS_TEXT_CLR)
            value_surf = self._stats_font.render(value, True, settings.COLLECTION_STATS_VALUE_CLR)
            rendered.append((label_surf, value_surf, label_surf.get_width() + value_surf.get_width()))
        sep_w = int(0.018 * _SW)
        total_w = sum(width for _, _, width in rendered) + sep_w * (len(rendered) - 1)
        content_left = r.x + int(0.008 * _SW)
        content_right = self._locked_toggle_rect.left - int(0.010 * _SW)
        content_w = max(1, content_right - content_left)
        x = content_left + max(0, (content_w - total_w) // 2)
        y = r.centery
        for i, (label_surf, value_surf, width) in enumerate(rendered):
            self.window.blit(label_surf, label_surf.get_rect(left=x, centery=y))
            self.window.blit(value_surf, value_surf.get_rect(left=x + label_surf.get_width(), centery=y))
            x += width
            if i < len(rendered) - 1:
                sep_x = x + sep_w // 2
                pygame.draw.line(self.window, (120, 105, 78, 160),
                                 (sep_x, r.y + int(0.010 * _SH)),
                                 (sep_x, r.bottom - int(0.010 * _SH)), 1)
                x += sep_w
        self._draw_locked_visibility_toggle()

    def _draw_collection_load_state(self):
        """Draw an honest loading or retry state instead of a false 0/52 grid."""
        if self._load_error:
            title = self._section_font.render(
                'Your cards could not be loaded', True, (235, 210, 175))
            detail = self._stats_font.render(
                'Check your connection and try again.', True,
                settings.COLLECTION_PACK_PANEL_MUTED_CLR)
            group_h = title.get_height() + detail.get_height() + int(0.018 * _SH)
            top = self._panel_rect.centery - group_h // 2 - int(0.045 * _SH)
            self.window.blit(title, title.get_rect(
                centerx=self._panel_rect.centerx, top=top))
            self.window.blit(detail, detail.get_rect(
                centerx=self._panel_rect.centerx,
                top=top + title.get_height() + int(0.010 * _SH)))
            self._draw_action_button(
                self._retry_rect, 'Retry', True, primary=True)
            return

        # Soft animated skeletons retain the gallery shape without claiming
        # that the player owns zero cards while the request is in flight.
        now = pygame.time.get_ticks()
        pulse = 24 + int(16 * (0.5 + 0.5 * math.sin(now / 260.0)))
        cw, ch = settings.COLLECTION_CARD_W, settings.COLLECTION_CARD_H
        gap = max(settings.COLLECTION_CARD_GAP_X, int(0.012 * _SW))
        cols = 8
        total_w = cols * cw + (cols - 1) * gap
        start_x = self._panel_rect.centerx - total_w // 2
        start_y = self._panel_rect.centery - ch - int(0.015 * _SH)
        for row in range(2):
            for col in range(cols):
                rect = pygame.Rect(
                    start_x + col * (cw + gap),
                    start_y + row * (ch + settings.COLLECTION_CARD_GAP_Y),
                    cw, ch,
                )
                skel = pygame.Surface(rect.size, pygame.SRCALPHA)
                pygame.draw.rect(skel, (170, 158, 130, pulse), skel.get_rect(),
                                 border_radius=4)
                pygame.draw.rect(skel, (205, 190, 150, pulse + 20),
                                 skel.get_rect(), 1, border_radius=4)
                self.window.blit(skel, rect.topleft)
        msg = self._stats_font.render(
            'Loading cards...', True, settings.COLLECTION_PACK_PANEL_MUTED_CLR)
        self.window.blit(msg, msg.get_rect(
            centerx=self._panel_rect.centerx,
            top=start_y + 2 * (ch + settings.COLLECTION_CARD_GAP_Y)
                + int(0.008 * _SH)))

    def _draw_pack_panel(self, pack_type):
        """Draw one grouped booster pack control panel."""
        panel = self._pack_panel_rects[pack_type]
        info = settings.COLLECTION_PACK_PREVIEWS[pack_type]
        count = self._boosters if pack_type == 'main' else self._boosters_side
        price = settings.BOOSTER_PACK_PRICE if pack_type == 'main' else settings.BOOSTER_PACK_SIDE_PRICE
        can_buy = self._gold >= price

        surf = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.COLLECTION_PACK_PANEL_BG_CLR, surf.get_rect(), border_radius=10)
        pygame.draw.rect(surf, settings.COLLECTION_PACK_PANEL_BORDER_CLR, surf.get_rect(), 1, border_radius=10)
        self.window.blit(surf, panel.topleft)

        pad_x = settings.COLLECTION_PACK_PANEL_PAD_X
        pad_y = settings.COLLECTION_PACK_PANEL_PAD_Y
        icon = self._booster_icon if pack_type == 'main' else self._booster_side_icon
        icon_sz = min(icon.get_width(), int(panel.h * 0.32))
        icon_img = pygame.transform.smoothscale(icon, (icon_sz, icon_sz))
        icon_x = panel.x + pad_x
        icon_y = panel.y + pad_y
        self.window.blit(icon_img, (icon_x, icon_y))

        title_x = icon_x + icon_sz + int(0.008 * _SW)
        title_y = panel.y + pad_y - int(0.001 * _SH)
        title = self._pack_title_font.render(
            info['title'], True, settings.COLLECTION_PACK_PANEL_TITLE_CLR)
        self.window.blit(title, (title_x, title_y))

        if settings.TOUCH_TARGET_MIN > 0:
            gap = max(4, int(0.006 * _SW))
            max_row_w = panel.right - pad_x - title_x
            owned_text = f'×{count}'
            count_surf = self._pack_detail_font.render(
                owned_text, True, settings.COLLECTION_PACK_PANEL_TEXT_CLR)
            if title.get_width() + gap + count_surf.get_width() <= max_row_w:
                self.window.blit(
                    count_surf,
                    count_surf.get_rect(
                        left=title_x + title.get_width() + gap,
                        centery=title_y + title.get_height() // 2,
                    ),
                )
        else:
            count_text = self._pack_detail_font.render(
                f'{count} pack{"s" if count != 1 else ""} ready', True,
                settings.COLLECTION_PACK_PANEL_TEXT_CLR)
            self.window.blit(
                count_text,
                (title_x, title_y + title.get_height() + int(0.004 * _SH)),
            )

        btns = self._pack_button_rects[pack_type]
        self._draw_action_button(
            btns['open'], 'Open pack', count > 0 and self._data_loaded,
            primary=True)
        self._draw_action_button(btns['buy'], f'Buy · {price}g', can_buy)

    def _draw_card_grid(self):
        """Draw all cards in both sections with section headers."""
        positions = self._compute_card_positions()
        cw = settings.COLLECTION_CARD_W
        ch = settings.COLLECTION_CARD_H
        px = self._panel_rect.x + settings.COLLECTION_PANEL_PAD_X

        # Section headers (x, y, text)
        for header_x, header_y, header_text in self._section_headers:
            if self._panel_rect.y <= header_y <= self._panel_rect.bottom:
                header_surf = self._section_font.render(header_text, True, (250, 221, 0))
                self.window.blit(header_surf, (header_x, header_y))

        # Cards
        mouse_pos = pygame.mouse.get_pos()
        if not positions:
            self._draw_empty_grid_message()
            return
        for (cx, cy, suit, rank, section) in positions:
            # Skip if outside visible panel
            if cy + ch < self._panel_rect.y or cy > self._panel_rect.bottom:
                continue

            card = self._card_imgs.get((suit, rank))
            if not card:
                continue
            qty = self._cards.get((suit, rank), 0)
            locked = self._locked.get((suit, rank), 0)
            display_state = _collection_card_display_state(
                self._cards, self._locked, suit, rank,
                getattr(self, '_show_locked_cards', False))
            card_rect = pygame.Rect(cx, cy, cw, ch)
            gain_progress = self._recent_gain_progress((suit, rank))
            hovered = (
                card_rect.collidepoint(mouse_pos)
                and not self._sell_dialogue
                and not self._trade_dialogue
                and not self._profile_dialogue
                and not self._craft_dialogue
                and not self._reveal_overlay
            )

            is_mk = (rank == settings.RANK_MAHARAJA)

            if display_state == 'owned':
                if is_mk:
                    self._draw_maharaja_glow(card_rect)  # warm gold halo behind
                card.draw_front_bright(cx, cy)
                if is_mk:
                    self._draw_maharaja_border(card_rect, owned=True)
                else:
                    self._draw_tier_border(cx, cy, cw, ch, rank, section, owned=True)
                if hovered:
                    glow_surf = pygame.Surface((cw + 4, ch + 4), pygame.SRCALPHA)
                    pygame.draw.rect(glow_surf, (250, 221, 0, 80), glow_surf.get_rect(), 2)
                    self.window.blit(glow_surf, (cx - 2, cy - 2))
                self._draw_card_badge(
                    cx, cy, cw, qty, locked,
                    show_locked=getattr(self, '_show_locked_cards', False),
                )
            else:
                if is_mk:
                    self._draw_maharaja_glow(card_rect, dim=True)
                card.draw_front_bright(cx, cy)
                self.window.blit(self._grey_overlay, (cx, cy))
                if is_mk:
                    # Gold frame hint on the missing slot so players discover
                    # that the Maharaja is craftable.
                    self._draw_maharaja_border(card_rect, owned=False)
                else:
                    self._draw_tier_border(cx, cy, cw, ch, rank, section, owned=False)
                if display_state == 'locked_placeholder':
                    self._draw_locked_card_placeholder(card_rect)
            if gain_progress is not None:
                self._draw_recent_gain_highlight(
                    card_rect, self._recent_card_gains.get((suit, rank), 1),
                    gain_progress)

    def _draw_locked_card_placeholder(self, card_rect):
        """Mark a filtered fully locked card without displaying its stock."""
        icon = getattr(self, '_lock_placeholder_icon', None)
        if icon is None:
            return
        pad = max(3, int(0.004 * _SW))
        pill = pygame.Surface(
            (icon.get_width() + pad * 2, icon.get_height() + pad * 2),
            pygame.SRCALPHA)
        pygame.draw.rect(pill, (30, 27, 24, 205), pill.get_rect(),
                         border_radius=max(4, pill.get_height() // 3))
        pygame.draw.rect(pill, (170, 138, 78, 205), pill.get_rect(), 1,
                         border_radius=max(4, pill.get_height() // 3))
        pill.blit(icon, (pad, pad))
        self.window.blit(pill, pill.get_rect(center=card_rect.center))

    def _recent_gain_progress(self, key):
        started = getattr(self, '_recent_gains_started_at', None)
        if started is None or key not in getattr(self, '_recent_card_gains', {}):
            return None
        duration = max(1, settings.COLLECTION_RECENT_GAIN_HIGHLIGHT_MS)
        elapsed = pygame.time.get_ticks() - started
        if elapsed < 0 or elapsed >= duration:
            return None
        return elapsed / duration

    def _draw_recent_gain_highlight(self, card_rect, gained, progress):
        """Link a completed booster reveal back to the updated grid card."""
        pulse = 0.55 + 0.45 * math.sin(progress * math.pi * 5.0) ** 2
        fade = max(0.0, 1.0 - progress)
        alpha = int(205 * pulse * fade)
        halo_rect = card_rect.inflate(12, 12)
        halo = pygame.Surface(halo_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(halo, (250, 221, 0, max(35, alpha // 4)),
                         halo.get_rect(), border_radius=7)
        pygame.draw.rect(halo, (255, 234, 92, alpha),
                         halo.get_rect().inflate(-2, -2), 2, border_radius=6)
        self.window.blit(halo, halo_rect.topleft)

        label = self._badge_font.render(
            f'+{gained}', True, (35, 28, 10))
        pad = max(2, settings.COLLECTION_BADGE_PAD_X)
        pill = pygame.Surface((label.get_width() + pad * 2,
                               label.get_height() + 2), pygame.SRCALPHA)
        pygame.draw.rect(pill, (250, 221, 0, min(245, alpha + 40)),
                         pill.get_rect(), border_radius=4)
        self.window.blit(pill, (card_rect.x + 2, card_rect.y + 2))
        self.window.blit(label, (card_rect.x + 2 + pad, card_rect.y + 3))

    def _draw_empty_grid_message(self):
        """Draw a small status message when the active filter has no cards."""
        if not getattr(self, '_data_loaded', False):
            text = 'Loading collection...'
        elif getattr(self, '_show_locked_cards', False):
            text = 'No owned cards yet'
        else:
            text = 'No free cards to show'
        msg = self._stats_font.render(text, True, settings.COLLECTION_PACK_PANEL_MUTED_CLR)
        self.window.blit(msg, msg.get_rect(center=self._panel_rect.center))

    def _draw_tier_border(self, cx, cy, cw, ch, rank, section, owned=True):
        """Draw a subtle tier-coloured outline just outside the card edge."""
        tier = _card_tier(rank, section)
        clr = settings.COLLECTION_TIER_BORDER_COLORS.get(tier)
        if not clr:
            return
        if not owned:
            r, g, b, a = clr
            clr = (r, g, b, max(0, a // 2))
        thickness = 2 if tier >= 2 else 1
        surf = pygame.Surface((cw + 4, ch + 4), pygame.SRCALPHA)
        pygame.draw.rect(surf, clr, surf.get_rect(), thickness, border_radius=4)
        self.window.blit(surf, (cx - 2, cy - 2))

    def _draw_maharaja_glow(self, card_rect, dim=False):
        """Feathered royal-gold halo behind a Maharaja cell, gently pulsing."""
        now = pygame.time.get_ticks()
        pulse = 0.5 + 0.5 * math.sin(now / 480.0)
        peak = (28 if dim else 66) + int((16 if dim else 44) * pulse)
        color = settings.COLLECTION_MAHARAJA_GLOW_CLR
        halo_rect = card_rect.inflate(int(card_rect.w * 0.42),
                                      int(card_rect.h * 0.28))
        halo = pygame.Surface(halo_rect.size, pygame.SRCALPHA)
        layers = 6
        for step in range(layers, 0, -1):
            t = step / layers  # 1.0 outer → ~0 inner
            inset_x = int(halo_rect.w * 0.5 * (1.0 - t))
            inset_y = int(halo_rect.h * 0.5 * (1.0 - t))
            ring = pygame.Rect(inset_x, inset_y,
                               halo_rect.w - inset_x * 2,
                               halo_rect.h - inset_y * 2)
            if ring.w <= 0 or ring.h <= 0:
                continue
            layer_alpha = max(0, int(peak * (1.0 - t) ** 2))
            if layer_alpha == 0:
                continue
            pygame.draw.ellipse(halo, (*color, layer_alpha), ring)
        self.window.blit(halo, halo_rect.topleft)

    def _draw_maharaja_border(self, card_rect, owned=True):
        """Gold frame around a Maharaja cell; pulses brighter when owned."""
        now = pygame.time.get_ticks()
        pulse = 0.5 + 0.5 * math.sin(now / 480.0)
        r, g, b = settings.COLLECTION_MAHARAJA_BORDER_CLR
        if owned:
            alpha = int(200 + 55 * pulse)
            thickness = 2
        else:
            alpha = 150
            thickness = 1
        surf = pygame.Surface((card_rect.w + 4, card_rect.h + 4), pygame.SRCALPHA)
        pygame.draw.rect(surf, (r, g, b, alpha), surf.get_rect(),
                         thickness, border_radius=4)
        self.window.blit(surf, (card_rect.x - 2, card_rect.y - 2))

    def _draw_card_badge(self, cx, cy, cw, qty, locked=0, show_locked=True):
        """Draw separate free-stock and in-use badges without slash ambiguity."""
        free = max(0, qty - locked)
        badge_text = str(free)
        bg_clr = ((88, 80, 66, 220) if free == 0
                  else settings.COLLECTION_BADGE_BG_CLR)
        badge_surf = self._badge_font.render(badge_text, True, settings.COLLECTION_BADGE_CLR)
        bw = badge_surf.get_width() + settings.COLLECTION_BADGE_PAD_X * 2
        bh = badge_surf.get_height() + settings.COLLECTION_BADGE_PAD_Y * 2
        bx = cx + cw - bw - 2
        by = cy + settings.COLLECTION_CARD_H - bh - 2
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        bg.fill(bg_clr)
        self.window.blit(bg, (bx, by))
        self.window.blit(badge_surf,
                         (bx + settings.COLLECTION_BADGE_PAD_X,
                          by + settings.COLLECTION_BADGE_PAD_Y))

        if show_locked and locked > 0:
            lock_icon = getattr(self, '_lock_badge_icon', None)
            lock_text = self._badge_font.render(
                str(locked), True, settings.COLLECTION_LOCK_BADGE_CLR)
            icon_w = lock_icon.get_width() if lock_icon else 0
            icon_gap = 1 if icon_w else 0
            lw = (lock_text.get_width() + icon_w + icon_gap
                  + settings.COLLECTION_BADGE_PAD_X * 2)
            lh = max(lock_text.get_height(), icon_w) + settings.COLLECTION_BADGE_PAD_Y * 2
            lock_bg = pygame.Surface((lw, lh), pygame.SRCALPHA)
            lock_bg.fill(settings.COLLECTION_LOCK_BADGE_BG_CLR)
            lx = cx + 2
            ly = cy + settings.COLLECTION_CARD_H - lh - 2
            self.window.blit(lock_bg, (lx, ly))
            text_x = lx + settings.COLLECTION_BADGE_PAD_X
            if lock_icon:
                self.window.blit(lock_icon, (
                    text_x,
                    ly + (lh - lock_icon.get_height()) // 2,
                ))
                text_x += icon_w + icon_gap
            self.window.blit(lock_text, (
                text_x,
                ly + (lh - lock_text.get_height()) // 2,
            ))

    def _draw_action_button(self, rect, text, enabled, primary=False):
        """Draw one of the bottom action buttons."""
        mouse_pos = pygame.mouse.get_pos()
        hovered = (
            rect.collidepoint(mouse_pos)
            and not self.dialogue_box
            and not self._sell_dialogue
            and not self._trade_dialogue
            and not self._profile_dialogue
            and not self._craft_dialogue
            and not self._reveal_overlay
        )
        from game.core.input_state import get_pressed as _get_pressed
        clicked = hovered and _get_pressed()[0]

        if enabled and hovered:
            glow = self._action_glows['yellow'] if clicked else self._action_glows['white']
            gx = rect.centerx - glow.get_width() // 2
            gy = rect.centery - glow.get_height() // 2
            self.window.blit(glow, (gx, gy))

        # Button background
        if not enabled:
            bg_clr = (40, 40, 40, 180)
            txt_clr = (100, 100, 100)
        elif clicked:
            bg_clr = (102, 78, 28, 235) if primary else (80, 70, 40, 220)
            txt_clr = (255, 255, 220)
        elif hovered:
            bg_clr = (88, 69, 28, 235) if primary else (60, 55, 35, 220)
            txt_clr = (250, 240, 200)
        else:
            bg_clr = (72, 55, 23, 230) if primary else (35, 35, 40, 200)
            txt_clr = (255, 238, 180) if primary else (200, 190, 160)

        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill(bg_clr)
        border = ((218, 180, 82, 225) if primary and enabled
                  else (120, 110, 90, 200))
        pygame.draw.rect(surf, border, surf.get_rect(), 2 if primary and enabled else 1)
        self.window.blit(surf, rect.topleft)

        txt = self._action_font.render(text, True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_profile_tooltip(self, text, anchor=None):
        """Draw a hover or tap-pinned description for a profile use tile."""
        font = settings.get_font(settings.TOOLTIP_FONT_SIZE)
        pad_x = settings.TOOLTIP_PAD_X
        pad_y = settings.TOOLTIP_PAD_Y
        corner_r = settings.TOOLTIP_CORNER_R
        # Maximum tooltip width: 35% of screen width (capped to avoid overshooting)
        max_content_w = int(0.35 * _SW)
        # Word-wrap each paragraph separately
        raw_lines = text.split('\n')
        wrapped = []
        for para in raw_lines:
            if not para.strip():
                wrapped.append('')
                continue
            words = para.split()
            current = []
            for word in words:
                test = ' '.join(current + [word])
                if font.size(test)[0] <= max_content_w:
                    current.append(word)
                else:
                    if current:
                        wrapped.append(' '.join(current))
                    current = [word]
            if current:
                wrapped.append(' '.join(current))
        line_surfs = [font.render(l, True, settings.TOOLTIP_TEXT_COLOR)
                      for l in wrapped if l]
        if not line_surfs:
            return
        line_h = font.get_height()
        content_w = max(s.get_width() for s in line_surfs)
        pill_w = pad_x * 2 + content_w
        pill_h = pad_y * 2 + len(line_surfs) * line_h + max(0, len(line_surfs) - 1) * 2
        mx, my = anchor or pygame.mouse.get_pos()
        pill_x = mx + 14
        pill_y = my - pill_h // 2
        pill_x = max(4, min(pill_x, _SW - pill_w - 4))
        pill_y = max(4, min(pill_y, _SH - pill_h - 4))
        pill = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pygame.draw.rect(pill, settings.TOOLTIP_BG_COLOR,
                         (0, 0, pill_w, pill_h), border_radius=corner_r)
        pygame.draw.rect(pill, settings.TOOLTIP_BORDER_COLOR,
                         (0, 0, pill_w, pill_h),
                         settings.TOOLTIP_BORDER_WIDTH, border_radius=corner_r)
        self.window.blit(pill, (pill_x, pill_y))
        y = pill_y + pad_y
        for surf in line_surfs:
            self.window.blit(surf, (pill_x + pad_x, y))
            y += line_h + 2

    def _draw_close_x_button(self):
        """Draw a small X close button in the top-right corner of the box."""
        r = self._btn_close_rect
        mouse_pos = pygame.mouse.get_pos()
        hovered = (
            r.collidepoint(mouse_pos)
            and not self.dialogue_box
            and not self._sell_dialogue
            and not self._trade_dialogue
            and not self._profile_dialogue
            and not self._craft_dialogue
            and not self._reveal_overlay
        )

        bg_clr = (80, 50, 25, 220) if hovered else (55, 35, 18, 200)
        border_clr = (180, 160, 120) if hovered else (120, 100, 70)
        txt_clr = (255, 240, 200) if hovered else (200, 180, 140)

        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg_clr, surf.get_rect(), border_radius=4)
        pygame.draw.rect(surf, border_clr, surf.get_rect(), 1, border_radius=4)
        self.window.blit(surf, r.topleft)

        txt = self._close_font.render('\u00d7', True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=r.center))

    # ── actions panel (mode toggles) ────────────────────────────────

    def _draw_actions_panel(self):
        """Make the safe default inspect interaction visible everywhere."""
        panel = self._actions_panel_rect
        surf = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.COLLECTION_PACK_PANEL_BG_CLR,
                         surf.get_rect(), border_radius=10)
        pygame.draw.rect(surf, settings.COLLECTION_PACK_PANEL_BORDER_CLR,
                         surf.get_rect(), 1, border_radius=10)
        self.window.blit(surf, panel.topleft)

        pad_x = settings.COLLECTION_PACK_PANEL_PAD_X
        pad_y = settings.COLLECTION_PACK_PANEL_PAD_Y
        title = self._pack_title_font.render(
            settings.COLLECTION_ACTIONS_PANEL_TITLE, True,
            settings.COLLECTION_PACK_PANEL_TITLE_CLR)
        self.window.blit(title, (panel.x + pad_x, panel.y + pad_y))

        hint = self._pack_detail_font.render(
            settings.COLLECTION_ACTIONS_PANEL_HINT, True,
            settings.COLLECTION_PACK_PANEL_TEXT_CLR)
        self.window.blit(
            hint,
            (panel.x + pad_x,
             panel.y + pad_y + title.get_height() + int(0.004 * _SH)),
        )
        if settings.TOUCH_TARGET_MIN <= 0:
            detail = self._pack_detail_font.render(
                'Uses, copy stock, sell and conversion', True,
                settings.COLLECTION_PACK_PANEL_MUTED_CLR)
            self.window.blit(
                detail,
                (panel.x + pad_x,
                 panel.y + pad_y + title.get_height()
                 + self._pack_detail_font.get_height() + int(0.006 * _SH)),
            )

    def _draw_locked_visibility_toggle(self):
        """Draw the show-locked-cards toggle in the collection stats strip."""
        rect = self._locked_toggle_rect
        active = bool(getattr(self, '_show_locked_cards', False))
        mouse_pos = pygame.mouse.get_pos()
        hovered = (
            rect.collidepoint(mouse_pos)
            and not self.dialogue_box
            and not self._sell_dialogue
            and not self._trade_dialogue
            and not self._profile_dialogue
            and not self._craft_dialogue
            and not self._reveal_overlay
        )

        if active:
            bg_clr = (72, 60, 28, 228)
            border_clr = (250, 221, 0)
            txt_clr = (255, 245, 200)
        elif hovered:
            bg_clr = (52, 48, 36, 218)
            border_clr = (190, 165, 105)
            txt_clr = (236, 224, 190)
        else:
            bg_clr = (35, 35, 40, 190)
            border_clr = (120, 110, 90, 190)
            txt_clr = settings.COLLECTION_PACK_PANEL_TEXT_CLR

        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg_clr, surf.get_rect(), border_radius=6)
        pygame.draw.rect(surf, border_clr, surf.get_rect(),
                         2 if active else 1, border_radius=6)
        self.window.blit(surf, rect.topleft)

        box_sz = max(10, min(rect.h - 8, int(0.018 * _SH)))
        box = pygame.Rect(rect.x + 6, rect.centery - box_sz // 2, box_sz, box_sz)
        pygame.draw.rect(self.window, (24, 24, 28), box, border_radius=3)
        pygame.draw.rect(self.window, border_clr, box, 1, border_radius=3)
        if active:
            p1 = (box.x + max(2, box_sz // 5), box.centery)
            p2 = (box.x + box_sz // 2, box.bottom - max(3, box_sz // 5))
            p3 = (box.right - max(2, box_sz // 6), box.y + max(3, box_sz // 5))
            pygame.draw.lines(self.window, txt_clr, False, [p1, p2, p3], 2)

        label = self._pack_detail_font.render('Show locked', True, txt_clr)
        label_x = box.right + 5
        self.window.blit(label, label.get_rect(
            left=label_x,
            centery=rect.centery,
        ))

    # ── card profile dialogue (default click) ──────────────────────

    def _open_profile_dialogue(self, suit, rank):
        """Show a profile dialogue with all uses of (suit, rank)."""
        # Maharaja cards are crafted, never sold or traded — every click on an
        # MK cell routes to the dedicated craft dialogue instead.
        if rank == settings.RANK_MAHARAJA:
            self._open_craft_dialogue(suit)
            return

        from utils.card_uses import get_card_uses

        qty = self._cards.get((suit, rank), 0)
        locked = self._locked.get((suit, rank), 0)
        free = max(0, qty - locked)
        unit_price = _sell_price(rank, 1)
        section = _card_pack_type(rank)
        tier_label = _tier_label(rank, section)

        # Card category shown beside the pack family in the profile overview.
        # Side cards are further split into side-key (2,4,5) and side-number (3,6)
        # based on which figure slot they typically fill.
        _SIDE_KEY_RANKS = {'2', '4', '5'}
        _SIDE_NUM_RANKS = {'3', '6'}
        if rank in settings.NUMBER_CARDS:
            category_label = 'Number Card'
        elif rank in _SIDE_KEY_RANKS:
            category_label = 'Side Key Card'
        elif rank in _SIDE_NUM_RANKS:
            category_label = 'Side Number Card'
        else:
            category_label = 'Key Card'

        try:
            uses = get_card_uses(suit, rank)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f'Card uses lookup failed: {e}')
            uses = {'figures': [], 'spells': [], 'battle_moves': []}

        max_items = settings.COLLECTION_PROFILE_GROUP_MAX_ITEMS

        def _group(title, entries, note='', icon=None):
            """Build a raw image-group dict for the profile dialogue."""
            # entries are (name, icon, description) triples
            pairs = [(name, icon, desc)
                     for name, icon, desc in entries[:max_items]
                     if icon is not None]
            icons = [icon for _n, icon, _d in pairs]
            tooltips = [f'{name}\n{desc}' if desc else name
                        for name, _icon, desc in pairs]
            return {
                'title': title,
                'items': icons,
                'item_tooltips': tooltips,
                'item_unit': 'option',
                'count': len(entries),
                'show_when_empty': True,
                'icon': icon,
                'badge_icon': None,
                'description': note or (
                    ', '.join(name for name, _, _ in entries[:max_items])
                    if entries else 'No uses'
                ),
            }

        groups = [
            _group('Figures', uses['figures'],
                   note=', '.join(n for n, _, _ in uses['figures'][:max_items])
                        if uses['figures'] else 'No figure recipes',
                   icon='figure'),
            _group('Spells', uses['spells'], icon='magic'),
            _group('Tactics', uses['battle_moves'], icon='dices'),
        ]

        card_img = self._card_imgs.get((suit, rank))
        if qty > 0:
            msg = (f'{tier_label} {section.title()} Card  ·  {category_label}\n'
                   f'{qty} owned  ·  {free} free  ·  {locked} in use  ·  '
                   f'{unit_price}g each')
        else:
            msg = (f'{tier_label} {section.title()} Card  ·  {category_label}\n'
                   'Not currently owned')
        self._profile_card = (suit, rank)
        self._profile_pinned_tooltip = None
        self._profile_pinned_tooltip_pos = None
        self._profile_dialogue = DialogueBox(
            self.window, msg, actions=['Sell copies', 'Convert', 'Close'],
            images=[card_img.front_img] if card_img else [],
            image_groups=groups,
            title=f'{suit} {rank}',
        )
        for button in self._profile_dialogue.buttons:
            action = button.text.lower()
            if action == 'sell copies':
                button.disabled = free <= 0
            elif action == 'convert':
                button.disabled = free < settings.COLLECTION_CONVERT_RATIO_SAME_COLOR

    # ── trade dialogue ──────────────────────────────────────────────

    def _open_trade_dialogue(self, suit, rank):
        """Open the convert/trade dialogue for a card."""
        qty = self._cards.get((suit, rank), 0)
        locked = self._locked.get((suit, rank), 0)
        free = max(0, qty - locked)
        if free < settings.COLLECTION_CONVERT_RATIO_SAME_COLOR:
            self._trade_card = None
            self._trade_target_suit = None
            self._trade_dialogue = DialogueBox(
                self.window,
                (f'You need at least '
                 f'{settings.COLLECTION_CONVERT_RATIO_SAME_COLOR} free copies '
                 f'of {suit} {rank} to convert.\n'
                 f'Owned: {qty}  ·  Free: {free}  ·  Locked: {locked}'),
                actions=['ok'], title='Cannot trade',
            )
            return
        # Default target: first other suit (preferring same-colour for cheapest ratio)
        same_colour = self._other_suits_same_colour(suit)
        diff_colour = self._other_suits_diff_colour(suit)
        default_target = same_colour[0] if same_colour else diff_colour[0]

        self._trade_card = (suit, rank)
        self._trade_target_suit = default_target
        self._trade_qty = 1
        self._trade_max = self._compute_trade_max(suit, rank, default_target)
        self._trade_qty_rects = {}
        self._trade_target_rects = {}

        card_img = self._card_imgs.get((suit, rank))
        msg = (f'Convert {suit} {rank}\n'
               f'Owned: {qty}  ·  Free: {free}  ·  Locked: {locked}\n'
               f'Same colour: {settings.COLLECTION_CONVERT_RATIO_SAME_COLOR}:1  ·  '
               f'Different colour: {settings.COLLECTION_CONVERT_RATIO_DIFF_COLOR}:1')
        after_msg = self._trade_after_text()
        self._trade_dialogue = DialogueBox(
            self.window, msg, actions=['trade', 'cancel'],
            images=[card_img] if card_img else [],
            title='Trade Card',
            message_after_images=after_msg)

    def _other_suits_same_colour(self, suit):
        if suit in settings.COLLECTION_RED_SUITS:
            return [s for s in settings.COLLECTION_RED_SUITS if s != suit]
        return [s for s in settings.COLLECTION_BLACK_SUITS if s != suit]

    def _other_suits_diff_colour(self, suit):
        if suit in settings.COLLECTION_RED_SUITS:
            return list(settings.COLLECTION_BLACK_SUITS)
        return list(settings.COLLECTION_RED_SUITS)

    def _convert_ratio_for(self, source_suit, target_suit):
        if source_suit == target_suit:
            return None
        same_red = (source_suit in settings.COLLECTION_RED_SUITS
                    and target_suit in settings.COLLECTION_RED_SUITS)
        same_black = (source_suit in settings.COLLECTION_BLACK_SUITS
                      and target_suit in settings.COLLECTION_BLACK_SUITS)
        if same_red or same_black:
            return settings.COLLECTION_CONVERT_RATIO_SAME_COLOR
        return settings.COLLECTION_CONVERT_RATIO_DIFF_COLOR

    def _compute_trade_max(self, suit, rank, target_suit):
        qty = self._cards.get((suit, rank), 0)
        locked = self._locked.get((suit, rank), 0)
        free = max(0, qty - locked)
        ratio = self._convert_ratio_for(suit, target_suit)
        if not ratio:
            return 0
        return free // ratio

    def _trade_after_text(self):
        if not self._trade_card or not self._trade_target_suit:
            return ''
        suit, rank = self._trade_card
        target = self._trade_target_suit
        ratio = self._convert_ratio_for(suit, target) or 0
        consumed = ratio * self._trade_qty
        # Reserve vertical space for the two control rows (target + qty) and
        # their labels with trailing blank lines so the overlay never
        # collides with the visible after-text.
        return (f'Target: {target} {rank}  ·  Ratio: {ratio}:1\n'
                f'Producing {self._trade_qty} {target} card(s)  ·  '
                f'Consuming {consumed} {suit} card(s).\n'
                + '\n' * 7)

    def _update_trade_after_text(self):
        if not self._trade_dialogue:
            return
        new_text = self._trade_after_text()
        _max_text_w = settings.DIALOGUE_BOX_WIDTH - int(0.08 * _SW)
        self._trade_dialogue.after_lines = DialogueBox._wrap_text(
            new_text, self._trade_dialogue.font, _max_text_w)
        self._trade_dialogue.after_lines_surfaces = [
            self._trade_dialogue.font.render(
                l, True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            for l in self._trade_dialogue.after_lines]

    def _layout_trade_target_rects(self):
        """Lay out the 3 target-suit selector buttons centred above qty controls."""
        if not self._trade_card or not self._trade_dialogue:
            return {}
        dlg = self._trade_dialogue
        suit, _rank = self._trade_card
        targets = [s for s in settings.SUITS if s != suit]
        btn_w = settings.COLLECTION_TRADE_TARGET_BTN_W
        btn_h = settings.COLLECTION_TRADE_TARGET_BTN_H
        gap = settings.COLLECTION_TRADE_TARGET_GAP
        total_w = btn_w * len(targets) + gap * (len(targets) - 1)
        x = dlg.rect.centerx - total_w // 2
        # Stack target row above qty row with enough gap to fit the 'Output
        # Qty' label between them.
        qty_btn_h = settings.COLLECTION_SELL_QTY_BTN_H
        # Target row sits qty_btn_h + qty-label gap (~0.022*SH) + intra-row
        # gap (~0.012*SH) + target_btn_h + bottom margin (~0.010*SH) above
        # the dialog's action-button area.
        y = (dlg.rect.bottom - dlg.button_height - qty_btn_h
             - int(0.034 * _SH) - btn_h)
        rects = {}
        for i, t in enumerate(targets):
            rects[t] = pygame.Rect(x + i * (btn_w + gap), y, btn_w, btn_h)
        return rects

    def _layout_trade_qty_rects(self):
        if not self._trade_dialogue:
            return {}
        dlg = self._trade_dialogue
        btn_w = settings.COLLECTION_SELL_QTY_BTN_W
        btn_h = settings.COLLECTION_SELL_QTY_BTN_H
        max_w = settings.COLLECTION_SELL_QTY_MAX_W
        gap = settings.COLLECTION_SELL_QTY_GAP
        qty_w = int(btn_w * 1.28)
        total_w = btn_w + gap + qty_w + gap + btn_w + gap + max_w
        x = dlg.rect.centerx - total_w // 2
        y = dlg.rect.bottom - dlg.button_height - btn_h - int(0.010 * _SH)
        return {
            'minus': pygame.Rect(x, y, btn_w, btn_h),
            'qty': pygame.Rect(x + btn_w + gap, y, qty_w, btn_h),
            'plus': pygame.Rect(x + btn_w + gap + qty_w + gap, y, btn_w, btn_h),
            'max': pygame.Rect(x + btn_w + gap + qty_w + gap + btn_w + gap, y, max_w, btn_h),
        }

    def _draw_trade_overlay(self):
        if not self._trade_card or not self._trade_dialogue:
            return
        dlg = self._trade_dialogue
        s_suit, s_rank = self._trade_card

        # Target suit selector
        target_rects = self._layout_trade_target_rects()
        self._trade_target_rects = target_rects
        if target_rects:
            label = self._stats_font.render(
                'Target Suit', True, settings.COLLECTION_STATS_TEXT_CLR)
            first = next(iter(target_rects.values()))
            self.window.blit(label, label.get_rect(
                center=(dlg.rect.centerx, first.top - int(0.012 * _SH))))
            for suit, rect in target_rects.items():
                ratio = self._convert_ratio_for(s_suit, suit) or 0
                affordable = self._compute_trade_max(s_suit, s_rank, suit) >= 1
                self._draw_trade_target_button(
                    rect, suit, ratio,
                    selected=(suit == self._trade_target_suit),
                    enabled=affordable)

        # Qty selector
        qty_rects = self._layout_trade_qty_rects()
        self._trade_qty_rects = qty_rects
        qty_label = self._stats_font.render(
            'Output Qty', True, settings.COLLECTION_STATS_TEXT_CLR)
        self.window.blit(qty_label, qty_label.get_rect(
            center=(dlg.rect.centerx, qty_rects['qty'].top - int(0.012 * _SH))))
        self._draw_sell_control_button(qty_rects['minus'], '−', self._trade_qty > 1)
        self._draw_sell_control_button(qty_rects['plus'], '+',
                                       self._trade_qty < self._trade_max)
        self._draw_sell_control_button(qty_rects['max'], 'Max',
                                       self._trade_qty < self._trade_max)
        qty_surf = pygame.Surface((qty_rects['qty'].w, qty_rects['qty'].h),
                                  pygame.SRCALPHA)
        pygame.draw.rect(qty_surf, (25, 25, 30, 230),
                         qty_surf.get_rect(), border_radius=6)
        pygame.draw.rect(qty_surf, (180, 155, 95, 210),
                         qty_surf.get_rect(), 1, border_radius=6)
        self.window.blit(qty_surf, qty_rects['qty'].topleft)
        qty_text = self._sell_control_font.render(
            str(self._trade_qty), True, settings.COLLECTION_STATS_VALUE_CLR)
        self.window.blit(qty_text, qty_text.get_rect(center=qty_rects['qty'].center))

    def _draw_trade_target_button(self, rect, suit, ratio, selected, enabled=True):
        mouse_pos = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse_pos) and enabled
        is_red = suit in settings.COLLECTION_RED_SUITS
        accent = (settings.COLLECTION_TRADE_RED_CLR if is_red
                  else settings.COLLECTION_TRADE_BLACK_CLR)
        if not enabled:
            bg = (28, 28, 32, 180)
            border = (80, 75, 65, 160)
            txt_clr = (110, 105, 95)
        elif selected:
            bg = (75, 60, 25, 235)
            border = (250, 221, 0)
            txt_clr = (255, 245, 200)
        elif hovered:
            bg = (50, 45, 30, 220)
            border = accent
            txt_clr = accent
        else:
            bg = (32, 32, 38, 210)
            border = (110, 100, 80, 210)
            txt_clr = accent

        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=6)
        pygame.draw.rect(surf, border, surf.get_rect(),
                         2 if selected else 1, border_radius=6)
        self.window.blit(surf, rect.topleft)

        font = settings.get_font(settings.COLLECTION_TRADE_TARGET_FONT_SIZE, bold=True)
        line1 = font.render(suit, True, txt_clr)
        line2 = font.render(f'{ratio}:1', True, txt_clr)
        total_h = line1.get_height() + line2.get_height()
        ty = rect.centery - total_h // 2
        self.window.blit(line1, line1.get_rect(centerx=rect.centerx, top=ty))
        self.window.blit(line2, line2.get_rect(
            centerx=rect.centerx, top=ty + line1.get_height()))

    def _handle_trade_overlay_click(self, pos):
        """Return True if the click hit a trade-overlay control."""
        if not self._trade_card or not self._trade_dialogue:
            return False
        s_suit, s_rank = self._trade_card
        # Target buttons
        for suit, rect in (self._trade_target_rects or {}).items():
            if rect.collidepoint(pos):
                cap = self._compute_trade_max(s_suit, s_rank, suit)
                if cap < 1:
                    # Unaffordable target — surface a clear notification
                    # instead of silently selecting an invalid suit.
                    ratio = self._convert_ratio_for(s_suit, suit) or 0
                    free = max(0, self._cards.get((s_suit, s_rank), 0)
                                - self._locked.get((s_suit, s_rank), 0))
                    self.state.set_msg(
                        f'Need {ratio} free {s_suit} {s_rank} for one '
                        f'{suit} (have {free}).')
                    return True
                if suit != self._trade_target_suit:
                    self._trade_target_suit = suit
                    self._trade_max = cap
                    if self._trade_qty > self._trade_max:
                        self._trade_qty = max(1, self._trade_max)
                    self._update_trade_after_text()
                return True
        # Qty buttons
        rects = self._trade_qty_rects or self._layout_trade_qty_rects()
        changed = False
        if rects['minus'].collidepoint(pos) and self._trade_qty > 1:
            self._trade_qty -= 1
            changed = True
        elif rects['plus'].collidepoint(pos) and self._trade_qty < self._trade_max:
            self._trade_qty += 1
            changed = True
        elif rects['max'].collidepoint(pos) and self._trade_qty < self._trade_max:
            self._trade_qty = self._trade_max
            changed = True
        if changed:
            self._update_trade_after_text()
            return True
        return any(rect.collidepoint(pos) for rect in rects.values())

    def _perform_trade(self):
        """Execute the convert_card API call."""
        if not self._trade_card or not self._trade_target_suit:
            self._trade_dialogue = None
            self._trade_card = None
            return
        suit, rank = self._trade_card
        target = self._trade_target_suit
        ratio = self._convert_ratio_for(suit, target) or 0
        if self._trade_max < 1 or ratio < 1:
            self.state.set_msg('Not enough free cards to convert')
            self._trade_dialogue = None
            self._trade_card = None
            return
        try:
            result = collection_service.convert_card(
                suit, rank, target, self._trade_qty)
            consumed = result.get('consumed', ratio * self._trade_qty)
            produced = result.get('produced', self._trade_qty)
            old_src = self._cards.get((suit, rank), 0)
            old_tgt = self._cards.get((target, rank), 0)
            self._cards[(suit, rank)] = max(0, old_src - consumed)
            self._cards[(target, rank)] = old_tgt + produced
            from utils import sound
            sound.play('coin')
            self.state.set_msg(
                f'Converted {consumed} {suit} {rank} → {produced} {target} {rank}')
        except Exception as e:
            logger.error(f'Convert failed: {e}')
            self.state.set_msg('Failed to convert card')
        self._trade_card = None
        self._trade_target_suit = None
        self._trade_dialogue = None
        self._trade_qty_rects = {}
        self._trade_target_rects = {}

    # ── maharaja craft dialogue ─────────────────────────────────────

    def _open_craft_dialogue(self, suit):
        """Open the Maharaja craft dialogue for *suit* (never sell/trade)."""
        self._profile_dialogue = None
        self._profile_card = None
        self._profile_pinned_tooltip = None
        ready, total, missing = _maharaja_craft_progress(
            self._cards, self._locked, suit)
        card_img = self._card_imgs.get((suit, settings.RANK_MAHARAJA))
        self._craft_suit = suit
        msg = (f'Trade one free copy of every {suit} rank (2–A, {total} cards) '
               f'for a {suit} Maharaja.\n'
               'Only free (unlocked) copies count.')
        if ready >= total:
            after = f'Ready to craft!  {ready} / {total} ranks available.'
        else:
            after = (f'{ready} / {total} ranks ready.\n'
                     f'Still need a free copy of: {", ".join(missing)}')
        self._craft_dialogue = DialogueBox(
            self.window, msg, actions=['Craft', 'cancel'],
            images=[card_img] if card_img else [],
            title='Craft Maharaja',
            message_after_images=after)
        for button in self._craft_dialogue.buttons:
            if button.text.lower() == 'craft':
                button.disabled = ready < total

    def _perform_craft(self):
        """Execute the craft_maharaja API call and celebrate on success."""
        suit = self._craft_suit
        self._craft_dialogue = None
        self._craft_suit = None
        if not suit:
            return
        ready, total, _missing = _maharaja_craft_progress(
            self._cards, self._locked, suit)
        if ready < total:
            self.state.set_msg('Need one free copy of every rank to craft')
            return
        try:
            result = collection_service.craft_maharaja(suit)
        except Exception as e:
            logger.error(f'Craft maharaja failed: {e}')
            self.state.set_msg('Failed to craft Maharaja card')
            return
        if not result or not result.get('success'):
            self.state.set_msg(
                (result or {}).get('message') or 'Failed to craft Maharaja card')
            return
        self._apply_craft_result(suit, result)

    def _apply_craft_result(self, suit, result):
        """Apply a successful craft: update stock, celebrate with a reveal."""
        card = result.get('card') or {}
        # Optimistically reflect the trade locally; the follow-up fetch makes it
        # authoritative. One free copy of every rank is consumed.
        for rank in settings.MAHARAJA_CRAFT_RANKS:
            key = (suit, rank)
            self._cards[key] = max(0, int(self._cards.get(key, 0) or 0) - 1)
        mk_key = (suit, settings.RANK_MAHARAJA)
        self._cards[mk_key] = int(self._cards.get(mk_key, 0) or 0) + 1
        # Highlight the new MK cell once the reveal is dismissed.
        self._pending_reveal_gains = {mk_key: 1}
        # Celebratory single-card reveal through the booster overlay. tier=3
        # earns the biggest reveal celebration (rings + sparkles); the impact
        # annotations make the label/summary read as a brand-new card.
        reveal_card = {
            'suit': suit,
            'rank': settings.RANK_MAHARAJA,
            'value': int(card.get('value', settings.RANK_TO_VALUE.get(
                settings.RANK_MAHARAJA, 4))),
            'tier': 3,
            '_impact_new_type': self._cards[mk_key] == 1,
            '_impact_owned_before': self._cards[mk_key] - 1,
            '_impact_owned_after': self._cards[mk_key],
            '_impact_free_after': self._cards[mk_key],
        }
        from game.components.booster_reveal import BoosterRevealOverlay
        from utils import sound
        sound.play('conquer_win')  # big-deal fanfare for a 13-card craft
        self._reveal_overlay = BoosterRevealOverlay(
            self.window, [reveal_card], pack_type='main')
        self._spawn_maharaja_floater(suit)
        self.state.set_msg(f'Crafted the {suit} Maharaja!')
        # Refresh authoritative stock (consumed cards + new MK).
        self._fetch_collection()

    def _spawn_maharaja_floater(self, suit):
        """Spawn a rising gold 'Maharaja crafted!' celebration floater."""
        font = settings.get_font(settings.COLLECT_FLOAT_FONT_SIZE, bold=True)
        self._floating_text.add(FloatingText(
            f'{suit} Maharaja!',
            (_SW // 2, int(0.20 * _SH)),
            color=settings.COLLECT_FLOAT_GOLD_CLR,
            duration_ms=settings.COLLECT_FLOAT_DURATION_MS,
            rise_px=settings.COLLECT_FLOAT_RISE_PX,
            font=font,
        ))

    # ── sell dialogue ───────────────────────────────────────────────

    def _open_sell_dialogue(self, suit, rank):
        """Open the sell dialogue for a card."""
        qty = self._cards.get((suit, rank), 0)
        locked = self._locked.get((suit, rank), 0)
        free = max(0, qty - locked)
        if free <= 0:
            # All copies are locked — surface a clear reason instead of
            # silently doing nothing.
            self._sell_card = None
            self._sell_qty_rects = {}
            self._sell_dialogue = DialogueBox(
                self.window,
                f'All {qty} {suit} {rank} card(s) are currently locked '
                f'in a conquer/defence configuration.',
                actions=['ok'], title='Cannot sell',
            )
            return
        self._sell_card = (suit, rank)
        self._sell_qty = 1
        self._sell_max = free
        self._sell_qty_rects = {}
        unit_price = _sell_price(rank, 1)
        card_img = self._card_imgs.get((suit, rank))
        images = [card_img] if card_img else []
        msg = (f'Sell {suit} {rank}?\n'
               f'Owned: {qty}  ·  Free: {free}  ·  Locked: {locked}')
        after_msg = self._sell_after_text(unit_price, qty, free, locked)
        self._sell_dialogue = DialogueBox(
            self.window, msg, actions=['sell', 'cancel'],
            images=images, title='Sell Card',
            message_after_images=after_msg)

    def _update_sell_after_text(self):
        """Rebuild the after-images text when quantity changes."""
        if not self._sell_card:
            return
        suit, rank = self._sell_card
        qty = self._cards.get((suit, rank), 0)
        locked = self._locked.get((suit, rank), 0)
        free = max(0, qty - locked)
        unit_price = _sell_price(rank, 1)
        new_text = self._sell_after_text(unit_price, qty, free, locked)
        _max_text_w = settings.DIALOGUE_BOX_WIDTH - int(0.08 * _SW)
        self._sell_dialogue.after_lines = DialogueBox._wrap_text(
            new_text, self._sell_dialogue.font, _max_text_w)
        self._sell_dialogue.after_lines_surfaces = [
            self._sell_dialogue.font.render(l, True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            for l in self._sell_dialogue.after_lines]

    def _draw_sell_qty_overlay(self):
        """Draw quantity selector arrows over the sell dialogue."""
        if not self._sell_card or not self._sell_dialogue:
            return
        rects = self._layout_sell_qty_rects()
        self._sell_qty_rects = rects

        label = self._stats_font.render('Quantity', True, settings.COLLECTION_STATS_TEXT_CLR)
        self.window.blit(label, label.get_rect(
            center=(self._sell_dialogue.rect.centerx, rects['qty'].top - int(0.010 * _SH))))

        self._draw_sell_control_button(rects['minus'], '−', self._sell_qty > 1)
        self._draw_sell_control_button(rects['plus'], '+', self._sell_qty < self._sell_max)
        self._draw_sell_control_button(rects['max'], 'Max', self._sell_qty < self._sell_max)
        qty_surf = pygame.Surface((rects['qty'].w, rects['qty'].h), pygame.SRCALPHA)
        pygame.draw.rect(qty_surf, (25, 25, 30, 230), qty_surf.get_rect(), border_radius=6)
        pygame.draw.rect(qty_surf, (180, 155, 95, 210), qty_surf.get_rect(), 1, border_radius=6)
        self.window.blit(qty_surf, rects['qty'].topleft)
        qty_text = self._sell_control_font.render(str(self._sell_qty), True, settings.COLLECTION_STATS_VALUE_CLR)
        self.window.blit(qty_text, qty_text.get_rect(center=rects['qty'].center))

    def _sell_after_text(self, unit_price, qty, free, locked):
        total = unit_price * self._sell_qty
        return (f'Unit value: {unit_price}g  ·  Total payout: {total}g\n'
                f'Selling {self._sell_qty} of {free} free copies '
                f'({locked} locked, {qty} owned).\n\n\n')

    def _layout_sell_qty_rects(self):
        dlg = self._sell_dialogue
        btn_w = settings.COLLECTION_SELL_QTY_BTN_W
        btn_h = settings.COLLECTION_SELL_QTY_BTN_H
        max_w = settings.COLLECTION_SELL_QTY_MAX_W
        gap = settings.COLLECTION_SELL_QTY_GAP
        qty_w = int(btn_w * 1.28)
        total_w = btn_w + gap + qty_w + gap + btn_w + gap + max_w
        x = dlg.rect.centerx - total_w // 2
        y = dlg.rect.bottom - dlg.button_height - btn_h - int(0.010 * _SH)
        return {
            'minus': pygame.Rect(x, y, btn_w, btn_h),
            'qty': pygame.Rect(x + btn_w + gap, y, qty_w, btn_h),
            'plus': pygame.Rect(x + btn_w + gap + qty_w + gap, y, btn_w, btn_h),
            'max': pygame.Rect(x + btn_w + gap + qty_w + gap + btn_w + gap, y, max_w, btn_h),
        }

    def _draw_sell_control_button(self, rect, text, enabled=True):
        mouse_pos = pygame.mouse.get_pos()
        hovered = enabled and rect.collidepoint(mouse_pos)
        bg = (64, 54, 33, 230) if hovered else (36, 36, 42, 220)
        border = (235, 206, 120, 230) if hovered else (135, 118, 82, 210)
        txt = (252, 240, 200) if enabled else (110, 105, 95)
        if not enabled:
            bg = (32, 32, 35, 165)
            border = (80, 75, 65, 160)
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=6)
        pygame.draw.rect(surf, border, surf.get_rect(), 1, border_radius=6)
        self.window.blit(surf, rect.topleft)
        text_surf = self._sell_control_font.render(text, True, txt)
        self.window.blit(text_surf, text_surf.get_rect(center=rect.center))

    def _handle_sell_qty_click(self, pos):
        if not self._sell_card or not self._sell_dialogue:
            return False
        rects = self._sell_qty_rects or self._layout_sell_qty_rects()
        changed = False
        if rects['minus'].collidepoint(pos) and self._sell_qty > 1:
            self._sell_qty -= 1
            changed = True
        elif rects['plus'].collidepoint(pos) and self._sell_qty < self._sell_max:
            self._sell_qty += 1
            changed = True
        elif rects['max'].collidepoint(pos) and self._sell_qty < self._sell_max:
            self._sell_qty = self._sell_max
            changed = True
        if changed:
            self._update_sell_after_text()
            return True
        return any(rect.collidepoint(pos) for rect in rects.values())

    def _perform_sell(self):
        """Execute the sell card API call."""
        suit, rank = self._sell_card
        try:
            result = collection_service.sell_card(suit, rank, self._sell_qty)
            self._gold = result.get('gold', self._gold)
            earned = result.get('gold_earned', 0)
            # Update local card count
            old_qty = self._cards.get((suit, rank), 0)
            self._cards[(suit, rank)] = max(0, old_qty - self._sell_qty)
            if self.state.user_dict:
                self.state.user_dict['gold'] = self._gold
            from utils import sound
            sound.play('coin')
            self.state.set_msg(f'Sold {self._sell_qty} {suit} {rank} for {earned} gold')
        except Exception as e:
            logger.error(f'Sell failed: {e}')
            self.state.set_msg('Failed to sell card')
        self._sell_card = None
        self._sell_dialogue = None
        self._sell_qty_rects = {}

    # ── booster flows ───────────────────────────────────────────────

    def _confirm_open_booster(self, pack_type='main'):
        """Show confirmation dialogue for opening a booster."""
        self._pending_booster_type = pack_type
        info = settings.COLLECTION_PACK_PREVIEWS[pack_type]
        count = self._boosters if pack_type == 'main' else self._boosters_side
        pack_icon = self._booster_icon_dialog if pack_type == 'main' else self._booster_side_icon_dialog
        actions = ['Open', 'cancel']
        if count > 1:
            actions.insert(1, 'Open all')
        self.dialogue_box = DialogueBox(
            self.window,
            f'Open {info["title"]}?\nOwned: {count}',
            actions=actions,
            images=[pack_icon],
            title='Open Booster')

    def _perform_open_booster(self, quantity=1):
        """Start the open booster API call and show reveal overlay when done."""
        pack_type = getattr(self, '_pending_booster_type', 'main')
        self._start_booster_request('open', pack_type, quantity=quantity)

    def _apply_open_booster_result(self, pack_type, result):
        """Apply an open-booster response and show the reveal overlay."""
        if pack_type == 'main':
            self._boosters = result.get('booster_packs', self._boosters)
            if self.state.user_dict:
                self.state.user_dict['booster_packs'] = self._boosters
            self._mark_onboarding_step_completed_local('open_first_main_booster')
        else:
            self._boosters_side = result.get('booster_packs_side', self._boosters_side)
            if self.state.user_dict:
                self.state.user_dict['booster_packs_side'] = self._boosters_side
            self._mark_onboarding_step_completed_local('open_first_side_booster')
        # Opening the first main booster grants the deferred starter set on the
        # server; pick up the updated onboarding (starter_suits + completed
        # steps) so the starter-suit reveal can fire after this booster reveal.
        onboarding = result.get('onboarding')
        if onboarding and self.state.user_dict is not None:
            self.state.user_dict['onboarding'] = onboarding
        drawn_cards = _annotate_booster_impact(
            result.get('cards', []), self._cards,
            getattr(self, '_locked', {}))
        gains = {}
        for c in drawn_cards:
            key = (c['suit'], c['rank'])
            self._cards[key] = c['_impact_owned_after']
            gains[key] = gains.get(key, 0) + 1
        self._pending_reveal_gains = gains
        from game.components.booster_reveal import BoosterRevealOverlay
        from utils import sound
        sound.play('booster_open')
        self._reveal_overlay = BoosterRevealOverlay(self.window, drawn_cards, pack_type=pack_type)

    def _activate_recent_reveal_gains(self):
        gains = dict(getattr(self, '_pending_reveal_gains', {}) or {})
        self._pending_reveal_gains = {}
        if not gains:
            return
        self._recent_card_gains = gains
        self._recent_gains_started_at = pygame.time.get_ticks()

    def _maybe_show_collection_basics(self):
        """First collection visit during the opening 'open a starter pack' phase:
        a windowed 'collection basics' explainer (cards become recipes) before
        the player opens their first booster."""
        if not getattr(self, '_data_loaded', False):
            return
        if getattr(self, '_collection_basics_dialogue', None):
            return
        if not self._menu_coach_allowed_common():
            return
        # Only before the first main booster is opened (the opening phase).
        if 'open_first_main_booster' in self._onboarding_completed_steps():
            return
        if 'collection_basics_window' in self._menu_coach_seen():
            return
        if (self._booster_poller or self._reveal_overlay or self._sell_dialogue
                or self._trade_dialogue or self._profile_dialogue or self.dialogue_box):
            return
        from game.components.tutorial_window import TutorialWindowDialogue
        from game.components import tutorial_diagrams as td
        self._collection_basics_dialogue = TutorialWindowDialogue(
            self.window,
            [
                {
                    'title': 'Key And Number Cards',
                    'layout': 'text_image_text',
                    'lines': [
                        'Key cards carry jewels; number cards carry numbers.',
                        'The outline shows rarity: grey is common, orange is rare, and gold is the most valuable.',
                    ],
                    'image': lambda: td.card_rarity_code_diagram(),
                },
                {
                    'title': 'Cards Become Actions',
                    'layout': 'text_image_text',
                    'lines': [
                        'Every figure, spell, and tactic is built from cards: some from a single card, some from a recipe.',
                        "Don't worry about memorizing recipes: the game always shows you what you can build.",
                    ],
                    'image': lambda: td.card_recipe_examples(),
                    'image_caption': 'Some examples.',
                },
            ],
            title='Your Collection',
        )

    def _handle_collection_basics_events(self, events):
        win = getattr(self, '_collection_basics_dialogue', None)
        if win is None:
            return False
        from pygame import QUIT
        if any(getattr(e, 'type', None) == QUIT for e in events):
            return False
        if win.update(events) == 'done':
            self._collection_basics_dialogue = None
            self._mark_menu_coach_seen('collection_basics_window')
        return True

    def _maybe_show_starter_present(self):
        """After the first booster reveal, explain the starter-card present
        before running the suit roulette."""
        if getattr(self, '_starter_present_dialogue', None):
            return
        if not self._menu_coach_allowed_common():
            return
        completed = self._onboarding_completed_steps()
        if 'open_first_main_booster' not in completed:
            return
        seen = self._menu_coach_seen()
        if 'starter_suit_reveal' in seen or 'starter_cards_present_window' in seen:
            return
        suits = (self._onboarding() or {}).get('starter_suits') or {}
        if not suits.get('offensive'):
            return
        if (self._reveal_overlay or self._collection_basics_dialogue
                or self._booster_poller or self._sell_dialogue
                or self._trade_dialogue or self._profile_dialogue or self.dialogue_box):
            return
        from game.components.tutorial_window import TutorialWindowDialogue
        from game.components import tutorial_diagrams as td
        self._starter_present_dialogue = TutorialWindowDialogue(
            self.window,
            [
                {
                    'title': 'Your Starter Set',
                    'layout': 'image_top',
                    'image': lambda: td.suit_roulette_diagram(),
                    'image_caption': 'One of the four suits, drawn at random.',
                    'lines': [
                        'One more gift: a full starter set of cards, all in one suit.',
                        'Spin to reveal which suit is yours.',
                    ],
                },
            ],
            title='Starter Cards',
        )

    def _handle_starter_present_events(self, events):
        win = getattr(self, '_starter_present_dialogue', None)
        if win is None:
            return False
        from pygame import QUIT
        if any(getattr(e, 'type', None) == QUIT for e in events):
            return False
        if win.update(events) == 'done':
            self._starter_present_dialogue = None
            self._mark_menu_coach_seen('starter_cards_present_window')
        return True

    def _maybe_show_starter_reveal(self):
        """After the first booster open, reveal the (deferred) starter suit and
        set — the beat just before the player is sent to the Kingdom."""
        if getattr(self, '_starter_reveal_dialogue', None):
            return
        if getattr(self, '_starter_present_dialogue', None):
            return
        if not self._menu_coach_allowed_common():
            return
        # Only once the starter set has been granted (first main booster open).
        suits = (self._onboarding() or {}).get('starter_suits') or {}
        offensive = suits.get('offensive')
        if not offensive:
            return
        seen = self._menu_coach_seen()
        if 'starter_suit_reveal' in seen:
            return
        if 'starter_cards_present_window' not in seen:
            return
        # Wait until the booster card reveal (and any other modal) has cleared.
        if (self._reveal_overlay or self._collection_basics_dialogue
                or self._booster_poller or self._sell_dialogue
                or self._trade_dialogue or self._profile_dialogue or self.dialogue_box):
            return
        from game.components.tutorial_window import StarterSuitRevealDialogue
        self._starter_reveal_dialogue = StarterSuitRevealDialogue(self.window, offensive)

    def _handle_starter_reveal_events(self, events):
        win = getattr(self, '_starter_reveal_dialogue', None)
        if win is None:
            return False
        from pygame import QUIT
        if any(getattr(e, 'type', None) == QUIT for e in events):
            return False
        if win.update(events) == 'done':
            self._starter_reveal_dialogue = None
            self._mark_menu_coach_seen('starter_suit_reveal')
        return True

    def _current_collection_coach_step(self):
        if not self._menu_coach_allowed_common():
            return None
        if getattr(self, '_collection_basics_dialogue', None):
            return None
        if getattr(self, '_starter_present_dialogue', None):
            return None
        if (self._booster_poller or self._reveal_overlay or self._sell_dialogue
                or self._trade_dialogue or self._profile_dialogue):
            return None
        completed = self._onboarding_completed_steps()
        next_action = self._first_session_next_action()
        if ((next_action or {}).get('screen') == 'kingdom'
                and 'finish_first_conquer_battle' not in completed):
            home_icon = getattr(self, '_icon_home', None)
            target_rect = getattr(home_icon, 'rect', None) or self._panel_rect
            return {
                'id': 'post_boosters_kingdom',
                'rect': target_rect,
                'title': 'Go To Kingdom',
                'body': 'Your starter set makes a ready-to-go attack. Head to your Kingdom to conquer your first land.',
                'action': 'next',
                'button_label': 'Go to Kingdom',
                'navigate_screen': 'kingdom',
                'max_lines': 4,
            }
        if ((next_action or {}).get('target_id') == 'collection_open_main_booster'
                and 'open_first_main_booster' not in completed):
            return {
                'id': 'collection_open_main_booster',
                'rect': self._btn_open_main_rect,
                'title': 'Open A Main Booster',
                'body': 'Tap here to open your first main booster.',
                'action': 'click',
                'mark_on_click': True,
                'max_lines': 4,
            }
        # No reward-pack round-trip and no side-booster nudge: after the first
        # conquest the kingdom screen closes the first-land tutorial, so the
        # collection screen no longer coaches the player.
        return None

    def _open_booster_sync_result(self, pack_type, quantity=1):
        try:
            if pack_type == 'main':
                data = collection_service.open_booster(quantity=quantity)
            else:
                data = collection_service.open_booster_side(quantity=quantity)
            return {'ok': True, 'data': data}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _confirm_buy_booster(self, pack_type='main'):
        """Show confirmation dialogue for buying a booster."""
        self._pending_booster_type = pack_type
        price = settings.BOOSTER_PACK_PRICE if pack_type == 'main' else settings.BOOSTER_PACK_SIDE_PRICE
        info = settings.COLLECTION_PACK_PREVIEWS[pack_type]
        pack_icon = self._booster_icon_dialog if pack_type == 'main' else self._booster_side_icon_dialog
        self.dialogue_box = DialogueBox(
            self.window,
            f'Buy {info["title"]} for {price} gold?',
            actions=['buy', 'cancel'],
            images=[pack_icon],
            title='Buy Booster')

    def _spawn_booster_floater(self, pack_type):
        """Spawn a rising '+1 Main Pack' / '+1 Side Pack' floater from the buy button."""
        btn_rect = self._btn_buy_main_rect if pack_type == 'main' else self._btn_buy_side_rect
        text = '+1 Main Pack' if pack_type == 'main' else '+1 Side Pack'
        color = settings.COLLECT_FLOAT_XP_CLR
        font = settings.get_font(settings.COLLECT_FLOAT_FONT_SIZE, bold=True)
        self._floating_text.add(FloatingText(
            text,
            btn_rect.center,
            color=color,
            duration_ms=settings.COLLECT_FLOAT_DURATION_MS,
            rise_px=settings.COLLECT_FLOAT_RISE_PX,
            font=font,
        ))

    def _perform_buy_booster(self):
        """Start the buy booster API call."""
        pack_type = getattr(self, '_pending_booster_type', 'main')
        self._start_booster_request('buy', pack_type)

    def _apply_buy_booster_result(self, pack_type, result):
        """Apply a buy-booster response."""
        if pack_type == 'main':
            self._boosters = result.get('booster_packs', self._boosters)
            if self.state.user_dict:
                self.state.user_dict['booster_packs'] = self._boosters
        else:
            self._boosters_side = result.get('booster_packs_side', self._boosters_side)
            if self.state.user_dict:
                self.state.user_dict['booster_packs_side'] = self._boosters_side
        self._gold = result.get('gold', self._gold)
        if self.state.user_dict:
            self.state.user_dict['gold'] = self._gold
        from utils import sound
        sound.play('coin')
        self.state.set_msg('Booster pack purchased!')
        self._spawn_booster_floater(pack_type)

    def _buy_booster_sync_result(self, pack_type, quantity=1):
        try:
            if pack_type == 'main':
                data = collection_service.buy_booster(quantity=quantity)
            else:
                data = collection_service.buy_booster_side(quantity=quantity)
            return {'ok': True, 'data': data}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _booster_async_transform(self, responses):
        response = responses.get('response') if responses else None
        if response is None:
            return {'ok': False, 'error': 'No response from server'}
        status_code = getattr(response, 'status_code', 0)
        if status_code >= 400 or status_code == 0:
            return {
                'ok': False,
                'status': status_code,
                'error': getattr(response, 'text', '')[:200] or 'Request failed',
            }
        try:
            return {'ok': True, 'data': response.json()}
        except Exception as e:
            return {'ok': False, 'status': status_code, 'error': str(e)}

    def _start_booster_request(self, action, pack_type, quantity=1):
        if self._booster_poller:
            return
        quantity = max(1, int(quantity or 1))
        if action == 'open':
            func = self._open_booster_sync_result
            endpoint = 'open_booster' if pack_type == 'main' else 'open_booster_side'
            self._draw_menu_coach(self._current_collection_coach_step())
            label = 'booster pack' if quantity == 1 else 'booster packs'
            self.state.set_msg(f'Opening {quantity} {label}...')
        else:
            func = self._buy_booster_sync_result
            endpoint = 'buy_booster' if pack_type == 'main' else 'buy_booster_side'
            self.state.set_msg('Buying booster pack...')
        self._booster_action = action
        self._booster_pack_type = pack_type
        self._booster_poller = BackgroundPoller(
            func,
            args=(pack_type, quantity),
            async_requests=[{
                'key': 'response',
                'method': 'POST',
                'url': f'{settings.SERVER_URL}/collection/{endpoint}',
                'data': {'quantity': 1},
            }],
            async_transform=self._booster_async_transform,
        )
        self._booster_poller.poll()

    def _clear_booster_request(self):
        self._booster_poller = None
        self._booster_action = None
        self._booster_pack_type = None

    def _handle_booster_result(self, result):
        action = self._booster_action
        pack_type = self._booster_pack_type or 'main'
        self._clear_booster_request()
        if not result or not result.get('ok'):
            error = (result or {}).get('error', 'Unknown booster request failure')
            logger.error(f'{action or "Booster"} booster failed: {error}')
            if action == 'buy':
                self.state.set_msg('Failed to buy booster pack')
            else:
                self.state.set_msg('Failed to open booster pack')
            return
        data = result.get('data') or {}
        if action == 'buy':
            self._apply_buy_booster_result(pack_type, data)
        else:
            self._apply_open_booster_result(pack_type, data)

    def _update_booster_request(self):
        if not self._booster_poller:
            return
        if self._booster_poller.has_result():
            self._handle_booster_result(self._booster_poller.result)
            return
        if not self._booster_poller.busy:
            action = self._booster_action
            self._clear_booster_request()
            logger.error(f'{action or "Booster"} booster request ended without a result')
            self.state.set_msg('Failed to open booster pack' if action == 'open'
                               else 'Failed to buy booster pack')

    # ── update / events ─────────────────────────────────────────────

    def update(self, events):
        super().update()
        self._update_icon_buttons()
        self._maybe_show_collection_basics()
        self._maybe_show_starter_present()
        self._maybe_show_starter_reveal()

        # Re-fetch if data never loaded (e.g. screen was created before login)
        if not self._data_loaded and not self._poller and not self._load_error:
            ud = getattr(self.state, 'user_dict', None) or {}
            self._gold = ud.get('gold', 0)
            self._boosters = ud.get('booster_packs', 0)
            self._boosters_side = ud.get('booster_packs_side', 0)
            self._fetch_collection()

        # Check background poller
        if self._poller and self._poller.has_result():
            try:
                result = self._poller.result
                if not isinstance(result, dict):
                    raise ValueError('Collection response was empty')
                self._apply_collection_data(result)
            except Exception as e:
                logger.error(f'Failed to apply collection data: {e}')
                self._refreshing = False
                self._load_error = 'Could not load collection'
            self._poller = None
        # A poller that ends without publishing a result normally means the
        # service call raised. Preserve cached cards and expose an explicit retry.
        elif self._poller and not self._poller.busy:
            self._poller = None
            self._refreshing = False
            self._load_error = 'Could not load collection'
            if self._data_loaded:
                self.state.set_msg('Could not refresh collection')

        self._update_booster_request()

        # Update reveal overlay
        if self._reveal_overlay:
            self._reveal_overlay.update()

        # Keep sell dialogue buttons hovered
        if self._sell_dialogue:
            for btn in self._sell_dialogue.buttons:
                btn.update()
        if self._trade_dialogue:
            for btn in self._trade_dialogue.buttons:
                btn.update()
        if self._profile_dialogue:
            for btn in self._profile_dialogue.buttons:
                btn.update()
        if self._craft_dialogue:
            for btn in self._craft_dialogue.buttons:
                btn.update()

    def handle_events(self, events):
        super().handle_events(events)

        # Handle open/buy dialogue response
        if self.state.action['status'] == 'open':
            self.reset_action()
            self._perform_open_booster()
            return
        if self.state.action['status'] == 'open all':
            pack_type = getattr(self, '_pending_booster_type', 'main')
            quantity = self._boosters if pack_type == 'main' else self._boosters_side
            self.reset_action()
            if quantity > 0:
                self._perform_open_booster(quantity=quantity)
            else:
                self.state.set_msg('No booster packs to open')
            return
        if self.state.action['status'] == 'buy':
            self.reset_action()
            self._perform_buy_booster()
            return
        if self.state.action['status'] == 'trade':
            self.reset_action()
            self._perform_trade()
            return
        if self.state.action['status'] in ('cancel', 'ok', 'close'):
            # Cancel/close — also close trade/profile dialogues if open
            self.reset_action()
            if self._trade_dialogue:
                self._trade_card = None
                self._trade_target_suit = None
                self._trade_dialogue = None
                self._trade_qty_rects = {}
                self._trade_target_rects = {}
            if self._profile_dialogue:
                self._profile_dialogue = None
                self._profile_card = None
                self._profile_pinned_tooltip = None
            if self._craft_dialogue:
                self._craft_dialogue = None
                self._craft_suit = None
            return
        if self.dialogue_box:
            return
        if self._booster_poller:
            return

        # The collection-basics window captures input while it is up.
        if self._handle_collection_basics_events(events):
            return

        if self._handle_starter_present_events(events):
            return

        # The starter-suit reveal owns its own timed reel animation; updating
        # it here lets the roulette settle and captures the final acknowledgement.
        if self._handle_starter_reveal_events(events):
            return

        coach_step = self._current_collection_coach_step()
        if self._handle_menu_coach_events(events, coach_step):
            return

        for event in events:
            # Reveal overlay captures all input when active
            if self._reveal_overlay:
                if event.type == MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                    done = self._reveal_overlay.handle_click(event.pos)
                    if done:
                        self._reveal_overlay = None
                        self._activate_recent_reveal_gains()
                continue

            # Sell dialogue captures input
            if self._sell_dialogue:
                if event.type == MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                    # Click outside the dialogue box → close without action
                    if (not self._sell_dialogue.rect.collidepoint(event.pos)
                            and pygame.time.get_ticks() - self._sell_dialogue._created_at >= 200):
                        self._sell_card = None
                        self._sell_dialogue = None
                        self._sell_qty_rects = {}
                        continue
                    if self._handle_sell_qty_click(event.pos):
                        continue
                    response = self._sell_dialogue.update([event])
                    if response == 'sell':
                        self._perform_sell()
                    elif response in ('cancel', 'ok'):
                        self._sell_card = None
                        self._sell_dialogue = None
                        self._sell_qty_rects = {}
                elif event.type == KEYDOWN:
                    if event.key == K_LEFT and self._sell_qty > 1:
                        self._sell_qty -= 1
                        self._update_sell_after_text()
                    elif event.key == K_RIGHT and self._sell_qty < self._sell_max:
                        self._sell_qty += 1
                        self._update_sell_after_text()
                continue

            # Trade dialogue captures input
            if self._trade_dialogue:
                if event.type == MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                    # Click outside the dialogue box → close without action
                    if (not self._trade_dialogue.rect.collidepoint(event.pos)
                            and pygame.time.get_ticks() - self._trade_dialogue._created_at >= 200):
                        self._trade_card = None
                        self._trade_target_suit = None
                        self._trade_dialogue = None
                        self._trade_qty_rects = {}
                        self._trade_target_rects = {}
                        continue
                    if self._handle_trade_overlay_click(event.pos):
                        continue
                    response = self._trade_dialogue.update([event])
                    if response == 'trade':
                        self._perform_trade()
                    elif response in ('cancel', 'ok'):
                        self._trade_card = None
                        self._trade_target_suit = None
                        self._trade_dialogue = None
                        self._trade_qty_rects = {}
                        self._trade_target_rects = {}
                elif event.type == KEYDOWN:
                    if event.key == K_LEFT and self._trade_qty > 1:
                        self._trade_qty -= 1
                        self._update_trade_after_text()
                    elif event.key == K_RIGHT and self._trade_qty < self._trade_max:
                        self._trade_qty += 1
                        self._update_trade_after_text()
                continue

            # Craft dialogue captures input (Maharaja — no sell/trade)
            if self._craft_dialogue:
                if event.type == MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                    # Click outside the dialogue box → close without action
                    if (not self._craft_dialogue.rect.collidepoint(event.pos)
                            and pygame.time.get_ticks() - self._craft_dialogue._created_at >= 200):
                        self._craft_dialogue = None
                        self._craft_suit = None
                        continue
                    response = self._craft_dialogue.update([event])
                    if response == 'craft':
                        self._perform_craft()
                    elif response in ('cancel', 'ok', 'close'):
                        self._craft_dialogue = None
                        self._craft_suit = None
                continue

            # Profile dialogue captures input
            if self._profile_dialogue:
                if event.type == MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                    # Click outside the dialogue box → close
                    if (not self._profile_dialogue.rect.collidepoint(event.pos)
                            and pygame.time.get_ticks() - self._profile_dialogue._created_at >= 200):
                        self._profile_dialogue = None
                        self._profile_card = None
                        self._profile_pinned_tooltip = None
                        continue
                    tooltip = self._profile_dialogue.get_tooltip(event.pos)
                    if tooltip:
                        self._profile_pinned_tooltip = tooltip
                        self._profile_pinned_tooltip_pos = event.pos
                        continue
                    self._profile_pinned_tooltip = None
                    response = self._profile_dialogue.update([event])
                    profile_card = self._profile_card
                    if response == 'sell copies' and profile_card:
                        self._profile_dialogue = None
                        self._profile_card = None
                        self._open_sell_dialogue(*profile_card)
                    elif response == 'convert' and profile_card:
                        self._profile_dialogue = None
                        self._profile_card = None
                        self._open_trade_dialogue(*profile_card)
                    elif response in ('close', 'ok', 'cancel'):
                        self._profile_dialogue = None
                        self._profile_card = None
                continue

            if self._handle_icon_events(event):
                continue

            # Click outside content box → back to game menu
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and not self._sell_dialogue
                    and not self._trade_dialogue
                    and not self._profile_dialogue
                    and not self._craft_dialogue
                    and not self._reveal_overlay
                    and not pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H).collidepoint(event.pos)):
                self.state.screen = 'game_menu'
                return

            if event.type == MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                # X close button
                if self._btn_close_rect.collidepoint(event.pos):
                    self.state.screen = 'game_menu'
                    continue
                if self._btn_open_main_rect.collidepoint(event.pos):
                    if not self._data_loaded:
                        self.state.set_msg('Wait for the collection to load')
                    elif self._boosters > 0:
                        self._confirm_open_booster('main')
                    else:
                        self.state.set_msg('No main booster packs to open')
                    continue
                if self._btn_open_side_rect.collidepoint(event.pos):
                    if not self._data_loaded:
                        self.state.set_msg('Wait for the collection to load')
                    elif self._boosters_side > 0:
                        self._confirm_open_booster('side')
                    else:
                        self.state.set_msg('No side booster packs to open')
                    continue
                if self._btn_buy_main_rect.collidepoint(event.pos):
                    if self._gold >= settings.BOOSTER_PACK_PRICE:
                        self._confirm_buy_booster('main')
                    else:
                        self.state.set_msg('Not enough gold')
                    continue
                if self._btn_buy_side_rect.collidepoint(event.pos):
                    if self._gold >= settings.BOOSTER_PACK_SIDE_PRICE:
                        self._confirm_buy_booster('side')
                    else:
                        self.state.set_msg('Not enough gold')
                    continue

                if (not self._data_loaded and self._load_error
                        and self._retry_rect.collidepoint(event.pos)):
                    self._fetch_collection()
                    continue

                if (self._data_loaded
                        and self._locked_toggle_rect.collidepoint(event.pos)):
                    self._show_locked_cards = not self._show_locked_cards
                    continue

                # Card taps always inspect; economic actions are contextual
                # buttons inside the profile instead of persistent global modes.
                if self._data_loaded and self._panel_rect.collidepoint(event.pos):
                    card = self._card_at_pos(event.pos)
                    if card:
                        suit, rank, _section = card
                        self._open_profile_dialogue(suit, rank)
