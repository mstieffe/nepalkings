# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Conquer screen — configure figures + battle moves for attacking a land."""

import pygame
from copy import copy
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from game.screens.build_figure_screen import BuildFigureScreen
from game.screens.battle_shop_screen import BattleShopScreen
from game.screens.prelude_spell_screen import PreludeSpellScreen
from game.core.card_source import CollectionCardSource
from game.core.kingdom_game_proxy import KingdomGameProxy
from game.components.cards.card import Card
from game.components.figures.figure import Figure
from game.components.figures.figure_icon import FieldFigureIcon
from game.components.figure_detail_box import FigureDetailBox
from game.components.dialogue_box import DialogueBox
from game.components.figures.figure_manager import FigureManager
from game.components.battle_moves.battle_move_manager import BattleMoveManager
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.components.battle_moves.battle_move_detail_box import BattleMoveDetailBox
from game.components.spells.spell_manager import SpellManager
from game.core.game import Game
from utils.game_service import fetch_game
from config import settings
from utils import http_compat as requests
from utils import collection_service
import logging

logger = logging.getLogger('nk.screens.conquer')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# ── Overall box ─────────────────────────────────────────────────────
_BOX_PAD    = int(0.020 * _SH)
_BOX_X      = int(0.04 * _SW)
_BOX_Y      = int(0.10 * _SH)
_BOX_W      = int(0.87 * _SW)
_BOX_BOTTOM = int(0.92 * _SH)
_BOX_H      = _BOX_BOTTOM - _BOX_Y


