# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Persistent connected-kingdom configuration screen."""

import os
import pygame
from pygame.locals import *

from config import settings
from game.components.cards.card_img import CardImg
from game.components.hex_map import _draw_surface_pattern
from game.components import badge_cosmetics
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
    'collect_kingdom_production',
    'collect_kingdom_production_item',
    'collect_loot',
    'acknowledge_loot',
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
        self._cosmetic_scroll = {'badge': 0, 'border': 0, 'surface': 0}
        self._cosmetic_scroll_areas = {}
        self._skills_scroll = 0
        self._skills_scroll_area = None
        self._skills_content_h = 0
        self._rename_dialog = None
        self._rename_input_rect = None
        self._rename_confirm_rect = None
        self._rename_cancel_rect = None
        self._pending_purchase = None
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
        self._loot_gained_rect = None
        self._loot_lost_rect = None

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

    def _fallback_production_items(self):
        default_cap = int((self._data or {}).get('vault_default_cap', 50) or 50)
        vault_cap = int(self._kingdom.get('vault_cap') or 0) if self._kingdom else 0
        if vault_cap <= 0:
            vault_cap = default_cap
        skills = (self._kingdom or {}).get('skills') or {}
        main_skill = skills.get('main_booster_production') or {}
        side_skill = skills.get('side_booster_production') or {}
        map_skill = skills.get('map_production') or {}
        return [
            {
                'key': 'gold',
                'kind': 'gold',
                'label': 'Gold Vault',
                'skill_key': 'gold_vault',
                'pending': float((self._kingdom or {}).get('pending_gold', 0) or 0),
                'capacity': vault_cap,
                'full': bool((self._kingdom or {}).get('vault_full')),
                'collectable': int(float((self._kingdom or {}).get('pending_gold', 0) or 0)) > 0,
                'progress_ratio': 0.0,
            },
            {
                'key': 'main_booster',
                'kind': 'booster',
                'label': 'Main Booster Pack',
                'skill_key': 'main_booster_production',
                'pending': int((self._kingdom or {}).get('pending_main_boosters', 0) or 0),
                'capacity': int((self._kingdom or {}).get('main_booster_capacity', 1) or 1),
                'enabled': int(main_skill.get('level', 0) or 0) > 0,
                'interval_hours': (self._kingdom or {}).get('main_booster_interval_hours'),
                'seconds_remaining': (self._kingdom or {}).get('main_booster_seconds_remaining'),
            },
            {
                'key': 'side_booster',
                'kind': 'booster',
                'label': 'Side Booster Pack',
                'skill_key': 'side_booster_production',
                'pending': int((self._kingdom or {}).get('pending_side_boosters', 0) or 0),
                'capacity': int((self._kingdom or {}).get('side_booster_capacity', 1) or 1),
                'enabled': int(side_skill.get('level', 0) or 0) > 0,
                'interval_hours': (self._kingdom or {}).get('side_booster_interval_hours'),
                'seconds_remaining': (self._kingdom or {}).get('side_booster_seconds_remaining'),
            },
            {
                'key': 'map',
                'kind': 'map',
                'label': 'Map',
                'skill_key': 'map_production',
                'pending': int((self._kingdom or {}).get('pending_maps', 0) or 0),
                'capacity': int((self._kingdom or {}).get('map_capacity', 1) or 1),
                'enabled': int(map_skill.get('level', 0) or 0) > 0,
                'interval_hours': (self._kingdom or {}).get('map_interval_hours'),
                'seconds_remaining': (self._kingdom or {}).get('map_seconds_remaining'),
            },
        ]

    def _production_items(self):
        items = (self._kingdom or {}).get('production_items') or []
        if items:
            return items
        return self._fallback_production_items()

    def _format_seconds(self, seconds):
        if seconds is None:
            return ''
        try:
            seconds = max(0, int(seconds or 0))
        except (TypeError, ValueError):
            return ''
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours >= 24:
            days = hours // 24
            rem = hours % 24
            return f'{days}d {rem}h'
        if hours > 0:
            return f'{hours}h {minutes}m'
        return f'{minutes}m'

    def _draw_production_item_row(self, item, row):
        """Draw a single production item inside its column-cell.

        Cells are laid out vertically (icon + title on top, progress bar in
        the middle, amount and detail below) so three items can share one
        compact row at one-third of the panel width each.
        """
        pad = 8
        key = item.get('key')
        skill_key = item.get('skill_key')
        icon = self._icons.get('gold_vault' if key == 'gold' else skill_key)
        icon_sz = 22
        icon_y = row.y + pad
        if icon:
            self.window.blit(pygame.transform.smoothscale(icon, (icon_sz, icon_sz)),
                             (row.x + pad, icon_y))

        title = item.get('label') or key
        pending = float(item.get('pending') or 0)
        capacity = float(item.get('capacity') or 0)
        is_full = bool(item.get('full')) or (capacity > 0 and pending >= capacity)
        title_clr = settings.KINGDOM_CONFIG_GOOD_CLR if is_full and key != 'gold' else settings.KINGDOM_CONFIG_TEXT_CLR
        title_text = self._fit_text(title, self._tiny_font,
                                    max(1, row.w - pad * 2 - icon_sz - 6))
        title_surf = self._tiny_font.render(title_text, True, title_clr)
        self.window.blit(title_surf, (row.x + pad + icon_sz + 6, icon_y + 4))

        bar_y = icon_y + icon_sz + 6
        bar_rect = pygame.Rect(row.x + pad, bar_y,
                               max(20, row.w - pad * 2),
                               max(6, settings.KINGDOM_VAULT_BAR_H - 4))
        ratio = max(0.0, min(1.0, float(item.get('progress_ratio', 0) or 0)))
        if capacity > 0 and key == 'gold':
            ratio = max(0.0, min(1.0, pending / capacity))
        elif capacity > 0 and pending > 0:
            ratio = max(ratio, min(1.0, pending / capacity))
        pygame.draw.rect(self.window, settings.KINGDOM_VAULT_BAR_TRACK_CLR,
                         bar_rect, border_radius=3)
        if ratio > 0:
            if ratio >= 1.0:
                fill_clr = settings.KINGDOM_VAULT_BAR_FULL_CLR
            elif ratio >= settings.KINGDOM_VAULT_NEAR_FULL_RATIO:
                fill_clr = settings.KINGDOM_VAULT_BAR_NEAR_CLR
            else:
                fill_clr = settings.KINGDOM_VAULT_BAR_FILL_CLR
            pygame.draw.rect(self.window, fill_clr,
                             pygame.Rect(bar_rect.x, bar_rect.y,
                                         max(2, int(bar_rect.w * ratio)), bar_rect.h),
                             border_radius=3)
        pygame.draw.rect(self.window, settings.KINGDOM_VAULT_BAR_BORDER_CLR,
                         bar_rect, 1, border_radius=3)

        text_y = bar_rect.bottom + 4
        max_text_w = max(1, row.w - pad * 2)

        if key == 'gold':
            cap_int = int(capacity or 0)
            amount_text = f'{int(pending)} / {cap_int} g'
            amount_surf = self._tiny_font.render(
                self._fit_text(amount_text, self._tiny_font, max_text_w),
                True, settings.KINGDOM_CONFIG_TEXT_CLR)
            self.window.blit(amount_surf, (row.x + pad, text_y))

            raw_rate = float(self._kingdom.get('raw_gold_rate', 0) or 0)
            effective_rate = float(self._kingdom.get('effective_gold_rate', raw_rate) or raw_rate)
            rate_per_hour = float(self._kingdom.get('gold_rate_per_hour', 0) or 0)
            live_rate = rate_per_hour if rate_per_hour > 0 else effective_rate
            gain = max(0.0, live_rate - raw_rate)
            rate_text = f'{raw_rate:.1f} g/hr'
            if gain > 0:
                rate_text += f' (+{gain:.1f})'
            rate_text = self._fit_text(rate_text, self._tiny_font, max_text_w)
            rate_surf = self._tiny_font.render(rate_text, True,
                                               settings.KINGDOM_CONFIG_HIGHLIGHT)
            self.window.blit(rate_surf,
                             (row.x + pad,
                              text_y + self._tiny_font.get_height() + 1))
            return

        enabled = bool(item.get('enabled'))
        interval = item.get('interval_hours')
        if not enabled:
            amount_text = '—'
            amount_clr = settings.KINGDOM_CONFIG_DIM_CLR
            detail = 'Unlock skill to start'
            detail_clr = settings.KINGDOM_CONFIG_DIM_CLR
        elif int(pending) > 0:
            amount_text = f'{int(pending)} / {int(capacity or 1)}'
            amount_clr = settings.KINGDOM_CONFIG_GOOD_CLR
            detail = 'Ready'
            detail_clr = settings.KINGDOM_CONFIG_GOOD_CLR
        else:
            amount_text = f'0 / {int(capacity or 1)}'
            amount_clr = settings.KINGDOM_CONFIG_TEXT_CLR
            remaining = self._format_seconds(item.get('seconds_remaining'))
            if remaining:
                detail = f'Ready in {remaining}'
            elif interval:
                detail = f'every {self._format_hours(interval)}'
            else:
                detail = 'Charging'
            detail_clr = settings.KINGDOM_CONFIG_HIGHLIGHT
        amount_surf = self._tiny_font.render(
            self._fit_text(amount_text, self._tiny_font, max_text_w),
            True, amount_clr)
        self.window.blit(amount_surf, (row.x + pad, text_y))
        detail_surf = self._tiny_font.render(
            self._fit_text(detail, self._tiny_font, max_text_w),
            True, detail_clr)
        self.window.blit(detail_surf,
                         (row.x + pad,
                          text_y + self._tiny_font.get_height() + 1))

    def _production_item_collectable(self, item):
        try:
            pending = float(item.get('pending') or 0)
        except (TypeError, ValueError):
            pending = 0.0
        return int(pending) > 0

    def _draw_production_item_cell(self, item, cell):
        collectable = self._production_item_collectable(item)
        mouse_pos = pygame.mouse.get_pos()
        hovered = bool(collectable and cell.collidepoint(mouse_pos))
        bg = settings.KINGDOM_CONFIG_CARD_ACTIVE_BG if collectable else settings.KINGDOM_CONFIG_CARD_BG
        if hovered:
            bg = tuple(min(255, c + 10) for c in bg)
        border = settings.KINGDOM_CONFIG_GOOD_CLR if collectable else settings.KINGDOM_CONFIG_DIM_CLR
        pygame.draw.rect(self.window, bg, cell, border_radius=8)
        pygame.draw.rect(self.window, border, cell, 2 if hovered else 1, border_radius=8)
        self._draw_production_item_row(item, cell)
        if collectable and item.get('key'):
            self._buttons.append(('collect_kingdom_production_item', item.get('key'), cell))

    def _draw_vault_panel(self, rect):
        """General Kingdom Production card: gold vault plus booster packs."""
        self._draw_panel(rect, 'Kingdom Production')
        self._collect_btn_rect = None
        if not self._kingdom:
            return

        items = self._production_items()
        collectable = any(
            (int(float(item.get('pending') or 0)) > 0)
            for item in items
        )
        collect_w = 118
        collect_rect = pygame.Rect(rect.right - collect_w - 14, rect.y + 10, collect_w, 28)
        self._collect_btn_rect = collect_rect
        self._draw_button(collect_rect, 'Collect All', 'collect_kingdom_production', None,
                          disabled=not collectable)

        content_y = rect.y + 42
        available_h = max(1, rect.bottom - content_y - 8)
        n = max(1, len(items))
        col_gap = 6
        total_gap = col_gap * (n - 1)
        cell_w = max(1, (rect.w - 28 - total_gap) // n)
        cell_h = min(available_h, 92)
        x = rect.x + 14
        for item in items:
            cell = pygame.Rect(x, content_y, cell_w, cell_h)
            self._draw_production_item_cell(item, cell)
            x += cell_w + col_gap

    def _loot_cards_from_events(self, events):
        cards = []
        for event in events or []:
            if not isinstance(event, dict):
                continue
            for card in (event.get('cards') or []):
                if not isinstance(card, dict):
                    continue
                suit = card.get('suit')
                rank = card.get('rank')
                if suit and rank:
                    cards.append(card)
        return cards

    def _loot_stack_layout(self, card_count, card_w, max_width):
        card_count = max(0, int(card_count or 0))
        card_w = max(1, int(card_w or 1))
        max_width = max(card_w, int(max_width or card_w))
        if card_count <= 1:
            return {'step': 0.0, 'total_w': float(card_w)}
        max_step = max(0.0, float(max_width - card_w) / float(card_count - 1))
        step = min(float(card_w), max_step)
        total_w = float(card_w) + float(card_count - 1) * step
        return {'step': step, 'total_w': total_w}

    def _get_loot_card_surface(self, suit, rank, size):
        suit = str(suit or '')
        rank = str(rank or '')
        width = max(1, int(size[0]))
        height = max(1, int(size[1]))
        cache = getattr(self, '_loot_card_surface_cache', None)
        if cache is None:
            cache = {}
            self._loot_card_surface_cache = cache
        key = (suit, rank, width, height)
        surf = cache.get(key)
        if surf is not None:
            return surf
        try:
            surf = CardImg(self.window, suit, rank, width=width, height=height).front_img
        except Exception:
            return None
        cache[key] = surf
        return surf

    def _draw_loot_card_stack(self, rect, cards, accent):
        if not cards or rect.w <= 0 or rect.h <= 0:
            return
        aspect = float(settings.CARD_WIDTH) / float(max(1, settings.CARD_HEIGHT))
        card_h = min(rect.h, max(38, int(rect.h * 0.95)))
        card_w = max(24, int(round(card_h * aspect)))
        if card_w > rect.w:
            card_w = rect.w
            card_h = max(1, int(round(float(card_w) / max(0.01, aspect))))
        layout = self._loot_stack_layout(len(cards), card_w, rect.w)
        total_w = int(round(layout['total_w']))
        start_x = rect.x + max(0, (rect.w - total_w) // 2)
        y = rect.y + max(0, (rect.h - card_h) // 2)

        shadow = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 45))
        for idx, card in enumerate(cards):
            surf = self._get_loot_card_surface(card.get('suit'), card.get('rank'), (card_w, card_h))
            if surf is None:
                continue
            x = start_x + int(round(idx * layout['step']))
            self.window.blit(shadow, (x + 2, y + 2))
            self.window.blit(surf, (x, y))
            pygame.draw.rect(self.window, accent, pygame.Rect(x, y, card_w, card_h), 1,
                             border_radius=4)

    def _draw_loot_compartment(self, rect, *, title, subtitle, cards, card_count,
                               accent, empty_text, action=None, active=False):
        mouse_pos = pygame.mouse.get_pos()
        hovered = bool(active and rect.collidepoint(mouse_pos))
        bg = settings.KINGDOM_CONFIG_CARD_ACTIVE_BG if active else settings.KINGDOM_CONFIG_CARD_BG
        if hovered:
            bg = tuple(min(255, c + 10) for c in bg)
        frame_clr = accent if active else settings.KINGDOM_CONFIG_DIM_CLR
        title_clr = settings.KINGDOM_CONFIG_TEXT_CLR if active else settings.KINGDOM_CONFIG_DIM_CLR
        pygame.draw.rect(self.window, bg, rect, border_radius=8)
        pygame.draw.rect(self.window, frame_clr, rect, 2 if hovered else 1, border_radius=8)

        pad = 10
        title_surf = self._small_font.render(title, True, title_clr)
        self.window.blit(title_surf, (rect.x + pad, rect.y + 8))

        count_label = f'{card_count} card{"s" if card_count != 1 else ""}'
        count_surf = self._tiny_font.render(count_label, True, frame_clr)
        count_rect = count_surf.get_rect(topright=(rect.right - pad, rect.y + 11))
        self.window.blit(count_surf, count_rect)

        stack_y = rect.y + 12 + title_surf.get_height() + 6
        if rect.h >= 88:
            subtitle_surf = self._tiny_font.render(
                self._fit_text(subtitle, self._tiny_font, rect.w - pad * 2),
                True,
                settings.KINGDOM_CONFIG_DIM_CLR,
            )
            subtitle_y = rect.y + 11 + title_surf.get_height()
            self.window.blit(subtitle_surf, (rect.x + pad, subtitle_y))
            stack_y = subtitle_y + subtitle_surf.get_height() + 6

        stack_rect = pygame.Rect(rect.x + pad, stack_y, rect.w - pad * 2,
                                 max(1, rect.bottom - stack_y - 8))
        if card_count <= 0 or not cards:
            lines = self._wrap_text(empty_text, self._tiny_font, stack_rect.w)
            total_h = len(lines) * self._tiny_font.get_height() + max(0, len(lines) - 1) * 2
            y = stack_rect.y + max(0, (stack_rect.h - total_h) // 2)
            for line in lines:
                surf = self._tiny_font.render(line, True, settings.KINGDOM_CONFIG_DIM_CLR)
                self.window.blit(surf, surf.get_rect(centerx=stack_rect.centerx, y=y))
                y += self._tiny_font.get_height() + 2
        else:
            self._draw_loot_card_stack(stack_rect, cards, accent if active else frame_clr)

        if active and action:
            self._buttons.append((action, None, rect))

    def _draw_loot_inbox_panel(self, rect):
        """Loot Inbox card: pending gained cards and unseen lost cards."""
        self._draw_panel(rect, 'Loot Inbox')
        inbox = (self._kingdom or {}).get('loot_inbox') or {}
        gained = inbox.get('gained') or []
        lost = inbox.get('lost') or []
        gained_count = int(inbox.get('gained_card_count') or 0)
        lost_count = int(inbox.get('lost_card_count') or 0)
        gained_cards = self._loot_cards_from_events(gained)
        lost_cards = self._loot_cards_from_events(lost)
        gained_count = max(gained_count, len(gained_cards))
        lost_count = max(lost_count, len(lost_cards))

        body_x = rect.x + 14
        body_y = rect.y + 42
        body_w = rect.w - 28
        body_rect = pygame.Rect(body_x, body_y, body_w, max(1, rect.bottom - body_y - 10))
        gap = 10
        cell_w = max(1, (body_rect.w - gap) // 2)
        gained_rect = pygame.Rect(body_rect.x, body_rect.y, cell_w, body_rect.h)
        lost_rect = pygame.Rect(gained_rect.right + gap, body_rect.y,
                                body_rect.w - cell_w - gap, body_rect.h)
        self._loot_gained_rect = gained_rect
        self._loot_lost_rect = lost_rect

        self._draw_loot_compartment(
            gained_rect,
            title='Gained',
            subtitle='Pending collection',
            cards=gained_cards,
            card_count=gained_count,
            accent=settings.KINGDOM_CONFIG_GOOD_CLR,
            empty_text='No gained cards waiting here.',
            action='collect_loot',
            active=gained_count > 0,
        )
        self._draw_loot_compartment(
            lost_rect,
            title='Lost',
            subtitle='Unseen losses',
            cards=lost_cards,
            card_count=lost_count,
            accent=settings.KINGDOM_CONFIG_BAD_CLR,
            empty_text='No lost-card notices right now.',
            action='acknowledge_loot',
            active=lost_count > 0,
        )

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
            if data.get('already_unlocked'):
                self._set_msg('Cosmetic already owned')
            else:
                self._set_msg('Cosmetic unlocked and equipped')
            self._fetch_config()

    def _equip_cosmetic(self, key):
        data = self._post_action('cosmetics/equip', {'cosmetic_key': key})
        if data:
            self._set_msg('Kingdom style updated')
            self._fetch_config()

    def _catalog_item(self, key):
        item = (self._catalog or {}).get(key)
        if not item:
            return {}
        row = dict(item)
        row['key'] = key
        return row

    def _confirm_cosmetic_purchase(self, key):
        item = self._catalog_item(key)
        price = max(0, int(item.get('price_gold', 0) or 0))
        if price <= 0:
            self._buy_cosmetic(key)
            return
        name = item.get('name') or key
        self._pending_purchase = {
            'kind': 'cosmetic',
            'key': key,
            'name': name,
            'price': price,
        }
        self.make_dialogue_box(
            f'Buy {name} for {price} gold? It will be equipped immediately.',
            actions=['Confirm', 'Cancel'],
            title='Confirm Purchase',
        )

    def _confirm_shield_purchase(self):
        quote = self._quote or {}
        price = max(0, int(quote.get('price_gold', 0) or 0))
        if price <= 0:
            self._buy_shield()
            return
        hours = int(quote.get('hours', self._selected_hours) or self._selected_hours)
        self._pending_purchase = {
            'kind': 'shield',
            'hours': hours,
            'price': price,
        }
        self.make_dialogue_box(
            f'Buy a {hours}h kingdom shield for {price} gold?',
            actions=['Confirm', 'Cancel'],
            title='Confirm Purchase',
        )

    def _handle_pending_purchase_dialogue(self, events):
        if not self._pending_purchase:
            return False
        if not self.dialogue_box:
            self._pending_purchase = None
            return False
        response = self.dialogue_box.update(events)
        if not response:
            return True

        pending = self._pending_purchase
        self._pending_purchase = None
        self.dialogue_box = None
        if response == 'confirm':
            if pending.get('kind') == 'cosmetic':
                self._buy_cosmetic(pending.get('key'))
            elif pending.get('kind') == 'shield':
                self._buy_shield()
        else:
            self._set_msg('Purchase cancelled')
        return True

    def _upgrade_skill(self, key):
        data = self._post_action('skills/upgrade', {'skill_key': key})
        if data:
            self._set_msg('Skill upgraded')
            self._fetch_quote(silent=True)

    def _collect_kingdom_production(self, item_key=None, origin_rect=None):
        if not self._kingdom:
            return
        kid = self._kingdom['id']
        payload = {}
        if item_key:
            payload['item_key'] = item_key
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/{kid}/collect_production',
                json=payload, timeout=12,
            )
        except Exception as exc:
            self._set_msg(f'Collect failed: {exc}')
            return
        try:
            data = resp.json()
        except ValueError:
            snippet = (getattr(resp, 'text', '') or '').strip().splitlines()
            head = snippet[0][:80] if snippet else ''
            self._set_msg(
                f'Collect failed: server returned HTTP {resp.status_code}'
                + (f' ({head})' if head else '')
            )
            return
        if not data.get('success'):
            self._set_msg(data.get('message', 'Collect failed'))
            return
        collected = int(data.get('collected_gold', data.get('collected', 0)) or 0)
        collected_main = int(data.get('collected_main_boosters', 0) or 0)
        collected_side = int(data.get('collected_side_boosters', 0) or 0)
        collected_maps = int(data.get('collected_maps', 0) or 0)
        if collected > 0 and hasattr(self, '_suppress_next_gold_floater'):
            self._suppress_next_gold_floater()
        if 'gold' in data:
            self._sync_gold(data['gold'])
        elif 'total_gold' in data:
            self._sync_gold(data['total_gold'])
        if getattr(self.state, 'user_dict', None) is not None:
            if 'booster_packs' in data:
                self.state.user_dict['booster_packs'] = int(data.get('booster_packs') or 0)
            if 'booster_packs_side' in data:
                self.state.user_dict['booster_packs_side'] = int(data.get('booster_packs_side') or 0)
            if 'maps' in data:
                self.state.user_dict['maps'] = int(data.get('maps') or 0)
        if self._kingdom is not None:
            if 'pending_gold' in data:
                self._kingdom['pending_gold'] = float(data.get('pending_gold') or 0.0)
            if 'vault_cap' in data:
                self._kingdom['vault_cap'] = int(data.get('vault_cap') or 0)
            if 'production' in data:
                self._kingdom['production'] = data.get('production') or {}
            if 'production_items' in data:
                self._kingdom['production_items'] = data.get('production_items') or []
            for key in ('pending_main_boosters', 'pending_side_boosters', 'pending_maps'):
                if key in data:
                    self._kingdom[key] = int(data.get(key) or 0)
        # Refresh shield quote so price reflects current gold / kingdom state.
        self._fetch_quote(silent=True)
        anchor_rect = origin_rect or self._collect_btn_rect
        if item_key:
            if anchor_rect is not None:
                if item_key == 'gold' and collected > 0:
                    self._spawn_collect_floater(collected, anchor_rect.center)
                elif item_key == 'main_booster' and collected_main > 0:
                    self._spawn_named_collect_floater('+1 Main Pack' if collected_main == 1 else f'+{collected_main} Main Packs',
                                                      anchor_rect.center,
                                                      color=settings.COLLECT_FLOAT_XP_CLR)
                elif item_key == 'side_booster' and collected_side > 0:
                    self._spawn_named_collect_floater('+1 Side Pack' if collected_side == 1 else f'+{collected_side} Side Packs',
                                                      anchor_rect.center,
                                                      color=settings.COLLECT_FLOAT_XP_CLR)
                elif item_key == 'map' and collected_maps > 0:
                    self._spawn_named_collect_floater('+1 Map' if collected_maps == 1 else f'+{collected_maps} Maps',
                                                      anchor_rect.center,
                                                      color=settings.COLLECT_FLOAT_XP_CLR)
        elif collected > 0 and self._collect_btn_rect is not None:
            self._spawn_collect_floater(collected, self._collect_btn_rect.center)
        parts = []
        if collected:
            parts.append(f'+{collected}g')
        if collected_main:
            parts.append(f'+{collected_main} main booster{"s" if collected_main != 1 else ""}')
        if collected_side:
            parts.append(f'+{collected_side} side booster{"s" if collected_side != 1 else ""}')
        if collected_maps:
            parts.append(f'+{collected_maps} map{"s" if collected_maps != 1 else ""}')
        if parts:
            self._set_msg('Collected ' + ', '.join(parts))

    def _collect_kingdom_gold(self):
        """Backward-compatible handler name used by existing button tests."""
        self._collect_kingdom_production()

    def _collect_loot(self):
        data = self._post_action('loot/collect', {})
        if data:
            count = int(data.get('collected_count') or 0)
            if count:
                loot_rect = getattr(self, '_loot_gained_rect', None)
                if loot_rect is not None:
                    self._spawn_loot_collect_floater(count, loot_rect.center)
                self._set_msg(f'Collected {count} looted card{"s" if count != 1 else ""}')
            else:
                self._set_msg('No pending loot to collect')

    def _acknowledge_loot(self):
        data = self._post_action('loot/acknowledge', {})
        if data:
            count = int(data.get('acknowledged_count') or 0)
            if count:
                loot_rect = getattr(self, '_loot_lost_rect', None)
                if loot_rect is not None:
                    self._spawn_loot_lost_floater(count, loot_rect.center)
                self._set_msg('Loot losses noticed')
            else:
                self._set_msg('No lost loot notices pending')

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

    def _spawn_named_collect_floater(self, text, pos, *, color, delay_ms=0):
        font = settings.get_font(settings.COLLECT_FLOAT_FONT_SIZE, bold=True)
        self._floating_text.add(FloatingText(
            text, pos,
            color=color,
            duration_ms=settings.COLLECT_FLOAT_DURATION_MS,
            rise_px=settings.COLLECT_FLOAT_RISE_PX,
            font=font,
            delay_ms=delay_ms,
        ))

    def _spawn_loot_collect_floater(self, count, pos, *, delay_ms=0):
        font = settings.get_font(settings.COLLECT_FLOAT_FONT_SIZE, bold=True)
        self._floating_text.add(FloatingText(
            f'+{int(count)} card{"s" if int(count) != 1 else ""}', pos,
            color=settings.KINGDOM_CONFIG_GOOD_CLR,
            duration_ms=settings.COLLECT_FLOAT_DURATION_MS,
            rise_px=settings.COLLECT_FLOAT_RISE_PX,
            font=font,
            delay_ms=delay_ms,
        ))

    def _spawn_loot_lost_floater(self, count, pos, *, delay_ms=0):
        font = settings.get_font(settings.COLLECT_FLOAT_FONT_SIZE, bold=True)
        self._floating_text.add(FloatingText(
            f'-{int(count)} card{"s" if int(count) != 1 else ""}', pos,
            color=settings.KINGDOM_CONFIG_BAD_CLR,
            duration_ms=settings.COLLECT_FLOAT_DURATION_MS,
            rise_px=-settings.COLLECT_FLOAT_RISE_PX,
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
        if self._handle_pending_purchase_dialogue(events):
            return
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
                if self._skills_scroll_area and self._skills_scroll_area.collidepoint(pos):
                    self._scroll_skills_panel(getattr(event, 'y', 0))
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
                    self._confirm_shield_purchase()
                elif action == 'buy_cosmetic':
                    self._confirm_cosmetic_purchase(value)
                elif action == 'equip_cosmetic':
                    self._equip_cosmetic(value)
                elif action == 'rename_start':
                    self._start_rename()
                elif action == 'upgrade_skill':
                    self._upgrade_skill(value)
                elif action in ('collect_kingdom_gold', 'collect_kingdom_production'):
                    self._collect_kingdom_production()
                elif action == 'collect_kingdom_production_item':
                    self._collect_kingdom_production(item_key=value, origin_rect=rect)
                elif action == 'collect_loot':
                    self._collect_loot()
                elif action == 'acknowledge_loot':
                    self._acknowledge_loot()
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

    def _scroll_skills_panel(self, wheel_y):
        area = self._skills_scroll_area
        if not area:
            return
        step = max(1, int(settings.KINGDOM_CONFIG_SKILL_ROW_H))
        max_scroll = max(0, int(self._skills_content_h or 0) - area.h)
        current = int(self._skills_scroll or 0)
        current -= int(wheel_y or 0) * step
        self._skills_scroll = max(0, min(max_scroll, current))

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

    def _wrap_text(self, text, font, max_width):
        """Word-wrap *text* into lines that each fit within *max_width* px."""
        words = str(text).split()
        lines, current = [], ''
        for word in words:
            test = (current + ' ' + word).strip()
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                if font.size(word)[0] > max_width:
                    lines.append(self._fit_text(word, font, max_width))
                    current = ''
                else:
                    current = word
        if current:
            lines.append(current)
        return lines or ['']

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

        # ── State notification pills (below XP) ─────────────────────
        notifications = []
        if self._kingdom.get('core_protection_active'):
            notifications.append(('Sanctuary active', settings.KINGDOM_CONFIG_GOOD_CLR))
        if notifications:
            pill_h = self._tiny_font.get_height() + 6
            pad_x = 8
            nx = right_rect.x + right_pad_x
            ny = xp_y + xp_surf.get_height() + 4
            for text, color in notifications:
                if ny + pill_h > right_rect.bottom - 2:
                    break
                text_surf = self._tiny_font.render(text, True, color)
                pill_w = text_surf.get_width() + pad_x * 2
                pill_rect = pygame.Rect(nx, ny, pill_w, pill_h)
                pygame.draw.rect(self.window, (35, 29, 34, 180), pill_rect, border_radius=4)
                pygame.draw.rect(self.window, color, pill_rect, 1, border_radius=4)
                self.window.blit(text_surf, (nx + pad_x, ny + 3))
                nx += pill_w + 6

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

    @staticmethod
    def _format_hours(value):
        try:
            value = float(value or 0)
        except (TypeError, ValueError):
            value = 0.0
        if abs(value - round(value)) < 1e-6:
            return f'{int(round(value))}h'
        return f'{value:.1f}h'

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
        elif key in ('main_booster_production', 'side_booster_production'):
            current_text = 'disabled' if level <= 0 else f'every {self._format_hours(current)}'
            next_text = f'every {self._format_hours(next_value)}'
        elif key == 'core_protection':
            current_text = f'protect {int(current)} land' + ('s' if int(current) != 1 else '')
            next_text = f'protect {int(next_value)} land' + ('s' if int(next_value) != 1 else '')
        elif key == 'loot_chance':
            current_text = f'{int(round(float(current) * 100))}% extra loot'
            next_text = f'{int(round(float(next_value) * 100))}% extra loot'
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
        self._draw_surface_skin_preview(style.get('surface_key'), points)
        border = settings.HEX_BORDER_SKINS.get(style.get('border_key'),
                                               settings.HEX_BORDER_SKINS['border_simple_gold'])
        pygame.draw.polygon(self.window, border.get('outer', (90, 70, 40)), points, 5)
        pygame.draw.polygon(self.window, border.get('main', (250, 221, 0)), points, 3)
        badge_key = style.get('badge_key', settings.HEX_BADGE_DEFAULT_KEY)
        badge_h = max(18, min(rect.h // 3, 30))
        shimmer_phase = badge_cosmetics.shimmer_phase_for(
            pygame.time.get_ticks())
        badge_surf = badge_cosmetics.render_badge(
            badge_key, 'Kingdom', self._small_font,
            target_h=badge_h, shimmer_phase=shimmer_phase)
        bx = rect.centerx - badge_surf.get_width() // 2
        by = rect.bottom - badge_surf.get_height() - 6
        self.window.blit(badge_surf, (bx, by))

    def _draw_surface_skin_preview(self, surface_key, points, seed=0):
        skin = settings.HEX_SURFACE_SKINS.get(surface_key, {})
        overlay = skin.get('overlay')
        pattern = skin.get('pattern')
        if not overlay and not pattern:
            return
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        rect = pygame.Rect(int(min(xs)), int(min(ys)),
                           max(1, int(max(xs) - min(xs)) + 1),
                           max(1, int(max(ys) - min(ys)) + 1))
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        local = [(x - rect.x, y - rect.y) for x, y in points]
        if overlay:
            pygame.draw.polygon(surf, overlay, local)
        if pattern:
            pattern_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            _draw_surface_pattern(
                pattern_surf,
                pattern,
                skin.get('pattern_clr', (0, 0, 0, 64)),
                int(seed or 0),
                max(1, min(rect.w, rect.h) / 2),
            )
            mask = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.polygon(mask, (255, 255, 255, 255), local)
            pattern_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(pattern_surf, (0, 0))
        self.window.blit(surf, rect.topleft)

    def _draw_cosmetic_chip(self, rect, cosmetic_type, key):
        pygame.draw.rect(self.window, (20, 18, 22), rect, border_radius=5)
        pygame.draw.rect(self.window, (84, 74, 58), rect, 1, border_radius=5)
        if cosmetic_type == 'badge':
            badge_h = max(14, min(rect.h - 8, 26))
            shimmer_phase = badge_cosmetics.shimmer_phase_for(
                pygame.time.get_ticks())
            badge_surf = badge_cosmetics.render_badge(
                key, 'Realm', self._tiny_font,
                target_h=badge_h, shimmer_phase=shimmer_phase)
            # Scale to fit chip width while preserving aspect.
            max_w = rect.w - 8
            if badge_surf.get_width() > max_w:
                scale = max_w / badge_surf.get_width()
                new_size = (int(badge_surf.get_width() * scale),
                            int(badge_surf.get_height() * scale))
                badge_surf = pygame.transform.smoothscale(
                    badge_surf, new_size)
            bx = rect.centerx - badge_surf.get_width() // 2
            by = rect.centery - badge_surf.get_height() // 2
            self.window.blit(badge_surf, (bx, by))
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
            pygame.draw.polygon(self.window, fill, points)
            self._draw_surface_skin_preview(
                key,
                points,
                seed=sum(ord(ch) for ch in str(key)),
            )
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
        self._skills_scroll_area = None
        self._skills_content_h = 0
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
        list_y = sp_y + self._body_font.get_height() + 10
        skills = self._kingdom.get('skills') or {}
        if not skills:
            return

        # Use the configured row height as the natural per-row size and clip
        # the list inside a scrollable area so tall skill lists never spill
        # past the bottom of the panel.
        row_step = max(64, settings.KINGDOM_CONFIG_SKILL_ROW_H)
        row_h = max(58, row_step - 8)
        list_rect = pygame.Rect(rect.x + 14, list_y,
                                rect.w - 28,
                                max(row_h, rect.bottom - list_y - 12))
        self._skills_scroll_area = list_rect
        content_h = row_step * len(skills)
        self._skills_content_h = content_h
        max_scroll = max(0, content_h - list_rect.h)
        scroll = max(0, min(max_scroll, int(getattr(self, '_skills_scroll', 0) or 0)))
        self._skills_scroll = scroll

        scrollbar_w = 8 if max_scroll > 0 else 0
        row_w = list_rect.w - (scrollbar_w + 4 if scrollbar_w else 0)

        old_clip = self.window.get_clip()
        self.window.set_clip(list_rect.clip(old_clip))
        try:
            for idx, (key, skill) in enumerate(skills.items()):
                y = list_rect.y + idx * row_step - scroll
                if y + row_h < list_rect.y or y > list_rect.bottom:
                    continue
                row = pygame.Rect(list_rect.x, y, row_w, row_h)
                pygame.draw.rect(self.window, settings.KINGDOM_CONFIG_CARD_BG, row,
                                 border_radius=8)
                icon = self._icons.get(key)
                icon_sz = min(42, row.h - 16)
                if icon:
                    self.window.blit(pygame.transform.smoothscale(icon, (icon_sz, icon_sz)),
                                     (row.x + 10, row.y + 10))
                name = skill.get('name', key)
                level = int(skill.get('level', 0) or 0)
                max_level = int(skill.get('max_level', 5) or 5)
                btn = pygame.Rect(row.right - 120, row.y + (row.h - 30) // 2, 104, 30)
                text_x = row.x + 62
                # Clamp text width so it never reaches the upgrade button.
                text_max_w = max(20, btn.x - text_x - 8)
                bottom_limit = row.bottom - 2

                # ── Name + level (single line, truncate) ────────────
                body_h = self._body_font.get_height()
                tiny_h = self._tiny_font.get_height()
                name_y = row.y + 8
                if name_y + body_h <= bottom_limit:
                    self.window.blit(
                        self._body_font.render(
                            self._fit_text(f'{name}  Lv {level}/{max_level}',
                                           self._body_font, text_max_w),
                            True, settings.KINGDOM_CONFIG_TEXT_CLR),
                        (text_x, name_y))

                # ── Description (word-wrapped, ≤ 2 lines) ───────────
                cur_y = name_y + body_h + 3
                desc_lines = self._wrap_text(
                    skill.get('description', ''), self._tiny_font, text_max_w)[:2]
                for line in desc_lines:
                    if cur_y + tiny_h > bottom_limit:
                        break
                    self.window.blit(
                        self._tiny_font.render(line, True, settings.KINGDOM_CONFIG_DIM_CLR),
                        (text_x, cur_y))
                    cur_y += tiny_h + 1

                # ── Effect (single line, truncate) below description ─
                effect_y = cur_y + 2
                if effect_y + tiny_h <= bottom_limit:
                    self.window.blit(
                        self._tiny_font.render(
                            self._fit_text(self._skill_effect_text(key, skill),
                                           self._tiny_font, text_max_w),
                            True, settings.KINGDOM_CONFIG_HIGHLIGHT),
                        (text_x, effect_y))

                cost = skill.get('next_cost')
                if cost is None:
                    label = 'Max'
                    disabled = True
                else:
                    label = f'Upgrade ({cost})'
                    disabled = available < int(cost)
                # Drawing is clipped to the viewport, but `_draw_button`
                # registers click hitboxes against the absolute rect — so
                # only register the button when its full hitbox is visible
                # to keep clicks from firing in empty space below the list.
                if list_rect.contains(btn):
                    self._draw_button(btn, label, 'upgrade_skill', key, disabled=disabled)
                else:
                    self._draw_button(btn, label, 'upgrade_skill', key, disabled=True)
                    if self._buttons and self._buttons[-1][2] == btn:
                        self._buttons.pop()
        finally:
            self.window.set_clip(old_clip)

        if max_scroll > 0:
            track = pygame.Rect(list_rect.right - scrollbar_w + 2, list_rect.y,
                                scrollbar_w - 4, list_rect.h)
            pygame.draw.rect(self.window, (52, 45, 42), track, border_radius=2)
            thumb_h = max(20, int(list_rect.h * list_rect.h / max(1, content_h)))
            thumb_y = track.y + int((track.h - thumb_h) * (scroll / max_scroll))
            pygame.draw.rect(self.window, settings.KINGDOM_CONFIG_HIGHLIGHT,
                             pygame.Rect(track.x, thumb_y, track.w, thumb_h),
                             border_radius=2)

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
        # Right column splits into Kingdom Production, Loot Inbox, and the
        # Skills/Level panel below.
        vault_h = max(140, int(content_h * 0.22))
        loot_h = max(128, int(content_h * 0.18))
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
            'loot_h': loot_h,
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
        self._loot_gained_rect = None
        self._loot_lost_rect = None
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
                                    'badge', 'Kingdom Badge')
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
        loot_y = vault_rect.bottom + gap_v
        loot_rect = pygame.Rect(right_x, loot_y, right_w, layout['loot_h'])
        self._draw_loot_inbox_panel(loot_rect)
        skills_y = loot_rect.bottom + gap_v
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
