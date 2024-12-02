from typing import Dict, List, Optional
import pygame
from config import settings
from game.components.figure_icon import FigureIcon

import pygame
from typing import List, Optional, Tuple
from config import settings

class FigureFamily:
    def __init__(
        self,
        name: str,
        color: str,
        icon_img: pygame.Surface,
        icon_gray_img: pygame.Surface,
        frame_img: pygame.Surface,
        frame_closed_img: pygame.Surface,
        description: str = "",
        field: Optional[str] = None,
    ):
        self.name = name
        self.color = color
        self.icon_img = icon_img
        self.icon_gray_img = icon_gray_img
        self.frame_img = frame_img
        self.frame_closed_img = frame_closed_img
        self.description = description
        self.field = field
        

class Figure:
    def __init__(
        self,
        name: str,
        suit: str,
        icon_img: pygame.Surface,
        icon_darkwhite_img: pygame.Surface,
        visible_img: pygame.Surface,
        hidden_img: pygame.Surface,
        key_cards: List[Tuple[str, str]],
        number_card: Optional[Tuple[str, str]] = None,
        upgrade_card: Optional[Tuple[str, str]] = None,
        extension_card: Optional[Tuple[str, str]] = None,
        description: str = "",
        field: Optional[str] = None,
    ):
        self.name = name
        self.suit = suit
        self.icon_img = icon_img
        self.icon_darkwhite_img = icon_darkwhite_img
        self.visible_img = visible_img
        self.hidden_img = hidden_img
        self.key_cards = key_cards
        self.number_card = number_card
        self.upgrade_card = upgrade_card
        self.extension_card = extension_card
        self.description = description
        self.field = field
        self.upgrade_to = []

        # Aggregate all cards for matching purposes
        self.cards = self.key_cards[:]
        if self.number_card:
            self.cards.append(self.number_card)
        if self.upgrade_card:
            self.cards.append(self.upgrade_card)
        if self.extension_card:
            self.cards.append(self.extension_card)

        # make figure icon
        self.icon = FigureIcon(self.icon_img, self.icon_darkwhite_img)

    def draw(self, window: pygame.Surface, x: int, y: int, visible: bool = True) -> None:
        """Draw the figure's image."""
        img = self.visible_img if visible else self.hidden_img
        window.blit(img, (x, y))


