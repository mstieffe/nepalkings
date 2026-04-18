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

# Sell price helpers (mirror server logic so we can preview locally)
_KEY_RANKS = ['J', 'Q', 'K', 'A']
_KEY_MULTIPLIER = 10

def _sell_price(rank, quantity=1):
    value = settings.RANK_TO_VALUE.get(rank, 0)
    if rank in _KEY_RANKS:
        return value * _KEY_MULTIPLIER * quantity
    return value * quantity


class CollectionScreen(MenuScreenMixin, Screen):
    """Full collection screen — card grid, sell dialogue, buy/open booster."""

    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── Fonts ───────────────────────────────────────────────────
        self._title_font = settings.get_font(settings.COLLECTION_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Collection', True, settings.COLLECTION_TITLE_CLR)
        self._suit_font = settings.get_font(settings.COLLECTION_SUIT_LABEL_FONT_SIZE)
        self._badge_font = settings.get_font(settings.COLLECTION_BADGE_FONT_SIZE, bold=True)
        self._section_font = settings.get_font(settings.COLLECTION_SUIT_LABEL_FONT_SIZE, bold=True)
        self._action_font = settings.get_font(settings.COLLECTION_ACTION_BTN_FONT_SIZE)

        # ── Card ranks ──────────────────────────────────────────────
        self._main_ranks = list(reversed(settings.RANKS_MAIN_CARDS))  # A,K,Q,J,10,9,8,7
        self._side_ranks = list(reversed(settings.RANKS_SIDE_CARDS))  # 6,5,4,3,2

        # ── Scroll offset for combined view ─────────────────────────
        self._scroll_y = 0
        self._content_height = 0  # computed in _compute_card_positions

        # ── Card data from server ───────────────────────────────────
        self._cards = {}       # {(suit,rank): quantity}
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

        # ── Card grid panel ─────────────────────────────────────────
        self._panel_rect = pygame.Rect(
            settings.COLLECTION_PANEL_X, settings.COLLECTION_PANEL_Y,
            settings.COLLECTION_PANEL_W,
            settings.COLLECTION_PANEL_BOTTOM - settings.COLLECTION_PANEL_Y)

        # Pre-render panel background
        self._panel_surf = pygame.Surface(
            (self._panel_rect.w, self._panel_rect.h), pygame.SRCALPHA)
        self._panel_surf.fill((20, 20, 25, 180))
        pygame.draw.rect(self._panel_surf, (80, 75, 65, 200),
                         self._panel_surf.get_rect(), 2)

        # Action buttons — 4 buttons: Open Main, Open Side, Buy Main, Buy Side + Back
        abw = settings.COLLECTION_ACTION_BTN_W
        abh = settings.COLLECTION_ACTION_BTN_H
        abg = settings.COLLECTION_ACTION_BTN_GAP
        aby = settings.COLLECTION_ACTION_BTN_Y
        # Narrower buttons to fit 5
        btn_w = int(abw * 0.85)
        total_ab = btn_w * 5 + abg * 4
        abx = (_SW - total_ab) // 2
        self._btn_open_main_rect = pygame.Rect(abx, aby, btn_w, abh)
        self._btn_open_side_rect = pygame.Rect(abx + btn_w + abg, aby, btn_w, abh)
        self._btn_buy_main_rect = pygame.Rect(abx + 2 * (btn_w + abg), aby, btn_w, abh)
        self._btn_buy_side_rect = pygame.Rect(abx + 3 * (btn_w + abg), aby, btn_w, abh)
        self._btn_back_rect = pygame.Rect(abx + 4 * (btn_w + abg), aby, btn_w, abh)

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

        # ── Booster reveal overlay ──────────────────────────────────
        self._reveal_overlay = None
        self._pending_booster_type = 'main'  # tracks which type for dialogue flow

        # ── Custom button glow ──────────────────────────────────────
        glow_w = int(abw * 1.3)
        glow_h = int(abh * 2.2)
        self._action_glows = {}
        for colour in ('yellow', 'white', 'orange'):
            raw = pygame.image.load(settings.GAME_MENU_GLOW_DIR + colour + '.png').convert_alpha()
            self._action_glows[colour] = pygame.transform.smoothscale(raw, (glow_w, glow_h))

        # Hover tracking for action buttons
        self._hovered_btn = None
        self._clicked_btn = None

    # ── data fetching ───────────────────────────────────────────────

    def _fetch_collection(self):
        """Start a background fetch of the collection data."""
        self._poller = BackgroundPoller(collection_service.fetch_collection_cards)
        self._poller.poll()

    def _apply_collection_data(self, data):
        """Apply fetched collection data dicts."""
        self._cards = {}
        for c in data.get('cards', []):
            self._cards[(c['suit'], c['rank'])] = c.get('total', c.get('quantity', 0))
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
        label_w = settings.COLLECTION_SUIT_LABEL_W
        px = self._panel_rect.x + settings.COLLECTION_PANEL_PAD_X
        py = self._panel_rect.y + settings.COLLECTION_PANEL_PAD_Y

        section_header_h = int(0.035 * _SH)
        section_gap_x = int(0.02 * _SW)   # horizontal gap between main and side sections

        positions = []
        self._card_rects = []
        self._section_headers = []  # [(x, y, text), ...]

        # Apply scroll offset
        offset_y = -self._scroll_y

        # X origin for cards (after suit labels)
        cards_x = px + label_w

        # Main section header & side section header on same row
        header_y = py + offset_y
        main_header_x = cards_x
        main_right_edge = cards_x + len(self._main_ranks) * (cw + gx) - gx
        side_x = main_right_edge + section_gap_x
        side_header_x = side_x

        self._section_headers.append((main_header_x, header_y, 'Main Cards'))
        self._section_headers.append((side_header_x, header_y, 'Side Cards'))

        # Card rows start below headers
        cur_y = header_y + section_header_h

        for row_i, suit in enumerate(suits):
            row_y = cur_y + row_i * (ch + gy) + offset_y if row_i > 0 else cur_y
            if row_i > 0:
                row_y = cur_y + row_i * (ch + gy)
            else:
                row_y = cur_y

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

        last_row_bottom = cur_y + len(suits) * (ch + gy)

        # Total content height (for scroll clamping)
        self._content_height = (last_row_bottom + self._scroll_y) - py

        return positions

    # ── render ──────────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        # Title
        tx = (_SW - self._title_surf.get_width()) // 2
        self.window.blit(self._title_surf, (tx, settings.COLLECTION_TITLE_Y))

        # Card grid panel
        self.window.blit(self._panel_surf, self._panel_rect.topleft)

        # Clip to panel area for scrollable content
        self.window.set_clip(self._panel_rect)
        self._draw_card_grid()
        self.window.set_clip(None)

        # Action buttons
        self._draw_action_button(self._btn_open_main_rect,
                                 f'Open Main ({self._boosters})', self._boosters > 0)
        self._draw_action_button(self._btn_open_side_rect,
                                 f'Open Side ({self._boosters_side})', self._boosters_side > 0)
        self._draw_action_button(self._btn_buy_main_rect,
                                 f'Buy Main ({settings.BOOSTER_PACK_PRICE}g)',
                                 self._gold >= settings.BOOSTER_PACK_PRICE)
        self._draw_action_button(self._btn_buy_side_rect,
                                 f'Buy Side ({settings.BOOSTER_PACK_SIDE_PRICE}g)',
                                 self._gold >= settings.BOOSTER_PACK_SIDE_PRICE)
        self._draw_action_button(self._btn_back_rect, 'Back', True)

        # Sell dialogue
        if self._sell_dialogue:
            self._sell_dialogue.draw()
            self._draw_sell_qty_overlay()

        # Booster reveal overlay
        if self._reveal_overlay:
            self._reveal_overlay.draw()

        # Icon buttons + messages overlay
        self._draw_menu_overlay()

    def _draw_card_grid(self):
        """Draw all cards in both sections with section headers."""
        positions = self._compute_card_positions()
        cw = settings.COLLECTION_CARD_W
        ch = settings.COLLECTION_CARD_H
        label_w = settings.COLLECTION_SUIT_LABEL_W
        px = self._panel_rect.x + settings.COLLECTION_PANEL_PAD_X

        # Section headers (x, y, text)
        for header_x, header_y, header_text in self._section_headers:
            if self._panel_rect.y <= header_y <= self._panel_rect.bottom:
                header_surf = self._section_font.render(header_text, True, (250, 221, 0))
                self.window.blit(header_surf, (header_x, header_y))

        # Suit labels — draw once per suit row (main + side share the row)
        drawn_suit_rows = set()
        for (cx, cy, suit, rank, section) in positions:
            row_key = (suit, cy)
            if row_key not in drawn_suit_rows and section == 'main' and rank == self._main_ranks[0]:
                drawn_suit_rows.add(row_key)
                if self._panel_rect.y <= cy <= self._panel_rect.bottom:
                    label = self._suit_font.render(suit[0], True, settings.COLLECTION_SUIT_LABEL_CLR)
                    ly = cy + (ch - label.get_height()) // 2
                    self.window.blit(label, (px, ly))

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
            card_rect = pygame.Rect(cx, cy, cw, ch)
            hovered = card_rect.collidepoint(mouse_pos) and not self._sell_dialogue and not self._reveal_overlay

            if qty > 0:
                if hovered:
                    card.draw_front_bright(cx, cy)
                    glow_surf = pygame.Surface((cw + 4, ch + 4), pygame.SRCALPHA)
                    pygame.draw.rect(glow_surf, (250, 221, 0, 80), glow_surf.get_rect(), 2)
                    self.window.blit(glow_surf, (cx - 2, cy - 2))
                else:
                    card.draw_front_bright(cx, cy)
                self._draw_card_badge(cx, cy, cw, qty)
            else:
                card.draw_front_bright(cx, cy)
                self.window.blit(self._grey_overlay, (cx, cy))

    def _draw_card_badge(self, cx, cy, cw, qty):
        """Draw ×N badge at the bottom-right of a card."""
        badge_text = f'×{qty}'
        badge_surf = self._badge_font.render(badge_text, True, settings.COLLECTION_BADGE_CLR)
        bw = badge_surf.get_width() + settings.COLLECTION_BADGE_PAD_X * 2
        bh = badge_surf.get_height() + settings.COLLECTION_BADGE_PAD_Y * 2
        bx = cx + cw - bw - 2
        by = cy + settings.COLLECTION_CARD_H - bh - 2
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        bg.fill(settings.COLLECTION_BADGE_BG_CLR)
        self.window.blit(bg, (bx, by))
        self.window.blit(badge_surf, (bx + settings.COLLECTION_BADGE_PAD_X,
                                      by + settings.COLLECTION_BADGE_PAD_Y))

    def _draw_action_button(self, rect, text, enabled):
        """Draw one of the bottom action buttons."""
        mouse_pos = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse_pos) and not self._sell_dialogue and not self._reveal_overlay
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

    # ── sell dialogue ───────────────────────────────────────────────

    def _open_sell_dialogue(self, suit, rank):
        """Open the sell dialogue for a card."""
        qty = self._cards.get((suit, rank), 0)
        if qty <= 0:
            return
        self._sell_card = (suit, rank)
        self._sell_qty = 1
        self._sell_max = qty
        unit_price = _sell_price(rank, 1)
        card_img = self._card_imgs.get((suit, rank))
        images = [card_img] if card_img else []
        msg = f'Sell {suit} {rank}?'
        after_msg = f'Price: {self._sell_qty} × {unit_price} = {unit_price * self._sell_qty} gold'
        self._sell_dialogue = DialogueBox(
            self.window, msg, actions=['sell', 'cancel'],
            images=images, title='Sell Card',
            message_after_images=after_msg)

    def _update_sell_after_text(self):
        """Rebuild the after-images text when quantity changes."""
        if not self._sell_card:
            return
        _, rank = self._sell_card
        unit_price = _sell_price(rank, 1)
        total = unit_price * self._sell_qty
        new_text = f'< {self._sell_qty} >  ×  {unit_price} = {total} gold'
        _max_text_w = settings.DIALOGUE_BOX_WIDTH - int(0.08 * _SW)
        self._sell_dialogue.after_lines = DialogueBox._wrap_text(
            new_text, self._sell_dialogue.font, _max_text_w)
        self._sell_dialogue.after_lines_surfaces = [
            self._sell_dialogue.font.render(l, True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            for l in self._sell_dialogue.after_lines]

    def _draw_sell_qty_overlay(self):
        """Draw quantity selector arrows over the sell dialogue."""
        # The quantity text is already rendered via after_lines — the < > arrows
        # are embedded in the text itself, so no separate overlay needed.
        pass

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

    # ── booster flows ───────────────────────────────────────────────

    def _confirm_open_booster(self, pack_type='main'):
        """Show confirmation dialogue for opening a booster."""
        self._pending_booster_type = pack_type
        self.dialogue_box = DialogueBox(
            self.window,
            f'Open a {pack_type} booster pack?',
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
            self._reveal_overlay = BoosterRevealOverlay(self.window, drawn_cards)
        except Exception as e:
            logger.error(f'Open booster failed: {e}')
            self.state.set_msg('Failed to open booster pack')

    def _confirm_buy_booster(self, pack_type='main'):
        """Show confirmation dialogue for buying a booster."""
        self._pending_booster_type = pack_type
        price = settings.BOOSTER_PACK_PRICE if pack_type == 'main' else settings.BOOSTER_PACK_SIDE_PRICE
        self.dialogue_box = DialogueBox(
            self.window,
            f'Buy a {pack_type} booster pack for {price} gold?',
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

        # Check background poller
        if self._poller and self._poller.has_result():
            try:
                self._apply_collection_data(self._poller.result)
            except Exception as e:
                logger.error(f'Failed to apply collection data: {e}')
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
                    response = self._sell_dialogue.update([event])
                    if response == 'sell':
                        self._perform_sell()
                    elif response == 'cancel':
                        self._sell_card = None
                        self._sell_dialogue = None
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

            if event.type == MOUSEBUTTONUP:
                # Action buttons
                if self._btn_back_rect.collidepoint(event.pos):
                    self.state.screen = 'game_menu'
                    logger.debug("Back button clicked")
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
