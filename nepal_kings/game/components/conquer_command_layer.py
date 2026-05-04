# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Conquer-only unified top panel.

The conquer top panel acts as the entire HUD for a conquer battle: a single
panel divided into five compartments — own spells, own battle figure, info /
action, opponent battle figure, opponent spells — populated progressively as
the battle phase advances.  There is no separate bottom log; the info /
action column is the single source of truth for what the player must do
next, and the spell / figure compartments visualise everything that has
happened so far.
"""

import pygame

from config import settings
from game.screens.conquer_flow import (
    CONQUER_PHASES,
    derive_conquer_objective,
    event_spells_by_side,
)


# ----------------------------------------------------------------- constants

# Compartment widths as fractions of SCREEN_WIDTH.
_PAD_X = 0.020
_GAP_X = 0.010
_OWN_SPELLS_W = 0.130
_OWN_BF_W = 0.180
_INFO_W = 0.300
_OPP_BF_W = 0.180
_OPP_SPELLS_W = 0.130

# Top strip (title bar) height as fraction of SCREEN_HEIGHT.
_TITLE_BAR_H = 0.040
# Bottom border padding.
_BOTTOM_PAD = 0.006

# Inner compartment padding.
_COMP_PAD_X = 10
_COMP_PAD_Y = 8


_TONE_COLORS = {
    'action': (255, 211, 116),
    'waiting': (176, 209, 255),
    'result': (165, 235, 168),
    'good': (165, 235, 168),
    'warning': (255, 196, 124),
    'bad': (245, 154, 142),
    'neutral': (229, 213, 177),
    'info': (229, 213, 177),
}


def _phase_label(phase: str) -> str:
    for key, label in CONQUER_PHASES:
        if key == phase:
            return label.upper()
    return (phase or '').upper()


class ConquerCommandLayer:
    """Draw the unified conquer top panel and its five compartments."""

    def __init__(self, window):
        self.window = window
        self.title_font = settings.get_font(settings.FS_HEADING, bold=True)
        self.section_font = settings.get_font(max(11, int(settings.FS_TINY * 0.78)), bold=True)
        self.headline_font = settings.get_font(settings.FS_HEADING, bold=True)
        self.body_font = settings.get_font(max(13, int(settings.FS_SMALL * 0.95)))
        self.note_font = settings.get_font(max(11, int(settings.FS_TINY * 0.85)))
        self.button_font = settings.get_font(max(13, int(settings.FS_TINY)), bold=True)
        self.role_font = settings.get_font(max(10, int(settings.FS_TINY * 0.72)), bold=True)
        self.figure_name_font = settings.get_font(max(13, int(settings.FS_SMALL * 0.95)), bold=True)
        self.phase_pill_font = settings.get_font(max(10, int(settings.FS_TINY * 0.78)), bold=True)
        # Each hover stores (label_or_object, anchor_rect [, extra])
        self._spell_hover = None   # (name_str, rect)
        self._figure_hover = None  # (figure_obj, rect, side_str)

    # -------------------------------------------------------------- entry

    def draw(self, screen):
        game = screen.state.game
        field = screen.subscreens.get('field') if hasattr(screen, 'subscreens') else None
        shop = screen.subscreens.get('battle_shop') if hasattr(screen, 'subscreens') else None
        if hasattr(screen, 'get_conquer_objective'):
            objective = screen.get_conquer_objective()
        else:
            objective = derive_conquer_objective(game, screen.state, field, shop)

        screen._conquer_objective_action_rects = {}
        self._spell_hover = None   # (name_str, rect)
        self._figure_hover = None  # (figure_obj, rect, side_str)

        header_h = int(settings.SCREEN_HEIGHT * screen.HEADER_H_FACTOR)
        self._draw_panel_background(header_h)
        self._draw_title_bar(screen, header_h, objective)
        self._draw_compartments(screen, header_h, objective)

        if self._spell_hover:
            self._draw_spell_tooltip(self._spell_hover[0], self._spell_hover[1])
        if self._figure_hover:
            self._draw_figure_tooltip(*self._figure_hover)

    # --------------------------------------------------------- backgrounds

    def _draw_panel_background(self, header_h):
        rect = pygame.Rect(0, 0, settings.SCREEN_WIDTH, header_h)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((19, 18, 16, 240))
        self.window.blit(panel, rect.topleft)
        pygame.draw.line(
            self.window, (189, 149, 75),
            (0, header_h - 1), (settings.SCREEN_WIDTH, header_h - 1), 2)

    def _draw_title_bar(self, screen, header_h, objective):
        title_h = int(settings.SCREEN_HEIGHT * _TITLE_BAR_H)
        game = screen.state.game

        tier = getattr(game, 'land_tier', None) if game else None
        opponent = (getattr(game, 'opponent_name', None) or 'Defender') if game else 'Defender'
        land = f'Tier {tier} Land' if tier else 'Conquer Battle'
        title = f'{land} vs {opponent}'

        title_x = int(settings.SCREEN_WIDTH * _PAD_X)
        title_y = max(6, (title_h - self.title_font.get_height()) // 2)
        title_surf = self.title_font.render(title, True, (246, 222, 170))
        self.window.blit(title_surf, (title_x, title_y))

        # Phase pill (right of title) — replaces the separate timeline strip.
        phase_label = _phase_label(objective.phase or 'start')
        pill_text = self.phase_pill_font.render(phase_label, True, (250, 230, 180))
        pill_pad_x = 12
        pill_pad_y = 4
        pill_w = pill_text.get_width() + pill_pad_x * 2
        pill_h = pill_text.get_height() + pill_pad_y * 2
        pill_x = title_x + title_surf.get_width() + 14
        pill_y = (title_h - pill_h) // 2
        pill_rect = pygame.Rect(pill_x, pill_y, pill_w, pill_h)
        pygame.draw.rect(self.window, (60, 50, 36), pill_rect, border_radius=10)
        pygame.draw.rect(self.window, (200, 158, 86), pill_rect, 1, border_radius=10)
        self.window.blit(pill_text, (pill_x + pill_pad_x, pill_y + pill_pad_y))

        # Withdraw button at right edge.
        if self._withdraw_available(screen):
            wd_w = int(settings.SCREEN_WIDTH * 0.072)
            wd_h = max(26, int(settings.SCREEN_HEIGHT * 0.030))
            wd_x = settings.SCREEN_WIDTH - int(settings.SCREEN_WIDTH * _PAD_X) - wd_w
            wd_y = (title_h - wd_h) // 2
            rect = pygame.Rect(wd_x, wd_y, wd_w, wd_h)
            screen._conquer_objective_action_rects['withdraw'] = rect
            self._draw_rect_button(rect, 'Withdraw', (93, 52, 48))

    # ------------------------------------------------------ compartments

    def _draw_compartments(self, screen, header_h, objective):
        title_h = int(settings.SCREEN_HEIGHT * _TITLE_BAR_H)
        bottom_pad = int(settings.SCREEN_HEIGHT * _BOTTOM_PAD)
        comp_y = title_h + 4
        comp_h = header_h - comp_y - bottom_pad

        x = int(settings.SCREEN_WIDTH * _PAD_X)
        gap = int(settings.SCREEN_WIDTH * _GAP_X)

        widths = [
            int(settings.SCREEN_WIDTH * _OWN_SPELLS_W),
            int(settings.SCREEN_WIDTH * _OWN_BF_W),
            int(settings.SCREEN_WIDTH * _INFO_W),
            int(settings.SCREEN_WIDTH * _OPP_BF_W),
            int(settings.SCREEN_WIDTH * _OPP_SPELLS_W),
        ]

        spells = event_spells_by_side(getattr(screen, '_conquer_events', []) or [])

        # 1) Own spells
        rect = pygame.Rect(x, comp_y, widths[0], comp_h)
        self._draw_compartment_frame(rect)
        self._draw_spell_compartment(
            screen, rect, 'OWN SPELLS',
            spells['own'], spells['own_roles'])
        x += widths[0] + gap

        # 2) Own battle figure
        rect = pygame.Rect(x, comp_y, widths[1], comp_h)
        self._draw_compartment_frame(rect)
        self._draw_battle_figure_compartment(
            screen, rect, side='own', title='YOUR BATTLE FIGURE')
        x += widths[1] + gap

        # 3) Info / action panel
        rect = pygame.Rect(x, comp_y, widths[2], comp_h)
        self._draw_compartment_frame(rect)
        self._draw_info_compartment(screen, rect, objective)
        x += widths[2] + gap

        # 4) Opponent battle figure
        rect = pygame.Rect(x, comp_y, widths[3], comp_h)
        self._draw_compartment_frame(rect)
        self._draw_battle_figure_compartment(
            screen, rect, side='opponent', title='OPPONENT BATTLE FIGURE')
        x += widths[3] + gap

        # 5) Opponent spells
        rect = pygame.Rect(x, comp_y, widths[4], comp_h)
        self._draw_compartment_frame(rect)
        self._draw_spell_compartment(
            screen, rect, 'OPPONENT SPELLS',
            spells['opponent'], spells['opponent_roles'])

    def _draw_compartment_frame(self, rect):
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        surf.fill((28, 26, 22, 220))
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, (122, 99, 61), rect, 1, border_radius=4)

    def _draw_section_title(self, rect, title):
        text = self.section_font.render(title, True, (205, 181, 122))
        self.window.blit(
            text, (rect.left + _COMP_PAD_X, rect.top + _COMP_PAD_Y - 2))
        return rect.top + _COMP_PAD_Y + text.get_height() + 4

    # ------------------------------------------ spell compartment helpers

    def _draw_spell_compartment(self, screen, rect, title, names, roles):
        content_top = self._draw_section_title(rect, title)

        if not names:
            # Empty state — silhouette badge + hint
            placeholder = self.note_font.render(
                'No spells yet', True, (140, 130, 110))
            self.window.blit(
                placeholder,
                (rect.left + _COMP_PAD_X,
                 content_top + 6))
            return

        max_icons = 2
        # Spell icon size: large per spec.
        size = max(48, min(rect.width // 2 - 16,
                           rect.height - (content_top - rect.top) - 28))
        size = min(size, 96)
        spacing = 12
        total_w = size * min(len(names), max_icons) + spacing * (min(len(names), max_icons) - 1)
        start_x = rect.left + (rect.width - total_w) // 2
        y = content_top + 2
        mouse = pygame.mouse.get_pos()

        for idx, name in enumerate(names[:max_icons]):
            icon_rect = pygame.Rect(start_x + idx * (size + spacing), y, size, size)
            self._draw_spell_icon(screen, icon_rect, name)
            if icon_rect.collidepoint(mouse):
                self._spell_hover = (name, icon_rect)

            role = (roles.get(name) or '').upper()
            if role:
                role_color = (250, 220, 150) if role == 'PRELUDE' else (180, 220, 250)
                role_text = self.role_font.render(role, True, role_color)
                self.window.blit(
                    role_text,
                    (icon_rect.centerx - role_text.get_width() // 2,
                     icon_rect.bottom + 3))

    def _draw_spell_icon(self, screen, rect, name):
        images = (screen._get_spell_icon_image(name)
                  if hasattr(screen, '_get_spell_icon_image') else [])
        if images:
            img = pygame.transform.smoothscale(images[0], (rect.w, rect.h))
            self.window.blit(img, rect)
        else:
            pygame.draw.rect(self.window, (64, 57, 47), rect, border_radius=6)
            letter = self.section_font.render(
                (name or '?')[:1], True, (230, 210, 160))
            self.window.blit(letter, letter.get_rect(center=rect.center))
        pygame.draw.rect(self.window, (184, 142, 71), rect, 1, border_radius=6)

    # -------------------------------------- battle figure compartment

    def _draw_battle_figure_compartment(self, screen, rect, side, title):
        content_top = self._draw_section_title(rect, title)
        figure, ownership_note, is_pending = self._battle_figure_for_side(
            screen, side)

        if not figure:
            placeholder = self.note_font.render(
                'No figure selected', True, (140, 130, 110))
            self.window.blit(
                placeholder,
                (rect.left + _COMP_PAD_X, content_top + 6))
            return

        # Icon: prefer the family small icon (already prepared by FigureManager)
        icon = getattr(figure.family, 'icon_img_small', None)
        if icon is None:
            icon = getattr(figure.family, 'icon_img', None)

        # Available area for the icon below the section title; reserve ~40 px
        # under the icon for the name + ownership note.
        avail_h = rect.bottom - content_top - 38
        icon_size = max(56, min(rect.width - 24, avail_h))
        icon_size = min(icon_size, 132)

        if icon is not None:
            scaled = pygame.transform.smoothscale(icon, (icon_size, icon_size))
            icon_rect = pygame.Rect(0, 0, icon_size, icon_size)
            icon_rect.centerx = rect.centerx
            icon_rect.top = content_top + 2
            # Pending pulse glow if not yet confirmed.
            if is_pending:
                self._draw_pulse_ring(icon_rect)
            self.window.blit(scaled, icon_rect)
            # Detect hover for rich figure tooltip.
            if icon_rect.collidepoint(pygame.mouse.get_pos()):
                self._figure_hover = (figure, icon_rect, side)
        else:
            icon_rect = pygame.Rect(0, 0, icon_size, icon_size)
            icon_rect.centerx = rect.centerx
            icon_rect.top = content_top + 2

        # Name beneath the icon
        name_text = self.figure_name_font.render(figure.name, True, (245, 222, 170))
        name_rect = name_text.get_rect(centerx=rect.centerx,
                                       top=icon_rect.bottom + 4)
        if name_rect.right > rect.right - 4:
            name_rect.right = rect.right - 4
        if name_rect.left < rect.left + 4:
            name_rect.left = rect.left + 4
        self.window.blit(name_text, name_rect)

        # Ownership / context note (e.g., "selected by opponent")
        if ownership_note:
            note = self.note_font.render(ownership_note, True, (210, 196, 156))
            note_rect = note.get_rect(centerx=rect.centerx,
                                      top=name_rect.bottom + 1)
            if note_rect.bottom > rect.bottom - 4:
                note_rect.bottom = rect.bottom - 4
            self.window.blit(note, note_rect)

    def _draw_pulse_ring(self, rect):
        import math
        t = pygame.time.get_ticks() / 1000.0
        pulse = 0.5 + 0.5 * math.sin(t * 3.0)
        alpha = int(80 + 100 * pulse)
        ring = pygame.Surface((rect.w + 12, rect.h + 12), pygame.SRCALPHA)
        pygame.draw.rect(
            ring, (245, 205, 95, alpha),
            ring.get_rect(), 4, border_radius=8)
        self.window.blit(ring, (rect.left - 6, rect.top - 6))

    def _battle_figure_for_side(self, screen, side):
        """Return ``(figure, ownership_note, is_pending)`` for the side.

        Reads from the live game state and the field-screen pending advance /
        defender selection so the panel mirrors the field highlight without
        waiting for a confirm.
        """
        game = screen.state.game
        if not game:
            return None, '', False

        field = screen.subscreens.get('field') if hasattr(screen, 'subscreens') else None
        player_id = getattr(game, 'player_id', None)
        adv_id = getattr(game, 'advancing_figure_id', None)
        def_id = getattr(game, 'defending_figure_id', None)
        adv_player = getattr(game, 'advancing_player_id', None)

        # Pending (not yet confirmed) icons take priority — shows the player
        # exactly which figure they are about to confirm.
        if side == 'own' and field is not None:
            pending = (getattr(field, '_pending_advance_figure', None)
                       or getattr(field, 'figure_pending_own_defender_selection', None))
            if pending:
                role = ('Pending — your advance'
                        if pending is getattr(field, '_pending_advance_figure', None)
                        else 'Pending — your defender (Invader Swap)')
                return pending, role, True
        if side == 'opponent' and field is not None:
            pending = getattr(field, 'figure_pending_defender_selection', None)
            if pending:
                return pending, "Pending — you picked their defender", True

        # Confirmed figures
        own_fig_id = adv_id if adv_player == player_id else def_id
        opp_fig_id = def_id if adv_player == player_id else adv_id
        target_id = own_fig_id if side == 'own' else opp_fig_id
        if not target_id:
            return None, '', False

        figure = self._lookup_figure(field, screen, target_id, side)
        if not figure:
            return None, '', False

        # Selection ownership note
        note = ''
        if side == 'own':
            # Opponent picked your figure when you are defender of an Invader
            # Swap-aborted attack (rare) — note left blank in normal flow.
            if adv_player != player_id and target_id == def_id:
                # You are defender; the attacker did NOT pick your figure.
                # Whether you picked it (own choice) or it was forced (e.g.,
                # must_be_attacked) is recorded by the server; default text
                # is silent for the common case to keep the panel calm.
                note = ''
            elif adv_player == player_id and target_id == adv_id:
                # You picked your own attacker — silent in the common case.
                note = ''
        else:
            if adv_player == player_id and target_id == def_id:
                # You picked the opponent's defender.
                note = "You picked their defender"
            elif adv_player != player_id and target_id == adv_id:
                # The opponent picked their own attacker.
                note = ''
        return figure, note, False

    def _lookup_figure(self, field, screen, fig_id, side):
        """Try several sources for the figure object identified by ``fig_id``."""
        # 1. From battle screen if it has loaded battle figures.
        battle = screen.subscreens.get('battle') if hasattr(screen, 'subscreens') else None
        if battle is not None:
            for attr in ('player_figure', 'opponent_figure',
                         'player_figure_2', 'opponent_figure_2'):
                fig = getattr(battle, attr, None)
                if fig is not None and getattr(fig, 'id', None) == fig_id:
                    return fig
        # 2. From the field screen's loaded figures.
        if field is not None:
            for fig in getattr(field, 'figures', []) or []:
                if getattr(fig, 'id', None) == fig_id:
                    return fig
        return None

    # ----------------------------------------- info / action compartment

    def _draw_info_compartment(self, screen, rect, objective):
        # Section title line: "STEP" + tone-coloured phase label.
        section = 'STEP'
        text = self.section_font.render(section, True, (205, 181, 122))
        self.window.blit(text, (rect.left + _COMP_PAD_X, rect.top + _COMP_PAD_Y - 2))

        # Headline (large, tone-coloured).
        tone = objective.tone or 'neutral'
        headline_color = _TONE_COLORS.get(tone, _TONE_COLORS['neutral'])
        max_w = rect.width - 2 * _COMP_PAD_X
        head_y = rect.top + _COMP_PAD_Y + 14
        for line in self._wrap(objective.headline, self.headline_font, max_w, max_lines=2):
            surf = self.headline_font.render(line, True, headline_color)
            self.window.blit(surf, (rect.left + _COMP_PAD_X, head_y))
            head_y += surf.get_height() + 1

        # Body text (wrap).
        body_y = head_y + 4
        bottom_action_h = 36
        body_bottom_limit = rect.bottom - bottom_action_h - 10
        body_lines = self._wrap(
            objective.instruction, self.body_font, max_w,
            max_lines=max(1, (body_bottom_limit - body_y) // (self.body_font.get_height() + 2)))
        for line in body_lines:
            if body_y + self.body_font.get_height() > body_bottom_limit:
                break
            surf = self.body_font.render(line, True, (221, 214, 195))
            self.window.blit(surf, (rect.left + _COMP_PAD_X, body_y))
            body_y += surf.get_height() + 2

        # Action buttons aligned to the bottom of the compartment.
        btn_y = rect.bottom - bottom_action_h + 4
        self._draw_objective_actions(screen, objective, rect, btn_y)

    def _draw_objective_actions(self, screen, objective, rect, btn_y):
        pending = getattr(screen, '_conquer_pending_confirmation', None)
        btn_h = max(28, int(settings.SCREEN_HEIGHT * 0.030))
        btn_w = max(96, int(rect.width * 0.30))

        if pending:
            # Confirm + Cancel side by side.
            x_left = rect.left + _COMP_PAD_X
            confirm_rect = pygame.Rect(x_left, btn_y, btn_w, btn_h)
            cancel_rect = pygame.Rect(x_left + btn_w + 10, btn_y, btn_w, btn_h)
            self._draw_rect_button(confirm_rect, 'Confirm', (77, 119, 71))
            self._draw_rect_button(cancel_rect, 'Cancel', (92, 75, 63))
            screen._conquer_objective_action_rects['confirm'] = confirm_rect
            screen._conquer_objective_action_rects['cancel'] = cancel_rect
            return

        if objective.primary_action == 'next_gate':
            x_left = rect.left + _COMP_PAD_X
            next_rect = pygame.Rect(x_left, btn_y, btn_w, btn_h)
            self._draw_rect_button(next_rect, 'Next', (86, 106, 134))
            screen._conquer_objective_action_rects['next_gate'] = next_rect
            return

        # No buttons: optionally show a hint about what's next.
        if objective.waiting:
            hint = self.note_font.render(
                'Waiting...', True, (170, 158, 130))
            self.window.blit(hint, (rect.left + _COMP_PAD_X, btn_y + 8))

    # ------------------------------------------------------ button draw

    def _draw_rect_button(self, rect, label, color):
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse)
        bg = tuple(min(255, c + 24) for c in color) if hovered else color
        pygame.draw.rect(self.window, bg, rect, border_radius=6)
        pygame.draw.rect(self.window, (238, 219, 172), rect, 1, border_radius=6)
        text = self.button_font.render(label, True, (255, 244, 216))
        self.window.blit(text, text.get_rect(center=rect.center))

    def _withdraw_available(self, screen):
        game = screen.state.game
        if not game or getattr(game, 'game_over', False) or getattr(game, 'state', None) == 'finished':
            return False
        if getattr(screen, '_withdraw_dialogue_open', False):
            return False
        return bool(screen._is_current_player_conquer_attacker())

    # -------------------------------------------------------- tooltips

    def _draw_spell_tooltip(self, name, anchor):
        """Tooltip for a spell icon: just the spell name, styled."""
        self._render_tooltip_lines(
            [(name, (255, 240, 190))],
            anchor)

    def _draw_figure_tooltip(self, figure, anchor, side):
        """Rich tooltip for a battle figure: name, suit, power, active skills."""
        lines = []
        name = getattr(figure, 'name', '?')
        suit = (getattr(figure, 'suit', '') or '').capitalize()
        base_power = getattr(figure, 'get_value', lambda: 0)()
        enchantments = getattr(figure, 'active_enchantments', []) or []
        enchant_mod = sum(e.get('power_modifier', 0) for e in enchantments)
        total_power = base_power + enchant_mod

        power_str = f'Power: {total_power}'
        if enchant_mod:
            sign = '+' if enchant_mod > 0 else ''
            power_str += f'  ({base_power} {sign}{enchant_mod} enchant)'

        lines.append((name, (255, 235, 170)))
        lines.append((f'{suit}  •  {power_str}', (210, 210, 190)))

        skills = []
        if hasattr(figure, 'get_active_skills'):
            try:
                skills = [label for _key, label in figure.get_active_skills()]
            except Exception:
                pass
        if skills:
            lines.append(('Skills: ' + ', '.join(skills), (190, 220, 240)))

        self._render_tooltip_lines(lines, anchor)

    def _render_tooltip_lines(self, lines, anchor):
        """Draw a multi-line tooltip box anchored below ``anchor``."""
        pad_x = settings.TOOLTIP_PAD_X
        pad_y = settings.TOOLTIP_PAD_Y
        line_gap = 3
        rendered = []
        for text, color in lines:
            surf = self.body_font.render(text, True, color)
            rendered.append(surf)

        max_w = max(s.get_width() for s in rendered)
        total_h = sum(s.get_height() for s in rendered) + line_gap * (len(rendered) - 1)
        box_w = max_w + pad_x * 2
        box_h = total_h + pad_y * 2

        box_x = anchor.centerx - box_w // 2
        box_y = anchor.bottom + 6
        box_x = max(4, min(box_x, settings.SCREEN_WIDTH - box_w - 4))
        box_y = min(box_y, settings.SCREEN_HEIGHT - box_h - 4)

        rect = pygame.Rect(box_x, box_y, box_w, box_h)
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.TOOLTIP_BG_COLOR, surf.get_rect(),
                         border_radius=settings.TOOLTIP_CORNER_R)
        pygame.draw.rect(surf, settings.TOOLTIP_BORDER_COLOR, surf.get_rect(),
                         settings.TOOLTIP_BORDER_WIDTH,
                         border_radius=settings.TOOLTIP_CORNER_R)
        self.window.blit(surf, rect.topleft)

        y = rect.top + pad_y
        for s in rendered:
            self.window.blit(s, (rect.left + pad_x, y))
            y += s.get_height() + line_gap

    # ------------------------------------------------------- text helpers

    def _wrap(self, text, font, max_width, max_lines=2):
        words = (text or '').split()
        if not words:
            return []
        lines = []
        current = ''
        for word in words:
            trial = word if not current else current + ' ' + word
            if font.size(trial)[0] <= max_width:
                current = trial
                continue
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        if current and len(lines) < max_lines:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        if len(lines) == max_lines and words:
            lines[-1] = self._fit(lines[-1], font, max_width)
        return lines

    def _fit(self, text, font, max_width):
        text = text or ''
        if font.size(text)[0] <= max_width:
            return text
        clipped = text
        ellipsis = '...'
        while clipped and font.size(clipped + ellipsis)[0] > max_width:
            clipped = clipped[:-1]
        return clipped + ellipsis if clipped else ellipsis
