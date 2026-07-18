# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from config import settings
from config.screen_settings import _UI_SCALE, _IS_MOBILE


class ScoreboardScroll:
    def __init__(
            self,
            window: pygame.Surface,
            game,
            x: int,
            y: int,
            width: int,
            height: int,
            bg_img_path: str):
        self.window = window
        self.game = game
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text_dict = self.make_text_dict()
        self.bg_img_path = bg_img_path

        # Whether to use the dark-panel mobile design
        self._use_panel = getattr(settings, 'SCOREBOARD_USE_PANEL', False)

        # Choose text/cross colours based on mode
        if self._use_panel:
            self._text_color = settings.SCOREBOARD_PANEL_TEXT_COLOR
            self._value_color = settings.SCOREBOARD_PANEL_VALUE_COLOR
            self._cross_color = settings.SCOREBOARD_PANEL_CROSS_COLOR
            self._cross_alpha = settings.SCOREBOARD_PANEL_CROSS_ALPHA
        else:
            self._text_color = settings.SCOREBOARD_SCROLL_TEXT_COLOR
            self._value_color = settings.SCOREBOARD_SCROLL_TEXT_COLOR
            self._cross_color = settings.SCOREBOARD_CROSS_COLOR
            self._cross_alpha = settings.SCOREBOARD_CROSS_ALPHA

        self.font_col_names = settings.get_font(settings.SCOREBOARD_SCROLL_FONT_TITLE_SIZE)
        self.font_text = settings.get_font(settings.SCOREBOARD_SCROLL_FONT_SIZE)
        self.font_number = settings.get_font(settings.SCOREBOARD_SCROLL_NUMBER_FONT_SIZE, bold=True)
        self.font_subtitle = settings.get_font(settings.SCOREBOARD_SUBTITLE_FONT_SIZE)

        # Pre-load suit icons for conquer mode
        self._suit_icons = {}
        suit_icon_size = int(self.font_text.get_height() * 1.1)
        for suit_name in ('hearts', 'diamonds', 'clubs', 'spades'):
            try:
                raw = pygame.image.load(
                    settings.SUIT_ICON_IMG_PATH + suit_name + '.png').convert_alpha()
                self._suit_icons[suit_name] = pygame.transform.smoothscale(
                    raw, (suit_icon_size, suit_icon_size))
            except Exception:
                pass

        # Load black and golden rectangle glow images (scale directly to target size)
        glow_w, glow_h = int(width * 1.2), int(height * 1.2)
        raw_black = pygame.image.load(settings.GLOW_RECT_IMG_PATH + 'black.png').convert_alpha()
        self.rect_glow_black = pygame.transform.smoothscale(raw_black, (glow_w, glow_h))
        del raw_black
        raw_yellow = pygame.image.load(settings.GLOW_RECT_IMG_PATH + 'yellow.png').convert_alpha()
        self.rect_glow_yellow = pygame.transform.smoothscale(raw_yellow, (glow_w, glow_h))
        del raw_yellow

        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)

        # Calculate cell dimensions for the scoreboard
        self.cell_width = self.width // 2
        self.cell_height = self.height // 2

        # Adjust height for bottom point-limit section
        self.limit_section_height = settings.SCOREBOARD_LIMIT_SECTION_HEIGHT
        self.cross_height = self.height - self.limit_section_height

        self.init_background()

    @staticmethod
    def _to_int(value, default=0):
        """Safely coerce a numeric value to an integer for display."""
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return default

    def make_text_dict(self):
        """Create a dictionary of text values to display on the scoreboard."""
        if self.game:
            is_conquer = getattr(self.game, 'mode', 'duel') == 'conquer'
            if is_conquer:
                suit = getattr(self.game, 'land_suit_bonus_suit', None) or '?'
                # Landslide inverts the land bonus for the whole battle.
                bonus_getter = getattr(self.game, 'effective_land_bonus', None)
                if callable(bonus_getter):
                    _eff_suit, eff_value = bonus_getter()
                    bonus = self._to_int(eff_value, 0)
                else:
                    bonus = self._to_int(getattr(self.game, 'land_suit_bonus_value', None), 0)
                gold_rate = self._to_int(getattr(self.game, 'land_gold_rate', None), 0)
                scoreboard_dict = {
                    'opponent': self.game.opponent_name,
                    'land_tier': getattr(self.game, 'land_tier', None) or '?',
                    'gold_rate': gold_rate,
                    'suit_bonus_value': bonus,
                    'suit_bonus_suit': suit.lower(),
                    'turns_left': self.game.current_player.get('turns_left', 0),
                }
            else:
                scoreboard_dict = {
                    'opponent': self.game.opponent_name,
                    'date': self.game.date,
                    'turns_left': self.game.current_player.get('turns_left', 0),
                    'round': self.game.current_round,
                    'your_score': self.game.current_player.get('points', 0),
                    'opponent_score': self.game.opponent_player.get('points', 0),
                    'game_limit': (
                        getattr(self.game, 'game_limit', None)
                        or getattr(self.game, 'stake', 45)
                    ),
                }
        else:
            scoreboard_dict = {
                'opponent': 'Opponent',
                'date': '2021-01-01',
                'turns_left': 0,
                'round': 0,
                'your_score': 0,
                'opponent_score': 0,
                'game_limit': 45,
            }
        return scoreboard_dict


    def update(self, game):
        """Update the game state."""
        self.game = game
        self.text_dict = self.make_text_dict()

    def init_background(self):
        """Initialize the background image or build a dark panel for mobile."""
        if self._use_panel:
            r = settings.SCOREBOARD_PANEL_CORNER_R
            self.background = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            pygame.draw.rect(self.background, settings.SCOREBOARD_PANEL_BG_CLR,
                             (0, 0, self.width, self.height), border_radius=r)
            pygame.draw.rect(self.background, settings.SCOREBOARD_PANEL_BORDER_CLR,
                             (0, 0, self.width, self.height),
                             width=settings.SCOREBOARD_PANEL_BORDER_WIDTH, border_radius=r)
        else:
            self.background = pygame.image.load(self.bg_img_path)
            self.background = pygame.transform.smoothscale(self.background, (self.width, self.height))

    def draw_transparent_line(self, start, end, color, width, alpha):
        """Draw a transparent line."""
        surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        pygame.draw.line(surface, (*color, alpha), start, end, width)
        self.window.blit(surface, (self.x, self.y))

    def draw_cross(self):
        """Draw the cross centered on top of the scroll background."""
        # Conquer mode uses a dedicated 2-row layout:
        # top row split into 2 cells, bottom row full-width land summary.
        if self._is_conquer():
            split_y = self.height // 2
            self.draw_transparent_line((0, split_y), (self.width, split_y),
                                       self._cross_color, settings.SCOREBOARD_CROSS_WIDTH,
                                       self._cross_alpha)
            self.draw_transparent_line((self.width // 2, 0), (self.width // 2, split_y),
                                       self._cross_color, settings.SCOREBOARD_CROSS_WIDTH,
                                       self._cross_alpha)
            return

        # The narrow mobile gutter works better as three full-width rows than
        # as four half-width cells.  In particular, this leaves enough room
        # for the opponent name instead of reducing both labels to ellipses.
        if _IS_MOBILE:
            rows = self._mobile_duel_row_rects()
            for row in rows[:-1]:
                line_y = row.bottom - self.y
                self.draw_transparent_line(
                    (0, line_y), (self.width, line_y),
                    self._cross_color, settings.SCOREBOARD_CROSS_WIDTH,
                    self._cross_alpha)
            return

        # Horizontal line — shifted down to match bottom-row offset
        h_y = self.height // 2 + settings.SCOREBOARD_BOTTOM_ROW_EXTRA_Y // 2
        horizontal_line_start = (0, h_y)
        horizontal_line_end = (self.width, h_y)
        # Vertical line
        vertical_line_start = (self.width // 2, 0)
        vertical_line_end = (self.width // 2, self.cross_height)

        self.draw_transparent_line(horizontal_line_start, horizontal_line_end, self._cross_color, settings.SCOREBOARD_CROSS_WIDTH, self._cross_alpha)
        self.draw_transparent_line(vertical_line_start, vertical_line_end, self._cross_color, settings.SCOREBOARD_CROSS_WIDTH, self._cross_alpha)

    def draw_cell(self, text, value, cell_x, cell_y, value_color=None,
                  subtitle=None, subtitle_color=None, y_offset=0, text_spacing=None,
                  value_font=None):
        """Draw the text and value in the specified cell.

        :param subtitle: optional smaller text drawn below the main label (e.g. "(battle)").
        :param y_offset: extra pixels to push the value centre downward (used for top-row cells).
        :param text_spacing: gap between title bottom and value top.  Defaults to SCOREBOARD_CELL_TEXT_SPACING.
        :param value_font: optional font override for the value text.
        """
        if value_color is None:
            value_color = self._value_color
        if text_spacing is None:
            text_spacing = settings.SCOREBOARD_CELL_TEXT_SPACING

        # Render the text and value. Labels must stay inside their cell —
        # long opponent names otherwise collide with the neighbouring cell,
        # so fall back to the subtitle font and then ellipsize.
        text_obj = self.font_text.render(text, True, self._text_color)
        max_label_w = max(12, self.cell_width - 4)
        if text_obj.get_width() > max_label_w:
            label = self._ellipsize(text, self.font_subtitle, max_label_w)
            text_obj = self.font_subtitle.render(label, True, self._text_color)
        vfont = value_font or self.font_number
        value_obj = vfont.render(str(value), True, value_color)

        # Centre text horizontally
        text_rect = text_obj.get_rect(centerx=cell_x + self.cell_width // 2)
        # Centre the value horizontally; push down from cell centre by y_offset
        value_rect = value_obj.get_rect(center=(cell_x + self.cell_width // 2,
                                                cell_y + self.cell_height // 2 + y_offset))

        # Position the title above the value with the given spacing (consistent for every cell in the row)
        text_rect.y = value_rect.y - text_spacing - text_rect.height

        # Draw subtitle between title and value if present (no title shift — keeps alignment)
        if subtitle:
            sub_obj = self.font_subtitle.render(subtitle, True, subtitle_color or (220, 60, 60))
            sub_rect = sub_obj.get_rect(centerx=cell_x + self.cell_width // 2)
            sub_rect.y = text_rect.bottom + 1
            self.window.blit(sub_obj, sub_rect)

        self.window.blit(text_obj, text_rect)
        self.window.blit(value_obj, value_rect)

    def _ellipsize(self, text, font, max_width):
        """Truncate text with an ellipsis so it fits the target width."""
        txt = str(text) if text is not None else ''
        if max_width <= 0:
            return ''
        if font.size(txt)[0] <= max_width:
            return txt

        ellipsis = '…'
        if font.size(ellipsis)[0] > max_width:
            return ''

        lo, hi = 0, len(txt)
        best = ''
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = txt[:mid] + ellipsis
            if font.size(candidate)[0] <= max_width:
                best = candidate
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    def _draw_conquer_cell(self, rect, label, value, *, value_color=None, value_font=None):
        """Draw a simple two-line conquer cell (label + value), centered and overlap-safe."""
        if value_color is None:
            value_color = self._value_color
        vfont = value_font or self.font_number

        inner_pad = max(2, int(0.004 * settings.SCREEN_WIDTH))
        label_surf = self.font_text.render(str(label), True, self._text_color)
        value_txt = self._ellipsize(value, vfont, rect.w - (2 * inner_pad))
        value_surf = vfont.render(value_txt, True, value_color)

        gap = max(1, int(0.003 * settings.SCREEN_HEIGHT))
        total_h = label_surf.get_height() + gap + value_surf.get_height()
        top_y = rect.y + max(0, (rect.h - total_h) // 2)

        label_rect = label_surf.get_rect(centerx=rect.centerx)
        label_rect.y = top_y
        value_rect = value_surf.get_rect(centerx=rect.centerx)
        value_rect.y = label_rect.bottom + gap

        self.window.blit(label_surf, label_rect)
        self.window.blit(value_surf, value_rect)

    def _build_land_segments(self, row_font, separator_text, *, short_gold=False):
        """Build rendered segments for the land summary row."""
        tier = self.text_dict.get('land_tier', '?')
        bonus_val = self._to_int(self.text_dict.get('suit_bonus_value', 0), 0)
        bonus_suit = str(self.text_dict.get('suit_bonus_suit', '') or '').lower()
        gold_rate = self._to_int(self.text_dict.get('gold_rate', 0), 0)

        tier_surf = row_font.render(f'T{tier}', True, self._value_color)
        sep_surf = row_font.render(separator_text, True, self._text_color)
        bonus_surf = row_font.render(f'+{bonus_val}', True, (200, 180, 120))
        gold_label = f'{gold_rate}/h' if short_gold else f'{gold_rate} gold/hr'
        gold_surf = row_font.render(gold_label, True, (250, 221, 0))

        segments = [tier_surf, sep_surf, bonus_surf]

        suit_icon = self._suit_icons.get(bonus_suit)
        if suit_icon:
            segments.append(suit_icon)
        elif bonus_suit and bonus_suit != '?':
            suit_fallback = row_font.render(bonus_suit[:1].upper(), True, self._value_color)
            segments.append(suit_fallback)

        segments.extend([sep_surf, gold_surf])
        return segments

    def _draw_conquer_land_cell(self, rect):
        """Draw the merged land cell: tier, suit bonus, and integer gold production."""
        label_surf = self.font_text.render('Land', True, self._text_color)

        row_font = self.font_text
        segments = self._build_land_segments(row_font, ' · ')

        inner_pad = max(2, int(0.004 * settings.SCREEN_WIDTH))
        gap_x = max(1, int(0.0025 * settings.SCREEN_WIDTH))

        def _segments_width(parts):
            if not parts:
                return 0
            return sum(p.get_width() for p in parts) + gap_x * (len(parts) - 1)

        max_inner_w = rect.w - (2 * inner_pad)
        if _segments_width(segments) > max_inner_w:
            row_font = self.font_subtitle
            segments = self._build_land_segments(row_font, '·')
        if _segments_width(segments) > max_inner_w:
            segments = self._build_land_segments(row_font, '·', short_gold=True)

        row_h = max((s.get_height() for s in segments), default=0)
        gap_y = max(1, int(0.003 * settings.SCREEN_HEIGHT))
        total_h = label_surf.get_height() + gap_y + row_h
        top_y = rect.y + max(0, (rect.h - total_h) // 2)

        label_rect = label_surf.get_rect(centerx=rect.centerx)
        label_rect.y = top_y
        self.window.blit(label_surf, label_rect)

        total_w = _segments_width(segments)
        row_y = label_rect.bottom + gap_y
        cursor_x = rect.x + max(inner_pad, (rect.w - total_w) // 2)
        for seg in segments:
            seg_y = row_y + (row_h - seg.get_height()) // 2
            self.window.blit(seg, (cursor_x, seg_y))
            cursor_x += seg.get_width() + gap_x

    def draw_game_limit(self):
        """Draw the game point limit at the bottom of the scoreboard."""
        limit_text = self.text_dict.get("game_limit", "")
        limit_obj = self.font_col_names.render(f"{limit_text}", True, self._text_color)

        # Position at the bottom center of the scoreboard
        limit_rect = limit_obj.get_rect(center=(
            self.x + self.width // 2,
            self.y + self.height - self.limit_section_height // 2,
        ))
        self.window.blit(limit_obj, limit_rect)

    def _is_conquer(self):
        """Check if we're in conquer mode."""
        return self.game and getattr(self.game, 'mode', 'duel') == 'conquer'

    def _mobile_duel_row_rects(self):
        """Return bounded rows for the mobile duel scoreboard.

        The two score rows receive any remainder pixels, while the final
        metadata row is kept large enough for the shared mobile text floor.
        """
        inset = max(1, settings.SCOREBOARD_PANEL_BORDER_WIDTH)
        inner = pygame.Rect(
            self.x + inset,
            self.y + inset,
            max(1, self.width - (2 * inset)),
            max(3, self.height - (2 * inset)),
        )
        meta_h = min(
            inner.h - 2,
            max(self.font_subtitle.get_height() + 2, inner.h // 3),
        )
        score_h = inner.h - meta_h
        your_h = score_h // 2
        return (
            pygame.Rect(inner.x, inner.y, inner.w, your_h),
            pygame.Rect(inner.x, inner.y + your_h, inner.w, score_h - your_h),
            pygame.Rect(inner.x, inner.bottom - meta_h, inner.w, meta_h),
        )

    def _draw_mobile_score_row(self, rect, label, value, value_color):
        """Draw one readable label/value line and return its drawn bounds."""
        pad_x = max(3, int(0.004 * settings.SCREEN_WIDTH))
        gap = max(2, int(0.002 * settings.SCREEN_WIDTH))

        value_obj = self.font_number.render(str(value), True, value_color)
        value_rect = value_obj.get_rect(
            midright=(rect.right - pad_x, rect.centery))

        label_left = rect.x + pad_x
        max_label_w = max(1, value_rect.left - gap - label_left)
        fitted_label = self._ellipsize(
            label, self.font_subtitle, max_label_w)
        label_obj = self.font_subtitle.render(
            fitted_label, True, self._text_color)
        label_rect = label_obj.get_rect(
            midleft=(label_left, rect.centery))

        self.window.blit(label_obj, label_rect)
        self.window.blit(value_obj, value_rect)
        return label_rect, value_rect

    def _mobile_duel_meta_tokens(self, in_battle, max_width):
        """Build turn, round, and target tokens that fit the metadata row."""
        turns = (
            getattr(self.game, 'battle_turns_left', 0)
            if in_battle
            else self.text_dict.get('turns_left', 0)
        )
        round_number = self.text_dict.get('round', 0)
        target = self.text_dict.get('game_limit', '')
        phase_color = (220, 60, 60) if in_battle else self._text_color

        phase_word = 'Battle' if in_battle else 'Turns'
        tokens = [
            (f'{phase_word} {turns}', phase_color),
            (f'R{round_number}', self._value_color),
            (f'/{target}', (250, 221, 0)),
        ]
        gap = max(1, int(0.0015 * settings.SCREEN_WIDTH))
        total_w = (
            sum(self.font_subtitle.size(text)[0] for text, _ in tokens)
            + gap * (len(tokens) - 1)
        )
        if total_w > max_width:
            phase_letter = 'B' if in_battle else 'T'
            tokens[0] = (f'{phase_letter}{turns}', phase_color)
        return tokens

    def _draw_mobile_duel_meta(self, rect, in_battle):
        """Draw the compact turn / round / target footer."""
        pad_x = max(2, int(0.002 * settings.SCREEN_WIDTH))
        gap = max(1, int(0.0015 * settings.SCREEN_WIDTH))
        tokens = self._mobile_duel_meta_tokens(
            in_battle, rect.w - (2 * pad_x))
        rendered = [
            (self.font_subtitle.render(text, True, color), text)
            for text, color in tokens
        ]
        total_w = (
            sum(surface.get_width() for surface, _ in rendered)
            + gap * (len(rendered) - 1)
        )
        cursor_x = rect.centerx - total_w // 2
        drawn = []
        for surface, text in rendered:
            token_rect = surface.get_rect(
                midleft=(cursor_x, rect.centery))
            self.window.blit(surface, token_rect)
            drawn.append((text, token_rect))
            cursor_x = token_rect.right + gap
        return drawn

    def _draw_mobile_duel_msg(self, in_battle):
        """Render the duel scoreboard as three scan-friendly mobile rows."""
        your_row, opponent_row, meta_row = self._mobile_duel_row_rects()
        self._draw_mobile_score_row(
            your_row,
            'You',
            self.text_dict.get('your_score', ''),
            settings.COLOR_GREEN,
        )
        self._draw_mobile_score_row(
            opponent_row,
            self.text_dict.get('opponent', 'Opponent'),
            self.text_dict.get('opponent_score', ''),
            settings.COLOR_RED,
        )
        self._draw_mobile_duel_meta(meta_row, in_battle)

    def draw_msg(self):
        """Render the scoreboard content."""
        if self._is_conquer():
            self._draw_conquer_msg()
        else:
            self._draw_duel_msg()

    def _draw_conquer_msg(self):
        """Render conquer-mode scoreboard with semantic cells.

        Layout:
        - Top-left: opponent
        - Top-right: battle/build turns
        - Bottom (full width): land summary (tier + suit bonus + gold/hr)
        """
        top_h = self.height // 2
        top_left_rect = pygame.Rect(self.x, self.y, self.cell_width, top_h)
        top_right_rect = pygame.Rect(self.x + self.cell_width, self.y,
                                     self.width - self.cell_width, top_h)
        bottom_rect = pygame.Rect(self.x, self.y + top_h, self.width, self.height - top_h)

        # Top-left: Opponent name (ellipsized to avoid overlap)
        opponent_label = self.text_dict.get('opponent', 'Opponent')
        opponent_value = self._ellipsize(opponent_label, self.font_text,
                                         top_left_rect.w - max(4, int(0.008 * settings.SCREEN_WIDTH)))
        self._draw_conquer_cell(top_left_rect, 'Opponent', opponent_value,
                                value_color=(220, 90, 80), value_font=self.font_text)

        # Top-right: simplified turns label
        in_battle = (getattr(self.game, 'in_battle_phase', False) or
                     (getattr(self.game, 'battle_confirmed', False) and
                      getattr(self.game, 'battle_turn_player_id', None) is not None))
        if in_battle:
            battle_turns = getattr(self.game, 'battle_turns_left', 0)
            self._draw_conquer_cell(top_right_rect, 'Battle Turns', battle_turns,
                                    value_color=(220, 60, 60))
        else:
            self._draw_conquer_cell(top_right_rect, 'Turns Left',
                                    self.text_dict.get('turns_left', ''))

        # Bottom: merged land summary cell
        self._draw_conquer_land_cell(bottom_rect)

    def _draw_duel_msg(self):
        """Render the standard duel-mode scoreboard content."""
        # Top-row cells share offset + subtitle spacing so labels & values stay aligned
        top_offset = settings.SCOREBOARD_CELL_VALUE_OFFSET
        top_spacing = settings.SCOREBOARD_CELL_SUBTITLE_SPACING

        # During an active battle, show battle turns with a "(battle)" subtitle
        # Use both client-side flag and server-side indicators as fallback (web compatibility)
        in_battle = False
        if self.game:
            in_battle = (getattr(self.game, 'in_battle_phase', False) or
                         (getattr(self.game, 'battle_confirmed', False) and
                          getattr(self.game, 'battle_turn_player_id', None) is not None))
        if _IS_MOBILE:
            self._draw_mobile_duel_msg(in_battle)
            return

        if in_battle:
            battle_turns = getattr(self.game, 'battle_turns_left', 0)
            self.draw_cell("Turns Left", battle_turns, self.x, self.y,
                           subtitle="(battle)",
                           subtitle_color=(220, 60, 60),
                           y_offset=top_offset, text_spacing=top_spacing)
        else:
            self.draw_cell("Turns Left", self.text_dict.get("turns_left", ""), self.x, self.y,
                           subtitle="(build-up)",
                           subtitle_color=(90, 115, 150),
                           y_offset=top_offset, text_spacing=top_spacing)
        self.draw_cell("Round", self.text_dict.get("round", ""), self.x + self.cell_width, self.y,
                       y_offset=top_offset, text_spacing=top_spacing)
        # Nudge bottom-row cells down so there's more visual separation from the top row
        _bot_extra = settings.SCOREBOARD_BOTTOM_ROW_EXTRA_Y
        _bot_offset = int(0.008 * settings.SCREEN_HEIGHT) if _IS_MOBILE else 0
        self.draw_cell("You", self.text_dict.get("your_score", ""), self.x, self.y + self.cell_height + _bot_extra, settings.COLOR_GREEN,
                       y_offset=_bot_offset)
        opponent_label = self.text_dict.get("opponent", "Opponent")
        self.draw_cell(opponent_label, self.text_dict.get("opponent_score", ""), self.x + self.cell_width, self.y + self.cell_height + _bot_extra, settings.COLOR_RED,
                       y_offset=_bot_offset)

        # Draw the point limit value
        self.draw_game_limit()

    def draw(self):
        """Draw the background, cross, and message to the screen."""
        # Glow effect based on mouse hover
        if self.collide():
            self.window.blit(self.rect_glow_yellow, (self.x - 0.1 * self.width, self.y - 0.1 * self.height))
        else:
            self.window.blit(self.rect_glow_black, (self.x - 0.1 * self.width, self.y - 0.1 * self.height))

        # Draw the background
        self.window.blit(self.background, (self.x, self.y))

        # Draw the cross and scoreboard
        self.draw_cross()
        self.draw_msg()

    def collide(self):
        """Check if the mouse is over the scroll."""
        return self.rect.collidepoint(pygame.mouse.get_pos())
