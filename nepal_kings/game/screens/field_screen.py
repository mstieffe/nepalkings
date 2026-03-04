import pygame
from pygame.locals import *
from config import settings
from game.screens.sub_screen import SubScreen
from game.components.figures.figure_manager import FigureManager
from game.components.figures.figure_icon import FieldFigureIcon
from game.components.figure_detail_box import FigureDetailBox
from game.components.cards.card_img import CardImg
from utils.figure_service import pickup_figure, upgrade_figure


class FieldScreen(SubScreen):
    """Screen for displaying figures on the field."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        self.figure_manager = FigureManager()

        self.figures = []  # List to store the player's figures
        self.figure_icons = []  # List to store figure icons for rendering
        self.icon_cache = {}  # Cache to store pre-rendered icons
        self.last_figure_ids = set()  # Track the last set of figure IDs
        self.last_enchantment_state = {}  # Track enchantment state for each figure
        self.last_player_id = None  # Track the last player ID to detect player changes
        self.figure_detail_box = None  # Detail box for selected figure
        self.figure_pending_pickup = None  # Figure waiting for pickup confirmation
        self.figure_pending_upgrade = None  # Figure waiting for upgrade confirmation
        self.figure_pending_defender_selection = None  # Figure waiting for defender selection confirmation
        self._pending_advance_figure = None  # Figure waiting for advance confirmation
        
        # Defender selection mode flag (True when player needs to select defender vs opponent advance)
        self.defender_selection_mode = False
        
        # Cache for opponent cards (for All Seeing Eye spell)
        self.opponent_card_cache = []  # List of pre-rotated card surfaces
        self.last_opponent_card_ids = set()  # Track opponent card IDs to detect changes
        
        # Initialize categorized figures structure
        self.categorized_figures = {
            'self': {'castle': [], 'village': [], 'military': []}, 
            'opponent': {'castle': [], 'village': [], 'military': []}
        }

        # Font for field titles
        self.field_title_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE)
        self.board_title_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_BOARD_TITLE_FONT_SIZE)
        self.board_title_font.set_bold(True)
        
        # Font for target selection prompt
        self.target_prompt_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE + 4)
        self.target_prompt_font.set_bold(True)
        
        # Cache All Seeing Eye status to avoid repeated expensive checks
        self.cached_all_seeing_eye_status = None
        self.cached_opponent_all_seeing_eye_status = None
        self.last_all_seeing_eye_check = 0
        self.all_seeing_eye_check_interval = 1000  # Check every 1 second instead of every frame
        self._last_all_seeing_eye_status = None  # Track previous status for change detection
        
        # Load slot icons for compartment backgrounds
        self.slot_icons = self._load_slot_icons()
        
        # Load All Seeing Eye icon for displaying active spell status
        eye_icon_path = 'img/spells/icons/eye.png'
        self.all_seeing_eye_icon = pygame.image.load(eye_icon_path).convert_alpha()
        # Scale to match board title font size
        icon_size = settings.FIELD_BOARD_TITLE_FONT_SIZE
        self.all_seeing_eye_icon = pygame.transform.smoothscale(self.all_seeing_eye_icon, (icon_size, icon_size))

        # Pre-load battle modifier icons for error dialogues
        self._battle_modifier_icons = {}
        self._load_battle_modifier_icons()

        self.init_field_compartments()

    def reset_state(self):
        """Reset all game-specific transient state.

        Called by GameScreen._reset_game_screen_state() when switching games.
        """
        self.figures = []
        self.figure_icons = []
        self.icon_cache = {}
        self.last_figure_ids = set()
        self.last_enchantment_state = {}
        self.last_player_id = None
        self.figure_detail_box = None
        self.figure_pending_pickup = None
        self.figure_pending_upgrade = None
        self.figure_pending_defender_selection = None
        self._pending_advance_figure = None
        self.defender_selection_mode = False
        self.opponent_card_cache = []
        self.last_opponent_card_ids = set()
        self.cached_all_seeing_eye_status = None
        self.cached_opponent_all_seeing_eye_status = None
        self._last_all_seeing_eye_status = None
        self.dialogue_box = None
        self._reset_defender_selectable()
        print("[FieldScreen] State reset for game switch")

    def update(self, game):
        """Update the game state and load figures."""
        super().update(game)

        self.game = game
        self.load_figures()  # Load figures whenever the game state updates

    def update_hover_state(self):
        """Update hover state for figure icons. Called only on mouse motion."""
        # Update hover state: only one figure can be hovered at a time
        # Check in reverse order (topmost figures get priority)
        hovered_icon = None
        for icon in reversed(self.figure_icons):
            if icon.collide() and hovered_icon is None:
                icon.hovered = True
                hovered_icon = icon
            else:
                icon.hovered = False

    def _load_battle_modifier_icons(self):
        """Pre-load battle modifier icons for use in error dialogues."""
        import os
        icon_dir = settings.SPELL_ICON_IMG_DIR
        icon_size = settings.BATTLE_MODIFIER_ICON_SIZE
        modifier_types = {
            'Civil War': 'civil_war.png',
            'Peasant War': 'peasant_war.png',
            'Blitzkrieg': 'blitzkrieg.png',
        }
        for modifier_name, filename in modifier_types.items():
            icon_path = os.path.join(icon_dir, filename)
            if os.path.exists(icon_path):
                img = pygame.image.load(icon_path).convert_alpha()
                img = pygame.transform.smoothscale(img, (icon_size, icon_size))
                self._battle_modifier_icons[modifier_name] = img

    def _get_modifier_icon_images(self, modifier_name):
        """Return a list with the modifier icon surface if available, else empty list."""
        icon = self._battle_modifier_icons.get(modifier_name)
        return [icon] if icon else []

    def _load_slot_icons(self):
        """Load and prepare slot icons for compartment backgrounds."""
        slot_icons = {}
        for field_type, img_path in settings.SLOT_ICON_IMG_PATH_DICT.items():
            # Load image
            icon = pygame.image.load(img_path).convert_alpha()
            
            # Set transparency
            icon.set_alpha(settings.SLOT_ICON_TRANSPARENCY)
            
            # Scale to fit compartment (leave some padding)
            target_size = int(settings.FIELD_ICON_WIDTH * 0.7)
            icon = pygame.transform.smoothscale(icon, (target_size, target_size*1.5))
            
            slot_icons[field_type] = icon
        return slot_icons

    def init_field_compartments(self):
        """Initialize compartments for the field screen.
        generates rectangle of size settings.FIELD_ICON_WIDTH and settings.FIELD_HEIGHT. Fill it with settings.FIELD_FILL_COLOR and make a border with settings.FIELD_BORDER_COLOR of width settings.FIELD_BORDER_WIDTH.
        Make 3 fields each for the swlf and opponent, starting at position settings.FIELD_SELF_X, settings.FIELD_OPPONENT_X and y position settings.FIELD_Y.
        Set transparency of the field to settings.FIELD_TRANSPARENCY.
        Margin in x direction is settings.FIELD_ICON_PADDING
        """
        compartments = {'self': {}, 'opponent': {}}

        compartments['self']['castle'] = pygame.Rect(settings.FIELD_SELF_X, settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['self']['village'] = pygame.Rect(settings.FIELD_SELF_X + settings.FIELD_ICON_WIDTH + settings.FIELD_ICON_PADDING_X, settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['self']['military'] = pygame.Rect(settings.FIELD_SELF_X + 2*(settings.FIELD_ICON_WIDTH + settings.FIELD_ICON_PADDING_X), settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)

        compartments['opponent']['military'] = pygame.Rect(settings.FIELD_OPPONENT_X, settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['opponent']['village'] = pygame.Rect(settings.FIELD_OPPONENT_X + settings.FIELD_ICON_WIDTH + settings.FIELD_ICON_PADDING_X, settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['opponent']['castle'] = pygame.Rect(settings.FIELD_OPPONENT_X + 2*(settings.FIELD_ICON_WIDTH + settings.FIELD_ICON_PADDING_X), settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)

        self.compartments = compartments

    def _get_opponent_hand_cards(self):
        """Get opponent's hand cards (not in deck, not part of figure)."""
        opponent_id = self.game.opponent_player.get('id') if self.game.opponent_player else None
        if not opponent_id:
            return [], []
        
        # Filter main cards (cards are dictionaries from server)
        opponent_main_cards = [
            card for card in self.game.main_cards
            if card.get('player_id') == opponent_id and not card.get('in_deck') and not card.get('part_of_figure')
        ]
        
        # Filter side cards (cards are dictionaries from server)
        opponent_side_cards = [
            card for card in self.game.side_cards
            if card.get('player_id') == opponent_id and not card.get('in_deck') and not card.get('part_of_figure')
        ]
        
        return opponent_main_cards, opponent_side_cards

    def load_figures(self):
        """Retrieve all figures for the current player."""
        try:
            # Check if player has changed and clear cache if so
            if self.last_player_id != self.game.player_id:
                self.icon_cache.clear()
                self.last_figure_ids.clear()
                self.last_enchantment_state.clear()
                self.last_player_id = self.game.player_id
            
            # Load figures using the game's `get_figures` method
            families = self.figure_manager.families

            # Categorize figures into compartments
            categorized_figures = {
                'self': {'castle': [], 'village': [], 'military': []}, 
                'opponent': {'castle': [], 'village': [], 'military': []}
            }
            
            self_figures = self.game.get_figures(families)
            opponent_figures = self.game.get_figures(families, is_opponent=True)
            
            for figure in self_figures:
                if figure.family.field == 'castle':
                    categorized_figures['self']['castle'].append(figure)
                elif figure.family.field == 'village':
                    categorized_figures['self']['village'].append(figure)
                elif figure.family.field == 'military':
                    categorized_figures['self']['military'].append(figure)
            for figure in opponent_figures:
                if figure.family.field == 'castle':
                    categorized_figures['opponent']['castle'].append(figure)
                elif figure.family.field == 'village':
                    categorized_figures['opponent']['village'].append(figure)
                elif figure.family.field == 'military':
                    categorized_figures['opponent']['military'].append(figure)
                    
            self.figures = self_figures + opponent_figures
            self.categorized_figures = categorized_figures

            # Get current figure IDs and enchantment states
            current_figure_ids = {figure.id for figure in self.figures}
            current_enchantment_state = self._get_enchantment_state()

            # Regenerate icons if figure IDs or enchantments have changed
            figures_changed = current_figure_ids != self.last_figure_ids
            enchantments_changed = current_enchantment_state != self.last_enchantment_state
            
            # Check if All Seeing Eye status changed (need to regenerate icons for visibility)
            all_seeing_eye_changed = (self.cached_all_seeing_eye_status != self._last_all_seeing_eye_status)
            
            if figures_changed or enchantments_changed or all_seeing_eye_changed:
                if all_seeing_eye_changed:
                    print(f"[FIELD_SCREEN] All Seeing Eye status changed: {self._last_all_seeing_eye_status} -> {self.cached_all_seeing_eye_status}")
                    # Clear icon cache for opponent figures to regenerate with new visibility
                    self.icon_cache.clear()
                    self._last_all_seeing_eye_status = self.cached_all_seeing_eye_status
                if enchantments_changed:
                    print(f"[FIELD_SCREEN] Enchantments changed, regenerating icons")
                    print(f"[FIELD_SCREEN] Old: {self.last_enchantment_state}")
                    print(f"[FIELD_SCREEN] New: {current_enchantment_state}")
                    
                    # Clear cache for figures whose enchantments changed
                    for figure_id in current_figure_ids:
                        old_enchant = self.last_enchantment_state.get(figure_id)
                        new_enchant = current_enchantment_state.get(figure_id)
                        if old_enchant != new_enchant:
                            if figure_id in self.icon_cache:
                                print(f"[FIELD_SCREEN] Clearing cache for figure {figure_id} due to enchantment change")
                                del self.icon_cache[figure_id]
                
                # Remove stale entries from icon_cache (destroyed figures)
                stale_ids = self.last_figure_ids - current_figure_ids
                for stale_id in stale_ids:
                    if stale_id in self.icon_cache:
                        del self.icon_cache[stale_id]
                
                # check if the figure is opponent or not
                self._generate_figure_icons()
                self.last_figure_ids = current_figure_ids
                self.last_enchantment_state = current_enchantment_state
        except Exception as e:
            print(f"Error loading figures: {e}")

    def _get_enchantment_state(self):
        """
        Create a snapshot of current enchantment state for all figures.
        Returns a dict mapping figure_id to tuple of enchantment data.
        """
        enchantment_state = {}
        for figure in self.figures:
            if hasattr(figure, 'active_enchantments') and figure.active_enchantments:
                # Create a hashable representation of enchantments
                enchantments_tuple = tuple(
                    (e.get('spell_name'), e.get('power_modifier'))
                    for e in figure.active_enchantments
                )
                enchantment_state[figure.id] = enchantments_tuple
            else:
                enchantment_state[figure.id] = None
        return enchantment_state

    def _generate_figure_icons(self, is_visible=True):
        """Generate and cache icons for the current figures."""


        
        self.figure_icons = []
        
        # Collect all player figures for battle bonus calculation
        all_player_figures = []
        for field_type, figures in self.categorized_figures['self'].items():
            all_player_figures.extend(figures)
        
        # Collect all opponent figures for their battle bonus calculation
        all_opponent_figures = []
        for field_type, figures in self.categorized_figures['opponent'].items():
            all_opponent_figures.extend(figures)
        
        # Calculate resources for both self and opponent
        # Use the cached figure_manager instead of creating a new one
        try:
            families = self.figure_manager.families
            resources_data = self.game.calculate_resources(families, is_opponent=False)
            opponent_resources_data = self.game.calculate_resources(families, is_opponent=True)
        except Exception as e:
            resources_data = None
            opponent_resources_data = None

        # Check if current player has cast "All Seeing Eye" spell
        # This makes opponent figures visible to the current player
        # Use cached status if available, otherwise check and cache
        current_time = pygame.time.get_ticks()
        if self.cached_all_seeing_eye_status is None or current_time - self.last_all_seeing_eye_check > self.all_seeing_eye_check_interval:
            self.cached_all_seeing_eye_status = self.game.has_active_all_seeing_eye()
            self.last_all_seeing_eye_check = current_time
        
        player_has_all_seeing_eye = self.cached_all_seeing_eye_status

        for category, compartments in self.categorized_figures.items():
            for field_type, figures in compartments.items():
                for figure in figures:
                    # Determine which figures and resources to use based on category
                    figures_list = all_opponent_figures if category == 'opponent' else all_player_figures
                    resources = opponent_resources_data if category == 'opponent' else resources_data
                    
                    # Determine visibility: 
                    # - Own figures (category == 'self') are always visible
                    # - Opponent figures are visible if:
                    #   * They are Maharajas (always visible)
                    #   * Current player cast All Seeing Eye (reveals opponent figures)
                    is_visible = (category == 'self' or 
                                  figure.name in ['Himalaya Maharaja', 'Djungle Maharaja'] or
                                  (category == 'opponent' and player_has_all_seeing_eye))
                    
                    if figure.id not in self.icon_cache:
                        self.icon_cache[figure.id] = FieldFigureIcon(
                            window=self.window,
                            game=self.game,
                            figure=figure,
                            is_visible=is_visible,
                            all_player_figures=figures_list,
                            resources_data=resources,
                        )
                    else:
                        # Update cached icon with new figure reference (in case enchantments changed)
                        self.icon_cache[figure.id].figure = figure
                        self.icon_cache[figure.id].game = self.game
                        # Update visibility and recalculate battle bonus for cached icon
                        self.icon_cache[figure.id].is_visible = is_visible
                        self.icon_cache[figure.id].battle_bonus_received = self.icon_cache[figure.id]._calculate_battle_bonus_received(figures_list)
                        self.icon_cache[figure.id].has_deficit = self.icon_cache[figure.id]._check_resource_deficit(resources)
                    self.figure_icons.append(self.icon_cache[figure.id])

    def handle_events(self, events):
        """Handle events for interacting with the field."""
        super().handle_events(events)
        
        # Update hover state only on mouse motion to improve performance
        for event in events:
            if event.type == pygame.MOUSEMOTION:
                self.update_hover_state()
                break
        
        # Handle dialogue box events first (before target selection mode check)
        # This ensures auto-closing dialogues work even during target selection
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response == 'auto_close':
                # Auto-close: just close dialogue and continue to other event handling
                self.dialogue_box = None
            elif response:
                # Remember the current dialogue so we can detect if a new one was created
                dialogue_before_response = self.dialogue_box
                # Button clicked - process the response
                if response == 'yes':
                    # Check if player is waiting for counter spell response
                    if hasattr(self.state, 'parent_screen') and hasattr(self.state.parent_screen, 'waiting_for_counter_response'):
                        if self.state.parent_screen.waiting_for_counter_response:
                            self.dialogue_box = None
                            self.make_dialogue_box(
                                message="You cannot pickup or upgrade figures while waiting for opponent's response to your spell.",
                                actions=['ok'],
                                icon="error",
                                title="Action Blocked"
                            )
                            return

                    # Check if battle is active
                    if hasattr(self.game, 'is_battle_active') and self.game.is_battle_active():
                        self.dialogue_box = None
                        self.make_dialogue_box(
                            message="You cannot pickup or upgrade figures while a battle is in progress.",
                            actions=['ok'],
                            icon="error",
                            title="Action Blocked"
                        )
                        return
                    
                    # Check which action is pending
                    if self.figure_pending_pickup:
                        # User confirmed pickup
                        try:
                            # Call server to pick up the figure
                            result = pickup_figure(
                                self.figure_pending_pickup.id,
                                self.game.player_id,
                                self.game.game_id
                            )
                            
                            if result.get('success'):
                                # Success message
                                card_count = result.get('main_card_count', 0) + result.get('side_card_count', 0)
                                print(f"Successfully picked up {self.figure_pending_pickup.name}. {card_count} cards returned to hand.")
                                
                                # Trigger a game update to refresh the state
                                # This will reload figures and cards from the server
                                self.state.set_msg(f"Picked up {self.figure_pending_pickup.name}. {card_count} cards returned to your hand.")
                                
                            else:
                                # Show error message
                                error_msg = result.get('message', 'Unknown error')
                                print(f"Failed to pick up figure: {error_msg}")
                                self.state.set_msg(f"Failed to pick up figure: {error_msg}")
                                
                        except Exception as e:
                            print(f"Error picking up figure: {str(e)}")
                            self.state.set_msg(f"Error picking up figure: {str(e)}")
                        
                        # Close the detail box and dialogue box
                        self.figure_detail_box = None
                        for icon in self.figure_icons:
                            icon.clicked = False
                        self.figure_pending_pickup = None
                    
                    elif getattr(self, '_pending_advance_figure', None):
                        # User confirmed advance
                        figure = self._pending_advance_figure
                        self._pending_advance_figure = None
                        from utils.game_service import advance_figure
                        result = advance_figure(
                            self.game.game_id,
                            self.game.player_id,
                            figure.id
                        )
                        if result.get('success'):
                            print(f"[FIELD] Advanced {figure.name} successfully")
                            self.state.set_msg(f"Advanced {figure.name} toward battle!")
                            # Update game state from response
                            if result.get('game'):
                                self.game.update_from_dict(result['game'])
                            # Reload figures to refresh icons
                            self.load_figures()
                            
                            # Check if Civil War needs a second figure
                            if result.get('civil_war_need_second'):
                                civil_war_color = result.get('civil_war_color', '')
                                color_name = 'red' if civil_war_color == 'offensive' else 'black'
                                self.game.civil_war_awaiting_second = True
                                self.game.civil_war_required_color = civil_war_color
                                cw_icons = self._get_modifier_icon_images('Civil War')
                                self.make_dialogue_box(
                                    message=f"Civil War! You may select a second village figure of the same color ({color_name}), or fight with only one figure.",
                                    actions=['select second', 'skip'],
                                    images=cw_icons if cw_icons else None,
                                    icon="magic" if not cw_icons else None,
                                    title="Civil War - Second Figure"
                                )
                            else:
                                # Clear Civil War second pick state if it was active
                                if hasattr(self.game, 'civil_war_awaiting_second'):
                                    self.game.civil_war_awaiting_second = False
                                    self.game.civil_war_required_color = None
                                # Clear forced advance state if it was a forced advance
                                if self.game.forced_advance_dialogue_shown:
                                    self.game.pending_forced_advance = False
                                # Trigger advance notification check (Blitzkrieg needs the combined dialogue)
                                self.game.pending_own_advance_notification = True
                                self.game.own_advance_figure_name = figure.name
                        else:
                            error_msg = result.get('message', 'Unknown error')
                            print(f"[FIELD] Failed to advance: {error_msg}")
                            self.make_dialogue_box(
                                message=f"Cannot advance: {error_msg}",
                                actions=['ok'],
                                icon="error",
                                title="Advance Failed"
                            )

                    elif self.figure_pending_defender_selection:
                        # User confirmed defender selection
                        target_figure = self.figure_pending_defender_selection
                        from utils.game_service import select_defender
                        result = select_defender(
                            self.game.game_id,
                            self.game.player_id,
                            target_figure.id
                        )
                        
                        if result.get('success'):
                            # Check if this was a deficit auto-loss
                            if result.get('deficit_loss'):
                                # Defender's figure had a deficit — they auto-lose
                                deficit_fig_name = result.get('deficit_figure_name', 'Unknown')
                                winner = result.get('winner', 'You')
                                points = result.get('points', 10)
                                # Update game state from response
                                if result.get('game'):
                                    self.game.update_from_dict(result['game'])
                                self.load_figures()
                                self.defender_selection_mode = False
                                self._reset_defender_selectable()
                                self.game.pending_defender_selection = False
                                # Clear Civil War state
                                if hasattr(self.game, 'civil_war_defender_second'):
                                    self.game.civil_war_defender_second = False
                                    self.game.civil_war_required_color = None
                                # Mark fold result as shown so check_fold_result() doesn't double-show
                                self.game.fold_result_shown = True
                                new_round = self.game.current_round
                                self.make_dialogue_box(
                                    message=f"Opponent's {deficit_fig_name} has a resource deficit and cannot fight!\n\n{winner} wins {points} points.\n\nRound {new_round} begins.",
                                    actions=['ok'],
                                    icon="magic",
                                    title="Resource Deficit — Victory!"
                                )
                            # Check if Civil War needs a second defender
                            elif result.get('civil_war_need_second'):
                                civil_war_color = result.get('civil_war_color', '')
                                color_name = 'red' if civil_war_color == 'offensive' else 'black'
                                self.game.civil_war_defender_second = True
                                self.game.civil_war_required_color = civil_war_color
                                cw_icons = self._get_modifier_icon_images('Civil War')
                                self.make_dialogue_box(
                                    message=f"Civil War! You may select a second opponent village figure of the same color ({color_name}), or proceed with only one.",
                                    actions=['select second', 'skip'],
                                    images=cw_icons if cw_icons else None,
                                    icon="magic" if not cw_icons else None,
                                    title="Civil War - Second Defender"
                                )
                                # Update selectable figures for second pick
                                self._update_defender_selectable()
                            else:
                                # Normal success — update and exit defender mode
                                if result.get('game'):
                                    self.game.update_from_dict(result['game'])
                                self.load_figures()
                                self.defender_selection_mode = False
                                self._reset_defender_selectable()
                                self.state.set_msg(f"Selected {target_figure.name} as opponent's defender.")
                                self.game.pending_defender_selection = False
                                # Clear Civil War defender state
                                if hasattr(self.game, 'civil_war_defender_second'):
                                    self.game.civil_war_defender_second = False
                                    self.game.civil_war_required_color = None
                        else:
                            error_msg = result.get('message', 'Unknown error')
                            self.make_dialogue_box(
                                message=f"Failed to select defender: {error_msg}",
                                actions=['ok'],
                                icon="error",
                                title="Error"
                            )
                        
                        self.figure_pending_defender_selection = None
                    
                    elif self.figure_pending_upgrade:
                        # User confirmed upgrade
                        try:
                            # Find the upgrade card in the player's hand
                            main_hand, side_hand = self.game.get_hand()
                            hand_cards = main_hand + side_hand
                            
                            upgrade_card_template = self.figure_pending_upgrade.upgrade_card
                            upgrade_card = None
                            
                            # Find the actual card in hand that matches the upgrade_card template
                            for card in hand_cards:
                                if card.to_tuple() == upgrade_card_template.to_tuple():
                                    upgrade_card = card
                                    break
                            
                            if not upgrade_card:
                                raise Exception("Upgrade card not found in hand")
                            
                            # Determine card type
                            upgrade_card_type = 'main' if upgrade_card.is_main_card else 'side'
                            
                            # Call server to upgrade the figure
                            result = upgrade_figure(
                                self.figure_pending_upgrade.id,
                                self.game.player_id,
                                self.game.game_id,
                                upgrade_card.id,
                                upgrade_card_type
                            )
                            
                            if result.get('success'):
                                # Success message
                                print(f"Successfully upgraded {self.figure_pending_upgrade.name} to {self.figure_pending_upgrade.upgrade_family_name}.")
                                self.state.set_msg(f"Upgraded {self.figure_pending_upgrade.name} to {self.figure_pending_upgrade.upgrade_family_name}.")
                                # Refresh game state and reload figures - load_figures() will handle cache updates
                                self.game.update()
                                self.load_figures()
                                print(f"[FIELD_SCREEN] Figures reloaded after upgrade, count: {len(self.figures)}")
                            else:
                                # Show error message
                                error_msg = result.get('message', 'Unknown error')
                                print(f"Failed to upgrade figure: {error_msg}")
                                self.state.set_msg(f"Failed to upgrade figure: {error_msg}")
                                
                        except Exception as e:
                            print(f"Error upgrading figure: {str(e)}")
                            self.state.set_msg(f"Error upgrading figure: {str(e)}")
                        
                        # Close the detail box and dialogue box
                        self.figure_detail_box = None
                        for icon in self.figure_icons:
                            icon.clicked = False
                        self.figure_pending_upgrade = None
                        
                elif response == 'no' or response == 'cancel':
                    # User cancelled action
                    self.figure_pending_pickup = None
                    self.figure_pending_upgrade = None
                    self.figure_pending_defender_selection = None
                    self._pending_advance_figure = None
                    # Keep the detail box open
                
                elif response == 'select second':
                    # Civil War — player wants to pick a second figure
                    # Just dismiss dialogue, the civil_war_awaiting_second / 
                    # civil_war_defender_second flag stays set so they can pick
                    pass
                elif response == 'skip':
                    # Civil War — player skips the second figure pick
                    from utils.game_service import skip_civil_war_second
                    if getattr(self.game, 'civil_war_awaiting_second', False):
                        result = skip_civil_war_second(
                            self.game.game_id, self.game.player_id, 'advance'
                        )
                        if result.get('success'):
                            if result.get('game'):
                                self.game.update_from_dict(result['game'])
                        self.game.civil_war_awaiting_second = False
                        self.game.civil_war_required_color = None
                        # Clear forced advance state if it was a forced advance
                        if self.game.forced_advance_dialogue_shown:
                            self.game.pending_forced_advance = False
                        # Trigger advance notification check (Blitzkrieg needs the combined dialogue)
                        self.game.pending_own_advance_notification = True
                        self.game.own_advance_figure_name = None
                    elif getattr(self.game, 'civil_war_defender_second', False):
                        result = skip_civil_war_second(
                            self.game.game_id, self.game.player_id, 'defender'
                        )
                        if result.get('success'):
                            if result.get('game'):
                                self.game.update_from_dict(result['game'])
                        self.game.civil_war_defender_second = False
                        self.game.civil_war_required_color = None
                        self.defender_selection_mode = False
                        self._reset_defender_selectable()
                        self.game.pending_defender_selection = False
                elif response == 'ok' or response == 'got it!':
                    # Simple acknowledgment
                    pass
                
                # Close the dialogue box (only if no new dialogue was created during response handling)
                if self.dialogue_box is dialogue_before_response:
                    self.dialogue_box = None
                return  # Don't process other events when button was clicked
            else:
                # Dialogue is still open, no response yet - block other events
                return
        
        # If in target selection mode, only allow figure selection
        if hasattr(self.state, 'pending_spell_cast') and self.state.pending_spell_cast:
            self._handle_target_selection(events)
            return
        
        # If in defender selection mode, only allow selecting own figures as defender
        if self.defender_selection_mode:
            self._handle_defender_selection(events)
            return
        
        # Handle figure detail box events first (if open)
        if self.figure_detail_box:
            response = self.figure_detail_box.handle_events(events)
            if response:
                if response == 'close':
                    self.figure_detail_box = None
                    # Deselect the figure
                    for icon in self.figure_icons:
                        icon.clicked = False
                elif response == 'advance':
                    # Show confirmation dialogue before advancing
                    figure = self.figure_detail_box.figure
                    self._pending_advance_figure = figure
                    # Find the existing FieldFigureIcon (has correct bonus/enchantments)
                    advance_icon = None
                    for icon in self.figure_icons:
                        if hasattr(icon, 'figure') and icon.figure.id == figure.id:
                            advance_icon = icon
                            break
                    if not advance_icon:
                        # Fallback: create a new icon if not found
                        from game.components.figures.figure_icon import FieldFigureIcon
                        advance_icon = FieldFigureIcon(
                            self.window,
                            self.game,
                            figure,
                            is_visible=True,
                            x=0,
                            y=0,
                            all_player_figures=[figure],
                            resources_data={}
                        )
                    advance_icon.show_advance_overlay = False
                    self.make_dialogue_box(
                        message=f"Do you want to advance {figure.name} toward battle?",
                        actions=['yes', 'cancel'],
                        images=[advance_icon],
                        icon=None,
                        title="Advance Figure"
                    )
                    # Close detail box
                    self.figure_detail_box = None
                    for icon in self.figure_icons:
                        icon.clicked = False
                elif response == 'disabled_advance_ceasefire':
                    # Advance button clicked while disabled due to ceasefire
                    # Check if it's a Blitzkrieg-induced ceasefire
                    modifiers = self.game.battle_modifier if isinstance(self.game.battle_modifier, list) else []
                    has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)
                    if has_blitzkrieg:
                        blitz_icons = self._get_modifier_icon_images('Blitzkrieg')
                        self.make_dialogue_box(
                            message="Blitzkrieg ceasefire is active.\n\nNo one can advance until ceasefire ends.",
                            actions=['ok'],
                            images=blitz_icons if blitz_icons else None,
                            icon="error" if not blitz_icons else None,
                            title="Blitzkrieg Ceasefire"
                        )
                    else:
                        self.make_dialogue_box(
                            message="You cannot advance figures during ceasefire.\n\nWait for the ceasefire to end.",
                            actions=['ok'],
                            icon="ceasefire_passive",
                            title="Ceasefire Active"
                        )
                elif response == 'disabled_advance_cannot_attack':
                    # Advance button clicked while disabled due to cannot_attack
                    self.make_dialogue_box(
                        message="This figure cannot attack and therefore cannot advance toward battle.",
                        actions=['ok'],
                        icon="error",
                        title="Cannot Attack"
                    )
                elif response == 'disabled_advance_cannot_be_blocked':
                    # Advance button clicked while disabled because opponent's advancing figure has cannot_be_blocked
                    self.make_dialogue_box(
                        message="The opponent's advancing figure cannot be blocked.\n\nYou cannot counter-advance against it.",
                        actions=['ok'],
                        icon="error",
                        title="Cannot Be Blocked"
                    )
                elif response == 'disabled_advance_blitzkrieg':
                    # Advance button clicked while disabled due to Blitzkrieg modifier
                    blitz_icons = self._get_modifier_icon_images('Blitzkrieg')
                    self.make_dialogue_box(
                        message="Blitzkrieg is active!\n\nThe defending player cannot counter-advance.",
                        actions=['ok'],
                        images=blitz_icons if blitz_icons else None,
                        icon="error" if not blitz_icons else None,
                        title="Blitzkrieg"
                    )
                elif response == 'disabled_advance_peasant_war':
                    # Advance button clicked while disabled due to Peasant War on non-village figure
                    pw_icons = self._get_modifier_icon_images('Peasant War')
                    self.make_dialogue_box(
                        message="Peasant War is active!\n\nOnly village figures can advance during Peasant War.",
                        actions=['ok'],
                        images=pw_icons if pw_icons else None,
                        icon="error" if not pw_icons else None,
                        title="Peasant War"
                    )
                elif response == 'disabled_advance_civil_war':
                    # Advance button clicked while disabled due to Civil War on non-village figure
                    cw_icons = self._get_modifier_icon_images('Civil War')
                    self.make_dialogue_box(
                        message="Civil War is active!\n\nOnly village figures can advance during Civil War.",
                        actions=['ok'],
                        images=cw_icons if cw_icons else None,
                        icon="error" if not cw_icons else None,
                        title="Civil War"
                    )
                elif response in ('disabled_upgrade_forced_advance', 'disabled_pick up_forced_advance'):
                    # Upgrade or Pick up clicked during forced advance
                    self.make_dialogue_box(
                        message="Last turn!\n\nYou must advance a figure toward battle. You cannot pick up or upgrade figures right now.",
                        actions=['ok'],
                        icon="error",
                        title="Battle Time"
                    )
                elif response == 'disabled_advance_civil_war_wrong_color':
                    # Advance clicked on wrong-color figure during Civil War second pick
                    required_color = getattr(self.game, 'civil_war_required_color', '')
                    color_name = 'red' if required_color == 'offensive' else 'black'
                    cw_icons = self._get_modifier_icon_images('Civil War')
                    self.make_dialogue_box(
                        message=f"Civil War requires a second village figure of the same color ({color_name}).",
                        actions=['ok'],
                        images=cw_icons if cw_icons else None,
                        icon="error" if not cw_icons else None,
                        title="Wrong Color"
                    )
                elif response == 'disabled_advance_civil_war_already_selected':
                    # Advance clicked on already-selected figure during Civil War
                    cw_icons = self._get_modifier_icon_images('Civil War')
                    self.make_dialogue_box(
                        message="This figure is already selected for battle. Choose a different figure.",
                        actions=['ok'],
                        images=cw_icons if cw_icons else None,
                        icon="error" if not cw_icons else None,
                        title="Already Selected"
                    )
                elif response == 'disabled_advance_resource_deficit':
                    # Advance clicked on a figure with resource deficit
                    self.make_dialogue_box(
                        message="This figure has a resource deficit and cannot advance toward battle.\n\nEnsure your figures' resource requirements are met before advancing.",
                        actions=['ok'],
                        icon="error",
                        title="Resource Deficit"
                    )
                elif response and response.startswith('disabled_') and response.endswith('_battle_active'):
                    # Any action disabled because a battle is in progress
                    self.make_dialogue_box(
                        message="You cannot perform this action while a battle is in progress.",
                        actions=['ok'],
                        icon="error",
                        title="Action Blocked"
                    )
                elif response == 'upgrade':
                    # Handle upgrade action - show confirmation dialogue with upgrade card image
                    upgrade_card = self.figure_detail_box.figure.upgrade_card
                    if upgrade_card:
                        self.figure_pending_upgrade = self.figure_detail_box.figure
                        # Create card image for display in dialogue
                        from game.components.cards.card_img import CardImg
                        card_img = CardImg(self.window, upgrade_card.suit, upgrade_card.rank)
                        self.make_dialogue_box(
                            f"Are you sure you want to upgrade {self.figure_pending_upgrade.name} to {self.figure_pending_upgrade.upgrade_family_name}? This will cost you:",
                            actions=['yes', 'cancel'],
                            images=[card_img],
                            title="Upgrade Figure"
                        )
                elif response == 'pick up':
                    # Handle pick up action - show confirmation dialogue
                    self.figure_pending_pickup = self.figure_detail_box.figure
                    self.make_dialogue_box(
                        f"Are you sure you want to pick up {self.figure_pending_pickup.name}? This will remove the figure from the field and return it to your hand.",
                        actions=['yes', 'cancel'],
                        title="Pick Up Figure"
                    )
            # If response is 'close', we already handled it above
            # For other actions, keep the box open unless user clicks close/outside
            return  # Don't process other events when detail box is open
        
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # Only allow one figure to be selected at a time
                # Check in reverse order (topmost figure gets priority)
                clicked_icon = None
                for icon in reversed(self.figure_icons):
                    if icon.hovered:
                        clicked_icon = icon
                        break
                
                if clicked_icon:
                    # Normal figure selection behavior
                    # Deselect all other icons
                    for icon in self.figure_icons:
                        if icon != clicked_icon:
                            icon.clicked = False
                    # Toggle the clicked icon
                    was_clicked = clicked_icon.clicked
                    clicked_icon.clicked = not clicked_icon.clicked
                    
                    # Force immediate visual feedback by redrawing the screen
                    # This ensures the icon state change is visible before the detail box opens
                    self._force_immediate_redraw()
                    
                    # Open detail box if figure was just selected and is visible
                    if clicked_icon.clicked and not was_clicked and clicked_icon.is_visible:
                        # During Civil War second-pick, skip detail box and go straight
                        # to advance confirmation (no pickup/upgrade allowed)
                        cw_second_pick = (getattr(self.game, 'civil_war_awaiting_second', False) or
                                          getattr(self.game, 'civil_war_defender_second', False))
                        if cw_second_pick:
                            figure = clicked_icon.figure
                            cw_icons = self._get_modifier_icon_images('Civil War')
                            
                            # Validate: must be a village figure
                            figure_field = getattr(figure.family, 'field', None) if hasattr(figure, 'family') else None
                            if figure_field != 'village':
                                self.make_dialogue_box(
                                    message="Civil War requires village figures only.",
                                    actions=['ok'],
                                    images=cw_icons if cw_icons else None,
                                    icon="error" if not cw_icons else None,
                                    title="Invalid Selection"
                                )
                                clicked_icon.clicked = False
                            # Validate: must match required color
                            elif getattr(self.game, 'civil_war_required_color', None):
                                figure_color = getattr(figure.family, 'color', None) if hasattr(figure, 'family') else None
                                if figure_color != self.game.civil_war_required_color:
                                    color_name = 'red' if self.game.civil_war_required_color == 'offensive' else 'black'
                                    self.make_dialogue_box(
                                        message=f"Civil War requires a second village figure of the same color ({color_name}).",
                                        actions=['ok'],
                                        images=cw_icons if cw_icons else None,
                                        icon="error" if not cw_icons else None,
                                        title="Wrong Color"
                                    )
                                    clicked_icon.clicked = False
                            # Validate: not already selected as first figure
                            elif (figure.id == self.game.advancing_figure_id or
                                  figure.id == self.game.defending_figure_id):
                                self.make_dialogue_box(
                                    message="This figure is already selected for battle. Choose a different figure.",
                                    actions=['ok'],
                                    images=cw_icons if cw_icons else None,
                                    icon="error" if not cw_icons else None,
                                    title="Already Selected"
                                )
                                clicked_icon.clicked = False
                            # Validate: no resource deficit
                            elif getattr(clicked_icon, 'has_deficit', False):
                                self.make_dialogue_box(
                                    message="This figure has a resource deficit and cannot advance toward battle.",
                                    actions=['ok'],
                                    images=cw_icons if cw_icons else None,
                                    icon="error" if not cw_icons else None,
                                    title="Resource Deficit"
                                )
                                clicked_icon.clicked = False
                            else:
                                # Valid selection — show confirmation
                                self._pending_advance_figure = figure
                                advance_icon = clicked_icon
                                advance_icon.show_advance_overlay = False
                                self.make_dialogue_box(
                                    message=f"Select {figure.name} as your second Civil War figure?",
                                    actions=['yes', 'cancel'],
                                    images=[advance_icon] + (cw_icons if cw_icons else []),
                                    icon=None,
                                    title="Civil War - Second Figure"
                                )
                        else:
                            # Calculate resources once for efficiency
                            resources_data = self.game.calculate_resources(self.figure_manager.families)
                            
                            self.figure_detail_box = FigureDetailBox(
                                self.window,
                                clicked_icon.figure,
                                self.game,
                                all_figures=self.figures,  # Pass cached figures to avoid server call
                                resources_data=resources_data  # Pass pre-calculated resources
                            )
                    # Close detail box if figure was deselected
                    elif not clicked_icon.clicked:
                        self.figure_detail_box = None


    def handle_figure_click(self, figure):
        """Handle actions when a figure is clicked."""
        print(f"Selected figure: {figure.name}")
        # Add additional functionality for interacting with the figure
    
    def _handle_target_selection(self, events):
        """Handle events when in target selection mode for spell casting."""
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # Check which figure was clicked
                clicked_icon = None
                for icon in reversed(self.figure_icons):
                    if icon.hovered:
                        clicked_icon = icon
                        break
                
                if clicked_icon:
                    # Check if trying to cast Explosion on a Maharaja
                    pending = self.state.pending_spell_cast
                    selected_spell = pending['spell']
                    target_figure = clicked_icon.figure
                    
                    if 'Explosion' in selected_spell.name and target_figure.name in ['Himalaya Maharaja', 'Djungle Maharaja']:
                        self.make_dialogue_box(
                            message="Explosion cannot be cast on Maharajas!",
                            actions=[],
                            icon="error",
                            title="Invalid Target",
                            auto_close_delay=2000
                        )
                        return
                    
                    # Apply spell to the selected figure
                    self._apply_spell_to_target(target_figure)
                    return
            
            elif event.type == KEYDOWN:
                # Allow ESC to cancel target selection
                if event.key == K_ESCAPE:
                    self.state.pending_spell_cast = None
                    self.make_dialogue_box(
                        message="Spell casting cancelled.",
                        actions=['ok'],
                        icon="error",
                        title="Cancelled"
                    )
                    return
    
    def _handle_defender_selection(self, events):
        """Handle events when in defender selection mode — advancing player selects opponent's defender."""
        # Determine active battle modifier restrictions
        modifiers = self.game.battle_modifier if isinstance(self.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        has_peasant_war = 'Peasant War' in modifier_types
        has_blitzkrieg = 'Blitzkrieg' in modifier_types
        has_civil_war = 'Civil War' in modifier_types
        village_only = has_peasant_war or has_civil_war
        
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # Check which figure was clicked
                clicked_icon = None
                for icon in reversed(self.figure_icons):
                    if icon.hovered:
                        clicked_icon = icon
                        break
                
                if clicked_icon:
                    print(f"[DEFENDER_CLICK] Clicked: {clicked_icon.figure.name} (id={clicked_icon.figure.id}), defender_selectable={getattr(clicked_icon, 'defender_selectable', 'N/A')}, is_visible={clicked_icon.is_visible}")
                    # Show error for non-selectable figures (works for both visible and hidden)
                    if hasattr(clicked_icon, 'defender_selectable') and not clicked_icon.defender_selectable:
                        reason = "This figure cannot be selected as a defender."
                        title = "Cannot Select"
                        images = []
                        target_fig = clicked_icon.figure
                        if target_fig.player_id == self.game.player_id:
                            reason = "You must select one of your opponent's figures."
                        elif village_only and hasattr(target_fig, 'family') and target_fig.family.field != 'village':
                            active_mod = 'Peasant War' if has_peasant_war else 'Civil War'
                            reason = f"{active_mod} is active — only village figures can be selected."
                            title = active_mod
                            images = self._get_modifier_icon_images(active_mod)
                        elif hasattr(target_fig, 'cannot_defend') and target_fig.cannot_defend:
                            reason = f"{target_fig.name} cannot defend and cannot be selected for battle."
                        elif hasattr(target_fig, 'cannot_be_targeted') and target_fig.cannot_be_targeted:
                            reason = f"{target_fig.name} cannot be targeted by the opponent."
                        elif not clicked_icon.is_visible:
                            reason = "This hidden figure cannot be selected as a defender."
                        elif hasattr(target_fig, 'must_be_attacked') and not target_fig.must_be_attacked:
                            reason = "You must select a figure with the 'Must Be Attacked' trait first."
                        self.make_dialogue_box(
                            message=reason,
                            actions=[],
                            images=images if images else None,
                            icon="error" if not images else None,
                            title=title,
                            auto_close_delay=2000
                        )
                        return
                    
                    target_figure = clicked_icon.figure
                    
                    # Must be an OPPONENT's figure (advancing player picks from opponent)
                    if target_figure.player_id == self.game.player_id:
                        self.make_dialogue_box(
                            message="You must select one of your opponent's figures as the defender.",
                            actions=[],
                            icon="error",
                            title="Invalid Selection",
                            auto_close_delay=2000
                        )
                        return
                    
                    # Village-only restriction (Peasant War / Civil War)
                    if village_only and hasattr(target_figure, 'family') and target_figure.family.field != 'village':
                        active_mod = 'Peasant War' if has_peasant_war else 'Civil War'
                        mod_icons = self._get_modifier_icon_images(active_mod)
                        self.make_dialogue_box(
                            message=f"{active_mod} is active — only village figures can be selected for battle.",
                            actions=[],
                            images=mod_icons if mod_icons else None,
                            icon="error" if not mod_icons else None,
                            title=active_mod,
                            auto_close_delay=2000
                        )
                        return
                    
                    # Check cannot_defend constraint (figure cannot be advanced against)
                    if hasattr(target_figure, 'cannot_defend') and target_figure.cannot_defend:
                        self.make_dialogue_box(
                            message=f"{target_figure.name} cannot defend and cannot be selected for battle.",
                            actions=[],
                            icon="error",
                            title="Cannot Defend",
                            auto_close_delay=2000
                        )
                        return
                    
                    # Check cannot_be_targeted constraint (opponent cannot choose this figure)
                    if hasattr(target_figure, 'cannot_be_targeted') and target_figure.cannot_be_targeted:
                        self.make_dialogue_box(
                            message=f"{target_figure.name} cannot be targeted by the opponent.",
                            actions=[],
                            icon="error",
                            title="Cannot Be Targeted",
                            auto_close_delay=2000
                        )
                        return
                    
                    # Check must_be_attacked constraint on opponent's eligible figures
                    # Exclude figures with cannot_defend or cannot_be_targeted
                    opponent_figures = [
                        fig for fig in self.figures 
                        if fig.player_id != self.game.player_id
                        and not (hasattr(fig, 'cannot_defend') and fig.cannot_defend)
                        and not (hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted)
                    ]
                    
                    # Village-only filter for must_be_attacked check too
                    if village_only:
                        opponent_figures = [
                            fig for fig in opponent_figures
                            if hasattr(fig, 'family') and fig.family.field == 'village'
                        ]
                    
                    # Check if advancing figure has cannot_be_blocked — if so, skip must_be_attacked
                    advancing_figure = None
                    if self.game.advancing_figure_id:
                        for fig in self.figures:
                            if fig.id == self.game.advancing_figure_id:
                                advancing_figure = fig
                                break
                    
                    advancing_cannot_be_blocked = (
                        advancing_figure and 
                        hasattr(advancing_figure, 'cannot_be_blocked') and 
                        advancing_figure.cannot_be_blocked
                    )
                    
                    # Blitzkrieg also skips must_be_attacked
                    skip_must_be_attacked = advancing_cannot_be_blocked or has_blitzkrieg
                    
                    if not skip_must_be_attacked:
                        must_be_attacked_figures = [
                            fig for fig in opponent_figures
                            if hasattr(fig, 'must_be_attacked') and fig.must_be_attacked
                        ]
                        must_be_attacked_ids = {fig.id for fig in must_be_attacked_figures}
                        
                        if must_be_attacked_figures and target_figure.id not in must_be_attacked_ids:
                            figure_names = ', '.join(f.name for f in must_be_attacked_figures)
                            self.make_dialogue_box(
                                message=f"You must select a figure with the 'Must Be Attacked' trait.\n\nEligible figures: {figure_names}",
                                actions=['ok'],
                                icon="error",
                                title="Invalid Selection"
                            )
                            return
                    
                    # Valid selection — show confirmation dialogue with figure icon
                    self.figure_pending_defender_selection = target_figure
                    if clicked_icon.is_visible:
                        confirm_msg = f"Are you sure you want to select {target_figure.name} as the defender for battle?"
                    else:
                        confirm_msg = "Are you sure you want to select this hidden figure as the defender for battle?"
                    self.make_dialogue_box(
                        message=confirm_msg,
                        actions=['yes', 'no'],
                        images=[clicked_icon],
                        title="Confirm Defender"
                    )
                    return

    def _apply_spell_to_target(self, target_figure):
        """
        Apply a pending spell cast to the selected target figure.
        
        :param target_figure: The figure selected as the target
        """
        from utils import spell_service
        
        pending = self.state.pending_spell_cast
        selected_spell = pending['spell']
        real_cards = pending['real_cards']
        
        # Determine if target figure should be visible in success dialogue
        # Explosion always reveals the destroyed figure
        # Other spells (Poison, Health Boost) respect the figure's actual visibility
        is_opponent_figure = target_figure.player_id != self.game.player_id
        player_has_all_seeing_eye = self.game.has_active_all_seeing_eye()
        is_maharaja = target_figure.name in ['Himalaya Maharaja', 'Djungle Maharaja']
        
        if 'Explosion' in selected_spell.name:
            # Explosion reveals the destroyed figure
            show_figure_visible = True
        elif is_opponent_figure:
            # For opponent figures, check if they're naturally visible
            show_figure_visible = is_maharaja or player_has_all_seeing_eye
        else:
            # Own figures are always visible
            show_figure_visible = True
        
        # Create figure icon for targeted spells to show in success dialogue
        # Always hide bonus and deficit to avoid revealing opponent's strategic state
        figure_icon = FieldFigureIcon(
            window=self.window,
            game=self.game,
            figure=target_figure,
            is_visible=show_figure_visible,
            all_player_figures=[],  # Empty list to prevent bonus calculation
            resources_data=None
        )
        # Explicitly set battle bonus and deficit to hide them
        figure_icon.battle_bonus_received = 0
        figure_icon.has_deficit = False
        
        # Prepare card data for server
        cards_data = [{
            'id': card.id,
            'rank': card.rank,
            'suit': card.suit,
            'value': card.value
        } for card in real_cards]
        
        # Call spell service to cast the spell
        result = spell_service.cast_spell(
            player_id=self.game.player_id,
            game_id=self.game.game_id,
            spell_name=selected_spell.name,
            spell_type=selected_spell.family.type,
            spell_family_name=selected_spell.family.name,
            suit=selected_spell.suit,
            cards=cards_data,
            target_figure_id=target_figure.id,
            counterable=selected_spell.counterable,
            possible_during_ceasefire=selected_spell.possible_during_ceasefire
        )
        
        if result.get('success'):
            # For Explosion spells, don't apply enchantment locally since figure is destroyed
            # Just update from server to remove the figure
            if 'Explosion' not in selected_spell.name:
                # Apply enchantment locally for immediate visual feedback
                self._apply_enchantment_to_figure(target_figure, selected_spell)
            else:
                # For Explosion spells, remove destroyed figure from cache immediately
                if target_figure.id in self.icon_cache:
                    del self.icon_cache[target_figure.id]
            
            # Update game state from server
            self.game.update()
            
            # Refresh figure icons to show updated enchantments (or removed figure for Explosion)
            self.load_figures()
            
            # Determine figure name to display in message
            # Only reveal name for Explosion or visible figures
            if 'Explosion' in selected_spell.name or show_figure_visible:
                figure_name_display = target_figure.name
            else:
                figure_name_display = "an opponent figure"
            
            # Show success message with figure icon
            if 'Explosion' in selected_spell.name:
                self.make_dialogue_box(
                    message=f"{selected_spell.name} destroyed {figure_name_display}!",
                    actions=['ok'],
                    icon="magic",
                    title="Figure Destroyed",
                    images=[figure_icon]
                )
            else:
                self.make_dialogue_box(
                    message=f"{selected_spell.name} cast on {figure_name_display}!",
                    actions=['ok'],
                    icon="magic",
                    title="Spell Cast",
                    images=[figure_icon]
                )
        else:
            # Show error message
            error_msg = result.get('message', 'Unknown error')
            self.make_dialogue_box(
                message=f"Failed to cast spell: {error_msg}",
                actions=['got it!'],
                icon="error",
                title="Casting Failed"
            )
        
        # Clear pending spell cast
        self.state.pending_spell_cast = None
    
    def _apply_enchantment_to_figure(self, figure, spell):
        """
        Apply an enchantment effect to a figure locally.
        
        :param figure: The figure to enchant
        :param spell: The spell being cast
        """
        # Determine power modifier based on spell name
        power_modifier = 0
        if 'Poison' in spell.name:
            power_modifier = -6
        elif 'Boost' in spell.name or 'Health' in spell.name:
            power_modifier = 6
        
        # Get icon filename from spell family config
        # The icon_img in configs is a filename string (e.g., 'poisson_portion.png')
        icon_filename = 'default_spell_icon.png'  # Default fallback
        
        # Try to get the icon filename from the spell's family configuration
        if hasattr(spell, 'family') and spell.family:
            # Check if it's from the ability_spell_config
            if 'Poison' in spell.name:
                icon_filename = 'poisson_portion.png'
            elif 'Boost' in spell.name or 'Health' in spell.name:
                icon_filename = 'health_portion.png'
            elif 'Explosion' in spell.name:
                icon_filename = 'bomb.png'
            elif 'All Seeing Eye' in spell.name:
                icon_filename = 'eye.png'
            elif 'Infinite Hammer' in spell.name:
                icon_filename = 'infinite_hammer.png'
        
        # Apply enchantment to figure
        figure.add_enchantment(
            spell_name=spell.name,
            spell_icon=icon_filename,
            power_modifier=power_modifier
        )

    def _draw_opponent_hand_cards(self):
        """Draw opponent's hand cards rotated 90 degrees after the castle compartment."""
        opponent_main_cards, opponent_side_cards = self._get_opponent_hand_cards()
        all_opponent_cards = opponent_main_cards + opponent_side_cards
        
        # Track current opponent card IDs
        current_card_ids = {card.get('id') for card in all_opponent_cards if card.get('id')}
        
        # Only regenerate card surfaces if cards have changed
        if current_card_ids != self.last_opponent_card_ids:
            self._generate_opponent_card_cache(opponent_main_cards, opponent_side_cards)
            self.last_opponent_card_ids = current_card_ids
        
        # Get the opponent's castle compartment for positioning
        castle_comp = self.compartments['opponent']['castle']
        
        # Card dimensions (after rotation)
        card_display_width = int(settings.CARD_WIDTH * 0.30)
        rotated_card_height = card_display_width
        
        # Starting position
        start_x = castle_comp.right + settings.FIELD_ICON_PADDING_X
        start_y = castle_comp.top + 30
        
        card_spacing = 3
        
        # Draw cached card surfaces
        current_y = start_y
        for card_surface in self.opponent_card_cache:
            self.window.blit(card_surface, (start_x, current_y))
            current_y += rotated_card_height + card_spacing

    def _generate_opponent_card_cache(self, opponent_main_cards, opponent_side_cards):
        """Generate and cache rotated card surfaces for opponent's hand."""
        self.opponent_card_cache = []
        
        card_display_width = int(settings.CARD_WIDTH * 0.27)
        card_display_height = int(settings.CARD_HEIGHT * 0.27)
        
        # Generate main cards
        for card in opponent_main_cards:
            card_img = CardImg(self.window, card.get('suit'), card.get('rank'), 
                              width=card_display_width, height=card_display_height)
            
            # Create and rotate surface
            card_surface = pygame.Surface((card_display_width, card_display_height), pygame.SRCALPHA)
            card_img.front_img.convert_alpha()
            card_surface.blit(card_img.front_img, (0, 0))
            rotated_surface = pygame.transform.rotate(card_surface, -90)
            
            self.opponent_card_cache.append(rotated_surface)
        
        # Generate side cards
        for card in opponent_side_cards:
            card_img = CardImg(self.window, card.get('suit'), card.get('rank'),
                              width=card_display_width, height=card_display_height)
            
            # Create and rotate surface
            card_surface = pygame.Surface((card_display_width, card_display_height), pygame.SRCALPHA)
            card_img.front_img.convert_alpha()
            card_surface.blit(card_img.front_img, (0, 0))
            rotated_surface = pygame.transform.rotate(card_surface, -90)
            
            self.opponent_card_cache.append(rotated_surface)

    def _draw_target_selection_prompt(self):
        """Draw a prominent prompt asking the player to select a target figure."""
        pending = self.state.pending_spell_cast
        spell_name = pending['spell'].name if 'spell' in pending else 'Spell'
        
        # Create prompt text
        prompt_text = f"SELECT A TARGET FOR {spell_name.upper()}"
        prompt_surface = self.target_prompt_font.render(prompt_text, True, (255, 50, 50))  # Bright red
        
        # Create cancel instruction text
        cancel_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 2)
        cancel_text = "Press ESC to cancel"
        cancel_surface = cancel_font.render(cancel_text, True, (255, 255, 150))  # Light yellow
        
        # Create background box for better visibility
        text_width = max(prompt_surface.get_width(), cancel_surface.get_width())
        text_height = prompt_surface.get_height() + cancel_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        # Draw semi-transparent black background
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        # Draw yellow border for emphasis
        pygame.draw.rect(self.window, (255, 255, 0), box_rect, 4)
        
        # Draw main prompt text centered in box
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        # Draw cancel text below
        cancel_x = box_rect.centerx - cancel_surface.get_width() // 2
        cancel_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(cancel_surface, (cancel_x, cancel_y))
        
        # Add pulsing effect to main prompt
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))
    
    def _draw_defender_selection_prompt(self):
        """Draw a prominent prompt asking the advancing player to select an opponent's defender."""
        # Create prompt text
        prompt_text = "SELECT OPPONENT'S DEFENDER"
        prompt_surface = self.target_prompt_font.render(prompt_text, True, (100, 200, 255))  # Blue
        
        # Create instruction text
        info_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 2)
        
        # Check for must_be_attacked constraint on opponent's eligible figures
        # Exclude figures with cannot_defend or cannot_be_targeted
        opponent_figures = [
            fig for fig in self.figures 
            if fig.player_id != self.game.player_id
            and not (hasattr(fig, 'cannot_defend') and fig.cannot_defend)
            and not (hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted)
        ]
        
        # Check if advancing figure has cannot_be_blocked — if so, skip must_be_attacked
        advancing_figure = None
        if self.game.advancing_figure_id:
            for fig in self.figures:
                if fig.id == self.game.advancing_figure_id:
                    advancing_figure = fig
                    break
        
        advancing_cannot_be_blocked = (
            advancing_figure and 
            hasattr(advancing_figure, 'cannot_be_blocked') and 
            advancing_figure.cannot_be_blocked
        )
        
        if advancing_cannot_be_blocked:
            info_text = "Your figure cannot be blocked — select any opponent figure"
        else:
            must_be_attacked_figures = [
                fig for fig in opponent_figures
                if hasattr(fig, 'must_be_attacked') and fig.must_be_attacked
            ]
            if must_be_attacked_figures:
                figure_names = ', '.join(f.name for f in must_be_attacked_figures)
                info_text = f"Must select: {figure_names}"
            else:
                info_text = "Click one of your opponent's figures to face your advance"
        
        info_surface = info_font.render(info_text, True, (180, 220, 255))  # Light blue
        
        # Create background box
        text_width = max(prompt_surface.get_width(), info_surface.get_width())
        text_height = prompt_surface.get_height() + info_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        # Draw semi-transparent black background
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        # Draw blue border for emphasis
        pygame.draw.rect(self.window, (100, 200, 255), box_rect, 4)
        
        # Draw main prompt text centered in box
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        # Draw info text below
        info_x = box_rect.centerx - info_surface.get_width() // 2
        info_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(info_surface, (info_x, info_y))
        
        # Add pulsing effect
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))

    def _force_immediate_redraw(self):
        """
        Force an immediate redraw of the field screen to show visual feedback.
        This is called when an icon state changes to provide instant visual response
        before any heavy operations (like opening detail box) occur.
        """
        # Redraw the field screen with updated icon states
        self.draw()
        # Update only the display to show the changes immediately
        pygame.display.update()

    def draw(self):
        """Draw the screen, including the field background and figure icons."""
        super().draw()

        # Safety check: ensure categorized_figures exists
        if not hasattr(self, 'categorized_figures') or not self.categorized_figures:
            return

        if self.figures or True:  # Always draw compartments even without figures
            # First pass: Draw all compartment fills and slot icon backgrounds
            for player in ['self', 'opponent']:
                for field in ['castle', 'village', 'military']:
                    compartment = self.compartments[player][field]
                    
                    # Create a new surface with per-pixel alpha for the fill
                    compartment_surface = pygame.Surface((compartment.width, compartment.height), pygame.SRCALPHA)
                    
                    # Draw the filled rectangle with transparency
                    fill_color = (*settings.FIELD_FILL_COLOR[:3], settings.FIELD_TRANSPARENCY)
                    pygame.draw.rect(compartment_surface, fill_color, compartment_surface.get_rect())
                    
                    # Draw slot icon as background (upper part of compartment)
                    if field in self.slot_icons:
                        slot_icon = self.slot_icons[field]
                        # Position in upper portion of compartment
                        icon_rect = slot_icon.get_rect()
                        icon_rect.centerx = compartment.width // 2
                        icon_rect.top = int(compartment.height * 0.018)
                        compartment_surface.blit(slot_icon, icon_rect)
                    
                    # Blit the fill onto the main window
                    self.window.blit(compartment_surface, compartment.topleft)
            
            # Second pass: Draw borders (to avoid double-thick borders between compartments)
            border_color = (*settings.FIELD_BORDER_COLOR[:3], settings.FIELD_TRANSPARENCY)
            for player in ['self', 'opponent']:
                # Get the three compartments for this player
                castle_comp = self.compartments[player]['castle']
                village_comp = self.compartments[player]['village']
                military_comp = self.compartments[player]['military']
                
                # Calculate the bounding box for all three compartments
                # Use min/max to handle different arrangements (self vs opponent)
                left = min(castle_comp.left, village_comp.left, military_comp.left)
                right = max(castle_comp.right, village_comp.right, military_comp.right)
                top = castle_comp.top
                bottom = castle_comp.bottom
                width = right - left
                height = bottom - top
                
                # Safety check: ensure valid dimensions
                if width <= 0 or height <= 0:
                    continue
                
                # Create surface for borders
                border_surface = pygame.Surface((width, height), pygame.SRCALPHA)
                
                # Draw outer border (full rectangle)
                pygame.draw.rect(border_surface, border_color, border_surface.get_rect(), settings.FIELD_BORDER_WIDTH)
                
                # Draw vertical dividers between compartments
                # Get sorted x-positions of all compartments
                comp_positions = sorted([
                    (castle_comp.left, castle_comp.width),
                    (village_comp.left, village_comp.width),
                    (military_comp.left, military_comp.width)
                ], key=lambda x: x[0])
                
                # Draw dividers between adjacent compartments
                for i in range(len(comp_positions) - 1):
                    divider_x = comp_positions[i][0] + comp_positions[i][1] - left
                    pygame.draw.line(border_surface, border_color, 
                                   (divider_x, 0), (divider_x, height), 
                                   settings.FIELD_BORDER_WIDTH)
                
                # Blit the border surface
                self.window.blit(border_surface, (left, top))
            
            # Draw board titles ("YOU" / "OPPONENT") - YOU on left, OPPONENT on right
            for player in ['self', 'opponent']:
                # Get the bounding box for all compartments
                castle_comp = self.compartments[player]['castle']
                village_comp = self.compartments[player]['village']
                military_comp = self.compartments[player]['military']
                
                left = min(castle_comp.left, village_comp.left, military_comp.left)
                right = max(castle_comp.right, village_comp.right, military_comp.right)
                
                # Determine title text
                title_text_str = "YOU" if player == 'self' else "OPPONENT"
                title_text = self.board_title_font.render(title_text_str, True, settings.FIELD_BOARD_TITLE_COLOR)
                title_rect = title_text.get_rect()
                
                # Check if All Seeing Eye is active for this player (cached for performance)
                # For opponent's side: show icon if current player has it active
                # For self's side: show icon if opponent has it active
                current_time = pygame.time.get_ticks()
                if current_time - self.last_all_seeing_eye_check > self.all_seeing_eye_check_interval:
                    self.cached_all_seeing_eye_status = self.game.has_active_all_seeing_eye()
                    self.cached_opponent_all_seeing_eye_status = self.game.has_opponent_cast_all_seeing_eye()
                    self.last_all_seeing_eye_check = current_time
                
                show_eye_icon = False
                if player == 'opponent':
                    show_eye_icon = self.cached_all_seeing_eye_status
                else:  # player == 'self'
                    show_eye_icon = self.cached_opponent_all_seeing_eye_status
                
                # Position: YOU on left side, OPPONENT on right side
                if player == 'self':
                    title_rect.left = left
                else:
                    title_rect.right = right
                
                title_rect.bottom = castle_comp.top + settings.FIELD_BOARD_TITLE_Y_OFFSET
                
                # Draw All Seeing Eye icon if active
                # For "YOU": icon to the right of text
                # For "OPPONENT": icon to the left of text
                if show_eye_icon:
                    eye_rect = self.all_seeing_eye_icon.get_rect()
                    if player == 'self':
                        # Icon to the right of "YOU"
                        eye_rect.left = title_rect.right + 5
                    else:
                        # Icon to the left of "OPPONENT"
                        eye_rect.right = title_rect.left - 5
                    eye_rect.centery = title_rect.centery
                    self.window.blit(self.all_seeing_eye_icon, eye_rect)
                
                # Draw title
                self.window.blit(title_text, title_rect)
            
            # Third pass: Draw titles for each compartment
            for player in ['self', 'opponent']:
                for field in ['castle', 'village', 'military']:
                    compartment = self.compartments[player][field]
                    
                    # Render title text
                    title_text = self.field_title_font.render(field.upper(), True, settings.FIELD_TITLE_COLOR)
                    title_rect = title_text.get_rect()
                    
                    # Position: left-aligned for self, right-aligned for opponent
                    if player == 'self':
                        title_rect.left = compartment.left + settings.FIELD_TITLE_PADDING
                    else:
                        title_rect.right = compartment.right - settings.FIELD_TITLE_PADDING
                    
                    title_rect.top = compartment.top + settings.FIELD_TITLE_PADDING
                    
                    # Draw title
                    self.window.blit(title_text, title_rect)
            
            # Fourth pass: Draw figures
            for player in ['self', 'opponent']:
                for field in ['castle', 'village', 'military']:
                    compartment = self.compartments[player][field]
                    # Safety check for categorized_figures
                    if player not in self.categorized_figures or field not in self.categorized_figures[player]:
                        continue
                    figures = self.categorized_figures[player][field]

                    if len(figures) > 0:
                        # Calculate the y-position to center the icons in the compartment
                        # Account for title space at the top
                        icon_height = settings.FIELD_ICON_WIDTH
                        title_space = settings.FIELD_TITLE_FONT_SIZE + 2 * settings.FIELD_TITLE_PADDING
                        available_height = compartment.height - 2 * settings.FIELD_BORDER_WIDTH - title_space
                        
                        # Calculate dynamic spacing to fit all figures within available height
                        if len(figures) == 1:
                            icon_spacing = 0
                            total_icons_height = icon_height
                        else:
                            # Calculate total height with default spacing
                            default_total_height = len(figures) * icon_height + (len(figures) - 1) * settings.FIELD_ICON_PADDING_Y
                            
                            # If it fits, use default spacing; otherwise, reduce spacing to fit
                            if default_total_height <= available_height:
                                icon_spacing = settings.FIELD_ICON_PADDING_Y
                                total_icons_height = default_total_height
                            else:
                                # Calculate reduced spacing to fit within available height
                                # Formula: total_height = N * icon_height + (N-1) * spacing
                                # Solving for spacing: spacing = (available_height - N * icon_height) / (N - 1)
                                icon_spacing = (available_height - len(figures) * icon_height) / (len(figures) - 1)
                                total_icons_height = available_height
                        
                        # Start position accounts for title space
                        icon_y_start = compartment.top + title_space + (available_height - total_icons_height) // 2 + 0.5*settings.FIELD_ICON_WIDTH

                        # Calculate positions and separate into layers: regular, selected, hovered
                        regular_positions = []
                        selected_positions = []
                        hovered_item = None
                        
                        for i, figure in enumerate(figures):
                            icon = self.icon_cache[figure.id]
                            icon_x = compartment.left + 0.5*settings.FIELD_ICON_WIDTH 
                            icon_y = icon_y_start + i * (icon_height + icon_spacing)
                            
                            if icon.hovered:
                                hovered_item = (icon, icon_x, icon_y)
                            elif icon.clicked:
                                selected_positions.append((icon, icon_x, icon_y))
                            else:
                                regular_positions.append((icon, icon_x, icon_y))
                        
                        # Draw in layers: regular -> selected -> hovered
                        # Each layer in reverse order (topmost figures in foreground)
                        for icon, icon_x, icon_y in reversed(regular_positions):
                            icon.draw(icon_x, icon_y)
                        
                        for icon, icon_x, icon_y in reversed(selected_positions):
                            icon.draw(icon_x, icon_y)
                        
                        # Draw hovered icon last (on top of everything)
                        if hovered_item:
                            icon, icon_x, icon_y = hovered_item
                            icon.draw(icon_x, icon_y)

        # Draw opponent's hand cards if All Seeing Eye is active (use cached status)
        if self.cached_all_seeing_eye_status:
            self._draw_opponent_hand_cards()

        # Note: Figure detail box is drawn in game_screen.py to ensure it's on top of hand cards
        
        # Draw target selection prompt if in target selection mode
        if hasattr(self.state, 'pending_spell_cast') and self.state.pending_spell_cast:
            self._draw_target_selection_prompt()
        
        # Draw defender selection prompt if in defender selection mode
        if self.defender_selection_mode:
            self._draw_defender_selection_prompt()

    def _update_defender_selectable(self):
        """Mark figure icons as selectable/non-selectable for defender selection mode."""
        # Get advancing figure to check cannot_be_blocked
        advancing_figure = None
        if self.game.advancing_figure_id:
            for fig in self.figures:
                if fig.id == self.game.advancing_figure_id:
                    advancing_figure = fig
                    break
        
        advancing_cannot_be_blocked = (
            advancing_figure and 
            hasattr(advancing_figure, 'cannot_be_blocked') and 
            advancing_figure.cannot_be_blocked
        )
        
        # Check active battle modifiers
        modifiers = self.game.battle_modifier if isinstance(self.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        has_peasant_war = 'Peasant War' in modifier_types
        has_blitzkrieg = 'Blitzkrieg' in modifier_types
        has_civil_war = 'Civil War' in modifier_types
        village_only = has_peasant_war or has_civil_war
        
        # Blitzkrieg acts like cannot_be_blocked for must_be_attacked purposes
        skip_must_be_attacked = advancing_cannot_be_blocked or has_blitzkrieg
        
        # Determine which opponent figures are eligible
        opponent_figures_eligible = []
        for fig in self.figures:
            if fig.player_id == self.game.player_id:
                continue
            if hasattr(fig, 'cannot_defend') and fig.cannot_defend:
                continue
            if hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted:
                continue
            # Village-only restriction (Peasant War / Civil War)
            if village_only and hasattr(fig, 'family') and fig.family.field != 'village':
                continue
            # Civil War second pick: must match color of first defender
            if has_civil_war and hasattr(self.game, 'civil_war_defender_second') and self.game.civil_war_defender_second:
                required_color = getattr(self.game, 'civil_war_required_color', None)
                if required_color and hasattr(fig, 'family') and fig.family.color != required_color:
                    continue
                # Exclude the figure already selected as first defender
                if fig.id == self.game.defending_figure_id:
                    continue
            opponent_figures_eligible.append(fig)
        
        # must_be_attacked filtering — only consider village figures if village_only
        must_be_attacked_figures = []
        if not skip_must_be_attacked:
            must_be_attacked_figures = [
                fig for fig in opponent_figures_eligible
                if hasattr(fig, 'must_be_attacked') and fig.must_be_attacked
            ]
        
        # Build set of must_be_attacked figure IDs for reliable comparison
        must_be_attacked_ids = {fig.id for fig in must_be_attacked_figures}
        eligible_ids = {fig.id for fig in opponent_figures_eligible}
        
        print(f"[DEFENDER_SELECT] Advancing figure: {advancing_figure.name if advancing_figure else 'None'}, cannot_be_blocked: {advancing_cannot_be_blocked}")
        print(f"[DEFENDER_SELECT] Battle modifiers: peasant_war={has_peasant_war}, blitzkrieg={has_blitzkrieg}, civil_war={has_civil_war}")
        print(f"[DEFENDER_SELECT] Eligible opponent figures: {[(f.name, f.id, getattr(f, 'must_be_attacked', False)) for f in opponent_figures_eligible]}")
        print(f"[DEFENDER_SELECT] Must-be-attacked figures: {[(f.name, f.id) for f in must_be_attacked_figures]}")
        
        for icon in self.figure_icons:
            fig = icon.figure
            # Enable defender selection mode on all icons (allows hidden figure hover)
            icon.in_defender_selection_mode = True
            
            # Own figures are never selectable as defenders
            if fig.player_id == self.game.player_id:
                icon.defender_selectable = False
                continue
            
            # Opponent figure must be in the eligible set (handles cannot_defend, cannot_be_targeted, village_only)
            if fig.id not in eligible_ids:
                icon.defender_selectable = False
                continue
            
            # If must_be_attacked applies, only those figures are selectable
            if must_be_attacked_ids and fig.id not in must_be_attacked_ids:
                icon.defender_selectable = False
                print(f"[DEFENDER_SELECT] {fig.name} (id={fig.id}) NOT selectable (must_be_attacked constraint)")
                continue
            
            icon.defender_selectable = True
            print(f"[DEFENDER_SELECT] {fig.name} (id={fig.id}) IS selectable")
    
    def _reset_defender_selectable(self):
        """Reset all figure icons to selectable (normal state)."""
        for icon in self.figure_icons:
            icon.defender_selectable = True
            icon.in_defender_selection_mode = False
