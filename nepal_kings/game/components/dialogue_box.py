# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config import settings
import pygame
import textwrap
from game.core.input_state import get_pressed as _get_pressed
from utils import haptics


# ── Themed button for the dialogue box ─────────────────────────────

class _DlgButton:
    """A small themed button drawn with menu_button2 + glow behind."""

    _btn_img_raw = None
    _glows = None

    @classmethod
    def _ensure_assets(cls, window):
        if cls._btn_img_raw is None:
            cls._btn_img_raw = pygame.image.load(
                settings.DIALOGUE_BOX_BTN_IMG_PATH).convert_alpha()
            cls._glows = {}
            glow_w = int(settings.DIALOGUE_BOX_BTN_W * 1.2)
            glow_h = int(settings.DIALOGUE_BOX_BTN_H * 2.0)
            for colour in ('yellow', 'white', 'orange'):
                raw = pygame.image.load(
                    settings.DIALOGUE_BOX_GLOW_DIR + colour + '.png').convert_alpha()
                cls._glows[colour] = pygame.transform.smoothscale(raw, (glow_w, glow_h))

    def __init__(self, window, x, y, text, width=None, height=None):
        _DlgButton._ensure_assets(window)
        self.window = window
        self.text = text
        w = width or settings.DIALOGUE_BOX_BTN_W
        h = height or settings.DIALOGUE_BOX_BTN_H
        self.rect = pygame.Rect(x, y, w, h)
        self.font = settings.get_font(settings.DIALOGUE_BOX_BTN_FONT_SIZE)
        self.font_small = settings.get_font(int(settings.DIALOGUE_BOX_BTN_FONT_SIZE * 0.9))
        self.btn_img = pygame.transform.smoothscale(
            _DlgButton._btn_img_raw, (w, h))
        self.btn_img_small = pygame.transform.smoothscale(
            _DlgButton._btn_img_raw, (int(w * 0.95), int(h * 0.95)))
        self.hovered = False
        self.clicked = False
        self.active = False
        self.disabled = False

    def hit_rect(self):
        if getattr(settings, 'TOUCH_TARGET_MIN', 0) <= 0:
            return self.rect
        min_w = max(self.rect.w, getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0)
        min_h = max(self.rect.h, getattr(settings, 'TOUCH_TARGET_MIN', 0) or 0)
        hit = self.rect.inflate(max(0, min_w - self.rect.w),
                                max(0, min_h - self.rect.h))
        hit.clamp_ip(pygame.Rect(0, 0, settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        return hit

    def collide(self, pos=None):
        return self.hit_rect().collidepoint(pos or pygame.mouse.get_pos())

    def update(self):
        if self.disabled:
            self.hovered = False
            self.clicked = False
        else:
            self.hovered = self.collide()
            self.clicked = self.hovered and _get_pressed()[0]
        haptics.tap_edge(self)

    def get_text_color(self):
        if self.disabled:
            return (100, 100, 100)
        if self.hovered:
            return settings.DIALOGUE_BOX_BTN_TEXT_HOVER_CLR
        return settings.DIALOGUE_BOX_BTN_TEXT_CLR

    def draw(self):
        # 1) Glow behind
        if not self.disabled:
            if self.hovered and self.clicked:
                glow = _DlgButton._glows['yellow']
            elif self.hovered:
                glow = _DlgButton._glows['white']
            else:
                glow = None
            if glow:
                gx = self.rect.centerx - glow.get_width() // 2
                gy = self.rect.centery - glow.get_height() // 2
                self.window.blit(glow, (gx, gy))

        # 2) Button image
        if self.clicked:
            img = self.btn_img_small
            pos = img.get_rect(center=self.rect.center).topleft
        else:
            img = self.btn_img
            pos = self.rect.topleft
        self.window.blit(img, pos)

        # 3) Text
        font = self.font_small if self.clicked else self.font
        txt = font.render(self.text, True, self.get_text_color())
        self.window.blit(txt, txt.get_rect(center=self.rect.center))


# ═══════════════════════════════════════════════════════════════════
#  DialogueBox
# ═══════════════════════════════════════════════════════════════════

class DialogueBox:
    def __init__(self, window, message, actions=None, images=None, icon=None,
                 title="", auto_close_delay=None, message_after_images=None,
                 image_captions=None, image_groups=None):
        if actions is None:
            actions = ['ok']
        if images is None:
            images = []
        if image_groups is None:
            image_groups = []

        self.window = window
        self.message = message
        self.message_after_images = message_after_images
        self.images = images
        self.image_captions = image_captions or []
        self.image_groups = []
        self.icon = None
        self.title = title
        self.font = settings.get_font(settings.FONT_SIZE_DIALOGUE_BOX)
        self.title_font = settings.get_font(settings.FONT_SIZE_TITLE_DIALOGUE_BOX, bold=True)
        self.caption_font = settings.get_font(settings.FS_TINY)
        self.group_title_font = settings.get_font(settings.FS_SMALL, bold=True)
        self.group_note_font = settings.get_font(max(10, int(settings.FS_TINY * 0.82)))
        self.actions = actions
        self.auto_close_delay = auto_close_delay
        self.auto_close_timer = pygame.time.get_ticks() if auto_close_delay else None
        self._created_at = pygame.time.get_ticks()  # grace period for MOUSEBUTTONUP

        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        _corner_r = settings.DIALOGUE_BOX_CORNER_R

        # Icon
        if icon and icon in settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT:
            original_icon = settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT[icon]
            self.icon = self.scale_icon(original_icon)

        # Wrap message (pixel-based to prevent overflow)
        _max_text_w = settings.DIALOGUE_BOX_WIDTH - int(0.08 * _SW)
        self.lines = self._wrap_text(self.message, self.font, _max_text_w)
        self.lines_surfaces = [self.font.render(l, True,
                               settings.DIALOGUE_BOX_MSG_TEXT_CLR) for l in self.lines]

        # Wrap after-images text
        self.after_lines = []
        if self.message_after_images:
            self.after_lines = self._wrap_text(self.message_after_images, self.font, _max_text_w)
        self.after_lines_surfaces = [self.font.render(l, True,
                                     settings.DIALOGUE_BOX_MSG_TEXT_CLR) for l in self.after_lines]

        # Process images
        self._group_max_w = settings.DIALOGUE_BOX_WIDTH - int(0.060 * _SW)
        self.image_groups = self.process_image_groups(image_groups)
        processed_images = self.process_images()
        # A profile can pair one prominent lead image with grouped content.
        # Historically images were silently discarded whenever groups existed.
        self._lead_items = processed_images if self.image_groups else []
        self.ordered_items = [] if self.image_groups else processed_images
        # The initial message wrap assumes the full dialogue width. A lead
        # image takes a fixed slice of that row, so re-wrap against the actual
        # remaining text column or long lines can run underneath the image.
        if self._lead_items:
            item_widths = [
                item.get_width() if kind == 'surface'
                else settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT
                for kind, item in self._lead_items
            ]
            lead_w = (sum(item_widths)
                      + max(0, len(item_widths) - 1) * int(0.008 * _SW))
            box_x = (_SW - settings.DIALOGUE_BOX_WIDTH) // 2
            text_left = (box_x + int(0.045 * _SW) + lead_w
                         + int(0.020 * _SW))
            text_right = (box_x + settings.DIALOGUE_BOX_WIDTH
                          - int(0.035 * _SW))
            lead_text_w = max(1, text_right - text_left)
            self.lines = self._wrap_text(self.message, self.font, lead_text_w)
            self.lines_surfaces = [
                self.font.render(line, True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
                for line in self.lines
            ]
        has_surfaces = any(t == 'surface' for t, _ in self.ordered_items)
        has_drawables = any(t == 'drawable' for t, _ in self.ordered_items)
        lead_heights = [
            item.get_height() if kind == 'surface'
            else settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT
            for kind, item in self._lead_items
        ]
        self.lead_height = max(lead_heights, default=0)

        # Metrics
        _line_h = self.font.get_height() + int(0.004 * _SH)
        _pad_top = settings.DIALOGUE_BOX_TEXT_MARGIN_Y
        _pad_bottom = settings.DIALOGUE_BOX_BTN_MARGIN_BOTTOM

        self.title_height = (self.title_font.get_height() + int(0.016 * _SH)) if self.title else 0
        self._sep_extra = int(0.018 * _SH) if self.title else 0  # space for separator line
        self.message_text_height = len(self.lines) * _line_h
        self.text_height = max(self.message_text_height, self.lead_height)
        self.after_text_height = len(self.after_lines) * _line_h if self.after_lines else 0
        self.img_height = settings.DIALOGUE_BOX_IMG_HEIGHT if has_surfaces else 0
        self.drawable_object_height = settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT if has_drawables else 0
        self.group_content_height = self._calc_group_content_height()
        self.content_height = self.group_content_height if self.image_groups else (
            max(self.img_height, self.drawable_object_height) if self.ordered_items else 0
        )
        has_visual_content = bool(self.image_groups or self.ordered_items)
        self.img_spacing = int(0.020 * _SH) if has_visual_content else 0
        self.drawable_bottom_spacing = int(0.018 * _SH) if has_visual_content else 0
        self.caption_height = 0 if self.image_groups else (
            (self.caption_font.get_height() + int(0.006 * _SH)) if self.image_captions else 0
        )

        btn_h = settings.DIALOGUE_BOX_BTN_H if self.actions else 0
        self.button_height = btn_h + _pad_bottom if self.actions else 0

        self.box_height = (_pad_top + self.title_height + self._sep_extra +
                           self.text_height + self.img_spacing +
                           self.content_height + self.caption_height +
                           self.drawable_bottom_spacing +
                           self.after_text_height + self.button_height +
                           int(0.010 * _SH))

        # Position (centred)
        box_w = settings.DIALOGUE_BOX_WIDTH
        self.x = (_SW - box_w) // 2
        height_diff = self.box_height - settings.DIALOGUE_BOX_HEIGHT
        self.y = int(_SH * 0.5 - settings.DIALOGUE_BOX_HEIGHT * 0.75 - height_diff / 2)
        self.y = max(int(0.020 * _SH), min(self.y, _SH - self.box_height - int(0.020 * _SH)))
        self.rect = pygame.Rect(self.x, self.y, box_w, self.box_height)

        # Pre-render panel surface (semi-transparent with rounded corners)
        self._panel = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
        pygame.draw.rect(self._panel, settings.DIALOGUE_BOX_BG_CLR,
                         self._panel.get_rect(), border_radius=_corner_r)
        pygame.draw.rect(self._panel, settings.DIALOGUE_BOX_BORDER_CLR,
                         self._panel.get_rect(),
                         settings.DIALOGUE_BOX_BORDER_WIDTH,
                         border_radius=_corner_r)

        # Full-screen dim overlay
        self._overlay = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
        self._overlay.fill(settings.DIALOGUE_BOX_OVERLAY_CLR)

        # Keep border_rect for any legacy code that references it
        self.border_rect = self.rect.inflate(2, 2)

        # Per-draw hover tracking for image-group item tooltips.
        # Reset at the start of each draw() call.
        self._hover_item_rects = []

        # Buttons
        if self.actions:
            _btn_w = settings.DIALOGUE_BOX_BTN_W
            _btn_gap = settings.DIALOGUE_BOX_BTN_GAP
            total_btns_w = len(self.actions) * _btn_w + (len(self.actions) - 1) * _btn_gap
            first_x = self.rect.centerx - total_btns_w // 2
            btn_y = self.rect.bottom - self.button_height + int(0.004 * _SH)
            self.buttons = []
            for i, action in enumerate(self.actions):
                bx = first_x + i * (_btn_w + _btn_gap)
                self.buttons.append(_DlgButton(self.window, bx, btn_y, action,
                                               width=_btn_w, height=settings.DIALOGUE_BOX_BTN_H))
        else:
            self.buttons = []

        # Layout cache
        self._line_h = _line_h

    # ── helpers ─────────────────────────────────────────────────────

    def process_images(self):
        ordered = []
        for img in self.images:
            if isinstance(img, pygame.Surface):
                iw, ih = img.get_size()
                ratio = settings.DIALOGUE_BOX_IMG_HEIGHT / ih
                nw = int(iw * ratio)
                scaled = pygame.transform.smoothscale(img, (nw, settings.DIALOGUE_BOX_IMG_HEIGHT))
                ordered.append(('surface', scaled))
            elif hasattr(img, "draw_icon"):
                ordered.append(('drawable', img))
        return ordered

    def process_image_groups(self, image_groups):
        """Normalize compact grouped-card sections for confirmation dialogues."""
        groups = []
        for raw_group in image_groups:
            raw_items = raw_group.get('items') or raw_group.get('images') or []
            raw_tooltips = raw_group.get('item_tooltips') or []
            items = []
            max_items = getattr(settings, 'DIALOGUE_BOX_GROUP_MAX_ITEMS', 16)
            for i, raw_item in enumerate(raw_items[:max_items]):
                item = raw_item.get('image') if isinstance(raw_item, dict) else raw_item
                normalized = self._normalize_group_item(item)
                if normalized:
                    normalized['tooltip'] = (raw_tooltips[i]
                                             if i < len(raw_tooltips) else '')
                    items.append(normalized)

            count = raw_group.get('count') or len(raw_items)
            more_count = max(0, count - len(items))
            if more_count:
                items.append({
                    'kind': 'more',
                    'width': int(settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT * 0.72),
                    'height': settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT,
                    'text': f'+{more_count}',
                })

            if not items and not raw_group.get('show_when_empty'):
                continue

            icon_name = raw_group.get('icon')
            # Omitting badge_icon keeps the historical header-icon fallback.
            # Passing it explicitly as None lets a caller keep the subsection
            # header icon without repeating it over every content tile.
            badge_name = (raw_group.get('badge_icon')
                          if 'badge_icon' in raw_group else icon_name)
            title = raw_group.get('title', 'Cards')
            item_unit = raw_group.get('item_unit', 'card')
            color = raw_group.get('color') or self._default_group_color(icon_name)
            note_prefix = raw_group.get('note_prefix', '')
            feature_item = bool(raw_group.get('feature_item') and len(items) == 1)
            note_width = self._group_max_w - int(0.040 * settings.SCREEN_WIDTH)
            if feature_item:
                note_width -= (
                    settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT
                    + int(0.020 * settings.SCREEN_WIDTH))
            group = {
                'key': raw_group.get('key'),
                'title': self._format_group_title(title, count, item_unit),
                'description': raw_group.get('description') or raw_group.get('note') or '',
                'note_prefix': note_prefix,
                'items': items,
                'count': count,
                'icon_name': icon_name,
                'icon': self._scaled_named_icon(icon_name, settings.DIALOGUE_BOX_GROUP_ICON_SIZE),
                'badge_icon': self._scaled_named_icon(badge_name, settings.DIALOGUE_BOX_GROUP_BADGE_SIZE),
                'color': color,
                'feature_item': feature_item,
            }
            group['note_lines'] = self._wrap_text(
                group['description'],
                self.group_note_font,
                note_width,
            ) if group['description'] else []
            group['rows'] = self._layout_group_rows(group['items'], self._group_max_w)
            group['height'] = self._calc_single_group_height(group)
            groups.append(group)
        return groups

    def _normalize_group_item(self, item):
        if isinstance(item, pygame.Surface):
            iw, ih = item.get_size()
            if ih <= 0:
                return None
            ratio = settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT / ih
            nw = max(1, int(iw * ratio))
            scaled = pygame.transform.smoothscale(
                item, (nw, settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT))
            return {
                'kind': 'surface',
                'surface': scaled,
                'width': scaled.get_width(),
                'height': scaled.get_height(),
            }
        if hasattr(item, 'draw_icon'):
            size = settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT
            return {
                'kind': 'drawable',
                'drawable': item,
                'width': size,
                'height': size,
            }
        return None

    def _layout_group_rows(self, items, max_width):
        rows = []
        current = []
        current_w = 0
        gap = settings.DIALOGUE_BOX_GROUP_CARD_GAP_X
        for item in items:
            item_w = item['width']
            next_w = item_w if not current else current_w + gap + item_w
            if current and next_w > max_width:
                rows.append(current)
                current = [item]
                current_w = item_w
            else:
                current.append(item)
                current_w = next_w
        if current:
            rows.append(current)
        return rows

    def _calc_group_content_height(self):
        if not self.image_groups:
            return 0
        gap = settings.DIALOGUE_BOX_GROUP_GAP_Y
        return sum(group['height'] for group in self.image_groups) + gap * (len(self.image_groups) - 1)

    def _calc_single_group_height(self, group):
        pad_y = settings.DIALOGUE_BOX_GROUP_PADDING_Y
        header_h = max(
            self.group_title_font.get_height(),
            settings.DIALOGUE_BOX_GROUP_ICON_SIZE if group.get('icon') else 0,
        )
        # note_prefix occupies one extra line rendered in a bold font
        prefix_h = 0
        if group.get('note_prefix'):
            bold_font = settings.get_font(
                max(10, int(settings.FS_TINY * 0.82)), bold=True)
            prefix_h = bold_font.get_height() + 1 + int(0.003 * settings.SCREEN_HEIGHT)
        note_h = len(group['note_lines']) * (self.group_note_font.get_height() + 1)
        if note_h:
            note_h += int(0.003 * settings.SCREEN_HEIGHT)
        rows = group.get('rows') or []
        if group.get('feature_item') and rows:
            text_h = header_h + prefix_h + note_h
            return pad_y * 2 + max(text_h, settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT)
        cards_h = 0
        if rows:
            cards_h = (
                len(rows) * settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT
                + (len(rows) - 1) * settings.DIALOGUE_BOX_GROUP_ROW_GAP
                + settings.DIALOGUE_BOX_GROUP_HEADER_GAP
            )
        return pad_y * 2 + header_h + prefix_h + note_h + cards_h

    def _format_group_title(self, title, count, unit='card'):
        suffix = unit if count == 1 else unit + 's'
        return f'{title}: {count} {suffix}'

    def _default_group_color(self, icon_name):
        if icon_name == 'remove':
            return settings.DIALOGUE_BOX_GROUP_CONSUME_CLR
        if icon_name == 'lock':
            return settings.DIALOGUE_BOX_GROUP_LOCK_CLR
        return settings.DIALOGUE_BOX_MSG_TEXT_CLR

    def _scaled_named_icon(self, icon_name, size):
        if not icon_name:
            return None
        icon = settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT.get(icon_name)
        if not icon:
            return None
        return pygame.transform.smoothscale(icon, (size, size))

    def scale_icon(self, icon):
        iw, ih = icon.get_size()
        ratio = settings.DIALOGUE_BOX_ICON_HEIGHT / ih
        nw = int(iw * ratio)
        return pygame.transform.smoothscale(icon, (nw, settings.DIALOGUE_BOX_ICON_HEIGHT))

    @staticmethod
    def _wrap_text(text, font, max_width):
        """Word-wrap *text* so no rendered line exceeds *max_width* pixels."""
        lines = []
        for paragraph in text.split('\n'):
            if not paragraph.strip():
                lines.append('')
                continue
            words = paragraph.split()
            current_line = []
            for word in words:
                test_line = ' '.join(current_line + [word])
                if font.size(test_line)[0] <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
            if current_line:
                lines.append(' '.join(current_line))
        return lines if lines else ['']

    # ── draw ────────────────────────────────────────────────────────

    def draw(self):
        _SH = settings.SCREEN_HEIGHT
        _SW = settings.SCREEN_WIDTH

        # Dim overlay
        self.window.blit(self._overlay, (0, 0))

        # Panel
        self.window.blit(self._panel, self.rect.topleft)

        current_y = self.rect.y + settings.DIALOGUE_BOX_TEXT_MARGIN_Y

        # Title
        if self.title:
            title_surface = self.title_font.render(self.title, True,
                                                   settings.TITLE_TEXT_COLOR)
            title_rect = title_surface.get_rect(
                center=(self.rect.centerx, current_y + title_surface.get_height() // 2))

            if self.icon:
                icon_gap = int(0.010 * _SW)
                icon_y = title_rect.centery - self.icon.get_height() // 2
                self.window.blit(self.icon,
                                 (title_rect.left - icon_gap - self.icon.get_width(), icon_y))
                self.window.blit(self.icon,
                                 (title_rect.right + icon_gap, icon_y))

            self.window.blit(title_surface, title_rect)
            current_y += title_surface.get_height() + int(0.016 * _SH)

            # Separator line
            sep_x1 = self.rect.x + int(0.04 * _SW)
            sep_x2 = self.rect.right - int(0.04 * _SW)
            pygame.draw.line(self.window, settings.DIALOGUE_BOX_SEP_CLR,
                             (sep_x1, current_y), (sep_x2, current_y), 1)
            current_y += int(0.018 * _SH)

        # Message lines. When grouped content supplies a lead image (the
        # Collection card profile), keep the image and stock copy side-by-side.
        message_center_x = self.rect.centerx
        message_top = current_y
        if self._lead_items:
            item_gap = int(0.008 * _SW)
            item_widths = [
                item.get_width() if kind == 'surface'
                else settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT
                for kind, item in self._lead_items
            ]
            lead_w = sum(item_widths) + max(0, len(item_widths) - 1) * item_gap
            lead_x = self.rect.x + int(0.045 * _SW)
            draw_x = lead_x
            for (kind, item), item_w in zip(self._lead_items, item_widths):
                if kind == 'surface':
                    draw_y = current_y + (self.text_height - item.get_height()) // 2
                    self.window.blit(item, (draw_x, draw_y))
                else:
                    size = settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT
                    draw_y = current_y + (self.text_height - size) // 2
                    item.draw_icon(draw_x, draw_y, size, size)
                draw_x += item_w + item_gap
            text_left = lead_x + lead_w + int(0.020 * _SW)
            text_right = self.rect.right - int(0.035 * _SW)
            message_center_x = (text_left + text_right) // 2
            message_top = current_y + max(
                0, (self.text_height - self.message_text_height) // 2)

        for i, line_surf in enumerate(self.lines_surfaces):
            ly = message_top + i * self._line_h
            self.window.blit(line_surf,
                             line_surf.get_rect(center=(message_center_x, ly)))

        # Images / drawables position
        image_y = current_y + self.text_height + self.img_spacing

        if self.image_groups:
            self._draw_image_groups(image_y)
        elif self.ordered_items:
            max_w = settings.DIALOGUE_BOX_WIDTH - int(0.04 * _SW)
            num = len(self.ordered_items)
            widths = []
            for t, item in self.ordered_items:
                if t == 'surface':
                    widths.append(item.get_width())
                else:
                    widths.append(settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT)

            natural_w = sum(widths) + (num - 1) * int(0.008 * _SW)

            # Collect (x, width) for each item so we can draw captions
            item_positions = []

            if natural_w <= max_w:
                ix = self.rect.centerx - natural_w // 2
                for idx, (t, item) in enumerate(self.ordered_items):
                    if t == 'surface':
                        self.window.blit(item, (ix, image_y))
                        item_positions.append((ix, item.get_width()))
                        ix += item.get_width() + int(0.008 * _SW)
                    else:
                        item.draw_icon(ix, image_y,
                                       settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT,
                                       settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT)
                        item_positions.append((ix, settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT))
                        ix += settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT + int(0.008 * _SW)
            else:
                if num == 1:
                    spacing = 0
                    ix = self.rect.centerx - widths[0] // 2
                else:
                    spacing = (max_w - widths[-1]) / (num - 1)
                    ix = self.rect.centerx - max_w // 2
                for i, (t, item) in enumerate(self.ordered_items):
                    xp = ix + i * spacing
                    if t == 'surface':
                        self.window.blit(item, (xp, image_y))
                        item_positions.append((xp, item.get_width()))
                    else:
                        item.draw_icon(xp, image_y,
                                       settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT,
                                       settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT)
                        item_positions.append((xp, settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT))

            # Captions below each image
            if self.image_captions:
                caption_y = image_y + self.content_height + int(0.004 * _SH)
                for idx, (ix_pos, iw) in enumerate(item_positions):
                    if idx < len(self.image_captions) and self.image_captions[idx]:
                        cap_surf = self.caption_font.render(
                            self.image_captions[idx], True,
                            settings.DIALOGUE_BOX_MSG_TEXT_CLR)
                        cap_rect = cap_surf.get_rect(
                            centerx=int(ix_pos + iw / 2), top=caption_y)
                        self.window.blit(cap_surf, cap_rect)

        # After-images text
        if self.after_lines_surfaces:
            aty = (image_y + self.content_height + self.caption_height +
                   self.drawable_bottom_spacing)
            for i, line_surf in enumerate(self.after_lines_surfaces):
                ly = aty + i * self._line_h
                self.window.blit(line_surf,
                                 line_surf.get_rect(center=(self.rect.centerx, ly)))

        # Buttons
        for button in self.buttons:
            button.draw()

    def _draw_image_groups(self, start_y):
        self._hover_item_rects = []  # reset per-draw
        group_x = self.rect.centerx - self._group_max_w // 2
        group_w = self._group_max_w
        current_y = start_y
        for group in self.image_groups:
            group_rect = pygame.Rect(group_x, current_y, group_w, group['height'])
            pygame.draw.rect(
                self.window,
                settings.DIALOGUE_BOX_GROUP_PANEL_BG_CLR,
                group_rect,
                border_radius=8,
            )
            pygame.draw.rect(
                self.window,
                group.get('color') or settings.DIALOGUE_BOX_GROUP_PANEL_BORDER_CLR,
                group_rect,
                1,
                border_radius=8,
            )

            pad_x = settings.DIALOGUE_BOX_GROUP_PADDING_X
            pad_y = settings.DIALOGUE_BOX_GROUP_PADDING_Y
            x = group_rect.x + pad_x
            y = group_rect.y + pad_y
            icon = group.get('icon')
            header_h = max(
                self.group_title_font.get_height(),
                settings.DIALOGUE_BOX_GROUP_ICON_SIZE if icon else 0,
            )
            if icon:
                icon_y = y + (header_h - icon.get_height()) // 2
                self.window.blit(icon, (x, icon_y))
                x += icon.get_width() + int(0.006 * settings.SCREEN_WIDTH)

            title_surf = self.group_title_font.render(
                group['title'], True, group.get('color') or settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            self.window.blit(title_surf, (x, y + (header_h - title_surf.get_height()) // 2))

            y += header_h
            # Bold prefix line (e.g. 'Key Card') drawn before the plain note
            prefix = group.get('note_prefix', '')
            if prefix:
                bold_font = settings.get_font(
                    max(10, int(settings.FS_TINY * 0.82)), bold=True)
                y += int(0.003 * settings.SCREEN_HEIGHT)
                prefix_surf = bold_font.render(
                    prefix, True, settings.DIALOGUE_BOX_GROUP_NOTE_CLR)
                self.window.blit(prefix_surf, (group_rect.x + pad_x, y))
                y += bold_font.get_height() + 1
            if group['note_lines']:
                y += int(0.003 * settings.SCREEN_HEIGHT)
                for line in group['note_lines']:
                    note_surf = self.group_note_font.render(
                        line, True, settings.DIALOGUE_BOX_GROUP_NOTE_CLR)
                    self.window.blit(note_surf, (group_rect.x + pad_x, y))
                    y += self.group_note_font.get_height() + 1

            if group.get('feature_item') and group['rows']:
                item = group['rows'][0][0]
                item_x = group_rect.right - pad_x - item['width']
                item_y = group_rect.centery - item['height'] // 2
                self._draw_group_item(item, item_x, item_y, group.get('badge_icon'))
                tooltip = item.get('tooltip', '')
                if tooltip:
                    self._hover_item_rects.append({
                        'rect': pygame.Rect(
                            item_x, item_y,
                            item['width'],
                            item['height']),
                        'tooltip': tooltip,
                    })
            elif group['rows']:
                y += settings.DIALOGUE_BOX_GROUP_HEADER_GAP
                for row in group['rows']:
                    row_w = self._row_width(row)
                    row_x = group_rect.centerx - row_w // 2
                    for item in row:
                        self._draw_group_item(item, row_x, y, group.get('badge_icon'))
                        tooltip = item.get('tooltip', '')
                        if tooltip:
                            self._hover_item_rects.append({
                                'rect': pygame.Rect(
                                    row_x, y,
                                    item['width'],
                                    item['height']),
                                'tooltip': tooltip,
                            })
                        row_x += item['width'] + settings.DIALOGUE_BOX_GROUP_CARD_GAP_X
                    y += settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT + settings.DIALOGUE_BOX_GROUP_ROW_GAP

            current_y += group['height'] + settings.DIALOGUE_BOX_GROUP_GAP_Y

    def _row_width(self, row):
        if not row:
            return 0
        return (sum(item['width'] for item in row)
                + (len(row) - 1) * settings.DIALOGUE_BOX_GROUP_CARD_GAP_X)

    def _draw_group_item(self, item, x, y, badge_icon):
        if item['kind'] == 'surface':
            self.window.blit(item['surface'], (x, y))
            self._draw_group_badge(x, y, badge_icon)
            return
        if item['kind'] == 'drawable':
            item['drawable'].draw_icon(
                x, y,
                settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT,
                settings.DIALOGUE_BOX_GROUP_IMG_HEIGHT,
            )
            self._draw_group_badge(x, y, badge_icon)
            return
        if item['kind'] == 'more':
            rect = pygame.Rect(x, y, item['width'], item['height'])
            pygame.draw.rect(
                self.window,
                settings.DIALOGUE_BOX_GROUP_MORE_CLR,
                rect,
                border_radius=6,
            )
            pygame.draw.rect(
                self.window,
                settings.DIALOGUE_BOX_GROUP_PANEL_BORDER_CLR,
                rect,
                1,
                border_radius=6,
            )
            text_surf = self.group_title_font.render(
                item['text'], True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            self.window.blit(text_surf, text_surf.get_rect(center=rect.center))

    def _draw_group_badge(self, x, y, badge_icon):
        if not badge_icon:
            return
        badge_bg = badge_icon.get_rect(topleft=(x + 2, y + 2)).inflate(4, 4)
        pygame.draw.rect(self.window, (245, 240, 220, 220), badge_bg, border_radius=4)
        self.window.blit(badge_icon, (x + 4, y + 4))

    # ── update ──────────────────────────────────────────────────────

    def update(self, events):
        if self.auto_close_delay is not None and self.auto_close_timer is not None:
            elapsed = pygame.time.get_ticks() - self.auto_close_timer
            if elapsed >= self.auto_close_delay:
                return 'auto_close'

        for button in self.buttons:
            button.update()

        # Ignore MOUSEBUTTONUP within 200ms of creation to prevent the
        # release from the click that opened the dialogue from triggering
        # a button immediately.
        if pygame.time.get_ticks() - self._created_at < 200:
            return None

        for event in events:
            if event.type == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                for button in self.buttons:
                    if button.collide(getattr(event, 'pos', None)):
                        from utils import sound
                        sound.play('ui_click')
                        return button.text.lower()
        return None

    def get_tooltip(self, pos):
        """Return tooltip text for the image-group item under *pos*, or ''."""
        for entry in self._hover_item_rects:
            if entry['rect'].collidepoint(pos):
                return entry['tooltip']
        return ''
