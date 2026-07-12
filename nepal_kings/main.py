#!/usr/bin/env python3
# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
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

# ── Logging (initialise before any other module) ──
from log import setup as _setup_logging
_CFG_DIR    = os.path.join(os.path.expanduser('~'), '.nepalkings')
_setup_logging(
    debug=os.getenv('NK_DEBUG', '').lower() in ('1', 'true'),
    log_dir=_CFG_DIR,          # logs land in ~/.nepalkings/
)

# Raise per-process file-descriptor limit so heavy image/font loading
# during init doesn't hit macOS's default 256-fd ceiling.
if sys.platform != "emscripten":
    try:
        import resource
        _soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if _soft < 4096:
            resource.setrlimit(resource.RLIMIT_NOFILE, (min(4096, _hard), _hard))
    except Exception:
        pass

import pygame

# ── Paths / Constants ──────────────────────────────────────────────
_DIR        = os.path.dirname(os.path.abspath(__file__))
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
_WEB_ASPECT_RATIO = 16.0 / 9.0
_MOBILE_WEB_RESOLUTIONS = [
    (1280, 720, '1.4'),
    (1024, 576, '1.5'),
    ( 854, 480, '1.6'),
]
_DESKTOP_WEB_RESOLUTIONS = [
    (1920, 1080),
    (1600, 900),
    (1366, 768),
    (1280, 720),
    (1024, 576),
    ( 854, 480),
]

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


_DEFAULT_SERVER_URL = 'https://nepalkings.pythonanywhere.com'

_SERVER_PRESETS = [
    ('http://localhost:5000',                     'Local (dev)'),
    ('https://nepalkings.pythonanywhere.com',     'PythonAnywhere'),
]


# ── Web viewport helpers ───────────────────────────────────────────
def _fit_16_9_rect(viewport_w, viewport_h):
    """Return the largest 16:9 CSS rectangle inside the browser viewport."""
    viewport_w = max(1, int(viewport_w))
    viewport_h = max(1, int(viewport_h))
    if viewport_w / viewport_h > _WEB_ASPECT_RATIO:
        return int(viewport_h * _WEB_ASPECT_RATIO), viewport_h
    return viewport_w, int(viewport_w / _WEB_ASPECT_RATIO)


def _select_web_resolution(viewport_w, viewport_h, mobile=False):
    """Return (canvas_w, canvas_h, ui_scale, fit_w, fit_h) for web startup."""
    fit_w, fit_h = _fit_16_9_rect(viewport_w, viewport_h)
    if mobile:
        for resolution_w, resolution_h, ui_scale in _MOBILE_WEB_RESOLUTIONS:
            if resolution_w <= fit_w and resolution_h <= fit_h:
                return resolution_w, resolution_h, ui_scale, fit_w, fit_h
        resolution_w, resolution_h, ui_scale = _MOBILE_WEB_RESOLUTIONS[-1]
        return resolution_w, resolution_h, ui_scale, fit_w, fit_h

    for resolution_w, resolution_h in _DESKTOP_WEB_RESOLUTIONS:
        if resolution_w <= fit_w and resolution_h <= fit_h:
            return resolution_w, resolution_h, None, fit_w, fit_h
    resolution_w, resolution_h = _DESKTOP_WEB_RESOLUTIONS[-1]
    return resolution_w, resolution_h, None, fit_w, fit_h


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


def _load_server_url():
    """Return the saved server URL, or None."""
    try:
        with open(_CFG_FILE, 'r') as f:
            data = json.load(f)
        url = data.get('server_url', '').strip()
        if url:
            return url
    except Exception:
        pass
    return None


def _save_choice(w, h, server_url=None):
    """Persist the chosen resolution and server URL."""
    try:
        os.makedirs(_CFG_DIR, exist_ok=True)
        # Merge with existing config to preserve other settings
        existing = {}
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, 'r') as f:
                existing = json.load(f)
        existing['width'] = w
        existing['height'] = h
        if server_url is not None:
            existing['server_url'] = server_url
        with open(_CFG_FILE, 'w') as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass


