"""Battle move icon with dynamic glow based on suit color."""

import pygame
from config import settings


class BattleMoveIcon:
    """Icon for a battle move family in the battle shop.

    Shows the move icon + frame, with glow color adapting to the currently
    selected suit color (green for red/Djungle suits, blue for black/Himalaya).
    """

    def __init__(self, window, game, family, x=0, y=0):
        self.window = window
        self.game = game
        self.family = family
        self.x = x
        self.y = y

        # State
        self.is_active = True
        self.clicked = False
        self.hovered = False

        # Fonts
        self.font = pygame.font.Font(settings.FONT_PATH, settings.BATTLE_MOVE_ICON_FONT_SIZE)
        self.font_big = pygame.font.Font(settings.FONT_PATH, settings.BATTLE_MOVE_ICON_FONT_BIG_SIZE)

        # Text surfaces
        self.text_surface = self.font.render(family.name, True, settings.BATTLE_MOVE_ICON_CAPTION_COLOR)
        self.text_surface_big = self.font_big.render(family.name, True, settings.BATTLE_MOVE_ICON_CAPTION_COLOR)
        self.text_surface_grey = self.font.render(family.name, True, (50, 50, 50))
        self.text_surface_grey_big = self.font_big.render(family.name, True, (50, 50, 50))

        # Scale icon/frame images
        self._init_images(family)

        # Load glow effects (green + blue for dynamic switching)
        self._init_glows(family)

        # Current glow mode: 'green', 'blue', or 'gold'
        self._glow_mode = 'gold'
        self._apply_glow_mode()

    # ------------------------------------------------------------------ init
    def _init_images(self, family):
        scale = 1.0
        big = settings.BATTLE_MOVE_ICON_BIG_SCALE

        self.icon_img = self._scale_icon(family.icon_img, scale)
        self.icon_gray_img = self._scale_icon(family.icon_gray_img, scale)
        self.frame_img = self._scale_frame(family.frame_img, scale)
        self.frame_gray_img = self._scale_frame(family.frame_gray_img, scale)

        self.icon_img_big = self._scale_icon(family.icon_img, big)
        self.icon_gray_img_big = self._scale_icon(family.icon_gray_img, big)
        self.frame_img_big = self._scale_frame(family.frame_img, big)
        self.frame_gray_img_big = self._scale_frame(family.frame_gray_img, big)

    def _init_glows(self, family):
        glow_black = pygame.image.load('img/game_button/glow/black.png').convert_alpha()
        glow_white = pygame.image.load('img/game_button/glow/white.png').convert_alpha()
        glow_yellow = pygame.image.load('img/game_button/glow/yellow.png').convert_alpha()

        w = settings.BATTLE_MOVE_ICON_GLOW_WIDTH
        bw = settings.BATTLE_MOVE_ICON_GLOW_BIG_WIDTH

        self.glow_black = pygame.transform.smoothscale(glow_black, (w, w))
        self.glow_black.set_alpha(160)

        self.glow_white = pygame.transform.smoothscale(glow_white, (w, w))
        self.glow_white_big = pygame.transform.smoothscale(glow_white, (bw, bw))

        # Golden glow (for hovered but not-selected icons)
        self.glow_gold = pygame.transform.smoothscale(glow_yellow, (w, w))
        self.glow_gold_big = pygame.transform.smoothscale(glow_yellow, (bw, bw))

        # Green glow (for red / Djungle suits)
        self.glow_green = pygame.transform.smoothscale(family.glow_green_img, (w, w))
        self.glow_green_big = pygame.transform.smoothscale(family.glow_green_img, (bw, bw))

        # Blue glow (for black / Himalaya suits)
        self.glow_blue = pygame.transform.smoothscale(family.glow_blue_img, (w, w))
        self.glow_blue_big = pygame.transform.smoothscale(family.glow_blue_img, (bw, bw))

    def _apply_glow_mode(self):
        """Set active glow images based on current mode."""
        if self._glow_mode == 'blue':
            self.glow_active = self.glow_blue
            self.glow_active_big = self.glow_blue_big
        elif self._glow_mode == 'gold':
            self.glow_active = self.glow_gold
            self.glow_active_big = self.glow_gold_big
        elif self._glow_mode == 'white':
            self.glow_active = self.glow_white
            self.glow_active_big = self.glow_white_big
        else:
            self.glow_active = self.glow_green
            self.glow_active_big = self.glow_green_big

    # ---------------------------------------------------------------- public
    def set_glow_mode(self, mode):
        """Switch glow color: 'green'/'blue' for suit, 'gold' for default active, 'white' for no cards."""
        if mode != self._glow_mode:
            self._glow_mode = mode
            self._apply_glow_mode()

    def set_position(self, x, y):
        self.x = x
        self.y = y

    def collide(self):
        mouse = pygame.mouse.get_pos()
        iw = self.icon_img.get_width() if self.icon_img else 0
        ih = self.icon_img.get_height() if self.icon_img else 0
        return (self.x - iw // 2 < mouse[0] < self.x + iw // 2 and
                self.y - ih // 2 < mouse[1] < self.y + ih // 2)

    def handle_events(self, events):
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.collide():
                    self.clicked = not self.clicked

    def update(self):
        self.hovered = self.collide()

    # ------------------------------------------------------------------ draw
    def draw(self):
        pressed = pygame.mouse.get_pressed()[0]
        shadow_y = settings.get_y(0.005)

        icon = self.icon_img if self.is_active else self.icon_gray_img
        icon_big = self.icon_img_big if self.is_active else self.icon_gray_img_big
        frame = self.frame_img if self.is_active else self.frame_gray_img
        frame_big = self.frame_img_big if self.is_active else self.frame_gray_img_big

        glow_bg = None
        if pressed and self.hovered:
            glow = self.glow_black
            if self.is_active:
                glow_bg = self.glow_active
            cur_icon, cur_frame = icon, frame
        elif self.clicked:
            # Selected: green/blue glow (set via set_glow_mode)
            glow = self.glow_active_big
            cur_icon, cur_frame = icon_big, frame_big
        elif self.hovered and self.is_active:
            # Hovered + active: golden glow
            glow = self.glow_gold_big
            cur_icon, cur_frame = icon_big, frame_big
        elif self.hovered:
            # Hovered + inactive: white glow
            glow = self.glow_white_big
            cur_icon, cur_frame = icon_big, frame_big
        else:
            # Default: black shadow + white bg glow for active, black only for inactive
            glow = self.glow_black
            if self.is_active:
                glow_bg = self.glow_white
            cur_icon, cur_frame = icon, frame

        # Background glow
        if glow_bg:
            r = glow_bg.get_rect(center=(self.x, self.y + shadow_y))
            self.window.blit(glow_bg, r.topleft)

        # Main glow
        r = glow.get_rect(center=(self.x, self.y + shadow_y))
        self.window.blit(glow, r.topleft)

        # Icon
        r = cur_icon.get_rect(center=(self.x, self.y))
        self.window.blit(cur_icon, r.topleft)

        # Frame
        r = cur_frame.get_rect(center=(self.x, self.y))
        self.window.blit(cur_frame, r.topleft)

        # Name
        if self.is_active:
            ts = self.text_surface_big if (self.hovered or self.clicked) else self.text_surface
        else:
            ts = self.text_surface_grey_big if (self.hovered or self.clicked) else self.text_surface_grey

        tr = ts.get_rect(center=(self.x, self.y + cur_frame.get_height() // 2 + 15))
        self.window.blit(ts, tr.topleft)

    # --------------------------------------------------------------- helpers
    def _scale_icon(self, img, factor):
        if img is None:
            return None
        w = int(settings.BATTLE_MOVE_ICON_WIDTH * factor)
        h = int(settings.BATTLE_MOVE_ICON_HEIGHT * factor)
        return pygame.transform.smoothscale(img.convert_alpha(), (w, h))

    def _scale_frame(self, img, factor):
        if img is None:
            return None
        w = int(settings.BATTLE_MOVE_ICON_WIDTH * factor * settings.BATTLE_MOVE_FRAME_SCALE)
        h = int(settings.BATTLE_MOVE_ICON_HEIGHT * factor * settings.BATTLE_MOVE_FRAME_SCALE)
        return pygame.transform.smoothscale(img.convert_alpha(), (w, h))
