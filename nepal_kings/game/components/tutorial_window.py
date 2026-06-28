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
from game.components.dialogue_box import _DlgButton


def _tutorial_rect(height_ratio):
    """Dialogue geometry tuned for teaching windows, especially phone portrait."""
    _SW = settings.SCREEN_WIDTH
    _SH = settings.SCREEN_HEIGHT
    small = _SW < 700 or getattr(settings, 'TOUCH_TARGET_MIN', 0) > 0
    if small:
        margin_x = max(12, int(0.05 * _SW))
        box_w = min(int(0.86 * _SW), _SW - margin_x * 2)
    else:
        box_w = settings.DIALOGUE_BOX_WIDTH
    box_h = int(height_ratio * _SH)
    if small:
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
                     max_scroll, accent):
    """A slim vertical scrollbar on the right edge of a panel's content area."""
    if content_h <= 0 or max_scroll <= 0:
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


def _apply_wheel_drag_scroll(events, content_rect, obj):
    """Update ``obj``'s scroll fields (_scroll/_max_scroll/_dragging/
    _drag_last_y/_drag_moved) from wheel + drag events, clamped to
    [0, _max_scroll]. Shared by the scrollable dialogues below."""
    if obj._max_scroll <= 0:
        obj._scroll = 0.0
        obj._dragging = False
        return
    step = max(24, int(0.045 * settings.SCREEN_HEIGHT))
    for event in events:
        et = getattr(event, 'type', None)
        if et == pygame.MOUSEWHEEL:
            obj._scroll -= getattr(event, 'y', 0) * step
        elif et == pygame.MOUSEBUTTONDOWN and getattr(event, 'button', 0) == 1:
            pos = getattr(event, 'pos', pygame.mouse.get_pos())
            if content_rect.collidepoint(pos):
                obj._dragging = True
                obj._drag_last_y = pos[1]
                obj._drag_moved = False
        elif et == pygame.MOUSEMOTION and obj._dragging:
            pos = getattr(event, 'pos', pygame.mouse.get_pos())
            dy = pos[1] - obj._drag_last_y
            if abs(dy) > 2:
                obj._drag_moved = True
            obj._scroll -= dy
            obj._drag_last_y = pos[1]
        elif et == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
            obj._dragging = False
    obj._scroll = max(0, min(obj._scroll, obj._max_scroll))


