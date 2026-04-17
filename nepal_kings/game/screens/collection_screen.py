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
        self._toggle_font = settings.get_font(settings.COLLECTION_SUIT_LABEL_FONT_SIZE)
        self._action_font = settings.get_font(settings.COLLECTION_ACTION_BTN_FONT_SIZE)

        # ── Toggle state ────────────────────────────────────────────
        self._tab = 'main'  # 'main' or 'side'
        self._main_ranks = list(reversed(settings.RANKS_MAIN_CARDS))  # A,K,Q,J,10,9,8,7
        self._side_ranks = list(reversed(settings.RANKS_SIDE_CARDS))  # 6,5,4,3,2

        # ── Card data from server ───────────────────────────────────
        self._cards = {}       # {(suit,rank): quantity}
        self._gold = 0
        self._boosters = 0
        self._boosters_side = 0
        self._data_loaded = False

        # ── Build CardImg cache ─────────────────────────────────────
        cw, ch = settings.COLLECTION_CARD_W, settings.COLLECTION_CARD_H
        self._card_imgs = {}   # {(suit,rank): CardImg}
        for suit in settings.SUITS:
            for rank in settings.RANKS:
                self._card_imgs[(suit, rank)] = CardImg(self.window, suit, rank, cw, ch)

        # ── Grey overlay for unowned cards ──────────────────────────
        self._grey_overlay = pygame.Surface((cw, ch), pygame.SRCALPHA)
        self._grey_overlay.fill((0, 0, 0, settings.COLLECTION_GREY_ALPHA))

        # ── Toggle button rects ─────────────────────────────────────
        tw, th = settings.COLLECTION_TOGGLE_W, settings.COLLECTION_TOGGLE_H
        tg = settings.COLLECTION_TOGGLE_GAP
        total_tw = tw * 2 + tg
        tx = (_SW - total_tw) // 2
        ty = settings.COLLECTION_TOGGLE_Y
        self._toggle_main_rect = pygame.Rect(tx, ty, tw, th)
        self._toggle_side_rect = pygame.Rect(tx + tw + tg, ty, tw, th)

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

        # ── Action buttons (bottom) ─────────────────────────────────
        abw = settings.COLLECTION_ACTION_BTN_W
        abh = settings.COLLECTION_ACTION_BTN_H
        abg = settings.COLLECTION_ACTION_BTN_GAP
        aby = settings.COLLECTION_ACTION_BTN_Y
        total_ab = abw * 3 + abg * 2
        abx = (_SW - total_ab) // 2
        self._btn_open_rect = pygame.Rect(abx, aby, abw, abh)
        self._btn_buy_rect = pygame.Rect(abx + abw + abg, aby, abw, abh)
        self._btn_back_rect = pygame.Rect(abx + 2 * (abw + abg), aby, abw, abh)

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
            self._cards[(c['suit'], c['rank'])] = c.get('quantity', 0)
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

    def _current_ranks(self):
        return self._main_ranks if self._tab == 'main' else self._side_ranks

    def _compute_card_positions(self):
        """Compute (x, y, suit, rank) for each card in the grid."""
        ranks = self._current_ranks()
        suits = settings.SUITS
        cw = settings.COLLECTION_CARD_W
        ch = settings.COLLECTION_CARD_H
        gx = settings.COLLECTION_CARD_GAP_X
        gy = settings.COLLECTION_CARD_GAP_Y
        label_w = settings.COLLECTION_SUIT_LABEL_W
        px = self._panel_rect.x + settings.COLLECTION_PANEL_PAD_X
        py = self._panel_rect.y + settings.COLLECTION_PANEL_PAD_Y

        positions = []
        self._card_rects = []
        for row_i, suit in enumerate(suits):
            row_y = py + row_i * (ch + gy)
            for col_i, rank in enumerate(ranks):
                cx = px + label_w + col_i * (cw + gx)
                positions.append((cx, row_y, suit, rank))
                self._card_rects.append((pygame.Rect(cx, row_y, cw, ch), suit, rank))
        return positions

    # ── render ──────────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        # Title
        tx = (_SW - self._title_surf.get_width()) // 2
        self.window.blit(self._title_surf, (tx, settings.COLLECTION_TITLE_Y))

        # Toggle buttons
        self._draw_toggle(self._toggle_main_rect, 'Main Cards', self._tab == 'main')
        self._draw_toggle(self._toggle_side_rect, 'Side Cards', self._tab == 'side')

        # Card grid panel
        self.window.blit(self._panel_surf, self._panel_rect.topleft)
        self._draw_card_grid()

        # Action buttons
        self._draw_action_button(self._btn_open_rect, self._open_label(), self._can_open())
        self._draw_action_button(self._btn_buy_rect, self._buy_label(), self._can_buy())
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

    def _draw_toggle(self, rect, text, active):
        """Draw a tab-style toggle button."""
        bg = settings.COLLECTION_TOGGLE_ACTIVE_BG if active else settings.COLLECTION_TOGGLE_BG_CLR
        clr = settings.COLLECTION_TOGGLE_ACTIVE_CLR if active else settings.COLLECTION_TOGGLE_INACTIVE_CLR
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill(bg)
        pygame.draw.rect(surf, settings.COLLECTION_TOGGLE_BORDER_CLR, surf.get_rect(), 1)
        self.window.blit(surf, rect.topleft)
        txt = self._toggle_font.render(text, True, clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_card_grid(self):
        """Draw all cards in the current tab's grid."""
        positions = self._compute_card_positions()
        suits = settings.SUITS
        ranks = self._current_ranks()
        cw = settings.COLLECTION_CARD_W
        ch = settings.COLLECTION_CARD_H
        label_w = settings.COLLECTION_SUIT_LABEL_W
        px = self._panel_rect.x + settings.COLLECTION_PANEL_PAD_X
        py = self._panel_rect.y + settings.COLLECTION_PANEL_PAD_Y
        gy = settings.COLLECTION_CARD_GAP_Y

        # Suit labels
        for row_i, suit in enumerate(suits):
            row_y = py + row_i * (ch + gy)
            label = self._suit_font.render(suit[0], True, settings.COLLECTION_SUIT_LABEL_CLR)
            ly = row_y + (ch - label.get_height()) // 2
            self.window.blit(label, (px, ly))

        # Cards
        mouse_pos = pygame.mouse.get_pos()
        for (cx, cy, suit, rank) in positions:
            card = self._card_imgs.get((suit, rank))
            if not card:
                continue
            qty = self._cards.get((suit, rank), 0)
            card_rect = pygame.Rect(cx, cy, cw, ch)
            hovered = card_rect.collidepoint(mouse_pos)

            if qty > 0:
                if hovered and not self._sell_dialogue and not self._reveal_overlay:
                    card.draw_front_bright(cx, cy)
                    # Bright glow on hover
                    glow_surf = pygame.Surface((cw + 4, ch + 4), pygame.SRCALPHA)
                    pygame.draw.rect(glow_surf, (250, 221, 0, 80), glow_surf.get_rect(), 2)
                    self.window.blit(glow_surf, (cx - 2, cy - 2))
                else:
                    card.draw_front_bright(cx, cy)
                # Badge
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

    def _open_label(self):
        count = self._boosters if self._tab == 'main' else self._boosters_side
        return f'Open ({count})'

    def _buy_label(self):
        price = settings.BOOSTER_PACK_PRICE if self._tab == 'main' else settings.BOOSTER_PACK_SIDE_PRICE
        return f'Buy ({price}g)'

    def _can_open(self):
        count = self._boosters if self._tab == 'main' else self._boosters_side
        return count > 0

    def _can_buy(self):
        price = settings.BOOSTER_PACK_PRICE if self._tab == 'main' else settings.BOOSTER_PACK_SIDE_PRICE
        return self._gold >= price

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

    def _confirm_open_booster(self):
        """Show confirmation dialogue for opening a booster."""
        pack_type = 'main' if self._tab == 'main' else 'side'
        self.dialogue_box = DialogueBox(
            self.window,
            f'Open a {pack_type} booster pack?',
            actions=['open', 'cancel'],
            title='Open Booster')

    def _perform_open_booster(self):
        """Execute the open booster API call and show reveal overlay."""
        try:
            if self._tab == 'main':
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

    def _confirm_buy_booster(self):
        """Show confirmation dialogue for buying a booster."""
        price = settings.BOOSTER_PACK_PRICE if self._tab == 'main' else settings.BOOSTER_PACK_SIDE_PRICE
        pack_type = 'main' if self._tab == 'main' else 'side'
        self.dialogue_box = DialogueBox(
            self.window,
            f'Buy a {pack_type} booster pack for {price} gold?',
            actions=['buy', 'cancel'],
            title='Buy Booster')

    def _perform_buy_booster(self):
        """Execute the buy booster API call."""
        try:
            if self._tab == 'main':
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
                # Toggle buttons
                if self._toggle_main_rect.collidepoint(event.pos):
                    self._tab = 'main'
                    continue
                if self._toggle_side_rect.collidepoint(event.pos):
                    self._tab = 'side'
                    continue

                # Action buttons
                if self._btn_back_rect.collidepoint(event.pos):
                    self.state.screen = 'game_menu'
                    logger.debug("Back button clicked")
                    continue
                if self._btn_open_rect.collidepoint(event.pos):
                    if self._can_open():
                        self._confirm_open_booster()
                    else:
                        self.state.set_msg('No booster packs to open')
                    continue
                if self._btn_buy_rect.collidepoint(event.pos):
                    if self._can_buy():
                        self._confirm_buy_booster()
                    else:
                        self.state.set_msg('Not enough gold')
                    continue

                # Card clicks
                for rect, suit, rank in self._card_rects:
                    if rect.collidepoint(event.pos):
                        self._open_sell_dialogue(suit, rank)
                        break
