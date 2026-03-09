"""
Shared helpers for menu-style screens (game_menu, new_game, load_game).

Provides:
  _MenuIconButton  – lightweight icon button (home / logout)
  MenuScreenMixin  – mixin that adds background, gold display, icon buttons
  ListButton       – programmatically drawn list-item button (no image assets)
"""

import pygame
from config import settings


# ═══════════════════════════════════════════════════════════════════
#  _MenuIconButton
# ═══════════════════════════════════════════════════════════════════

class _MenuIconButton:
    """Lightweight icon button for menu screens (no game-state dependency)."""

    def __init__(self, window, x, y, symbol_name, action):
        self.window = window
        self.action = action

        _stone_sz  = settings.GAME_MENU_ICON_STONE_SZ
        _sym_sz    = settings.GAME_MENU_ICON_SYMBOL_SZ
        _sym_big   = settings.GAME_MENU_ICON_SYMBOL_BIG_SZ
        _glow_sz   = settings.GAME_MENU_ICON_GLOW_SZ
        _glow_big  = settings.GAME_MENU_ICON_GLOW_BIG_SZ
        _sym_path  = settings.GAME_MENU_ICON_SYMBOL_PATH
        _glow_path = settings.GAME_MENU_ICON_GLOW_PATH

        raw_stone = pygame.image.load(settings.GAME_MENU_ICON_STONE_PATH).convert_alpha()
        self.stone = pygame.transform.smoothscale(raw_stone, (_stone_sz, _stone_sz))

        raw_active  = pygame.image.load(_sym_path + symbol_name + '_active.png').convert_alpha()
        raw_passive = pygame.image.load(_sym_path + symbol_name + '_passive.png').convert_alpha()
        self.sym_active     = pygame.transform.smoothscale(raw_active,  (_sym_sz,  _sym_sz))
        self.sym_passive    = pygame.transform.smoothscale(raw_passive, (_sym_sz,  _sym_sz))
        self.sym_active_big = pygame.transform.smoothscale(raw_active,  (_sym_big, _sym_big))

        raw_gy = pygame.image.load(_glow_path + 'yellow.png').convert_alpha()
        raw_gw = pygame.image.load(_glow_path + 'white.png').convert_alpha()
        raw_gb = pygame.image.load(_glow_path + 'black.png').convert_alpha()
        self.glow_yellow     = pygame.transform.smoothscale(raw_gy, (_glow_sz,  _glow_sz))
        self.glow_white      = pygame.transform.smoothscale(raw_gw, (_glow_sz,  _glow_sz))
        self.glow_black      = pygame.transform.smoothscale(raw_gb, (_glow_sz,  _glow_sz))
        self.glow_yellow_big = pygame.transform.smoothscale(raw_gy, (_glow_big, _glow_big))

        self.rect = pygame.Rect(x, y, _stone_sz, _stone_sz)
        self.hovered = False
        self.clicked = False

    def _center(self, img):
        return img.get_rect(center=self.rect.center).topleft

    def collide(self):
        return self.rect.collidepoint(pygame.mouse.get_pos())

    def update(self):
        self.hovered = self.collide()
        self.clicked = self.hovered and pygame.mouse.get_pressed()[0]

    def draw(self):
        if self.hovered:
            if self.clicked:
                self.window.blit(self.glow_yellow_big, self._center(self.glow_yellow_big))
                self.window.blit(self.sym_active, self._center(self.sym_active))
            else:
                self.window.blit(self.glow_yellow, self._center(self.glow_yellow))
                self.window.blit(self.sym_active_big, self._center(self.sym_active_big))
        else:
            self.window.blit(self.glow_black, self._center(self.glow_black))
            self.window.blit(self.sym_active, self._center(self.sym_active))


# ═══════════════════════════════════════════════════════════════════
#  ListButton – fully programmatic, no background images
# ═══════════════════════════════════════════════════════════════════

class ListButton:
    """A list-item button drawn entirely with code (rounded rect + text).

    States:
      - idle:    dark semi-transparent fill, muted border
      - hovered: lighter fill, gold border, brighter text
      - clicked: even lighter fill (pressed feel)
    """

    def __init__(self, window, x, y, text, width=None, height=None):
        self.window = window
        self.text = text
        w = width  or settings.LIST_BTN_W
        h = height or settings.LIST_BTN_H
        self.rect = pygame.Rect(x, y, w, h)
        self.font = pygame.font.Font(settings.FONT_PATH, settings.LIST_BTN_FONT_SIZE)
        self.hovered = False
        self.clicked = False

    def collide(self):
        return self.rect.collidepoint(pygame.mouse.get_pos())

    def update(self):
        self.hovered = self.collide()
        self.clicked = self.hovered and pygame.mouse.get_pressed()[0]

    def draw(self):
        # Pick colours based on state
        if self.clicked:
            bg   = settings.LIST_BTN_BG_CLICK_CLR
            bdr  = settings.LIST_BTN_BORDER_HOVER_CLR
            txt  = settings.LIST_BTN_TEXT_HOVER_CLR
        elif self.hovered:
            bg   = settings.LIST_BTN_BG_HOVER_CLR
            bdr  = settings.LIST_BTN_BORDER_HOVER_CLR
            txt  = settings.LIST_BTN_TEXT_HOVER_CLR
        else:
            bg   = settings.LIST_BTN_BG_CLR
            bdr  = settings.LIST_BTN_BORDER_CLR
            txt  = settings.LIST_BTN_TEXT_CLR

        r = settings.LIST_BTN_CORNER_RADIUS

        # Background fill (with alpha)
        surf = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=r)
        self.window.blit(surf, self.rect.topleft)

        # Border
        pygame.draw.rect(self.window, bdr, self.rect,
                         settings.LIST_BTN_BORDER_W, border_radius=r)

        # Text (centred)
        text_surf = self.font.render(self.text, True, txt)
        self.window.blit(text_surf, text_surf.get_rect(center=self.rect.center))