# ── Resolution & Server Picker UI ─────────────────────────────────
def _pick_resolution():
    """Show a themed dialog for resolution + server selection.

    Returns (width, height, server_url).
    """
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
    pw = 480
    btn_h = 44
    svr_btn_h = 58          # taller to fit label + URL
    gap   = 12
    adv_row_h = 26          # collapsed "Advanced settings" toggle row
    res_start_y = 72

    # The server presets are a developer concern, so they stay collapsed
    # behind an "Advanced settings" toggle for regular players.
    advanced_open = False

    def _window_height(open_advanced):
        # Trace exact same layout as the render loop:
        # res section label + separator = 32px
        res_btn_start = res_start_y + 32
        res_btns_bottom = res_btn_start + len(choices) * (btn_h + gap)
        y = res_btns_bottom + 10 + adv_row_h
        if open_advanced:
            y += 16 + 32 + len(_SERVER_PRESETS) * (svr_btn_h + gap)
        start_y = y + 16
        # Start button (44) + gap (16) + hint text (~18) + bottom margin (14)
        return start_y + 44 + 16 + 18 + 14

    win = pygame.display.set_mode((pw, _window_height(advanced_open)))
    pygame.display.set_caption('Nepal Kings — Settings')

    # Fonts
    title_font   = pygame.font.SysFont('Arial', 28, bold=True)
    section_font = pygame.font.SysFont('Arial', 20, bold=True)
    btn_font     = pygame.font.SysFont('Arial', 22)
    hint_font    = pygame.font.SysFont('Arial', 16)

    # Pre-select saved resolution
    saved = _load_saved()
    selected_idx = None
    for i, (w, h, _) in enumerate(choices):
        if saved and w == saved[0] and h == saved[1]:
            selected_idx = i
            break
    if selected_idx is None:
        selected_idx = len(choices) - 1

    # Pre-select saved server
    saved_url = _load_server_url() or _DEFAULT_SERVER_URL
    server_idx = None
    for i, (url, _) in enumerate(_SERVER_PRESETS):
        if saved_url.rstrip('/') == url.rstrip('/'):
            server_idx = i
            break
    if server_idx is None:
        # Default to the live server so players never land on localhost.
        server_idx = next(i for i, (url, _) in enumerate(_SERVER_PRESETS)
                          if url == _DEFAULT_SERVER_URL)
    # A non-default saved server means a dev is switching back and forth —
    # keep the section visible for them.
    if saved_url.rstrip('/') != _DEFAULT_SERVER_URL.rstrip('/'):
        advanced_open = True
        win = pygame.display.set_mode((pw, _window_height(advanced_open)))

    clock = pygame.time.Clock()
    running = True

    while running:
        win.fill(_BG)
        mx, my = pygame.mouse.get_pos()

        # ── Title ──
        title_surf = title_font.render('Nepal Kings', True, _TITLE_CLR)
        win.blit(title_surf, ((pw - title_surf.get_width()) // 2, 18))

        # ── Resolution section ──
        sec_lbl = section_font.render('Resolution', True, _TEXT_CLR)
        win.blit(sec_lbl, (40, res_start_y - 2))
        # thin separator line
        pygame.draw.line(win, _BTN_BDR, (40, res_start_y + 24), (pw - 40, res_start_y + 24))
        res_btn_start = res_start_y + 32

        btn_rects = []
        for i, (w, h, label) in enumerate(choices):
            r = pygame.Rect(40, res_btn_start + i * (btn_h + gap), pw - 80, btn_h)
            btn_rects.append(r)
            is_hover = r.collidepoint(mx, my)
            is_sel   = (i == selected_idx)
            bg  = _BTN_BG_SEL if is_sel else (_BTN_BG_HOV if is_hover else _BTN_BG)
            bdr = _BTN_BDR_SEL if is_sel else (_BTN_BDR_HOV if is_hover else _BTN_BDR)
            pygame.draw.rect(win, bg, r, border_radius=8)
            pygame.draw.rect(win, bdr, r, 2, border_radius=8)
            txt = btn_font.render(label, True, _TEXT_CLR)
            win.blit(txt, (r.x + 18, r.y + (r.h - txt.get_height()) // 2))
            if w == native_w and h == native_h:
                tag = hint_font.render('native', True, _CHECK_CLR)
                win.blit(tag, (r.right - tag.get_width() - 14,
                               r.y + (r.h - tag.get_height()) // 2))
            elif is_sel:
                dot = btn_font.render('●', True, _TITLE_CLR)
                win.blit(dot, (r.right - dot.get_width() - 14,
                               r.y + (r.h - dot.get_height()) // 2))

        # ── Advanced settings toggle (server presets live behind it) ──
        adv_y = res_btn_start + len(choices) * (btn_h + gap) + 10
        adv_lbl = hint_font.render('Advanced settings', True, _HINT_CLR)
        tri_sz = 8
        adv_rect = pygame.Rect(40, adv_y, tri_sz + 10 + adv_lbl.get_width() + 8, adv_row_h)
        adv_clr = _TEXT_CLR if (advanced_open or adv_rect.collidepoint(mx, my)) else _HINT_CLR
        adv_lbl = hint_font.render('Advanced settings', True, adv_clr)
        tri_cy = adv_rect.y + adv_rect.h // 2
        if advanced_open:
            tri = [(40, tri_cy - 2), (40 + tri_sz, tri_cy - 2),
                   (40 + tri_sz // 2, tri_cy + tri_sz // 2 + 2)]
        else:
            tri = [(41, tri_cy - tri_sz // 2), (41, tri_cy + tri_sz // 2),
                   (41 + tri_sz // 2 + 2, tri_cy)]
        pygame.draw.polygon(win, adv_clr, tri)
        win.blit(adv_lbl, (40 + tri_sz + 10,
                           adv_rect.y + (adv_rect.h - adv_lbl.get_height()) // 2))

        svr_rects = []
        after_adv_y = adv_rect.bottom
        if advanced_open:
            svr_y = after_adv_y + 16
            sec_lbl2 = section_font.render('Server', True, _TEXT_CLR)
            win.blit(sec_lbl2, (40, svr_y))
            pygame.draw.line(win, _BTN_BDR, (40, svr_y + 24), (pw - 40, svr_y + 24))
            svr_btn_start = svr_y + 32

            for i, (url, label) in enumerate(_SERVER_PRESETS):
                r = pygame.Rect(40, svr_btn_start + i * (svr_btn_h + gap), pw - 80, svr_btn_h)
                svr_rects.append(r)
                is_hover = r.collidepoint(mx, my)
                is_sel   = (i == server_idx)
                bg  = _BTN_BG_SEL if is_sel else (_BTN_BG_HOV if is_hover else _BTN_BG)
                bdr = _BTN_BDR_SEL if is_sel else (_BTN_BDR_HOV if is_hover else _BTN_BDR)
                pygame.draw.rect(win, bg, r, border_radius=8)
                pygame.draw.rect(win, bdr, r, 2, border_radius=8)
                txt = btn_font.render(label, True, _TEXT_CLR)
                win.blit(txt, (r.x + 18, r.y + 6))
                # Show URL underneath the label
                url_txt = hint_font.render(url, True, _HINT_CLR)
                win.blit(url_txt, (r.x + 18, r.y + 6 + txt.get_height() + 2))
                if is_sel:
                    dot = btn_font.render('●', True, _TITLE_CLR)
                    win.blit(dot, (r.right - dot.get_width() - 14,
                                   r.y + (r.h - dot.get_height()) // 2))
            after_adv_y = svr_btn_start + len(_SERVER_PRESETS) * (svr_btn_h + gap)

        # ── "Start Game" button ──
        start_y_btn = after_adv_y + 16
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
        hint = hint_font.render('ESC = quit', True, _HINT_CLR)
        win.blit(hint, ((pw - hint.get_width()) // 2,
                        start_rect.bottom + 12))

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
                    running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for i, r in enumerate(btn_rects):
                    if r.collidepoint(ev.pos):
                        selected_idx = i
                        break
                for i, r in enumerate(svr_rects):
                    if r.collidepoint(ev.pos):
                        server_idx = i
                        break
                if adv_rect.collidepoint(ev.pos):
                    advanced_open = not advanced_open
                    win = pygame.display.set_mode((pw, _window_height(advanced_open)))
                elif start_rect.collidepoint(ev.pos):
                    running = False

    chosen_w, chosen_h = choices[selected_idx][0], choices[selected_idx][1]
    chosen_url = _SERVER_PRESETS[server_idx][0]

    pygame.display.quit()
    return chosen_w, chosen_h, chosen_url


# ── Entry Point ────────────────────────────────────────────────────
def main():
    force_picker = ('--pick-resolution' in sys.argv or '-r' in sys.argv
                    or '--settings' in sys.argv or '-s' in sys.argv)

    # Sound preference (reads ~/.nepalkings/resolution.json)
    from utils import sound as _sound
    _sound.init()

    saved = _load_saved()
    if saved and not force_picker:
        w, h = saved
    else:
        w, h, picked_url = _pick_resolution()
        _save_choice(w, h, server_url=picked_url)

    # Server URL: CLI flag > env var > config file > default
    server_url = None
    for i, arg in enumerate(sys.argv):
        if arg == '--server-url' and i + 1 < len(sys.argv):
            server_url = sys.argv[i + 1]
            break
    if not server_url:
        server_url = os.environ.get('SERVER_URL')
    if not server_url:
        server_url = _load_server_url()
    if not server_url:
        server_url = _DEFAULT_SERVER_URL

    # Persist the server URL so it's remembered
    _save_choice(w, h, server_url=server_url)

    # Set env vars BEFORE importing any config/game modules
    os.environ['NK_SCREEN_WIDTH']  = str(w)
    os.environ['NK_SCREEN_HEIGHT'] = str(h)
    os.environ['SERVER_URL'] = server_url

    # Ensure cwd is the nepal_kings directory so relative image paths resolve
    # (also handles PyInstaller _MEIPASS for bundled apps)
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        os.chdir(_sys._MEIPASS)
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Now import the game — all config constants are derived from env vars
    import asyncio
    from nepal_kings import Client
    client = Client()
    asyncio.run(client.run())


if __name__ == '__main__':
    if sys.platform == "emscripten":
        # ── Web / pygbag mode ──────────────────────────────────────
        import asyncio

        # ── Dynamic resolution based on viewport ──────────────────
        _w, _h = 1280, 720          # safe defaults
        try:
            import embed as _embed
            # Use visualViewport (accurate on mobile) with fallback
            _vp = _embed.js("""(function(){
                var vv=window.visualViewport;
                return {w: vv? vv.width : window.innerWidth,
                        h: vv? vv.height: window.innerHeight,
                        dpr: window.devicePixelRatio||1,
                        mobile: /iPhone|iPod|Android|webOS|BlackBerry|IEMobile|Opera Mini/i
                                .test(navigator.userAgent)
                                || (navigator.maxTouchPoints>0
                                    && Math.min(window.innerWidth,window.innerHeight)<500)
                       }
            })()""")
            _vw, _vh = int(_vp['w']), int(_vp['h'])
            _mobile = bool(_vp.get('mobile', False))
            _w, _h, _ui_scale, _fw, _fh = _select_web_resolution(_vw, _vh, _mobile)
            if _mobile:
                os.environ['NK_IS_MOBILE'] = '1'
                if _ui_scale:
                    os.environ['NK_UI_SCALE'] = _ui_scale
        except Exception:
            pass

        try:
            _web_cfg = _embed.js("""(function(){
                var p=new URLSearchParams(window.location.search);
                return {
                    perf: p.get('nk_perf')==='1'
                        || window.localStorage.getItem('NK_PERF')==='1',
                    fixture: p.get('nk_perf_fixture')
                        || window.localStorage.getItem('NK_PERF_FIXTURE')
                        || '',
                    server_url: p.get('server_url')
                        || window.localStorage.getItem('NK_SERVER_URL')
                        || ''
                };
            })()""")
            if _web_cfg.get('server_url'):
                os.environ['SERVER_URL'] = str(_web_cfg.get('server_url')).rstrip('/')
            if _web_cfg.get('perf'):
                os.environ['NK_PERF'] = '1'
            if _web_cfg.get('fixture'):
                os.environ['NK_PERF_FIXTURE'] = str(_web_cfg.get('fixture'))
        except Exception:
            pass
        os.environ['NK_SCREEN_WIDTH']  = str(_w)
        os.environ['NK_SCREEN_HEIGHT'] = str(_h)
        os.environ.setdefault('SERVER_URL', _DEFAULT_SERVER_URL)
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

        # ── Canvas CSS: maintain 16:9 aspect ratio + centre ───────
        # (main styling is in web/index.html; this is a safety net)
        try:
            _embed.js("""(function(){
                var m=document.querySelector('meta[name=viewport]');
                if(m) m.content='width=device-width,initial-scale=1,'
                    +'maximum-scale=1,user-scalable=no,viewport-fit=cover';
                window.addEventListener('resize',function(){
                    if(window.window_resize) window.window_resize();
                });
                return 1;
            })()""")
        except Exception:
            pass

        # ── Mobile-keyboard support ───────────────────────────────
        from utils.web_keyboard import init as _init_kb
        _init_kb()

        # ── Haptic feedback support (Vibration API) ───────────────
        from utils import haptics as _haptics
        _haptics.init()

        # ── Sound effects ──────────────────────────────────────────
        from utils import sound as _sound
        _sound.init()

        from nepal_kings import Client

        def _web_show_crash(exc):
            """Paint a traceback on the canvas so a web crash is visible
            instead of a dead black screen (pygbag has no crash.log)."""
            import traceback as _tb
            text = ''.join(_tb.format_exception(type(exc), exc, exc.__traceback__))
            print('--- nepal_kings web crash ---')
            print(text)
            # Make sure the branded HTML loader is gone so the error shows.
            try:
                import embed as _embed
                _embed.js("var l=document.getElementById('nk-loader');"
                          "if(l)l.style.display='none';")
            except Exception:
                pass
            try:
                surf = pygame.display.get_surface()
                if surf is None:
                    surf = pygame.display.set_mode((960, 600))
                surf.fill((24, 16, 16))
                font = pygame.font.SysFont('monospace', 16)
                title = pygame.font.SysFont('Arial', 26, bold=True).render(
                    'Nepal Kings hit an error', True, (255, 120, 120))
                surf.blit(title, (24, 20))
                y = 64
                for line in text.replace('\t', '    ').splitlines():
                    surf.blit(font.render(line[:160], True, (235, 210, 210)), (24, y))
                    y += 19
                pygame.display.flip()
            except Exception:
                pass

        async def _web_main():
            try:
                client = Client()
                await client.run()
            except Exception as exc:        # noqa: BLE001 — last-resort UI
                _web_show_crash(exc)
                # Keep the page responsive so the error stays on screen.
                while True:
                    pygame.event.pump()
                    await asyncio.sleep(0.2)

        asyncio.run(_web_main())
    else:
        # ── Desktop mode ───────────────────────────────────────────
        import traceback as _tb
        _log = os.path.join(os.path.expanduser('~'), '.nepalkings', 'crash.log')
        try:
            main()
        except Exception:
            os.makedirs(os.path.dirname(_log), exist_ok=True)
            with open(_log, 'a') as _f:
                _f.write('\n--- crash ' + __import__('datetime').datetime.now().isoformat() + ' ---\n')
                _tb.print_exc(file=_f)
            raise
