from config import settings
import pygame
import textwrap


# ── Themed button for the dialogue box ─────────────────────────────

class _DlgButton:
    """A small themed button drawn with menu_button2 + glow behind."""

    _btn_img_raw = None
    _glows = None

    @classmethod
    def _ensure_assets(cls, window):
        if cls._btn_img_raw is None:
            cls._btn_img_raw = pygame.image.load(
                settings.DIALOGUE_BOX_BTN_IMG_PATH).convert_alpha()
            cls._glows = {}
            glow_w = int(settings.DIALOGUE_BOX_BTN_W * 1.2)
            glow_h = int(settings.DIALOGUE_BOX_BTN_H * 2.0)
            for colour in ('yellow', 'white', 'orange'):
                raw = pygame.image.load(
                    settings.DIALOGUE_BOX_GLOW_DIR + colour + '.png').convert_alpha()
                cls._glows[colour] = pygame.transform.smoothscale(raw, (glow_w, glow_h))

    def __init__(self, window, x, y, text, width=None, height=None):
        _DlgButton._ensure_assets(window)
        self.window = window
        self.text = text
        w = width or settings.DIALOGUE_BOX_BTN_W
        h = height or settings.DIALOGUE_BOX_BTN_H
        self.rect = pygame.Rect(x, y, w, h)
        self.font = pygame.font.Font(settings.FONT_PATH,
                                     settings.DIALOGUE_BOX_BTN_FONT_SIZE)
        self.font_small = pygame.font.Font(settings.FONT_PATH,
                                           int(settings.DIALOGUE_BOX_BTN_FONT_SIZE * 0.9))
        self.btn_img = pygame.transform.smoothscale(
            _DlgButton._btn_img_raw, (w, h))
        self.btn_img_small = pygame.transform.smoothscale(
            _DlgButton._btn_img_raw, (int(w * 0.95), int(h * 0.95)))
        self.hovered = False
        self.clicked = False
        self.active = False
        self.disabled = False

    def collide(self):
        return self.rect.collidepoint(pygame.mouse.get_pos())

    def update(self):
        if self.disabled:
            self.hovered = False
            self.clicked = False
        else:
            self.hovered = self.collide()
            self.clicked = self.hovered and pygame.mouse.get_pressed()[0]

    def get_text_color(self):
        if self.disabled:
            return (100, 100, 100)
        if self.hovered:
            return settings.DIALOGUE_BOX_BTN_TEXT_HOVER_CLR
        return settings.DIALOGUE_BOX_BTN_TEXT_CLR

    def draw(self):
        # 1) Glow behind
        if not self.disabled:
            if self.hovered and self.clicked:
                glow = _DlgButton._glows['yellow']
            elif self.hovered:
                glow = _DlgButton._glows['white']
            else:
                glow = None
            if glow:
                gx = self.rect.centerx - glow.get_width() // 2
                gy = self.rect.centery - glow.get_height() // 2
                self.window.blit(glow, (gx, gy))

        # 2) Button image
        if self.clicked:
            img = self.btn_img_small
            pos = img.get_rect(center=self.rect.center).topleft
        else:
            img = self.btn_img
            pos = self.rect.topleft
        self.window.blit(img, pos)

        # 3) Text
        font = self.font_small if self.clicked else self.font
        txt = font.render(self.text, True, self.get_text_color())
        self.window.blit(txt, txt.get_rect(center=self.rect.center))


# ═══════════════════════════════════════════════════════════════════
#  DialogueBox
# ═══════════════════════════════════════════════════════════════════

