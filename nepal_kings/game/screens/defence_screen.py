# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Defence screen — configure figures, battle moves, spells & gamble for defending a land."""

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
from game.components.figures.figure_manager import FigureManager
from game.components.battle_moves.battle_move_manager import BattleMoveManager
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.components.battle_moves.battle_move_detail_box import BattleMoveDetailBox
from game.components.spells.spell_manager import SpellManager
from game.components.dialogue_box import DialogueBox
from config import settings
from utils import http_compat as requests
from utils import collection_service
import logging

logger = logging.getLogger('nk.screens.defence')

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

_DEFENCE_PRELUDE_SPELLS = [
    'Dump Cards', 'Forced Deal', 'Poison', 'Health Boost',
    'Explosion', 'Peasant War', 'Civil War',
]

_DEFENCE_COUNTER_SPELLS = [
    'Dump Cards', 'Forced Deal', 'Poison', 'Health Boost',
]

_RED_SUITS = {'Hearts', 'Diamonds'}
_BLACK_SUITS = {'Clubs', 'Spades'}

_AUTO_GAMBLE_THRESHOLD_DEFAULT = 10
_AUTO_GAMBLE_THRESHOLD_MIN = 1
_AUTO_GAMBLE_THRESHOLD_MAX = 20

_RIGHT_SECTION_INFO = {
    'battle_plan': {
        'title': 'Battle Plan',
        'message': (
            'Choose the three battle move cards your defenders will use, one per battle round. '
            'A saved defence needs all three rounds assigned, and these cards stay locked while the defence is active.'
        ),
    },
    'prelude_spell': {
        'title': 'Prelude Spell',
        'message': (
            'Prelude spells are optional effects that trigger before a conquer battle begins. '
            'They can restrict the battle or help your defenders before the first round, and any required cards stay locked in the saved defence.'
        ),
    },
    'defender_response': {
        'title': 'Defender Response',
        'message': (
            'Choose the final response your defence will use during battle: either a battle figure or a counter spell. '
            'Exactly one response is required so the defender has a clear last-round plan.'
        ),
    },
}


