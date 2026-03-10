#!/usr/bin/env python3
"""Nepal Kings — launcher with startup resolution picker.

Run this instead of nepal_kings.py.  On first launch a small dialog
lets the user choose a resolution; the choice is saved to
``resolution.cfg`` so subsequent launches skip straight to the game.

To re-open the picker, delete ``resolution.cfg`` or press any key
while the splash/progress bar is visible (TODO: could add a menu
option later).
"""

import json
import os
import sys

import pygame

# ── Paths / Constants ──────────────────────────────────────────────
_DIR        = os.path.dirname(os.path.abspath(__file__))
_CFG_DIR    = os.path.join(os.path.expanduser('~'), '.nepalkings')
_CFG_FILE   = os.path.join(_CFG_DIR, 'resolution.json')

# Resolutions offered (width, height, label)  — 16∶9 aspect ratio
_RESOLUTIONS = [
    ( 854,  480,  '854 × 480    (FWVGA)'),
    (1024,  576, '1024 × 576    (PAL wide)'),
    (1280,  720, '1280 × 720    (HD)'),
    (1366,  768, '1366 × 768    (Laptop)'),
    (1600,  900, '1600 × 900    (HD+)'),
    (1920, 1080, '1920 × 1080  (Full HD)'),
    (2048, 1152, '2048 × 1152  (QWXGA)'),
    (2560, 1440, '2560 × 1440  (QHD)'),
    (3200, 1800, '3200 × 1800  (QHD+)'),
    (3840, 2160, '3840 × 2160  (4K UHD)'),
]

_DEFAULT_W, _DEFAULT_H = 1920, 1080

# ── Theme colours (match game palette) ─────────────────────────────
_BG          = (30, 28, 24)
_TITLE_CLR   = (250, 221, 0)
_TEXT_CLR     = (235, 225, 208)
_BTN_BG      = (50, 45, 35)
_BTN_BG_HOV  = (75, 65, 48)
_BTN_BG_SEL  = (100, 80, 40)
_BTN_BDR     = (120, 105, 75)
_BTN_BDR_HOV = (180, 160, 130)
_BTN_BDR_SEL = (250, 221, 0)
_HINT_CLR    = (140, 130, 110)
_CHECK_CLR   = (90, 200, 110)


# ── Persistence helpers ────────────────────────────────────────────
def _load_saved():
    """Return (w, h) from config file, or None."""
    try:
        with open(_CFG_FILE, 'r') as f:
            data = json.load(f)
        w, h = int(data['width']), int(data['height'])
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return None


def _save_choice(w, h):
    """Persist the chosen resolution."""
    try:
        os.makedirs(_CFG_DIR, exist_ok=True)
        with open(_CFG_FILE, 'w') as f:
            json.dump({'width': w, 'height': h}, f)
    except Exception:
        pass


