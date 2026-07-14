# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Top-left leaderboard panel for the kingdom map.

Renders the server-wide top-3 "Largest Kingdom" and "Greatest Realm"
rankings with gold / silver crown icons. Clicking any row invokes the
``on_focus`` callback so the host screen can pan the map to that kingdom.
"""

import pygame
from config import settings


_CHAMPION_ICON_PATH = 'img/kingdom/ranking/champion.png'
_REGION_SUITS = ('Spades', 'Clubs', 'Hearts', 'Diamonds')


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
        self.collapsed = False
        self._toggle_rect = None
        self._toggle_hit_rect = None
        self._top_largest = []
        self._top_realms = []
        self._my_largest_rank = None
        self._my_largest_size = 0
        self._my_realm_rank = None
        self._my_realm_size = 0
        self._my_user_id = None
        self._regions = []
        self._view = 'rankings'
        self._tab_rects = {}
        self._title_font = settings.get_font(settings.FS_SMALL, bold=True)
        self._row_font = settings.get_font(settings.FS_TINY)
        self._row_font_bold = settings.get_font(settings.FS_TINY, bold=True)
        self._small_font = settings.get_font(
            max(8, int(settings.FS_TINY * 0.86)))
        self._champion_icon = self._load_region_icon(_CHAMPION_ICON_PATH)
        self._suit_icons = {
            suit: self._load_region_icon(
                f'{settings.SUIT_ICON_IMG_PATH}{suit.lower()}.png')
            for suit in _REGION_SUITS
        }
        self._region_icon_cache = {}

    @staticmethod
    def _load_region_icon(path):
        try:
            return pygame.image.load(path).convert_alpha()
        except Exception:
            return None

    def _region_icon(self, kind, size):
        """Return one cached Champion/suit icon at the requested row size."""
        size = max(8, int(size))
        cache_key = (kind, size)
        cached = self._region_icon_cache.get(cache_key)
        if cached is not None:
            return cached
        if kind == 'champion':
            raw = self._champion_icon
        else:
            raw = self._suit_icons.get(kind)
        if raw is not None:
            icon = pygame.transform.smoothscale(raw, (size, size))
        elif kind == 'neutral':
            icon = pygame.Surface((size, size), pygame.SRCALPHA)
            center = (size // 2, size // 2)
            pygame.draw.circle(icon, (230, 216, 176, 220), center,
                               max(2, size // 3), max(1, size // 6))
            pygame.draw.circle(icon, (80, 72, 54, 190), center,
                               max(1, size // 9))
        else:
            return None
        self._region_icon_cache[cache_key] = icon
        return icon

    def set_rect(self, rect):
        self.rect = pygame.Rect(rect)

    def set_my_user_id(self, user_id):
        self._my_user_id = user_id

    def set_data(self, *, top_largest=None, top_realms=None,
                 my_largest_rank=None, my_largest_size=0,
                 my_realm_rank=None, my_realm_size=0, regions=None):
        self._top_largest = list(top_largest or [])
        self._top_realms = list(top_realms or [])
        self._my_largest_rank = my_largest_rank
        self._my_largest_size = int(my_largest_size or 0)
        self._my_realm_rank = my_realm_rank
        self._my_realm_size = int(my_realm_size or 0)
        if regions is not None:
            self._regions = list(regions or [])

    def _header_h(self):
        return self._title_font.get_height() + 8

    def _visible_rect(self):
        """Rect actually drawn/hit-tested (header only when collapsed)."""
        if self.rect is None:
            return None
        if self.collapsed:
            collapsed_w = min(
                self.rect.w,
                max(110, int(0.16 * settings.SCREEN_WIDTH)),
            )
            return pygame.Rect(self.rect.x, self.rect.y, collapsed_w,
                               self._header_h())
        return self.rect

    def _draw_toggle(self, vr):
        """Collapse/expand caret at the panel's top-right corner."""
        sz = max(12, int(vr.w * 0.09))
        tr = pygame.Rect(vr.right - sz - 5, vr.y + 5, sz, sz)
        self._toggle_rect = tr
        hit = tr.copy()
        if settings.TOUCH_TARGET_MIN > 0:
            hit.inflate_ip(
                max(0, settings.TOUCH_TARGET_MIN - hit.w),
                max(0, settings.TOUCH_TARGET_MIN - hit.h),
            )
            hit.clamp_ip(vr)
        self._toggle_hit_rect = hit
        hovered = hit.collidepoint(pygame.mouse.get_pos())
        clr = (245, 232, 196) if hovered else (200, 188, 158)
        cx, cy = tr.center
        w = max(4, int(sz * 0.30))
        h = max(3, int(sz * 0.22))
        if self.collapsed:
            pts = [(cx - w, cy - h), (cx + w, cy - h), (cx, cy + h)]  # ▾ expand
        else:
            pts = [(cx - w, cy + h), (cx + w, cy + h), (cx, cy - h)]  # ▴ collapse
        pygame.draw.polygon(self.window, clr, pts)

    def render(self):
        if self.rect is None:
            return
        r = self.rect
        vr = self._visible_rect()
        self._row_rects = []
        self._tab_rects = {}

        # Background panel + border (header-height only when collapsed).
        surf = pygame.Surface((vr.w, vr.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.MINIMAP_BG_CLR, surf.get_rect(),
                         border_radius=6)
        self.window.blit(surf, vr.topleft)
        pygame.draw.rect(self.window, settings.MINIMAP_BORDER_CLR, vr,
                         settings.MINIMAP_BORDER_W, border_radius=6)

        self._draw_toggle(vr)

        if self.collapsed:
            label_text = 'Regions' if self._view == 'regions' else 'Rankings'
            label = self._title_font.render(label_text, True,
                                            settings.KINGDOM_INFO_CLR)
            self.window.blit(label, label.get_rect(
                midleft=(vr.x + 8, vr.centery)))
            return

        old_clip = self.window.get_clip()
        self.window.set_clip(r)
        try:
            pad = max(4, int(r.w * 0.05))
            y = r.y + pad
            section_gap = max(4, int(r.h * 0.03))
            row_h = max(self._row_font.get_height() + 4,
                        int(r.h * 0.085),
                        settings.TOUCH_COMPACT_MIN)

            # Segmented view switch.  Keeping the five regions in the same
            # collapsible surface avoids adding another permanent map widget.
            tab_h = max(self._title_font.get_height() + 7,
                        settings.TOUCH_COMPACT_MIN)
            tab_right = r.right - pad - max(16, self._header_h() - 2)
            tab_gap = max(2, int(r.w * 0.012))
            tab_w = max(
                42, (tab_right - (r.x + pad) - tab_gap) // 2)
            for idx, (key, text) in enumerate((
                    ('rankings', 'Rankings'), ('regions', 'Regions'))):
                tab = pygame.Rect(r.x + pad + idx * (tab_w + tab_gap), y,
                                  tab_w, tab_h)
                self._tab_rects[key] = tab
                active = self._view == key
                bg = ((78, 69, 94, 225) if active
                      else (37, 34, 46, 175))
                pygame.draw.rect(self.window, bg, tab,
                                 border_radius=4)
                pygame.draw.rect(
                    self.window,
                    settings.KINGDOM_INFO_CLR if active
                    else settings.MINIMAP_BORDER_CLR,
                    tab, 1, border_radius=4)
                surf = self._row_font_bold.render(
                    text, True,
                    (250, 232, 174) if active
                    else settings.KINGDOM_ACTIVITY_DIM_CLR)
                self.window.blit(surf, surf.get_rect(center=tab.center))
            y += tab_h + section_gap

            if self._view == 'regions':
                self._draw_regions(r, y, row_h)
                return

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

    def _draw_regions(self, panel_rect, y, row_h):
        """Draw five structured Region/Champion/progress cards."""
        if not self._regions:
            empty = self._small_font.render(
                '— no region data —', True,
                settings.KINGDOM_ACTIVITY_DIM_CLR)
            self.window.blit(empty, (panel_rect.x + 10, y + 2))
            return

        visible_regions = self._regions[:5]
        available_h = max(1, panel_rect.bottom - y - 4)
        per_row_limit = max(1, available_h // len(visible_regions))
        three_line_min = (self._row_font_bold.get_height()
                          + self._small_font.get_height() * 2 + 12)
        fitted_h = max(1, min(
            max(row_h, three_line_min), per_row_limit))

        for region in visible_regions:
            rect = pygame.Rect(panel_rect.x + 4, y,
                               panel_rect.w - 8, max(1, fitted_h - 2))
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            bg = (62, 56, 80, 205) if hovered else (32, 30, 40, 145)
            surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(surface, bg, surface.get_rect(), border_radius=4)
            self.window.blit(surface, rect.topleft)

            name = str(region.get('name') or region.get('key') or 'Region')
            champions = region.get('champions') or (
                [region.get('champion')] if region.get('champion') else [])
            champion_name = ', '.join(
                str(champion.get('username') or 'Unknown')
                for champion in champions)
            champ_count = int(region.get('champion_land_count') or 0)
            my_count = int(region.get('my_land_count') or 0)
            needed = int(region.get('lands_to_champion') or 0)
            is_champion = (
                self._my_user_id is not None
                and any(champion.get('user_id') == self._my_user_id
                        for champion in champions)
            )

            pad_x = 7
            line_gap = 2
            dominant = region.get('dominant_suit')
            suit_icon = self._region_icon(
                dominant if dominant else 'neutral',
                min(18, max(10, self._row_font_bold.get_height())))
            suit_w = suit_icon.get_width() if suit_icon else 0

            # Region identity owns its own line, with a reserved suit slot.
            # It can therefore never collide with the Champion identity.
            title_max = max(12, rect.w - pad_x * 2 - suit_w
                            - (4 if suit_icon else 0))
            title = self._fit_text(name, self._row_font_bold, title_max)
            title_surf = self._row_font_bold.render(
                title, True, settings.KINGDOM_INFO_CLR)
            title_y = rect.y + max(3, (rect.h - three_line_min) // 2 + 3)
            self.window.blit(title_surf, (rect.x + pad_x, title_y))
            if suit_icon is not None:
                self.window.blit(suit_icon, suit_icon.get_rect(
                    midright=(rect.right - pad_x,
                              title_y + title_surf.get_height() // 2)))

            if not champions:
                champion_summary = 'No Champion'
            elif len(champions) == 1:
                champion_summary = f'{champion_name} · {champ_count}'
            else:
                champion_summary = (
                    f'{len(champions)} co-Champions · {champ_count}')
            champion_icon = None
            if champions:
                champion_icon = self._region_icon(
                    'champion', min(
                        18, max(10, self._small_font.get_height() + 1)))
            champion_reserved = (
                champion_icon.get_width() + 4 if champion_icon else 0)
            champion_summary = self._fit_text(
                champion_summary, self._small_font,
                max(12, rect.w - pad_x * 2 - champion_reserved))
            champion_surf = self._small_font.render(
                champion_summary, True,
                (settings.KINGDOM_ACTIVITY_TEXT_CLR if champions
                 else settings.KINGDOM_ACTIVITY_DIM_CLR))
            champion_y = title_y + title_surf.get_height() + line_gap
            champion_x = rect.x + pad_x
            if champion_icon is not None:
                self.window.blit(champion_icon, champion_icon.get_rect(
                    midleft=(champion_x,
                             champion_y + champion_surf.get_height() // 2)))
                champion_x += champion_icon.get_width() + 4
            self.window.blit(champion_surf, (champion_x, champion_y))

            if is_champion:
                progress = f'You: Champion · {my_count} lands'
            elif needed:
                progress = f'You: {my_count} · {needed} to lead'
            else:
                progress = f'You: {my_count}'
            tribute_rate = float(region.get('tribute_rate_per_hour') or 0.0)
            meta = (f'+{tribute_rate:g}g/h'
                    if is_champion and tribute_rate > 0 else '')
            meta_surf = self._small_font.render(
                meta, True, settings.KINGDOM_ACTIVITY_DIM_CLR)
            progress = self._fit_text(
                progress, self._small_font,
                max(12, rect.w - pad_x * 2 - meta_surf.get_width()
                    - (6 if meta else 0)))
            progress_surf = self._small_font.render(
                progress, True,
                ((255, 239, 184) if is_champion
                 else settings.KINGDOM_ACTIVITY_DIM_CLR))
            progress_y = champion_y + champion_surf.get_height() + line_gap
            # Short panels preserve the two identity lines; full personal
            # progress remains available in the click-open inspector.
            if progress_y + progress_surf.get_height() <= rect.bottom - 2:
                self.window.blit(progress_surf, (rect.x + pad_x, progress_y))
                if meta:
                    self.window.blit(meta_surf, meta_surf.get_rect(
                        topright=(rect.right - pad_x, progress_y)))

            target = dict(region)
            target['region_key'] = region.get('key')
            self._row_rects.append((rect, target))
            y += fitted_h

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
        vr = self._visible_rect()
        if vr is None or not vr.collidepoint(event.pos):
            return None
        # Collapse / expand toggle.
        if self._toggle_hit_rect and self._toggle_hit_rect.collidepoint(event.pos):
            self.collapsed = not self.collapsed
            return {}
        if self.collapsed:
            self.collapsed = False
            return {}
        for key, rect in self._tab_rects.items():
            if rect.collidepoint(event.pos):
                self._view = key
                return {'view': key}
        for rect, entry in self._row_rects:
            if rect.collidepoint(event.pos):
                if callable(self.on_focus):
                    self.on_focus(entry)
                return entry
        # Consume clicks anywhere inside the panel so they don't pass
        # through to the hex map.
        return {}

    def contains_point(self, pos):
        vr = self._visible_rect()
        return bool(vr and vr.collidepoint(pos))
