# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Responsive Collection card details, sell, and suit-conversion workshop."""

from __future__ import annotations

import pygame

from config import settings


_PANEL_BG = (22, 22, 28)
_PANEL_INNER = (34, 32, 35)
_PANEL_BORDER = (164, 143, 98)
_SUBPANEL_BG = (12, 14, 18)
_SUBPANEL_BORDER = (92, 88, 78)
_TEXT = (236, 229, 211)
_MUTED = (178, 170, 151)
_FAINT = (126, 120, 108)
_GOLD = (250, 221, 0)
_GOLD_SOFT = (236, 205, 119)
_GOOD = (137, 214, 154)
_WARN = (255, 181, 112)
_DANGER = (244, 126, 108)

# Source card art is 102x149; width / height.
_CARD_ASPECT = 102 / 149


_ALPHA_RECT_CACHE = {}


def _blit_alpha_rect(window, rect, color, radius):
    """Blit a truly translucent rounded rect (draw.rect ignores alpha)."""
    key = (rect.w, rect.h, color, radius)
    surf = _ALPHA_RECT_CACHE.get(key)
    if surf is None:
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, color, surf.get_rect(), border_radius=radius)
        _ALPHA_RECT_CACHE[key] = surf
    window.blit(surf, rect.topleft)


def _fit_text(font, text, max_width):
    """Ellipsize *text* to one rendered line."""
    if font.size(text)[0] <= max_width:
        return text
    suffix = '…'
    available = max(1, max_width - font.size(suffix)[0])
    value = text
    while value and font.size(value)[0] > available:
        value = value[:-1]
    return value.rstrip() + suffix


def _wrap_text(font, text, max_width, max_lines=None):
    lines = []
    for paragraph in str(text or '').split('\n'):
        if not paragraph:
            lines.append('')
            continue
        words = paragraph.split()
        current = []
        for word in words:
            candidate = ' '.join(current + [word])
            if not current or font.size(candidate)[0] <= max_width:
                current.append(word)
            else:
                lines.append(' '.join(current))
                current = [word]
        if current:
            lines.append(' '.join(current))
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _fit_text(font, lines[-1], max_width)
        if not lines[-1].endswith('…'):
            lines[-1] = _fit_text(font, lines[-1] + '…', max_width)
    return lines