class DialogueBox:
    def __init__(self, window, message, actions=None, images=None, icon=None,
                 title="", auto_close_delay=None, message_after_images=None):
        if actions is None:
            actions = ['ok']
        if images is None:
            images = []

        self.window = window
        self.message = message
        self.message_after_images = message_after_images
        self.images = images
        self.icon = None
        self.title = title
        self.font = pygame.font.Font(settings.FONT_PATH,
                                     settings.FONT_SIZE_DIALOGUE_BOX)
        self.title_font = pygame.font.Font(settings.FONT_PATH,
                                           settings.FONT_SIZE_TITLE_DIALOGUE_BOX)
        self.title_font.set_bold(True)
        self.actions = actions
        self.auto_close_delay = auto_close_delay
        self.auto_close_timer = pygame.time.get_ticks() if auto_close_delay else None
        self._created_at = pygame.time.get_ticks()  # grace period for MOUSEBUTTONUP

        _SW = settings.SCREEN_WIDTH
        _SH = settings.SCREEN_HEIGHT
        _corner_r = settings.DIALOGUE_BOX_CORNER_R

        # Icon
        if icon and icon in settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT:
            original_icon = settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT[icon]
            self.icon = self.scale_icon(original_icon)

        # Wrap message
        wrap_width = (settings.DIALOGUE_BOX_WIDTH - int(0.06 * _SW)) // max(1, self.font.size(' ')[0])
        self.lines = []
        for paragraph in self.message.split('\n'):
            if paragraph.strip():
                wrapped = textwrap.wrap(paragraph, width=wrap_width)
                self.lines.extend(wrapped if wrapped else [''])
            else:
                self.lines.append('')
        self.lines_surfaces = [self.font.render(l, True,
                               settings.DIALOGUE_BOX_MSG_TEXT_CLR) for l in self.lines]

        # Wrap after-images text
        self.after_lines = []
        if self.message_after_images:
            for paragraph in self.message_after_images.split('\n'):
                if paragraph.strip():
                    wrapped = textwrap.wrap(paragraph, width=wrap_width)
                    self.after_lines.extend(wrapped if wrapped else [''])
                else:
                    self.after_lines.append('')
        self.after_lines_surfaces = [self.font.render(l, True,
                                     settings.DIALOGUE_BOX_MSG_TEXT_CLR) for l in self.after_lines]

        # Process images
        self.ordered_items = self.process_images()
        has_surfaces = any(t == 'surface' for t, _ in self.ordered_items)
        has_drawables = any(t == 'drawable' for t, _ in self.ordered_items)

        # Metrics
        _line_h = self.font.get_height() + int(0.004 * _SH)
        _pad_top = settings.DIALOGUE_BOX_TEXT_MARGIN_Y
        _pad_bottom = settings.DIALOGUE_BOX_BTN_MARGIN_BOTTOM

        self.title_height = (self.title_font.get_height() + int(0.016 * _SH)) if self.title else 0
        self._sep_extra = int(0.018 * _SH) if self.title else 0  # space for separator line
        self.text_height = len(self.lines) * _line_h
        self.after_text_height = len(self.after_lines) * _line_h if self.after_lines else 0
        self.img_height = settings.DIALOGUE_BOX_IMG_HEIGHT if has_surfaces else 0
        self.drawable_object_height = settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT if has_drawables else 0
        self.content_height = max(self.img_height, self.drawable_object_height) if self.ordered_items else 0
        self.img_spacing = int(0.020 * _SH) if self.ordered_items else 0
        self.drawable_bottom_spacing = int(0.022 * _SH) if self.ordered_items else 0

        btn_h = settings.DIALOGUE_BOX_BTN_H if self.actions else 0
        self.button_height = btn_h + _pad_bottom if self.actions else 0

        self.box_height = (_pad_top + self.title_height + self._sep_extra +
                           self.text_height + self.img_spacing +
                           self.content_height + self.drawable_bottom_spacing +
                           self.after_text_height + self.button_height +
                           int(0.010 * _SH))

        # Position (centred)
        box_w = settings.DIALOGUE_BOX_WIDTH
        self.x = (_SW - box_w) // 2
        height_diff = self.box_height - settings.DIALOGUE_BOX_HEIGHT
        self.y = int(_SH * 0.5 - settings.DIALOGUE_BOX_HEIGHT * 0.75 - height_diff / 2)
        self.rect = pygame.Rect(self.x, self.y, box_w, self.box_height)

        # Pre-render panel surface (semi-transparent with rounded corners)
        self._panel = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
        pygame.draw.rect(self._panel, settings.DIALOGUE_BOX_BG_CLR,
                         self._panel.get_rect(), border_radius=_corner_r)
        pygame.draw.rect(self._panel, settings.DIALOGUE_BOX_BORDER_CLR,
                         self._panel.get_rect(),
                         settings.DIALOGUE_BOX_BORDER_WIDTH,
                         border_radius=_corner_r)

        # Full-screen dim overlay
        self._overlay = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
        self._overlay.fill(settings.DIALOGUE_BOX_OVERLAY_CLR)

        # Keep border_rect for any legacy code that references it
        self.border_rect = self.rect.inflate(2, 2)

        # Buttons
        if self.actions:
            _btn_w = settings.DIALOGUE_BOX_BTN_W
            _btn_gap = settings.DIALOGUE_BOX_BTN_GAP
            total_btns_w = len(self.actions) * _btn_w + (len(self.actions) - 1) * _btn_gap
            first_x = self.rect.centerx - total_btns_w // 2
            btn_y = self.rect.bottom - self.button_height + int(0.004 * _SH)
            self.buttons = []
            for i, action in enumerate(self.actions):
                bx = first_x + i * (_btn_w + _btn_gap)
                self.buttons.append(_DlgButton(self.window, bx, btn_y, action,
                                               width=_btn_w, height=settings.DIALOGUE_BOX_BTN_H))
        else:
            self.buttons = []

        # Layout cache
        self._line_h = _line_h

    # ── helpers ─────────────────────────────────────────────────────

    def process_images(self):
        ordered = []
        for img in self.images:
            if isinstance(img, pygame.Surface):
                iw, ih = img.get_size()
                ratio = settings.DIALOGUE_BOX_IMG_HEIGHT / ih
                nw = int(iw * ratio)
                scaled = pygame.transform.smoothscale(img, (nw, settings.DIALOGUE_BOX_IMG_HEIGHT))
                ordered.append(('surface', scaled))
            elif hasattr(img, "draw_icon"):
                ordered.append(('drawable', img))
        return ordered

    def scale_icon(self, icon):
        iw, ih = icon.get_size()
        ratio = settings.DIALOGUE_BOX_ICON_HEIGHT / ih
        nw = int(iw * ratio)
        return pygame.transform.smoothscale(icon, (nw, settings.DIALOGUE_BOX_ICON_HEIGHT))

    # ── draw ────────────────────────────────────────────────────────

    def draw(self):
        _SH = settings.SCREEN_HEIGHT
        _SW = settings.SCREEN_WIDTH

        # Dim overlay
        self.window.blit(self._overlay, (0, 0))

        # Panel
        self.window.blit(self._panel, self.rect.topleft)

        current_y = self.rect.y + settings.DIALOGUE_BOX_TEXT_MARGIN_Y

        # Title
        if self.title:
            title_surface = self.title_font.render(self.title, True,
                                                   settings.TITLE_TEXT_COLOR)
            title_rect = title_surface.get_rect(
                center=(self.rect.centerx, current_y + title_surface.get_height() // 2))

            if self.icon:
                icon_gap = int(0.010 * _SW)
                icon_y = title_rect.centery - self.icon.get_height() // 2
                self.window.blit(self.icon,
                                 (title_rect.left - icon_gap - self.icon.get_width(), icon_y))
                self.window.blit(self.icon,
                                 (title_rect.right + icon_gap, icon_y))

            self.window.blit(title_surface, title_rect)
            current_y += title_surface.get_height() + int(0.016 * _SH)

            # Separator line
            sep_x1 = self.rect.x + int(0.04 * _SW)
            sep_x2 = self.rect.right - int(0.04 * _SW)
            pygame.draw.line(self.window, settings.DIALOGUE_BOX_SEP_CLR,
                             (sep_x1, current_y), (sep_x2, current_y), 1)
            current_y += int(0.018 * _SH)

        # Message lines
        for i, line_surf in enumerate(self.lines_surfaces):
            ly = current_y + i * self._line_h
            self.window.blit(line_surf,
                             line_surf.get_rect(center=(self.rect.centerx, ly)))

        # Images / drawables position
        image_y = (current_y + len(self.lines_surfaces) * self._line_h +
                   self.img_spacing)

        if self.ordered_items:
            max_w = settings.DIALOGUE_BOX_WIDTH - int(0.04 * _SW)
            num = len(self.ordered_items)
            widths = []
            for t, item in self.ordered_items:
                if t == 'surface':
                    widths.append(item.get_width())
                else:
                    widths.append(settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT)

            natural_w = sum(widths) + (num - 1) * int(0.008 * _SW)

            if natural_w <= max_w:
                ix = self.rect.centerx - natural_w // 2
                for t, item in self.ordered_items:
                    if t == 'surface':
                        self.window.blit(item, (ix, image_y))
                        ix += item.get_width() + int(0.008 * _SW)
                    else:
                        item.draw_icon(ix, image_y,
                                       settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT,
                                       settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT)
                        ix += settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT + int(0.008 * _SW)
            else:
                if num == 1:
                    spacing = 0
                    ix = self.rect.centerx - widths[0] // 2
                else:
                    spacing = (max_w - widths[-1]) / (num - 1)
                    ix = self.rect.centerx - max_w // 2
                for i, (t, item) in enumerate(self.ordered_items):
                    xp = ix + i * spacing
                    if t == 'surface':
                        self.window.blit(item, (xp, image_y))
                    else:
                        item.draw_icon(xp, image_y,
                                       settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT,
                                       settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT)

        # After-images text
        if self.after_lines_surfaces:
            aty = image_y + self.content_height + self.drawable_bottom_spacing
            for i, line_surf in enumerate(self.after_lines_surfaces):
                ly = aty + i * self._line_h
                self.window.blit(line_surf,
                                 line_surf.get_rect(center=(self.rect.centerx, ly)))

        # Buttons
        for button in self.buttons:
            button.draw()

    # ── update ──────────────────────────────────────────────────────

    def update(self, events):
        if self.auto_close_delay is not None and self.auto_close_timer is not None:
            elapsed = pygame.time.get_ticks() - self.auto_close_timer
            if elapsed >= self.auto_close_delay:
                return 'auto_close'

        for button in self.buttons:
            button.update()

        # Ignore MOUSEBUTTONUP within 200ms of creation to prevent the
        # release from the click that opened the dialogue from triggering
        # a button immediately.
        if pygame.time.get_ticks() - self._created_at < 200:
            return None

        for event in events:
            if event.type == pygame.MOUSEBUTTONUP:
                for button in self.buttons:
                    if button.collide():
                        return button.text.lower()
        return None
