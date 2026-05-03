# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Modal overlay showing detailed info for a single hex / land tile."""

import math
import pygame
from config import settings
from game.core.input_state import get_pressed as _get_pressed
import logging

logger = logging.getLogger('nk.components.land_detail_box')


def _star_points(cx, cy, outer_r, inner_r, points=5):
    pts = []
    start = -math.pi / 2
    step = math.pi / points
    for i in range(points * 2):
        r = outer_r if i % 2 == 0 else inner_r
        a = start + i * step
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def _format_cooldown_text(seconds):
    """Return a compact cooldown label from seconds."""
    total = max(0, int(seconds or 0))
    hours = total // 3600
    mins = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f'{hours}h {mins}m'
    if mins > 0:
        return f'{mins}m {secs}s'
    return f'{secs}s'


# ═══════════════════════════════════════════════════════════════════
#  _LandButton — lightweight themed button (matches dialogue box style)
# ═══════════════════════════════════════════════════════════════════

class _LandButton:
    _btn_img_raw = None
    _glows = None

    @classmethod
    def _ensure_assets(cls):
        if cls._btn_img_raw is None:
            cls._btn_img_raw = pygame.image.load(
                settings.DIALOGUE_BOX_BTN_IMG_PATH).convert_alpha()
            cls._glows = {}
            glow_w = int(settings.LAND_DETAIL_BTN_W * 1.2)
            glow_h = int(settings.LAND_DETAIL_BTN_H * 2.0)
            for colour in ('yellow', 'white', 'orange'):
                raw = pygame.image.load(
                    settings.DIALOGUE_BOX_GLOW_DIR + colour + '.png').convert_alpha()
                cls._glows[colour] = pygame.transform.smoothscale(raw, (glow_w, glow_h))

    def __init__(self, window, x, y, text, disabled=False):
        _LandButton._ensure_assets()
        self.window = window
        self.text = text
        w = settings.LAND_DETAIL_BTN_W
        h = settings.LAND_DETAIL_BTN_H
        self.rect = pygame.Rect(x, y, w, h)
        self.font = settings.get_font(settings.LAND_DETAIL_BODY_FONT)
        self.font_small = settings.get_font(int(settings.LAND_DETAIL_BODY_FONT * 0.9))
        self.btn_img = pygame.transform.smoothscale(_LandButton._btn_img_raw, (w, h))
        self.btn_img_small = pygame.transform.smoothscale(
            _LandButton._btn_img_raw, (int(w * 0.95), int(h * 0.95)))
        self.hovered = False
        self.clicked = False
        self.disabled = disabled
        self.sub_text = None  # optional secondary line (e.g. cooldown)

    def collide(self):
        return self.rect.collidepoint(pygame.mouse.get_pos())

    def update(self):
        if self.disabled:
            self.hovered = False
            self.clicked = False
        else:
            self.hovered = self.collide()
            self.clicked = self.hovered and _get_pressed()[0]

    def _text_color(self):
        if self.disabled:
            return (100, 100, 100)
        if self.hovered:
            return settings.DIALOGUE_BOX_BTN_TEXT_HOVER_CLR
        return settings.DIALOGUE_BOX_BTN_TEXT_CLR

    def draw(self):
        if not self.disabled:
            if self.hovered and self.clicked:
                glow = _LandButton._glows['yellow']
            elif self.hovered:
                glow = _LandButton._glows['white']
            else:
                glow = None
            if glow:
                gx = self.rect.centerx - glow.get_width() // 2
                gy = self.rect.centery - glow.get_height() // 2
                self.window.blit(glow, (gx, gy))

        if self.clicked:
            img = self.btn_img_small
            pos = img.get_rect(center=self.rect.center).topleft
        else:
            img = self.btn_img
            pos = self.rect.topleft
        self.window.blit(img, pos)

        font = self.font_small if self.clicked else self.font
        txt = font.render(self.text, True, self._text_color())
        self.window.blit(txt, txt.get_rect(center=self.rect.center))

        if self.sub_text:
            sub = self.font_small.render(self.sub_text, True, settings.LAND_DETAIL_DIM_CLR)
            self.window.blit(sub, sub.get_rect(centerx=self.rect.centerx,
                                                top=self.rect.bottom + 2))


# ═══════════════════════════════════════════════════════════════════
#  LandDetailBox
# ═══════════════════════════════════════════════════════════════════

