import pygame
from config import settings
from utils.utils import Button
from game.components.cards.card_img import CardImg


class FigureDetailBox:
    """
    A detailed info box that displays comprehensive information about a selected figure,
    including stats, cards, and action buttons.
    """

    def __init__(self, window, figure, game, x=None, y=None):
        """
        Initialize the figure detail box.

        :param window: The pygame surface to draw on
        :param figure: The Figure object to display details for
        :param game: Reference to the game object
        :param x: Optional x position (defaults to center of screen)
        :param y: Optional y position (defaults to center of screen)
        """
        self.window = window
        self.figure = figure
        self.game = game

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

        # Box dimensions
        self.width = int(settings.SCREEN_WIDTH * 0.35)
        self.height = int(settings.SCREEN_HEIGHT * 0.75)
        
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
        """Draw the figure detail box."""
        # Draw border
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX_BORDER, self.border_rect)

        # Draw background
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX, self.rect)

        # Calculate maximum Y position for content (leave space for buttons)
        button_section_height = len(self.buttons) * (settings.MENU_BUTTON_HEIGHT + settings.SMALL_SPACER_Y)
        max_content_y = self.rect.bottom - button_section_height

        current_y = self.rect.y + settings.SMALL_SPACER_Y

        # Draw title (figure name)
        title_surface = self.title_font.render(self.figure.name, True, settings.TITLE_TEXT_COLOR)
        title_rect = title_surface.get_rect(centerx=self.rect.centerx, top=current_y)
        self.window.blit(title_surface, title_rect)
        current_y += title_rect.height + settings.SMALL_SPACER_Y

        # Draw divider line
        if current_y + 2 < max_content_y:
            pygame.draw.line(
                self.window,
                settings.COLOR_DIALOGUE_BOX_BORDER,
                (self.rect.left + settings.SMALL_SPACER_X, current_y),
                (self.rect.right - settings.SMALL_SPACER_X, current_y),
                2
            )
            current_y += settings.SMALL_SPACER_Y

        # Draw figure family/type
        if current_y + self.font.get_height() <= max_content_y:
            family_text = f"Type: {self.figure.family.field.capitalize()}"
            family_surface = self.font.render(family_text, True, settings.MSG_TEXT_COLOR)
            family_rect = family_surface.get_rect(centerx=self.rect.centerx, top=current_y)
            self.window.blit(family_surface, family_rect)
            current_y += family_rect.height + settings.SMALL_SPACER_Y // 2

        # Draw suit
        if current_y + self.font.get_height() <= max_content_y:
            suit_text = f"Suit: {self.figure.suit.capitalize()}"
            suit_surface = self.font.render(suit_text, True, settings.MSG_TEXT_COLOR)
            suit_rect = suit_surface.get_rect(centerx=self.rect.centerx, top=current_y)
            self.window.blit(suit_surface, suit_rect)
            current_y += suit_rect.height + settings.SMALL_SPACER_Y

        # Draw power/value
        if current_y + self.font.get_height() <= max_content_y:
            power_text = f"Power: {self.figure.get_value()}"
            power_surface = self.font.render(power_text, True, settings.MSG_TEXT_COLOR)
            power_rect = power_surface.get_rect(centerx=self.rect.centerx, top=current_y)
            self.window.blit(power_surface, power_rect)
            current_y += power_rect.height + settings.SMALL_SPACER_Y

        # Draw divider line
        if current_y + 2 < max_content_y:
            pygame.draw.line(
                self.window,
                settings.COLOR_DIALOGUE_BOX_BORDER,
                (self.rect.left + settings.SMALL_SPACER_X, current_y),
                (self.rect.right - settings.SMALL_SPACER_X, current_y),
                2
            )
            current_y += settings.SMALL_SPACER_Y

        # Draw cards section
        if self.card_images and current_y + self.font.get_height() <= max_content_y:
            cards_title = self.font.render("Cards:", True, settings.TITLE_TEXT_COLOR)
            cards_title_rect = cards_title.get_rect(centerx=self.rect.centerx, top=current_y)
            self.window.blit(cards_title, cards_title_rect)
            current_y += cards_title_rect.height + settings.SMALL_SPACER_Y

            # Draw card images horizontally
            card_spacing = int(settings.SMALL_SPACER_X * 0.5)
            card_width = self.card_images[0].front_img.get_width()
            card_height = self.card_images[0].front_img.get_height()
            
            # Only draw cards if they fit
            if current_y + card_height <= max_content_y:
                # Calculate total width of all cards with spacing
                total_cards_width = len(self.card_images) * card_width + (len(self.card_images) - 1) * card_spacing
                
                # Start x position to center the cards
                cards_start_x = self.rect.centerx - total_cards_width // 2
                
                # Draw each card image
                for i, card_img in enumerate(self.card_images):
                    draw_x = cards_start_x + i * (card_width + card_spacing)
                    draw_y = current_y
                    card_img.draw_front(draw_x, draw_y)
                
                current_y += card_height + settings.SMALL_SPACER_Y

        # Draw description if available and there's space
        if hasattr(self.figure.family, 'description') and self.figure.family.description:
            # Check if we have at least 80 pixels for description (title + 1-2 lines)
            if current_y + 80 <= max_content_y:
                pygame.draw.line(
                    self.window,
                    settings.COLOR_DIALOGUE_BOX_BORDER,
                    (self.rect.left + settings.SMALL_SPACER_X, current_y),
                    (self.rect.right - settings.SMALL_SPACER_X, current_y),
                    2
                )
                current_y += settings.SMALL_SPACER_Y

                desc_title = self.font.render("Description:", True, settings.TITLE_TEXT_COLOR)
                desc_title_rect = desc_title.get_rect(centerx=self.rect.centerx, top=current_y)
                self.window.blit(desc_title, desc_title_rect)
                current_y += desc_title_rect.height + settings.SMALL_SPACER_Y // 2

                # Wrap description text based on actual pixel width
                max_text_width = self.width - 4 * settings.SMALL_SPACER_X
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
                    if current_y + line_height >= max_content_y:
                        break
                    line_surface = self.small_font.render(line, True, settings.MSG_TEXT_COLOR)
                    line_rect = line_surface.get_rect(left=self.rect.left + settings.SMALL_SPACER_X * 2, top=current_y)
                    self.window.blit(line_surface, line_rect)
                    current_y += line_height

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
