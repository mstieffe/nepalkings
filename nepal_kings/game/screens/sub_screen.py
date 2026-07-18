# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import sys
import pygame
from pygame.locals import *
from config import settings
from game.components.dialogue_box import DialogueBox
from game.components.scroll_text_list_shifter import ScrollTextListShifter
from utils.utils import SubScreenButton

class SubScreen:
    def __init__(self, window, game, x, y, title=None):

        # Set up the display
        self.window = window

        self.game = game

        self.x = x
        self.y = y
        self._layout_offset_x = self.x - settings.SUB_SCREEN_X
        self._layout_offset_y = self.y - settings.SUB_SCREEN_Y

        self.title = title

        self.init_background()
        self.sub_box_background = None
        self.scroll_background = None

        # Set up the font
        self.font = settings.get_font(settings.FONT_SIZE)
        self.title_font = settings.get_font(settings.SUB_SCREEN_TITLE_FONT_SIZE)

        self.dialogue_box = None

        self.last_update_time = pygame.time.get_ticks()
        self.update_interval = 100  # Set default interval for updates

        self.buttons = []

        self.scroll_text_list = []
        self.scroll_text_list_shifter = None

        # Close / X button (top-right of subscreen background).  Kingdom
        # pickers are modal on mobile, so the old decorative 13px close mark
        # was not a usable touch target.  Keep the visual compact on desktop,
        # but give mobile a visible compact control plus a full-size hit area.
        self._on_done = None  # callback set by parent screen
        self._close_font = settings.get_font(int(settings.FONT_SIZE * 0.85), bold=True)
        _cbsz = int(0.028 * settings.SCREEN_HEIGHT)
        if settings.TOUCH_TARGET_MIN > 0:
            _cbsz = max(_cbsz, settings.TOUCH_COMPACT_MIN)
        _bg_w = settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH
        _margin = int(0.012 * settings.SCREEN_WIDTH)
        self._close_rect = pygame.Rect(
            self.x + _bg_w - _cbsz - _margin,
            self.y + _margin,
            _cbsz, _cbsz)
        self._close_hit_rect = self._close_rect.copy()
        if settings.TOUCH_TARGET_MIN > 0:
            grow_x = max(0, settings.TOUCH_TARGET_MIN - self._close_hit_rect.w)
            grow_y = max(0, settings.TOUCH_TARGET_MIN - self._close_hit_rect.h)
            self._close_hit_rect.inflate_ip(grow_x, grow_y)

    def _fx_layer(self):
        """Effects layer of the owning duel shell, or ``None``.

        ``GameScreen`` exposes ``_fx``; ``ConquerGameScreen`` runs its own
        effect choreography and has no ``_fx`` attribute, so subscreen effect
        calls (``fx = self._fx_layer(); if fx: ...``) are automatically inert
        in conquer mode.
        """
        state = getattr(self, 'state', None)
        return getattr(getattr(state, 'parent_screen', None), '_fx', None)

    def _sx(self, x):
        """Translate a base screen x-coordinate by this subscreen origin."""
        return int(x + self._layout_offset_x)

    def _sy(self, y):
        """Translate a base screen y-coordinate by this subscreen origin."""
        return int(y + self._layout_offset_y)

    def _spos(self, x, y):
        """Translate a base screen coordinate pair by this subscreen origin."""
        return self._sx(x), self._sy(y)

    def make_button(self, text, x, y, width: int = None, height: int = None, button_img_active=None, button_img_inactive=None):
        """Helper to create a button."""
        return SubScreenButton(self.window, x, y, text, width=width, height=height, 
                             button_img_active=button_img_active, button_img_inactive=button_img_inactive)

    def draw_title(self):
        """Draw the title on an opaque brown badge."""
        if self.title:
            _pad = settings.SUB_SCREEN_TITLE_PADDING
            _corner_r = settings.SUB_SCREEN_TITLE_CORNER_R
            _off = settings.SUB_SCREEN_TITLE_SHADOW_OFFSET

            # Measure title text
            title_surf = self.title_font.render(self.title, True,
                                               settings.SUB_SCREEN_TITLE_COLOR)
            title_rect = title_surf.get_rect(
                center=self._spos(settings.SUB_SCREEN_TITLE_X, settings.SUB_SCREEN_TITLE_Y))

            # Background badge rect with padding
            bg_rect = pygame.Rect(
                title_rect.left - _pad * 2,
                title_rect.top - _pad,
                title_rect.width + 4 * _pad,
                title_rect.height + 2 * _pad
            )

            mode = getattr(self, 'mode', None)
            title_bg = settings.SUB_SCREEN_TITLE_BG_COLOR
            title_border = settings.SUB_SCREEN_TITLE_BORDER_COLOR
            if mode == 'conquer':
                title_bg = (72, 38, 24)
                title_border = (210, 142, 72)
            elif mode in ('defence', 'defence_draft'):
                title_bg = (35, 48, 66)
                title_border = (112, 160, 204)

            # Opaque contextual badge; the rest of the picker remains shared.
            pygame.draw.rect(self.window, title_bg,
                             bg_rect, border_radius=_corner_r)
            pygame.draw.rect(self.window, title_border,
                             bg_rect, settings.SUB_SCREEN_TITLE_BORDER_WIDTH,
                             border_radius=_corner_r)

            # Drop shadow text
            shadow_surf = self.title_font.render(self.title, True,
                                                settings.SUB_SCREEN_TITLE_SHADOW_COLOR)
            shadow_rect = shadow_surf.get_rect(
                center=self._spos(settings.SUB_SCREEN_TITLE_X + _off,
                                  settings.SUB_SCREEN_TITLE_Y + _off))
            self.window.blit(shadow_surf, shadow_rect)

            # Gold title text
            self.window.blit(title_surf, title_rect)

            


    def init_background(self):
        """Build a programmatic parchment background with a thick decorative frame."""
        w = settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH
        h = settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT
        r = settings.SUB_SCREEN_BG_CORNER_R
        pad = settings.SUB_SCREEN_BG_PAD
        bw = settings.SUB_SCREEN_BG_BORDER_W
        frame = settings.SUB_SCREEN_BG_FRAME_W

        panel = pygame.Surface((w, h), pygame.SRCALPHA)

        # 1) Outer frame fill (thick brown band)
        pygame.draw.rect(panel, settings.SUB_SCREEN_BG_FRAME_CLR,
                         (0, 0, w, h), border_radius=r)

        # 2) Slightly darker inner frame edge for bevel depth
        pygame.draw.rect(panel, settings.SUB_SCREEN_BG_FRAME_INNER_CLR,
                         (frame // 3, frame // 3,
                          w - 2 * (frame // 3), h - 2 * (frame // 3)),
                         border_radius=max(1, r - 2))

        # 3) Parchment fill inside the frame
        inner_r = max(1, r - 4)
        pygame.draw.rect(panel, settings.SUB_SCREEN_BG_CLR,
                         (frame, frame, w - 2 * frame, h - 2 * frame),
                         border_radius=inner_r)

        # 4) Subtle depth within parchment
        pygame.draw.rect(panel, settings.SUB_SCREEN_BG_INNER_CLR,
                         (frame + pad, frame + pad,
                          w - 2 * (frame + pad), h - 2 * (frame + pad)),
                         border_radius=max(1, inner_r - 2))

        # 5) Dark edge line between frame and parchment
        pygame.draw.rect(panel, settings.SUB_SCREEN_BG_FRAME_EDGE_CLR,
                         (frame, frame, w - 2 * frame, h - 2 * frame),
                         2, border_radius=inner_r)

        # 6) Outer dark border
        pygame.draw.rect(panel, settings.SUB_SCREEN_BG_BORDER_CLR,
                         (0, 0, w, h), bw, border_radius=r)

        self.background = panel

    def init_sub_box_background(self, x, y, width, height):
        """Build a programmatic warm orange-brown sub-box panel with dark frame."""
        r = settings.SUB_BOX_BG_CORNER_R
        pad = settings.SUB_BOX_BG_PAD
        bw = settings.SUB_BOX_BG_BORDER_W
        frame = settings.SUB_BOX_BG_FRAME_W

        panel = pygame.Surface((width, height), pygame.SRCALPHA)

        # 1) Dark frame band
        pygame.draw.rect(panel, settings.SUB_BOX_BG_FRAME_CLR,
                         (0, 0, width, height), border_radius=r)

        # 2) Slightly darker inner frame edge
        pygame.draw.rect(panel, settings.SUB_BOX_BG_FRAME_INNER_CLR,
                         (frame // 3, frame // 3,
                          width - 2 * (frame // 3), height - 2 * (frame // 3)),
                         border_radius=max(1, r - 1))

        # 3) Warm orange-brown fill inside the frame
        inner_r = max(1, r - 2)
        pygame.draw.rect(panel, settings.SUB_BOX_BG_CLR,
                         (frame, frame, width - 2 * frame, height - 2 * frame),
                         border_radius=inner_r)

        # 4) Subtle depth within the fill
        pygame.draw.rect(panel, settings.SUB_BOX_BG_INNER_CLR,
                         (frame + pad, frame + pad,
                          width - 2 * (frame + pad), height - 2 * (frame + pad)),
                         border_radius=max(1, inner_r - 1))

        # 5) Dark edge line at frame/fill boundary
        pygame.draw.rect(panel, settings.SUB_BOX_BG_BORDER_CLR,
                         (frame, frame, width - 2 * frame, height - 2 * frame),
                         bw, border_radius=inner_r)

        # 6) Outer border
        pygame.draw.rect(panel, settings.SUB_BOX_BG_BORDER_CLR,
                         (0, 0, width, height), bw, border_radius=r)

        self.sub_box_background = panel
        self.sub_box_x = self._sx(x)
        self.sub_box_y = self._sy(y)

    def init_scroll_background(self, x, y, width, height):
        """Build a warm brown programmatic scroll panel (replaces scroll.png)."""
        self.scroll_x = self._sx(x)
        self.scroll_y = self._sy(y)
        self.scroll_w = width
        self.scroll_h = height
        self.scroll_text_list = []

        r = settings.SCROLL_PANEL_CORNER_R
        pad = settings.SCROLL_PANEL_PAD
        bw = settings.SCROLL_PANEL_BORDER_WIDTH

        panel = pygame.Surface((width, height), pygame.SRCALPHA)

        # Outer fill
        pygame.draw.rect(panel, settings.SCROLL_PANEL_BG_CLR,
                         (0, 0, width, height), border_radius=r)

        # Subtle inner darker rect for depth
        inner_rect = (pad, pad, width - 2 * pad, height - 2 * pad)
        pygame.draw.rect(panel, settings.SCROLL_PANEL_INNER_CLR,
                         inner_rect, border_radius=max(1, r - 2))

        # Border
        pygame.draw.rect(panel, settings.SCROLL_PANEL_BORDER_CLR,
                         (0, 0, width, height),
                         bw, border_radius=r)

        self.scroll_background = panel


    def draw_msg(self):
        """Render any messages to the screen."""
        pass
        #starting_y_position = settings.get_y(0.6)
        #for line, _ in self.state.message_lines:
        #    line_y_position = starting_y_position + (self.state.message_lines.index((line, _)) * settings.MESSAGE_SPACING)
        #    self.draw_text(line, settings.MSG_TEXT_COLOR, settings.get_x(0.1), line_y_position)

    def draw_text(self, text, color, x, y):
        """Draw text to the screen."""
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)


    def make_dialogue_box(self, message, actions=None, images=None, icon=None, title="", auto_close_delay=None, message_after_images=None):
        """Create a dialogue box with specified message and actions."""
        from utils import sound
        sound.play_for_dialogue(title)
        self.dialogue_box = DialogueBox(self.window, message, actions=actions, images=images, icon=icon, title=title, auto_close_delay=auto_close_delay, message_after_images=message_after_images)

    def make_scroll_text_list_shifter(self, text_list, x, y, scroll_height=None):
        """Create a scroll text list shifter."""
        scroll_rect = None
        if hasattr(self, 'scroll_x'):
            scroll_rect = pygame.Rect(self.scroll_x, self.scroll_y, self.scroll_w, self.scroll_h)
        self.scroll_text_list_shifter = ScrollTextListShifter(
            self.window, text_list, self._sx(x), self._sy(y),
            scroll_height=scroll_height, scroll_rect=scroll_rect
        )

    def handle_events(self, events):
        """Handle events like mouse clicks and quit."""
        # Derived subscreens own the response semantics for their overlays,
        # but the shared scroll/close controls sit underneath them.  Do not
        # let the same pointer event reach those covered controls first.
        if any(getattr(self, name, None) for name in (
                'dialogue_box',
                'figure_detail_box',
                'battle_move_detail_box',
                '_figure_detail_box',
                '_move_detail_box')):
            return
        if self.scroll_text_list_shifter:
            self.scroll_text_list_shifter.handle_events(events)
        for event in events:
            if event.type == MOUSEBUTTONUP and getattr(event, 'button', 1) == 1:
                hit_rect = getattr(self, '_close_hit_rect', self._close_rect)
                if hit_rect.collidepoint(event.pos):
                    if self._on_done:
                        self._on_done()

    def draw(self):
        """Render buttons, messages, and the dialogue box."""

        # Draw the background image
        self.window.blit(self.background, (self.x, self.y))

        # Draw the sub box background image
        if self.sub_box_background:
            self.window.blit(self.sub_box_background, (self.sub_box_x, self.sub_box_y))
        
        # Draw the scroll background image
        if self.scroll_background:
            self.window.blit(self.scroll_background, (self.scroll_x, self.scroll_y))
        if self.scroll_text_list != [] and self.scroll_text_list_shifter:
            self.scroll_text_list_shifter.draw()
        #if self.scroll_text != []:
        #    #for text in self.scroll_text:
        #    #    self.draw_text_in_scroll(text, settings.SCROLL_TEXT_X, settings.SCROLL_TEXT_Y)


        for button in self.buttons:
            button.draw()
            
        self.draw_title()
        self._draw_close_button()

    def _draw_close_button(self):
        """Draw a small X button in the top-right corner of the subscreen."""
        if not self._on_done:
            return
        r = self._close_rect
        mouse_pos = pygame.mouse.get_pos()
        hovered = getattr(self, '_close_hit_rect', r).collidepoint(mouse_pos)

        bg_clr = (80, 50, 25, 220) if hovered else (55, 35, 18, 200)
        border_clr = (180, 160, 120) if hovered else (120, 100, 70)
        txt_clr = (255, 240, 200) if hovered else (200, 180, 140)

        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg_clr, surf.get_rect(), border_radius=4)
        pygame.draw.rect(surf, border_clr, surf.get_rect(), 1, border_radius=4)
        self.window.blit(surf, r.topleft)

        txt = self._close_font.render('\u00d7', True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=r.center))

    def draw_on_top(self):

        if self.dialogue_box:
            self.dialogue_box.draw()  # Ensure the dialogue box is rendered on top of other elements

        self.draw_msg()



    def update(self, game):
        """Update control buttons and game/menu buttons."""
        self.game = game
        if any(getattr(self, name, None) for name in (
                'dialogue_box',
                'figure_detail_box',
                'battle_move_detail_box',
                '_figure_detail_box',
                '_move_detail_box')):
            return
        for button in self.buttons:
            button.update()
        if self.scroll_text_list_shifter:
            self.scroll_text_list_shifter.update()
