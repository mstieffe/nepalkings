# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
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
    return settings.COLLECTION_TIER_LABELS.get(_card_tier(rank, pack_type), 'Common')


def _collection_sort_key(rank, pack_type):
    """Sort key for the collection grid.

    Order: tier desc → key cards before number cards → higher card value first.
    """
    tier = _card_tier(rank, pack_type)
    is_number = 1 if rank in settings.NUMBER_CARDS else 0  # key (0) before number (1)
    value = settings.RANK_TO_VALUE.get(rank, 0)
    return (-tier, is_number, -value)


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

        # ── Card ranks ──────────────────────────────────────────────
        # Sort: tier desc → key cards before number cards → value desc.
        self._main_ranks = sorted(
            settings.RANKS_MAIN_CARDS,
            key=lambda r: _collection_sort_key(r, 'main'),
        )
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
        cw, ch = settings.COLLECTION_CARD_W, settings.COLLECTION_CARD_H
        self._card_imgs = {}   # {(suit,rank): CardImg}
        for suit in settings.SUITS:
            for rank in settings.RANKS:
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
        # Third panel beside the two booster panels: hosts mutually-exclusive
        # Sell / Trade mode toggles.
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

        # Mode toggle buttons inside the actions panel
        _ap = self._actions_panel_rect
        _mode_btn_h = settings.COLLECTION_PACK_PANEL_BTN_H
        _mode_btn_gap = settings.COLLECTION_PACK_PANEL_BTN_GAP
        _mode_btn_w = min(
            settings.COLLECTION_PACK_PANEL_BTN_W,
            (_ap.w - settings.COLLECTION_PACK_PANEL_PAD_X * 2 - _mode_btn_gap) // 2,
        )
        _mode_btn_y = _ap.bottom - settings.COLLECTION_PACK_PANEL_PAD_Y - _mode_btn_h
        _mode_btn_x = _ap.centerx - (_mode_btn_w * 2 + _mode_btn_gap) // 2
        self._mode_btn_rects = {
            'sell': pygame.Rect(_mode_btn_x, _mode_btn_y, _mode_btn_w, _mode_btn_h),
            'trade': pygame.Rect(_mode_btn_x + _mode_btn_w + _mode_btn_gap, _mode_btn_y,
                                 _mode_btn_w, _mode_btn_h),
        }
        # Active mode: None | 'sell' | 'trade'. Drives card-click behaviour.
        self._mode = None

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

        # ── Card click rects (computed per frame based on tab) ──────
        self._card_rects = []  # [(rect, suit, rank), ...]

        # ── Background poller for fetching data ─────────────────────
        self._poller = None
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

        # ── Booster reveal overlay ──────────────────────────────────
        self._reveal_overlay = None
        self._pending_booster_type = 'main'  # tracks which type for dialogue flow
        self._booster_poller = None
        self._booster_action = None
        self._booster_pack_type = None

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
        """Called each time the collection screen becomes active — force re-fetch."""
        self._data_loaded = False
        self._cards = {}
        self._locked = {}
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
        self._mode = None
        self._fetch_collection()

    # ── data fetching ───────────────────────────────────────────────

    def _fetch_collection(self):
        """Start a background fetch of the collection data."""
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
                cx = cards_x + col_i * (cw + gx)
                positions.append((cx, row_y, suit, rank, 'main'))
                self._card_rects.append((pygame.Rect(cx, row_y, cw, ch), suit, rank, 'main'))

            # Side cards (same row, to the right)
            for col_i, rank in enumerate(self._side_ranks):
                cx = side_x + col_i * (cw + gx)
                positions.append((cx, row_y, suit, rank, 'side'))
                self._card_rects.append((pygame.Rect(cx, row_y, cw, ch), suit, rank, 'side'))

        return positions

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
        self._draw_card_grid()
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

    def _draw_collection_stats(self):
        """Draw a compact owned/missing/locked summary strip."""
        r = self._stats_rect
        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.COLLECTION_STATS_BG_CLR, surf.get_rect(), border_radius=8)
        pygame.draw.rect(surf, settings.COLLECTION_STATS_BORDER_CLR, surf.get_rect(), 1, border_radius=8)
        self.window.blit(surf, r.topleft)

        stats = _collection_stats(self._cards, self._locked)
        items = [
            ('Collection', f"{stats['unique_owned']}/{stats['unique_total']}"),
            ('Total', str(stats['owned_total'])),
            ('Locked', str(stats['locked_total'])),
            ('Available', str(stats['available_total'])),
        ]

        rendered = []
        for label, value in items:
            label_surf = self._stats_font.render(f'{label}: ', True, settings.COLLECTION_STATS_TEXT_CLR)
            value_surf = self._stats_font.render(value, True, settings.COLLECTION_STATS_VALUE_CLR)
            rendered.append((label_surf, value_surf, label_surf.get_width() + value_surf.get_width()))
        sep_w = int(0.018 * _SW)
        total_w = sum(width for _, _, width in rendered) + sep_w * (len(rendered) - 1)
        x = r.centerx - total_w // 2
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
            owned_text = f'Owned: {count}'
            count_surf = self._pack_detail_font.render(
                owned_text, True, settings.COLLECTION_PACK_PANEL_TEXT_CLR)
            if title.get_width() + gap + count_surf.get_width() > max_row_w:
                count_surf = self._pack_detail_font.render(
                    f'x{count}', True, settings.COLLECTION_PACK_PANEL_TEXT_CLR)
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
                f'Owned: {count}', True, settings.COLLECTION_PACK_PANEL_TEXT_CLR)
            self.window.blit(
                count_text,
                (title_x, title_y + title.get_height() + int(0.004 * _SH)),
            )

        btns = self._pack_button_rects[pack_type]
        self._draw_action_button(btns['open'], f'Open ({count})', count > 0)
        self._draw_action_button(btns['buy'], f'Buy {price}g', can_buy)

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
        for (cx, cy, suit, rank, section) in positions:
            # Skip if outside visible panel
            if cy + ch < self._panel_rect.y or cy > self._panel_rect.bottom:
                continue

            card = self._card_imgs.get((suit, rank))
            if not card:
                continue
            qty = self._cards.get((suit, rank), 0)
            locked = self._locked.get((suit, rank), 0)
            card_rect = pygame.Rect(cx, cy, cw, ch)
            hovered = (
                card_rect.collidepoint(mouse_pos)
                and not self._sell_dialogue
                and not self._trade_dialogue
                and not self._profile_dialogue
                and not self._reveal_overlay
            )

            if qty > 0:
                card.draw_front_bright(cx, cy)
                self._draw_tier_border(cx, cy, cw, ch, rank, section, owned=True)
                if hovered:
                    glow_surf = pygame.Surface((cw + 4, ch + 4), pygame.SRCALPHA)
                    pygame.draw.rect(glow_surf, (250, 221, 0, 80), glow_surf.get_rect(), 2)
                    self.window.blit(glow_surf, (cx - 2, cy - 2))
                self._draw_card_badge(cx, cy, cw, qty, locked)
            else:
                card.draw_front_bright(cx, cy)
                self.window.blit(self._grey_overlay, (cx, cy))
                self._draw_tier_border(cx, cy, cw, ch, rank, section, owned=False)

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

    def _draw_card_badge(self, cx, cy, cw, qty, locked=0):
        """Draw the available/owned badge at the bottom-right of a card."""
        free = max(0, qty - locked)
        badge_text = f'{free}/{qty}'
        if free == 0 and qty > 0:
            bg_clr = (88, 80, 66, 220)        # all locked → muted grey
        elif locked > 0:
            bg_clr = (120, 90, 30, 210)       # some locked → amber
        else:
            bg_clr = settings.COLLECTION_BADGE_BG_CLR
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

    def _draw_action_button(self, rect, text, enabled):
        """Draw one of the bottom action buttons."""
        mouse_pos = pygame.mouse.get_pos()
        hovered = (
            rect.collidepoint(mouse_pos)
            and not self.dialogue_box
            and not self._sell_dialogue
            and not self._trade_dialogue
            and not self._profile_dialogue
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
            bg_clr = (80, 70, 40, 220)
            txt_clr = (255, 255, 220)
        elif hovered:
            bg_clr = (60, 55, 35, 220)
            txt_clr = (250, 240, 200)
        else:
            bg_clr = (35, 35, 40, 200)
            txt_clr = (200, 190, 160)

        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill(bg_clr)
        pygame.draw.rect(surf, (120, 110, 90, 200), surf.get_rect(), 1)
        self.window.blit(surf, rect.topleft)

        txt = self._action_font.render(text, True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_profile_tooltip(self, text):
        """Draw a multi-line, word-wrapped tooltip pill for a hovered profile group icon."""
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
        mx, my = pygame.mouse.get_pos()
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
        """Draw the third panel with Sell / Trade mode toggles."""
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

        if settings.TOUCH_TARGET_MIN <= 0:
            if self._mode is None:
                hint_text = 'Click a card to view its uses'
            elif self._mode == 'sell':
                hint_text = 'Click a card to sell copies'
            else:
                hint_text = 'Click a card to convert copies'
            hint = self._pack_detail_font.render(
                hint_text, True, settings.COLLECTION_PACK_PANEL_TEXT_CLR)
            self.window.blit(
                hint,
                (panel.x + pad_x,
                 panel.y + pad_y + title.get_height() + int(0.004 * _SH)),
            )

        for mode_key, rect in self._mode_btn_rects.items():
            label = settings.COLLECTION_MODE_BTN_TEXT[mode_key]
            self._draw_mode_toggle_button(rect, label, mode_key == self._mode)

    def _draw_mode_toggle_button(self, rect, text, active):
        """Draw a mode toggle (active = highlighted)."""
        mouse_pos = pygame.mouse.get_pos()
        hovered = (
            rect.collidepoint(mouse_pos)
            and not self.dialogue_box
            and not self._sell_dialogue
            and not self._trade_dialogue
            and not self._profile_dialogue
            and not self._reveal_overlay
        )

        if active:
            bg_clr = (90, 75, 30, 235)
            border_clr = (250, 221, 0)
            txt_clr = (255, 245, 200)
        elif hovered:
            bg_clr = (60, 55, 35, 220)
            border_clr = (200, 175, 110)
            txt_clr = (250, 240, 200)
        else:
            bg_clr = (35, 35, 40, 200)
            border_clr = (120, 110, 90, 200)
            txt_clr = (200, 190, 160)

        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg_clr, surf.get_rect(), border_radius=6)
        pygame.draw.rect(surf, border_clr, surf.get_rect(), 2 if active else 1,
                         border_radius=6)
        self.window.blit(surf, rect.topleft)
        txt = self._action_font.render(text, True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _toggle_mode(self, mode):
        """Mutually-exclusive mode toggle: clicking active mode deactivates."""
        if self._mode == mode:
            self._mode = None
        else:
            self._mode = mode

    # ── card profile dialogue (default click) ──────────────────────

    def _open_profile_dialogue(self, suit, rank):
        """Show a profile dialogue with all uses of (suit, rank)."""
        from utils.card_uses import get_card_uses

        qty = self._cards.get((suit, rank), 0)
        locked = self._locked.get((suit, rank), 0)
        free = max(0, qty - locked)
        unit_price = _sell_price(rank, 1)
        section = _card_pack_type(rank)
        tier_label = _tier_label(rank, section)

        # Card category — shown inside the Figures section, not the header.
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

        def _group(title, entries, note='', note_prefix=''):
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
                'note_prefix': note_prefix,
                'description': note or (
                    ', '.join(name for name, _, _ in entries[:max_items])
                    if entries else 'No uses'
                ),
            }

        groups = [
            _group('Figures', uses['figures'],
                   note=', '.join(n for n, _, _ in uses['figures'][:max_items])
                        if uses['figures'] else 'No uses',
                   note_prefix=category_label),
            _group('Spells', uses['spells']),
            _group('Battle Options', uses['battle_moves']),
        ]

        card_img = self._card_imgs.get((suit, rank))
        if qty > 0:
            msg = (f'{suit} {rank}  ·  {tier_label}\n'
                   f'Owned: {qty}  ·  Free: {free}  ·  Locked: {locked}  ·  Sell: {unit_price}g')
        else:
            msg = f'{suit} {rank}  ·  {tier_label}\nNot in collection'
        self._profile_dialogue = DialogueBox(
            self.window, msg, actions=['close'],
            images=[card_img] if card_img else [],
            image_groups=groups,
            title='Card Profile',
        )

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
        pack_icon = self._booster_icon_dialog if pack_type == 'main' else self._booster_side_icon_dialog
        self.dialogue_box = DialogueBox(
            self.window,
            f'Open {info["title"]}?',
            actions=['open', 'cancel'],
            images=[pack_icon],
            title='Open Booster')

    def _perform_open_booster(self):
        """Start the open booster API call and show reveal overlay when done."""
        pack_type = getattr(self, '_pending_booster_type', 'main')
        self._start_booster_request('open', pack_type)

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
        drawn_cards = result.get('cards', [])
        for c in drawn_cards:
            key = (c['suit'], c['rank'])
            self._cards[key] = self._cards.get(key, 0) + 1
        from game.components.booster_reveal import BoosterRevealOverlay
        from utils import sound
        sound.play('booster_open')
        self._reveal_overlay = BoosterRevealOverlay(self.window, drawn_cards, pack_type=pack_type)

    def _current_collection_coach_step(self):
        if not self._menu_coach_allowed_common():
            return None
        if (self._booster_poller or self._reveal_overlay or self._sell_dialogue
                or self._trade_dialogue or self._profile_dialogue):
            return None
        completed = self._onboarding_completed_steps()
        if 'finish_first_duel' not in completed:
            return None
        if 'open_first_main_booster' not in completed:
            return {
                'id': 'collection_open_main_booster',
                'rect': self._btn_open_main_rect,
                'title': 'Open A Main Booster',
                'body': 'Main cards build core figures, spells, and battle moves. Cards have three different tiers: common, rare, and epic. Click Open on the main pack panel, then confirm the booster reveal.',
                'action': 'click',
                'mark_on_click': True,
                'max_lines': 5,
            }
        if 'open_first_side_booster' not in completed:
            return {
                'id': 'collection_open_side_booster',
                'rect': self._btn_open_side_rect,
                'title': 'Open A Side Booster',
                'body': 'Side cards unlock more advanced figures and effects. Open one side booster so your collection has both card families.',
                'action': 'click',
                'mark_on_click': True,
                'max_lines': 5,
            }
        if 'collection_return_home' not in self._menu_coach_seen():
            return {
                'id': 'collection_return_home',
                'rect': self._icon_home.rect,
                'title': 'Back To The Menu',
                'body': 'Good. You opened some packs and added cards to your collection. Return to the main menu and the tour will continue with kingdom play.',
                'action': 'click',
                'mark_on_click': True,
                'max_lines': 5,
            }
        return None

    def _open_booster_sync_result(self, pack_type):
        try:
            if pack_type == 'main':
                data = collection_service.open_booster()
            else:
                data = collection_service.open_booster_side()
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
        self.state.set_msg('Booster pack purchased!')
        self._spawn_booster_floater(pack_type)

    def _buy_booster_sync_result(self, pack_type):
        try:
            if pack_type == 'main':
                data = collection_service.buy_booster()
            else:
                data = collection_service.buy_booster_side()
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

    def _start_booster_request(self, action, pack_type):
        if self._booster_poller:
            return
        if action == 'open':
            func = self._open_booster_sync_result
            endpoint = 'open_booster' if pack_type == 'main' else 'open_booster_side'
            self._draw_menu_coach(self._current_collection_coach_step())
            self.state.set_msg('Opening booster pack...')
        else:
            func = self._buy_booster_sync_result
            endpoint = 'buy_booster' if pack_type == 'main' else 'buy_booster_side'
            self.state.set_msg('Buying booster pack...')
        self._booster_action = action
        self._booster_pack_type = pack_type
        self._booster_poller = BackgroundPoller(
            func,
            args=(pack_type,),
            async_requests=[{
                'key': 'response',
                'method': 'POST',
                'url': f'{settings.SERVER_URL}/collection/{endpoint}',
                'data': {'quantity': 1} if action == 'buy' else {},
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

        # Re-fetch if data never loaded (e.g. screen was created before login)
        if not self._data_loaded and not self._poller:
            ud = getattr(self.state, 'user_dict', None) or {}
            self._gold = ud.get('gold', 0)
            self._boosters = ud.get('booster_packs', 0)
            self._boosters_side = ud.get('booster_packs_side', 0)
            self._fetch_collection()

        # Check background poller
        if self._poller and self._poller.has_result():
            try:
                self._apply_collection_data(self._poller.result)
            except Exception as e:
                logger.error(f'Failed to apply collection data: {e}')
            self._poller = None
        # Clear a failed/stale poller so re-fetch can trigger next frame
        elif self._poller and not self._poller.busy:
            self._poller = None

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

    def handle_events(self, events):
        super().handle_events(events)

        # Handle open/buy dialogue response
        if self.state.action['status'] == 'open':
            self.reset_action()
            self._perform_open_booster()
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
            return
        if self.dialogue_box:
            return
        if self._booster_poller:
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

            # Profile dialogue captures input
            if self._profile_dialogue:
                if event.type == MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                    # Click outside the dialogue box → close
                    if (not self._profile_dialogue.rect.collidepoint(event.pos)
                            and pygame.time.get_ticks() - self._profile_dialogue._created_at >= 200):
                        self._profile_dialogue = None
                        continue
                    response = self._profile_dialogue.update([event])
                    if response in ('close', 'ok', 'cancel'):
                        self._profile_dialogue = None
                continue

            if self._handle_icon_events(event):
                continue

            # Click outside content box → back to game menu
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and not self._sell_dialogue
                    and not self._trade_dialogue
                    and not self._profile_dialogue
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
                    if self._boosters > 0:
                        self._confirm_open_booster('main')
                    else:
                        self.state.set_msg('No main booster packs to open')
                    continue
                if self._btn_open_side_rect.collidepoint(event.pos):
                    if self._boosters_side > 0:
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

                # Mode toggle buttons (Sell / Trade)
                _mode_clicked = None
                for _mode_key, _mode_rect in self._mode_btn_rects.items():
                    if _mode_rect.collidepoint(event.pos):
                        _mode_clicked = _mode_key
                        break
                if _mode_clicked:
                    self._toggle_mode(_mode_clicked)
                    continue

                # Card clicks (only within panel) — behaviour depends on mode
                if self._panel_rect.collidepoint(event.pos):
                    for rect, suit, rank, section in self._card_rects:
                        if rect.collidepoint(event.pos):
                            if self._mode == 'sell':
                                self._open_sell_dialogue(suit, rank)
                            elif self._mode == 'trade':
                                self._open_trade_dialogue(suit, rank)
                            else:
                                # Default mode — show profile for any card (owned or not)
                                self._open_profile_dialogue(suit, rank)
                            break
