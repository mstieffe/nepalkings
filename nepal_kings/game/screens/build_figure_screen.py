# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from pygame.locals import *
from collections import Counter
from config import settings
from game.components.figures.family_configs.skill_config import SKILL_KEYS
from game.components.figures.skill_display_filters import filter_figure_for_display
from game.screens.sub_screen import SubScreen
from game.components.figures.figure_manager import FigureManager
from game.components.cards.card import Card
from game.components.buttons.confirm_button import ConfirmButton
from game.components.figures.figure_db_service import FigureDbService
from game.core.card_source import GameCardSource
from utils.utils import ColorTogglePill
from utils import http_compat as requests
import logging

logger = logging.getLogger('nk.screens.build_figure')


def _is_kingdom_config_mode(mode):
    return mode in ('conquer', 'defence', 'defence_draft')


def _kingdom_mode_path(mode):
    return 'defence/draft' if mode == 'defence_draft' else mode

class BuildFigureScreen(SubScreen):
    """Screen for building a figure by selecting figures and suits."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None,
                 card_source=None, mode='duel'):
        super().__init__(window, state.game, x, y, title)

        # Initialize the figure manager and load figures
        self.figure_manager = FigureManager()

        self.state = state
        self.game = state.game
        self.card_source = card_source or GameCardSource(self.game)
        self.mode = mode

        # Map display names to internal color names
        self.color_mapping = {
            'Djungle': 'offensive',
            'Himalaya': 'defensive'
        }

        # Initialize buttons and UI components
        self.init_figure_info_box()
        self.init_color_buttons()
        self.init_figure_family_icons()
        self.init_scroll_test_list_shifter()

        self.color = "Djungle"

        # Store selected figures
        self.selected_figure_family = None
        self.selected_figures = []

        self.confirm_button = ConfirmButton(
            self.window,
            self._sx(settings.BUILD_FIGURE_CONFIRM_BUTTON_X),
            self._sy(settings.BUILD_FIGURE_CONFIRM_BUTTON_Y),
            "create!"
        )

    def reset_state(self):
        """Reset all game-specific transient state.

        Called by GameScreen._reset_game_screen_state() when switching games.
        """
        self.selected_figure_family = None
        self.selected_figures = []
        self.dialogue_box = None
        logger.debug("[BuildFigureScreen] State reset for game switch")

    def create_figure_in_db(self, selected_figure, instant_charge_advance=False):
        """Insert the selected figure into the database. Returns the server response dict."""
        if _is_kingdom_config_mode(self.mode):
            return self._create_figure_kingdom(selected_figure)

        if getattr(self.game, 'game_over', False):
            return {'success': False, 'message': 'Game is finished'}

        if self.game.action_in_progress:
            return {'success': False, 'message': 'Action already in progress'}

        self.game.lock_actions()
        try:
            # Map dummy cards in the figure to real cards in the player's hand
            real_cards = self.map_figure_cards_to_hand(selected_figure)

            if real_cards is None:
                logger.error(f"Failed to create figure: Could not find all cards in the player's hand.")
                self.game.unlock_actions()
                return {'success': False, 'message': 'Could not find all cards in hand'}

            # Update the selected figure with real cards
            selected_figure.cards = real_cards
            selected_figure.key_cards = [card for card in real_cards if card in selected_figure.key_cards]
            
            # Update number_card only if it exists
            if selected_figure.number_card is not None:
                selected_figure.number_card = next((card for card in real_cards if card == selected_figure.number_card), None)
            
            # Update upgrade_card only if it exists
            if selected_figure.upgrade_card is not None:
                selected_figure.upgrade_card = next((card for card in real_cards if card == selected_figure.upgrade_card), None)

            # Save the figure to the database
            response = FigureDbService.save_figure(
                figure=selected_figure,
                player_id=self.game.player_id,
                game_id=self.game.game_id,
                instant_charge_advance=instant_charge_advance
            )

            if response.get('success'):
                logger.debug(f"Figure {selected_figure.name} created successfully in the database.")
            else:
                logger.error(f"Failed to create figure: {response.get('message', 'Unknown error')}")
                self.game.unlock_actions()
                return response

            # (update() -> _apply_game_dict -> unlock_actions)
            self.game.update()

            return response
        except Exception:
            self.game.unlock_actions()
            raise

    # ── Kingdom (conquer / defence) figure creation ─────────────────

    def _create_figure_kingdom(self, selected_figure):
        """Build a figure via the kingdom config endpoint."""
        real_cards = self.map_figure_cards_to_hand(selected_figure)
        if real_cards is None:
            return {'success': False, 'message': 'Could not find all cards in collection'}

        selected_figure.cards = real_cards
        selected_figure.key_cards = [c for c in real_cards if c in selected_figure.key_cards]
        if selected_figure.number_card is not None:
            selected_figure.number_card = next(
                (c for c in real_cards if c == selected_figure.number_card), None)
        if selected_figure.upgrade_card is not None:
            selected_figure.upgrade_card = next(
                (c for c in real_cards if c == selected_figure.upgrade_card), None)

        card_specs = [{'suit': c.suit, 'rank': c.rank} for c in real_cards]
        card_roles = []
        for c in real_cards:
            if c in selected_figure.key_cards:
                card_roles.append('key')
            elif selected_figure.number_card and c == selected_figure.number_card:
                card_roles.append('number')
            elif selected_figure.upgrade_card and c == selected_figure.upgrade_card:
                card_roles.append('upgrade')
            else:
                card_roles.append('number')

        land_id = getattr(self.game, 'land_id', None)
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/{_kingdom_mode_path(self.mode)}/build_figure',
                json={
                    'land_id': land_id,
                    'family_name': selected_figure.family.name,
                    'name': getattr(selected_figure, 'name', selected_figure.family.name),
                    'suit': selected_figure.suit,
                    'color': getattr(selected_figure.family, 'color', selected_figure.suit),
                    'field': selected_figure.family.field,
                    'card_specs': card_specs,
                    'card_roles': card_roles,
                    'produces': getattr(selected_figure, 'produces', None),
                    'requires': getattr(selected_figure, 'requires', None),
                    'description': getattr(selected_figure, 'description', ''),
                    'upgrade_family_name': getattr(selected_figure, 'upgrade_family_name', None),
                    'checkmate': getattr(selected_figure, 'checkmate', False),
                    'cannot_be_blocked': getattr(selected_figure, 'cannot_be_blocked', False),
                    'rest_after_attack': getattr(selected_figure, 'rest_after_attack', False),
                },
                timeout=15,
            )
            result = resp.json()
            if result.get('success') and result.get('config'):
                self.game.set_config(result['config'])
            return result
        except Exception as e:
            logger.error(f'Kingdom build_figure error: {e}')
            return {'success': False, 'message': 'Connection error'}

    def _can_instant_charge_advance(self, figure):
        """
        Check if a figure with instant_charge can actually advance right now.
        Returns (can_advance, is_counter, reason) tuple.
        - can_advance: True if advancing is possible
        - is_counter: True if this would be a counter-advance
        - reason: Short description of why not (if can_advance is False)
        """
        if _is_kingdom_config_mode(self.mode):
            return False, False, 'disabled_in_kingdom_config'

        if not getattr(figure, 'instant_charge', False):
            return False, False, 'no_instant_charge'

        game = self.game

        # Cannot advance during ceasefire
        if game.ceasefire_active:
            return False, False, 'ceasefire'

        # Check if there's already an advance in progress by this player
        if game.advancing_figure_id and game.advancing_player_id == game.player_id:
            return False, False, 'already_advancing'

        # Determine if this would be a counter-advance
        is_counter = (game.advancing_figure_id is not None and
                      game.advancing_player_id != game.player_id)

        # Check battle modifiers
        modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]

        # Blitzkrieg: defender cannot counter-advance
        if 'Blitzkrieg' in modifier_types and is_counter:
            return False, True, 'blitzkrieg'

        # Peasant War / Civil War: only village figures can advance
        if 'Peasant War' in modifier_types or 'Civil War' in modifier_types:
            fig_field = getattr(figure.family, 'field', None) if hasattr(figure, 'family') else None
            if fig_field != 'village':
                return False, is_counter, 'village_only'

        # cannot_attack check
        if getattr(figure, 'cannot_attack', False):
            return False, is_counter, 'cannot_attack'

        # cannot_be_blocked check (opponent's advancing figure)
        if is_counter and game.advancing_figure_id:
            # Look up the opponent's advancing figure in the game's figures
            if hasattr(game, 'figures') and game.figures:
                for fig in game.figures:
                    if hasattr(fig, 'id') and fig.id == game.advancing_figure_id:
                        if getattr(fig, 'cannot_be_blocked', False):
                            return False, True, 'cannot_be_blocked'
                        break

        # Resource deficit check: simulate adding this figure to the player's
        # existing figures and check if it would create a deficit on any
        # resource it requires.  If so, the figure cannot advance after build.
        if figure.requires:
            resources = game.calculate_resources(self.figure_manager.families)
            sim_produces = dict(resources.get('produces', {}))
            sim_requires = dict(resources.get('requires', {}))
            for res, amt in (figure.produces or {}).items():
                sim_produces[res] = sim_produces.get(res, 0) + amt
            for res, amt in figure.requires.items():
                sim_requires[res] = sim_requires.get(res, 0) + amt
            for res in figure.requires:
                if sim_requires.get(res, 0) > sim_produces.get(res, 0):
                    return False, is_counter, 'resource_deficit'

        return True, is_counter, None

    def _display_figure_for_mode(self, figure):
        """Hide duel-only skill display in kingdom config builders."""
        if not _is_kingdom_config_mode(self.mode):
            return figure
        return filter_figure_for_display(
            figure,
            hide_checkmate=True,
            hide_instant_charge=True,
        )

    def _check_build_causes_deficit(self, figure):
        """
        Check if building this figure would cause any NEW resource deficits.
        Returns (warning_string, deficit_resource_names) if deficits would occur,
        or (None, []) if safe.
        """
        if not figure.requires and not figure.produces:
            return None, []

        resources = self.game.calculate_resources(self.figure_manager.families)
        cur_produces = resources.get('produces', {})
        cur_requires = resources.get('requires', {})

        # Simulate adding the new figure
        sim_produces = dict(cur_produces)
        sim_requires = dict(cur_requires)
        for res, amt in (figure.produces or {}).items():
            sim_produces[res] = sim_produces.get(res, 0) + amt
        for res, amt in (figure.requires or {}).items():
            sim_requires[res] = sim_requires.get(res, 0) + amt

        # Find resources that would be in deficit AFTER building
        new_deficits = []
        for res in sim_requires:
            was_deficit = cur_requires.get(res, 0) > cur_produces.get(res, 0)
            will_deficit = sim_requires[res] > sim_produces.get(res, 0)
            if will_deficit and not was_deficit:
                new_deficits.append(res)

        if not new_deficits:
            return None, []

        res_list = ", ".join(new_deficits)
        return (
            f"Warning: Building this figure will cause a deficit in: {res_list}.\n"
            f"All figures requiring these resources will be non-functional "
            f"(cannot advance or fight).",
            new_deficits
        )


    def init_scroll_test_list_shifter(self):
        """Initialize the scroll text list shifter."""
        self.make_scroll_text_list_shifter(
            self.scroll_text_list, 
            settings.BUILD_FIGURE_SCROLL_TEXT_X, 
            settings.BUILD_FIGURE_SCROLL_TEXT_Y,
            scroll_height=settings.BUILD_FIGURE_INFO_BOX_SCROLL_HEIGHT
        )


    def init_figure_family_icons(self):
        """Initialize figure family icons and their shifters.
        
        For castle families, only show the King icon (not Maharaja).
        """
        self.figure_family_buttons = {}
        
        for color in ['offensive', 'defensive']:
            families = self.figure_manager.families_by_color[color]
            buttons = []
            
            for family in families:
                # Skip Maharaja families - only show King families
                if 'Maharaja' in family.name:
                    continue
                
                buttons.append(
                    family.make_icon(
                        self.window,
                        self.game,
                        self._sx(family.build_position[0]),
                        self._sy(family.build_position[1])
                    )
                )
            
            self.figure_family_buttons[color] = buttons

    def init_color_buttons(self):
        """Initialize colour toggle pill buttons."""
        colors = ['Djungle', 'Himalaya']
        start_x = settings.BUILD_FIGURE_COLOR_BUTTON_X
        gap = settings.COLOR_TOGGLE_GAP
        self.color_buttons = []
        for i, color in enumerate(colors):
            x = start_x + i * (settings.COLOR_TOGGLE_W + gap)
            btn = ColorTogglePill(self.window, self._sx(x), self._sy(settings.BUILD_FIGURE_COLOR_BUTTON_Y), color)
            self.color_buttons.append(btn)
        self.color_buttons[0].active = True
        self.buttons += self.color_buttons

    def init_figure_info_box(self):
        """Initialize figure info box."""
        super().init_sub_box_background(
            settings.BUILD_FIGURE_INFO_BOX_X,
            settings.BUILD_FIGURE_INFO_BOX_Y,
            settings.BUILD_FIGURE_INFO_BOX_WIDTH,
            settings.BUILD_FIGURE_INFO_BOX_HEIGHT
        )
        super().init_scroll_background(
            settings.BUILD_FIGURE_INFO_BOX_SCROLL_X,
            settings.BUILD_FIGURE_INFO_BOX_SCROLL_Y,
            settings.BUILD_FIGURE_INFO_BOX_SCROLL_WIDTH,
            settings.BUILD_FIGURE_INFO_BOX_SCROLL_HEIGHT
        )

        self.build_hierarchy = pygame.image.load(settings.BUILD_HIERARCHY_IMG_PATH).convert_alpha()
        self.build_hierarchy = pygame.transform.smoothscale(
            self.build_hierarchy,
            (settings.BUILD_HIERARCHY_WIDTH, settings.BUILD_HIERARCHY_HEIGHT)
        )

    def update(self, game):
        """Update the game state and button components."""
        super().update(game)
        self.game = game
        # Keep card_source in sync for GameCardSource (duel mode)
        if hasattr(self.card_source, 'game'):
            self.card_source.game = game

        if _is_kingdom_config_mode(self.mode) or self.game.turn:
            self.confirm_button.disabled = False
        else:
            self.confirm_button.disabled = True

        # Update icon states based on available cards
        self.update_family_icon_states()

        internal_color = self.color_mapping.get(self.color, self.color)
        for button in self.figure_family_buttons[internal_color]:
            button.update()

        if self.scroll_text_list_shifter:
            selected_figure = self.scroll_text_list_shifter.get_current_selected()
            if selected_figure:
                self.confirm_button.update()

    def update_family_icon_states(self):
        """Update the active state of family icons based on whether they can be built."""
        for color in ['offensive', 'defensive']:
            for button in self.figure_family_buttons[color]:
                # Check if any figure in this family can be built with current hand
                buildable_figures = self.get_figures_in_hand(button.family)
                # Set active state: true if at least one figure can be built
                button.is_active = len(buildable_figures) > 0

    def handle_events(self, events):
        """Handle events for button interactions."""
        super().handle_events(events)

        internal_color = self.color_mapping.get(self.color, self.color)
        for button in self.figure_family_buttons[internal_color]:
            button.handle_events(events)

        if self.scroll_text_list_shifter:
            selected_figure = self.scroll_text_list_shifter.get_current_selected()

        if self.dialogue_box:

            response = self.dialogue_box.update(events)
            if response:
                
                logger.debug("Response: %s", response)
                if response == 'yes':
                    # Block regular build during forced advance
                    if getattr(self.game, 'pending_forced_advance', False):
                        self.dialogue_box = None
                        self.make_dialogue_box(
                            message="You must advance a figure this turn.\n\nUse 'build + advance' with an Instant Charge figure, or go to the field and advance an existing figure.",
                            actions=['ok'],
                            icon="error",
                            title="Must Advance"
                        )
                        return
                    # Check if player is waiting for counter spell response
                    if hasattr(self.state, 'parent_screen') and hasattr(self.state.parent_screen, 'waiting_for_counter_response'):
                        if self.state.parent_screen.waiting_for_counter_response:
                            self.dialogue_box = None
                            self.make_dialogue_box(
                                message="You cannot build a figure while waiting for opponent's response to your spell.",
                                actions=['ok'],
                                icon="error",
                                title="Action Blocked"
                            )
                            return

                    # Check if battle is active
                    if hasattr(self.game, 'is_battle_active') and self.game.is_battle_active():
                        self.dialogue_box = None
                        self.make_dialogue_box(
                            message="You cannot build a figure while a battle is in progress.",
                            actions=['ok'],
                            icon="error",
                            title="Action Blocked"
                        )
                        return
                    
                    logger.debug("Creating figure...")
                    build_result = self.create_figure_in_db(selected_figure)

                    if not build_result or not build_result.get('success'):
                        error_msg = build_result.get('message', 'Unknown error') if build_result else 'Build failed'
                        self.make_dialogue_box(
                            message=f"Failed to build figure: {error_msg}",
                            actions=['ok'],
                            icon="error",
                            title="Build Failed"
                        )
                        return

                    self.make_dialogue_box(
                        message="Your new figure has been placed on the field.",
                        actions=['to field'],
                        icon="figure",
                        title="Figure Built"
                    )

                elif response in ('build + advance', 'build + counter'):
                    # Check if player is waiting for counter spell response
                    if hasattr(self.state, 'parent_screen') and hasattr(self.state.parent_screen, 'waiting_for_counter_response'):
                        if self.state.parent_screen.waiting_for_counter_response:
                            self.dialogue_box = None
                            self.make_dialogue_box(
                                message="You cannot build a figure while waiting for opponent's response to your spell.",
                                actions=['ok'],
                                icon="error",
                                title="Action Blocked"
                            )
                            return

                    logger.debug("Creating figure with instant charge advance...")
                    build_result = self.create_figure_in_db(selected_figure, instant_charge_advance=True)

                    if not build_result or not build_result.get('success'):
                        error_msg = build_result.get('message', 'Unknown error') if build_result else 'Build failed'
                        self.make_dialogue_box(
                            message=f"Failed to build figure: {error_msg}",
                            actions=['ok'],
                            icon="error",
                            title="Build Failed"
                        )
                        return

                    # Update game state from the combined response
                    if build_result.get('game'):
                        self.game.update_from_dict(build_result['game'])

                    # Check the instant_charge result from the combined response
                    charge_result = build_result.get('instant_charge', {})
                    action_word = "counter-advanced" if response == 'build + counter' else "advanced"
                    fig_name = selected_figure.name

                    if charge_result.get('success'):
                        # Check if Civil War needs a second figure
                        if charge_result.get('civil_war_need_second'):
                            civil_war_color = charge_result.get('civil_war_color', '')
                            color_name = 'red' if civil_war_color == 'offensive' else 'black'
                            self.game.civil_war_awaiting_second = True
                            self.game.civil_war_required_color = civil_war_color
                            self.make_dialogue_box(
                                message=f"{fig_name} has been built and {action_word} toward battle!\n\nCivil War! You may select a second village figure of the same color ({color_name}).",
                                actions=['to field'],
                                icon="figure",
                                title="Instant Charge!"
                            )
                        else:
                            # Clear Civil War state
                            if hasattr(self.game, 'civil_war_awaiting_second'):
                                self.game.civil_war_awaiting_second = False
                                self.game.civil_war_required_color = None
                            # Trigger advance notification
                            self.game.pending_own_advance_notification = True
                            self.game.own_advance_figure_name = fig_name
                            self.make_dialogue_box(
                                message=f"{fig_name} has been built and {action_word} toward battle!",
                                actions=['to field'],
                                icon="figure",
                                title="Instant Charge!"
                            )
                    else:
                        # Advance failed but figure was still built
                        error_msg = charge_result.get('message', 'Advance conditions not met')
                        self.make_dialogue_box(
                            message=f"Figure was built successfully, but could not advance:\n\n{error_msg}",
                            actions=['to field'],
                            icon="error",
                            title="Advance Failed"
                        )

                elif response == 'to field':
                    self.dialogue_box = None
                    if _is_kingdom_config_mode(self.mode):
                        # Signal parent to dismiss the build subscreen
                        if hasattr(self, '_on_done') and self._on_done:
                            self._on_done()
                    else:
                        self.state.subscreen = "field"
                elif response in ['cancel', 'got it!', 'ok']:
                    self.dialogue_box = None

        else:

            for event in events:
                if event.type == MOUSEBUTTONDOWN:

                    # Handle confirm button only if a figure is selected
                    if selected_figure and self.confirm_button.collide() and not self.confirm_button.disabled:

                        # Create a FieldFigureIcon for the selected figure (without bonus)
                        from game.components.figures.figure_icon import FieldFigureIcon
                        figure_icon = FieldFigureIcon(
                            self.window,
                            self.game,
                            selected_figure,
                            is_visible=True,
                            x=0,
                            y=0,
                            all_player_figures=[selected_figure],
                            resources_data={}
                        )
                        figure_icon.show_advance_overlay = False

                        images = [figure_icon]
                        actions = ['yes', 'cancel']
                        message = "Do you want to build this figure?"
                        message_after = None

                        # Check if building this figure would cause resource deficits
                        deficit_warning, deficit_resources = self._check_build_causes_deficit(selected_figure)

                        # Load resource icons for any deficit resources
                        if deficit_resources:
                            import os
                            from config.info_scroll_settings import RESOURCE_ICON_IMG_PATH_DICT
                            for res_name in deficit_resources:
                                res_icon_path = RESOURCE_ICON_IMG_PATH_DICT.get(res_name, '')
                                if res_icon_path and os.path.exists(res_icon_path):
                                    res_icon = pygame.image.load(res_icon_path).convert_alpha()
                                    images.append(res_icon)

                        # Check if figure has instant_charge and can advance
                        can_charge, is_counter, charge_reason = self._can_instant_charge_advance(selected_figure)

                        # During forced advance, only show build+advance (not regular build)
                        is_forced_advance = getattr(self.game, 'pending_forced_advance', False)

                        if can_charge:
                            # Load the instant_charge skill icon
                            import os
                            from game.components.figures.family_configs.skill_config import SKILL_ICON_IMG_PATH_DICT
                            icon_path = SKILL_ICON_IMG_PATH_DICT.get('instant_charge', '')
                            if icon_path and os.path.exists(icon_path):
                                charge_icon = pygame.image.load(icon_path).convert_alpha()
                                images.append(charge_icon)

                            if is_counter:
                                charge_action = 'build + counter'
                                message_after = "This figure has Instant Charge and can counter-advance immediately after being built!"
                            else:
                                charge_action = 'build + advance'
                                message_after = "This figure has Instant Charge and can advance toward battle immediately after being built!"

                            if is_forced_advance:
                                # Only allow build+advance during forced advance
                                actions = [charge_action, 'cancel']
                                message = "You must advance this turn.\nBuild and advance this figure?"
                            else:
                                actions = ['yes', charge_action, 'cancel']
                        elif is_forced_advance:
                            if charge_reason == 'resource_deficit':
                                # Figure has instant charge but would have resource deficit
                                self.make_dialogue_box(
                                    message="This figure would have a resource deficit after being built and cannot advance toward battle.\n\nBuild a different figure or go to the field and advance an existing figure.",
                                    actions=['ok'],
                                    icon="error",
                                    title="Resource Deficit"
                                )
                                return
                            # Forced advance but figure has no instant charge — block build
                            self.make_dialogue_box(
                                message="You must advance a figure this turn.\n\nThis figure does not have Instant Charge — go to the field and advance an existing figure instead.",
                                actions=['ok'],
                                icon="error",
                                title="Must Advance"
                            )
                            return

                        self.make_dialogue_box(
                            message=message,
                            actions=actions,
                            images=images,
                            icon="warning" if deficit_warning else "question",
                            title="Resource Deficit Warning" if deficit_warning else "Create Figure",
                            message_after_images=(deficit_warning + "\n\n" + message_after) if (deficit_warning and message_after) else (deficit_warning or message_after),
                        )
                        #print("making dialogue box")
                    elif selected_figure and self.confirm_button.collide() and self.confirm_button.disabled:
                        self.make_dialogue_box(
                            message="You can only build figures on your turn.",
                            actions=['ok'],
                            icon="error",
                            title="Not Your Turn"
                        )
                    


                    for button in self.color_buttons:
                        if button.collide():
                            self.update_color_selection(button)

                    internal_color = self.color_mapping.get(self.color, self.color)
                    for button in self.figure_family_buttons[internal_color]:
                        if button.collide():
                            self.update_figure_family_selection(button)

    def update_color_selection(self, button):
        """Update color selection when a color button is clicked."""
        for other_button in self.buttons:
            other_button.active = False
        button.active = True
        self.color = button.text

    def update_figure_family_selection(self, button):
        """Update figure family selection."""
        self.selected_figure_family = button.family
        internal_color = self.color_mapping.get(self.color, self.color)
        for other_button in self.figure_family_buttons[internal_color]:
            other_button.clicked = False
        button.clicked = True
        
        figures = self.get_figures_in_hand(button.family)
        if figures:
            self.selected_figures = figures
            self.scroll_text_list = [{"title": figure.name,
                                      "figure_type": f"{figure.family.field.capitalize()} Figure",
                                      "text": figure.family.description,
                                      "power": figure.get_value(),
                                      "support": figure.get_battle_bonus(),
                                      "produces": figure.produces if figure.produces else None,
                                      "requires": figure.requires if figure.requires else None,
                                      **{k: getattr(figure, k, False) for k in SKILL_KEYS},
                                      "cards": figure.cards,
                                      "content": figure}
                                     for figure in figures]
            self.scroll_text_list.sort(key=lambda x: x["power"], reverse=True)
        else:
            # Get figure instances to show their attributes even when cards are missing
            self.scroll_text_list = []
            for suit in button.family.suits:
                for figure in button.family.get_figures_by_suit(suit):
                    display_figure = self._display_figure_for_mode(figure)
                    self.scroll_text_list.append({
                        "title": button.family.name,
                        "figure_type": f"{display_figure.family.field.capitalize()} Figure",
                        "text": display_figure.family.description,
                        # Don't show power when cards are missing
                        "support": display_figure.get_battle_bonus(),
                        "produces": display_figure.produces if display_figure.produces else None,
                        "requires": display_figure.requires if display_figure.requires else None,
                        **{k: getattr(display_figure, k, False) for k in SKILL_KEYS},
                        "suit": suit,
                        "cards": self.get_given_cards_for_figure(display_figure),
                        "missing_cards": self.get_missing_cards_converted_ZK_for_figure(display_figure),
                        "content": None,
                        "_sort_power": display_figure.get_value()
                    })
            self.scroll_text_list.sort(key=lambda x: x["_sort_power"], reverse=True)
        self.scroll_text_list_shifter.set_displayed_texts(self.scroll_text_list)

    def draw(self):
        """Draw the screen, including buttons and background."""
        super().draw()

        self.window.blit(self.build_hierarchy, self._spos(settings.BUILD_HIERARCHY_X, settings.BUILD_HIERARCHY_Y))

        internal_color = self.color_mapping.get(self.color, self.color)
        # Z-order layering: regular → selected → hovered (so info boxes appear on top)
        all_regular = []
        all_selected = []
        all_hovered = None
        for button in self.figure_family_buttons[internal_color]:
            if button.hovered:
                all_hovered = button
            elif button.clicked:
                all_selected.append(button)
            else:
                all_regular.append(button)

        for button in all_regular:
            button.draw()
        for button in all_selected:
            button.draw()
        if all_hovered:
            all_hovered.draw()

        if self.scroll_text_list_shifter:
            selected_figure = self.scroll_text_list_shifter.get_current_selected()
            if selected_figure:
                self.confirm_button.draw()

        super().draw_on_top()

    def map_figure_cards_to_hand(self, figure):
        """
        Map dummy cards in the figure to real cards in the player's hand.
        Handles duplicate cards correctly by tracking which cards have been used.

        :param figure: The Figure object with dummy cards.
        :return: A list of real Card objects mapped from the player's hand.
        """
        main_cards, side_cards = self.card_source.get_cards()
        hand_cards = main_cards + side_cards

        # Create a list of available cards (will remove as we use them)
        available_cards = hand_cards.copy()

        # Map figure cards to real cards in the hand
        real_cards = []
        for dummy_card in figure.cards:
            # Find the first matching card in available_cards
            real_card = None
            for i, card in enumerate(available_cards):
                if card.to_tuple() == dummy_card.to_tuple():
                    real_card = card
                    # Remove this card from available so we don't use it twice
                    available_cards.pop(i)
                    break
            
            if real_card:
                real_cards.append(real_card)
            else:
                logger.debug(f"Card {dummy_card} not found in hand.")
                return None  # Return None if any card is not found

        return real_cards


    def get_figures_in_hand(self, figure_family):
        """Get figures in the player's hand."""
        # Get all cards in the player's hand
        main_cards, side_cards = self.card_source.get_cards()
        hand_cards = main_cards + side_cards

        # Count occurrences of each card in the hand
        hand_counter = Counter(card.to_tuple() for card in hand_cards)

        possible_figures = []
        for figure in figure_family.figures:
            # Count occurrences of required cards for the figure
            figure_counter = Counter(card.to_tuple() for card in figure.cards)
            # Check if the hand has enough cards to build the figure
            if all(hand_counter[card] >= count for card, count in figure_counter.items()):
                possible_figures.append(self._display_figure_for_mode(figure))

        return possible_figures
    

    
    def get_missing_cards(self, figure):
        """Get missing cards for a figure."""
        # Get all cards in the player's hand
        main_cards, side_cards = self.card_source.get_cards()
        hand_cards = main_cards + side_cards

        # Count occurrences of each card in the hand using tuples
        hand_counter = Counter(card.to_tuple() for card in hand_cards)

        # Count occurrences of required cards for the figure using tuples
        figure_counter = Counter(card.to_tuple() for card in figure.cards)

        # Get missing cards for the figure
        missing_cards = []
        for card_tuple, count in figure_counter.items():
            if hand_counter[card_tuple] < count:
                # Find the original Card instances that match the missing card tuples
                for card in figure.cards:
                    if card.to_tuple() == card_tuple:
                        missing_cards.extend([card] * (count - hand_counter[card_tuple]))
                        break

        return missing_cards
    
    def get_given_cards(self, figure_family, suit):
        """Get given cards for the first figure variant in a family/suit."""
        figure = figure_family.get_figures_by_suit(suit)[0]
        return self.get_given_cards_for_figure(figure)

    def get_given_cards_for_figure(self, figure):
        """Get given cards for a specific figure."""
        main_cards, side_cards = self.card_source.get_cards()
        hand_cards = main_cards + side_cards
        hand_counter = Counter(card.to_tuple() for card in hand_cards)

        # Count occurrences of required cards for the figure using tuples
        figure_counter = Counter(card.to_tuple() for card in figure.cards)

        # Get given cards for the figure
        given_cards = []
        for card_tuple, count in figure_counter.items():
            if hand_counter[card_tuple] > 0:
                # Find the original Card instances that match the given card tuples
                given_count = min(count, hand_counter[card_tuple])
                for card in figure.cards:
                    if card.to_tuple() == card_tuple and given_count > 0:
                        given_cards.append(card)
                        given_count -= 1

        return given_cards
    
    def get_missing_cards_converted_ZK(self, figure_family, suit):
        """Get missing cards for all figures in a family."""
        figure = figure_family.get_figures_by_suit(suit)[0]
        return self.get_missing_cards_converted_ZK_for_figure(figure)

    def get_missing_cards_converted_ZK_for_figure(self, figure):
        """Get missing cards for a specific figure, converting ZK cards."""
        missing_cards = []
        for card in self.get_missing_cards(figure):
            if card.is_ZK:
                missing_cards.append(Card('ZK', figure.suit, 0))
            else:
                missing_cards.append(card)
        return missing_cards
