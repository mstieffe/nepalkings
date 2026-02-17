import pygame
from typing import List, Dict, Optional, Tuple
from config import settings
from game.components.figures.family_configs.family_config_list import FAMILY_CONFIG_LIST
from game.components.figures.figure import Figure, FigureFamily
from game.components.cards.card import Card


class FigureManager:
    def __init__(self):
        self.families: Dict[str, FigureFamily] = {}
        self.figures: List[Figure] = []
        self.figures_by_field: Dict[str, List[Figure]] = {
            "all": [],
            "village": [],
            "military": [],
            "castle": [],
        }
        self.figures_by_suit: Dict[str, List[Figure]] = {suit: [] for suit in settings.SUITS}
        self.figures_by_name: Dict[str, List[Figure]] = {}
        self.figures_by_number_card: Dict[Optional[Tuple[str, str]], List[Figure]] = {}
        self.families_by_field: Dict[str, List[FigureFamily]] = {
            "all": [],
            "village": [],
            "military": [],
            "castle": [],
        }
        self.families_by_color: Dict[str, List[FigureFamily]] = {color: [] for color in settings.COLORS}

        # Initialize families and figures
        self.initialize_figure_families()
        self.link_figures()
        #self.categorize_all_figures()

    def load_image(self, path: str) -> pygame.Surface:
        """Helper method to load an image."""
        return pygame.image.load(path).convert_alpha()

    def add_figure_family(self, family: FigureFamily) -> None:
        """Add a figure family to the manager and categorize it."""
        self.families[family.name] = family
        self.families_by_field[family.field].append(family)
        self.families_by_color[family.color].append(family)

    def add_figure(self, figure: Figure) -> None:
        """Add a figure to the manager and categorize it."""
        self.figures.append(figure)
        self.figures_by_field[figure.family.field].append(figure)
        self.figures_by_suit[figure.suit].append(figure)
        self.figures_by_name.setdefault(figure.name, []).append(figure)
        self.figures_by_number_card.setdefault(figure.number_card.to_tuple() if figure.number_card else None, []).append(figure)

    def categorize_all_figures(self):
        """Categorize all figures within their respective families."""
        for family in self.families.values():
            for figure in family.figures:
                self.add_figure(figure)

    def create_figure_family(self, name, color, suits, figures, field, description, icon_img, icon_gray_img, frame_img, frame_closed_img, frame_hidden_img, glow_img, build_position=None):
        """Helper method to create and add a FigureFamily."""
        family = FigureFamily(
            name=name,
            color=color,
            suits=suits,
            figures=figures,
            field=field,
            description=description,
            icon_img=icon_img,
            icon_gray_img=icon_gray_img,
            frame_img=frame_img,
            frame_closed_img=frame_closed_img,
            frame_hidden_img=frame_hidden_img,
            glow_img=glow_img,
            build_position=build_position,
        )
        self.add_figure_family(family)

        return family
    

    def initialize_figure_families(self):
        """Initialize all figure families."""
        for config in FAMILY_CONFIG_LIST:

            family = self.create_figure_family(
                name=config["name"],
                color=config["color"],
                suits=config["suits"],
                figures=None,
                field=config["field"],
                description=config["description"],
                icon_img=self.load_image(settings.FIGURE_ICON_IMG_DIR + config["icon_img"]),
                icon_gray_img=self.load_image(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + config["icon_gray_img"]),
                frame_img=self.load_image(settings.FIGURE_FRAME_IMG_DIR + config["frame_img"]),
                frame_closed_img=self.load_image(settings.FIGURE_FRAME_GREYSCALE_IMG_DIR + config["frame_closed_img"]),
                frame_hidden_img=self.load_image(settings.FIGURE_FRAME_HIDDEN_IMG_DIR + config["frame_closed_img"]),
                glow_img=self.load_image(settings.FIGURE_GLOW_IMG_DIR + config["glow_img"]),
                build_position=config.get("build_position"),
            )
            family_figures  = []
            for suit in config["suits"]:
                for figure in config["figures"](family, suit):
                    family_figures.append(figure)
                    self.add_figure(figure)
            family.figures = family_figures

    def link_figures(self):
        """Establish relationships like upgrades and extensions between figures."""
        for figure in self.figures:
            if figure.upgrade_family_name:
                upgrade_family = self.families.get(figure.upgrade_family_name)
                if upgrade_family:
                    figure.upgrade_to = [
                        upgrade_figure
                        for upgrade_figure in self.figures
                        if upgrade_figure.family == upgrade_family and upgrade_figure.suit == figure.suit
                    ]

    def match_figure(self, cards: List[Card]) -> Optional[Figure]:
        """Match a set of cards to a figure."""
        card_set = {card.to_tuple() for card in cards}
        return next((figure for figure in self.figures if {card.to_tuple() for card in figure.cards} == card_set), None)

    def get_figures_by_field(self, field: str) -> List[Figure]:
        """Retrieve all figures belonging to a specific field."""
        return self.figures_by_field.get(field, [])

    def get_figures_by_suit(self, suit: str) -> List[Figure]:
        """Retrieve all figures belonging to a specific suit."""
        return self.figures_by_suit.get(suit, [])

    def get_family_by_name(self, name: str) -> Optional[FigureFamily]:
        """Retrieve a family by its name."""
        return self.families.get(name)

    def get_figures_by_name(self, name: str) -> List[Figure]:
        """Retrieve all figures with a specific name."""
        return self.figures_by_name.get(name, [])

    def get_figure_from_number_card(self, number_card: Card) -> List[Figure]:
        """Retrieve figures based on their number card."""
        return self.figures_by_number_card.get(number_card.to_tuple(), [])
