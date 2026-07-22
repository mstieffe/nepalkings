# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Paginated teaching window for the tutorial (option-b coaching).

A large dialogue that presents game concepts with an image + text per page and
Back / Next / Got it buttons. Modeled on RewardsRevealDialogueBox's panel,
overlay and button conventions.

    pages = [{'title': str, 'lines': [str, ...],
              'image': pygame.Surface | callable() -> Surface | None,
              'image_caption': str | None,
              'image_frame': bool | None}]
    win = TutorialWindowDialogue(window, pages, title='...')
    # in the event loop:
    if win.update(events) == 'done':
        win = None
"""

import pygame

from config import settings
from game.components.dialogue_box import (
    _DlgButton,
    _responsive_dialogue_button_metrics,
)


def _tutorial_rect(height_ratio, presentation='modal'):
    """Responsive teaching geometry.

    ``map_sidecar`` leaves a useful part of the background map exposed: a
    right-hand teaching rail in landscape and a bottom sheet in portrait.
    Other tutorials remain centered and use nearly all of a phone canvas.
    """
    _SW = settings.SCREEN_WIDTH
    _SH = settings.SCREEN_HEIGHT
    mobile = getattr(settings, 'TOUCH_TARGET_MIN', 0) > 0
    small = _SW < 700 or mobile

    if presentation == 'map_sidecar' and mobile:
        if _SW >= _SH:
            margin_x = max(10, int(0.018 * _SW))
            margin_y = max(8, int(0.03 * _SH))
            box_w = min(_SW - margin_x * 2, max(340, int(0.43 * _SW)))
            box_h = min(_SH - margin_y * 2, int(0.94 * _SH))
            return pygame.Rect(
                _SW - margin_x - box_w,
                (_SH - box_h) // 2,
                box_w,
                box_h,
            )
        margin_x = max(10, int(0.04 * _SW))
        margin_y = max(10, int(0.025 * _SH))
        box_w = _SW - margin_x * 2
        box_h = min(int(0.48 * _SH), _SH - margin_y * 2)
        return pygame.Rect(
            margin_x,
            _SH - margin_y - box_h,
            box_w,
            box_h,
        )

    if mobile:
        margin_x = max(12, int((0.03 if _SW >= _SH else 0.05) * _SW))
        width_ratio = 0.94 if _SW >= _SH else 0.90
        box_w = min(int(width_ratio * _SW), _SW - margin_x * 2)
    elif small:
        margin_x = max(12, int(0.05 * _SW))
        box_w = min(int(0.86 * _SW), _SW - margin_x * 2)
    else:
        box_w = settings.DIALOGUE_BOX_WIDTH
    box_h = int(height_ratio * _SH)
    if mobile:
        box_h = min(int(0.88 * _SH), max(box_h, int(0.86 * _SH)))
    elif small:
        box_h = min(int(0.82 * _SH), max(box_h, int(0.72 * _SH)))
    x = (_SW - box_w) // 2
    y = max(int(0.02 * _SH), (_SH - box_h) // 2)
    return pygame.Rect(x, y, box_w, box_h)


def _wrap_text(text, font, max_w):
    words = str(text or '').split()
    lines, cur = [], ''
    for word in words:
        trial = (cur + ' ' + word).strip()
        if font.size(trial)[0] <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _draw_vscrollbar(window, panel_rect, top, avail_h, content_h, scroll,
                     max_scroll, accent, obj=None):
    """A slim vertical scrollbar on the right edge of a panel's content area.

    When ``obj`` is given, the thumb/track geometry is stashed on it so the
    event handler can drag the thumb directly (a real scrollbar where the thumb
    follows the cursor), instead of grab-scrolling the content the opposite way.
    """
    if content_h <= 0 or max_scroll <= 0:
        if obj is not None:
            obj._scroll_track_rect = None
        return
    w = max(4, int(0.009 * settings.SCREEN_WIDTH))
    x = panel_rect.right - w - int(0.012 * settings.SCREEN_WIDTH)
    thumb_h = max(20, int(avail_h * avail_h / content_h))
    max_off = max(1, avail_h - thumb_h)
    frac = (scroll / max_scroll) if max_scroll else 0
    thumb_y = int(frac * max_off)
    bar = pygame.Surface((w, avail_h), pygame.SRCALPHA)
    pygame.draw.rect(bar, (255, 255, 255, 26), bar.get_rect(), border_radius=w // 2)
    pygame.draw.rect(bar, (*accent, 200), (0, thumb_y, w, thumb_h), border_radius=w // 2)
    window.blit(bar, (x, top))
    if obj is not None:
        touch_w = getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0
        hit_pad = max(w, (touch_w - w + 1) // 2)
        obj._scroll_track_rect = pygame.Rect(
            x - hit_pad, top, w + 2 * hit_pad, avail_h)
        obj._scroll_track_top = top
        obj._scroll_thumb_h = thumb_h
        obj._scroll_thumb_top = top + thumb_y
        obj._scroll_max_off = max_off


def _set_scroll_from_thumb(obj, y):
    """Map a pointer Y on the scrollbar track to a scroll offset so the thumb
    follows the cursor (drag the bar down → scroll down)."""
    top = getattr(obj, '_scroll_track_top', None)
    max_off = getattr(obj, '_scroll_max_off', 0)
    if top is None or max_off <= 0:
        return
    grab = getattr(obj, '_scroll_grab_offset', 0)
    frac = max(0.0, min(1.0, (y - top - grab) / max_off))
    obj._scroll = frac * obj._max_scroll


def _apply_wheel_drag_scroll(events, content_rect, obj):
    """Update ``obj``'s scroll fields (_scroll/_max_scroll/_dragging/
    _drag_last_y/_drag_moved) from wheel + drag events, clamped to
    [0, _max_scroll]. Shared by the scrollable dialogues below.

    Dragging the scrollbar moves the thumb under the cursor; dragging elsewhere
    in the content grab-scrolls (touch-style)."""
    if obj._max_scroll <= 0:
        obj._scroll = 0.0
        obj._dragging = False
        obj._scrollbar_dragging = False
        return
    step = max(24, int(0.045 * settings.SCREEN_HEIGHT))
    track = getattr(obj, '_scroll_track_rect', None)
    for event in events:
        et = getattr(event, 'type', None)
        if et == pygame.MOUSEWHEEL:
            obj._scroll -= getattr(event, 'y', 0) * step
        elif et == pygame.MOUSEBUTTONDOWN and getattr(event, 'button', 0) == 1:
            pos = getattr(event, 'pos', pygame.mouse.get_pos())
            if track is not None and track.collidepoint(pos):
                # Scrollbar drag: the thumb tracks the cursor. If the press
                # lands on the thumb, keep its grab offset; otherwise centre the
                # thumb under the cursor (page jump).
                obj._scrollbar_dragging = True
                obj._drag_moved = True
                thumb_top = getattr(obj, '_scroll_thumb_top', pos[1])
                thumb_h = getattr(obj, '_scroll_thumb_h', 0)
                if thumb_top <= pos[1] <= thumb_top + thumb_h:
                    obj._scroll_grab_offset = pos[1] - thumb_top
                else:
                    obj._scroll_grab_offset = thumb_h / 2
                _set_scroll_from_thumb(obj, pos[1])
            elif content_rect.collidepoint(pos):
                obj._dragging = True
                obj._drag_last_y = pos[1]
                obj._drag_moved = False
        elif et == pygame.MOUSEMOTION:
            pos = getattr(event, 'pos', pygame.mouse.get_pos())
            if getattr(obj, '_scrollbar_dragging', False):
                _set_scroll_from_thumb(obj, pos[1])
            elif obj._dragging:
                dy = pos[1] - obj._drag_last_y
                if abs(dy) > 2:
                    obj._drag_moved = True
                obj._scroll -= dy
                obj._drag_last_y = pos[1]
        elif et == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
            obj._dragging = False
            obj._scrollbar_dragging = False
    obj._scroll = max(0, min(obj._scroll, obj._max_scroll))


class TutorialWindowDialogue:
    def __init__(self, window, pages, *, title=None, presentation='modal'):
        self.window = window
        self.title = title or ''
        self.presentation = presentation
        self.background_interactive = presentation == 'map_sidecar'
        self.pages = [p for p in (pages or []) if p]
        self.page_index = 0
        self._created_at = pygame.time.get_ticks()

        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        # The window title is a small "kicker"; the per-page title is the big,
        # catchy headline.
        self.kicker_font = settings.get_font(
            getattr(settings, 'FS_SMALL', settings.FONT_SIZE_DIALOGUE_BOX))
        self.headline_font = settings.get_font(
            settings.FONT_SIZE_TITLE_DIALOGUE_BOX, bold=True)
        self.font = settings.get_font(settings.FONT_SIZE_DIALOGUE_BOX)
        self.caption_font = settings.get_font(getattr(settings, 'FS_TINY', 14))
        # Warm accent for headlines/captions; falls back to the title colour.
        self._accent = getattr(settings, 'TITLE_TEXT_COLOR', (240, 210, 140))

        self.rect = _tutorial_rect(0.66, presentation)
        self.x, self.y = self.rect.topleft
        box_w, box_h = self.rect.size

        _corner_r = settings.DIALOGUE_BOX_CORNER_R
        self._panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(self._panel, settings.DIALOGUE_BOX_BG_CLR,
                         self._panel.get_rect(), border_radius=_corner_r)
        pygame.draw.rect(self._panel, settings.DIALOGUE_BOX_BORDER_CLR,
                         self._panel.get_rect(),
                         settings.DIALOGUE_BOX_BORDER_WIDTH, border_radius=_corner_r)
        self._overlay = None
        if not self.background_interactive:
            self._overlay = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
            self._overlay.fill(settings.DIALOGUE_BOX_OVERLAY_CLR)

        btn_w, btn_h, margin = _responsive_dialogue_button_metrics()
        side_margin = max(10, int(0.02 * _SW))
        # Narrow sidecars must always keep both controls inside the panel.
        btn_w = min(btn_w, max(1, (self.rect.w - side_margin * 3) // 2))
        btn_y = self.rect.bottom - btn_h - margin
        self._btn_back = _DlgButton(
            window, self.rect.x + side_margin, btn_y, 'Back',
            width=btn_w, height=btn_h)
        next_x = self.rect.right - side_margin - btn_w
        if len(self.pages) <= 1:
            next_x = self.rect.centerx - btn_w // 2
        self._btn_next = _DlgButton(
            window, next_x, btn_y, 'Next',
            width=btn_w, height=btn_h)
        self._btn_y = btn_y
        self._btn_w = btn_w
        self._btn_h = btn_h

        # Scroll state: pages taller than the content area scroll (wheel/drag)
        # instead of being shrunk to fit.
        self._scroll = 0.0
        self._max_scroll = 0
        self._content_rect = pygame.Rect(self.rect.x, self.rect.y, self.rect.w, 0)
        self._dragging = False
        self._drag_last_y = 0
        self._drag_moved = False
        self._scrollbar_dragging = False
        self._scroll_track_rect = None

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _wrap(text, font, max_w):
        return _wrap_text(text, font, max_w)

    def _page_image(self, page):
        img = page.get('image')
        if callable(img):
            try:
                img = img()
            except Exception:
                img = None
        return img if isinstance(img, pygame.Surface) else None

    @property
    def _is_last(self):
        return self.page_index >= len(self.pages) - 1

    def captures_event(self, event):
        """Whether an event belongs to this window instead of its background.

        Normal teaching windows are modal.  A map sidecar only owns pointer
        gestures that start over its panel, leaving the exposed map usable.
        An active content/scrollbar drag remains captured through release even
        if the pointer strays outside the panel.
        """
        if not self.background_interactive:
            return True
        event_type = getattr(event, 'type', None)
        pointer_types = {
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION,
            pygame.MOUSEWHEEL,
        }
        multi_gesture = getattr(pygame, 'MULTIGESTURE', None)
        if multi_gesture is not None:
            pointer_types.add(multi_gesture)
        if event_type not in pointer_types:
            return True
        if (getattr(self, '_dragging', False)
                or getattr(self, '_scrollbar_dragging', False)):
            return True
        if event_type == multi_gesture:
            x = int(float(getattr(event, 'x', 0.5) or 0.5)
                    * settings.SCREEN_WIDTH)
            y = int(float(getattr(event, 'y', 0.5) or 0.5)
                    * settings.SCREEN_HEIGHT)
            return self.rect.collidepoint((x, y))
        pos = getattr(event, 'pos', None) or pygame.mouse.get_pos()
        return self.rect.collidepoint(pos)

    # ── update / draw ────────────────────────────────────────────────
    def _goto_page(self, idx):
        self.page_index = max(0, min(len(self.pages) - 1, idx))
        self._scroll = 0.0  # each page starts at the top

    def _handle_scroll(self, events):
        """Wheel + drag scrolling for pages taller than the content area."""
        _apply_wheel_drag_scroll(events, self._content_rect, self)

    def update(self, events):
        self._btn_back.disabled = self.page_index == 0
        self._btn_back.update()
        self._btn_next.update()
        self._handle_scroll(events)
        if pygame.time.get_ticks() - self._created_at < 200:
            return None
        for event in events:
            if event.type == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                # A drag-release inside the content area is a scroll, not a tap.
                if self._drag_moved:
                    self._drag_moved = False
                    continue
                if not self._btn_back.disabled and self._btn_back.collide(pos):
                    from utils import sound
                    sound.play('ui_back')
                    self._goto_page(self.page_index - 1)
                    return None
                if self._btn_next.collide(pos):
                    from utils import sound
                    sound.play('ui_click')
                    if self._is_last:
                        return 'done'
                    self._goto_page(self.page_index + 1)
                    return None
        return None

    def _scaled_image(self, page):
        """Page image scaled to a generous, layout-aware box (or None)."""
        img = self._page_image(page)
        if img is None:
            return None
        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        # 'image_top' treats the image as a hero, so allow it to be larger.
        hero = page.get('layout', 'image_top') in ('image_top', 'image_only')

        if not page.get('image_frame', True):
            # Pre-framed illustrations (img/tutorial banners) carry their own
            # border, so they skip the window's frame and get a larger box. They
            # are scaled in a single pass straight from the source — up to fill
            # the box, or down if oversized — for a bigger, crisper result.
            mobile = getattr(settings, 'TOUCH_TARGET_MIN', 0) > 0
            max_w = self.rect.w - int((0.04 if mobile else 0.06) * _SW)
            max_h = int((0.34 if hero else 0.26) * _SH)
            ratio = min(max_w / img.get_width(), max_h / img.get_height())
            return pygame.transform.smoothscale(
                img, (max(1, int(img.get_width() * ratio)),
                      max(1, int(img.get_height() * ratio))))

        mobile = getattr(settings, 'TOUCH_TARGET_MIN', 0) > 0
        max_w = self.rect.w - int((0.06 if mobile else 0.14) * _SW)
        max_h_ratio = page.get(
            'image_max_height_ratio',
            0.30 if hero else 0.22,
        )
        max_h = int(max_h_ratio * _SH)
        if img.get_width() > max_w or img.get_height() > max_h:
            ratio = min(max_w / img.get_width(), max_h / img.get_height())
            img = pygame.transform.smoothscale(
                img, (max(1, int(img.get_width() * ratio)),
                      max(1, int(img.get_height() * ratio))))
        return img

    def _content_region(self):
        """Return ``(top_y, height)`` of the area between the header and the
        page-dots/buttons — the room available to the page content. Mirrors the
        geometry used in :meth:`draw`."""
        _SH = settings.SCREEN_HEIGHT
        top = self.rect.y + settings.DIALOGUE_BOX_TEXT_MARGIN_Y
        if self.title:
            top += self.kicker_font.get_height() + int(0.010 * _SH)
        header_bottom = top + int(0.018 * _SH)
        dots_top = self._btn_y - int(0.03 * _SH)
        return header_bottom, max(1, dots_top - header_bottom)

    def _page_rows(self, page):
        """Ordered (surface, kind, gap_after) blocks for the current page.

        The image/text order is per-page via ``layout``: 'image_top' (default),
        'image_bottom', 'text_only', 'image_only', or 'text_image_text' (text
        above AND below the image; the below text comes from ``lines_below``).
        """
        _SH = settings.SCREEN_HEIGHT
        _SW = settings.SCREEN_WIDTH
        block_gap = int(0.024 * _SH)
        line_gap = int(0.006 * _SH)

        max_w = self.rect.w - int(0.10 * _SW)
        headline_surfs = []
        if page.get('title'):
            for line in _wrap_text(page['title'], self.headline_font, max_w):
                headline_surfs.append(self.headline_font.render(line, True, self._accent))
        img = self._scaled_image(page)
        cap_surfs = []
        if img is not None and page.get('image_caption'):
            for line in _wrap_text(page['image_caption'], self.caption_font, max_w):
                cap_surfs.append(self.caption_font.render(
                    line, True, settings.DIALOGUE_BOX_MSG_TEXT_CLR))

        def render_lines(key):
            out = []
            for raw in page.get(key, []) or []:
                for line in self._wrap(raw, self.font, max_w):
                    out.append(self.font.render(
                        line, True, settings.DIALOGUE_BOX_MSG_TEXT_CLR))
            return out

        text_surfs = render_lines('lines')
        below_surfs = render_lines('lines_below')

        # The image draws a backing panel that extends ~0.012*SW below it, so a
        # caption needs a gap larger than that to sit clear of the panel border.
        caption_gap = int(0.022 * _SW)

        def image_block():
            blocks = []
            if img is not None:
                kind = 'image' if page.get('image_frame', True) else 'image_plain'
                blocks.append((img, kind, caption_gap if cap_surfs else block_gap))
                for idx, cap in enumerate(cap_surfs):
                    gap = line_gap if idx < len(cap_surfs) - 1 else block_gap
                    blocks.append((cap, 'caption', gap))
            return blocks

        def text_block(surfs):
            return [(s, 'text', line_gap) for s in surfs]

        layout = page.get('layout', 'image_top')
        rows = []
        for idx, headline in enumerate(headline_surfs):
            gap = line_gap if idx < len(headline_surfs) - 1 else block_gap
            rows.append((headline, 'headline', gap))
        if layout == 'text_only':
            rows += text_block(text_surfs)
        elif layout == 'image_only':
            rows += image_block()
        elif layout == 'text_image_text':
            rows += text_block(text_surfs)
            if text_surfs and img is not None:
                s, k, _ = rows[-1]
                rows[-1] = (s, k, block_gap)
            rows += image_block()
            rows += text_block(below_surfs)
        elif layout == 'image_bottom':
            rows += text_block(text_surfs)
            if text_surfs and (img is not None):
                # promote the gap before the image to a block gap
                s, k, _ = rows[-1]
                rows[-1] = (s, k, block_gap)
            rows += image_block()
        else:  # image_top
            rows += image_block()
            rows += text_block(text_surfs)

        # Pre-framed banners are sized to fill the box, but the page text varies
        # in length; if the whole page would overflow (and scroll), shrink the
        # banner — rescaled from its native source so it stays single-pass crisp
        # — until the page fits.
        if img is not None and not page.get('image_frame', True):
            rows = self._fit_frameless_banner(page, img, rows)
        return rows

    def _fit_frameless_banner(self, page, scaled_img, rows):
        _, avail_h = self._content_region()
        content_h = (sum(s.get_height() for s, _, _ in rows)
                     + sum(g for _, _, g in rows[:-1]))
        overflow = content_h - avail_h
        if overflow <= 0:
            return rows
        native = self._page_image(page)
        if native is None:
            return rows
        target_h = max(int(0.16 * settings.SCREEN_HEIGHT),
                       scaled_img.get_height() - overflow)
        if target_h >= scaled_img.get_height():
            return rows
        ratio = target_h / native.get_height()
        fitted = pygame.transform.smoothscale(
            native, (max(1, int(native.get_width() * ratio)), max(1, target_h)))
        return [(fitted if surf is scaled_img else surf, kind, gap)
                for surf, kind, gap in rows]

    def draw(self):
        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        if self._overlay is not None:
            self.window.blit(self._overlay, (0, 0))
        self.window.blit(self._panel, self.rect.topleft)

        # ── Header: small kicker + accent rule ──
        top = self.rect.y + settings.DIALOGUE_BOX_TEXT_MARGIN_Y
        if self.title:
            ks = self.kicker_font.render(self.title.upper(), True, self._accent)
            self.window.blit(ks, ks.get_rect(center=(self.rect.centerx, top + ks.get_height() // 2)))
            top += ks.get_height() + int(0.010 * _SH)
        rule_w = int(self.rect.w * 0.18)
        pygame.draw.line(self.window, settings.DIALOGUE_BOX_SEP_CLR,
                         (self.rect.centerx - rule_w // 2, top),
                         (self.rect.centerx + rule_w // 2, top), 2)
        header_bottom = top + int(0.018 * _SH)

        # ── Content: vertically centered between header and the controls ──
        page = self.pages[self.page_index] if self.pages else {}
        rows = self._page_rows(page)
        dots_top = self._btn_y - int(0.03 * _SH)
        avail_top = header_bottom
        avail_h = dots_top - avail_top

        def _content_h(rs):
            return (sum(s.get_height() for s, _, _ in rs)
                    + (sum(g for _, _, g in rs[:-1]) if rs else 0))

        # Pages taller than the content area scroll (wheel/drag) rather than
        # being shrunk to fit, so content gets all the room it needs.
        content_h = _content_h(rows)
        avail_h = max(1, avail_h)
        self._content_rect = pygame.Rect(self.rect.x, avail_top, self.rect.w, avail_h)
        self._max_scroll = max(0, content_h - avail_h)
        # Ignore a sub-line sliver of overflow so a page that essentially fits
        # (e.g. the single-page welcome window) never shows a near-empty
        # scrollbar — a few pixels of difference can come from font-height
        # rounding that varies by platform/backend. The overflow falls into the
        # gap above the buttons, so nothing visible is clipped.
        if self._max_scroll <= max(2, int(0.014 * _SH)):
            self._max_scroll = 0
        self._scroll = max(0, min(self._scroll, self._max_scroll))

        if self._max_scroll > 0:
            self.window.set_clip(self._content_rect)
            y = avail_top - int(self._scroll)
        else:
            y = avail_top + max(0, (avail_h - content_h) // 2)

        for surf, kind, gap in rows:
            r = surf.get_rect(midtop=(self.rect.centerx, y))
            if kind == 'image':
                pad = int(0.012 * _SW)
                bg = pygame.Rect(r.x - pad, r.y - pad // 2,
                                 r.w + pad * 2, r.h + pad)
                panel = pygame.Surface((bg.w, bg.h), pygame.SRCALPHA)
                pygame.draw.rect(panel, (0, 0, 0, 60), panel.get_rect(), border_radius=10)
                pygame.draw.rect(panel, (*self._accent, 90), panel.get_rect(), 1, border_radius=10)
                self.window.blit(panel, bg.topleft)
            self.window.blit(surf, r.topleft)
            y += surf.get_height() + gap

        if self._max_scroll > 0:
            self.window.set_clip(None)
            self._draw_scrollbar(avail_top, avail_h, content_h)

        # ── Page dots ──
        if len(self.pages) > 1:
            dot_r = max(3, int(0.005 * _SH))
            gap = dot_r * 3
            total = (len(self.pages) - 1) * gap
            dx = self.rect.centerx - total // 2
            dy = self._btn_y - int(0.02 * _SH)
            for i in range(len(self.pages)):
                col = self._accent if i == self.page_index else settings.DIALOGUE_BOX_SEP_CLR
                pygame.draw.circle(self.window, col, (dx + i * gap, dy), dot_r)

        # ── Buttons (the last page may supply a specific action label) ──
        page = self.pages[self.page_index] if self.pages else {}
        if self._is_last:
            self._btn_next.text = page.get('button_label') or 'Got it'
        else:
            self._btn_next.text = 'Next'
        if self.page_index > 0:
            self._btn_back.draw()
        self._btn_next.draw()

    def _draw_scrollbar(self, avail_top, avail_h, content_h):
        _draw_vscrollbar(self.window, self.rect, avail_top, avail_h, content_h,
                         self._scroll, self._max_scroll, self._accent, obj=self)

    def get_tooltip(self, pos):
        return ''


# Spin tuning for the starter-suit reveal.
_REEL_SPIN_MS = 1400
_REEL_TICK_MS = 90

# Stable card-game facts; kept local so the client UI does not depend on
# server-only settings.
_OFFENSIVE_SUITS = ('Hearts', 'Diamonds')
_DEFENSIVE_SUITS = ('Clubs', 'Spades')
# All four suits cycle on the reel; the player is seeded an offensive suit but
# the reveal is framed as a draw "from all four suits".
_ALL_SUITS = ('Hearts', 'Diamonds', 'Clubs', 'Spades')
class StarterSuitRevealDialogue:
    """One-armed-bandit reveal of the player's starter suit.

    The reel spins through all four suit icons, settles on the player's
    assigned suit, then announces the granted starter set. Presented as a draw
    "from all four suits" (new players are seeded an offensive suit, but the
    reveal does not label it as such). ``update`` returns ``'revealed'`` once
    when the reel settles, then ``'done'`` after the result is acknowledged.
    """

    def __init__(self, window, suit, *, done_label='Got it', wait_for_grant=False):
        self.window = window
        self.suit = suit
        self.done_label = done_label
        self._grant_status = 'pending' if wait_for_grant else 'confirmed'
        self._created_at = pygame.time.get_ticks()
        self._phase = 'spin'   # spin -> done
        self._phase_started = self._created_at
        self._reveal_notified = False
        # The click that opens the reel is already covered by the tutorial
        # button. Start ticking on the first visible suit change, not at t=0.
        self._last_reel_tick_index = 0

        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        self.title_font = settings.get_font(
            settings.FONT_SIZE_TITLE_DIALOGUE_BOX, bold=True)
        self.font = settings.get_font(settings.FONT_SIZE_DIALOGUE_BOX)
        self.caption_font = settings.get_font(getattr(settings, 'FS_TINY', 14))

        self.rect = _tutorial_rect(0.68)
        self.x, self.y = self.rect.topleft
        box_w, box_h = self.rect.size

        _corner_r = settings.DIALOGUE_BOX_CORNER_R
        self._panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(self._panel, settings.DIALOGUE_BOX_BG_CLR,
                         self._panel.get_rect(), border_radius=_corner_r)
        pygame.draw.rect(self._panel, settings.DIALOGUE_BOX_BORDER_CLR,
                         self._panel.get_rect(),
                         settings.DIALOGUE_BOX_BORDER_WIDTH, border_radius=_corner_r)
        self._overlay = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
        self._overlay.fill(settings.DIALOGUE_BOX_OVERLAY_CLR)

        btn_w, btn_h, margin = _responsive_dialogue_button_metrics()
        btn_w = min(btn_w, max(1, self.rect.w - int(0.08 * _SW)))
        self._btn = _DlgButton(
            window, self.rect.centerx - btn_w // 2,
            self.rect.bottom - btn_h - margin, 'Reveal',
            width=btn_w, height=btn_h)

        # Scroll state for the (large) starter-set breakdown.
        self._scroll = 0.0
        self._max_scroll = 0
        self._content_rect = pygame.Rect(self.rect.x, self.rect.y, self.rect.w, 0)
        self._dragging = False
        self._drag_last_y = 0
        self._drag_moved = False
        self._scrollbar_dragging = False
        self._scroll_track_rect = None

    def _draw_centered_lines(self, lines, font, color, y, *, gap=None):
        max_w = self.rect.w - int(0.08 * settings.SCREEN_WIDTH)
        line_surfs = []
        for raw in lines:
            for line in _wrap_text(raw, font, max_w):
                line_surfs.append(font.render(line, True, color))
        if gap is None:
            gap = int(0.004 * settings.SCREEN_HEIGHT)
        for surf in line_surfs:
            self.window.blit(
                surf,
                surf.get_rect(center=(self.rect.centerx, y + surf.get_height() // 2)),
            )
            y += surf.get_height() + gap
        return y

    def _advance_spin(self):
        """Advance the audible reel and settle it once its time has elapsed."""
        now = pygame.time.get_ticks()
        if self._phase != 'spin':
            return
        elapsed = max(0, now - self._phase_started)
        if elapsed < _REEL_SPIN_MS:
            tick_index = elapsed // _REEL_TICK_MS
            if tick_index > self._last_reel_tick_index:
                self._last_reel_tick_index = tick_index
                from utils import sound
                sound.play('tally_tick', volume=0.35)
            return
        if elapsed >= _REEL_SPIN_MS:
            self._phase = 'done'
            # Normal callers wait for the server grant before celebrating.
            # The confirmed-by-construction mode is retained for standalone
            # uses and tests, so it gets its landing cue here.
            if self._grant_status == 'confirmed':
                from utils import sound
                sound.play('reward_reveal', volume=0.8)

    def _current_reel_suit(self):
        """The suit icon to show right now (cycling all four while spinning)."""
        if self._phase == 'spin':
            idx = ((pygame.time.get_ticks() - self._phase_started) // _REEL_TICK_MS) % len(_ALL_SUITS)
            return _ALL_SUITS[idx]
        return self.suit

    def update(self, events):
        self._advance_spin()
        self._btn.disabled = (
            self._phase == 'spin' or self._grant_status == 'pending')
        self._btn.update()
        _apply_wheel_drag_scroll(events, self._content_rect, self)
        if self._phase == 'done' and not self._reveal_notified:
            self._reveal_notified = True
            return 'revealed'
        if pygame.time.get_ticks() - self._created_at < 200:
            return None
        for event in events:
            if event.type == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                if self._btn.disabled or not self._btn.collide(pos):
                    continue
                if self._phase == 'done':
                    from utils import sound
                    sound.play('ui_click')
                    if self._grant_status == 'failed':
                        return 'retry'
                    return 'done'
        return None

    def set_grant_result(self, success):
        """Unlock the truthful result view, or expose an explicit retry."""
        self._grant_status = 'confirmed' if success else 'failed'
        from utils import sound
        sound.play('reward_reveal' if success else 'error',
                   volume=0.8 if success else 0.65)

    def _sized_breakdown(self, td, max_w):
        """The starter-set breakdown rendered to fill ``max_w`` so the cards and
        icons are large; the reveal then scrolls it vertically."""
        _SH = settings.SCREEN_HEIGHT
        ref_h = int(0.085 * _SH)
        ref = td.starter_set_breakdown('offensive', self.suit, ref_h)
        if ref is None or ref.get_width() <= 0:
            return ref
        target = int(ref_h * max_w / ref.get_width())
        target = max(ref_h, min(int(0.13 * _SH), target))
        bd = td.starter_set_breakdown('offensive', self.suit, target)
        if bd.get_width() > max_w:  # safety clamp
            r = max_w / bd.get_width()
            bd = pygame.transform.smoothscale(
                bd, (max_w, max(1, int(bd.get_height() * r))))
        return bd

    def draw(self):
        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        from game.components import tutorial_diagrams
        self.window.blit(self._overlay, (0, 0))
        self.window.blit(self._panel, self.rect.topleft)

        y = self.rect.y + settings.DIALOGUE_BOX_TEXT_MARGIN_Y
        settled = self._phase == 'done'
        ts = self.title_font.render('Your Starter Suit', True, settings.TITLE_TEXT_COLOR)
        self.window.blit(ts, ts.get_rect(center=(self.rect.centerx, y + ts.get_height() // 2)))
        y += ts.get_height() + int(0.018 * _SH)

        # Spinning: a big reel icon. Settled: a smaller icon to leave room for
        # the (scrollable) breakdown of cards the player gained.
        icon_sz = int((0.08 if settled else 0.16) * _SH)
        ic = tutorial_diagrams.suit_icon(self._current_reel_suit(), icon_sz)
        if ic:
            self.window.blit(ic, ic.get_rect(center=(self.rect.centerx, y + icon_sz // 2)))
        y += icon_sz + int(0.014 * _SH)

        if settled and self._grant_status == 'confirmed':
            y = self._draw_centered_lines(
                [f'{self.suit} is your starter suit!'], self.font,
                settings.TITLE_TEXT_COLOR, y)
            y += int(0.004 * _SH)
            # Make clear these are GAINED starter cards, not just shown.
            y = self._draw_centered_lines(
                ['These starter cards are added to your collection:'],
                self.caption_font,
                settings.DIALOGUE_BOX_MSG_TEXT_CLR,
                y,
            )
            y += int(0.004 * _SH)
            # Cards mapped to the figures / spell / tactics they build. Rendered
            # large (filling the panel width) and SCROLLED vertically, so the
            # cards and icons stay big instead of being shrunk to fit.
            max_w = self.rect.w - int(0.06 * _SW)
            breakdown = self._sized_breakdown(tutorial_diagrams, max_w)
            if breakdown is not None:
                content_top = y
                content_h = max(1, self._btn.rect.top - content_top - int(0.02 * _SH))
                self._content_rect = pygame.Rect(
                    self.rect.x, content_top, self.rect.w, content_h)
                bw, bh = breakdown.get_size()
                self._max_scroll = max(0, bh - content_h)
                self._scroll = max(0, min(self._scroll, self._max_scroll))
                bx = self.rect.centerx - bw // 2
                if self._max_scroll > 0:
                    self.window.set_clip(self._content_rect)
                    self.window.blit(breakdown, (bx, content_top - int(self._scroll)))
                    self.window.set_clip(None)
                    _draw_vscrollbar(self.window, self.rect, content_top, content_h,
                                     bh, self._scroll, self._max_scroll,
                                     settings.TITLE_TEXT_COLOR, obj=self)
                else:
                    self.window.blit(
                        breakdown, (bx, content_top + max(0, (content_h - bh) // 2)))
        elif not settled:
            spin = self.font.render('Drawing from all four suits…', True,
                                    settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            self.window.blit(spin, spin.get_rect(center=(self.rect.centerx, y + spin.get_height() // 2)))
        else:
            status = (
                'Adding your starter cards…'
                if self._grant_status == 'pending'
                else 'Could not add your starter cards. Please retry.'
            )
            y = self._draw_centered_lines(
                [f'{self.suit} is your starter suit!', status],
                self.font,
                settings.DIALOGUE_BOX_MSG_TEXT_CLR,
                y,
            )

        if self._btn.disabled:
            self._btn.text = '…'
        elif self._grant_status == 'failed':
            self._btn.text = 'Retry'
        else:
            self._btn.text = self.done_label
        self._btn.draw()

    def get_tooltip(self, pos):
        return ''
