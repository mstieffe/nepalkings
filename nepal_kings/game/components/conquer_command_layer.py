# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Conquer-only command layer and bottom battle log."""

import pygame

from config import settings
from game.screens.conquer_flow import CONQUER_PHASES, derive_conquer_objective, spell_names_from_events


class ConquerCommandLayer:
    """Draw the conquer objective panel, persistent spell icons, and log strip."""

    def __init__(self, window):
        self.window = window
        self.title_font = settings.get_font(settings.FS_HEADING, bold=True)
        self.phase_font = settings.get_font(settings.FS_TINY, bold=True)
        self.headline_font = settings.get_font(settings.FS_SMALL, bold=True)
        self.body_font = settings.get_font(max(12, int(settings.FS_TINY * 0.95)))
        self.log_title_font = settings.get_font(settings.FS_TINY, bold=True)
        self.log_font = settings.get_font(max(10, int(settings.FS_TINY * 0.82)))
        self.button_font = settings.get_font(max(12, int(settings.FS_TINY * 0.95)), bold=True)
        self._spell_hover = None

    def draw(self, screen):
        game = screen.state.game
        field = screen.subscreens.get('field') if hasattr(screen, 'subscreens') else None
        shop = screen.subscreens.get('battle_shop') if hasattr(screen, 'subscreens') else None
        if hasattr(screen, 'get_conquer_objective'):
            objective = screen.get_conquer_objective()
        else:
            objective = derive_conquer_objective(game, screen.state, field, shop)

        screen._conquer_objective_action_rects = {}
        self._spell_hover = None
        self._draw_top_command(screen, objective)
        self._draw_bottom_log(screen)
        if self._spell_hover:
            self._draw_tooltip(self._spell_hover)

    def _draw_top_command(self, screen, objective):
        header_h = int(settings.SCREEN_HEIGHT * screen.HEADER_H_FACTOR)
        rect = pygame.Rect(0, 0, settings.SCREEN_WIDTH, header_h)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((21, 20, 18, 238))
        self.window.blit(panel, rect.topleft)
        pygame.draw.line(
            self.window, (189, 149, 75),
            (0, header_h - 1), (settings.SCREEN_WIDTH, header_h - 1), 2)

        tier = getattr(screen.state.game, 'land_tier', None)
        land = f'Tier {tier} Land' if tier else 'Conquer Battle'
        opponent = getattr(screen.state.game, 'opponent_name', None) or 'Defender'
        title = f'{land} vs {opponent}'
        title_surf = self.title_font.render(title, True, (246, 222, 170))
        self.window.blit(title_surf, (settings.get_x(0.026), settings.get_y(0.014)))

        timeline_rect = pygame.Rect(
            int(settings.get_x(0.026)),
            int(settings.get_y(0.058)),
            int(settings.get_x(0.36)),
            max(20, int(header_h * 0.32)),
        )
        self._draw_timeline(timeline_rect, objective.phase)

        obj_x = settings.get_x(0.42)
        obj_y = settings.get_y(0.018)
        obj_w = settings.get_x(0.34)
        tone_color = {
            'action': (255, 211, 116),
            'waiting': (176, 209, 255),
            'result': (165, 235, 168),
        }.get(objective.tone, (229, 213, 177))
        headline = self._fit(objective.headline, self.headline_font, obj_w)
        headline_surf = self.headline_font.render(headline, True, tone_color)
        self.window.blit(headline_surf, (obj_x, obj_y))

        lines = self._wrap(objective.instruction, self.body_font, obj_w, max_lines=2)
        y = obj_y + headline_surf.get_height() + int(settings.SCREEN_HEIGHT * 0.006)
        for line in lines:
            surf = self.body_font.render(line, True, (221, 214, 195))
            self.window.blit(surf, (obj_x, y))
            y += surf.get_height() + 2

        self._draw_objective_actions(screen, objective, obj_x, y + 2)
        self._draw_spell_strip(screen, pygame.Rect(
            settings.get_x(0.78),
            settings.get_y(0.014),
            settings.get_x(0.20),
            header_h - settings.get_y(0.024),
        ))

    def _draw_timeline(self, rect, active_phase):
        phases = list(CONQUER_PHASES)
        if not phases:
            return
        dot_r = max(4, int(settings.SCREEN_HEIGHT * 0.006))
        gap = rect.width / max(1, len(phases) - 1)
        y = rect.top + int(rect.height * 0.36)
        active_idx = next((i for i, (key, _label) in enumerate(phases)
                           if key == active_phase), 0)
        for idx, (key, label) in enumerate(phases):
            x = int(rect.left + idx * gap)
            if idx > 0:
                prev_x = int(rect.left + (idx - 1) * gap)
                color = (154, 121, 61) if idx <= active_idx else (74, 68, 58)
                pygame.draw.line(self.window, color, (prev_x + dot_r, y), (x - dot_r, y), 2)
            color = (247, 203, 91) if idx == active_idx else (
                (159, 126, 66) if idx < active_idx else (88, 80, 67))
            pygame.draw.circle(self.window, color, (x, y), dot_r)
            label_surf = self.phase_font.render(label, True, (211, 190, 145))
            self.window.blit(label_surf, (x - label_surf.get_width() // 2, y + dot_r + 3))

    def _draw_objective_actions(self, screen, objective, x, y):
        pending = getattr(screen, '_conquer_pending_confirmation', None)
        if pending:
            self._draw_button(screen, 'Confirm', 'confirm', x, y, (77, 119, 71))
            self._draw_button(screen, 'Cancel', 'cancel', x + settings.get_x(0.078), y, (92, 75, 63))
            return

        if objective.primary_action == 'next_gate':
            self._draw_button(screen, 'Next', 'next_gate', x, y, (86, 106, 134))
            if self._withdraw_available(screen):
                self._draw_withdraw_button(screen)
            return

        if self._withdraw_available(screen):
            self._draw_withdraw_button(screen)

    def _draw_withdraw_button(self, screen):
        width = settings.get_x(0.078)
        rect = pygame.Rect(int(settings.get_x(0.90)), int(settings.get_y(0.020)),
                           int(width), max(26, int(settings.SCREEN_HEIGHT * 0.034)))
        screen._conquer_objective_action_rects['withdraw'] = rect
        self._draw_rect_button(rect, 'Withdraw', (93, 52, 48))

    def _draw_button(self, screen, label, action, x, y, color):
        rect = pygame.Rect(int(x), int(y), int(settings.get_x(0.070)),
                           max(26, int(settings.SCREEN_HEIGHT * 0.034)))
        screen._conquer_objective_action_rects[action] = rect
        self._draw_rect_button(rect, label, color)

    def _draw_rect_button(self, rect, label, color):
        pygame.draw.rect(self.window, color, rect, border_radius=6)
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

    def _draw_spell_strip(self, screen, rect):
        names = spell_names_from_events(getattr(screen, '_conquer_events', []) or [])
        title = self.log_title_font.render('SPELLS', True, (205, 181, 122))
        self.window.blit(title, (rect.left, rect.top))
        x = rect.left
        y = rect.top + title.get_height() + int(settings.SCREEN_HEIGHT * 0.006)
        size = max(24, int(settings.SCREEN_HEIGHT * 0.042))
        mouse = pygame.mouse.get_pos()
        for name in names[:8]:
            images = screen._get_spell_icon_image(name) if hasattr(screen, '_get_spell_icon_image') else []
            icon_rect = pygame.Rect(x, y, size, size)
            if images:
                img = pygame.transform.smoothscale(images[0], (size, size))
                self.window.blit(img, icon_rect)
            else:
                pygame.draw.rect(self.window, (64, 57, 47), icon_rect, border_radius=5)
                letter = self.phase_font.render((name or '?')[:1], True, (230, 210, 160))
                self.window.blit(letter, letter.get_rect(center=icon_rect.center))
            pygame.draw.rect(self.window, (184, 142, 71), icon_rect, 1, border_radius=5)
            if icon_rect.collidepoint(mouse):
                self._spell_hover = (name, icon_rect)
            x += size + int(settings.SCREEN_WIDTH * 0.006)
            if x + size > rect.right:
                break

    def _draw_bottom_log(self, screen):
        log_h = int(settings.SCREEN_HEIGHT * screen.BOTTOM_LOG_H_FACTOR)
        rect = pygame.Rect(0, settings.SCREEN_HEIGHT - log_h, settings.SCREEN_WIDTH, log_h)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((18, 17, 15, 235))
        self.window.blit(panel, rect.topleft)
        pygame.draw.line(self.window, (171, 133, 70), rect.topleft, (rect.right, rect.top), 2)

        title = self.log_title_font.render('BATTLE LOG', True, (220, 192, 128))
        self.window.blit(title, (settings.get_x(0.018), rect.top + settings.get_y(0.012)))

        events = list(getattr(screen, '_conquer_events', []) or [])[-7:]
        if not events:
            empty = self.body_font.render('Conquer events will appear here from left to right.', True, (166, 155, 130))
            self.window.blit(empty, (settings.get_x(0.12), rect.top + settings.get_y(0.036)))
            return

        start_x = settings.get_x(0.115)
        gap = settings.get_x(0.010)
        card_w = int((settings.SCREEN_WIDTH - start_x - settings.get_x(0.025) - gap * 6) / 7)
        card_h = int(log_h - settings.get_y(0.028))
        y = int(rect.top + settings.get_y(0.014))
        for idx, event in enumerate(events):
            card = pygame.Rect(int(start_x + idx * (card_w + gap)), y, card_w, card_h)
            self._draw_event_card(screen, card, event)

    def _draw_event_card(self, screen, rect, event):
        tone_colors = {
            'good': (65, 102, 65),
            'bad': (105, 58, 55),
            'action': (119, 91, 45),
            'warning': (126, 104, 50),
            'waiting': (54, 72, 98),
        }
        bg = tone_colors.get(event.tone, (49, 46, 39))
        pygame.draw.rect(self.window, bg, rect, border_radius=6)
        pygame.draw.rect(self.window, (122, 99, 61), rect, 1, border_radius=6)

        phase = event.phase.upper()
        phase_surf = self.phase_font.render(phase, True, (229, 208, 159))
        self.window.blit(phase_surf, (rect.left + 8, rect.top + 6))

        icon_x = rect.right - 8
        for name in reversed(event.spell_names[:2]):
            images = screen._get_spell_icon_image(name) if hasattr(screen, '_get_spell_icon_image') else []
            if not images:
                continue
            size = max(16, int(settings.SCREEN_HEIGHT * 0.024))
            icon_rect = pygame.Rect(icon_x - size, rect.top + 5, size, size)
            img = pygame.transform.smoothscale(images[0], (size, size))
            self.window.blit(img, icon_rect)
            pygame.draw.rect(self.window, (211, 171, 91), icon_rect, 1, border_radius=4)
            icon_x -= size + 4

        title = self._fit(event.title, self.log_title_font, rect.width - 16)
        title_surf = self.log_title_font.render(title, True, (248, 234, 203))
        self.window.blit(title_surf, (rect.left + 8, rect.top + 26))

        lines = self._wrap(event.detail, self.log_font, rect.width - 16, max_lines=2)
        y = rect.top + 26 + title_surf.get_height() + 3
        for line in lines:
            surf = self.log_font.render(line, True, (218, 208, 184))
            self.window.blit(surf, (rect.left + 8, y))
            y += surf.get_height() + 1

    def _draw_tooltip(self, hover):
        name, anchor = hover
        text = self.body_font.render(name, True, settings.TOOLTIP_TEXT_COLOR)
        pad_x = settings.TOOLTIP_PAD_X
        pad_y = settings.TOOLTIP_PAD_Y
        rect = pygame.Rect(anchor.centerx - text.get_width() // 2 - pad_x,
                           anchor.bottom + 6,
                           text.get_width() + pad_x * 2,
                           text.get_height() + pad_y * 2)
        rect.right = min(rect.right, settings.SCREEN_WIDTH - 4)
        rect.left = max(4, rect.left)
        rect.bottom = min(rect.bottom, settings.SCREEN_HEIGHT - 4)
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.TOOLTIP_BG_COLOR, surf.get_rect(),
                         border_radius=settings.TOOLTIP_CORNER_R)
        pygame.draw.rect(surf, settings.TOOLTIP_BORDER_COLOR, surf.get_rect(),
                         settings.TOOLTIP_BORDER_WIDTH,
                         border_radius=settings.TOOLTIP_CORNER_R)
        self.window.blit(surf, rect.topleft)
        self.window.blit(text, (rect.left + pad_x, rect.top + pad_y))

    def _fit(self, text, font, max_width):
        text = text or ''
        if font.size(text)[0] <= max_width:
            return text
        clipped = text
        ellipsis = '...'
        while clipped and font.size(clipped + ellipsis)[0] > max_width:
            clipped = clipped[:-1]
        return clipped + ellipsis if clipped else ellipsis

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
