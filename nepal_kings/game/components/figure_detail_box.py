import pygame
from config import settings
from utils.utils import Button
from game.components.cards.card_img import CardImg


class FigureDetailBox:
    """
    A detailed info box that displays comprehensive information about a selected figure,
    including stats, cards, and action buttons.
    """

    def __init__(self, window, figure, game, x=None, y=None, all_figures=None, resources_data=None):
        """
        Initialize the figure detail box.

        :param window: The pygame surface to draw on
        :param figure: The Figure object to display details for
        :param game: Reference to the game object
        :param x: Optional x position (defaults to center of screen)
        :param y: Optional y position (defaults to center of screen)
        :param all_figures: Optional list of all figures (to avoid server call)
        :param resources_data: Optional pre-calculated resources data (to avoid recalculation)
        """
        self.window = window
        self.figure = figure
        self.game = game
        self.all_figures = all_figures  # Cache for battle bonus calculation
        self.resources_data = resources_data  # Cache for resource deficit calculation

        # Fonts
        self.title_font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_TITLE_DIALOGUE_BOX)
        self.title_font.set_bold(True)
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DIALOGUE_BOX)
        self.small_font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DIALOGUE_BOX - 4)

        # Create card images for the figure's cards
        card_width = int(settings.SCREEN_WIDTH * 0.05)
        card_height = int(card_width * 1.4)  # Standard card aspect ratio
        self.card_images = [
            CardImg(
                self.window,
                card.suit,
                card.rank,
                width=card_width,
                height=card_height
            ) for card in figure.cards
        ]

        # Box dimensions - wider to accommodate two-column layout
        self.width = int(settings.SCREEN_WIDTH * 0.55)
        self.height = int(settings.SCREEN_HEIGHT * 0.75)
        
        # Column widths for two-column layout
        self.left_column_width = int(self.width * 0.35)
        self.right_column_width = int(self.width * 0.55)
        self.column_spacing = int(self.width * 0.05)
        
        # Position (center of screen by default)
        self.x = x if x is not None else (settings.SCREEN_WIDTH - self.width) // 2
        self.y = y if y is not None else (settings.SCREEN_HEIGHT - self.height) // 2

        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)
        self.border_rect = self.rect.inflate(settings.DIALOGUE_BOX_BORDER_WIDTH, settings.DIALOGUE_BOX_BORDER_WIDTH)

        # Create X button for closing (top right corner)
        close_button_size = 30
        close_button_margin = 10
        self.close_button_rect = pygame.Rect(
            self.rect.right - close_button_size - close_button_margin,
            self.rect.top + close_button_margin,
            close_button_size,
            close_button_size
        )
        self.close_button_hovered = False
        self.close_button_clicked = False

        # Check if upgrade card is available in hand
        self.upgrade_card_available = self._check_upgrade_card_available()

        # Load resource icons
        self.resource_icons = self._load_resource_icons()
        
        # Load state icons (success/error)
        self.state_icons = self._load_state_icons()
        
        # Load skill icons
        self.skill_icons = self._load_skill_icons()
        
        # Load figure icon
        self.figure_icon = self._load_figure_icon()

        # Calculate battle bonus (do this once, not every frame)
        self.potential_battle_bonus = self._calculate_potential_battle_bonus()
        
        # Calculate resource deficits (do this once, not every frame)
        self.resource_deficits = self._calculate_resource_deficits()
        self.has_any_deficit = any(self.resource_deficits.values()) if self.resource_deficits else False

        # Action buttons (customize these based on figure type/state)
        self.buttons = self._create_action_buttons()

    def _create_action_buttons(self):
        """Create action buttons based on figure state and type."""
        buttons = []
        button_y_start = self.rect.bottom - settings.MENU_BUTTON_HEIGHT - settings.SMALL_SPACER_Y
        button_x = self.rect.centerx - settings.MENU_BUTTON_WIDTH // 2

        # Example actions - customize based on your game logic
        actions = []
        
        # Check if this is the player's own figure
        is_own_figure = self.figure.player_id == self.game.player_id
        is_maharaja = 'Maharaja' in self.figure.name
        
        if is_own_figure and self.game.turn:
            # Add upgrade action if figure can be upgraded AND upgrade card is available
            if (hasattr(self.figure, 'upgrade_family_name') and self.figure.upgrade_family_name 
                and self.upgrade_card_available):
                actions.append('Upgrade')
            
            # Add charge action (formerly "move")
            actions.append('Charge')
            
            # Add pick up action if not a Maharaja
            if not is_maharaja:
                actions.append('Pick up')

        # Create buttons vertically stacked from bottom
        for i, action in enumerate(reversed(actions)):
            button = Button(
                self.window,
                button_x,
                button_y_start - i * (settings.MENU_BUTTON_HEIGHT + settings.SMALL_SPACER_Y),
                action
            )
            buttons.append(button)

        return buttons

    def _load_resource_icons(self):
        """Load and scale resource icons."""
        icon_size = int(settings.FONT_SIZE_DIALOGUE_BOX * 1.2)  # Slightly larger than text
        icons = {}
        
        # Use the predefined resource icon paths from settings
        if hasattr(settings, 'RESOURCE_ICON_IMG_PATH_DICT'):
            for resource, path in settings.RESOURCE_ICON_IMG_PATH_DICT.items():
                try:
                    icon = pygame.image.load(path).convert_alpha()
                    icons[resource] = pygame.transform.smoothscale(icon, (icon_size, icon_size))
                except Exception as e:
                    print(f"[FIGURE_DETAIL] Failed to load icon for {resource} from {path}: {e}")
        
        return icons

    def _load_state_icons(self):
        """Load and scale state icons (success/error)."""
        icon_size = int(settings.FONT_SIZE_DIALOGUE_BOX * 1.2)
        icons = {}
        
        icon_paths = {
            'success': 'img/figures/state_icons/check_yes.png',
            'error': 'img/figures/state_icons/check_no.png'
        }
        
        for icon_name, path in icon_paths.items():
            try:
                icon = pygame.image.load(path).convert_alpha()
                icons[icon_name] = pygame.transform.smoothscale(icon, (icon_size, icon_size))
            except Exception as e:
                print(f"[FIGURE_DETAIL] Failed to load state icon {icon_name} from {path}: {e}")
        
        return icons

    def _load_skill_icons(self):
        """Load and scale skill icons for combat attributes."""
        icon_size = int(settings.FONT_SIZE_DIALOGUE_BOX * 1.2)
        icons = {}
        
        if hasattr(settings, 'SKILL_ICON_IMG_PATH_DICT'):
            for skill, path in settings.SKILL_ICON_IMG_PATH_DICT.items():
                try:
                    icon = pygame.image.load(path).convert_alpha()
                    icons[skill] = pygame.transform.smoothscale(icon, (icon_size, icon_size))
                except Exception as e:
                    print(f"[FIGURE_DETAIL] Failed to load skill icon {skill} from {path}: {e}")
        
        return icons
    
    def _load_enchantment_icon(self, icon_filename):
        """
        Load and scale an enchantment spell icon for the detail box.
        
        :param icon_filename: Filename of the spell icon (e.g., 'poisson_portion.png')
        :return: Scaled pygame Surface or None if loading fails
        """
        icon_size = int(settings.FONT_SIZE_DIALOGUE_BOX * 1.2)  # Same size as skill icons
        
        try:
            # Spell icons are in img/spells/icons/
            icon_path = f'img/spells/icons/{icon_filename}'
            icon = pygame.image.load(icon_path).convert_alpha()
            return pygame.transform.smoothscale(icon, (icon_size, icon_size))
        except Exception as e:
            print(f"[FIGURE_DETAIL] Failed to load enchantment icon '{icon_filename}': {e}")
            return None

    def _load_figure_icon(self):
        """Load and scale the figure's icon image."""
        try:
            # Get the icon image from the figure's family
            if hasattr(self.figure.family, 'icon_img') and self.figure.family.icon_img:
                # The icon_img should already be a pygame Surface
                icon = self.figure.family.icon_img
                # Scale to fit in left column (leave some margin)
                target_size = int(self.left_column_width * 0.9)
                return pygame.transform.smoothscale(icon, (target_size, target_size))
        except Exception as e:
            print(f"[FIGURE_DETAIL] Failed to load figure icon: {e}")
        return None

    def _map_resource_to_icon(self, resource_name):
        """
        Map database resource names to icon keys.
        Database uses names like 'food_red', 'warrior_black' etc.
        Icons use 'rice', 'meat', 'warrior_red', 'villager_black' etc.
        """
        # Resource name mapping
        resource_map = {
            'food_red': 'rice',
            'food_black': 'meat',
            'warrior_red': 'warrior_red',
            'warrior_black': 'warrior_black',
            'material_red': 'wood',
            'material_black': 'stone',
            'armor_red': 'sword_shield',
            'armor_black': 'sword_shield',
            'villager_red': 'villager_red',
            'villager_black': 'villager_black',
        }
        
        # Return mapped name or original if no mapping exists
        return resource_map.get(resource_name, resource_name)

    def _calculate_resource_deficits(self):
        """
        Calculate which resources are in deficit for this figure.
        Returns a dict mapping resource names to deficit status.
        """
        try:
            # Use cached resources data if available
            if self.resources_data is not None:
                produces = self.resources_data.get('produces', {})
                requires = self.resources_data.get('requires', {})
            else:
                # Calculate if not provided
                from game.components.figures.figure_manager import FigureManager
                
                figure_manager = FigureManager()
                families = figure_manager.families
                
                resources_data = self.game.calculate_resources(families)
                produces = resources_data.get('produces', {})
                requires = resources_data.get('requires', {})
            
            deficits = {}
            
            # Check each resource this figure requires
            if hasattr(self.figure, 'requires') and self.figure.requires:
                for resource_name, amount in self.figure.requires.items():
                    # Check if this resource type is in deficit overall
                    total_required = requires.get(resource_name, 0)
                    total_produced = produces.get(resource_name, 0)
                    deficits[resource_name] = total_required > total_produced
            
            return deficits
        except Exception as e:
            return {}

    def _calculate_potential_battle_bonus(self):
        """
        Calculate the potential battle bonus this figure could receive.
        Rules:
        - Castle figures get bonus from other castle figures (same suit)
        - Village figures get bonus from castle figures (same suit)
        - Military figures get bonus from castle + village figures (same suit)
        - Military figures provide 0 bonus
        """
        try:
            # Use cached figures if available, otherwise fetch from server
            if self.all_figures is not None:
                all_figures = [fig for fig in self.all_figures if fig.player_id == self.game.player_id]
            else:
                # Import here to avoid circular imports
                from game.components.figures.figure_manager import FigureManager
                
                # Get all families
                figure_manager = FigureManager()
                families = figure_manager.families
                
                # Get all figures for this player
                all_figures = self.game.get_figures(families, is_opponent=False)
            
            # Determine this figure's type
            current_figure_type = self.figure.family.field if hasattr(self.figure.family, 'field') else None
            
            # Determine which figure types can provide bonus to this figure
            if current_figure_type == 'castle':
                # Castle gets bonus from other castle figures only
                valid_types = ['castle']
            elif current_figure_type == 'village':
                # Village gets bonus from castle figures only
                valid_types = ['castle']
            elif current_figure_type == 'military':
                # Military gets bonus from castle + village figures
                valid_types = ['castle', 'village']
            else:
                # Unknown type, no bonus
                valid_types = []
            
            # Filter for same suit, valid types, excluding current figure
            same_suit_figures = [
                fig for fig in all_figures 
                if (fig.suit == self.figure.suit and 
                    fig.id != self.figure.id and
                    hasattr(fig.family, 'field') and
                    fig.family.field in valid_types)
            ]
            
            # Sum battle bonuses
            total_bonus = sum(fig.get_battle_bonus() for fig in same_suit_figures)
            return total_bonus
        except Exception as e:
            # If anything fails, just return 0
            return 0

    def _check_upgrade_card_available(self):
        """Check if the upgrade card required for this figure is in the player's hand."""
        if not hasattr(self.figure, 'upgrade_card') or not self.figure.upgrade_card:
            return False
        
        # Get player's hand
        main_hand, side_hand = self.game.get_hand()
        hand_cards = main_hand + side_hand
        
        # Check if upgrade card is in hand
        upgrade_card_tuple = self.figure.upgrade_card.to_tuple()
        for card in hand_cards:
            if card.to_tuple() == upgrade_card_tuple:
                return True
        
        return False

    def draw(self):
        """Draw the figure detail box with two-column layout."""
        # Draw border
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX_BORDER, self.border_rect)

        # Draw background
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX, self.rect)

        # Calculate maximum Y position for content (leave space for buttons)
        button_section_height = len(self.buttons) * (settings.MENU_BUTTON_HEIGHT + settings.SMALL_SPACER_Y)
        max_content_y = self.rect.bottom - button_section_height

        current_y = self.rect.y + settings.SMALL_SPACER_Y

        # Draw title (figure name) - centered above both columns
        title_surface = self.title_font.render(self.figure.name, True, settings.TITLE_TEXT_COLOR)
        title_rect = title_surface.get_rect(centerx=self.rect.centerx, top=current_y)
        self.window.blit(title_surface, title_rect)
        current_y += title_rect.height + settings.SMALL_SPACER_Y

        # Draw divider line under title
        if current_y + 2 < max_content_y:
            pygame.draw.line(
                self.window,
                settings.COLOR_DIALOGUE_BOX_BORDER,
                (self.rect.left + settings.SMALL_SPACER_X, current_y),
                (self.rect.right - settings.SMALL_SPACER_X, current_y),
                2
            )
            current_y += settings.SMALL_SPACER_Y

        # Define column positions
        left_column_x = self.rect.left + settings.SMALL_SPACER_X
        right_column_x = left_column_x + self.left_column_width + self.column_spacing
        
        # Store starting Y position for both columns
        content_start_y = current_y
        
        # --- LEFT COLUMN: Figure icon and cards ---
        left_y = content_start_y
        
        # Draw figure icon
        if self.figure_icon and left_y < max_content_y:
            icon_x = left_column_x + (self.left_column_width - self.figure_icon.get_width()) // 2
            self.window.blit(self.figure_icon, (icon_x, left_y))
            left_y += self.figure_icon.get_height() + settings.SMALL_SPACER_Y
        
        # Draw cards section in left column
        if self.card_images and left_y < max_content_y:
            cards_title = self.font.render("Cards:", True, settings.TITLE_TEXT_COLOR)
            cards_title_x = left_column_x + (self.left_column_width - cards_title.get_width()) // 2
            self.window.blit(cards_title, (cards_title_x, left_y))
            left_y += cards_title.get_height() + settings.SMALL_SPACER_Y // 2

            # Draw card images horizontally in left column
            card_spacing = int(settings.SMALL_SPACER_X * 0.3)
            card_width = self.card_images[0].front_img.get_width()
            card_height = self.card_images[0].front_img.get_height()
            
            # Calculate total width of all cards with spacing
            total_cards_width = len(self.card_images) * card_width + (len(self.card_images) - 1) * card_spacing
            
            # Only draw cards if they fit horizontally
            if total_cards_width <= self.left_column_width and left_y + card_height <= max_content_y:
                # Start x position to center the cards horizontally
                cards_start_x = left_column_x + (self.left_column_width - total_cards_width) // 2
                
                # Draw each card image horizontally
                for i, card_img in enumerate(self.card_images):
                    draw_x = cards_start_x + i * (card_width + card_spacing)
                    card_img.draw_front(draw_x, left_y)
                
                left_y += card_height + card_spacing
        
        # --- RIGHT COLUMN: All info ---
        right_y = content_start_y
        
        # Draw figure family/type as subtitle (e.g., "Village Figure")
        if right_y + self.font.get_height() <= max_content_y:
            family_text = f"{self.figure.family.field.capitalize()} Figure"
            family_surface = self.font.render(family_text, True, settings.TITLE_TEXT_COLOR)
            self.window.blit(family_surface, (right_column_x, right_y))
            right_y += family_surface.get_height() + settings.SMALL_SPACER_Y

        # Draw power/value with potential battle bonus and enchantment modifier
        if right_y + self.font.get_height() <= max_content_y:
            power_value = self.figure.get_value()
            power_text = f"Power: {power_value}"
            power_surface = self.font.render(power_text, True, settings.MSG_TEXT_COLOR)
            self.window.blit(power_surface, (right_column_x, right_y))
            
            current_bonus_x = right_column_x + power_surface.get_width()
            
            # Display potential battle bonus (calculated once in __init__)
            if self.potential_battle_bonus > 0:
                bonus_text = f" (+{self.potential_battle_bonus})"
                bonus_surface = self.font.render(bonus_text, True, (0, 180, 0))  # Green color
                self.window.blit(bonus_surface, (current_bonus_x, right_y))
                current_bonus_x += bonus_surface.get_width()
            
            # Display enchantment modifier (purple)
            if hasattr(self.figure, 'active_enchantments') and self.figure.active_enchantments:
                enchantment_modifier = self.figure.get_total_enchantment_modifier()
                if enchantment_modifier != 0:
                    enchant_text = f" ({enchantment_modifier:+d})"
                    enchant_surface = self.font.render(enchant_text, True, (150, 50, 200))  # Purple color
                    self.window.blit(enchant_surface, (current_bonus_x, right_y))
            
            right_y += power_surface.get_height() + settings.SMALL_SPACER_Y // 2

        # Draw battle bonus this figure provides
        if right_y + self.font.get_height() <= max_content_y:
            battle_bonus = self.figure.get_battle_bonus()
            bonus_text = f"Support: {battle_bonus}"
            bonus_surface = self.font.render(bonus_text, True, settings.MSG_TEXT_COLOR)
            self.window.blit(bonus_surface, (right_column_x, right_y))
            right_y += bonus_surface.get_height() + settings.SMALL_SPACER_Y

        # Draw resources produced
        if self.figure.produces and right_y + self.font.get_height() <= max_content_y:
            # Draw horizontal divider line
            pygame.draw.line(
                self.window,
                settings.COLOR_DIALOGUE_BOX_BORDER,
                (right_column_x, right_y),
                (right_column_x + self.right_column_width, right_y),
                2
            )
            right_y += settings.SMALL_SPACER_Y
            
            # Draw "Production" label on first line
            produces_label = self.font.render("Production", True, settings.TITLE_TEXT_COLOR)
            self.window.blit(produces_label, (right_column_x, right_y))
            right_y += produces_label.get_height() + settings.SMALL_SPACER_Y #// 2
            
            # Draw resource icons and amounts on second line
            current_x = right_column_x + settings.SMALL_SPACER_X
            
            for resource, amount in self.figure.produces.items():
                # Map resource name to icon key
                icon_key = self._map_resource_to_icon(resource)
                
                # Draw icon if available
                if icon_key in self.resource_icons:
                    icon = self.resource_icons[icon_key]
                    self.window.blit(icon, (current_x, right_y))
                    current_x += icon.get_width() + 2
                    
                    # Draw amount next to icon
                    amount_text = self.font.render(f"{amount}", True, settings.MSG_TEXT_COLOR)
                    self.window.blit(amount_text, (current_x, right_y))
                    current_x += amount_text.get_width() + settings.SMALL_SPACER_X
                else:
                    # Fallback to text only
                    text = self.font.render(f"{resource.capitalize()} ({amount})", True, settings.MSG_TEXT_COLOR)
                    self.window.blit(text, (current_x, right_y))
                    current_x += text.get_width() + settings.SMALL_SPACER_X
            
            right_y += self.resource_icons[list(self.resource_icons.keys())[0]].get_height() + settings.SMALL_SPACER_Y

        # Draw resource requirements
        if self.figure.requires and right_y + self.font.get_height() <= max_content_y:
            # Use cached resource deficit data
            resource_deficits = self.resource_deficits
            has_any_deficit = self.has_any_deficit
            
            # Draw horizontal divider line
            pygame.draw.line(
                self.window,
                settings.COLOR_DIALOGUE_BOX_BORDER,
                (right_column_x, right_y),
                (right_column_x + self.right_column_width, right_y),
                2
            )
            right_y += settings.SMALL_SPACER_Y
            
            # Draw "Requirements" label with state icon on first line
            requires_label = self.font.render("Requirements", True, settings.TITLE_TEXT_COLOR)
            self.window.blit(requires_label, (right_column_x, right_y))
            
            # Draw success/error icon to the RIGHT of the label, vertically centered
            icon_to_draw = None
            if has_any_deficit:
                # Show error icon if any resource is in deficit
                if 'error' in self.state_icons:
                    icon_to_draw = self.state_icons['error']
            else:
                # Show success icon if all requirements are met
                if 'success' in self.state_icons:
                    icon_to_draw = self.state_icons['success']
            
            if icon_to_draw:
                # Position icon to the right of text, vertically centered
                icon_x = right_column_x + requires_label.get_width() + settings.SMALL_SPACER_X // 2
                icon_y = right_y + (requires_label.get_height() - icon_to_draw.get_height()) // 2
                self.window.blit(icon_to_draw, (icon_x, icon_y))
            
            right_y += requires_label.get_height() + settings.SMALL_SPACER_Y #// 2
            
            # Draw resource icons and amounts on second line
            current_x = right_column_x + settings.SMALL_SPACER_X
            
            for resource, amount in self.figure.requires.items():
                # Map resource name to icon key
                icon_key = self._map_resource_to_icon(resource)
                
                # Check if this specific resource is in deficit
                is_deficit = resource_deficits.get(resource, False)
                
                # Draw icon if available
                if icon_key in self.resource_icons:
                    icon = self.resource_icons[icon_key]
                    self.window.blit(icon, (current_x, right_y))
                    current_x += icon.get_width() + 2
                    
                    # Draw amount next to icon
                    amount_text = self.font.render(f"{amount}", True, settings.MSG_TEXT_COLOR)
                    amount_text_rect = amount_text.get_rect(topleft=(current_x, right_y))
                    self.window.blit(amount_text, (current_x, right_y))
                    
                    # Draw red frame around amount if in deficit
                    if is_deficit:
                        frame_rect = amount_text_rect.inflate(4, 4)  # Add padding
                        pygame.draw.rect(self.window, (220, 0, 0), frame_rect, 2)  # Red frame, 2 pixels
                    
                    current_x += amount_text.get_width() + settings.SMALL_SPACER_X
                else:
                    # Fallback to text only
                    text = self.font.render(f"{resource.capitalize()} ({amount})", True, settings.MSG_TEXT_COLOR)
                    self.window.blit(text, (current_x, right_y))
                    current_x += text.get_width() + settings.SMALL_SPACER_X
            
            right_y += self.resource_icons[list(self.resource_icons.keys())[0]].get_height() + settings.SMALL_SPACER_Y * 1.5

        # Draw skills section
        skills_to_display = []
        
        if hasattr(self.figure, 'cannot_attack') and self.figure.cannot_attack:
            skills_to_display.append(('cannot_attack', 'Cannot Attack'))
        if hasattr(self.figure, 'must_be_attacked') and self.figure.must_be_attacked:
            skills_to_display.append(('must_be_attacked', 'Must Be Attacked'))
        if hasattr(self.figure, 'rest_after_attack') and self.figure.rest_after_attack:
            skills_to_display.append(('rest_after_attack', 'Rest After Attack'))
        if hasattr(self.figure, 'distance_attack') and self.figure.distance_attack:
            skills_to_display.append(('distance_attack', 'Distance Attack'))
        if hasattr(self.figure, 'buffs_allies') and self.figure.buffs_allies:
            skills_to_display.append(('buffs_allies', 'Buffs Allies'))
        if hasattr(self.figure, 'blocks_bonus') and self.figure.blocks_bonus:
            skills_to_display.append(('blocks_bonus', 'Blocks Bonus'))
        
        print(f"[FIGURE_DETAIL] Skills to display: {skills_to_display}")
        
        # Draw skills if any exist
        if skills_to_display and right_y + self.font.get_height() + 20 <= max_content_y:
            # Draw horizontal divider line
            pygame.draw.line(
                self.window,
                settings.COLOR_DIALOGUE_BOX_BORDER,
                (right_column_x, right_y),
                (right_column_x + self.right_column_width, right_y),
                2
            )
            right_y += settings.SMALL_SPACER_Y
            
            # Draw "Skills" label
            skills_label = self.font.render("Skills", True, settings.TITLE_TEXT_COLOR)
            self.window.blit(skills_label, (right_column_x, right_y))
            right_y += skills_label.get_height() + settings.SMALL_SPACER_Y // 2
            
            # Draw skill icons and names
            for skill_key, skill_name in skills_to_display:
                # Determine row height
                if skill_key in self.skill_icons:
                    row_height = self.skill_icons[skill_key].get_height()
                else:
                    row_height = self.small_font.get_height()
                
                # Check if we have space for this skill
                if right_y + row_height > max_content_y - 10:
                    break  # Stop if we run out of space
                
                current_x = right_column_x + settings.SMALL_SPACER_X
                
                # Draw icon if available
                if skill_key in self.skill_icons:
                    icon = self.skill_icons[skill_key]
                    self.window.blit(icon, (current_x, right_y))
                    current_x += icon.get_width() + settings.SMALL_SPACER_X // 2
                    
                    # Draw skill name next to icon
                    skill_text = self.small_font.render(skill_name, True, settings.MSG_TEXT_COLOR)
                    # Center text vertically with icon
                    text_y = right_y + (icon.get_height() - skill_text.get_height()) // 2
                    self.window.blit(skill_text, (current_x, text_y))
                    
                    right_y += icon.get_height() + settings.SMALL_SPACER_Y // 2
                else:
                    # Fallback to text only
                    skill_text = self.small_font.render(f"• {skill_name}", True, settings.MSG_TEXT_COLOR)
                    self.window.blit(skill_text, (current_x, right_y))
                    right_y += skill_text.get_height() + settings.SMALL_SPACER_Y // 2
            
            right_y += settings.SMALL_SPACER_Y // 2  # Reduced spacing after skills

        # Draw enchantments section if any active enchantments
        if hasattr(self.figure, 'active_enchantments') and self.figure.active_enchantments:
            if right_y + self.font.get_height() + 20 <= max_content_y:
                # Draw horizontal divider line
                pygame.draw.line(
                    self.window,
                    settings.COLOR_DIALOGUE_BOX_BORDER,
                    (right_column_x, right_y),
                    (right_column_x + self.right_column_width, right_y),
                    2
                )
                right_y += settings.SMALL_SPACER_Y
                
                # Draw "Enchantments" label
                enchant_label = self.font.render("Enchantments", True, settings.TITLE_TEXT_COLOR)
                self.window.blit(enchant_label, (right_column_x, right_y))
                right_y += enchant_label.get_height() + settings.SMALL_SPACER_Y // 2
                
                # Draw each enchantment
                for enchantment in self.figure.active_enchantments:
                    spell_name = enchantment.get('spell_name', 'Unknown')
                    power_modifier = enchantment.get('power_modifier', 0)
                    spell_icon_filename = enchantment.get('spell_icon', '')
                    
                    # Try to load spell icon
                    enchant_icon = None
                    if spell_icon_filename:
                        enchant_icon = self._load_enchantment_icon(spell_icon_filename)
                    
                    # Determine row height
                    if enchant_icon:
                        row_height = enchant_icon.get_height()
                    else:
                        row_height = self.small_font.get_height()
                    
                    # Check if we have space for this enchantment
                    if right_y + row_height > max_content_y - 10:
                        break  # Stop if we run out of space
                    
                    current_x = right_column_x + settings.SMALL_SPACER_X
                    
                    # Draw icon if available
                    if enchant_icon:
                        self.window.blit(enchant_icon, (current_x, right_y))
                        current_x += enchant_icon.get_width() + settings.SMALL_SPACER_X // 2
                        
                        # Draw spell name next to icon
                        spell_text = self.small_font.render(spell_name, True, settings.MSG_TEXT_COLOR)
                        # Center text vertically with icon
                        text_y = right_y + (enchant_icon.get_height() - spell_text.get_height()) // 2
                        self.window.blit(spell_text, (current_x, text_y))
                        current_x += spell_text.get_width() + settings.SMALL_SPACER_X // 2
                        
                        # Draw purple modifier
                        modifier_text = f"({power_modifier:+d})"
                        modifier_surface = self.small_font.render(modifier_text, True, (150, 50, 200))
                        modifier_y = text_y  # Same vertical alignment as spell name
                        self.window.blit(modifier_surface, (current_x, modifier_y))
                        
                        right_y += enchant_icon.get_height() + settings.SMALL_SPACER_Y // 2
                    else:
                        # Fallback to text only
                        enchant_text = self.small_font.render(f"• {spell_name} ({power_modifier:+d})", True, (150, 50, 200))
                        self.window.blit(enchant_text, (current_x, right_y))
                        right_y += enchant_text.get_height() + settings.SMALL_SPACER_Y // 2
                
                right_y += settings.SMALL_SPACER_Y // 2  # Reduced spacing after enchantments

        # Draw description if available and there's space
        if hasattr(self.figure.family, 'description') and self.figure.family.description:
            # Check if we have at least 80 pixels for description (title + 1-2 lines)
            if right_y + 80 <= max_content_y:
                # Draw divider line
                divider_y = right_y
                pygame.draw.line(
                    self.window,
                    settings.COLOR_DIALOGUE_BOX_BORDER,
                    (right_column_x, divider_y),
                    (right_column_x + self.right_column_width, divider_y),
                    2
                )
                right_y += settings.SMALL_SPACER_Y

                desc_title = self.font.render("Description:", True, settings.TITLE_TEXT_COLOR)
                self.window.blit(desc_title, (right_column_x, right_y))
                right_y += desc_title.get_height() + settings.SMALL_SPACER_Y // 2

                # Wrap description text based on actual pixel width
                max_text_width = self.right_column_width - settings.SMALL_SPACER_X
                words = self.figure.family.description.split()
                desc_lines = []
                current_line = []
                
                for word in words:
                    test_line = ' '.join(current_line + [word])
                    test_width = self.small_font.size(test_line)[0]
                    
                    if test_width <= max_text_width:
                        current_line.append(word)
                    else:
                        if current_line:
                            desc_lines.append(' '.join(current_line))
                            current_line = [word]
                        else:
                            # Single word is too long, add it anyway but truncate
                            desc_lines.append(word)
                
                if current_line:
                    desc_lines.append(' '.join(current_line))
                
                # Draw only lines that fit
                line_height = self.small_font.get_height() + 2
                for line in desc_lines:
                    if right_y + line_height >= max_content_y:
                        break
                    line_surface = self.small_font.render(line, True, settings.MSG_TEXT_COLOR)
                    self.window.blit(line_surface, (right_column_x + settings.SMALL_SPACER_X // 2, right_y))
                    right_y += line_height

        # Draw buttons
        for button in self.buttons:
            button.draw()
        
        # Draw X button in top right corner with hover/click effects
        # Determine colors based on state
        if self.close_button_clicked:
            bg_color = (150, 150, 150)  # Darker gray when clicked
            x_color = (255, 100, 100)  # Bright red when clicked
            glow_alpha = 180
        elif self.close_button_hovered:
            bg_color = (200, 200, 200)  # Light gray when hovered
            x_color = (255, 50, 50)  # Red when hovered
            glow_alpha = 120
        else:
            bg_color = settings.COLOR_DIALOGUE_BOX_BORDER
            x_color = settings.TITLE_TEXT_COLOR
            glow_alpha = 0
        
        # Draw glow effect when hovered or clicked
        if glow_alpha > 0:
            glow_radius = 20
            glow_surface = pygame.Surface((glow_radius * 2, glow_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_surface, (255, 100, 100, glow_alpha), (glow_radius, glow_radius), glow_radius)
            glow_pos = (
                self.close_button_rect.centerx - glow_radius,
                self.close_button_rect.centery - glow_radius
            )
            self.window.blit(glow_surface, glow_pos)
        
        # Draw button background
        pygame.draw.rect(self.window, bg_color, self.close_button_rect, border_radius=3)
        
        # Draw X with lines
        margin = 8
        line_width = 4 if self.close_button_hovered else 3
        pygame.draw.line(
            self.window,
            x_color,
            (self.close_button_rect.left + margin, self.close_button_rect.top + margin),
            (self.close_button_rect.right - margin, self.close_button_rect.bottom - margin),
            line_width
        )
        pygame.draw.line(
            self.window,
            x_color,
            (self.close_button_rect.right - margin, self.close_button_rect.top + margin),
            (self.close_button_rect.left + margin, self.close_button_rect.bottom - margin),
            line_width
        )

    def update(self, events):
        """
        Handle events and update button states.

        :param events: List of pygame events
        :return: The action string if a button was clicked, None otherwise
        """
        for button in self.buttons:
            button.update()
        
        # Update close button hover state
        mouse_pos = pygame.mouse.get_pos()
        self.close_button_hovered = self.close_button_rect.collidepoint(mouse_pos)
        
        # Check if mouse is pressed for click effect
        mouse_pressed = pygame.mouse.get_pressed()[0]
        self.close_button_clicked = self.close_button_hovered and mouse_pressed

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                
                # Check if X button was clicked
                if self.close_button_rect.collidepoint(mouse_pos):
                    return 'close'
                
                # Check if clicked outside the box
                if not self.border_rect.collidepoint(mouse_pos):
                    return 'close'
                
                # Check if any action button was clicked
                for button in self.buttons:
                    if button.collide():
                        return button.text.lower()
        
        return None

    def handle_events(self, events):
        """Handle events (wrapper for update method)."""
        return self.update(events)
