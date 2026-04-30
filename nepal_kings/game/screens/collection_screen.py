# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
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
_BOX_Y      = int(0.10 * _SH)
_BOX_W      = int(0.87 * _SW)
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
        self._tier_font = settings.get_font(settings.COLLECTION_BADGE_FONT_SIZE, bold=True)
        self._sell_control_font = settings.get_font(settings.COLLECTION_SELL_FONT_SIZE, bold=True)

        # ── Card ranks ──────────────────────────────────────────────
        self._main_ranks = list(reversed(settings.RANKS_MAIN_CARDS))  # A,K,Q,J,10,9,8,7
        self._side_ranks = list(reversed(settings.RANKS_SIDE_CARDS))  # 6,5,4,3,2

        # ── Scroll offset for combined view ─────────────────────────
        self._scroll_y = 0
        self._content_height = 0  # computed in _compute_card_positions

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
        _pack_w = (_BOX_W - _pack_margin_x * 2 - _pack_gap) // 2
        _pack_x = _BOX_X + _pack_margin_x
        self._pack_panel_rects = {
            'main': pygame.Rect(_pack_x, _pack_y, _pack_w, _pack_h),
            'side': pygame.Rect(_pack_x + _pack_w + _pack_gap, _pack_y, _pack_w, _pack_h),
        }
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

        # ── Booster reveal overlay ──────────────────────────────────
        self._reveal_overlay = None
        self._pending_booster_type = 'main'  # tracks which type for dialogue flow

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
        self._scroll_y = 0
        self._sell_card = None
        self._sell_dialogue = None
        self._reveal_overlay = None
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
        header_y = py - self._scroll_y
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

        last_row_bottom = (settings.COLLECTION_PANEL_PAD_Y + section_header_h +
                   len(suits) * ch + max(0, len(suits) - 1) * gy +
                   settings.COLLECTION_PANEL_PAD_Y)

        # Total content height (for scroll clamping)
        self._content_height = last_row_bottom

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

        self._draw_close_x_button()

        # Sell dialogue
        if self._sell_dialogue:
            self._sell_dialogue.draw()
            self._draw_sell_qty_overlay()

        # Booster reveal overlay
        if self._reveal_overlay:
            self._reveal_overlay.draw()

        # Icon buttons + messages overlay
        self._draw_menu_overlay()

    def _draw_collection_stats(self):
        """Draw a compact owned/missing/locked summary strip."""
        r = self._stats_rect
        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.COLLECTION_STATS_BG_CLR, surf.get_rect(), border_radius=8)
        pygame.draw.rect(surf, settings.COLLECTION_STATS_BORDER_CLR, surf.get_rect(), 1, border_radius=8)
        self.window.blit(surf, r.topleft)

        stats = _collection_stats(self._cards, self._locked)
        items = [
            ('Unique', f"{stats['unique_owned']}/{stats['unique_total']}"),
            ('Cards', str(stats['owned_total'])),
            ('Missing', str(stats['missing_total'])),
            ('Locked', str(stats['locked_total'])),
            ('Packs', f"M {self._boosters}  ·  S {self._boosters_side}"),
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
        title = self._pack_title_font.render(info['title'], True, settings.COLLECTION_PACK_PANEL_TITLE_CLR)
        self.window.blit(title, (title_x, panel.y + pad_y - int(0.001 * _SH)))
        count_text = self._pack_detail_font.render(
            f'Owned: {count}  ·  {info["range"]}', True, settings.COLLECTION_PACK_PANEL_TEXT_CLR)
        self.window.blit(count_text, (title_x, panel.y + pad_y + title.get_height() + int(0.002 * _SH)))

        preview_y = panel.y + pad_y + icon_sz + int(0.008 * _SH)
        preview = self._pack_detail_font.render(info['preview'], True, settings.COLLECTION_PACK_PANEL_TEXT_CLR)
        self.window.blit(preview, (panel.x + pad_x, preview_y))
        odds = self._pack_detail_font.render(f'Odds: {info["odds"]}', True, settings.COLLECTION_PACK_PANEL_MUTED_CLR)
        self.window.blit(odds, (panel.x + pad_x, preview_y + preview.get_height() + int(0.002 * _SH)))

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
            hovered = card_rect.collidepoint(mouse_pos) and not self._sell_dialogue and not self._reveal_overlay

            if qty > 0:
                card.draw_front_bright(cx, cy)
                self._draw_card_tier_accent(card_rect, rank, section, owned=True)
                if hovered:
                    glow_surf = pygame.Surface((cw + 4, ch + 4), pygame.SRCALPHA)
                    pygame.draw.rect(glow_surf, (250, 221, 0, 80), glow_surf.get_rect(), 2)
                    self.window.blit(glow_surf, (cx - 2, cy - 2))
                self._draw_card_badge(cx, cy, cw, qty, locked)
            else:
                card.draw_front_bright(cx, cy)
                self.window.blit(self._grey_overlay, (cx, cy))
                self._draw_card_tier_accent(card_rect, rank, section, owned=False)

    def _draw_card_tier_accent(self, rect, rank, section, owned=True):
        """Draw a subtle tier strip/corner marker without overpowering card art."""
        tier = _card_tier(rank, section)
        border = settings.COLLECTION_TIER_BORDER_COLORS.get(tier, (160, 160, 160, 120))
        alpha_scale = 1.0 if owned else 0.38
        color = (border[0], border[1], border[2], max(35, int(border[3] * alpha_scale)))
        accent = pygame.Surface((rect.w + 4, rect.h + 4), pygame.SRCALPHA)
        pygame.draw.rect(accent, color, accent.get_rect(), 2 if owned else 1, border_radius=5)
        strip_h = max(3, int(0.0045 * _SH))
        pygame.draw.rect(accent, color, pygame.Rect(2, 2, rect.w, strip_h), border_radius=2)
        corner = max(10, int(0.012 * _SW))
        pygame.draw.polygon(accent, color, [(rect.w + 1, 2), (rect.w + 1, corner), (rect.w + 1 - corner, 2)])
        self.window.blit(accent, (rect.x - 2, rect.y - 2))

    def _draw_card_badge(self, cx, cy, cw, qty, locked=0):
        """Draw ×N (free/total) badge at the bottom-right of a card."""
        if locked > 0:
            free = max(0, qty - locked)
            badge_text = f'×{free}/{qty}'
            if free == 0:
                bg_clr = (88, 80, 66, 220)
            else:
                bg_clr = (126, 84, 32, 220)
        else:
            badge_text = f'×{qty}'
            bg_clr = settings.COLLECTION_BADGE_BG_CLR
        badge_surf = self._badge_font.render(badge_text, True, settings.COLLECTION_BADGE_CLR)
        lock_extra = int(0.013 * _SW) if locked > 0 else 0
        bw = badge_surf.get_width() + settings.COLLECTION_BADGE_PAD_X * 2 + lock_extra
        bh = badge_surf.get_height() + settings.COLLECTION_BADGE_PAD_Y * 2
        bx = cx + cw - bw - 2
        by = cy + settings.COLLECTION_CARD_H - bh - 2
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        bg.fill(bg_clr)
        self.window.blit(bg, (bx, by))
        text_x = bx + settings.COLLECTION_BADGE_PAD_X
        if locked > 0:
            icon_size = max(6, min(lock_extra, bh - 4))
            self._draw_lock_icon(text_x, by + (bh - icon_size) // 2, icon_size)
            text_x += lock_extra
        self.window.blit(badge_surf, (text_x, by + settings.COLLECTION_BADGE_PAD_Y))

    def _draw_lock_icon(self, x, y, size):
        """Draw a tiny lock icon programmatically for locked collection cards."""
        if size <= 0:
            return
        color = (245, 226, 180, 235)
        shackle = pygame.Rect(int(x + size * 0.25), int(y), int(size * 0.50), int(size * 0.55))
        body = pygame.Rect(int(x + size * 0.14), int(y + size * 0.40),
                           int(size * 0.72), int(size * 0.52))
        pygame.draw.arc(self.window, color, shackle, 3.14, 6.28, max(1, size // 8))
        pygame.draw.rect(self.window, color, body, border_radius=max(1, size // 8))

    def _draw_action_button(self, rect, text, enabled):
        """Draw one of the bottom action buttons."""
        mouse_pos = pygame.mouse.get_pos()
        hovered = (rect.collidepoint(mouse_pos) and not self.dialogue_box
               and not self._sell_dialogue and not self._reveal_overlay)
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

    def _draw_close_x_button(self):
        """Draw a small X close button in the top-right corner of the box."""
        r = self._btn_close_rect
        mouse_pos = pygame.mouse.get_pos()
        hovered = (r.collidepoint(mouse_pos) and not self.dialogue_box
               and not self._sell_dialogue and not self._reveal_overlay)

        bg_clr = (80, 50, 25, 220) if hovered else (55, 35, 18, 200)
        border_clr = (180, 160, 120) if hovered else (120, 100, 70)
        txt_clr = (255, 240, 200) if hovered else (200, 180, 140)

        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg_clr, surf.get_rect(), border_radius=4)
        pygame.draw.rect(surf, border_clr, surf.get_rect(), 1, border_radius=4)
        self.window.blit(surf, r.topleft)

        txt = self._close_font.render('\u00d7', True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=r.center))

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
        tier = _tier_label(rank, _card_pack_type(rank))
        msg = (f'{suit} {rank} · {tier} card\n'
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
        self.dialogue_box = DialogueBox(
            self.window,
            f'Open a {info["title"]}?\n{info["preview"]}\nOdds: {info["odds"]}',
            actions=['open', 'cancel'],
            title='Open Booster')

    def _perform_open_booster(self):
        """Execute the open booster API call and show reveal overlay."""
        pack_type = getattr(self, '_pending_booster_type', 'main')
        try:
            if pack_type == 'main':
                result = collection_service.open_booster()
                self._boosters = result.get('booster_packs', self._boosters)
                if self.state.user_dict:
                    self.state.user_dict['booster_packs'] = self._boosters
            else:
                result = collection_service.open_booster_side()
                self._boosters_side = result.get('booster_packs_side', self._boosters_side)
                if self.state.user_dict:
                    self.state.user_dict['booster_packs_side'] = self._boosters_side
            drawn_cards = result.get('cards', [])
            # Update local card counts
            for c in drawn_cards:
                key = (c['suit'], c['rank'])
                self._cards[key] = self._cards.get(key, 0) + 1
            # Show reveal overlay
            from game.components.booster_reveal import BoosterRevealOverlay
            self._reveal_overlay = BoosterRevealOverlay(self.window, drawn_cards, pack_type=pack_type)
        except Exception as e:
            logger.error(f'Open booster failed: {e}')
            self.state.set_msg('Failed to open booster pack')

    def _confirm_buy_booster(self, pack_type='main'):
        """Show confirmation dialogue for buying a booster."""
        self._pending_booster_type = pack_type
        price = settings.BOOSTER_PACK_PRICE if pack_type == 'main' else settings.BOOSTER_PACK_SIDE_PRICE
        info = settings.COLLECTION_PACK_PREVIEWS[pack_type]
        self.dialogue_box = DialogueBox(
            self.window,
            f'Buy a {info["title"]} for {price} gold?\n{info["preview"]}\nOdds: {info["odds"]}',
            actions=['buy', 'cancel'],
            title='Buy Booster')

    def _perform_buy_booster(self):
        """Execute the buy booster API call."""
        pack_type = getattr(self, '_pending_booster_type', 'main')
        try:
            if pack_type == 'main':
                result = collection_service.buy_booster()
                self._boosters = result.get('booster_packs', self._boosters)
                if self.state.user_dict:
                    self.state.user_dict['booster_packs'] = self._boosters
            else:
                result = collection_service.buy_booster_side()
                self._boosters_side = result.get('booster_packs_side', self._boosters_side)
                if self.state.user_dict:
                    self.state.user_dict['booster_packs_side'] = self._boosters_side
            self._gold = result.get('gold', self._gold)
            if self.state.user_dict:
                self.state.user_dict['gold'] = self._gold
            self.state.set_msg('Booster pack purchased!')
        except Exception as e:
            logger.error(f'Buy booster failed: {e}')
            self.state.set_msg('Failed to buy booster pack')

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

        # Update reveal overlay
        if self._reveal_overlay:
            self._reveal_overlay.update()

        # Keep sell dialogue buttons hovered
        if self._sell_dialogue:
            for btn in self._sell_dialogue.buttons:
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
        if self.state.action['status'] in ('cancel', 'ok', 'close'):
            self.reset_action()
            return
        if self.dialogue_box:
            return

        for event in events:
            # Reveal overlay captures all input when active
            if self._reveal_overlay:
                if event.type == MOUSEBUTTONUP:
                    done = self._reveal_overlay.handle_click(event.pos)
                    if done:
                        self._reveal_overlay = None
                continue

            # Sell dialogue captures input
            if self._sell_dialogue:
                if event.type == MOUSEBUTTONUP:
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

            if self._handle_icon_events(event):
                continue

            # Click outside content box → back to game menu
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and not self._sell_dialogue
                    and not self._reveal_overlay
                    and not pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H).collidepoint(event.pos)):
                self.state.screen = 'game_menu'
                return

            if event.type == MOUSEBUTTONUP:
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

                # Card clicks (only within panel)
                if self._panel_rect.collidepoint(event.pos):
                    for rect, suit, rank, section in self._card_rects:
                        if rect.collidepoint(event.pos):
                            self._open_sell_dialogue(suit, rank)
                            break

            # Scroll wheel within panel
            if event.type == MOUSEWHEEL and self._panel_rect.collidepoint(pygame.mouse.get_pos()):
                scroll_speed = int(0.04 * _SH)
                self._scroll_y -= event.y * scroll_speed
                max_scroll = max(0, self._content_height - self._panel_rect.h)
                self._scroll_y = max(0, min(self._scroll_y, max_scroll))
