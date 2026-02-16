import pygame
from config import settings
from game.components.arrow_button import ArrowButton
from game.components.cards.card_img import CardImg


class ScrollTextListShifter:
    def __init__(self, window, text_list, x, y, delta_x=-settings.get_x(0.01), num_texts_displayed=1,
                 shift_cooldown=300, scroll_height=None):
        """
        :param text_list: List of text dictionaries, each representing an item.
        :param scroll_height: Height of the scroll background for centering arrows. If None, uses default offset.
        """
        self.window = window
        self.title_font = pygame.font.Font(settings.FONT_PATH, int(settings.FONT_SIZE_DETAIL * 1.05))
        self.title_font.set_bold(True)
        self.scroll_font = pygame.font.Font(settings.FONT_PATH, int(settings.FONT_SIZE_DETAIL * 0.9))
        self.small_font = pygame.font.Font(settings.FONT_PATH, int(settings.FONT_SIZE_DETAIL * 0.75))
        self.text_list = text_list  # List of text dictionaries
        self.x = x
        self.y = y
        self.delta_x = delta_x  # Vertical spacing between text items
        self.num_texts_displayed = num_texts_displayed
        self.shift_cooldown = shift_cooldown  # Cooldown between shifts in milliseconds
        self.last_shift_time = 0  # To track time since the last shift

        self.card_imgs = self.initialize_card_imgs()
        
        # Load resource icons
        self.resource_icons = self._load_resource_icons()
        
        # Load check icons for spell attributes
        self.check_icons = self._load_check_icons()

        # Initialize text shifter states
        self.start_index = 0
        self.displayed_texts = []

        # Initialize arrow buttons for shifting
        # Position them slightly outside the scroll edges and centered vertically
        arrow_horizontal_offset = settings.get_x(0.02)  # Distance outside scroll edges
        left_x = self.x - arrow_horizontal_offset
        right_x = self.x + settings.SCROLL_TEXT_MAX_WIDTH + arrow_horizontal_offset
        
        # Calculate vertical center position
        if scroll_height is not None:
            # Center arrows vertically on the scroll background
            # Assuming scroll starts at y position passed in during init_scroll_background
            # We need to calculate where the scroll background actually is
            # The text position (self.y) is offset from the scroll background top
            # For BUILD_FIGURE: scroll_y = 0.15, text_y = 0.22, so text is 0.07 below scroll top
            # scroll_height = 0.44
            # Center = scroll top + height/2 = need to calculate scroll top from text position
            text_offset_from_scroll_top = settings.get_y(0.07)  # Typical offset
            scroll_top = self.y - text_offset_from_scroll_top
            arrow_y = scroll_top + scroll_height // 2
        else:
            # Default: position at a reasonable vertical offset
            arrow_y = self.y + settings.get_y(0.15)  # Better centered default

        self.arrow_up_button = ArrowButton(self.window, self.shift_up, x=left_x, y=arrow_y,
                                           direction='left', is_active=True)
        self.arrow_down_button = ArrowButton(self.window, self.shift_down, x=right_x, y=arrow_y,
                                             direction='right', is_active=True)

        # Update the initially displayed texts
        self.update_displayed_texts()

    def initialize_card_imgs(self):
        """Initialize card images with larger size for better visibility."""
        # Use 1.4x the mini card size for better visibility in scroll
        card_width = int(settings.MINI_CARD_WIDTH * 1.4)
        card_height = int(settings.MINI_CARD_HEIGHT * 1.4)
        return {(suit, rank): CardImg(self.window, suit, rank, width=card_width,
                                      height=card_height) for suit in settings.SUITS for rank in
                settings.RANKS_WITH_ZK}
    
    def _load_resource_icons(self):
        """Load and scale resource icons."""
        icon_size = int(settings.FONT_SIZE_DETAIL * 1.1)  # Slightly larger for visibility
        icons = {}
        
        # Use the predefined resource icon paths from settings
        if hasattr(settings, 'RESOURCE_ICON_IMG_PATH_DICT'):
            for resource, path in settings.RESOURCE_ICON_IMG_PATH_DICT.items():
                try:
                    icon = pygame.image.load(path).convert_alpha()
                    icons[resource] = pygame.transform.smoothscale(icon, (icon_size, icon_size))
                except Exception as e:
                    print(f"[SCROLL] Failed to load icon for {resource} from {path}: {e}")
        
        return icons
    
    def _load_check_icons(self):
        """Load and scale check icons (yes/no) for spell attributes."""
        icon_size = int(settings.FONT_SIZE_DETAIL * 1.0)  # Match font size
        icons = {}
        
        icon_paths = {
            'yes': 'img/figures/state_icons/check_yes.png',
            'no': 'img/figures/state_icons/check_no.png'
        }
        
        for icon_name, path in icon_paths.items():
            try:
                icon = pygame.image.load(path).convert_alpha()
                icons[icon_name] = pygame.transform.smoothscale(icon, (icon_size, icon_size))
            except Exception as e:
                print(f"[SCROLL] Failed to load check icon {icon_name} from {path}: {e}")
        
        return icons
    
    def _map_resource_to_icon(self, resource_name):
        """Map database resource names to icon keys."""
        resource_map = {
            'food_red': 'rice',
            'food_black': 'meat',
            'warrior_red': 'warrior_red',
            'warrior_black': 'warrior_black',
            'material_red': 'wood_stone',
            'material_black': 'wood_stone',
            'armor_red': 'sword_shield',
            'armor_black': 'sword_shield',
            'villager_red': 'villager_red',
            'villager_black': 'villager_black',
        }
        return resource_map.get(resource_name, resource_name)

    def shift_up(self):
        """Shift the text list upwards, respecting the cooldown."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.start_index = (self.start_index - 1) % len(self.text_list)
            self.update_displayed_texts()
            self.last_shift_time = current_time

    def shift_down(self):
        """Shift the text list downwards, respecting the cooldown."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.start_index = (self.start_index + 1) % len(self.text_list)
            self.update_displayed_texts()
            self.last_shift_time = current_time

    def update_displayed_texts(self):
        """Update the list of texts currently being displayed."""
        if len(self.text_list) <= self.num_texts_displayed:
            self.displayed_texts = self.text_list
        elif len(self.text_list) == 0:
            self.displayed_texts = []
        else:
            indices = [(self.start_index + i) % len(self.text_list) for i in range(self.num_texts_displayed)]
            self.displayed_texts = [self.text_list[i] for i in indices]

    def draw(self):
        """Draw the texts and arrow controls."""
        # Draw arrow buttons
        if len(self.text_list) > self.num_texts_displayed:
            self.arrow_up_button.draw()
            self.arrow_down_button.draw()

        # Draw displayed texts using the custom draw function
        x_offset = 0
        for text_dict in self.displayed_texts:
            self.draw_text_in_scroll(text_dict, self.x + x_offset, self.y)
            x_offset += self.delta_x

    def draw_text_in_scroll(self, text_dict, x, y, max_width=settings.SCROLL_TEXT_MAX_WIDTH):
        """Draw text to the screen with line breaks after reaching a certain width."""
        # TITLE
        title_obj = self.title_font.render(text_dict.get('title', ''), True, settings.SCROLL_TEXT_COLOR)
        title_rect = title_obj.get_rect()
        title_rect.midtop = (x + max_width // 2, y)
        self.window.blit(title_obj, title_rect)
        y += title_rect.height

        # Leave one blank line
        blank_line_height = self.scroll_font.size(" ")[1]
        y += blank_line_height * 0.5

        # CARDS
        if 'cards' in text_dict:
            cards = text_dict.get('cards', [])
            missing_cards = text_dict.get('missing_cards', [])
            total_cards = cards + missing_cards

            # Use object IDs for missing cards to avoid equality comparisons
            missing_card_ids = {id(card) for card in missing_cards}

            num_cards = len(total_cards)
            if num_cards > 0:
                card_img = self.card_imgs.get((total_cards[0].suit, total_cards[0].rank))
                card_width = card_img.front_img.get_width()
                card_height = card_img.front_img.get_height()
                
                # Calculate spacing - use negative spacing (overlap) for more than 2 cards
                if num_cards > 2:
                    # Calculate overlap needed to fit within max_width
                    total_cards_width = num_cards * card_width
                    available_width = max_width * 0.9  # Use 90% of available width
                    
                    if total_cards_width > available_width:
                        # Need overlap - calculate spacing to fit
                        spacer = (available_width - card_width) / (num_cards - 1) - card_width
                    else:
                        # Small positive spacing
                        spacer = card_width * 0.1
                else:
                    # 2 or fewer cards - use comfortable spacing
                    spacer = card_width * 0.2
                
                total_width = card_width + (num_cards - 1) * (card_width + spacer)

                card_x = x + (max_width - total_width) // 2
                for card in total_cards:
                    card_img = self.card_imgs.get((card.suit, card.rank))
                    if id(card) in missing_card_ids:
                        card_img.draw_missing(card_x, y)
                    else:
                        card_img.draw_front_bright(card_x, y)
                    card_x += card_width + spacer

                y += card_height + blank_line_height * 0.6

        # FIGURE TYPE or SPELL TYPE (subtitle)
        if 'figure_type' in text_dict:
            figure_type_obj = self.scroll_font.render(text_dict['figure_type'], True, settings.SCROLL_TEXT_COLOR)
            figure_type_rect = figure_type_obj.get_rect(topleft=(x, y))
            self.window.blit(figure_type_obj, figure_type_rect)
            y += figure_type_rect.height + blank_line_height * 0.6
        elif 'spell_type' in text_dict:
            spell_type_obj = self.scroll_font.render(text_dict['spell_type'], True, settings.SCROLL_TEXT_COLOR)
            spell_type_rect = spell_type_obj.get_rect(topleft=(x, y))
            self.window.blit(spell_type_obj, spell_type_rect)
            y += spell_type_rect.height + blank_line_height * 0.6

        # SPELL ATTRIBUTES (counterable, ceasefire) - with icons
        if 'counterable' in text_dict:
            # Render label text
            label_text = "Counterable:"
            label_obj = self.scroll_font.render(label_text, True, settings.SCROLL_TEXT_COLOR)
            label_rect = label_obj.get_rect(topleft=(x, y))
            self.window.blit(label_obj, label_rect)
            
            # Render icon
            icon_key = 'yes' if text_dict['counterable'] else 'no'
            if icon_key in self.check_icons:
                icon = self.check_icons[icon_key]
                icon_x = label_rect.right + int(settings.FONT_SIZE_DETAIL * 0.3)
                # Center icon vertically with text
                icon_y = y + (label_rect.height - icon.get_height()) // 2
                self.window.blit(icon, (icon_x, icon_y))
            
            y += label_rect.height + blank_line_height * 0.4
        
        if 'ceasefire' in text_dict:
            # Render label text
            label_text = "Ceasefire:"
            label_obj = self.scroll_font.render(label_text, True, settings.SCROLL_TEXT_COLOR)
            label_rect = label_obj.get_rect(topleft=(x, y))
            self.window.blit(label_obj, label_rect)
            
            # Render icon
            icon_key = 'yes' if text_dict['ceasefire'] else 'no'
            if icon_key in self.check_icons:
                icon = self.check_icons[icon_key]
                icon_x = label_rect.right + int(settings.FONT_SIZE_DETAIL * 0.3)
                # Center icon vertically with text
                icon_y = y + (label_rect.height - icon.get_height()) // 2
                self.window.blit(icon, (icon_x, icon_y))
            
            y += label_rect.height + blank_line_height * 0.8

        # POWER & SUPPORT (on same line or separate lines if needed)
        stats_line = ""
        if 'power' in text_dict:
            stats_line = f"Power: {text_dict['power']}"
        if 'support' in text_dict:
            if stats_line:
                stats_line += f"  |  Support: {text_dict['support']}"
            else:
                stats_line = f"Support: {text_dict['support']}"
        
        if stats_line:
            stats_obj = self.scroll_font.render(stats_line, True, settings.SCROLL_TEXT_COLOR)
            stats_rect = stats_obj.get_rect(topleft=(x, y))
            self.window.blit(stats_obj, stats_rect)
            y += stats_rect.height + blank_line_height * 0.8

        # PRODUCTION
        if 'produces' in text_dict and text_dict['produces']:
            # Draw divider line
            pygame.draw.line(
                self.window,
                settings.COLOR_DIALOGUE_BOX_BORDER,
                (x, y),
                (x + max_width, y),
                1
            )
            y += blank_line_height * 0.4
            
            # Draw "Production" label
            production_label = self.scroll_font.render("Production", True, settings.SCROLL_TEXT_COLOR)
            production_rect = production_label.get_rect(topleft=(x, y))
            self.window.blit(production_label, production_rect)
            y += production_rect.height + blank_line_height * 0.4
            
            # Draw resource icons and amounts
            current_x = x + blank_line_height * 0.5
            icon_spacing = int(blank_line_height * 0.3)
            
            for resource, amount in text_dict['produces'].items():
                icon_key = self._map_resource_to_icon(resource)
                
                # Draw icon if available
                if icon_key in self.resource_icons:
                    icon = self.resource_icons[icon_key]
                    self.window.blit(icon, (current_x, y))
                    current_x += icon.get_width() + 2
                    
                    # Draw amount next to icon
                    amount_text = self.small_font.render(f"{amount}", True, settings.SCROLL_TEXT_COLOR)
                    self.window.blit(amount_text, (current_x, y + (icon.get_height() - amount_text.get_height()) // 2))
                    current_x += amount_text.get_width() + icon_spacing
                else:
                    # Fallback to text only
                    text = self.small_font.render(f"{resource.replace('_', ' ').title()}: {amount}", True, settings.SCROLL_TEXT_COLOR)
                    self.window.blit(text, (current_x, y))
                    current_x += text.get_width() + icon_spacing
            
            # Move y down by icon height
            if self.resource_icons:
                first_icon = list(self.resource_icons.values())[0]
                y += first_icon.get_height() + blank_line_height * 0.4
            else:
                y += blank_line_height

        # REQUIREMENTS
        if 'requires' in text_dict and text_dict['requires']:
            # Draw divider line
            pygame.draw.line(
                self.window,
                settings.COLOR_DIALOGUE_BOX_BORDER,
                (x, y),
                (x + max_width, y),
                1
            )
            y += blank_line_height * 0.4
            
            # Draw "Requirements" label
            requirements_label = self.scroll_font.render("Requirements", True, settings.SCROLL_TEXT_COLOR)
            requirements_rect = requirements_label.get_rect(topleft=(x, y))
            self.window.blit(requirements_label, requirements_rect)
            y += requirements_rect.height + blank_line_height * 0.4
            
            # Draw resource icons and amounts
            current_x = x + blank_line_height * 0.5
            icon_spacing = int(blank_line_height * 0.3)
            
            for resource, amount in text_dict['requires'].items():
                icon_key = self._map_resource_to_icon(resource)
                
                # Draw icon if available
                if icon_key in self.resource_icons:
                    icon = self.resource_icons[icon_key]
                    self.window.blit(icon, (current_x, y))
                    current_x += icon.get_width() + 2
                    
                    # Draw amount next to icon
                    amount_text = self.small_font.render(f"{amount}", True, settings.SCROLL_TEXT_COLOR)
                    self.window.blit(amount_text, (current_x, y + (icon.get_height() - amount_text.get_height()) // 2))
                    current_x += amount_text.get_width() + icon_spacing
                else:
                    # Fallback to text only
                    text = self.small_font.render(f"{resource.replace('_', ' ').title()}: {amount}", True, settings.SCROLL_TEXT_COLOR)
                    self.window.blit(text, (current_x, y))
                    current_x += text.get_width() + icon_spacing
            
            # Move y down by icon height
            if self.resource_icons:
                first_icon = list(self.resource_icons.values())[0]
                y += first_icon.get_height() + blank_line_height * 0.4
            else:
                y += blank_line_height

        # TEXT (description)
        if 'text' in text_dict and text_dict['text']:
            # Draw divider line before description
            pygame.draw.line(
                self.window,
                settings.COLOR_DIALOGUE_BOX_BORDER,
                (x, y),
                (x + max_width, y),
                1
            )
            y += blank_line_height * 0.4
            
            for line in self.wrap_text_lines(text_dict.get('text', ''), max_width, use_small_font=True):
                text_obj = self.small_font.render(line, True, settings.SCROLL_TEXT_COLOR)
                text_rect = text_obj.get_rect(topleft=(x, y))
                self.window.blit(text_obj, text_rect)
                y += text_rect.height + blank_line_height * 0.1

        # FIGURE STRENGTH (keep for backward compatibility with non-figure items)
        if 'figure_strength' in text_dict:
            y += blank_line_height * 0.4
            strength_obj = self.scroll_font.render(text_dict['figure_strength'], True, settings.SCROLL_TEXT_COLOR)
            strength_rect = strength_obj.get_rect(midtop=(x + max_width // 2, y))
            self.window.blit(strength_obj, strength_rect)
            y += strength_rect.height

    def wrap_text_lines(self, text, max_width, use_small_font=False):
        """Wrap text into multiple lines based on maximum width."""
        font = self.small_font if use_small_font else self.scroll_font
        words = text.split(' ')
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines

    def set_displayed_texts(self, text_list):
        """Update the list of texts to be displayed."""
        self.text_list = text_list
        self.update_displayed_texts()

    def get_current_selected(self):
        """Return the currently selected content."""
        if not self.displayed_texts:  # Ensure there are displayed texts
            return None
        if self.num_texts_displayed == 1:
            selected = self.displayed_texts[0] if self.displayed_texts else None
            return selected.get('content', selected) if selected else None  # Safeguard against None
        return [text_dict.get('content', text_dict) for text_dict in self.displayed_texts if text_dict]


    def update(self):
        """Update the arrow buttons."""
        self.arrow_up_button.update()
        self.arrow_down_button.update()

    def handle_events(self, events):
        """Handle events for the arrows."""
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.arrow_up_button.hovered:
                    self.shift_up()
                elif self.arrow_down_button.hovered:
                    self.shift_down()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.shift_up()
                elif event.key == pygame.K_DOWN:
                    self.shift_down()
