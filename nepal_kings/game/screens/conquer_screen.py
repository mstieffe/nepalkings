# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Conquer screen — configure figures + battle moves for attacking a land."""

import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import (
    MenuScreenMixin,
    menu_chrome_safe_top,
    menu_chrome_safe_width,
)
from game.screens.build_figure_screen import BuildFigureScreen
from game.screens.battle_shop_screen import BattleShopScreen
from game.screens.prelude_spell_screen import PreludeSpellScreen
from game.screens.loot_risk_tutorial import (
    draw_loot_risk_tutorial,
    handle_loot_risk_tutorial_events,
    loot_risk_tutorial_seen,
    open_loot_risk_tutorial,
)
from game.core.card_source import CollectionCardSource
from game.core.figure_buffs import apply_buffs_allies_to_icon_map
from game.core.kingdom_game_proxy import KingdomGameProxy
from game.components.cards.card import Card
from game.components.figures.figure import Figure
from game.components.figures.skill_display_filters import (
    filter_family_for_display,
    filter_figure_for_display,
    strip_duel_only_skill_description,
)
from game.components.figures.figure_icon import FieldFigureIcon
from game.components.figure_detail_box import FigureDetailBox
from game.components.castle_cap_indicator import (
    castle_cap_reached,
    draw_castle_cap_indicator,
)
from game.components import info_popup
from game.components.config_screen_common import (
    DIVIDER,
    ERROR_TEXT,
    SLOT_HOVER_GLOW,
    draw_close_x_button,
    draw_empty_slot,
    draw_hover_tooltip,
    draw_panel as _draw_panel,
    draw_remove_x,
    draw_section_panel,
    fit_text,
    mobile_collide as _mobile_collide,
    open_dialogue,
)
from game.components.figures.figure_manager import FigureManager
from game.components.battle_moves.battle_move_manager import BattleMoveManager
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.components.battle_moves.battle_move_detail_box import BattleMoveDetailBox
from game.components.spells.spell_manager import SpellManager
from game.components.easing import ease_out_back
from game.components.loading_indicator import draw_loading_indicator
from game.core.game import Game
from game.core.screen_routing import gameplay_screen_for
from utils.game_service import fetch_game
from config import settings
from utils import http_compat as requests
from utils import sound
from utils.background_poller import BackgroundPoller
from utils import collection_service
import logging
import sys as _sys

logger = logging.getLogger('nk.screens.conquer')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# ── Overall box ─────────────────────────────────────────────────────
_BOX_PAD    = int(0.020 * _SH)
_BOX_X      = int(0.04 * _SW)
_BOX_Y      = menu_chrome_safe_top(int(0.10 * _SH))
_BOX_W      = menu_chrome_safe_width(_BOX_X, int(0.87 * _SW))
_BOX_BOTTOM = int(0.92 * _SH)
_BOX_H      = _BOX_BOTTOM - _BOX_Y


def _strip_duel_only_skill_description(text):
    return strip_duel_only_skill_description(
        text,
        hide_checkmate=True,
        hide_instant_charge=True,
    )


def _display_family_without_duel_only_skills(family):
    return filter_family_for_display(
        family,
        hide_checkmate=True,
        hide_instant_charge=True,
    )


_CONQUER_PRELUDE_SPELLS = [
    'Draw 2 MainCards', 'Draw 4 MainCards', 'Dump Cards', 'Forced Deal',
    'Poison', 'Health Boost', 'All Seeing Eye', 'Explosion', 'Copy Figure',
    'Peasant War', 'Civil War', 'Blitzkrieg',
    'Invader Swap', 'Royal Decree', 'Landslide',
]

_RIGHT_SECTION_INFO = {
    'battle_plan': {
        'title': 'Battle Plan',
        'message': (
            'Choose the three battle move cards your attacking force will use, one per battle round. '
            'You need all three rounds filled before starting a conquer battle, and these cards are committed to the attack. '
            "You cannot see the defender's setup — commit your plan blind."
        ),
    },
    'prelude_spell': {
        'title': 'Prelude Spell',
        'message': (
            'Prelude spells are optional effects that trigger before the conquer battle starts. '
            'They can draw cards, weaken the defender, or change battle restrictions. Their card cost is locked while committed and can be looted if the attack fails.'
        ),
    },
}

_RED_SUITS = {'Hearts', 'Diamonds'}
_BLACK_SUITS = {'Clubs', 'Spades'}
_CALL_FIELD_MAP = {
    'Call Villager': 'village',
    'Call Military': 'military',
    'Call King': 'castle',
}


