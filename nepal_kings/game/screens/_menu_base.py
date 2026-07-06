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
import pygame
from config import settings
from game.components.coach_card import draw_coach_highlight, draw_coach_spotlight
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
        self._onboarding_guide_font = settings.get_font(max(16, int(0.020 * _SH)))
        self._onboarding_guide_small_font = settings.get_font(max(14, int(0.017 * _SH)))
        self._onboarding_guide_title_font = settings.get_font(max(24, int(0.034 * _SH)), bold=True)
        self._onboarding_guide_section_font = settings.get_font(max(18, int(0.023 * _SH)), bold=True)
        self._onboarding_guide_badge_font = settings.get_font(max(16, int(0.020 * _SH)), bold=True)
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
        self._menu_coach_font = settings.get_font(max(14, int(0.018 * _SH)))
        self._menu_coach_title_font = settings.get_font(max(16, int(0.024 * _SH)), bold=True)
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
        reward = dict(reward or {})
        items = []
        gold = int(reward.get('gold') or 0)
        if gold > 0:
            items.append({'kind': 'gold', 'label': f'{gold} gold',
                          'description': 'Spend it on booster packs, cosmetics, and shields.'})
        main = int(reward.get('booster_packs') or 0)
        if main > 0:
            items.append({'kind': 'main_booster',
                          'label': f"{main} main booster" + ('' if main == 1 else 's'),
                          'description': 'Main cards build your core figures, spells, and tactics.'})
        side = int(reward.get('booster_packs_side') or 0)
        if side > 0:
            items.append({'kind': 'side_booster',
                          'label': f"{side} side booster" + ('' if side == 1 else 's'),
                          'description': 'Side cards unlock advanced figures and effects.'})
        maps = int(reward.get('maps') or 0)
        if maps > 0:
            items.append({'kind': 'map',
                          'label': f"{maps} map" + ('' if maps == 1 else 's'),
                          'description': 'Maps skip the cooldown after conquering a land.'})
        return items

    # Ordered: conquer tutorial completes first, the duel tutorial later.
    _TUTORIAL_COMPLETIONS = (
        ('finish_tutorial', 'Conquer Tutorial Complete!', [
            "You know the conquer loop: open packs, build an attack, take the land.",
            "Keep expanding your kingdom, or try the Duel tutorial from the Duel menu whenever you're ready.",
        ]),
        ('finish_first_duel', 'Duel Tutorial Complete!', [
            "You've played a full duel: building figures, casting spells, and winning battles.",
            "Quick duels and kingdom conquests are all yours now. Have fun!",
        ]),
    )

    def _pending_tutorial_completion(self):
        """Return ``(step_id, title, lines, reward)`` for a completed-but-
        uncelebrated tutorial milestone, or ``None``."""
        onboarding = self._onboarding()
        if not onboarding or onboarding.get('welcome_pending'):
            return None
        if onboarding.get('onboarding_skipped'):
            return None
        celebrated = getattr(self, '_tutorial_celebrated', None)
        if celebrated is None:
            celebrated = self._tutorial_celebrated = set()
        steps = {s.get('id'): s for s in (onboarding.get('core_steps') or [])}
        for step_id, title, lines in self._TUTORIAL_COMPLETIONS:
            payload = steps.get(step_id)
            if not payload or not payload.get('completed') or payload.get('claimed'):
                continue
            if step_id in celebrated:
                continue
            if self._tutorial_completion_blocked(step_id):
                continue
            return step_id, title, lines, payload.get('reward')
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
        step_id, title, lines, reward = pending
        if getattr(self, '_tutorial_celebrated', None) is None:
            self._tutorial_celebrated = set()
        self._tutorial_celebrated.add(step_id)
        self._tutorial_complete_step_id = step_id
        self._tutorial_complete_dialogue = RewardsRevealDialogueBox(
            self.window,
            title,
            'victory',
            lines,
            self._reward_reveal_items(reward),
            footer_when_done='Reward claimed. Well played!',
            hint_text='Click each box to reveal your reward.',
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
            self._tutorial_complete_dialogue = None
            self._tutorial_complete_step_id = None
            if step_id:
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

    def _reset_onboarding_guide_scroll(self):
        self._onboarding_guide_scroll = 0
        self._onboarding_guide_touch_scrolling = False
        self._onboarding_guide_touch_last_y = 0
        self._onboarding_guide_touch_moved = 0

    def _onboarding_guide_row_metrics(self):
        row_h = max(42, min(64, int(0.060 * _SH)))
        return row_h, 6

    @staticmethod
    def _onboarding_guide_visible_items(items):
        visible = [item for item in items if item.get('claimable')]
        visible += [item for item in items if not item.get('completed') and item not in visible]
        visible += [item for item in items if item.get('completed') and item not in visible]
        return visible

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

        intro = 'Finish the conquer tutorial, then try the optional duel tutorial. Claim rewards as milestones unlock.'
        intro_surf = self._onboarding_guide_small_font.render(
            self._fit_text(intro, self._onboarding_guide_small_font, rect.w - 44),
            True,
            settings.DIALOGUE_BOX_MSG_TEXT_CLR,
        )
        intro_y = content_top
        self.window.blit(intro_surf, (rect.x + 22, intro_y))

        area_top = intro_y + intro_surf.get_height() + int(0.026 * _SH)
        if onboarding.get('onboarding_skipped'):
            pause_h = max(42, int(0.052 * _SH))
            pause_rect = pygame.Rect(rect.x + 22, area_top, rect.w - 44, pause_h)
            pause_bg = pygame.Surface((pause_rect.w, pause_rect.h), pygame.SRCALPHA)
            pause_bg.fill((34, 29, 23, 168))
            self.window.blit(pause_bg, pause_rect.topleft)
            pygame.draw.rect(self.window, (150, 126, 74), pause_rect, 1, border_radius=5)
            label = self._onboarding_guide_font.render(
                'Tutorial paused', True, (235, 222, 184))
            self.window.blit(label, (
                pause_rect.x + 12,
                pause_rect.y + pause_rect.h // 2 - label.get_height() // 2,
            ))
            resume_label = 'Continue tutorial'
            resume_w = max(138, self._onboarding_guide_small_font.size(resume_label)[0] + 26)
            resume_h = max(28, self._onboarding_guide_small_font.get_height() + 8)
            resume_rect = pygame.Rect(
                pause_rect.right - resume_w - 12,
                pause_rect.y + (pause_rect.h - resume_h) // 2,
                resume_w,
                resume_h,
            )
            self._draw_onboarding_guide_button(
                resume_rect, resume_label, ('resume_tutorial', None))
            area_top = pause_rect.bottom + int(0.018 * _SH)

        area_h = max(84, int(0.108 * _SH))
        self._draw_onboarding_area_overview(
            pygame.Rect(rect.x + 22, area_top, rect.w - 44, area_h))

        top = area_top + area_h + int(0.020 * _SH)
        gap = int(0.018 * _SW)
        scroll_gutter = max(10, int(0.010 * _SW))
        columns_w = rect.w - 44 - scroll_gutter
        col_w = (columns_w - gap) // 2
        header_h = self._onboarding_guide_section_font.get_height() + 8
        rows_viewport = pygame.Rect(rect.x + 22, top + header_h,
                                    columns_w, rect.bottom - top - header_h - 22)
        rows_viewport.h = max(42, rows_viewport.h)
        content_h = max(
            self._onboarding_guide_rows_height(onboarding.get('core_steps') or []),
            self._onboarding_guide_rows_height(onboarding.get('early_goals') or []),
        )
        self._onboarding_guide_scroll_area = rows_viewport.copy()
        self._onboarding_guide_content_h = content_h
        self._clamp_onboarding_guide_scroll()
        scroll = int(getattr(self, '_onboarding_guide_scroll', 0) or 0)
        col_h = header_h + rows_viewport.h
        left = pygame.Rect(rect.x + 22, top, col_w, col_h)
        right = pygame.Rect(left.right + gap, top, col_w, col_h)
        self._draw_onboarding_guide_section(
            'Checklist',
            onboarding.get('core_steps') or [],
            left,
            scroll_offset=scroll,
            clip_rect=pygame.Rect(left.x, rows_viewport.y, left.w, rows_viewport.h),
        )
        self._draw_onboarding_guide_section(
            'Early Goals',
            onboarding.get('early_goals') or [],
            right,
            scroll_offset=scroll,
            clip_rect=pygame.Rect(right.x, rows_viewport.y, right.w, rows_viewport.h),
        )
        self._draw_onboarding_guide_scrollbar(rows_viewport)

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

    # ── Guide tabs (Journey / Rulebook) ────────────────────────────

    _GUIDE_TABS = (('journey', 'Journey'), ('rulebook', 'Rulebook'))

    def _onboarding_guide_tab_metrics(self, rect):
        """Shared geometry for the tab bar: (tabs_y, tab_h, content_top)."""
        title_h = self._onboarding_guide_title_font.get_height()
        tab_h = max(34, int(0.044 * _SH))
        tabs_y = rect.y + 16 + title_h + 12
        content_top = tabs_y + tab_h + max(10, int(0.016 * _SH))
        return tabs_y, tab_h, content_top

    def _draw_onboarding_guide_tabs(self, rect):
        """Draw the segmented Journey/Rulebook control; returns content top y."""
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
        badge_count = self._onboarding_guide_badge_count()
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
            if key == 'journey' and badge_count > 0:
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

    def _draw_onboarding_area_overview(self, rect):
        header = self._onboarding_guide_section_font.render(
            'Where To Go', True, settings.SUB_SCREEN_HEADER_CLR)
        self.window.blit(header, (rect.x, rect.y))
        items = [
            ('Kingdom', 'Conquer lands and collect production.'),
            ('Duel', 'Play full duels against other players.'),
            ('Collection', 'Open boosters, trade, and sell cards.'),
            ('Rankings', 'Compare progress with other players.'),
        ]
        gap = int(0.010 * _SW)
        top = rect.y + header.get_height() + 8
        row_h = max(46, rect.bottom - top)
        card_w = (rect.w - gap * (len(items) - 1)) // len(items)
        x = rect.x
        for title, body in items:
            card = pygame.Rect(x, top, card_w, row_h)
            bg = pygame.Surface((card.w, card.h), pygame.SRCALPHA)
            bg.fill((24, 22, 19, 150))
            self.window.blit(bg, card.topleft)
            pygame.draw.rect(self.window, (112, 96, 66), card, 1, border_radius=5)
            title_surf = self._onboarding_guide_font.render(title, True, (235, 222, 184))
            self.window.blit(title_surf, (card.x + 10, card.y + 7))
            body = self._fit_text(body, self._onboarding_guide_small_font, card.w - 20)
            body_surf = self._onboarding_guide_small_font.render(body, True, (170, 160, 135))
            self.window.blit(body_surf, (card.x + 10, card.bottom - body_surf.get_height() - 7))
            x += card_w + gap

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
            title_max_w = row.w - 132
            title = self._fit_text(item.get('title') or '', self._onboarding_guide_font, title_max_w)
            title_surf = self._onboarding_guide_font.render(title, True, (235, 222, 184))
            self.window.blit(title_surf, (row.x + 26, row.y + 6))

            desc_max_w = row.w - 138
            desc = self._fit_text(item.get('description') or '', self._onboarding_guide_small_font, desc_max_w)
            desc_surf = self._onboarding_guide_small_font.render(desc, True, (170, 160, 135))
            self.window.blit(desc_surf, (row.x + 26, row.y + row_h - desc_surf.get_height() - 6))

            if item.get('claimable'):
                claim_w = max(68, self._onboarding_guide_small_font.size('Claim')[0] + 22)
                claim_h = max(28, self._onboarding_guide_small_font.get_height() + 8)
                claim_rect = pygame.Rect(row.right - claim_w - 12, row.y + (row_h - claim_h) // 2,
                                         claim_w, claim_h)
                hit_rect = claim_rect.clip(clip_rect) if clip_rect else claim_rect.copy()
                self._draw_onboarding_guide_button(claim_rect, 'Claim', ('claim', item.get('id')), hit_rect=hit_rect)
                self._draw_onboarding_reward_icons(item.get('reward') or {}, claim_rect.left - 10, row.y + row_h // 2)
            elif item.get('claimed'):
                claimed = self._onboarding_guide_small_font.render('claimed', True, (120, 190, 125))
                self.window.blit(claimed, (row.right - claimed.get_width() - 10,
                                           row.y + row_h // 2 - claimed.get_height() // 2))
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
                        if getattr(self.state, 'set_msg', None):
                            self.state.set_msg(data.get('reward_label') or 'Reward claimed')
                    elif kind == 'resume_tutorial':
                        self._resume_onboarding_tutorial()
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

    def _onboarding_completed_steps(self):
        return set((self._onboarding() or {}).get('completed_steps') or [])

    def _first_session_journey_phase(self):
        """Client mirror of onboarding_service._journey_metadata.

        The mandatory tutorial is the kingdom core loop: open a starter booster
        -> conquer the first land. Production, the kingdom-config tour, and
        defence setup are deferred to on-demand coaching, and the duel is
        optional, so no phase routes to those areas.
        """
        completed = self._onboarding_completed_steps()
        if 'open_first_main_booster' not in completed:
            return 'open_starter_pack'
        if 'finish_first_conquer_battle' not in completed:
            return 'first_conquest'
        return 'complete'

    def _first_session_next_action(self):
        phase = self._first_session_journey_phase()
        if phase == 'open_starter_pack':
            return {
                'screen': 'collection',
                'label': 'Open a Booster Pack',
                'target_id': 'collection_open_main_booster',
            }
        if phase == 'first_conquest':
            return {
                'screen': 'kingdom',
                'label': 'Conquer First Land',
                'target_id': 'recommended_tutorial_land',
            }
        return None

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
        mx, my = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mx, my)
        if muted:
            # Secondary/ghost style so "Skip tutorial" reads clearly as the
            # lesser action and isn't confused with the primary "Next".
            bg = (40, 37, 32) if hovered else (30, 28, 24)
            bdr = (110, 100, 84) if hovered else (78, 72, 60)
            txt_clr = (170, 160, 142) if hovered else (132, 124, 108)
        else:
            bg = (96, 70, 34) if hovered else (58, 45, 28)
            bdr = (235, 204, 105) if hovered else (150, 126, 74)
            txt_clr = (245, 232, 190)
        pygame.draw.rect(self.window, bg, rect, border_radius=4)
        pygame.draw.rect(self.window, bdr, rect, 1, border_radius=4)
        txt = self._menu_coach_font.render(label, True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))
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
        self._menu_coach_step = step
        if not step:
            return
        target_rects = self._menu_coach_target_rects(step)
        draw_coach_spotlight(self.window, target_rects)
        draw_coach_highlight(self.window, target_rects, pygame.time.get_ticks())
        target = self._menu_coach_target_bounds(step).inflate(14, 14)

        card_w = min(420, max(320, int(0.36 * _SW)), _SW - 16)
        body_lines = self._wrap_menu_coach_lines(
            step['body'], card_w - 28, max_lines=step.get('max_lines', 5))
        title_h = self._menu_coach_title_font.get_height()
        body_line_h = self._menu_coach_font.get_height() + 3
        button_h = max(30, self._menu_coach_font.get_height() + 10)
        draws_next = step.get('action', 'next') == 'next'
        draws_finish = bool(step.get('finish_tutorial_button'))
        draws_skip = (
            not draws_finish
            and not (self._onboarding() or {}).get('onboarding_skipped')
        )
        button_space = button_h + 16 if (draws_next or draws_finish or draws_skip) else 8
        card_h = max(152, 22 + title_h + 10 + len(body_lines) * body_line_h + button_space)
        gap = 14
        if target.right + gap + card_w < _SW:
            card_x = target.right + gap
        else:
            card_x = max(8, target.left - gap - card_w)
        card_y = max(8, min(target.centery - card_h // 2, _SH - card_h - 8))
        card = pygame.Rect(card_x, card_y, card_w, card_h)
        surf = pygame.Surface((card.w, card.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (24, 20, 16, 235), surf.get_rect(), border_radius=8)
        self.window.blit(surf, card.topleft)
        pygame.draw.rect(self.window, (220, 185, 88), card, 2, border_radius=8)

        title_text = self._fit_text(step['title'], self._menu_coach_title_font, card.w - 24)
        title = self._menu_coach_title_font.render(title_text, True, (248, 232, 180))
        self.window.blit(title, (card.x + 12, card.y + 10))
        y = card.y + 10 + title_h + 10
        for line in body_lines:
            line_surf = self._menu_coach_font.render(line, True, (214, 204, 174))
            self.window.blit(line_surf, (card.x + 12, y))
            y += body_line_h

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
        if draws_skip:
            label = 'Skip tutorial'
            button_w = max(96, self._menu_coach_font.size(label)[0] + 20)
            skip_rect = pygame.Rect(card.x + 14, card.bottom - button_h - 12,
                                    button_w, button_h)
            self._draw_menu_coach_button(skip_rect, label, ('skip_tutorial', step['id']),
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

    def _handle_menu_coach_events(self, events, step=_MENU_COACH_STEP_UNSET):
        if step is _MENU_COACH_STEP_UNSET:
            step = getattr(self, '_menu_coach_step', None)
        if not step:
            return False
        action = step.get('action', 'next')
        block_types = self._menu_coach_blocking_event_types()
        passthrough_rects = self._menu_coach_passthrough_rects(step)
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
                    sound.play('ui_back' if kind == 'skip_tutorial' else 'ui_click')
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
                    return True
                if action == 'click':
                    if any(rect.collidepoint(pos) for rect in passthrough_rects):
                        if step.get('mark_on_click', True):
                            self._mark_menu_coach_seen(step.get('id'))
                        return False
                    return True
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
        if 'guide_first_duel_reward' not in seen:
            row = (self._onboarding_guide_item_rects.get('finish_tutorial')
                   or self._onboarding_guide_item_rects.get('collect_first_kingdom_production'))
            if row is None:
                row = self._onboarding_guide_rect().inflate(-40, -140)
            return {
                'id': 'guide_first_duel_reward',
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
