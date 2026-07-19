# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import math
import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from game.components.easing import ease_out_back
from config import settings
from config.screen_settings import _UI_SCALE
from game.components.buttons.menu_button import Button
from utils.game_service import fetch_user_games, fetch_user
from utils import sound
import logging

logger = logging.getLogger('nk.screens.duel_menu')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# Badge appearance (same as game_menu_screen)
_BADGE_RADIUS = int(0.014 * _SH * _UI_SCALE)
_BADGE_CLR    = (210, 40, 40)
_BADGE_TXT    = (255, 255, 255)


def _draw_panel(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


class DuelMenuScreen(MenuScreenMixin, Screen):
    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── Custom button image ─────────────────────────────────────
        self._btn_img = pygame.image.load(settings.GAME_MENU_BTN_IMG_PATH).convert_alpha()

        # ── Title font ──────────────────────────────────────────────
        self._title_font = settings.get_font(settings.GAME_MENU_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Duel', True, settings.GAME_MENU_TITLE_CLR)

        # ── Menu buttons (centred) ──────────────────────────────────
        _btn_w = settings.GAME_MENU_BTN_W
        _btn_h = settings.GAME_MENU_BTN_H
        _btn_gap = settings.GAME_MENU_BTN_GAP

        btn_x = (_SW - _btn_w) // 2
        title_h = self._title_surf.get_height() + settings.GAME_MENU_TITLE_PAD_BOTTOM
        n_btns = 3
        content_h = title_h + n_btns * _btn_h + (n_btns - 1) * _btn_gap
        box_h = settings.GAME_MENU_BOX_PAD_TOP + content_h + settings.GAME_MENU_BOX_PAD_BOTTOM
        box_w = _btn_w + settings.GAME_MENU_BOX_PAD_X * 2
        self._box_rect = pygame.Rect(
            (_SW - box_w) // 2,
            (_SH - box_h) // 2,
            box_w, box_h)

        first_btn_y = self._box_rect.y + settings.GAME_MENU_BOX_PAD_TOP + title_h

        self.button_new = Button(self.window, btn_x, first_btn_y,
                                 "New Game", width=_btn_w, height=_btn_h)
        self.button_load = Button(self.window, btn_x, first_btn_y + _btn_h + _btn_gap,
                                  "Load Game", width=_btn_w, height=_btn_h)
        self.button_back = Button(self.window, btn_x, first_btn_y + 2 * (_btn_h + _btn_gap),
                                  "Back", width=_btn_w, height=_btn_h)

        # Apply custom button images
        for btn in (self.button_new, self.button_load, self.button_back):
            btn.button_image = pygame.transform.smoothscale(
                self._btn_img, (btn.rect.width, btn.rect.height))
            btn.button_image_small = pygame.transform.smoothscale(
                self._btn_img, (int(btn.rect.width * 0.95), int(btn.rect.height * 0.95)))

        # ── Oversized glow images (drawn BEHIND the button) ─────────
        glow_w = int(_btn_w * settings.GAME_MENU_GLOW_W_FACTOR)
        glow_h = int(_btn_h * settings.GAME_MENU_GLOW_H_FACTOR)
        self._menu_glows = {}
        for colour in ('yellow', 'white', 'orange'):
            raw = pygame.image.load(settings.GAME_MENU_GLOW_DIR + colour + '.png').convert_alpha()
            self._menu_glows[colour] = pygame.transform.smoothscale(raw, (glow_w, glow_h))

        self.menu_buttons += [self.button_new, self.button_load, self.button_back]

        # Badge font
        self._badge_font = settings.get_font(settings.mobile_font_size(
            int(0.018 * _SH * _UI_SCALE), settings.FS_BODY), bold=True)
        self._duel_tutorial_intro_dialogue = None

        # Entrance-slide bookkeeping (stamped when rendering resumes)
        self._last_render_ms = None
        self._entered_at_ms = 0


    # ── helper: draw a menu button with glow BEHIND ─────────────────
    def _draw_menu_button(self, btn, dy=0):
        # dy is a draw-only entrance offset; hit-testing keeps btn.rect.
        rect = btn.rect.move(0, dy) if dy else btn.rect
        is_disabled = hasattr(btn, 'disabled') and btn.disabled
        if not is_disabled:
            if btn.hovered and btn.clicked:
                glow = self._menu_glows['yellow']
            elif btn.hovered and not btn.active:
                glow = self._menu_glows['white']
            elif btn.active:
                glow = self._menu_glows['orange']
            else:
                glow = None
            if glow:
                gx = rect.centerx - glow.get_width() // 2
                gy = rect.centery - glow.get_height() // 2
                self.window.blit(glow, (gx, gy))

        if btn.clicked:
            img = btn.button_image_small
            pos = img.get_rect(center=rect.center).topleft
        else:
            img = btn.button_image
            pos = rect.topleft
        self.window.blit(img, pos)

        font = btn.font_small if btn.clicked else btn.font
        text_surf = font.render(btn.text, True, btn.get_text_color())
        self.window.blit(text_surf, text_surf.get_rect(center=rect.center))

    def _menu_button_entrance_dy(self, index):
        """Draw-only staggered slide-up offset for a menu button."""
        if not self._entered_at_ms:
            return 0
        t = (pygame.time.get_ticks() - self._entered_at_ms - index * 60) / 240.0
        if t >= 1.0:
            return 0
        return int((1.0 - ease_out_back(max(0.0, t))) * 12)

    def _draw_badge(self, btn, count):
        if count <= 0:
            return
        # Gentle breathing pulse — pure draw, no state.
        txt = self._badge_font.render(str(count), True, _BADGE_TXT)
        content_radius = (max(txt.get_width(), txt.get_height()) + 5) // 2
        anchor_radius = max(_BADGE_RADIUS, content_radius)
        radius = max(
            content_radius,
            int(_BADGE_RADIUS * (
                1.0 + 0.12 * math.sin(pygame.time.get_ticks() * 0.006))),
        )
        cx = btn.rect.right - anchor_radius
        cy = btn.rect.top + anchor_radius
        pygame.draw.circle(self.window, _BADGE_CLR, (cx, cy), radius)
        self.window.blit(txt, txt.get_rect(center=(cx, cy)))

    def render(self):
        self._draw_menu_chrome()

        # Dark transparent box
        _draw_panel(self.window, self._box_rect)

        # Title
        title_x = self._box_rect.centerx - self._title_surf.get_width() // 2
        title_y = self._box_rect.y + settings.GAME_MENU_BOX_PAD_TOP
        self.window.blit(self._title_surf, (title_x, title_y))

        # Entrance detection: a gap in rendering means the screen was just
        # (re)entered — slide the buttons up with a small stagger.
        now = pygame.time.get_ticks()
        if self._last_render_ms is None or now - self._last_render_ms > 500:
            self._entered_at_ms = now
        self._last_render_ms = now

        # Menu buttons
        for index, btn in enumerate((self.button_new, self.button_load, self.button_back)):
            self._draw_menu_button(btn, dy=self._menu_button_entrance_dy(index))

        # Badges
        self._draw_badge(self.button_load, self.state.badge_new_games)
        self._draw_badge(self.button_new, self.state.badge_new_challenges)

        self._draw_menu_overlay()
        self._draw_menu_coach(self._current_duel_menu_coach_step())
        if getattr(self, '_duel_tutorial_intro_dialogue', None):
            self._duel_tutorial_intro_dialogue.draw()
        self._draw_tutorial_complete_dialogue()

    def update(self, events):
        super().update()
        self._update_icon_buttons()
        self._maybe_show_duel_tutorial_intro_window()
        self._maybe_show_tutorial_completion()

    def handle_events(self, events):
        if self._handle_tutorial_completion_events(events):
            return
        if self._handle_duel_tutorial_intro_events(events):
            return
        coach_step = self._current_duel_menu_coach_step()
        if self._handle_menu_coach_events(events, coach_step):
            return

        if super().handle_events(events):
            events = ()
        for event in events:
            if self._handle_icon_events(event):
                continue
            # Click outside content box → back to game menu
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and not self._box_rect.collidepoint(event.pos)):
                self.state.screen = 'game_menu'
                return
            if event.type == MOUSEBUTTONUP:
                self.handle_button_clicks()

    def handle_button_clicks(self):
        if self.button_new.collide():
            sound.play('ui_click')
            self._mark_menu_coach_seen('new_game')
            # Mark current challenges as seen
            self.state.badge_new_challenges = 0
            try:
                username = self.state.user_dict.get('username') if self.state.user_dict else None
                if username:
                    user = fetch_user(username)
                    received = user.get('challenges_received', [])
                    self.state._known_challenge_ids = {c['id'] for c in received}
            except Exception:
                pass
            self.state.screen = 'new_game'
            logger.debug("New Game button clicked")
        elif self.button_load.collide():
            sound.play('ui_click')
            # Mark current games as seen
            self.state.badge_new_games = 0
            try:
                username = self.state.user_dict.get('username') if self.state.user_dict else None
                if username:
                    game_dicts = fetch_user_games(username)
                    self.state._known_game_ids = {g['id'] for g in game_dicts if g.get('mode', 'duel') == 'duel'}
            except Exception:
                pass
            self.state.screen = 'load_game'
            logger.debug("Load Game button clicked")
        elif self.button_back.collide():
            sound.play('ui_back')
            self.state.screen = 'game_menu'
            logger.debug("Back button clicked")

    def _first_duel_incomplete(self):
        onboarding = (getattr(self.state, 'user_dict', None) or {}).get('onboarding') or {}
        completed = set(onboarding.get('completed_steps') or [])
        return bool(
            onboarding
            and (
                onboarding.get('replaying_lesson') == 'duel_basics'
                or 'finish_duel_basics_lesson' not in completed
            )
        )

    def _duel_basics_active(self):
        onboarding = (
            (getattr(self.state, 'user_dict', None) or {})
            .get('onboarding') or {}
        )
        return onboarding.get('active_lesson') == 'duel_basics'

    def _duel_tutorial_intro_allowed(self):
        onboarding = (getattr(self.state, 'user_dict', None) or {}).get('onboarding') or {}
        if not onboarding or onboarding.get('onboarding_skipped'):
            return False
        if not self._duel_basics_active():
            return False
        if not self._first_duel_incomplete():
            return False
        if getattr(self, 'dialogue_box', None) or getattr(self, '_onboarding_guide_open', False):
            return False
        return True

    def _duel_tutorial_intro_pages(self):
        from game.tutorial_content import duel_intro_pages
        return duel_intro_pages()

    def _maybe_show_duel_tutorial_intro_window(self):
        if getattr(self, '_duel_tutorial_intro_dialogue', None):
            return
        if not self._duel_tutorial_intro_allowed():
            return
        forced = bool(getattr(self.state, 'pending_duel_tutorial_intro', False))
        if not forced and 'duel_tutorial_start_window' in self._menu_coach_seen():
            return
        from game.components.tutorial_window import TutorialWindowDialogue
        self._duel_tutorial_intro_dialogue = TutorialWindowDialogue(
            self.window,
            self._duel_tutorial_intro_pages(),
            title='Duel Basics',
        )

    def _handle_duel_tutorial_intro_events(self, events):
        win = getattr(self, '_duel_tutorial_intro_dialogue', None)
        if win is None:
            return False
        if any(getattr(e, 'type', None) == QUIT for e in events):
            return False
        if win.update(events) == 'done':
            self._duel_tutorial_intro_dialogue = None
            if hasattr(self.state, 'pending_duel_tutorial_intro'):
                self.state.pending_duel_tutorial_intro = False
            self._mark_menu_coach_seen('duel_tutorial_start_window')
        return True

    def _current_duel_menu_coach_step(self):
        if (not self._menu_coach_allowed_common()
                or not self._duel_basics_active()
                or not self._first_duel_incomplete()):
            return None
        if getattr(self, '_duel_tutorial_intro_dialogue', None):
            return None
        if 'new_game' in self._menu_coach_seen():
            return None
        return {
            'id': 'new_game',
            'rect': self.button_new.rect,
            'title': 'Create A Duel',
            'body': "Tap New Game. We'll set up a friendly AI opponent for your first duel.",
            'action': 'click',
            'mark_on_click': True,
        }
