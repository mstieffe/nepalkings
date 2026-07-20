# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Defence screen — configure figures, battle moves, spells & gamble for defending a land."""

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
from game.core.game import battle_required_field
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
from game.components.figures.figure_manager import FigureManager
from game.components.battle_moves.battle_move_manager import BattleMoveManager
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.components.battle_moves.battle_move_detail_box import BattleMoveDetailBox
from game.components.spells.spell_manager import SpellManager
from game.components.dialogue_box import DialogueBox
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
from game.components.loading_indicator import draw_loading_indicator
from config import settings
from utils import http_compat as requests
from utils import sound
from utils.background_poller import BackgroundPoller
from utils import collection_service
import logging

logger = logging.getLogger('nk.screens.defence')

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
        hide_checkmate=False,
        hide_instant_charge=True,
    )


def _display_family_without_duel_only_skills(family):
    return filter_family_for_display(
        family,
        hide_checkmate=False,
        hide_instant_charge=True,
    )


_DEFENCE_PRELUDE_SPELLS = [
    'Draw 2 MainCards', 'Draw 4 MainCards', 'Dump Cards', 'Forced Deal',
    'Poison', 'Health Boost', 'All Seeing Eye', 'Explosion', 'Copy Figure',
    'Peasant War', 'Civil War', 'Royal Decree', 'Landslide',
]

_DEFENCE_COUNTER_SPELLS = [
    'Draw 2 MainCards', 'Draw 4 MainCards', 'Dump Cards', 'Forced Deal',
    'Poison', 'Health Boost', 'Copy Figure', 'Landslide',
]

_DEFENCE_COUNTER_DESCRIPTION_OVERRIDES = {
    'Copy Figure': (
        'When an enemy figure advances, automatically copy one random '
        'targetable enemy figure. Its full-power clone joins your defence '
        'for this battle and is never a Checkmate figure.'
    ),
}