class DefenceScreen(MenuScreenMixin, Screen):
    """Defence configuration screen.

    Reads ``state.defence_land_id`` to know which owned land the player
    wants to set up defences for.  Fetches (or creates) the LandConfig
    from the server and lets the user build figures, buy battle moves,
    set a modifier, select a battle figure or spell, and toggle auto-gamble.
    """

    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── Persistent state ────────────────────────────────────────
        self._land_id = None
        self._land = None
        self._config = None
        self._loading = False
        self._error = None

        # ── Subscreen state ─────────────────────────────────────────
        self._active_subscreen = None
        self._subscreen_obj = None
        self._game_proxy = None

        # ── Fonts (using font_settings categories) ─────────────────
        self._title_font = settings.get_font(settings.FS_SUBTITLE, bold=True)
        self._label_font = settings.get_font(settings.FS_BODY)
        self._value_font = settings.get_font(settings.FS_BODY, bold=True)
        self._btn_font = settings.get_font(settings.FS_BUTTON, bold=True)
        self._small_font = settings.get_font(settings.FS_SMALL)
        self._res_font = settings.get_font(settings.FS_TINY)
        self._slot_font = settings.get_font(settings.FS_TINY, bold=True)

        # ── Layout rects ────────────────────────────────────────────
        self._field_rects = {}
        self._move_slots_rect = None
        self._move_slot_size = int(0.06 * _SH)
        self._battle_plan_rect = None
        self._prelude_panel_rect = None
        self._counter_panel_rect = None
        self._btn_build = None
        self._btn_buy_move = None
        self._btn_auto_gamble = None
        self._btn_auto_gamble_dec = None
        self._btn_auto_gamble_inc = None
        self._auto_gamble_threshold_rect = None
        self._btn_close_rect = None
        self._res_rect = None
        self._res_castle_rect = None
        self._res_village_rect = None
        self._field_title_pos = None
        self._moves_title_pos = None
        self._prelude_spell_rect = None   # Rect for prelude spell icon slot
        self._prelude_x_rect = None       # Rect for prelude X remove button
        self._counter_spell_rect = None   # Rect for counter spell icon slot
        self._counter_x_rect = None       # Rect for counter X remove button
        self._battle_figure_rect = None   # Rect for battle figure icon slot
        self._battle_figure_x_rect = None # Rect for battle figure X remove button
        self._info_button_rects = {}
        self._active_info_key = None
        self._active_info_popup_rect = None
        self._layout_built = False
        self._hovered_slot = -1
        self._pending_prelude_spell = None
        self._pending_prelude_clear = False
        self._prelude_spell_choices = []
        self._prelude_spell_choice_idx = 0
        self._pending_counter_spell = None
        self._pending_counter_clear = False
        self._counter_spell_choices = []
        self._counter_spell_choice_idx = 0
        self._pending_save_confirm = False
        self._pending_leave_confirm = False
        self._pending_nav = None
        self._draft_dirty = False
        self._collection_cards = None
        self._selecting_battle_fig = False  # True when prompting user to pick a figure
        self._selecting_spell_target = None  # 'prelude' or 'counter' while choosing Health Boost target

        # ── Figure display (eagerly loaded) ─────────────────────────
        self._figure_manager = FigureManager()
        self._move_manager = BattleMoveManager()
        self._figure_objects = []
        self._figure_icons = {}
        self._figure_detail_box = None
        self._move_detail_box = None
        self._move_remove_rects = {}   # round_index → Rect for X buttons

        # ── Slot caches for draw_battle_move_icon ───────────────────
        self._slot_glow_cache = {}
        self._slot_icon_cache = {}
        self._slot_frame_cache = {}
        self._suit_icon_cache = {}
        self._slot_diamond = None
        self._init_move_slot_caches()

        # ── Spell icons (framed, from SpellManager) ─────────────────
        self._spell_icons = {}   # spell_name → icon dict (all prelude + counter spells)
        self._spell_manager = SpellManager()
        self._init_spell_icons()

        # ── Resource icons ──────────────────────────────────────────
        self._resource_icons = {}
        self._init_resource_icons()

        # ── Edit icon (for section title buttons) ───────────────────
        _icon_sz = int(0.025 * _SH)
        self._edit_icon = pygame.transform.smoothscale(
            pygame.image.load('img/dialogue_box/icons/edit.png').convert_alpha(),
            (_icon_sz, _icon_sz),
        )
        self._edit_icon_size = _icon_sz

        # ── Broken icon (for incomplete defence indicator) ──────────
        _broken_sz = int(0.035 * _SH)
        try:
            raw = pygame.image.load('img/figures/state_icons/broken.png').convert_alpha()
            self._broken_icon = pygame.transform.smoothscale(raw, (_broken_sz, _broken_sz))
        except Exception:
            self._broken_icon = None

        # ── Advance icon (for selected battle figure) ─────────────
        self._advance_icon = None
        try:
            raw = pygame.image.load('img/figures/state_icons/charge.png').convert_alpha()
            adv_sz = int(self._spell_frame_size * 0.45)
            self._advance_icon = pygame.transform.smoothscale(raw, (adv_sz, adv_sz))
        except Exception:
            pass

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
        """Called each time the defence screen becomes active — reset cached config."""
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
        self._selecting_spell_target = None
        self._active_info_key = None
        self._active_info_popup_rect = None
        self._pending_save_confirm = False
        self._pending_leave_confirm = False
        self._pending_nav = None
        self._draft_dirty = False

    # ── Asset init ────────────────────────────────────────────────────

    def _init_move_slot_caches(self):
        """Pre-load glow, icon, frame and suit images for battle move icon rendering."""
        sw = self._move_slot_size
        glow_w = int(sw * 1.6)
        frame_w = int(sw * 1.3)
        icon_w = sw - 4
        big = 1.25
        glow_w_big = int(glow_w * big)
        frame_w_big = int(frame_w * big)
        icon_w_big = int(icon_w * big)

        # Glow colours
        glow_colors = {
            'green': 'img/game_button/glow/green.png',
            'blue': 'img/game_button/glow/blue.png',
            'yellow': 'img/game_button/glow/yellow.png',
        }
        for name, path in glow_colors.items():
            try:
                img = pygame.image.load(path).convert_alpha()
                self._slot_glow_cache[name] = pygame.transform.smoothscale(img, (glow_w, glow_w))
                self._slot_glow_cache[name + '_big'] = pygame.transform.smoothscale(img, (glow_w_big, glow_w_big))
            except Exception:
                pass

        # Suit icons
        for suit_name in ('hearts', 'diamonds', 'clubs', 'spades'):
            path = settings.SUIT_ICON_IMG_PATH + suit_name + '.png'
            try:
                img = pygame.image.load(path).convert_alpha()
                s = int(sw * 0.3)
                s_big = int(s * big)
                self._suit_icon_cache[suit_name] = pygame.transform.smoothscale(img, (s, s))
                self._suit_icon_cache[suit_name + '_big'] = pygame.transform.smoothscale(img, (s_big, s_big))
            except Exception:
                pass

        # Move family icons + frames
        for fam_name, fam in self._move_manager.families_by_name.items():
            if fam.icon_img:
                try:
                    self._slot_icon_cache[fam_name] = pygame.transform.smoothscale(fam.icon_img, (icon_w, icon_w))
                    self._slot_icon_cache[fam_name + '_big'] = pygame.transform.smoothscale(fam.icon_img, (icon_w_big, icon_w_big))
                except Exception:
                    pass
            if fam.frame_img:
                try:
                    self._slot_frame_cache[fam_name] = pygame.transform.smoothscale(fam.frame_img, (frame_w, frame_w))
                    self._slot_frame_cache[fam_name + '_big'] = pygame.transform.smoothscale(fam.frame_img, (frame_w_big, frame_w_big))
                except Exception:
                    pass

        # Empty diamond placeholder
        d_size = int(sw * 1.3)
        self._slot_diamond = pygame.Surface((d_size, d_size), pygame.SRCALPHA)
        pts = [(d_size // 2, 0), (d_size, d_size // 2), (d_size // 2, d_size), (0, d_size // 2)]
        pygame.draw.polygon(self._slot_diamond, (60, 60, 60), pts)
        pygame.draw.polygon(self._slot_diamond, (100, 90, 70), pts, 2)

    def _init_spell_icons(self):
        """Load spell icons with frames from SpellManager for all prelude + counter spells."""
        isz = int(0.045 * _SW)
        fsz = int(isz * 1.4)
        ssz = int(isz * 0.4)
        xsz = int(isz * 0.3)
        self._mod_icon_size = isz
        self._mod_frame_size = fsz
        self._spell_frame_size = fsz

        all_spell_names = set(_DEFENCE_PRELUDE_SPELLS) | set(_DEFENCE_COUNTER_SPELLS)
        for spell_name in all_spell_names:
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
        """Load resource icons for inline display."""
        icon_s = int(0.019 * _SW)
        for key, path in settings.RESOURCE_ICON_IMG_PATH_DICT.items():
            try:
                img = pygame.image.load(path).convert_alpha()
                self._resource_icons[key] = pygame.transform.smoothscale(img, (icon_s, icon_s))
            except Exception:
                pass

    # ── Layout ──────────────────────────────────────────────────────

    def _build_layout(self):
        pad = int(0.02 * _SW)
        top = _BOX_Y + _BOX_PAD + int(0.045 * _SH)   # below compact title

        # Section title row height — add extra gap below subtitle (gold rate / suit bonus)
        section_h = int(0.03 * _SH) + int(0.01 * _SH)
        content_top = top + section_h + int(0.65 * pad)

        # Left: 3 field compartments.  Keep the structure, but trim width a bit
        # so the action column can breathe.
        field_w = int(0.132 * _SW)
        field_h = int(0.48 * _SH)
        fx = _BOX_X + pad
        for field in ('castle', 'village', 'military'):
            self._field_rects[field] = pygame.Rect(fx, content_top, field_w, field_h)
            fx += field_w + pad

        # Edit icon button next to "Defence Field" section title
        isz = self._edit_icon_size
        field_title_surf = self._label_font.render('Defence Field', True, (0, 0, 0))
        title_w = field_title_surf.get_width()
        self._field_title_pos = (_BOX_X + pad, top)
        self._btn_build = pygame.Rect(
            _BOX_X + pad + title_w + int(0.008 * _SW),
            top + (field_title_surf.get_height() - isz) // 2,
            isz, isz,
        )

        btn_h = int(0.045 * _SH)

        # Right column: battle plan, prelude spell, defender response.
        right_x = _BOX_X + pad + 3 * (field_w + pad)
        self._right_x = right_x
        right_right = _BOX_X + _BOX_W - _BOX_PAD
        right_w = right_right - right_x
        panel_gap = int(0.014 * _SH)
        panel_pad = int(0.010 * _SW)
        panel_pad_y = int(0.010 * _SH)
        sw = self._move_slot_size
        slot_row_w = int(sw * 2.0) * 2 + int(sw * 1.3)
        slot_row_h = int(sw * 1.45)
        header_h = self._label_font.get_height() + self._res_font.get_height() + int(0.015 * _SH)
        ag_btn_h = int(0.035 * _SH)
        battle_controls_gap = int(0.018 * _SH)
        fsz = self._mod_frame_size

        # Save Defence button (bottom-right of box)
        save_w = int(0.20 * _SW)
        save_h = int(0.055 * _SH)
        self._btn_save = pygame.Rect(
            _BOX_X + _BOX_W - _BOX_PAD - save_w,
            _BOX_BOTTOM - _BOX_PAD - save_h,
            save_w, save_h,
        )

        right_content_bottom = self._btn_save.y - panel_gap
        right_content_h = max(1, right_content_bottom - content_top)
        available_panel_h = max(1, right_content_h - 2 * panel_gap)
        battle_plan_min_h = header_h + slot_row_h + battle_controls_gap + ag_btn_h + panel_pad_y
        prelude_min_h = header_h + fsz + panel_pad_y
        counter_min_h = header_h + fsz + panel_pad_y

        max_battle_plan_h = max(ag_btn_h, available_panel_h - prelude_min_h - counter_min_h)
        battle_plan_h = min(
            max(battle_plan_min_h, int(available_panel_h * 0.40)),
            max_battle_plan_h,
        )
        remaining_h = max(1, available_panel_h - battle_plan_h)
        prelude_h = min(
            max(prelude_min_h, int(available_panel_h * 0.27)),
            max(prelude_min_h, remaining_h - counter_min_h),
        )
        counter_h = max(counter_min_h, remaining_h - prelude_h)

        self._battle_plan_rect = pygame.Rect(right_x, content_top, right_w, battle_plan_h)
        self._prelude_panel_rect = pygame.Rect(
            right_x, self._battle_plan_rect.bottom + panel_gap, right_w, prelude_h)
        self._counter_panel_rect = pygame.Rect(
            right_x, self._prelude_panel_rect.bottom + panel_gap, right_w, counter_h)
        self._info_button_rects = {
            'battle_plan': self._info_button_rect(self._battle_plan_rect),
            'prelude_spell': self._info_button_rect(self._prelude_panel_rect),
            'defender_response': self._info_button_rect(self._counter_panel_rect),
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

        self._move_slots_rect = pygame.Rect(
            self._battle_plan_rect.centerx - slot_row_w // 2,
            self._battle_plan_rect.y + header_h,
            slot_row_w,
            slot_row_h,
        )

        # Auto-gamble controls — footer row below battle moves.
        agw = int(0.12 * _SW)
        ag_y = min(
            self._move_slots_rect.bottom + battle_controls_gap,
            self._battle_plan_rect.bottom - panel_pad_y - ag_btn_h,
        )
        ag_x = self._battle_plan_rect.x + panel_pad
        self._btn_auto_gamble = pygame.Rect(ag_x, ag_y, agw, ag_btn_h)

        # Threshold controls ("Below") in the same footer row.
        ag_ctrl_w = int(0.024 * _SW)
        ag_ctrl_gap = int(0.004 * _SW)
        below_label_w = self._res_font.size('Below:')[0] + int(0.006 * _SW)
        ag_ctrl_x = self._btn_auto_gamble.right + int(0.014 * _SW) + below_label_w
        ag_ctrl_y = ag_y
        self._btn_auto_gamble_dec = pygame.Rect(ag_ctrl_x, ag_ctrl_y, ag_ctrl_w, ag_btn_h)
        self._btn_auto_gamble_inc = pygame.Rect(ag_ctrl_x + ag_ctrl_w + int(0.04 * _SW), ag_ctrl_y,
                                                ag_ctrl_w, ag_btn_h)
        self._auto_gamble_threshold_rect = pygame.Rect(
            self._btn_auto_gamble_dec.right + ag_ctrl_gap,
            ag_ctrl_y,
            max(1, self._btn_auto_gamble_inc.x - self._btn_auto_gamble_dec.right - (2 * ag_ctrl_gap)),
            ag_btn_h,
        )

        # ── Prelude Spell panel (single spell icon slot + edit button) ──
        prelude_header_y = self._prelude_panel_rect.y + int(0.010 * _SH)
        self._mod_section_y = self._prelude_panel_rect.y + header_h
        self._prelude_spell_rect = pygame.Rect(
            self._prelude_panel_rect.x + panel_pad,
            self._mod_section_y,
            fsz, fsz)
        # Edit icon button next to "Prelude Spell" label
        prelude_title_surf = self._small_font.render('Prelude Spell', True, (0, 0, 0))
        prelude_title_w = prelude_title_surf.get_width()
        self._prelude_title_pos = (self._prelude_panel_rect.x + panel_pad, prelude_header_y)
        self._btn_prelude_edit = pygame.Rect(
            self._prelude_title_pos[0] + prelude_title_w + int(0.008 * _SW),
            self._prelude_title_pos[1] + (prelude_title_surf.get_height() - isz) // 2,
            isz, isz,
        )

        # ── Counter Action panel (battle figure OR counter spell + edit button) ──
        counter_header_y = self._counter_panel_rect.y + int(0.010 * _SH)
        self._final_section_y = self._counter_panel_rect.y + header_h
        final_x = self._counter_panel_rect.x + panel_pad
        # Battle figure slot
        self._battle_figure_rect = pygame.Rect(final_x, self._final_section_y, fsz, fsz)
        # Counter spell slot (to the right of battle figure with separator gap)
        spell_gap = min(
            fsz + int(0.11 * _SW),
            self._counter_panel_rect.right - final_x - fsz,
        )
        self._counter_spell_rect = pygame.Rect(final_x + spell_gap, self._final_section_y, fsz, fsz)
        # Edit icon next to "Counter Action" label
        counter_title_surf = self._small_font.render('Defender Response', True, (0, 0, 0))
        counter_title_w = counter_title_surf.get_width()
        self._counter_title_pos = (self._counter_panel_rect.x + panel_pad, counter_header_y)
        self._btn_counter_edit = pygame.Rect(
            self._counter_title_pos[0] + counter_title_w + int(0.008 * _SW),
            self._counter_title_pos[1] + (counter_title_surf.get_height() - isz) // 2,
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

        # ── Divider positions (computed from layout) ────────────────
        self._divider_v_x = right_x - pad // 2
        self._divider_v_top = top
        self._divider_v_bottom = _BOX_BOTTOM - _BOX_PAD
        self._divider_h1_y = None
        self._divider_h2_y = None

        # X close button (top-right of box)
        _xsz = int(0.028 * _SH)
        _xmargin = int(0.012 * _SW)
        self._btn_close_rect = pygame.Rect(
            _BOX_X + _BOX_W - _xsz - _xmargin,
            _BOX_Y + _xmargin,
            _xsz, _xsz)

        self._layout_built = True

    # ── Data loading ────────────────────────────────────────────────

    def _apply_config(self, config):
        self._config = config
        self._draft_dirty = bool((config or {}).get('draft_dirty', True))

    def _load_config(self):
        self._loading = True
        self._error = None
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/open',
                json={'land_id': self._land_id},
                timeout=15,
            )
            if resp.status_code != 200:
                err = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
                self._error = err.get('message', err.get('error', 'Failed to load defence config'))
                self._loading = False
                return
            data = resp.json()
            self._apply_config(data.get('config'))
            self._land = data.get('land')
            self._loading = False
            self._rebuild_figure_objects()
            self._refresh_collection()
            self._maybe_prompt_missing_spell_target()
            logger.debug(f'Defence config loaded for land {self._land_id}')
        except Exception as e:
            self._error = 'Connection error'
            logger.error(f'Defence config load error: {e}')
            self._loading = False

    # ── Server actions ──────────────────────────────────────────────

    def _server_validate_draft(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/validate',
                json={'land_id': self._land_id},
                timeout=10,
            )
            data = resp.json()
            return data
        except Exception as e:
            logger.error(f'Validate defence draft error: {e}')
            return {'success': False, 'problems': ['Connection error']}

    def _server_save_draft(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/save',
                json={'land_id': self._land_id},
                timeout=15,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data.get('config'))
                self._land = data.get('land', self._land)
                self._rebuild_figure_objects()
                self._refresh_collection()
                self.state.set_msg('Defence saved')
                return True
            problems = data.get('problems') or [data.get('message', 'Could not save defence')]
            self._show_problem_dialogue('Cannot Save Defence', problems)
            return False
        except Exception as e:
            logger.error(f'Save defence draft error: {e}')
            self.state.set_msg('Could not save defence')
            return False

    def _server_discard_draft(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/discard',
                json={'land_id': self._land_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data.get('config'))
                self._land = data.get('land', self._land)
                if self._config:
                    self._rebuild_figure_objects()
                else:
                    self._figure_objects = []
                    self._figure_icons = {}
                self._refresh_collection()
                return True
            self.state.set_msg(data.get('message', 'Could not discard changes'))
            return False
        except Exception as e:
            logger.error(f'Discard defence draft error: {e}')
            self.state.set_msg('Could not discard changes')
            return False

    def _show_problem_dialogue(self, title, problems):
        msg = '\n'.join(f'• {p}' for p in (problems or ['Unknown problem']))
        self.dialogue_box = DialogueBox(
            self.window,
            msg,
            actions=['OK'],
            title=title,
        )

    def _complete_pending_navigation(self):
        target = self._pending_nav or 'kingdom'
        self._pending_nav = None
        if target == 'logout':
            self._logout_dialogue = DialogueBox(
                self.window,
                'Are you sure you want to log out?',
                actions=['yes', 'no'],
                icon='question',
                title='Logout'
            )
            return
        self.state.screen = target

    def _server_remove_figure(self, figure_id):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/remove_figure',
                json={'figure_id': figure_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data['config'])
                self._rebuild_figure_objects()
                self._maybe_prompt_missing_spell_target()
            else:
                logger.warning(f'Remove figure failed: {data.get("message")}')
        except Exception as e:
            logger.error(f'Remove figure error: {e}')

    def _server_return_move(self, move_id):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/return_battle_move',
                json={'move_id': move_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data['config'])
            else:
                logger.warning(f'Return move failed: {data.get("message")}')
        except Exception as e:
            logger.error(f'Return move error: {e}')

    def _server_set_prelude_spell(self, spell_name, target_figure_id=None):
        try:
            payload = {'land_id': self._land_id, 'spell_name': spell_name}
            if target_figure_id:
                payload['target_figure_id'] = target_figure_id
                payload['spell_data'] = {'target_figure_id': target_figure_id}
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/set_prelude_spell',
                json=payload,
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data['config'])
                self._refresh_collection()
                self._maybe_prompt_missing_spell_target()
            else:
                self.state.set_msg(data.get('message', 'Cannot set prelude spell'))
        except Exception as e:
            logger.error(f'Set prelude spell error: {e}')

    def _server_clear_prelude_spell(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/clear_prelude_spell',
                json={'land_id': self._land_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data['config'])
                self._refresh_collection()
        except Exception as e:
            logger.error(f'Clear prelude spell error: {e}')

    def _server_set_battle_figure(self, figure_id, figure_id_2=None):
        try:
            payload = {'land_id': self._land_id, 'figure_id': figure_id}
            if figure_id_2:
                payload['figure_id_2'] = figure_id_2
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/set_battle_figure',
                json=payload, timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data['config'])
            else:
                logger.warning(f'Set battle figure failed: {data.get("message")}')
        except Exception as e:
            logger.error(f'Set battle figure error: {e}')

    def _server_clear_battle_figure(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/clear_battle_figure',
                json={'land_id': self._land_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data['config'])
        except Exception as e:
            logger.error(f'Clear battle figure error: {e}')

    def _server_set_counter_spell(self, spell_name, target_figure_id=None):
        try:
            payload = {'land_id': self._land_id, 'spell_name': spell_name}
            if target_figure_id:
                payload['target_figure_id'] = target_figure_id
                payload['spell_data'] = {'target_figure_id': target_figure_id}
            # Atomically clear an existing battle figure on the server side
            # so we don't issue two separate requests that could race.
            cfg = self._config or {}
            if cfg.get('battle_figure_id') or cfg.get('battle_figure_id_2'):
                payload['clear_battle_figure'] = True
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/set_counter_spell',
                json=payload,
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data['config'])
                self._refresh_collection()
                self._maybe_prompt_missing_spell_target()
            else:
                self.state.set_msg(data.get('message', 'Cannot set counter spell'))
        except Exception as e:
            logger.error(f'Set counter spell error: {e}')

    def _server_clear_counter_spell(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/clear_counter_spell',
                json={'land_id': self._land_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data['config'])
                self._refresh_collection()
        except Exception as e:
            logger.error(f'Clear counter spell error: {e}')

    def _server_set_auto_gamble(self, enabled):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/set_auto_gamble',
                json={'land_id': self._land_id, 'auto_gamble': enabled},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._apply_config(data['config'])
        except Exception as e:
            logger.error(f'Set auto gamble error: {e}')

    def _get_auto_gamble_threshold(self):
        raw = (_AUTO_GAMBLE_THRESHOLD_DEFAULT if not self._config
               else self._config.get('auto_gamble_threshold', _AUTO_GAMBLE_THRESHOLD_DEFAULT))
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = _AUTO_GAMBLE_THRESHOLD_DEFAULT

        if value < _AUTO_GAMBLE_THRESHOLD_MIN:
            return _AUTO_GAMBLE_THRESHOLD_MIN
        if value > _AUTO_GAMBLE_THRESHOLD_MAX:
            return _AUTO_GAMBLE_THRESHOLD_MAX
        return value

    def _server_set_auto_gamble_threshold(self, threshold):
        threshold = max(_AUTO_GAMBLE_THRESHOLD_MIN,
                        min(_AUTO_GAMBLE_THRESHOLD_MAX, int(threshold)))
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/set_auto_gamble_threshold',
                json={'land_id': self._land_id, 'auto_gamble_threshold': threshold},
                timeout=10,
            )
            data = None
            try:
                data = resp.json()
            except Exception:
                data = None

            if not isinstance(data, dict):
                body = (getattr(resp, 'text', '') or '').strip().replace('\n', ' ')
                logger.error(
                    'Set auto gamble threshold failed: unexpected response '
                    f'status={getattr(resp, "status_code", "?")} body={body[:200]}'
                )
                self.state.set_msg('Could not update auto-gamble threshold')
                return False

            if data.get('success'):
                self._apply_config(data['config'])
                return True

            self.state.set_msg(data.get('message', 'Could not update auto-gamble threshold'))
            return False
        except Exception as e:
            logger.error(f'Set auto gamble threshold error: {e}')
            self.state.set_msg('Could not update auto-gamble threshold')
            return False

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

        for cfg_fig in self._config.get('figures', []):
            fig = self._config_fig_to_figure(cfg_fig, families)
            if fig is None:
                continue
            self._figure_objects.append(fig)

            if fig.id in old_icons:
                icon = old_icons[fig.id]
                icon.figure = fig
                icon.game = game_proxy
                icon.has_deficit = icon._check_resource_deficit(resources_data)
                icon.battle_bonus_received = icon._calculate_battle_bonus_received(self._figure_objects)
            else:
                icon = FieldFigureIcon(
                    window=self.window,
                    game=game_proxy,
                    figure=fig,
                    is_visible=True,
                    all_player_figures=self._figure_objects,
                    resources_data=resources_data,
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

        matched = None
        for fam_fig in family.figures:
            if fam_fig.suit == suit and fam_fig.name == name:
                matched = fam_fig
                break
        if matched is None:
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
        produces = {}
        requires = {}
        for fig in self._config.get('figures', []):
            for res, amt in (fig.get('produces') or {}).items():
                produces[res] = produces.get(res, 0) + amt
            for res, amt in (fig.get('requires') or {}).items():
                requires[res] = requires.get(res, 0) + amt
        return {'produces': produces, 'requires': requires}

    # ── Rendering ───────────────────────────────────────────────────

    def _draw_land_header(self, land):
        """Draw compact header: title + integer land summary."""
        title = 'Defence Setup'
        t_surf = self._title_font.render(title, True, (100, 200, 255))
        self.window.blit(t_surf, t_surf.get_rect(centerx=_BOX_X + _BOX_W // 2,
                                                  top=_BOX_Y + _BOX_PAD))

        tier = land.get('tier', '?')
        gold_rate = self._to_int(land.get('gold_rate', 0), 0)
        suit = str(land.get('suit_bonus_suit', '?') or '?')
        bonus = self._to_int(land.get('suit_bonus_value', 0), 0)

        prefix = f'Tier {tier}  ·  {gold_rate} gold/hr  ·  +{bonus} '
        specs_surf = self._res_font.render(prefix, True, (180, 170, 140))
        suit_icon = self._header_suit_icons.get(suit.lower())
        total_w = specs_surf.get_width() + (suit_icon.get_width() + 2 if suit_icon else 0)
        specs_x = _BOX_X + _BOX_W // 2 - total_w // 2
        specs_y = _BOX_Y + _BOX_PAD + t_surf.get_height() + 4
        self.window.blit(specs_surf, (specs_x, specs_y))
        if suit_icon:
            self.window.blit(suit_icon, (specs_x + specs_surf.get_width() + 2,
                                        specs_y + (specs_surf.get_height() - suit_icon.get_height()) // 2))

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

    def _blit_scaled_centered(self, source, rect, scale=1.0, alpha=None):
        """Scale a surface to fit within rect and blit it centered."""
        if not source or not rect:
            return
        max_w = max(1, int(rect.w * scale))
        max_h = max(1, int(rect.h * scale))
        src_w, src_h = source.get_size()
        if src_w <= 0 or src_h <= 0:
            return
        factor = min(max_w / src_w, max_h / src_h)
        size = (max(1, int(src_w * factor)), max(1, int(src_h * factor)))
        surf = pygame.transform.smoothscale(source, size)
        if alpha is not None:
            surf.set_alpha(alpha)
        self.window.blit(surf, surf.get_rect(center=rect.center).topleft)

    def _draw_compact_figure_icon(self, rect, figure_id, hovered=False):
        """Draw a figure icon in a panel without field labels or selection badges."""
        figure = next((f for f in self._figure_objects if f.id == figure_id), None)
        if not figure:
            return False
        family = figure.family
        glow = getattr(family, 'glow_img', None)
        if glow:
            self._blit_scaled_centered(glow, rect, scale=1.28, alpha=170 if hovered else 115)
        self._blit_scaled_centered(getattr(family, 'icon_img_small', None), rect, scale=0.62)
        self._blit_scaled_centered(getattr(family, 'frame_img', None), rect, scale=1.0)
        return True

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
        self._draw_section_panel(
            self._counter_panel_rect,
            'Defender Response',
            description='Choose a battle figure or counter spell',
            icon_rect=self._btn_counter_edit,
            title_pos=self._counter_title_pos,
        )
        self._draw_info_buttons()

    def _draw_selection_prompt(self, prompt_text, helper_text, color):
        """Draw a selection prompt below the screen header, never over the title."""
        prompt = self._label_font.render(prompt_text, True, color)
        helper = self._small_font.render(helper_text, True, (180, 170, 150))
        prompt_pad_x = int(0.012 * _SW)
        prompt_pad_y = int(0.008 * _SH)
        prompt_w = max(prompt.get_width(), helper.get_width()) + 2 * prompt_pad_x
        prompt_h = prompt.get_height() + helper.get_height() + int(0.006 * _SH) + 2 * prompt_pad_y
        header_bottom = _BOX_Y + _BOX_PAD + self._title_font.get_height() + self._res_font.get_height() + int(0.022 * _SH)
        section_bottom = self._field_title_pos[1] + self._label_font.get_height() + self._res_font.get_height() + int(0.010 * _SH)
        prompt_y = max(header_bottom, section_bottom)
        prompt_rect = pygame.Rect(
            _BOX_X + (_BOX_W - prompt_w) // 2,
            prompt_y,
            prompt_w,
            prompt_h,
        )
        surf = pygame.Surface((prompt_rect.w, prompt_rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (22, 18, 14, 225), surf.get_rect(), border_radius=6)
        self.window.blit(surf, prompt_rect.topleft)
        pygame.draw.rect(self.window, (130, 115, 80), prompt_rect, 1, border_radius=6)
        self.window.blit(prompt, prompt.get_rect(centerx=prompt_rect.centerx,
                                                 top=prompt_rect.y + prompt_pad_y))
        self.window.blit(helper, helper.get_rect(centerx=prompt_rect.centerx,
                                                 top=prompt_rect.y + prompt_pad_y + prompt.get_height() + int(0.006 * _SH)))
        return prompt_rect

    def render(self):
        self._draw_menu_chrome()

        if self._active_subscreen and self._subscreen_obj:
            self._subscreen_obj.draw()
            self._draw_menu_overlay()
            return

        box_rect = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        _draw_panel(self.window, box_rect)

        if self._loading:
            txt = self._label_font.render('Loading defence config…', True, (200, 185, 150))
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

        # ── Title / land summary ────────────────────────────────────
        land = self._land or {}
        self._draw_land_header(land)

        self._draw_right_panels()
        self._draw_field_compartments()
        self._draw_battle_move_slots()
        self._draw_auto_gamble()
        self._draw_prelude_spell()
        self._draw_counter_action()
        self._draw_resources()

        # Save Defence button
        ready = self._is_defence_ready()
        save_clr = (100, 180, 80) if ready else (80, 80, 80)
        self._draw_button(self._btn_save, 'Save Defence', save_clr)

        # ── Divider lines ───────────────────────────────────────────
        div_clr = (90, 80, 60)
        # Vertical divider between left (field/resources) and right (battle) columns
        pygame.draw.line(self.window, div_clr,
                         (self._divider_v_x, self._divider_v_top),
                         (self._divider_v_x, self._divider_v_bottom), 1)

        self._draw_section_title('Defence Field', self._field_title_pos, self._btn_build,
                                description='Place figures to protect your land')

        # Incomplete defence indicator (top-left of box)
        if not self._is_defence_ready() and self._broken_icon:
            bx = _BOX_X + _BOX_PAD
            by = _BOX_Y + _BOX_PAD
            self.window.blit(self._broken_icon, (bx, by))
            warn = self._small_font.render('Defence incomplete', True, (220, 60, 60))
            self.window.blit(warn, (bx + self._broken_icon.get_width() + 6,
                                    by + (self._broken_icon.get_height() - warn.get_height()) // 2))

        # Battle figure selection mode overlay
        if self._selecting_battle_fig:
            # Dim the whole box
            dim = pygame.Surface((_BOX_W, _BOX_H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 120))
            self.window.blit(dim, (_BOX_X, _BOX_Y))
            # Re-draw field compartments on top of dim so figures are visible and clickable
            self._draw_field_compartments()
            self._draw_selection_prompt(
                'Click a figure to select as Battle Figure',
                'Click elsewhere to cancel',
                (255, 220, 80),
            )

        # Health Boost target selection mode overlay
        if self._selecting_spell_target:
            dim = pygame.Surface((_BOX_W, _BOX_H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 120))
            self.window.blit(dim, (_BOX_X, _BOX_Y))
            label = 'prelude' if self._selecting_spell_target == 'prelude' else 'counter spell'
            prompt_text = f'Click one of your figures for Health Boost {label}'
            helper_text = 'Press Esc to cancel.'
            self._draw_field_compartments()
            self._draw_selection_prompt(prompt_text, helper_text, (120, 240, 120))

        self._draw_close_x_button()

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

        battle_fig_ids = set()
        bf1 = self._config.get('battle_figure_id')
        bf2 = self._config.get('battle_figure_id_2')
        if bf1:
            battle_fig_ids.add(bf1)
        if bf2:
            battle_fig_ids.add(bf2)

        # Collect icon positions so X buttons can be placed on figure icons
        icon_positions = {}  # fig.id → (icon_x, icon_y)

        for field_name, rect in self._field_rects.items():
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            clr = field_colors.get(field_name, (106, 58, 24))
            surf.fill((*clr, settings.FIELD_TRANSPARENCY))
            self.window.blit(surf, rect.topleft)

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

            pygame.draw.rect(self.window, settings.FIELD_BORDER_COLOR, rect,
                             settings.FIELD_BORDER_WIDTH, border_radius=2)

            lbl = self._label_font.render(field_name.upper(), True, (180, 160, 120))
            self.window.blit(lbl, (rect.x + 6, rect.y + 4))

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

        for icon, ix, iy in reversed(all_regular):
            icon.draw(ix, iy)
        if all_hovered:
            icon, ix, iy = all_hovered
            icon.draw(ix, iy)

        # Draw X buttons on each figure icon (top-right of frame) and advance icon for battle figures
        _xbs = self._x_btn_sz
        frame_w = int(settings.FRAME_FIGURE_SCALE * settings.FIGURE_ICON_WIDTH)
        frame_h = int(settings.FRAME_FIGURE_SCALE * settings.FIGURE_ICON_HEIGHT)
        mouse_pos = pygame.mouse.get_pos()
        for fig in self._figure_objects:
            pos = icon_positions.get(fig.id)
            if not pos:
                continue
            ix, iy = pos
            # Frame rect centered on icon position
            fr_left = ix - frame_w // 2
            fr_top = iy - frame_h // 2
            frame_rect = pygame.Rect(int(fr_left), int(fr_top), frame_w, frame_h)

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

            # Battle figure advance icon (replaces old [B] indicator)
            if fig.id in battle_fig_ids and self._advance_icon:
                adv_w = self._advance_icon.get_width()
                adv_h = self._advance_icon.get_height()
                adv_x = int(ix - adv_w // 2)
                adv_y = int(iy - adv_h // 2)
                self.window.blit(self._advance_icon, (adv_x, adv_y))

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

                rlbl = self._small_font.render(f'R{i + 1}', True, (160, 140, 120))
                self.window.blit(rlbl, rlbl.get_rect(centerx=cx, top=cy + int(sw * 0.55)))
            else:
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
                if spell_name == 'Health Boost':
                    target = self._config.get('prelude_spell_target_figure') or {}
                    target_name = target.get('name') or 'choose target'
                    target_clr = (120, 220, 120) if target.get('id') else (230, 140, 80)
                    lines.append((f'Target: {target_name}', self._res_font, target_clr))
                text_h = sum(font.get_height() for _, font, _ in lines) + max(0, len(lines) - 1) * 2
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

    def _draw_counter_action(self):
        """Draw the counter action section: battle figure OR counter spell."""
        counter_spell = self._config.get('counter_spell_name')
        bf_id = self._config.get('battle_figure_id')
        fsz = self._spell_frame_size
        mx_mouse, my_mouse = pygame.mouse.get_pos()

        # ── Battle figure slot ──
        bf_rect = self._battle_figure_rect
        if bf_rect:
            self._draw_battle_figure_icon(bf_rect, bf_id, mx_mouse, my_mouse)

        # ── Vertical separator between figure and spell ──
        cs_rect = self._counter_spell_rect
        if bf_rect and cs_rect:
            sep_x = (bf_rect.right + cs_rect.x) // 2
            sep_y1 = self._final_section_y
            sep_y2 = self._final_section_y + fsz
            pygame.draw.line(self.window, (100, 90, 70), (sep_x, sep_y1), (sep_x, sep_y2), 1)
            or_surf = self._res_font.render('or', True, (150, 135, 110))
            bg = pygame.Surface((or_surf.get_width() + 8, or_surf.get_height() + 4), pygame.SRCALPHA)
            pygame.draw.rect(bg, (35, 30, 25, 210), bg.get_rect(), border_radius=3)
            bg_rect = bg.get_rect(center=(sep_x, self._final_section_y + fsz // 2))
            self.window.blit(bg, bg_rect.topleft)
            self.window.blit(or_surf, or_surf.get_rect(center=bg_rect.center))

        # ── Counter spell slot ──
        if not cs_rect:
            return

        cx = cs_rect.x + fsz // 2
        cy = cs_rect.y + fsz // 2
        caption_x = cs_rect.right + int(0.012 * _SW)
        caption_right = (self._counter_panel_rect.right - int(0.010 * _SW)
                         if self._counter_panel_rect else cs_rect.right)
        caption_w = max(0, caption_right - caption_x)

        if counter_spell:
            icons = self._spell_icons.get(counter_spell)
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
                lines = [(counter_spell, self._res_font, (180, 100, 220))]
                if counter_spell == 'Health Boost':
                    target = self._config.get('counter_spell_target_figure') or {}
                    target_name = target.get('name') or 'choose target'
                    target_clr = (120, 220, 120) if target.get('id') else (230, 140, 80)
                    lines.append((f'Target: {target_name}', self._res_font, target_clr))
                text_h = sum(font.get_height() for _, font, _ in lines) + max(0, len(lines) - 1) * 2
                self._draw_caption_lines(lines, caption_x, cy - text_h // 2, caption_w)
                if self._success_badge:
                    bx = cs_rect.x
                    by = cs_rect.bottom - self._success_badge.get_height()
                    self.window.blit(self._success_badge, (bx, by))
                _xbs = self._x_btn_sz
                xrect = pygame.Rect(cs_rect.right - _xbs - 2, cs_rect.y + 2, _xbs, _xbs)
                x_hovered = xrect.collidepoint(mx_mouse, my_mouse)
                if cs_rect.collidepoint(mx_mouse, my_mouse) or x_hovered:
                    self._counter_x_rect = xrect
                    bg = (180, 60, 60) if x_hovered else (120, 40, 40)
                    bdr = (220, 120, 120) if x_hovered else (160, 80, 80)
                    tc = (255, 255, 255) if x_hovered else (200, 180, 180)
                    pygame.draw.rect(self.window, bg, xrect, border_radius=3)
                    pygame.draw.rect(self.window, bdr, xrect, 1, border_radius=3)
                    xf = settings.get_font(max(int(_xbs * 1.3), 8), bold=True)
                    xt = xf.render('\u00d7', True, tc)
                    self.window.blit(xt, xt.get_rect(center=xrect.center))
                else:
                    self._counter_x_rect = None
        else:
            self._counter_x_rect = None
            empty_surf = pygame.Surface((fsz, fsz), pygame.SRCALPHA)
            pygame.draw.rect(empty_surf, (50, 45, 35, 180), empty_surf.get_rect(), border_radius=6)
            pygame.draw.rect(empty_surf, (100, 90, 70), empty_surf.get_rect(), 1, border_radius=6)
            self.window.blit(empty_surf, cs_rect.topleft)
            lines = [
                ('No counter spell', self._res_font, (140, 130, 110)),
                ('Optional', self._res_font, (110, 105, 95)),
            ]
            text_h = sum(font.get_height() for _, font, _ in lines) + 2
            self._draw_caption_lines(lines, caption_x, cy - text_h // 2, caption_w)

    def _draw_battle_figure_icon(self, rect, bf_id, mx, my_mouse):
        """Draw the battle figure slot in the final round section."""
        fsz = self._spell_frame_size
        cx = rect.x + fsz // 2
        cy = rect.y + fsz // 2

        is_selected = bf_id is not None

        if is_selected:
            hovered = rect.collidepoint(mx, my_mouse)
            if not self._draw_compact_figure_icon(rect, bf_id, hovered=hovered):
                fig_name = self._figure_name(bf_id)
                pygame.draw.rect(self.window, (40, 50, 60, 200), rect, border_radius=4)
                pygame.draw.rect(self.window, (80, 100, 130), rect, 1, border_radius=4)
                ntxt = self._res_font.render(fig_name, True, (100, 200, 255))
                self.window.blit(ntxt, ntxt.get_rect(center=(cx, cy)))
        else:
            # Empty slot
            hovered = rect.collidepoint(mx, my_mouse)
            if hovered:
                glow = pygame.Surface((fsz + 6, fsz + 6), pygame.SRCALPHA)
                glow.fill((255, 255, 200, 35))
                self.window.blit(glow, (rect.x - 3, rect.y - 3))
            pygame.draw.rect(self.window, (30, 35, 40, 180), rect, border_radius=4)
            pygame.draw.rect(self.window, (80, 100, 130), rect, 1, border_radius=4)

        # Only show label when slot is empty
        if not is_selected:
            ntxt = self._res_font.render('Battle Fig', True, (130, 130, 130))
            self.window.blit(ntxt, ntxt.get_rect(centerx=cx, top=rect.bottom + 2))

        if is_selected:
            if self._advance_icon:
                ax = rect.right - self._advance_icon.get_width()
                ay = rect.y
                self.window.blit(self._advance_icon, (ax, ay))

            _xbs = self._x_btn_sz
            xrect = pygame.Rect(rect.right - _xbs - 2, rect.y + 2, _xbs, _xbs)
            x_hovered = xrect.collidepoint(mx, my_mouse)
            if rect.collidepoint(mx, my_mouse) or x_hovered:
                self._battle_figure_x_rect = xrect
                bg = (180, 60, 60) if x_hovered else (120, 40, 40)
                bdr = (220, 120, 120) if x_hovered else (160, 80, 80)
                tc = (255, 255, 255) if x_hovered else (200, 180, 180)
                pygame.draw.rect(self.window, bg, xrect, border_radius=3)
                pygame.draw.rect(self.window, bdr, xrect, 1, border_radius=3)
                xf = settings.get_font(max(int(_xbs * 1.3), 8), bold=True)
                xt = xf.render('\u00d7', True, tc)
                self.window.blit(xt, xt.get_rect(center=xrect.center))
            else:
                self._battle_figure_x_rect = None
        else:
            self._battle_figure_x_rect = None

    def _draw_auto_gamble(self):
        enabled = self._config.get('auto_gamble', False)
        threshold = self._get_auto_gamble_threshold()
        label = 'Auto-Gamble: ON' if enabled else 'Auto-Gamble: OFF'
        clr = (100, 220, 100) if enabled else (130, 130, 130)

        rect = self._btn_auto_gamble
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill((30, 30, 35, 200))
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, (70, 120, 70), rect, 1, border_radius=2)
        txt = self._small_font.render(label, True, clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))

        if (not self._btn_auto_gamble_dec or not self._btn_auto_gamble_inc
                or not self._auto_gamble_threshold_rect):
            return

        mx, my_mouse = pygame.mouse.get_pos()
        dec_rect = self._btn_auto_gamble_dec
        inc_rect = self._btn_auto_gamble_inc
        val_rect = self._auto_gamble_threshold_rect

        label_clr = (180, 180, 120) if enabled else (120, 120, 120)
        threshold_label = self._res_font.render('Below:', True, label_clr)
        label_x = dec_rect.x - threshold_label.get_width() - int(0.006 * _SW)
        self.window.blit(threshold_label, threshold_label.get_rect(
            left=label_x,
            centery=val_rect.centery,
        ))

        for btn_rect, symbol in ((dec_rect, '-'), (inc_rect, '+')):
            hovered = btn_rect.collidepoint(mx, my_mouse)
            bg = (65, 65, 72) if hovered else (45, 45, 52)
            border = (120, 120, 130) if hovered else (90, 90, 100)
            pygame.draw.rect(self.window, bg, btn_rect, border_radius=3)
            pygame.draw.rect(self.window, border, btn_rect, 1, border_radius=3)
            sym = self._value_font.render(symbol, True, (200, 200, 210))
            self.window.blit(sym, sym.get_rect(center=btn_rect.center))

        pygame.draw.rect(self.window, (35, 35, 40), val_rect, border_radius=3)
        pygame.draw.rect(self.window, (90, 90, 100), val_rect, 1, border_radius=3)
        val_txt = self._value_font.render(str(threshold), True, (210, 210, 210))
        self.window.blit(val_txt, val_txt.get_rect(center=val_rect.center))

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

    def _build_confirm_data(self):
        """Build confirmation data: message text, grouped cards, and after-message."""
        from game.components.cards.card_img import CardImg

        locked_cards = []
        consumed_if_lost_cards = []

        def add_card(target, suit, rank):
            if suit and rank:
                ci = CardImg(self.window, suit, rank)
                target.append(ci.front_img)

        # Figures — locked (use card_details from server config)
        for fig in self._config.get('figures', []):
            for cd in fig.get('card_details', []):
                add_card(locked_cards, cd.get('suit', ''), cd.get('rank', ''))

        # Battle moves — consumed only if the active defence loses.
        for mv in self._config.get('battle_moves', []):
            if mv.get('card_id'):
                add_card(consumed_if_lost_cards, mv.get('suit', ''), mv.get('rank', ''))

        # Modifiers / legacy spell cards — consumed only if the defence loses
        for cd in self._config.get('modifier_card_details') or []:
            add_card(consumed_if_lost_cards, cd.get('suit', ''), cd.get('rank', ''))
        for cd in self._config.get('spell_card_details') or []:
            add_card(consumed_if_lost_cards, cd.get('suit', ''), cd.get('rank', ''))

        # Prelude spell — consumed only if the active defence loses.
        prelude_details = self._config.get('prelude_spell_card_details') or []
        if prelude_details:
            for cd in prelude_details:
                add_card(consumed_if_lost_cards, cd.get('suit', ''), cd.get('rank', ''))

        # Counter spell — consumed only if the active defence loses.
        counter_details = self._config.get('counter_spell_card_details') or []
        if counter_details:
            for cd in counter_details:
                add_card(consumed_if_lost_cards, cd.get('suit', ''), cd.get('rank', ''))

        image_groups = []
        if consumed_if_lost_cards:
            image_groups.append({
                'key': 'consumed_if_lost',
                'title': 'Consumed if land falls',
                'description': 'These battle and spell cards are reserved now, but only removed if this defence loses.',
                'icon': 'remove',
                'badge_icon': 'remove',
                'items': consumed_if_lost_cards,
            })
        if locked_cards:
            image_groups.append({
                'key': 'locked',
                'title': 'Locked figure cards',
                'description': 'These figure cards stay in your deck, but cannot be used elsewhere while this defence is active.',
                'icon': 'lock',
                'badge_icon': 'lock',
                'items': locked_cards,
            })

        msg = 'Review the card costs before saving this defence.'
        if not image_groups:
            msg = 'No cards are used in this configuration.'

        after_msg = None
        if consumed_if_lost_cards or locked_cards:
            after_msg = 'Cards removed from the defence before saving are returned to your collection.'

        return msg, image_groups, after_msg

    def _on_save_click(self):
        """Handle click on Save Defence button."""
        if not self._is_defence_ready():
            problems = self._get_defence_problems()
            self._show_problem_dialogue('Cannot Save Defence', problems)
            return
        validation = self._server_validate_draft()
        if not validation.get('success'):
            self._show_problem_dialogue(
                'Cannot Save Defence',
                validation.get('problems') or [validation.get('message', 'Configuration is incomplete')],
            )
            return
        msg, image_groups, after_msg = self._build_confirm_data()
        self._pending_save_confirm = True
        self.dialogue_box = DialogueBox(
            self.window,
            msg,
            actions=['Confirm', 'Cancel'],
            title='Save Defence',
            image_groups=image_groups,
            message_after_images=after_msg,
        )

    def _get_config_fig(self, figure_id):
        for fig in self._config.get('figures', []):
            if fig['id'] == figure_id:
                return fig
        return None

    def _prelude_health_target_id(self):
        data = self._config.get('prelude_spell_data') or {}
        if isinstance(data, dict):
            return data.get('target_figure_id')
        return None

    def _has_health_boost_target(self, kind):
        if not self._config:
            return False
        if kind == 'prelude':
            return self._config.get('prelude_spell_name') != 'Health Boost' or bool(self._prelude_health_target_id())
        return self._config.get('counter_spell_name') != 'Health Boost' or bool(self._config.get('counter_spell_target_figure_id'))

    def _begin_spell_target_selection(self, kind):
        if kind not in ('prelude', 'counter'):
            return
        if not self._config or not self._config.get('figures'):
            self.state.set_msg('Build a figure before choosing a Health Boost target')
            return
        self._selecting_battle_fig = False
        self._selecting_spell_target = kind

    def _maybe_prompt_missing_spell_target(self):
        if not self._config or self._selecting_spell_target:
            return
        if self._config.get('prelude_spell_name') == 'Health Boost' and not self._prelude_health_target_id():
            self._begin_spell_target_selection('prelude')
            return
        if self._config.get('counter_spell_name') == 'Health Boost' and not self._config.get('counter_spell_target_figure_id'):
            self._begin_spell_target_selection('counter')

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

    # ── Helpers ─────────────────────────────────────────────────────

    def _figure_name(self, figure_id):
        for fig in self._config.get('figures', []):
            if fig['id'] == figure_id:
                return fig.get('name', fig.get('family_name', '?'))
        return '?'

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
        self._game_proxy = KingdomGameProxy(self._config, self._land_id, mode='defence')
        self.state.game = self._game_proxy
        sx, sy = self._config_subscreen_origin()
        self._subscreen_obj = BuildFigureScreen(
            self.window, self.state,
            x=sx, y=sy,
            title='Figure Builder', card_source=card_source, mode='defence_draft',
        )
        self._subscreen_obj._on_done = self._close_subscreen
        self._active_subscreen = 'build_figure'

    def _open_battle_shop(self):
        """Open BattleShopScreen as a subscreen."""
        card_source = self._build_card_source()
        if not card_source:
            self._error = 'Failed to load collection'
            return
        self._game_proxy = KingdomGameProxy(self._config, self._land_id, mode='defence')
        self.state.game = self._game_proxy
        sx, sy = self._config_subscreen_origin()
        self._subscreen_obj = BattleShopScreen(
            self.window, self.state,
            x=sx, y=sy,
            title='Battle Shop', card_source=card_source, mode='defence_draft',
        )
        self._subscreen_obj._on_done = self._close_subscreen
        self._active_subscreen = 'battle_shop'

    # ── Spell selection helpers ────────────────────────────────────

    def _open_prelude_spell_screen(self):
        """Open PreludeSpellScreen as a subscreen for defence prelude."""
        card_source = self._build_card_source()
        if not card_source:
            self._error = 'Failed to load collection'
            return
        self._game_proxy = KingdomGameProxy(self._config, self._land_id, mode='defence')
        self.state.game = self._game_proxy
        sx, sy = self._config_subscreen_origin()
        self._subscreen_obj = PreludeSpellScreen(
            self.window, self.state,
            x=sx, y=sy,
            title='Prelude Spell', card_source=card_source, mode='defence',
            allowed_spells=_DEFENCE_PRELUDE_SPELLS,
            server_endpoint='/kingdom/defence/draft/set_prelude_spell',
            land_id=self._land_id,
        )
        self._subscreen_obj._on_done = self._close_subscreen
        self._active_subscreen = 'prelude_spell'

    def _open_counter_spell_screen(self):
        """Open PreludeSpellScreen as a subscreen for defence counter spell."""
        # Counter spell and battle figure are mutually exclusive.  Defer
        # the clear to the server-side endpoint via ``clear_battle_figure``
        # so it happens atomically with the counter-spell set.
        had_battle_figure = bool(
            self._config.get('battle_figure_id') or self._config.get('battle_figure_id_2')
        )
        card_source = self._build_card_source()
        if not card_source:
            self._error = 'Failed to load collection'
            return
        self._game_proxy = KingdomGameProxy(self._config, self._land_id, mode='defence')
        self.state.game = self._game_proxy
        sx, sy = self._config_subscreen_origin()
        self._subscreen_obj = PreludeSpellScreen(
            self.window, self.state,
            x=sx, y=sy,
            title='Counter Spell', card_source=card_source, mode='defence',
            allowed_spells=_DEFENCE_COUNTER_SPELLS,
            server_endpoint='/kingdom/defence/draft/set_counter_spell',
            land_id=self._land_id,
            extra_payload={'clear_battle_figure': True} if had_battle_figure else None,
        )
        self._subscreen_obj._on_done = self._close_subscreen
        self._active_subscreen = 'counter_spell'

    def _close_subscreen(self):
        """Dismiss the active subscreen and sync config."""
        if self._game_proxy:
            self._apply_config(self._game_proxy._config)
        self._active_subscreen = None
        self._subscreen_obj = None
        self._game_proxy = None
        # Refresh config from server to get authoritative state
        self._load_config()

    def _leave_screen(self):
        """Go back to kingdom without deleting the saved active defence."""
        self._pending_nav = 'kingdom'
        self._complete_pending_navigation()

    def _has_unsaved_changes(self):
        """True if the open defence draft differs from the saved active config."""
        if not self._config:
            return False
        return bool(self._draft_dirty or self._config.get('draft_dirty'))

    def _try_leave_screen(self):
        """Prompt if the draft is dirty; otherwise leave immediately."""
        if not self._pending_nav:
            self._pending_nav = 'kingdom'
        if not self._has_unsaved_changes():
            self._complete_pending_navigation()
            return
        self._pending_leave_confirm = True
        self.dialogue_box = DialogueBox(
            self.window,
            'You have unsaved defence changes.\n'
            'Save them, discard only this draft, or stay here.',
            actions=['Save & Leave', 'Discard Changes', 'Stay'],
            title='Unsaved Defence Changes',
        )

    # ── Readiness check ─────────────────────────────────────────────

    def _is_defence_ready(self):
        """True when the defence configuration is complete enough."""
        if not self._config:
            return False
        figures = self._config.get('figures', [])
        moves = self._config.get('battle_moves', [])

        prelude = self._config.get('prelude_spell_name')
        village_only = prelude in ('Peasant War', 'Civil War')

        has_valid_figure = any(
            not f.get('has_deficit', False)
            and (not village_only or f.get('field') == 'village')
            for f in figures
        )
        has_moves = len(moves) == 3

        # Defence requires exactly one counter strategy:
        # battle figure XOR counter spell.
        has_battle_fig = self._config.get('battle_figure_id') is not None
        has_counter_spell = self._config.get('counter_spell_name') is not None
        has_exactly_one_strategy = (has_battle_fig != has_counter_spell)
        has_required_spell_targets = (
            self._has_health_boost_target('prelude')
            and self._has_health_boost_target('counter')
        )
        return has_valid_figure and has_moves and has_exactly_one_strategy and has_required_spell_targets

    def _get_defence_problems(self):
        """Return a list of human-readable problems preventing save."""
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
            can_fight = [f for f in figures if not f.get('has_deficit', False)]
            if not can_fight:
                problems.append('All figures have a resource deficit.')
            elif village_only:
                village_fighters = [f for f in can_fight if f.get('field') == 'village']
                if not village_fighters:
                    problems.append(
                        f'{prelude} is selected \u2014 only village figures can fight, '
                        'but none of your village figures are available.'
                    )

        if len(moves) < 3:
            missing = 3 - len(moves)
            problems.append(f'{missing} battle move{"s" if missing > 1 else ""} still missing (need 3).')

        has_battle_fig = self._config.get('battle_figure_id') is not None
        has_counter_spell = self._config.get('counter_spell_name') is not None

        if has_battle_fig and has_counter_spell:
            problems.append('Select exactly one strategy: battle figure or counter spell (not both).')
        elif not has_battle_fig and not has_counter_spell:
            problems.append('Select exactly one strategy: battle figure or counter spell.')

        if prelude == 'Health Boost' and not self._prelude_health_target_id():
            problems.append('Health Boost prelude needs one of your figures as target.')
        if self._config.get('counter_spell_name') == 'Health Boost' and not self._config.get('counter_spell_target_figure_id'):
            problems.append('Health Boost counter spell needs one of your figures as target.')

        return problems

    # ── Prelude spell cycling (auto-defender) ─────────────────────

    def _cycle_prelude_spell(self):
        """Cycle through prelude spells for auto-defender."""
        current = self._config.get('prelude_spell_name')
        spells = list(_DEFENCE_PRELUDE_SPELLS)
        if not current:
            for s in spells:
                if self._has_cards_for(s):
                    self._server_set_prelude_spell(s)
                    return
        else:
            try:
                idx = spells.index(current)
            except ValueError:
                idx = -1
            # Try next spells
            for i in range(1, len(spells) + 1):
                next_idx = idx + i
                if next_idx >= len(spells):
                    self._server_clear_prelude_spell()
                    return
                if self._has_cards_for(spells[next_idx]):
                    self._server_clear_prelude_spell()
                    self._server_set_prelude_spell(spells[next_idx])
                    return
            self._server_clear_prelude_spell()

    # ── Counter spell cycling (auto-defender) ──────────────────────

    def _cycle_counter_spell(self):
        """Cycle through counter spells for auto-defender."""
        current = self._config.get('counter_spell_name')
        spells = list(_DEFENCE_COUNTER_SPELLS)
        if not current:
            for s in spells:
                if self._has_cards_for(s):
                    # Clear battle figure first (mutually exclusive)
                    if self._config.get('battle_figure_id'):
                        self._server_clear_battle_figure()
                    self._server_set_counter_spell(s)
                    return
        else:
            try:
                idx = spells.index(current)
            except ValueError:
                idx = -1
            for i in range(1, len(spells) + 1):
                next_idx = idx + i
                if next_idx >= len(spells):
                    self._server_clear_counter_spell()
                    return
                if self._has_cards_for(spells[next_idx]):
                    self._server_clear_counter_spell()
                    self._server_set_counter_spell(spells[next_idx])
                    return
            self._server_clear_counter_spell()

    # ── Update / events ─────────────────────────────────────────────

    def _handle_icon_events(self, event):
        """Guard shared menu icons so they cannot bypass draft handling."""
        if hasattr(self, '_logout_dialogue') and self._logout_dialogue:
            return MenuScreenMixin._handle_icon_events(self, event)
        if event.type == pygame.MOUSEBUTTONUP:
            if self._icon_settings.collide():
                self._pending_nav = 'settings'
                self._try_leave_screen()
                return True
            if self._icon_home.collide():
                self._pending_nav = 'game_menu'
                self._try_leave_screen()
                return True
            if self._icon_logout.collide():
                self._pending_nav = 'logout'
                self._try_leave_screen()
                return True
        return False

    def update(self, events):
        super().update()
        self._update_icon_buttons()

        # If subscreen is active, delegate
        if self._active_subscreen and self._subscreen_obj:
            self._subscreen_obj.update(self._game_proxy)
            return

        target_land = getattr(self.state, 'defence_land_id', None)
        if target_land and target_land != self._land_id:
            self._land_id = target_land
            self._config = None
            self._land = None
            self._loading = False
            self._error = None

        if self._land_id and not self._config and not self._loading and not self._error:
            self._load_config()

        # Update figure icon hover states
        for icon in self._figure_icons.values():
            icon.update()

    def handle_events(self, events):
        super().handle_events(events)

        # Handle save / prelude / counter spell confirmation dialogue responses
        response = self.state.action.get('status')
        if response and self._pending_save_confirm:
            self._pending_save_confirm = False
            self.reset_action()
            if response == 'confirm':
                self._pending_nav = self._pending_nav or 'kingdom'
                if self._server_save_draft():
                    self._complete_pending_navigation()
            return
        if response and self._pending_leave_confirm:
            self._pending_leave_confirm = False
            self.reset_action()
            if response == 'save & leave':
                if self._server_save_draft():
                    self._complete_pending_navigation()
            elif response == 'discard changes':
                if self._server_discard_draft():
                    self._complete_pending_navigation()
            else:
                self._pending_nav = None
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
        if response and self._pending_counter_spell:
            self._pending_counter_spell = None
            self.reset_action()
            return
        if response and self._pending_counter_clear:
            self._pending_counter_clear = False
            self.reset_action()
            if response == 'confirm':
                self._server_clear_counter_spell()
            return
        if response in ('ok', 'cancel'):
            self._pending_prelude_spell = None
            self._pending_prelude_clear = False
            self._pending_counter_spell = None
            self._pending_counter_clear = False
            self._pending_save_confirm = False
            self._pending_leave_confirm = False
            self._pending_nav = None
            self._selecting_spell_target = None
            self.reset_action()
            return

        if self.dialogue_box:
            return

        # If subscreen is active, delegate events
        if self._active_subscreen and self._subscreen_obj:
            self._subscreen_obj.handle_events(events)
            _ss_rect = self._config_subscreen_rect()
            for event in events:
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

        # Health Boost target selection mode — click an own figure target
        if self._selecting_spell_target:
            for event in events:
                if event.type == MOUSEBUTTONUP and event.button == 1:
                    for icon in self._figure_icons.values():
                        if icon.hovered:
                            fig = icon.figure
                            cfg_fig = self._get_config_fig(fig.id)
                            if cfg_fig:
                                if self._selecting_spell_target == 'prelude':
                                    self._server_set_prelude_spell('Health Boost', target_figure_id=fig.id)
                                else:
                                    if self._config.get('battle_figure_id'):
                                        self._server_clear_battle_figure()
                                    self._server_set_counter_spell('Health Boost', target_figure_id=fig.id)
                                self._selecting_spell_target = None
                            else:
                                self.state.set_msg('Could not select that figure')
                            return
                    self._selecting_spell_target = None
                    return
                if event.type == KEYDOWN and event.key == K_ESCAPE:
                    self._selecting_spell_target = None
                    return
            return

        # Battle figure selection mode — click a figure to select it
        if self._selecting_battle_fig:
            for event in events:
                if event.type == MOUSEBUTTONUP and event.button == 1:
                    # Check if a figure icon was clicked
                    selected = False
                    for icon in self._figure_icons.values():
                        if icon.hovered:
                            fig = icon.figure
                            cfg_fig = self._get_config_fig(fig.id)
                            if cfg_fig and not cfg_fig.get('has_deficit', False):
                                self._server_set_battle_figure(fig.id)
                                selected = True
                            else:
                                self.state.set_msg('Cannot select a figure in deficit')
                                selected = True
                            break
                    self._selecting_battle_fig = False
                    return
                if event.type == KEYDOWN and event.key == K_ESCAPE:
                    self._selecting_battle_fig = False
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

                if self._battle_figure_x_rect and self._battle_figure_x_rect.collidepoint(pos):
                    self._server_clear_battle_figure()
                    continue

                if self._counter_x_rect and self._counter_x_rect.collidepoint(pos):
                    current_spell = self._config.get('counter_spell_name')
                    if current_spell:
                        self._pending_counter_clear = True
                        self.dialogue_box = DialogueBox(
                            self.window,
                            f'Remove {current_spell} counter spell?',
                            actions=['Confirm', 'Cancel'],
                            title='Clear Counter Spell',
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

                # Prelude spell: edit button opens spell picker; Health Boost slot picks target
                if self._btn_prelude_edit and self._btn_prelude_edit.collidepoint(pos):
                    self._open_prelude_spell_screen()
                    continue
                if self._prelude_spell_rect and self._prelude_spell_rect.collidepoint(pos):
                    if self._config.get('prelude_spell_name') == 'Health Boost':
                        self._begin_spell_target_selection('prelude')
                    else:
                        self._open_prelude_spell_screen()
                    continue

                # Counter action: battle figure slot click
                if self._battle_figure_rect and self._battle_figure_rect.collidepoint(pos):
                    if not self._config.get('battle_figure_id'):
                        figs = self._config.get('figures', [])
                        valid = [f for f in figs if not f.get('has_deficit', False)]
                        if valid:
                            # Clear counter spell first (mutually exclusive)
                            if self._config.get('counter_spell_name'):
                                self._server_clear_counter_spell()
                            self._selecting_battle_fig = True
                        else:
                            self.state.set_msg('No valid figures available')
                    continue

                # Counter action: edit button opens picker; Health Boost slot picks target
                if self._btn_counter_edit and self._btn_counter_edit.collidepoint(pos):
                    self._open_counter_spell_screen()
                    continue
                if self._counter_spell_rect and self._counter_spell_rect.collidepoint(pos):
                    if self._config.get('counter_spell_name') == 'Health Boost':
                        self._begin_spell_target_selection('counter')
                    else:
                        self._open_counter_spell_screen()
                    continue

                # Threshold controls first so they keep working even if layout
                # changes make them overlap with the auto-gamble toggle rect.
                if self._btn_auto_gamble_dec and self._btn_auto_gamble_dec.collidepoint(pos):
                    current = self._get_auto_gamble_threshold()
                    target = max(_AUTO_GAMBLE_THRESHOLD_MIN, current - 1)
                    if target != current:
                        self._config['auto_gamble_threshold'] = target
                    if not self._server_set_auto_gamble_threshold(target):
                        self._config['auto_gamble_threshold'] = current
                    continue

                if self._btn_auto_gamble_inc and self._btn_auto_gamble_inc.collidepoint(pos):
                    current = self._get_auto_gamble_threshold()
                    target = min(_AUTO_GAMBLE_THRESHOLD_MAX, current + 1)
                    if target != current:
                        self._config['auto_gamble_threshold'] = target
                    if not self._server_set_auto_gamble_threshold(target):
                        self._config['auto_gamble_threshold'] = current
                    continue

                # Auto-gamble toggle
                if self._btn_auto_gamble and self._btn_auto_gamble.collidepoint(pos):
                    current = self._config.get('auto_gamble', False)
                    self._server_set_auto_gamble(not current)
                    continue

                # Save Defence button
                if self._btn_save and self._btn_save.collidepoint(pos):
                    self._on_save_click()
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
