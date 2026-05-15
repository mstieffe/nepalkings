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
from utils import http_compat as requests
import logging

logger = logging.getLogger('nk.screens.prelude_spell')


class PreludeSpellScreen(SubScreen):
    """SubScreen for selecting a prelude or counter spell in kingdom config."""

    def __init__(self, window, state, x=0.0, y=0.0, title=None,
                 card_source=None, mode='conquer',
                 allowed_spells=None, server_endpoint=None, land_id=None,
                 extra_payload=None):
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
        self.allowed_spells = set(allowed_spells or [])
        self.server_endpoint = server_endpoint
        self.land_id = land_id
        self.extra_payload = dict(extra_payload or {})

        # Spell manager
        self.spell_manager = SpellManager()

        # UI components
        self.init_spell_info_box()
        self.init_spell_family_icons()
        self.init_scroll_test_list_shifter()

        self.selected_spell_family = None

        self.confirm_button = ConfirmButton(
            self.window,
            self._sx(settings.CAST_SPELL_CONFIRM_BUTTON_X),
            self._sy(settings.CAST_SPELL_CONFIRM_BUTTON_Y),
            "select!"
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

    def init_spell_family_icons(self):
        """Create clickable icons for each allowed spell family, grouped by type."""
        self.spell_family_buttons = []
        all_families = self.spell_manager.get_all_families()

        families_by_effect = {'greed': [], 'enchantment': [], 'tactics': []}
        for family in all_families:
            if family.name in self.allowed_spells and family.type in families_by_effect:
                families_by_effect[family.type].append(family)

        effect_types_order = ['greed', 'enchantment', 'tactics']

        self.type_label_font = settings.get_font(settings.SPELL_TYPE_LABEL_FONT_SIZE)
        self.type_labels = {}
        self.type_label_positions = {}

        for row_index, effect_type in enumerate(effect_types_order):
            families_in_row = families_by_effect[effect_type]

            label_text = effect_type.capitalize()
            label_surface = self.type_label_font.render(label_text, True, settings.SPELL_TYPE_LABEL_COLOR)
            label_surface = pygame.transform.rotate(label_surface, 90)
            self.type_labels[effect_type] = label_surface

            row_y = settings.CAST_SPELL_ICON_START_Y + row_index * settings.SPELL_ICON_DELTA_Y
            label_rect = label_surface.get_rect()
            label_rect.midleft = self._spos(settings.SPELL_TYPE_LABEL_X, row_y)
            self.type_label_positions[effect_type] = label_rect.topleft

            for col_index, family in enumerate(families_in_row):
                btn_x = settings.CAST_SPELL_ICON_START_X + col_index * settings.SPELL_ICON_DELTA_X
                btn_y = settings.CAST_SPELL_ICON_START_Y + row_index * settings.SPELL_ICON_DELTA_Y
                button = family.make_icon(self.window, self.game, self._sx(btn_x), self._sy(btn_y))
                self.spell_family_buttons.append(button)

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

    # ── Update ──────────────────────────────────────────────────────

    def update(self, game):
        super().update(game)
        self.game = game
        if hasattr(self.card_source, 'game'):
            self.card_source.game = game

        self._update_icon_states()

        for button in self.spell_family_buttons:
            button.update()

        if self.scroll_text_list_shifter and self.scroll_text_list_shifter.get_current_selected():
            self.confirm_button.update()

    def _update_icon_states(self):
        hand = self._all_free_cards()
        castable_families = self.spell_manager.get_families_with_castable_spells(hand)
        castable_names = {f.name for f in castable_families} & self.allowed_spells
        for btn in self.spell_family_buttons:
            btn.is_active = btn.family.name in castable_names

    # ── Events ──────────────────────────────────────────────────────

    def handle_events(self, events):
        super().handle_events(events)

        # Dialogue box takes priority
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response and response.lower() in ('ok', 'got it!'):
                self.dialogue_box = None
                # After success dialogue, close subscreen
                if self._on_done:
                    self._on_done()
            return

        # Spell family icon clicks
        for button in self.spell_family_buttons:
            button.handle_events(events)

            if button.clicked and button.family != self.selected_spell_family:
                self.selected_spell_family = button.family
                castable = self.get_spells_in_collection(button.family)

                if castable:
                    self.scroll_text_list = [
                        {
                            'title': spell.name,
                            'text': spell.family.description,
                            'cards': spell.cards,
                            'spell_type': self._format_spell_type(spell.family.type),
                            'counterable': spell.counterable,
                            'ceasefire': spell.possible_during_ceasefire,
                            'content': spell,
                        }
                        for spell in castable
                    ]
                else:
                    self.scroll_text_list = []
                    for spell in button.family.spells:
                        given, missing = self.get_given_and_missing_cards(spell)
                        self.scroll_text_list.append({
                            'title': spell.name,
                            'text': spell.family.description,
                            'spell_type': self._format_spell_type(spell.family.type),
                            'counterable': spell.counterable,
                            'ceasefire': spell.possible_during_ceasefire,
                            'cards': given,
                            'missing_cards': missing,
                            'content': None,
                        })

                if self.scroll_text_list_shifter:
                    self.scroll_text_list_shifter.set_displayed_texts(self.scroll_text_list)

                for other in self.spell_family_buttons:
                    if other != button:
                        other.clicked = False

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

        for effect_type, label_surf in self.type_labels.items():
            self.window.blit(label_surf, self.type_label_positions[effect_type])

        for button in self.spell_family_buttons:
            button.draw()

        if self.scroll_text_list_shifter and self.scroll_text_list_shifter.get_current_selected():
            self.confirm_button.draw()

        super().draw_on_top()
