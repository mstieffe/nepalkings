# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared drawing helpers + palette for the conquer/defence config screens.

Both ``conquer_screen.py`` and ``defence_screen.py`` render the same config
board (panel box, section cards, remove-× buttons, close ×). The helpers and
colors here keep the two screens visually identical; the screens keep thin
wrapper methods so tests can monkeypatch them by name.
"""

import pygame

from config import settings
from game.components.dialogue_box import DialogueBox
from utils import sound

# ── Shared palette ──────────────────────────────────────────────────
X_BTN_BG            = (120, 40, 40)
X_BTN_BG_HOVER      = (180, 60, 60)
X_BTN_BORDER        = (160, 80, 80)
X_BTN_BORDER_HOVER  = (220, 120, 120)
X_BTN_TEXT          = (200, 180, 180)
X_BTN_TEXT_HOVER    = (255, 255, 255)

SECTION_BG          = (28, 24, 20, 120)
SECTION_BORDER      = (110, 95, 72)
SECTION_TITLE       = (200, 185, 150)
SECTION_DESC        = (160, 145, 120)

POPUP_BG            = (26, 22, 16, 242)
POPUP_BORDER        = (210, 185, 115)
POPUP_TITLE         = (235, 215, 145)
POPUP_BODY          = (195, 180, 140)

DIVIDER             = (90, 80, 60)
EMPTY_SLOT_BG       = (50, 45, 35, 180)
EMPTY_SLOT_BORDER   = (100, 90, 70)
ERROR_TEXT          = (200, 80, 80)
EDIT_GLOW           = (255, 255, 200, 40)
SLOT_HOVER_GLOW     = (255, 255, 200, 35)


def draw_panel(window, rect, corner_r=None):
    """Draw the translucent outer content box."""
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


def mobile_hit_rect(rect, min_w=None, min_h=None):
    """Return a touch-friendly hit rect while leaving visuals unchanged."""
    if rect is None or settings.TOUCH_TARGET_MIN <= 0:
        return rect
    min_w = min_w or settings.TOUCH_TARGET_MIN
    min_h = min_h or settings.TOUCH_TARGET_MIN
    grow_w = max(0, min_w - rect.w)
    grow_h = max(0, min_h - rect.h)
    hit = rect.inflate(grow_w, grow_h)
    hit.clamp_ip(pygame.Rect(0, 0, settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    return hit


def mobile_collide(rect, pos, min_w=None, min_h=None):
    hit = mobile_hit_rect(rect, min_w=min_w, min_h=min_h)
    return bool(hit and hit.collidepoint(pos))


def draw_remove_x(window, rect, hovered):
    """Draw the small crimson remove-× button used on figures/moves/spells."""
    bg = X_BTN_BG_HOVER if hovered else X_BTN_BG
    bdr = X_BTN_BORDER_HOVER if hovered else X_BTN_BORDER
    tc = X_BTN_TEXT_HOVER if hovered else X_BTN_TEXT
    pygame.draw.rect(window, bg, rect, border_radius=3)
    pygame.draw.rect(window, bdr, rect, 1, border_radius=3)
    xf = settings.get_font(max(int(rect.h * 1.3), 8), bold=True)
    xt = xf.render('×', True, tc)
    window.blit(xt, xt.get_rect(center=rect.center))


def draw_close_x_button(window, rect):
    """Draw the top-right box close button."""
    if not rect:
        return
    hovered = rect.collidepoint(pygame.mouse.get_pos())

    bg_clr = (80, 50, 25, 220) if hovered else (55, 35, 18, 200)
    border_clr = (180, 160, 120) if hovered else (120, 100, 70)
    txt_clr = (255, 240, 200) if hovered else (200, 180, 140)

    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, bg_clr, surf.get_rect(), border_radius=4)
    pygame.draw.rect(surf, border_clr, surf.get_rect(), 1, border_radius=4)
    window.blit(surf, rect.topleft)

    xfont = settings.get_font(int(settings.FONT_SIZE * 0.85), bold=True)
    txt = xfont.render('×', True, txt_clr)
    window.blit(txt, txt.get_rect(center=rect.center))


def draw_section_panel(window, rect, title, *, title_font, desc_font,
                       edit_icon=None, description=None,
                       icon_rect=None, title_pos=None):
    """Draw a quiet section card with one title row and optional edit icon."""
    if not rect:
        return
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, SECTION_BG, surf.get_rect(), border_radius=5)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, SECTION_BORDER, rect, 1, border_radius=5)

    x = title_pos[0] if title_pos else rect.x + int(0.010 * settings.SCREEN_WIDTH)
    y = title_pos[1] if title_pos else rect.y + int(0.010 * settings.SCREEN_HEIGHT)
    title_surf = title_font.render(title, True, SECTION_TITLE)
    window.blit(title_surf, (x, y))
    if description:
        desc_surf = desc_font.render(description, True, SECTION_DESC)
        window.blit(desc_surf, (x, y + title_surf.get_height() + 2))

    if icon_rect and edit_icon:
        if icon_rect.collidepoint(pygame.mouse.get_pos()):
            glow = pygame.Surface((icon_rect.w + 4, icon_rect.h + 4), pygame.SRCALPHA)
            glow.fill(EDIT_GLOW)
            window.blit(glow, (icon_rect.x - 2, icon_rect.y - 2))
        window.blit(edit_icon, icon_rect.topleft)


def draw_empty_slot(window, rect):
    """Draw the dashed-looking empty slot square used for spell slots."""
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, EMPTY_SLOT_BG, surf.get_rect(), border_radius=6)
    pygame.draw.rect(surf, EMPTY_SLOT_BORDER, surf.get_rect(), 1, border_radius=6)
    window.blit(surf, rect.topleft)


def fit_text(text, font, max_width):
    """Trim text with an ellipsis so captions stay inside their panel."""
    text = str(text)
    if max_width <= 0:
        return ''
    if font.size(text)[0] <= max_width:
        return text
    ellipsis = '…'
    if font.size(ellipsis)[0] > max_width:
        return ''
    lo = 0
    hi = len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.size(text[:mid] + ellipsis)[0] <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ellipsis


def draw_hover_tooltip(window, anchor_rect, text, font):
    """Draw a one-line tooltip below an anchor rect (desktop hover hint)."""
    pad_x = 6
    pad_y = 3
    surf = font.render(text, True, POPUP_TITLE)
    w = surf.get_width() + 2 * pad_x
    h = surf.get_height() + 2 * pad_y
    win_w, win_h = window.get_size()
    x = max(4, min(anchor_rect.left, win_w - w - 4))
    y = anchor_rect.bottom + 4
    if y + h > win_h - 4:
        y = anchor_rect.top - h - 4
    rect = pygame.Rect(int(x), int(y), int(w), int(h))
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(bg, POPUP_BG, bg.get_rect(), border_radius=4)
    window.blit(bg, rect.topleft)
    pygame.draw.rect(window, POPUP_BORDER, rect, 1, border_radius=4)
    window.blit(surf, (rect.x + pad_x, rect.y + pad_y))


def open_dialogue(screen, message, actions, title, icon=None):
    """Open a DialogueBox on a screen and play its title-matched stinger."""
    kwargs = {'actions': actions, 'title': title}
    if icon:
        kwargs['icon'] = icon
    screen.dialogue_box = DialogueBox(screen.window, message, **kwargs)
    sound.play_for_dialogue(title)
