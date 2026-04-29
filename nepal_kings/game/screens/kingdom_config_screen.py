# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Persistent connected-kingdom configuration screen."""

import os
import pygame
from pygame.locals import *

from config import settings
from game.components.floating_text import FloatingText, FloatingTextLayer
from game.screens._menu_base import MenuScreenMixin
from game.screens.screen import Screen
from utils import http_compat as requests


_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

_BOX_PAD = int(0.020 * _SH)
_BOX_X = int(0.04 * _SW)
_BOX_Y = int(0.10 * _SH)
_BOX_W = int(0.87 * _SW)
_BOX_BOTTOM = int(0.92 * _SH)
_BOX_H = _BOX_BOTTOM - _BOX_Y

HANDLED_KINGDOM_CONFIG_ACTIONS = frozenset({
    'back',
    'kingdom_prev',
    'kingdom_next',
    'select_hours',
    'buy_shield',
    'buy_cosmetic',
    'equip_cosmetic',
    'rename_start',
    'rename_confirm',
    'rename_cancel',
    'upgrade_skill',
    'collect_kingdom_gold',
})


def _draw_config_frame(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


class KingdomConfigScreen(MenuScreenMixin, Screen):
    """Configure cosmetics, shields, and skill points for one kingdom."""

    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()
        self._title_font = settings.get_font(settings.FS_SUBTITLE, bold=True)
        self._heading_font = settings.get_font(settings.FS_BODY, bold=True)
        self._body_font = settings.get_font(settings.FS_BODY)
        self._button_font = settings.get_font(settings.FS_BUTTON, bold=True)
        self._small_font = settings.get_font(settings.FS_SMALL)
        self._tiny_font = settings.get_font(settings.FS_TINY)
        self._data = None
        self._kingdom = None
        self._catalog = {}
        self._gold = 0
        self._selected_hours = 6
        self._quote = None
        self._message = ''
        self._loading = False
        self._buttons = []
        self._box_rect = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        self._btn_close_rect = None
        self._cosmetic_scroll = {'flag': 0, 'border': 0, 'surface': 0}
        self._cosmetic_scroll_areas = {}
        self._rename_dialog = None
        self._rename_input_rect = None
        self._rename_confirm_rect = None
        self._rename_cancel_rect = None
        self._icons = {}
        self._shield_icon = self._load_icon(settings.KINGDOM_SHIELD_ICON_PATH)
        for key, path in settings.KINGDOM_SKILL_ICON_PATHS.items():
            self._icons[key] = self._load_icon(path)
        # Edit (pencil) icon used as the rename trigger next to the kingdom
        # name title — same affordance as the defence/conquer config screens.
        self._edit_icon_size = max(18, int(0.030 * _SH))
        edit_raw = self._load_icon('img/dialogue_box/icons/edit.png')
        if edit_raw is not None:
            try:
                self._edit_icon = pygame.transform.smoothscale(
                    edit_raw, (self._edit_icon_size, self._edit_icon_size))
            except Exception:
                self._edit_icon = edit_raw
        else:
            self._edit_icon = None
        self._rename_icon_rect = None
        # Visual layer for `+amount` floaters spawned by Collect.
        self._floating_text = FloatingTextLayer()
        self._last_render_ms = pygame.time.get_ticks()
        self._last_seen_level = None

    def _load_icon(self, rel_path):
        try:
            path = rel_path
            if not os.path.isabs(path):
                path = os.path.join(settings.RESOURCE_BASE, rel_path)
            return pygame.image.load(path).convert_alpha()
        except Exception:
            return None

    def on_enter(self):
        self._fetch_config()

    def _set_msg(self, msg):
        self._message = msg or ''
        if hasattr(self.state, 'set_msg'):
            self.state.set_msg(self._message)

    def _sync_gold(self, gold_value):
        try:
            gold_int = int(gold_value or 0)
        except (TypeError, ValueError):
            gold_int = 0
        self._gold = gold_int
        if getattr(self.state, 'user_dict', None) is not None:
            self.state.user_dict['gold'] = gold_int

    def _fetch_config(self):
        self._loading = True
        land_id = getattr(self.state, 'kingdom_config_land_id', None)
        try:
            url = f'{settings.SERVER_URL}/kingdom/config'
            if land_id:
                url += f'?land_id={int(land_id)}'
            resp = requests.get(url, timeout=12)
            data = resp.json()
            if not data.get('success'):
                self._set_msg(data.get('message', 'Could not load kingdom config'))
                return
            self._data = data
            self._catalog = data.get('catalog') or {}
            self._sync_gold(data.get('gold', 0))
            selected_id = getattr(self.state, 'kingdom_config_id', None) or data.get('selected_kingdom_id')
            kingdoms = data.get('kingdoms') or []
            self._kingdom = None
            for row in kingdoms:
                if row.get('id') == selected_id:
                    self._kingdom = row
                    break
            if self._kingdom is None and kingdoms:
                self._kingdom = kingdoms[0]
            if self._kingdom is not None:
                self.state.kingdom_config_id = self._kingdom.get('id')
            hours = data.get('shield_options_hours') or [6, 12, 24]
            if self._selected_hours not in hours:
                self._selected_hours = hours[0]
            self._quote = None
            if self._kingdom:
                self._fetch_quote(silent=True)
        except Exception as exc:
            self._set_msg(f'Kingdom config unavailable: {exc}')
        finally:
            self._loading = False

    def _fetch_quote(self, silent=False):
        if not self._kingdom:
            return
        try:
            kid = self._kingdom['id']
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/config/{kid}/shield/quote',
                json={'hours': self._selected_hours}, timeout=10)
            data = resp.json()
            if data.get('success'):
                self._quote = data.get('quote') or {}
            elif not silent:
                self._set_msg(data.get('message', 'Could not quote shield'))
        except Exception as exc:
            if not silent:
                self._set_msg(f'Could not quote shield: {exc}')

    def _post_action(self, path, payload=None):
        if not self._kingdom:
            return None
        try:
            kid = self._kingdom['id']
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/config/{kid}/{path}',
                json=payload or {}, timeout=12)
            data = resp.json()
            if data.get('success'):
                if data.get('kingdom'):
                    self._kingdom = data['kingdom']
                if 'gold' in data:
                    self._sync_gold(data['gold'])
                return data
            self._set_msg(data.get('message', 'Action failed'))
        except Exception as exc:
            self._set_msg(f'Action failed: {exc}')
        return None

    def _buy_cosmetic(self, key):
        data = self._post_action('cosmetics/purchase', {'cosmetic_key': key})
        if data:
            self._set_msg('Cosmetic unlocked')
            self._fetch_config()

    def _equip_cosmetic(self, key):
        data = self._post_action('cosmetics/equip', {'cosmetic_key': key})
        if data:
            self._set_msg('Kingdom style updated')
            self._fetch_config()

    def _upgrade_skill(self, key):
        data = self._post_action('skills/upgrade', {'skill_key': key})
        if data:
            self._set_msg('Skill upgraded')
            self._fetch_quote(silent=True)

    def _collect_kingdom_gold(self):
        if not self._kingdom:
            return
        kid = self._kingdom['id']
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/{kid}/collect_gold',
                json={}, timeout=12,
            )
            data = resp.json()
        except Exception as exc:
            self._set_msg(f'Collect failed: {exc}')
            return
        if not data.get('success'):
            self._set_msg(data.get('message', 'Collect failed'))
            return
        collected = int(data.get('collected', 0) or 0)
        if collected > 0 and hasattr(self, '_suppress_next_gold_floater'):
            self._suppress_next_gold_floater()
        if 'gold' in data:
            self._sync_gold(data['gold'])
        elif 'total_gold' in data:
            self._sync_gold(data['total_gold'])
        if self._kingdom is not None:
            if 'pending_gold' in data:
                self._kingdom['pending_gold'] = float(data.get('pending_gold') or 0.0)
            if 'vault_cap' in data:
                self._kingdom['vault_cap'] = int(data.get('vault_cap') or 0)
        # Refresh shield quote so price reflects current gold / kingdom state.
        self._fetch_quote(silent=True)
        if collected > 0 and self._collect_btn_rect is not None:
            self._spawn_collect_floater(collected, self._collect_btn_rect.center)
            self._set_msg(f'Collected +{collected}g')

    def _spawn_collect_floater(self, amount, pos, *, delay_ms=0):
        font = settings.get_font(settings.COLLECT_FLOAT_FONT_SIZE, bold=True)
        self._floating_text.add(FloatingText(
            f'+{int(amount)}g', pos,
            color=settings.COLLECT_FLOAT_GOLD_CLR,
            duration_ms=settings.COLLECT_FLOAT_DURATION_MS,
            rise_px=settings.COLLECT_FLOAT_RISE_PX,
            font=font,
            delay_ms=delay_ms,
        ))

    def _buy_shield(self):
        data = self._post_action('shield/purchase', {'hours': self._selected_hours})
        if data:
            self._set_msg('Kingdom shield activated')
            self._fetch_quote(silent=True)

    def _kingdoms(self):
        kingdoms = (self._data or {}).get('kingdoms') or []
        if kingdoms:
            return kingdoms
        return [self._kingdom] if self._kingdom else []

    def _selected_kingdom_index(self):
        kingdoms = self._kingdoms()
        if not kingdoms or not self._kingdom:
            return 0
        selected_id = self._kingdom.get('id')
        for idx, row in enumerate(kingdoms):
            if row.get('id') == selected_id:
                return idx
        return 0

    def _select_kingdom_at(self, index):
        kingdoms = self._kingdoms()
        if not kingdoms:
            return
        idx = index % len(kingdoms)
        self._kingdom = kingdoms[idx]
        self.state.kingdom_config_id = self._kingdom.get('id')
        self._quote = None
        self._fetch_quote(silent=True)

    def _switch_kingdom(self, delta):
        kingdoms = self._kingdoms()
        if len(kingdoms) <= 1:
            return
        self._select_kingdom_at(self._selected_kingdom_index() + delta)

    def handle_events(self, events):
        super().handle_events(events)
        if self.dialogue_box:
            return
        for event in events:
            if self._rename_dialog:
                self._handle_rename_event(event)
                continue
            if self._handle_icon_events(event):
                continue
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                self.state.screen = 'kingdom'
                return
            if event.type == MOUSEWHEEL:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                for cosmetic_type, area in self._cosmetic_scroll_areas.items():
                    if area.collidepoint(pos):
                        self._scroll_cosmetic_section(cosmetic_type, getattr(event, 'y', 0))
                        return
                continue
            if event.type != MOUSEBUTTONUP or event.button != 1:
                continue
            if not self._box_rect.collidepoint(event.pos):
                self.state.screen = 'kingdom'
                return
            for action, value, rect in list(self._buttons):
                if not rect.collidepoint(event.pos):
                    continue
                if action == 'back':
                    self.state.screen = 'kingdom'
                elif action == 'kingdom_prev':
                    self._switch_kingdom(-1)
                elif action == 'kingdom_next':
                    self._switch_kingdom(1)
                elif action == 'select_hours':
                    self._selected_hours = value
                    self._fetch_quote()
                elif action == 'buy_shield':
                    self._buy_shield()
                elif action == 'buy_cosmetic':
                    self._buy_cosmetic(value)
                elif action == 'equip_cosmetic':
                    self._equip_cosmetic(value)
                elif action == 'rename_start':
                    self._start_rename()
                elif action == 'upgrade_skill':
                    self._upgrade_skill(value)
                elif action == 'collect_kingdom_gold':
                    self._collect_kingdom_gold()
                return

    def _handle_rename_event(self, event):
        if not self._rename_dialog:
            return False
        if event.type == KEYDOWN:
            if event.key == K_ESCAPE:
                self._close_rename_dialog()
            elif event.key == K_BACKSPACE:
                self._rename_dialog['text'] = self._rename_dialog.get('text', '')[:-1]
                self._rename_dialog['error'] = ''
            elif event.key == K_RETURN:
                self._submit_rename()
            return True
        if event.type == pygame.TEXTINPUT:
            text = self._rename_dialog.get('text', '')
            if len(text) < 40:
                self._rename_dialog['text'] = (text + event.text)[:40]
                self._rename_dialog['error'] = ''
            return True
        if event.type == MOUSEBUTTONUP and event.button == 1:
            if self._rename_cancel_rect and self._rename_cancel_rect.collidepoint(event.pos):
                self._close_rename_dialog()
                return True
            if self._rename_confirm_rect and self._rename_confirm_rect.collidepoint(event.pos):
                self._submit_rename()
                return True
            return True
        return True

    def _close_rename_dialog(self):
        self._rename_dialog = None
        try:
            pygame.key.stop_text_input()
        except Exception:
            pass

    def _start_rename(self):
        if not self._kingdom:
            return
        try:
            pygame.key.start_text_input()
        except Exception:
            pass
        self._rename_dialog = {
            'text': self._kingdom.get('name') or f"Kingdom #{self._kingdom.get('id', '?')}",
            'error': '',
        }

    def _submit_rename(self):
        if not self._rename_dialog:
            return False
        name = (self._rename_dialog.get('text') or '').strip()
        if not name:
            self._rename_dialog['error'] = 'Enter a kingdom name.'
            return False
        price = int((self._data or {}).get('rename_price_gold', 0) or 0)
        if self._gold < price:
            self._rename_dialog['error'] = 'Not enough gold to rename.'
            return False
        data = self._post_action('rename', {'name': name})
        if data:
            self._close_rename_dialog()
            self._set_msg('Kingdom renamed')
            self._fetch_config()
            return True
        self._rename_dialog['error'] = self._message or 'Rename failed.'
        return False

    def _scroll_cosmetic_section(self, cosmetic_type, wheel_y):
        items = self._catalog_items(cosmetic_type)
        area = self._cosmetic_scroll_areas.get(cosmetic_type)
        if not area:
            return
        item_h = max(30, min(38, int(0.038 * settings.SCREEN_HEIGHT)))
        max_scroll = max(0, len(items) * item_h - area.h)
        current = int(self._cosmetic_scroll.get(cosmetic_type, 0) or 0)
        current -= int(wheel_y or 0) * item_h
        self._cosmetic_scroll[cosmetic_type] = max(0, min(max_scroll, current))

    def update(self, events=None):
        super().update()
        self._update_icon_buttons()

    def _draw_panel(self, rect, title=None):
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.KINGDOM_CONFIG_PANEL_BG, surf.get_rect(),
                         border_radius=10)
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, settings.KINGDOM_CONFIG_PANEL_BORDER, rect, 2,
                         border_radius=10)
        if title:
            surf = self._heading_font.render(title, True, settings.LAND_DETAIL_TITLE_CLR)
            self.window.blit(surf, (rect.x + 14, rect.y + 10))

    def _draw_button(self, rect, text, action, value=None, disabled=False):
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse) and not disabled
        bg = (82, 66, 44) if hovered else (58, 48, 38)
        if disabled:
            bg = (42, 40, 42)
        pygame.draw.rect(self.window, bg, rect, border_radius=7)
        pygame.draw.rect(self.window, (204, 174, 104), rect, 1, border_radius=7)
        clr = settings.KINGDOM_CONFIG_DIM_CLR if disabled else settings.KINGDOM_CONFIG_TEXT_CLR
        surf = self._small_font.render(text, True, clr)
        self.window.blit(surf, surf.get_rect(center=rect.center))
        if not disabled:
            self._buttons.append((action, value, rect))

    def _fit_text(self, text, font, max_width):
        text = str(text)
        if font.size(text)[0] <= max_width:
            return text
        ellipsis = '...'
        clipped = text
        while clipped and font.size(clipped + ellipsis)[0] > max_width:
            clipped = clipped[:-1]
        return (clipped + ellipsis) if clipped else ellipsis

    def _draw_status_pill(self, rect, text, color=None):
        pygame.draw.rect(self.window, (35, 29, 34, 200), rect, border_radius=8)
        pygame.draw.rect(self.window, (132, 112, 78), rect, 1, border_radius=8)
        label = self._fit_text(text, self._small_font, rect.w - 14)
        surf = self._small_font.render(label, True, color or settings.KINGDOM_CONFIG_TEXT_CLR)
        self.window.blit(surf, surf.get_rect(center=rect.center))

    def _draw_rename_icon(self, rect, *, enabled):
        """Draw the pencil rename trigger and register the click hitbox.

        Mirrors the edit-icon affordance used on the defence/conquer config
        screens: a small icon (with a hover glow) instead of a large text
        button.
        """
        if not rect:
            return
        mouse_pos = pygame.mouse.get_pos()
        hovered = enabled and rect.collidepoint(mouse_pos)
        if self._edit_icon is not None:
            if hovered:
                glow = pygame.Surface((rect.w + 4, rect.h + 4), pygame.SRCALPHA)
                glow.fill((255, 240, 180, 55))
                self.window.blit(glow, (rect.x - 2, rect.y - 2))
            icon = self._edit_icon
            if not enabled:
                icon = icon.copy()
                icon.fill((0, 0, 0, 110), special_flags=pygame.BLEND_RGBA_MULT)
            self.window.blit(icon, rect.topleft)
        else:
            # Fallback if the asset failed to load: draw a simple outlined box.
            clr = (220, 200, 150) if enabled else settings.KINGDOM_CONFIG_DIM_CLR
            pygame.draw.rect(self.window, clr, rect, 1, border_radius=4)
        if enabled:
            self._buttons.append(('rename_start', None, rect))
            self._rename_icon_rect = rect

    def _draw_close_x_button(self):
        r = self._btn_close_rect
        if not r:
            return
        mouse_pos = pygame.mouse.get_pos()
        hovered = r.collidepoint(mouse_pos)
        bg_clr = (80, 50, 25, 220) if hovered else (55, 35, 18, 200)
        border_clr = (180, 160, 120) if hovered else (120, 100, 70)
        txt_clr = (255, 240, 200) if hovered else (200, 180, 140)
        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg_clr, surf.get_rect(), border_radius=4)
        pygame.draw.rect(surf, border_clr, surf.get_rect(), 1, border_radius=4)
        self.window.blit(surf, r.topleft)
        x_font = settings.get_font(int(settings.FONT_SIZE * 0.85), bold=True)
        txt = x_font.render('\u00d7', True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=r.center))
        self._buttons.append(('back', None, r))

    def _draw_pager_arrow(self, rect, action, *, enabled, glyph):
        """Small chevron button used by the unified header pill."""
        if not rect:
            return
        mouse_pos = pygame.mouse.get_pos()
        hovered = enabled and rect.collidepoint(mouse_pos)
        bg = (60, 50, 38, 220) if hovered else (35, 29, 34, 200)
        border = (190, 168, 116) if hovered else (120, 100, 70)
        clr = settings.KINGDOM_CONFIG_TEXT_CLR if enabled else settings.KINGDOM_CONFIG_DIM_CLR
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=6)
        pygame.draw.rect(surf, border, surf.get_rect(), 1, border_radius=6)
        self.window.blit(surf, rect.topleft)
        font = settings.get_font(int(settings.FONT_SIZE * 0.95), bold=True)
        txt = font.render(glyph, True, clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))
        if enabled:
            self._buttons.append((action, None, rect))

    def _draw_header_pill(self, rect):
        """Unified header: pager + name + edit + level/XP, all in one pill.

        Left zone (60%): prev arrow, kingdom name + edit pencil, next arrow,
        with a small ``N lands \u00b7 i/k`` subtitle line under the name.
        Right zone (40%): kingdom level header + XP progress bar.
        """
        if not rect:
            return
        # Pill background.
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (35, 29, 34, 200), bg.get_rect(), border_radius=10)
        self.window.blit(bg, rect.topleft)
        pygame.draw.rect(self.window, (132, 112, 78), rect, 1, border_radius=10)

        if not self._kingdom:
            return

        kingdoms = self._kingdoms()
        count = len(kingdoms)
        idx = self._selected_kingdom_index()
        name = self._kingdom.get('name') or f"Kingdom #{self._kingdom.get('id', '?')}"
        lands_count = int(self._kingdom.get('lands_count', 0) or len(self._kingdom.get('land_ids') or []))
        meta = f'{lands_count} land{"s" if lands_count != 1 else ""}'
        if count > 1:
            meta += f'  \u00b7  {idx + 1}/{count}'

        # Vertical divider between left (name + pager) and right (level/XP).
        split_x = rect.x + int(rect.w * 0.58)
        pygame.draw.line(self.window, (90, 78, 60),
                         (split_x, rect.y + 8), (split_x, rect.bottom - 8), 1)

        # ── Left zone: pager + name + edit + subtitle ───────────────
        left_rect = pygame.Rect(rect.x, rect.y, split_x - rect.x, rect.h)
        arrow_w = max(28, int(rect.h * 0.55))
        arrow_h = max(26, int(rect.h * 0.50))
        arrow_y = rect.y + (rect.h - arrow_h) // 2
        prev_rect = pygame.Rect(left_rect.x + 8, arrow_y, arrow_w, arrow_h)
        next_rect = pygame.Rect(left_rect.right - arrow_w - 8, arrow_y, arrow_w, arrow_h)
        # Always reserve the arrow area so the name region stays steady when
        # the user only owns one kingdom; just don't make it interactive.
        self._draw_pager_arrow(prev_rect, 'kingdom_prev', enabled=count > 1, glyph='\u2039')
        self._draw_pager_arrow(next_rect, 'kingdom_next', enabled=count > 1, glyph='\u203a')

        name_zone = pygame.Rect(prev_rect.right + 10, rect.y,
                                next_rect.x - prev_rect.right - 20, rect.h)
        # Title row: name (left-aligned in zone) + edit pencil immediately right.
        edit_sz = self._edit_icon_size
        edit_pad = 8
        # Reserve room for the edit icon when measuring/clipping the name.
        max_name_w = max(40, name_zone.w - edit_sz - edit_pad)
        title_text = self._fit_text(name, self._title_font, max_name_w)
        title_surf = self._title_font.render(title_text, True,
                                             settings.LAND_DETAIL_TITLE_CLR)
        title_y = rect.y + 6
        self.window.blit(title_surf, (name_zone.x, title_y))

        # Edit pencil (rename trigger), vertically aligned with the name.
        rename_price = int((self._data or {}).get('rename_price_gold', 0) or 0)
        can_rename = self._gold >= rename_price
        edit_x = name_zone.x + title_surf.get_width() + edit_pad
        edit_y = title_y + (title_surf.get_height() - edit_sz) // 2
        edit_rect = pygame.Rect(edit_x, edit_y, edit_sz, edit_sz)
        self._draw_rename_icon(edit_rect, enabled=can_rename)

        # Subtitle metadata.
        meta_surf = self._tiny_font.render(meta, True,
                                           settings.KINGDOM_CONFIG_DIM_CLR)
        meta_y = title_y + title_surf.get_height() + 2
        # Keep subtitle within the pill.
        meta_y = min(meta_y, rect.bottom - meta_surf.get_height() - 6)
        self.window.blit(meta_surf, (name_zone.x, meta_y))

        # ── Right zone: level + XP bar ──────────────────────────────
        right_rect = pygame.Rect(split_x + 1, rect.y, rect.right - split_x - 1, rect.h)
        right_pad_x = 14
        right_pad_y = 8
        level = int(self._kingdom.get('level', 1) or 1)
        max_level = int(self._kingdom.get('level_max', 50) or 50)
        xp_into = int(self._kingdom.get('xp_into_level', 0) or 0)
        xp_for_next = int(self._kingdom.get('xp_for_next_level', 0) or 0)
        total_xp = int(self._kingdom.get('experience', 0) or 0)

        # Spawn a level-up floater the first time we see ``level`` advance,
        # mirroring the prior skills-panel behavior so users keep that feedback.
        if self._last_seen_level is None:
            self._last_seen_level = level
        elif level > self._last_seen_level:
            font = settings.get_font(settings.COLLECT_FLOAT_FONT_SIZE, bold=True)
            self._floating_text.add(FloatingText(
                'Level Up!', (right_rect.x + 80, right_rect.y + 24),
                color=settings.COLLECT_FLOAT_LEVEL_CLR,
                duration_ms=settings.COLLECT_FLOAT_DURATION_MS * 2,
                rise_px=settings.COLLECT_FLOAT_RISE_PX,
                font=font,
            ))
            self._last_seen_level = level

        header_label = (f'Kingdom Level {level}/{max_level}'
                        if level < max_level else f'Kingdom Level {level} (MAX)')
        level_font = settings.get_font(settings.KINGDOM_LEVEL_HEADER_FONT_SIZE, bold=True)
        level_surf = level_font.render(header_label, True,
                                       settings.KINGDOM_LEVEL_HEADER_CLR)
        self.window.blit(level_surf, (right_rect.x + right_pad_x,
                                      right_rect.y + right_pad_y))
        # XP bar.
        bar_y = right_rect.y + right_pad_y + level_surf.get_height() + 4
        bar_rect = pygame.Rect(right_rect.x + right_pad_x, bar_y,
                               right_rect.w - right_pad_x * 2,
                               settings.KINGDOM_XP_BAR_H)
        pygame.draw.rect(self.window, settings.KINGDOM_XP_BAR_TRACK_CLR,
                         bar_rect, border_radius=4)
        if level < max_level and xp_for_next > 0:
            ratio = max(0.0, min(1.0, xp_into / float(xp_for_next)))
            fill_w = int(bar_rect.w * ratio)
            if fill_w > 0:
                pygame.draw.rect(self.window, settings.KINGDOM_XP_BAR_FILL_CLR,
                                 pygame.Rect(bar_rect.x, bar_rect.y, fill_w, bar_rect.h),
                                 border_radius=4)
            xp_label = f'{xp_into} / {xp_for_next} XP  (total {total_xp})'
        else:
            pygame.draw.rect(self.window, settings.KINGDOM_XP_BAR_FILL_CLR,
                             bar_rect, border_radius=4)
            xp_label = f'MAX  (total {total_xp} XP)'
        pygame.draw.rect(self.window, settings.KINGDOM_XP_BAR_BORDER_CLR,
                         bar_rect, 1, border_radius=4)
        xp_surf = self._tiny_font.render(xp_label, True,
                                         settings.KINGDOM_XP_BAR_TEXT_CLR)
        # Keep xp label inside the pill bottom.
        xp_y = min(bar_rect.bottom + 2,
                   right_rect.bottom - xp_surf.get_height() - 4)
        self.window.blit(xp_surf, (bar_rect.x, xp_y))

    def _catalog_items(self, cosmetic_type):
        items = []
        for key, item in sorted(self._catalog.items()):
            if item.get('type') == cosmetic_type:
                row = dict(item)
                row['key'] = key
                items.append(row)
        return items

    @staticmethod
    def _skill_increment(skill, level):
        """Return the skill effect value for ``level`` (1-indexed).

        Server payloads use ``effect_values`` (a list); legacy payloads with
        ``increments`` (dict keyed by level) are accepted for compatibility
        with older tests.
        """
        if level <= 0:
            return 0
        effect_values = skill.get('effect_values')
        if effect_values:
            idx = max(0, min(int(level) - 1, len(effect_values) - 1))
            return effect_values[idx] or 0
        increments = skill.get('increments') or {}
        value = increments.get(level, increments.get(str(level), None))
        if value is not None:
            return value or 0
        current_level = int(skill.get('level', 0) or 0)
        if level == current_level:
            return skill.get('current_bonus', 0) or 0
        if level == current_level + 1:
            return skill.get('next_bonus', 0) or 0
        return 0

    def _skill_effect_text(self, key, skill):
        level = int(skill.get('level', 0) or 0)
        max_level = int(skill.get('max_level', 5) or 5)
        current = self._skill_increment(skill, level)
        next_value = self._skill_increment(skill, min(max_level, level + 1))

        if key == 'gold_production':
            current_text = f'+{int(round(float(current) * 100))}% gold'
            next_text = f'+{int(round(float(next_value) * 100))}% gold'
        elif key == 'shield_cost_reduction':
            current_text = f'-{int(round(float(current) * 100))}% shield cost'
            next_text = f'-{int(round(float(next_value) * 100))}% shield cost'
        elif key == 'gold_vault':
            default_cap = int((self._data or {}).get('vault_default_cap', 50) or 50)
            current_cap = int(current) if level > 0 else default_cap
            next_cap = int(next_value) if level < max_level else current_cap
            current_text = f'cap {current_cap}'
            next_text = f'cap {next_cap}'
        elif key == 'core_protection':
            current_text = f'protect {int(current)} land' + ('s' if int(current) != 1 else '')
            next_text = f'protect {int(next_value)} land' + ('s' if int(next_value) != 1 else '')
        else:
            current_text = f'+{current}'
            next_text = f'+{next_value}'

        if level >= max_level:
            return f'Current: {current_text}  •  Max level'
        return f'Current: {current_text}  •  Next: {next_text}'

    def _style_preview(self, rect, style):
        tier_fill = settings.HEX_TIER_FILL.get(2, (100, 110, 90))
        pygame.draw.rect(self.window, (18, 16, 18), rect, border_radius=8)
        cx, cy = rect.center
        radius = min(rect.w, rect.h) // 3
        points = []
        for idx in range(6):
            angle = 3.14159 / 6 + idx * 3.14159 / 3
            points.append((cx + int(radius * pygame.math.Vector2(1, 0).rotate_rad(angle).x),
                           cy + int(radius * pygame.math.Vector2(1, 0).rotate_rad(angle).y)))
        pygame.draw.polygon(self.window, tier_fill, points)
        surface = settings.HEX_SURFACE_SKINS.get(style.get('surface_key'), {})
        overlay = surface.get('overlay')
        if overlay:
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.polygon(surf, overlay, [(x - rect.x, y - rect.y) for x, y in points])
            self.window.blit(surf, rect.topleft)
        border = settings.HEX_BORDER_SKINS.get(style.get('border_key'),
                                               settings.HEX_BORDER_SKINS['border_simple_gold'])
        pygame.draw.polygon(self.window, border.get('outer', (90, 70, 40)), points, 5)
        pygame.draw.polygon(self.window, border.get('main', (250, 221, 0)), points, 3)
        flag = settings.HEX_FLAG_STYLES.get(style.get('flag_key'),
                                            settings.HEX_FLAG_STYLES['flag_plain'])
        pole_x = rect.right - 28
        pole_y = rect.y + 24
        pygame.draw.line(self.window, flag.get('pole', (150, 120, 72)),
                         (pole_x, pole_y), (pole_x, pole_y + 40), 3)
        pygame.draw.rect(self.window, flag.get('fill', (230, 214, 158)),
                         (pole_x, pole_y, 30, 18), border_radius=2)
        pygame.draw.rect(self.window, flag.get('accent', (120, 90, 50)),
                         (pole_x, pole_y, 30, 18), 1, border_radius=2)

    def _draw_cosmetic_chip(self, rect, cosmetic_type, key):
        pygame.draw.rect(self.window, (20, 18, 22), rect, border_radius=5)
        pygame.draw.rect(self.window, (84, 74, 58), rect, 1, border_radius=5)
        if cosmetic_type == 'flag':
            flag = settings.HEX_FLAG_STYLES.get(key, settings.HEX_FLAG_STYLES['flag_plain'])
            pole_x = rect.x + 7
            pole_y = rect.y + 5
            pygame.draw.line(self.window, flag.get('pole', (150, 120, 72)),
                             (pole_x, pole_y), (pole_x, rect.bottom - 5), 2)
            flag_rect = pygame.Rect(pole_x, pole_y, rect.w - 11, max(10, rect.h // 2))
            pygame.draw.rect(self.window, flag.get('fill', (230, 214, 158)), flag_rect,
                             border_radius=2)
            pygame.draw.rect(self.window, flag.get('accent', (120, 90, 50)), flag_rect, 1,
                             border_radius=2)
            return

        cx, cy = rect.center
        radius = min(rect.w, rect.h) // 3
        points = []
        for idx in range(6):
            angle = 3.14159 / 6 + idx * 3.14159 / 3
            points.append((cx + int(radius * pygame.math.Vector2(1, 0).rotate_rad(angle).x),
                           cy + int(radius * pygame.math.Vector2(1, 0).rotate_rad(angle).y)))
        fill = settings.HEX_TIER_FILL.get(2, (100, 110, 90))
        if cosmetic_type == 'surface':
            surface = settings.HEX_SURFACE_SKINS.get(key, {})
            fill = surface.get('overlay') or fill
            if isinstance(fill, tuple) and len(fill) == 4:
                fill = fill[:3]
            pygame.draw.polygon(self.window, fill, points)
            pygame.draw.polygon(self.window, (75, 62, 42), points, 2)
            return

        pygame.draw.polygon(self.window, fill, points)
        border = settings.HEX_BORDER_SKINS.get(key,
                                               settings.HEX_BORDER_SKINS['border_simple_gold'])
        pygame.draw.polygon(self.window, border.get('outer', (90, 70, 40)), points, 4)
        pygame.draw.polygon(self.window, border.get('main', (250, 221, 0)), points, 2)

    def _draw_cosmetic_section(self, rect, cosmetic_type, title):
        self._draw_panel(rect, title)
        if not self._kingdom:
            return
        style = self._kingdom.get('style') or {}
        current_key = style.get(f'{cosmetic_type}_key')
        unlocked = set(self._kingdom.get('unlocked_cosmetics') or [])
        preview = pygame.Rect(rect.x + 14, rect.y + 44, 92, rect.h - 58)
        preview_style = dict(style)
        self._style_preview(preview, preview_style)
        x = preview.right + 14
        y = rect.y + 42
        items = self._catalog_items(cosmetic_type)
        item_h = max(30, min(38, int(0.038 * settings.SCREEN_HEIGHT)))
        list_rect = pygame.Rect(x, y, rect.right - x - 18, max(28, rect.bottom - y - 12))
        self._cosmetic_scroll_areas[cosmetic_type] = list_rect
        max_scroll = max(0, len(items) * item_h - list_rect.h)
        scroll = max(0, min(max_scroll, int(self._cosmetic_scroll.get(cosmetic_type, 0) or 0)))
        self._cosmetic_scroll[cosmetic_type] = scroll
        old_clip = self.window.get_clip()
        self.window.set_clip(list_rect.clip(old_clip))
        try:
            for idx, item in enumerate(items):
                row_y = list_rect.y + idx * item_h - scroll
                row = pygame.Rect(list_rect.x, row_y, list_rect.w - (8 if max_scroll > 0 else 0), item_h - 5)
                if row.bottom < list_rect.y or row.y > list_rect.bottom:
                    continue
                self._draw_cosmetic_row(row, cosmetic_type, item, current_key, unlocked)
        finally:
            self.window.set_clip(old_clip)
        if max_scroll > 0:
            track = pygame.Rect(list_rect.right - 5, list_rect.y, 4, list_rect.h)
            pygame.draw.rect(self.window, (52, 45, 42), track, border_radius=2)
            thumb_h = max(18, int(list_rect.h * list_rect.h / max(list_rect.h, len(items) * item_h)))
            thumb_y = track.y + int((track.h - thumb_h) * (scroll / max_scroll)) if max_scroll else track.y
            pygame.draw.rect(self.window, settings.KINGDOM_CONFIG_HIGHLIGHT,
                             pygame.Rect(track.x, thumb_y, track.w, thumb_h), border_radius=2)

    def _draw_cosmetic_row(self, row, cosmetic_type, item, current_key, unlocked):
        key = item['key']
        active = key == current_key
        bg = settings.KINGDOM_CONFIG_CARD_ACTIVE_BG if active else settings.KINGDOM_CONFIG_CARD_BG
        pygame.draw.rect(self.window, bg, row, border_radius=6)
        chip = pygame.Rect(row.x + 6, row.y + 5, 32, row.h - 10)
        self._draw_cosmetic_chip(chip, cosmetic_type, key)
        btn = pygame.Rect(row.right - 76, row.y + 5, 66, row.h - 10)
        price_rect = pygame.Rect(btn.x - 58, row.y, 52, row.h)
        name = item.get('name', key)
        label_w = max(36, price_rect.x - chip.right - 12)
        label_text = self._fit_text(name, self._small_font, label_w)
        label = self._small_font.render(label_text, True, settings.KINGDOM_CONFIG_TEXT_CLR)
        self.window.blit(label, (chip.right + 6, row.y + 5))
        price = int(item.get('price_gold', 0) or 0)
        price_text = 'Free' if price <= 0 else f'{price}g'
        price_surf = self._tiny_font.render(price_text, True, settings.KINGDOM_CONFIG_DIM_CLR)
        self.window.blit(price_surf, price_surf.get_rect(center=price_rect.center))
        if key in unlocked:
            action_text = 'Equipped' if active else 'Equip'
            disabled = active
            action = 'equip_cosmetic'
        else:
            action_text = 'Buy'
            disabled = self._gold < price
            action = 'buy_cosmetic'
        self._draw_button(btn, action_text, action, key, disabled=disabled)

    def _draw_shield_panel(self, rect):
        self._draw_panel(rect, 'Kingdom Shield')
        if not self._kingdom:
            return
        icon_sz = int(rect.h * 0.38)
        if self._shield_icon:
            icon = pygame.transform.smoothscale(self._shield_icon, (icon_sz, icon_sz))
            self.window.blit(icon, (rect.x + 18, rect.y + 48))
        remaining = int(self._kingdom.get('shield_remaining', 0) or 0)
        status = 'No active shield'
        if remaining > 0:
            status = f'Protected for {remaining // 3600}h {(remaining % 3600) // 60}m'
        self.window.blit(self._body_font.render(status, True, settings.KINGDOM_CONFIG_TEXT_CLR),
                         (rect.x + 18 + icon_sz + 14, rect.y + 48))
        quote = self._quote or {}
        price = quote.get('price_gold', '—')
        self.window.blit(self._small_font.render(f'Quote: {price} gold', True,
                                                 settings.KINGDOM_CONFIG_DIM_CLR),
                         (rect.x + 18 + icon_sz + 14, rect.y + 78))
        options = (self._data or {}).get('shield_options_hours') or [6, 12, 24]
        x = rect.x + 18
        y = rect.bottom - 44
        for hours in options:
            btn = pygame.Rect(x, y, 58, 30)
            text = f'{hours}h'
            self._draw_button(btn, text, 'select_hours', hours,
                              disabled=False)
            if hours == self._selected_hours:
                pygame.draw.rect(self.window, settings.KINGDOM_CONFIG_GOOD_CLR, btn, 2,
                                 border_radius=7)
            x += 66
        buy_rect = pygame.Rect(rect.right - 124, y, 104, 30)
        self._draw_button(buy_rect, 'Buy Shield', 'buy_shield', None,
                          disabled=not quote or self._gold < int(quote.get('price_gold', 0) or 0))

    def _draw_skills_panel(self, rect):
        self._draw_panel(rect, 'Kingdom Skills')
        if not self._kingdom:
            return

        # Level / XP have moved to the unified header pill; this card now
        # focuses purely on the skill-point summary plus the skill rows.

        # ── Skill points summary ─────────────────────────────────────
        sp_y = rect.y + 40
        total = int(self._kingdom.get('skill_points_total', 0) or 0)
        spent = int(self._kingdom.get('skill_points_spent', 0) or 0)
        available = int(self._kingdom.get('skill_points_available', 0) or 0)
        summary = f'Skill points: {available} available / {total} total ({spent} spent)'
        self.window.blit(self._body_font.render(summary, True,
                                                settings.KINGDOM_CONFIG_TEXT_CLR),
                         (rect.x + 14, sp_y))

        # ── Skill rows (data-driven) ─────────────────────────────────
        y = sp_y + self._body_font.get_height() + 10
        skills = self._kingdom.get('skills') or {}
        row_step = settings.KINGDOM_CONFIG_SKILL_ROW_H
        if skills:
            available_h = max(1, rect.bottom - y - 12)
            row_step = max(58, min(row_step, available_h // max(1, len(skills))))
        for key, skill in skills.items():
            row = pygame.Rect(rect.x + 14, y, rect.w - 28, max(52, row_step - 8))
            pygame.draw.rect(self.window, settings.KINGDOM_CONFIG_CARD_BG, row, border_radius=8)
            icon = self._icons.get(key)
            icon_sz = min(42, row.h - 16)
            if icon:
                self.window.blit(pygame.transform.smoothscale(icon, (icon_sz, icon_sz)),
                                 (row.x + 10, row.y + 10))
            name = skill.get('name', key)
            level = int(skill.get('level', 0) or 0)
            max_level = int(skill.get('max_level', 5) or 5)
            self.window.blit(self._body_font.render(f'{name}  Lv {level}/{max_level}', True,
                                                    settings.KINGDOM_CONFIG_TEXT_CLR),
                             (row.x + 62, row.y + 8))
            desc = skill.get('description', '')[:72]
            self.window.blit(self._tiny_font.render(desc, True, settings.KINGDOM_CONFIG_DIM_CLR),
                             (row.x + 62, row.y + 34))
            cost = skill.get('next_cost')
            if cost is None:
                label = 'Max'
                disabled = True
            else:
                label = f'Upgrade ({cost})'
                disabled = available < int(cost)
            effect = self._tiny_font.render(self._skill_effect_text(key, skill), True,
                                            settings.KINGDOM_CONFIG_HIGHLIGHT)
            self.window.blit(effect, (row.x + 62, row.y + 50))
            btn = pygame.Rect(row.right - 120, row.y + (row.h - 30) // 2, 104, 30)
            self._draw_button(btn, label, 'upgrade_skill', key, disabled=disabled)
            y += row_step

    def _draw_vault_panel(self, rect):
        """Standalone Gold Vault card.

        Pending gold and the per-hour rate displayed here are computed lazily
        on every ``/kingdom/config`` fetch (see ``serialize_kingdom_config``):
        the server applies elapsed-time accrual against the vault cap when it
        serializes the kingdom, so the values are always fresh as of the
        most recent fetch \u2014 no background ticker is required.
        """
        self._draw_panel(rect, 'Gold Vault')
        self._collect_btn_rect = None
        if not self._kingdom:
            return

        pending = float(self._kingdom.get('pending_gold', 0) or 0)
        default_cap = int((self._data or {}).get('vault_default_cap', 50) or 50)
        vault_cap = int(self._kingdom.get('vault_cap') or 0)
        if vault_cap <= 0:
            vault_cap = default_cap
        rate_per_hour = float(self._kingdom.get('gold_rate_per_hour', 0) or 0)

        # Coin/vault icon on the left of the card.
        icon = self._icons.get('gold_vault')
        icon_sz = min(48, rect.h - 60)
        icon_pad_x = rect.x + 14
        body_x = icon_pad_x
        if icon and icon_sz > 0:
            self.window.blit(
                pygame.transform.smoothscale(icon, (icon_sz, icon_sz)),
                (icon_pad_x, rect.y + 44))
            body_x = icon_pad_x + icon_sz + 12

        # Vault progress bar (pending / cap), with collect button on the right.
        collect_w = 96
        bar_y = rect.y + 50
        bar_rect = pygame.Rect(body_x, bar_y,
                               rect.right - body_x - collect_w - 22,
                               settings.KINGDOM_VAULT_BAR_H)
        pygame.draw.rect(self.window, settings.KINGDOM_VAULT_BAR_TRACK_CLR,
                         bar_rect, border_radius=4)
        ratio = max(0.0, min(1.0, pending / float(vault_cap))) if vault_cap > 0 else 0.0
        if ratio >= 1.0:
            fill_clr = settings.KINGDOM_VAULT_BAR_FULL_CLR
        elif ratio >= settings.KINGDOM_VAULT_NEAR_FULL_RATIO:
            fill_clr = settings.KINGDOM_VAULT_BAR_NEAR_CLR
        else:
            fill_clr = settings.KINGDOM_VAULT_BAR_FILL_CLR
        if ratio > 0:
            fill_w = max(2, int(bar_rect.w * ratio))
            pygame.draw.rect(self.window, fill_clr,
                             pygame.Rect(bar_rect.x, bar_rect.y,
                                         fill_w, bar_rect.h),
                             border_radius=4)
        pygame.draw.rect(self.window, settings.KINGDOM_VAULT_BAR_BORDER_CLR,
                         bar_rect, 1, border_radius=4)
        vault_label = f'{int(pending)} / {vault_cap} gold'
        vault_surf = self._small_font.render(vault_label, True,
                                             settings.KINGDOM_CONFIG_TEXT_CLR)
        self.window.blit(vault_surf, (bar_rect.x, bar_rect.bottom + 4))

        # Production rate (effective and base).
        raw_rate = float(self._kingdom.get('raw_gold_rate', 0) or 0)
        effective_rate = float(self._kingdom.get('effective_gold_rate', raw_rate) or raw_rate)
        # Prefer the dedicated gold_rate_per_hour (skill-multiplied) when set,
        # falling back to the kingdom-wide effective rate.
        live_rate = rate_per_hour if rate_per_hour > 0 else effective_rate
        gain = max(0.0, live_rate - raw_rate)
        rate_y = bar_rect.bottom + 4 + vault_surf.get_height() + 2
        rate_base = self._tiny_font.render(
            f'Production: {raw_rate:.1f} gold/hr',
            True,
            settings.KINGDOM_CONFIG_HIGHLIGHT,
        )
        rate_bonus = self._tiny_font.render(
            f' +{gain:.1f}',
            True,
            settings.KINGDOM_CONFIG_GOOD_CLR,
        )
        self.window.blit(rate_base, (bar_rect.x, rate_y))
        self.window.blit(rate_bonus, (bar_rect.x + rate_base.get_width(), rate_y))
        rate_line_h = max(rate_base.get_height(), rate_bonus.get_height())

        # Collect button (right-aligned).
        collect_rect = pygame.Rect(bar_rect.right + 12, bar_rect.y - 4,
                                   collect_w, 30)
        self._collect_btn_rect = collect_rect
        self._draw_button(collect_rect, 'Collect', 'collect_kingdom_gold', None,
                          disabled=int(pending) <= 0)

        # Sanctuary badge for active core_protection.
        if self._kingdom.get('core_protection_active'):
            badge_y = (bar_rect.bottom + 4
                       + vault_surf.get_height() + 2
                       + rate_line_h + 2)
            badge = self._tiny_font.render('Sanctuary active',
                                           True, settings.KINGDOM_CONFIG_GOOD_CLR)
            self.window.blit(badge, (bar_rect.x, badge_y))

    def _layout_rects(self):
        self._box_rect = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        xsz = int(0.028 * _SH)
        xmargin = int(0.012 * _SW)
        self._btn_close_rect = pygame.Rect(
            _BOX_X + _BOX_W - xsz - xmargin,
            _BOX_Y + xmargin,
            xsz,
            xsz,
        )
        content_x = _BOX_X + _BOX_PAD
        header_y = _BOX_Y + _BOX_PAD
        # Unified header pill is a two-row widget: name + edit + pager on the
        # left, kingdom level + XP bar on the right.  Tall enough for both.
        header_h = int(0.105 * _SH)
        content_top = header_y + header_h + max(6, int(0.010 * _SH))
        content_bottom = _BOX_BOTTOM - _BOX_PAD
        gap = max(8, int(0.014 * _SH))
        left_w = min(settings.KINGDOM_CONFIG_LEFT_W, int(_BOX_W * 0.43))
        right_x = content_x + left_w + gap
        right_w = _BOX_X + _BOX_W - _BOX_PAD - right_x
        content_h = max(1, content_bottom - content_top)
        shield_h = min(settings.KINGDOM_CONFIG_SHIELD_H, max(92, int(content_h * 0.24)))
        card_h = max(82, (content_h - shield_h - gap * 3) // 3)
        # Right column splits into a dedicated Gold Vault card on top and the
        # Skills/Level panel below.
        vault_h = max(120, int(content_h * 0.22))
        # Header pill spans the content row, leaving clearance for the X.
        header_right = _BOX_X + _BOX_W - _BOX_PAD - xsz - xmargin
        header_rect = pygame.Rect(content_x, header_y,
                                  max(320, header_right - content_x),
                                  header_h)
        return {
            'header_y': header_y,
            'content_x': content_x,
            'content_top': content_top,
            'content_bottom': content_bottom,
            'gap': gap,
            'left_w': left_w,
            'right_x': right_x,
            'right_w': right_w,
            'shield_h': shield_h,
            'card_h': card_h,
            'vault_h': vault_h,
            'header': header_rect,
        }

    def _draw_rename_modal(self):
        if not self._rename_dialog:
            return
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 135))
        self.window.blit(overlay, (0, 0))

        box = pygame.Rect(0, 0, int(0.40 * _SW), int(0.28 * _SH))
        box.center = (_SW // 2, _SH // 2)
        self._draw_panel(box, None)
        pad = int(0.018 * _SH)
        title = self._heading_font.render('Rename Kingdom', True, settings.LAND_DETAIL_TITLE_CLR)
        self.window.blit(title, (box.x + pad, box.y + pad))

        price = int((self._data or {}).get('rename_price_gold', 0) or 0)
        helper = f'Renaming costs {price} gold. Enter confirms; Esc cancels.'
        helper = self._fit_text(helper, self._tiny_font, box.w - pad * 2)
        helper_surf = self._tiny_font.render(helper, True, settings.KINGDOM_CONFIG_DIM_CLR)
        self.window.blit(helper_surf, (box.x + pad, box.y + pad + title.get_height() + 8))

        input_y = box.y + pad + title.get_height() + helper_surf.get_height() + 22
        self._rename_input_rect = pygame.Rect(box.x + pad, input_y, box.w - pad * 2,
                                              int(0.052 * _SH))
        pygame.draw.rect(self.window, (18, 17, 24, 235), self._rename_input_rect,
                         border_radius=6)
        pygame.draw.rect(self.window, settings.KINGDOM_CONFIG_PANEL_BORDER,
                         self._rename_input_rect, 1, border_radius=6)
        text = self._rename_dialog.get('text') or ''
        display = text if text else 'Kingdom name'
        color = settings.KINGDOM_CONFIG_TEXT_CLR if text else settings.KINGDOM_CONFIG_DIM_CLR
        shown = self._fit_text(display, self._body_font, self._rename_input_rect.w - 18)
        shown_surf = self._body_font.render(shown, True, color)
        self.window.blit(shown_surf, (self._rename_input_rect.x + 9,
                                      self._rename_input_rect.centery - shown_surf.get_height() // 2))
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            cursor_x = self._rename_input_rect.x + 11 + min(
                self._body_font.size(text)[0], self._rename_input_rect.w - 24)
            pygame.draw.line(self.window, settings.KINGDOM_CONFIG_TEXT_CLR,
                             (cursor_x, self._rename_input_rect.y + 8),
                             (cursor_x, self._rename_input_rect.bottom - 8), 1)

        err = self._rename_dialog.get('error') or ''
        if err:
            err_surf = self._tiny_font.render(self._fit_text(err, self._tiny_font, box.w - pad * 2),
                                              True, settings.KINGDOM_CONFIG_BAD_CLR)
            self.window.blit(err_surf, (box.x + pad, self._rename_input_rect.bottom + 6))

        btn_w = int(0.094 * _SW)
        btn_h = int(0.040 * _SH)
        gap = int(0.012 * _SW)
        by = box.bottom - pad - btn_h
        self._rename_cancel_rect = pygame.Rect(box.right - pad - btn_w * 2 - gap, by, btn_w, btn_h)
        self._rename_confirm_rect = pygame.Rect(box.right - pad - btn_w, by, btn_w, btn_h)
        self._draw_button(self._rename_cancel_rect, 'Cancel', 'rename_cancel')
        can_afford = self._gold >= price
        self._draw_button(self._rename_confirm_rect, 'Rename', 'rename_confirm', disabled=not can_afford)

    def render(self):
        self._draw_menu_chrome()
        self._buttons = []
        self._cosmetic_scroll_areas = {}
        self._collect_btn_rect = None
        self._rename_icon_rect = None
        layout = self._layout_rects()
        _draw_config_frame(self.window, self._box_rect)
        # Unified header pill: pager + name + edit + level/XP in one widget.
        self._draw_header_pill(layout['header'])
        self._draw_close_x_button()

        if self._loading:
            msg = self._heading_font.render('Loading kingdom configuration …', True,
                                            settings.KINGDOM_CONFIG_TEXT_CLR)
            self.window.blit(msg, msg.get_rect(center=(settings.SCREEN_WIDTH // 2,
                                                       settings.SCREEN_HEIGHT // 2)))
            self._draw_menu_overlay()
            return

        if not self._kingdom:
            msg = self._heading_font.render('No owned kingdom found.', True,
                                            settings.KINGDOM_CONFIG_DIM_CLR)
            self.window.blit(msg, msg.get_rect(center=(settings.SCREEN_WIDTH // 2,
                                                       settings.SCREEN_HEIGHT // 2)))
            self._draw_menu_overlay()
            return

        left_x = layout['content_x']
        top = layout['content_top']
        left_w = layout['left_w']
        gap = layout['gap']
        card_h = layout['card_h']
        self._draw_cosmetic_section(pygame.Rect(left_x, top, left_w, card_h),
                                    'flag', 'Flag')
        self._draw_cosmetic_section(pygame.Rect(left_x, top + card_h + gap, left_w, card_h),
                                    'border', 'Border')
        self._draw_cosmetic_section(pygame.Rect(left_x, top + (card_h + gap) * 2, left_w, card_h),
                                    'surface', 'Surface')
        shield_y = top + (card_h + gap) * 3
        self._draw_shield_panel(pygame.Rect(left_x, shield_y, left_w,
                                            layout['shield_h']))

        right_x = layout['right_x']
        right_w = layout['right_w']
        right_top = top
        right_bottom = layout['content_bottom']
        vault_h = layout['vault_h']
        gap_v = layout['gap']
        vault_rect = pygame.Rect(right_x, right_top, right_w, vault_h)
        self._draw_vault_panel(vault_rect)
        skills_y = vault_rect.bottom + gap_v
        skills_h = max(120, right_bottom - skills_y)
        self._draw_skills_panel(pygame.Rect(right_x, skills_y, right_w, skills_h))

        if self._message and not getattr(self.state, 'message_lines', None):
            surf = self._small_font.render(self._message, True, settings.KINGDOM_CONFIG_GOOD_CLR)
            self.window.blit(surf, (_BOX_X + _BOX_PAD, _BOX_BOTTOM - surf.get_height() - 6))
        if self._rename_dialog:
            self._draw_rename_modal()
        # Drive and draw the floating-text layer (collect feedback, level-up).
        now_ms = pygame.time.get_ticks()
        dt_ms = max(0, now_ms - (self._last_render_ms or now_ms))
        self._last_render_ms = now_ms
        self._floating_text.update(dt_ms)
        self._floating_text.draw(self.window)
        self._draw_menu_overlay()