# ── Resolution Picker UI ──────────────────────────────────────────
def _pick_resolution():
    """Show a small themed dialog and return (width, height)."""
    pygame.init()

    # Detect native desktop resolution
    info = pygame.display.Info()
    native_w, native_h = info.current_w, info.current_h

    # Filter resolutions that fit the display
    choices = [(w, h, lbl) for w, h, lbl in _RESOLUTIONS
               if w <= native_w and h <= native_h]
    if not choices:
        choices = [(_DEFAULT_W, _DEFAULT_H, f'{_DEFAULT_W} × {_DEFAULT_H}')]

    # ── Picker window geometry ──
    pw, ph = 440, 120 + len(choices) * 56 + 80
    win = pygame.display.set_mode((pw, ph))
    pygame.display.set_caption('Nepal Kings — Resolution')

    # Fonts (system fallback — game font needs config which we haven't imported)
    title_font = pygame.font.SysFont('Arial', 28, bold=True)
    btn_font   = pygame.font.SysFont('Arial', 22)
    hint_font  = pygame.font.SysFont('Arial', 16)

    # Pre-select the current native or saved resolution
    saved = _load_saved()
    selected_idx = None
    for i, (w, h, _) in enumerate(choices):
        if saved and w == saved[0] and h == saved[1]:
            selected_idx = i
            break
    if selected_idx is None:
        # Default to largest that fits
        selected_idx = len(choices) - 1

    btn_h = 44
    gap   = 12
    start_y = 72

    clock = pygame.time.Clock()
    running = True
    confirmed = False

    while running:
        win.fill(_BG)

        # Title
        title_surf = title_font.render('Select Resolution', True, _TITLE_CLR)
        win.blit(title_surf, ((pw - title_surf.get_width()) // 2, 22))

        mx, my = pygame.mouse.get_pos()

        # Resolution buttons
        btn_rects = []
        for i, (w, h, label) in enumerate(choices):
            r = pygame.Rect(40, start_y + i * (btn_h + gap), pw - 80, btn_h)
            btn_rects.append(r)

            is_hover = r.collidepoint(mx, my)
            is_sel   = (i == selected_idx)

            if is_sel:
                bg = _BTN_BG_SEL
                bdr = _BTN_BDR_SEL
            elif is_hover:
                bg = _BTN_BG_HOV
                bdr = _BTN_BDR_HOV
            else:
                bg = _BTN_BG
                bdr = _BTN_BDR

            pygame.draw.rect(win, bg, r, border_radius=8)
            pygame.draw.rect(win, bdr, r, 2, border_radius=8)

            # Label
            txt = btn_font.render(label, True, _TEXT_CLR)
            win.blit(txt, (r.x + 18, r.y + (r.h - txt.get_height()) // 2))

            # Native indicator
            if w == native_w and h == native_h:
                tag = hint_font.render('native', True, _CHECK_CLR)
                win.blit(tag, (r.right - tag.get_width() - 14,
                               r.y + (r.h - tag.get_height()) // 2))
            elif is_sel:
                dot = btn_font.render('●', True, _TITLE_CLR)
                win.blit(dot, (r.right - dot.get_width() - 14,
                               r.y + (r.h - dot.get_height()) // 2))

        # "Start Game" button
        start_y_btn = start_y + len(choices) * (btn_h + gap) + 16
        start_rect = pygame.Rect(pw // 2 - 80, start_y_btn, 160, 44)
        start_hover = start_rect.collidepoint(mx, my)
        sbg = _BTN_BG_HOV if start_hover else _BTN_BG
        sbdr = _TITLE_CLR if start_hover else _BTN_BDR_HOV
        pygame.draw.rect(win, sbg, start_rect, border_radius=8)
        pygame.draw.rect(win, sbdr, start_rect, 2, border_radius=8)
        start_txt = btn_font.render('Start Game', True, _TITLE_CLR)
        win.blit(start_txt, (start_rect.x + (start_rect.w - start_txt.get_width()) // 2,
                             start_rect.y + (start_rect.h - start_txt.get_height()) // 2))

        # Hint
        hint = hint_font.render('ESC = quit  •  click to select, then Start', True, _HINT_CLR)
        win.blit(hint, ((pw - hint.get_width()) // 2, ph - 28))

        pygame.display.flip()
        clock.tick(30)

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit(0)
                elif ev.key == pygame.K_RETURN:
                    confirmed = True
                    running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for i, r in enumerate(btn_rects):
                    if r.collidepoint(ev.pos):
                        selected_idx = i
                        break
                if start_rect.collidepoint(ev.pos):
                    confirmed = True
                    running = False

    chosen_w, chosen_h = choices[selected_idx][0], choices[selected_idx][1]

    # Destroy the picker window (the game will create its own)
    pygame.display.quit()

    return chosen_w, chosen_h


# ── Entry Point ────────────────────────────────────────────────────
def main():
    force_picker = '--pick-resolution' in sys.argv or '-r' in sys.argv

    saved = _load_saved()
    if saved and not force_picker:
        w, h = saved
    else:
        w, h = _pick_resolution()
        _save_choice(w, h)

    # Set env vars BEFORE importing any config/game modules
    os.environ['NK_SCREEN_WIDTH']  = str(w)
    os.environ['NK_SCREEN_HEIGHT'] = str(h)

    # Now import the game — all config constants are derived from env vars
    from nepal_kings import Client
    client = Client()
    client.run()


if __name__ == '__main__':
    main()
