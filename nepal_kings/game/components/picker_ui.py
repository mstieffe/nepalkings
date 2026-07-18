# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared presentation helpers for the figure, spell, and tactics pickers.

The three pickers intentionally keep their gameplay code separate, but share
the same responsive navigation, caption, empty-state, and footer language.
This module contains draw/input primitives only; it never mutates game state.
"""

from __future__ import annotations

import pygame

from config import settings


_INK = (82, 50, 22)
_MUTED_INK = (112, 82, 54)
_PARCHMENT = (232, 205, 168, 238)
_PARCHMENT_DARK = (203, 169, 126, 232)
_GOLD = (224, 182, 82)
_GOLD_BRIGHT = (250, 221, 0)
_BROWN = (62, 40, 22)
_BROWN_SOFT = (82, 57, 34)


def _fit_font(text, max_width, preferred_size, *, bold=False, minimum=8):
    """Return the largest configured font that fits ``text``."""
    size = max(minimum, int(preferred_size))
    font = settings.get_font(size, bold=bold)
    while size > minimum and font.size(text)[0] > max_width:
        size -= 1
        font = settings.get_font(size, bold=bold)
    return font


def split_caption(text, font, max_width, max_lines=2):
    """Wrap a short caption into at most ``max_lines`` balanced lines."""
    words = str(text or '').split()
    if not words:
        return ['']
    lines = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if not current or font.size(candidate)[0] <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break
    remaining_start = sum(len(line.split()) for line in lines)
    remaining = words[remaining_start:]
    if remaining:
        current = ' '.join(remaining)
    if current:
        lines.append(current)
    lines = lines[:max_lines]

    # If the final line is still too wide, shrink it with an ellipsis.
    if lines and font.size(lines[-1])[0] > max_width:
        tail = lines[-1]
        while tail and font.size(tail + '…')[0] > max_width:
            tail = tail[:-1]
        lines[-1] = (tail.rstrip() + '…') if tail else '…'
    return lines


def draw_caption_cell(window, text, center_x, top_y, max_width, *,
                      color=_INK, inactive=False, selected=False,
                      preferred_size=None, background=False):
    """Draw a stable one/two-line caption and return its visual rectangle."""
    preferred_size = preferred_size or settings.FS_TINY
    font = _fit_font(
        str(text or ''), max_width * 1.55, preferred_size,
        bold=selected,
        minimum=max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.72)),
    )
    lines = split_caption(text, font, max_width, max_lines=2)
    line_h = font.get_linesize()
    block_h = max(1, len(lines)) * line_h
    rect = pygame.Rect(
        int(center_x - max_width // 2),
        int(top_y),
        int(max_width),
        int(block_h),
    )
    if background:
        bg = pygame.Surface((rect.w, rect.h + 4), pygame.SRCALPHA)
        pygame.draw.rect(
            bg,
            (235, 210, 170, 232) if not selected else (248, 222, 165, 246),
            bg.get_rect(),
            border_radius=max(3, int(0.004 * settings.SCREEN_HEIGHT)),
        )
        pygame.draw.rect(
            bg, _GOLD if selected else (120, 72, 36),
            bg.get_rect(), 1,
            border_radius=max(3, int(0.004 * settings.SCREEN_HEIGHT)),
        )
        window.blit(bg, (rect.x, rect.y - 2))

    draw_color = (82, 72, 60) if inactive else color
    for index, line in enumerate(lines):
        surf = font.render(line, True, draw_color)
        window.blit(
            surf,
            surf.get_rect(centerx=center_x, top=top_y + index * line_h),
        )
    return rect


class SegmentedTabs:
    """Touch-safe horizontal category tabs used by all picker screens."""

    def __init__(self, window, rect, options, active_key=None):
        self.window = window
        self.rect = pygame.Rect(rect)
        self.options = list(options)
        self.active_key = (
            active_key if active_key is not None
            else (self.options[0][0] if self.options else None)
        )
        self.font = settings.get_font(
            max(settings.FS_CONQUER_LABEL, int(settings.FS_SMALL * 0.92)),
            bold=True)
        self._tab_rects = {}
        self._rebuild_rects()

    def _rebuild_rects(self):
        self._tab_rects = {}
        count = max(1, len(self.options))
        base_w = self.rect.w // count
        x = self.rect.x
        for index, (key, _label) in enumerate(self.options):
            width = self.rect.right - x if index == count - 1 else base_w
            self._tab_rects[key] = pygame.Rect(x, self.rect.y, width, self.rect.h)
            x += width

    def set_rect(self, rect):
        self.rect = pygame.Rect(rect)
        self._rebuild_rects()

    def select(self, key):
        if key in self._tab_rects:
            self.active_key = key
            return True
        return False

    def handle_events(self, events):
        """Return the newly-selected key, or ``None``."""
        for event in events:
            if event.type != pygame.MOUSEBUTTONDOWN or getattr(event, 'button', 1) != 1:
                continue
            pos = getattr(event, 'pos', pygame.mouse.get_pos())
            for key, rect in self._tab_rects.items():
                hit = rect
                if settings.TOUCH_HIT_PAD:
                    hit = hit.inflate(0, settings.TOUCH_HIT_PAD)
                if hit.collidepoint(pos):
                    if key != self.active_key:
                        self.active_key = key
                        return key
                    return None
        return None

    def draw(self):
        pygame.draw.rect(
            self.window, (50, 38, 28, 210), self.rect,
            border_radius=max(4, int(0.006 * settings.SCREEN_HEIGHT)))
        for key, label in self.options:
            rect = self._tab_rects[key]
            active = key == self.active_key
            fill = (92, 65, 36, 245) if active else (55, 42, 31, 220)
            border = _GOLD if active else (120, 96, 65)
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                panel, fill, panel.get_rect(),
                border_radius=max(4, int(0.006 * settings.SCREEN_HEIGHT)))
            self.window.blit(panel, rect.topleft)
            pygame.draw.rect(
                self.window, border, rect, 2 if active else 1,
                border_radius=max(4, int(0.006 * settings.SCREEN_HEIGHT)))
            font = _fit_font(
                label, max(1, rect.w - 10), self.font.get_height(),
                bold=True, minimum=settings.FS_CONQUER_META)
            color = _GOLD_BRIGHT if active else (222, 205, 180)
            surf = font.render(label, True, color)
            self.window.blit(surf, surf.get_rect(center=rect.center))


_TYPE_ORDER = ('greed', 'enchantment', 'tactics')


def layout_family_grid_desktop(buttons, box, *, type_order=_TYPE_ORDER,
                               max_cols=6, top_pad=None):
    """Lay every family button out at once, grouped by type into full rows.

    Used on desktop where the whole spell book fits on one page — the category
    tabs collapse into lightweight section headings so the player scans all
    families without clicking through tabs.  Each button is centred inside its
    column cell and made visible; returns ``[(type, header_rect), …]`` so the
    caller can render the section labels.
    """
    present = [t for t in type_order
               if any(getattr(b.family, 'type', None) == t for b in buttons)]
    for b in buttons:
        t = getattr(b.family, 'type', None)
        if t is not None and t not in present:
            present.append(t)
    if not present:
        return []

    margin_x = int(0.045 * box.w)
    usable_w = box.w - 2 * margin_x
    start_x = box.x + margin_x
    top = box.y + (top_pad if top_pad is not None
                   else int(0.028 * settings.SCREEN_HEIGHT))
    bottom = box.bottom - int(0.012 * settings.SCREEN_HEIGHT)
    block_h = max(1, (bottom - top) // len(present))
    header_font = settings.get_font(
        max(settings.FS_CONQUER_LABEL, int(settings.FS_SMALL * 0.98)), bold=True)
    label_h = header_font.get_height() + int(0.004 * settings.SCREEN_HEIGHT)
    gap = max(4, int(0.008 * settings.SCREEN_HEIGHT))

    # Icon footprint (already rescaled for this dense page) drives placement so
    # the icon sits just under its section label and the caption clears the
    # next section's label.
    icon_h = max(
        (b.frame_img.get_height() for b in buttons
         if getattr(b, 'frame_img', None) is not None),
        default=int(0.09 * settings.SCREEN_HEIGHT))

    for b in buttons:
        b.visible = True

    headers = []
    for ti, spell_type in enumerate(present):
        fam = [b for b in buttons
               if getattr(b.family, 'type', None) == spell_type]
        cols = max(1, min(max_cols, len(fam)))
        cell_w = usable_w / cols
        block_top = top + ti * block_h
        headers.append(
            (spell_type,
             pygame.Rect(start_x, int(block_top), int(usable_w), label_h)))
        icon_cy = int(block_top + label_h + gap + icon_h / 2)
        for index, button in enumerate(fam):
            col = index % cols
            row = index // cols
            cx = int(start_x + col * cell_w + cell_w / 2)
            cy = icon_cy + row * int(icon_h + label_h)
            button.set_position(cx, cy)
            button.caption_max_width = max(48, int(cell_w * 0.9))
    return headers


def draw_section_header(window, label_text, rect):
    """Draw a left-aligned gold section label with a trailing hairline rule."""
    font = settings.get_font(
        max(settings.FS_CONQUER_LABEL, int(settings.FS_SMALL * 0.98)), bold=True)
    text = str(label_text or '').capitalize()
    surf = font.render(text, True, _GOLD_BRIGHT)
    window.blit(surf, surf.get_rect(midleft=(rect.x, rect.centery)))
    line_x0 = rect.x + surf.get_width() + max(8, int(0.008 * settings.SCREEN_WIDTH))
    if line_x0 < rect.right - 6:
        pygame.draw.line(
            window, (150, 116, 70),
            (line_x0, rect.centery), (rect.right - 4, rect.centery), 1)


def draw_empty_detail(window, rect, title, body):
    """Fill an otherwise blank detail panel with useful first-step guidance."""
    rect = pygame.Rect(rect)
    title_font = settings.get_font(settings.FS_HEADING, bold=True)
    body_font = settings.get_font(settings.FS_SMALL)
    icon_r = max(10, int(0.018 * settings.SCREEN_WIDTH))
    icon_center = (rect.centerx, rect.y + int(rect.h * 0.28))
    pygame.draw.circle(window, (112, 82, 54), icon_center, icon_r, 2)
    pygame.draw.circle(window, _GOLD, icon_center, max(2, icon_r // 5))

    title_surf = title_font.render(title, True, _GOLD_BRIGHT)
    window.blit(
        title_surf,
        title_surf.get_rect(centerx=rect.centerx,
                            top=icon_center[1] + icon_r + 8),
    )

    max_w = max(20, rect.w - 20)
    words = str(body).split()
    lines = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if not current or body_font.size(candidate)[0] <= max_w:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    top = icon_center[1] + icon_r + 12 + title_surf.get_height()
    for line in lines[:4]:
        surf = body_font.render(line, True, (224, 211, 190))
        window.blit(surf, surf.get_rect(centerx=rect.centerx, top=top))
        top += body_font.get_linesize()


def footer_rect(subscreen):
    """Return the footer band fully inside the parchment decorative frame."""
    margin_x = max(8, int(0.018 * settings.SCREEN_WIDTH))
    frame = max(1, settings.SUB_SCREEN_BG_FRAME_W)
    edge_gap = max(3, int(0.006 * settings.SCREEN_HEIGHT))
    height = max(
        int(0.052 * settings.SCREEN_HEIGHT),
        settings.TOUCH_COMPACT_MIN if settings.TOUCH_TARGET_MIN > 0 else 24,
    )
    inner_bottom = (
        subscreen.y + settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT
        - frame - edge_gap
    )
    return pygame.Rect(
        subscreen.x + margin_x,
        inner_bottom - height,
        settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH - 2 * margin_x,
        height,
    )


def footer_rail_rects(subscreen):
    """Return footer rails aligned with the picker detail and catalog panes."""
    footer = footer_rect(subscreen)
    gap = max(5, int(0.006 * settings.SCREEN_WIDTH))

    # Picker screens initialise these pane coordinates before their buttons.
    # Keep proportional fallbacks for small geometry-only test doubles and
    # defensive use while a picker is still being constructed.
    action_x = getattr(subscreen, 'scroll_x', footer.x)
    action_w = getattr(subscreen, 'scroll_w', int(footer.w * 0.30))
    status_x = getattr(
        subscreen, 'sub_box_x', action_x + action_w + gap)
    sub_box = getattr(subscreen, 'sub_box_background', None)
    status_w = (
        sub_box.get_width()
        if sub_box is not None
        else footer.right - status_x
    )

    action_left = max(footer.left, int(action_x))
    action_right = min(footer.right, int(action_x + action_w))
    action = pygame.Rect(
        action_left, footer.y,
        max(1, action_right - action_left), footer.h)

    status_left = max(footer.left, int(status_x))
    if status_left <= action.right:
        status_left = action.right + gap
    status_right = min(footer.right, int(status_x + status_w))
    status = pygame.Rect(
        status_left, footer.y,
        max(1, status_right - status_left), footer.h)
    return action, status


def footer_button_geometry(subscreen, label, *, align='left'):
    """Return touch-conscious geometry for a footer ``ConfirmButton``."""
    action_rail, status_rail = footer_rail_rects(subscreen)
    rail = status_rail if align == 'right' else action_rail
    font = settings.get_font(settings.CONFIRM_BUTTON_FONT_SIZE)
    width = max(
        int(0.12 * settings.SCREEN_WIDTH),
        font.size(label)[0] + max(18, settings.SMALL_SPACER_X),
    )
    width = min(width, max(1, rail.w - 12))
    height = max(
        settings.CONFIRM_BUTTON_HEIGHT,
        settings.TOUCH_COMPACT_MIN if settings.TOUCH_TARGET_MIN > 0 else 0,
    )
    y = rail.centery - height // 2
    if align == 'right':
        x = rail.right - width - 6
    else:
        x = rail.x + 6
    return x, y, width, height


def _draw_footer_rail(window, rect):
    """Draw one compact footer rail."""
    radius = max(5, int(0.007 * settings.SCREEN_HEIGHT))
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(
        panel, (55, 40, 27, 222), panel.get_rect(),
        border_radius=radius)
    window.blit(panel, rect.topleft)
    pygame.draw.rect(
        window, (135, 102, 62), rect, 1, border_radius=radius)


def draw_footer(
        window, subscreen, status='', *, tone='neutral',
        show_action=True, show_status=None, reserve_status_right=False):
    """Draw compact action and status rails beneath their owning panes."""
    action_rect, status_rect = footer_rail_rects(subscreen)
    if show_status is None:
        show_status = bool(status)
    # Mobile: the action button carries its own chrome — an extra rail box
    # behind it reads as clutter on the small canvas. The status rail stays;
    # its text needs the backdrop.
    if show_action and settings.TOUCH_TARGET_MIN <= 0:
        _draw_footer_rail(window, action_rect)
    if show_status:
        _draw_footer_rail(window, status_rect)

    if status and show_status:
        colors = {
            'good': (174, 226, 150),
            'warning': (255, 205, 105),
            'bad': (255, 145, 125),
            'neutral': (222, 205, 180),
        }
        text_rect = status_rect.inflate(-12, -4)
        if reserve_status_right:
            text_rect.width = max(1, int(text_rect.w * 0.60))
        font = settings.get_font(settings.FS_SMALL, bold=tone != 'neutral')
        font = _fit_font(status, text_rect.w, font.get_height(),
                         bold=tone != 'neutral',
                         minimum=settings.FS_CONQUER_META)
        # At the legibility floor the text may still exceed the rail —
        # ellipsize rather than shrinking into unreadability.
        shown = status
        if font.size(shown)[0] > text_rect.w:
            while shown and font.size(shown + '…')[0] > text_rect.w:
                shown = shown[:-1]
            shown = (shown.rstrip() + '…') if shown else '…'
        surf = font.render(shown, True, colors.get(tone, colors['neutral']))
        window.blit(surf, surf.get_rect(center=text_rect.center))
    return footer_rect(subscreen)


def draw_small_badge(window, text, rect, *, tone='gold'):
    """Draw a compact labelled state badge (for limits and availability)."""
    rect = pygame.Rect(rect)
    colors = {
        'gold': ((72, 52, 32, 235), _GOLD_BRIGHT),
        'good': ((45, 82, 45, 235), (188, 238, 170)),
        'bad': ((92, 45, 38, 235), (255, 170, 150)),
        'neutral': ((58, 48, 38, 225), (220, 205, 180)),
    }
    bg_color, text_color = colors.get(tone, colors['gold'])
    surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(surf, bg_color, surf.get_rect(),
                     border_radius=max(4, rect.h // 3))
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, (145, 112, 68), rect, 1,
                     border_radius=max(4, rect.h // 3))
    font = _fit_font(text, rect.w - 8, settings.FS_TINY,
                     bold=True, minimum=settings.FS_CONQUER_META)
    label = font.render(text, True, text_color)
    window.blit(label, label.get_rect(center=rect.center))