class _WorkshopButton:
    """Programmatic workshop button with a touch-sized hit target."""

    def __init__(self, window, rect, text, action, kind='secondary',
                 disabled=False):
        self.window = window
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.kind = kind
        self.disabled = disabled
        self.hovered = False
        self.clicked = False
        self.font = settings.get_font(settings.FS_BODY, bold=True)

    def hit_rect(self):
        min_size = getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0
        hit = self.rect.inflate(
            max(0, min_size - self.rect.w),
            max(0, min_size - self.rect.h),
        )
        hit.clamp_ip(pygame.Rect(
            0, 0, settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        return hit

    def collide(self, pos):
        return not self.disabled and self.hit_rect().collidepoint(pos)

    def update(self):
        self.hovered = self.collide(pygame.mouse.get_pos())
        self.clicked = False

    def draw(self):
        self.update()
        if self.disabled:
            bg = (31, 31, 35)
            border = (76, 72, 65)
            text_color = (112, 108, 100)
        elif self.kind == 'primary':
            bg = ((105, 75, 28) if self.hovered
                  else (76, 56, 26))
            border = ((255, 231, 126) if self.hovered
                      else (207, 171, 86))
            text_color = (255, 247, 218)
        elif self.kind == 'danger':
            bg = ((116, 52, 38) if self.hovered
                  else (79, 42, 35))
            border = ((255, 171, 140) if self.hovered
                      else (187, 112, 91))
            text_color = (255, 237, 225)
        else:
            bg = ((55, 51, 45) if self.hovered
                  else (38, 37, 40))
            border = ((211, 192, 146) if self.hovered
                      else (119, 109, 90))
            text_color = _TEXT

        shadow = self.rect.move(0, max(2, self.rect.h // 15))
        _blit_alpha_rect(self.window, shadow, (0, 0, 0, 105), 8)
        pygame.draw.rect(
            self.window, bg, self.rect, border_radius=8)
        pygame.draw.rect(
            self.window, border, self.rect, 2 if self.hovered else 1,
            border_radius=8)
        if not self.disabled and self.kind in {'primary', 'danger'}:
            pygame.draw.line(
                self.window, (238, 207, 144),
                (self.rect.x + 8, self.rect.y + 4),
                (self.rect.right - 8, self.rect.y + 4), 1)

        label = _fit_text(self.font, self.text, self.rect.w - 14)
        text = self.font.render(label, True, text_color)
        self.window.blit(text, text.get_rect(center=self.rect.center))


class CardWorkshopDialogue:
    """One stable modal for card information and reversible copy actions."""

    VIEW_DETAILS = 'details'
    VIEW_SELL = 'sell'
    VIEW_CONVERT = 'convert'

    def __init__(
            self, window, suit, rank, card_surfaces, uses, qty, locked,
            unit_price, tier_label, pack_label, category_label,
            stock_by_suit=None,
            same_color_ratio=2, different_color_ratio=4,
            red_suits=('Hearts', 'Diamonds'),
            black_suits=('Clubs', 'Spades'), start_view='details',
            tier_color=None):
        self.window = window
        self.suit = suit
        self.rank = rank
        self.card_surfaces = dict(card_surfaces or {})
        self.stock_by_suit = dict(stock_by_suit or {})
        self.uses = uses or {
            'figures': [], 'spells': [], 'battle_moves': []}
        self.qty = max(0, int(qty or 0))
        self.locked = max(0, int(locked or 0))
        self.free = max(0, self.qty - self.locked)
        self.unit_price = max(0, int(unit_price or 0))
        self.tier_label = tier_label
        self.pack_label = pack_label
        self.category_label = category_label
        self.same_color_ratio = same_color_ratio
        self.different_color_ratio = different_color_ratio
        self.red_suits = tuple(red_suits)
        self.black_suits = tuple(black_suits)
        self.tier_color = tuple(tier_color or _GOLD_SOFT)[:3]
        self._created_at = pygame.time.get_ticks()

        self.title = f'{suit} {rank}'
        self.message = (
            f'{tier_label} {pack_label} Card · {category_label}\n'
            f'{self.qty} owned · {self.free} free · {self.locked} in use')
        self.message_after_images = None
        source = self.card_surfaces.get(suit)
        self._lead_items = [('surface', source)] if source else []
        self.image_groups = [
            {'title': 'Figures', 'count': len(self.uses.get('figures', []))},
            {'title': 'Spells', 'count': len(self.uses.get('spells', []))},
            {'title': 'Tactics',
             'count': len(self.uses.get('battle_moves', []))},
        ]

        self.sell_qty = 1 if self.free else 0
        self.convert_qty = 1
        self.target_suit = self._default_target_suit()
        self.view = self.VIEW_DETAILS
        self.buttons = []
        self.actions = []
        self._button_by_action = {}
        self._tooltip_entries = []
        self._scaled_cards = {}
        self._control_rects = {}
        self._target_rects = {}
        self._flow_rects = {}
        self._notice = ''
        self._layout_key = None

        self._build_metrics()
        self.set_view(start_view)

    # ── public state -------------------------------------------------

    @property
    def selected_ratio(self):
        return self._ratio_for(self.target_suit)

    @property
    def convert_max(self):
        ratio = self.selected_ratio
        return self.free // ratio if ratio else 0

    @property
    def consumed_qty(self):
        return self.selected_ratio * self.convert_qty

    def set_view(self, view):
        if view not in {
                self.VIEW_DETAILS, self.VIEW_SELL, self.VIEW_CONVERT}:
            view = self.VIEW_DETAILS
        self.view = view
        self._notice = ''
        if view == self.VIEW_SELL:
            self.sell_qty = min(max(1, self.sell_qty), self.free) if self.free else 0
        elif view == self.VIEW_CONVERT:
            if not self.target_suit:
                self.target_suit = self._default_target_suit()
            if self.convert_max:
                self.convert_qty = min(
                    max(1, self.convert_qty), self.convert_max)
            else:
                self.convert_qty = 0
                self._notice = (
                    f'Need {self.selected_ratio} free copies to create one '
                    f'{self.target_suit} card; you have {self.free}.')
        self._layout()

    def get_tooltip(self, pos):
        for entry in self._tooltip_entries:
            if entry['rect'].collidepoint(pos):
                return entry['tooltip']
        return ''

    def update(self, events):
        self._layout()
        if pygame.time.get_ticks() - self._created_at < 200:
            return None

        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.view == self.VIEW_DETAILS:
                        return 'close'
                    self.set_view(self.VIEW_DETAILS)
                    return None
                if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    delta = -1 if event.key == pygame.K_LEFT else 1
                    self._change_quantity(delta)
                    return None
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    action = ('sell' if self.view == self.VIEW_SELL
                              else 'convert' if self.view == self.VIEW_CONVERT
                              else None)
                    button = self._button_by_action.get(action)
                    if button is not None and not button.disabled:
                        self._play_click()
                        return action
                    return None
            if (event.type != pygame.MOUSEBUTTONUP
                    or getattr(event, 'button', 0) != 1):
                continue
            pos = event.pos
            if not self.rect.collidepoint(pos):
                return 'close'
            if self._close_rect.collidepoint(pos):
                return 'close'

            if self.view == self.VIEW_CONVERT:
                for target, rect in self._target_rects.items():
                    if rect.collidepoint(pos):
                        cap = self._max_for_target(target)
                        if cap < 1:
                            ratio = self._ratio_for(target)
                            self._notice = (
                                f'Need {ratio} free copies for {target}; '
                                f'you have {self.free}.')
                            return None
                        self.target_suit = target
                        self.convert_qty = min(
                            max(1, self.convert_qty), cap)
                        self._notice = ''
                        self._layout()
                        self._play_click()
                        return None

            for action, rect in self._control_rects.items():
                if not rect.collidepoint(pos):
                    continue
                if action in {'minus', 'plus', 'max'}:
                    self._handle_quantity_action(action)
                    self._play_click()
                    return None

            for button in self.buttons:
                if not button.collide(pos):
                    continue
                self._play_click()
                if button.action == 'details':
                    self.set_view(self.VIEW_DETAILS)
                    return None
                if button.action == 'sell_view':
                    self.set_view(self.VIEW_SELL)
                    return None
                if button.action == 'convert_view':
                    self.set_view(self.VIEW_CONVERT)
                    return None
                return button.action
        return None

    # ── metrics / layout --------------------------------------------

    def _build_metrics(self):
        sw, sh = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        mobile = bool(getattr(settings, 'TOUCH_TARGET_MIN', 0))
        portrait = sh > sw
        margin = max(10, int(0.025 * min(sw, sh)))
        if portrait:
            width = min(sw - margin * 2, int(0.94 * sw))
            height = min(sh - margin * 2, int(0.92 * sh))
        elif mobile:
            width = min(sw - margin * 2, int(0.86 * sw))
            height = min(sh - margin * 2, int(0.90 * sh))
        else:
            width = min(sw - margin * 2, int(0.64 * sw))
            height = min(sh - margin * 2, int(0.80 * sh))
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (sw // 2, sh // 2)
        self._portrait = portrait
        self._wide = width >= 600 and not portrait

        self._pad_x = max(14, int(0.018 * sw))
        self._pad_y = max(10, int(0.014 * sh))
        self._header_h = max(
            52, settings.FS_SUBTITLE + settings.FS_SMALL + self._pad_y)
        self._chip_h = max(30, settings.FS_SMALL + 12)
        touch_h = getattr(settings, 'TOUCH_TARGET_MIN', 0) or 0
        self._button_h = max(44, touch_h, int(0.060 * sh))
        self._footer_h = self._button_h + self._pad_y * 2

        self._title_font = settings.get_font(settings.FS_SUBTITLE, bold=True)
        self._subtitle_font = settings.get_font(settings.FS_SMALL)
        self._heading_font = settings.get_font(settings.FS_HEADING, bold=True)
        self._body_font = settings.get_font(settings.FS_BODY)
        self._body_bold_font = settings.get_font(settings.FS_BODY, bold=True)
        self._small_font = settings.get_font(settings.FS_SMALL)
        self._small_bold_font = settings.get_font(settings.FS_SMALL, bold=True)
        self._tiny_font = settings.get_font(
            max(11, int(settings.FS_TINY * 0.84)))
        self._value_font = settings.get_font(
            max(settings.FS_HEADING, int(settings.FS_TITLE * 0.95)), bold=True)

        close_size = max(
            30, getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0,
            self._title_font.get_height() + 10)
        self._close_rect = pygame.Rect(
            self.rect.right - self._pad_x - close_size,
            self.rect.y + self._pad_y,
            close_size, close_size)
        self._layout()

    def _layout(self):
        # Geometry only depends on this signature; skip redundant rebuilds
        # (draw/update call _layout every frame).
        key = (self.view, self.rect.size, self.sell_qty, self.convert_qty,
               self.target_suit, self._notice)
        if key == self._layout_key:
            return
        self._layout_key = key
        content_x = self.rect.x + self._pad_x
        content_w = self.rect.w - self._pad_x * 2
        header_bottom = self.rect.y + self._header_h
        chip_gap = max(6, int(0.006 * settings.SCREEN_WIDTH))
        chip_rows = 2 if content_w < 560 else 1
        self._chip_rows = chip_rows
        self._stock_rect = pygame.Rect(
            content_x, header_bottom + self._pad_y // 2,
            content_w,
            chip_rows * self._chip_h + (chip_rows - 1) * chip_gap)
        footer_top = self.rect.bottom - self._footer_h
        self._footer_rect = pygame.Rect(
            content_x, footer_top, content_w, self._footer_h)
        body_top = self._stock_rect.bottom + self._pad_y
        self._body_rect = pygame.Rect(
            content_x, body_top, content_w,
            max(1, footer_top - body_top))
        self._layout_footer_buttons()
        self._layout_controls()

    def _layout_footer_buttons(self):
        gap = max(8, int(0.010 * settings.SCREEN_WIDTH))
        top = self._footer_rect.y + self._pad_y
        available_w = self._footer_rect.w
        buttons = []
        if self.view == self.VIEW_DETAILS:
            actions = [
                ('Sell copies', 'sell_view', 'secondary', self.free <= 0),
                ('Convert suit', 'convert_view', 'primary',
                 self.free < self.same_color_ratio),
            ]
            if self._wide:
                actions.append(('Close', 'close', 'secondary', False))
            count = len(actions)
            width = (available_w - gap * (count - 1)) // count
            for index, (text, action, kind, disabled) in enumerate(actions):
                rect = pygame.Rect(
                    self._footer_rect.x + index * (width + gap),
                    top, width, self._button_h)
                buttons.append(_WorkshopButton(
                    self.window, rect, text, action, kind, disabled))
        else:
            back_w = max(
                int(0.27 * available_w),
                getattr(settings, 'TOUCH_TARGET_MIN', 0) or 0)
            primary_w = available_w - gap - back_w
            back_rect = pygame.Rect(
                self._footer_rect.x, top, back_w, self._button_h)
            if self.view == self.VIEW_SELL:
                total = self.sell_qty * self.unit_price
                disabled = self.sell_qty < 1
                text = (f'Sell {self.sell_qty} for {total}g'
                        if not disabled else 'No free copies to sell')
                action = 'sell'
                kind = 'danger'
            else:
                disabled = self.convert_max < 1
                text = (f'Convert {self.consumed_qty} into {self.convert_qty}'
                        if not disabled else 'Not enough free copies')
                action = 'convert'
                kind = 'primary'
            primary_rect = pygame.Rect(
                back_rect.right + gap, top, primary_w, self._button_h)
            buttons = [
                _WorkshopButton(
                    self.window, back_rect, 'Back', 'details', 'secondary'),
                _WorkshopButton(
                    self.window, primary_rect, text, action, kind, disabled),
            ]
        self.buttons = buttons
        self.actions = [button.action for button in buttons]
        self._button_by_action = {
            button.action: button for button in buttons}

    def _layout_controls(self):
        self._control_rects = {}
        self._target_rects = {}
        self._flow_rects = {}
        if self.view not in {self.VIEW_SELL, self.VIEW_CONVERT}:
            return

        # Flow the control column top-down instead of positioning rows at
        # fixed fractions of the area; proportional offsets overlap on short
        # portrait areas and leave voids on tall desktop ones.
        _visual_area, area = self._transaction_areas(self.view)
        gap = max(6, self._pad_y // 2)
        tiny_h = self._tiny_font.get_height()
        heading_h = self._heading_font.get_height()
        # The quantity row renders its label just above the qty box.
        label_h = self._small_bold_font.get_height() + 4

        control_h = max(
            38, getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0,
            int(0.050 * settings.SCREEN_HEIGHT))
        small_w = max(control_h, int(0.055 * settings.SCREEN_WIDTH))
        max_w = max(int(1.45 * small_w), self._small_font.size('Max')[0] + 18)
        qty_w = max(int(1.20 * small_w), self._body_font.size('99')[0] + 22)
        btn_gap = max(6, int(0.006 * settings.SCREEN_WIDTH))
        total_w = small_w * 2 + qty_w + max_w + btn_gap * 3

        if self.view == self.VIEW_SELL:
            expl_h = len(_wrap_text(
                self._tiny_font, self._sell_explanation(), area.w,
                max_lines=2)) * (tiny_h + 1)
            panel_min = max(
                self._value_font.get_height() + 20,
                8 + self._small_font.get_height() + 3 + tiny_h
                + gap + tiny_h + 8)
            rows = [heading_h + 4, expl_h + gap, label_h + control_h + gap]
        else:
            target_h = max(
                44, getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0,
                self._small_bold_font.get_height() + tiny_h + 14)
            panel_min = 10 + 3 * (tiny_h + 2) + 10
            rows = [heading_h + gap, target_h + gap,
                    label_h + control_h + gap]

        # The result panel absorbs a bounded share of any spare height and
        # the whole stack floats toward the vertical centre of the area.
        stack_min = sum(rows) + panel_min
        spare = max(0, area.h - stack_min)
        panel_h = panel_min + min(spare, int(0.20 * area.h))
        spare = max(0, area.h - sum(rows) - panel_h)
        top = area.y + min(spare // 2, int(0.15 * area.h))

        self._flow_rects['heading'] = pygame.Rect(
            area.x, top, area.w, heading_h)
        cursor = top + rows[0]
        if self.view == self.VIEW_SELL:
            self._flow_rects['explanation'] = pygame.Rect(
                area.x, cursor, area.w, expl_h)
        else:
            targets = [suit for suit in settings.SUITS if suit != self.suit]
            name_w = max(
                self._small_bold_font.size(target)[0]
                for target in targets) + 16
            target_w = (
                area.w - btn_gap * (len(targets) - 1)) // len(targets)
            target_w = min(
                target_w,
                max(name_w, 100, int(0.115 * settings.SCREEN_WIDTH)))
            total_target_w = (
                target_w * len(targets) + btn_gap * (len(targets) - 1))
            target_x = area.centerx - total_target_w // 2
            for index, target in enumerate(targets):
                self._target_rects[target] = pygame.Rect(
                    target_x + index * (target_w + btn_gap),
                    cursor, target_w, target_h)
        cursor += rows[1]

        qty_y = min(cursor + label_h, area.bottom - control_h - 8)
        x = area.centerx - total_w // 2
        self._control_rects = {
            'minus': pygame.Rect(x, qty_y, small_w, control_h),
            'qty': pygame.Rect(x + small_w + btn_gap, qty_y, qty_w, control_h),
            'plus': pygame.Rect(
                x + small_w + btn_gap + qty_w + btn_gap,
                qty_y, small_w, control_h),
            'max': pygame.Rect(
                x + small_w + btn_gap + qty_w + btn_gap + small_w + btn_gap,
                qty_y, max_w, control_h),
        }

        panel_top = qty_y + control_h + gap
        self._flow_rects['panel'] = pygame.Rect(
            area.x, panel_top, area.w,
            min(panel_h, max(38, area.bottom - panel_top)))

    # ── drawing ------------------------------------------------------

    def draw(self):
        self._layout()
        self._tooltip_entries = []
        overlay = pygame.Surface(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 158))
        # Painting the drop shadow into the scrim keeps it genuinely
        # translucent; draw.rect on the window would render it opaque.
        shadow = self.rect.inflate(12, 12).move(0, 5)
        pygame.draw.rect(overlay, (0, 0, 0, 216), shadow, border_radius=16)
        self.window.blit(overlay, (0, 0))
        pygame.draw.rect(
            self.window, _PANEL_BG, self.rect, border_radius=14)
        inner = self.rect.inflate(-4, -4)
        pygame.draw.rect(
            self.window, _PANEL_INNER, inner, border_radius=12)
        pygame.draw.rect(
            self.window, _PANEL_BORDER, self.rect, 1, border_radius=14)
        pygame.draw.line(
            self.window, self.tier_color,
            (self.rect.x + self._pad_x, self.rect.y + self._header_h),
            (self.rect.right - self._pad_x, self.rect.y + self._header_h),
            2)

        self._draw_header()
        self._draw_stock_chips()
        if self.view == self.VIEW_DETAILS:
            self._draw_details()
        elif self.view == self.VIEW_SELL:
            self._draw_sell()
        else:
            self._draw_convert()
        self._draw_footer()

    def _draw_header(self):
        x = self.rect.x + self._pad_x
        y = self.rect.y + self._pad_y
        title = self._title_font.render(self.title, True, _GOLD)
        self.window.blit(title, (x, y))
        subtitle_text = (
            f'{self.tier_label} · {self.pack_label} · '
            f'{self.category_label}')
        subtitle = self._subtitle_font.render(
            _fit_text(
                self._subtitle_font, subtitle_text,
                self._close_rect.x - x - 12),
            True, _MUTED)
        self.window.blit(subtitle, (x, y + title.get_height() + 1))

        hovered = self._close_rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(
            self.window,
            (73, 52, 36) if hovered else (42, 39, 39),
            self._close_rect, border_radius=8)
        pygame.draw.rect(
            self.window,
            (224, 190, 128) if hovered else (117, 104, 83),
            self._close_rect, 1, border_radius=8)
        close = self._title_font.render('×', True, _TEXT)
        self.window.blit(close, close.get_rect(center=self._close_rect.center))

    def _draw_stock_chips(self):
        values = [
            ('Owned', str(self.qty), _TEXT),
            ('Free', str(self.free), _GOOD if self.free else _WARN),
            ('In use', str(self.locked), (169, 205, 255)),
            ('Sells for', f'{self.unit_price}g', _GOLD_SOFT),
        ]
        gap = max(6, int(0.006 * settings.SCREEN_WIDTH))
        columns = 2 if self._chip_rows == 2 else 4
        chip_w = (
            self._stock_rect.w - gap * (columns - 1)
        ) // columns
        for index, (label, value, color) in enumerate(values):
            row = index // columns
            col = index % columns
            rect = pygame.Rect(
                self._stock_rect.x + col * (chip_w + gap),
                self._stock_rect.y + row * (self._chip_h + gap),
                chip_w, self._chip_h)
            pygame.draw.rect(
                self.window, (18, 19, 23), rect, border_radius=7)
            pygame.draw.rect(
                self.window, (83, 79, 69), rect, 1, border_radius=7)
            label_surf = self._small_font.render(f'{label} ', True, _MUTED)
            value_surf = self._small_bold_font.render(value, True, color)
            total_w = label_surf.get_width() + value_surf.get_width()
            tx = rect.centerx - total_w // 2
            self.window.blit(
                label_surf,
                label_surf.get_rect(left=tx, centery=rect.centery))
            self.window.blit(
                value_surf,
                value_surf.get_rect(
                    left=tx + label_surf.get_width(),
                    centery=rect.centery))

    def _draw_details(self):
        if self._wide:
            left_w = max(160, int(self._body_rect.w * 0.24))
            left = pygame.Rect(
                self._body_rect.x, self._body_rect.y,
                left_w, self._body_rect.h)
            right = pygame.Rect(
                left.right + self._pad_x, self._body_rect.y,
                self._body_rect.right - left.right - self._pad_x,
                self._body_rect.h)
            self._draw_card_context(left, compact=False)
            self._draw_use_panels(right)
            return

        card_h = min(
            int(self._body_rect.h * 0.28),
            int(0.17 * settings.SCREEN_HEIGHT))
        card_area = pygame.Rect(
            self._body_rect.x, self._body_rect.y,
            self._body_rect.w, max(110, card_h))
        self._draw_card_context(card_area, compact=True)
        uses = pygame.Rect(
            self._body_rect.x,
            card_area.bottom + self._pad_y // 2,
            self._body_rect.w,
            max(1, self._body_rect.bottom - card_area.bottom
                - self._pad_y // 2))
        self._draw_use_panels(uses)

    def _draw_card_context(self, rect, compact=False):
        pygame.draw.rect(
            self.window, _SUBPANEL_BG, rect, border_radius=10)
        pygame.draw.rect(
            self.window, _SUBPANEL_BORDER, rect, 1, border_radius=10)
        source = self.card_surfaces.get(self.suit)
        if compact:
            card_h = min(
                rect.h - self._pad_y * 2, int(0.22 * settings.SCREEN_HEIGHT))
            card_w = min(int(rect.w * 0.22), int(card_h * _CARD_ASPECT))
            card_rect = pygame.Rect(0, 0, card_w, card_h)
            card_rect.midleft = (
                rect.x + self._pad_x + card_w // 2, rect.centery)
            self._draw_card_surface(source, card_rect, border=True)
            text_x = card_rect.right + self._pad_x
            text_w = rect.right - text_x - self._pad_x
            heading = self._heading_font.render(
                'Strategic stock', True, _TEXT)
            self.window.blit(heading, (text_x, rect.y + self._pad_y))
            summary = (
                f'{self.free} free copies are ready for recipes, '
                'spells, tactics, or new defences.'
                if self.free else
                'Every owned copy is currently committed in play.')
            self._draw_wrapped(
                summary, self._small_font, _MUTED,
                pygame.Rect(
                    text_x, rect.y + self._pad_y + heading.get_height() + 4,
                    text_w, rect.h - heading.get_height() - self._pad_y * 2),
                max_lines=3)
            return

        label_h = self._small_bold_font.get_height()
        summary_h = self._tiny_font.get_height()
        card_h = min(
            int(rect.h * 0.56),
            int(0.30 * settings.SCREEN_HEIGHT),
            rect.h - label_h - summary_h - self._pad_y * 3)
        card_w = min(rect.w - self._pad_x * 2, int(card_h * _CARD_ASPECT))
        group_h = card_h + self._pad_y // 2 + label_h + 3 + summary_h
        top = rect.y + max(self._pad_y, (rect.h - group_h) // 2)
        card_box = pygame.Rect(0, 0, card_w, card_h)
        card_box.midtop = (rect.centerx, top)
        self._draw_card_surface(source, card_box, border=True)
        label = self._small_bold_font.render(
            'Strategic stock', True, _TEXT)
        label_rect = label.get_rect(
            centerx=rect.centerx,
            top=card_box.bottom + self._pad_y // 2)
        self.window.blit(label, label_rect)
        summary = (
            f'{self.free} ready · {self.locked} in use'
            if self.qty else 'Not currently owned')
        summary_surf = self._tiny_font.render(
            _fit_text(self._tiny_font, summary, rect.w - self._pad_x * 2),
            True, _MUTED)
        self.window.blit(
            summary_surf, summary_surf.get_rect(
                centerx=rect.centerx, top=label_rect.bottom + 3))

    def _draw_use_panels(self, rect):
        groups = [
            ('Figures', 'figure', self.uses.get('figures', [])),
            ('Spells', 'magic', self.uses.get('spells', [])),
            ('Tactics', 'dices', self.uses.get('battle_moves', [])),
        ]
        title = self._heading_font.render('Used by', True, _TEXT)
        self.window.blit(title, (rect.x, rect.y))
        top = rect.y + title.get_height() + max(4, self._pad_y // 3)
        gap = max(6, int(0.008 * settings.SCREEN_HEIGHT))
        panel_h = max(1, (rect.bottom - top - gap * 2) // 3)
        for index, (label, icon_name, entries) in enumerate(groups):
            panel = pygame.Rect(
                rect.x, top + index * (panel_h + gap),
                rect.w, panel_h)
            self._draw_use_panel(panel, label, icon_name, entries)

    def _draw_use_panel(self, rect, label, icon_name, entries):
        pygame.draw.rect(
            self.window, _SUBPANEL_BG, rect, border_radius=9)
        pygame.draw.rect(
            self.window, _SUBPANEL_BORDER, rect, 1, border_radius=9)
        pad = max(8, self._pad_x // 2)
        icon_size = min(
            rect.h - pad * 2,
            max(24, int(0.046 * settings.SCREEN_HEIGHT)))
        header_icon = settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT.get(icon_name)
        x = rect.x + pad
        if header_icon is not None and icon_size > 0:
            icon = pygame.transform.smoothscale(
                header_icon, (icon_size, icon_size))
            self.window.blit(icon, (x, rect.y + pad))
            x += icon_size + max(5, pad // 2)
        heading = self._small_bold_font.render(
            f'{label} · {len(entries)}', True, _TEXT)
        heading_pos = (x, rect.y + pad)
        self.window.blit(heading, heading_pos)

        valid = [
            (name, icon, desc)
            for name, icon, desc in entries
            if icon is not None]
        max_icons = min(5, len(valid))
        icon_gap = max(4, int(0.004 * settings.SCREEN_WIDTH))
        item_size = min(
            max(28, int(rect.h * 0.72)),
            max(28, int(0.088 * settings.SCREEN_HEIGHT)),
            rect.h - pad * 2)
        if max_icons:
            # Never let the icon strip crowd out the recipe-name text.
            width_cap = (
                int(rect.w * 0.46) - (max_icons - 1) * icon_gap) // max_icons
            item_size = max(24, min(item_size, width_cap))
        icons_w = (
            max_icons * item_size + max(0, max_icons - 1) * icon_gap)
        icons_x = rect.right - pad - icons_w
        names_w = max(40, icons_x - x - pad)
        names = ', '.join(name for name, _icon, _desc in entries)
        note = names if names else f'No {label.lower()} use this card'
        note_surf = self._tiny_font.render(
            _fit_text(self._tiny_font, note, names_w), True,
            _MUTED if names else _FAINT)
        # Keep the name list adjacent to its heading; bottom-anchoring
        # strands it across an empty middle on tall desktop panels.
        note_y = min(
            rect.bottom - pad - note_surf.get_height(),
            heading_pos[1] + heading.get_height() + 5)
        self.window.blit(note_surf, (x, note_y))

        icon_y = rect.centery - item_size // 2
        for index, (name, icon, desc) in enumerate(valid[:max_icons]):
            item_rect = pygame.Rect(
                icons_x + index * (item_size + icon_gap),
                icon_y, item_size, item_size)
            self._draw_icon_item(icon, item_rect)
            self._tooltip_entries.append({
                'rect': item_rect,
                'tooltip': f'{name}\n{desc}' if desc else name,
            })

    @staticmethod
    def _sell_explanation():
        return ('Only free copies can be sold. '
                'Cards in use stay protected.')

    def _protected_note(self):
        if self.locked == 1:
            return '1 in-use copy stays protected', (169, 205, 255)
        if self.locked:
            return (f'{self.locked} in-use copies stay protected',
                    (169, 205, 255))
        return 'No copies are locked in play', _FAINT

    def _draw_sell(self):
        visual, controls = self._transaction_areas(self.VIEW_SELL)
        self._draw_transaction_card(
            visual, self.suit, 'Free stock only',
            horizontal=not self._wide)
        self._draw_sell_controls(controls)

    def _draw_sell_controls(self, rect):
        flow = self._flow_rects
        heading = self._heading_font.render(
            'Choose copies to sell', True, _TEXT)
        self.window.blit(heading, flow['heading'].topleft)
        self._draw_wrapped(
            self._sell_explanation(), self._tiny_font, _MUTED,
            flow['explanation'], max_lines=2)
        self._draw_quantity_controls(
            label='Quantity', value=self.sell_qty,
            maximum=self.free)

        payout = flow['panel']
        pygame.draw.rect(
            self.window, (48, 38, 20), payout, border_radius=9)
        pygame.draw.rect(
            self.window, (151, 119, 57), payout, 1, border_radius=9)
        total = self.sell_qty * self.unit_price
        label = self._small_font.render('You receive', True, _MUTED)
        value = self._value_font.render(f'+{total}g', True, _GOLD)
        calculation = self._tiny_font.render(
            f'{self.unit_price}g each × {self.sell_qty}',
            True, _GOLD_SOFT)
        # Balance the receipt block above the bottom outcome line so a
        # roomy panel does not read as top-anchored text in a void.
        bottom_zone = self._tiny_font.get_height() + 16
        block_h = label.get_height() + 3 + calculation.get_height()
        block_y = payout.y + max(8, (payout.h - bottom_zone - block_h) // 2)
        self.window.blit(label, (payout.x + 12, block_y))
        self.window.blit(
            calculation,
            (payout.x + 12, block_y + label.get_height() + 3))
        value_rect = value.get_rect(
            right=payout.right - 12,
            centery=block_y + block_h // 2)
        self.window.blit(value, value_rect)
        after = max(0, self.free - self.sell_qty)
        outcome_w = max(40, value_rect.left - payout.x - 26)
        outcome_y = payout.bottom - self._tiny_font.get_height() - 8
        if after:
            self._draw_stock_change(
                'Free copies', self.free, after, _GOOD,
                (payout.x + 12, outcome_y), outcome_w)
        else:
            outcome_surf = self._tiny_font.render(
                _fit_text(
                    self._tiny_font,
                    'Leaves no free copy for new recipes or defences',
                    outcome_w),
                True, _WARN)
            self.window.blit(outcome_surf, (payout.x + 12, outcome_y))

    def _draw_stock_change(self, prefix, before, after, color, pos,
                           max_width, align='left'):
        """Draw '<prefix> <before> -> <after>' with a drawn arrow glyph.

        The UI font has no arrow codepoint, so the arrow is drawn. *pos* is
        the top-left corner, or the top-centre when *align* is 'center'.
        """
        font = self._tiny_font
        lead = f'{prefix}  {before}' if prefix else str(before)
        lead_surf = font.render(lead, True, color)
        tail_surf = font.render(str(after), True, color)
        line_h = font.get_height()
        arrow_w = max(16, int(line_h * 1.2))
        total = lead_surf.get_width() + arrow_w + tail_surf.get_width()
        if prefix and total > max_width:
            # Drop the prefix rather than clipping the numbers.
            self._draw_stock_change(
                '', before, after, color, pos, max_width, align)
            return
        x = pos[0] - (total // 2 if align == 'center' else 0)
        y = pos[1]
        self.window.blit(lead_surf, (x, y))
        ax = x + lead_surf.get_width() + 5
        ay = y + line_h // 2
        tip = x + lead_surf.get_width() + arrow_w - 5
        pygame.draw.line(self.window, color, (ax, ay), (tip - 3, ay), 1)
        pygame.draw.polygon(
            self.window, color,
            [(tip, ay), (tip - 5, ay - 3), (tip - 5, ay + 3)])
        self.window.blit(
            tail_surf, (x + lead_surf.get_width() + arrow_w, y))

    def _draw_convert(self):
        visual, controls = self._transaction_areas(self.VIEW_CONVERT)
        self._draw_conversion_visual(visual, horizontal=not self._wide)
        self._draw_convert_controls(controls)

    def _draw_conversion_visual(self, rect, horizontal=False):
        pygame.draw.rect(
            self.window, _SUBPANEL_BG, rect, border_radius=10)
        pygame.draw.rect(
            self.window, _SUBPANEL_BORDER, rect, 1, border_radius=10)
        ratio = self.selected_ratio
        if horizontal:
            card_h = rect.h - self._pad_y * 2
            top = rect.y + self._pad_y
        else:
            label_h = self._tiny_font.get_height()
            card_h = min(
                int(rect.h * 0.62),
                int(0.18 * settings.SCREEN_HEIGHT),
                rect.h - label_h - self._pad_y * 3)
            group_h = card_h + self._pad_y // 2 + label_h
            top = rect.y + max(self._pad_y, (rect.h - group_h) // 2)
        source_box = pygame.Rect(
            rect.x + self._pad_x, top,
            int(rect.w * 0.29), card_h)
        target_box = pygame.Rect(
            rect.right - self._pad_x - int(rect.w * 0.29), top,
            int(rect.w * 0.29), card_h)
        self._draw_card_surface(
            self.card_surfaces.get(self.suit), source_box, border=True)
        self._draw_card_surface(
            self.card_surfaces.get(self.target_suit), target_box, border=True)

        arrow_center = (
            (source_box.right + target_box.left) // 2,
            source_box.centery)
        arrow_half = max(10, int(0.018 * settings.SCREEN_WIDTH))
        pygame.draw.line(
            self.window, _GOLD,
            (arrow_center[0] - arrow_half, arrow_center[1]),
            (arrow_center[0] + arrow_half, arrow_center[1]), 2)
        pygame.draw.polygon(
            self.window, _GOLD,
            [
                (arrow_center[0] + arrow_half, arrow_center[1]),
                (arrow_center[0] + arrow_half - 7, arrow_center[1] - 5),
                (arrow_center[0] + arrow_half - 7, arrow_center[1] + 5),
            ])
        ratio_text = self._small_bold_font.render(
            f'{ratio}:1', True, _GOLD_SOFT)
        self.window.blit(
            ratio_text, ratio_text.get_rect(
                centerx=arrow_center[0],
                top=arrow_center[1] + 7))

        if not horizontal:
            source_label = self._tiny_font.render(
                f'Consume {self.consumed_qty}', True, _WARN)
            target_label = self._tiny_font.render(
                f'Create {self.convert_qty}', True, _GOOD)
            label_y = min(
                rect.bottom - source_label.get_height() - 8,
                source_box.bottom + self._pad_y // 2)
            self.window.blit(
                source_label, source_label.get_rect(
                    centerx=source_box.centerx, top=label_y))
            self.window.blit(
                target_label, target_label.get_rect(
                    centerx=target_box.centerx, top=label_y))

    def _draw_convert_controls(self, rect):
        flow = self._flow_rects
        heading = self._heading_font.render(
            'Choose the new suit', True, _TEXT)
        self.window.blit(heading, flow['heading'].topleft)
        for target, target_rect in self._target_rects.items():
            self._draw_target_button(target, target_rect)

        self._draw_quantity_controls(
            label='Cards created', value=self.convert_qty,
            maximum=self.convert_max)
        outcome = flow['panel']
        pygame.draw.rect(
            self.window, (18, 25, 24), outcome, border_radius=9)
        pygame.draw.rect(
            self.window, (79, 125, 100), outcome, 1, border_radius=9)
        source_after = max(0, self.free - self.consumed_qty)
        target_total, target_locked = self.stock_by_suit.get(
            self.target_suit, (0, 0))
        target_free = max(0, int(target_total or 0) - int(target_locked or 0))
        if not self._notice and outcome.h >= 120:
            self._draw_expanded_conversion_outcome(
                outcome, source_after, target_free)
            return
        line_h = self._tiny_font.get_height() + 2
        if self._notice:
            result_lines = _wrap_text(
                self._tiny_font, self._notice,
                outcome.w - 20, max_lines=2)
            total_h = len(result_lines) * line_h
            y = outcome.centery - total_h // 2
            for line in result_lines:
                surf = self._tiny_font.render(line, True, _WARN)
                self.window.blit(
                    surf, surf.get_rect(centerx=outcome.centerx, top=y))
                y += line_h
            return
        changes = [
            (f'{self.suit} free', self.free, source_after),
            (f'{self.target_suit} free', target_free,
             target_free + self.convert_qty),
        ]
        rows = len(changes) + (1 if source_after == 0 else 0)
        y = outcome.centery - (rows * line_h) // 2
        for prefix, before, after in changes:
            self._draw_stock_change(
                prefix, before, after, _GOOD,
                (outcome.centerx, y), outcome.w - 20, align='center')
            y += line_h
        if source_after == 0:
            warn = self._tiny_font.render(
                _fit_text(
                    self._tiny_font,
                    f'Leaves no free {self.suit} copies',
                    outcome.w - 20),
                True, _WARN)
            self.window.blit(
                warn, warn.get_rect(centerx=outcome.centerx, top=y))

    def _draw_expanded_conversion_outcome(
            self, rect, source_after, target_free):
        label = self._small_font.render('After conversion', True, _MUTED)
        self.window.blit(label, (rect.x + 12, rect.y + 8))
        divider_x = rect.centerx
        pygame.draw.line(
            self.window, (74, 93, 83),
            (divider_x, rect.y + 12),
            (divider_x, rect.bottom - 12), 1)

        columns = [
            (
                pygame.Rect(
                    rect.x + 10, rect.y + label.get_height() + 10,
                    rect.w // 2 - 20,
                    rect.h - label.get_height() - 28),
                self.suit, source_after),
            (
                pygame.Rect(
                    rect.centerx + 10, rect.y + label.get_height() + 10,
                    rect.w // 2 - 20,
                    rect.h - label.get_height() - 28),
                self.target_suit, target_free + self.convert_qty),
        ]
        for column, suit, free_after in columns:
            suit_label = self._small_bold_font.render(
                suit, True,
                (235, 96, 96) if suit in self.red_suits
                else (204, 207, 219))
            value = self._body_bold_font.render(
                f'{free_after} free', True,
                _GOOD if free_after else _WARN)
            total_h = suit_label.get_height() + value.get_height() + 3
            top = column.centery - total_h // 2
            self.window.blit(
                suit_label, suit_label.get_rect(
                    centerx=column.centerx, top=top))
            self.window.blit(
                value, value.get_rect(
                    centerx=column.centerx,
                    top=top + suit_label.get_height() + 3))

        if source_after == 0:
            warning = self._tiny_font.render(
                f'Leaves no free {self.suit} copies',
                True, _WARN)
            self.window.blit(
                warning, warning.get_rect(
                    centerx=rect.centerx,
                    bottom=rect.bottom - 7))

    def _draw_transaction_card(
            self, rect, suit, caption, horizontal=False):
        pygame.draw.rect(
            self.window, _SUBPANEL_BG, rect, border_radius=10)
        pygame.draw.rect(
            self.window, _SUBPANEL_BORDER, rect, 1, border_radius=10)
        protected, protected_color = self._protected_note()
        if horizontal:
            card_h = min(
                rect.h - self._pad_y * 2, int(0.22 * settings.SCREEN_HEIGHT))
            card_w = min(int(rect.w * 0.24), int(card_h * _CARD_ASPECT))
            card_box = pygame.Rect(0, 0, card_w, card_h)
            card_box.midleft = (
                rect.x + self._pad_x + card_w // 2, rect.centery)
            self._draw_card_surface(
                self.card_surfaces.get(suit), card_box, border=True)
            text_x = card_box.right + self._pad_x
            text_w = max(40, rect.right - text_x - self._pad_x)
            heading = self._small_bold_font.render(
                _fit_text(self._small_bold_font, caption, text_w),
                True, _TEXT)
            self.window.blit(heading, (text_x, rect.y + self._pad_y))
            self._draw_wrapped(
                protected, self._tiny_font, protected_color,
                pygame.Rect(
                    text_x, rect.y + self._pad_y + heading.get_height() + 4,
                    text_w,
                    max(1, rect.bottom - self._pad_y
                        - (rect.y + self._pad_y + heading.get_height() + 4))),
                max_lines=2)
            return

        caption_h = self._small_bold_font.get_height()
        note_h = self._tiny_font.get_height()
        card_h = min(
            int(rect.h * 0.58),
            int(0.30 * settings.SCREEN_HEIGHT),
            rect.h - caption_h - note_h - self._pad_y * 3)
        card_w = min(rect.w - self._pad_x * 2, int(card_h * _CARD_ASPECT))
        group_h = card_h + self._pad_y // 2 + caption_h + 3 + note_h
        top = rect.y + max(self._pad_y, (rect.h - group_h) // 2)
        card_box = pygame.Rect(0, 0, card_w, card_h)
        card_box.midtop = (rect.centerx, top)
        self._draw_card_surface(
            self.card_surfaces.get(suit), card_box, border=True)
        heading = self._small_bold_font.render(
            _fit_text(self._small_bold_font, caption,
                      rect.w - self._pad_x * 2),
            True, _TEXT)
        heading_rect = heading.get_rect(
            centerx=rect.centerx,
            top=card_box.bottom + self._pad_y // 2)
        self.window.blit(heading, heading_rect)
        detail = self._tiny_font.render(
            _fit_text(self._tiny_font, protected, rect.w - self._pad_x * 2),
            True, protected_color)
        self.window.blit(
            detail, detail.get_rect(
                centerx=rect.centerx, top=heading_rect.bottom + 3))

    def _transaction_areas(self, view):
        if self._wide:
            ratio = 0.39 if view == self.VIEW_SELL else 0.40
            visual = pygame.Rect(
                self._body_rect.x, self._body_rect.y,
                int(self._body_rect.w * ratio), self._body_rect.h)
            controls = pygame.Rect(
                visual.right + self._pad_x, self._body_rect.y,
                self._body_rect.right - visual.right - self._pad_x,
                self._body_rect.h)
            return visual, controls

        height_ratio = 0.30 if view == self.VIEW_SELL else 0.34
        minimum = 100 if view == self.VIEW_SELL else 120
        visual_h = max(minimum, int(self._body_rect.h * height_ratio))
        visual = pygame.Rect(
            self._body_rect.x, self._body_rect.y,
            self._body_rect.w, visual_h)
        controls = pygame.Rect(
            self._body_rect.x, visual.bottom + self._pad_y // 2,
            self._body_rect.w,
            max(1, self._body_rect.bottom - visual.bottom
                - self._pad_y // 2))
        return visual, controls

    def _draw_quantity_controls(self, label, value, maximum):
        rects = self._control_rects
        label_surf = self._small_bold_font.render(label, True, _MUTED)
        self.window.blit(
            label_surf, label_surf.get_rect(
                centerx=rects['qty'].centerx,
                bottom=rects['qty'].top - 4))
        self._draw_step_button(
            rects['minus'], '−', enabled=value > 1)
        self._draw_step_button(
            rects['plus'], '+', enabled=value < maximum)
        self._draw_step_button(
            rects['max'], 'Max', enabled=value < maximum)
        pygame.draw.rect(
            self.window, (13, 14, 18),
            rects['qty'], border_radius=8)
        pygame.draw.rect(
            self.window, (184, 157, 91),
            rects['qty'], 1, border_radius=8)
        qty = self._body_bold_font.render(str(value), True, _GOLD)
        self.window.blit(qty, qty.get_rect(center=rects['qty'].center))

    def _draw_step_button(self, rect, text, enabled=True):
        hovered = enabled and rect.collidepoint(pygame.mouse.get_pos())
        if not enabled:
            bg, border, color = (
                (29, 29, 33), (72, 68, 62), (105, 101, 94))
        elif hovered:
            bg, border, color = (
                (78, 60, 31), (244, 211, 124), (255, 244, 211))
        else:
            bg, border, color = (
                (38, 37, 40), (119, 109, 90), _TEXT)
        pygame.draw.rect(
            self.window, bg, rect, border_radius=8)
        pygame.draw.rect(
            self.window, border, rect, 1, border_radius=8)
        font = self._body_bold_font if len(text) == 1 else self._small_bold_font
        surf = font.render(text, True, color)
        self.window.blit(surf, surf.get_rect(center=rect.center))

    def _draw_target_button(self, target, rect):
        cap = self._max_for_target(target)
        selected = target == self.target_suit
        hovered = cap > 0 and rect.collidepoint(pygame.mouse.get_pos())
        is_red = target in self.red_suits
        accent = (235, 96, 96) if is_red else (204, 207, 219)
        if cap < 1:
            bg, border, color = (
                (29, 29, 33), (70, 67, 62), (106, 101, 94))
        elif selected:
            bg, border, color = (
                (82, 61, 25), _GOLD, (255, 245, 210))
        elif hovered:
            bg, border, color = (
                (52, 47, 39), accent, accent)
        else:
            bg, border, color = (
                (35, 35, 40), (103, 96, 83), accent)
        pygame.draw.rect(
            self.window, bg, rect, border_radius=8)
        pygame.draw.rect(
            self.window, border, rect, 2 if selected else 1,
            border_radius=8)
        name = self._small_bold_font.render(
            _fit_text(self._small_bold_font, target, rect.w - 10),
            True, color)
        detail = (f'{self._ratio_for(target)}:1 · max {cap}' if cap >= 1
                  else f'need {self._ratio_for(target)} free')
        ratio = self._tiny_font.render(
            _fit_text(self._tiny_font, detail, rect.w - 10), True, color)
        total_h = name.get_height() + ratio.get_height()
        top = rect.centery - total_h // 2
        self.window.blit(
            name, name.get_rect(centerx=rect.centerx, top=top))
        self.window.blit(
            ratio, ratio.get_rect(
                centerx=rect.centerx, top=top + name.get_height()))

    def _draw_footer(self):
        pygame.draw.line(
            self.window, (80, 76, 68),
            (self._footer_rect.x, self._footer_rect.y),
            (self._footer_rect.right, self._footer_rect.y), 1)
        for button in self.buttons:
            button.draw()

    def _draw_card_surface(self, surface, bounds, border=False):
        if surface is None or bounds.w <= 0 or bounds.h <= 0:
            return
        sw, sh = surface.get_size()
        scale = min(bounds.w / sw, bounds.h / sh)
        size = (max(1, int(sw * scale)), max(1, int(sh * scale)))
        key = (id(surface), size)
        scaled = self._scaled_cards.get(key)
        if scaled is None:
            scaled = pygame.transform.smoothscale(surface, size)
            self._scaled_cards[key] = scaled
        dest = scaled.get_rect(center=bounds.center)
        if border:
            glow = dest.inflate(8, 8)
            _blit_alpha_rect(
                self.window, glow, (*self.tier_color, 45), 8)
            pygame.draw.rect(
                self.window, self.tier_color,
                glow, 1, border_radius=8)
        self.window.blit(scaled, dest)

    def _draw_icon_item(self, icon, rect):
        if isinstance(icon, pygame.Surface):
            iw, ih = icon.get_size()
            scale = min(rect.w / max(1, iw), rect.h / max(1, ih))
            size = (max(1, int(iw * scale)), max(1, int(ih * scale)))
            scaled = pygame.transform.smoothscale(icon, size)
            self.window.blit(scaled, scaled.get_rect(center=rect.center))
        elif hasattr(icon, 'draw_icon'):
            icon.draw_icon(rect.x, rect.y, rect.w, rect.h)

    def _draw_wrapped(
            self, text, font, color, rect, max_lines=None):
        lines = _wrap_text(font, text, rect.w, max_lines=max_lines)
        y = rect.y
        for line in lines:
            surf = font.render(line, True, color)
            self.window.blit(surf, (rect.x, y))
            y += font.get_height() + 1
            if y > rect.bottom:
                break

    # ── interaction helpers -----------------------------------------

    def _default_target_suit(self):
        same = self._other_suits_same_color()
        different = self._other_suits_different_color()
        return (same + different)[0] if same or different else None

    def _other_suits_same_color(self):
        group = self.red_suits if self.suit in self.red_suits else self.black_suits
        return [suit for suit in group if suit != self.suit]

    def _other_suits_different_color(self):
        group = (
            self.black_suits if self.suit in self.red_suits
            else self.red_suits)
        return list(group)

    def _ratio_for(self, target):
        if not target or target == self.suit:
            return 0
        same_red = self.suit in self.red_suits and target in self.red_suits
        same_black = (
            self.suit in self.black_suits and target in self.black_suits)
        return (
            self.same_color_ratio
            if same_red or same_black
            else self.different_color_ratio)

    def _max_for_target(self, target):
        ratio = self._ratio_for(target)
        return self.free // ratio if ratio else 0

    def _change_quantity(self, delta):
        if self.view == self.VIEW_SELL:
            if not self.free:
                return
            self.sell_qty = min(
                self.free, max(1, self.sell_qty + delta))
        elif self.view == self.VIEW_CONVERT and self.convert_max:
            self.convert_qty = min(
                self.convert_max, max(1, self.convert_qty + delta))
        self._layout()

    def _handle_quantity_action(self, action):
        if self.view == self.VIEW_SELL:
            maximum = self.free
            value = self.sell_qty
        else:
            maximum = self.convert_max
            value = self.convert_qty
        if action == 'minus' and value > 1:
            value -= 1
        elif action == 'plus' and value < maximum:
            value += 1
        elif action == 'max' and maximum > value:
            value = maximum
        if self.view == self.VIEW_SELL:
            self.sell_qty = value
        else:
            self.convert_qty = value
        self._layout()

    @staticmethod
    def _play_click():
        try:
            from utils import sound
            sound.play('ui_click')
        except Exception:
            pass
