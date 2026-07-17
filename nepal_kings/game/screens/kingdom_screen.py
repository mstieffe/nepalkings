# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom screen — interactive hex map with land details."""

import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import (
    MenuScreenMixin,
    menu_chrome_safe_top,
    menu_chrome_safe_width,
)
from game.components.hex_map import HexMap
from game.components.land_detail_box import LandDetailBox
from game.components.leaderboard_panel import LeaderboardPanel
from game.components.floating_text import FloatingText, FloatingTextLayer
from game.components.conquer_effects import ConquerEffectsLayer
from game.components.loading_indicator import draw_loading_indicator
from game.components import sigil_cosmetics
from config import settings
from utils import http_compat as requests
from utils import sound
from utils.background_poller import BackgroundPoller
import logging

logger = logging.getLogger('nk.screens.kingdom')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
_MAP_RETRY_INITIAL_MS = 10_000
_MAP_RETRY_MAX_MS = 60_000
_MAP_CONNECT_TIMEOUT_SECONDS = 10
_MAP_READ_TIMEOUT_SECONDS = 75

# ── Overall box ─────────────────────────────────────────────────────
_BOX_PAD    = int(0.020 * _SH)
_BOX_X      = int(0.04 * _SW)
_BOX_Y      = menu_chrome_safe_top(int(0.10 * _SH))
_BOX_W      = menu_chrome_safe_width(_BOX_X, int(0.87 * _SW))
_BOX_BOTTOM = int(0.92 * _SH)
_BOX_H      = _BOX_BOTTOM - _BOX_Y

# Player-facing map layers.  Ownership and vulnerability remain part of the
# renderer for compatibility/testing, but the kingdom screen deliberately
# exposes only the two useful everyday views.
_MAP_MODES = (
    ('terrain',    'Terrain'),
    ('gold',       'Gold'),
)