class TutorialWindowDialogue:
    def __init__(self, window, pages, *, title=None):
        self.window = window
        self.title = title or ''
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

        self.rect = _tutorial_rect(0.66)
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

        btn_w = settings.DIALOGUE_BOX_BTN_W
        btn_h = settings.DIALOGUE_BOX_BTN_H
        margin = settings.DIALOGUE_BOX_BTN_MARGIN_BOTTOM
        btn_y = self.rect.bottom - btn_h - margin
        self._btn_back = _DlgButton(
            window, self.rect.x + int(0.04 * _SW), btn_y, 'Back',
            width=btn_w, height=btn_h)
        self._btn_next = _DlgButton(
            window, self.rect.right - int(0.04 * _SW) - btn_w, btn_y, 'Next',
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

        # Cache the fitted page image per page so the (supersampled) diagram is
        # composed and scaled once, not every frame.
        self._scaled_image_cache = {}

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _wrap(text, font, max_w):
        return _wrap_text(text, font, max_w)

    def _page_image(self, page):
        img = page.get('image')
        if callable(img):
            try:
                # Diagram factories compose from screen-relative metrics, so
                # render them supersampled for crisper art on large canvases.
                from game.components import tutorial_diagrams
                img = tutorial_diagrams.render_supersampled(img)
            except Exception:
                img = None
        return img if isinstance(img, pygame.Surface) else None

    @property
    def _is_last(self):
        return self.page_index >= len(self.pages) - 1

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
                if not self._btn_back.disabled and self._btn_back.rect.collidepoint(pos):
                    self._goto_page(self.page_index - 1)
                    return None
                if self._btn_next.rect.collidepoint(pos):
                    if self._is_last:
                        return 'done'
                    self._goto_page(self.page_index + 1)
                    return None
        return None

    def _scaled_image(self, page):
        """Page image scaled to a generous, layout-aware box (or None).

        Cached per page (keyed by ``page_index``); ``_page_rows`` only ever asks
        for the current page, so this avoids recomposing/rescaling each frame.
        """
        cache_key = self.page_index
        if cache_key in self._scaled_image_cache:
            return self._scaled_image_cache[cache_key]
        img = self._page_image(page)
        if img is None:
            self._scaled_image_cache[cache_key] = None
            return None
        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        max_w = self.rect.w - int(0.14 * _SW)
        # 'image_top' treats the image as a hero, so allow it to be larger.
        hero = page.get('layout', 'image_top') in ('image_top', 'image_only')
        max_h = int((0.30 if hero else 0.22) * _SH)
        if img.get_width() > max_w or img.get_height() > max_h:
            ratio = min(max_w / img.get_width(), max_h / img.get_height())
            img = pygame.transform.smoothscale(
                img, (max(1, int(img.get_width() * ratio)),
                      max(1, int(img.get_height() * ratio))))
        self._scaled_image_cache[cache_key] = img
        return img

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
        return rows

    def draw(self):
        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
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

        # ── Buttons (Next becomes Got it on the last page) ──
        self._btn_next.text = 'Got it' if self._is_last else 'Next'
        if self.page_index > 0:
            self._btn_back.draw()
        self._btn_next.draw()

    def _draw_scrollbar(self, avail_top, avail_h, content_h):
        _draw_vscrollbar(self.window, self.rect, avail_top, avail_h, content_h,
                         self._scroll, self._max_scroll, self._accent)

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
# The granted starter set (mirrors server_settings STARTER_OFFENSIVE_SET).
_OFFENSIVE_SET_RANKS = ['K', 'A', 'J', '7', '7', '8', '8', '9', '10']


class StarterSuitRevealDialogue:
    """One-armed-bandit reveal of the player's starter suit.

    The reel spins through all four suit icons, settles on the player's
    assigned suit, then announces the granted starter set. Presented as a draw
    "from all four suits" (new players are seeded an offensive suit, but the
    reveal does not label it as such). ``update`` returns ``'done'`` once the
    suit is revealed and acknowledged.
    """

    def __init__(self, window, suit):
        self.window = window
        self.suit = suit
        self._created_at = pygame.time.get_ticks()
        self._phase = 'spin'   # spin -> done
        self._phase_started = self._created_at

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

        btn_w = settings.DIALOGUE_BOX_BTN_W
        btn_h = settings.DIALOGUE_BOX_BTN_H
        margin = settings.DIALOGUE_BOX_BTN_MARGIN_BOTTOM
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
        """Promote the spin to done once the spin time has elapsed."""
        now = pygame.time.get_ticks()
        if self._phase == 'spin' and now - self._phase_started >= _REEL_SPIN_MS:
            self._phase = 'done'

    def _current_reel_suit(self):
        """The suit icon to show right now (cycling all four while spinning)."""
        if self._phase == 'spin':
            idx = ((pygame.time.get_ticks() - self._phase_started) // _REEL_TICK_MS) % len(_ALL_SUITS)
            return _ALL_SUITS[idx]
        return self.suit

    def update(self, events):
        self._advance_spin()
        self._btn.disabled = self._phase == 'spin'
        self._btn.update()
        _apply_wheel_drag_scroll(events, self._content_rect, self)
        if pygame.time.get_ticks() - self._created_at < 200:
            return None
        for event in events:
            if event.type == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                if self._btn.disabled or not self._btn.rect.collidepoint(pos):
                    continue
                if self._phase == 'done':
                    return 'done'
        return None

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

        if settled:
            y = self._draw_centered_lines(
                [f'{self.suit} — your starter suit!'], self.font,
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
                                     settings.TITLE_TEXT_COLOR)
                else:
                    self.window.blit(
                        breakdown, (bx, content_top + max(0, (content_h - bh) // 2)))
        else:
            spin = self.font.render('Drawing from all four suits…', True,
                                    settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            self.window.blit(spin, spin.get_rect(center=(self.rect.centerx, y + spin.get_height() // 2)))

        self._btn.text = '…' if self._btn.disabled else 'Got it'
        self._btn.draw()

    def get_tooltip(self, pos):
        return ''