class LandDetailBox:
    """Modal overlay displaying detailed land info with action buttons.

    Constructor:
        tile        – HexTile from the hex map
        window      – pygame display surface
        cooldown    – player conquer cooldown seconds remaining (0 = ready)
        land_cooldown – land protection cooldown seconds remaining (0 = ready)
        on_conquer  – callback when Conquer is clicked  (tile)
        on_defence  – callback when Configure Defence is clicked  (tile)
        on_config   – callback when Configure Kingdom is clicked  (tile)
        on_close    – callback when box is dismissed
        on_message  – callback when Message Owner is clicked  (tile)
    """

    def __init__(self, window, tile, cooldown=0, land_cooldown=0,
                 on_conquer=None, on_defence=None, on_close=None,
                 on_message=None, on_config=None, conquest_outcome=None):
        self.window = window
        self.tile = tile
        self._base_cooldown = max(0, int(cooldown or 0))
        self._base_land_cooldown = max(0, int(land_cooldown or 0))
        self._on_conquer = on_conquer
        self._on_defence = on_defence
        self._on_config = on_config
        self._on_close = on_close
        self._on_message = on_message
        self._conquest_outcome = conquest_outcome
        self._created_at = pygame.time.get_ticks()
        self._last_render_cooldowns = None

        # Fonts
        self._title_font = settings.get_font(settings.LAND_DETAIL_TITLE_FONT, bold=True)
        self._body_font = settings.get_font(settings.LAND_DETAIL_BODY_FONT)
        self._small_font = settings.get_font(settings.LAND_DETAIL_SMALL_FONT)

        # Suit icon
        self._suit_icon = None
        icon_sz = int(settings.HEX_ICON_SIZE * 1.4)
        path = settings.SUIT_ICON_PATHS.get(tile.suit_bonus_suit)
        if path:
            try:
                raw = pygame.image.load(path).convert_alpha()
                self._suit_icon = pygame.transform.smoothscale(raw, (icon_sz, icon_sz))
            except Exception:
                pass
        self._icon_sz = icon_sz

        # Gold icon
        self._gold_icon = None
        try:
            raw = pygame.image.load(settings.GAME_MENU_GOLD_ICON_PATH).convert_alpha()
            self._gold_icon = pygame.transform.smoothscale(raw, (icon_sz, icon_sz))
        except Exception:
            pass

        # Broken icon (for incomplete defence)
        self._broken_icon = None
        try:
            import os
            broken_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))),
                'img', 'figures', 'state_icons', 'broken.png')
            raw = pygame.image.load(broken_path).convert_alpha()
            self._broken_icon = pygame.transform.smoothscale(raw, (icon_sz, icon_sz))
        except Exception:
            pass

        # Build layout
        self._build_layout()

    def _current_cooldowns(self):
        """Return current (player_cooldown, land_cooldown) in seconds."""
        elapsed = max(0, (pygame.time.get_ticks() - self._created_at) // 1000)
        cooldown = max(0, self._base_cooldown - elapsed)
        land_cooldown = max(0, self._base_land_cooldown - elapsed)
        return cooldown, land_cooldown

    def _line_height(self, kind):
        """Return the vertical space reserved for a rendered detail row."""
        body_h = self._body_font.get_height()
        small_h = self._small_font.get_height()

        if kind == 'title':
            return self._title_font.get_height() + 4
        if kind == 'spacer':
            return int(body_h * 0.4)
        if kind == 'gold':
            return max(self._icon_sz if self._gold_icon else 0, body_h) + 2
        if kind == 'suit':
            return max(self._icon_sz if self._suit_icon else 0, body_h) + 2
        if kind == 'defence_warning':
            return max(self._icon_sz if self._broken_icon else 0, body_h) + 2
        if kind in ('since', 'kingdom_bonus', 'land_cd', 'shield', 'conquest_hint'):
            return small_h + 2
        return body_h + 2

    def _build_layout(self):
        tile = self.tile
        cooldown, land_cooldown = self._current_cooldowns()
        self._last_render_cooldowns = (cooldown, land_cooldown)

        pad = settings.LAND_DETAIL_PAD
        w = settings.LAND_DETAIL_W

        # Pre-render text lines
        self._lines = []
        self._lines.append(('title', f'Land ({tile.col}, {tile.row})'))
        self._lines.append(('tier', tile.tier))
        self._lines.append(('spacer', ''))
        self._lines.append(('gold', f'Gold production: {tile.gold_rate:.1f} / hour'))
        if tile.suit_bonus_suit == 'Neutral' or not tile.suit_bonus_value:
            self._lines.append(('suit', 'Suit bonus: none (neutral land)'))
        else:
            self._lines.append(('suit', f'Suit bonus: {tile.suit_bonus_suit} +{tile.suit_bonus_value}'))
        if tile.owner and getattr(tile, 'kingdom_component_size', 0):
            size = getattr(tile, 'kingdom_component_size', 0) or 0
            land_word = 'land' if size == 1 else 'lands'
            self._lines.append(('kingdom', f'Kingdom: {size} connected {land_word}'))
            bonuses = getattr(tile, 'kingdom_bonuses', {}) or {}
            loot_chance = float(bonuses.get('loot_chance', 0.0) or 0.0)
            if loot_chance:
                pct = int(round(loot_chance * 100))
                self._lines.append(('kingdom_bonus', f'+{pct}% defensive loot chance'))

        if tile.is_mine and tile.defence_incomplete:
            self._lines.append(('defence_warning', 'Defence config incomplete!'))

        self._lines.append(('spacer', ''))

        if tile.owner:
            since = tile.owner.get('owned_since', '')
            if since and 'T' in since:
                since = since.split('T')[0]
            self._lines.append(('owner', f'Owner: {tile.owner_username}'))
            self._lines.append(('since', f'Since: {since}'))
        else:
            self._lines.append(('owner', 'Unclaimed (AI defended)'))

        if not tile.is_mine and self._conquest_outcome:
            if self._conquest_outcome == 'expand':
                self._lines.append(('conquest_hint', 'Conquering expands your existing kingdom'))
            else:
                self._lines.append(('conquest_hint', 'Conquering starts a new separate kingdom'))

        if not tile.is_mine and land_cooldown > 0:
            self._lines.append(
                ('land_cd',
                 f'Land protection active: {_format_cooldown_text(land_cooldown)} remaining'))
        shield_remaining = getattr(tile, 'kingdom_shield_remaining', 0) or 0
        shield_reason = getattr(tile, 'kingdom_shield_reason', None)
        core_protected = shield_reason == 'core_protection' or shield_remaining < 0
        if core_protected:
            self._lines.append(
                ('shield', 'Core Protection active: cannot be conquered'))
        elif shield_remaining > 0:
            self._lines.append(
                ('shield',
                 f'Kingdom shield active: {_format_cooldown_text(shield_remaining)} remaining'))

        button_actions = []
        if tile.is_mine:
            button_actions.append('defence')
            button_actions.append('config')
        else:
            button_actions.append('conquer')
            if tile.owner_user_id:
                button_actions.append('message')
        btn_count = len(button_actions)
        button_gap = 8
        shield_remaining = getattr(tile, 'kingdom_shield_remaining', 0) or 0
        shield_reason = getattr(tile, 'kingdom_shield_reason', None)
        core_protected = shield_reason == 'core_protection' or shield_remaining < 0
        extra_after_conquer = 0
        if (cooldown > 0 or land_cooldown > 0 or shield_remaining > 0 or core_protected) and not tile.is_mine:
            extra_after_conquer = int(self._body_font.get_height() * 0.8)

        text_h = sum(self._line_height(kind) for kind, _ in self._lines)
        button_stack_h = (
            settings.LAND_DETAIL_BTN_H * btn_count
            + button_gap * max(0, btn_count - 1)
            + extra_after_conquer
        )
        content_h = pad + text_h + pad + button_stack_h + pad

        # Position box (centred on screen)
        sw, sh = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        self._box_rect = pygame.Rect((sw - w) // 2, (sh - content_h) // 2,
                                     w, content_h)

        # X close button (top-right of box)
        _xsz = int(0.028 * sh)
        _xmargin = int(0.012 * sw)
        self._btn_close_rect = pygame.Rect(
            self._box_rect.right - _xsz - _xmargin,
            self._box_rect.y + _xmargin,
            _xsz, _xsz)

        # Create buttons
        btn_x = self._box_rect.centerx - settings.LAND_DETAIL_BTN_W // 2
        self._text_bottom_y = self._box_rect.y + pad + text_h
        btn_y = self._text_bottom_y + pad

        self._buttons = []
        if tile.is_mine:
            btn = _LandButton(self.window, btn_x, btn_y, 'Configure Defence')
            self._buttons.append(('defence', btn))
            btn_y += settings.LAND_DETAIL_BTN_H + button_gap
            self._buttons.append(('config', _LandButton(
                self.window, btn_x, btn_y, 'Configure Kingdom')))
        else:
            # Player cooldown blocks all conquer starts; land cooldown does not
            # block opening conquer setup but is shown as guidance.
            disabled = cooldown > 0 or shield_remaining > 0 or core_protected
            btn = _LandButton(self.window, btn_x, btn_y, 'Conquer', disabled=disabled)
            if disabled:
                if core_protected:
                    btn.sub_text = 'Core Protection active'
                elif shield_remaining > 0:
                    btn.sub_text = f'Shield: {_format_cooldown_text(shield_remaining)}'
                else:
                    btn.sub_text = f'Your cooldown: {_format_cooldown_text(cooldown)}'
            elif land_cooldown > 0:
                btn.sub_text = (
                    f'Land protection: {_format_cooldown_text(land_cooldown)}')
            self._buttons.append(('conquer', btn))
            btn_y += settings.LAND_DETAIL_BTN_H + button_gap + extra_after_conquer
            if tile.owner_user_id:
                self._buttons.append(('message', _LandButton(
                    self.window, btn_x, btn_y, 'Message Owner')))

    def update(self):
        if not self.tile.is_mine:
            current = self._current_cooldowns()
            if current != self._last_render_cooldowns:
                # Rebuild once per second as cooldown values change.
                self._build_layout()

        for _, btn in self._buttons:
            btn.update()

    def handle_event(self, event):
        """Process a single event. Returns action string or None.

        Actions: 'conquer', 'defence', 'config', 'message', 'close'
        """
        # Grace period to prevent accidental click-through
        if pygame.time.get_ticks() - self._created_at < 200:
            return None

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            # X close button
            if self._btn_close_rect and self._btn_close_rect.collidepoint(event.pos):
                if self._on_close:
                    self._on_close()
                return 'close'

            for action, btn in self._buttons:
                if btn.collide() and not btn.disabled:
                    if action == 'conquer' and self._on_conquer:
                        self._on_conquer(self.tile)
                    elif action == 'defence' and self._on_defence:
                        self._on_defence(self.tile)
                    elif action == 'config' and self._on_config:
                        self._on_config(self.tile)
                    elif action == 'message' and self._on_message:
                        self._on_message(self.tile)
                    return action

            # Click outside box → close
            if not self._box_rect.collidepoint(event.pos):
                if self._on_close:
                    self._on_close()
                return 'close'

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self._on_close:
                self._on_close()
            return 'close'

        return None

    def render(self):
        """Draw semi-transparent overlay + detail box."""
        sw, sh = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

        # Dim overlay
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self.window.blit(overlay, (0, 0))

        # Box background
        box_surf = pygame.Surface((self._box_rect.w, self._box_rect.h), pygame.SRCALPHA)
        r = settings.LAND_DETAIL_CORNER_R
        pygame.draw.rect(box_surf, settings.LAND_DETAIL_BG_CLR,
                         box_surf.get_rect(), border_radius=r)
        pygame.draw.rect(box_surf, settings.LAND_DETAIL_BORDER_CLR,
                         box_surf.get_rect(), settings.LAND_DETAIL_BORDER_W,
                         border_radius=r)
        self.window.blit(box_surf, self._box_rect.topleft)

        # Draw text lines
        pad = settings.LAND_DETAIL_PAD
        x = self._box_rect.x + pad
        y = self._box_rect.y + pad

        for kind, text in self._lines:
            if kind == 'title':
                surf = self._title_font.render(text, True, settings.LAND_DETAIL_TITLE_CLR)
                self.window.blit(surf, (x, y))
                y += surf.get_height() + 4
            elif kind == 'spacer':
                y += int(self._body_font.get_height() * 0.4)
            elif kind == 'tier':
                tier = int(text)
                label_surf = self._body_font.render(f'Tier {tier}  ', True, settings.LAND_DETAIL_TITLE_CLR)
                self.window.blit(label_surf, (x, y))
                body_h = self._body_font.get_height()
                outer = max(4, int(body_h * 0.38))
                inner = max(2, int(outer * 0.50))
                gap = max(2, int(outer * 0.55))
                star_cy = y + body_h // 2
                outline_w = 1
                for i in range(tier):
                    sx = x + label_surf.get_width() + outer + i * (outer * 2 + gap)
                    pygame.draw.polygon(self.window, (36, 24, 8), _star_points(sx + 1, star_cy + 1, outer, inner))
                    pygame.draw.polygon(self.window, settings.HEX_STAR_FILL, _star_points(sx, star_cy, outer, inner))
                    pygame.draw.polygon(self.window, settings.HEX_STAR_BORDER, _star_points(sx, star_cy, outer, inner), outline_w)
                y += body_h + 2
            elif kind == 'gold':
                if self._gold_icon:
                    self.window.blit(self._gold_icon, (x, y))
                    txt = self._body_font.render(text, True, settings.LAND_DETAIL_TEXT_CLR)
                    self.window.blit(txt, (x + self._icon_sz + 6, y +
                                          (self._icon_sz - txt.get_height()) // 2))
                    y += max(self._icon_sz, txt.get_height()) + 2
                else:
                    surf = self._body_font.render(text, True, settings.LAND_DETAIL_TEXT_CLR)
                    self.window.blit(surf, (x, y))
                    y += surf.get_height() + 2
            elif kind == 'suit':
                if self._suit_icon:
                    self.window.blit(self._suit_icon, (x, y))
                    txt = self._body_font.render(text, True, settings.LAND_DETAIL_TEXT_CLR)
                    self.window.blit(txt, (x + self._icon_sz + 6, y +
                                          (self._icon_sz - txt.get_height()) // 2))
                    y += max(self._icon_sz, txt.get_height()) + 2
                else:
                    surf = self._body_font.render(text, True, settings.LAND_DETAIL_TEXT_CLR)
                    self.window.blit(surf, (x, y))
                    y += surf.get_height() + 2
            elif kind == 'owner':
                clr = settings.LAND_DETAIL_TEXT_CLR
                if self.tile.is_mine:
                    clr = settings.LAND_DETAIL_TITLE_CLR
                surf = self._body_font.render(text, True, clr)
                self.window.blit(surf, (x, y))
                y += surf.get_height() + 2
            elif kind == 'since':
                surf = self._small_font.render(text, True, settings.LAND_DETAIL_DIM_CLR)
                self.window.blit(surf, (x, y))
                y += surf.get_height() + 2
            elif kind in ('kingdom', 'kingdom_bonus'):
                font = self._body_font if kind == 'kingdom' else self._small_font
                clr = settings.LAND_DETAIL_TITLE_CLR if kind == 'kingdom' else settings.LAND_DETAIL_DIM_CLR
                surf = font.render(text, True, clr)
                self.window.blit(surf, (x, y))
                y += surf.get_height() + 2
            elif kind in ('land_cd', 'shield'):
                surf = self._small_font.render(text, True, settings.LAND_DETAIL_TITLE_CLR)
                self.window.blit(surf, (x, y))
                y += surf.get_height() + 2
            elif kind == 'conquest_hint':
                clr = ((110, 195, 110) if self._conquest_outcome == 'expand'
                       else (170, 140, 90))
                surf = self._small_font.render(text, True, clr)
                self.window.blit(surf, (x, y))
                y += surf.get_height() + 2
            elif kind == 'defence_warning':
                if self._broken_icon:
                    self.window.blit(self._broken_icon, (x, y))
                    txt = self._body_font.render(text, True, (220, 60, 60))
                    self.window.blit(txt, (x + self._icon_sz + 6, y +
                                          (self._icon_sz - txt.get_height()) // 2))
                    y += max(self._icon_sz, txt.get_height()) + 2
                else:
                    surf = self._body_font.render(text, True, (220, 60, 60))
                    self.window.blit(surf, (x, y))
                    y += surf.get_height() + 2

        # Draw X close button
        r_close = self._btn_close_rect
        mouse_pos = pygame.mouse.get_pos()
        hovered = r_close.collidepoint(mouse_pos)
        bg_clr = (80, 50, 25, 220) if hovered else (55, 35, 18, 200)
        border_clr = (180, 160, 120) if hovered else (120, 100, 70)
        txt_clr = (255, 240, 200) if hovered else (200, 180, 140)
        x_surf = pygame.Surface((r_close.w, r_close.h), pygame.SRCALPHA)
        pygame.draw.rect(x_surf, bg_clr, x_surf.get_rect(), border_radius=4)
        pygame.draw.rect(x_surf, border_clr, x_surf.get_rect(), 1, border_radius=4)
        self.window.blit(x_surf, r_close.topleft)
        _xfont = settings.get_font(int(settings.FONT_SIZE * 0.85), bold=True)
        xt = _xfont.render('\u00d7', True, txt_clr)
        self.window.blit(xt, xt.get_rect(center=r_close.center))

        # Draw buttons
        for _, btn in self._buttons:
            btn.draw()