_RED_SUITS = {'Hearts', 'Diamonds'}
_BLACK_SUITS = {'Clubs', 'Spades'}
_CALL_FIELD_MAP = {
    'Call Villager': 'village',
    'Call Military': 'military',
    'Call King': 'castle',
}

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
    'auto_gamble': {
        'title': 'Auto-Gamble',
        'message': (
            'Your defence fights automatically when attacked. With Auto-Gamble ON, '
            'the defender redraws (gambles) any battle move whose power is below the '
            'threshold before playing it — a chance at a stronger card, at the risk of a weaker one.'
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
        self._loading_started_at_ms = 0
        self._loading_message = 'Loading defence config...'
        self._error = None
        self._config_poller = None
        self._config_poller_land_id = None

        # ── Victory Review mode (post-conquer one-shot edit) ────────
        # Set when the player is routed here right after a successful
        # conquer.  Swaps title + Save chrome and adds a Clear All button
        # plus a non-destructive Skip-for-now exit.
        self._victory_review_mode = False
        self._victory_review_game_id = None
        self._btn_clear_all = None
        self._btn_skip = None
        self._pending_clear_all_confirm = False
        self._pending_victory_ack = False

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
        self._tiny_font = settings.get_font(settings.FS_TINY)
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
        self._btn_retry = None            # "Retry" button rect (error state only)
        self._res_rect = None
        self._field_title_pos = None
        self._moves_title_pos = None
        self._prelude_spell_rect = None   # Rect for prelude spell icon slot
        self._prelude_x_rect = None       # Rect for prelude X remove button
        self._counter_spell_rect = None   # Rect for counter spell icon slot
        self._counter_x_rect = None       # Rect for counter X remove button
        self._battle_figure_rect = None   # Rect for battle figure icon slot
        self._battle_figure_rect_2 = None # Rect for Civil War second battle figure slot
        self._battle_figure_x_rect = None # Rect for battle figure X remove button
        self._battle_figure_x_rect_2 = None
        self._info_button_rects = {}
        self._active_info_key = None
        self._active_info_popup_rect = None
        self._layout_built = False
        self._hovered_slot = -1
        self._pending_tooltip = None      # (anchor_rect, text) for edit-icon hover
        self._loot_risk_tutorial_dialogue = None
        self._loot_risk_tutorial_action = None
        self._pending_leave_confirm = False
        self._pending_nav = None
        self._draft_dirty = False
        self._collection_cards = None
        self._selecting_battle_fig = False  # True when prompting user to pick a figure
        self._pending_civil_war_battle_fig_1 = None
        self._selecting_spell_target = None  # 'prelude' or 'counter' while choosing Health Boost target
        # Only prompt for a missing Health Boost target right after the
        # player picked the spell — never when the screen merely (re)loads.
        self._prompt_spell_target_on_next_load = False

        # ── Figure display (eagerly loaded) ─────────────────────────
        self._figure_manager = FigureManager()
        self._move_manager = BattleMoveManager()
        self._figure_objects = []
        self._figure_icons = {}
        self._figure_detail_box = None
        self._move_detail_box = None
        self._move_remove_rects = {}   # round_index → Rect for X buttons
        self._empty_move_slot_rects = {}  # round_index → Rect for empty slots

        # ── Slot caches for draw_battle_move_icon ───────────────────
        self._slot_glow_cache = {}
        self._slot_icon_cache = {}
        self._slot_frame_cache = {}
        self._suit_icon_cache = {}
        self._slot_diamond = None
        self._field_slot_icon_raw = {}
        self._field_slot_icon_cache = {}
        self._init_move_slot_caches()

        # ── Spell icons (framed, from SpellManager) ─────────────────
        self._spell_icons = {}   # spell_name → icon dict (all prelude + counter spells)
        self._spell_manager = SpellManager()
        self._init_spell_icons()

        # ── Resource icons ──────────────────────────────────────────
        self._resource_icons = {}
        self._init_resource_icons()

        # ── Edit icon (for section title buttons) ───────────────────
        _icon_sz = max(int(0.025 * _SH), settings.TOUCH_ICON_MIN)
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
        self._loading_started_at_ms = 0
        self._loading_message = 'Loading defence config...'
        self._error = None
        self._config_poller = None
        self._config_poller_land_id = None
        self._active_subscreen = None
        self._subscreen_obj = None
        self._game_proxy = None
        self._figure_objects = []
        self._figure_icons = {}
        self._figure_detail_box = None
        self._layout_built = False
        self._hovered_slot = -1
        self._selecting_spell_target = None
        self._prompt_spell_target_on_next_load = False
        self._btn_retry = None
        self._pending_tooltip = None
        self._active_info_key = None
        self._active_info_popup_rect = None
        self._loot_risk_tutorial_dialogue = None
        self._loot_risk_tutorial_action = None
        self._pending_leave_confirm = False
        self._pending_nav = None
        self._draft_dirty = False
        # Pick up Victory Review handoff from battle_screen.  State field is
        # consumed (cleared) so re-entering defence later does not re-trigger.
        review_gid = getattr(self.state, 'victory_review_game_id', None)
        if review_gid:
            self._victory_review_mode = True
            self._victory_review_game_id = review_gid
            self.state.victory_review_game_id = None
        else:
            self._victory_review_mode = False
            self._victory_review_game_id = None
        self._btn_clear_all = None
        self._btn_skip = None
        self._pending_clear_all_confirm = False
        self._pending_victory_ack = False

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
        if settings.TOUCH_TARGET_MIN > 0:
            self._x_btn_sz = max(self._x_btn_sz, int(0.045 * _SH))

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

        # Right column: battle plan, prelude spell, defender response.
        right_x = _BOX_X + pad + 3 * (field_w + pad)
        self._right_x = right_x
        right_right = _BOX_X + _BOX_W - _BOX_PAD
        right_w = right_right - right_x
        panel_gap = int(0.014 * _SH)
        panel_pad = int(0.010 * _SW)
        panel_pad_y = int(0.010 * _SH)
        mobile_ui = settings.TOUCH_TARGET_MIN > 0
        if mobile_ui:
            panel_pad_y = max(1, int(0.004 * _SH))
        sw = self._move_slot_size
        slot_row_w = int(sw * 2.0) * 2 + int(sw * 1.3)
        slot_row_h = int(sw * 1.45)
        if mobile_ui:
            header_h = (
                max(self._label_font.get_height(), self._small_font.get_height())
                + max(8, int(0.020 * _SH))
            )
        else:
            header_h = self._label_font.get_height() + self._res_font.get_height() + int(0.015 * _SH)
        ag_btn_h = (
            max(settings.TOUCH_COMPACT_MIN, int(0.050 * _SH))
            if mobile_ui else int(0.035 * _SH)
        )
        battle_controls_gap = int(0.018 * _SH)
        battle_header_h = header_h
        if mobile_ui:
            # The Auto controls share the Battle Plan header on phones.  Size
            # the slot offset from the actual control height (plus the
            # header's top inset), not only the text height, so larger mobile
            # fonts cannot make the controls touch the first round slot.
            battle_header_h = max(
                header_h,
                int(0.010 * _SH) + ag_btn_h
                + max(2, int(0.004 * _SH)),
            )
        fsz = self._mod_frame_size

        # Save Defence / Confirm Defence button (bottom-right of box).
        # In Victory Review mode the label is longer and we add two sibling
        # buttons to its left: "Clear All" (destructive) and "Skip for now"
        # (non-destructive exit that preserves the partial draft).
        save_w = int(0.20 * _SW) if self._victory_review_mode else int(0.20 * _SW)
        save_h = max(int(0.055 * _SH), settings.TOUCH_TARGET_MIN)
        self._btn_save = pygame.Rect(
            _BOX_X + _BOX_W - _BOX_PAD - save_w,
            _BOX_BOTTOM - _BOX_PAD - save_h,
            save_w, save_h,
        )

        if self._victory_review_mode:
            clear_w = int(0.14 * _SW)
            skip_w = int(0.16 * _SW)
            sibling_gap = int(0.012 * _SW)
            # Never let sibling buttons intrude on the left field column.
            min_sibling_x = _BOX_X + _BOX_PAD + int(0.018 * _SW)

            clear_x = self._btn_save.x - sibling_gap - clear_w
            skip_x = clear_x - sibling_gap - skip_w
            if skip_x < min_sibling_x:
                # Compress the two sibling widths proportionally so they still
                # fit between the left column and the Confirm button.
                available = self._btn_save.x - sibling_gap - min_sibling_x - sibling_gap
                if available > 0:
                    skip_w = max(int(0.10 * _SW), available // 2)
                    clear_w = max(int(0.10 * _SW), available - skip_w)
                skip_x = min_sibling_x
                clear_x = skip_x + skip_w + sibling_gap

            self._btn_skip = pygame.Rect(
                skip_x,
                self._btn_save.y,
                skip_w,
                save_h,
            )
            self._btn_clear_all = pygame.Rect(
                clear_x,
                self._btn_save.y,
                clear_w,
                save_h,
            )
        else:
            self._btn_clear_all = None
            self._btn_skip = None

        right_content_bottom = self._btn_save.y - panel_gap
        right_content_h = max(1, right_content_bottom - content_top)
        available_panel_h = max(1, right_content_h - 2 * panel_gap)
        battle_plan_min_h = battle_header_h + slot_row_h + panel_pad_y
        if not mobile_ui:
            battle_plan_min_h += battle_controls_gap + ag_btn_h
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
            self._battle_plan_rect.y + battle_header_h,
            slot_row_w,
            slot_row_h,
        )

        # Auto-gamble controls. On mobile, keep them in the Battle Plan
        # header so they no longer sit on top of the round slots.
        ag_ctrl_gap = max(3, int(0.004 * _SW))
        if mobile_ui:
            ag_ctrl_gap = max(2, int(0.002 * _SW))
            agw = max(int(0.052 * _SW), self._small_font.size('Auto')[0] + 8)
            ag_ctrl_w = max(int(0.050 * _SH), 24)
            val_w = max(int(0.030 * _SW), self._value_font.size('20')[0] + 8)
            total_w = agw + ag_ctrl_w * 2 + val_w + ag_ctrl_gap * 3
            info_rect = self._info_button_rects.get('battle_plan')
            right_limit = (info_rect.left - int(0.010 * _SW)) if info_rect else (self._battle_plan_rect.right - panel_pad)
            ag_x = right_limit - total_w
            min_x = self._btn_buy_move.right + ag_ctrl_gap
            if ag_x < min_x and min_x + total_w <= right_limit:
                ag_x = min_x
            if ag_x + total_w > right_limit:
                ag_x = max(self._battle_plan_rect.x + panel_pad,
                           right_limit - total_w)
            ag_y = self._moves_title_pos[1]
        else:
            agw = int(0.12 * _SW)
            ag_y = min(
                self._move_slots_rect.bottom + battle_controls_gap,
                self._battle_plan_rect.bottom - panel_pad_y - ag_btn_h,
            )
            ag_x = self._battle_plan_rect.x + panel_pad
            ag_ctrl_w = int(0.024 * _SW)
            val_w = int(0.04 * _SW)
        self._btn_auto_gamble = pygame.Rect(ag_x, ag_y, agw, ag_btn_h)

        if mobile_ui:
            ag_ctrl_x = self._btn_auto_gamble.right + ag_ctrl_gap
            ag_ctrl_y = ag_y
            self._btn_auto_gamble_dec = pygame.Rect(ag_ctrl_x, ag_ctrl_y, ag_ctrl_w, ag_btn_h)
            self._auto_gamble_threshold_rect = pygame.Rect(
                self._btn_auto_gamble_dec.right + ag_ctrl_gap,
                ag_ctrl_y,
                val_w,
                ag_btn_h,
            )
            self._btn_auto_gamble_inc = pygame.Rect(
                self._auto_gamble_threshold_rect.right + ag_ctrl_gap,
                ag_ctrl_y,
                ag_ctrl_w,
                ag_btn_h,
            )
        else:
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

        # Auto-gamble "(i)" — desktop only; the mobile header row is packed
        # right up against the Battle Plan info button already.
        if not mobile_ui:
            ag_info_size = max(int(0.022 * _SH), 18, settings.TOUCH_ICON_MIN)
            ag_info_x = self._btn_auto_gamble_inc.right + int(0.010 * _SW)
            ag_info_y = ag_ctrl_y + (ag_btn_h - ag_info_size) // 2
            if ag_info_x + ag_info_size <= self._battle_plan_rect.right - panel_pad:
                self._info_button_rects['auto_gamble'] = pygame.Rect(
                    ag_info_x, ag_info_y, ag_info_size, ag_info_size)

        if mobile_ui:
            min_slot_y = self._btn_auto_gamble.bottom + max(2, int(0.004 * _SH))
            max_slot_y = self._battle_plan_rect.bottom - panel_pad_y - slot_row_h
            if self._move_slots_rect.y < min_slot_y and max_slot_y >= min_slot_y:
                self._move_slots_rect.y = min_slot_y

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

        # ── Defender Response panel (battle figure OR counter spell + edit button) ──
        counter_header_y = self._counter_panel_rect.y + int(0.010 * _SH)
        self._final_section_y = self._counter_panel_rect.y + header_h
        final_x = self._counter_panel_rect.x + panel_pad
        # Battle figure slot
        self._battle_figure_rect = pygame.Rect(final_x, self._final_section_y, fsz, fsz)
        cw_gap = max(4, int(0.006 * _SW))
        self._battle_figure_rect_2 = pygame.Rect(
            self._battle_figure_rect.right + cw_gap,
            self._final_section_y,
            fsz,
            fsz,
        )
        # Counter spell slot (to the right of battle figure with separator gap)
        spell_gap = min(
            fsz + int(0.11 * _SW),
            self._counter_panel_rect.right - final_x - fsz,
        )
        self._counter_spell_rect = pygame.Rect(final_x + spell_gap, self._final_section_y, fsz, fsz)
        # Edit icon next to "Defender Response" label
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

        # ── Divider positions (computed from layout) ────────────────
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

    def _apply_config(self, config):
        self._config = config
        self._draft_dirty = bool((config or {}).get('draft_dirty', True))
        if (not config or not self._civil_war_battle_strategy()
                or config.get('battle_figure_id_2')):
            self._pending_civil_war_battle_fig_1 = None

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
            return {'error': err.get('message', err.get('error', 'Failed to load defence config'))}
        config_data = cls._response_json(config_resp)
        result = {
            'config_data': config_data,
            'collection_data': config_data.get('collection') or {},
        }
        collection_resp = (responses or {}).get('collection')
        if (not result['collection_data'] and collection_resp is not None
                and getattr(collection_resp, 'status_code', 0) == 200):
            result['collection_data'] = cls._response_json(collection_resp)
        return result

    def _fetch_config_bundle(self, land_id):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/draft/open',
                json={'land_id': land_id},
                timeout=15,
            )
            if resp.status_code != 200:
                err = self._response_json(resp)
                return {'error': err.get('message', err.get('error', 'Failed to load defence config'))}
            config_data = resp.json()
            collection_data = config_data.get('collection') or {}
            if not collection_data:
                try:
                    collection_data = collection_service.fetch_collection_cards()
                except Exception as e:
                    logger.error(f'Collection fetch error: {e}')
            return {
                'config_data': config_data,
                'collection_data': collection_data,
            }
        except Exception as e:
            logger.error(f'Defence config load error: {e}')
            return {'error': 'Connection error'}

    def _start_config_load(self):
        if not self._land_id:
            return
        if self._config_poller is None:
            base = settings.SERVER_URL
            self._config_poller = BackgroundPoller(
                self._fetch_config_bundle,
                async_requests=[
                    {'key': 'config', 'method': 'POST_JSON',
                     'url': f'{base}/kingdom/defence/draft/open',
                     'json': {'land_id': 0}},
                ],
                async_transform=self._transform_config_bundle_async,
            )
        if self._config_poller.busy:
            return
        self._loading = True
        self._loading_started_at_ms = pygame.time.get_ticks()
        self._loading_message = 'Fetching defence config...'
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
        self._loading_message = 'Building defence figures...'
        self._apply_config(data.get('config'))
        self._land = data.get('land')
        self._collection_cards = (result.get('collection_data') or {}).get('cards', [])
        self._rebuild_figure_objects()
        if self._prompt_spell_target_on_next_load:
            self._prompt_spell_target_on_next_load = False
            self._maybe_prompt_missing_spell_target()
        self._loading = False
        logger.debug(f'Defence config loaded for land {self._land_id}')

    def _load_config(self):
        self._loading = True
        self._loading_started_at_ms = pygame.time.get_ticks()
        self._loading_message = 'Fetching defence config...'
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
            collection_data = data.get('collection') or {}
            self._collection_cards = collection_data.get('cards', [])
            self._loading = False
            self._rebuild_figure_objects()
            if not collection_data:
                self._refresh_collection()
            if self._prompt_spell_target_on_next_load:
                self._prompt_spell_target_on_next_load = False
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
                self._apply_onboarding_payload(data)
                self._apply_config(data.get('config'))
                self._land = data.get('land', self._land)
                self._rebuild_figure_objects()
                self._refresh_collection()
                self.state.set_msg('Defence saved')
                sound.play('defence_set')
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
        open_dialogue(self, msg, ['OK'], title)

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
        if self._pending_victory_ack:
            self._pending_victory_ack = False
            game = getattr(self.state, 'game', None)
            if game is not None:
                game._conquer_battle_ended = False
                self.state.game = None
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
                sound.play('card_slide')
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
                sound.play('card_slide')
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
                sound.play('card_slide')
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
                sound.play('figure_place', volume=0.8)
            else:
                msg = data.get('message') or 'Could not select battle figure'
                self.state.set_msg(msg)
                logger.warning(f'Set battle figure failed: {msg}')
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
                sound.play('card_slide')
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
                sound.play('card_slide')
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
            checkmate=cfg_fig.get('checkmate', False),
            override_base_power=getattr(matched, 'override_base_power', None) if matched else None,
        )
        return filter_figure_for_display(
            figure,
            hide_checkmate=False,
            hide_instant_charge=True,
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
        if self._victory_review_mode:
            title = 'Victory! Review your new defence'
            title_color = (235, 215, 145)  # warm gold
        else:
            title = 'Defence Setup'
            title_color = (100, 200, 255)
        # Constrain the title width so it never spills past the box on small
        # screens (the Victory Review label is noticeably longer).
        title_max_w = _BOX_W - 2 * _BOX_PAD
        t_surf = self._title_font.render(title, True, title_color)
        if t_surf.get_width() > title_max_w:
            scale = title_max_w / max(1, t_surf.get_width())
            new_h = max(1, int(t_surf.get_height() * scale))
            new_w = max(1, int(t_surf.get_width() * scale))
            t_surf = pygame.transform.smoothscale(t_surf, (new_w, new_h))
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

        loot_effects = [e for e in (land.get('kingdom_skill_effects') or []) if 'loot chance' in e]
        if loot_effects and settings.TOUCH_TARGET_MIN <= 0:
            tiny_font = getattr(self, '_tiny_font', self._res_font)
            effect_text = self._fit_text(loot_effects[0], tiny_font, int(_BOX_W * 0.72))
            effect_surf = tiny_font.render(effect_text, True, settings.KINGDOM_CONFIG_HIGHLIGHT)
            self.window.blit(effect_surf, effect_surf.get_rect(centerx=_BOX_X + _BOX_W // 2,
                                                               top=specs_y + specs_surf.get_height() + 3))

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
        self._draw_section_panel(
            self._counter_panel_rect,
            'Defender Response',
            description=None if mobile_ui else 'Choose a battle figure or counter spell',
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

    def _current_defence_coach_step(self):
        """Light first-time guidance for the defence config (mixin coach)."""
        if not self._menu_coach_allowed_common():
            return None
        # Defence is an explicit follow-up lesson, not an interruption on every
        # first visit to this screen.
        if self._active_onboarding_lesson_id() != 'defend_land':
            return None
        if 'finish_defend_land_lesson' in self._onboarding_completed_steps():
            return None
        if (self._loading or self._error or not self._config or not self._layout_built
                or self._active_subscreen or self._figure_detail_box
                or self._move_detail_box or self._active_info_key):
            return None
        seen = self._menu_coach_seen()
        if self._btn_build and 'defence_intro' not in seen:
            return {
                'id': 'defence_intro',
                'rect': self._btn_build,
                'title': 'Defend This Land',
                'body': 'Build figures that hold this land when attacked — like an attack, but they stay to defend.',
                'action': 'next',
                'max_lines': 4,
            }
        if self._battle_plan_rect and 'defence_battle_plan' not in seen:
            return {
                'id': 'defence_battle_plan',
                'rect': self._battle_plan_rect,
                'title': 'Defence Battle Plan',
                'body': 'Assign the tactics your defenders use. A saved defence needs all three rounds filled.',
                'action': 'next',
                'max_lines': 4,
            }
        if self._counter_panel_rect and 'defence_final_response' not in seen:
            return {
                'id': 'defence_final_response',
                'rect': self._counter_panel_rect,
                'title': 'Defender Response',
                'body': 'Pick your defender response: a battle figure that fights back, or a counter spell that disrupts.',
                'action': 'next',
                'max_lines': 4,
            }
        if self._btn_save and 'defence_save' not in seen:
            return {
                'id': 'defence_save',
                'rect': self._btn_save,
                'title': 'Save Your Defence',
                'body': 'Save to lock it in. Its cards stay reserved, and the land is much harder to take.',
                'action': 'next',
                'button_label': 'Got it',
                'max_lines': 4,
            }
        return None

    def render(self):
        self._draw_menu_chrome()

        if self._active_subscreen and self._subscreen_obj:
            self._subscreen_obj.draw()
            self._draw_menu_overlay()
            return

        box_rect = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        _draw_panel(self.window, box_rect)

        if self._loading:
            draw_loading_indicator(
                self.window,
                box_rect,
                self._loading_message,
                started_at_ms=self._loading_started_at_ms,
                title='Defence Setup',
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

        # Save Defence / Confirm Defence button
        ready = self._is_defence_ready()
        save_clr = (100, 180, 80) if ready else (80, 80, 80)
        save_label = 'Confirm Defence' if self._victory_review_mode else 'Save Defence'
        self._draw_button(self._btn_save, save_label, save_clr)

        # Victory Review: secondary Clear All action to return every figure
        # to the player's collection before confirming.  Drawn in muted
        # crimson so it reads as destructive without screaming at the player.
        if self._victory_review_mode and self._btn_clear_all:
            has_figs = bool((self._config or {}).get('figures'))
            clear_clr = (170, 70, 70) if has_figs else (80, 80, 80)
            self._draw_button(self._btn_clear_all, 'Clear All', clear_clr)

        # Victory Review: non-destructive Skip exit.  Leaves whatever the
        # player has placed as a draft so they can finish later from the
        # land detail; the kingdom map flags the land as undefended via
        # the existing defence-incomplete badge.
        if self._victory_review_mode and self._btn_skip:
            self._draw_button(self._btn_skip, 'Skip for now', (140, 120, 70))

        # ── Divider lines ───────────────────────────────────────────
        # Vertical divider between left (field/resources) and right (battle) columns
        pygame.draw.line(self.window, DIVIDER,
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

        # Desktop hover tooltips for the small edit (pencil) icons
        self._pending_tooltip = None
        if (settings.TOUCH_TARGET_MIN <= 0 and not self.dialogue_box
                and not self._figure_detail_box and not self._move_detail_box
                and not self._selecting_battle_fig and not self._selecting_spell_target):
            mpos = pygame.mouse.get_pos()
            for icon_rect, tip in (
                (self._btn_build, 'Build a figure'),
                (self._btn_buy_move, 'Choose starting tactics'),
                (self._btn_prelude_edit, 'Choose a spell'),
                (self._btn_counter_edit, 'Pick your response'),
            ):
                if icon_rect and icon_rect.collidepoint(mpos):
                    self._pending_tooltip = (icon_rect, tip)
                    break
        if self._pending_tooltip:
            draw_hover_tooltip(self.window, self._pending_tooltip[0],
                               self._pending_tooltip[1], self._res_font)

        self._draw_menu_coach(self._current_defence_coach_step())
        self._draw_menu_overlay()
        draw_loot_risk_tutorial(self)
        self._draw_tutorial_complete_dialogue()

    def _field_slot_background(self, field_name, rect):
        slot_path = settings.SLOT_ICON_IMG_PATH_DICT.get(field_name)
        if not slot_path:
            return None
        if field_name not in self._field_slot_icon_raw:
            try:
                self._field_slot_icon_raw[field_name] = pygame.image.load(slot_path).convert_alpha()
            except Exception:
                self._field_slot_icon_raw[field_name] = None
        raw = self._field_slot_icon_raw.get(field_name)
        if raw is None:
            return None
        slot_s = max(1, min(rect.w, rect.h) - 10)
        key = (field_name, slot_s, settings.SLOT_ICON_TRANSPARENCY)
        surf = self._field_slot_icon_cache.get(key)
        if surf is None:
            surf = pygame.transform.smoothscale(raw, (slot_s, slot_s))
            surf.set_alpha(settings.SLOT_ICON_TRANSPARENCY)
            self._field_slot_icon_cache[key] = surf
        return surf

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

            slot_icon = self._field_slot_background(field_name, rect)
            if slot_icon:
                sr = slot_icon.get_rect(center=rect.center)
                self.window.blit(slot_icon, sr.topleft)

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
                if settings.TOUCH_TARGET_MIN > 0 or frame_rect.collidepoint(mouse_pos) or x_hovered:
                    draw_remove_x(self.window, xbtn, x_hovered)
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
                hw = sw * 0.7
                hh = sw * 0.7
                is_hovered = (abs(mouse_pos[0] - cx) / hw + abs(mouse_pos[1] - cy) / hh <= 1.0)
                if is_hovered:
                    self._hovered_slot = i

                m = move_by_round[i]
                hovered = is_hovered and not mouse_pressed

                draw_battle_move_icon(
                    self.window, cx, cy,
                    m['family_name'], m['suit'],
                    self._battle_move_display_power(m),
                    self._slot_glow_cache, self._slot_icon_cache,
                    self._slot_frame_cache, self._suit_icon_cache,
                    self._slot_font, sw,
                    hovered=hovered,
                )

                xsz = self._x_btn_sz
                xrect = pygame.Rect(cx + int(sw * 0.35), cy - int(sw * 0.65), xsz, xsz)
                x_hovered = xrect.collidepoint(mouse_pos)
                if settings.TOUCH_TARGET_MIN > 0 or is_hovered or x_hovered:
                    draw_remove_x(self.window, xrect, x_hovered)
                    self._move_remove_rects[i] = xrect

                rlbl = self._small_font.render(f'R{i + 1}', True, (160, 140, 120))
                self.window.blit(rlbl, rlbl.get_rect(centerx=cx, top=cy + int(sw * 0.55)))
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
                if settings.TOUCH_TARGET_MIN > 0 or rect.collidepoint(mx_mouse, my_mouse) or x_hovered:
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

    def _draw_counter_action(self):
        """Draw the counter action section: battle figure OR counter spell."""
        counter_spell = self._config.get('counter_spell_name')
        is_civil_war = self._civil_war_battle_strategy()
        bf_id = self._config.get('battle_figure_id')
        bf2_id = self._config.get('battle_figure_id_2')
        if is_civil_war and self._pending_civil_war_battle_fig_1 and not bf2_id:
            bf_id = self._pending_civil_war_battle_fig_1
        fsz = self._spell_frame_size
        mx_mouse, my_mouse = pygame.mouse.get_pos()

        # ── Battle figure slot ──
        bf_rect = self._battle_figure_rect
        if bf_rect:
            self._draw_battle_figure_icon(
                bf_rect, bf_id, mx_mouse, my_mouse,
                x_attr='_battle_figure_x_rect',
                empty_label='Battle Fig',
            )

        bf2_rect = self._battle_figure_rect_2 if is_civil_war else None
        if bf2_rect:
            self._draw_battle_figure_icon(
                bf2_rect, bf2_id, mx_mouse, my_mouse,
                x_attr='_battle_figure_x_rect_2',
                empty_label='Optional',
            )
        elif not is_civil_war:
            self._battle_figure_x_rect_2 = None

        # ── Vertical separator between figure and spell ──
        cs_rect = self._counter_spell_rect
        if bf_rect and cs_rect:
            left_edge = bf2_rect.right if bf2_rect else bf_rect.right
            sep_x = (left_edge + cs_rect.x) // 2
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
                if settings.TOUCH_TARGET_MIN > 0 or cs_rect.collidepoint(mx_mouse, my_mouse) or x_hovered:
                    self._counter_x_rect = xrect
                    draw_remove_x(self.window, xrect, x_hovered)
                else:
                    self._counter_x_rect = None
        else:
            self._counter_x_rect = None
            draw_empty_slot(self.window, cs_rect)
            empty_label = (
                'No counter'
                if settings.TOUCH_TARGET_MIN > 0
                else 'No counter spell'
            )
            lines = [
                (empty_label, self._res_font, (140, 130, 110)),
                ('Optional', self._res_font, (110, 105, 95)),
            ]
            text_h = sum(font.get_height() for _, font, _ in lines) + 2
            self._draw_caption_lines(lines, caption_x, cy - text_h // 2, caption_w)

    def _draw_battle_figure_icon(
        self, rect, bf_id, mx, my_mouse, *,
        x_attr='_battle_figure_x_rect', empty_label='Battle Fig',
    ):
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
            ntxt = self._res_font.render(empty_label, True, (130, 130, 130))
            self.window.blit(ntxt, ntxt.get_rect(centerx=cx, top=rect.bottom + 2))

        if is_selected:
            if self._advance_icon:
                ax = rect.right - self._advance_icon.get_width()
                ay = rect.y
                self.window.blit(self._advance_icon, (ax, ay))

            _xbs = self._x_btn_sz
            xrect = pygame.Rect(rect.right - _xbs - 2, rect.y + 2, _xbs, _xbs)
            x_hovered = xrect.collidepoint(mx, my_mouse)
            if settings.TOUCH_TARGET_MIN > 0 or rect.collidepoint(mx, my_mouse) or x_hovered:
                setattr(self, x_attr, xrect)
                draw_remove_x(self.window, xrect, x_hovered)
            else:
                setattr(self, x_attr, None)
        else:
            setattr(self, x_attr, None)

    def _draw_auto_gamble(self):
        enabled = self._config.get('auto_gamble', False)
        threshold = self._get_auto_gamble_threshold()
        mobile_ui = settings.TOUCH_TARGET_MIN > 0
        label = 'Auto' if mobile_ui else (
            'Auto-Gamble: ON' if enabled else 'Auto-Gamble: OFF')
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

        if not mobile_ui:
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
        from game.components.resource_panel import draw_resource_panel
        draw_resource_panel(
            self.window, self._res_rect, self._calc_resources(),
            self._resource_icons, self._res_font)

    def _on_save_click(self):
        """Handle click on Save Defence / Confirm Defence button."""
        sound.play('ui_click', volume=0.8)
        cannot_title = 'Cannot Confirm Defence' if self._victory_review_mode else 'Cannot Save Defence'
        if not self._is_defence_ready():
            problems = self._get_defence_problems()
            if self._victory_review_mode:
                problems = list(problems) + [
                    'Use Clear All to leave this land undefended for now.'
                ]
            self._show_problem_dialogue(cannot_title, problems)
            return
        validation = self._server_validate_draft()
        if not validation.get('success'):
            self._show_problem_dialogue(
                cannot_title,
                validation.get('problems') or [validation.get('message', 'Configuration is incomplete')],
            )
            return
        self._save_defence_with_loot_tutorial()

    def _save_defence_with_loot_tutorial(self):
        if loot_risk_tutorial_seen(self):
            self._save_ready_defence()
            return
        open_loot_risk_tutorial(self, {'kind': 'save_defence'})

    def _save_ready_defence(self):
        self._pending_nav = self._pending_nav or 'kingdom'
        if self._server_save_draft():
            if self._victory_review_mode:
                self._server_acknowledge_victory_review()
                self._victory_review_mode = False
                self._victory_review_game_id = None
                self._pending_victory_ack = True
            self._complete_pending_navigation()

    def _resume_loot_risk_tutorial_action(self, action):
        if isinstance(action, dict) and action.get('kind') == 'save_defence':
            self._save_ready_defence()

    def _on_skip_click(self):
        """Victory Review: leave without finalising the defence.

        The draft (whatever figures the player has placed so far) is
        already persisted server-side, so we just acknowledge the victory
        and navigate back to the kingdom.  The land will surface the
        existing ``defence_incomplete`` badge so the player remembers to
        finish setup later.
        """
        if not self._victory_review_mode:
            return
        self._server_acknowledge_victory_review()
        self._victory_review_mode = False
        self._victory_review_game_id = None
        self._pending_victory_ack = True
        self._pending_nav = self._pending_nav or 'kingdom'
        self.state.set_msg('Defence left incomplete — finish later from the land')
        self._complete_pending_navigation()

    def _on_clear_all_click(self):
        """Victory Review: confirm dialog before wiping draft + active defence."""
        if not self._victory_review_mode:
            return
        figs = (self._config or {}).get('figures') or []
        if not figs:
            self.state.set_msg('Defence is already empty')
            return
        self._pending_clear_all_confirm = True
        open_dialogue(
            self,
            ("Return every figure on this land to your collection?\n\n"
             "This land will be left undefended until you configure it."),
            ['Clear All', 'Cancel'],
            'Leave this land undefended?',
            icon='warning',
        )

    def _server_acknowledge_victory_review(self):
        """POST /kingdom/conquer/acknowledge_victory_review. Idempotent on the server."""
        gid = self._victory_review_game_id
        if not gid:
            return True
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/acknowledge_victory_review',
                json={'game_id': gid},
                timeout=10,
            )
            data = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
            if not data.get('success'):
                logger.warning('Victory ack failed: %s', data.get('message'))
                return False
            return True
        except Exception as e:
            logger.error('Victory ack error: %s', e)
            return False

    def _server_clear_active_defence(self):
        """POST /kingdom/defence/clear_active. Wipes both draft and active for this land."""
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/clear_active',
                json={'land_id': self._land_id},
                timeout=15,
            )
            data = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
            if data.get('success'):
                return True
            message = data.get('message') or data.get('error') or 'Could not clear defence'
            logger.warning('Clear active defence failed: %s', message)
            self.state.set_msg(message)
            return False
        except Exception as e:
            logger.error('Clear active defence error: %s', e)
            self.state.set_msg('Could not clear defence')
            return False

    def _get_config_fig(self, figure_id):
        for fig in self._config.get('figures', []):
            if fig['id'] == figure_id:
                return fig
        return None

    def _figure_object(self, figure_id):
        return next((f for f in self._figure_objects if f.id == figure_id), None)

    def _battle_required_field(self):
        modifiers = []
        prelude = self._config.get('prelude_spell_name')
        if prelude:
            modifiers.append({'type': prelude})
        modifier = self._config.get('battle_modifier') or {}
        if isinstance(modifier, dict):
            modifiers.append(modifier)
        elif isinstance(modifier, list):
            modifiers.extend(modifier)
        return battle_required_field(modifiers)

    def _battle_modifier_requires_village(self):
        return self._battle_required_field() == 'village'

    def _civil_war_battle_strategy(self):
        if self._battle_required_field() == 'castle':
            return False
        if self._config.get('prelude_spell_name') == 'Civil War':
            return True
        modifier = self._config.get('battle_modifier') or {}
        return isinstance(modifier, dict) and modifier.get('type') == 'Civil War'

    def _battle_figure_block_reason(self, figure_id):
        cfg_fig = self._get_config_fig(figure_id)
        fig = self._figure_object(figure_id)
        if not cfg_fig or not fig:
            return 'Could not select that figure'
        if cfg_fig.get('has_deficit', False):
            return 'Cannot select a figure in deficit'
        if getattr(fig, 'cannot_attack', False):
            return 'This figure cannot counter-advance because it cannot attack'
        if getattr(fig, 'cannot_defend', False):
            return 'This figure cannot counter-advance because it cannot defend'
        required_field = self._battle_required_field()
        if required_field and getattr(fig.family, 'field', None) != required_field:
            if required_field == 'castle':
                return 'Royal Decree requires castle battle figures'
            return 'This battle modifier requires village figures'
        return None

    def _battle_figure_is_selectable(self, figure_id):
        return self._battle_figure_block_reason(figure_id) is None

    def _battle_figure_color(self, figure_id):
        cfg_fig = self._get_config_fig(figure_id)
        if cfg_fig:
            return cfg_fig.get('color')
        fig = self._figure_object(figure_id)
        return getattr(fig, 'color', None)

    def _begin_battle_figure_selection(self):
        if self._config.get('counter_spell_name'):
            self._server_clear_counter_spell()
        self._selecting_battle_fig = True
        self._pending_civil_war_battle_fig_1 = None
        if self._civil_war_battle_strategy():
            current_first = self._config.get('battle_figure_id')
            current_second = self._config.get('battle_figure_id_2')
            if current_first and not current_second and self._battle_figure_is_selectable(current_first):
                self._pending_civil_war_battle_fig_1 = current_first
                self.state.set_msg('Select an optional second same-color Civil War figure')
            else:
                self.state.set_msg('Select the first Civil War battle figure')

    def _handle_battle_figure_pick(self, figure_id):
        if not self._civil_war_battle_strategy():
            self._server_set_battle_figure(figure_id)
            self._selecting_battle_fig = False
            self._pending_civil_war_battle_fig_1 = None
            return

        first_id = self._pending_civil_war_battle_fig_1
        if not first_id:
            # Commit the first figure immediately. The second Civil War slot
            # is an optional enhancement and can be selected with a separate
            # click, matching the runtime skip-second rule.
            self._server_set_battle_figure(figure_id)
            self._selecting_battle_fig = False
            self._pending_civil_war_battle_fig_1 = None
            return

        if figure_id == first_id:
            self.state.set_msg('Civil War requires two different battle figures')
            return
        if self._battle_figure_color(figure_id) != self._battle_figure_color(first_id):
            self.state.set_msg('Civil War requires two battle figures of the same color')
            return

        self._server_set_battle_figure(first_id, figure_id)
        self._selecting_battle_fig = False
        self._pending_civil_war_battle_fig_1 = None

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
                    type='main' if (c['rank'] in settings.RANKS_MAIN_CARDS
                                    or c['rank'] == settings.RANK_MAHARAJA) else 'side_card',
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
            self._config, self._land_id, mode='defence', land=self._land or {})
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
        self._game_proxy = KingdomGameProxy(
            self._config, self._land_id, mode='defence', land=self._land or {})
        self.state.game = self._game_proxy
        sx, sy = self._config_subscreen_origin()
        self._subscreen_obj = BattleShopScreen(
            self.window, self.state,
            x=sx, y=sy,
            title='Starting Tactics', card_source=card_source, mode='defence_draft',
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
        self._game_proxy = KingdomGameProxy(
            self._config, self._land_id, mode='defence', land=self._land or {})
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
        self._game_proxy = KingdomGameProxy(
            self._config, self._land_id, mode='defence', land=self._land or {})
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
            description_overrides=_DEFENCE_COUNTER_DESCRIPTION_OVERRIDES,
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
        # The player may have just picked Health Boost — prompt for its
        # target once the refreshed config arrives.
        self._prompt_spell_target_on_next_load = True
        # Refresh config from server (async — keeps the event loop responsive)
        self._start_config_load()

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
            sound.play('ui_back')
            self._complete_pending_navigation()
            return
        self._pending_leave_confirm = True
        open_dialogue(
            self,
            'You have unsaved defence changes.\n'
            'Save them, discard only this draft, or stay here.',
            ['Save & Leave', 'Discard Changes', 'Stay'],
            'Unsaved Defence Changes',
        )

    # ── Readiness check ─────────────────────────────────────────────

    def _is_defence_ready(self):
        """True when the defence configuration is complete enough."""
        if not self._config:
            return False
        figures = self._config.get('figures', [])
        moves = self._config.get('battle_moves', [])

        prelude = self._config.get('prelude_spell_name')
        required_field = self._battle_required_field()

        has_valid_figure = any(
            not f.get('has_deficit', False)
            and (not required_field or f.get('field') == required_field)
            for f in figures
        )
        has_moves = len(moves) == 3

        # Defence requires exactly one counter strategy:
        # battle figure XOR counter spell.
        has_battle_fig = self._config.get('battle_figure_id') is not None
        has_counter_spell = self._config.get('counter_spell_name') is not None
        has_exactly_one_strategy = (has_battle_fig != has_counter_spell)
        battle_fig_valid = (
            not has_battle_fig
            or self._battle_figure_is_selectable(self._config.get('battle_figure_id'))
        )
        if has_battle_fig and self._civil_war_battle_strategy():
            fig1_id = self._config.get('battle_figure_id')
            fig2_id = self._config.get('battle_figure_id_2')
            if fig2_id:
                battle_fig_valid = (
                    battle_fig_valid
                    and fig2_id != fig1_id
                    and self._battle_figure_is_selectable(fig2_id)
                    and self._battle_figure_color(fig1_id) == self._battle_figure_color(fig2_id)
                )
        elif self._config.get('battle_figure_id_2'):
            battle_fig_valid = False
        has_required_spell_targets = (
            self._has_health_boost_target('prelude')
            and self._has_health_boost_target('counter')
        )
        return (has_valid_figure and has_moves and has_exactly_one_strategy
                and battle_fig_valid and has_required_spell_targets)

    def _get_defence_problems(self):
        """Return a list of human-readable problems preventing save."""
        problems = []
        if not self._config:
            problems.append('Configuration not loaded.')
            return problems

        figures = self._config.get('figures', [])
        moves = self._config.get('battle_moves', [])
        prelude = self._config.get('prelude_spell_name')
        required_field = self._battle_required_field()

        if not figures:
            problems.append('No figures on the field.')
        else:
            can_fight = [f for f in figures if not f.get('has_deficit', False)]
            if not can_fight:
                problems.append('All figures have a resource deficit.')
            elif required_field:
                field_fighters = [
                    f for f in can_fight if f.get('field') == required_field
                ]
                if not field_fighters:
                    modifier_name = (
                        'Royal Decree' if required_field == 'castle' else prelude
                    )
                    problems.append(
                        f'{modifier_name} is selected \u2014 only {required_field} figures can fight, '
                        f'but none of your {required_field} figures are available.'
                    )

        if len(moves) < 3:
            missing = 3 - len(moves)
            problems.append(
                f'{missing} starting tactic{"s" if missing > 1 else ""} '
                'still missing (need 3).')

        has_battle_fig = self._config.get('battle_figure_id') is not None
        has_counter_spell = self._config.get('counter_spell_name') is not None

        if has_battle_fig and has_counter_spell:
            problems.append('Select exactly one strategy: battle figure or counter spell (not both).')
        elif not has_battle_fig and not has_counter_spell:
            problems.append('Select exactly one strategy: battle figure or counter spell.')
        elif has_battle_fig:
            reason = self._battle_figure_block_reason(self._config.get('battle_figure_id'))
            if reason:
                problems.append(reason)
            if self._civil_war_battle_strategy():
                fig2_id = self._config.get('battle_figure_id_2')
                if fig2_id == self._config.get('battle_figure_id'):
                    problems.append('Civil War requires two different battle figures.')
                elif fig2_id:
                    reason = self._battle_figure_block_reason(fig2_id)
                    if reason:
                        problems.append(f'Second battle figure: {reason}')
                    elif (self._battle_figure_color(fig2_id)
                          != self._battle_figure_color(self._config.get('battle_figure_id'))):
                        problems.append('Civil War: both battle figures must be the same color.')
        elif self._config.get('battle_figure_id_2'):
            problems.append('Second battle figure is only valid with Civil War.')

        if prelude == 'Health Boost' and not self._prelude_health_target_id():
            problems.append('Health Boost prelude needs one of your figures as target.')
        if self._config.get('counter_spell_name') == 'Health Boost' and not self._config.get('counter_spell_target_figure_id'):
            problems.append('Health Boost counter spell needs one of your figures as target.')

        return problems

    # ── Update / events ─────────────────────────────────────────────

    def _handle_icon_events(self, event):
        """Guard shared menu icons so they cannot bypass draft handling."""
        if getattr(self, '_onboarding_guide_open', False):
            return MenuScreenMixin._handle_icon_events(self, event)
        if hasattr(self, '_logout_dialogue') and self._logout_dialogue:
            return MenuScreenMixin._handle_icon_events(self, event)
        if event.type == pygame.MOUSEBUTTONUP:
            if self._icon_guide.collide():
                self._open_onboarding_guide()
                return True
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
            self._config_poller = None
            self._config_poller_land_id = None

        self._drain_config_poller()

        if self._land_id and not self._config and not self._loading and not self._error:
            self._start_config_load()

        # Update figure icon hover states
        for icon in self._figure_icons.values():
            icon.update()
        self._maybe_show_tutorial_completion()

    def handle_events(self, events):
        if self._handle_tutorial_completion_events(events):
            return
        if super().handle_events(events):
            events = ()

        # Handle prelude / counter spell confirmation dialogue responses
        response = self.state.action.get('status')
        if response and self._pending_clear_all_confirm:
            self._pending_clear_all_confirm = False
            self.reset_action()
            if response == 'clear all':
                if self._server_clear_active_defence():
                    if self._victory_review_mode:
                        self._server_acknowledge_victory_review()
                        self._victory_review_mode = False
                        self._victory_review_game_id = None
                        self._pending_victory_ack = True
                    self._pending_nav = self._pending_nav or 'kingdom'
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
        if response in ('ok', 'cancel'):
            self._pending_leave_confirm = False
            self._pending_nav = None
            self._selecting_spell_target = None
            self.reset_action()
            return

        if self.dialogue_box:
            return

        loot_tutorial_action = handle_loot_risk_tutorial_events(self, events)
        if loot_tutorial_action is not None:
            if isinstance(loot_tutorial_action, dict):
                self._resume_loot_risk_tutorial_action(loot_tutorial_action)
            return

        # Tutorial coach captures input while a card is showing.
        if self._handle_menu_coach_events(events, self._current_defence_coach_step()):
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
                            reason = self._battle_figure_block_reason(fig.id)
                            if cfg_fig and reason is None:
                                self._handle_battle_figure_pick(fig.id)
                                selected = True
                            else:
                                self.state.set_msg(reason or 'Cannot select that figure')
                                selected = True
                            break
                    if not selected:
                        self._selecting_battle_fig = False
                        self._pending_civil_war_battle_fig_1 = None
                    return
                if event.type == KEYDOWN and event.key == K_ESCAPE:
                    self._selecting_battle_fig = False
                    self._pending_civil_war_battle_fig_1 = None
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

                if (_mobile_collide(self._battle_figure_x_rect, pos,
                                    settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN)
                        or _mobile_collide(self._battle_figure_x_rect_2, pos,
                                           settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN)):
                    self._pending_civil_war_battle_fig_1 = None
                    self._server_clear_battle_figure()
                    continue

                if _mobile_collide(self._counter_x_rect, pos,
                                   settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                    if self._config.get('counter_spell_name'):
                        self._server_clear_counter_spell()
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

                # Prelude spell: edit button opens spell picker; Health Boost slot picks target
                if _mobile_collide(self._btn_prelude_edit, pos,
                                   settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                    sound.play('ui_click')
                    self._open_prelude_spell_screen()
                    continue
                if _mobile_collide(self._prelude_spell_rect, pos):
                    sound.play('ui_click')
                    if self._config.get('prelude_spell_name') == 'Health Boost':
                        self._begin_spell_target_selection('prelude')
                    else:
                        self._open_prelude_spell_screen()
                    continue

                # Counter action: battle figure slot click
                battle_slot_clicked = (
                    _mobile_collide(self._battle_figure_rect, pos)
                ) or (
                    self._civil_war_battle_strategy()
                    and self._battle_figure_rect_2
                    and _mobile_collide(self._battle_figure_rect_2, pos)
                )
                if battle_slot_clicked:
                    civil_war_incomplete = (
                        self._civil_war_battle_strategy()
                        and not self._config.get('battle_figure_id_2')
                    )
                    if not self._config.get('battle_figure_id') or civil_war_incomplete:
                        figs = self._config.get('figures', [])
                        valid = [f for f in figs if self._battle_figure_is_selectable(f.get('id'))]
                        if valid:
                            sound.play('ui_click')
                            self._begin_battle_figure_selection()
                        else:
                            self.state.set_msg('No valid figures available')
                    continue

                # Defender response: edit button opens picker; Health Boost slot picks target
                if _mobile_collide(self._btn_counter_edit, pos,
                                   settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                    sound.play('ui_click')
                    self._open_counter_spell_screen()
                    continue
                if _mobile_collide(self._counter_spell_rect, pos):
                    sound.play('ui_click')
                    if self._config.get('counter_spell_name') == 'Health Boost':
                        self._begin_spell_target_selection('counter')
                    else:
                        self._open_counter_spell_screen()
                    continue

                # Threshold controls first so they keep working even if layout
                # changes make them overlap with the auto-gamble toggle rect.
                if _mobile_collide(self._btn_auto_gamble_dec, pos,
                                   settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                    sound.play('ui_click', volume=0.7)
                    current = self._get_auto_gamble_threshold()
                    target = max(_AUTO_GAMBLE_THRESHOLD_MIN, current - 1)
                    if target != current:
                        self._config['auto_gamble_threshold'] = target
                    if not self._server_set_auto_gamble_threshold(target):
                        self._config['auto_gamble_threshold'] = current
                    continue

                if _mobile_collide(self._btn_auto_gamble_inc, pos,
                                   settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
                    sound.play('ui_click', volume=0.7)
                    current = self._get_auto_gamble_threshold()
                    target = min(_AUTO_GAMBLE_THRESHOLD_MAX, current + 1)
                    if target != current:
                        self._config['auto_gamble_threshold'] = target
                    if not self._server_set_auto_gamble_threshold(target):
                        self._config['auto_gamble_threshold'] = current
                    continue

                # Auto-gamble toggle
                if _mobile_collide(self._btn_auto_gamble, pos):
                    sound.play('ui_click', volume=0.7)
                    current = self._config.get('auto_gamble', False)
                    self._server_set_auto_gamble(not current)
                    continue

                # Save Defence / Confirm Defence button
                if _mobile_collide(self._btn_save, pos):
                    self._on_save_click()
                    continue

                # Victory Review: Clear All button
                if (self._victory_review_mode and self._btn_clear_all
                        and _mobile_collide(self._btn_clear_all, pos)):
                    self._on_clear_all_click()
                    continue

                # Victory Review: Skip for now button
                if (self._victory_review_mode and self._btn_skip
                        and _mobile_collide(self._btn_skip, pos)):
                    self._on_skip_click()
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