# ═══════════════════════════════════════════════════════════════════
#  MenuScreenMixin  – background, gold, icon buttons
# ═══════════════════════════════════════════════════════════════════

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT


class MenuScreenMixin:
    """Mix into any Screen subclass to get the shared menu chrome.

    Call ``_init_menu_chrome()`` at the end of your ``__init__`` and
    ``_draw_menu_chrome()`` in your ``render()`` (before your own content)
    and ``_draw_menu_overlay()`` after your content.
    """

    def _init_menu_chrome(self):
        """Load background, gold display assets, and icon buttons."""
        # Background
        raw_bg = pygame.image.load(settings.GAME_MENU_BG_IMG_PATH).convert()
        self._bg = pygame.transform.smoothscale(raw_bg, (_SW, _SH))

        # Gold icon + font
        raw_gold = pygame.image.load(settings.GAME_MENU_GOLD_ICON_PATH).convert_alpha()
        sz = settings.GAME_MENU_GOLD_ICON_SZ
        self._gold_icon = pygame.transform.smoothscale(raw_gold, (sz, sz))
        self._gold_font = pygame.font.Font(settings.FONT_PATH, settings.GAME_MENU_GOLD_FONT_SIZE)

        # Icon buttons (top-right)
        stone_sz = settings.GAME_MENU_ICON_STONE_SZ
        logout_x = _SW - settings.GAME_MENU_ICON_RIGHT_MARGIN - stone_sz
        home_x   = logout_x - settings.GAME_MENU_ICON_GAP - stone_sz

        self._icon_home   = _MenuIconButton(self.window, home_x,   settings.GAME_MENU_ICON_TOP_Y, 'home',   'home')
        self._icon_logout = _MenuIconButton(self.window, logout_x, settings.GAME_MENU_ICON_TOP_Y, 'logout', 'logout')
        self._icon_buttons = [self._icon_home, self._icon_logout]

    # ── draw helpers ────────────────────────────────────────────────

    def _draw_menu_chrome(self):
        """Draw background + gold display.  Call FIRST in render()."""
        self.window.blit(self._bg, (0, 0))
        self._draw_gold()

    def _draw_menu_overlay(self):
        """Draw icon buttons + messages.  Call LAST in render()."""
        self.draw_msg()
        if self.dialogue_box:
            self.dialogue_box.draw()
        for ib in self._icon_buttons:
            ib.draw()

    def _draw_gold(self):
        """Gold icon + amount with a background box (upper-left)."""
        gold = 0
        if self.state.user_dict:
            gold = self.state.user_dict.get('gold', 0)

        icon_sz  = settings.GAME_MENU_GOLD_ICON_SZ
        pad_x    = settings.GAME_MENU_GOLD_BOX_PAD_X
        pad_y    = settings.GAME_MENU_GOLD_BOX_PAD_Y
        gap      = settings.GAME_MENU_GOLD_ICON_TEXT_GAP
        mx       = settings.GAME_MENU_GOLD_MARGIN_X
        my       = settings.GAME_MENU_GOLD_MARGIN_Y

        text_surf = self._gold_font.render(str(gold), True, settings.GAME_MENU_GOLD_TEXT_CLR)

        cw = icon_sz + gap + text_surf.get_width()
        ch = max(icon_sz, text_surf.get_height())
        bw = pad_x * 2 + cw
        bh = pad_y * 2 + ch

        box = pygame.Surface((bw, bh), pygame.SRCALPHA)
        box.fill(settings.GAME_MENU_GOLD_BOX_BG_CLR)
        pygame.draw.rect(box, settings.GAME_MENU_GOLD_BOX_BORDER_CLR,
                         box.get_rect(), settings.GAME_MENU_GOLD_BOX_BORDER_W)
        self.window.blit(box, (mx, my))

        ix = mx + pad_x
        iy = my + pad_y + (ch - icon_sz) // 2
        self.window.blit(self._gold_icon, (ix, iy))

        tx = ix + icon_sz + gap
        ty = my + pad_y + (ch - text_surf.get_height()) // 2
        self.window.blit(text_surf, (tx, ty))

    # ── update / event helpers ──────────────────────────────────────

    def _update_icon_buttons(self):
        for ib in self._icon_buttons:
            ib.update()

    def _handle_icon_events(self, event):
        """Handle MOUSEBUTTONUP for icon buttons.  Returns True if handled."""
        if event.type == pygame.MOUSEBUTTONUP:
            if self._icon_home.collide():
                self.state.screen = 'game_menu'
                return True
            if self._icon_logout.collide():
                self.state.screen = 'login'
                self.reset_action()
                self.state.user = None
                self.state.user_dict = None
                self.state.game = None
                self.state.set_msg('Logged out')
                return True
        return False
