"""Detail box for a bought battle move, similar to FigureDetailBox.

Supports two modes:
  - Shop context (default): shows a Return button + figure selector for Call moves.
  - Battle context: shows action buttons (use!/gamble!/combine!) + figure selector
    for Call moves.

The figure selector (list-shifter) is shown in BOTH modes for Call moves.
"""

import pygame
from config import settings
from utils.utils import Button
from game.components.cards.card_img import CardImg
from game.components.buttons.confirm_button import ConfirmButton
from game.components.arrow_button import ArrowButton

# Suit colour classification
_RED_SUITS = {'Hearts', 'Diamonds'}
_BLACK_SUITS = {'Clubs', 'Spades'}


class BattleMoveDetailBox:
    """A detail info box displayed when clicking a bought battle move slot.

    Shows the family icon, name, description, card, suit, power value,
    and either a Return button (shop) or action buttons (battle).
    For Call moves, a figure list-shifter is always shown.
    """

    # Maps Call family names → figure field types
    CALL_FIELD_MAP = {
        'Call Villager': 'village',
        'Call Military': 'military',
        'Call King': 'castle',
    }

    def __init__(self, window, battle_move_data, families_by_name, game,
                 is_battle_context=False, eligible_figures=None, move_index=None,
                 gamble_disabled=False, use_disabled=False, combine_disabled=False,
                 combinable_daggers=None, dismantle_disabled=False):
        """
        :param window: pygame surface
        :param battle_move_data: server dict with keys: id, family_name, suit, rank, value, card_id, card_type
        :param families_by_name: dict mapping family name -> BattleMoveFamily
        :param game: game object
        :param is_battle_context: True when opened from the battle screen
        :param eligible_figures: list of Figure objects eligible for a Call move (pre-filtered)
        :param move_index: index of the move in the player_moves list (0-2)
        :param gamble_disabled: True to grey out the gamble button
        :param use_disabled: True to grey out the use button
        :param combine_disabled: True to grey out the combine button
        :param combinable_daggers: list of dagger move dicts eligible to combine with this dagger
        :param dismantle_disabled: True to grey out the dismantle button
        """
        self.window = window
        self.bm = battle_move_data
        self.game = game

        self.is_battle_context = is_battle_context
        self.eligible_figures = eligible_figures or []
        self.move_index = move_index
        self.gamble_disabled = gamble_disabled
        self.use_disabled = use_disabled
        self.combine_disabled = combine_disabled
        self.dismantle_disabled = dismantle_disabled
        self.combinable_daggers = combinable_daggers or []

        self.family = families_by_name.get(battle_move_data['family_name'])

        family_name = battle_move_data.get('family_name', '')
        self.is_call_move = family_name in self.CALL_FIELD_MAP
        self.is_dagger_move = (family_name == 'Dagger')
        self.is_double_dagger_move = (family_name == 'Double Dagger')
        self.is_block_move = (family_name == 'Block')

        # Determine the effective display power for this battle move
        raw_value = battle_move_data.get('value', 0)
        self.display_power = 0 if self.is_block_move else raw_value

        # Battle move suit colour (red / black)
        bm_suit = battle_move_data.get('suit', '')
        self.bm_is_red = bm_suit in _RED_SUITS

        # Fonts
        self.title_font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_TITLE_DIALOGUE_BOX)
        self.title_font.set_bold(True)
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DIALOGUE_BOX)
        self.small_font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DIALOGUE_BOX - 4)
        self.value_font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DIALOGUE_BOX)
        self.value_font.set_bold(True)

        # Card image(s)
        card_w = int(settings.SCREEN_WIDTH * 0.038)
        card_h = int(card_w * 1.4)
        self.card_img_b = None  # second card for Double Dagger

        if self.is_double_dagger_move:
            # Double Dagger: show both source cards side-by-side
            rank_str = battle_move_data.get('rank', '')
            ranks = rank_str.split('+') if '+' in rank_str else [rank_str, rank_str]
            suit_a = battle_move_data.get('suit', '')
            suit_b = battle_move_data.get('suit_b', suit_a)
            self.card_img = CardImg(window, suit_a, ranks[0], width=card_w, height=card_h)
            self.card_img_b = CardImg(window, suit_b, ranks[1] if len(ranks) > 1 else ranks[0],
                                      width=card_w, height=card_h)
        else:
            self.card_img = CardImg(
                window, battle_move_data['suit'], battle_move_data['rank'],
                width=card_w, height=card_h,
            )

        # Family icon (scaled for the detail box)
        self.family_icon = None
        if self.family and self.family.icon_img:
            icon_size = int(settings.SCREEN_WIDTH * 0.07)
            self.family_icon = pygame.transform.smoothscale(
                self.family.icon_img.convert_alpha(), (icon_size, icon_size)
            )

        # Family frame
        self.family_frame = None
        if self.family and self.family.frame_img:
            frame_size = int(settings.SCREEN_WIDTH * 0.07 * settings.BATTLE_MOVE_FRAME_SCALE)
            self.family_frame = pygame.transform.smoothscale(
                self.family.frame_img.convert_alpha(), (frame_size, frame_size)
            )

        # Suit icon
        self.suit_icon = self._load_suit_icon(battle_move_data['suit'])

        # ── Figure selector assets (pre-scale only, no positioning) ──
        self.fig_selector_index = 0
        self.fig_arrow_left = None
        self.fig_arrow_right = None
        self.fig_icons = {}
        self.fig_frames = {}
        self.fig_suit_icons = {}
        self.fig_icon_size = int(settings.SCREEN_WIDTH * 0.05)
        self._fig_shift_cooldown = 200
        self._fig_last_shift_time = 0
        self._has_fig_selector = self.is_call_move and bool(self.eligible_figures)

        if self._has_fig_selector:
            self._prepare_fig_assets()

        # ── Dagger combine selector assets ──
        self.dagger_selector_index = 0
        self.dagger_arrow_left = None
        self.dagger_arrow_right = None
        self._dagger_shift_cooldown = 200
        self._dagger_last_shift_time = 0
        self._has_dagger_selector = (self.is_dagger_move and bool(self.combinable_daggers)
                                     and self.is_battle_context)

        if self._has_dagger_selector:
            self._prepare_dagger_assets()

        # ── Dynamic layout: compute total height and key Y positions ──
        self.width = int(settings.SCREEN_WIDTH * 0.35)
        content_h, fig_cy_rel, dagger_cy_rel, btn_y_rel = self._compute_layout()
        self._dagger_cy_rel = dagger_cy_rel
        self.height = content_h

        self.x = (settings.SCREEN_WIDTH - self.width) // 2
        self.y = (settings.SCREEN_HEIGHT - self.height) // 2

        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)
        self.border_rect = self.rect.inflate(
            settings.DIALOGUE_BOX_BORDER_WIDTH, settings.DIALOGUE_BOX_BORDER_WIDTH
        )

        # Close button (X) — top-right
        cb_size = 30
        cb_margin = 10
        self.close_button_rect = pygame.Rect(
            self.rect.right - cb_size - cb_margin,
            self.rect.top + cb_margin,
            cb_size, cb_size,
        )
        self.close_button_hovered = False
        self.close_button_clicked = False

        # ── Create interactive elements at computed absolute positions ──
        self.return_button = None
        self.action_buttons = []

        abs_btn_y = self.y + btn_y_rel
        if is_battle_context:
            self._create_action_buttons(abs_btn_y)
        else:
            btn_x = self.rect.centerx - settings.MENU_BUTTON_WIDTH // 2
            self.return_button = Button(window, btn_x, abs_btn_y, "Return")
            self.return_button.disabled = False

        if self._has_fig_selector:
            self._create_fig_arrows(self.y + fig_cy_rel)

        if self._has_dagger_selector:
            self._create_dagger_arrows(self.y + self._dagger_cy_rel)

    # ────────────────── init helpers ─────────────────────────────

    def _prepare_fig_assets(self):
        """Pre-scale icon/frame/suit images for eligible figures (no positioning)."""
        frame_s = int(self.fig_icon_size * settings.BATTLE_MOVE_FRAME_SCALE)
        for fig in self.eligible_figures:
            if fig.family.icon_img:
                self.fig_icons[fig.id] = pygame.transform.smoothscale(
                    fig.family.icon_img.convert_alpha(),
                    (self.fig_icon_size, self.fig_icon_size),
                )
            if fig.family.frame_img:
                self.fig_frames[fig.id] = pygame.transform.smoothscale(
                    fig.family.frame_img.convert_alpha(),
                    (frame_s, frame_s),
                )
            suit_lower = fig.suit.lower()
            if suit_lower not in self.fig_suit_icons:
                try:
                    img = pygame.image.load(
                        settings.SUIT_ICON_IMG_PATH + suit_lower + '.png'
                    ).convert_alpha()
                    s = int(settings.SUIT_ICON_WIDTH * 0.5)
                    self.fig_suit_icons[suit_lower] = pygame.transform.smoothscale(img, (s, s))
                except Exception:
                    pass

    def _prepare_dagger_assets(self):
        """Pre-scale icon/frame/suit images for combinable daggers."""
        icon_s = self.fig_icon_size
        frame_s = int(icon_s * settings.BATTLE_MOVE_FRAME_SCALE)
        self.dagger_icons = {}
        self.dagger_frames = {}
        self.dagger_suit_icons = {}

        for d in self.combinable_daggers:
            d_id = d['id']
            # Load the dagger family icon/frame
            dagger_family = self.family  # same Dagger family
            if dagger_family and dagger_family.icon_img:
                self.dagger_icons[d_id] = pygame.transform.smoothscale(
                    dagger_family.icon_img.convert_alpha(), (icon_s, icon_s)
                )
            if dagger_family and dagger_family.frame_img:
                self.dagger_frames[d_id] = pygame.transform.smoothscale(
                    dagger_family.frame_img.convert_alpha(), (frame_s, frame_s)
                )
            suit_lower = d.get('suit', '').lower()
            if suit_lower and suit_lower not in self.dagger_suit_icons:
                try:
                    img = pygame.image.load(
                        settings.SUIT_ICON_IMG_PATH + suit_lower + '.png'
                    ).convert_alpha()
                    s = int(settings.SUIT_ICON_WIDTH * 0.5)
                    self.dagger_suit_icons[suit_lower] = pygame.transform.smoothscale(img, (s, s))
                except Exception:
                    pass

    def _create_dagger_arrows(self, content_cy):
        """Create left/right arrow buttons for the dagger combine selector."""
        arrow_pad = int(self.width * 0.10)
        self.dagger_arrow_left = ArrowButton(
            self.window, self._shift_dagger_left,
            self.rect.left + arrow_pad, content_cy,
            direction='left', is_active=True,
        )
        self.dagger_arrow_right = ArrowButton(
            self.window, self._shift_dagger_right,
            self.rect.right - arrow_pad, content_cy,
            direction='right', is_active=True,
        )

    def _shift_dagger_left(self):
        now = pygame.time.get_ticks()
        if now - self._dagger_last_shift_time >= self._dagger_shift_cooldown:
            self.dagger_selector_index = (self.dagger_selector_index - 1) % len(self.combinable_daggers)
            self._dagger_last_shift_time = now

    def _shift_dagger_right(self):
        now = pygame.time.get_ticks()
        if now - self._dagger_last_shift_time >= self._dagger_shift_cooldown:
            self.dagger_selector_index = (self.dagger_selector_index + 1) % len(self.combinable_daggers)
            self._dagger_last_shift_time = now

    def get_selected_dagger(self):
        """Return the currently selected dagger move dict, or None."""
        if self.combinable_daggers and 0 <= self.dagger_selector_index < len(self.combinable_daggers):
            return self.combinable_daggers[self.dagger_selector_index]
        return None

    def _compute_layout(self):
        """Simulate the vertical content flow and return
        (total_height, fig_content_cy_rel, dagger_cy_rel, btn_y_rel).

        All Y values are relative to the box top.
        fig_content_cy_rel is 0 when there is no figure selector.
        dagger_cy_rel is 0 when there is no dagger selector.
        """
        pad = settings.SMALL_SPACER_Y
        y = pad

        # Title
        y += self.title_font.get_height() + pad // 2
        # Divider
        y += int(pad * 1.4)
        # Family icon
        if self.family_icon:
            y += self.family_icon.get_height() + pad
        # Description
        if self.family:
            lines = self._wrap_text(self.family.description, self.width - pad * 4)
            y += len(lines) * (self.small_font.get_height() + 2) + pad
        # Card row
        y += self.card_img.front_img.get_height() + pad // 2

        # Double Dagger: extra rows for suit icons + power label below cards
        if self.is_double_dagger_move:
            si_size = int(settings.SUIT_ICON_WIDTH * 0.7)
            y += max(si_size, self.small_font.get_height()) + 4   # suit row
            y += self.value_font.get_height() + pad // 2           # power row

        # Figure selector
        fig_cy_rel = 0
        if self._has_fig_selector:
            y += pad                                                  # gap before divider
            y += self.small_font.get_height() + pad                   # "Select figure:" label
            fig_cy_rel = y + self.fig_icon_size // 2                  # icon centre
            y += self.fig_icon_size + pad // 2
            y += self.small_font.get_height() + pad                   # counter "1 / N"

        # Dagger combine selector
        dagger_cy_rel = 0
        dagger_icon_size = self.fig_icon_size  # same size as figure selector
        if self._has_dagger_selector:
            y += pad
            y += self.small_font.get_height() + pad                   # "Combine with:" label
            dagger_cy_rel = y + dagger_icon_size // 2
            y += dagger_icon_size + pad // 2
            y += self.small_font.get_height() + pad                   # counter "1 / N"

        # Buttons
        btn_y_rel = y
        btn_gap = 5
        if self.is_battle_context:
            btn_h = int(settings.SCREEN_HEIGHT * 0.026)
            if self.is_double_dagger_move:
                n = 2  # use! + dismantle!
            elif self.is_dagger_move:
                n = 3  # use! + gamble! + combine!
            else:
                n = 2  # use! + gamble!
            y += n * (btn_h + btn_gap)
        else:
            y += settings.MENU_BUTTON_HEIGHT

        y += int(pad * 1.5)  # bottom padding
        return y, fig_cy_rel, dagger_cy_rel, btn_y_rel

    def _wrap_text(self, text, max_width):
        """Split text into lines that fit within max_width using small_font."""
        words = text.split(' ')
        lines = []
        current = ''
        for word in words:
            test = (current + ' ' + word).strip()
            if self.small_font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or ['']

    def _create_action_buttons(self, start_y):
        """Create use!/gamble!/combine! buttons flowing down from start_y."""
        btn_w = int(self.width * 0.26)
        btn_h = int(settings.SCREEN_HEIGHT * 0.026)
        btn_gap = 5
        cx = self.rect.centerx

        actions = [('use', 'use!')]
        if self.is_double_dagger_move:
            actions.append(('dismantle', 'dismantle!'))
        elif self.is_dagger_move:
            actions.append(('gamble', 'gamble!'))
            actions.append(('combine', 'combine!'))
        else:
            actions.append(('gamble', 'gamble!'))

        self.action_buttons = []
        for i, (action_id, label) in enumerate(actions):
            btn_y = start_y + i * (btn_h + btn_gap)
            btn_x = cx - btn_w // 2
            btn = ConfirmButton(self.window, btn_x, btn_y, label, width=btn_w, height=btn_h)
            if action_id == 'gamble' and self.gamble_disabled:
                btn.disabled = True
            if action_id == 'use' and self.use_disabled:
                btn.disabled = True
            if action_id == 'combine' and self.combine_disabled:
                btn.disabled = True
            if action_id == 'dismantle' and self.dismantle_disabled:
                btn.disabled = True
            self.action_buttons.append((action_id, btn))

    def _create_fig_arrows(self, content_cy):
        """Create left/right arrow buttons at the figure selector row."""
        arrow_pad = int(self.width * 0.10)
        self.fig_arrow_left = ArrowButton(
            self.window, self._shift_fig_left,
            self.rect.left + arrow_pad, content_cy,
            direction='left', is_active=True,
        )
        self.fig_arrow_right = ArrowButton(
            self.window, self._shift_fig_right,
            self.rect.right - arrow_pad, content_cy,
            direction='right', is_active=True,
        )

    def _shift_fig_left(self):
        now = pygame.time.get_ticks()
        if now - self._fig_last_shift_time >= self._fig_shift_cooldown:
            self.fig_selector_index = (self.fig_selector_index - 1) % len(self.eligible_figures)
            self._fig_last_shift_time = now

    def _shift_fig_right(self):
        now = pygame.time.get_ticks()
        if now - self._fig_last_shift_time >= self._fig_shift_cooldown:
            self.fig_selector_index = (self.fig_selector_index + 1) % len(self.eligible_figures)
            self._fig_last_shift_time = now

    def get_selected_figure(self):
        """Return the currently selected Figure, or None."""
        if self.eligible_figures and 0 <= self.fig_selector_index < len(self.eligible_figures):
            return self.eligible_figures[self.fig_selector_index]
        return None

    # ────────────────── suit-match power helpers ───────────────

    def _suits_match(self, fig):
        """Check if the figure's suit matches the battle move's suit exactly."""
        return fig.suit == self.bm.get('suit', '')

    def _figure_colour_compatible(self, fig):
        """Red battle move → red figure suit; black → black."""
        if self.bm_is_red:
            return fig.suit in _RED_SUITS
        else:
            return fig.suit in _BLACK_SUITS

    def _get_call_power_parts(self, fig):
        """Return (figure_base_power, move_bonus) for a Call move.

        move_bonus = battle move value if both suits match exactly, else 0.
        """
        base = fig.get_value()
        bonus = self.display_power if self._suits_match(fig) else 0
        return base, bonus

    # ---------------------------------------------------------------- helpers
    def _load_suit_icon(self, suit):
        suit_lower = suit.lower()
        try:
            img = pygame.image.load(settings.SUIT_ICON_IMG_PATH + suit_lower + '.png').convert_alpha()
            size = int(settings.SUIT_ICON_WIDTH * 0.7)
            return pygame.transform.smoothscale(img, (size, size))
        except Exception:
            return None

    # ------------------------------------------------------------------ draw
    def draw(self):
        """Draw the detail box with fully dynamic vertical flow."""
        # Border + background
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX_BORDER, self.border_rect)
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX, self.rect)

        pad = settings.SMALL_SPACER_Y
        cx = self.rect.centerx
        cur_y = self.rect.top + pad

        # ── Title ──
        title_surf = self.title_font.render(self.bm['family_name'], True, settings.TITLE_TEXT_COLOR)
        self.window.blit(title_surf, title_surf.get_rect(centerx=cx, top=cur_y))
        cur_y += title_surf.get_height() + pad // 2

        # ── Divider ──
        pygame.draw.line(self.window, settings.COLOR_DIALOGUE_BOX_BORDER,
                         (self.rect.left + pad, cur_y), (self.rect.right - pad, cur_y), 2)
        cur_y += int(pad * 1.4)

        # ── Family icon + frame ──
        if self.family_icon:
            ir = self.family_icon.get_rect(centerx=cx, top=cur_y)
            self.window.blit(self.family_icon, ir.topleft)
            if self.family_frame:
                fr = self.family_frame.get_rect(center=ir.center)
                self.window.blit(self.family_frame, fr.topleft)
            cur_y = ir.bottom + pad

        # ── Description ──
        if self.family:
            lines = self._wrap_text(self.family.description, self.width - pad * 4)
            for line in lines:
                surf = self.small_font.render(line, True, settings.TITLE_TEXT_COLOR)
                self.window.blit(surf, surf.get_rect(centerx=cx, top=cur_y))
                cur_y += surf.get_height() + 2
            cur_y += pad

        # ── Card + suit + power row ──
        row_y = cur_y
        card_w = self.card_img.front_img.get_width()
        card_h = self.card_img.front_img.get_height()

        if self.card_img_b:
            # Double Dagger: two cards side-by-side, centred
            gap_cards = 6
            cards_total_w = card_w * 2 + gap_cards
            card_x_a = cx - cards_total_w // 2
            self.card_img.draw_front(card_x_a, row_y)
            self.card_img_b.draw_front(card_x_a + card_w + gap_cards, row_y)
            cur_y = row_y + card_h + pad // 2

            # Suits and power below the cards for Double Dagger
            suit_a = self.bm.get('suit', '')
            suit_b_name = self.bm.get('suit_b', suit_a)
            icon_a = self._load_suit_icon(suit_a) if suit_a else None
            icon_b = self._load_suit_icon(suit_b_name) if suit_b_name else None
            # Draw suit icons + text centred
            si_h = 0
            suit_items = []
            for si in (icon_a, icon_b):
                if si:
                    suit_items.append(si)
                    si_h = max(si_h, si.get_height())
            suit_text = f"{suit_a} + {suit_b_name}" if suit_b_name != suit_a else suit_a
            suit_surf = self.small_font.render(suit_text, True, settings.TITLE_TEXT_COLOR)
            # Total width: icons + gap + text
            icons_w = sum(si.get_width() for si in suit_items) + 4 * (len(suit_items) - 1) if suit_items else 0
            total_suit_w = icons_w + 6 + suit_surf.get_width() if suit_items else suit_surf.get_width()
            sx = cx - total_suit_w // 2
            for si in suit_items:
                self.window.blit(si, (sx, cur_y))
                sx += si.get_width() + 4
            if suit_items:
                sx += 2  # extra gap before text
            self.window.blit(suit_surf, (sx, cur_y + (si_h - suit_surf.get_height()) // 2 if si_h else 0))
            cur_y += max(si_h, suit_surf.get_height()) + 4
            self._draw_power_label_centred(cx, cur_y)
            cur_y += self.value_font.get_height() + pad // 2
        else:
            card_x = cx - card_w - pad
            self.card_img.draw_front(card_x, row_y)

            info_x = cx + pad
            if self.suit_icon:
                self.window.blit(self.suit_icon, (info_x, row_y))
                si_h = self.suit_icon.get_height()
            else:
                si_h = 0
            suit_surf = self.small_font.render(self.bm['suit'], True, settings.TITLE_TEXT_COLOR)
            self.window.blit(suit_surf, (info_x, row_y + si_h + 4))
            self._draw_power_label(info_x, row_y + si_h + suit_surf.get_height() + 8)

            cur_y = row_y + card_h + pad // 2

        # ── Figure selector (Call moves, both contexts) ──
        if self._has_fig_selector:
            cur_y = self._draw_figure_selector(cur_y)

        # ── Dagger combine selector ──
        if self._has_dagger_selector:
            cur_y = self._draw_dagger_selector(cur_y)

        # ── Bottom buttons (drawn at pre-computed positions) ──
        if self.is_battle_context:
            for _aid, btn in self.action_buttons:
                btn.draw()
        elif self.return_button:
            self.return_button.draw()

        # ── Close (X) button ──
        self._draw_close_button()

    # ────────────────── power label ────────────────────────────

    def _draw_power_label(self, x, y):
        """Draw the power label.  For Call moves with a selected figure
        show   Power: Y + X   where Y = figure base, X = move bonus (green if matching).
        For Double Daggers show   Power: A + B = total.
        """
        if self.is_double_dagger_move:
            va = self.bm.get('value_a', 0)
            vb = self.bm.get('value_b', 0)
            total = va + vb
            parts = [
                self.value_font.render(f"Power: {va}", True, (220, 180, 100)),
                self.value_font.render(" + ", True, (220, 180, 100)),
                self.value_font.render(f"{vb}", True, (220, 180, 100)),
                self.value_font.render(f" = {total}", True, (80, 200, 80)),
            ]
            cur_x = x
            for surf in parts:
                self.window.blit(surf, (cur_x, y))
                cur_x += surf.get_width()
            return

        if self.is_call_move and self.eligible_figures:
            fig = self.get_selected_figure()
            if fig:
                base, bonus = self._get_call_power_parts(fig)
                parts = []
                if base > 0:
                    parts.append(self.value_font.render(f"Power: {base}", True, (220, 180, 100)))
                    if bonus > 0:
                        parts.append(self.value_font.render(" + ", True, (220, 180, 100)))
                        parts.append(self.value_font.render(str(bonus), True, (80, 200, 80)))
                elif bonus > 0:
                    parts.append(self.value_font.render(f"Power: {bonus}", True, (80, 200, 80)))
                else:
                    parts.append(self.value_font.render("Power: 0", True, (220, 180, 100)))

                cur_x = x
                for surf in parts:
                    self.window.blit(surf, (cur_x, y))
                    cur_x += surf.get_width()
                return

        val_surf = self.value_font.render(f"Power: {self.display_power}", True, (220, 180, 100))
        self.window.blit(val_surf, (x, y))

    def _draw_power_label_centred(self, cx, y):
        """Draw power label centred at cx. Used for Double Dagger layout."""
        va = self.bm.get('value_a', 0)
        vb = self.bm.get('value_b', 0)
        total = va + vb
        parts = [
            self.value_font.render(f"Power: {va}", True, (220, 180, 100)),
            self.value_font.render(" + ", True, (220, 180, 100)),
            self.value_font.render(f"{vb}", True, (220, 180, 100)),
            self.value_font.render(f" = {total}", True, (80, 200, 80)),
        ]
        total_w = sum(s.get_width() for s in parts)
        cur_x = cx - total_w // 2
        for surf in parts:
            self.window.blit(surf, (cur_x, y))
            cur_x += surf.get_width()

    # ────────────────── figure selector drawing ────────────────

    def _draw_figure_selector(self, cur_y):
        """Draw the figure list-shifter flowing from cur_y. Returns updated cur_y."""
        if not self.eligible_figures:
            return cur_y

        pad = settings.SMALL_SPACER_Y
        cx = self.rect.centerx

        # Divider
        pygame.draw.line(self.window, settings.COLOR_DIALOGUE_BOX_BORDER,
                         (self.rect.left + pad, cur_y), (self.rect.right - pad, cur_y), 1)
        cur_y += pad

        # Label
        label = self.small_font.render("Select figure:", True, (180, 170, 150))
        self.window.blit(label, label.get_rect(centerx=cx, top=cur_y))
        cur_y += label.get_height() + pad

        # Current figure
        fig = self.eligible_figures[self.fig_selector_index]
        content_cy = cur_y + self.fig_icon_size // 2
        icon_cx = cx - int(self.width * 0.12)

        # Icon + frame
        icon_img = self.fig_icons.get(fig.id)
        frame_img = self.fig_frames.get(fig.id)
        if icon_img:
            ir = icon_img.get_rect(center=(icon_cx, content_cy))
            self.window.blit(icon_img, ir.topleft)
        if frame_img:
            fr = frame_img.get_rect(center=(icon_cx, content_cy))
            self.window.blit(frame_img, fr.topleft)

        # Name
        text_x = cx - int(self.width * 0.02)
        name_surf = self.font.render(fig.name, True, settings.TITLE_TEXT_COLOR)
        self.window.blit(name_surf, (text_x, content_cy - name_surf.get_height() - 2))

        # Suit icon + base power
        suit_icon = self.fig_suit_icons.get(fig.suit.lower())
        info_y = content_cy + 2
        base, _bonus = self._get_call_power_parts(fig)
        val_surf = self.font.render(str(base), True, (220, 180, 100))
        if suit_icon:
            self.window.blit(suit_icon, (text_x, info_y))
            self.window.blit(val_surf, (text_x + suit_icon.get_width() + 4,
                                        info_y + (suit_icon.get_height() - val_surf.get_height()) // 2))
        else:
            self.window.blit(val_surf, (text_x, info_y))

        cur_y += self.fig_icon_size + pad // 2

        # Counter
        counter = self.small_font.render(
            f"{self.fig_selector_index + 1} / {len(self.eligible_figures)}",
            True, (140, 130, 120),
        )
        self.window.blit(counter, counter.get_rect(centerx=cx, top=cur_y))
        cur_y += counter.get_height() + pad

        # Arrows (at pre-computed positions)
        if self.fig_arrow_left:
            self.fig_arrow_left.draw()
        if self.fig_arrow_right:
            self.fig_arrow_right.draw()

        return cur_y

    # ────────────────── dagger combine selector ────────────────

    def _draw_dagger_selector(self, cur_y):
        """Draw the dagger list-shifter for the combine option. Returns updated cur_y."""
        if not self.combinable_daggers:
            return cur_y

        pad = settings.SMALL_SPACER_Y
        cx = self.rect.centerx

        # Divider
        pygame.draw.line(self.window, settings.COLOR_DIALOGUE_BOX_BORDER,
                         (self.rect.left + pad, cur_y), (self.rect.right - pad, cur_y), 1)
        cur_y += pad

        # Label
        label = self.small_font.render("Combine with:", True, (180, 170, 150))
        self.window.blit(label, label.get_rect(centerx=cx, top=cur_y))
        cur_y += label.get_height() + pad

        # Current dagger
        d = self.combinable_daggers[self.dagger_selector_index]
        icon_size = self.fig_icon_size
        content_cy = cur_y + icon_size // 2
        icon_cx = cx - int(self.width * 0.12)

        # Icon + frame
        d_id = d['id']
        icon_img = self.dagger_icons.get(d_id)
        frame_img = self.dagger_frames.get(d_id)
        if icon_img:
            ir = icon_img.get_rect(center=(icon_cx, content_cy))
            self.window.blit(icon_img, ir.topleft)
        if frame_img:
            fr = frame_img.get_rect(center=(icon_cx, content_cy))
            self.window.blit(frame_img, fr.topleft)

        # Name + value
        text_x = cx - int(self.width * 0.02)
        name_surf = self.font.render("Dagger", True, settings.TITLE_TEXT_COLOR)
        self.window.blit(name_surf, (text_x, content_cy - name_surf.get_height() - 2))

        # Suit icon + power value
        suit_lower = d.get('suit', '').lower()
        suit_icon = self.dagger_suit_icons.get(suit_lower)
        info_y = content_cy + 2
        val_surf = self.font.render(str(d.get('value', 0)), True, (220, 180, 100))
        if suit_icon:
            self.window.blit(suit_icon, (text_x, info_y))
            self.window.blit(val_surf, (text_x + suit_icon.get_width() + 4,
                                        info_y + (suit_icon.get_height() - val_surf.get_height()) // 2))
        else:
            self.window.blit(val_surf, (text_x, info_y))

        cur_y += icon_size + pad // 2

        # Counter
        counter = self.small_font.render(
            f"{self.dagger_selector_index + 1} / {len(self.combinable_daggers)}",
            True, (140, 130, 120),
        )
        self.window.blit(counter, counter.get_rect(centerx=cx, top=cur_y))
        cur_y += counter.get_height() + pad

        # Arrows
        if self.dagger_arrow_left:
            self.dagger_arrow_left.draw()
        if self.dagger_arrow_right:
            self.dagger_arrow_right.draw()

        return cur_y

    def _draw_wrapped_text(self, text, center_x, y, max_width):
        """Render text wrapped to max_width, centred horizontally."""
        for line in self._wrap_text(text, max_width):
            surf = self.small_font.render(line, True, settings.TITLE_TEXT_COLOR)
            self.window.blit(surf, surf.get_rect(centerx=center_x, top=y))
            y += surf.get_height() + 2

    def _draw_close_button(self):
        if self.close_button_clicked:
            bg = (150, 150, 150)
            xc = (255, 100, 100)
        elif self.close_button_hovered:
            bg = (200, 200, 200)
            xc = (255, 50, 50)
        else:
            bg = settings.COLOR_DIALOGUE_BOX_BORDER
            xc = settings.TITLE_TEXT_COLOR

        # Hover glow
        if self.close_button_hovered or self.close_button_clicked:
            r = 20
            glow = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            alpha = 180 if self.close_button_clicked else 120
            pygame.draw.circle(glow, (255, 100, 100, alpha), (r, r), r)
            self.window.blit(glow, (self.close_button_rect.centerx - r, self.close_button_rect.centery - r))

        pygame.draw.rect(self.window, bg, self.close_button_rect, border_radius=3)
        m = 8
        lw = 4 if self.close_button_hovered else 3
        pygame.draw.line(self.window, xc,
                         (self.close_button_rect.left + m, self.close_button_rect.top + m),
                         (self.close_button_rect.right - m, self.close_button_rect.bottom - m), lw)
        pygame.draw.line(self.window, xc,
                         (self.close_button_rect.right - m, self.close_button_rect.top + m),
                         (self.close_button_rect.left + m, self.close_button_rect.bottom - m), lw)

    # --------------------------------------------------------------- events
    def update(self, events):
        """Process events. Returns action dict, action string, or None.

        Battle context returns:
            {'action': 'use'|'gamble'|'combine', 'move_index': int,
             'selected_figure': Figure | None}
        Shop context returns:
            'return' | 'close'
        """
        # Update button hover states
        if self.is_battle_context:
            for _aid, btn in self.action_buttons:
                btn.update()
        else:
            if self.return_button:
                self.return_button.update()

        # Always update figure selector arrows (both contexts)
        if self.fig_arrow_left:
            self.fig_arrow_left.update()
        if self.fig_arrow_right:
            self.fig_arrow_right.update()

        # Update dagger selector arrows
        if self.dagger_arrow_left:
            self.dagger_arrow_left.update()
        if self.dagger_arrow_right:
            self.dagger_arrow_right.update()

        mouse_pos = pygame.mouse.get_pos()
        self.close_button_hovered = self.close_button_rect.collidepoint(mouse_pos)
        self.close_button_clicked = self.close_button_hovered and pygame.mouse.get_pressed()[0]

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.close_button_rect.collidepoint(mouse_pos):
                    return 'close'
                if not self.border_rect.collidepoint(mouse_pos):
                    return 'close'

                if self.is_battle_context:
                    # Check action buttons
                    for action_id, btn in self.action_buttons:
                        if btn.collide() and not btn.disabled:
                            selected = self.get_selected_figure() if self.is_call_move else None
                            selected_dagger = self.get_selected_dagger() if action_id == 'combine' else None
                            return {
                                'action': action_id,
                                'move_index': self.move_index,
                                'selected_figure': selected,
                                'selected_dagger': selected_dagger,
                            }
                else:
                    if self.return_button and self.return_button.collide():
                        return 'return'
        return None

    def handle_events(self, events):
        """Wrapper for update."""
        return self.update(events)