def _draw_panel(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


def _compute_kingdom_layout(activity_open=True):
    """Return non-overlapping layout rects for the kingdom dashboard."""
    box = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
    pad = _BOX_PAD
    gap = settings.KINGDOM_PANEL_GAP
    mobile_ui = settings.TOUCH_TARGET_MIN > 0
    portrait_ui = mobile_ui and _SH > _SW
    header_h = settings.KINGDOM_HEADER_H
    if portrait_ui:
        header_h = max(header_h, int(0.16 * _SH))
    header = pygame.Rect(
        box.x + pad,
        box.y + pad,
        box.w - 2 * pad,
        header_h,
    )

    content_top = header.bottom + int(0.008 * _SH)
    content_bottom = box.bottom - pad
    content_h = max(1, content_bottom - content_top)
    activity_w = settings.KINGDOM_ACTIVITY_W
    if mobile_ui:
        # On phones the map owns the content area.  Activity becomes a
        # temporary drawer over the right side instead of permanently taking
        # almost a quarter of the screen.
        activity_w = min(int(0.48 * _SW), box.w - 2 * pad)
        activity = pygame.Rect(
            box.right - pad - activity_w,
            content_top,
            activity_w,
            content_h,
        )
        map_right = box.right - pad
    else:
        activity = pygame.Rect(
            box.right - pad - activity_w,
            content_top,
            activity_w,
            content_h,
        )
        map_right = (activity.x - gap
                     if activity_open else box.right - pad)
    map_frame = pygame.Rect(
        box.x + pad,
        content_top,
        map_right - (box.x + pad),
        content_h,
    )
    map_viewport = pygame.Rect(
        map_frame.x + settings.KINGDOM_MAP_FRAME_PAD,
        map_frame.y + settings.KINGDOM_MAP_FRAME_PAD,
        map_frame.w - 2 * settings.KINGDOM_MAP_FRAME_PAD,
        map_frame.h - 2 * settings.KINGDOM_MAP_FRAME_PAD,
    )
    _xsz = max(
        int(0.028 * _SH),
        settings.TOUCH_COMPACT_MIN if mobile_ui else 0,
    )
    close = pygame.Rect(
        header.right - _xsz,
        header.y,
        _xsz,
        _xsz,
    )
    return {
        'box': box,
        'header': header,
        'map_frame': map_frame,
        'map_viewport': map_viewport,
        'activity': activity,
        'close': close,
    }


class KingdomScreen(MenuScreenMixin, Screen):
    """Kingdom screen with hex-map, minimap, land detail box, and nav controls."""

    # Defaults keep lightweight ``__new__`` test doubles and older saved
    # screen objects compatible with the responsive fields introduced here.
    _mobile_ui = settings.TOUCH_TARGET_MIN > 0
    _activity_open = False
    _layers_open = False
    _activity_panel_toggle_rect = None
    _activity_tab_hit_rects = {}
    _mark_read_hit_rect = None
    _new_msg_hit_rect = None
    _map_control_press = None

    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── State ───────────────────────────────────────────────────
        self._hex_map = None          # built on first enter
        self._kingdom_overview_dialogue = None  # first-open teaching window
        self._kingdom_management_dialogue = None
        self._kingdom_management_intro_step_id = None
        self._detail_box = None       # LandDetailBox (modal)
        self._map_data = None         # raw server response
        self._cooldown = 0            # conquer cooldown seconds
        self._recommended_tutorial_land_id = None
        self._loading = False
        self._loading_started_at_ms = 0
        self._loading_message = 'Loading kingdom map...'
        self._error = None
        self._retry_rect = None
        self._map_retry_delay_ms = _MAP_RETRY_INITIAL_MS
        self._next_map_retry_at_ms = 0
        self._last_map_updated_at_ms = 0

        # ── Attack notifications ────────────────────────────────────
        self._notifications = []      # unseen attack notifications
        self._attack_history = []     # recent attack history for this user
        self._messages = []           # legacy flat list (kept for tests / fallback)
        self._conversations = []      # one row per conversation partner
        self._message_unread_count = 0
        self._activity_tab = 'alerts'
        self._mobile_ui = settings.TOUCH_TARGET_MIN > 0
        # The map is the primary kingdom-screen task on every form factor.
        # Activity stays one click away and advertises unread work via badges.
        self._activity_open = False
        self._layers_open = False
        self._activity_toggle_rect = None
        self._activity_panel_toggle_rect = None
        self._activity_close_rect = None
        self._activity_tab_hit_rects = {}
        self._mark_read_hit_rect = None
        self._new_msg_hit_rect = None
        self._layers_toggle_rect = None
        self._activity_tab_rects = {}
        self._activity_row_rects = []
        self._activity_scroll_offsets = {'alerts': 0, 'history': 0, 'messages': 0}
        self._activity_scrollbar_rect = None
        self._mark_read_rect = None
        self._mark_read_kind = None
        self._new_msg_rect = None     # "+ New message" button on Messages tab
        # Thread modal: opened conversation with full history + composer
        self._thread = None           # dict or None
        self._thread_scrollbar_rect = None
        self._thread_input_rect = None
        self._thread_send_rect = None
        self._thread_cancel_rect = None
        self._thread_close_rect = None
        # Recipient picker modal for "+ New message"
        self._new_msg_picker = None
        self._new_msg_picker_input_rect = None
        self._new_msg_picker_ok_rect = None
        self._new_msg_picker_cancel_rect = None
        self._new_msg_picker_close_rect = None
        # Back-compat shim: tests reference _message_compose; mirror thread state.
        self._message_compose = None
        self._message_input_rect = None
        self._message_send_rect = None
        self._message_cancel_rect = None

        # ── Layout ──────────────────────────────────────────────────
        self._layout = _compute_kingdom_layout(self._activity_open)
        self._box_rect = self._layout['box']
        self._header_rect = self._layout['header']
        self._map_frame_rect = self._layout['map_frame']
        self._map_viewport_rect = self._layout['map_viewport']
        self._activity_rect = self._layout['activity']

        # ── Title ───────────────────────────────────────────────────
        self._title_font = settings.get_font(settings.SUB_SCREEN_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Kingdom', True, settings.SUB_SCREEN_TITLE_CLR)
        self._title_y = self._header_rect.y

        # ── Fonts ───────────────────────────────────────────────────
        self._info_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE)
        self._nav_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE, bold=True)
        self._activity_title_font = settings.get_font(settings.FS_SMALL, bold=True)
        self._activity_font = settings.get_font(settings.FS_TINY)
        self._activity_small_font = settings.get_font(int(settings.FS_TINY * 0.86))

        # ── Navigation zoom buttons (inside map frame, bottom-left) ─
        btn_sz = max(
            settings.NAV_BTN_SIZE,
            settings.TOUCH_ICON_MIN if self._mobile_ui else 0,
        )
        margin = settings.NAV_BTN_MARGIN
        if self._mobile_ui:
            margin = max(margin, settings.TOUCH_TARGET_MIN - btn_sz)
        hit_inset = (max(0, settings.TOUCH_TARGET_MIN - btn_sz) // 2
                     if self._mobile_ui else 0)
        nav_by = (self._map_frame_rect.bottom
                  - settings.KINGDOM_MAP_FRAME_PAD - btn_sz - hit_inset)
        nav_x = (self._map_frame_rect.x
                 + settings.KINGDOM_MAP_FRAME_PAD + hit_inset)

        self._nav_rects = {
            'zoom_out': pygame.Rect(nav_x, nav_by, btn_sz, btn_sz),
            'recenter': pygame.Rect(nav_x + btn_sz + margin, nav_by, btn_sz, btn_sz),
            'zoom_in': pygame.Rect(nav_x + 2 * (btn_sz + margin), nav_by, btn_sz, btn_sz),
        }
        self._nav_hit_rects = {}
        self._nav_labels = {
            'zoom_in': '+',
            'zoom_out': '\u2212',  # minus sign
            'recenter': '\u25ce',  # bullseye / refocus
        }
        self._map_control_press = None

        # ── Map scan modes (toolbar inside the map frame) ──────────
        # 'terrain' is the default rich suit/tier view; the others wash the
        # map by one dimension so it's playful to scan.
        self._map_mode = 'terrain'
        self._map_mode_rects = {}

        # ── X close button (top-right of header) ───────────────────
        self._btn_close_rect = self._layout['close']
        self._btn_close_hit_rect = self._btn_close_rect.copy()
        if self._mobile_ui:
            self._btn_close_hit_rect.inflate_ip(
                max(0, settings.TOUCH_TARGET_MIN - self._btn_close_hit_rect.w),
                max(0, settings.TOUCH_TARGET_MIN - self._btn_close_hit_rect.h),
            )
            self._btn_close_hit_rect.clamp_ip(self._header_rect)

        # ── Collect All gold button (drawn in info bar) ────────────
        self._collect_all_rect = None
        self._collect_all_enabled = False
        self._floating_text = FloatingTextLayer()
        self._floating_text_last_tick = pygame.time.get_ticks()
        self._collect_float_font = settings.get_font(
            getattr(settings, 'COLLECT_FLOAT_FONT_SIZE', settings.FS_HEADING), bold=True)

        # ── Reward / conquest particle effects ─────────────────────
        # Gold streams from owned lands to the HUD on Collect All, and a
        # burst + border pulse celebrates a newly-conquered land on return.
        self._fx = ConquerEffectsLayer(self.window, lambda _id: None)
        # Set of my land ids from the last map load; diffed to detect new
        # conquests (a land that became mine) so we can celebrate it.
        self._prev_my_land_ids = None
        self._prev_champion_region_keys = None

        # ── Track last load time ────────────────────────────────────
        self._last_load_tick = 0

        # ── Background loaders ──────────────────────────────────────
        # The map fetch is a (potentially slow) HTTP round-trip; running it
        # via BackgroundPoller keeps the main loop unblocked so the game
        # menu chrome stays interactive while data is in flight.  The
        # activity fetch (notifications + history + messages) is bundled
        # into a second poller so it never re-freezes the screen.
        self._map_poller: BackgroundPoller | None = None
        self._activity_poller: BackgroundPoller | None = None

        # ── Leaderboard panel (top-left of map viewport) ────────────
        # Sized similarly to the minimap so the two widgets balance the
        # corners of the map frame.  Position is finalised in
        # ``_apply_map_response`` once the map viewport rect is known.
        self._leaderboard_panel = LeaderboardPanel(
            self.window,
            rect=None,
            on_focus=self._on_leaderboard_focus,
            render_crown_icon=self._render_panel_crown_icon,
        )

        # ── Kingdom selector chip (in header, drives map focus + config) ─
        # ``self._kingdom_chip_index`` tracks which of the player's
        # persistent kingdoms is currently focused on the map.  Stored on
        # the screen rather than on state so refocusing on re-entry is
        # deterministic.
        self._kingdom_chip_index = 0
        self._kingdom_chip_rect = None
        self._kingdom_chip_prev_rect = None
        self._kingdom_chip_next_rect = None
        self._kingdom_chip_gear_rect = None
        self._kingdom_chip_font = settings.get_font(settings.FS_SMALL, bold=True)
        self._kingdom_chip_small_font = settings.get_font(settings.FS_TINY)
        # Reuse the same edit icon as the defence/conquer config screens so
        # the affordance is consistent across kingdom-config entry points.
        try:
            self._kingdom_chip_edit_icon = pygame.image.load(
                'img/dialogue_box/icons/edit.png').convert_alpha()
        except Exception:
            self._kingdom_chip_edit_icon = None
        self._kingdom_chip_edit_icon_scaled = None
        self._kingdom_chip_edit_icon_scaled_sz = 0

    # ── Lifecycle ────────────────────────────────────────────────────

    def on_enter(self):
        """Called each time the kingdom screen becomes active.

        We deliberately do NOT clear ``_hex_map`` here: rebuilding the map
        from scratch on every entry is what made the screen feel slow.
        Instead we kick off a non-blocking refresh — on a cold start this
        shows the loading state, on re-entry the previously rendered map
        stays interactive while fresh data is fetched in the background.
        """
        self._last_load_tick = pygame.time.get_ticks()
        self._floating_text_last_tick = pygame.time.get_ticks()
        self._kingdom_management_dialogue = None
        self._kingdom_management_intro_step_id = None
        if getattr(self, '_fx', None):
            self._fx.clear()
        # Until the first conquest is complete, returning to Kingdom should
        # bring the marked target back instead of preserving an accidental pan
        # that left a phone user hunting across the full 96x50 map.
        if self._hex_map and self._recommended_tutorial_land_pending():
            self._focus_recommended_tutorial_land()
        self._load_map()

    # ── Data loading ────────────────────────────────────────────────

    @staticmethod
    def _fetch_map_data():
        """Worker: blocking HTTP call. Runs in BackgroundPoller's thread/XHR.

        Returns a dict with keys ``data``, ``status_code`` and ``error``.
        Network exceptions are converted into structured results so the main
        thread can react via :meth:`_apply_map_response` without re-entering
        ``requests``.
        """
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/map',
                timeout=(_MAP_CONNECT_TIMEOUT_SECONDS, _MAP_READ_TIMEOUT_SECONDS),
            )
            if resp.status_code != 200:
                return {'data': None, 'status_code': resp.status_code,
                        'error': 'Failed to load kingdom map'}
            return {'data': resp.json(), 'status_code': 200, 'error': None}
        except Exception as e:  # noqa: BLE001 — surface any failure verbatim
            return {'data': None, 'status_code': 0, 'error': str(e) or 'Connection error'}

    @staticmethod
    def _transform_map_async_response(resp):
        """Convert a web async-XHR response into the threaded worker shape."""
        try:
            if resp.status_code != 200:
                return {'data': None, 'status_code': resp.status_code,
                        'error': 'Failed to load kingdom map'}
            return {'data': resp.json(), 'status_code': 200, 'error': None}
        except Exception as e:  # noqa: BLE001
            return {'data': None, 'status_code': 0, 'error': str(e) or 'Connection error'}

    def _load_map(self):
        """Kick off a non-blocking kingdom map fetch.

        First entry: shows the loading state while the request is in flight.
        Subsequent re-entries: keeps the previously rendered hex map
        interactive (the result is applied once the poller returns).
        """
        if self._map_poller is None:
            self._map_poller = BackgroundPoller(
                self._fetch_map_data,
                async_get_url=f'{settings.SERVER_URL}/kingdom/map',
                async_transform=self._transform_map_async_response,
            )
        # If a previous request is already in flight, don't queue another.
        if self._map_poller.busy:
            return
        # Only show the "Loading..." overlay on cold starts; warm refreshes
        # keep the existing map interactive in the background.
        if self._hex_map is None:
            self._loading = True
            self._loading_started_at_ms = pygame.time.get_ticks()
            self._loading_message = 'Loading kingdom map...'
        self._error = None
        self._map_poller.poll()

    def _schedule_map_retry(self):
        delay = max(
            _MAP_RETRY_INITIAL_MS,
            int(getattr(self, '_map_retry_delay_ms', _MAP_RETRY_INITIAL_MS) or 0),
        )
        self._next_map_retry_at_ms = pygame.time.get_ticks() + delay
        self._map_retry_delay_ms = min(delay * 2, _MAP_RETRY_MAX_MS)

    def _clear_map_retry(self):
        self._map_retry_delay_ms = _MAP_RETRY_INITIAL_MS
        self._next_map_retry_at_ms = 0

    def _drain_map_poller(self):
        """Apply a finished map fetch, if any."""
        poller = self._map_poller
        if poller is None or not poller.has_result():
            return
        result = poller.result
        self._apply_map_response(result)

    def _apply_map_response(self, result):
        """Process the structured ``_fetch_map_data`` result on the main thread."""
        if not result or result.get('error') or not result.get('data'):
            err = (result or {}).get('error') or 'Connection error'
            self._error = err if err == 'Failed to load kingdom map' else 'Connection error'
            logger.error(f'Kingdom map load failed: {err}')
            self._loading = False
            self._schedule_map_retry()
            return
        self._clear_map_retry()
        data = result['data']
        self._map_data = data
        self._cooldown = data.get('conquer_cooldown_remaining', 0)
        self._recommended_tutorial_land_id = data.get('recommended_tutorial_land_id')
        lands = data.get('lands', [])
        cold_load = self._hex_map is None
        if cold_load:
            self._hex_map = HexMap(lands, self.window, viewport_rect=self._map_viewport_rect)
        else:
            self._hex_map.set_viewport(self._map_viewport_rect)
            self._hex_map.update_data(lands)
        # Re-apply the chosen scan mode (survives cold rebuilds + refreshes).
        if hasattr(self._hex_map, 'set_map_mode'):
            self._hex_map.set_map_mode(self._map_mode)
        regions = data.get('regions') or []
        if hasattr(self._hex_map, 'set_regions'):
            self._hex_map.set_regions(regions)

        # Keep the minimap and leaderboard pinned to the resized map corners.
        self._position_map_overlays()
        if cold_load and self._mobile_ui:
            self._leaderboard_panel.collapsed = True
        self._leaderboard_panel.set_my_user_id(self._current_user_id())
        self._leaderboard_panel.set_data(
            top_largest=data.get('top_largest_kingdoms') or [],
            top_realms=data.get('top_greatest_realms') or [],
            my_largest_rank=data.get('my_largest_rank'),
            my_largest_size=data.get('my_largest_size') or 0,
            my_realm_rank=data.get('my_realm_rank'),
            my_realm_size=data.get('my_realm_size') or 0,
            regions=regions,
        )

        # Wire the same leaderboard into the hex map so the on-map kingdom
        # name badges get gold / silver crown decorations.
        if hasattr(self._hex_map, 'set_leaderboards'):
            self._hex_map.set_leaderboards(
                data.get('top_largest_kingdoms') or [],
                data.get('top_greatest_realms') or [],
            )

        # Clamp the kingdom selector chip index so swapping kingdoms while
        # the screen is open never points past the new list.
        self._clamp_kingdom_chip_index()

        # Detect lands that just became mine (e.g. after returning from a
        # winning conquest) by diffing against the previous load.
        new_conquered = self._diff_new_conquests(lands)

        # Focus only on meaningful navigation events.  A warm refresh must not
        # undo a player's pan/zoom exploration.
        focused = bool(new_conquered
                       and self._hex_map.focus_lands(
                           new_conquered, fit=True, max_zoom=1.5))
        # Cold loads normally retain HexMap's full-world camera fit.  The one
        # exception is a returning tutorial player who has already read the
        # overview: their next task is a single marked hex, so show it at a
        # useful phone scale instead of leaving it a few pixels wide.
        if (cold_load and self._recommended_tutorial_land_pending()
                and 'kingdom_overview_window' in self._menu_coach_seen()):
            focused = bool(self._focus_recommended_tutorial_land()) or focused

        if new_conquered:
            self._celebrate_conquests(new_conquered)
        gained_regions = self._diff_champion_regions(regions)
        if gained_regions:
            self._celebrate_region_championships(gained_regions)

        self._loading = False
        self._last_map_updated_at_ms = pygame.time.get_ticks()
        logger.debug(f'Kingdom map loaded: {len(lands)} lands')
        self._load_activity()

    def _focus_largest_kingdom_component(self):
        """Center map camera on the largest connected component of owned lands."""
        if not self._hex_map or not isinstance(self._map_data, dict):
            return None

        my_kingdom = self._map_data.get('my_kingdom') or {}
        components = my_kingdom.get('components') or []
        if not components:
            return None

        best_land_ids = None
        best_key = None
        for component in components:
            land_ids = [
                land_id for land_id in (component.get('land_ids') or [])
                if isinstance(land_id, int)
            ]
            if not land_ids:
                continue
            size = int(component.get('size') or len(land_ids))
            key = (size, -min(land_ids))
            if best_key is None or key > best_key:
                best_key = key
                best_land_ids = land_ids

        if not best_land_ids:
            return None

        if hasattr(self._hex_map, 'focus_lands'):
            try:
                return self._hex_map.focus_lands(
                    best_land_ids, fit=True, max_zoom=1.5)
            except TypeError:
                # Compatibility for simple HexMap doubles and older clients.
                return self._hex_map.focus_lands(best_land_ids)

        # Backward-compatible fallback for older HexMap instances.
        return self._hex_map.focus_land(best_land_ids[0])

    # ── Leaderboard ↔ Hex map bridge ───────────────────────────────

    def _render_panel_crown_icon(self, category, rank_or_size, size=None):
        """Delegate to the HexMap's procedural crown so panel + map icons match.

        Mirrors HexMap._render_crown_icon's two call forms: ``(category, rank,
        size)`` for the per-row leaderboard crowns and the legacy ``(tier,
        size)`` shape kept for section-header icons.  Returns ``None`` before
        the hex map is built — the leaderboard panel handles that case by
        leaving the icon slot empty.
        """
        if self._hex_map is None or not hasattr(self._hex_map, '_render_crown_icon'):
            return None
        if size is None:
            return self._hex_map._render_crown_icon(category, rank_or_size)
        return self._hex_map._render_crown_icon(category, rank_or_size, size)

    def _on_leaderboard_focus(self, entry):
        """Pan the hex map to the kingdom referenced by a clicked panel row."""
        if not self._hex_map or not isinstance(entry, dict):
            return
        region_key = entry.get('region_key')
        if region_key and hasattr(self._hex_map, 'focus_region'):
            self._hex_map.focus_region(region_key)
            return
        # Largest-kingdom rows carry the matching component's land_ids;
        # greatest-realm rows carry the user's largest component land_ids.
        land_ids = (entry.get('land_ids')
                    or entry.get('largest_land_ids')
                    or [])
        if land_ids and hasattr(self._hex_map, 'focus_lands'):
            self._hex_map.focus_lands(land_ids, fit=True, max_zoom=1.5)
            return
        kid = entry.get('kingdom_id') or entry.get('largest_kingdom_id')
        cid = (entry.get('kingdom_component_id')
               or entry.get('largest_component_id'))
        if hasattr(self._hex_map, 'focus_on_kingdom'):
            self._hex_map.focus_on_kingdom(
                kingdom_id=kid,
                component_id=cid,
                user_id=entry.get('user_id'),
            )

    # ── Kingdom selector chip ──────────────────────────────────────

    def _kingdoms_list(self):
        if not isinstance(self._map_data, dict):
            return []
        return self._map_data.get('my_kingdoms') or []

    def _clamp_kingdom_chip_index(self):
        kingdoms = self._kingdoms_list()
        if not kingdoms:
            self._kingdom_chip_index = 0
            return
        self._kingdom_chip_index = max(
            0, min(self._kingdom_chip_index, len(kingdoms) - 1))

    def _current_chip_kingdom(self):
        kingdoms = self._kingdoms_list()
        if not kingdoms:
            return None
        idx = max(0, min(self._kingdom_chip_index, len(kingdoms) - 1))
        return kingdoms[idx]

    def _cycle_kingdom_chip(self, delta):
        kingdoms = self._kingdoms_list()
        n = len(kingdoms)
        if n <= 1:
            return
        self._kingdom_chip_index = (self._kingdom_chip_index + delta) % n
        # Pan the map to the newly-selected kingdom.
        self._focus_kingdom_on_map(kingdoms[self._kingdom_chip_index])

    def _focus_kingdom_on_map(self, kingdom):
        """Pan the hex map onto the lands of a given persistent kingdom."""
        if not (self._hex_map and isinstance(kingdom, dict)):
            return
        kid = kingdom.get('id')
        if kid is None:
            return
        land_ids = [t.land_id for t in self._hex_map.tiles
                    if getattr(t, 'kingdom_id', None) == kid]
        if land_ids and hasattr(self._hex_map, 'focus_lands'):
            self._hex_map.focus_lands(land_ids, fit=True, max_zoom=1.5)
        elif hasattr(self._hex_map, 'focus_on_kingdom'):
            self._hex_map.focus_on_kingdom(kingdom_id=kid)

    def _open_chip_config(self):
        """Open the kingdom config screen for the currently-focused chip kingdom."""
        kingdom = self._current_chip_kingdom()
        if not kingdom:
            return
        self.state.kingdom_config_land_id = None
        self.state.kingdom_config_id = kingdom.get('id')
        self.state.screen = 'kingdom_config'

    def _handle_kingdom_chip_click(self, pos):
        """Route a click on the chip to prev / next cycle, name tap, or gear."""
        chip_rect = getattr(self, '_kingdom_chip_rect', None)
        if not chip_rect or not chip_rect.collidepoint(pos):
            return False
        gear_rect = getattr(self, '_kingdom_chip_gear_rect', None)
        if gear_rect and gear_rect.collidepoint(pos):
            self._open_chip_config()
            return True
        prev_rect = getattr(self, '_kingdom_chip_prev_rect', None)
        if prev_rect and prev_rect.collidepoint(pos):
            self._cycle_kingdom_chip(-1)
            return True
        next_rect = getattr(self, '_kingdom_chip_next_rect', None)
        if next_rect and next_rect.collidepoint(pos):
            self._cycle_kingdom_chip(+1)
            return True
        # Tap on the body of the chip cycles to the next kingdom when the
        # player has more than one; otherwise it re-focuses the map on it.
        kingdoms = self._kingdoms_list()
        if len(kingdoms) > 1:
            self._cycle_kingdom_chip(+1)
        else:
            self._focus_kingdom_on_map(self._current_chip_kingdom())
        return True

    def _visible_notifications(self):
        """Return notification rows that should still appear in Alerts."""
        return [n for n in getattr(self, '_notifications', []) if not n.get('seen', False)]

    def _load_messages(self):
        """Fetch conversation summaries for the Messages tab."""
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/messages/conversations', timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self._conversations = data.get('conversations', [])
                self._message_unread_count = data.get('unread_count', 0)
            else:
                self._conversations = []
                self._message_unread_count = 0
        except Exception as e:
            logger.warning(f'Failed to load kingdom conversations: {e}')
            self._conversations = []
            self._message_unread_count = 0
        # Maintain legacy flat list for tests/back-compat.
        self._messages = list(self._conversations)

    def _load_activity(self):
        """Fetch unseen alerts and recent attack history for the activity panel.

        Runs as a single non-blocking BackgroundPoller job (3 endpoints) so it
        does not stack a multi-call freeze onto the kingdom-screen entry right
        after the map itself finishes loading.
        """
        if self._activity_poller is None:
            base = settings.SERVER_URL
            self._activity_poller = BackgroundPoller(
                self._fetch_activity_data,
                async_requests=[
                    {'key': 'notifications',
                     'url': f'{base}/kingdom/notifications'},
                    {'key': 'attack_history',
                     'url': f'{base}/kingdom/attack_history',
                     'params': {'per_page': 50}},
                    {'key': 'conversations',
                     'url': f'{base}/kingdom/messages/conversations'},
                ],
                async_transform=self._transform_activity_async_responses,
            )
        if self._activity_poller.busy:
            return
        self._activity_poller.poll()

    @staticmethod
    def _fetch_activity_data():
        """Worker: fetch notifications, attack history and conversations.

        Runs off the main thread; returns a plain dict the UI thread applies
        via :meth:`_apply_activity_data`.
        """
        base = settings.SERVER_URL
        out = {'notifications': [], 'attack_history': [],
               'conversations': [], 'unread_count': 0}
        try:
            resp = requests.get(f'{base}/kingdom/notifications', timeout=10)
            if resp.status_code == 200:
                out['notifications'] = resp.json().get('notifications', [])
        except Exception as e:  # noqa: BLE001
            logger.warning(f'Failed to load notifications: {e}')
        try:
            resp = requests.get(
                f'{base}/kingdom/attack_history?per_page=50', timeout=10)
            if resp.status_code == 200:
                out['attack_history'] = resp.json().get('history', [])
        except Exception as e:  # noqa: BLE001
            logger.warning(f'Failed to load attack history: {e}')
        try:
            resp = requests.get(
                f'{base}/kingdom/messages/conversations', timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                out['conversations'] = data.get('conversations', [])
                out['unread_count'] = data.get('unread_count', 0)
        except Exception as e:  # noqa: BLE001
            logger.warning(f'Failed to load kingdom conversations: {e}')
        return out

    @staticmethod
    def _transform_activity_async_responses(responses):
        """Convert web async activity responses into the worker result shape."""
        out = {'notifications': [], 'attack_history': [],
               'conversations': [], 'unread_count': 0}
        try:
            resp = responses.get('notifications') if isinstance(responses, dict) else None
            if resp and resp.status_code == 200:
                out['notifications'] = resp.json().get('notifications', [])
        except Exception as e:  # noqa: BLE001
            logger.warning(f'Failed to load notifications: {e}')
        try:
            resp = responses.get('attack_history') if isinstance(responses, dict) else None
            if resp and resp.status_code == 200:
                out['attack_history'] = resp.json().get('history', [])
        except Exception as e:  # noqa: BLE001
            logger.warning(f'Failed to load attack history: {e}')
        try:
            resp = responses.get('conversations') if isinstance(responses, dict) else None
            if resp and resp.status_code == 200:
                data = resp.json()
                out['conversations'] = data.get('conversations', [])
                out['unread_count'] = data.get('unread_count', 0)
        except Exception as e:  # noqa: BLE001
            logger.warning(f'Failed to load kingdom conversations: {e}')
        return out

    def _apply_activity_data(self, data):
        """Assign a finished ``_fetch_activity_data`` result on the main thread."""
        if not data:
            return
        self._notifications = data.get('notifications', [])
        self._attack_history = data.get('attack_history', [])
        self._conversations = data.get('conversations', [])
        self._message_unread_count = data.get('unread_count', 0)
        # Maintain legacy flat list for tests/back-compat.
        self._messages = list(self._conversations)

    def _drain_activity_poller(self):
        """Apply a finished activity fetch, if any."""
        poller = self._activity_poller
        if poller is None or not poller.has_result():
            return
        self._apply_activity_data(poller.result)

    # ── Rendering ───────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        # Outer box
        _draw_panel(self.window, self._box_rect)

        # Desktop keeps the formal screen title.  Mobile uses the active
        # kingdom identity as its title so the compact header has one clear
        # focal point instead of three competing labels.
        if not self._mobile_ui:
            tx = self._header_rect.x + (self._header_rect.w - self._title_surf.get_width()) // 2
            self.window.blit(self._title_surf, (tx, self._title_y))
        self._draw_info_bar()
        self._draw_map_frame()
        if not self._mobile_ui and self._activity_open:
            self._draw_activity_panel()

        if self._loading:
            draw_loading_indicator(
                self.window,
                self._map_frame_rect,
                self._loading_message,
                started_at_ms=self._loading_started_at_ms,
                font=self._info_font,
                small_font=self._info_font,
            )
        elif self._error:
            self._draw_map_error_state()
        elif self._hex_map:
            self._hex_map.set_viewport(self._map_viewport_rect)
            self._hex_map.render()
            self._draw_nav_buttons()
            # Leaderboard panel sits on top of the hex map at the top-left
            # of the viewport so it mirrors the minimap (bottom-right).
            self._leaderboard_panel.render()
            # Scan-mode toolbar sits at the top-right of the map.
            self._draw_map_modes_toolbar()

        # Mobile activity is a temporary drawer above the map, not a permanent
        # column beside it.
        if self._mobile_ui and self._activity_open:
            self._draw_activity_panel()

        # Kingdom selector chip lives inside the header — always drawn so
        # it stays available even while the map is loading.
        self._draw_kingdom_chip()

        # Hover preview card (sits above the map, below the modal layer).
        self._draw_hover_preview()

        self._draw_close_x_button()

        # Modal layer
        if self._detail_box:
            self._detail_box.render()
        if self._thread:
            self._draw_thread_modal()
        if self._new_msg_picker:
            self._draw_new_msg_picker()

        # Floating text (gold collect / level up) above modals' chrome
        now_ms = pygame.time.get_ticks()
        dt_ms = max(0, now_ms - getattr(self, '_floating_text_last_tick', now_ms))
        self._floating_text_last_tick = now_ms
        self._floating_text.update(dt_ms)
        self._floating_text.draw(self.window)

        # Reward / conquest particle effects (gold streams, conquest bursts).
        if getattr(self, '_fx', None):
            self._fx.draw()

        self._draw_menu_overlay()
        self._draw_menu_coach(self._current_kingdom_coach_step())
        if getattr(self, '_kingdom_overview_dialogue', None):
            self._kingdom_overview_dialogue.draw()
        if getattr(self, '_kingdom_management_dialogue', None):
            self._kingdom_management_dialogue.draw()
        # Topmost modal: the conquer-tutorial completion celebration, shown
        # right after the final task completes on this screen.
        self._draw_tutorial_complete_dialogue()

    def _draw_map_error_state(self):
        """Draw a useful retry state instead of a dead-end error label."""
        center = self._map_frame_rect.center
        txt = self._info_font.render(self._error or 'Connection error', True,
                                     (224, 112, 96))
        self.window.blit(txt, txt.get_rect(center=(center[0], center[1] - 18)))
        seconds = max(
            0,
            int((getattr(self, '_next_map_retry_at_ms', 0)
                 - pygame.time.get_ticks()) / 1000),
        )
        label = 'Retry now' if seconds <= 0 else f'Retry now  ·  auto in {seconds}s'
        font = self._nav_font
        surf = font.render(label, True, (245, 232, 196))
        pad_x = max(12, int(0.010 * _SW))
        h = max(surf.get_height() + 10,
                settings.TOUCH_COMPACT_MIN if self._mobile_ui else 0)
        w = surf.get_width() + pad_x * 2
        self._retry_rect = pygame.Rect(0, 0, w, h)
        self._retry_rect.center = (center[0], center[1] + 20)
        pygame.draw.rect(self.window, (72, 54, 38), self._retry_rect,
                         border_radius=6)
        pygame.draw.rect(self.window, settings.KINGDOM_MAP_FRAME_BORDER,
                         self._retry_rect, 1, border_radius=6)
        self.window.blit(surf, surf.get_rect(center=self._retry_rect.center))

    def _maybe_show_kingdom_overview(self):
        """First Kingdom open: a teaching window about lands and kingdoms."""
        if self._kingdom_overview_dialogue:
            return
        onboarding = self._onboarding()
        if not onboarding or onboarding.get('onboarding_skipped'):
            return
        if 'kingdom_overview_window' in self._menu_coach_seen():
            return
        if not self._hex_map or self._loading or self._error:
            return
        if self._detail_box or self._thread or self._new_msg_picker:
            return
        if getattr(self, 'dialogue_box', None) or getattr(self, '_onboarding_guide_open', False):
            return
        from game.components.tutorial_window import TutorialWindowDialogue
        from game.tutorial_content import kingdom_overview_pages
        self._kingdom_overview_dialogue = TutorialWindowDialogue(
            self.window,
            kingdom_overview_pages(),
            title='Your Kingdom',
            presentation=('map_sidecar' if self._mobile_ui else 'modal'),
        )

    def _maybe_show_kingdom_management_intro(self):
        """Open the illustrated introduction for Kingdom-based lessons."""
        if getattr(self, '_kingdom_management_dialogue', None):
            return
        lesson_id = self._active_onboarding_lesson_id()
        specs = {
            'build_attack': (
                'build_attack_intro_window',
                'Build Your Own Attack',
                'build_attack_intro_pages',
            ),
            'run_kingdom': (
                'kingdom_management_intro',
                'Run Your Kingdom',
                'kingdom_management_pages',
            ),
            'defend_land': (
                'defend_land_intro_window',
                'Defend Your Land',
                'defend_land_intro_pages',
            ),
        }
        spec = specs.get(lesson_id)
        if not spec:
            return
        step_id, title, pages_name = spec
        if step_id in self._menu_coach_seen():
            return
        if not self._hex_map or self._loading or self._error:
            return
        if (self._detail_box or self._thread or self._new_msg_picker
                or getattr(self, '_kingdom_overview_dialogue', None)):
            return
        if (getattr(self, 'dialogue_box', None)
                or getattr(self, '_onboarding_guide_open', False)):
            return
        from game.components.tutorial_window import TutorialWindowDialogue
        from game import tutorial_content
        pages = getattr(tutorial_content, pages_name)()
        self._kingdom_management_intro_step_id = step_id
        self._kingdom_management_dialogue = TutorialWindowDialogue(
            self.window,
            pages,
            title=title,
        )

    def _handle_kingdom_management_events(self, events):
        dialogue = getattr(self, '_kingdom_management_dialogue', None)
        if not dialogue:
            return False
        from pygame import QUIT
        if any(getattr(event, 'type', None) == QUIT for event in events):
            return False
        if dialogue.update(events) == 'done':
            self._kingdom_management_dialogue = None
            step_id = getattr(
                self, '_kingdom_management_intro_step_id', None)
            self._kingdom_management_intro_step_id = None
            if step_id:
                self._mark_menu_coach_seen(step_id)
        return True

    def _handle_kingdom_overview_events(self, events):
        dialogue = getattr(self, '_kingdom_overview_dialogue', None)
        if not dialogue:
            return False
        from pygame import QUIT
        if any(getattr(e, 'type', None) == QUIT for e in events):
            return False

        dialogue_events = []
        map_events = []
        for event in events:
            event_type = getattr(event, 'type', None)
            dialogue_dragging = (
                getattr(dialogue, '_dragging', False)
                or getattr(dialogue, '_scrollbar_dragging', False)
            )
            map_dragging = (
                getattr(getattr(self, '_hex_map', None), '_dragging', False)
                or getattr(self, '_map_control_press', None) is not None
            )
            if (not dialogue_dragging and map_dragging
                    and event_type in (pygame.MOUSEMOTION,
                                       pygame.MOUSEBUTTONUP)):
                map_events.append(event)
                continue
            if dialogue.captures_event(event):
                dialogue_events.append(event)
            else:
                map_events.append(event)

        if dialogue.update(dialogue_events) == 'done':
            self._kingdom_overview_dialogue = None
            self._mark_menu_coach_seen('kingdom_overview_window')
            self._focus_recommended_tutorial_land()
            return True
        self._handle_map_navigation_behind_tutorial(map_events)
        return True

    def _handle_map_navigation_behind_tutorial(self, events):
        """Keep map exploration live in the area exposed by the sidecar.

        This deliberately ignores returned land clicks: the overview teaches
        the map without opening another panel above it.  Drag, pinch/wheel zoom
        and the dedicated zoom/recenter buttons still work normally.
        """
        hex_map = getattr(self, '_hex_map', None)
        if not hex_map:
            return
        multi_gesture = getattr(pygame, 'MULTIGESTURE', None)
        map_event_types = {
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION,
            pygame.MOUSEWHEEL,
        }
        if multi_gesture is not None:
            map_event_types.add(multi_gesture)
        for event in events:
            event_type = getattr(event, 'type', None)
            if event_type not in map_event_types:
                continue
            if (event_type == pygame.MOUSEBUTTONDOWN
                    and getattr(event, 'button', 0) == 1
                    and self._begin_map_control_press(event.pos)):
                continue
            if (event_type == pygame.MOUSEMOTION
                    and self._drag_map_control_press(event.pos)):
                continue
            if (event_type == pygame.MOUSEBUTTONUP
                    and getattr(event, 'button', 0) == 1
                    and self._finish_map_control_press(event.pos)):
                continue
            hex_map.handle_event(event)

    def _kingdom_coach_ready(self):
        # The first-open overview window teaches concepts before coach pointers.
        if (getattr(self, '_kingdom_overview_dialogue', None)
                or getattr(self, '_kingdom_management_dialogue', None)):
            return False
        return 'kingdom_overview_window' in self._menu_coach_seen()

    def _detail_action_button_rect(self, wanted_action):
        detail_box = getattr(self, '_detail_box', None)
        if not detail_box:
            return None
        for action, btn in getattr(detail_box, '_buttons', []) or []:
            if action == wanted_action and not getattr(btn, 'disabled', False):
                return getattr(btn, 'rect', None)
        return None

    def _detail_conquer_button_rect(self):
        return self._detail_action_button_rect('conquer')

    def _first_conquest_attempted(self):
        """True once the player has finished at least one conquer battle.

        Combined with an incomplete first conquest, this means they lost their
        first attempt — the no-penalty retry path.
        """
        facts = (self._onboarding() or {}).get('facts') or {}
        return int(facts.get('conquer_battles') or 0) >= 1

    def _recommended_tutorial_land_pending(self):
        """Whether the marked first-conquest target should still be guided."""
        land_id = getattr(self, '_recommended_tutorial_land_id', None)
        onboarding = self._onboarding() or {}
        return bool(
            self._mobile_ui
            and land_id is not None
            and not onboarding.get('onboarding_skipped')
            and 'finish_first_conquer_battle'
            not in self._onboarding_completed_steps()
        )

    def _focus_recommended_tutorial_land(self):
        """Centre the marked land at a tap-friendly zoom without opening it."""
        if not self._recommended_tutorial_land_pending() or not self._hex_map:
            return None
        land_id = self._recommended_tutorial_land_id
        focus_many = getattr(self._hex_map, 'focus_lands', None)
        if callable(focus_many):
            tile = focus_many([land_id], fit=True, max_zoom=1.5)
        else:
            focus_one = getattr(self._hex_map, 'focus_land', None)
            tile = focus_one(land_id) if callable(focus_one) else None
        if tile is not None and hasattr(self._hex_map, 'selected_tile'):
            # The coach asks the player to tap; centring must not make the land
            # look as though it has already been selected.
            self._hex_map.selected_tile = None
        return tile

    def _recommended_tutorial_touch_tile(self, pos, coach_step):
        """Return the marked tile for a forgiving mobile tap around its hex."""
        if (not self._mobile_ui or not coach_step
                or coach_step.get('id') not in (
                    'kingdom_pick_land', 'kingdom_conquer_retry')):
            return None
        rect = self._recommended_land_anchor_rect()
        if rect is None:
            return None
        target = max(
            settings.TOUCH_TARGET_MIN,
            getattr(settings, 'TOUCH_ICON_MIN', 0) or 0,
        )
        hit = rect.inflate(max(0, target - rect.w),
                           max(0, target - rect.h))
        hit.clamp_ip(self._map_viewport_rect)
        if not hit.collidepoint(pos):
            return None
        land_id = self._recommended_tutorial_land_id
        return next(
            (tile for tile in getattr(self._hex_map, 'tiles', [])
             if getattr(tile, 'land_id', None) == land_id),
            None,
        )

    def _recommended_land_anchor_rect(self):
        """Screen rect of the recommended tutorial land, or None.

        Used to anchor the conquer-tutorial coach card on the specific hex
        (so the card sits beside the land instead of covering it). Falls back
        to None when the land is unknown or panned off-screen, letting callers
        use the whole map viewport instead.
        """
        land_id = getattr(self, '_recommended_tutorial_land_id', None)
        if not land_id or not self._hex_map:
            return None
        getter = getattr(self._hex_map, 'land_screen_rect', None)
        if not callable(getter):
            return None
        return getter(land_id)

    def _current_kingdom_coach_step(self):
        if not self._menu_coach_allowed_common() or not self._kingdom_coach_ready():
            return None
        if self._thread or self._new_msg_picker:
            return None
        seen = self._menu_coach_seen()
        completed = self._onboarding_completed_steps()
        first_conquer_complete = 'finish_first_conquer_battle' in completed
        conquer_button_rect = self._detail_conquer_button_rect()
        if not first_conquer_complete and conquer_button_rect and 'kingdom_conquer_button' not in seen:
            return {
                'id': 'kingdom_conquer_button',
                'rect': conquer_button_rect,
                'title': 'Open Conquer Setup',
                'body': "Tap Conquer. We've pre-built your first attack so you can see how one fits together.",
                'action': 'click',
                'mark_on_click': True,
                'max_lines': 4,
            }
        active_lesson = self._active_onboarding_lesson_id()
        first_journey_finished = 'finish_tutorial' in completed
        if first_journey_finished and self._detail_box:
            if active_lesson == 'build_attack':
                attack_rect = self._detail_action_button_rect('conquer')
                if attack_rect and 'conquer_open_next_attack' not in seen:
                    return {
                        'id': 'conquer_open_next_attack',
                        'rect': attack_rect,
                        'title': 'Open Attack Setup',
                        'body': 'Choose Conquer. This time you will build the figures, tactics, and optional prelude yourself.',
                        'action': 'click',
                        'mark_on_click': True,
                        'max_lines': 4,
                    }
            elif active_lesson == 'defend_land':
                defence_rect = self._detail_action_button_rect('defence')
                if defence_rect and 'defence_open_config' not in seen:
                    return {
                        'id': 'defence_open_config',
                        'rect': defence_rect,
                        'title': 'Open Defence Setup',
                        'body': 'Choose Defence to replace the automatic starter defence with a plan you build yourself.',
                        'action': 'click',
                        'mark_on_click': True,
                        'max_lines': 4,
                    }
        if self._detail_box:
            return None
        if not self._hex_map or self._loading or self._error:
            return None
        if not first_conquer_complete and 'kingdom_pick_land' not in seen:
            land_rect = self._recommended_land_anchor_rect()
            has_recommended = land_rect is not None
            return {
                'id': 'kingdom_pick_land',
                # Anchor on the marked hex so the card sits beside it, but let
                # taps anywhere on the map pass through (pan + land selection).
                'rect': land_rect or self._map_viewport_rect,
                'click_through_rects': [self._map_viewport_rect],
                'title': 'Pick The Marked Land' if has_recommended else 'Pick A Land',
                'body': (
                    "Tap the gold-marked land. It's a perfect first target for your starter attack."
                    if has_recommended else
                    'Each hex is a land. Tap one you do not own to inspect it, then choose Conquer.'
                ),
                'action': 'click',
                'mark_on_click': False,
                'max_lines': 4,
                'coach_placement': (
                    'inside_top' if self._mobile_ui and not has_recommended
                    else None
                ),
            }
        # Lost the first conquest (no land won yet): re-guide the no-penalty
        # retry. No cards were lost and the recommended land + starter attack are
        # still available, so the player can attack the marked land again. This
        # nudge is never marked, so it re-shows every visit until they win.
        if not first_conquer_complete and self._first_conquest_attempted():
            land_rect = self._recommended_land_anchor_rect()
            return {
                'id': 'kingdom_conquer_retry',
                'rect': land_rect or self._map_viewport_rect,
                'click_through_rects': [self._map_viewport_rect],
                'title': 'Try Again',
                'body': 'Nothing was lost, and your attack is still ready. Tap the gold-marked land and try again.',
                'action': 'click',
                'mark_on_click': False,
                'max_lines': 4,
                'coach_placement': (
                    'inside_top' if self._mobile_ui and land_rect is None
                    else None
                ),
            }
        if not first_conquer_complete:
            return None

        if 'kingdom_after_conquer_map' not in seen:
            return {
                'id': 'kingdom_after_conquer_map',
                'rect': self._map_viewport_rect,
                'title': 'Your First Land!',
                'body': 'Congratulations! Your first land joins your kingdom and starts producing gold for you.',
                'action': 'coach',
                'interactive_rects': [self._map_viewport_rect],
                'coach_placement': 'inside_top' if self._mobile_ui else None,
                'finish_tutorial_button': True,
                'max_lines': 5,
            }

        if active_lesson == 'build_attack':
            if 'conquer_choose_next_land' not in seen:
                return {
                    'id': 'conquer_choose_next_land',
                    'rect': self._map_viewport_rect,
                    'click_through_rects': [self._map_viewport_rect],
                    'title': 'Choose Your Next Target',
                    'body': 'Tap a neighbouring land you do not own, inspect it, then choose Conquer.',
                    'action': 'click',
                    'mark_on_click': False,
                    'max_lines': 4,
                    'coach_placement': (
                        'inside_top' if self._mobile_ui else None),
                }
            return None

        if active_lesson == 'defend_land':
            if 'defence_choose_land' not in seen:
                return {
                    'id': 'defence_choose_land',
                    'rect': self._map_viewport_rect,
                    'click_through_rects': [self._map_viewport_rect],
                    'title': 'Choose One Of Your Lands',
                    'body': 'Tap a land you own, inspect it, then open its Defence setup.',
                    'action': 'click',
                    'mark_on_click': False,
                    'max_lines': 4,
                    'coach_placement': (
                        'inside_top' if self._mobile_ui else None),
                }
            return None

        if active_lesson == 'run_kingdom':
            if ('kingdom_collect_production' not in seen
                    and self._collect_all_rect):
                collect_ready = bool(self._collect_all_enabled)
                return {
                    'id': 'kingdom_collect_production',
                    'rect': self._collect_all_rect,
                    'title': (
                        'Collect Ready Production'
                        if collect_ready else 'Production Appears Here'),
                    'body': (
                        'Tap here to collect the gold, packs, or maps your kingdoms have produced.'
                        if collect_ready else
                        'Gold, packs, and maps accumulate here over time. Nothing is ready yet, but this is where you collect it later.'
                    ),
                    'action': 'click' if collect_ready else 'next',
                    'mark_on_click': True,
                    'button_label': (
                        None if collect_ready else 'Got it'),
                    'max_lines': 4,
                }
            if ('kingdom_open_management' not in seen
                    and self._kingdom_chip_gear_rect):
                return {
                    'id': 'kingdom_open_management',
                    'rect': self._kingdom_chip_gear_rect,
                    'title': 'Open Kingdom Management',
                    'body': 'Next, use this edit button to review production, skills, the Loot Inbox, shields, and kingdom appearance.',
                    'action': 'click',
                    'mark_on_click': True,
                    'max_lines': 4,
                }
            return None

        return None

    def _finish_menu_coach_tutorial(self, step_id):
        if step_id == 'kingdom_after_conquer_map':
            if self._complete_onboarding_step('finish_tutorial'):
                self._mark_menu_coach_seen(step_id)
        else:
            self._mark_menu_coach_seen(step_id)

    def _draw_close_x_button(self):
        r = self._btn_close_rect
        mouse_pos = pygame.mouse.get_pos()
        hovered = r.collidepoint(mouse_pos)
        bg_clr = (80, 50, 25, 220) if hovered else (55, 35, 18, 200)
        border_clr = (180, 160, 120) if hovered else (120, 100, 70)
        txt_clr = (255, 240, 200) if hovered else (200, 180, 140)
        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg_clr, surf.get_rect(), border_radius=4)
        pygame.draw.rect(surf, border_clr, surf.get_rect(), 1, border_radius=4)
        self.window.blit(surf, r.topleft)
        _xfont = settings.get_font(int(settings.FONT_SIZE * 0.85), bold=True)
        txt = _xfont.render('\u00d7', True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=r.center))

    def _draw_map_frame(self):
        """Draw the dedicated map frame that owns map rendering and input."""
        r = self._map_frame_rect
        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.KINGDOM_MAP_FRAME_BG, surf.get_rect(), border_radius=8)
        self.window.blit(surf, r.topleft)
        pygame.draw.rect(self.window, settings.KINGDOM_MAP_FRAME_BORDER, r,
                         settings.KINGDOM_MAP_FRAME_BORDER_W, border_radius=8)

    def _position_map_overlays(self):
        """Keep map-corner widgets aligned after the viewport changes size."""
        vp = self._map_viewport_rect
        hm = getattr(self, '_hex_map', None)
        if hm is not None:
            minimap_y = (
                vp.bottom - settings.MINIMAP_H - settings.MINIMAP_MARGIN)
            if self._mobile_ui and _SH > _SW:
                minimap_y -= settings.TOUCH_TARGET_MIN + settings.MINIMAP_MARGIN
            hm.minimap_origin = (
                vp.right - settings.MINIMAP_W - settings.MINIMAP_MARGIN,
                minimap_y,
            )

        leaderboard = getattr(self, '_leaderboard_panel', None)
        if leaderboard is None or not hasattr(leaderboard, 'set_rect'):
            return
        lb_w = settings.MINIMAP_W
        lb_h = int(settings.MINIMAP_H * 2.1)
        if self._mobile_ui:
            lb_w = min(int(0.34 * _SW), int(vp.w * 0.48))
            lb_h = min(int(0.60 * _SH), int(vp.h * 0.94))
        leaderboard.set_rect((
            vp.x + settings.MINIMAP_MARGIN,
            vp.y + settings.MINIMAP_MARGIN,
            lb_w,
            lb_h,
        ))

    def _set_activity_open(self, is_open):
        """Open/close Activity and let the desktop map reclaim its column."""
        is_open = bool(is_open)
        if self._activity_open == is_open:
            return
        self._activity_open = is_open
        self._activity_toggle_rect = None
        self._activity_panel_toggle_rect = None

        # Mobile already renders Activity as an overlay over a full-width map.
        if self._mobile_ui:
            return

        old_vp = pygame.Rect(self._map_viewport_rect)
        layout = _compute_kingdom_layout(is_open)
        self._layout = layout
        self._map_frame_rect = layout['map_frame']
        self._map_viewport_rect = layout['map_viewport']
        self._activity_rect = layout['activity']

        hm = getattr(self, '_hex_map', None)
        set_viewport = getattr(hm, 'set_viewport', None)
        if callable(set_viewport):
            # Preserve the world point at the centre of the map while the
            # viewport grows/shrinks, then clamp it to the legal map bounds.
            zoom = max(0.001, float(getattr(hm, 'zoom', 1.0) or 1.0))
            world_cx = getattr(hm, 'camera_x', 0.0) + old_vp.w / (2 * zoom)
            world_cy = getattr(hm, 'camera_y', 0.0) + old_vp.h / (2 * zoom)
            set_viewport(self._map_viewport_rect)
            if hasattr(hm, 'camera_x') and hasattr(hm, 'camera_y'):
                hm.camera_x = world_cx - self._map_viewport_rect.w / (2 * zoom)
                hm.camera_y = world_cy - self._map_viewport_rect.h / (2 * zoom)
                clamp = getattr(hm, '_clamp_camera', None)
                if callable(clamp):
                    clamp()

        self._position_map_overlays()

        detail = getattr(self, '_detail_box', None)
        if (detail is not None and getattr(detail, '_anchored', False)
                and hasattr(detail, '_build_layout')):
            detail._viewport_rect = pygame.Rect(self._map_viewport_rect)
            detail._build_layout()

    def _activity_scroll_offsets_map(self):
        offsets = getattr(self, '_activity_scroll_offsets', None)
        if not isinstance(offsets, dict):
            offsets = {'alerts': 0, 'history': 0, 'messages': 0}
            self._activity_scroll_offsets = offsets
        return offsets

    def _activity_content_top(self):
        tab_y = self._activity_rect.y + (44 if self._mobile_ui else 34)
        tab_h = max(
            int(0.036 * _SH),
            settings.TOUCH_TARGET_MIN if self._mobile_ui else 0,
        )
        return tab_y + tab_h + 10

    def _activity_visible_count(self):
        row_h = settings.KINGDOM_ACTIVITY_ROW_H
        available_h = self._activity_rect.bottom - 10 - self._activity_content_top()
        # Reserve space for "+ New message" button on Messages tab.
        if self._activity_tab == 'messages':
            available_h -= (
                settings.TOUCH_TARGET_MIN + 8 if self._mobile_ui else 32)
        return max(1, available_h // row_h)

    def _activity_rows_for_tab(self, tab=None):
        tab = tab or self._activity_tab
        if tab == 'alerts':
            return self._visible_notifications(), 'No new kingdom alerts.'
        if tab == 'history':
            return getattr(self, '_attack_history', []), 'No attacks yet.'
        if tab == 'messages':
            convos = getattr(self, '_conversations', None)
            if convos is None:
                convos = getattr(self, '_messages', [])
            return (convos,
                    'No conversations yet. Use "+ New message" or click another player\'s land.')
        return [], 'Select a kingdom activity tab.'

    def _clamp_activity_scroll(self, tab=None, row_count=None, visible_count=None):
        tab = tab or self._activity_tab
        if row_count is None:
            rows, _empty = self._activity_rows_for_tab(tab)
            row_count = len(rows)
        if visible_count is None:
            visible_count = self._activity_visible_count()
        max_offset = max(0, int(row_count) - int(visible_count))
        offsets = self._activity_scroll_offsets_map()
        offset = max(0, min(int(offsets.get(tab, 0) or 0), max_offset))
        offsets[tab] = offset
        return offset

    def _scroll_activity_tab(self, delta_rows, tab=None):
        """Scroll the active activity tab by row count. Returns True if changed."""
        tab = tab or self._activity_tab
        rows, _empty = self._activity_rows_for_tab(tab)
        visible_count = self._activity_visible_count()
        max_offset = max(0, len(rows) - visible_count)
        offsets = self._activity_scroll_offsets_map()
        before = self._clamp_activity_scroll(tab, len(rows), visible_count)
        after = max(0, min(before + int(delta_rows), max_offset))
        offsets[tab] = after
        return after != before

    def _draw_activity_scrollbar(self, panel_rect, content_top, max_bottom,
                                 row_count, visible_count, offset):
        if row_count <= visible_count:
            self._activity_scrollbar_rect = None
            return
        track_h = max(1, max_bottom - content_top - 2)
        track = pygame.Rect(panel_rect.right - 14, content_top, 5, track_h)
        self._activity_scrollbar_rect = track
        pygame.draw.rect(self.window, (48, 44, 58), track, border_radius=3)
        knob_h = max(14, int(track.h * (visible_count / float(row_count))))
        max_offset = max(1, row_count - visible_count)
        knob_y = track.y + int((track.h - knob_h) * (offset / float(max_offset)))
        knob = pygame.Rect(track.x, knob_y, track.w, knob_h)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, knob, border_radius=3)

    def _draw_activity_panel(self):
        """Draw the right-side activity panel with alert/history tabs."""
        r = self._activity_rect
        self._activity_tab_rects = {}
        self._activity_tab_hit_rects = {}
        self._activity_row_rects = []
        self._activity_scrollbar_rect = None
        self._mark_read_rect = None
        self._mark_read_kind = None
        self._new_msg_rect = None
        self._new_msg_hit_rect = None
        self._mark_read_hit_rect = None
        self._activity_close_rect = None
        self._activity_panel_toggle_rect = None

        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        panel_bg = ((22, 20, 28, 246) if self._mobile_ui
                    else settings.KINGDOM_ACTIVITY_BG)
        pygame.draw.rect(surf, panel_bg, surf.get_rect(), border_radius=8)
        self.window.blit(surf, r.topleft)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, r, 1, border_radius=8)

        old_clip = self.window.get_clip()
        self.window.set_clip(r)
        try:
            alert_rows = self._visible_notifications()
            rows, empty = self._activity_rows_for_tab(self._activity_tab)
            has_mark_read = (
                (self._activity_tab == 'alerts' and rows)
                or (self._activity_tab == 'messages' and self._message_unread_count)
            )
            title_label = 'Activity' if self._mobile_ui else 'Kingdom Activity'
            title_max_w = r.w - (
                152 if self._mobile_ui else (168 if has_mark_read else 48))
            title_label = self._fit_text(title_label, self._activity_title_font, title_max_w)
            title = self._activity_title_font.render(title_label, True, settings.KINGDOM_INFO_CLR)
            title_y = r.y + (12 if self._mobile_ui else 8)
            self.window.blit(title, (r.x + 12, title_y))

            if self._mobile_ui:
                close_sz = settings.TOUCH_ICON_MIN
                self._activity_close_rect = pygame.Rect(
                    r.right - close_sz - 8, r.y + 6, close_sz, close_sz)
                pygame.draw.rect(self.window, (55, 35, 18, 220),
                                 self._activity_close_rect, border_radius=5)
                close = self._activity_title_font.render('\u00d7', True,
                                                         (230, 214, 180))
                self.window.blit(close, close.get_rect(
                    center=self._activity_close_rect.center))
            else:
                toggle_sz = max(22, self._activity_title_font.get_height() + 6)
                self._activity_panel_toggle_rect = pygame.Rect(
                    r.right - toggle_sz - 7, r.y + 5, toggle_sz, toggle_sz)
                hovered = self._activity_panel_toggle_rect.collidepoint(
                    pygame.mouse.get_pos())
                toggle_bg = ((72, 64, 88, 235) if hovered
                             else settings.KINGDOM_ACTIVITY_TAB_BG)
                pygame.draw.rect(self.window, toggle_bg,
                                 self._activity_panel_toggle_rect,
                                 border_radius=5)
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER,
                                 self._activity_panel_toggle_rect, 1,
                                 border_radius=5)
                caret = self._activity_title_font.render(
                    '\u203a', True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
                self.window.blit(caret, caret.get_rect(
                    center=self._activity_panel_toggle_rect.center))

            msg_label = 'Messages'
            if self._message_unread_count:
                msg_label = f'Messages ({self._message_unread_count})'
            tabs = [('alerts', f'Alerts ({len(alert_rows)})'),
                    ('history', 'History'),
                    ('messages', msg_label)]
            tab_y = r.y + (44 if self._mobile_ui else 34)
            tab_h = max(
                int(0.036 * _SH),
                settings.TOUCH_TARGET_MIN if self._mobile_ui else 0,
            )
            tab_gap = 4
            tab_w = (r.w - 20 - tab_gap * (len(tabs) - 1)) // len(tabs)
            for i, (key, label) in enumerate(tabs):
                tr = pygame.Rect(r.x + 10 + i * (tab_w + tab_gap), tab_y, tab_w, tab_h)
                self._activity_tab_rects[key] = tr
                hit = tr.copy()
                self._activity_tab_hit_rects[key] = hit
                bg = (settings.KINGDOM_ACTIVITY_TAB_ACTIVE_BG
                      if self._activity_tab == key else settings.KINGDOM_ACTIVITY_TAB_BG)
                pygame.draw.rect(self.window, bg, tr, border_radius=5)
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, tr, 1, border_radius=5)
                label = self._fit_text(label, self._activity_small_font, tr.w - 8)
                lbl = self._activity_small_font.render(label, True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
                self.window.blit(lbl, lbl.get_rect(center=tr.center))

            content_top = self._activity_content_top()
            # "+ New message" button on the Messages tab, above the row list.
            if self._activity_tab == 'messages':
                new_btn_h = max(
                    24,
                    settings.TOUCH_TARGET_MIN if self._mobile_ui else 0,
                )
                self._new_msg_rect = pygame.Rect(r.x + 10, content_top,
                                                 r.w - 20, new_btn_h)
                self._new_msg_hit_rect = self._new_msg_rect.copy()
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_TAB_ACTIVE_BG,
                                 self._new_msg_rect, border_radius=5)
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER,
                                 self._new_msg_rect, 1, border_radius=5)
                lbl = self._activity_small_font.render('+ New message', True,
                                                       settings.KINGDOM_ACTIVITY_TEXT_CLR)
                self.window.blit(lbl, lbl.get_rect(center=self._new_msg_rect.center))
                content_top = self._new_msg_rect.bottom + 8
            if self._activity_tab == 'alerts' and rows:
                mark_w = 104
                mark_h = settings.TOUCH_COMPACT_MIN if self._mobile_ui else 20
                right_pad = ((settings.TOUCH_ICON_MIN + 16) if self._mobile_ui
                             else self._activity_panel_toggle_rect.w + 20)
                self._mark_read_rect = pygame.Rect(
                    r.right - right_pad - mark_w, r.y + 6, mark_w, mark_h)
                self._mark_read_kind = 'alerts'
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_TAB_BG,
                                 self._mark_read_rect, border_radius=5)
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER,
                                 self._mark_read_rect, 1, border_radius=5)
                mark = self._activity_small_font.render('Mark all read', True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
                self.window.blit(mark, mark.get_rect(center=self._mark_read_rect.center))
            elif self._activity_tab == 'messages' and self._message_unread_count:
                mark_w = 104
                mark_h = settings.TOUCH_COMPACT_MIN if self._mobile_ui else 20
                right_pad = ((settings.TOUCH_ICON_MIN + 16) if self._mobile_ui
                             else self._activity_panel_toggle_rect.w + 20)
                self._mark_read_rect = pygame.Rect(
                    r.right - right_pad - mark_w, r.y + 6, mark_w, mark_h)
                self._mark_read_kind = 'messages'
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_TAB_BG,
                                 self._mark_read_rect, border_radius=5)
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER,
                                 self._mark_read_rect, 1, border_radius=5)
                mark = self._activity_small_font.render('Mark all read', True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
                self.window.blit(mark, mark.get_rect(center=self._mark_read_rect.center))

            if self._mark_read_rect:
                self._mark_read_hit_rect = self._mark_read_rect.copy()

            if not rows:
                empty_rect = pygame.Rect(r.x + 12, content_top + 8,
                                         r.w - 24, r.bottom - content_top - 18)
                self._draw_wrapped_text(empty, self._activity_font,
                                        settings.KINGDOM_ACTIVITY_DIM_CLR, empty_rect)
                return

            row_h = settings.KINGDOM_ACTIVITY_ROW_H
            y = content_top
            max_bottom = r.bottom - 10
            visible_count = self._activity_visible_count()
            offset = self._clamp_activity_scroll(self._activity_tab, len(rows), visible_count)
            scrolling = len(rows) > visible_count
            row_right_pad = 30 if scrolling else 20
            self._draw_activity_scrollbar(r, content_top, max_bottom,
                                          len(rows), visible_count, offset)
            for item in rows[offset:offset + visible_count]:
                if y + row_h > max_bottom:
                    break
                rr = pygame.Rect(r.x + 10, y, r.w - row_right_pad, row_h - 4)
                self._activity_row_rects.append((rr, item))
                self._draw_activity_row(rr, item)
                y += row_h
        finally:
            self.window.set_clip(old_clip)

    def _draw_activity_row(self, rect, item):
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_ROW_BG, rect, border_radius=6)
        pygame.draw.rect(self.window, (90, 85, 105), rect, 1, border_radius=6)
        title, detail, good = self._format_activity_item(item)
        navigates_to_land = bool(
            item.get('land_id')
            and not self._is_conversation_item(item)
            and not self._is_message_item(item)
        )
        max_w = rect.w - (34 if navigates_to_land else 16)
        title = self._fit_text(title, self._activity_font, max_w)
        detail = self._fit_text(detail, self._activity_small_font, max_w)
        if self._is_conversation_item(item):
            unread = int(item.get('unread_count') or 0) > 0
            title_clr = settings.KINGDOM_INFO_CLR if unread else settings.KINGDOM_ACTIVITY_TEXT_CLR
        elif self._is_message_item(item):
            unread = (item.get('recipient_user_id') == self._current_user_id()
                      and not item.get('seen_by_recipient'))
            title_clr = settings.KINGDOM_INFO_CLR if unread else settings.KINGDOM_ACTIVITY_TEXT_CLR
        elif item.get('activity_tone') == 'neutral':
            title_clr = settings.KINGDOM_ACTIVITY_TEXT_CLR
        else:
            title_clr = (settings.KINGDOM_ACTIVITY_GOOD_CLR if good else settings.KINGDOM_ACTIVITY_BAD_CLR)
        title_surf = self._activity_font.render(title, True, title_clr)
        detail_surf = self._activity_small_font.render(
            detail, True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
        title_y = rect.y + 6
        detail_y = title_y + title_surf.get_height() + 4
        self.window.blit(title_surf, (rect.x + 8, title_y))

        land = self._activity_small_font.render(self._activity_land_label(item), True,
                                                settings.KINGDOM_ACTIVITY_DIM_CLR)
        land_y = rect.bottom - land.get_height() - 5
        if detail_y + detail_surf.get_height() + 3 <= land_y:
            self.window.blit(detail_surf, (rect.x + 8, detail_y))
        self.window.blit(land, (rect.x + 8, land_y))
        if navigates_to_land:
            cue = self._activity_title_font.render(
                '\u203a', True, settings.KINGDOM_INFO_CLR)
            self.window.blit(cue, cue.get_rect(
                midright=(rect.right - 8, rect.centery)))

    def _draw_wrapped_text(self, text, font, color, rect, line_gap=2):
        """Draw text wrapped inside rect and clipped to rect bounds."""
        old_clip = self.window.get_clip()
        self.window.set_clip(rect.clip(old_clip))
        try:
            line_h = font.get_height() + line_gap
            max_lines = max(1, rect.h // line_h)
            for i, line in enumerate(self._wrap_text(text, font, rect.w, max_lines=max_lines)):
                surf = font.render(line, True, color)
                self.window.blit(surf, (rect.x, rect.y + i * line_h))
        finally:
            self.window.set_clip(old_clip)

    def _wrap_text(self, text, font, max_width, max_lines=None):
        """Return text lines that fit max_width, adding ellipsis if truncated."""
        words = str(text).split()
        if not words:
            return ['']
        lines = []
        current = ''
        for word in words:
            candidate = word if not current else f'{current} {word}'
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = word
                if font.size(current)[0] > max_width:
                    lines.append(self._fit_text(current, font, max_width))
                    current = ''
            else:
                lines.append(self._fit_text(word, font, max_width))
                current = ''
            if max_lines and len(lines) >= max_lines:
                break
        if current and (not max_lines or len(lines) < max_lines):
            lines.append(current)
        if max_lines and len(lines) >= max_lines and words:
            lines[-1] = self._fit_text(lines[-1], font, max_width)
        return lines or ['']

    def _fit_text(self, text, font, max_width):
        if font.size(text)[0] <= max_width:
            return text
        ellipsis = '...'
        clipped = text
        while clipped and font.size(clipped + ellipsis)[0] > max_width:
            clipped = clipped[:-1]
        return (clipped + ellipsis) if clipped else ellipsis

    def _format_activity_item(self, item):
        if self._is_conversation_item(item):
            return self._format_conversation_item(item)
        if item.get('activity_title') is not None or item.get('activity_detail') is not None:
            title = item.get('activity_title') or 'Kingdom event'
            detail = item.get('activity_detail') or ''
            tone = item.get('activity_tone') or 'neutral'
            return title, detail, tone != 'bad'
        if self._is_message_item(item):
            return self._format_message_item(item)
        if self._is_kingdom_event_item(item):
            return self._format_kingdom_event_item(item)
        attacker = item.get('attacker_username') or item.get('attacker_name') or 'Unknown'
        defender = item.get('defender_username') or 'AI'
        result = item.get('result')
        role = item.get('role')
        current_user_id = self._current_user_id()
        is_attacker = current_user_id is not None and item.get('attacker_user_id') == current_user_id
        is_defender = current_user_id is not None and item.get('defender_user_id') == current_user_id
        is_attacker_perspective = role == 'attacker' if role else is_attacker
        is_defender_perspective = role == 'defender' if role else is_defender
        if result == 'attacker_won':
            if is_defender_perspective:
                title = f'{attacker} conquered your land'
                deleted = item.get('kingdom_deleted_name')
                detail = (f'{deleted} had no lands left and was dissolved.' if deleted
                          else (self._loot_detail(item, 'Loot lost')
                          or self._card_pair_detail(
                              item, 'card_won_suit', 'card_won_rank', 'Loot lost')
                          or self._card_pair_detail(
                              item, 'card_lost_suit', 'card_lost_rank', 'Loot lost')
                          or 'Land ownership changed.'))
                return title, detail, False
            if is_attacker_perspective:
                title = f'You conquered {defender}'
                detail = self._card_detail(item, won=True) or 'Attack succeeded.'
                return title, detail, True
            title = f'{attacker} conquered {defender}'
            detail = self._card_detail(item, won=True) or 'Attack succeeded.'
            return title, detail, True
        if result == 'defender_won':
            if is_defender_perspective:
                title = f'{attacker} failed to conquer you'
                detail = (
                    self._loot_detail(item, 'Loot gained')
                    or self._card_pair_detail(
                        item, 'card_lost_suit', 'card_lost_rank', 'Loot gained')
                    or self._card_pair_detail(
                        item, 'card_won_suit', 'card_won_rank', 'Loot gained')
                    or 'Your defence held.'
                )
                return title, detail, True
            if is_attacker_perspective:
                title = f'Your attack on {defender} failed'
                detail = self._card_detail(item, lost=True) or 'Attack failed.'
                return title, detail, False
            title = f'{attacker} failed against {defender}'
            detail = self._card_detail(item, lost=True) or 'Attack failed.'
            return title, detail, False
        if is_defender_perspective:
            title = f'{attacker} failed to conquer you'
        elif is_attacker_perspective:
            title = f'Attack on {defender} updated'
        else:
            title = f'{attacker} vs {defender}'
        detail = 'Battle result updated.'
        return title, detail, False

    def _is_message_item(self, item):
        return 'sender_user_id' in item and 'recipient_user_id' in item and 'message' in item

    def _is_conversation_item(self, item):
        return isinstance(item, dict) and 'other_user_id' in item and 'last_message' in item

    def _format_message_item(self, item):
        current_user_id = self._current_user_id()
        is_sent = item.get('sender_user_id') == current_user_id
        other = item.get('recipient_username') if is_sent else item.get('sender_username')
        other = other or 'Unknown'
        title = f'To {other}' if is_sent else f'From {other}'
        detail = item.get('message') or ''
        return title, detail, True

    def _format_conversation_item(self, item):
        other = item.get('other_username') or 'Unknown'
        unread = int(item.get('unread_count') or 0)
        title = f'{other}'
        if unread > 0:
            title = f'● {other}'
        last = item.get('last_message') or ''
        last_sender = item.get('last_sender_user_id')
        if last_sender == self._current_user_id():
            seen = item.get('last_seen_by_recipient')
            tick = ' ✓✓' if seen else ' ✓'
            detail = f'You: {last}{tick}'
        else:
            detail = last
        return title, detail, True

    @staticmethod
    def _format_relative_time(timestamp_iso):
        """Return a compact relative-time label like '2m', '1h', 'yest.', 'Mar 3'."""
        if not timestamp_iso:
            return ''
        try:
            from datetime import datetime, timezone
            ts = timestamp_iso
            # Python's fromisoformat doesn't parse trailing Z prior to 3.11.
            if ts.endswith('Z'):
                ts = ts[:-1] + '+00:00'
            then = datetime.fromisoformat(ts)
            if then.tzinfo is None:
                then = then.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = now - then
            secs = int(delta.total_seconds())
            if secs < 45:
                return 'now'
            if secs < 3600:
                return f'{max(1, secs // 60)}m'
            if secs < 86400:
                return f'{secs // 3600}h'
            if secs < 86400 * 2:
                return 'yest.'
            if secs < 86400 * 7:
                return f'{secs // 86400}d'
            return then.strftime('%b %-d') if hasattr(then, 'strftime') else then.isoformat()[:10]
        except Exception:
            return ''

    def _is_kingdom_event_item(self, item):
        """True for KingdomNotification rows (have ``kind`` + ``payload``)."""
        return ('kind' in item and 'payload' in item
                and 'attacker_user_id' not in item
                and 'sender_user_id' not in item)

    def _format_kingdom_event_item(self, item):
        kind = item.get('kind') or ''
        payload = item.get('payload') or {}
        if kind == 'map_regenerated':
            return (
                'The realm has been redrawn',
                'Territory and kingdom progress reset; account value was preserved.',
                True,
            )
        if kind == 'region_champion_gained':
            name = payload.get('region_name') or 'a historic region'
            count = int(payload.get('land_count') or 0)
            return (f'Champion of {name}',
                    f'You took the lead with {count} lands.', True)
        if kind == 'region_champion_lost':
            name = payload.get('region_name') or 'a historic region'
            payout = int(payload.get('tribute_paid') or 0)
            detail = ('Your accrued tribute was paid automatically.' if not payout
                      else f'{payout} tribute paid automatically.')
            return (f'Champion title lost: {name}', detail, False)
        if kind == 'region_tribute_collected':
            amount = int(payload.get('amount') or 0)
            return ('Regional tribute collected',
                    f'{amount} gold included in Collect All.', True)
        if kind == 'xp_gained':
            amount = int(payload.get('amount') or 0)
            reason = payload.get('reason') or 'conquer'
            level = int(payload.get('level') or 0)
            title = f'+{amount} XP gained'
            detail = f'Kingdom level {level} ({reason}).' if level else f'Earned from {reason}.'
            return title, detail, True
        if kind == 'level_up':
            new_level = int(payload.get('new_level') or 0)
            sp = int(payload.get('sp_gained') or 0)
            title = f'Kingdom reached level {new_level}!'
            detail = f'+{sp} skill point{"s" if sp != 1 else ""}.' if sp else 'Level up!'
            return title, detail, True
        if kind == 'kingdoms_merged':
            absorbed = payload.get('absorbed_kingdom_name') or 'A kingdom'
            lands = int(payload.get('absorbed_lands') or 0)
            xp = int(payload.get('xp_awarded') or 0)
            title = 'Kingdoms merged'
            detail = f'{absorbed} absorbed ({lands} lands, +{xp} XP).'
            return title, detail, True
        if kind == 'card_looted':
            rank = payload.get('rank') or '?'
            suit = payload.get('suit') or 'card'
            defender = payload.get('defender_name')
            if not defender and payload.get('is_ai_defender'):
                defender = 'AI defender'
            title = 'Card looted'
            detail = f'{rank} of {suit} lost to {defender or "the defender"}.'
            return title, detail, False
        if kind == 'shield_expired':
            name = payload.get('kingdom_name') or 'Your kingdom'
            title = 'Shield expired'
            detail = f'{name} can be attacked again.'
            return title, detail, False
        if kind == 'kingdom_dissolved':
            name = payload.get('kingdom_name') or 'Your kingdom'
            title = 'Kingdom dissolved'
            detail = f'{name} had no lands left.'
            return title, detail, False
        if kind == 'skill_downgraded':
            skill = payload.get('skill') or 'A skill'
            title = 'Skill downgraded'
            detail = f'{skill} level decreased.'
            return title, detail, False
        # Generic fallback
        title = (kind or 'Kingdom event').replace('_', ' ').capitalize()
        detail = ''
        return title, detail, True

    def _current_user_id(self):
        data = getattr(self.state, 'user_dict', None) or {}
        return data.get('id') or data.get('user_id')

    def _card_detail(self, item, won=False, lost=False):
        if won:
            return self._loot_detail(item, 'Loot gained') or self._card_pair_detail(
                item, 'card_won_suit', 'card_won_rank', 'Loot gained')
        if lost:
            return self._loot_detail(item, 'Loot lost') or self._card_pair_detail(
                item, 'card_lost_suit', 'card_lost_rank', 'Loot lost')
        return ''

    def _loot_detail(self, item, label):
        cards = item.get('loot_cards') or []
        count = int(item.get('loot_card_count') or len(cards or []))
        if not count:
            return ''
        first = cards[0] if cards else {}
        first_label = ''
        if isinstance(first, dict) and first.get('rank') and first.get('suit'):
            first_label = f" ({first.get('rank')} of {first.get('suit')}"
            if count > 1:
                first_label += f' + {count - 1} more'
            first_label += ')'
        noun = 'card' if count == 1 else 'cards'
        return f'{label}: {count} {noun}{first_label}'

    def _card_pair_detail(self, item, suit_key, rank_key, label):
        suit = item.get(suit_key)
        rank = item.get(rank_key)
        if suit and rank:
            return f'{label}: {rank} of {suit}'
        return ''

    def _activity_land_label(self, item):
        if item.get('activity_land_label'):
            return str(item.get('activity_land_label'))
        if self._is_conversation_item(item):
            rel = self._format_relative_time(item.get('last_timestamp'))
            unread = int(item.get('unread_count') or 0)
            parts = []
            if rel:
                parts.append(rel)
            col = item.get('last_land_col')
            row = item.get('last_land_row')
            land_id = item.get('last_land_id')
            if col is not None and row is not None:
                parts.append(f'Land ({col}, {row})')
            elif land_id is not None:
                parts.append(f'Land #{land_id}')
            if unread > 0:
                parts.append(f'({unread} unread)')
            return '  ·  '.join(parts) if parts else ''
        col = item.get('land_col')
        row = item.get('land_row')
        land_id = item.get('land_id')
        payload = item.get('payload') if isinstance(item.get('payload'), dict) else {}
        if col is None:
            col = payload.get('land_col')
        if row is None:
            row = payload.get('land_row')
        if land_id is None:
            land_id = payload.get('land_id')
        rel = self._format_relative_time(item.get('timestamp'))
        base = ''
        if col is not None and row is not None:
            base = f'Land ({col}, {row})'
        elif land_id is not None:
            base = f'Land #{land_id}'
        elif self._is_kingdom_event_item(item):
            kingdom_name = payload.get('kingdom_name') or payload.get('absorbed_kingdom_name')
            base = kingdom_name or 'Kingdom event'
        else:
            base = 'Kingdom land'
        return f'{rel}  ·  {base}' if rel else base

    def _draw_kingdom_chip(self):
        """Draw the kingdom selector chip on the left side of the header.

        Shows the currently-focused kingdom's sigil + name + prev/next
        chevrons + a gear icon that jumps to the kingdom config screen.
        """
        # Reset click targets each frame.
        self._kingdom_chip_rect = None
        self._kingdom_chip_prev_rect = None
        self._kingdom_chip_next_rect = None
        self._kingdom_chip_gear_rect = None

        kingdoms = self._kingdoms_list()
        if not kingdoms:
            return
        self._clamp_kingdom_chip_index()
        kingdom = self._current_chip_kingdom()
        if not kingdom:
            return

        font = self._kingdom_chip_font
        small_font = self._kingdom_chip_small_font
        name = str(kingdom.get('name') or f'Kingdom #{kingdom.get("id")}')

        # Level / XP progression (from serialize_kingdom_config).
        level = int(kingdom.get('level') or 1)
        level_max = int(kingdom.get('level_max') or level)
        xp_into = float(kingdom.get('xp_into_level') or 0.0)
        xp_next = float(kingdom.get('xp_for_next_level') or 0.0)
        at_max = level >= level_max or xp_next <= 0
        xp_frac = 1.0 if at_max else (
            max(0.0, min(1.0, xp_into / xp_next)) if xp_next else 0.0)
        lv_text = 'MAX' if at_max else f'Lv {level}'

        # Taller two-line "hero" chip: line 1 = sigil + name + counter,
        # line 2 = level + XP progress bar, so the active kingdom reads as
        # the player's identity rather than a small selector.
        chip_h = max(int(0.056 * _SH),
                     font.get_height() + small_font.get_height() + 12)
        sigil_sz = max(18, int(chip_h * 0.62))
        portrait_ui = self._mobile_ui and _SH > _SW
        chevron_w = (max(14, int(chip_h * 0.42))
                     if len(kingdoms) > 1 else 0)
        gear_sz = max(16, int(chip_h * 0.52))
        pad_x = max(6, int(0.006 * _SW))

        # Truncate name to fit a reasonable budget.
        max_name_w = int((0.25 if portrait_ui else 0.13) * _SW)
        truncated = name
        if font.size(truncated)[0] > max_name_w:
            while truncated and font.size(truncated + '…')[0] > max_name_w:
                truncated = truncated[:-1]
            truncated = (truncated + '…') if truncated else '…'
        name_surf = font.render(truncated, True, settings.KINGDOM_INFO_CLR)
        position_label = f'{self._kingdom_chip_index + 1}/{len(kingdoms)}'
        pos_surf = small_font.render(position_label, True,
                                     settings.KINGDOM_ACTIVITY_DIM_CLR)
        lv_surf = small_font.render(lv_text, True, (232, 208, 150))

        line1_w = name_surf.get_width() + 6 + pos_surf.get_width()
        min_bar = int(0.055 * _SW)
        block_w = max(line1_w, lv_surf.get_width() + 6 + min_bar)

        chip_w = (pad_x + sigil_sz + 6 + chevron_w + 4 + block_w
                  + 6 + chevron_w + 6 + gear_sz + pad_x)

        # Anchor the chip just to the right of the box's left pad, vertically
        # centred in the header.
        chip_x = self._header_rect.x + 6
        chip_y = (self._header_rect.y + 2 if portrait_ui else
                  self._header_rect.y + max(
                      0, (self._header_rect.h - chip_h) // 2))
        chip_rect = pygame.Rect(chip_x, chip_y, chip_w, chip_h)
        self._kingdom_chip_rect = chip_rect

        # Background pill.
        radius = min(chip_h // 2, int(0.014 * _SH))
        bg = pygame.Surface((chip_rect.w, chip_rect.h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (20, 18, 14, 210), bg.get_rect(),
                         border_radius=radius)
        pygame.draw.rect(bg, settings.KINGDOM_MAP_FRAME_BORDER, bg.get_rect(),
                         1, border_radius=radius)
        self.window.blit(bg, chip_rect.topleft)

        cursor_x = chip_x + pad_x

        # Sigil glyph tinted with the kingdom's accent.
        style = kingdom.get('style') or {}
        sigil_key = style.get('sigil_key') or (
            settings.HEX_DEFAULT_OWNER_STYLE.get('sigil_key'))
        color_key = style.get('color_key') or (
            settings.HEX_DEFAULT_OWNER_STYLE.get('color_key'))
        palette_entry = (settings.KINGDOM_COLOR_PALETTE.get(color_key)
                         if color_key else None)
        accent = ((palette_entry or {}).get('accent_rgb')
                  or settings.HEX_MINE_BORDER_HIGHLIGHT)
        sigil_surf = None
        if sigil_key and sigil_key != 'sigil_none':
            try:
                sigil_surf = sigil_cosmetics.render_sigil(
                    sigil_key, sigil_sz, accent)
            except Exception:
                sigil_surf = None
        sigil_cy = chip_y + chip_h // 2
        sigil_y = sigil_cy - sigil_sz // 2
        if sigil_surf is not None:
            self.window.blit(sigil_surf, (cursor_x, sigil_y))
        else:
            pygame.draw.circle(self.window, accent,
                               (cursor_x + sigil_sz // 2, sigil_cy),
                               sigil_sz // 2)
            pygame.draw.circle(self.window, (24, 18, 6),
                               (cursor_x + sigil_sz // 2, sigil_cy),
                               sigil_sz // 2, 1)
        cursor_x += sigil_sz + 6

        # Prev chevron (spans both lines).
        prev_rect = pygame.Rect(cursor_x, chip_y + 2, chevron_w, chip_h - 4)
        if len(kingdoms) > 1:
            self._kingdom_chip_prev_rect = prev_rect
            self._draw_chip_chevron(prev_rect, '‹')
        cursor_x += chevron_w + 4

        # Two-line block: name + counter (line 1), level + XP bar (line 2).
        block_x = cursor_x
        line1_cy = chip_y + int(chip_h * 0.31)
        line2_cy = chip_y + int(chip_h * 0.70)
        self.window.blit(name_surf,
                         name_surf.get_rect(midleft=(block_x, line1_cy)))
        self.window.blit(pos_surf, pos_surf.get_rect(
            midleft=(block_x + name_surf.get_width() + 6, line1_cy)))

        self.window.blit(lv_surf, lv_surf.get_rect(midleft=(block_x, line2_cy)))
        bar_x = block_x + lv_surf.get_width() + 6
        bar_w = max(24, block_x + block_w - bar_x)
        bar_h = max(3, int(chip_h * 0.11))
        bar_y = line2_cy - bar_h // 2
        pygame.draw.rect(self.window, (46, 40, 30),
                         (bar_x, bar_y, bar_w, bar_h), border_radius=bar_h // 2)
        fill_w = int(bar_w * xp_frac)
        if fill_w > 0:
            fill_clr = (230, 200, 110) if at_max else (150, 205, 140)
            pygame.draw.rect(self.window, fill_clr,
                             (bar_x, bar_y, fill_w, bar_h),
                             border_radius=bar_h // 2)
        pygame.draw.rect(self.window, (96, 86, 64),
                         (bar_x, bar_y, bar_w, bar_h), 1, border_radius=bar_h // 2)
        cursor_x = block_x + block_w + 6

        # Next chevron.
        next_rect = pygame.Rect(cursor_x, chip_y + 2, chevron_w, chip_h - 4)
        if len(kingdoms) > 1:
            self._kingdom_chip_next_rect = next_rect
            self._draw_chip_chevron(next_rect, '›')
        cursor_x += chevron_w + 6

        # Edit icon (same asset used by defence/conquer config) to open
        # kingdom_config for the currently-focused kingdom.
        gear_rect = pygame.Rect(cursor_x, chip_y + (chip_h - gear_sz) // 2,
                                gear_sz, gear_sz)
        self._kingdom_chip_gear_rect = gear_rect
        self._draw_chip_edit_icon(gear_rect)

    def _draw_chip_chevron(self, rect, glyph):
        mouse_pos = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse_pos)
        clr = (255, 230, 150) if hovered else (200, 188, 158)
        font = self._kingdom_chip_font
        surf = font.render(glyph, True, clr)
        self.window.blit(surf, surf.get_rect(center=rect.center))

    def _draw_chip_edit_icon(self, rect):
        """Render the kingdom-config edit affordance using the shared icon.

        Matches the defence / conquer screens' section-title edit button
        (asset ``img/dialogue_box/icons/edit.png`` plus a yellow hover
        glow), so the same visual means "open config for this thing"
        across the kingdom flow.
        """
        mouse_pos = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse_pos)
        if hovered:
            glow = pygame.Surface((rect.w + 6, rect.h + 6), pygame.SRCALPHA)
            glow.fill((255, 255, 200, 50))
            self.window.blit(glow, (rect.x - 3, rect.y - 3))
        if self._kingdom_chip_edit_icon is not None:
            # Cache the scaled icon per chip height so we don't smoothscale
            # every frame.
            if (self._kingdom_chip_edit_icon_scaled is None
                    or self._kingdom_chip_edit_icon_scaled_sz != rect.w):
                self._kingdom_chip_edit_icon_scaled = (
                    pygame.transform.smoothscale(
                        self._kingdom_chip_edit_icon, (rect.w, rect.h)))
                self._kingdom_chip_edit_icon_scaled_sz = rect.w
            self.window.blit(self._kingdom_chip_edit_icon_scaled,
                             rect.topleft)
            return
        # Fallback if the asset failed to load: simple pencil tip.
        clr = (245, 224, 158) if hovered else (210, 196, 152)
        cx, cy = rect.center
        r = int(rect.w * 0.36)
        pygame.draw.line(self.window, clr,
                         (cx - r, cy + r), (cx + r, cy - r), 2)
        pygame.draw.line(self.window, clr,
                         (cx + r - 1, cy - r + 1), (cx + r + 2, cy - r - 2), 2)

    def _draw_info_bar(self):
        """Draw production rate / lands count bar at top of box, below title."""
        # Reset clickable rect each frame
        self._collect_all_rect = None
        self._collect_all_enabled = False
        if not self._map_data:
            return

        rate = self._map_data.get('my_total_gold_rate', 0)
        effective_rate = self._map_data.get('my_effective_gold_rate', rate)
        count = self._map_data.get('my_lands_count', 0)

        # Aggregate vault stats across all owned kingdoms
        my_kingdoms = self._map_data.get('my_kingdoms') or []
        num_kingdoms = len(my_kingdoms)
        pending_total = 0.0
        collectable_total = 0
        collectable_main_boosters = 0
        collectable_side_boosters = 0
        any_full = False
        any_near_full = False
        near_ratio = float(getattr(settings, 'KINGDOM_VAULT_NEAR_FULL_RATIO', 0.80))
        for k in my_kingdoms:
            pending = float(k.get('pending_gold') or 0.0)
            cap = float(k.get('vault_cap') or 0.0)
            pending_total += pending
            collectable_total += int(pending)
            if cap > 0:
                ratio = pending / cap if cap else 0
                if ratio >= 0.999:
                    any_full = True
                elif ratio >= near_ratio:
                    any_near_full = True
            production = k.get('production') if isinstance(k.get('production'), dict) else {}
            main_item = production.get('main_booster') if isinstance(production.get('main_booster'), dict) else {}
            side_item = production.get('side_booster') if isinstance(production.get('side_booster'), dict) else {}
            main_pending = int(main_item.get('pending', k.get('pending_main_boosters') or 0) or 0)
            side_pending = int(side_item.get('pending', k.get('pending_side_boosters') or 0) or 0)
            collectable_main_boosters += main_pending
            collectable_side_boosters += side_pending
            # NB: ``any_full`` only signals "gold production is stalled".
            # Booster packs being ready is normal/desired, not a warning,
            # so we deliberately do not set ``any_full`` for boosters.

        base_rate = float(rate or 0)
        bonus_rate = max(0.0, float(effective_rate or 0) - base_rate)
        kingdom_word = 'kingdom' if num_kingdoms == 1 else 'kingdoms'
        land_count = int(count or 0)
        land_word = 'land' if land_count == 1 else 'lands'
        header_base = (
            f'{num_kingdoms} {kingdom_word}  ·  '
            f'{land_count} {land_word}  ·  '
            f'{base_rate:.1f} gold/hr'
        )
        if self._cooldown > 0:
            hours = self._cooldown // 3600
            mins = (self._cooldown % 3600) // 60
            cooldown_text = f'  conquer cooldown: {hours}h {mins}m'
        else:
            cooldown_text = ''

        # Color gold-rate-bearing text red when any vault is full (production stalled)
        info_clr = (220, 90, 90) if any_full else settings.KINGDOM_INFO_CLR
        bonus_clr = getattr(settings, 'KINGDOM_CONFIG_GOOD_CLR', (132, 220, 142))
        segments = [
            self._info_font.render(header_base, True, info_clr),
            self._info_font.render(f' +{bonus_rate:.1f}', True, bonus_clr),
        ]
        if cooldown_text:
            segments.append(self._info_font.render(cooldown_text, True, info_clr))
        px = settings.KINGDOM_INFO_PAD_X
        py = settings.KINGDOM_INFO_PAD_Y
        text_w = sum(s.get_width() for s in segments)
        text_h = max((s.get_height() for s in segments), default=0)
        bw = text_w + px * 2
        bh = text_h + py * 2

        mobile_ui = settings.TOUCH_TARGET_MIN > 0
        portrait_ui = mobile_ui and _SH > _SW
        info_left_bound = self._header_rect.x
        info_right_bound = self._header_rect.right
        if portrait_ui:
            compact_font = settings.get_font(
                max(8, int(settings.FS_TINY * 0.78)), bold=True)
            max_bw = max(80, int(self._header_rect.w * 0.52))
            short_base = f'{land_count} {land_word} · {base_rate:.0f}g/h'
            segments = [
                compact_font.render(short_base, True, info_clr),
                compact_font.render(f'+{bonus_rate:.0f}', True, bonus_clr),
            ]
            text_w = sum(s.get_width() for s in segments)
            text_h = max((s.get_height() for s in segments), default=0)
            bw = min(text_w + px * 2, max_bw)
            bh = text_h + py * 2
        elif mobile_ui:
            # The mobile header also contains the kingdom chip on the left
            # and the Collect button on the right. Keep the info pill in the
            # middle lane so those controls never paint on top of each other.
            info_left_bound = self._header_rect.x + int(0.28 * _SW)
            if my_kingdoms:
                info_right_bound -= int(0.25 * _SW)
            max_bw = max(80, info_right_bound - info_left_bound)
            if bw > max_bw:
                short_base = f'{land_count} {land_word}  ·  {base_rate:.1f}g/hr'
                segments = [
                    self._info_font.render(short_base, True, info_clr),
                    self._info_font.render(f' +{bonus_rate:.1f}', True, bonus_clr),
                ]
                text_w = sum(s.get_width() for s in segments)
                text_h = max((s.get_height() for s in segments), default=0)
                bw = min(text_w + px * 2, max_bw)
                bh = text_h + py * 2

        box = pygame.Surface((bw, bh), pygame.SRCALPHA)
        box.fill(settings.KINGDOM_INFO_BG_CLR)
        if portrait_ui:
            bar_x = self._header_rect.x
        elif mobile_ui:
            lane_w = max(1, info_right_bound - info_left_bound)
            bar_x = info_left_bound + max(0, (lane_w - bw) // 2)
        else:
            bar_x = self._header_rect.x + (self._header_rect.w - bw) // 2
        bar_y = (self._header_rect.y + int(0.085 * _SH)
                 if portrait_ui else
                 self._header_rect.y + self._title_surf.get_height()
                 + int(0.006 * _SH))
        self.window.blit(box, (bar_x, bar_y))
        tx = bar_x + px
        ty = bar_y + py
        for surf in segments:
            self.window.blit(surf, (tx, ty + (text_h - surf.get_height()) // 2))
            tx += surf.get_width()

        # Collect All button (right of info bar)
        if my_kingdoms:
            # Server collects ``int(pending)`` per kingdom, then sums those
            # integers. Mirror that here so the button amount reflects what
            # would actually be collected right now.
            collectable = (
                collectable_total > 0
                or collectable_main_boosters > 0
                or collectable_side_boosters > 0
            )
            parts = []
            if collectable_total > 0:
                parts.append(f'{collectable_total}g')
            if collectable_main_boosters:
                parts.append(f'{collectable_main_boosters} main')
            if collectable_side_boosters:
                parts.append(f'{collectable_side_boosters} side')
            label = 'Collect All' if not parts else 'Collect All: ' + ' + '.join(parts)
            if mobile_ui:
                label = 'Collect' if not parts else 'Collect ' + ' + '.join(parts)
            if any_full:
                label += '  (FULL!)'
            btn_font = (settings.get_font(
                max(8, int(settings.FS_TINY * 0.78)), bold=True)
                if portrait_ui else self._nav_font)
            max_btn_text_w = (int(0.32 * _SW) if portrait_ui else
                              int(0.22 * _SW) if mobile_ui else None)
            if max_btn_text_w:
                label = self._fit_text(label, btn_font, max_btn_text_w)
            btn_surf = btn_font.render(label, True, (240, 230, 180))
            bpx = int(0.012 * _SW)
            bpy = int(0.006 * _SH)
            btn_w = btn_surf.get_width() + bpx * 2
            if portrait_ui:
                btn_w = min(btn_w, int(0.36 * _SW))
            elif mobile_ui:
                btn_w = min(btn_w, int(0.24 * _SW))
            btn_h = max(bh, btn_surf.get_height() + bpy * 2)
            btn_x = bar_x + bw + int(0.010 * _SW)
            # Keep button inside header area; if overflow, place to right of title within header
            max_right = (self._header_rect.right if portrait_ui else
                         self._header_rect.right - self._btn_close_rect.w
                         - int(0.012 * _SW))
            if btn_x + btn_w > max_right:
                btn_x = max(self._header_rect.x, max_right - btn_w)
            btn_y = bar_y + (bh - btn_h) // 2
            rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

            mx, my = pygame.mouse.get_pos()
            hovered = rect.collidepoint(mx, my) and collectable
            if not collectable:
                bg = (42, 40, 42, 205)
                border = (120, 110, 100)
            elif any_full:
                bg = (140, 50, 50, 230) if hovered else (110, 40, 40, 210)
                border = (220, 120, 120)
            elif any_near_full:
                bg = (130, 110, 50, 230) if hovered else (100, 85, 40, 210)
                border = (220, 200, 120)
            else:
                bg = (60, 80, 60, 230) if hovered else (45, 60, 45, 210)
                border = (160, 200, 160)
            bsurf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(bsurf, bg, bsurf.get_rect(), border_radius=6)
            pygame.draw.rect(bsurf, border, bsurf.get_rect(), 1, border_radius=6)
            self.window.blit(bsurf, rect.topleft)
            self.window.blit(btn_surf, btn_surf.get_rect(center=rect.center))
            self._collect_all_rect = rect
            self._collect_all_enabled = collectable

    def _draw_nav_buttons(self):
        """Draw zoom/recenter controls with mobile-safe hit rectangles."""
        self._nav_hit_rects = {}
        mx, my = pygame.mouse.get_pos()
        for key, rect in self._nav_rects.items():
            hit = rect.copy()
            if self._mobile_ui:
                hit.inflate_ip(
                    max(0, settings.TOUCH_TARGET_MIN - hit.w),
                    max(0, settings.TOUCH_TARGET_MIN - hit.h),
                )
                hit.clamp_ip(self._map_viewport_rect)
            self._nav_hit_rects[key] = hit
            hovered = hit.collidepoint(mx, my)
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(surf, settings.NAV_BTN_BG_CLR, surf.get_rect(),
                             border_radius=4)
            pygame.draw.rect(surf, settings.NAV_BTN_BORDER_CLR, surf.get_rect(), 1,
                             border_radius=4)
            self.window.blit(surf, rect.topleft)
            clr = settings.NAV_BTN_HOVER_CLR if hovered else settings.NAV_BTN_TEXT_CLR
            label = self._nav_labels.get(key, '?')
            if key == 'recenter':
                cx, cy = rect.center
                radius = max(4, int(rect.w * 0.22))
                pygame.draw.circle(self.window, clr, (cx, cy), radius, 1)
                pygame.draw.circle(self.window, clr, (cx, cy), 2)
                arm = max(3, int(rect.w * 0.12))
                pygame.draw.line(self.window, clr,
                                 (cx, cy - radius - arm), (cx, cy - radius + 1), 1)
                pygame.draw.line(self.window, clr,
                                 (cx, cy + radius - 1), (cx, cy + radius + arm), 1)
                pygame.draw.line(self.window, clr,
                                 (cx - radius - arm, cy), (cx - radius + 1, cy), 1)
                pygame.draw.line(self.window, clr,
                                 (cx + radius - 1, cy), (cx + radius + arm, cy), 1)
            else:
                lbl = self._nav_font.render(label, True, clr)
                self.window.blit(lbl, lbl.get_rect(center=rect.center))

    def _nav_key_at_pos(self, pos):
        rects = getattr(self, '_nav_hit_rects', None) or getattr(
            self, '_nav_rects', {})
        for key, rect in rects.items():
            if rect.collidepoint(pos):
                return key
        return None

    def _minimap_contains_pos(self, pos):
        hm = getattr(self, '_hex_map', None)
        rect = getattr(hm, '_minimap_rect', None)
        return bool(rect and rect.collidepoint(pos))

    def _map_mode_key_at_pos(self, pos):
        for key, rect in (getattr(self, '_map_mode_rects', None) or {}).items():
            if rect.collidepoint(pos):
                return key
        return None

    def _map_toolbar_toggle_at_pos(self, pos):
        layers_rect = getattr(self, '_layers_toggle_rect', None)
        if layers_rect and layers_rect.collidepoint(pos):
            return 'layers_toggle'
        activity_rect = getattr(self, '_activity_toggle_rect', None)
        if activity_rect and activity_rect.collidepoint(pos):
            return 'activity_toggle'
        return None

    def _cancel_hex_map_drag(self):
        hm = getattr(self, '_hex_map', None)
        cancel = getattr(hm, 'cancel_drag', None)
        if callable(cancel):
            cancel()

    def _activate_nav_control(self, key):
        if not self._hex_map:
            return False
        if key == 'zoom_in':
            self._hex_map.zoom_in()
            return True
        if key == 'zoom_out':
            self._hex_map.zoom_out()
            return True
        if key == 'recenter':
            if self._recommended_tutorial_land_pending():
                return self._focus_recommended_tutorial_land() is not None
            kingdom = self._current_chip_kingdom()
            if kingdom:
                self._focus_kingdom_on_map(kingdom)
            else:
                self._focus_largest_kingdom_component()
            return True
        return False

    def _begin_map_control_press(self, pos):
        key = self._nav_key_at_pos(pos)
        if key:
            self._map_control_press = ('nav', key)
            self._cancel_hex_map_drag()
            return True
        if self._minimap_contains_pos(pos):
            self._map_control_press = ('minimap', None)
            self._cancel_hex_map_drag()
            return True
        mode_key = self._map_mode_key_at_pos(pos)
        if mode_key:
            self._map_control_press = ('mode', mode_key)
            self._cancel_hex_map_drag()
            return True
        toggle_key = self._map_toolbar_toggle_at_pos(pos)
        if toggle_key:
            self._map_control_press = ('toolbar_toggle', toggle_key)
            self._cancel_hex_map_drag()
            return True
        return False

    def _drag_map_control_press(self, pos):
        press = getattr(self, '_map_control_press', None)
        if not press:
            return False
        kind, _key = press
        if kind == 'minimap' and self._minimap_contains_pos(pos):
            self._hex_map.handle_minimap_click(*pos)
        return True

    def _finish_map_control_press(self, pos):
        press = getattr(self, '_map_control_press', None)
        if not press:
            return False
        self._map_control_press = None
        self._cancel_hex_map_drag()
        kind, key = press
        if kind == 'nav':
            if self._nav_key_at_pos(pos) == key:
                self._activate_nav_control(key)
            return True
        if kind == 'minimap':
            if self._minimap_contains_pos(pos):
                self._hex_map.handle_minimap_click(*pos)
            return True
        if kind == 'mode':
            if self._map_mode_key_at_pos(pos) == key:
                self._handle_map_mode_click(pos)
            return True
        if kind == 'toolbar_toggle':
            if key == self._map_toolbar_toggle_at_pos(pos):
                if key == 'layers_toggle':
                    self._layers_open = not self._layers_open
                    self._set_activity_open(False)
                elif key == 'activity_toggle':
                    self._set_activity_open(not self._activity_open)
                    self._layers_open = False
            return True
        return True

    # ── Update / events ─────────────────────────────────────────────

    def update(self, events):
        super().update()
        self._update_icon_buttons()

        # Drain any completed background fetches before deciding whether to
        # kick off another one.
        self._drain_map_poller()
        self._drain_activity_poller()

        # Auto-load map on first frame (or re-enter)
        now = pygame.time.get_ticks()
        next_retry_at = getattr(self, '_next_map_retry_at_ms', 0)
        retry_due = (
            not next_retry_at
            or now >= next_retry_at
        )
        if (self._hex_map is None and not self._loading and retry_due
                and (now - self._last_load_tick > 2000)):
            self._last_load_tick = now
            self._load_map()

        if self._detail_box:
            self._detail_box.update()

        self._maybe_show_kingdom_overview()
        self._maybe_show_kingdom_management_intro()
        self._maybe_show_tutorial_completion()

    def handle_events(self, events):
        # The conquer-tutorial completion celebration is modal and fires here so
        # it appears immediately after the final first-land task,
        # not only once the player returns to the menu.
        if self._handle_tutorial_completion_events(events):
            return
        # The first-open teaching window is modal — it captures all input.
        if self._handle_kingdom_overview_events(events):
            return
        if self._handle_kingdom_management_events(events):
            return

        super().handle_events(events)

        coach_step = self._current_kingdom_coach_step()
        if self._handle_menu_coach_events(events, coach_step):
            return

        for event in events:
            # Icon buttons (settings, home, logout) — highest priority
            if self._handle_icon_events(event):
                continue

            # Recipient picker captures input first when open.
            if self._new_msg_picker:
                self._handle_new_msg_picker_event(event)
                continue

            # Thread modal captures normal kingdom input.
            if self._thread:
                self._handle_thread_event(event)
                continue

            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and self._finish_map_control_press(event.pos)):
                continue

            if (event.type == MOUSEMOTION
                    and self._drag_map_control_press(event.pos)):
                continue

            # X close button
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and getattr(self, '_btn_close_hit_rect',
                                self._btn_close_rect).collidepoint(event.pos)):
                self.state.screen = 'game_menu'
                return

            # Mobile drawers and popovers dismiss before input reaches the
            # map beneath them.  This prevents an outside-close tap from also
            # selecting a land.
            if (self._mobile_ui and self._activity_open
                    and event.type in (MOUSEBUTTONDOWN, MOUSEBUTTONUP)
                    and event.button == 1):
                if (self._activity_close_rect
                        and self._activity_close_rect.collidepoint(event.pos)):
                    if event.type == MOUSEBUTTONUP:
                        self._set_activity_open(False)
                    continue
                if not self._activity_rect.collidepoint(event.pos):
                    self._set_activity_open(False)
                    self._cancel_hex_map_drag()
                    continue
                if event.type == MOUSEBUTTONDOWN:
                    self._cancel_hex_map_drag()
                    continue

            if (self._mobile_ui and self._layers_open
                    and event.type == MOUSEBUTTONDOWN and event.button == 1
                    and not self._point_in_map_modes(event.pos)):
                self._layers_open = False
                continue

            # ESC → dismiss the anchored inspector first, else leave the screen.
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                if self._detail_box:
                    self._detail_box = None
                    continue
                if not self.dialogue_box:
                    self.state.screen = 'game_menu'
                    return

            # Click outside content box → back to game menu
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and not (self._hex_map and self._hex_map.is_drag_release(event))
                    and not self._box_rect.collidepoint(event.pos)):
                self.state.screen = 'game_menu'
                return

            # Anchored land inspector: consume only clicks that land on the
            # panel itself (buttons / close).  Every other event falls through
            # so the map stays pannable/zoomable and clicking another hex
            # re-targets the panel (handled in the hex-map block below).
            if self._detail_box:
                on_panel = (
                    event.type in (MOUSEBUTTONUP, MOUSEBUTTONDOWN)
                    and event.button == 1
                    and self._detail_box.contains_point(event.pos)
                )
                if on_panel:
                    map_drag_release = (
                        event.type == MOUSEBUTTONUP
                        and self._hex_map
                        and self._hex_map.is_drag_release(event)
                    )
                    if not map_drag_release:
                        self._detail_box.handle_event(event)
                        continue

            if (event.type == MOUSEBUTTONDOWN and event.button == 1
                    and self._begin_map_control_press(event.pos)):
                continue

            if event.type == MOUSEWHEEL:
                if (self._activity_open
                        and self._activity_rect.collidepoint(pygame.mouse.get_pos())):
                    # Prefer precise_y so a slow trackpad swipe (which yields
                    # fractional deltas that int() would truncate to 0) still
                    # nudges the activity list one row at a time.
                    raw = getattr(event, 'precise_y', None)
                    if raw is None or raw == 0:
                        raw = getattr(event, 'y', 0)
                    delta_rows = -float(raw or 0)
                    rows = int(delta_rows) if abs(delta_rows) >= 1 \
                        else (1 if delta_rows > 0 else -1 if delta_rows < 0 else 0)
                    if rows:
                        self._scroll_activity_tab(rows)
                    continue

            if event.type == MOUSEBUTTONUP and event.button == 1:
                map_drag_release = bool(
                    self._hex_map and self._hex_map.is_drag_release(event))
                retry_rect = getattr(self, '_retry_rect', None)
                if (not map_drag_release
                        and getattr(self, '_error', None) and retry_rect
                        and retry_rect.collidepoint(event.pos)):
                    self._next_map_retry_at_ms = 0
                    self._load_map()
                    continue

                if (not map_drag_release
                        and self._mobile_ui and self._layers_toggle_rect
                        and self._layers_toggle_rect.collidepoint(event.pos)):
                    self._layers_open = not self._layers_open
                    self._set_activity_open(False)
                    continue

                if (not map_drag_release
                        and self._mobile_ui and self._activity_toggle_rect
                        and self._activity_toggle_rect.collidepoint(event.pos)):
                    self._set_activity_open(not self._activity_open)
                    self._layers_open = False
                    continue

                if not map_drag_release and self._handle_activity_click(event.pos):
                    continue
                if (not map_drag_release
                        and self._mobile_ui and self._activity_open
                        and self._activity_rect.collidepoint(event.pos)):
                    continue

                # Map scan-mode toolbar (top-right of the map).
                if (not map_drag_release
                        and self._handle_map_mode_click(event.pos)):
                    continue

                # Kingdom selector chip (header) — prev/next + gear-to-config.
                if (not map_drag_release
                        and self._handle_kingdom_chip_click(event.pos)):
                    continue

                # Leaderboard panel (top-left of map viewport).  Must be
                # handled before the hex map so a row click doesn't also
                # trigger map pan/click logic underneath.
                lb = getattr(self, '_leaderboard_panel', None)
                if (not map_drag_release
                        and lb is not None and lb.contains_point(event.pos)):
                    lb.handle_event(event)
                    continue

                # Collect All gold button (info bar)
                if (not map_drag_release
                    and self._collect_all_rect
                    and getattr(self, '_collect_all_enabled', False)
                        and self._collect_all_rect.collidepoint(event.pos)):
                    self._collect_all_gold()
                    continue

                # Nav buttons
                nav_key = None if map_drag_release else self._nav_key_at_pos(event.pos)
                if nav_key and self._activate_nav_control(nav_key):
                    continue

                # Minimap click
                if (not map_drag_release and self._hex_map
                        and self._hex_map.handle_minimap_click(*event.pos)):
                    continue

            # Hex map events (pan, zoom wheel, click) — gated so the
            # leaderboard panel and chip swallow clicks that land on them.
            # The anchored inspector no longer blocks the map; clicks on the
            # panel were already consumed above, and clicking another hex here
            # re-targets the inspector.
            if self._hex_map:
                if event.type == MOUSEMOTION:
                    lb = getattr(self, '_leaderboard_panel', None)
                    if lb is not None and lb.contains_point(event.pos):
                        self._hex_map.hovered_tile = None
                        continue
                if event.type == MOUSEBUTTONDOWN and event.button == 1:
                    lb = getattr(self, '_leaderboard_panel', None)
                    chip_rect = getattr(self, '_kingdom_chip_rect', None)
                    blocked = (
                        (lb is not None and lb.contains_point(event.pos))
                        or (chip_rect is not None
                            and chip_rect.collidepoint(event.pos))
                        or self._point_in_map_modes(event.pos)
                    )
                    if blocked:
                        continue
                tutorial_tile = None
                if (event.type == MOUSEBUTTONUP and event.button == 1
                        and not self._hex_map.is_drag_release(event)):
                    tutorial_tile = self._recommended_tutorial_touch_tile(
                        event.pos, coach_step)
                clicked_tile = self._hex_map.handle_event(event)
                if tutorial_tile is not None:
                    self._hex_map.selected_tile = tutorial_tile
                    clicked_tile = tutorial_tile
                if clicked_tile:
                    self._open_detail(clicked_tile)

        # Keyboard pan (continuous) — stays live while the anchored inspector
        # is open so the map keeps exploring.
        keys = pygame.key.get_pressed()
        if self._hex_map:
            pan_speed = 8 / self._hex_map.zoom
            if keys[K_LEFT] or keys[K_a]:
                self._hex_map.pan(-pan_speed, 0)
            if keys[K_RIGHT] or keys[K_d]:
                self._hex_map.pan(pan_speed, 0)
            if keys[K_UP] or keys[K_w]:
                self._hex_map.pan(0, -pan_speed)
            if keys[K_DOWN] or keys[K_s]:
                self._hex_map.pan(0, pan_speed)

    def _diff_new_conquests(self, lands):
        """Return land ids that became mine since the last load; update state.

        Returns [] on the very first load (no baseline to diff against) so
        pre-existing lands are never celebrated.
        """
        my_ids = {ld.get('id') for ld in lands if ld.get('is_mine')}
        prev = getattr(self, '_prev_my_land_ids', None)
        new = [lid for lid in my_ids if lid not in prev] if prev is not None else []
        self._prev_my_land_ids = my_ids
        return new

    def _diff_champion_regions(self, regions):
        """Return newly gained Champion snapshots, never on first load."""
        user_id = self._current_user_id()
        current = {
            region.get('key'): region
            for region in (regions or [])
            if isinstance(region, dict)
            and any(
                champion.get('user_id') == user_id
                for champion in (region.get('champions') or
                                  ([region.get('champion')]
                                   if region.get('champion') else []))
            )
        }
        previous = getattr(self, '_prev_champion_region_keys', None)
        gained = ([current[key] for key in current if key not in previous]
                  if previous is not None else [])
        self._prev_champion_region_keys = set(current)
        return gained

    def _celebrate_region_championships(self, regions):
        """Celebrate each newly gained title once, without persistent chrome."""
        fx = getattr(self, '_fx', None)
        if not fx:
            return
        for idx, region in enumerate(list(regions)[:2]):
            name = region.get('name') or 'the region'
            fx.spawn_banner(
                f'Champion of {name}!', (248, 214, 104),
                duration_ms=1500 + idx * 180,
                anchor_rect=self._map_viewport_rect,
            )
            fx.spawn_confetti(
                self._map_viewport_rect,
                [(248, 214, 104), (236, 230, 194), (130, 190, 145)],
                count=24, fall_speed=(72.0, 132.0),
                gravity=105.0, life_ms=(650, 1050), delay_ms=idx * 180,
            )
        sound.play('conquer_win', volume=0.75)

    def _celebrate_conquests(self, land_ids):
        """Burst + border-merge pulse on lands that just became mine."""
        fx = getattr(self, '_fx', None)
        if not fx or not self._hex_map:
            return
        gold = (255, 214, 96)
        pale = (255, 246, 205)
        green = (140, 224, 150)
        played = False
        for lid in list(land_ids)[:4]:
            rect = self._hex_map.land_screen_rect(lid)
            if not rect:
                continue
            # The tile now wears the player's colours: pulse its border as it
            # merges into the kingdom, then pop a celebratory upward burst.
            fx.spawn_rect_pulse(rect, green, secondary=(230, 255, 225),
                                duration_ms=680, scale=1.15)
            fx.spawn_burst(rect, gold, secondary=pale, count=24,
                           upward_bias=0.4, speed=(140.0, 320.0),
                           life_ms=(420, 820))
            played = True
        if played:
            fx.spawn_banner('Land conquered!', green, duration_ms=1100)

    def _collect_reward_fx(self, gold_amount, main_boosters, side_boosters):
        """Stream gold orbs from owned lands toward the HUD gold widget."""
        fx = getattr(self, '_fx', None)
        target = getattr(self, '_user_item_display_rect', None)
        if not fx or not self._hex_map or target is None:
            return
        if gold_amount <= 0 and main_boosters <= 0 and side_boosters <= 0:
            return
        gold = (255, 214, 96)
        pale = (255, 246, 205)
        # Target the gold slot at the left of the HUD currency box.
        gold_slot = pygame.Rect(target.x, target.y,
                                max(24, int(target.w * 0.28)), target.h)
        # Source rects: on-screen owned lands (capped so the burst stays
        # tasteful and within the particle budget).
        sources = []
        for tile in self._hex_map.tiles:
            if not tile.is_mine:
                continue
            rect = self._hex_map.land_screen_rect(tile.land_id)
            if rect:
                sources.append(rect)
            if len(sources) >= 8:
                break
        if not sources:
            fx.spawn_rect_pulse(gold_slot, gold, secondary=pale, duration_ms=520)
            return
        for i, src in enumerate(sources):
            fx.spawn_copy_ghost(src, gold_slot, color=gold, secondary=pale,
                                duration_ms=900 + i * 60)
        # Land with a pulse on the HUD once the orbs arrive.
        fx.spawn_rect_pulse(gold_slot, gold, secondary=pale,
                            duration_ms=560, delay_ms=760)

    def _collect_all_gold(self):
        """POST to collect all kingdom production and spawn feedback."""
        if not self._collect_all_rect:
            return
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/collect_production_all', timeout=15)
            if resp.status_code != 200:
                logger.error(f'collect_production_all failed: {resp.status_code}')
                return
            data = resp.json() or {}
        except Exception as exc:
            logger.error(f'collect_production_all error: {exc}')
            return

        if data.get('onboarding') is not None:
            self._apply_onboarding_payload(data)

        gold_after = data.get('gold', data.get('total_gold'))
        total_collected = int(round(float(
            data.get('collected_gold_total', data.get('collected_total', data.get('collected') or 0))
        )))
        main_collected = int(data.get('collected_main_boosters_total', 0) or 0)
        side_collected = int(data.get('collected_side_boosters_total', 0) or 0)
        maps_collected = int(data.get('collected_maps_total', 0) or 0)
        if total_collected > 0 and hasattr(self, '_suppress_next_gold_floater'):
            # Keep collect feedback anchored to the clicked Collect-All button
            # instead of duplicating it at the top-left HUD gold widget.
            self._suppress_next_gold_floater()
        if gold_after is not None and getattr(self.state, 'user_dict', None) is not None:
            self.state.user_dict['gold'] = int(gold_after)
        if getattr(self.state, 'user_dict', None) is not None:
            if 'booster_packs' in data:
                self.state.user_dict['booster_packs'] = int(data.get('booster_packs') or 0)
            if 'booster_packs_side' in data:
                self.state.user_dict['booster_packs_side'] = int(data.get('booster_packs_side') or 0)

        breakdown = data.get('kingdoms') or []
        if total_collected <= 0 and breakdown:
            total_collected = sum(
                int(round(float(entry.get('collected_gold', entry.get('collected') or 0) or 0)))
                for entry in breakdown
            )
            main_collected = sum(int(entry.get('collected_main_boosters') or 0)
                                 for entry in breakdown)
            side_collected = sum(int(entry.get('collected_side_boosters') or 0)
                                 for entry in breakdown)
        center = self._collect_all_rect.center
        rise_px = int(getattr(settings, 'COLLECT_FLOAT_RISE_PX',
                              int(0.07 * _SH)))
        duration = int(getattr(settings, 'COLLECT_FLOAT_DURATION_MS', 900))
        gold_clr = getattr(settings, 'COLLECT_FLOAT_GOLD_CLR', (255, 220, 90))
        if total_collected > 0 or main_collected or side_collected:
            from utils import sound
            sound.play('coin')
        if total_collected > 0:
            self._floating_text.add(FloatingText(
                f'+{total_collected}g',
                center,
                color=gold_clr,
                duration_ms=duration,
                rise_px=rise_px,
                font=self._collect_float_font,
            ))
        if main_collected or side_collected:
            parts = []
            if main_collected:
                parts.append(f'+{main_collected} main booster')
            if side_collected:
                parts.append(f'+{side_collected} side booster')
            if hasattr(self.state, 'set_msg'):
                self.state.set_msg('Collected ' + ', '.join(parts))
        # Gold orbs stream from owned lands to the HUD gold widget.  Spawned
        # before the reload so the source land rects use the current camera.
        self._collect_reward_fx(total_collected, main_collected, side_collected)
        # Refresh map data so vault bars / pending totals update.
        # Reset the floater tick after the blocking reload so network latency
        # does not instantly age out the newly added burst.
        self._load_map()
        self._floating_text_last_tick = pygame.time.get_ticks()

    def _handle_activity_click(self, pos):
        """Handle clicks in the right activity panel. Returns True if handled."""
        if not self._activity_open:
            return False
        if not self._activity_rect.collidepoint(pos):
            return False
        panel_toggle = getattr(self, '_activity_panel_toggle_rect', None)
        if panel_toggle and panel_toggle.collidepoint(pos):
            self._set_activity_open(False)
            return True
        if (self._mark_read_hit_rect
                and self._mark_read_hit_rect.collidepoint(pos)):
            if self._mark_read_kind == 'messages':
                self._mark_messages_seen()
            else:
                self._mark_notifications_seen()
            return True
        for key, rect in (self._activity_tab_hit_rects
                          or self._activity_tab_rects).items():
            if rect.collidepoint(pos):
                self._activity_tab = key
                self._clamp_activity_scroll(key)
                return True
        if self._activity_scrollbar_rect and self._activity_scrollbar_rect.collidepoint(pos):
            rows, _empty = self._activity_rows_for_tab(self._activity_tab)
            visible = self._activity_visible_count()
            offset = self._clamp_activity_scroll(self._activity_tab, len(rows), visible)
            direction = -visible if pos[1] < self._activity_scrollbar_rect.centery else visible
            self._scroll_activity_tab(direction)
            if offset == self._activity_scroll_offsets_map().get(self._activity_tab, 0):
                # Keep the click consumed even if the list was already at an edge.
                return True
            return True
        # "+ New message" button on Messages tab
        if ((self._new_msg_hit_rect or self._new_msg_rect)
                and self._activity_tab == 'messages'
                and (self._new_msg_hit_rect or self._new_msg_rect).collidepoint(pos)):
            self._open_new_msg_picker()
            return True
        for rect, item in self._activity_row_rects:
            if rect.collidepoint(pos):
                if self._is_conversation_item(item):
                    self._open_thread(
                        item.get('other_user_id'),
                        item.get('other_username'),
                        land_id=item.get('last_land_id'),
                        is_ai=bool(item.get('is_ai')),
                    )
                    return True
                if self._is_message_item(item):
                    # Back-compat: derive the other participant and open thread.
                    current_user_id = self._current_user_id()
                    if item.get('sender_user_id') == current_user_id:
                        other_id = item.get('recipient_user_id')
                        other_name = item.get('recipient_username')
                    else:
                        other_id = item.get('sender_user_id')
                        other_name = item.get('sender_username')
                    self._open_thread(other_id, other_name,
                                      land_id=item.get('land_id'))
                    return True
                land_id = item.get('land_id')
                if land_id and self._hex_map:
                    tile = self._hex_map.focus_land(land_id)
                    if tile:
                        self.state.set_msg(f'Focused {self._activity_land_label(item)}')
                        if self._mobile_ui:
                            self._set_activity_open(False)
                return True
        return True

    # ── Thread modal (full conversation + composer) ─────────────────────────

    def _open_thread(self, other_user_id, other_username, land_id=None, is_ai=False):
        """Open the thread modal for a conversation with another player."""
        if not other_user_id:
            self.state.set_msg('Cannot message AI defenders.')
            return
        if other_user_id == self._current_user_id():
            self.state.set_msg('You cannot message yourself.')
            return
        if is_ai:
            self.state.set_msg('Cannot message AI defenders.')
            return
        self._thread = {
            'other_user_id': int(other_user_id),
            'other_username': other_username or 'Player',
            'land_id': land_id,
            'messages': [],
            'text': '',
            'error': '',
            'scroll': 0,        # bottom-anchored offset (rows from bottom)
            'loading': True,
        }
        # Tests rely on _message_compose mirroring composer state for back-compat.
        self._message_compose = {
            'recipient_user_id': int(other_user_id),
            'recipient_username': other_username or 'Player',
            'land_id': land_id,
            'text': '',
            'error': '',
        }
        self._activity_tab = 'messages'
        self._load_thread()

    def _load_thread(self):
        """Fetch full message history for the open thread."""
        if not self._thread:
            return
        other_id = self._thread.get('other_user_id')
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/messages/thread'
                f'?other_user_id={other_id}', timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self._thread['messages'] = data.get('messages', [])
                self._thread['other_username'] = (
                    data.get('other_username') or self._thread.get('other_username'))
            else:
                self._thread['error'] = 'Could not load conversation.'
        except Exception as e:
            logger.warning(f'Failed to load thread: {e}')
            self._thread['error'] = 'Connection error.'
        self._thread['loading'] = False
        # If thread had unread messages from the other side, mark them seen
        # since opening the thread implies the user has read them.
        try:
            unread_ids = [m.get('id') for m in (self._thread.get('messages') or [])
                          if m.get('recipient_user_id') == self._current_user_id()
                          and not m.get('seen_by_recipient')
                          and m.get('id')]
            if unread_ids:
                requests.post(
                    f'{settings.SERVER_URL}/kingdom/messages/mark_seen',
                    json={'message_ids': unread_ids}, timeout=10)
                for m in self._thread['messages']:
                    if m.get('id') in unread_ids:
                        m['seen_by_recipient'] = True
                # Reload conversation list so unread counts refresh.
                self._load_messages()
        except Exception as e:
            logger.warning(f'Failed to auto-mark thread seen: {e}')

    def _send_thread_message(self):
        """Send the composer text in the current thread."""
        if not self._thread:
            return False
        text = (self._thread.get('text') or '').strip()
        if not text:
            self._thread['error'] = 'Write a message first.'
            return False
        payload = {
            'recipient_user_id': self._thread.get('other_user_id'),
            'land_id': self._thread.get('land_id'),
            'message': text,
        }
        try:
            resp = requests.post(f'{settings.SERVER_URL}/kingdom/messages',
                                 json=payload, timeout=10)
            data = resp.json() if hasattr(resp, 'json') else {}
            if resp.status_code == 200 and data.get('success'):
                self._thread['text'] = ''
                self._thread['error'] = ''
                if self._message_compose:
                    self._message_compose['text'] = ''
                self._load_thread()
                self._load_messages()
                return True
            self._thread['error'] = data.get('message', 'Message failed.')
        except Exception as e:
            logger.warning(f'Failed to send kingdom message: {e}')
            self._thread['error'] = 'Connection error.'
        return False

    def _handle_thread_event(self, event):
        """Handle input while the thread modal is open. Returns True when captured."""
        if not self._thread:
            return False
        if event.type == KEYDOWN:
            if event.key == K_ESCAPE:
                self._thread = None
                self._message_compose = None
                return True
            if event.key == K_BACKSPACE:
                self._thread['text'] = self._thread.get('text', '')[:-1]
                self._thread['error'] = ''
                if self._message_compose:
                    self._message_compose['text'] = self._thread['text']
                return True
            if event.key == K_RETURN:
                mods = pygame.key.get_mods()
                if mods & KMOD_SHIFT:
                    text = self._thread.get('text', '')
                    if len(text) < 500:
                        self._thread['text'] = (text + '\n')[:500]
                        if self._message_compose:
                            self._message_compose['text'] = self._thread['text']
                else:
                    self._send_thread_message()
                return True
            return True
        if event.type == pygame.TEXTINPUT:
            text = self._thread.get('text', '')
            if len(text) < 500:
                self._thread['text'] = (text + event.text)[:500]
                self._thread['error'] = ''
                if self._message_compose:
                    self._message_compose['text'] = self._thread['text']
            return True
        if event.type == MOUSEWHEEL:
            raw = getattr(event, 'precise_y', None)
            if raw is None or raw == 0:
                raw = getattr(event, 'y', 0)
            self._thread['scroll'] = max(
                0, self._thread.get('scroll', 0) - int(round(float(raw or 0))))
            return True
        if event.type == MOUSEBUTTONUP and event.button == 1:
            if self._thread_close_rect and self._thread_close_rect.collidepoint(event.pos):
                self._thread = None
                self._message_compose = None
                return True
            if self._thread_cancel_rect and self._thread_cancel_rect.collidepoint(event.pos):
                self._thread = None
                self._message_compose = None
                return True
            if self._thread_send_rect and self._thread_send_rect.collidepoint(event.pos):
                self._send_thread_message()
                return True
        return True

    def _draw_thread_modal(self):
        """Draw the conversation thread modal with full history + composer."""
        sw, sh = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.window.blit(overlay, (0, 0))

        box = pygame.Rect(0, 0, int(0.54 * sw), int(0.72 * sh))
        box.center = (sw // 2, sh // 2)
        surf = pygame.Surface((box.w, box.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.KINGDOM_ACTIVITY_BG, surf.get_rect(), border_radius=10)
        self.window.blit(surf, box.topleft)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, box, 1, border_radius=10)

        pad = int(0.018 * sh)
        # Header: recipient name + close button.
        other = self._thread.get('other_username') or 'Player'
        title = self._activity_title_font.render(
            f'Conversation with {other}', True, settings.KINGDOM_INFO_CLR)
        self.window.blit(title, (box.x + pad, box.y + pad))

        _xsz = int(0.028 * sh)
        self._thread_close_rect = pygame.Rect(
            box.right - _xsz - pad, box.y + pad, _xsz, _xsz)
        self._draw_compose_button(self._thread_close_rect, '×', active=False)

        # Sub-header: land context if present.
        sub_y = box.y + pad + title.get_height() + 4
        land_id = self._thread.get('land_id')
        sub_text_parts = []
        if land_id:
            sub_text_parts.append(f'About Land #{land_id}')
        sub_text_parts.append('Enter sends · Shift+Enter newline · Esc closes')
        sub_surf = self._activity_small_font.render(
            '   ·   '.join(sub_text_parts), True, settings.KINGDOM_ACTIVITY_DIM_CLR)
        self.window.blit(sub_surf, (box.x + pad, sub_y))

        # Composer area at the bottom.
        comp_h = int(0.13 * sh)
        comp_top = box.bottom - pad - comp_h - int(0.05 * sh)  # leave space for buttons
        # Buttons row.
        btn_w = int(0.085 * sw)
        btn_h = int(0.04 * sh)
        gap = int(0.010 * sw)
        by = box.bottom - pad - btn_h
        self._thread_cancel_rect = pygame.Rect(
            box.right - pad - btn_w * 2 - gap, by, btn_w, btn_h)
        self._thread_send_rect = pygame.Rect(
            box.right - pad - btn_w, by, btn_w, btn_h)
        self._draw_compose_button(self._thread_cancel_rect, 'Cancel', active=False)
        self._draw_compose_button(self._thread_send_rect, 'Send', active=True)

        # Composer input box (multi-line, wrapped).
        self._thread_input_rect = pygame.Rect(
            box.x + pad, comp_top, box.w - 2 * pad, comp_h)
        pygame.draw.rect(self.window, (18, 17, 24, 235),
                         self._thread_input_rect, border_radius=6)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER,
                         self._thread_input_rect, 1, border_radius=6)
        text = self._thread.get('text') or ''
        placeholder = 'Type a message...'
        self._draw_thread_compose_text(text, placeholder)

        err = self._thread.get('error')
        if err:
            err_surf = self._activity_small_font.render(
                err, True, settings.KINGDOM_ACTIVITY_BAD_CLR)
            self.window.blit(err_surf,
                             (box.x + pad, comp_top - err_surf.get_height() - 2))

        # History area.
        hist_top = sub_y + sub_surf.get_height() + 8
        hist_bottom = comp_top - 8
        hist_rect = pygame.Rect(box.x + pad, hist_top,
                                box.w - 2 * pad, max(1, hist_bottom - hist_top))
        pygame.draw.rect(self.window, (16, 14, 22, 180), hist_rect, border_radius=6)
        self._draw_thread_history(hist_rect)

    def _draw_thread_compose_text(self, text, placeholder):
        """Render the multi-line composer text inside _thread_input_rect."""
        r = self._thread_input_rect
        font = self._activity_font
        pad_x = 8
        line_h = font.get_height() + 2
        if not text:
            ph = font.render(placeholder, True, settings.KINGDOM_ACTIVITY_DIM_CLR)
            self.window.blit(ph, (r.x + pad_x, r.y + 6))
            return
        # Wrap by explicit newlines first, then by max width.
        lines = []
        for raw_line in text.split('\n'):
            lines.extend(self._wrap_text(raw_line, font, r.w - pad_x * 2)
                         if raw_line else [''])
        max_lines = max(1, (r.h - 8) // line_h)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        y = r.y + 4
        for ln in lines:
            surf = font.render(ln, True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
            self.window.blit(surf, (r.x + pad_x, y))
            y += line_h
        # Blinking cursor at the end.
        if (pygame.time.get_ticks() // 500) % 2 == 0 and lines:
            last = lines[-1]
            cx = r.x + pad_x + min(font.size(last)[0], r.w - pad_x * 2 - 2)
            cy = y - line_h
            pygame.draw.line(self.window, settings.KINGDOM_ACTIVITY_TEXT_CLR,
                             (cx, cy + 2), (cx, cy + font.get_height() - 2), 1)

    def _draw_thread_history(self, rect):
        """Render scrollable conversation history inside rect."""
        if not self._thread:
            return
        if self._thread.get('loading'):
            txt = self._activity_font.render('Loading…', True,
                                             settings.KINGDOM_ACTIVITY_DIM_CLR)
            self.window.blit(txt, txt.get_rect(center=rect.center))
            return
        messages = self._thread.get('messages') or []
        if not messages:
            txt = self._activity_font.render('No messages yet. Say hi!', True,
                                             settings.KINGDOM_ACTIVITY_DIM_CLR)
            self.window.blit(txt, txt.get_rect(center=rect.center))
            return

        old_clip = self.window.get_clip()
        self.window.set_clip(rect)
        try:
            current_user_id = self._current_user_id()
            font = self._activity_font
            small = self._activity_small_font
            line_h = font.get_height() + 2
            bubble_pad = 6
            max_bubble_w = int(rect.w * 0.78)
            # Build bubble (rect, lines, sender_is_me, header, footer) per message.
            entries = []
            for m in messages:
                is_me = m.get('sender_user_id') == current_user_id
                body = m.get('message') or ''
                wrapped = []
                for raw_line in body.split('\n'):
                    if raw_line:
                        wrapped.extend(self._wrap_text(raw_line, font, max_bubble_w - 2 * bubble_pad))
                    else:
                        wrapped.append('')
                rel = self._format_relative_time(m.get('timestamp'))
                header = ('You' if is_me else m.get('sender_username') or 'Other')
                header_txt = f'{header}  ·  {rel}' if rel else header
                footer_txt = ''
                if is_me:
                    footer_txt = '✓✓' if m.get('seen_by_recipient') else '✓'
                bubble_w = min(max_bubble_w,
                               max(small.size(header_txt)[0],
                                   max((font.size(ln)[0] for ln in wrapped), default=0))
                               + 2 * bubble_pad)
                bubble_h = (small.get_height() + 4 + line_h * len(wrapped)
                            + (small.get_height() + 2 if footer_txt else 0))
                entries.append({
                    'is_me': is_me,
                    'header': header_txt,
                    'lines': wrapped,
                    'footer': footer_txt,
                    'w': bubble_w,
                    'h': bubble_h,
                })

            gap = 6
            total_h = sum(e['h'] for e in entries) + gap * max(0, len(entries) - 1)
            scroll = int(self._thread.get('scroll') or 0)
            # Bottom-anchored: layout so newest is at bottom; scroll moves upward.
            start_y = rect.bottom - total_h + scroll * line_h
            min_start_y = rect.y + 4
            if start_y < min_start_y:
                # Clamp so the oldest bubble is visible at top when fully scrolled.
                start_y = min_start_y
                self._thread['scroll'] = max(0, int((rect.bottom - total_h - min_start_y) / line_h))
            y = start_y
            for e in entries:
                x = rect.right - e['w'] - 8 if e['is_me'] else rect.x + 8
                bubble = pygame.Rect(x, y, e['w'], e['h'])
                clr = ((44, 80, 60, 215) if e['is_me']
                       else (40, 38, 54, 215))
                bsurf = pygame.Surface((bubble.w, bubble.h), pygame.SRCALPHA)
                pygame.draw.rect(bsurf, clr, bsurf.get_rect(), border_radius=8)
                pygame.draw.rect(bsurf, settings.KINGDOM_ACTIVITY_BORDER,
                                 bsurf.get_rect(), 1, border_radius=8)
                self.window.blit(bsurf, bubble.topleft)
                hy = bubble.y + 4
                hsurf = small.render(e['header'], True, settings.KINGDOM_ACTIVITY_DIM_CLR)
                self.window.blit(hsurf, (bubble.x + bubble_pad, hy))
                hy += small.get_height() + 2
                for ln in e['lines']:
                    ls = font.render(ln, True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
                    self.window.blit(ls, (bubble.x + bubble_pad, hy))
                    hy += line_h
                if e['footer']:
                    fclr = ((150, 200, 150) if e['footer'] == '✓✓'
                            else settings.KINGDOM_ACTIVITY_DIM_CLR)
                    fsurf = small.render(e['footer'], True, fclr)
                    self.window.blit(fsurf, (bubble.right - bubble_pad - fsurf.get_width(),
                                             bubble.bottom - small.get_height() - 2))
                y += e['h'] + gap
        finally:
            self.window.set_clip(old_clip)

    # ── Recipient picker for "+ New message" ────────────────────────────────

    def _open_new_msg_picker(self):
        """Open the recipient-username picker modal."""
        self._new_msg_picker = {
            'username': '',
            'error': '',
            'loading': False,
        }

    def _resolve_recipient_and_open_thread(self):
        """Validate the typed username and open a thread on success."""
        if not self._new_msg_picker:
            return
        username = (self._new_msg_picker.get('username') or '').strip()
        if not username:
            self._new_msg_picker['error'] = 'Type a username.'
            return
        self._new_msg_picker['loading'] = True
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/users/lookup'
                f'?username={username}', timeout=10)
            data = resp.json() if hasattr(resp, 'json') else {}
            if resp.status_code == 200 and data.get('success'):
                user_id = data.get('user_id')
                resolved = data.get('username') or username
                self._new_msg_picker = None
                self._open_thread(user_id, resolved, is_ai=bool(data.get('is_ai')))
                return
            self._new_msg_picker['error'] = data.get('message', 'User not found.')
        except Exception as e:
            logger.warning(f'Failed to look up recipient: {e}')
            self._new_msg_picker['error'] = 'Connection error.'
        finally:
            if self._new_msg_picker:
                self._new_msg_picker['loading'] = False

    def _handle_new_msg_picker_event(self, event):
        """Handle input for the recipient picker modal."""
        if not self._new_msg_picker:
            return False
        if event.type == KEYDOWN:
            if event.key == K_ESCAPE:
                self._new_msg_picker = None
                return True
            if event.key == K_BACKSPACE:
                self._new_msg_picker['username'] = (
                    self._new_msg_picker.get('username', '')[:-1])
                self._new_msg_picker['error'] = ''
                return True
            if event.key == K_RETURN:
                self._resolve_recipient_and_open_thread()
                return True
            return True
        if event.type == pygame.TEXTINPUT:
            uname = self._new_msg_picker.get('username', '')
            if len(uname) < 40:
                self._new_msg_picker['username'] = (uname + event.text)[:40]
                self._new_msg_picker['error'] = ''
            return True
        if event.type == MOUSEBUTTONUP and event.button == 1:
            if self._new_msg_picker_close_rect and self._new_msg_picker_close_rect.collidepoint(event.pos):
                self._new_msg_picker = None
                return True
            if self._new_msg_picker_cancel_rect and self._new_msg_picker_cancel_rect.collidepoint(event.pos):
                self._new_msg_picker = None
                return True
            if self._new_msg_picker_ok_rect and self._new_msg_picker_ok_rect.collidepoint(event.pos):
                self._resolve_recipient_and_open_thread()
                return True
        return True

    def _draw_new_msg_picker(self):
        """Draw the recipient-username picker modal."""
        sw, sh = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.window.blit(overlay, (0, 0))

        box = pygame.Rect(0, 0, int(0.36 * sw), int(0.24 * sh))
        box.center = (sw // 2, sh // 2)
        surf = pygame.Surface((box.w, box.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.KINGDOM_ACTIVITY_BG, surf.get_rect(), border_radius=8)
        self.window.blit(surf, box.topleft)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, box, 1, border_radius=8)

        pad = int(0.018 * sh)
        title = self._activity_title_font.render(
            'Send message to player', True, settings.KINGDOM_INFO_CLR)
        self.window.blit(title, (box.x + pad, box.y + pad))

        _xsz = int(0.028 * sh)
        self._new_msg_picker_close_rect = pygame.Rect(
            box.right - _xsz - pad, box.y + pad, _xsz, _xsz)
        self._draw_compose_button(self._new_msg_picker_close_rect, '×', active=False)

        label = self._activity_small_font.render(
            'Username:', True, settings.KINGDOM_ACTIVITY_DIM_CLR)
        ly = box.y + pad + title.get_height() + 10
        self.window.blit(label, (box.x + pad, ly))

        input_rect = pygame.Rect(box.x + pad,
                                 ly + label.get_height() + 6,
                                 box.w - 2 * pad, int(0.05 * sh))
        pygame.draw.rect(self.window, (18, 17, 24, 235), input_rect, border_radius=6)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, input_rect, 1, border_radius=6)
        uname = self._new_msg_picker.get('username') or ''
        placeholder = 'Type a username...'
        display = uname if uname else placeholder
        color = (settings.KINGDOM_ACTIVITY_TEXT_CLR if uname
                 else settings.KINGDOM_ACTIVITY_DIM_CLR)
        usurf = self._activity_font.render(
            self._fit_text(display, self._activity_font, input_rect.w - 16),
            True, color)
        self.window.blit(usurf, (input_rect.x + 8,
                                 input_rect.centery - usurf.get_height() // 2))
        if uname and (pygame.time.get_ticks() // 500) % 2 == 0:
            cx = input_rect.x + 10 + min(
                self._activity_font.size(uname)[0], input_rect.w - 24)
            pygame.draw.line(self.window, settings.KINGDOM_ACTIVITY_TEXT_CLR,
                             (cx, input_rect.y + 6),
                             (cx, input_rect.bottom - 6), 1)

        err = self._new_msg_picker.get('error')
        if err:
            err_surf = self._activity_small_font.render(
                err, True, settings.KINGDOM_ACTIVITY_BAD_CLR)
            self.window.blit(err_surf,
                             (box.x + pad, input_rect.bottom + 6))

        btn_w = int(0.085 * sw)
        btn_h = int(0.04 * sh)
        gap = int(0.010 * sw)
        by = box.bottom - pad - btn_h
        self._new_msg_picker_cancel_rect = pygame.Rect(
            box.right - pad - btn_w * 2 - gap, by, btn_w, btn_h)
        self._new_msg_picker_ok_rect = pygame.Rect(
            box.right - pad - btn_w, by, btn_w, btn_h)
        self._draw_compose_button(self._new_msg_picker_cancel_rect, 'Cancel', active=False)
        self._draw_compose_button(self._new_msg_picker_ok_rect, 'Continue', active=True)

    def _draw_compose_button(self, rect, label, active=False):
        bg = settings.KINGDOM_ACTIVITY_TAB_ACTIVE_BG if active else settings.KINGDOM_ACTIVITY_TAB_BG
        pygame.draw.rect(self.window, bg, rect, border_radius=5)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, rect, 1, border_radius=5)
        txt = self._activity_font.render(label, True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _mark_notifications_seen(self):
        """Tell the server to mark current notifications as seen."""
        attack_log_ids = []
        kingdom_notification_ids = []
        for n in self._visible_notifications():
            nid = n.get('id')
            if not nid:
                continue
            if self._is_kingdom_event_item(n) or n.get('source') == 'kingdom_notification':
                kingdom_notification_ids.append(nid)
            else:
                attack_log_ids.append(nid)
        if not attack_log_ids and not kingdom_notification_ids:
            self._notifications = []
            self._activity_scroll_offsets_map()['alerts'] = 0
            return
        try:
            requests.post(
                f'{settings.SERVER_URL}/kingdom/notifications/mark_seen',
                json={
                    'attack_log_ids': attack_log_ids,
                    'kingdom_notification_ids': kingdom_notification_ids,
                }, timeout=10)
        except Exception as e:
            logger.warning(f'Failed to mark notifications seen: {e}')
        self._notifications = []
        self._activity_scroll_offsets_map()['alerts'] = 0

    def _mark_messages_seen(self):
        """Mark every unread kingdom message addressed to the current user as read."""
        if self._message_unread_count <= 0:
            self._activity_scroll_offsets_map()['messages'] = 0
            return
        try:
            requests.post(
                f'{settings.SERVER_URL}/kingdom/messages/mark_all_seen',
                json={}, timeout=10)
        except Exception as e:
            logger.warning(f'Failed to mark kingdom messages seen: {e}')
        for conv in getattr(self, '_conversations', []) or []:
            conv['unread_count'] = 0
        self._message_unread_count = 0
        self._activity_scroll_offsets_map()['messages'] = 0

    # ── Detail box ──────────────────────────────────────────────────

    def _open_detail(self, tile):
        """Open the anchored land inspector for *tile*."""
        conquest_outcome = (
            self._hex_map.conquest_outcome_for(tile)
            if self._hex_map else None
        )
        region_info = next((
            region for region in ((self._map_data or {}).get('regions') or [])
            if region.get('key') == getattr(tile, 'region', None)
        ), None)
        self._detail_box = LandDetailBox(
            self.window, tile,
            cooldown=self._cooldown,
            land_cooldown=getattr(tile, 'conquer_cooldown_remaining', 0),
            on_conquer=self._on_conquer,
            on_defence=self._on_defence,
            on_config=self._on_configure_kingdom,
            on_message=self._on_message_owner,
            on_close=lambda: setattr(self, '_detail_box', None),
            conquest_outcome=conquest_outcome,
            anchored=True,
            viewport_rect=self._map_viewport_rect,
            region_info=region_info,
        )
        self._keep_selected_hex_visible(tile)
        if self._kingdom_coach_ready() and self._detail_conquer_button_rect():
            self._mark_menu_coach_seen('kingdom_pick_land')
        active_lesson = self._active_onboarding_lesson_id()
        if (active_lesson == 'build_attack'
                and self._detail_action_button_rect('conquer')):
            self._mark_menu_coach_seen('conquer_choose_next_land')
        elif (active_lesson == 'defend_land'
              and self._detail_action_button_rect('defence')):
            self._mark_menu_coach_seen('defence_choose_land')

    def _keep_selected_hex_visible(self, tile):
        """Pan the map so the inspected hex stays visible above the sheet.

        Only nudges the camera when the tile would otherwise sit behind (or
        below the top edge of) the anchored inspector, recentring it into the
        middle of the visible band above the panel.
        """
        if not self._hex_map or not self._detail_box:
            return
        box = self._detail_box.box_rect
        if not box:
            return
        vp = self._map_viewport_rect
        margin = int(0.02 * settings.SCREEN_HEIGHT)
        tile_rect = self._hex_map.land_screen_rect(tile.land_id)
        covered = tile_rect is None or tile_rect.bottom > box.top - margin
        if not covered:
            return
        desired_sy = (vp.y + box.top) / 2
        offset = (vp.y + vp.h / 2) - desired_sy
        self._hex_map.focus_land(tile.land_id, screen_offset_y=offset)

    # ── Hover preview ────────────────────────────────────────────────

    @staticmethod
    def _hover_preview_lines(tile):
        """Return the deliberately small set of facts shown before a click."""
        region = (getattr(settings, 'KINGDOM_REGIONS', {}).get(
            getattr(tile, 'region', None), {}) or {}).get('name')
        if region:
            title = f'{region} \u00b7 ({tile.col}, {tile.row}) \u00b7 Tier {int(tile.tier)}'
        else:
            title = f'Land ({tile.col}, {tile.row})  \u00b7  Tier {int(tile.tier)}'
        if (tile.suit_bonus_suit and tile.suit_bonus_suit != 'Neutral'
                and tile.suit_bonus_value):
            suit = f'{tile.suit_bonus_suit} +{tile.suit_bonus_value}'
        else:
            suit = 'Neutral'
        stats = f'{tile.gold_rate:.1f} gold/hr  \u00b7  {suit}'
        if tile.is_mine:
            owner = 'Yours'
        elif getattr(tile, 'owner_username', None):
            owner = f'Owner: {tile.owner_username}'
        else:
            owner = 'Unclaimed'
        return title, stats, owner

    def _draw_hover_preview(self):
        """Draw a small summary next to the hovered hex.

        The click-open inspector owns shields, conquest outcomes, cooldowns,
        and the rest of the detailed land information.
        """
        hm = self._hex_map
        if not hm or self._loading or self._error:
            return
        tile = getattr(hm, 'hovered_tile', None)
        if tile is None:
            return
        leaderboard = getattr(self, '_leaderboard_panel', None)
        if (leaderboard is not None
                and leaderboard.contains_point(pygame.mouse.get_pos())):
            return
        # Suppress under blocking modals/overlays and for the land already
        # open in the inspector (avoids duplicating its info).
        if (self._thread or self._new_msg_picker
                or getattr(self, '_kingdom_overview_dialogue', None)
                or getattr(self, 'dialogue_box', None)):
            return
        if (self._detail_box
                and getattr(self._detail_box.tile, 'land_id', None) == tile.land_id):
            return

        title_clr = getattr(settings, 'LAND_DETAIL_TITLE_CLR', (236, 214, 150))
        dim = getattr(settings, 'KINGDOM_ACTIVITY_DIM_CLR', (150, 140, 120))
        good = getattr(settings, 'KINGDOM_CONFIG_GOOD_CLR', (132, 220, 142))

        title_text, stats_text, owner_text = self._hover_preview_lines(tile)
        if tile.is_mine:
            owner_clr = good
        elif getattr(tile, 'owner_username', None):
            owner_clr = settings.KINGDOM_INFO_CLR
        else:
            owner_clr = dim
        rows = [
            ('title', title_text, title_clr),
            ('body', stats_text, settings.KINGDOM_INFO_CLR),
            ('body', owner_text, owner_clr),
        ]

        title_font = self._activity_title_font
        body_font = self._activity_font
        pad = max(5, int(0.006 * settings.SCREEN_HEIGHT))
        gap = 2

        # Measure.
        surfs = []
        max_w = 0
        total_h = 0
        for kind, text, clr in rows:
            font = title_font if kind == 'title' else body_font
            surf = font.render(text, True, clr)
            w = surf.get_width()
            max_w = max(max_w, w)
            surfs.append((kind, surf))
            total_h += surf.get_height() + gap
        total_h -= gap
        card_w = max_w + pad * 2
        card_h = total_h + pad * 2

        # Position beside the hovered hex (flip / clamp inside the viewport).
        vp = self._map_viewport_rect
        hex_rect = hm.land_screen_rect(tile.land_id)
        if hex_rect:
            cx = hex_rect.right + 12
            cy = hex_rect.centery - card_h // 2
            if cx + card_w > vp.right - 4:
                cx = hex_rect.left - card_w - 12
        else:
            mx, my = pygame.mouse.get_pos()
            cx, cy = mx + 16, my + 16
            if cx + card_w > vp.right - 4:
                cx = mx - card_w - 16
        cx = max(vp.x + 4, min(cx, vp.right - card_w - 4))
        cy = max(vp.y + 4, min(cy, vp.bottom - card_h - 4))

        # Panel.
        panel = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (24, 20, 15, 234), panel.get_rect(),
                         border_radius=6)
        pygame.draw.rect(panel, settings.KINGDOM_MAP_FRAME_BORDER,
                         panel.get_rect(), 1, border_radius=6)
        self.window.blit(panel, (cx, cy))

        y = cy + pad
        for kind, surf in surfs:
            self.window.blit(surf, (cx + pad, y))
            y += surf.get_height() + gap

    # ── Map scan modes toolbar ───────────────────────────────────────

    def _draw_map_modes_toolbar(self):
        """Draw the scan-mode toolbar (top-right of the map) + a legend."""
        self._map_mode_rects = {}
        self._activity_toggle_rect = None
        self._layers_toggle_rect = None
        if not self._hex_map or self._loading or self._error:
            return
        if self._mobile_ui:
            self._draw_mobile_map_toolbar()
            return
        vp = self._map_viewport_rect
        font = self._nav_font
        pad_x = max(6, int(0.006 * settings.SCREEN_WIDTH))
        pad_y = max(3, int(0.004 * settings.SCREEN_HEIGHT))
        gap = max(4, int(0.004 * settings.SCREEN_WIDTH))
        margin = max(6, int(0.008 * settings.SCREEN_HEIGHT))

        btns = []
        total_w = 0
        h = 0
        for key, label in _MAP_MODES:
            tw, th = font.size(label)
            bw = tw + pad_x * 2
            bh = th + pad_y * 2
            btns.append((key, label, bw))
            total_w += bw + gap
            h = max(h, bh)
        total_w -= gap

        activity_button = None
        if not self._activity_open:
            activity_label = '\u2039 Activity'
            tw, th = font.size(activity_label)
            activity_w = tw + pad_x * 2
            activity_button = (activity_label, activity_w)
            total_w += gap + activity_w
            h = max(h, th + pad_y * 2)

        x = vp.right - margin - total_w
        y = vp.y + margin
        if _SH > _SW:
            # The collapsed Regions/Rankings header owns the first map row;
            # move layer/activity controls beneath it instead of overlapping.
            leaderboard = getattr(self, '_leaderboard_panel', None)
            header_h = (leaderboard._header_h()
                        if leaderboard is not None
                        and hasattr(leaderboard, '_header_h') else 0)
            y += header_h + gap
        mx, my = pygame.mouse.get_pos()
        for key, label, bw in btns:
            rect = pygame.Rect(x, y, bw, h)
            active = (key == self._map_mode)
            hovered = rect.collidepoint(mx, my)
            if active:
                bg, border, tclr = (196, 150, 60, 235), (236, 206, 130), (28, 22, 10)
            elif hovered:
                bg, border, tclr = (60, 54, 40, 232), (200, 180, 130), (245, 232, 196)
            else:
                bg, border, tclr = (34, 30, 22, 214), (120, 108, 82), (206, 194, 162)
            bsurf = pygame.Surface((bw, h), pygame.SRCALPHA)
            pygame.draw.rect(bsurf, bg, bsurf.get_rect(), border_radius=6)
            pygame.draw.rect(bsurf, border, bsurf.get_rect(), 1, border_radius=6)
            self.window.blit(bsurf, rect.topleft)
            tsurf = font.render(label, True, tclr)
            self.window.blit(tsurf, tsurf.get_rect(center=rect.center))
            self._map_mode_rects[key] = rect
            x += bw + gap

        if activity_button:
            label, bw = activity_button
            rect = pygame.Rect(x, y, bw, h)
            hovered = rect.collidepoint(mx, my)
            bg = ((72, 64, 88, 238) if hovered else (42, 38, 52, 224))
            border = ((210, 194, 225) if hovered
                      else settings.KINGDOM_ACTIVITY_BORDER)
            bsurf = pygame.Surface((bw, h), pygame.SRCALPHA)
            pygame.draw.rect(bsurf, bg, bsurf.get_rect(), border_radius=6)
            pygame.draw.rect(bsurf, border, bsurf.get_rect(), 1,
                             border_radius=6)
            self.window.blit(bsurf, rect.topleft)
            tsurf = font.render(label, True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
            self.window.blit(tsurf, tsurf.get_rect(center=rect.center))
            self._activity_toggle_rect = rect
            self._draw_activity_badges(rect)

        self._draw_map_mode_legend(vp, y + h + max(3, pad_y), margin)

    def _mobile_activity_count(self):
        return len(self._visible_notifications()) + int(
            self._message_unread_count or 0)

    def _activity_badge_counts(self):
        """Return unread notification/message counts for the toolbar badges."""
        return (len(self._visible_notifications()),
                max(0, int(self._message_unread_count or 0)))

    def _draw_activity_badges(self, rect):
        """Draw compact N/M unread pills without lengthening Activity text."""
        alerts, messages = self._activity_badge_counts()
        badges = []
        if alerts:
            badges.append((f'N{min(alerts, 99)}' if alerts < 100 else 'N99+',
                           (188, 66, 56), (255, 238, 222)))
        if messages:
            badges.append((f'M{min(messages, 99)}' if messages < 100 else 'M99+',
                           (74, 108, 178), (238, 244, 255)))
        if not badges:
            return
        font = self._activity_small_font
        gap = 3
        right = rect.right - 2
        y = rect.y - max(3, font.get_height() // 3)
        for label, bg, text_clr in reversed(badges):
            text = font.render(label, True, text_clr)
            width = text.get_width() + 8
            height = max(14, text.get_height() + 2)
            pill = pygame.Rect(right - width, y, width, height)
            pygame.draw.rect(self.window, bg, pill, border_radius=height // 2)
            pygame.draw.rect(self.window, (247, 223, 177), pill, 1,
                             border_radius=height // 2)
            self.window.blit(text, text.get_rect(center=pill.center))
            right = pill.left - gap

    def _draw_mobile_toolbar_button(self, rect, label, *, active=False):
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        if active:
            bg, border, text_clr = ((112, 82, 34, 242),
                                    (240, 205, 124), (255, 242, 204))
        elif hovered:
            bg, border, text_clr = ((64, 56, 42, 238),
                                    (205, 182, 132), (245, 232, 196))
        else:
            bg, border, text_clr = ((30, 26, 20, 230),
                                    (134, 118, 88), (220, 208, 178))
        # Keep a full 58px hit target while the visible pill stays compact.
        visual = rect.inflate(0, -max(0, rect.h - settings.TOUCH_COMPACT_MIN))
        pygame.draw.rect(self.window, bg, visual, border_radius=7)
        pygame.draw.rect(self.window, border, visual, 1, border_radius=7)
        label = self._fit_text(label, self._nav_font, visual.w - 16)
        surf = self._nav_font.render(label, True, text_clr)
        self.window.blit(surf, surf.get_rect(center=visual.center))

    def _draw_mobile_map_toolbar(self):
        """Draw two large map controls and an optional layer picker."""
        vp = self._map_viewport_rect
        margin = max(6, int(0.008 * _SH))
        h = settings.TOUCH_TARGET_MIN
        gap = max(6, int(0.007 * _SW))
        activity_w = max(118, int(0.17 * _SW))
        layers_w = max(118, int(0.17 * _SW))
        y = vp.y + margin
        activity_x = vp.right - margin - activity_w
        layers_x = activity_x - gap - layers_w

        activity_label = 'Activity'
        self._activity_toggle_rect = pygame.Rect(
            activity_x, y, activity_w, h)
        self._layers_toggle_rect = pygame.Rect(layers_x, y, layers_w, h)
        mode_label = dict(_MAP_MODES).get(self._map_mode, 'Terrain')
        self._draw_mobile_toolbar_button(
            self._layers_toggle_rect, f'Layer: {mode_label}',
            active=self._layers_open)
        self._draw_mobile_toolbar_button(
            self._activity_toggle_rect, activity_label,
            active=self._activity_open)
        self._draw_activity_badges(self._activity_toggle_rect)

        if not self._layers_open:
            return

        menu_gap = 5
        cell_w = max(layers_w, activity_w)
        menu_w = cell_w * 2 + menu_gap
        start_x = vp.right - margin - menu_w
        start_y = y + h + menu_gap
        for index, (key, label) in enumerate(_MAP_MODES):
            col = index % 2
            row = index // 2
            rect = pygame.Rect(
                start_x + col * (cell_w + menu_gap),
                start_y + row * (h + menu_gap),
                cell_w,
                h,
            )
            self._map_mode_rects[key] = rect
            self._draw_mobile_toolbar_button(
                rect, label, active=(key == self._map_mode))

    def _draw_map_mode_legend(self, vp, top_y, margin):
        """Compact right-aligned legend describing the active scan mode."""
        mode = self._map_mode
        font = self._activity_small_font
        pad = max(5, int(0.005 * settings.SCREEN_HEIGHT))
        swatch = max(8, int(0.012 * settings.SCREEN_HEIGHT))
        border_clr = settings.KINGDOM_MAP_FRAME_BORDER
        label_clr = (206, 194, 162)

        def _panel(w, ht):
            cx = vp.right - margin - w
            surf = pygame.Surface((w, ht), pygame.SRCALPHA)
            pygame.draw.rect(surf, (24, 20, 15, 224), surf.get_rect(),
                             border_radius=6)
            pygame.draw.rect(surf, border_clr, surf.get_rect(), 1,
                             border_radius=6)
            self.window.blit(surf, (cx, top_y))
            return cx

        if mode == 'gold':
            bar_w = max(80, int(0.10 * settings.SCREEN_WIDTH))
            lo_s = font.render('Low', True, label_clr)
            hi_s = font.render('High', True, label_clr)
            content_w = lo_s.get_width() + 6 + bar_w + 6 + hi_s.get_width()
            card_w = content_w + pad * 2
            card_h = max(swatch, lo_s.get_height()) + pad * 2
            cx = _panel(card_w, card_h)
            midy = top_y + card_h // 2
            x = cx + pad
            self.window.blit(lo_s, lo_s.get_rect(midleft=(x, midy)))
            x += lo_s.get_width() + 6
            for i in range(bar_w):
                t = i / max(1, bar_w - 1)
                clr = (int(58 + t * 197), int(50 + t * 168), int(74 - t * 44))
                pygame.draw.line(self.window, clr,
                                 (x + i, midy - swatch // 2),
                                 (x + i, midy + swatch // 2))
            pygame.draw.rect(self.window, border_clr,
                             (x, midy - swatch // 2, bar_w, swatch), 1)
            x += bar_w + 6
            self.window.blit(hi_s, hi_s.get_rect(midleft=(x, midy)))
            return

        if mode == 'ownership':
            items = [((70, 200, 120), 'You'), ((210, 90, 80), 'Rival'),
                     ((120, 132, 150), 'Unclaimed')]
        elif mode == 'vulnerable':
            items = [((70, 205, 110), 'Open'), ((210, 162, 72), 'Cooldown'),
                     ((200, 70, 70), 'Protected')]
        else:
            return  # terrain: no legend needed

        labels = [font.render(t, True, label_clr) for _, t in items]
        content_w = (sum(swatch + 4 + s.get_width() for s in labels)
                     + max(0, len(items) - 1) * 8)
        card_w = content_w + pad * 2
        card_h = max(swatch, labels[0].get_height()) + pad * 2
        cx = _panel(card_w, card_h)
        midy = top_y + card_h // 2
        x = cx + pad
        for (clr, _), lsurf in zip(items, labels):
            pygame.draw.rect(self.window, clr,
                             (x, midy - swatch // 2, swatch, swatch),
                             border_radius=3)
            pygame.draw.rect(self.window, (0, 0, 0),
                             (x, midy - swatch // 2, swatch, swatch), 1,
                             border_radius=3)
            x += swatch + 4
            self.window.blit(lsurf, lsurf.get_rect(midleft=(x, midy)))
            x += lsurf.get_width() + 8

    def _handle_map_mode_click(self, pos):
        """Switch scan mode if *pos* hits a toolbar button. Returns bool."""
        for key, rect in (getattr(self, '_map_mode_rects', None) or {}).items():
            if rect.collidepoint(pos):
                self._map_mode = key
                if self._hex_map and hasattr(self._hex_map, 'set_map_mode'):
                    self._hex_map.set_map_mode(key)
                if self._mobile_ui:
                    self._layers_open = False
                return True
        return False

    def _point_in_map_modes(self, pos):
        rects = list(
            (getattr(self, '_map_mode_rects', None) or {}).values())
        for rect in (getattr(self, '_layers_toggle_rect', None),
                     getattr(self, '_activity_toggle_rect', None)):
            if rect:
                rects.append(rect)
        return any(r.collidepoint(pos) for r in rects)

    def _on_conquer(self, tile):
        """Transition to the conquer screen for this land."""
        self.state.conquer_land_id = tile.land_id
        self.state.screen = 'conquer'
        self._detail_box = None

    def _on_defence(self, tile):
        """Transition to the defence screen for this owned land."""
        self.state.defence_land_id = tile.land_id
        self.state.screen = 'defence'
        self._detail_box = None

    def _on_configure_kingdom(self, tile):
        """Transition to the kingdom configuration screen for this land."""
        self.state.kingdom_config_land_id = tile.land_id
        self.state.kingdom_config_id = getattr(tile, 'kingdom_id', None)
        self.state.screen = 'kingdom_config'
        self._detail_box = None

    def _on_message_owner(self, tile):
        """Open the kingdom thread modal for a land owner."""
        self._detail_box = None
        self._open_thread(
            getattr(tile, 'owner_user_id', None),
            getattr(tile, 'owner_username', None) or 'Owner',
            land_id=getattr(tile, 'land_id', None),
            is_ai=bool(getattr(tile, 'owner_is_ai', False)),
        )
