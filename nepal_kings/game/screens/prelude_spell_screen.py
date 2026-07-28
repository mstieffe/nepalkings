# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Spell selection screen for conquer/defence prelude and counter spells.

Opened as a subscreen from ConquerScreen / DefenceScreen, similarly to
BuildFigureScreen and BattleShopScreen.  Displays allowed spell families
as clickable icons, lists castable variants in a scroll list, and calls
the server endpoint on confirmation.
"""
import pygame
from pygame.locals import *
from collections import Counter
from config import settings
from game.screens.sub_screen import SubScreen
from game.components.spells.spell_manager import SpellManager
from game.components.buttons.confirm_button import ConfirmButton
from game.components.picker_ui import (
    SegmentedTabs,
    draw_empty_detail,
    draw_footer,
    draw_section_header,
    footer_button_geometry,
    layout_family_grid_desktop,
)
from utils import http_compat as requests
import logging

logger = logging.getLogger('nk.screens.prelude_spell')


class PreludeSpellScreen(SubScreen):
    """SubScreen for selecting a prelude or counter spell in kingdom config."""

    def __init__(self, window, state, x=0.0, y=0.0, title=None,
                 card_source=None, mode='conquer',
                 allowed_spells=None, server_endpoint=None, land_id=None,
                 extra_payload=None, description_overrides=None):
        """
        Parameters
        ----------
        allowed_spells : list[str]
            Spell family names the user may choose from.
        server_endpoint : str
            Server URL to POST the selection to, e.g.
            ``/kingdom/conquer/set_prelude_spell``.
        land_id : int
            The land this config belongs to.
        extra_payload : dict, optional
            Additional fields merged into the POST body.  Used e.g. by the
            defence counter spell flow to pass ``clear_battle_figure=True``
            so the server clears the existing battle figure atomically.
        """
        super().__init__(window, state.game, x, y, title)

        self.state = state
        self.game = state.game
        self.card_source = card_source
        self.mode = mode
        # Keep the caller's ordering — the icon grid lays out families in
        # exactly this sequence (e.g. Draw 4 directly after Draw 2).
        self.allowed_spell_order = list(allowed_spells or [])
        self.allowed_spells = set(self.allowed_spell_order)
        self.server_endpoint = server_endpoint
        self.land_id = land_id
        self.extra_payload = dict(extra_payload or {})
        self.description_overrides = dict(description_overrides or {})
        self._active_spell_type = 'greed'
        self._initial_family_selected = False
        self._desktop_headers = []
        self._is_counter_picker = 'counter' in str(server_endpoint or '').lower()
        if self._is_counter_picker:
            self.title = 'Set Counter · Defence Setup'
        elif self.mode == 'conquer':
            self.title = 'Set Prelude · Attack Setup'
        else:
            self.title = 'Set Prelude · Defence Setup'

        # Spell manager
        self.spell_manager = SpellManager()

        # UI components
        self.init_spell_info_box()
        self.init_spell_category_tabs()
        self.init_spell_family_icons()
        self.init_scroll_test_list_shifter()

        self.selected_spell_family = None

        action_label = 'Set Counter' if self._is_counter_picker else 'Set Prelude'
        bx, by, bw, bh = footer_button_geometry(
            self, action_label, align='center')
        self.confirm_button = ConfirmButton(
            self.window,
            bx, by, action_label, width=bw, height=bh,
        )

    # ── Initialisation helpers ──────────────────────────────────────

    def init_spell_info_box(self):
        super().init_sub_box_background(
            settings.CAST_SPELL_INFO_BOX_X,
            settings.CAST_SPELL_INFO_BOX_Y,
            settings.CAST_SPELL_INFO_BOX_WIDTH,
            settings.CAST_SPELL_INFO_BOX_HEIGHT,
        )
        super().init_scroll_background(
            settings.CAST_SPELL_INFO_BOX_SCROLL_X,
            settings.CAST_SPELL_INFO_BOX_SCROLL_Y,
            settings.CAST_SPELL_INFO_BOX_SCROLL_WIDTH,
            settings.CAST_SPELL_INFO_BOX_SCROLL_HEIGHT,
        )

    def init_scroll_test_list_shifter(self):
        self.make_scroll_text_list_shifter(
            self.scroll_text_list,
            settings.CAST_SPELL_SCROLL_TEXT_X,
            settings.CAST_SPELL_SCROLL_TEXT_Y,
            scroll_height=settings.CAST_SPELL_INFO_BOX_SCROLL_HEIGHT,
        )

    def init_spell_category_tabs(self):
        ordered_types = ['greed', 'enchantment', 'tactics']
        present_types = []
        allowed_order = getattr(
            self, 'allowed_spell_order',
            sorted(getattr(self, 'allowed_spells', set())))
        for name in allowed_order:
            family = self.spell_manager.get_family_by_name(name)
            if family and family.type not in present_types:
                present_types.append(family.type)
        present_types = [
            spell_type for spell_type in ordered_types
            if spell_type in present_types
        ]
        if not present_types:
            present_types = ordered_types
        self._active_spell_type = present_types[0]

        offset_x = getattr(self, '_layout_offset_x', 0)
        offset_y = getattr(self, '_layout_offset_y', 0)
        box_x = int(settings.CAST_SPELL_INFO_BOX_X + offset_x)
        box_y = int(settings.CAST_SPELL_INFO_BOX_Y + offset_y)
        margin = max(8, int(0.012 * settings.SCREEN_WIDTH))
        tab_h = max(
            26,
            settings.TOUCH_COMPACT_MIN
            if settings.TOUCH_TARGET_MIN > 0 else 0,
        )
        self.spell_category_tabs = SegmentedTabs(
            self.window,
            pygame.Rect(
                box_x + margin,
                box_y + max(6, int(0.012 * settings.SCREEN_HEIGHT)),
                settings.CAST_SPELL_INFO_BOX_WIDTH - 2 * margin,
                tab_h,
            ),
            [(spell_type, spell_type.capitalize())
             for spell_type in present_types],
            active_key=self._active_spell_type,
        )

    def init_spell_family_icons(self):
        """Create fixed-size icons; the selected category forms a clean grid."""
        if not hasattr(self, 'spell_category_tabs'):
            self.init_spell_category_tabs()
        self.spell_family_buttons = []
        ordered_names = getattr(self, 'allowed_spell_order', None) or sorted(self.allowed_spells)
        for name in ordered_names:
            family = self.spell_manager.get_family_by_name(name)
            if family is not None:
                button = family.make_icon(self.window, self.game,
                                          0, 0,
                                          fixed_size=True)
                if settings.TOUCH_TARGET_MIN <= 0:
                    # Desktop packs all category rows on one page.
                    button.grid_mode = True
                    button.rescale(settings.PICKER_DESKTOP_ICON_SCALE)
                self.spell_family_buttons.append(button)
        self.type_labels = {}
        self.type_label_positions = {}
        self._layout_spell_family_icons()

    def _visible_spell_buttons(self):
        # Desktop shows the whole spell book at once; mobile pages by category.
        if settings.TOUCH_TARGET_MIN <= 0:
            return list(self.spell_family_buttons)
        active_type = getattr(self, '_active_spell_type', 'greed')
        return [
            button for button in self.spell_family_buttons
            if button.family.type == active_type
        ]

    def _layout_spell_family_icons(self):
        offset_x = getattr(self, '_layout_offset_x', 0)
        offset_y = getattr(self, '_layout_offset_y', 0)
        box = pygame.Rect(
            int(settings.CAST_SPELL_INFO_BOX_X + offset_x),
            int(settings.CAST_SPELL_INFO_BOX_Y + offset_y),
            settings.CAST_SPELL_INFO_BOX_WIDTH,
            settings.CAST_SPELL_INFO_BOX_HEIGHT,
        )
        mobile = settings.TOUCH_TARGET_MIN > 0
        if not mobile:
            # All allowed families on one page, grouped into category rows.
            self._desktop_headers = layout_family_grid_desktop(
                self.spell_family_buttons, box)
            return
        cols = 5 if mobile else 6
        margin_x = int(0.07 * box.w)
        usable_w = box.w - 2 * margin_x
        pitch_x = usable_w // max(1, cols - 1)
        start_x = box.x + margin_x
        start_y = self.spell_category_tabs.rect.bottom + int(
            0.105 * settings.SCREEN_HEIGHT)
        pitch_y = int(0.205 * settings.SCREEN_HEIGHT)
        visible = set(self._visible_spell_buttons())
        for button in self.spell_family_buttons:
            button.visible = button in visible
            button.caption_max_width = max(48, int(pitch_x * 0.92))
        for index, button in enumerate(self._visible_spell_buttons()):
            row, col = divmod(index, cols)
            button.set_position(
                start_x + col * pitch_x,
                start_y + row * pitch_y,
            )

    # ── Card helpers ────────────────────────────────────────────────

    def _collection_cards(self):
        """Return (main, side) card lists from the card source."""
        if self.card_source:
            return self.card_source.get_cards()
        return [], []

    def _all_free_cards(self):
        main, side = self._collection_cards()
        return main + side

    def get_spells_in_collection(self, spell_family):
        """Return spell variants from *spell_family* that the player can afford."""
        hand = self._all_free_cards()
        hand_counter = Counter((c.suit, c.rank) for c in hand)
        castable = []
        for spell in spell_family.spells:
            spell_counter = Counter((c.suit, c.rank) for c in spell.cards)
            if all(hand_counter[t] >= n for t, n in spell_counter.items()):
                castable.append(spell)
        return castable

    def get_given_and_missing_cards(self, spell):
        """Split spell cards into available / missing based on collection."""
        hand = self._all_free_cards()
        hand_counter = Counter((c.suit, c.rank) for c in hand)
        assigned = Counter()
        given, missing = [], []
        for card in spell.cards:
            t = (card.suit, card.rank)
            if assigned[t] < hand_counter[t]:
                given.append(card)
                assigned[t] += 1
            else:
                missing.append(card)
        return given, missing

    def _format_spell_type(self, spell_type):
        return {'greed': 'Greed Spell', 'enchantment': 'Enchantment Spell',
                'tactics': 'Tactics Spell'}.get(spell_type, spell_type.capitalize())

    def _family_description(self, family):
        return self.description_overrides.get(family.name, family.description)

    def _detail_item(self, spell, *, content, cards=None,
                     missing_cards=None):
        item = {
            'title': spell.name,
            'text': self._family_description(spell.family),
            'cards': spell.cards if cards is None else cards,
            'spell_type': self._format_spell_type(spell.family.type),
            'counterable': spell.counterable,
            'timing': (
                'Timing: responds before battle'
                if self._is_counter_picker
                else 'Timing: resolves before battle'
            ),
            'content': content,
        }
        if getattr(spell, 'requires_target', False):
            item['target_hint'] = 'Target: choose after setting this spell'
        if missing_cards:
            item['missing_cards'] = missing_cards
        return item

    def _select_spell_family(self, button):
        self.selected_spell_family = button.family
        castable = self.get_spells_in_collection(button.family)
        if castable:
            self.scroll_text_list = [
                self._detail_item(spell, content=spell)
                for spell in castable
            ]
        else:
            self.scroll_text_list = []
            for spell in button.family.spells:
                given, missing = self.get_given_and_missing_cards(spell)
                self.scroll_text_list.append(
                    self._detail_item(
                        spell, content=None,
                        cards=given, missing_cards=missing)
                )
        self.scroll_text_list_shifter.set_displayed_texts(
            self.scroll_text_list)
        for other in self.spell_family_buttons:
            other.clicked = other is button

    def _select_initial_spell_family(self):
        if self._initial_family_selected:
            return
        visible = self._visible_spell_buttons()
        if not visible:
            return
        chosen = next((button for button in visible if button.is_active),
                      visible[0])
        self._select_spell_family(chosen)
        self._initial_family_selected = True

    def _confirm_action_label(self, selected_spell):
        if getattr(selected_spell, 'requires_target', False):
            return 'Choose Target'
        return 'Set Counter' if self._is_counter_picker else 'Set Prelude'

    # ── Update ──────────────────────────────────────────────────────

    def update(self, game):
        super().update(game)
        self.game = game
        if hasattr(self.card_source, 'game'):
            self.card_source.game = game

        self._update_icon_states()
        self._layout_spell_family_icons()
        if settings.TOUCH_TARGET_MIN > 0:
            self._select_initial_spell_family()

        for button in self.spell_family_buttons:
            button.update()

        if self.scroll_text_list_shifter and self.scroll_text_list_shifter.get_current_selected():
            selected = self.scroll_text_list_shifter.get_current_selected()
            self.confirm_button.set_text(
                self._confirm_action_label(selected))
            self.confirm_button.update()

    def _update_icon_states(self):
        hand = self._all_free_cards()
        castable_families = self.spell_manager.get_families_with_castable_spells(hand)
        castable_names = {f.name for f in castable_families} & self.allowed_spells
        for btn in self.spell_family_buttons:
            btn.is_active = btn.family.name in castable_names

    # ── Events ──────────────────────────────────────────────────────

    def handle_events(self, events):
        # Dialogue input is modal. Handle it before any underlying picker or
        # subscreen controls.
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response and response.lower() in ('ok', 'got it!'):
                self.dialogue_box = None
                # After success dialogue, close subscreen
                if self._on_done:
                    self._on_done()
            return

        super().handle_events(events)

        if settings.TOUCH_TARGET_MIN > 0:
            changed_type = self.spell_category_tabs.handle_events(events)
            if changed_type is not None:
                self._active_spell_type = changed_type
                self.selected_spell_family = None
                self.scroll_text_list = []
                self.scroll_text_list_shifter.set_displayed_texts([])
                self._initial_family_selected = False
                self._layout_spell_family_icons()
                self._select_initial_spell_family()

        # Spell family icon clicks
        for button in self._visible_spell_buttons():
            button.handle_events(events)

            if button.clicked and button.family != self.selected_spell_family:
                self._select_spell_family(button)

        # Confirm button
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                if self.confirm_button.collide() and self.scroll_text_list_shifter:
                    selected = self.scroll_text_list_shifter.get_current_selected()
                    if selected:
                        self._confirm_spell(selected)

    # ── Confirm / server call ───────────────────────────────────────

    def _confirm_spell(self, spell):
        """Call the server endpoint to set the selected spell."""
        spell_name = spell.family.name
        url = f'{settings.SERVER_URL}{self.server_endpoint}'
        payload = {'land_id': self.land_id, 'spell_name': spell_name}
        payload.update(self.extra_payload)
        try:
            resp = requests.post(
                url,
                json=payload,
                timeout=10,
            )
            data = resp.json()
        except Exception as e:
            logger.error(f'Set spell error: {e}')
            self.make_dialogue_box(
                message='Connection error. Please try again.',
                actions=['OK'], icon='error', title='Error',
            )
            return

        if data.get('success'):
            from utils import sound
            sound.play_spell(spell_name)
            # Sync config back to proxy
            if data.get('config'):
                self.game.set_config(data['config'])
            # Show success dialogue
            card_img_objects = [c.make_icon(self.window, self.game, 0, 0)
                                for c in spell.cards]
            card_images = ([self.selected_spell_family.icon_img]
                           + [ci.front_img for ci in card_img_objects])
            self.make_dialogue_box(
                message=f'{spell_name} selected!',
                actions=['OK'], images=card_images,
                icon='magic', title='Spell Set',
            )
        else:
            self.make_dialogue_box(
                message=data.get('message', 'Failed to set spell.'),
                actions=['OK'], icon='error', title='Error',
            )

    # ── Draw ────────────────────────────────────────────────────────

    def draw(self):
        super().draw()

        selected = (
            self.scroll_text_list_shifter.get_current_selected()
            if self.scroll_text_list_shifter else None
        )
        draw_footer(
            self.window, self, '',
            show_action=bool(selected),
            show_status=False,
        )
        if settings.TOUCH_TARGET_MIN > 0:
            self.spell_category_tabs.draw()
        else:
            for spell_type, header_rect in getattr(self, '_desktop_headers', []):
                draw_section_header(self.window, spell_type, header_rect)

        for button in self._visible_spell_buttons():
            button.draw()

        if not self.scroll_text_list:
            draw_empty_detail(
                self.window,
                pygame.Rect(
                    self.scroll_x, self.scroll_y,
                    self.scroll_w, self.scroll_h),
                'Choose a spell',
                'Preview its cards, timing, target, and counter rules.',
            )

        if selected:
            self.confirm_button.draw()

        super().draw_on_top()
