# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Top-left leaderboard panel for the kingdom map.

Renders the server-wide top-3 "Largest Kingdom" and "Greatest Realm"
rankings with gold / silver crown icons. Clicking any row invokes the
``on_focus`` callback so the host screen can pan the map to that kingdom.
"""

import pygame
from config import settings


class LeaderboardPanel:
    """Compact two-section leaderboard rendered inside the map viewport."""

    def __init__(self, window, *, rect=None, on_focus=None,
                 render_crown_icon=None):
        self.window = window
        self.rect = pygame.Rect(rect) if rect else None
        self.on_focus = on_focus
        # Inject the same procedural crown renderer used by HexMap so the
        # icons in the panel match the on-map badge crowns exactly.
        self._render_crown_icon = render_crown_icon
        self._row_rects = []  # [(pygame.Rect, target_dict)]
        self._top_largest = []
        self._top_realms = []
        self._my_largest_rank = None
        self._my_largest_size = 0
        self._my_realm_rank = None
        self._my_realm_size = 0
        self._my_user_id = None
        self._title_font = settings.get_font(settings.FS_SMALL, bold=True)
        self._row_font = settings.get_font(settings.FS_TINY)
        self._row_font_bold = settings.get_font(settings.FS_TINY, bold=True)
        self._small_font = settings.get_font(
            max(8, int(settings.FS_TINY * 0.86)))

    def set_rect(self, rect):
        self.rect = pygame.Rect(rect)

    def set_my_user_id(self, user_id):
        self._my_user_id = user_id

    def set_data(self, *, top_largest=None, top_realms=None,
                 my_largest_rank=None, my_largest_size=0,
                 my_realm_rank=None, my_realm_size=0):
        self._top_largest = list(top_largest or [])
        self._top_realms = list(top_realms or [])
        self._my_largest_rank = my_largest_rank
        self._my_largest_size = int(my_largest_size or 0)
        self._my_realm_rank = my_realm_rank
        self._my_realm_size = int(my_realm_size or 0)

    def render(self):
        if self.rect is None:
            return
        r = self.rect
        self._row_rects = []

        # Background panel + border.
        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.MINIMAP_BG_CLR, surf.get_rect(),
                         border_radius=6)
        self.window.blit(surf, r.topleft)
        pygame.draw.rect(self.window, settings.MINIMAP_BORDER_CLR, r,
                         settings.MINIMAP_BORDER_W, border_radius=6)

        old_clip = self.window.get_clip()
        self.window.set_clip(r)
        try:
            pad = max(4, int(r.w * 0.05))
            y = r.y + pad
            section_gap = max(4, int(r.h * 0.03))
            row_h = max(self._row_font.get_height() + 4,
                        int(r.h * 0.085))

            # Section A: Largest Kingdom → kingdom_{gold,silver,bronce}.
            self._draw_section_title('Largest Kingdom', r, y)
            y += self._title_font.get_height() + 2
            y = self._draw_rows(self._top_largest, r, y, row_h,
                                category='kingdom',
                                size_field='size')

            if self._my_largest_rank is not None and self._my_largest_rank > 3:
                y = self._draw_you_line(
                    r, y, f'You: #{self._my_largest_rank}',
                    f'{self._my_largest_size} lands')

            y += section_gap

            # Section B: Greatest Realm → lands_{gold,silver,bronce}.
            self._draw_section_title('Greatest Realm', r, y)
            y += self._title_font.get_height() + 2
            y = self._draw_rows(self._top_realms, r, y, row_h,
                                category='lands',
                                size_field='total_lands')

            if self._my_realm_rank is not None and self._my_realm_rank > 3:
                self._draw_you_line(
                    r, y, f'You: #{self._my_realm_rank}',
                    f'{self._my_realm_size} lands')
        finally:
            self.window.set_clip(old_clip)

    def _draw_section_title(self, text, panel_rect, y):
        surf = self._title_font.render(text, True,
                                       settings.KINGDOM_INFO_CLR)
        self.window.blit(surf, (panel_rect.x + 8, y))

    def _draw_rows(self, rows, panel_rect, y, row_h, category, size_field):
        if not rows:
            empty = self._small_font.render('— no data —', True,
                                            settings.KINGDOM_ACTIVITY_DIM_CLR)
            self.window.blit(empty, (panel_rect.x + 12, y + 2))
            return y + row_h
        for entry in rows[:3]:
            rect = pygame.Rect(panel_rect.x + 4, y,
                               panel_rect.w - 8, row_h - 2)
            self._draw_row(rect, entry, category, size_field)
            self._row_rects.append((rect, entry))
            y += row_h
        return y

    def _draw_row(self, rect, entry, category, size_field):
        mouse_pos = pygame.mouse.get_pos()
        is_me = (self._my_user_id is not None
                 and entry.get('user_id') == self._my_user_id)
        hovered = rect.collidepoint(mouse_pos)
        bg = (62, 56, 80, 200) if hovered else (
            (44, 40, 56, 175) if is_me else (32, 30, 40, 130))
        bg_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(bg_surf, bg, bg_surf.get_rect(), border_radius=4)
        self.window.blit(bg_surf, rect.topleft)

        # Ranking icon: matches the on-map crown for this entry exactly
        # (``kingdom_{tier}`` or ``lands_{tier}`` per the row's rank).
        rank = entry.get('rank') if isinstance(entry, dict) else None
        crown_sz = max(12, rect.h - 4)
        x = rect.x + 4
        if (self._render_crown_icon is not None
                and rank in (1, 2, 3)):
            icon = self._render_crown_icon(category, rank, crown_sz)
            if icon is not None:
                self.window.blit(
                    icon, icon.get_rect(midleft=(x, rect.centery)))
                x += icon.get_width() + 4
            else:
                x += crown_sz + 4
        else:
            x += crown_sz + 4

        rank = entry.get('rank') or '?'
        size = int(entry.get(size_field) or 0)
        # Bold rank, then name, fit to remaining width.
        rank_surf = self._row_font_bold.render(f'#{rank}', True,
                                               (245, 224, 130))
        self.window.blit(
            rank_surf,
            rank_surf.get_rect(midleft=(x, rect.centery)))
        x += rank_surf.get_width() + 4

        size_str = f'{size}'
        size_surf = self._row_font.render(size_str, True,
                                          settings.KINGDOM_ACTIVITY_TEXT_CLR)
        size_x = rect.right - 4 - size_surf.get_width()
        self.window.blit(size_surf,
                         size_surf.get_rect(midleft=(size_x, rect.centery)))

        name = str(entry.get('name') or entry.get('username') or 'Player')
        name_clr = ((255, 246, 200) if is_me
                    else settings.KINGDOM_ACTIVITY_TEXT_CLR)
        avail_w = max(8, size_x - x - 6)
        name = self._fit_text(name, self._row_font, avail_w)
        name_surf = self._row_font.render(name, True, name_clr)
        self.window.blit(
            name_surf,
            name_surf.get_rect(midleft=(x, rect.centery)))

    def _draw_you_line(self, panel_rect, y, label, suffix):
        line = f'{label}   {suffix}'
        surf = self._small_font.render(line, True,
                                       settings.KINGDOM_ACTIVITY_DIM_CLR)
        self.window.blit(surf, (panel_rect.x + 8, y))
        return y + surf.get_height() + 2

    def _fit_text(self, text, font, max_width):
        if font.size(text)[0] <= max_width:
            return text
        ellipsis = '…'
        clipped = text
        while clipped and font.size(clipped + ellipsis)[0] > max_width:
            clipped = clipped[:-1]
        return (clipped + ellipsis) if clipped else ellipsis

    def handle_event(self, event):
        """Return a target dict if a row was clicked, else None."""
        if event.type != pygame.MOUSEBUTTONUP or event.button != 1:
            return None
        if self.rect is None or not self.rect.collidepoint(event.pos):
            return None
        for rect, entry in self._row_rects:
            if rect.collidepoint(event.pos):
                if callable(self.on_focus):
                    self.on_focus(entry)
                return entry
        # Consume clicks anywhere inside the panel so they don't pass
        # through to the hex map.
        return {}

    def contains_point(self, pos):
        return bool(self.rect and self.rect.collidepoint(pos))