class FigureManager:
    def __init__(self):
        self.figures: List[Figure] = []
        self.figures_by_field: Dict[str, List[Figure]] = {"all": [], "village": [], "military": [], "castle": []}
        self.figures_by_suit: Dict[str, List[Figure]] = {suit: [] for suit in settings.SUITS}
        self.figures_by_name: Dict[str, List[Figure]] = {}
        self.figures_by_number_card: Dict[Optional[Tuple[str, str]], List[Figure]] = {}

        # Initialize figures
        self.initialize_figures()

    def initialize_figures(self):
        """Initialize all figures."""
        self.initialize_main_figures(
            name="Farm",
            description=["Farm I description", "Farm II description", "Farm I w/ Altar", "Farm II w/ Altar"],
            img="farm",
            key_ranks=["J"],
            upgrade_rank="Q",
            field="village",
        )
        self.initialize_main_figures(
            name="Temple",
            description=["Temple I desc", "Temple II desc", "Temple I w/ Altar", "Temple II w/ Altar"],
            img="temple",
            key_ranks=["Q", "Q"],
            upgrade_rank="7",
            field="village",
        )
        self.initialize_side_figures(
            name="Archery",
            description="Archery description",
            img="catapult",
            key_ranks=["J", "3"],
        )
        self.initialize_side_figures(
            name="Wall",
            description="Wall description",
            img="wall",
            key_ranks=["4", "5", "6"],
            suits=["Spades", "Clubs"],
        )

    def load_images(self, img_name: str, is_hidden: bool = False) -> pygame.Surface:
        """Load and optionally scale an image."""
        base_path = settings.FIGURE_HIDDEN_IMG_PATH if is_hidden else settings.FIGURE_VISIBLE_IMG_PATH
        img_path = f"{base_path}{img_name}.png"
        img = pygame.image.load(img_path)
        return pygame.transform.scale(img, (settings.FIGURE_WIDTH, settings.FIGURE_HEIGHT))

    def initialize_side_figures(
        self, name: str, description: str, img: str, key_ranks: List[str], suits: List[str] = settings.SUITS, field: str = "military"
    ):
        """Initialize side figures."""
        icon_img = pygame.image.load(f"{settings.FIGURE_ICON_IMG_PATH}{img}.png")
        icon_darkwhite_img = pygame.image.load(f"{settings.FIGURE_ICON_DARKWHITE_IMG_PATH}{img}.png")
        visible_img = self.load_images(img)
        hidden_img = self.load_images(img, is_hidden=True)

        for suit in suits:
            key_cards = [(suit, rank) for rank in key_ranks]
            self.add_figure(
                Figure(
                    name=name,
                    suit=suit,
                    icon_img=icon_img,
                    icon_darkwhite_img=icon_darkwhite_img,
                    visible_img=visible_img,
                    hidden_img=hidden_img,
                    key_cards=key_cards,
                    description=description,
                    field=field,
                )
            )

    def initialize_main_figures(
        self,
        name: str,
        description: List[str],
        img: str,
        key_ranks: List[str],
        upgrade_rank: Optional[str] = None,
        number_ranks: List[str] = settings.NUMBER_CARDS,
        suits: List[str] = settings.SUITS,
        field: str = "village",
    ):
        """Initialize main figures."""
        icon_img1 = pygame.image.load(f"{settings.FIGURE_ICON_IMG_PATH}{img}1.png")
        icon_img2 = pygame.image.load(f"{settings.FIGURE_ICON_IMG_PATH}{img}2.png")
        icon_darkwhite_img1 = pygame.image.load(f"{settings.FIGURE_ICON_DARKWHITE_IMG_PATH}{img}1.png")
        icon_darkwhite_img2 = pygame.image.load(f"{settings.FIGURE_ICON_DARKWHITE_IMG_PATH}{img}2.png")
        visible_img1 = self.load_images(f"{img}1")
        visible_img2 = self.load_images(f"{img}2")
        hidden_img = self.load_images("village" if field == "village" else img, is_hidden=True)

        for suit in suits:
            key_cards = [(suit, rank) for rank in key_ranks]
            for number_rank in number_ranks:
                number_card = (suit, number_rank) if number_rank else None
                upgrade_card = (suit, upgrade_rank)
                self.add_main_figure(name, suit, key_cards, number_card, upgrade_card, field, description, icon_img1, icon_img2, icon_darkwhite_img1, icon_darkwhite_img2, visible_img1, visible_img2, hidden_img)

    def add_main_figure(self, name, suit, key_cards, number_card, upgrade_card, field, description, icon_img1, icon_img2, icon_darkwhite_img1, icon_darkwhite_img2, visible_img1, visible_img2, hidden_img):
        """Add main figures to the manager."""
        self.add_figure(
            Figure(name=f"{name} I", suit=suit, icon_img=icon_img1, icon_darkwhite_img=icon_darkwhite_img1, visible_img=visible_img1, hidden_img=hidden_img, key_cards=key_cards, number_card=number_card, description=description[0], field=field)
        )
        self.add_figure(
            Figure(name=f"{name} II", suit=suit, icon_img=icon_img2, icon_darkwhite_img=icon_darkwhite_img2, visible_img=visible_img2, hidden_img=hidden_img, key_cards=key_cards, number_card=number_card, upgrade_card=upgrade_card, description=description[1], field=field)
        )
        self.figures[-2].upgrade_to.append(self.figures[-1])

    def add_figure(self, figure: Figure) -> None:
        """Add a figure to the manager and categorize it."""
        self.figures.append(figure)
        self.figures_by_field[figure.field].append(figure)
        self.figures_by_suit[figure.suit].append(figure)
        self.figures_by_name.setdefault(figure.name, []).append(figure)
        self.figures_by_number_card.setdefault(figure.number_card, []).append(figure)

    def match_figure(self, cards: List[Tuple[str, str]]) -> Optional[Figure]:
        """Match a set of cards to a figure."""
        card_set = set(cards)
        return next((figure for figure in self.figures if set(figure.cards) == card_set), None)