class ConquerScreen(MenuScreenMixin, Screen):
    """Conquer configuration screen.

    Reads ``state.conquer_land_id`` to know which land the player
    wants to attack.  Fetches (or creates) the LandConfig from the
    server and lets the user build figures, buy battle moves, and set
    a battle modifier.
    """

    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── Persistent state ────────────────────────────────────────
        self._land_id = None
        self._land = None          # server dict
        self._config = None        # serialised LandConfig
        self._loading = False
        self._loading_started_at_ms = 0
        self._loading_message = 'Loading conquer config...'
        self._error = None
        self._config_poller = None
        self._config_poller_land_id = None
        self._cooldown_remaining = 0
        self._cooldown_synced_at_ms = 0
        self._maps_available = 0
        self._land_cooldown_remaining = 0

        # ── Subscreen state ─────────────────────────────────────────
        self._active_subscreen = None   # 'build_figure' | 'battle_shop' | None
        self._subscreen_obj = None      # BuildFigureScreen or BattleShopScreen instance
        self._game_proxy = None         # KingdomGameProxy

        # ── Fonts (using font_settings categories) ─────────────────
        self._title_font = settings.get_font(settings.FS_SUBTITLE, bold=True)
        self._label_font = settings.get_font(settings.FS_BODY)
        self._value_font = settings.get_font(settings.FS_BODY, bold=True)
        self._btn_font = settings.get_font(settings.FS_BUTTON, bold=True)
        self._small_font = settings.get_font(settings.FS_SMALL)
        self._tiny_font = settings.get_font(settings.FS_TINY)
        self._res_font = settings.get_font(settings.FS_TINY)

        # ── Layout rects (initialised lazily after first data load) ─
        self._field_rects = {}       # 'castle'/'village'/'military' → Rect
        self._move_slots_rect = None  # Rect enclosing all 3 move slots
        self._battle_plan_rect = None
        self._prelude_panel_rect = None
        self._btn_build = None       # "Build Figure" button rect
        self._btn_buy_move = None    # "Buy Move" button rect
        self._btn_battle = None      # "To Battle!" button rect
        self._btn_close_rect = None   # X close button rect
        self._btn_retry = None       # "Retry" button rect (error state only)
        self._res_rect = None        # Resource panel rect
        self._field_title_pos = None  # section title position
        self._moves_title_pos = None  # section title position
        self._prelude_title_pos = None
        self._info_button_rects = {}
        self._active_info_key = None
        self._active_info_popup_rect = None
        self._layout_built = False

        # ── Figure icons (FieldFigureIcon) ──────────────────────────
        self._figure_manager = FigureManager()
        self._move_manager = BattleMoveManager()
        self._figure_objects = []      # Figure objects from config
        self._figure_icons = {}        # figure_id → FieldFigureIcon
        self._figure_detail_box = None
        self._move_detail_box = None
        self._config_version = 0       # incremented on config change
        # ── Entrance animations (draw-only) ─────────────────────────
        # Newly appearing config slots (figures / battle moves / prelude)
        # slide up into place with a small overshoot instead of popping in.
        # Keyed ('fig', id) / ('move', round_index) / ('prelude',); records
        # are {'started_at': ms, 'index': stagger_slot}.  Change detection
        # diffs a config signature (``_config_version`` is vestigial and
        # never incremented).  Offsets apply to DRAW positions only — hit
        # rects always use the resting position.
        self._entrance_anims = {}
        self._entrance_prev_sig = None
        self._pending_map_confirm = False
        self._start_battle_rid = None
        self._start_battle_fetch_game_rid = None
        self._start_battle_fetch_game_id = None
        self._start_battle_poller = None
        self._loot_risk_tutorial_dialogue = None
        self._loot_risk_tutorial_action = None
        self._pending_leave_confirm = False
        self._pending_tooltip = None   # (anchor_rect, text) for edit-icon hover
        self._move_remove_rects = {}   # round_index → Rect for X buttons
        self._empty_move_slot_rects = {}  # round_index → Rect for empty slots

        # ── Battle move slot caches (for draw_battle_move_icon) ─────
        self._slot_glow_cache = {}
        self._slot_frame_cache = {}
        self._slot_icon_cache = {}
        self._suit_icon_cache = {}
        self._slot_font = settings.get_font(settings.BATTLE_MOVE_ICON_FONT_SIZE)
        self._move_slot_size = int(0.055 * _SW)
        self._slot_diamond = None      # empty-slot diamond surface
        self._hovered_slot = -1
        self._init_move_slot_caches()

        # ── Prelude spell icon cache ─────────────────────────────────
        self._spell_icons = {}           # spell_name → icon dict
        self._prelude_spell_rect = None  # Rect for the spell icon slot
        self._prelude_x_rect = None      # Rect for X remove button
        self._spell_manager = SpellManager()
        self._collection_cards = None    # cached collection data
        self._init_spell_icons()

        # ── Resource icon cache ─────────────────────────────────────
        self._resource_icons = {}
        self._init_resource_icons()

        # ── Edit icon (for section title buttons) ───────────────────
        _icon_sz = max(int(0.025 * _SH), settings.TOUCH_ICON_MIN)
        self._edit_icon = pygame.transform.smoothscale(
            pygame.image.load('img/dialogue_box/icons/edit.png').convert_alpha(),
            (_icon_sz, _icon_sz),
        )
        self._edit_icon_size = _icon_sz

        # ── Suit icon for header ─────────────────────────────────
        self._header_suit_icons = {}
        _hdr_suit_sz = int(self._res_font.get_height() * 1.5)
        for suit_name in ('hearts', 'diamonds', 'clubs', 'spades'):
            try:
                raw = pygame.image.load(settings.SUIT_ICON_IMG_PATH + suit_name + '.png').convert_alpha()
                self._header_suit_icons[suit_name] = pygame.transform.smoothscale(raw, (_hdr_suit_sz, _hdr_suit_sz))
            except Exception:
                pass

    @staticmethod
    def _to_int(value, default=0):
        """Safely coerce a numeric config value to an integer for display."""
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return default

    # ── Lifecycle ────────────────────────────────────────────────────

    def on_enter(self):
        """Called each time the conquer screen becomes active — reset cached config."""
        self._land_id = None
        self._land = None
        self._config = None
        self._loading = False
        self._loading_started_at_ms = 0
        self._loading_message = 'Loading conquer config...'
        self._error = None
        self._config_poller = None
        self._config_poller_land_id = None
        self._cooldown_remaining = 0
        self._cooldown_synced_at_ms = 0
        self._maps_available = 0
        self._land_cooldown_remaining = 0
        self._active_subscreen = None
        self._subscreen_obj = None
        self._game_proxy = None
        self._entrance_anims = {}
        self._entrance_prev_sig = None   # None → full cascade on next config
        self._pending_map_confirm = False
        self._start_battle_rid = None
        self._start_battle_fetch_game_rid = None
        self._start_battle_fetch_game_id = None
        self._start_battle_poller = None
        self._loot_risk_tutorial_dialogue = None
        self._loot_risk_tutorial_action = None
        self._figure_objects = []
        self._figure_icons = {}
        self._figure_detail_box = None
        self._layout_built = False
        self._hovered_slot = -1
        self._btn_retry = None
        self._pending_tooltip = None
        self._active_info_key = None
        self._active_info_popup_rect = None

    # ── Asset init helpers ─────────────────────────────────────────

    def _init_move_slot_caches(self):
        """Load glow/frame/icon images for battle move slot rendering."""
        sw = self._move_slot_size
        big_scale = 1.25
        gw = int(sw * 1.6)
        gw_big = int(gw * big_scale)
        frame_w = int(sw * 1.3)
        frame_w_big = int(frame_w * big_scale)
        icon_w = sw - 4
        icon_w_big = int(icon_w * big_scale)

        for name, path in [('green', 'img/game_button/glow/green.png'),
                           ('blue', 'img/game_button/glow/blue.png'),
                           ('yellow', 'img/game_button/glow/yellow.png')]:
            raw = pygame.image.load(path).convert_alpha()
            self._slot_glow_cache[name] = pygame.transform.smoothscale(raw, (gw, gw))
            self._slot_glow_cache[name + '_big'] = pygame.transform.smoothscale(raw, (gw_big, gw_big))

        suit_s = int(settings.SUIT_ICON_WIDTH * 0.6)
        suit_s_big = int(suit_s * big_scale)
        for suit_name in ('hearts', 'diamonds', 'spades', 'clubs'):
            try:
                raw = pygame.image.load(settings.SUIT_ICON_IMG_PATH + suit_name + '.png').convert_alpha()
                self._suit_icon_cache[suit_name] = pygame.transform.smoothscale(raw, (suit_s, suit_s))
                self._suit_icon_cache[suit_name + '_big'] = pygame.transform.smoothscale(raw, (suit_s_big, suit_s_big))
            except Exception:
                pass

        for family in self._move_manager.families:
            if family.frame_img:
                raw = family.frame_img.convert_alpha()
                self._slot_frame_cache[family.name] = pygame.transform.smoothscale(raw, (frame_w, frame_w))
                self._slot_frame_cache[family.name + '_big'] = pygame.transform.smoothscale(raw, (frame_w_big, frame_w_big))
            if family.icon_img:
                raw = family.icon_img.convert_alpha()
                self._slot_icon_cache[family.name] = pygame.transform.smoothscale(raw, (icon_w, icon_w))
                self._slot_icon_cache[family.name + '_big'] = pygame.transform.smoothscale(raw, (icon_w_big, icon_w_big))
        for name, family in self._move_manager.families_by_name.items():
            if name not in self._slot_frame_cache and family.frame_img:
                raw = family.frame_img.convert_alpha()
                self._slot_frame_cache[name] = pygame.transform.smoothscale(raw, (frame_w, frame_w))
                self._slot_frame_cache[name + '_big'] = pygame.transform.smoothscale(raw, (frame_w_big, frame_w_big))
            if name not in self._slot_icon_cache and family.icon_img:
                raw = family.icon_img.convert_alpha()
                self._slot_icon_cache[name] = pygame.transform.smoothscale(raw, (icon_w, icon_w))
                self._slot_icon_cache[name + '_big'] = pygame.transform.smoothscale(raw, (icon_w_big, icon_w_big))

        # Empty slot diamond
        d_size = int(sw * 0.8)
        diamond = pygame.Surface((d_size, d_size), pygame.SRCALPHA)
        pts = [(d_size // 2, 0), (d_size, d_size // 2),
               (d_size // 2, d_size), (0, d_size // 2)]
        pygame.draw.polygon(diamond, (60, 50, 40, 150), pts)
        pygame.draw.polygon(diamond, (120, 100, 70), pts, 1)
        self._slot_diamond = pygame.transform.rotate(diamond, 0)

    def _init_spell_icons(self):
        """Load spell icons with frames from SpellManager for all prelude spells."""
        isz = int(0.045 * _SW)          # icon size
        fsz = int(isz * 1.4)            # frame size (same ratio as SpellIcon)
        ssz = int(isz * 0.4)            # success badge size
        xsz = int(isz * 0.3)            # X-remove button size
        self._mod_icon_size = isz
        self._mod_frame_size = fsz

        # Hover-scaled sizes (15% larger)
        isz_h = int(isz * 1.15)
        fsz_h = int(fsz * 1.15)

        for spell_name in _CONQUER_PRELUDE_SPELLS:
            family = self._spell_manager.get_family_by_name(spell_name)
            if not family:
                continue
            self._spell_icons[spell_name] = {
                'icon': pygame.transform.smoothscale(family.icon_img, (isz, isz)) if family.icon_img else None,
                'icon_gray': pygame.transform.smoothscale(family.icon_gray_img, (isz, isz)) if family.icon_gray_img else None,
                'frame': pygame.transform.smoothscale(family.frame_img, (fsz, fsz)) if family.frame_img else None,
                'frame_gray': pygame.transform.smoothscale(family.frame_closed_img, (fsz, fsz)) if family.frame_closed_img else None,
                'glow': pygame.transform.smoothscale(family.glow_img, (fsz + 12, fsz + 12)) if family.glow_img else None,
                'description': family.description,
                'mini_game_description': family.mini_game_description,
            }

        # Success badge
        try:
            raw = pygame.image.load('img/dialogue_box/icons/success.png').convert_alpha()
            self._success_badge = pygame.transform.smoothscale(raw, (ssz, ssz))
        except Exception:
            self._success_badge = None

        # X-remove surface
        xf = settings.get_font(xsz, bold=True)
        self._x_remove_surf = xf.render('X', True, (220, 60, 60))

        # Unified X-button size for all icon types
        self._x_btn_sz = max(int(0.016 * _SW), 16)
        if settings.TOUCH_TARGET_MIN > 0:
            self._x_btn_sz = max(self._x_btn_sz, int(0.045 * _SH))

    def _init_resource_icons(self):
        """Load resource icons for the info panel."""
        icon_size = int(0.019 * _SW)
        for key, path in settings.RESOURCE_ICON_IMG_PATH_DICT.items():
            try:
                raw = pygame.image.load(path).convert_alpha()
                self._resource_icons[key] = pygame.transform.smoothscale(raw, (icon_size, icon_size))
            except Exception:
                pass

    # ── Layout ──────────────────────────────────────────────────────

    def _build_layout(self):
        """Compute rects based on screen dimensions."""
        pad = int(0.02 * _SW)
        top = _BOX_Y + _BOX_PAD + int(0.045 * _SH)   # below compact title

        # Section title row height — extra gap below subtitle (gold rate / suit bonus)
        section_h = int(0.03 * _SH) + int(0.01 * _SH)
        content_top = top + section_h + int(0.65 * pad)

        # Left half: 3 field compartments, trimmed slightly so the action
        # column gets the same breathing room as the defence screen.
        field_w = int(0.132 * _SW)
        field_h = int(0.48 * _SH)
        fx = _BOX_X + pad
        for field in ('castle', 'village', 'military'):
            self._field_rects[field] = pygame.Rect(fx, content_top, field_w, field_h)
            fx += field_w + pad

        # Edit icon button next to "Conquer Field" section title
        isz = self._edit_icon_size
        field_title_surf = self._label_font.render('Conquer Field', True, (0, 0, 0))
        title_w = field_title_surf.get_width()
        self._field_title_pos = (_BOX_X + pad, top)
        self._btn_build = pygame.Rect(
            _BOX_X + pad + title_w + int(0.008 * _SW),
            top + (field_title_surf.get_height() - isz) // 2,
            isz, isz,
        )

        # Right column: battle plan + prelude spell panels.
        right_x = _BOX_X + pad + 3 * (field_w + pad)
        self._right_x = right_x
        right_right = _BOX_X + _BOX_W - _BOX_PAD
        right_w = right_right - right_x
        panel_gap = int(0.014 * _SH)
        panel_pad = int(0.010 * _SW)
        panel_pad_y = int(0.010 * _SH)
        mobile_ui = settings.TOUCH_TARGET_MIN > 0

        # To Battle — lower right of box
        battle_w = int(0.20 * _SW)
        battle_h = max(int(0.055 * _SH), settings.TOUCH_TARGET_MIN)
        self._btn_battle = pygame.Rect(
            _BOX_X + _BOX_W - _BOX_PAD - battle_w,
            _BOX_BOTTOM - _BOX_PAD - battle_h,
            battle_w, battle_h,
        )

        sw = self._move_slot_size
        slot_spacing = int(sw * 2.0)
        slots_w = slot_spacing * 2 + sw * 2
        slot_row_h = int(sw * 2.0)
        fsz = self._mod_frame_size
        header_h = self._label_font.get_height() + self._res_font.get_height() + int(0.015 * _SH)
        if mobile_ui:
            header_h = max(header_h, settings.TOUCH_COMPACT_MIN + int(0.010 * _SH))
        right_content_bottom = self._btn_battle.y - panel_gap
        right_content_h = max(1, right_content_bottom - content_top)
        available_panel_h = max(1, right_content_h - panel_gap)
        battle_plan_min_h = header_h + slot_row_h + panel_pad_y
        prelude_min_h = header_h + fsz + panel_pad_y
        battle_plan_h = min(
            max(battle_plan_min_h, int(available_panel_h * 0.58)),
            max(battle_plan_min_h, available_panel_h - prelude_min_h),
        )
        prelude_h = max(prelude_min_h, available_panel_h - battle_plan_h)

        self._battle_plan_rect = pygame.Rect(right_x, content_top, right_w, battle_plan_h)
        self._prelude_panel_rect = pygame.Rect(
            right_x, self._battle_plan_rect.bottom + panel_gap, right_w, prelude_h)
        self._info_button_rects = {
            'battle_plan': self._info_button_rect(self._battle_plan_rect),
            'prelude_spell': self._info_button_rect(self._prelude_panel_rect),
        }

        # Edit icon button next to "Battle Plan" section title
        moves_title_surf = self._label_font.render('Battle Plan', True, (0, 0, 0))
        moves_w = moves_title_surf.get_width()
        self._moves_title_pos = (
            self._battle_plan_rect.x + panel_pad,
            self._battle_plan_rect.y + int(0.010 * _SH),
        )
        self._btn_buy_move = pygame.Rect(
            self._moves_title_pos[0] + moves_w + int(0.008 * _SW),
            self._moves_title_pos[1] + (moves_title_surf.get_height() - isz) // 2,
            isz, isz,
        )

        # Battle move slots — 3 diamond icons in a row
        self._move_slots_rect = pygame.Rect(
            self._battle_plan_rect.centerx - slots_w // 2,
            self._battle_plan_rect.y + header_h,
            slots_w,
            slot_row_h,
        )

        # Prelude spell section — single spell icon slot
        prelude_header_y = self._prelude_panel_rect.y + int(0.010 * _SH)
        self._mod_section_y = self._prelude_panel_rect.y + header_h
        # Single spell icon slot
        self._prelude_spell_rect = pygame.Rect(
            self._prelude_panel_rect.x + panel_pad,
            self._mod_section_y,
            fsz,
            fsz,
        )
        # Edit icon button next to "Prelude Spell" section title
        prelude_title_surf = self._small_font.render('Prelude Spell', True, (0, 0, 0))
        prelude_title_w = prelude_title_surf.get_width()
        self._prelude_title_pos = (self._prelude_panel_rect.x + panel_pad, prelude_header_y)
        self._btn_prelude_edit = pygame.Rect(
            self._prelude_title_pos[0] + prelude_title_w + int(0.008 * _SW),
            self._prelude_title_pos[1] + (prelude_title_surf.get_height() - isz) // 2,
            isz, isz,
        )

        # Combined resource panel below castle+village field compartments
        castle_r = self._field_rects['castle']
        village_r = self._field_rects['village']
        res_top = castle_r.bottom + pad + int(0.005 * _SH)
        res_w = village_r.right - castle_r.x
        res_h = max(1, _BOX_BOTTOM - _BOX_PAD - res_top)
        self._res_rect = pygame.Rect(castle_r.x, res_top, res_w, res_h)

        # ── Divider positions ──────────────────────────────────────
        # Vertical: between left fields/resources and right battle column
        self._divider_v_x = right_x - pad // 2
        self._divider_v_top = content_top
        self._divider_v_bottom = _BOX_BOTTOM - _BOX_PAD

        # X close button (top-right of box)
        _xsz = max(int(0.028 * _SH), settings.TOUCH_COMPACT_MIN)
        _xmargin = int(0.012 * _SW)
        self._btn_close_rect = pygame.Rect(
            _BOX_X + _BOX_W - _xsz - _xmargin,
            _BOX_Y + _xmargin,
            _xsz, _xsz)

        self._layout_built = True

    # ── Data loading ────────────────────────────────────────────────

    @staticmethod
    def _response_json(response):
        try:
            return response.json()
        except Exception:
            return {}

    @classmethod
    def _transform_config_bundle_async(cls, responses):
        config_resp = (responses or {}).get('config')
        if config_resp is None:
            return {'error': 'Connection error'}
        if getattr(config_resp, 'status_code', 0) != 200:
            err = cls._response_json(config_resp)
            return {'error': err.get('error', err.get('message', 'Failed to load conquer config'))}
        result = {'config_data': cls._response_json(config_resp), 'collection_data': {}}
        collection_resp = (responses or {}).get('collection')
        if collection_resp is not None and getattr(collection_resp, 'status_code', 0) == 200:
            result['collection_data'] = cls._response_json(collection_resp)
        return result

    def _fetch_config_bundle(self, land_id):
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/conquer/config',
                params={'land_id': land_id},
                timeout=15,
            )
            if resp.status_code != 200:
                err = self._response_json(resp)
                return {'error': err.get('error', err.get('message', 'Failed to load conquer config'))}
            collection_data = {}
            try:
                collection_data = collection_service.fetch_collection_cards()
            except Exception as e:
                logger.error(f'Collection fetch error: {e}')
            return {
                'config_data': resp.json(),
                'collection_data': collection_data,
            }
        except Exception as e:
            logger.error(f'Conquer config load error: {e}')
            return {'error': 'Connection error'}

    def _start_config_load(self):
        if not self._land_id:
            return
        if self._config_poller is None:
            base = settings.SERVER_URL
            self._config_poller = BackgroundPoller(
                self._fetch_config_bundle,
                async_requests=[
                    {'key': 'config', 'url': f'{base}/kingdom/conquer/config',
                     'params': {'land_id': 0}},
                    {'key': 'collection', 'url': f'{base}/collection/cards'},
                ],
                async_transform=self._transform_config_bundle_async,
            )
        if self._config_poller.busy:
            return
        self._loading = True
        self._loading_started_at_ms = pygame.time.get_ticks()
        self._loading_message = 'Fetching conquer config...'
        self._error = None
        self._config_poller_land_id = self._land_id
        self._config_poller.poll(args=(self._land_id,))

    def _drain_config_poller(self):
        poller = self._config_poller
        if poller is None or not poller.has_result():
            return
        result = poller.result or {}
        expected_land_id = self._config_poller_land_id
        self._config_poller_land_id = None
        if expected_land_id != self._land_id:
            self._loading = False
            return
        if result.get('error'):
            self._error = result.get('error') or 'Connection error'
            self._loading = False
            return
        data = result.get('config_data') or {}
        self._loading_message = 'Building conquer figures...'
        self._config = data.get('config')
        self._land = data.get('land')
        self._set_cooldown_state(data)
        self._collection_cards = (result.get('collection_data') or {}).get('cards', [])
        self._rebuild_figure_objects()
        self._loading = False
        logger.debug(f'Conquer config loaded for land {self._land_id}')

    def _load_config(self):
        """Fetch (or create) the conquer config from the server."""
        self._loading = True
        self._loading_started_at_ms = pygame.time.get_ticks()
        self._loading_message = 'Fetching conquer config...'
        self._error = None
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/conquer/config',
                params={'land_id': self._land_id},
                timeout=15,
            )
            if resp.status_code != 200:
                err = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
                self._error = err.get('error', 'Failed to load conquer config')
                self._loading = False
                return
            data = resp.json()
            self._config = data.get('config')
            self._land = data.get('land')
            self._set_cooldown_state(data)
            self._loading = False
            self._rebuild_figure_objects()
            self._refresh_collection()
            logger.debug(f'Conquer config loaded for land {self._land_id}')
        except Exception as e:
            self._error = 'Connection error'
            logger.error(f'Conquer config load error: {e}')
            self._loading = False

    def _set_cooldown_state(self, data):
        """Store server cooldown/map metadata for local countdown display."""
        data = data or {}
        try:
            self._cooldown_remaining = max(
                0, int(data.get('conquer_cooldown_remaining',
                                data.get('cooldown_remaining', 0)) or 0))
        except (TypeError, ValueError):
            self._cooldown_remaining = 0
        try:
            user_maps = 0
            if getattr(self.state, 'user_dict', None):
                user_maps = self.state.user_dict.get('maps', 0)
            self._maps_available = max(
                0, int(data.get('maps_available', user_maps) or 0))
        except (TypeError, ValueError):
            self._maps_available = 0
        try:
            self._land_cooldown_remaining = max(
                0, int(data.get('land_conquer_cooldown_remaining', 0) or 0))
        except (TypeError, ValueError):
            self._land_cooldown_remaining = 0
        self._cooldown_synced_at_ms = pygame.time.get_ticks()
        if getattr(self.state, 'user_dict', None) is not None:
            self.state.user_dict['maps'] = self._maps_available

    @staticmethod
    def _format_duration(seconds):
        seconds = max(0, int(seconds or 0))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours:
            return f'{hours}h {minutes:02d}m'
        if minutes:
            return f'{minutes}m {secs:02d}s'
        return f'{secs}s'

    def _current_cooldown_remaining(self):
        base = max(0, int(getattr(self, '_cooldown_remaining', 0) or 0))
        synced_at = int(getattr(self, '_cooldown_synced_at_ms', 0) or 0)
        if base <= 0 or synced_at <= 0:
            return base
        elapsed = max(0, (pygame.time.get_ticks() - synced_at) // 1000)
        return max(0, base - elapsed)

    def _battle_button_label(self):
        if not self._is_battle_ready():
            return 'To Battle!'
        remaining = self._current_cooldown_remaining()
        if remaining <= 0:
            return 'To Battle!'
        text = self._format_duration(remaining)
        return f'Cooldown {text}'

    # ── Server actions ──────────────────────────────────────────────

    def _server_remove_figure(self, figure_id):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/remove_figure',
                json={'figure_id': figure_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
                self._rebuild_figure_objects()
                sound.play('card_slide')
            else:
                logger.warning(f'Remove figure failed: {data.get("message")}')
        except Exception as e:
            logger.error(f'Remove figure error: {e}')

    def _server_return_move(self, move_id):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/return_battle_move',
                json={'move_id': move_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
                sound.play('card_slide')
            else:
                logger.warning(f'Return move failed: {data.get("message")}')
        except Exception as e:
            logger.error(f'Return move error: {e}')

    def _server_set_prelude_spell(self, spell_name):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/set_prelude_spell',
                json={'land_id': self._land_id, 'spell_name': spell_name},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
                self._refresh_collection()
            else:
                self.state.set_msg(data.get('message', 'Cannot set prelude spell'))
        except Exception as e:
            logger.error(f'Set prelude spell error: {e}')

    def _server_clear_prelude_spell(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/clear_prelude_spell',
                json={'land_id': self._land_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
                self._refresh_collection()
                sound.play('card_slide')
        except Exception as e:
            logger.error(f'Clear prelude spell error: {e}')

    # ── Collection helpers ─────────────────────────────────────────

    def _refresh_collection(self):
        """Fetch collection cards to determine card availability."""
        try:
            data = collection_service.fetch_collection_cards()
            self._collection_cards = data.get('cards', [])
        except Exception as e:
            logger.error(f'Collection fetch error: {e}')
            self._collection_cards = []

    # ── Figure conversion ──────────────────────────────────────────

    def _rebuild_figure_objects(self):
        """Convert config figure dicts into real Figure objects + FieldFigureIcons."""
        families = self._figure_manager.families
        self._figure_objects = []
        old_icons = dict(self._figure_icons)
        self._figure_icons = {}

        resources_data = self._calc_resources()

        # Lightweight game proxy so FieldFigureIcon can apply land suit bonus
        land = self._land or {}
        game_proxy = KingdomGameProxy(
            self._config, self._land_id, mode='conquer',
            land_suit_bonus_suit=land.get('suit_bonus_suit'),
            land_suit_bonus_value=land.get('suit_bonus_value'),
            land=land,
        )

        # First pass: build the complete figure list. Support-bonus depends
        # on every other same-suit ally being known, so we must NOT compute
        # `battle_bonus_received` until the list is fully assembled (otherwise
        # the displayed bonus becomes order-dependent on build order).
        for cfg_fig in self._config.get('figures', []):
            fig = self._config_fig_to_figure(cfg_fig, families)
            if fig is None:
                continue
            self._figure_objects.append(fig)

        # Second pass: create / refresh icons with the complete list.
        for fig in self._figure_objects:
            if fig.id in old_icons:
                icon = old_icons[fig.id]
                icon.figure = fig
                icon.game = game_proxy
                icon.has_deficit = icon._check_resource_deficit(resources_data)
            else:
                icon = FieldFigureIcon(
                    window=self.window,
                    game=game_proxy,
                    figure=fig,
                    is_visible=True,
                    all_player_figures=self._figure_objects,
                    resources_data=resources_data,
                )
            # Always recompute against the full figure list so bonuses are
            # consistent regardless of which figure was just (re)built.
            icon.battle_bonus_received = icon._calculate_battle_bonus_received(
                self._figure_objects
            )
            self._figure_icons[fig.id] = icon

        apply_buffs_allies_to_icon_map(
            self._figure_objects,
            self._figure_icons,
            has_deficit=lambda fig: (
                fig.id in self._figure_icons and self._figure_icons[fig.id].has_deficit
            ),
        )

    def _config_fig_to_figure(self, cfg_fig, families):
        """Convert a config figure dict to a real Figure object."""
        family_name = cfg_fig.get('family_name', '')
        family = families.get(family_name)
        if not family:
            return None

        suit = cfg_fig.get('suit', '')
        name = cfg_fig.get('name', family_name)

        # Match to the exact figure variant in the family definition
        matched = None
        for fam_fig in family.figures:
            if fam_fig.suit == suit and fam_fig.name == name:
                matched = fam_fig
                break
        if matched is None:
            # Fallback: match by suit only
            for fam_fig in family.figures:
                if fam_fig.suit == suit:
                    matched = fam_fig
                    break

        card_specs = cfg_fig.get('card_specs') or []
        card_roles = cfg_fig.get('card_roles') or []
        key_cards = []
        number_card = None
        upgrade_card = None
        if card_specs:
            for spec, role in zip(card_specs, card_roles):
                if not spec:
                    continue
                card = Card(
                    rank=spec['rank'], suit=spec['suit'], value=spec['value'],
                )
                if role == 'key':
                    key_cards.append(card)
                elif role == 'number':
                    number_card = card
                elif role == 'upgrade':
                    upgrade_card = card
        if not key_cards and not number_card and not upgrade_card:
            key_cards = matched.key_cards if matched else []
            number_card = matched.number_card if matched else None
            upgrade_card = matched.upgrade_card if matched else None

        display_family = _display_family_without_duel_only_skills(family)

        figure = Figure(
            name=name,
            sub_name=matched.sub_name if matched else '',
            suit=suit,
            family=display_family,
            key_cards=key_cards,
            number_card=number_card,
            upgrade_card=upgrade_card,
            upgrade_family_name=cfg_fig.get('upgrade_family_name'),
            produces=cfg_fig.get('produces', {}),
            requires=cfg_fig.get('requires', {}),
            description=_strip_duel_only_skill_description(cfg_fig.get('description', '')),
            id=cfg_fig['id'],
            cannot_attack=getattr(matched, 'cannot_attack', False) if matched else False,
            must_be_attacked=getattr(matched, 'must_be_attacked', False) if matched else False,
            rest_after_attack=cfg_fig.get('rest_after_attack', False),
            distance_attack=getattr(matched, 'distance_attack', False) if matched else False,
            buffs_allies=getattr(matched, 'buffs_allies', False) if matched else False,
            buffs_allies_defence=getattr(matched, 'buffs_allies_defence', False) if matched else False,
            blocks_bonus=getattr(matched, 'blocks_bonus', False) if matched else False,
            cannot_defend=getattr(matched, 'cannot_defend', False) if matched else False,
            instant_charge=getattr(matched, 'instant_charge', False) if matched else False,
            cannot_be_blocked=cfg_fig.get('cannot_be_blocked', False),
            cannot_be_targeted=getattr(matched, 'cannot_be_targeted', False) if matched else False,
            override_base_power=getattr(matched, 'override_base_power', None) if matched else None,
        )
        return filter_figure_for_display(
            figure,
            hide_checkmate=True,
            hide_instant_charge=True,
        )

    def _calc_resources(self):
        """Calculate produces/requires from config figures."""
        produces = {}
        requires = {}
        for fig in self._config.get('figures', []):
            for res, amt in (fig.get('produces') or {}).items():
                produces[res] = produces.get(res, 0) + amt
            for res, amt in (fig.get('requires') or {}).items():
                requires[res] = requires.get(res, 0) + amt
        return {'produces': produces, 'requires': requires}

    def _info_button_rect(self, panel_rect):
        return info_popup.info_button_rect(panel_rect)

    def _draw_info_button(self, rect, active=False):
        info_popup.draw_info_button(self.window, rect, active=active)

    def _wrap_info_text(self, text, font, max_width):
        return info_popup.wrap_info_text(text, font, max_width)

    def _draw_info_popup(self):
        info = _RIGHT_SECTION_INFO.get(self._active_info_key)
        anchor = self._info_button_rects.get(self._active_info_key) if self._active_info_key else None
        self._active_info_popup_rect = info_popup.draw_info_popup(
            self.window, info, anchor,
            box_rect=pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H),
            box_pad=_BOX_PAD,
            max_panel_w=self._battle_plan_rect.w,
            title_font=self._small_font,
            body_font=self._res_font,
        )

    def _draw_info_buttons(self):
        for key, rect in self._info_button_rects.items():
            self._draw_info_button(rect, active=(key == self._active_info_key))

    def _handle_info_button_event(self, event):
        consumed, new_key, hit_button = info_popup.handle_info_event(
            event, self._info_button_rects, self._active_info_key,
            self._active_info_popup_rect, collide=_mobile_collide)
        if not consumed:
            return False
        if hit_button:
            sound.play('ui_click', volume=0.6)
        self._active_info_key = new_key
        if new_key is None:
            self._active_info_popup_rect = None
        return True

    def _draw_section_panel(self, rect, title, *, description=None,
                            icon_rect=None, title_pos=None):
        """Draw a quiet section card with one title row and optional edit icon."""
        font = self._label_font if title == 'Battle Plan' else self._small_font
        draw_section_panel(
            self.window, rect, title,
            title_font=font, desc_font=self._res_font,
            edit_icon=self._edit_icon,
            description=description, icon_rect=icon_rect, title_pos=title_pos)

    def _fit_text(self, text, font, max_width):
        """Trim text with an ellipsis so captions stay inside their panel."""
        return fit_text(text, font, max_width)

    def _draw_caption_lines(self, lines, x, y, max_width, *, line_gap=2):
        """Draw fitted caption lines and return the bottom y position."""
        cy = y
        for text, font, color in lines:
            fitted = self._fit_text(text, font, max_width)
            surf = font.render(fitted, True, color)
            self.window.blit(surf, (x, cy))
            cy += surf.get_height() + line_gap
        return cy - line_gap

    def _draw_right_panels(self):
        """Draw structured panels behind the right-column controls."""
        mobile_ui = settings.TOUCH_TARGET_MIN > 0
        self._draw_section_panel(
            self._battle_plan_rect,
            'Battle Plan',
            description=None if mobile_ui else 'Assign cards for battle rounds',
            icon_rect=self._btn_buy_move,
            title_pos=self._moves_title_pos,
        )
        self._draw_section_panel(
            self._prelude_panel_rect,
            'Prelude Spell',
            description=None if mobile_ui else 'Optional spell before battle',
            icon_rect=self._btn_prelude_edit,
            title_pos=self._prelude_title_pos,
        )
        self._draw_info_buttons()

    # ── Rendering ───────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        # If a subscreen is active, render it instead of the config UI
        if self._active_subscreen and self._subscreen_obj:
            self._subscreen_obj.draw()
            self._draw_menu_overlay()
            return

        # Outer box
        box_rect = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        _draw_panel(self.window, box_rect)

        if self._loading:
            draw_loading_indicator(
                self.window,
                box_rect,
                self._loading_message,
                started_at_ms=self._loading_started_at_ms,
                title='Conquer Setup',
                font=self._label_font,
                small_font=self._small_font,
            )
            self._draw_menu_overlay()
            return

        if self._error:
            txt = self._label_font.render(self._error, True, ERROR_TEXT)
            self.window.blit(txt, txt.get_rect(center=(_SW // 2, _SH // 2)))
            btn_w = int(0.12 * _SW)
            btn_h = max(int(0.05 * _SH), settings.TOUCH_TARGET_MIN)
            self._btn_retry = pygame.Rect(
                _SW // 2 - btn_w // 2, _SH // 2 + int(0.05 * _SH), btn_w, btn_h)
            self._draw_button(self._btn_retry, 'Retry', (100, 140, 90))
            self._draw_close_x_button()
            self._draw_menu_overlay()
            return
        self._btn_retry = None

        if not self._config:
            self._draw_menu_overlay()
            return

        if not self._layout_built:
            self._build_layout()

        # Stamp entrance animations for slots that just appeared.
        self._sync_entrance_animations()

        # ── Title (centred inside box) ──────────────────────────────
        land = self._land or {}
        tier = land.get('tier', '?')
        owner = land.get('owner')
        if owner:
            defender_name = owner.get('username', 'Unknown')
        else:
            defender_name = land.get('ai_name') or 'AI'
        title = f'Conquer Land (Tier {tier}) \u2014 Defended by {defender_name}'
        title_max_w = _BOX_W - 2 * _BOX_PAD
        if self._btn_close_rect:
            title_max_w -= self._btn_close_rect.w + int(0.02 * _SW)
        title = self._fit_text(title, self._title_font, title_max_w)
        t_surf = self._title_font.render(title, True, (250, 221, 0))
        self.window.blit(t_surf, t_surf.get_rect(centerx=_BOX_X + _BOX_W // 2,
                                                  top=_BOX_Y + _BOX_PAD))

        # Land specifications
        gold_rate = self._to_int(land.get('gold_rate', 0), 0)
        suit = land.get('suit_bonus_suit', '?')
        bonus = self._to_int(land.get('suit_bonus_value', 0), 0)
        specs_text = f'Gold: {gold_rate}/hr  |  Suit Bonus: +{bonus} '
        specs_surf = self._res_font.render(specs_text, True, (180, 170, 140))
        suit_icon = self._header_suit_icons.get(suit.lower())
        fog_surf = None
        if settings.TOUCH_TARGET_MIN <= 0:
            # Fog of war: the defender's setup is never revealed pre-battle.
            fog_surf = self._res_font.render(
                '  |  Enemy defence hidden', True, (150, 140, 115))
        total_w = (specs_surf.get_width()
                   + (suit_icon.get_width() + 2 if suit_icon else 0)
                   + (fog_surf.get_width() if fog_surf else 0))
        specs_x = _BOX_X + _BOX_W // 2 - total_w // 2
        specs_y = _BOX_Y + _BOX_PAD + t_surf.get_height() + 4
        self.window.blit(specs_surf, (specs_x, specs_y))
        cursor_x = specs_x + specs_surf.get_width()
        if suit_icon:
            self.window.blit(suit_icon, (cursor_x + 2,
                                        specs_y + (specs_surf.get_height() - suit_icon.get_height()) // 2))
            cursor_x += suit_icon.get_width() + 2
        if fog_surf:
            self.window.blit(fog_surf, (cursor_x, specs_y))

        loot_effects = [e for e in (land.get('kingdom_skill_effects') or []) if 'loot chance' in e]
        if loot_effects and settings.TOUCH_TARGET_MIN <= 0:
            effect_text = self._fit_text(loot_effects[0], self._tiny_font, int(_BOX_W * 0.72))
            effect_surf = self._tiny_font.render(effect_text, True, settings.KINGDOM_CONFIG_HIGHLIGHT)
            self.window.blit(effect_surf, effect_surf.get_rect(centerx=_BOX_X + _BOX_W // 2,
                                                               top=specs_y + specs_surf.get_height() + 3))

        self._draw_right_panels()

        # ── Field compartments with figure icons ────────────────────
        self._draw_field_compartments()

        # ── Battle move slots ───────────────────────────────────────
        self._draw_battle_move_slots()

        # ── Prelude Spell ───────────────────────────────────────────
        self._draw_prelude_spell()

        # ── Resources ───────────────────────────────────────────────
        self._draw_resources()

        # ── Divider lines ───────────────────────────────────────────
        # Vertical divider between left (field/resources) and right (battle) columns
        pygame.draw.line(self.window, DIVIDER,
                         (self._divider_v_x, self._divider_v_top),
                         (self._divider_v_x, self._divider_v_bottom), 1)

        # ── Section titles with edit icon buttons ───────────────────
        self._draw_section_title('Conquer Field', self._field_title_pos, self._btn_build,
                                description='Place figures to grow your economy')

        # To Battle — enabled only when ready
        ready = self._is_battle_ready()
        cooldown = self._current_cooldown_remaining() if ready else 0
        if ready and cooldown > 0:
            battle_clr = (178, 130, 36) if self._maps_available > 0 else (92, 82, 68)
        else:
            battle_clr = (200, 170, 0) if ready else (80, 80, 80)
        self._draw_button(self._btn_battle, self._battle_button_label(), battle_clr)

        self._draw_close_x_button()

        # ── Detail boxes (drawn last, on top) ──────────────────────
        if self._figure_detail_box:
            self._figure_detail_box.draw()
        if self._move_detail_box:
            self._move_detail_box.draw()

        self._draw_info_popup()

        # Desktop hover tooltips for the small edit (pencil) icons
        self._pending_tooltip = None
        if (settings.TOUCH_TARGET_MIN <= 0 and not self.dialogue_box
                and not self._figure_detail_box and not self._move_detail_box):
            mpos = pygame.mouse.get_pos()
            for icon_rect, tip in (
                (self._btn_build, 'Build a figure'),
                (self._btn_buy_move, 'Buy battle moves'),
                (self._btn_prelude_edit, 'Choose a spell'),
            ):
                if icon_rect and icon_rect.collidepoint(mpos):
                    self._pending_tooltip = (icon_rect, tip)
                    break
        if self._pending_tooltip:
            draw_hover_tooltip(self.window, self._pending_tooltip[0],
                               self._pending_tooltip[1], self._res_font)

        self._draw_menu_overlay()
        self._draw_menu_coach(self._current_conquer_coach_step())
        draw_loot_risk_tutorial(self)

    def _conquer_coach_ready(self):
        # The starter conquer config is preassembled server-side, so the first
        # battle can happen before the player opens any boosters.
        return 'finish_first_conquer_battle' not in self._onboarding_completed_steps()

    def _conquer_field_coach_rect(self):
        rects = [rect for rect in getattr(self, '_field_rects', {}).values() if rect]
        for rect in (getattr(self, '_res_rect', None), getattr(self, '_btn_build', None)):
            if rect:
                rects.append(rect)
        if not rects:
            return None
        bounds = rects[0].copy()
        for rect in rects[1:]:
            bounds.union_ip(rect)
        return bounds

    def _conquer_combined_rect(self, *rects):
        usable = [rect for rect in rects if rect]
        if not usable:
            return None
        bounds = usable[0].copy()
        for rect in usable[1:]:
            bounds.union_ip(rect)
        return bounds

    def _second_build_coach_ready(self):
        """True during the player's guided second conquest (build-it-yourself).

        The first conquer attack is pre-assembled; this coaches the *next* one,
        which the player builds by hand. Gated to exactly one finished conquer
        battle so it fires only for the second conquest and never again.
        """
        onboarding = (getattr(self.state, 'user_dict', None) or {}).get('onboarding') or {}
        if not onboarding or onboarding.get('onboarding_skipped'):
            return False
        completed = set(onboarding.get('completed_steps') or [])
        if 'finish_first_conquer_battle' not in completed:
            return False
        facts = onboarding.get('facts') or {}
        return int(facts.get('conquer_battles') or 0) == 1

    def _second_build_coach_step(self, seen):
        if not self._second_build_coach_ready():
            return None
        figures = (self._config or {}).get('figures', []) if self._config else []
        if self._btn_build and 'conquer_build_yourself' not in seen:
            return {
                'id': 'conquer_build_yourself',
                'rect': self._btn_build,
                'title': 'Now Build It Yourself',
                'body': 'Time to build an attack yourself. Tap Build and pick a glowing recipe: start with your King, then add a Farm and Warriors the same way.',
                'action': 'click',
                'mark_on_click': True,
                'max_lines': 5,
            }
        if not figures:
            # Wait until the player has actually built a figure before moving on.
            return None
        battle_plan_rect = self._conquer_combined_rect(
            self._battle_plan_rect, self._btn_buy_move)
        if battle_plan_rect and 'conquer_build_yourself_tactics' not in seen:
            return {
                'id': 'conquer_build_yourself_tactics',
                'rect': battle_plan_rect,
                'title': 'Add Your Tactics',
                'body': 'Now set your battle plan: add three Daggers as tactics, just like your first attack.',
                'action': 'next',
                'button_label': 'Got it',
                'max_lines': 4,
            }
        if self._btn_battle and 'conquer_build_yourself_battle' not in seen:
            return {
                'id': 'conquer_build_yourself_battle',
                'rect': self._btn_battle,
                'title': 'Start When Ready',
                'body': 'When you have a figure and three tactics, Start Battle lights up. This defender is real, so your build decides the fight.',
                'action': 'next',
                'button_label': 'Got it',
                'max_lines': 5,
            }
        return None

    def _current_conquer_coach_step(self):
        if not self._menu_coach_allowed_common():
            return None
        if (self._loading or self._error or not self._config or not self._layout_built
                or self._active_subscreen or self._figure_detail_box or self._move_detail_box
                or self._active_info_key):
            return None
        seen = self._menu_coach_seen()
        # Guided second conquest: pay off the "build it yourself" promise.
        second = self._second_build_coach_step(seen)
        if second is not None:
            return second
        if not self._conquer_coach_ready():
            return None
        # The first attack is pre-assembled, so a single card orients the
        # player and sends them straight into battle. Detailed mechanics are
        # taught in context once the battle is under way.
        if self._btn_battle and 'conquer_config_to_battle' not in seen:
            return {
                'id': 'conquer_config_to_battle',
                'rect': self._btn_battle,
                'title': 'Your Attack Is Ready',
                'body': 'Here is your attack: figures for power, three tactics for the rounds, and a prelude spell. Tap Start Battle to try it out.',
                'action': 'next',
                'button_label': 'Got it',
                'max_lines': 5,
            }
        return None

    # ── Entrance animations (draw-only) ──────────────────────────────

    #: Duration of one slot's slide-in, and the cascade gap between slots.
    ENTRANCE_MS = 380
    ENTRANCE_STAGGER_MS = 70
    ENTRANCE_SLIDE_PX = max(18, int(0.028 * _SH))

    def _config_entrance_signature(self):
        """Cheap identity of the visible config slots for change detection."""
        cfg = self._config or {}
        fig_ids = tuple(sorted(
            str(f.get('id')) for f in (cfg.get('figures') or [])))
        move_keys = tuple(sorted(
            (int(m.get('round_index', -1)), str(m.get('family_name')))
            for m in (cfg.get('battle_moves') or [])))
        prelude = cfg.get('prelude_spell_name') or None
        return fig_ids, move_keys, prelude

    def _sync_entrance_animations(self):
        """Stamp entrance records for newly appearing config slots.

        Diffs a config signature each frame (covering every ``self._config``
        assignment site uniformly — ``_config_version`` is never bumped), so
        the first config sighting cascades the whole board in and later
        changes animate only the new slot(s).  Fail-soft: on any hiccup the
        board simply appears instantly, exactly as before.
        """
        try:
            sig = self._config_entrance_signature()
        except Exception:
            return
        prev = self._entrance_prev_sig
        if sig == prev:
            return
        self._entrance_prev_sig = sig
        now = pygame.time.get_ticks()
        prev_figs = set(prev[0]) if prev else set()
        prev_moves = set(prev[1]) if prev else set()
        prev_prelude = prev[2] if prev else None
        stagger = 0
        for fid in sig[0]:
            if fid not in prev_figs:
                self._entrance_anims[('fig', fid)] = {
                    'started_at': now, 'index': stagger}
                stagger += 1
        for key in sig[1]:
            if key not in prev_moves:
                self._entrance_anims[('move', key[0])] = {
                    'started_at': now, 'index': stagger}
                stagger += 1
        if sig[2] and sig[2] != prev_prelude:
            self._entrance_anims[('prelude',)] = {
                'started_at': now, 'index': stagger}

    def _entrance_offset(self, key):
        """(dx, dy) DRAW offset for an entering slot; (0, 0) once settled.

        Slots rise from ``ENTRANCE_SLIDE_PX`` below their resting spot with
        an ``ease_out_back`` overshoot.  Callers must never apply this to
        hit rects — hover/click always test the resting position.
        """
        rec = self._entrance_anims.get(key)
        if not rec:
            return 0, 0
        try:
            elapsed = (pygame.time.get_ticks() - int(rec['started_at'])
                       - int(rec['index']) * self.ENTRANCE_STAGGER_MS)
            t = elapsed / max(1, self.ENTRANCE_MS)
        except Exception:
            self._entrance_anims.pop(key, None)
            return 0, 0
        if t >= 1.0:
            self._entrance_anims.pop(key, None)
            return 0, 0
        if t <= 0.0:
            # Cascade slot not reached yet — parked below its resting spot.
            return 0, self.ENTRANCE_SLIDE_PX
        return 0, int((1.0 - ease_out_back(t)) * self.ENTRANCE_SLIDE_PX)

    def _draw_icon_with_entrance(self, icon, ix, iy, fig_id):
        """Draw a figure icon honouring its entrance offset.

        ``FieldFigureIcon.draw`` moves the icon's logical rects via
        ``set_position`` and hover / detail-open key off those rects, so
        after an offset draw the resting position is restored immediately
        (review finding: a naive draw offset would move hover targets).
        """
        dx, dy = self._entrance_offset(('fig', str(fig_id)))
        if not dx and not dy:
            icon.draw(ix, iy)
            return
        try:
            icon.draw(ix + dx, iy + dy)
        finally:
            try:
                icon.set_position(ix, iy)
            except Exception:
                pass

    def _draw_field_compartments(self):
        """Draw the three field compartments with FieldFigureIcon rendering."""
        field_colors = {
            'castle': settings.FIELD_FILL_COLOR,
            'village': settings.FIELD_FILL_COLOR,
            'military': settings.FIELD_FILL_COLOR,
        }

        all_regular = []
        all_hovered = None

        # Collect icon positions so X buttons can be placed on figure icons
        icon_positions = {}  # fig.id → (icon_x, icon_y)

        for field_name, rect in self._field_rects.items():
            # Background
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            clr = field_colors.get(field_name, (106, 58, 24))
            surf.fill((*clr, settings.FIELD_TRANSPARENCY))
            self.window.blit(surf, rect.topleft)

            # Slot icon (faint)
            slot_path = settings.SLOT_ICON_IMG_PATH_DICT.get(field_name)
            if slot_path:
                try:
                    slot_icon = pygame.image.load(slot_path).convert_alpha()
                    slot_icon.set_alpha(settings.SLOT_ICON_TRANSPARENCY)
                    slot_s = min(rect.w, rect.h) - 10
                    slot_icon = pygame.transform.smoothscale(slot_icon, (slot_s, slot_s))
                    sr = slot_icon.get_rect(center=rect.center)
                    self.window.blit(slot_icon, sr.topleft)
                except Exception:
                    pass

            # Border
            pygame.draw.rect(self.window, settings.FIELD_BORDER_COLOR, rect,
                             settings.FIELD_BORDER_WIDTH, border_radius=2)

            # Title
            lbl = self._label_font.render(field_name.upper(), True, (180, 160, 120))
            self.window.blit(lbl, (rect.x + 6, rect.y + 4))

            # Position figure icons within compartment
            field_figs = [f for f in self._figure_objects if f.family.field == field_name]
            if not field_figs:
                continue

            frame_h = settings.FRAME_FIGURE_SCALE * settings.FIGURE_ICON_HEIGHT
            top_margin = settings.FIGURE_ICON_HEIGHT * 0.42
            caption_font_size = settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE
            caption_h = int(caption_font_size * 2.6)
            bottom_margin = 0.34 * settings.FIGURE_ICON_HEIGHT + caption_h

            title_space = 24
            if settings.TOUCH_TARGET_MIN > 0:
                title_space = max(title_space, int(0.068 * _SH))
            first_center = rect.top + title_space + top_margin
            last_center = rect.top + rect.height - bottom_margin

            if len(field_figs) == 1:
                icon_y_start = (first_center + last_center) / 2
                icon_spacing = 0
            else:
                default_spacing = top_margin + bottom_margin + settings.FIELD_ICON_PADDING_Y
                max_spacing = (last_center - first_center) / (len(field_figs) - 1)
                if max_spacing >= default_spacing:
                    icon_spacing = default_spacing
                    group_h = (len(field_figs) - 1) * icon_spacing
                    offset = ((last_center - first_center) - group_h) / 2
                    icon_y_start = first_center + offset
                else:
                    icon_spacing = max_spacing
                    icon_y_start = first_center

            icon_x = rect.left + 0.5 * rect.w
            for i, fig in enumerate(field_figs):
                icon = self._figure_icons.get(fig.id)
                if not icon:
                    continue
                if settings.TOUCH_TARGET_MIN > 0:
                    icon.max_info_width = max(48, rect.w - 6)
                else:
                    icon.max_info_width = None
                icon_y = icon_y_start + i * icon_spacing
                icon_positions[fig.id] = (icon_x, icon_y)
                if icon.hovered:
                    all_hovered = (icon, icon_x, icon_y, fig.id)
                else:
                    all_regular.append((icon, icon_x, icon_y, fig.id))

        # Draw in z-order layers (entrance-aware: offsets apply to the draw
        # only; logical rects are restored to the resting position).
        for icon, ix, iy, fig_id in reversed(all_regular):
            self._draw_icon_with_entrance(icon, ix, iy, fig_id)
        if all_hovered:
            icon, ix, iy, fig_id = all_hovered
            self._draw_icon_with_entrance(icon, ix, iy, fig_id)

        # Draw X buttons on each figure icon (top-right of frame)
        _xbs = self._x_btn_sz
        frame_w = int(settings.FRAME_FIGURE_SCALE * settings.FIGURE_ICON_WIDTH)
        frame_h_btn = int(settings.FRAME_FIGURE_SCALE * settings.FIGURE_ICON_HEIGHT)
        mouse_pos = pygame.mouse.get_pos()
        for fig in self._figure_objects:
            pos = icon_positions.get(fig.id)
            if not pos:
                continue
            ix, iy = pos
            fr_left = ix - frame_w // 2
            fr_top = iy - frame_h_btn // 2
            frame_rect = pygame.Rect(int(fr_left), int(fr_top), frame_w, frame_h_btn)

            cfg_fig = self._get_config_fig(fig.id)
            if cfg_fig:
                xbtn = pygame.Rect(int(fr_left + frame_w - _xbs - 2), int(fr_top + 2), _xbs, _xbs)
                x_hovered = xbtn.collidepoint(mouse_pos)
                if settings.TOUCH_TARGET_MIN > 0 or frame_rect.collidepoint(mouse_pos) or x_hovered:
                    draw_remove_x(self.window, xbtn, x_hovered)
                    cfg_fig['_remove_rect'] = xbtn
                else:
                    cfg_fig['_remove_rect'] = None

        self._draw_castle_cap_indicator()

    def _draw_castle_cap_indicator(self):
        rect = self._field_rects.get('castle')
        if not rect:
            return None
        reached, count, cap = castle_cap_reached(
            self._land or {},
            (self._config or {}).get('figures', []),
        )
        if not reached:
            return None
        return draw_castle_cap_indicator(
            self.window, rect, count, cap, font=self._res_font)

    def _draw_battle_move_slots(self):
        """Draw 3 battle move slots as diamond icons."""
        moves = self._config.get('battle_moves', [])
        move_by_round = {m['round_index']: m for m in moves}
        self._hovered_slot = -1
        self._move_remove_rects = {}
        self._empty_move_slot_rects = {}

        sw = self._move_slot_size
        slot_spacing = int(sw * 2.0)
        mouse_pos = pygame.mouse.get_pos()
        mouse_pressed = pygame.mouse.get_pressed()[0]

        for i in range(3):
            cx = self._move_slots_rect.x + sw + i * slot_spacing
            cy = self._move_slots_rect.y + self._move_slots_rect.h // 2

            if i in move_by_round:
                # Hit test (diamond shape)
                hw = sw * 0.7
                hh = sw * 0.7
                is_hovered = (abs(mouse_pos[0] - cx) / hw + abs(mouse_pos[1] - cy) / hh <= 1.0)
                if is_hovered:
                    self._hovered_slot = i

                m = move_by_round[i]
                hovered = is_hovered and not mouse_pressed

                # Entrance offset applies to the DRAW only — the diamond
                # hit-test and X-button rects stay on the resting position.
                dxe, dye = self._entrance_offset(('move', i))
                draw_battle_move_icon(
                    self.window, cx + dxe, cy + dye,
                    m['family_name'], m['suit'],
                    self._battle_move_display_power(m),
                    self._slot_glow_cache, self._slot_icon_cache,
                    self._slot_frame_cache, self._suit_icon_cache,
                    self._slot_font, sw,
                    hovered=hovered,
                )

                if not dxe and not dye:
                    # X button only once the slot has settled, so the remove
                    # chrome never floats detached from a sliding icon.
                    xsz = self._x_btn_sz
                    xrect = pygame.Rect(cx + int(sw * 0.35), cy - int(sw * 0.65), xsz, xsz)
                    x_hovered = xrect.collidepoint(mouse_pos)
                    if settings.TOUCH_TARGET_MIN > 0 or is_hovered or x_hovered:
                        draw_remove_x(self.window, xrect, x_hovered)
                        self._move_remove_rects[i] = xrect

                # Round label below
                rlbl = self._small_font.render(f'R{i + 1}', True, (160, 140, 120))
                self.window.blit(rlbl, rlbl.get_rect(centerx=cx + dxe,
                                                     top=cy + dye + int(sw * 0.55)))
            else:
                # Empty slot \u2014 clickable to open the Battle Shop
                dr = self._slot_diamond.get_rect(center=(cx, cy))
                hovered = dr.collidepoint(mouse_pos)
                if hovered:
                    glow = pygame.Surface((dr.w + 6, dr.h + 6), pygame.SRCALPHA)
                    glow.fill(SLOT_HOVER_GLOW)
                    self.window.blit(glow, (dr.x - 3, dr.y - 3))
                self.window.blit(self._slot_diamond, dr.topleft)
                rlbl = self._small_font.render(
                    f'R{i + 1}', True, (150, 135, 110) if hovered else (100, 100, 100))
                self.window.blit(rlbl, rlbl.get_rect(centerx=cx, top=cy + int(sw * 0.55)))
                self._empty_move_slot_rects[i] = dr

    def _figure_by_id(self, figure_id):
        return next((
            fig for fig in self._figure_objects
            if str(getattr(fig, 'id', None)) == str(figure_id)
        ), None)

    def _figure_has_deficit(self, figure):
        icon = self._figure_icons.get(getattr(figure, 'id', None))
        if icon is not None:
            return bool(getattr(icon, 'has_deficit', False))
        return False

    def _call_figure_power_bonus(self, figure):
        icon = self._figure_icons.get(getattr(figure, 'id', None))
        return int(getattr(icon, 'buffs_allies_bonus', 0) or 0) if icon else 0

    def _call_figure_power_bonuses(self):
        return {
            getattr(fig, 'id', None): self._call_figure_power_bonus(fig)
            for fig in self._figure_objects
        }

    def _call_figure_matches_move(self, move, figure):
        field = getattr(getattr(figure, 'family', None), 'field', None)
        if field != _CALL_FIELD_MAP.get(move.get('family_name')):
            return False
        if getattr(figure, 'cannot_be_targeted', False):
            return False
        if self._figure_has_deficit(figure):
            return False
        suit = getattr(figure, 'suit', None)
        move_is_red = move.get('suit') in _RED_SUITS
        return suit in (_RED_SUITS if move_is_red else _BLACK_SUITS)

    def _eligible_call_figures(self, move, *, include_bound=True):
        if move.get('family_name') not in _CALL_FIELD_MAP:
            return []
        eligible = [
            fig for fig in self._figure_objects
            if self._call_figure_matches_move(move, fig)
        ]
        if include_bound and move.get('call_figure_id') is not None:
            bound = self._figure_by_id(move.get('call_figure_id'))
            if bound is not None and bound not in eligible:
                eligible.insert(0, bound)
        return eligible

    def _call_figure_effective_power(self, move, figure):
        try:
            base = int(figure.get_value() or 0)
        except Exception:
            base = 0
        total = base + self._call_figure_power_bonus(figure)
        if ((getattr(figure, 'suit', '') or '').lower()
                == (move.get('suit', '') or '').lower()):
            total += int(move.get('value') or 0)
        return total

    def _battle_move_display_power(self, move):
        if move.get('family_name') == 'Block':
            return 0
        if move.get('family_name') not in _CALL_FIELD_MAP:
            return move.get('value', 0)
        bound = self._figure_by_id(move.get('call_figure_id'))
        if bound is not None:
            return self._call_figure_effective_power(move, bound)
        eligible = self._eligible_call_figures(move, include_bound=False)
        if not eligible:
            return move.get('value', 0)
        return max(self._call_figure_effective_power(move, fig) for fig in eligible)

    def _best_call_figure_index(self, move, eligible):
        if not eligible:
            return 0
        call_figure_id = move.get('call_figure_id')
        if call_figure_id is not None:
            for idx, fig in enumerate(eligible):
                if str(getattr(fig, 'id', None)) == str(call_figure_id):
                    return idx
        return max(
            range(len(eligible)),
            key=lambda idx: self._call_figure_effective_power(move, eligible[idx]),
        )

    def _draw_prelude_spell(self):
        """Draw the prelude spell section with a single spell icon slot."""
        spell_name = self._config.get('prelude_spell_name')
        fsz = self._mod_frame_size
        mx_mouse, my_mouse = pygame.mouse.get_pos()

        rect = self._prelude_spell_rect
        if not rect:
            return

        cx = rect.x + fsz // 2
        cy = rect.y + fsz // 2
        caption_x = rect.right + int(0.012 * _SW)
        caption_right = (self._prelude_panel_rect.right - int(0.010 * _SW)
                         if self._prelude_panel_rect else rect.right)
        caption_w = max(0, caption_right - caption_x)

        if spell_name:
            icons = self._spell_icons.get(spell_name)
            if icons:
                # Entrance offset applies to the icon draw only; the caption,
                # badge and X-button hit rect stay on the resting position.
                dxe, dye = self._entrance_offset(('prelude',))
                icx, icy = cx + dxe, cy + dye
                if icons.get('glow'):
                    glow_surf = icons['glow']
                    gr = glow_surf.get_rect(center=(icx, icy))
                    self.window.blit(glow_surf, gr.topleft)
                if icons.get('icon'):
                    ir = icons['icon'].get_rect(center=(icx, icy))
                    self.window.blit(icons['icon'], ir.topleft)
                if icons.get('frame'):
                    fr = icons['frame'].get_rect(center=(icx, icy))
                    self.window.blit(icons['frame'], fr.topleft)
                lines = [(spell_name, self._res_font, (200, 180, 80))]
                text_h = sum(font.get_height() for _, font, _ in lines)
                self._draw_caption_lines(lines, caption_x, cy - text_h // 2, caption_w)
                if self._success_badge:
                    bx = rect.x
                    by = rect.bottom - self._success_badge.get_height()
                    self.window.blit(self._success_badge, (bx, by))
                _xbs = self._x_btn_sz
                xrect = pygame.Rect(rect.right - _xbs - 2, rect.y + 2, _xbs, _xbs)
                x_hovered = xrect.collidepoint(mx_mouse, my_mouse)
                if (not dxe and not dye) and (
                        settings.TOUCH_TARGET_MIN > 0
                        or rect.collidepoint(mx_mouse, my_mouse) or x_hovered):
                    self._prelude_x_rect = xrect
                    draw_remove_x(self.window, xrect, x_hovered)
                else:
                    self._prelude_x_rect = None
        else:
            self._prelude_x_rect = None
            draw_empty_slot(self.window, rect)
            lines = [
                ('No prelude spell', self._res_font, (140, 130, 110)),
                ('Optional', self._res_font, (110, 105, 95)),
            ]
            text_h = sum(font.get_height() for _, font, _ in lines) + 2
            self._draw_caption_lines(lines, caption_x, cy - text_h // 2, caption_w)

    def _draw_resources(self):
        """Draw a combined resource panel below the field compartments."""
        if not self._res_rect:
            return
        from game.components.resource_panel import draw_resource_panel
        draw_resource_panel(
            self.window, self._res_rect, self._calc_resources(),
            self._resource_icons, self._res_font)

    def _get_config_fig(self, figure_id):
        """Find config dict for a figure by id."""
        for fig in self._config.get('figures', []):
            if fig['id'] == figure_id:
                return fig
        return None

    def _draw_button(self, rect, text, color):
        if not rect:
            return
        mx, my = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mx, my)
        c = tuple(min(v + 30, 255) for v in color) if hovered else color
        pygame.draw.rect(self.window, c, rect, border_radius=4)
        pygame.draw.rect(self.window, (200, 180, 140), rect, 1, border_radius=4)
        text = self._fit_text(text, self._btn_font, rect.w - 10)
        txt = self._btn_font.render(text, True, (255, 255, 255))
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_section_title(self, title, title_pos, icon_rect, description=None):
        """Draw a section title with an edit icon button next to it."""
        if not icon_rect:
            return
        txt = self._label_font.render(title, True, (200, 185, 150))
        self.window.blit(txt, title_pos)
        if description and settings.TOUCH_TARGET_MIN <= 0:
            desc_surf = self._res_font.render(description, True, (160, 145, 120))
            self.window.blit(desc_surf, (title_pos[0], title_pos[1] + txt.get_height() + 2))
        # Draw icon with hover highlight
        isz = self._edit_icon_size
        mx, my = pygame.mouse.get_pos()
        hovered = icon_rect.collidepoint(mx, my)
        if hovered:
            glow = pygame.Surface((isz + 4, isz + 4), pygame.SRCALPHA)
            glow.fill((255, 255, 200, 40))
            self.window.blit(glow, (icon_rect.x - 2, icon_rect.y - 2))
        self.window.blit(self._edit_icon, icon_rect.topleft)

    def _draw_close_x_button(self):
        """Draw a small X close button in the top-right corner of the box."""
        if not self._btn_close_rect:
            if not self._layout_built:
                self._build_layout()
        draw_close_x_button(self.window, self._btn_close_rect)

    # ── Subscreen helpers ──────────────────────────────────────────

    def _build_card_source(self):
        """Create a CollectionCardSource from the player's collection."""
        try:
            data = collection_service.fetch_collection_cards()
        except Exception as e:
            logger.error(f'Failed to fetch collection for card source: {e}')
            return None

        cards = []
        for c in data.get('cards', []):
            qty = c.get('free', c.get('total', 0))
            for i in range(qty):
                cards.append(Card(
                    rank=c['rank'], suit=c['suit'],
                    value=settings.RANK_TO_VALUE.get(c['rank'], 0),
                    id=c.get('id', hash((c['suit'], c['rank'], i))),
                    type='main' if c['rank'] in settings.RANKS_MAIN_CARDS else 'side_card',
                ))

        locked_ids = set()
        for fig in self._config.get('figures', []):
            for cid in fig.get('card_ids', []):
                locked_ids.add(cid)
        for mv in self._config.get('battle_moves', []):
            if mv.get('card_id'):
                locked_ids.add(mv['card_id'])

        return CollectionCardSource(cards, self._config.get('figures', []), locked_ids)

    def _config_subscreen_origin(self):
        """Return a centered modal origin for config-edit subscreens."""
        x = (settings.SCREEN_WIDTH - settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH) // 2
        y = (settings.SCREEN_HEIGHT - settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT) // 2
        return max(0, x), max(0, y)

    def _config_subscreen_rect(self):
        x, y = self._config_subscreen_origin()
        return pygame.Rect(x, y,
                           settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH,
                           settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT)

    def _open_build_figure(self):
        """Open BuildFigureScreen as a subscreen."""
        card_source = self._build_card_source()
        if not card_source:
            self._error = 'Failed to load collection'
            return
        self._game_proxy = KingdomGameProxy(
            self._config, self._land_id, mode='conquer', land=self._land or {})
        self.state.game = self._game_proxy
        sx, sy = self._config_subscreen_origin()
        self._subscreen_obj = BuildFigureScreen(
            self.window, self.state,
            x=sx, y=sy,
            title='Figure Builder', card_source=card_source, mode='conquer',
        )
        self._subscreen_obj._on_done = self._close_subscreen
        self._active_subscreen = 'build_figure'

    def _open_battle_shop(self):
        """Open BattleShopScreen as a subscreen."""
        card_source = self._build_card_source()
        if not card_source:
            self._error = 'Failed to load collection'
            return
        self._game_proxy = KingdomGameProxy(
            self._config, self._land_id, mode='conquer', land=self._land or {})
        self.state.game = self._game_proxy
        sx, sy = self._config_subscreen_origin()
        self._subscreen_obj = BattleShopScreen(
            self.window, self.state,
            x=sx, y=sy,
            title='Battle Shop', card_source=card_source, mode='conquer',
        )
        self._subscreen_obj._on_done = self._close_subscreen
        self._active_subscreen = 'battle_shop'

    def _open_prelude_spell_screen(self):
        """Open PreludeSpellScreen as a subscreen."""
        card_source = self._build_card_source()
        if not card_source:
            self._error = 'Failed to load collection'
            return
        self._game_proxy = KingdomGameProxy(
            self._config, self._land_id, mode='conquer', land=self._land or {})
        self.state.game = self._game_proxy
        sx, sy = self._config_subscreen_origin()
        self._subscreen_obj = PreludeSpellScreen(
            self.window, self.state,
            x=sx, y=sy,
            title='Prelude Spell', card_source=card_source, mode='conquer',
            allowed_spells=_CONQUER_PRELUDE_SPELLS,
            server_endpoint='/kingdom/conquer/set_prelude_spell',
            land_id=self._land_id,
        )
        self._subscreen_obj._on_done = self._close_subscreen
        self._active_subscreen = 'prelude_spell'

    def _close_subscreen(self):
        """Dismiss the active subscreen and sync config."""
        if self._game_proxy:
            self._config = self._game_proxy._config
        self._active_subscreen = None
        self._subscreen_obj = None
        self._game_proxy = None
        # Refresh config from server (async — keeps the event loop responsive)
        self._start_config_load()

    # ── Readiness check ────────────────────────────────────────────

    def _is_battle_ready(self):
        """True when the user can initiate the conquer battle."""
        if not self._config:
            return False
        figures = self._config.get('figures', [])
        moves = self._config.get('battle_moves', [])

        prelude = self._config.get('prelude_spell_name')
        village_only = prelude in ('Peasant War', 'Civil War')

        has_valid_figure = any(
            not f.get('has_deficit', False)
            and not f.get('cannot_attack', False)
            and (not village_only or f.get('field') == 'village')
            for f in figures
        )
        has_moves = len(moves) == 3
        return has_valid_figure and has_moves

    def _get_battle_problems(self):
        """Return a list of human-readable problems preventing battle start."""
        problems = []
        if not self._config:
            problems.append('Configuration not loaded.')
            return problems

        figures = self._config.get('figures', [])
        moves = self._config.get('battle_moves', [])
        prelude = self._config.get('prelude_spell_name')
        village_only = prelude in ('Peasant War', 'Civil War')

        if not figures:
            problems.append('No figures on the field.')
        else:
            can_advance = [
                f for f in figures
                if not f.get('has_deficit', False) and not f.get('cannot_attack', False)
            ]
            if not can_advance:
                deficit_only = any(
                    f.get('has_deficit', False) and not f.get('cannot_attack', False)
                    for f in figures
                )
                if deficit_only:
                    problems.append('All figures that can fight have a resource deficit.')
                else:
                    problems.append('No figure on the field is able to advance into battle.')
            elif village_only:
                village_advance = [
                    f for f in can_advance if f.get('field') == 'village'
                ]
                if not village_advance:
                    problems.append(
                        f'{prelude} is selected — only village figures can advance, '
                        'but none of your village figures are able to fight.'
                    )

        if len(moves) < 3:
            missing = 3 - len(moves)
            problems.append(f'{missing} battle move{"s" if missing > 1 else ""} still missing (need 3).')

        return problems

    def _show_cooldown_dialogue(self, remaining=None):
        remaining = self._current_cooldown_remaining() if remaining is None else remaining
        remaining = max(0, int(remaining or 0))
        cd_text = self._format_duration(remaining)
        maps_available = int(getattr(self, '_maps_available', 0) or 0)
        self._cooldown_remaining = remaining
        self._cooldown_synced_at_ms = pygame.time.get_ticks()
        if maps_available > 0:
            self._pending_map_confirm = True
            open_dialogue(
                self,
                f'Conquer cooldown: {cd_text} remaining.\n'
                f'Use 1 map to start this battle now? '
                f'You have {maps_available}.',
                ['Use Map', 'Cancel'],
                'Conquer Cooldown',
            )
        else:
            open_dialogue(
                self,
                f'Conquer cooldown: {cd_text} remaining.\n'
                'You do not have a map to bypass it.',
                ['OK'],
                'Conquer Cooldown',
            )

    def _on_battle_click(self):
        """Handle click on 'To Battle!' — validate or confirm."""
        sound.play('ui_click', volume=0.8)
        if self._is_battle_ready():
            remaining = self._current_cooldown_remaining()
            if remaining > 0:
                self._show_cooldown_dialogue(remaining)
                return
            self._start_battle_with_loot_tutorial(use_map=False)
        else:
            problems = self._get_battle_problems()
            msg = '\n'.join(f'\u2022 {p}' for p in problems)
            open_dialogue(self, msg, ['OK'], 'Cannot Start Battle')

    def _first_conquer_tutorial_active(self):
        """True during the first guided conquest, before any land is won.

        The first tutorial battle is risk-free (losing costs nothing and the
        retry is free), so the loot-and-lock lesson is meaningless there. It is
        deferred to the second, self-built conquest — the first battle with a
        real defender where cards can actually be looted.
        """
        onboarding = (getattr(self.state, 'user_dict', None) or {}).get('onboarding') or {}
        if not onboarding or onboarding.get('onboarding_skipped'):
            return False
        return 'finish_first_conquer_battle' not in set(onboarding.get('completed_steps') or [])

    def _start_battle_with_loot_tutorial(self, use_map=False):
        if loot_risk_tutorial_seen(self) or self._first_conquer_tutorial_active():
            self._start_battle(use_map=use_map)
            return
        open_loot_risk_tutorial(
            self,
            {'kind': 'start_battle', 'use_map': bool(use_map)},
        )

    def _resume_loot_risk_tutorial_action(self, action):
        if isinstance(action, dict) and action.get('kind') == 'start_battle':
            self._start_battle(use_map=bool(action.get('use_map')))

    # ── Start battle ────────────────────────────────────────────────

    def _leave_screen(self):
        """Reset config on the server (unlock cards) and go back to kingdom."""
        sound.play('ui_back')
        try:
            requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/reset_config',
                json={'land_id': self._land_id},
                timeout=10,
            )
        except Exception as e:
            logger.error(f'Failed to reset conquer config: {e}')
        self.state.screen = 'kingdom'

    def _has_config_content(self):
        """True if the config has any figures, moves, or spells set."""
        if not self._config:
            return False
        return bool(
            self._config.get('figures')
            or self._config.get('battle_moves')
            or self._config.get('prelude_spell_name')
            or self._config.get('battle_modifier')
        )

    def _try_leave_screen(self):
        """Prompt if config has content; otherwise leave immediately."""
        if self._has_config_content():
            self._pending_leave_confirm = True
            open_dialogue(
                self,
                'You have unsaved changes.\n'
                'Leaving will discard all figures, battle moves,\n'
                'and spells you have configured.',
                ['Leave', 'Stay'],
                'Discard Changes?',
            )
        else:
            self._leave_screen()

    def _start_battle(self, use_map=False):
        """Start the battle without blocking the UI; transition on success."""
        if _sys.platform == 'emscripten':
            self._start_battle_web(use_map=use_map)
            return
        if self._start_battle_poller is not None and self._start_battle_poller.busy:
            return
        if not use_map:
            remaining = self._current_cooldown_remaining()
            if remaining > 0:
                self._show_cooldown_dialogue(remaining)
                return
        self._loading = True
        self._loading_started_at_ms = pygame.time.get_ticks()
        self._loading_message = 'Starting conquer battle...'
        self._error = None
        self._start_battle_poller = BackgroundPoller(self._start_battle_task)
        self._start_battle_poller.poll(args=(self._land_id, bool(use_map)))

    def _start_battle_task(self, land_id, use_map):
        """Background start_battle request. Must never raise — the poller
        swallows exceptions without publishing a result."""
        try:
            payload = {'land_id': land_id}
            if use_map:
                payload['use_map'] = True
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/start_battle',
                json=payload,
                timeout=15,
            )
            data = self._response_json(resp)
            result = {'data': data}
            if data.get('game_id'):
                try:
                    result['game_dict'] = fetch_game(data['game_id'])
                except Exception as e:
                    logger.error(f'Failed to fetch game after battle start: {e}')
                    result['game_dict'] = None
            return result
        except Exception as e:
            logger.error(f'Start battle error: {e}')
            return {'error': 'Connection error'}

    def _drain_start_battle_native(self):
        poller = self._start_battle_poller
        if poller is None or not poller.has_result():
            return
        self._start_battle_poller = None
        result = poller.result or {}
        self._loading = False
        if result.get('error'):
            self._error = result['error']
            return
        data = result.get('data') or {}
        if data.get('game_id'):
            game_id = data['game_id']
            self.state.game_id = game_id
            # Update local maps count if a map was consumed.
            if data.get('map_consumed') and self.state.user_dict is not None:
                self.state.user_dict['maps'] = int(data.get('maps', 0))
                self._maps_available = int(data.get('maps', 0))
            game_dict = result.get('game_dict')
            self.state.game = (
                Game(game_dict, self.state.user_dict) if game_dict else None)
            # Mark the deliberate start so the battle screen plays its
            # "3·2·1·GO!" moment. Lives on ``state`` (not the game) so it
            # survives the game-object lifecycle and is naturally absent on
            # a reload/resume (which should not replay the countdown).
            self.state.conquer_battle_countdown_pending = True
            self.state.screen = gameplay_screen_for(self.state.game)
            logger.info(f'Battle started: game_id={game_id}')
            return
        self._handle_start_battle_failure(data)

    def _handle_start_battle_failure(self, data):
        """Shared tail for start_battle responses without a game_id."""
        # Cooldown branch: offer to consume a map.
        if data.get('code') == 'cooldown':
            self._set_cooldown_state(data)
            self._show_cooldown_dialogue(data.get('cooldown_remaining') or 0)
            return
        if data.get('code') == 'no_cooldown':
            self._set_cooldown_state(data)
            self._start_battle(use_map=False)
            return
        if data.get('code') == 'no_maps':
            self._set_cooldown_state(data)
        self._error = (
            data.get('message')
            or data.get('error')
            or 'Failed to start battle'
        )
        logger.warning(f'Start battle failed: {self._error}')

    def _start_battle_web(self, use_map=False):
        """Web-only non-blocking start_battle flow."""
        if self._start_battle_rid or self._start_battle_fetch_game_rid:
            return
        if not use_map:
            remaining = self._current_cooldown_remaining()
            if remaining > 0:
                self._show_cooldown_dialogue(remaining)
                return
        try:
            payload = {'land_id': self._land_id}
            if use_map:
                payload['use_map'] = True
            self._loading = True
            self._loading_started_at_ms = pygame.time.get_ticks()
            self._loading_message = 'Starting conquer battle...'
            self._error = None
            self._start_battle_rid = requests.start_async_post_json(
                f'{settings.SERVER_URL}/kingdom/conquer/start_battle',
                payload,
            )
        except Exception as e:
            self._loading = False
            self._error = 'Connection error'
            logger.error(f'Start battle async error: {e}')

    def _drain_start_battle_web(self):
        if _sys.platform != 'emscripten':
            return
        if self._start_battle_rid:
            try:
                resp = requests.check_async(self._start_battle_rid)
            except Exception as e:
                self._start_battle_rid = None
                self._loading = False
                self._error = 'Connection error'
                logger.error(f'Start battle async check error: {e}')
                return
            if resp is None:
                return
            self._start_battle_rid = None
            if resp.status_code != 200:
                self._loading = False
                err = self._response_json(resp)
                self._error = err.get('message') or err.get('error') or 'Failed to start battle'
                logger.warning(f'Start battle failed: {self._error}')
                return
            data = self._response_json(resp)
            self._handle_start_battle_response(data)
            return

        if self._start_battle_fetch_game_rid:
            try:
                resp = requests.check_async(self._start_battle_fetch_game_rid)
            except Exception as e:
                self._start_battle_fetch_game_rid = None
                self._start_battle_fetch_game_id = None
                self._loading = False
                self._error = 'Connection error'
                logger.error(f'Fetch game async check error: {e}')
                return
            if resp is None:
                return
            game_id = self._start_battle_fetch_game_id
            self._start_battle_fetch_game_rid = None
            self._start_battle_fetch_game_id = None
            self._loading = False
            if resp.status_code != 200:
                err = self._response_json(resp)
                self._error = err.get('message') or err.get('error') or 'Failed to load battle'
                logger.warning(f'Fetch game after battle start failed: {self._error}')
                return
            game_dict = (self._response_json(resp) or {}).get('game')
            if not game_dict:
                self._error = 'Failed to load battle'
                return
            self.state.game = Game(game_dict, self.state.user_dict, lightweight=True)
            # See _drain_start_battle_native: flag the battle-start moment.
            self.state.conquer_battle_countdown_pending = True
            self.state.screen = gameplay_screen_for(self.state.game)
            logger.info(f'Battle started: game_id={game_id}')

    def _handle_start_battle_response(self, data):
        if data.get('game_id'):
            game_id = data['game_id']
            self.state.game_id = game_id
            if data.get('map_consumed') and self.state.user_dict is not None:
                self.state.user_dict['maps'] = int(data.get('maps', 0))
                self._maps_available = int(data.get('maps', 0))
            if _sys.platform == 'emscripten':
                try:
                    self._loading_message = 'Loading conquer battle...'
                    self._start_battle_fetch_game_id = game_id
                    self._start_battle_fetch_game_rid = requests.start_async_get(
                        f'{settings.SERVER_URL}/games/get_game',
                        {'game_id': game_id},
                    )
                except Exception as e:
                    self._loading = False
                    self._error = 'Connection error'
                    logger.error(f'Fetch game async start error: {e}')
            return
        self._loading = False
        self._handle_start_battle_failure(data)

    # ── Update / events ─────────────────────────────────────────────

    def update(self, events):
        super().update()
        self._update_icon_buttons()

        self._drain_start_battle_web()
        self._drain_start_battle_native()

        # If subscreen is active, delegate
        if self._active_subscreen and self._subscreen_obj:
            self._subscreen_obj.update(self._game_proxy)
            return

        # Check if the land_id changed (new conquer target)
        target_land = getattr(self.state, 'conquer_land_id', None)
        if target_land and target_land != self._land_id:
            self._land_id = target_land
            self._config = None
            self._land = None
            self._loading = False
            self._error = None
            self._config_poller = None
            self._config_poller_land_id = None

        self._drain_config_poller()

        # Auto-load config if needed
        if self._land_id and not self._config and not self._loading and not self._error:
            self._start_config_load()

        # Update figure icon hover states
        for icon in self._figure_icons.values():
            icon.update()

    def handle_events(self, events):
        super().handle_events(events)

        # Handle cooldown / info dialogue response
        response = self.state.action.get('status')
        if response and self._pending_map_confirm:
            self._pending_map_confirm = False
            self.reset_action()
            if response == 'use map':
                self._start_battle_with_loot_tutorial(use_map=True)
            return
        if response and self._pending_leave_confirm:
            self._pending_leave_confirm = False
            self.reset_action()
            if response == 'leave':
                self._leave_screen()
            return
        if response in ('ok', 'cancel'):
            self._pending_leave_confirm = False
            self.reset_action()
            return

        if self.dialogue_box:
            return

        loot_tutorial_action = handle_loot_risk_tutorial_events(self, events)
        if loot_tutorial_action is not None:
            if isinstance(loot_tutorial_action, dict):
                self._resume_loot_risk_tutorial_action(loot_tutorial_action)
            return

        coach_step = self._current_conquer_coach_step()
        if self._handle_menu_coach_events(events, coach_step):
            return

        # If subscreen is active, delegate events
        if self._active_subscreen and self._subscreen_obj:
            self._subscreen_obj.handle_events(events)
            _ss_rect = self._config_subscreen_rect()
            for event in events:
                # ESC closes subscreen
                if event.type == KEYDOWN and event.key == K_ESCAPE:
                    self._close_subscreen()
                    return
                # Click outside subscreen closes it
                if event.type == MOUSEBUTTONUP and event.button == 1:
                    if not _ss_rect.collidepoint(event.pos):
                        self._close_subscreen()
                        return
            return

        # Battle move detail box intercepts events when open
        if self._move_detail_box:
            response = self._move_detail_box.handle_events(events)
            if response:
                if response == 'return':
                    move_id = self._move_detail_box.bm.get('id')
                    self._move_detail_box = None
                    if move_id:
                        self._server_return_move(move_id)
                else:
                    self._move_detail_box = None
            return

        # Figure detail box intercepts events when open
        if self._figure_detail_box:
            for event in events:
                if event.type == MOUSEBUTTONUP and event.button == 1:
                    self._figure_detail_box = None
                    return
                if event.type == KEYDOWN and event.key == K_ESCAPE:
                    self._figure_detail_box = None
                    return
            return

        for event in events:
            if self._handle_icon_events(event):
                continue
            if self._handle_info_button_event(event):
                continue

            if event.type == KEYDOWN and event.key == K_ESCAPE and self._active_info_key:
                self._active_info_key = None
                self._active_info_popup_rect = None
                return

            # Click outside content box → back to kingdom
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and not pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H).collidepoint(event.pos)):
                self._try_leave_screen()
                return

            if event.type == MOUSEBUTTONUP and event.button == 1:
                pos = event.pos

                # X close button
                if _mobile_collide(self._btn_close_rect, pos,
                                   settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                    self._try_leave_screen()
                    return

                # Retry button (error state)
                if self._error and self._btn_retry and _mobile_collide(self._btn_retry, pos):
                    sound.play('ui_click')
                    self._error = None
                    self._btn_retry = None
                    if not self._config:
                        self._start_config_load()
                    return

                if not self._config:
                    continue

                # Remove buttons must win over icon/detail clicks.
                # Removals are free draft edits (cards unlock server-side),
                # so they fire immediately — same as figure/move removal.
                if _mobile_collide(self._prelude_x_rect, pos,
                                   settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                    if self._config.get('prelude_spell_name'):
                        self._server_clear_prelude_spell()
                    continue

                figure_removed = False
                for fig in self._config.get('figures', []):
                    xrect = fig.get('_remove_rect')
                    if _mobile_collide(xrect, pos,
                                       settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                        self._server_remove_figure(fig['id'])
                        figure_removed = True
                        break
                if figure_removed:
                    continue

                move_removed = False
                for ri, xrect in self._move_remove_rects.items():
                    if _mobile_collide(xrect, pos,
                                       settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                        moves = self._config.get('battle_moves', [])
                        for m in moves:
                            if m['round_index'] == ri:
                                self._server_return_move(m['id'])
                                break
                        move_removed = True
                        break
                if move_removed:
                    continue

                # Figure icon clicks → open detail box
                for icon in self._figure_icons.values():
                    if icon.hovered:
                        resources_data = self._calc_resources()
                        self._figure_detail_box = FigureDetailBox(
                            window=self.window,
                            figure=icon.figure,
                            game=None,
                            all_figures=self._figure_objects,
                            resources_data=resources_data,
                        )
                        break

                # Build Figure button
                if _mobile_collide(self._btn_build, pos,
                                   settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                    sound.play('ui_click')
                    self._open_build_figure()
                    continue

                # Buy Move button
                if _mobile_collide(self._btn_buy_move, pos,
                                   settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                    sound.play('ui_click')
                    self._open_battle_shop()
                    continue

                # Empty battle-move slot click → open the Battle Shop
                if any(_mobile_collide(r, pos)
                       for r in self._empty_move_slot_rects.values()):
                    sound.play('ui_click')
                    self._open_battle_shop()
                    continue

                # Prelude spell: edit button or empty slot click
                if (_mobile_collide(self._btn_prelude_edit, pos,
                                    settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN)
                        or _mobile_collide(self._prelude_spell_rect, pos)):
                    sound.play('ui_click')
                    self._open_prelude_spell_screen()
                    continue

                # To Battle
                if _mobile_collide(self._btn_battle, pos):
                    self._on_battle_click()
                    continue

                # Click on filled battle move slot → open detail box
                if self._hovered_slot >= 0:
                    moves = self._config.get('battle_moves', [])
                    for m in moves:
                        if m['round_index'] == self._hovered_slot:
                            eligible = self._eligible_call_figures(m)
                            self._move_detail_box = BattleMoveDetailBox(
                                self.window, m,
                                self._move_manager.families_by_name,
                                None,
                                eligible_figures=eligible,
                                best_figure_index=self._best_call_figure_index(
                                    m, eligible),
                                figure_power_bonuses=self._call_figure_power_bonuses(),
                            )
                            break
                    continue

            # ESC → back to kingdom
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                self._try_leave_screen()
                return
