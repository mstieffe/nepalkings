# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Paginated teaching window for the tutorial (option-b coaching).

A large dialogue that presents game concepts with an image + text per page and
Back / Next / Got it buttons. Modeled on RewardsRevealDialogueBox's panel,
overlay and button conventions.

    pages = [{'title': str, 'lines': [str, ...],
              'image': pygame.Surface | callable() -> Surface | None,
              'image_caption': str | None}]
    win = TutorialWindowDialogue(window, pages, title='...')
    # in the event loop:
    if win.update(events) == 'done':
        win = None
"""

import pygame

from config import settings
from game.components.dialogue_box import _DlgButton


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

        box_w = settings.DIALOGUE_BOX_WIDTH
        box_h = int(0.66 * _SH)
        self.x = (_SW - box_w) // 2
        self.y = max(int(0.02 * _SH), (_SH - box_h) // 2)
        self.rect = pygame.Rect(self.x, self.y, box_w, box_h)

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

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _wrap(text, font, max_w):
        words = str(text or '').split()
        lines, cur = [], ''
        for w in words:
            trial = (cur + ' ' + w).strip()
            if font.size(trial)[0] <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

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

    # ── update / draw ────────────────────────────────────────────────
    def update(self, events):
        self._btn_back.disabled = self.page_index == 0
        self._btn_back.update()
        self._btn_next.update()
        if pygame.time.get_ticks() - self._created_at < 200:
            return None
        for event in events:
            if event.type == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                if not self._btn_back.disabled and self._btn_back.rect.collidepoint(pos):
                    self.page_index = max(0, self.page_index - 1)
                    return None
                if self._btn_next.rect.collidepoint(pos):
                    if self._is_last:
                        return 'done'
                    self.page_index = min(len(self.pages) - 1, self.page_index + 1)
                    return None
        return None

    def _scaled_image(self, page):
        """Page image scaled to a generous, layout-aware box (or None)."""
        img = self._page_image(page)
        if img is None:
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

        headline = None
        if page.get('title'):
            headline = self.headline_font.render(page['title'], True, self._accent)
        img = self._scaled_image(page)
        cap = None
        if img is not None and page.get('image_caption'):
            cap = self.caption_font.render(
                page['image_caption'], True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
        max_w = self.rect.w - int(0.10 * _SW)

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
                blocks.append((img, 'image', caption_gap if cap else block_gap))
                if cap:
                    blocks.append((cap, 'caption', block_gap))
            return blocks

        def text_block(surfs):
            return [(s, 'text', line_gap) for s in surfs]

        layout = page.get('layout', 'image_top')
        rows = []
        if headline:
            rows.append((headline, 'headline', block_gap))
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

        # Fit pass: if the page is taller than the space above the buttons,
        # shrink the image row so text never overflows onto the controls.
        content_h = _content_h(rows)
        if content_h > avail_h:
            overflow = content_h - avail_h
            min_img_h = int(0.10 * _SH)
            for i, (surf, kind, gap) in enumerate(rows):
                if kind != 'image':
                    continue
                new_h = max(min_img_h, surf.get_height() - overflow)
                if new_h < surf.get_height():
                    ratio = new_h / surf.get_height()
                    rows[i] = (pygame.transform.smoothscale(
                        surf, (max(1, int(surf.get_width() * ratio)), new_h)), kind, gap)
                break
            content_h = _content_h(rows)
        # Top-align when still too tall (text-heavy) so it stays off the buttons.
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

    def get_tooltip(self, pos):
        return ''


# Spin tuning for the starter-suit reveal.
_REEL_SPIN_MS = 1400
_REEL_TICK_MS = 90

# Stable card-game facts (red = offensive, black = defensive); kept local so the
# client UI does not depend on server-only settings.
_OFFENSIVE_SUITS = ('Hearts', 'Diamonds')
_DEFENSIVE_SUITS = ('Clubs', 'Spades')
# The granted starter sets (mirror server_settings STARTER_*_SET), shown as the
# actual cards in the reveal.
_OFFENSIVE_SET_RANKS = ['K', 'A', 'J', '7', '7', '8', '8', '9', '10']
_DEFENSIVE_SET_RANKS = ['K', 'A', 'J', '7', '7', '8', '9', '10']


class StarterSuitRevealDialogue:
    """One-armed-bandit reveal of the assigned offensive then defensive suit.

    Each reel spins through its two candidate suit icons, settles on the
    assigned suit, then announces the granted starter set. ``update`` returns
    ``'done'`` once both reels are revealed and acknowledged.
    """

    def __init__(self, window, offensive_suit, defensive_suit):
        self.window = window
        self.offensive_suit = offensive_suit
        self.defensive_suit = defensive_suit
        self._created_at = pygame.time.get_ticks()
        self._phase = 'off_spin'   # off_spin -> off_done -> def_spin -> def_done
        self._phase_started = self._created_at

        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        self.title_font = settings.get_font(
            settings.FONT_SIZE_TITLE_DIALOGUE_BOX, bold=True)
        self.font = settings.get_font(settings.FONT_SIZE_DIALOGUE_BOX)
        self.caption_font = settings.get_font(getattr(settings, 'FS_TINY', 14))

        box_w = settings.DIALOGUE_BOX_WIDTH
        box_h = int(0.68 * _SH)
        self.x = (_SW - box_w) // 2
        self.y = max(int(0.02 * _SH), (_SH - box_h) // 2)
        self.rect = pygame.Rect(self.x, self.y, box_w, box_h)

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

    @property
    def _candidates(self):
        return (list(_OFFENSIVE_SUITS) if self._phase.startswith('off')
                else list(_DEFENSIVE_SUITS))

    @property
    def _assigned(self):
        return self.offensive_suit if self._phase.startswith('off') else self.defensive_suit

    def _advance_spin(self):
        """Promote spinning phases to done once the spin time has elapsed."""
        now = pygame.time.get_ticks()
        if self._phase == 'off_spin' and now - self._phase_started >= _REEL_SPIN_MS:
            self._phase = 'off_done'
        elif self._phase == 'def_spin' and now - self._phase_started >= _REEL_SPIN_MS:
            self._phase = 'def_done'

    def _current_reel_suit(self):
        """The suit icon to show right now (cycling while spinning)."""
        if self._phase in ('off_spin', 'def_spin'):
            cands = self._candidates
            idx = ((pygame.time.get_ticks() - self._phase_started) // _REEL_TICK_MS) % len(cands)
            return cands[idx]
        return self._assigned

    def update(self, events):
        self._advance_spin()
        self._btn.disabled = self._phase in ('off_spin', 'def_spin')
        self._btn.update()
        if pygame.time.get_ticks() - self._created_at < 200:
            return None
        for event in events:
            if event.type == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                if self._btn.disabled or not self._btn.rect.collidepoint(pos):
                    continue
                if self._phase == 'off_done':
                    self._phase = 'def_spin'
                    self._phase_started = pygame.time.get_ticks()
                    return None
                if self._phase == 'def_done':
                    return 'done'
        return None

    def draw(self):
        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        from game.components import tutorial_diagrams
        self.window.blit(self._overlay, (0, 0))
        self.window.blit(self._panel, self.rect.topleft)

        y = self.rect.y + settings.DIALOGUE_BOX_TEXT_MARGIN_Y
        is_off = self._phase.startswith('off')
        settled = self._phase in ('off_done', 'def_done')
        title = 'Your Attack Suit' if is_off else 'Your Defence Suit'
        ts = self.title_font.render(title, True, settings.TITLE_TEXT_COLOR)
        self.window.blit(ts, ts.get_rect(center=(self.rect.centerx, y + ts.get_height() // 2)))
        y += ts.get_height() + int(0.018 * _SH)

        # Spinning: a big reel icon. Settled: a smaller icon to leave room for
        # the actual cards the player gained.
        icon_sz = int((0.10 if settled else 0.16) * _SH)
        suit = self._current_reel_suit()
        ic = tutorial_diagrams.suit_icon(suit, icon_sz)
        if ic:
            self.window.blit(ic, ic.get_rect(center=(self.rect.centerx, y + icon_sz // 2)))
        y += icon_sz + int(0.014 * _SH)

        if settled:
            assigned = self.offensive_suit if is_off else self.defensive_suit
            headline = (f'{assigned} — an offensive (red) suit!' if is_off
                        else f'{assigned} — a defensive (black) suit!')
            hs = self.font.render(headline, True, settings.TITLE_TEXT_COLOR)
            self.window.blit(hs, hs.get_rect(center=(self.rect.centerx, y + hs.get_height() // 2)))
            y += hs.get_height() + int(0.008 * _SH)
            # Make clear these are GAINED starter cards, not just shown.
            grant = self.caption_font.render(
                'These starter cards are added to your collection:',
                True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            self.window.blit(grant, grant.get_rect(center=(self.rect.centerx, y + grant.get_height() // 2)))
            y += grant.get_height() + int(0.008 * _SH)
            # Cards mapped to the figures / spell / tactics they build.
            kind = 'offensive' if is_off else 'defensive'
            breakdown = tutorial_diagrams.starter_set_breakdown(kind, assigned)
            if breakdown is not None:
                max_w = self.rect.w - int(0.08 * _SW)
                max_h = self._btn.rect.top - y - int(0.02 * _SH)
                bw, bh = breakdown.get_size()
                if bw > max_w or bh > max_h:
                    ratio = min(max_w / bw, max_h / bh)
                    breakdown = pygame.transform.smoothscale(
                        breakdown, (max(1, int(bw * ratio)), max(1, int(bh * ratio))))
                self.window.blit(breakdown, breakdown.get_rect(midtop=(self.rect.centerx, y)))
        else:
            spin = self.font.render('Spinning…', True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            self.window.blit(spin, spin.get_rect(center=(self.rect.centerx, y + spin.get_height() // 2)))

        self._btn.text = ('…' if self._btn.disabled
                          else ('Next' if self._phase == 'off_done' else 'Got it'))
        self._btn.draw()

    def get_tooltip(self, pos):
        return ''