def _draw_panel(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


def _strip_duel_only_skill_description(text):
    """Remove duel-only skill wording from kingdom config descriptions."""
    return (text or '').replace(' Triggers checkmate when defeated.', '').replace(
        'Triggers checkmate when defeated.', '').strip()


def _display_family_without_duel_only_skills(family):
    description = getattr(family, 'description', '')
    clean_description = _strip_duel_only_skill_description(description)
    if clean_description == description:
        return family
    display_family = copy(family)
    display_family.description = clean_description
    return display_family


# Card requirements per modifier/spell: rank, count, color_constraint
_SPELL_CARD_COST = {
    'Draw 2 MainCards': ('8', 1, None),
    'Fill up to 10':    ('10', 1, None),
    'Dump Cards':       ('7', 4, None),
    'Forced Deal':      ('4', 2, None),
    'Poison':           ('3', 2, 'black'),
    'Health Boost':     ('3', 2, 'red'),
    'All Seeing Eye':   ('9', 2, None),
    'Explosion':        ('6', 4, None),
    'Peasant War':      ('J', 2, None),
    'Civil War':        ('5', 2, None),
    'Blitzkrieg':       ('Q', 2, None),
}

_CONQUER_PRELUDE_SPELLS = [
    'Draw 2 MainCards', 'Fill up to 10', 'Dump Cards', 'Forced Deal',
    'Poison', 'Health Boost', 'All Seeing Eye', 'Explosion',
    'Peasant War', 'Civil War', 'Blitzkrieg',
]

_RIGHT_SECTION_INFO = {
    'battle_plan': {
        'title': 'Battle Plan',
        'message': (
            'Choose the three battle move cards your attacking force will use, one per battle round. '
            'You need all three rounds filled before starting a conquer battle, and these cards are committed to the attack.'
        ),
    },
    'prelude_spell': {
        'title': 'Prelude Spell',
        'message': (
            'Prelude spells are optional effects that trigger before the conquer battle starts. '
            'They can draw cards, weaken the defender, or change battle restrictions, and their card cost is consumed when battle begins.'
        ),
    },
}

_RED_SUITS = {'Hearts', 'Diamonds'}
_BLACK_SUITS = {'Clubs', 'Spades'}


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
        self._error = None

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
        self._res_rect = None        # Resource panel rect
        self._res_castle_rect = None  # Resource sub-panel below castle
        self._res_village_rect = None # Resource sub-panel below village
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
        self._pending_battle_confirm = False
        self._pending_leave_confirm = False
        self._pending_prelude_spell = None   # spell name pending confirmation
        self._pending_prelude_clear = False  # pending clear confirmation
        self._prelude_spell_choices = []     # affordable spells list
        self._prelude_spell_choice_idx = 0   # current index in choices
        self._move_remove_rects = {}   # round_index → Rect for X buttons

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
        _icon_sz = int(0.025 * _SH)
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
        self._error = None
        self._active_subscreen = None
        self._subscreen_obj = None
        self._game_proxy = None
        self._figure_objects = []
        self._figure_icons = {}
        self._figure_detail_box = None
        self._layout_built = False
        self._hovered_slot = -1
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

        # To Battle — lower right of box
        battle_w = int(0.20 * _SW)
        battle_h = int(0.055 * _SH)
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
        self._res_castle_rect = None
        self._res_village_rect = None

        # ── Divider positions ──────────────────────────────────────
        # Vertical: between left fields/resources and right battle column
        self._divider_v_x = right_x - pad // 2
        self._divider_v_top = top
        self._divider_v_bottom = _BOX_BOTTOM - _BOX_PAD
        self._divider_h1_y = None

        # X close button (top-right of box)
        _xsz = int(0.028 * _SH)
        _xmargin = int(0.012 * _SW)
        self._btn_close_rect = pygame.Rect(
            _BOX_X + _BOX_W - _xsz - _xmargin,
            _BOX_Y + _xmargin,
            _xsz, _xsz)

        self._layout_built = True

    # ── Data loading ────────────────────────────────────────────────

    def _load_config(self):
        """Fetch (or create) the conquer config from the server."""
        self._loading = True
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
            self._loading = False
            self._rebuild_figure_objects()
            self._refresh_collection()
            logger.debug(f'Conquer config loaded for land {self._land_id}')
        except Exception as e:
            self._error = 'Connection error'
            logger.error(f'Conquer config load error: {e}')
            self._loading = False

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

    def _has_cards_for(self, req_key, reqs_dict=None):
        """Check if player has enough free cards for a requirement."""
        reqs = (reqs_dict or _SPELL_CARD_COST).get(req_key)
        if not reqs:
            return False
        rank, count, color = reqs
        cards = self._collection_cards or []
        # Group free cards of the required rank by colour
        red_free = sum(c.get('free', 0) for c in cards
                       if c.get('rank') == rank and c.get('suit') in _RED_SUITS)
        black_free = sum(c.get('free', 0) for c in cards
                         if c.get('rank') == rank and c.get('suit') in _BLACK_SUITS)
        if color == 'red':
            return red_free >= count
        elif color == 'black':
            return black_free >= count
        else:
            return red_free >= count or black_free >= count

    def _card_req_label(self, req_key, reqs_dict=None):
        """Return a human-readable label for card requirements."""
        reqs = (reqs_dict or _SPELL_CARD_COST).get(req_key)
        if not reqs:
            return ''
        rank, count, color = reqs
        color_str = f' ({color})' if color else ''
        return f'{count}\u00d7 rank {rank}{color_str}'

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

        key_cards = matched.key_cards if matched else []
        number_card = matched.number_card if matched else None
        upgrade_card = matched.upgrade_card if matched else None

        display_family = _display_family_without_duel_only_skills(family)

        return Figure(
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
        size = max(int(0.022 * _SH), 18)
        margin_x = int(0.008 * _SW)
        margin_y = int(0.010 * _SH)
        return pygame.Rect(
            panel_rect.right - margin_x - size,
            panel_rect.y + margin_y,
            size,
            size,
        )

    def _draw_info_button(self, rect, active=False):
        if not rect:
            return
        mx, my = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mx, my)
        center = rect.center
        radius = rect.w // 2
        fill = (80, 70, 45, 235) if active else ((70, 62, 42, 225) if hovered else (45, 40, 32, 210))
        border = (230, 210, 140) if active or hovered else (150, 135, 95)
        text_clr = (255, 240, 185) if active or hovered else (195, 180, 130)
        pygame.draw.circle(self.window, fill, center, radius)
        pygame.draw.circle(self.window, border, center, radius, 1)
        font = settings.get_font(max(int(rect.h * 0.72), 9), bold=True)
        txt = font.render('i', True, text_clr)
        self.window.blit(txt, txt.get_rect(center=center))

    def _wrap_info_text(self, text, font, max_width):
        lines = []
        for paragraph in str(text).split('\n'):
            words = paragraph.split()
            current = ''
            for word in words:
                candidate = f'{current} {word}'.strip()
                if current and font.size(candidate)[0] > max_width:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            if current:
                lines.append(current)
        return lines

    def _draw_info_popup(self):
        info = _RIGHT_SECTION_INFO.get(self._active_info_key)
        anchor = self._info_button_rects.get(self._active_info_key) if self._active_info_key else None
        if not info or not anchor:
            self._active_info_popup_rect = None
            return

        pad = int(0.010 * _SW)
        gap = int(0.006 * _SH)
        popup_w = min(int(0.30 * _SW), max(int(0.20 * _SW), self._battle_plan_rect.w - 2 * pad))
        text_w = popup_w - 2 * pad
        title_font = self._small_font
        body_font = self._res_font
        title = info['title']
        lines = self._wrap_info_text(info['message'], body_font, text_w)
        line_gap = 3
        popup_h = (
            pad
            + title_font.get_height()
            + int(0.006 * _SH)
            + len(lines) * body_font.get_height()
            + max(0, len(lines) - 1) * line_gap
            + pad
        )
        x = min(anchor.right - popup_w, _BOX_X + _BOX_W - _BOX_PAD - popup_w)
        x = max(_BOX_X + _BOX_PAD, x)
        y = anchor.bottom + gap
        if y + popup_h > _BOX_BOTTOM - _BOX_PAD:
            y = anchor.top - popup_h - gap
        y = max(_BOX_Y + _BOX_PAD, y)
        popup_rect = pygame.Rect(int(x), int(y), int(popup_w), int(popup_h))
        self._active_info_popup_rect = popup_rect

        surf = pygame.Surface((popup_rect.w, popup_rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (26, 22, 16, 242), surf.get_rect(), border_radius=6)
        self.window.blit(surf, popup_rect.topleft)
        pygame.draw.rect(self.window, (210, 185, 115), popup_rect, 1, border_radius=6)

        cx = popup_rect.x + pad
        cy = popup_rect.y + pad
        title_surf = title_font.render(title, True, (235, 215, 145))
        self.window.blit(title_surf, (cx, cy))
        cy += title_surf.get_height() + int(0.006 * _SH)
        for line in lines:
            line_surf = body_font.render(line, True, (195, 180, 140))
            self.window.blit(line_surf, (cx, cy))
            cy += body_font.get_height() + line_gap

    def _draw_info_buttons(self):
        for key, rect in self._info_button_rects.items():
            self._draw_info_button(rect, active=(key == self._active_info_key))

    def _handle_info_button_event(self, event):
        if event.type != MOUSEBUTTONUP or event.button != 1:
            return False
        pos = event.pos
        for key, rect in self._info_button_rects.items():
            if rect and rect.collidepoint(pos):
                self._active_info_key = None if self._active_info_key == key else key
                return True
        if self._active_info_key:
            popup = self._active_info_popup_rect
            if popup and popup.collidepoint(pos):
                return True
            self._active_info_key = None
            self._active_info_popup_rect = None
            return True
        return False

    def _draw_section_panel(self, rect, title, *, description=None,
                            icon_rect=None, title_pos=None):
        """Draw a quiet section card with one title row and optional edit icon."""
        if not rect:
            return
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (28, 24, 20, 120), surf.get_rect(), border_radius=5)
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, (110, 95, 72), rect, 1, border_radius=5)

        x = title_pos[0] if title_pos else rect.x + int(0.010 * _SW)
        y = title_pos[1] if title_pos else rect.y + int(0.010 * _SH)
        font = self._label_font if title == 'Battle Plan' else self._small_font
        title_surf = font.render(title, True, (200, 185, 150))
        self.window.blit(title_surf, (x, y))
        if description:
            desc_surf = self._res_font.render(description, True, (160, 145, 120))
            self.window.blit(desc_surf, (x, y + title_surf.get_height() + 2))

        if icon_rect:
            isz = self._edit_icon_size
            mx, my = pygame.mouse.get_pos()
            hovered = icon_rect.collidepoint(mx, my)
            if hovered:
                glow = pygame.Surface((isz + 4, isz + 4), pygame.SRCALPHA)
                glow.fill((255, 255, 200, 40))
                self.window.blit(glow, (icon_rect.x - 2, icon_rect.y - 2))
            self.window.blit(self._edit_icon, icon_rect.topleft)

    def _fit_text(self, text, font, max_width):
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
        self._draw_section_panel(
            self._battle_plan_rect,
            'Battle Plan',
            description='Assign cards for battle rounds',
            icon_rect=self._btn_buy_move,
            title_pos=self._moves_title_pos,
        )
        self._draw_section_panel(
            self._prelude_panel_rect,
            'Prelude Spell',
            description='Optional spell before battle',
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
            txt = self._label_font.render('Loading conquer config…', True, (200, 185, 150))
            self.window.blit(txt, txt.get_rect(center=(_SW // 2, _SH // 2)))
            self._draw_menu_overlay()
            return

        if self._error:
            txt = self._label_font.render(self._error, True, (200, 80, 80))
            self.window.blit(txt, txt.get_rect(center=(_SW // 2, _SH // 2)))
            self._draw_close_x_button()
            self._draw_menu_overlay()
            return

        if not self._config:
            self._draw_menu_overlay()
            return

        if not self._layout_built:
            self._build_layout()

        # ── Title (centred inside box) ──────────────────────────────
        land = self._land or {}
        tier = land.get('tier', '?')
        owner = land.get('owner')
        if owner:
            defender_name = owner.get('username', 'Unknown')
        else:
            defender_name = land.get('ai_name') or 'AI'
        title = f'Conquer Land (Tier {tier}) \u2014 Defended by {defender_name}'
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
        total_w = specs_surf.get_width() + (suit_icon.get_width() + 2 if suit_icon else 0)
        specs_x = _BOX_X + _BOX_W // 2 - total_w // 2
        specs_y = _BOX_Y + _BOX_PAD + t_surf.get_height() + 4
        self.window.blit(specs_surf, (specs_x, specs_y))
        if suit_icon:
            self.window.blit(suit_icon, (specs_x + specs_surf.get_width() + 2,
                                        specs_y + (specs_surf.get_height() - suit_icon.get_height()) // 2))

        effects = land.get('kingdom_skill_effects') or []
        if effects:
            kingdom_name = land.get('kingdom_name') or 'Defender kingdom'
            effect_text = f'{kingdom_name} skills: ' + ', '.join(effects[:4])
            effect_text = self._fit_text(effect_text, self._tiny_font, int(_BOX_W * 0.72))
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
        div_clr = (90, 80, 60)
        # Vertical divider between left (field/resources) and right (battle) columns
        pygame.draw.line(self.window, div_clr,
                         (self._divider_v_x, self._divider_v_top),
                         (self._divider_v_x, self._divider_v_bottom), 1)

        # ── Section titles with edit icon buttons ───────────────────
        self._draw_section_title('Conquer Field', self._field_title_pos, self._btn_build,
                                description='Place figures to grow your economy')

        # To Battle — enabled only when ready
        ready = self._is_battle_ready()
        battle_clr = (200, 170, 0) if ready else (80, 80, 80)
        self._draw_button(self._btn_battle, 'To Battle!', battle_clr)

        self._draw_close_x_button()

        # ── Detail boxes (drawn last, on top) ──────────────────────
        if self._figure_detail_box:
            self._figure_detail_box.draw()
        if self._move_detail_box:
            self._move_detail_box.draw()

        self._draw_info_popup()

        self._draw_menu_overlay()

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
                icon_y = icon_y_start + i * icon_spacing
                icon_positions[fig.id] = (icon_x, icon_y)
                if icon.hovered:
                    all_hovered = (icon, icon_x, icon_y)
                else:
                    all_regular.append((icon, icon_x, icon_y))

        # Draw in z-order layers
        for icon, ix, iy in reversed(all_regular):
            icon.draw(ix, iy)
        if all_hovered:
            icon, ix, iy = all_hovered
            icon.draw(ix, iy)

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
                if frame_rect.collidepoint(mouse_pos) or x_hovered:
                    bg = (180, 60, 60) if x_hovered else (120, 40, 40)
                    bdr = (220, 120, 120) if x_hovered else (160, 80, 80)
                    tc = (255, 255, 255) if x_hovered else (200, 180, 180)
                    pygame.draw.rect(self.window, bg, xbtn, border_radius=3)
                    pygame.draw.rect(self.window, bdr, xbtn, 1, border_radius=3)
                    xf = settings.get_font(max(int(xbtn.h * 1.3), 8), bold=True)
                    xt = xf.render('\u00d7', True, tc)
                    self.window.blit(xt, xt.get_rect(center=xbtn.center))
                    cfg_fig['_remove_rect'] = xbtn
                else:
                    cfg_fig['_remove_rect'] = None

    def _draw_battle_move_slots(self):
        """Draw 3 battle move slots as diamond icons."""
        moves = self._config.get('battle_moves', [])
        move_by_round = {m['round_index']: m for m in moves}
        self._hovered_slot = -1
        self._move_remove_rects = {}

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

                draw_battle_move_icon(
                    self.window, cx, cy,
                    m['family_name'], m['suit'], m.get('value', 0),
                    self._slot_glow_cache, self._slot_icon_cache,
                    self._slot_frame_cache, self._suit_icon_cache,
                    self._slot_font, sw,
                    hovered=hovered,
                )

                xsz = self._x_btn_sz
                xrect = pygame.Rect(cx + int(sw * 0.35), cy - int(sw * 0.65), xsz, xsz)
                x_hovered = xrect.collidepoint(mouse_pos)
                if is_hovered or x_hovered:
                    bg = (180, 60, 60) if x_hovered else (120, 40, 40)
                    bdr = (220, 120, 120) if x_hovered else (160, 80, 80)
                    tc = (255, 255, 255) if x_hovered else (200, 180, 180)
                    pygame.draw.rect(self.window, bg, xrect, border_radius=3)
                    pygame.draw.rect(self.window, bdr, xrect, 1, border_radius=3)
                    xf = settings.get_font(max(int(xsz * 1.3), 8), bold=True)
                    xt = xf.render('\u00d7', True, tc)
                    self.window.blit(xt, xt.get_rect(center=xrect.center))
                    self._move_remove_rects[i] = xrect

                # Round label below
                rlbl = self._small_font.render(f'R{i + 1}', True, (160, 140, 120))
                self.window.blit(rlbl, rlbl.get_rect(centerx=cx, top=cy + int(sw * 0.55)))
            else:
                # Empty slot
                dr = self._slot_diamond.get_rect(center=(cx, cy))
                self.window.blit(self._slot_diamond, dr.topleft)
                rlbl = self._small_font.render(f'R{i + 1}', True, (100, 100, 100))
                self.window.blit(rlbl, rlbl.get_rect(centerx=cx, top=cy + int(sw * 0.55)))

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
                if icons.get('glow'):
                    glow_surf = icons['glow']
                    gr = glow_surf.get_rect(center=(cx, cy))
                    self.window.blit(glow_surf, gr.topleft)
                if icons.get('icon'):
                    ir = icons['icon'].get_rect(center=(cx, cy))
                    self.window.blit(icons['icon'], ir.topleft)
                if icons.get('frame'):
                    fr = icons['frame'].get_rect(center=(cx, cy))
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
                if rect.collidepoint(mx_mouse, my_mouse) or x_hovered:
                    self._prelude_x_rect = xrect
                    bg = (180, 60, 60) if x_hovered else (120, 40, 40)
                    bdr = (220, 120, 120) if x_hovered else (160, 80, 80)
                    tc = (255, 255, 255) if x_hovered else (200, 180, 180)
                    pygame.draw.rect(self.window, bg, xrect, border_radius=3)
                    pygame.draw.rect(self.window, bdr, xrect, 1, border_radius=3)
                    xf = settings.get_font(max(int(_xbs * 1.3), 8), bold=True)
                    xt = xf.render('\u00d7', True, tc)
                    self.window.blit(xt, xt.get_rect(center=xrect.center))
                else:
                    self._prelude_x_rect = None
        else:
            self._prelude_x_rect = None
            empty_surf = pygame.Surface((fsz, fsz), pygame.SRCALPHA)
            pygame.draw.rect(empty_surf, (50, 45, 35, 180), empty_surf.get_rect(), border_radius=6)
            pygame.draw.rect(empty_surf, (100, 90, 70), empty_surf.get_rect(), 1, border_radius=6)
            self.window.blit(empty_surf, rect.topleft)
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

        resources_data = self._calc_resources()
        produces = resources_data.get('produces', {})
        requires = resources_data.get('requires', {})

        icon_s = int(0.019 * _SW)
        pill_font = self._res_font
        pill_min_w = pill_font.size("00/00")[0] + 8
        rect = self._res_rect

        # Subtitle
        lbl = self._res_font.render('Resources', True, (180, 170, 140))
        self.window.blit(lbl, (rect.x, rect.y - lbl.get_height() - 2))

        # Panel background
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (35, 30, 25, 200), surf.get_rect(), border_radius=4)
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, (140, 130, 110), rect, 1, border_radius=4)

        # Castle resources on the left, village resources on the right
        castle_rows = [
            ('village',  'villager_red_black', [('villager_red', 'villager_black')]),
            ('military', 'warrior_red_black',  [('warrior_red', 'warrior_black')]),
        ]
        village_rows = [
            ('food',     'rice_meat',          [('food_red', 'food_black')]),
            ('material', 'wood_stone',         [('material_red', 'material_black')]),
            ('armor',    'sword_shield',       [('armor_red', 'armor_black')]),
        ]

        half_w = rect.w // 2
        for col_offset, rows in [(0, castle_rows), (half_w, village_rows)]:
            y = rect.y + 8
            for label, icon_key, res_pairs in rows:
                ix = rect.x + col_offset + 8
                icon = self._resource_icons.get(icon_key)
                if icon:
                    self.window.blit(icon, (ix, y))
                    ix += icon_s + 6

                for red_key, black_key in res_pairs:
                    for res_key, pill_clr in [(red_key, (45, 90, 45)), (black_key, (35, 60, 110))]:
                        req = requires.get(res_key, 0)
                        prod = produces.get(res_key, 0)
                        deficit = req > prod
                        text = f'{req}/{prod}'
                        t_surf = pill_font.render(text, True, (255, 255, 255))
                        pw = max(t_surf.get_width() + 8, pill_min_w)
                        ph = t_surf.get_height() + 4
                        pr = pygame.Rect(ix, y + (icon_s - ph) // 2, pw, ph)
                        pill = pygame.Surface((pw, ph), pygame.SRCALPHA)
                        pygame.draw.rect(pill, (*pill_clr, 220), pill.get_rect(), border_radius=3)
                        self.window.blit(pill, pr.topleft)
                        if deficit:
                            pygame.draw.rect(self.window, (200, 50, 50), pr, 2, border_radius=3)
                        tr = t_surf.get_rect(center=pr.center)
                        self.window.blit(t_surf, tr.topleft)
                        ix += pw + 4

                y += icon_s + 6

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
        txt = self._btn_font.render(text, True, (255, 255, 255))
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_section_title(self, title, title_pos, icon_rect, description=None):
        """Draw a section title with an edit icon button next to it."""
        if not icon_rect:
            return
        txt = self._label_font.render(title, True, (200, 185, 150))
        self.window.blit(txt, title_pos)
        if description:
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
        self._game_proxy = KingdomGameProxy(self._config, self._land_id, mode='conquer')
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
        self._game_proxy = KingdomGameProxy(self._config, self._land_id, mode='conquer')
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
        self._game_proxy = KingdomGameProxy(self._config, self._land_id, mode='conquer')
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
        # Refresh config from server to get authoritative state
        self._load_config()

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

    def _build_confirm_data(self):
        """Build confirmation data: message text, grouped cards, and after-message."""
        from game.components.cards.card_img import CardImg

        locked_cards = []
        consumed_cards = []

        def add_card(target, suit, rank):
            if suit and rank:
                ci = CardImg(self.window, suit, rank)
                target.append(ci.front_img)

        # Figures — locked (use card_details from server config)
        for fig in self._config.get('figures', []):
            for cd in fig.get('card_details', []):
                add_card(locked_cards, cd.get('suit', ''), cd.get('rank', ''))

        # Battle moves — spent on this conquer attempt.
        for mv in self._config.get('battle_moves', []):
            if mv.get('card_id'):
                add_card(consumed_cards, mv.get('suit', ''), mv.get('rank', ''))

        # Modifiers / spell cards — spent on this conquer attempt.
        for cd in self._config.get('modifier_card_details') or []:
            add_card(consumed_cards, cd.get('suit', ''), cd.get('rank', ''))
        for cd in self._config.get('spell_card_details') or []:
            add_card(consumed_cards, cd.get('suit', ''), cd.get('rank', ''))

        # Prelude spell — consumed
        prelude_details = self._config.get('prelude_spell_card_details') or []
        if prelude_details:
            for cd in prelude_details:
                add_card(consumed_cards, cd.get('suit', ''), cd.get('rank', ''))

        # Counter spell — included for consistency if conquer configs ever carry one.
        for cd in self._config.get('counter_spell_card_details') or []:
            add_card(consumed_cards, cd.get('suit', ''), cd.get('rank', ''))

        image_groups = []
        if consumed_cards:
            image_groups.append({
                'key': 'consumed',
                'title': 'Consumed when battle starts',
                'description': 'These battle and spell cards are consumed when the conquer battle begins, win or lose.',
                'icon': 'remove',
                'badge_icon': 'remove',
                'items': consumed_cards,
            })
        if locked_cards:
            image_groups.append({
                'key': 'locked',
                'title': 'Locked figure cards',
                'description': 'These figure cards are committed to the attack and cannot be used elsewhere. If you lose, one key card may be looted/lost and the remaining committed figure cards are consumed.',
                'icon': 'lock',
                'badge_icon': 'lock',
                'items': locked_cards,
            })

        msg = 'Review the card costs before starting this conquer battle.'
        if not image_groups:
            msg = 'No cards are used in this configuration.'

        after_msg = None
        if locked_cards:
            after_msg = 'If you lose, one locked key card may be looted/lost and all other committed attack figure cards are consumed.'

        return msg, image_groups, after_msg

    def _on_battle_click(self):
        """Handle click on 'To Battle!' — validate or confirm."""
        if self._is_battle_ready():
            msg, image_groups, after_msg = self._build_confirm_data()
            self._pending_battle_confirm = True
            self.dialogue_box = DialogueBox(
                self.window,
                msg,
                actions=['Confirm', 'Cancel'],
                title='To Battle!',
                image_groups=image_groups,
                message_after_images=after_msg,
            )
        else:
            problems = self._get_battle_problems()
            msg = '\n'.join(f'\u2022 {p}' for p in problems)
            self.dialogue_box = DialogueBox(
                self.window,
                msg,
                actions=['OK'],
                title='Cannot Start Battle',
            )

    # ── Start battle ────────────────────────────────────────────────

    def _leave_screen(self):
        """Reset config on the server (unlock cards) and go back to kingdom."""
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
            self.dialogue_box = DialogueBox(
                self.window,
                'You have unsaved changes.\n'
                'Leaving will discard all figures, battle moves,\n'
                'and spells you have configured.',
                actions=['Leave', 'Stay'],
                title='Discard Changes?',
            )
        else:
            self._leave_screen()

    def _start_battle(self):
        """Call start_battle endpoint and transition to the game screen."""
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/start_battle',
                json={'land_id': self._land_id},
                timeout=15,
            )
            data = resp.json()
            if data.get('game_id'):
                game_id = data['game_id']
                self.state.game_id = game_id
                # Fetch and create a real Game object for the game screen
                try:
                    game_dict = fetch_game(game_id)
                    if game_dict:
                        self.state.game = Game(game_dict, self.state.user_dict)
                    else:
                        self.state.game = None
                except Exception as e:
                    logger.error(f'Failed to fetch game after battle start: {e}')
                    self.state.game = None
                self.state.screen = 'game'
                logger.info(f'Battle started: game_id={game_id}')
            else:
                self._error = (
                    data.get('message')
                    or data.get('error')
                    or 'Failed to start battle'
                )
                logger.warning(f'Start battle failed: {self._error}')
        except Exception as e:
            self._error = 'Connection error'
            logger.error(f'Start battle error: {e}')

    # ── Update / events ─────────────────────────────────────────────

    def update(self, events):
        super().update()
        self._update_icon_buttons()

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

        # Auto-load config if needed
        if self._land_id and not self._config and not self._loading and not self._error:
            self._load_config()

        # Update figure icon hover states
        for icon in self._figure_icons.values():
            icon.update()

    def handle_events(self, events):
        super().handle_events(events)

        # Handle battle confirm / info dialogue response
        response = self.state.action.get('status')
        if response and self._pending_battle_confirm:
            self._pending_battle_confirm = False
            self.reset_action()
            if response == 'confirm':
                self._start_battle()
            return
        if response and self._pending_leave_confirm:
            self._pending_leave_confirm = False
            self.reset_action()
            if response == 'leave':
                self._leave_screen()
            return
        if response and self._pending_prelude_spell:
            self._pending_prelude_spell = None
            self.reset_action()
            return
        if response and self._pending_prelude_clear:
            self._pending_prelude_clear = False
            self.reset_action()
            if response == 'confirm':
                self._server_clear_prelude_spell()
            return
        if response in ('ok', 'cancel'):
            self._pending_battle_confirm = False
            self._pending_leave_confirm = False
            self._pending_prelude_spell = None
            self._pending_prelude_clear = False
            self.reset_action()
            return

        if self.dialogue_box:
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
                if self._btn_close_rect and self._btn_close_rect.collidepoint(pos):
                    self._try_leave_screen()
                    return

                if not self._config:
                    continue

                # Remove buttons must win over icon/detail clicks.
                if self._prelude_x_rect and self._prelude_x_rect.collidepoint(pos):
                    current_spell = self._config.get('prelude_spell_name')
                    if current_spell:
                        self._pending_prelude_clear = True
                        self.dialogue_box = DialogueBox(
                            self.window,
                            f'Remove {current_spell} prelude spell?',
                            actions=['Confirm', 'Cancel'],
                            title='Clear Prelude Spell',
                        )
                    continue

                figure_removed = False
                for fig in self._config.get('figures', []):
                    xrect = fig.get('_remove_rect')
                    if xrect and xrect.collidepoint(pos):
                        self._server_remove_figure(fig['id'])
                        figure_removed = True
                        break
                if figure_removed:
                    continue

                move_removed = False
                for ri, xrect in self._move_remove_rects.items():
                    if xrect.collidepoint(pos):
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
                if self._btn_build and self._btn_build.collidepoint(pos):
                    self._open_build_figure()
                    continue

                # Buy Move button
                if self._btn_buy_move and self._btn_buy_move.collidepoint(pos):
                    self._open_battle_shop()
                    continue

                # Prelude spell: edit button or empty slot click
                if ((self._btn_prelude_edit and self._btn_prelude_edit.collidepoint(pos))
                        or (self._prelude_spell_rect and self._prelude_spell_rect.collidepoint(pos))):
                    self._open_prelude_spell_screen()
                    continue

                # To Battle
                if self._btn_battle and self._btn_battle.collidepoint(pos):
                    self._on_battle_click()
                    continue

                # Click on filled battle move slot → open detail box
                if self._hovered_slot >= 0:
                    moves = self._config.get('battle_moves', [])
                    for m in moves:
                        if m['round_index'] == self._hovered_slot:
                            self._move_detail_box = BattleMoveDetailBox(
                                self.window, m,
                                self._move_manager.families_by_name,
                                None,
                            )
                            break
                    continue

            # ESC → back to kingdom
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                self._try_leave_screen()
                return
