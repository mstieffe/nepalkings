# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Two-stage game-over rewards dialogue with clickable wooden-chest reveal.

Each duel reward-pool draw is shown as a wooden chest. Hovering scales the
chest up and adds a warm glow halo; clicking plays a scale-bounce + cross-fade
that swaps the chest for the actual item icon. The 'ok' button stays disabled
until every chest has been opened.
"""
from config import settings
import math
import pygame
import textwrap

from game.components.dialogue_box import _DlgButton
from game.core.input_state import get_pressed as _get_pressed


# Loaded lazily on first construction to avoid touching the display subsystem
# during module import (tests can import this module without a video mode set).
_CHEST_IMG = None
_REWARD_ICONS = {}


def _load_chest_image():
    global _CHEST_IMG
    if _CHEST_IMG is None:
        _CHEST_IMG = pygame.image.load(
            'img/dialogue_box/icons/wooden_chest.png').convert_alpha()
    return _CHEST_IMG


def _load_reward_icon(name):
    """Load a reward item icon by kind name ('main_booster', 'side_booster',
    'map', 'gold'). Cached after first load."""
    if name in _REWARD_ICONS:
        return _REWARD_ICONS[name]
    path_by_kind = {
        'main_booster': 'img/dialogue_box/icons/booster_pack.png',
        'side_booster': 'img/dialogue_box/icons/booster_pack_side.png',
        'map':          'img/dialogue_box/icons/map.png',
        'gold':         'img/dialogue_box/icons/gold.png',
    }
    path = path_by_kind.get(name)
    if not path:
        return None
    surf = pygame.image.load(path).convert_alpha()
    _REWARD_ICONS[name] = surf
    return surf


# ── tuning ──────────────────────────────────────────────────────────
_REVEAL_DURATION_MS  = 350   # total time for one chest's reveal anim
_HOVER_SCALE         = 1.08  # idle chest scale on hover
_BOUNCE_PEAK         = 1.22  # peak scale mid-reveal
_CHEST_FRAME_HEIGHT_FACTOR = 0.115  # of SCREEN_HEIGHT, approximate frame size


class _ChestItem:
    """One reveal slot — wooden chest that turns into a reward icon on click."""

    __slots__ = (
        'kind', 'label', 'description', 'item_icon', 'frame_size',
        'rect', 'revealed', 'reveal_started_at',
    )

    def __init__(self, kind, label, description, item_icon, frame_size):
        self.kind = kind
        self.label = label
        self.description = description
        self.item_icon = item_icon  # already-scaled pygame.Surface (or None)
        self.frame_size = frame_size  # int — bounding box per slot
        self.rect = pygame.Rect(0, 0, frame_size, frame_size)
        self.revealed = False
        self.reveal_started_at = None

    # ── state helpers ───────────────────────────────────────────────
    def reveal_progress(self, now_ms):
        """Return reveal progress in [0,1]; 0 = chest, 1 = fully revealed."""
        if self.revealed:
            return 1.0
        if self.reveal_started_at is None:
            return 0.0
        elapsed = now_ms - self.reveal_started_at
        if elapsed >= _REVEAL_DURATION_MS:
            self.revealed = True
            return 1.0
        return max(0.0, min(1.0, elapsed / _REVEAL_DURATION_MS))

    def is_animating(self, now_ms):
        return (self.reveal_started_at is not None) and (not self.revealed) and \
               (now_ms - self.reveal_started_at < _REVEAL_DURATION_MS)


class RewardsRevealDialogueBox:
    """Drop-in replacement for DialogueBox during the spoils-of-war step.

    Exposes the same ``draw()`` / ``update(events)`` interface so the
    game_screen's dialogue plumbing can manage it without special-casing.
    """

    def __init__(self, window, title, icon, summary_lines, items,
                 footer_when_done="All loot collected!",
                 summary_image=None,
                 hint_text=None):
        """
        :param summary_lines: list[str] — always-visible text shown above the
            chest row (e.g. "Stake winnings: +90 gold" or "Stake lost: -45 gold").
            One entry per line.
        :param items: list[dict] with keys 'kind', 'label', and optional 'icon'
            (a pygame.Surface). When 'icon' is missing, it is loaded from the
            kind. Empty list → dialogue immediately enables ok.
        :param footer_when_done: text shown below the chest row once every
            chest has been opened.
        :param summary_image: optional pygame.Surface — a single icon
            (typically the gold/gold_lost image) shown centered between the
            title and the summary_lines.
        """
        self.window = window
        self.title = title or ""
        self.summary_lines = list(summary_lines or [])
        self.footer_when_done = footer_when_done
        self._created_at = pygame.time.get_ticks()

        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        small = _SW < 700 or getattr(settings, 'TOUCH_TARGET_MIN', 0) > 0
        if small:
            margin_x = max(12, int(0.05 * _SW))
            box_w = min(int(0.86 * _SW), _SW - margin_x * 2)
        else:
            box_w = settings.DIALOGUE_BOX_WIDTH

        self.font = settings.get_font(settings.FONT_SIZE_DIALOGUE_BOX)
        self.title_font = settings.get_font(
            settings.FONT_SIZE_TITLE_DIALOGUE_BOX, bold=True)
        self.caption_font = settings.get_font(settings.FS_TINY)
        self.description_font = settings.get_font(settings.FS_SMALL)

        # Icon (title decoration on either side, like DialogueBox)
        self.icon = None
        if icon and icon in settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT:
            raw = settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT[icon]
            tgt_h = settings.DIALOGUE_BOX_ICON_HEIGHT
            ratio = tgt_h / raw.get_height()
            self.icon = pygame.transform.smoothscale(
                raw, (int(raw.get_width() * ratio), tgt_h))

        # Summary image (e.g. gold pile for stake winnings)
        self.summary_image = None
        if summary_image is not None:
            tgt_h = int(0.115 * _SH)
            ratio = tgt_h / summary_image.get_height()
            self.summary_image = pygame.transform.smoothscale(
                summary_image,
                (max(1, int(summary_image.get_width() * ratio)), tgt_h))

        # ── build chest items ─────────────────────────────────────────
        frame_size = int(_CHEST_FRAME_HEIGHT_FACTOR * _SH)
        self._frame_size = frame_size
        self._chest_img = self._scale_to_frame(_load_chest_image(), frame_size)

        self.items = []
        for it in items or []:
            kind = it.get('kind')
            label = it.get('label', '')
            description = it.get('description', '')
            icon_surf = it.get('icon') or _load_reward_icon(kind)
            scaled = self._scale_to_frame(icon_surf, int(frame_size * 0.84)) \
                if icon_surf else None
            self.items.append(_ChestItem(kind, label, description, scaled, frame_size))
        self._last_revealed_item = None

        # ── wrap text ─────────────────────────────────────────────────
        _max_text_w = box_w - int(0.08 * _SW)
        self.summary_surfaces = self._render_lines(self.summary_lines, _max_text_w)
        self.footer_surfaces = self._render_lines(
            [self.footer_when_done] if self.footer_when_done else [],
            _max_text_w,
        )
        self.hint_surfaces = [
            self.caption_font.render(line, True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            for line in self._wrap_text(
                hint_text or "Click each chest to reveal your loot",
                self.caption_font,
                _max_text_w,
            )
        ]
        self._hint_h = (
            len(self.hint_surfaces) * self.caption_font.get_height()
            + max(0, len(self.hint_surfaces) - 1) * int(0.004 * _SH)
        )

        # ── layout ────────────────────────────────────────────────────
        _line_h = self.font.get_height() + int(0.004 * _SH)
        _pad_top = settings.DIALOGUE_BOX_TEXT_MARGIN_Y
        _pad_bottom = settings.DIALOGUE_BOX_BTN_MARGIN_BOTTOM
        self._line_h = _line_h

        # Chest-row layout: greedy fit, wrap to multiple rows if needed.
        gap_x = int(0.012 * _SW)
        gap_y = int(0.014 * _SH)
        max_row_w = box_w - int(0.08 * _SW)
        per_row = max(1, min(len(self.items) or 1,
                             (max_row_w + gap_x) // (frame_size + gap_x)))
        self._chest_rows = []
        for i in range(0, len(self.items), per_row):
            self._chest_rows.append(self.items[i:i + per_row])
        chest_block_h = (len(self._chest_rows) * frame_size +
                         max(0, len(self._chest_rows) - 1) * gap_y) \
            if self._chest_rows else 0
        # Reserve a strip below each chest row for the item label caption.
        if self._chest_rows:
            chest_block_h += self.caption_font.get_height() + int(0.004 * _SH)
            chest_block_h += int(0.006 * _SH)  # hint text gap above chests
            chest_block_h += self._hint_h
        description_h = 0
        if any(item.description for item in self.items):
            desc_max_w = box_w - int(0.10 * _SW)
            max_desc_lines = 1
            for item in self.items:
                lines = self._wrap_text(item.description, self.description_font, desc_max_w)
                max_desc_lines = max(max_desc_lines, len(lines))
            desc_line_h = self.description_font.get_height() + int(0.004 * _SH)
            description_h = int(0.018 * _SH) + max_desc_lines * desc_line_h
        self._chest_gap_x = gap_x
        self._chest_gap_y = gap_y
        self._chest_block_h = chest_block_h
        self._description_h = description_h
        self._desc_max_w = box_w - int(0.10 * _SW)

        title_h = (self.title_font.get_height() + int(0.016 * _SH)) if self.title else 0
        sep_extra = int(0.018 * _SH) if self.title else 0
        summary_h = len(self.summary_surfaces) * _line_h
        summary_img_h = (self.summary_image.get_height() + int(0.008 * _SH)) \
            if self.summary_image else 0
        footer_h = len(self.footer_surfaces) * _line_h
        btn_h = settings.DIALOGUE_BOX_BTN_H + _pad_bottom

        block_gap = int(0.020 * _SH)
        self._block_gap = block_gap
        self._summary_img_h = summary_img_h
        self.box_height = (
            _pad_top + title_h + sep_extra +
            summary_img_h +
            summary_h + (block_gap if (summary_h or summary_img_h) else 0) +
            chest_block_h + description_h + (block_gap if footer_h else 0) +
            footer_h + btn_h + int(0.010 * _SH)
        )

        self.x = (_SW - box_w) // 2
        margin_y = int(0.020 * _SH)
        if small:
            self.y = max(margin_y, (_SH - self.box_height) // 2)
            self.y = min(self.y, max(margin_y, _SH - self.box_height - margin_y))
        else:
            height_diff = self.box_height - settings.DIALOGUE_BOX_HEIGHT
            self.y = int(_SH * 0.5 - settings.DIALOGUE_BOX_HEIGHT * 0.75 - height_diff / 2)
            self.y = max(margin_y, min(self.y, _SH - self.box_height - margin_y))
        self.rect = pygame.Rect(self.x, self.y, box_w, self.box_height)
        self.border_rect = self.rect.inflate(2, 2)

        # Panel + overlay
        _corner_r = settings.DIALOGUE_BOX_CORNER_R
        self._panel = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
        pygame.draw.rect(self._panel, settings.DIALOGUE_BOX_BG_CLR,
                         self._panel.get_rect(), border_radius=_corner_r)
        pygame.draw.rect(self._panel, settings.DIALOGUE_BOX_BORDER_CLR,
                         self._panel.get_rect(),
                         settings.DIALOGUE_BOX_BORDER_WIDTH,
                         border_radius=_corner_r)
        self._overlay = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
        self._overlay.fill(settings.DIALOGUE_BOX_OVERLAY_CLR)

        # Glow halo surface — pre-rendered once.
        self._glow_surf = self._build_glow(frame_size)

        # Place the OK button (single action). Disabled until all revealed.
        _btn_w = settings.DIALOGUE_BOX_BTN_W
        first_x = self.rect.centerx - _btn_w // 2
        btn_y = self.rect.bottom - btn_h + int(0.004 * _SH)
        self._ok_button = _DlgButton(window, first_x, btn_y, 'ok',
                                     width=_btn_w, height=settings.DIALOGUE_BOX_BTN_H)

        # Position chest rects (recomputed once now; centres on x).
        self._description_top = None
        self._layout_chest_positions()

    # ── helpers ─────────────────────────────────────────────────────
    def _scale_to_frame(self, surf, target):
        if surf is None:
            return None
        w, h = surf.get_size()
        if h <= 0:
            return surf
        ratio = target / h
        return pygame.transform.smoothscale(
            surf, (max(1, int(w * ratio)), max(1, int(h * ratio))))

    def _render_lines(self, lines, max_w):
        surfaces = []
        for line in lines:
            wrapped = self._wrap_text(line, self.font, max_w)
            for w in wrapped:
                surfaces.append(self.font.render(
                    w, True, settings.DIALOGUE_BOX_MSG_TEXT_CLR))
        return surfaces

    @staticmethod
    def _wrap_text(text, font, max_w):
        if not text:
            return ['']
        out = []
        for raw in text.split('\n'):
            if not raw:
                out.append('')
                continue
            # binary-ish word wrap by pixel width
            words = raw.split(' ')
            line = ''
            for w in words:
                trial = (line + ' ' + w).strip()
                if font.size(trial)[0] <= max_w:
                    line = trial
                else:
                    if line:
                        out.append(line)
                    # word itself too long — let pygame just draw it (rare)
                    line = w
            if line:
                out.append(line)
        return out

    def _build_glow(self, frame_size):
        """Soft warm radial glow used behind hovered chests."""
        size = int(frame_size * 1.5)
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        cx, cy = size // 2, size // 2
        max_r = size // 2
        # Concentric circles from outside-in (low alpha → higher alpha at centre).
        for r in range(max_r, 0, -2):
            t = r / max_r
            a = int(72 * (1 - t) ** 2)
            if a <= 0:
                continue
            pygame.draw.circle(surf, (255, 210, 110, a), (cx, cy), r)
        return surf

    def _layout_chest_positions(self):
        """Compute each chest's rect (top-left). Called once during init —
        chest positions don't change after layout."""
        if not self._chest_rows:
            return
        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        frame = self._frame_size
        gap_x = self._chest_gap_x

        # Compute starting y once the rest of the layout is known.
        _pad_top = settings.DIALOGUE_BOX_TEXT_MARGIN_Y
        title_h = (self.title_font.get_height() + int(0.016 * _SH)) if self.title else 0
        sep_extra = int(0.018 * _SH) if self.title else 0
        summary_h = len(self.summary_surfaces) * self._line_h

        current_y = (self.rect.y + _pad_top + title_h + sep_extra +
                     self._summary_img_h +
                     summary_h +
                     (self._block_gap if (summary_h or self._summary_img_h) else 0))
        # Hint line above chests
        current_y += self._hint_h + int(0.006 * _SH)

        gap_y = self._chest_gap_y
        for row in self._chest_rows:
            row_w = len(row) * frame + (len(row) - 1) * gap_x
            ix = self.rect.centerx - row_w // 2
            for item in row:
                item.rect = pygame.Rect(ix, current_y, frame, frame)
                ix += frame + gap_x
            current_y += frame + gap_y
        if self._description_h:
            caption_h = self.caption_font.get_height() + int(0.004 * _SH)
            self._description_top = current_y - gap_y + caption_h + int(0.018 * _SH)

    # ── draw ────────────────────────────────────────────────────────
    def draw(self):
        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT

        # Dim overlay + panel
        self.window.blit(self._overlay, (0, 0))
        self.window.blit(self._panel, self.rect.topleft)

        current_y = self.rect.y + settings.DIALOGUE_BOX_TEXT_MARGIN_Y

        # Title + icons + separator
        if self.title:
            title_surface = self.title_font.render(
                self.title, True, settings.TITLE_TEXT_COLOR)
            title_rect = title_surface.get_rect(
                center=(self.rect.centerx, current_y + title_surface.get_height() // 2))
            if self.icon:
                icon_gap = int(0.010 * _SW)
                total_title_w = title_rect.w + 2 * (self.icon.get_width() + icon_gap)
                if total_title_w <= self.rect.w - int(0.03 * _SW):
                    icon_y = title_rect.centery - self.icon.get_height() // 2
                    self.window.blit(self.icon,
                                     (title_rect.left - icon_gap - self.icon.get_width(), icon_y))
                    self.window.blit(self.icon,
                                     (title_rect.right + icon_gap, icon_y))
            self.window.blit(title_surface, title_rect)
            current_y += title_surface.get_height() + int(0.016 * _SH)
            sep_x1 = self.rect.x + int(0.04 * _SW)
            sep_x2 = self.rect.right - int(0.04 * _SW)
            pygame.draw.line(self.window, settings.DIALOGUE_BOX_SEP_CLR,
                             (sep_x1, current_y), (sep_x2, current_y), 1)
            current_y += int(0.018 * _SH)

        # Summary image (e.g. gold pile centered above the text)
        if self.summary_image is not None:
            img_rect = self.summary_image.get_rect(
                midtop=(self.rect.centerx, current_y))
            self.window.blit(self.summary_image, img_rect.topleft)
            current_y += self.summary_image.get_height() + int(0.008 * _SH)

        # Summary lines (always visible — stake winnings/losses)
        for i, surf in enumerate(self.summary_surfaces):
            ly = current_y + i * self._line_h
            self.window.blit(surf, surf.get_rect(center=(self.rect.centerx, ly)))
        if self.summary_surfaces:
            current_y += len(self.summary_surfaces) * self._line_h + self._block_gap
        elif self.summary_image is not None:
            current_y += self._block_gap

        # Hint line above chests
        if self._chest_rows:
            hint_y = current_y
            hint_gap = int(0.004 * _SH)
            for surf in self.hint_surfaces:
                hint_rect = surf.get_rect(
                    center=(self.rect.centerx, hint_y + surf.get_height() // 2))
                self.window.blit(surf, hint_rect)
                hint_y += surf.get_height() + hint_gap

        # Chests
        now = pygame.time.get_ticks()
        mouse_pos = pygame.mouse.get_pos()
        for row in self._chest_rows:
            for item in row:
                self._draw_chest_or_item(item, mouse_pos, now)

        self._draw_revealed_item_description(now)

        # Footer message — only once all revealed
        if self.footer_surfaces and self._all_revealed(now):
            fy = (self.rect.bottom -
                  settings.DIALOGUE_BOX_BTN_H -
                  settings.DIALOGUE_BOX_BTN_MARGIN_BOTTOM -
                  int(0.018 * _SH) -
                  len(self.footer_surfaces) * self._line_h)
            for i, surf in enumerate(self.footer_surfaces):
                ly = fy + i * self._line_h
                self.window.blit(surf, surf.get_rect(center=(self.rect.centerx, ly)))

        # OK button (disabled until all revealed)
        self._ok_button.disabled = not self._all_revealed(now)
        self._ok_button.draw()

    def _draw_chest_or_item(self, item, mouse_pos, now_ms):
        progress = item.reveal_progress(now_ms)
        hovered = (progress == 0.0) and item.rect.collidepoint(mouse_pos)

        # Scale animation curve: bounce peaks mid-reveal, hover gives steady 1.08.
        if 0.0 < progress < 1.0:
            # half-sine bounce
            scale = 1.0 + (_BOUNCE_PEAK - 1.0) * math.sin(math.pi * progress)
        elif progress == 0.0 and hovered:
            scale = _HOVER_SCALE
        else:
            scale = 1.0

        # Hover glow (only on idle, unrevealed, hovered chests)
        if hovered and not item.revealed:
            gw, gh = self._glow_surf.get_size()
            self.window.blit(self._glow_surf,
                             (item.rect.centerx - gw // 2,
                              item.rect.centery - gh // 2))

        # During reveal: cross-fade chest (alpha 255→0 in 0..0.5) with
        # item (alpha 0→255 in 0.5..1.0).
        if progress >= 1.0:
            self._draw_scaled(item.item_icon, item.rect.center, scale, 255)
            self._draw_item_caption(item)
        elif progress == 0.0:
            self._draw_scaled(self._chest_img, item.rect.center, scale, 255)
        else:
            chest_a = max(0, min(255, int(255 * (1 - min(1.0, progress * 2)))))
            item_a = max(0, min(255, int(255 * max(0.0, (progress - 0.5) * 2))))
            if chest_a > 0:
                self._draw_scaled(self._chest_img, item.rect.center, scale, chest_a)
            if item_a > 0 and item.item_icon is not None:
                self._draw_scaled(item.item_icon, item.rect.center, scale, item_a)

    def _draw_scaled(self, surf, center, scale, alpha):
        if surf is None:
            return
        if scale != 1.0:
            w, h = surf.get_size()
            scaled = pygame.transform.smoothscale(
                surf, (max(1, int(w * scale)), max(1, int(h * scale))))
        else:
            scaled = surf
        if alpha < 255:
            scaled = scaled.copy()
            scaled.set_alpha(alpha)
        rect = scaled.get_rect(center=center)
        self.window.blit(scaled, rect.topleft)

    def _draw_item_caption(self, item):
        if not item.label:
            return
        cap = self.caption_font.render(
            item.label, True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
        cy = item.rect.bottom + int(0.004 * settings.SCREEN_HEIGHT) \
            + cap.get_height() // 2
        self.window.blit(cap, cap.get_rect(center=(item.rect.centerx, cy)))

    def _description_item(self, now_ms):
        if (self._last_revealed_item is not None
                and self._last_revealed_item.reveal_progress(now_ms) >= 1.0
                and self._last_revealed_item.description):
            return self._last_revealed_item
        for item in reversed(self.items):
            if item.reveal_progress(now_ms) >= 1.0 and item.description:
                return item
        return None

    def _draw_revealed_item_description(self, now_ms):
        if not self._description_h or self._description_top is None:
            return
        item = self._description_item(now_ms)
        if item is None:
            return
        lines = self._wrap_text(item.description, self.description_font, self._desc_max_w)
        line_h = self.description_font.get_height() + int(0.004 * settings.SCREEN_HEIGHT)
        y = self._description_top
        for line in lines:
            surf = self.description_font.render(line, True, settings.DIALOGUE_BOX_MSG_TEXT_CLR)
            self.window.blit(surf, surf.get_rect(center=(self.rect.centerx, y)))
            y += line_h

    # ── interaction ─────────────────────────────────────────────────
    def _all_revealed(self, now_ms):
        for item in self.items:
            if not item.revealed:
                # Force progress check (also lets anim flip 'revealed' to True
                # once duration has elapsed).
                if item.reveal_progress(now_ms) < 1.0:
                    return False
        return True

    def update(self, events):
        now = pygame.time.get_ticks()
        self._ok_button.disabled = not self._all_revealed(now)
        self._ok_button.update()

        # Reject MOUSEBUTTONUP within 200ms of creation (same as DialogueBox)
        # so the click that opened the dialogue doesn't immediately trigger
        # a chest reveal.
        if pygame.time.get_ticks() - self._created_at < 200:
            return None

        for event in events:
            if event.type == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                # OK button (only if not disabled)
                if not self._ok_button.disabled and self._ok_button.collide():
                    return 'ok'
                # Chest clicks
                for item in self.items:
                    if item.revealed or item.reveal_started_at is not None:
                        continue
                    if item.rect.collidepoint(event.pos):
                        item.reveal_started_at = now
                        self._last_revealed_item = item
                        break  # one click → one chest
        return None

    def get_tooltip(self, pos):
        # Game screen calls this on dialogues; reveal dialogue has no tooltips.
        return ''
