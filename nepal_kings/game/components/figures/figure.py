from typing import List, Optional
import pygame
#from config import settings
from game.components.cards.card import Card
from game.components.figures.figure_icon import BuildFigureIcon
from config import settings

class FigureFamily:
    """Represents a family of figures with shared attributes."""
    def __init__(
        self,
        name: str,
        color: str,
        suits: List[str],
        figures: List['Figure'],
        icon_img: pygame.Surface,
        icon_gray_img: pygame.Surface,
        frame_img: pygame.Surface,
        frame_closed_img: pygame.Surface,
        frame_hidden_img: pygame.Surface,
        build_position: Optional[tuple] = None,
        description: str = "",
        field: Optional[str] = None,
    ):
        self.name = name
        self.color = color
        self.suits = suits
        self.figures = figures
        self.icon_img = icon_img
        self.icon_gray_img = icon_gray_img
        self.frame_img = frame_img
        self.frame_closed_img = frame_closed_img
        self.frame_hidden_img = frame_hidden_img
        self.build_position = build_position
        self.description = description
        self.field = field


    def make_icon(self, window, game, x, y) -> BuildFigureIcon:
        """Creates a figure icon for this family."""
        return BuildFigureIcon(window, game, self, x, y)
       
    def get_figures_by_suit(self, suit: str) -> List['Figure']:
        """Returns all figures of this family for a specific suit."""
        return [figure for figure in self.figures if figure.suit == suit]


class Figure:
    """Represents a specific figure with its attributes and gameplay logic."""
    def __init__(
        self,
        name: str,
        sub_name: str,
        suit: str,
        family: FigureFamily,
        key_cards: List[Card],
        number_card: Optional[Card] = None,
        upgrade_card: Optional[Card] = None,
        upgrade_family_name: Optional[str] = None,
        extension_card: Optional[Card] = None,
        extension_family_name: Optional[str] = None,
        attachment_family_name: Optional[str] = None,
        produces: Optional[dict] = None,  # Resources produced by figure
        requires: Optional[dict] = None,  # Resources required by figure
        description: str = "",
        id: Optional[int] = None,
        player_id: Optional[int] = None,
    ):
        self.name = name
        self.sub_name = sub_name
        self.suit = suit
        self.family = family
        self.key_cards = key_cards
        self.number_card = number_card
        self.upgrade_card = upgrade_card
        self.upgrade_family_name = upgrade_family_name
        self.player_id = player_id
        self.produces = produces or {}  # Default to empty dict
        self.requires = requires or {}  # Default to empty dict
        # Keep old 'resources' attribute for backward compatibility (alias to produces)
        self.resources = self.produces
        #self.extension_card = extension_card
        #self.extension_family_name = extension_family_name
        #self.attachment_family_name = attachment_family_name
        self.description = description

        # Derived properties for gameplay logic
        self.cards = self.key_cards[:]  # Include key cards
        if self.number_card:
            self.cards.append(self.number_card)
        self.cards_including_upgrade = self.cards[:]
        if self.upgrade_card:
            self.cards_including_upgrade.append(self.upgrade_card)
        #if self.extension_card:
        #    self.cards.append(self.extension_card)

        self.value = self.get_value()  # Value of the figure

        # Placeholder for relationships with other figures
        self.upgrade_to: List['Figure'] = []
        self.extensions: List['Figure'] = []

        # Store the figure's ID
        self.id = id

    def get_value(self) -> int:
        """Returns the value of the figure."""
        v = 0
        for card in self.cards:
            v += card.value
        return v

    def add_upgrade(self, figure: 'Figure'):
        """Links this figure to an upgraded version."""
        self.upgrade_to.append(figure)

    def is_match(self, cards: List[Card]) -> bool:
        """Checks if a given set of cards can build this figure."""
        required_cards = {card.to_tuple() for card in self.cards}
        provided_cards = {card.to_tuple() for card in cards}
        return required_cards <= provided_cards  # Subset check

    def has_upgrade(self) -> bool:
        """Checks if the figure can be upgraded."""
        return self.upgrade_family_name is not None

    def __repr__(self):
        return f"Figure(name={self.name}, suit={self.suit}, family={self.family.name})"


   
class VillageFigure(Figure):
    """Represents a figure of the Village I family."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class MilitaryFigure(Figure):
    """Represents a figure of the Military I family."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class CastleFigure(Figure):
    """Represents a figure of the Castle family."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)