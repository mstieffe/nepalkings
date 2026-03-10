from config import settings
import pygame


class ConfirmButton:
    def __init__(self, window, x=0, y=0, text="", width=None, height=None, disabled=False):
        self.window = window
        self.x = x
        self.y = y
        self.text = text
        self.disabled = disabled

        # Fonts
        self.font = pygame.font.Font(settings.FONT_PATH, settings.CONFIRM_BUTTON_FONT_SIZE)
        self.font_small = pygame.font.Font(settings.FONT_PATH, settings.CONFIRM_BUTTON_FONT_SIZE_SMALL)

        # Dimensions
        self.set_dimensions(width, height)

        # Images
        self.load_images()

        # States
        self.hovered = False
        self.clicked = False
        self.active = False

    def set_dimensions(self, width, height):
        text_obj = self.font.render(self.text, True, settings.CONFIRM_BUTTON_TEXT_COLOR_PASSIVE)
        button_width = max(width or settings.CONFIRM_BUTTON_WIDTH,
                           text_obj.get_width() + settings.SMALL_SPACER_X)
        button_height = height or settings.CONFIRM_BUTTON_HEIGHT
        self.rect = pygame.Rect(self.x, self.y, button_width, button_height)

    def load_images(self):
        w, h = self.rect.width, self.rect.height

        # Normal button (same as login menu)
        raw = pygame.image.load(settings.CONFIRM_BUTTON_IMG_PATH).convert_alpha()
        self.button_image = pygame.transform.smoothscale(raw, (w, h))
        self.button_image_small = pygame.transform.smoothscale(raw,
                                    (int(w * 0.95), int(h * 0.95)))

        # Disabled / greyscale button
        raw_gs = pygame.image.load(settings.CONFIRM_BUTTON_IMG_DISABLED_PATH).convert_alpha()
        self.button_image_disabled = pygame.transform.smoothscale(raw_gs, (w, h))

        # Glow images
        glow_w = int(w * settings.CONFIRM_BUTTON_GLOW_W_FACTOR)
        glow_h = int(h * settings.CONFIRM_BUTTON_GLOW_H_FACTOR)
        self.glow_images = {}
        for colour in ('yellow', 'white', 'orange'):
            g = pygame.image.load(settings.CONFIRM_BUTTON_GLOW_DIR + colour + '.png').convert_alpha()
            self.glow_images[colour] = pygame.transform.smoothscale(g, (glow_w, glow_h))

    def collide(self):
        return self.rect.collidepoint(pygame.mouse.get_pos())

    def draw(self):
        # ---- Disabled state: greyscale, no glow ----
        if self.disabled:
            self.window.blit(self.button_image_disabled, self.rect.topleft)
            txt = self.font.render(self.text, True, settings.CONFIRM_BUTTON_TEXT_COLOR_DISABLED)
            self.window.blit(txt, txt.get_rect(center=self.rect.center))
            return

        # ---- Glow ----
        if self.hovered and self.active:
            self._draw_glow('orange')
        elif self.hovered:
            self._draw_glow('yellow')
        elif self.active:
            self._draw_glow('orange')
        else:
            self._draw_glow('white')

        # ---- Button image (slightly smaller when click-pressed) ----
        if self.clicked:
            img = self.button_image_small
            r = img.get_rect(center=self.rect.center)
            self.window.blit(img, r.topleft)
        else:
            self.window.blit(self.button_image, self.rect.topleft)

        # ---- Text ----
        font = self.font_small if self.clicked else self.font
        txt = font.render(self.text, True, self._text_color())
        self.window.blit(txt, txt.get_rect(center=self.rect.center))

    def _draw_glow(self, colour):
        glow = self.glow_images.get(colour)
        if glow:
            self.window.blit(glow, glow.get_rect(center=self.rect.center).topleft)

    def _text_color(self):
        if self.disabled:
            return settings.CONFIRM_BUTTON_TEXT_COLOR_DISABLED
        if self.hovered:
            return settings.CONFIRM_BUTTON_TEXT_COLOR_HOVERED
        if self.active:
            return settings.CONFIRM_BUTTON_TEXT_COLOR_ACTIVE
        return settings.CONFIRM_BUTTON_TEXT_COLOR_PASSIVE

    def update(self):
        if not self.disabled:
            self.hovered = self.collide()
            self.clicked = self.hovered and pygame.mouse.get_pressed()[0]
        else:
            self.hovered = False
            self.clicked = False
