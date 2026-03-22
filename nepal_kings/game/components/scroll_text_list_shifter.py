import pygame
from config import settings
from config.screen_settings import _UI_SCALE
from game.components.cards.card_img import CardImg


class ScrollTextListShifter:
    def __init__(self, window, text_list, x, y, delta_x=-settings.get_x(0.01), num_texts_displayed=1,
                 shift_cooldown=300, scroll_height=None, scroll_rect=None):
        """
        :param text_list: List of text dictionaries, each representing an item.
        :param scroll_height: Height of the scroll background for centering arrows. If None, uses default offset.
        :param scroll_rect: pygame.Rect of the scroll panel (for clipping & chevron placement).
        """
        self.window = window
        self.title_font = settings.get_font(settings.SCROLL_FONT_SIZE_TITLE, bold=True)
        self.scroll_font = settings.get_font(settings.SCROLL_FONT_SIZE_BODY)
        self.small_font = settings.get_font(settings.SCROLL_FONT_SIZE_SMALL)
        self.counter_font = settings.get_font(settings.SCROLL_FONT_SIZE_SMALL)
        self.text_list = text_list  # List of text dictionaries
        self.x = x
        self.y = y
        self.delta_x = delta_x  # Vertical spacing between text items
        self.num_texts_displayed = num_texts_displayed
        self.shift_cooldown = shift_cooldown  # Cooldown between shifts in milliseconds
        self.last_shift_time = 0  # To track time since the last shift
        self.scroll_height = scroll_height  # Store scroll height for scrollbar calculations
        self.scroll_rect = scroll_rect  # Panel rect for clipping

        self.card_imgs = self.initialize_card_imgs()
        
        # Load resource icons
        self.resource_icons = self._load_resource_icons()
        
        # Load check icons for spell attributes
        self.check_icons = self._load_check_icons()
        
        # Load skill icons for figure attributes
        self.skill_icons = self._load_skill_icons()

        # Initialize text shifter states
        self.start_index = 0
        self.displayed_texts = []

        # ------ Chevron / navigation bar inside the panel, horizontally centred ------
        self._chevron_sz = settings.SCROLL_CHEVRON_SIZE
        self._chevron_lw = settings.SCROLL_CHEVRON_LINE_W

        # Height reserved for navigation bar (chevrons + dots) at the bottom
        self._nav_bar_h = int(0.055 * settings.SCREEN_HEIGHT)

        if scroll_rect is not None:
            panel_cx = scroll_rect.x + scroll_rect.width // 2
            # Place nav bar near the bottom of the panel
            bar_y = scroll_rect.y + scroll_rect.height - int(0.028 * settings.SCREEN_HEIGHT)
        else:
            panel_cx = self.x + settings.SCROLL_TEXT_MAX_WIDTH // 2
            bar_y = self.y - int(0.02 * settings.SCREEN_HEIGHT)

        # Chevron spacing from centre — leave room for the counter text
        chev_offset = int(0.04 * settings.SCREEN_WIDTH)
        self._arrow_y = bar_y
        self._left_x = panel_cx - chev_offset
        self._right_x = panel_cx + chev_offset
        self._counter_cx = panel_cx  # centre x for "1 / N" text

        # Hit rects for chevron hover / click detection
        hit_sz = self._chevron_sz * 3
        self._left_hit = pygame.Rect(self._left_x - hit_sz // 2,
                                     self._arrow_y - hit_sz // 2,
                                     hit_sz, hit_sz)
        self._right_hit = pygame.Rect(self._right_x - hit_sz // 2,
                                      self._arrow_y - hit_sz // 2,
                                      hit_sz, hit_sz)
        self._left_hovered = False
        self._right_hovered = False

        # ------ Vertical content scroll offset (for overflow) ------
        self._content_scroll_y = 0  # pixel offset (negative = scrolled down)
        self._content_scroll_speed = int(0.025 * settings.SCREEN_HEIGHT)
        self._last_content_h = 0    # rendered height of current item (updated each draw)

        # ------ Touch-drag scrolling state ------
        self._touch_scrolling = False
        self._touch_last_y = 0

        # Clip rect: area where text content should be visible
        # Content fills from the top of the panel down to just above the nav bar
        if scroll_rect is not None:
            top_pad = int(0.020 * settings.SCREEN_HEIGHT)
            self._clip_rect = pygame.Rect(
                scroll_rect.x + 4,
                scroll_rect.y + top_pad,
                scroll_rect.width - 8,
                scroll_rect.height - top_pad - self._nav_bar_h
            )
            # Content starts at the top of the clip area (overrides caller's y)
            self.y = self._clip_rect.y + int(0.010 * settings.SCREEN_HEIGHT)
        else:
            self._clip_rect = None

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
        icon_size = settings.SCROLL_ICON_SIZE
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
        icon_size = settings.SCROLL_ICON_SIZE
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
    
    def _load_skill_icons(self):
        """Load and scale skill icons for combat attributes."""
        icon_size = settings.SCROLL_SKILL_ICON_SIZE
        icons = {}
        
        if hasattr(settings, 'SKILL_ICON_IMG_PATH_DICT'):
            for skill, path in settings.SKILL_ICON_IMG_PATH_DICT.items():
                try:
                    icon = pygame.image.load(path).convert_alpha()
                    icons[skill] = pygame.transform.smoothscale(icon, (icon_size, icon_size))
                except Exception as e:
                    print(f"[SCROLL] Failed to load skill icon {skill} from {path}: {e}")
        
        return icons
    
    def _map_resource_to_icon(self, resource_name):
        """Map database resource names to icon keys."""
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
        return resource_map.get(resource_name, resource_name)

    def shift_up(self):
        """Shift the text list upwards, respecting the cooldown."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.start_index = (self.start_index - 1) % len(self.text_list)
            self._content_scroll_y = 0  # reset vertical scroll on item change
            self.update_displayed_texts()
            self.last_shift_time = current_time

    def shift_down(self):
        """Shift the text list downwards, respecting the cooldown."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.start_index = (self.start_index + 1) % len(self.text_list)
            self._content_scroll_y = 0  # reset vertical scroll on item change
            self.update_displayed_texts()
            self.last_shift_time = current_time

    def _max_scroll(self):
        """Return the max negative scroll offset based on actual content height."""
        if self._clip_rect and self._last_content_h > self._clip_rect.height:
            return self._last_content_h - self._clip_rect.height
        return 0  # no overflow — no scrolling allowed

    def _content_overflows(self):
        """Return True if the rendered content is taller than the clip area."""
        if self._clip_rect:
            return self._last_content_h > self._clip_rect.height
        return False

    def update_displayed_texts(self):
        """Update the list of texts currently being displayed."""
        if len(self.text_list) <= self.num_texts_displayed:
            self.displayed_texts = self.text_list
        elif len(self.text_list) == 0:
            self.displayed_texts = []
        else:
            indices = [(self.start_index + i) % len(self.text_list) for i in range(self.num_texts_displayed)]
            self.displayed_texts = [self.text_list[i] for i in indices]

    def _draw_chevron(self, cx, cy, direction, hovered):
        """Draw a chevron arrow (< or >) at the given centre."""
        sz = self._chevron_sz
        clr = settings.SCROLL_CHEVRON_HOVER_COLOR if hovered else settings.SCROLL_CHEVRON_COLOR
        if direction == 'left':
            points = [(cx + sz, cy - sz), (cx, cy), (cx + sz, cy + sz)]
        else:
            points = [(cx, cy - sz), (cx + sz, cy), (cx, cy + sz)]
        pygame.draw.lines(self.window, clr, False, points, self._chevron_lw)

    def draw(self):
        """Draw the navigation bar, dot indicator, and clipped text content."""
        n = len(self.text_list)

        # ---- Navigation bar (chevrons + dots) — fixed at bottom of panel ----
        if n > self.num_texts_displayed:
            self._draw_chevron(self._left_x, self._arrow_y, 'left', self._left_hovered)
            self._draw_chevron(self._right_x, self._arrow_y, 'right', self._right_hovered)

            # Dot position indicator centred vertically with chevrons
            dot_r = max(3, int(0.004 * settings.SCREEN_HEIGHT))
            dot_gap = dot_r * 3
            total_w = n * dot_r * 2 + (n - 1) * (dot_gap - dot_r * 2)
            dot_cx_start = self._counter_cx - total_w // 2 + dot_r
            dot_cy = self._arrow_y  # same vertical centre as chevrons

            for i in range(n):
                cx = dot_cx_start + i * dot_gap
                if i == self.start_index:
                    pygame.draw.circle(self.window, settings.SCROLL_CHEVRON_HOVER_COLOR, (cx, dot_cy), dot_r)
                else:
                    pygame.draw.circle(self.window, settings.SCROLL_CHEVRON_COLOR, (cx, dot_cy), max(2, dot_r - 1))

        # ---- Draw content with clipping so overflow is hidden ----
        if self._clip_rect is not None:
            self.window.set_clip(self._clip_rect)

        x_offset = 0
        for text_dict in self.displayed_texts:
            end_y = self.draw_text_in_scroll(text_dict, self.x + x_offset,
                                             self.y + self._content_scroll_y)
            # Track rendered content height (relative to content start)
            self._last_content_h = end_y - (self.y + self._content_scroll_y)
            x_offset += self.delta_x

        if self._clip_rect is not None:
            self.window.set_clip(None)  # reset clipping

        # ---- Thin scroll-progress bar on right edge if content is scrolled ----
        if self._clip_rect is not None and self._content_overflows() and self._content_scroll_y < 0:
            bar_x = self._clip_rect.right - 3
            bar_h = self._clip_rect.height
            # Thumb size proportional to visible / total content
            visible_frac = self._clip_rect.height / max(1, self._last_content_h)
            thumb_h = max(20, int(bar_h * min(1.0, visible_frac)))
            scroll_range = self._max_scroll() or 1
            frac = min(1.0, abs(self._content_scroll_y) / scroll_range)
            thumb_y = self._clip_rect.y + int(frac * (bar_h - thumb_h))
            pygame.draw.rect(self.window, settings.SCROLL_CHEVRON_COLOR,
                             (bar_x, thumb_y, 3, thumb_h), border_radius=1)

    def draw_text_in_scroll(self, text_dict, x, y, max_width=settings.SCROLL_TEXT_MAX_WIDTH):
        """Draw text to the screen with line breaks after reaching a certain width."""
        # TITLE — gold
        title_obj = self.title_font.render(text_dict.get('title', ''), True, settings.SCROLL_TEXT_TITLE_COLOR)
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
                icon_x = label_rect.right + int(settings.SCROLL_ICON_SIZE * 0.3)
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
                icon_x = label_rect.right + int(settings.SCROLL_ICON_SIZE * 0.3)
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
                settings.SCROLL_TEXT_DIVIDER_COLOR,
                (x, y),
                (x + max_width, y),
                1
            )
            y += blank_line_height * 0.4
            
            # Draw "Production" label
            production_label = self.scroll_font.render("Production", True, settings.SCROLL_TEXT_SECTION_COLOR)
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
                settings.SCROLL_TEXT_DIVIDER_COLOR,
                (x, y),
                (x + max_width, y),
                1
            )
            y += blank_line_height * 0.4
            
            # Draw "Requirements" label
            requirements_label = self.scroll_font.render("Requirements", True, settings.SCROLL_TEXT_SECTION_COLOR)
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

        # SKILLS
        from game.components.figures.family_configs.skill_config import SKILL_KEYS, SKILL_DEFINITIONS as _SKILL_DEFS
        from game.components.figures.family_configs.skill_config import get_advantage_suit
        skills_to_display = []
        for key in SKILL_KEYS:
            if key in text_dict and text_dict[key]:
                skills_to_display.append((key, _SKILL_DEFS[key]['name']))
        
        # Load advantage suit icon if any skill uses suit_advantage
        adv_suit_icon = None
        figure_obj = text_dict.get('content')
        suit_str = None
        if figure_obj and hasattr(figure_obj, 'suit'):
            suit_str = figure_obj.suit
        elif text_dict.get('suit'):
            suit_str = text_dict['suit']
        if suit_str:
            adv_suit = get_advantage_suit(suit_str or '')
            if adv_suit:
                # Slightly smaller than skill icon for centered overlay
                skill_icon_size = settings.SCROLL_SKILL_ICON_SIZE
                icon_size = int(skill_icon_size * 0.85)
                suit_file = adv_suit.lower() + '.png'
                try:
                    suit_path = settings.SUIT_ICON_IMG_PATH + suit_file
                    suit_img = pygame.image.load(suit_path).convert_alpha()
                    adv_suit_icon = pygame.transform.smoothscale(suit_img, (icon_size, icon_size))
                except Exception:
                    pass
        
        if skills_to_display:
            # Draw divider line
            pygame.draw.line(
                self.window,
                settings.SCROLL_TEXT_DIVIDER_COLOR,
                (x, y),
                (x + max_width, y),
                1
            )
            y += blank_line_height * 0.4
            
            # Draw "Skills" label
            skills_label = self.scroll_font.render("Skills", True, settings.SCROLL_TEXT_SECTION_COLOR)
            skills_rect = skills_label.get_rect(topleft=(x, y))
            self.window.blit(skills_label, skills_rect)
            y += skills_rect.height + blank_line_height * 0.4
            
            # Draw skill icons and names (1 per row on mobile, 2 on desktop)
            _max_per_row = 1 if _UI_SCALE > 1.0 else 2
            current_x = x + blank_line_height * 0.5
            icon_spacing = int(blank_line_height * 0.3)
            skills_in_row = 0
            row_height = 0
            
            for skill_key, skill_name in skills_to_display:
                # Start a new row when row is full
                if skills_in_row >= _max_per_row:
                    y += row_height + blank_line_height * 0.3
                    current_x = x + blank_line_height * 0.5
                    skills_in_row = 0
                    row_height = 0
                
                # Draw icon if available
                if skill_key in self.skill_icons:
                    icon = self.skill_icons[skill_key]
                    
                    # Draw white glow behind skill icon
                    glow_size = int(icon.get_width() * 1.5)
                    glow_surface = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
                    glow_center = glow_size // 2
                    glow_radius = glow_size // 2
                    for r in range(glow_radius, 0, -1):
                        alpha = int(120 * (1 - (r / glow_radius) ** 1.5))
                        pygame.draw.circle(glow_surface, (255, 255, 255, alpha), (glow_center, glow_center), r)
                    glow_x = current_x + (icon.get_width() - glow_size) // 2
                    glow_y = y + (icon.get_height() - glow_size) // 2
                    self.window.blit(glow_surface, (glow_x, glow_y))
                    
                    # Draw suit icon behind skill icon (background), centered
                    if adv_suit_icon and _SKILL_DEFS.get(skill_key, {}).get('suit_advantage', False):
                        adv_x = current_x + (icon.get_width() - adv_suit_icon.get_width()) // 2
                        adv_y = y + (icon.get_height() - adv_suit_icon.get_height()) // 2
                        self.window.blit(adv_suit_icon, (adv_x, adv_y))
                    # Draw skill icon on top (foreground)
                    self.window.blit(icon, (current_x, y))
                    
                    current_x += icon.get_width() + 2
                    
                    # Draw skill name next to icon
                    skill_text = self.small_font.render(skill_name, True, settings.SCROLL_TEXT_COLOR)
                    self.window.blit(skill_text, (current_x, y + (icon.get_height() - skill_text.get_height()) // 2))
                    current_x += skill_text.get_width() + icon_spacing
                    row_height = max(row_height, icon.get_height())
                else:
                    # Fallback to text only
                    skill_text = self.small_font.render(f"• {skill_name}", True, settings.SCROLL_TEXT_COLOR)
                    self.window.blit(skill_text, (current_x, y))
                    current_x += skill_text.get_width() + icon_spacing
                    row_height = max(row_height, skill_text.get_height())
                
                skills_in_row += 1
            
            # Move y down by last row height
            if row_height > 0:
                y += row_height + blank_line_height * 0.4
            elif self.skill_icons:
                first_icon = list(self.skill_icons.values())[0]
                y += first_icon.get_height() + blank_line_height * 0.4
            else:
                y += blank_line_height

        # TEXT (description)
        if 'text' in text_dict and text_dict['text']:
            # Draw divider line before description
            pygame.draw.line(
                self.window,
                settings.SCROLL_TEXT_DIVIDER_COLOR,
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

        return y  # return final y so caller can measure content height

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
        self._content_scroll_y = 0  # reset content scroll on new data
        self._last_content_h = 0   # reset measured content height
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
        """Update chevron hover states."""
        mx, my = pygame.mouse.get_pos()
        self._left_hovered = self._left_hit.collidepoint(mx, my)
        self._right_hovered = self._right_hit.collidepoint(mx, my)

    def handle_events(self, events):
        """Handle events for the chevron arrows and content scrolling."""
        can_scroll = self._content_overflows()
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # left click / touch
                    if self._left_hovered:
                        self.shift_up()
                    elif self._right_hovered:
                        self.shift_down()
                    elif can_scroll and self._clip_rect and self._clip_rect.collidepoint(event.pos):
                        # Start touch-drag scroll tracking
                        self._touch_scrolling = True
                        self._touch_last_y = event.pos[1]
                # Mouse wheel — scroll content vertically when inside the panel
                elif event.button == 4 and can_scroll:  # wheel up
                    if self._clip_rect and self._clip_rect.collidepoint(pygame.mouse.get_pos()):
                        self._content_scroll_y = min(0, self._content_scroll_y + self._content_scroll_speed)
                elif event.button == 5 and can_scroll:  # wheel down
                    if self._clip_rect and self._clip_rect.collidepoint(pygame.mouse.get_pos()):
                        self._content_scroll_y = max(-self._max_scroll(),
                                                     self._content_scroll_y - self._content_scroll_speed)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._touch_scrolling = False
            elif event.type == pygame.MOUSEMOTION and self._touch_scrolling:
                # Touch-drag vertical scrolling
                dy = event.pos[1] - self._touch_last_y
                self._touch_last_y = event.pos[1]
                self._content_scroll_y += dy
                self._content_scroll_y = max(-self._max_scroll(), min(0, self._content_scroll_y))
            elif event.type == pygame.MOUSEWHEEL and can_scroll:
                # Some systems use MOUSEWHEEL instead of button 4/5
                if self._clip_rect and self._clip_rect.collidepoint(pygame.mouse.get_pos()):
                    if event.y > 0:  # scroll up
                        self._content_scroll_y = min(0, self._content_scroll_y + self._content_scroll_speed)
                    elif event.y < 0:  # scroll down
                        self._content_scroll_y = max(-self._max_scroll(),
                                                     self._content_scroll_y - self._content_scroll_speed)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT:
                    self.shift_up()
                elif event.key == pygame.K_RIGHT:
                    self.shift_down()
                elif event.key == pygame.K_UP and can_scroll:
                    self._content_scroll_y = min(0, self._content_scroll_y + self._content_scroll_speed)
                elif event.key == pygame.K_DOWN and can_scroll:
                    self._content_scroll_y = max(-self._max_scroll(),
                                                 self._content_scroll_y - self._content_scroll_speed)
