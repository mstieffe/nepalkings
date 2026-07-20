# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
Shared helpers for menu-style screens (game_menu, new_game, load_game).

Provides:
  _MenuIconButton  – lightweight icon button (home / logout)
  MenuScreenMixin  – mixin that adds background, gold display, icon buttons
  ListButton       – programmatically drawn list-item button (no image assets)
"""

import os
from datetime import datetime, timezone

import pygame
from config import settings
from game.components.coach_card import draw_coach_button, draw_coach_panel
from game.components.floating_text import FloatingText, FloatingTextLayer
from game.core.input_state import get_pressed as _get_pressed
from utils import onboarding_service


_MENU_COACH_STEP_UNSET = object()


# ═══════════════════════════════════════════════════════════════════
#  _MenuIconButton
# ═══════════════════════════════════════════════════════════════════

class _MenuIconButton:
    """Lightweight icon button for menu screens (no game-state dependency)."""

    # Class-level cache: shared stone & glow images (loaded once for all instances)
    _shared_cache = {}

    @classmethod
    def _load_shared(cls):
        """Load stone and glow images once, return cached dict."""
        if not cls._shared_cache:
            _stone_sz = settings.GAME_MENU_ICON_STONE_SZ
            _glow_sz  = settings.GAME_MENU_ICON_GLOW_SZ
            _glow_big = settings.GAME_MENU_ICON_GLOW_BIG_SZ
            _glow_path = settings.GAME_MENU_ICON_GLOW_PATH

            raw_stone = pygame.image.load(settings.GAME_MENU_ICON_STONE_PATH).convert_alpha()
            raw_gy = pygame.image.load(_glow_path + 'yellow.png').convert_alpha()
            raw_gw = pygame.image.load(_glow_path + 'white.png').convert_alpha()
            raw_gb = pygame.image.load(_glow_path + 'black.png').convert_alpha()

            cls._shared_cache = {
                'stone':          pygame.transform.smoothscale(raw_stone, (_stone_sz, _stone_sz)),
                'glow_yellow':    pygame.transform.smoothscale(raw_gy, (_glow_sz,  _glow_sz)),
                'glow_white':     pygame.transform.smoothscale(raw_gw, (_glow_sz,  _glow_sz)),
                'glow_black':     pygame.transform.smoothscale(raw_gb, (_glow_sz,  _glow_sz)),
                'glow_yellow_big': pygame.transform.smoothscale(raw_gy, (_glow_big, _glow_big)),
            }
        return cls._shared_cache

    def __init__(self, window, x, y, symbol_name, action):
        self.window = window
        self.action = action

        _stone_sz  = settings.GAME_MENU_ICON_STONE_SZ
        _sym_sz    = settings.GAME_MENU_ICON_SYMBOL_SZ
        _sym_big   = settings.GAME_MENU_ICON_SYMBOL_BIG_SZ
        _sym_path  = settings.GAME_MENU_ICON_SYMBOL_PATH

        shared = self._load_shared()
        self.stone           = shared['stone']
        self.glow_yellow     = shared['glow_yellow']
        self.glow_white      = shared['glow_white']
        self.glow_black      = shared['glow_black']
        self.glow_yellow_big = shared['glow_yellow_big']

        active_path = _sym_path + symbol_name + '_active.png'
        passive_path = _sym_path + symbol_name + '_passive.png'
        if not os.path.exists(passive_path):
            passive_path = active_path
        raw_active  = pygame.image.load(active_path).convert_alpha()
        raw_passive = pygame.image.load(passive_path).convert_alpha()
        self.sym_active     = pygame.transform.smoothscale(raw_active,  (_sym_sz,  _sym_sz))
        self.sym_passive    = pygame.transform.smoothscale(raw_passive, (_sym_sz,  _sym_sz))
        self.sym_active_big = pygame.transform.smoothscale(raw_active,  (_sym_big, _sym_big))

        self.rect = pygame.Rect(x, y, _stone_sz, _stone_sz)
        self.hovered = False
        self.clicked = False

    def _center(self, img):
        return img.get_rect(center=self.rect.center).topleft

    def collide(self):
        return self.rect.collidepoint(pygame.mouse.get_pos())

    def update(self):
        self.hovered = self.collide()
        self.clicked = self.hovered and _get_pressed()[0]

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
        self.font = settings.get_font(settings.LIST_BTN_FONT_SIZE)
        self.hovered = False
        self.clicked = False

    def collide(self):
        return self.rect.collidepoint(pygame.mouse.get_pos())

    def update(self):
        self.hovered = self.collide()
        self.clicked = self.hovered and _get_pressed()[0]

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


def menu_chrome_safe_top(default_y, extra_gap=None):
    """Return a y-position that clears the persistent top-left item strip."""
    if settings.TOUCH_TARGET_MIN <= 0:
        return int(default_y)
    row_h = max(settings.GAME_MENU_GOLD_ICON_SZ,
                settings.GAME_MENU_GOLD_FONT_SIZE)
    hud_bottom = (
        settings.GAME_MENU_GOLD_MARGIN_Y
        + 2 * settings.GAME_MENU_GOLD_BOX_PAD_Y
        + row_h
    )
    gap = extra_gap if extra_gap is not None else max(6, int(0.012 * _SH))
    return max(int(default_y), int(hud_bottom + gap))


def menu_chrome_safe_width(x, default_w, extra_gap=None):
    """Return a panel width that clears the persistent right-side icon rail."""
    if settings.TOUCH_TARGET_MIN <= 0:
        return int(default_w)
    gap = extra_gap if extra_gap is not None else max(8, int(0.012 * _SW))
    rail_left = (
        _SW
        - settings.GAME_MENU_ICON_RIGHT_MARGIN
        - settings.GAME_MENU_ICON_STONE_SZ
    )
    max_right = rail_left - gap
    min_w = max(1, int(0.50 * _SW))
    if max_right <= x + min_w:
        return int(default_w)
    return max(1, min(int(default_w), int(max_right - x)))


class MenuScreenMixin:
    """Mix into any Screen subclass to get the shared menu chrome.

    Call ``_init_menu_chrome()`` at the end of your ``__init__`` and
    ``_draw_menu_chrome()`` in your ``render()`` (before your own content)
    and ``_draw_menu_overlay()`` after your content.
    """

    # Class-level cache: background + gold icon loaded once, shared by all screens
    _chrome_cache = {}

    @classmethod
    def _load_chrome_cache(cls):
        """Load background and gold icon once, return cached dict."""
        if not cls._chrome_cache:
            raw_bg = pygame.image.load(settings.GAME_MENU_BG_IMG_PATH).convert()
            raw_gold = pygame.image.load(settings.GAME_MENU_GOLD_ICON_PATH).convert_alpha()
            raw_booster = pygame.image.load(settings.GAME_MENU_BOOSTER_ICON_PATH).convert_alpha()
            raw_booster_side = pygame.image.load(settings.GAME_MENU_BOOSTER_SIDE_ICON_PATH).convert_alpha()
            raw_map = pygame.image.load(settings.GAME_MENU_MAP_ICON_PATH).convert_alpha()
            sz = settings.GAME_MENU_GOLD_ICON_SZ
            # Larger version used by dialogue boxes / pack panels so the icon
            # stays crisp instead of being upscaled from the small HUD size.
            dialog_sz = max(sz, settings.DIALOGUE_BOX_IMG_HEIGHT)
            cls._chrome_cache = {
                'bg':                  pygame.transform.smoothscale(raw_bg, (_SW, _SH)),
                'gold':                pygame.transform.smoothscale(raw_gold, (sz, sz)),
                'booster':             pygame.transform.smoothscale(raw_booster, (sz, sz)),
                'booster_side':        pygame.transform.smoothscale(raw_booster_side, (sz, sz)),
                'map':                 pygame.transform.smoothscale(raw_map, (sz, sz)),
                'booster_dialog':      pygame.transform.smoothscale(
                    raw_booster, (dialog_sz, dialog_sz)),
                'booster_side_dialog': pygame.transform.smoothscale(
                    raw_booster_side, (dialog_sz, dialog_sz)),
                'map_dialog':          pygame.transform.smoothscale(
                    raw_map, (dialog_sz, dialog_sz)),
            }
        return cls._chrome_cache

    def _init_menu_chrome(self):
        """Load background, gold display assets, and icon buttons."""
        cache = self._load_chrome_cache()
        self._bg = cache['bg']
        self._gold_icon = cache['gold']
        self._booster_icon = cache['booster']
        self._booster_side_icon = cache['booster_side']
        self._map_icon = cache['map']
        self._booster_icon_dialog = cache['booster_dialog']
        self._booster_side_icon_dialog = cache['booster_side_dialog']
        self._map_icon_dialog = cache['map_dialog']
        self._gold_font = settings.get_font(settings.GAME_MENU_GOLD_FONT_SIZE)
        self._gold_floaters = FloatingTextLayer()
        self._gold_floaters_last_tick = pygame.time.get_ticks()
        self._onboarding_reward_floaters = FloatingTextLayer()
        self._onboarding_reward_floaters_last_tick = pygame.time.get_ticks()
        self._last_seen_gold = self._current_gold_amount()
        # Optional one-shot controls for the next automatic top-bar gold
        # floater. Screens that show their own collect animation can suppress
        # or re-anchor the shared HUD floater to avoid duplicates.
        self._suppress_next_gold_gain_floater = False
        self._next_gold_gain_floater_pos = None
        self._onboarding_guide_open = False
        self._onboarding_guide_tab = 'journey'
        self._onboarding_guide_tab_rects = {}
        self._guide_rulebook = None
        self._onboarding_guide_buttons = []
        self._onboarding_guide_font = settings.get_font(
            settings.mobile_font_size(
                max(16, int(0.020 * _SH)), settings.FS_BODY))
        self._onboarding_guide_small_font = settings.get_font(
            settings.mobile_font_size(
                max(14, int(0.017 * _SH)), settings.FS_SMALL))
        self._onboarding_guide_title_font = settings.get_font(
            settings.mobile_font_size(
                max(24, int(0.034 * _SH)), settings.FS_TITLE), bold=True)
        self._onboarding_guide_section_font = settings.get_font(
            settings.mobile_font_size(
                max(18, int(0.023 * _SH)), settings.FS_HEADING), bold=True)
        self._onboarding_guide_badge_font = settings.get_font(
            settings.mobile_font_size(
                max(16, int(0.020 * _SH)), settings.FS_BODY), bold=True)
        self._onboarding_guide_icon_cache = {}
        self._onboarding_guide_item_rects = {}
        self._onboarding_guide_section_header_rects = {}
        self._onboarding_guide_close_rect = pygame.Rect(0, 0, 0, 0)
        self._onboarding_guide_scroll = 0
        self._onboarding_guide_scroll_area = None
        self._onboarding_guide_content_h = 0
        self._onboarding_guide_scrollbar_rect = pygame.Rect(0, 0, 0, 0)
        self._onboarding_guide_scrollbar_thumb_rect = pygame.Rect(0, 0, 0, 0)
        self._onboarding_guide_touch_scrolling = False
        self._onboarding_guide_touch_last_y = 0
        self._onboarding_guide_touch_moved = 0
        self._user_item_display_rect = pygame.Rect(0, 0, 0, 0)
        self._menu_coach_buttons = []
        self._menu_coach_step = None
        self._menu_coach_pressed_button_action = None
        self._menu_coach_font = settings.get_font(settings.mobile_font_size(
            max(14, int(0.018 * _SH)), settings.FS_SMALL))
        self._menu_coach_title_font = settings.get_font(
            settings.mobile_font_size(
                max(16, int(0.024 * _SH)), settings.FS_BODY), bold=True)
        self._menu_chrome_username = self._current_menu_username()

        # Icon buttons (top-right): home and guide at top, settings at
        # bottom, logout just above settings.
        stone_sz = settings.GAME_MENU_ICON_STONE_SZ
        home_x   = _SW - settings.GAME_MENU_ICON_RIGHT_MARGIN - stone_sz
        home_y   = settings.GAME_MENU_ICON_TOP_Y

        self._icon_home   = _MenuIconButton(self.window, home_x,   home_y,   'home',   'home')
        guide_gap = getattr(settings, 'GAME_MENU_ICON_LOGOUT_GAP_Y', int(0.006 * _SH))
        guide_y = home_y + stone_sz + guide_gap
        self._icon_guide = _MenuIconButton(self.window, home_x, guide_y, 'guide', 'guide')

        # Settings icon (bottom-right)
        settings_x = _SW - settings.GAME_MENU_ICON_RIGHT_MARGIN - stone_sz
        settings_y = _SH - settings.GAME_MENU_ICON_RIGHT_MARGIN - stone_sz
        self._icon_settings = _MenuIconButton(self.window, settings_x, settings_y, 'settings', 'settings')

        # Logout icon just above settings
        logout_gap = getattr(settings, 'GAME_MENU_ICON_LOGOUT_GAP_Y', int(0.006 * _SH))
        logout_x = settings_x
        logout_y = settings_y - stone_sz - logout_gap
        self._icon_logout = _MenuIconButton(self.window, logout_x, logout_y, 'logout', 'logout')

        self._icon_buttons = [self._icon_settings, self._icon_home,
                              self._icon_guide, self._icon_logout]

    # ── draw helpers ────────────────────────────────────────────────

    def _draw_menu_chrome(self):
        """Draw background + gold display + booster pack display.  Call FIRST in render()."""
        self._sync_menu_user_context()
        self.window.blit(self._bg, (0, 0))
        self._draw_gold()
        self._draw_booster_packs()

    def _draw_menu_overlay(self):
        """Draw icon buttons + messages.  Call LAST in render()."""
        self.draw_msg()
        if self.dialogue_box:
            self.dialogue_box.draw()
        for ib in self._icon_buttons:
            ib.draw()
        self._draw_onboarding_guide_badge()
        self._draw_gold_floaters()
        self._draw_logout_dialogue()
        if self._onboarding_guide_open:
            self._draw_onboarding_guide()
        self._draw_onboarding_reward_floaters()

    def _draw_gold(self):
        """Gold + booster pack icons in one horizontal box (upper-left)."""
        ud = self.state.user_dict or {}
        gold = ud.get('gold', 0)
        bpacks = ud.get('booster_packs', 0)
        bpacks_side = ud.get('booster_packs_side', 0)
        maps = ud.get('maps', 0)

        icon_sz = settings.GAME_MENU_GOLD_ICON_SZ
        pad_x   = settings.GAME_MENU_GOLD_BOX_PAD_X
        pad_y   = settings.GAME_MENU_GOLD_BOX_PAD_Y
        gap     = settings.GAME_MENU_GOLD_ICON_TEXT_GAP
        mx      = settings.GAME_MENU_GOLD_MARGIN_X
        my      = settings.GAME_MENU_GOLD_MARGIN_Y
        sep     = int(0.018 * _SW)  # separator between items

        items = [
            (self._gold_icon,         str(gold)),
            (self._booster_icon,      str(bpacks)),
            (self._booster_side_icon, str(bpacks_side)),
            (self._map_icon,          str(maps)),
        ]

        # Pre-render text surfaces
        text_surfs = [self._gold_font.render(txt, True, settings.GAME_MENU_GOLD_TEXT_CLR)
                      for _, txt in items]

        # Compute total content width and row height
        total_w = 0
        row_h = 0
        for i, (icon, _) in enumerate(items):
            ts = text_surfs[i]
            total_w += icon_sz + gap + ts.get_width()
            row_h = max(row_h, icon_sz, ts.get_height())
        total_w += sep * (len(items) - 1)

        bw = pad_x * 2 + total_w
        bh = pad_y * 2 + row_h
        self._user_item_display_rect = pygame.Rect(mx, my, bw, bh)

        # Draw box background
        box = pygame.Surface((bw, bh), pygame.SRCALPHA)
        box.fill(settings.GAME_MENU_GOLD_BOX_BG_CLR)
        pygame.draw.rect(box, settings.GAME_MENU_GOLD_BOX_BORDER_CLR,
                         box.get_rect(), settings.GAME_MENU_GOLD_BOX_BORDER_W)
        self.window.blit(box, (mx, my))

        # Draw each icon + text pair
        cx = mx + pad_x
        gold_floater_pos = None
        for i, (icon, _) in enumerate(items):
            ts = text_surfs[i]
            iy = my + pad_y + (row_h - icon_sz) // 2
            self.window.blit(icon, (cx, iy))
            tx = cx + icon_sz + gap
            ty = my + pad_y + (row_h - ts.get_height()) // 2
            self.window.blit(ts, (tx, ty))
            if i == 0:
                gold_floater_pos = (tx + ts.get_width() // 2, my + bh + int(0.012 * _SH))
            cx = tx + ts.get_width() + sep

        self._maybe_spawn_gold_gain_floater(gold, gold_floater_pos)

    def _current_gold_amount(self):
        state = getattr(self, 'state', None)
        ud = getattr(state, 'user_dict', None) or {}
        try:
            return int(ud.get('gold', 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _suppress_next_gold_floater(self):
        """Skip the next automatic top-bar gold gain floater exactly once."""
        self._suppress_next_gold_gain_floater = True

    def _set_next_gold_floater_pos(self, pos):
        """Override the next automatic top-bar gold floater start position."""
        if pos is None:
            self._next_gold_gain_floater_pos = None
            return
        self._next_gold_gain_floater_pos = (int(pos[0]), int(pos[1]))

    def _maybe_spawn_gold_gain_floater(self, current_gold, start_pos):
        try:
            current_gold = int(current_gold or 0)
        except (TypeError, ValueError):
            current_gold = 0
        previous_gold = getattr(self, '_last_seen_gold', None)
        self._last_seen_gold = current_gold
        if previous_gold is None or current_gold <= previous_gold:
            return
        if getattr(self, '_suppress_next_gold_gain_floater', False):
            self._suppress_next_gold_gain_floater = False
            self._next_gold_gain_floater_pos = None
            return
        floater_pos = getattr(self, '_next_gold_gain_floater_pos', None) or start_pos
        self._next_gold_gain_floater_pos = None
        if not floater_pos:
            return
        self._spawn_gold_gain_floater(current_gold - previous_gold, floater_pos)

    def _spawn_gold_gain_floater(self, amount, start_pos):
        layer = getattr(self, '_gold_floaters', None)
        if layer is None:
            return
        font = settings.get_font(getattr(settings, 'COLLECT_FLOAT_FONT_SIZE', settings.GAME_MENU_GOLD_FONT_SIZE))
        layer.add(FloatingText(
            f'+{int(amount)}g',
            start_pos,
            color=getattr(settings, 'COLLECT_FLOAT_GOLD_CLR', settings.GAME_MENU_GOLD_TEXT_CLR),
            duration_ms=getattr(settings, 'COLLECT_FLOAT_DURATION_MS', 900),
            rise_px=getattr(settings, 'COLLECT_FLOAT_RISE_PX', int(0.07 * _SH)),
            font=font,
            jitter_px=5,
        ))

    def _draw_gold_floaters(self):
        layer = getattr(self, '_gold_floaters', None)
        if layer is None:
            return
        now = pygame.time.get_ticks()
        last_tick = getattr(self, '_gold_floaters_last_tick', now)
        self._gold_floaters_last_tick = now
        layer.update(max(0, now - last_tick))
        layer.draw(self.window)

    def _spawn_onboarding_reward_floaters(self, reward, start_pos):
        layer = getattr(self, '_onboarding_reward_floaters', None)
        if layer is None or not start_pos:
            return
        font_size = getattr(settings, 'COLLECT_FLOAT_FONT_SIZE', settings.GAME_MENU_GOLD_FONT_SIZE)
        font = settings.get_font(font_size, bold=True)
        fallback_color = settings.GAME_MENU_GOLD_TEXT_CLR
        gold_color = getattr(settings, 'COLLECT_FLOAT_GOLD_CLR', fallback_color)
        item_color = getattr(settings, 'COLLECT_FLOAT_XP_CLR', fallback_color)
        entries = [
            ('gold', '+{amount}g', gold_color),
            ('booster_packs', '+{amount} Main Pack{suffix}', item_color),
            ('booster_packs_side', '+{amount} Side Pack{suffix}', item_color),
            ('maps', '+{amount} Map{suffix}', item_color),
        ]
        delay_step = int(getattr(settings, 'COLLECT_FLOAT_STAGGER_MS', 80))
        delay_ms = 0
        for key, template, color in entries:
            amount = int((reward or {}).get(key) or 0)
            if amount <= 0:
                continue
            suffix = '' if amount == 1 else 's'
            text = template.format(amount=amount, suffix=suffix)
            layer.add(FloatingText(
                text,
                start_pos,
                color=color,
                duration_ms=getattr(settings, 'COLLECT_FLOAT_DURATION_MS', 900),
                rise_px=getattr(settings, 'COLLECT_FLOAT_RISE_PX', int(0.07 * _SH)),
                font=font,
                delay_ms=delay_ms,
            ))
            delay_ms += delay_step

    def _draw_onboarding_reward_floaters(self):
        layer = getattr(self, '_onboarding_reward_floaters', None)
        if layer is None:
            return
        now = pygame.time.get_ticks()
        last_tick = getattr(self, '_onboarding_reward_floaters_last_tick', now)
        self._onboarding_reward_floaters_last_tick = now
        layer.update(max(0, now - last_tick))
        layer.draw(self.window)

    def _draw_booster_packs(self):
        """No-op — boosters are now drawn inside _draw_gold."""
        pass

    # ── update / event helpers ──────────────────────────────────────

    def _update_icon_buttons(self):
        for ib in self._icon_buttons:
            ib.update()

    def _handle_icon_events(self, event):
        """Handle MOUSEBUTTONUP for icon buttons.  Returns True if handled."""
        self._sync_menu_user_context()
        if getattr(self, '_onboarding_guide_open', False):
            self._handle_onboarding_guide_events([event])
            return True
        # If logout dialogue is active, route all events to it
        if hasattr(self, '_logout_dialogue') and self._logout_dialogue:
            self._update_logout_dialogue([event])
            return True
        if event.type == pygame.MOUSEBUTTONUP:
            if self._icon_guide.collide():
                from utils import sound
                sound.play('ui_click')
                self._open_onboarding_guide()
                return True
            if self._icon_settings.collide():
                from utils import sound
                sound.play('ui_click')
                self.state.screen = 'settings'
                return True
            if self._icon_home.collide():
                from utils import sound
                sound.play('ui_back')
                self.state.screen = 'game_menu'
                return True
            if self._icon_logout.collide():
                # Show confirmation dialogue instead of instant logout
                from game.components.dialogue_box import DialogueBox
                self._logout_dialogue = DialogueBox(
                    self.window,
                    'Are you sure you want to log out?',
                    actions=['yes', 'no'],
                    icon='question',
                    title='Logout'
                )
                return True
        return False

    def _update_logout_dialogue(self, events):
        """Process the logout confirmation dialogue. Returns True if active."""
        if not hasattr(self, '_logout_dialogue') or self._logout_dialogue is None:
            return False
        response = self._logout_dialogue.update(events)
        if response == 'yes':
            self._logout_dialogue = None
            from utils import http_compat as _http
            _http.clear_auth_token()
            self.state.screen = 'login'
            self.reset_action()
            self.state.user = None
            self.state.user_dict = None
            self.state.game = None
            self.state.pending_spell_cast = None
            self.state.pending_conquer_prelude_target = None
            self.state._notified_accepted_challenges = set()
            self.state._pending_accepted_challenge = None
            self.state.set_msg('Logged out')
            self._menu_chrome_username = None
            self._onboarding_guide_open = False
            self._reset_onboarding_guide_scroll()
            if hasattr(self, '_welcome_present_dialogue'):
                self._welcome_present_dialogue = None
            if hasattr(self, '_welcome_dialogue_opened'):
                self._welcome_dialogue_opened = False
            if hasattr(self, '_badge_poller'):
                self._badge_poller = None
        elif response is not None:  # 'no' or any other response
            self._logout_dialogue = None
        return True

    def _draw_logout_dialogue(self):
        """Draw the logout confirmation dialogue if active."""
        if hasattr(self, '_logout_dialogue') and self._logout_dialogue:
            self._logout_dialogue.draw()

    # ── onboarding guide modal ─────────────────────────────────────

    def _onboarding(self):
        ud = getattr(self.state, 'user_dict', None) or {}
        return ud.get('onboarding') or {}

    def _set_onboarding_skipped_local(self, skipped):
        ud = getattr(self.state, 'user_dict', None)
        if not ud:
            return
        onboarding = dict(ud.get('onboarding') or {})
        onboarding['onboarding_skipped'] = bool(skipped)
        if skipped:
            onboarding['welcome_pending'] = False
        ud['onboarding'] = onboarding

    def _pause_onboarding_tutorial(self):
        try:
            data = onboarding_service.skip_onboarding()
            self._apply_onboarding_payload(data)
        except Exception:
            self._set_onboarding_skipped_local(True)
        self._menu_coach_pressed_button_action = None
        if getattr(self.state, 'set_msg', None):
            self.state.set_msg('Tutorial paused. Open Guide to continue.')

    def _resume_onboarding_tutorial(self):
        try:
            data = onboarding_service.resume_onboarding()
            self._apply_onboarding_payload(data)
        except Exception:
            self._set_onboarding_skipped_local(False)
        if getattr(self.state, 'set_msg', None):
            self.state.set_msg('Tutorial resumed')

    def _current_menu_username(self):
        ud = getattr(self.state, 'user_dict', None) or {}
        return ud.get('username')

    def _sync_menu_user_context(self):
        username = self._current_menu_username()
        if getattr(self, '_menu_chrome_username', None) == username:
            return
        self._menu_chrome_username = username
        self._onboarding_guide_open = False
        self._onboarding_guide_tab = 'journey'
        self._onboarding_guide_buttons = []
        self._onboarding_guide_item_rects = {}
        self._onboarding_guide_section_header_rects = {}
        self._reset_onboarding_guide_scroll()
        if hasattr(self, '_onboarding_reward_floaters'):
            self._onboarding_reward_floaters.clear()
            self._onboarding_reward_floaters_last_tick = pygame.time.get_ticks()
        self._menu_coach_buttons = []
        self._menu_coach_step = None
        if hasattr(self, '_welcome_present_dialogue'):
            self._welcome_present_dialogue = None
        if hasattr(self, '_welcome_dialogue_opened'):
            self._welcome_dialogue_opened = False
        if hasattr(self, '_welcome_dialogue_username'):
            self._welcome_dialogue_username = username
        if hasattr(self, '_badge_poller'):
            self._badge_poller = None
        if hasattr(self, '_badge_timer'):
            self._badge_timer = 0

    def _apply_onboarding_payload(self, data):
        self._sync_menu_user_context()
        if not data or not getattr(self.state, 'user_dict', None):
            return
        onboarding = data.get('onboarding')
        if onboarding is not None:
            replaying = onboarding.get('replaying_lesson')
            celebrated = getattr(self, '_tutorial_celebrated', None)
            if replaying and celebrated is not None:
                celebrated.discard(f'replay:{replaying}')
            self.state.user_dict['onboarding'] = self._merge_onboarding_state(onboarding)
        balances = data.get('balances') or {}
        for key in ('gold', 'booster_packs', 'booster_packs_side', 'maps'):
            if key in balances:
                self.state.user_dict[key] = balances[key]

    # ── Tutorial completion celebrations (shared across menu-like screens) ──
    # Shown on whatever tutorial-coach screen completes a tutorial (e.g. the
    # kingdom-config screen for the conquer tutorial), not only on the menu.

    @staticmethod
    def _reward_reveal_items(reward):
        """Turn a reward dict into reveal-dialogue items with explanations."""
        from game.tutorial_content import reward_reveal_items
        return reward_reveal_items(reward)

    # Ordered curriculum: the First Journey, then the optional Guide lessons.
    _TUTORIAL_COMPLETIONS = (
        ('finish_tutorial', 'First Journey Complete!', [
            "You revealed your starter cards, launched a prepared attack, chose tactics, and took your first land.",
            "Your First Journey rewards are below. From now on, open Guide to claim completed lesson rewards and choose when to start the next lesson.",
        ]),
        ('finish_collection_lesson', 'Grow Your Collection Complete!', [
            "You opened both pack types and learned how free, locked, spare, sold, and converted cards fit together.",
            "Next in Guide: Build Your Own Attack, where you choose every part of a conquest plan.",
        ]),
        ('finish_build_attack_lesson', 'Build Your Own Attack Complete!', [
            "You assembled the figures, tactics, and prelude for a real attack, then carried the plan through battle.",
            "Next in Guide: Run Your Kingdom and learn how conquered land becomes lasting strength.",
        ]),
        ('finish_run_kingdom_lesson', 'Run Your Kingdom Complete!', [
            "You found production, skills, maps, loot, shields, and kingdom style—and made the kingdom your own.",
            "Next in Guide: Defend Your Land by preparing the plan that rivals must overcome.",
        ]),
        ('finish_defend_land_lesson', 'Defend Your Land Complete!', [
            "You saved a complete defence with figures, tactics, a prelude, and a final response.",
            "Next in Guide: Duel Basics, the full head-to-head game from setup to final score.",
        ]),
        ('finish_duel_basics_lesson', 'Duel Basics Complete!', [
            "You played a full duel and learned setup turns, advancing, battle moves, responses, and scoring.",
            "The guided lessons are complete. Keep growing through Goals, daily quests, Conquer, and Duel.",
        ]),
    )

    def _pending_tutorial_completion(self):
        """Return completion-dialogue data for a finished lesson."""
        onboarding = self._onboarding()
        if not onboarding or onboarding.get('welcome_pending'):
            return None
        if onboarding.get('onboarding_skipped'):
            return None
        celebrated = getattr(self, '_tutorial_celebrated', None)
        if celebrated is None:
            celebrated = self._tutorial_celebrated = set()
        # Lesson starts can be triggered from a Guide overlay owned by a
        # different persistent screen object.  Clear this screen's stale replay
        # guard as soon as it observes the shared active replay; otherwise a
        # second replay can finish on this screen without reopening its recap,
        # leaving replay_completion_pending stuck on the server.
        replaying_lesson_id = onboarding.get('replaying_lesson')
        if replaying_lesson_id:
            celebrated.discard(f'replay:{replaying_lesson_id}')
        replay_lesson_id = onboarding.get('replay_completion_pending')
        if replay_lesson_id:
            lesson = next((
                item for item in (onboarding.get('lessons') or [])
                if item.get('id') == replay_lesson_id
            ), None)
            completion_step = (lesson or {}).get('completion_step')
            completion = next((
                item for item in self._TUTORIAL_COMPLETIONS
                if item[0] == completion_step
            ), None)
            celebration_id = f'replay:{replay_lesson_id}'
            if completion and celebration_id not in celebrated:
                _step_id, title, lines = completion
                return (
                    celebration_id,
                    title,
                    lines,
                    {},
                    replay_lesson_id,
                )
        steps = {s.get('id'): s for s in (onboarding.get('core_steps') or [])}
        for step_id, title, lines in self._TUTORIAL_COMPLETIONS:
            payload = steps.get(step_id)
            if not payload or not payload.get('completed') or payload.get('claimed'):
                continue
            if step_id in celebrated:
                continue
            if self._tutorial_completion_blocked(step_id):
                continue
            return step_id, title, lines, payload.get('reward'), None
        return None

    def _tutorial_completion_blocked(self, step_id):
        if step_id == 'finish_tutorial':
            return 'kingdom_after_conquer_map' not in self._menu_coach_seen()
        return False

    def _maybe_show_tutorial_completion(self):
        if getattr(self, '_tutorial_complete_dialogue', None):
            return
        if getattr(self, '_welcome_present_dialogue', None):
            return
        if getattr(self, '_starter_reveal_dialogue', None):
            return
        if getattr(self, 'dialogue_box', None) or getattr(self, '_onboarding_guide_open', False):
            return
        pending = self._pending_tutorial_completion()
        if not pending:
            return
        from game.components.rewards_reveal_dialogue import RewardsRevealDialogueBox
        step_id, title, lines, reward, replay_lesson_id = pending
        if getattr(self, '_tutorial_celebrated', None) is None:
            self._tutorial_celebrated = set()
        self._tutorial_celebrated.add(step_id)
        self._tutorial_complete_step_id = step_id
        self._tutorial_complete_replay_lesson_id = replay_lesson_id
        self._tutorial_complete_dialogue = RewardsRevealDialogueBox(
            self.window,
            title,
            'victory',
            lines,
            self._reward_reveal_items(reward),
            footer_when_done=(
                'Replay complete. No additional reward is granted.'
                if replay_lesson_id
                else (
                    'All rewards revealed. First Journey complete!'
                    if step_id == 'finish_tutorial'
                    else 'All rewards revealed. Lesson complete!'
                )
            ),
            hint_text=(
                None if replay_lesson_id
                else 'Click each box to reveal your reward.'
            ),
            ok_label=(
                'Finish tutorial'
                if step_id == 'finish_tutorial'
                else 'Finish Lesson'
            ),
        )

    def _draw_tutorial_complete_dialogue(self):
        if getattr(self, '_tutorial_complete_dialogue', None):
            self._tutorial_complete_dialogue.draw()

    def _handle_tutorial_completion_events(self, events):
        if not getattr(self, '_tutorial_complete_dialogue', None):
            return False
        if any(event.type == pygame.QUIT for event in events):
            return False
        response = self._tutorial_complete_dialogue.update(events)
        if response:
            step_id = getattr(self, '_tutorial_complete_step_id', None)
            replay_lesson_id = getattr(
                self, '_tutorial_complete_replay_lesson_id', None)
            self._tutorial_complete_dialogue = None
            self._tutorial_complete_step_id = None
            self._tutorial_complete_replay_lesson_id = None
            if replay_lesson_id:
                try:
                    data = onboarding_service.acknowledge_replay_completion(
                        replay_lesson_id)
                    self._apply_onboarding_payload(data)
                    if getattr(self.state, 'set_msg', None):
                        self.state.set_msg(
                            'Lesson replay complete. No additional reward.')
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception(
                        "Failed to acknowledge tutorial lesson replay")
            elif step_id:
                try:
                    data = onboarding_service.claim_reward(step_id)
                    reward = (data or {}).get('reward') or {}
                    if int(reward.get('gold') or 0) and hasattr(self, '_suppress_next_gold_floater'):
                        self._suppress_next_gold_floater()
                    self._apply_onboarding_payload(data)
                    if getattr(self.state, 'set_msg', None) and data.get('reward_label'):
                        self.state.set_msg(data['reward_label'])
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception(
                        "Failed to claim tutorial completion reward")
        return True

    def _merge_onboarding_state(self, incoming):
        if not isinstance(incoming, dict):
            return incoming
        current = self._onboarding()
        if not isinstance(current, dict):
            return incoming
        if incoming.get('replaying_lesson'):
            # Starting a replay intentionally clears that lesson's historical
            # hint ids. Merging the previous client state here would undo it.
            return incoming
        merged = dict(incoming)
        for key in ('duel_hints_seen', 'menu_hints_seen'):
            values = list(merged.get(key) or [])
            for value in current.get(key) or []:
                if value not in values:
                    values.append(value)
            if values:
                merged[key] = values
        return merged

    def _open_onboarding_guide(self):
        self._onboarding_guide_open = True
        self._reset_onboarding_guide_scroll()
        try:
            data = onboarding_service.fetch_onboarding()
            self._apply_onboarding_payload(data)
        except Exception:
            if getattr(self.state, 'set_msg', None):
                self.state.set_msg('Guide could not refresh')

    def _onboarding_guide_badge_count(self):
        onboarding = self._onboarding()
        if not onboarding:
            return 0
        count = int(onboarding.get('pending_reward_count') or 0)
        if onboarding.get('welcome_pending'):
            count += 1
        return count

    def _onboarding_guide_tab_badge_counts(self):
        """Return claimable reward counts for the tabs that display them."""
        onboarding = self._onboarding() or {}
        journey_count = sum(
            1 for item in onboarding.get('core_steps') or []
            if item.get('claimable'))
        goals_count = sum(
            1 for item in onboarding.get('early_goals') or []
            if item.get('claimable'))
        if (onboarding.get('daily_quest') or {}).get('claimable'):
            goals_count += 1
        return {
            'journey': journey_count,
            'goals': goals_count,
            'rulebook': 0,
        }

    def _reset_onboarding_guide_scroll(self):
        self._onboarding_guide_scroll = 0
        self._onboarding_guide_touch_scrolling = False
        self._onboarding_guide_touch_last_y = 0
        self._onboarding_guide_touch_moved = 0

    def _onboarding_guide_row_metrics(self):
        row_h = max(52, min(72, int(0.070 * _SH)))
        return row_h, 6

    @staticmethod
    def _onboarding_guide_visible_items(items):
        visible = [item for item in items if item.get('claimable')]
        visible += [item for item in items if not item.get('completed') and item not in visible]
        visible += [item for item in items if item.get('completed') and item not in visible]
        return visible

    @staticmethod
    def _onboarding_pending_items(items):
        """Hide completed, non-claimable rows behind the collapsed history."""
        return [
            item for item in (items or [])
            if item.get('claimable') or not item.get('completed')
        ]

    def _onboarding_guide_rows_height(self, items):
        visible = self._onboarding_guide_visible_items(items or [])
        if not visible:
            return self._onboarding_guide_font.get_height() + 12
        row_h, gap = self._onboarding_guide_row_metrics()
        return len(visible) * row_h + max(0, len(visible) - 1) * gap

    def _max_onboarding_guide_scroll(self):
        area = getattr(self, '_onboarding_guide_scroll_area', None)
        if not area:
            return 0
        return max(0, int(getattr(self, '_onboarding_guide_content_h', 0) or 0) - area.h)

    def _clamp_onboarding_guide_scroll(self):
        self._onboarding_guide_scroll = max(
            0,
            min(int(getattr(self, '_onboarding_guide_scroll', 0) or 0),
                self._max_onboarding_guide_scroll()),
        )

    def _scroll_onboarding_guide(self, wheel_y):
        max_scroll = self._max_onboarding_guide_scroll()
        if max_scroll <= 0:
            return False
        step = max(60, int(0.080 * _SH))
        current = int(getattr(self, '_onboarding_guide_scroll', 0) or 0)
        new_scroll = max(0, min(max_scroll, current - int(round(float(wheel_y or 0) * step))))
        self._onboarding_guide_scroll = new_scroll
        return new_scroll != current

    def _drag_onboarding_guide(self, dy):
        max_scroll = self._max_onboarding_guide_scroll()
        if max_scroll <= 0:
            return False
        current = int(getattr(self, '_onboarding_guide_scroll', 0) or 0)
        new_scroll = max(0, min(max_scroll, current - int(dy)))
        self._onboarding_guide_scroll = new_scroll
        return new_scroll != current

    def _begin_onboarding_guide_touch_scroll(self, pos):
        if self._max_onboarding_guide_scroll() <= 0:
            return False
        area = getattr(self, '_onboarding_guide_scroll_area', None)
        track = getattr(self, '_onboarding_guide_scrollbar_rect', None)
        if not ((area and area.collidepoint(pos)) or (track and track.collidepoint(pos))):
            return False
        self._onboarding_guide_touch_scrolling = True
        self._onboarding_guide_touch_last_y = pos[1]
        self._onboarding_guide_touch_moved = 0
        return True

    def _update_onboarding_guide_touch_scroll(self, pos):
        if not getattr(self, '_onboarding_guide_touch_scrolling', False):
            return False
        dy = pos[1] - self._onboarding_guide_touch_last_y
        if dy == 0:
            return True
        self._onboarding_guide_touch_last_y = pos[1]
        self._onboarding_guide_touch_moved += abs(dy)
        self._drag_onboarding_guide(dy)
        return True

    def _end_onboarding_guide_touch_scroll(self):
        was_scrolling = getattr(self, '_onboarding_guide_touch_scrolling', False)
        moved = getattr(self, '_onboarding_guide_touch_moved', 0)
        was_swipe = was_scrolling and moved > max(6, int(0.012 * _SH))
        self._onboarding_guide_touch_scrolling = False
        self._onboarding_guide_touch_last_y = 0
        self._onboarding_guide_touch_moved = 0
        return was_swipe

    def _onboarding_guide_rect(self):
        top = max(int(0.12 * _SH), settings.GAME_MENU_GOLD_MARGIN_Y
                  + settings.GAME_MENU_GOLD_ICON_SZ
                  + settings.GAME_MENU_GOLD_BOX_PAD_Y * 2
                  + int(0.035 * _SH))
        height = min(int(0.74 * _SH), _SH - top - int(0.075 * _SH))
        return pygame.Rect(int(0.10 * _SW), top, int(0.80 * _SW), height)

    def _draw_onboarding_guide_badge(self):
        count = self._onboarding_guide_badge_count()
        if count <= 0 or not hasattr(self, '_icon_guide'):
            return
        r = max(9, int(0.014 * _SH))
        cx = self._icon_guide.rect.right - r
        cy = self._icon_guide.rect.top + r
        pygame.draw.circle(self.window, (210, 40, 40), (cx, cy), r)
        pygame.draw.circle(self.window, (255, 255, 255), (cx, cy), r, 1)
        txt = self._onboarding_guide_badge_font.render(str(min(count, 99)), True, (255, 255, 255))
        self.window.blit(txt, txt.get_rect(center=(cx, cy)))

    def _draw_onboarding_guide(self):
        onboarding = self._onboarding()
        self._onboarding_guide_buttons = []
        self._onboarding_guide_item_rects = {}
        self._onboarding_guide_section_header_rects = {}

        overlay = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
        overlay.fill(settings.DIALOGUE_BOX_OVERLAY_CLR)
        self.window.blit(overlay, (0, 0))

        rect = self._onboarding_guide_rect()
        panel = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(panel, settings.DIALOGUE_BOX_BG_CLR,
                         panel.get_rect(), border_radius=settings.DIALOGUE_BOX_CORNER_R)
        pygame.draw.rect(panel, settings.DIALOGUE_BOX_BORDER_CLR,
                         panel.get_rect(), settings.DIALOGUE_BOX_BORDER_WIDTH,
                         border_radius=settings.DIALOGUE_BOX_CORNER_R)
        self.window.blit(panel, rect.topleft)

        title = self._onboarding_guide_title_font.render('Guide', True, settings.TITLE_TEXT_COLOR)
        self.window.blit(title, (rect.x + 20, rect.y + 16))

        close_sz = max(24, int(0.032 * _SH))
        self._onboarding_guide_close_rect = pygame.Rect(
            rect.right - close_sz - 16,
            rect.y + 16,
            close_sz,
            close_sz,
        )
        self._draw_onboarding_guide_close_x()

        content_top = self._draw_onboarding_guide_tabs(rect)

        if self._onboarding_guide_tab == 'rulebook':
            self._draw_onboarding_guide_rulebook()
            return
        if self._onboarding_guide_tab == 'goals':
            self._draw_onboarding_guide_goals(rect, content_top)
            return
        self._draw_onboarding_guide_journey(rect, content_top, onboarding)

    def _draw_onboarding_guide_intro(self, rect, content_top, text):
        intro_surf = self._onboarding_guide_small_font.render(
            self._fit_text(
                text, self._onboarding_guide_small_font, rect.w - 44),
            True,
            settings.DIALOGUE_BOX_MSG_TEXT_CLR,
        )
        self.window.blit(intro_surf, (rect.x + 22, content_top))
        return intro_surf.get_height()

    def _draw_onboarding_pause_banner(self, rect, top):
        onboarding = self._onboarding() or {}
        if not onboarding.get('onboarding_skipped'):
            return top
        pause_h = max(42, int(0.052 * _SH))
        pause_rect = pygame.Rect(rect.x + 22, top, rect.w - 44, pause_h)
        pause_bg = pygame.Surface(
            (pause_rect.w, pause_rect.h), pygame.SRCALPHA)
        pause_bg.fill((34, 29, 23, 168))
        self.window.blit(pause_bg, pause_rect.topleft)
        pygame.draw.rect(
            self.window, (150, 126, 74), pause_rect, 1, border_radius=5)
        label = self._onboarding_guide_font.render(
            'Tutorial paused', True, (235, 222, 184))
        self.window.blit(
            label,
            (pause_rect.x + 12,
             pause_rect.y + pause_rect.h // 2 - label.get_height() // 2),
        )
        resume_label = 'Continue tutorial'
        resume_w = max(
            138,
            self._onboarding_guide_small_font.size(resume_label)[0] + 26)
        resume_h = max(
            28, self._onboarding_guide_small_font.get_height() + 8)
        resume_rect = pygame.Rect(
            pause_rect.right - resume_w - 12,
            pause_rect.y + (pause_rect.h - resume_h) // 2,
            resume_w,
            resume_h,
        )
        self._draw_onboarding_guide_button(
            resume_rect, resume_label, ('resume_tutorial', None))
        return pause_rect.bottom + int(0.018 * _SH)

    def _draw_onboarding_guide_journey(
            self, rect, content_top, onboarding=None):
        onboarding = onboarding or self._onboarding() or {}
        intro_h = self._draw_onboarding_guide_intro(
            rect,
            content_top,
            'Choose a lesson. Each cover shows its progress and reward.',
        )
        top = content_top + intro_h + int(0.018 * _SH)
        top = self._draw_onboarding_pause_banner(rect, top)
        scroll_gutter = max(10, int(0.010 * _SW))
        viewport = pygame.Rect(
            rect.x + 22,
            top,
            rect.w - 44 - scroll_gutter,
            max(52, rect.bottom - top - 22),
        )
        lessons = self._onboarding_journey_catalogue(onboarding)
        self._draw_onboarding_lesson_catalogue(lessons, viewport)

    def _draw_onboarding_guide_goals(self, rect, content_top):
        intro_h = self._draw_onboarding_guide_intro(
            rect,
            content_top,
            'Complete today\'s quest and long-term goals to earn rewards.',
        )
        top = content_top + intro_h + int(0.018 * _SH)
        quest_h = max(78, int(0.104 * _SH))
        self._draw_onboarding_area_overview(
            pygame.Rect(rect.x + 22, top, rect.w - 44, quest_h))

        section_top = top + quest_h + int(0.020 * _SH)
        header_h = self._onboarding_guide_section_font.get_height() + 8
        scroll_gutter = max(10, int(0.010 * _SW))
        viewport = pygame.Rect(
            rect.x + 22,
            section_top + header_h,
            rect.w - 44 - scroll_gutter,
            max(42, rect.bottom - section_top - header_h - 22),
        )
        goals = self._onboarding_pending_items(
            (self._onboarding() or {}).get('early_goals') or [])
        self._onboarding_guide_scroll_area = viewport.copy()
        self._onboarding_guide_content_h = self._onboarding_guide_rows_height(
            goals)
        self._clamp_onboarding_guide_scroll()
        section = pygame.Rect(
            viewport.x,
            section_top,
            viewport.w,
            header_h + viewport.h,
        )
        self._draw_onboarding_guide_section(
            'Goals',
            goals,
            section,
            scroll_offset=int(
                getattr(self, '_onboarding_guide_scroll', 0) or 0),
            clip_rect=viewport,
        )
        self._draw_onboarding_guide_scrollbar(viewport)

    _GUIDE_LESSON_COVERS = {
        'finish_tutorial': 'conquer_start_image',
        'grow_collection': 'collection_growth_start_image',
        'build_attack': 'build_attack_start_image',
        'run_kingdom': 'run_kingdom_start_image',
        'defend_land': 'defend_land_start_image',
        'duel_basics': 'duel_start_image',
    }

    def _onboarding_journey_catalogue(self, onboarding=None):
        """Return the complete, ordered lesson catalogue for Journey."""
        onboarding = onboarding or self._onboarding() or {}
        core_steps = onboarding.get('core_steps') or []
        first_steps = [
            item for item in core_steps
            if item.get('group') == 'first_journey'
        ]
        first_finish = next(
            (item for item in first_steps
             if item.get('id') == 'finish_tutorial'),
            {},
        )
        first_progress = sum(
            1 for item in first_steps if item.get('completed'))
        next_action = onboarding.get('next_action') or {}
        first_completed = bool(first_finish.get('completed'))
        first_started = bool(
            first_progress
            or onboarding.get('welcome_seen')
            or onboarding.get('starter_set_granted')
            or onboarding.get('menu_hints_seen')
        )
        first_journey = {
            'id': 'finish_tutorial',
            'title': 'Your Path to the Crown',
            'description': (
                'Reveal your starter cards, conquer your first land, and '
                'claim your royal welcome.'
            ),
            'lesson': True,
            'first_journey': True,
            'progress': first_progress,
            'total_steps': len(first_steps),
            'progress_label': (
                f'{first_progress}/{len(first_steps)}'
                if first_steps else ''
            ),
            'completed': first_completed,
            'claimed': bool(first_finish.get('claimed')),
            'claimable': bool(first_finish.get('claimable')),
            'reward': dict(first_finish.get('reward') or {}),
            'reward_id': 'finish_tutorial',
            'locked': False,
            'started': first_started,
            'active': not first_completed and first_started,
            'entry_screen': next_action.get('screen') or 'collection',
        }
        lessons = [
            dict(item)
            for item in onboarding.get('lessons') or []
            if item.get('group') == 'lessons'
        ]
        return [first_journey, *lessons]

    def _onboarding_lesson_catalogue_metrics(self):
        card_h = max(124, min(150, int(0.168 * _SH)))
        gap = max(8, int(0.012 * _SH))
        return card_h, gap

    def _draw_onboarding_lesson_catalogue(self, lessons, viewport):
        card_h, gap = self._onboarding_lesson_catalogue_metrics()
        self._onboarding_guide_scroll_area = viewport.copy()
        self._onboarding_guide_content_h = (
            len(lessons) * card_h + max(0, len(lessons) - 1) * gap
        )
        self._clamp_onboarding_guide_scroll()
        scroll = int(getattr(self, '_onboarding_guide_scroll', 0) or 0)
        old_clip = self.window.get_clip()
        self.window.set_clip(viewport)
        y = viewport.y - scroll
        for item in lessons:
            card = pygame.Rect(viewport.x, y, viewport.w, card_h)
            if card.colliderect(viewport):
                item_id = item.get('id')
                if item_id:
                    self._onboarding_guide_item_rects[item_id] = card.clip(
                        viewport)
                self._draw_onboarding_lesson_card(
                    item, card, clip_rect=viewport)
            y += card_h + gap
        self.window.set_clip(old_clip)
        self._draw_onboarding_guide_scrollbar(viewport)

    def _draw_onboarding_lesson_card(self, item, card, clip_rect=None):
        completed = bool(item.get('completed'))
        claimable = bool(item.get('claimable'))
        locked = bool(item.get('locked'))
        active = bool(item.get('active'))
        started = bool(item.get('started'))

        bg = pygame.Surface((card.w, card.h), pygame.SRCALPHA)
        if claimable:
            fill = (45, 35, 20, 220)
        elif completed:
            fill = (22, 34, 25, 188)
        elif active:
            fill = (36, 31, 22, 196)
        else:
            fill = (24, 22, 19, 165)
        bg.fill(fill)
        self.window.blit(bg, card.topleft)
        if claimable:
            border = (225, 188, 82)
        elif completed:
            border = (91, 156, 101)
        elif active:
            border = (170, 142, 73)
        else:
            border = (112, 96, 66)
        pygame.draw.rect(
            self.window, border, card, 1, border_radius=7)

        pad = 8
        cover_h = card.h - pad * 2
        cover_w = min(
            int(cover_h * 1.78),
            max(118, int(card.w * 0.34)),
        )
        cover_rect = pygame.Rect(
            card.x + pad, card.y + pad, cover_w, cover_h)
        pygame.draw.rect(
            self.window, (15, 14, 12), cover_rect, border_radius=5)
        cover = self._onboarding_lesson_cover(
            item.get('id'), cover_rect.size)
        if cover is not None:
            self.window.blit(cover, cover_rect.topleft)
        pygame.draw.rect(
            self.window, (137, 112, 64), cover_rect, 1, border_radius=5)

        if completed:
            veil = pygame.Surface(cover_rect.size, pygame.SRCALPHA)
            veil.fill((18, 70, 34, 54))
            self.window.blit(veil, cover_rect.topleft)

        info_x = cover_rect.right + 12
        info_right = card.right - 10
        info_w = max(80, info_right - info_x)
        status, status_color = self._onboarding_lesson_status(item)
        status_surf = self._onboarding_guide_small_font.render(
            status, True, status_color)
        status_pad_x = 8
        status_rect = pygame.Rect(
            info_right - status_surf.get_width() - status_pad_x * 2,
            card.y + 8,
            status_surf.get_width() + status_pad_x * 2,
            status_surf.get_height() + 6,
        )
        status_bg = pygame.Surface(status_rect.size, pygame.SRCALPHA)
        status_bg.fill((18, 17, 15, 185))
        self.window.blit(status_bg, status_rect.topleft)
        pygame.draw.rect(
            self.window, status_color, status_rect, 1, border_radius=8)
        self.window.blit(
            status_surf, status_surf.get_rect(center=status_rect.center))

        title_w = max(50, status_rect.x - info_x - 8)
        title = self._fit_text(
            item.get('title') or '', self._onboarding_guide_font, title_w)
        title_surf = self._onboarding_guide_font.render(
            title, True, (238, 225, 188))
        self.window.blit(title_surf, (info_x, card.y + 9))

        description = self._fit_text(
            item.get('description') or '',
            self._onboarding_guide_small_font,
            info_w,
        )
        desc_surf = self._onboarding_guide_small_font.render(
            description, True, (174, 164, 139))
        desc_y = card.y + 39
        self.window.blit(desc_surf, (info_x, desc_y))

        progress_label = item.get('progress_label') or ''
        if progress_label:
            unit = 'milestones' if item.get('first_journey') else 'steps'
            progress_surf = self._onboarding_guide_small_font.render(
                f'{progress_label} {unit}',
                True,
                (195, 180, 140),
            )
            self.window.blit(
                progress_surf,
                (info_x, desc_y + desc_surf.get_height() + 5),
            )

        action_label = None
        action = None
        if claimable:
            action_label = 'Claim'
            action = ('claim', item.get('reward_id') or item.get('id'))
        elif completed and not item.get('first_journey'):
            action_label = 'Replay'
            action = ('start_lesson', item.get('id'))
        elif not completed and locked:
            action_label = 'Locked'
        elif not completed and item.get('first_journey'):
            action_label = 'Continue' if started else 'Start Tutorial'
            action = ('continue_journey', item.get('entry_screen'))
        elif not completed:
            action_label = (
                'Continue' if active or started
                else ('Restart' if item.get('dismissed') else 'Start')
            )
            action = ('start_lesson', item.get('id'))

        button_rect = None
        if action_label:
            button_w = max(
                72,
                self._onboarding_guide_small_font.size(action_label)[0] + 22,
            )
            button_h = max(
                28, self._onboarding_guide_small_font.get_height() + 8)
            button_rect = pygame.Rect(
                info_right - button_w,
                card.bottom - button_h - 9,
                button_w,
                button_h,
            )
            if action:
                hit_rect = (
                    button_rect.clip(clip_rect)
                    if clip_rect else button_rect.copy()
                )
                self._draw_onboarding_guide_button(
                    button_rect,
                    action_label,
                    action,
                    hit_rect=hit_rect,
                )
            else:
                self._draw_onboarding_guide_disabled_button(
                    button_rect, action_label)

        reward = item.get('reward') or {}
        if reward and (not completed or claimable):
            reward_label = self._onboarding_guide_small_font.render(
                'Reward', True, (205, 184, 125))
            reward_y = card.bottom - max(
                28, self._onboarding_guide_small_font.get_height() + 8) // 2 - 9
            self.window.blit(
                reward_label,
                (info_x, reward_y - reward_label.get_height() // 2),
            )
            reward_right = (
                button_rect.left - 8 if button_rect else info_right)
            self._draw_onboarding_reward_icons(
                reward, reward_right, reward_y)

    @staticmethod
    def _onboarding_lesson_status(item):
        if item.get('completed'):
            return 'Completed', (105, 205, 120)
        if item.get('locked'):
            return 'Locked', (154, 145, 126)
        if item.get('active') or item.get('started'):
            return 'In progress', (226, 190, 96)
        return 'Not started', (174, 164, 139)

    def _onboarding_lesson_cover(self, lesson_id, size):
        loader_name = self._GUIDE_LESSON_COVERS.get(lesson_id)
        if not loader_name:
            return None
        cache_key = ('lesson_cover', lesson_id, int(size[0]), int(size[1]))
        cached = self._onboarding_guide_icon_cache.get(cache_key)
        if cached is not None:
            return cached
        from game.components import tutorial_diagrams
        source = getattr(tutorial_diagrams, loader_name)()
        if source is None or source.get_width() <= 0 or source.get_height() <= 0:
            return None
        target_w, target_h = max(1, int(size[0])), max(1, int(size[1]))
        scale = max(
            target_w / source.get_width(),
            target_h / source.get_height(),
        )
        scaled = pygame.transform.smoothscale(
            source,
            (
                max(1, int(round(source.get_width() * scale))),
                max(1, int(round(source.get_height() * scale))),
            ),
        )
        cover = pygame.Surface((target_w, target_h), pygame.SRCALPHA)
        cover.blit(
            scaled,
            (
                (target_w - scaled.get_width()) // 2,
                (target_h - scaled.get_height()) // 2,
            ),
        )
        self._onboarding_guide_icon_cache[cache_key] = cover
        return cover

    def _draw_onboarding_guide_disabled_button(self, rect, label):
        pygame.draw.rect(self.window, (38, 35, 30), rect, border_radius=4)
        pygame.draw.rect(
            self.window, (91, 84, 72), rect, 1, border_radius=4)
        txt = self._onboarding_guide_small_font.render(
            label, True, (145, 137, 120))
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_onboarding_guide_close_x(self):
        r = self._onboarding_guide_close_rect
        mouse_pos = pygame.mouse.get_pos()
        hovered = r.collidepoint(mouse_pos)
        bg_clr = (80, 50, 25, 220) if hovered else (55, 35, 18, 200)
        border_clr = (180, 160, 120) if hovered else (120, 100, 70)
        txt_clr = (255, 240, 200) if hovered else (200, 180, 140)
        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg_clr, surf.get_rect(), border_radius=4)
        pygame.draw.rect(surf, border_clr, surf.get_rect(), 1, border_radius=4)
        self.window.blit(surf, r.topleft)
        txt = self._onboarding_guide_section_font.render('X', True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=r.center))

    # ── Guide tabs (Journey / Goals / Rulebook) ────────────────────

    _GUIDE_TABS = (
        ('journey', 'Journey'),
        ('goals', 'Goals'),
        ('rulebook', 'Rulebook'),
    )

    def _onboarding_guide_tab_metrics(self, rect):
        """Shared geometry for the tab bar: (tabs_y, tab_h, content_top)."""
        title_h = self._onboarding_guide_title_font.get_height()
        tab_h = max(34, int(0.044 * _SH))
        tabs_y = rect.y + 16 + title_h + 12
        content_top = tabs_y + tab_h + max(10, int(0.016 * _SH))
        return tabs_y, tab_h, content_top

    def _draw_onboarding_guide_tabs(self, rect):
        """Draw the segmented Guide tabs; returns content top y."""
        self._onboarding_guide_tab_rects = {}
        tabs_y, tab_h, content_top = self._onboarding_guide_tab_metrics(rect)

        seg_w = max(
            int(0.105 * _SW),
            max(self._onboarding_guide_font.size(label)[0]
                for _, label in self._GUIDE_TABS) + 52,
        )
        total = pygame.Rect(rect.x + 22, tabs_y, seg_w * len(self._GUIDE_TABS), tab_h)

        container = pygame.Surface((total.w, total.h), pygame.SRCALPHA)
        pygame.draw.rect(container, (26, 23, 19, 205), container.get_rect(), border_radius=7)
        self.window.blit(container, total.topleft)

        mouse_pos = pygame.mouse.get_pos()
        badge_counts = self._onboarding_guide_tab_badge_counts()
        active_tab = getattr(self, '_onboarding_guide_tab', 'journey')
        for i, (key, label) in enumerate(self._GUIDE_TABS):
            seg = pygame.Rect(total.x + i * seg_w, total.y, seg_w, tab_h)
            self._onboarding_guide_tab_rects[key] = seg
            active = key == active_tab
            hovered = seg.collidepoint(mouse_pos) and not active
            if active:
                fill = pygame.Rect(seg.x + 3, seg.y + 3, seg.w - 6, seg.h - 6)
                seg_bg = pygame.Surface((fill.w, fill.h), pygame.SRCALPHA)
                pygame.draw.rect(seg_bg, (92, 70, 32, 240), seg_bg.get_rect(), border_radius=6)
                self.window.blit(seg_bg, fill.topleft)
                pygame.draw.rect(self.window, (235, 204, 105), fill, 1, border_radius=6)
                txt_clr = (248, 232, 180)
            elif hovered:
                fill = pygame.Rect(seg.x + 3, seg.y + 3, seg.w - 6, seg.h - 6)
                seg_bg = pygame.Surface((fill.w, fill.h), pygame.SRCALPHA)
                pygame.draw.rect(seg_bg, (44, 38, 30, 225), seg_bg.get_rect(), border_radius=6)
                self.window.blit(seg_bg, fill.topleft)
                txt_clr = (228, 216, 184)
            else:
                txt_clr = (176, 166, 142)
            txt = self._onboarding_guide_font.render(label, True, txt_clr)
            self.window.blit(txt, txt.get_rect(center=seg.center))
            badge_count = badge_counts.get(key, 0)
            if badge_count > 0:
                r = max(8, int(0.011 * _SH))
                cx, cy = seg.right - r - 5, seg.y + r + 4
                pygame.draw.circle(self.window, (210, 40, 40), (cx, cy), r)
                pygame.draw.circle(self.window, (255, 255, 255), (cx, cy), r, 1)
                count_txt = self._onboarding_guide_badge_font.render(
                    str(min(badge_count, 9)), True, (255, 255, 255))
                self.window.blit(count_txt, count_txt.get_rect(center=(cx, cy)))
        pygame.draw.rect(self.window, (112, 96, 66), total, 1, border_radius=7)
        return content_top

    def _onboarding_guide_rulebook_area(self):
        rect = self._onboarding_guide_rect()
        _, _, content_top = self._onboarding_guide_tab_metrics(rect)
        return pygame.Rect(rect.x + 22, content_top,
                           rect.w - 44, rect.bottom - content_top - 20)

    def _ensure_guide_rulebook(self):
        gb = getattr(self, '_guide_rulebook', None)
        if gb is None:
            from game.screens.guide_book_screen import GuideBookScreen
            gb = GuideBookScreen(self.window, self.state,
                                 x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y)
            gb.embed_into(self._onboarding_guide_rulebook_area())
            self._guide_rulebook = gb
        return gb

    def _draw_onboarding_guide_rulebook(self):
        self._ensure_guide_rulebook().draw_embedded()

    def _guide_next_action(self):
        onboarding = self._onboarding() or {}
        action = onboarding.get('next_action')
        if isinstance(action, dict) and action.get('screen'):
            return action
        lessons = onboarding.get('lessons') or []
        active_id = onboarding.get('active_lesson')
        ordered = (
            [item for item in lessons if item.get('id') == active_id]
            + [item for item in lessons
               if item.get('group') == 'lessons'
               and item.get('id') != active_id]
        )
        for item in ordered:
            if item.get('completed') or item.get('locked'):
                continue
            if item.get('dismissed') and item.get('id') != active_id:
                continue
            return {
                'screen': item.get('entry_screen'),
                'label': item.get('entry_label') or item.get('title'),
                'target_id': item.get('id'),
                'lesson_id': item.get('id'),
            }
        return None

    def _draw_onboarding_next_action(self, rect):
        action = self._guide_next_action()
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((45, 35, 20, 205) if action else (25, 23, 20, 150))
        self.window.blit(bg, rect.topleft)
        pygame.draw.rect(
            self.window, (225, 188, 82) if action else (100, 90, 72),
            rect, 1, border_radius=6)
        label = self._onboarding_guide_small_font.render(
            'DO NEXT', True, (224, 190, 105))
        self.window.blit(label, (rect.x + 12, rect.y + 7))
        text = action.get('label') if action else 'All lessons complete — explore at your pace.'
        text_surf = self._onboarding_guide_font.render(
            self._fit_text(text, self._onboarding_guide_font, rect.w - 210),
            True, (240, 226, 188))
        self.window.blit(text_surf, (rect.x + 12, rect.bottom - text_surf.get_height() - 7))
        if action:
            button_w = max(68, self._onboarding_guide_small_font.size('Go')[0] + 28)
            button_h = max(30, self._onboarding_guide_small_font.get_height() + 9)
            button = pygame.Rect(
                rect.right - button_w - 12,
                rect.y + (rect.h - button_h) // 2,
                button_w,
                button_h,
            )
            self._draw_onboarding_guide_button(
                button, 'Go',
                (('start_lesson', action.get('lesson_id'))
                 if action.get('lesson_id')
                 else ('navigate', action.get('screen'))))

    def _draw_onboarding_area_overview(self, rect):
        onboarding = self._onboarding() or {}
        quest = onboarding.get('daily_quest') or {}
        header = self._onboarding_guide_section_font.render(
            'Daily Quest', True, settings.SUB_SCREEN_HEADER_CLR)
        self.window.blit(header, (rect.x, rect.y))

        countdown = self._daily_quest_countdown_text(quest.get('resets_at'))
        if countdown:
            countdown_surf = self._onboarding_guide_small_font.render(
                countdown, True, (170, 160, 135))
            self.window.blit(countdown_surf, (
                rect.right - countdown_surf.get_width(),
                rect.y + header.get_height() // 2 - countdown_surf.get_height() // 2,
            ))

        top = rect.y + header.get_height() + 8
        card = pygame.Rect(rect.x, top, rect.w, max(54, rect.bottom - top))
        bg = pygame.Surface((card.w, card.h), pygame.SRCALPHA)
        bg.fill((34, 29, 23, 178) if quest.get('claimable') else (24, 22, 19, 150))
        self.window.blit(bg, card.topleft)
        border = (215, 184, 92) if quest.get('claimable') else (112, 96, 66)
        pygame.draw.rect(self.window, border, card, 1, border_radius=5)

        pad = 12
        side_w = max(126, min(190, int(card.w * 0.28)))
        left_w = max(80, card.w - side_w - pad * 3)
        title = quest.get('title') or 'Daily Quest'
        desc = quest.get('description') or 'Open the Guide to refresh today\'s quest.'
        title = self._fit_text(title, self._onboarding_guide_font, left_w)
        title_surf = self._onboarding_guide_font.render(title, True, (235, 222, 184))
        self.window.blit(title_surf, (card.x + pad, card.y + 8))

        desc = self._fit_text(desc, self._onboarding_guide_small_font, left_w)
        desc_surf = self._onboarding_guide_small_font.render(desc, True, (170, 160, 135))
        self.window.blit(desc_surf, (card.x + pad, card.y + 32))

        if quest.get('locked'):
            lock_label = self._onboarding_guide_small_font.render(
                'locked', True, (150, 140, 118))
            self.window.blit(lock_label, (
                card.right - pad - lock_label.get_width(),
                card.y + card.h // 2 - lock_label.get_height() // 2,
            ))
            return

        target = max(1, int(quest.get('target') or 1))
        progress = max(0, min(target, int(quest.get('progress') or 0)))
        bar_w = max(70, left_w - 58)
        bar = pygame.Rect(card.x + pad, card.bottom - 18, bar_w, 8)
        pygame.draw.rect(self.window, (45, 39, 32), bar, border_radius=4)
        fill_w = int(bar.w * (progress / target)) if target else 0
        if fill_w > 0:
            pygame.draw.rect(
                self.window, (120, 190, 105),
                pygame.Rect(bar.x, bar.y, fill_w, bar.h),
                border_radius=4,
            )
        pygame.draw.rect(self.window, (105, 92, 70), bar, 1, border_radius=4)
        progress_txt = self._onboarding_guide_small_font.render(
            f'{progress} / {target}', True, (205, 192, 158))
        self.window.blit(progress_txt, (
            bar.right + 8,
            bar.y + bar.h // 2 - progress_txt.get_height() // 2,
        ))

        if quest.get('claimable'):
            claim_w = max(72, self._onboarding_guide_small_font.size('Claim')[0] + 24)
            claim_h = max(30, self._onboarding_guide_small_font.get_height() + 9)
            claim_rect = pygame.Rect(
                card.right - pad - claim_w,
                card.y + card.h // 2 - claim_h // 2,
                claim_w,
                claim_h,
            )
            self._draw_onboarding_guide_button(
                claim_rect, 'Claim', ('claim', 'daily_quest'))
            self._draw_onboarding_reward_icons(
                quest.get('reward') or {}, claim_rect.left - 10, claim_rect.centery)
        elif quest.get('claimed'):
            claimed = self._onboarding_guide_small_font.render(
                'claimed', True, (120, 190, 125))
            self.window.blit(claimed, (
                card.right - pad - claimed.get_width(),
                card.y + card.h // 2 - claimed.get_height() // 2,
            ))
        else:
            self._draw_onboarding_reward_icons(
                quest.get('reward') or {}, card.right - pad, card.y + card.h // 2)

    def _daily_quest_countdown_text(self, resets_at_iso):
        if not resets_at_iso:
            return ''
        try:
            raw = str(resets_at_iso).replace('Z', '+00:00')
            resets_at = datetime.fromisoformat(raw)
            if resets_at.tzinfo is not None:
                resets_at = resets_at.astimezone(timezone.utc).replace(tzinfo=None)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            seconds = max(0, int((resets_at - now).total_seconds()))
        except (TypeError, ValueError):
            return ''
        minutes = seconds // 60
        if minutes <= 0:
            return 'Resets soon'
        hours = minutes // 60
        minutes = minutes % 60
        if hours:
            return f'Resets in {hours}h {minutes}m'
        return f'Resets in {minutes}m'

    def _draw_onboarding_guide_section(self, title, items, rect, scroll_offset=0, clip_rect=None):
        header = self._onboarding_guide_section_font.render(
            title, True, settings.SUB_SCREEN_HEADER_CLR)
        header_rect = header.get_rect(topleft=(rect.x, rect.y))
        self.window.blit(header, header_rect)
        self._onboarding_guide_section_header_rects[title.lower().replace(' ', '_')] = header_rect.inflate(8, 6)
        y = rect.y + header.get_height() + 8 - int(scroll_offset or 0)
        visible = self._onboarding_guide_visible_items(items or [])
        old_clip = None
        if clip_rect:
            old_clip = self.window.get_clip()
            self.window.set_clip(clip_rect)
        if not visible:
            empty = self._onboarding_guide_font.render(
                'All set for now.', True, (170, 160, 135))
            self.window.blit(empty, (rect.x + 6, y + 6))
            if old_clip is not None:
                self.window.set_clip(old_clip)
            return

        row_h, gap = self._onboarding_guide_row_metrics()
        for item in visible:
            row = pygame.Rect(rect.x, y, rect.w, row_h)
            if clip_rect and not row.colliderect(clip_rect):
                y += row_h + gap
                continue
            item_id = item.get('id')
            if item_id:
                self._onboarding_guide_item_rects[item_id] = row.clip(clip_rect) if clip_rect else row.copy()
            bg = pygame.Surface((row.w, row.h), pygame.SRCALPHA)
            fill = (34, 29, 23, 178) if item.get('claimable') else (24, 22, 19, 138)
            bg.fill(fill)
            self.window.blit(bg, row.topleft)
            border = (215, 184, 92) if item.get('claimable') else (112, 96, 66)
            pygame.draw.rect(self.window, border, row, 1, border_radius=5)

            dot = pygame.Rect(row.x + 8, row.y + row_h // 2 - 5, 10, 10)
            dot_clr = (96, 190, 105) if item.get('completed') else (105, 100, 86)
            pygame.draw.ellipse(self.window, dot_clr, dot)
            title_max_w = row.w - 146
            title = self._fit_text(item.get('title') or '', self._onboarding_guide_font, title_max_w)
            title_surf = self._onboarding_guide_font.render(title, True, (235, 222, 184))
            self.window.blit(title_surf, (row.x + 26, row.y + 6))

            desc_max_w = row.w - 146
            description = item.get('description') or ''
            if item.get('lesson') and item.get('total_steps'):
                description = (
                    f"{item.get('progress_label', '0/0')} steps  ·  "
                    f"{description}")
            desc = self._fit_text(
                description, self._onboarding_guide_small_font, desc_max_w)
            desc_surf = self._onboarding_guide_small_font.render(desc, True, (170, 160, 135))
            self.window.blit(desc_surf, (row.x + 26, row.y + row_h - desc_surf.get_height() - 6))

            if item.get('claimable'):
                claim_w = max(68, self._onboarding_guide_small_font.size('Claim')[0] + 22)
                claim_h = max(28, self._onboarding_guide_small_font.get_height() + 8)
                claim_rect = pygame.Rect(row.right - claim_w - 12, row.y + (row_h - claim_h) // 2,
                                         claim_w, claim_h)
                hit_rect = claim_rect.clip(clip_rect) if clip_rect else claim_rect.copy()
                self._draw_onboarding_guide_button(
                    claim_rect,
                    'Claim',
                    ('claim', item.get('reward_id') or item.get('id')),
                    hit_rect=hit_rect,
                )
                self._draw_onboarding_reward_icons(item.get('reward') or {}, claim_rect.left - 10, row.y + row_h // 2)
            elif item.get('claimed'):
                claimed = self._onboarding_guide_small_font.render('claimed', True, (120, 190, 125))
                self.window.blit(claimed, (row.right - claimed.get_width() - 10,
                                           row.y + row_h // 2 - claimed.get_height() // 2))
            elif item.get('lesson') and not item.get('completed'):
                if item.get('locked'):
                    lock = self._onboarding_guide_small_font.render(
                        'locked', True, (145, 135, 116))
                    self.window.blit(
                        lock,
                        (row.right - lock.get_width() - 12,
                         row.y + row_h // 2 - lock.get_height() // 2),
                    )
                else:
                    action_label = (
                        'Continue' if item.get('active') or item.get('started')
                        else ('Restart' if item.get('dismissed') else 'Start')
                    )
                    action_w = max(
                        70,
                        self._onboarding_guide_small_font.size(
                            action_label)[0] + 20)
                    action_h = max(
                        28,
                        self._onboarding_guide_small_font.get_height() + 8)
                    action_rect = pygame.Rect(
                        row.right - action_w - 10,
                        row.y + (row_h - action_h) // 2,
                        action_w,
                        action_h,
                    )
                    hit_rect = (
                        action_rect.clip(clip_rect)
                        if clip_rect else action_rect.copy())
                    self._draw_onboarding_guide_button(
                        action_rect,
                        action_label,
                        ('start_lesson', item.get('id')),
                        hit_rect=hit_rect,
                    )
                    self._draw_onboarding_reward_icons(
                        item.get('reward') or {},
                        action_rect.left - 8,
                        row.y + row_h // 2,
                    )
            else:
                self._draw_onboarding_reward_icons(item.get('reward') or {}, row.right - 88, row.y + row_h // 2)
            y += row_h + gap
        if old_clip is not None:
            self.window.set_clip(old_clip)

    def _draw_onboarding_reward_icons(self, reward, right_x, center_y):
        pairs = []
        for key in ('gold', 'booster_packs', 'booster_packs_side', 'maps'):
            amount = int((reward or {}).get(key) or 0)
            if amount > 0:
                pairs.append((key, amount))
        if not pairs:
            return
        icon_sz = max(14, min(24, int(0.024 * _SH)))
        gap = 4
        rendered = []
        total_w = 0
        for key, amount in pairs:
            icon = self._onboarding_reward_icon(key, icon_sz)
            txt = self._onboarding_guide_small_font.render(f'+{amount}', True, (236, 220, 160))
            rendered.append((icon, txt))
            total_w += icon_sz + 2 + txt.get_width() + gap
        total_w -= gap
        x = right_x - total_w
        for icon, txt in rendered:
            self.window.blit(icon, (x, center_y - icon_sz // 2))
            x += icon_sz + 2
            self.window.blit(txt, (x, center_y - txt.get_height() // 2))
            x += txt.get_width() + gap

    def _onboarding_reward_icon(self, key, size):
        cache_key = (key, size)
        cached = self._onboarding_guide_icon_cache.get(cache_key)
        if cached is not None:
            return cached
        source_by_key = {
            'gold': self._gold_icon,
            'booster_packs': self._booster_icon,
            'booster_packs_side': self._booster_side_icon,
            'maps': self._map_icon,
        }
        surf = pygame.transform.smoothscale(source_by_key[key], (size, size))
        self._onboarding_guide_icon_cache[cache_key] = surf
        return surf

    def _draw_onboarding_guide_button(self, rect, label, action, hit_rect=None):
        mx, my = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mx, my)
        bg = (92, 70, 32) if hovered else (58, 45, 28)
        bdr = (235, 204, 105) if hovered else (150, 126, 74)
        pygame.draw.rect(self.window, bg, rect, border_radius=4)
        pygame.draw.rect(self.window, bdr, rect, 1, border_radius=4)
        txt = self._onboarding_guide_small_font.render(label, True, (245, 232, 190))
        self.window.blit(txt, txt.get_rect(center=rect.center))
        hit_rect = hit_rect or rect
        if hit_rect.w > 0 and hit_rect.h > 0:
            self._onboarding_guide_buttons.append((hit_rect.copy(), action))

    def _draw_onboarding_guide_scrollbar(self, viewport):
        max_scroll = self._max_onboarding_guide_scroll()
        if max_scroll <= 0:
            self._onboarding_guide_scrollbar_rect = pygame.Rect(0, 0, 0, 0)
            self._onboarding_guide_scrollbar_thumb_rect = pygame.Rect(0, 0, 0, 0)
            return
        track_w = max(4, int(0.006 * _SW))
        track = pygame.Rect(viewport.right + max(4, int(0.004 * _SW)),
                            viewport.y, track_w, viewport.h)
        content_h = max(viewport.h, int(getattr(self, '_onboarding_guide_content_h', 0) or 0))
        thumb_h = max(28, int(track.h * (viewport.h / content_h)))
        thumb_h = min(track.h, thumb_h)
        ratio = self._onboarding_guide_scroll / max_scroll if max_scroll else 0
        thumb_y = track.y + int((track.h - thumb_h) * ratio)
        thumb = pygame.Rect(track.x, thumb_y, track.w, thumb_h)
        self._onboarding_guide_scrollbar_rect = track
        self._onboarding_guide_scrollbar_thumb_rect = thumb
        pygame.draw.rect(self.window, (38, 34, 28, 160), track, border_radius=3)
        pygame.draw.rect(self.window, (142, 120, 72), thumb, border_radius=3)

    def _onboarding_guide_tab_hit(self, pos):
        for key, tab in (getattr(self, '_onboarding_guide_tab_rects', None) or {}).items():
            if tab.collidepoint(pos):
                return key
        return None

    def _handle_onboarding_guide_events(self, events):
        rulebook_active = getattr(self, '_onboarding_guide_tab', 'journey') == 'rulebook'
        rulebook = getattr(self, '_guide_rulebook', None) if rulebook_active else None
        for event in events:
            if event.type == pygame.MOUSEWHEEL:
                if rulebook:
                    rulebook.handle_events([event])
                    return True
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                area = getattr(self, '_onboarding_guide_scroll_area', None)
                track = getattr(self, '_onboarding_guide_scrollbar_rect', None)
                if ((area and area.collidepoint(pos)) or
                        (track and track.collidepoint(pos)) or
                        self._onboarding_guide_rect().collidepoint(pos)):
                    wheel_y = getattr(event, 'precise_y', None)
                    if wheel_y is None or wheel_y == 0:
                        wheel_y = getattr(event, 'y', 0)
                    self._scroll_onboarding_guide(wheel_y)
                return True
            if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                if rulebook:
                    if not self._onboarding_guide_tab_hit(pos):
                        rulebook.handle_events([event])
                else:
                    self._begin_onboarding_guide_touch_scroll(pos)
                return True
            if event.type == pygame.MOUSEMOTION:
                if rulebook:
                    rulebook.handle_events([event])
                elif getattr(self, '_onboarding_guide_touch_scrolling', False):
                    self._update_onboarding_guide_touch_scroll(getattr(event, 'pos', pygame.mouse.get_pos()))
                return True
            if event.type != pygame.MOUSEBUTTONUP or getattr(event, 'button', 0) != 1:
                continue
            pos = getattr(event, 'pos', pygame.mouse.get_pos())
            if rulebook:
                rulebook.handle_events([event])
            tab_key = self._onboarding_guide_tab_hit(pos)
            if tab_key:
                if tab_key != getattr(self, '_onboarding_guide_tab', 'journey'):
                    from utils import sound
                    sound.play('ui_click')
                    self._onboarding_guide_tab = tab_key
                    self._reset_onboarding_guide_scroll()
                    if tab_key == 'rulebook':
                        self._ensure_guide_rulebook()
                return True
            if not rulebook and self._end_onboarding_guide_touch_scroll():
                return True
            if self._onboarding_guide_close_rect.collidepoint(pos):
                self._onboarding_guide_open = False
                self._reset_onboarding_guide_scroll()
                return True
            if not self._onboarding_guide_rect().collidepoint(pos):
                self._onboarding_guide_open = False
                self._reset_onboarding_guide_scroll()
                return True
            if rulebook:
                return True
            for rect, action in list(self._onboarding_guide_buttons):
                if not rect.collidepoint(pos):
                    continue
                kind, value = action
                try:
                    if kind == 'claim':
                        data = onboarding_service.claim_reward(value)
                        reward = data.get('reward') or {}
                        if int(reward.get('gold') or 0):
                            self._suppress_next_gold_floater()
                        self._apply_onboarding_payload(data)
                        self._spawn_onboarding_reward_floaters(reward, rect.center)
                        from utils import sound
                        sound.play('quest_claim')
                        if getattr(self.state, 'set_msg', None):
                            self.state.set_msg(data.get('reward_label') or 'Reward claimed')
                    elif kind == 'resume_tutorial':
                        self._resume_onboarding_tutorial()
                    elif kind == 'continue_journey' and value:
                        if (self._onboarding() or {}).get(
                                'onboarding_skipped'):
                            self._resume_onboarding_tutorial()
                        self._onboarding_guide_open = False
                        self._reset_onboarding_guide_scroll()
                        self.state.screen = value
                    elif kind == 'start_lesson' and value:
                        data = onboarding_service.start_lesson(value)
                        self._apply_onboarding_payload(data)
                        destination = data.get('screen')
                        if destination:
                            self._onboarding_guide_open = False
                            self._reset_onboarding_guide_scroll()
                            self.state.screen = destination
                    elif kind == 'navigate' and value:
                        self._onboarding_guide_open = False
                        self._reset_onboarding_guide_scroll()
                        self.state.screen = value
                except Exception:
                    if getattr(self.state, 'set_msg', None):
                        self.state.set_msg('Guide action failed')
                return True
        return False

    # ── lightweight menu coach cards ──────────────────────────────

    def _menu_coach_allowed_common(self):
        onboarding = self._onboarding()
        if not onboarding:
            return False
        if onboarding.get('onboarding_skipped'):
            return False
        if getattr(self, '_onboarding_guide_open', False):
            return False
        if getattr(self, '_logout_dialogue', None):
            return False
        if getattr(self, '_welcome_present_dialogue', None):
            return False
        if getattr(self, '_starter_reveal_dialogue', None):
            return False
        if getattr(self, '_tutorial_complete_dialogue', None):
            return False
        if getattr(self, 'dialogue_box', None):
            return False
        return True

    def _menu_coach_seen(self):
        onboarding = self._onboarding()
        return set(onboarding.get('menu_hints_seen') or [])

    _REPLAY_STEP_IDS_BY_LESSON = {
        'grow_collection': {
            'open_first_main_booster',
            'open_first_side_booster',
            'sell_first_card',
            'trade_first_card',
            'finish_collection_lesson',
        },
        'build_attack': {
            'finish_second_conquer_battle',
            'finish_build_attack_lesson',
        },
        'run_kingdom': {
            'buy_first_cosmetic',
            'finish_run_kingdom_lesson',
        },
        'defend_land': {
            'save_first_defence_config',
            'finish_defend_land_lesson',
        },
        'duel_basics': {
            'finish_first_duel',
            'finish_duel_basics_lesson',
        },
    }

    _SKIPPABLE_MENU_COACH_STEPS = {
        'collection_growth_main': (
            'collection_growth_main', 'open_first_main_booster'),
        'collection_growth_side': (
            'collection_growth_side', 'open_first_side_booster'),
        'collection_sell_spare': (
            'collection_sell_spare', 'sell_first_card'),
        'collection_trade_spare': (
            'collection_trade_spare', 'trade_first_card'),
        'conquer_choose_next_land': ('conquer_choose_next_land',),
        'conquer_open_next_attack': ('conquer_open_next_attack',),
        'conquer_build_yourself': ('conquer_build_yourself',),
        'conquer_build_yourself_tactics': (
            'conquer_build_yourself_tactics',),
        'conquer_build_yourself_battle': (
            'conquer_build_yourself_battle',
            'finish_second_conquer_battle',
        ),
        'kingdom_buy_cosmetic': (
            'kingdom_buy_cosmetic', 'buy_first_cosmetic'),
        'defence_save': (
            'defence_save', 'save_first_defence_config'),
    }

    def _replaying_onboarding_lesson_id(self):
        return (self._onboarding() or {}).get('replaying_lesson')

    def _onboarding_lesson_replaying(self, lesson_id):
        return self._replaying_onboarding_lesson_id() == lesson_id

    def _onboarding_completed_steps(self):
        onboarding = self._onboarding() or {}
        completed = set(onboarding.get('completed_steps') or [])
        replaying = onboarding.get('replaying_lesson')
        if replaying:
            completed.difference_update(
                self._REPLAY_STEP_IDS_BY_LESSON.get(replaying) or ())
            completed.update(onboarding.get('lesson_replay_steps') or [])
        completed.update(onboarding.get('lesson_skipped_steps') or [])
        return completed

    def _active_onboarding_lesson_id(self):
        onboarding = self._onboarding() or {}
        lesson_id = onboarding.get('active_lesson')
        dismissed = set(onboarding.get('lessons_dismissed') or [])
        return lesson_id if lesson_id and lesson_id not in dismissed else None

    def _active_onboarding_lesson(self):
        lesson_id = self._active_onboarding_lesson_id()
        if not lesson_id:
            return None
        return next((
            lesson for lesson in (self._onboarding() or {}).get('lessons') or []
            if lesson.get('id') == lesson_id
        ), None)

    def _first_session_journey_phase(self):
        """Client mirror of onboarding_service._journey_metadata.

        The mandatory tutorial is the kingdom core loop: reveal the prepared
        starter cards -> conquer the first land. Production, kingdom config, and
        defence setup are deferred to on-demand coaching, and the duel is
        optional, so no phase routes to those areas.
        """
        completed = self._onboarding_completed_steps()
        if ('starter_suit_reveal' not in self._menu_coach_seen()
                and 'finish_first_conquer_battle' not in completed):
            return 'reveal_starter_cards'
        if 'finish_first_conquer_battle' not in completed:
            return 'first_conquest'
        if 'finish_tutorial' not in completed:
            return 'finish_tutorial'
        return 'complete'

    def _first_session_next_action(self):
        phase = self._first_session_journey_phase()
        if phase == 'reveal_starter_cards':
            return {
                'screen': 'collection',
                'label': 'Reveal Starter Cards',
                'target_id': 'starter_suit_reveal',
            }
        if phase == 'first_conquest':
            return {
                'screen': 'kingdom',
                'label': 'Conquer First Land',
                'target_id': 'recommended_tutorial_land',
            }
        if phase == 'finish_tutorial':
            return {
                'screen': 'kingdom',
                'label': 'Finish the Kingdom Tour',
                'target_id': 'kingdom_after_conquer_map',
            }
        return None

    def _complete_onboarding_step(self, step_id):
        try:
            data = onboarding_service.complete_step(step_id)
            self._apply_onboarding_payload(data)
            return True
        except Exception:
            state = getattr(self, 'state', None)
            if getattr(state, 'set_msg', None):
                state.set_msg('Could not finish the tutorial. Please try again.')
            return False

    def _mark_onboarding_step_completed_local(self, step_id):
        if not step_id:
            return
        ud = getattr(self.state, 'user_dict', None)
        if not ud:
            return
        onboarding = dict(ud.get('onboarding') or {})
        completed = list(onboarding.get('completed_steps') or [])
        if step_id not in completed:
            completed.append(step_id)
        onboarding['completed_steps'] = completed
        ud['onboarding'] = onboarding

    def _mark_menu_coach_seen(self, step_id):
        if not step_id:
            return
        try:
            data = onboarding_service.mark_tip(f'menu:{step_id}')
            self._apply_onboarding_payload(data)
            return
        except Exception:
            pass
        ud = getattr(self.state, 'user_dict', None)
        if not ud:
            return
        onboarding = dict(ud.get('onboarding') or {})
        seen = list(onboarding.get('menu_hints_seen') or [])
        if step_id not in seen:
            seen.append(step_id)
        onboarding['menu_hints_seen'] = seen
        ud['onboarding'] = onboarding

    def _mark_menu_coaches_seen(self, step_ids, *, event=None):
        step_ids = tuple(step_ids or ())
        if not step_ids:
            return
        try:
            data = onboarding_service.mark_tips(
                [f'menu:{step_id}' for step_id in step_ids], event=event)
            self._apply_onboarding_payload(data)
            return
        except Exception:
            for step_id in step_ids:
                self._mark_menu_coach_seen(step_id)

    @staticmethod
    def _menu_coach_lesson_ids(step_id):
        groups = {
            'collection_growth_intro': (
                'collection_growth_intro',),
            'collection_growth_main': (
                'collection_growth_main', 'collection_growth_side'),
            'collection_growth_side': (
                'collection_growth_main', 'collection_growth_side',
                'collection_sell_spare', 'collection_trade_spare'),
            'collection_sell_spare': (
                'collection_growth_main', 'collection_growth_side',
                'collection_sell_spare', 'collection_trade_spare'),
            'collection_trade_spare': (
                'collection_growth_main', 'collection_growth_side',
                'collection_sell_spare', 'collection_trade_spare'),
            'build_attack_intro_window': (
                'build_attack_intro_window',
                'conquer_choose_next_land',
                'conquer_open_next_attack',
                'conquer_build_yourself',
                'conquer_build_yourself_tactics',
                'conquer_build_yourself_prelude',
                'conquer_build_yourself_battle',
            ),
            'conquer_build_yourself': (
                'conquer_build_yourself',
                'conquer_build_yourself_tactics',
                'conquer_build_yourself_prelude',
                'conquer_build_yourself_battle',
            ),
            'conquer_build_yourself_tactics': (
                'conquer_build_yourself',
                'conquer_build_yourself_tactics',
                'conquer_build_yourself_prelude',
                'conquer_build_yourself_battle',
            ),
            'conquer_build_yourself_prelude': (
                'conquer_build_yourself',
                'conquer_build_yourself_tactics',
                'conquer_build_yourself_prelude',
                'conquer_build_yourself_battle',
            ),
            'conquer_build_yourself_battle': (
                'conquer_build_yourself',
                'conquer_build_yourself_tactics',
                'conquer_build_yourself_prelude',
                'conquer_build_yourself_battle',
            ),
            'conquer_choose_next_land': (
                'conquer_choose_next_land',
                'conquer_open_next_attack',
                'conquer_build_yourself',
                'conquer_build_yourself_tactics',
                'conquer_build_yourself_prelude',
                'conquer_build_yourself_battle',
            ),
            'conquer_open_next_attack': (
                'conquer_choose_next_land',
                'conquer_open_next_attack',
                'conquer_build_yourself',
                'conquer_build_yourself_tactics',
                'conquer_build_yourself_prelude',
                'conquer_build_yourself_battle',
            ),
            'kingdom_management_intro': (
                'kingdom_management_intro',),
            'kingdom_open_management': (
                'kingdom_open_management',
                'kingdom_collect_production',
                'kingdom_config_essentials',
            ),
            'kingdom_collect_production': (
                'kingdom_open_management',
                'kingdom_collect_production',
                'kingdom_config_essentials',
            ),
            'defence_choose_land': (
                'defence_choose_land', 'defence_open_config',
                'defence_intro', 'defence_battle_plan',
                'defence_final_response', 'defence_save',
            ),
            'defence_open_config': (
                'defence_choose_land', 'defence_open_config',
                'defence_intro', 'defence_battle_plan',
                'defence_final_response', 'defence_save',
            ),
            'defence_intro': (
                'defence_intro', 'defence_battle_plan',
                'defence_final_response', 'defence_save',
            ),
            'defence_battle_plan': (
                'defence_intro', 'defence_battle_plan',
                'defence_final_response', 'defence_save',
            ),
            'defence_final_response': (
                'defence_intro', 'defence_battle_plan',
                'defence_final_response', 'defence_save',
            ),
            'defence_save': (
                'defence_intro', 'defence_battle_plan',
                'defence_final_response', 'defence_save',
            ),
            'kingdom_config_essentials': (
                'kingdom_config_essentials',),
            'kingdom_config_shields_style': (
                'kingdom_config_shields_style',),
            'kingdom_buy_cosmetic': (
                'kingdom_buy_cosmetic',),
            'defend_land_intro_window': (
                'defend_land_intro_window',
                'defence_choose_land', 'defence_open_config',
                'defence_intro', 'defence_battle_plan',
                'defence_final_response', 'defence_save',
            ),
        }
        return groups.get(step_id)

    @staticmethod
    def _menu_coach_lesson_id(step_id):
        if step_id in (
                'collection_growth_intro',
                'collection_growth_main',
                'collection_growth_side',
                'collection_sell_spare',
                'collection_trade_spare'):
            return 'grow_collection'
        if step_id in (
                'build_attack_intro_window',
                'conquer_choose_next_land',
                'conquer_open_next_attack',
                'conquer_build_yourself',
                'conquer_build_yourself_tactics',
                'conquer_build_yourself_prelude',
                'conquer_build_yourself_battle'):
            return 'build_attack'
        if step_id in (
                'kingdom_management_intro',
                'kingdom_open_management',
                'kingdom_collect_production',
                'kingdom_config_essentials',
                'kingdom_config_shields_style',
                'kingdom_buy_cosmetic'):
            return 'run_kingdom'
        if step_id in (
                'defend_land_intro_window',
                'defence_choose_land',
                'defence_open_config',
                'defence_intro',
                'defence_battle_plan',
                'defence_final_response',
                'defence_save'):
            return 'defend_land'
        return None

    def _wrap_menu_coach_lines(self, text, max_width, max_lines=5):
        words = str(text or '').split()
        lines = []
        current = ''
        for word in words:
            candidate = word if not current else f'{current} {word}'
            if self._menu_coach_font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:max_lines]

    def _draw_menu_coach_button(self, rect, label, action, muted=False):
        draw_coach_button(
            self.window, rect, label, self._menu_coach_font, muted=muted)
        self._menu_coach_buttons.append((rect.copy(), action))

    def _menu_coach_target_rects(self, step):
        rects = step.get('rects') if step else None
        if rects:
            return [pygame.Rect(rect) for rect in rects]
        return [pygame.Rect(step['rect'])]

    def _menu_coach_passthrough_rects(self, step):
        """Rects where an ``action='click'`` tap is let through to the screen.

        Defaults to the visual target rects, but a step may set
        ``click_through_rects`` to allow taps over a wider area than the
        highlighted target (e.g. tapping anywhere on the map while the coach
        card only marks one land), so the underlying view stays interactive.
        """
        rects = step.get('click_through_rects') if step else None
        if rects:
            return [pygame.Rect(rect) for rect in rects]
        return self._menu_coach_target_rects(step)

    def _menu_coach_target_bounds(self, step):
        rects = self._menu_coach_target_rects(step)
        bounds = rects[0].copy()
        for rect in rects[1:]:
            bounds.union_ip(rect)
        return bounds

    def _draw_menu_coach(self, step):
        self._menu_coach_buttons = []
        self._menu_coach_card_rect = None
        self._menu_coach_step = step
        if not step:
            return
        target_rects = self._menu_coach_target_rects(step)
        draws_next = step.get('action', 'next') == 'next'
        draws_finish = bool(step.get('finish_tutorial_button'))
        lesson_id = self._menu_coach_lesson_id(step.get('id'))
        draws_step_skip = bool(
            lesson_id
            and step.get('id') in self._SKIPPABLE_MENU_COACH_STEPS
            and step.get('allow_skip', True)
        )
        draws_pause = (
            not draws_finish
            and not (self._onboarding() or {}).get('onboarding_skipped')
            and step.get('allow_skip', True)
        )
        card, button_h = draw_coach_panel(
            self.window,
            target_rects,
            title=step['title'],
            body=step['body'],
            title_font=self._menu_coach_title_font,
            body_font=self._menu_coach_font,
            ticks=pygame.time.get_ticks(),
            width_ratio=0.36,
            min_width=390 if draws_step_skip else 320,
            max_width=420,
            min_height=152,
            max_lines=step.get('max_lines', 5),
            has_button_row=(
                draws_next or draws_finish or draws_step_skip or draws_pause),
            placement=step.get('coach_placement'),
        )
        if card is None:
            return
        self._menu_coach_card_rect = card.copy()

        if draws_next:
            label = step.get('button_label') or 'Next'
            button_w = max(76, self._menu_coach_font.size(label)[0] + 28)
            next_rect = pygame.Rect(card.right - button_w - 14, card.bottom - button_h - 12,
                                    button_w, button_h)
            self._draw_menu_coach_button(next_rect, label, ('next', step['id']))
        if draws_finish:
            label = step.get('finish_button_label') or 'Finish tutorial'
            button_w = max(132, self._menu_coach_font.size(label)[0] + 28)
            finish_rect = pygame.Rect(card.right - button_w - 14,
                                      card.bottom - button_h - 12,
                                      button_w, button_h)
            self._draw_menu_coach_button(
                finish_rect, label, ('finish_tutorial', step['id']))
        left_x = card.x + 14
        if draws_step_skip:
            label = 'Skip this step'
            button_w = max(96, self._menu_coach_font.size(label)[0] + 20)
            skip_rect = pygame.Rect(
                left_x, card.bottom - button_h - 12, button_w, button_h)
            self._draw_menu_coach_button(
                skip_rect, label, ('skip_lesson_step', step['id']),
                muted=True)
            left_x = skip_rect.right + 8
        if draws_pause:
            label = 'Pause guidance'
            button_w = max(72, self._menu_coach_font.size(label)[0] + 20)
            pause_rect = pygame.Rect(
                left_x, card.bottom - button_h - 12, button_w, button_h)
            self._draw_menu_coach_button(
                pause_rect, label, ('skip_tutorial', step['id']),
                muted=True)

    def _menu_coach_blocking_event_types(self):
        event_types = {
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEWHEEL,
            pygame.KEYDOWN,
            pygame.KEYUP,
        }
        text_input = getattr(pygame, 'TEXTINPUT', None)
        if text_input is not None:
            event_types.add(text_input)
        return event_types

    def _menu_coach_interactive_rects(self, step):
        """Areas that stay interactive while a coach card is visible.

        Click-action lessons already pass their target through.  A coach-only
        card can opt a larger background area in as well, which the Kingdom
        screen uses to keep map exploration live behind its final card.
        """
        explicit = step.get('interactive_rects') if step else None
        if explicit:
            return [pygame.Rect(rect) for rect in explicit]
        if step and step.get('action', 'next') == 'click':
            return self._menu_coach_passthrough_rects(step)
        return []

    def _handle_menu_coach_events(self, events, step=_MENU_COACH_STEP_UNSET):
        if step is _MENU_COACH_STEP_UNSET:
            step = getattr(self, '_menu_coach_step', None)
        if not step:
            return False
        action = step.get('action', 'next')
        block_types = self._menu_coach_blocking_event_types()
        passthrough_rects = self._menu_coach_passthrough_rects(step)
        interactive_rects = self._menu_coach_interactive_rects(step)
        for event in events:
            if event.type == pygame.QUIT:
                continue
            if event.type not in block_types:
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                self._menu_coach_pressed_button_action = None
                for rect, button_action in list(self._menu_coach_buttons):
                    if rect.collidepoint(pos):
                        self._menu_coach_pressed_button_action = button_action
                        return True
                card_rect = getattr(self, '_menu_coach_card_rect', None)
                if card_rect and card_rect.collidepoint(pos):
                    return True
                if (action != 'click'
                        and any(rect.collidepoint(pos)
                                for rect in interactive_rects)):
                    return False
                if action != 'click':
                    return True
                if any(rect.collidepoint(pos) for rect in passthrough_rects):
                    return False
                return True
            if event.type == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                pressed_action = getattr(self, '_menu_coach_pressed_button_action', None)
                self._menu_coach_pressed_button_action = None
                for rect, button_action in list(self._menu_coach_buttons):
                    if not rect.collidepoint(pos):
                        continue
                    if pressed_action and pressed_action != button_action:
                        return True
                    kind, step_id = button_action
                    from utils import sound
                    sound.play('ui_back' if kind in (
                        'skip_tutorial', 'skip_lesson_step',
                        'dismiss_lesson') else 'ui_click')
                    if kind == 'next':
                        self._mark_menu_coach_seen(step_id)
                        self._after_menu_coach_next(step_id)
                    elif kind == 'finish_tutorial':
                        handler = getattr(self, '_finish_menu_coach_tutorial', None)
                        if callable(handler):
                            handler(step_id)
                        else:
                            self._mark_menu_coach_seen(step_id)
                    elif kind == 'skip_tutorial':
                        self._pause_onboarding_tutorial()
                    elif kind == 'skip_lesson_step':
                        lesson_id = self._menu_coach_lesson_id(step_id)
                        try:
                            data = onboarding_service.skip_lesson_step(
                                lesson_id, step_id)
                            self._apply_onboarding_payload(data)
                        except Exception:
                            onboarding = dict(self._onboarding() or {})
                            skipped = set(
                                onboarding.get('lesson_skipped_steps') or [])
                            skipped.update(
                                self._SKIPPABLE_MENU_COACH_STEPS.get(
                                    step_id) or ())
                            onboarding['lesson_skipped_steps'] = sorted(
                                skipped)
                            seen = set(
                                onboarding.get('menu_hints_seen') or [])
                            seen.update(
                                skipped_id for skipped_id in skipped
                                if self._menu_coach_lesson_id(skipped_id)
                            )
                            onboarding['menu_hints_seen'] = list(seen)
                            if getattr(self.state, 'user_dict', None):
                                self.state.user_dict[
                                    'onboarding'] = onboarding
                        if getattr(self.state, 'set_msg', None):
                            self.state.set_msg(
                                'Step skipped. Continue with the next step.')
                    elif kind == 'dismiss_lesson':
                        lesson_id = self._menu_coach_lesson_id(step_id)
                        if lesson_id:
                            try:
                                data = onboarding_service.dismiss_lesson(
                                    lesson_id)
                                self._apply_onboarding_payload(data)
                            except Exception:
                                onboarding = dict(self._onboarding() or {})
                                dismissed = list(
                                    onboarding.get('lessons_dismissed') or [])
                                if lesson_id not in dismissed:
                                    dismissed.append(lesson_id)
                                onboarding['lessons_dismissed'] = dismissed
                                onboarding['active_lesson'] = None
                                if getattr(self.state, 'user_dict', None):
                                    self.state.user_dict[
                                        'onboarding'] = onboarding
                        else:
                            lesson_ids = (
                                self._menu_coach_lesson_ids(step_id)
                                or (step_id,))
                            self._mark_menu_coaches_seen(
                                lesson_ids, event='lesson_dismissed')
                        if getattr(self.state, 'set_msg', None):
                            self.state.set_msg('Lesson skipped. Other guidance stays active.')
                    return True
                card_rect = getattr(self, '_menu_coach_card_rect', None)
                if card_rect and card_rect.collidepoint(pos):
                    return True
                if (action != 'click'
                        and any(rect.collidepoint(pos)
                                for rect in interactive_rects)):
                    return False
                if action == 'click':
                    if any(rect.collidepoint(pos) for rect in passthrough_rects):
                        if step.get('mark_on_click', True):
                            self._mark_menu_coach_seen(step.get('id'))
                        return False
                    return True
                return True
            if event.type == pygame.MOUSEWHEEL:
                pos = getattr(event, 'pos', None) or pygame.mouse.get_pos()
                card_rect = getattr(self, '_menu_coach_card_rect', None)
                if card_rect and card_rect.collidepoint(pos):
                    return True
                if any(rect.collidepoint(pos) for rect in interactive_rects):
                    return False
                return True
            return True
        return False

    def _after_menu_coach_next(self, step_id):
        step = getattr(self, '_menu_coach_step', None) or {}
        if step.get('id') != step_id:
            return
        navigate_screen = step.get('navigate_screen')
        if navigate_screen and getattr(self, 'state', None) is not None:
            self.state.screen = navigate_screen

    def _current_onboarding_guide_coach_step(self):
        if not getattr(self, '_onboarding_guide_open', False):
            return None
        if getattr(self, '_onboarding_guide_tab', 'journey') != 'journey':
            return None
        onboarding = self._onboarding()
        if not onboarding:
            return None
        if onboarding.get('onboarding_skipped'):
            return None
        completed = set(onboarding.get('completed_steps') or [])
        if 'finish_tutorial' in completed:
            return None
        seen = self._menu_coach_seen()
        if 'guide_rewards_track' not in seen:
            row = (self._onboarding_guide_item_rects.get('finish_tutorial')
                   or self._onboarding_guide_item_rects.get('collect_first_kingdom_production'))
            if row is None:
                row = self._onboarding_guide_rect().inflate(-40, -140)
            return {
                'id': 'guide_rewards_track',
                'title': 'Rewards Track Your Progress',
                'rect': row,
                'body': 'The checklist and goals grant rewards as you learn. Finish the kingdom tutorial to claim this one.',
                'max_lines': 4,
            }
        return None

    @staticmethod
    def _fit_text(text, font, max_width):
        text = str(text or '')
        if font.size(text)[0] <= max_width:
            return text
        ell = '...'
        max_width = max(0, max_width - font.size(ell)[0])
        out = ''
        for char in text:
            if font.size(out + char)[0] > max_width:
                break
            out += char
        return out.rstrip() + ell
