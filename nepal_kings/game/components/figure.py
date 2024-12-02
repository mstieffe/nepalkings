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

import pygame
from typing import List, Dict, Optional, Tuple
from config import settings


class FigureManager:
    def __init__(self):
        self.families: Dict[str, FigureFamily] = {}
        self.figures: List[Figure] = []
        self.figures_by_field: Dict[str, List[Figure]] = {"all": [], "village1": [], "village2": [], "military1": [], "military2": [], "castle": []}
        self.figures_by_suit: Dict[str, List[Figure]] = {suit: [] for suit in settings.SUITS}
        self.figures_by_name: Dict[str, List[Figure]] = {}
        self.figures_by_number_card: Dict[Optional[Tuple[str, str]], List[Figure]] = {}
        self.families_by_field: Dict[str, List[FigureFamily]] = {"all": [], "village1": [], "village2": [], "military1": [], "military2": [], "castle": []}
        self.families_by_color: Dict[str, List[FigureFamily]] = {color: [] for color in settings.COLORS}

        # Initialize families and figures
        self.initialize_figure_families()
        self.categorize_all_figures()

    def load_image(self, path: str) -> pygame.Surface:
        """Helper method to load an image."""
        return pygame.image.load(path)

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
        self.figures_by_number_card.setdefault(figure.number_card, []).append(figure)

    def categorize_all_figures(self):
        """Categorize all figures within their respective families."""
        for family in self.families.values():
            for figure in family.figures:
                self.add_figure(figure)

    def create_figure_family(self, name, color, field, description, icon_img, icon_gray_img, frame_img, frame_closed_img):
        """Helper method to create and add a FigureFamily."""
        family = FigureFamily(
            name=name,
            color=color,
            field=field,
            description=description,
            icon_img=icon_img,
            icon_gray_img=icon_gray_img,
            frame_img=frame_img,
            frame_closed_img=frame_closed_img,
        )
        self.add_figure_family(family)
        return family

    def initialize_figure_families(self):
        """Initialize all figure families."""
        
        family_config = [
            ############# Castle #############
            # Himalaya Castle
            {
                "name": "Himalaya Castle",
                "color": "defensive",
                "field": "castle",
                "description": (
                    "The Himalaya Castle is the residence of your black kings, ruling over your defensive forces. "
                    "Each additional king adds a new black land, i.e., figure slot, to your village and military base."
                ),
                "icon_img": "castle_black.png",
                "icon_gray_img": "castle_black.png",
                "frame_img": "castle.png",
                "frame_closed_img": "castle.png",
                "suits": settings.SUITS_BLACK,
                "figures": lambda family, suit: [
                    CastleFigure(
                        name=f"Himalaya King {suit}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "king")]
                    )
                ]
            },
            # Djungle Castle
            {
                "name": "Djungle Castle",
                "color": "offensive",
                "field": "castle",
                "description": (
                    "The Djungle Castle is the residence of your red kings, ruling over your offensive forces. "
                    "Each additional king adds a new red land, i.e., figure slot, to your village and military base."
                ),
                "icon_img": "castle_red.png",
                "icon_gray_img": "castle_red.png",
                "frame_img": "castle.png",
                "frame_closed_img": "castle.png",
                "suits": settings.SUITS_RED,
                "figures": lambda family, suit: [
                    CastleFigure(
                        name=f"Djungle King {suit}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "king")]
                    )
                ]
            },
            ############# Village #############
            # Stone Mason I
            {
                "name": "Stone Mason I",
                "color": "defensive",
                "field": "village1",
                "description": (
                    "The Stone Mason I is a defensive figure who supplies you with essential stone resources "
                    "required for constructing a fortress. It generates stone equal to its number-card value. "
                    "The stone mason can be upgraded to Stone Mason II."
                ),
                "icon_img": "stone_mason1.png",
                "icon_gray_img": "stone_mason1.png",
                "frame_img": "village.png",
                "frame_closed_img": "village.png",
                "suits": settings.SUITS_BLACK,
                "figures": lambda family, suit: [
                    Village1Figure(
                        name=f"Stone Mason I {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J")],
                        number_card=(suit, number),
                        upgrade_card=(suit, "Q"),
                        upgrade_family_name="Stone Mason II",
                        extension_card=(suit, "2"),
                        extension_family_name="Ore Mine"
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            # Stone Mason II
            {
                "name": "Stone Mason II",
                "color": "defensive",
                "field": "village1",
                "description": (
                    "The Stone Mason II is a defensive figure who supplies you with essential stone resources "
                    "required for constructing a fortress. It generates stone equal to twice its number-card value."
                ),
                "icon_img": "stone_mason2.png",
                "icon_gray_img": "stone_mason2.png",
                "frame_img": "village.png",
                "frame_closed_img": "village.png",
                "suits": settings.SUITS_BLACK,
                "figures": lambda family, suit: [
                    Village1Figure(
                        name=f"Stone Mason II {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J"), (suit, "Q")],
                        number_card=(suit, number),
                        upgrade_card=None,
                        upgrade_family_name=None,
                        extension_card=(suit, "2"),
                        extension_family_name="Ore Mine"
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            # Farm I
            {
                "name": "Farm I",
                "color": "offensive",
                "field": "village1",
                "description": (
                    "The Farm I is an offensive figure who supplies you with essential food resources "
                    "required for constructing an army. It generates food equal to its number-card value. "
                    "The farm can be upgraded to Farm II."
                ),
                "icon_img": "farm1.png",
                "icon_gray_img": "farm1.png",
                "frame_img": "village.png",
                "frame_closed_img": "village.png",
                "suits": settings.SUITS_RED,
                "figures": lambda family, suit: [
                    Village1Figure(
                        name=f"Farm I {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J")],
                        number_card=(suit, number),
                        upgrade_card=(suit, "Q"),
                        upgrade_family_name="Farm II",
                        extension_card=(suit, "2"),
                        extension_family_name="Horse Breeding"
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            # Farm II
            {
                "name": "Farm II",
                "color": "offensive",
                "field": "village1",
                "description": (
                    "The Farm II is an offensive figure who supplies you with essential food resources "
                    "required for constructing an army. It generates food equal to twice its number-card value."
                ),
                "icon_img": "farm2.png",
                "icon_gray_img": "farm2.png",
                "frame_img": "village.png",
                "frame_closed_img": "village.png",
                "suits": settings.SUITS_RED,
                "figures": lambda family, suit: [
                    Village1Figure(
                        name=f"Farm II {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J"), (suit, "Q")],
                        number_card=(suit, number),
                        upgrade_card=None,
                        upgrade_family_name=None,
                        extension_card=(suit, "2"),
                        extension_family_name="Horse Breeding"
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            # Himalaya Temple
            {
                "name": "Himalaya Temple",
                "color": "defensive",
                "field": "village1",
                "description": (
                    "The Himalaya Temple is a spiritual figure who provides you with protection against the bloodline bonus "
                    "of its counterpart, i.e., Spade Temple protecting against Heart and Cross Temple protecting against Diamond."
                ),
                "icon_img": "temple_black.png",
                "icon_gray_img": "temple_black.png",
                "frame_img": "village.png",
                "frame_closed_img": "village.png",
                "suits": settings.SUITS_BLACK,
                "figures": lambda family, suit: [
                    Village1Figure(
                        name=f"Himalaya Temple {suit}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "Q"), (suit, "Q")],
                        number_card=None,
                        upgrade_card=None,
                        extension_card=(suit, "2"),
                        extension_family_name="Himalaya Shrine"
                    )
                ]
            },
            # Djungle Temple
            {
                "name": "Djungle Temple",
                "color": "offensive",
                "field": "village1",
                "description": (
                    "The Djungle Temple is a spiritual figure who provides you with protection against the bloodline bonus "
                    "of its counterpart, i.e., Heart Temple protecting against Cross and Diamond Temple protecting against Spade."
                ),
                "icon_img": "temple_red.png",
                "icon_gray_img": "temple_red.png",
                "frame_img": "village.png",
                "frame_closed_img": "village.png",
                "suits": settings.SUITS_RED,
                "figures": lambda family, suit: [
                    Village1Figure(
                        name=f"Djungle Temple {suit}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "Q"), (suit, "Q")],
                        number_card=None,
                        upgrade_card=None,
                        extension_card=(suit, "2"),
                        extension_family_name="Djungle Shrine"
                    )
                ]
            },
                # Manufactory Shields
            {
                "name": "Manufactory Shields",
                "color": "defensive",
                "field": "village1",
                "description": (
                    "The Manufactory Shields is a defensive figure who provides you with essential shield resources "
                    "required for constructing a fortress II. It generates shields equal to its number-card value."
                ),
                "icon_img": "manufactory_black.png",
                "icon_gray_img": "manufactory_black.png",
                "frame_img": "village.png",
                "frame_closed_img": "village.png",
                "suits": settings.SUITS_BLACK,
                "figures": lambda family, suit: [
                    Village1Figure(
                        name=f"Manufactory Shields {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J")],
                        number_card=(suit, number)
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            # Manufactory Swords
            {
                "name": "Manufactory Swords",
                "color": "offensive",
                "field": "village1",
                "description": (
                    "The Manufactory Swords is an offensive figure who provides you with essential sword resources "
                    "required for constructing an army II. It generates swords equal to its number-card value."
                ),
                "icon_img": "manufactory_red.png",
                "icon_gray_img": "manufactory_red.png",
                "frame_img": "village.png",
                "frame_closed_img": "village.png",
                "suits": settings.SUITS_RED,
                "figures": lambda family, suit: [
                    Village1Figure(
                        name=f"Manufactory Swords {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J")],
                        number_card=(suit, number)
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            ############# Military #############
            # Fortress I
            {
                "name": "Fortress I",
                "color": "defensive",
                "field": "military1",
                "description": (
                    "The Fortress I is a defensive military figure. When under attack, the fortress fights the enemy figure "
                    "without advancing. The fortress I requires as many stones as its number-card value to be operational. "
                    "The fortress can be upgraded to Fortress II."
                ),
                "icon_img": "fortress1.png",
                "icon_gray_img": "fortress1.png",
                "frame_img": "military.png",
                "frame_closed_img": "military.png",
                "suits": settings.SUITS_BLACK,
                "figures": lambda family, suit: [
                    Military1Figure(
                        name=f"Fortress I {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J")],
                        number_card=(suit, number),
                        upgrade_card=(suit, "Q"),
                        upgrade_family_name="Fortress II"
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            # Fortress II
            {
                "name": "Fortress II",
                "color": "defensive",
                "field": "military1",
                "description": (
                    "The Fortress II is a defensive military figure. When under attack, the fortress fights the enemy figure "
                    "without advancing. The fortress II requires as many stones as its number-card value and an additional 7 shields to be operational."
                ),
                "icon_img": "fortress2.png",
                "icon_gray_img": "fortress2.png",
                "frame_img": "military.png",
                "frame_closed_img": "military.png",
                "suits": settings.SUITS_BLACK,
                "figures": lambda family, suit: [
                    Military1Figure(
                        name=f"Fortress II {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J"), (suit, "Q")],
                        number_card=(suit, number)
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            # Army I
            {
                "name": "Army I",
                "color": "offensive",
                "field": "military1",
                "description": (
                    "The Army I is an offensive military figure. The army I requires as many food as its number-card value to "
                    "be operational. The army can be upgraded to Army II."
                ),
                "icon_img": "army1.png",
                "icon_gray_img": "army1.png",
                "frame_img": "military.png",
                "frame_closed_img": "military.png",
                "suits": settings.SUITS_RED,
                "figures": lambda family, suit: [
                    Military1Figure(
                        name=f"Army I {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J")],
                        number_card=(suit, number),
                        upgrade_card=(suit, "Q"),
                        upgrade_family_name="Army II"
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            # Army II
            {
                "name": "Army II",
                "color": "offensive",
                "field": "military1",
                "description": (
                    "The Army II is an offensive military figure. The army II requires as many food as its number-card value "
                    "and an additional 7 swords to be operational."
                ),
                "icon_img": "army2.png",
                "icon_gray_img": "army2.png",
                "frame_img": "military.png",
                "frame_closed_img": "military.png",
                "suits": settings.SUITS_RED,
                "figures": lambda family, suit: [
                    Military1Figure(
                        name=f"Army II {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J"), (suit, "Q")],
                        number_card=(suit, number)
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            # Wall
            {
                "name": "Wall",
                "color": "defensive",
                "field": "military2",
                "description": (
                    "The Wall is a defensive military figure that cannot attack. It offers protection for village figures "
                    "under attack by adding 5 to their power."
                ),
                "icon_img": "wall.png",
                "icon_gray_img": "wall.png",
                "frame_img": "military.png",
                "frame_closed_img": "military.png",
                "suits": settings.SUITS_BLACK,
                "figures": lambda family, suit: [
                    Military2Figure(
                        name=f"Wall {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J")],
                        number_card=(suit, number)
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            # Cavalry
            {
                "name": "Cavalry",
                "color": "offensive",
                "field": "military2",
                "description": (
                    "The Cavalry is an offensive figure that cannot be blocked by advancing. It gains its bloodline bonus "
                    "from the enemy figures."
                ),
                "icon_img": "cavalry.png",
                "icon_gray_img": "cavalry.png",
                "frame_img": "military.png",
                "frame_closed_img": "military.png",
                "suits": settings.SUITS_RED,
                "figures": lambda family, suit: [
                    Military2Figure(
                        name=f"Cavalry {suit} {number}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J")],
                        number_card=(suit, number)
                    )
                    for number in settings.NUMBER_CARDS
                ]
            },
            ############# Extensions #############
            # Ore Mine
            {
                "name": "Ore Mine",
                "color": "defensive",
                "field": "village2",
                "description": (
                    "The Ore Mine is a defensive extension for the Stone Mason I or II producing ore required for a wall. "
                    "It generates ore equal (Stone Mason I) or twice (Stone Mason II) to the number-card of the Stone Mason "
                    "it is attached to."
                ),
                "icon_img": "ore_mine.png",
                "icon_gray_img": "ore_mine.png",
                "frame_img": "village2.png",
                "frame_closed_img": "village2.png",
                "suits": settings.SUITS_BLACK,
                "figures": lambda family, suit: [
                    ExtensionFigure(
                        name=f"Ore Mine {suit}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J")]
                    )
                ]
            },
            # Horse Breeding
            {
                "name": "Horse Breeding",
                "color": "offensive",
                "field": "village2",
                "description": (
                    "The Horse Breeding is an offensive extension for the Farm I or II producing horses required for a Cavalry. "
                    "It generates horses equal (Farm I) or twice (Farm II) to the number-card of the Farm it is attached to."
                ),
                "icon_img": "horse_breeding.png",
                "icon_gray_img": "horse_breeding.png",
                "frame_img": "village2.png",
                "frame_closed_img": "village2.png",
                "suits": settings.SUITS_RED,
                "figures": lambda family, suit: [
                    ExtensionFigure(
                        name=f"Horse Breeding {suit}",
                        suit=suit,
                        family=family,
                        key_cards=[(suit, "J")]
                    )
                ]
            }
            # Additional extensions and figures...
        ]


        for config in family_config:
            family = self.create_figure_family(
                name=config["name"],
                color=config["color"],
                field=config["field"],
                description=config["description"],
                icon_img=self.load_image(settings.FIGURE_ICON_IMG_DIR + config["icon_img"]),
                icon_gray_img=self.load_image(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + config["icon_gray_img"]),
                frame_img=self.load_image(settings.FIGURE_FRAME_IMG_DIR + config["frame_img"]),
                frame_closed_img=self.load_image(settings.FIGURE_FRAME_CLOSED_IMG_DIR + config["frame_closed_img"]),
            )
            for suit in config["suits"]:
                for figure in config["figures"](family, suit):
                    self.add_figure(figure)

    def match_figure(self, cards: List[Tuple[str, str]]) -> Optional[Figure]:
        """Match a set of cards to a figure."""
        card_set = set(cards)
        return next((figure for figure in self.figures if set(figure.cards) == card_set), None)

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

    def get_figure_from_number_card(self, number_card: Tuple[str, str]) -> List[Figure]:
        """Retrieve figures based on their number card."""
        return self.figures_by_number_card.get(number_card, [])


class FigureManagerOld:
    def __init__(self):
        self.figures: List[Figure] = []
        self.figures_by_field: Dict[str, List[Figure]] = {"all": [], "village": [], "military": [], "castle": []}
        self.figures_by_suit: Dict[str, List[Figure]] = {suit: [] for suit in settings.SUITS}
        self.figures_by_name: Dict[str, List[Figure]] = {}
        self.figures_by_number_card: Dict[Optional[Tuple[str, str]], List[Figure]] = {}

        self.initialize_figure_families()
        # Initialize figures
        self.initialize_figures()

    def load_image(path):
        return pygame.image.load(path)



    def initialize_figure_families(self):
        """Initialize all figure families."""
        self.families = {}
        self.families_by_field = {"all": [], "village1": [], "village2": [], "military1": [], "military2": [], "castle": []}
        self.families_by_color = {color: [] for color in settings.COLORS}

        # Castle
        self.add_figure_family(
            FigureFamily(
                name="Himalaya Castle",
                color="defensive",
                icon_img=self.load_image(settings.FIGURE_ICON_IMG_DIR + "castle_black.png"),
                icon_gray_img=self.load_image(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "castle_black.png"),
                frame_img=self.load_image(settings.FIGURE_FRAME_IMG_DIR + "castle.png"),
                frame_closed_img=self.load_image(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "castle.png"),
                description="The himalya castle is the residence of your black kings, ruling over your defensive forces. Each additional king adds a new black land, i.e. figure slot, to your village and military base.",
                field="castle",
            )
        )
        for suit in settings.SUITS_BLACK:
            self.add_figure(
                Figure(
                    name=f"Himalaya King {suit}",
                    suit=suit,
                    family=self.families["Himalaya Castle"],
                    key_cards=[(suit, "king")]
                )
            )

        self.add_figure_family(
            FigureFamily(
                name="Djungle Castle",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "castle_red.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "castle_red.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "castle.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "castle.png"),
                description="The djungle castle is the residence of your red kings, ruling over your offensive forces. Each additional king adds a new red land, i.e. figure slot, to your village and military base.",
                field="castle",
            )
        )
        for suit in settings.SUITS_RED:
            self.add_figure(
                Figure(
                    name=f"Djungle King {suit}",
                    suit=suit,
                    family=self.families["Djungle Castle"],
                    key_cards=[(suit, "king")]
                )
            )

        # Village

        # Stone Mason I
        self.add_figure_family(
            FigureFamily(
                name="Stone Mason I",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "stone_mason1.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "stone_mason1.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village.png"),
                description="The Stone Mason I is a defensive figure who supplies you with essential stone resources required for constructing a fortress. It generates stone equal to its number-card value. The stone mason can be upgraded to a stone mason II.",
                field="village1",
            )
        )

        for suit in settings.SUITS_BLACK:
            for number in settings.NUMBER_CARDS:
                self.add_figure(
                    Figure(
                        name=f"Stone Mason {suit} {number}",
                        suit=suit,
                        family=self.families["Stone Mason I"],
                        key_cards=[(suit, "J")],
                        number_card=[(suit, number)]
                    )
            )

        # Stone Mason II
        self.add_figure_family(
            FigureFamily(
                name="Stone Mason II",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "stone_mason2.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "stone_mason2.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village.png"),
                description="The Stone Mason II is a defensive figure who supplies you with essential stone resources required for constructing a fortress. It generates stone equal to twice its number-card value.",
                field="village1",
            )
        )
        
        for suit in settings.SUITS_BLACK:
            for number in settings.NUMBER_CARDS:
                self.add_figure(
                    Figure(
                        name=f"Stone Mason {suit} {number}",
                        suit=suit,
                        family=self.families["Stone Mason II"],
                        key_cards=[(suit, "J"), (suit, "Q")],
                        number_card=[(suit, number)]                    )
            )


        # Farm I
        self.add_figure_family(
            FigureFamily(
                name="Farm I",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "farm1.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "farm1.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village.png"),
                description="The Farm I is an offensive figure who supplies you with essential food resources required for constructing an army. It generates food equal to its number-card value. The farm can be upgraded to a farm II.",
                field="village1",
            )
        )
        for suit in settings.SUITS_RED:
            for number in settings.NUMBER_CARDS:
                self.add_figure(
                    Figure(
                        name=f"Farm {suit} {number}",
                        suit=suit,
                        family=self.families["Farm I"],
                        key_cards=[(suit, "J")],
                        number_card=[(suit, number)]
                    )
            )

        # Farm II
        self.add_figure_family(
            FigureFamily(
                name="Farm II",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "farm2.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "farm2.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village.png"),
                description="The Farm II is an offensive figure who supplies you with essential food resources required for constructing an army. It generates food equal to twice its number-card value.",
                field="village1",
            )
        )
        for suit in settings.SUITS_RED:
            for number in settings.NUMBER_CARDS:
                self.add_figure(
                    Figure(
                        name=f"Farm {suit} {number}",
                        suit=suit,
                        family=self.families["Farm II"],
                        key_cards=[(suit, "J"), (suit, "Q")],
                        number_card=[(suit, number)]
                    )
            )


        # Himalya Temple
        self.add_figure_family(
            FigureFamily(
                name="Himalaya Temple",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "temple_black.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "temple_black.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village.png"),
                description="The Himalaya Temple is a spiritual figure who provides you with protection against the bloodline bonus of its counterpart, i.e. spade temple protecting against heart and cross temple protecting against diamond.",
                field="village1",
            )
        )
        # Djungle Temple
        self.add_figure_family(
            FigureFamily(
                name="Djungle Temple",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "temple_red.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "temple_red.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village.png"),
                description="The Djungle Temple is a spiritual figure who provides you with protection against the bloodline bonus of its counterpart, i.e. heart temple protecting against cross and diamond temple protecting against spade.",
                field="village1",
            )
        )


        # Manufactory Shields
        self.add_figure_family(
            FigureFamily(
                name="Manufactory Shields",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "manufactory_black.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "manufactory_black.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village.png"),
                description="The Manufactory Shields is a defensive figure who provides you with essential shield resources required for constructing a fortress II. It generates shields equal to its number-card value.",
                field="village1",
            )
        )

        # Manufactory Swords
        self.add_figure_family(
            FigureFamily(
                name="Manufactory Swords",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "manufactory_red.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "manufactory_red.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village.png"),
                description="The Manufactory Swords is an offensive figure who provides you with essential sword resources required for constructing an army II. It generates swords equal to its number-card value.",
                field="village1",
            )
        )

        # Military

        # Fortress I
        self.add_figure_family(
            FigureFamily(
                name="Fortress I",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "fortress1.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "fortress1.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "military.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "military.png"),
                description="The Fortress I is a defensive military figure. When under attack, the fortress the fight the enemy figure without advancing. The fortress I requires as many stones as its number-card value to be operational. The fortress can be upgraded to a fortress II.",
                field="military1",
            )
        )
        # Fortress II
        self.add_figure_family(
            FigureFamily(
                name="Fortress II",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "fortress2.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "fortress2.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "military.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "military.png"),
                description="The Fortress II is a defensive military figure. When under attack, the fortress the fight the enemy figure without advancing. The fortress II requires as many stones as its number-card value and additional 7 shields to be operational.",
                field="military1",
            )
        )

        # Army I
        self.add_figure_family(
            FigureFamily(
                name="Army I",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "army1.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "army1.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "military.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "military.png"),
                description="The Army I is an offensive military figure. The army I requires as many food as its number-card value to be operational. The army can be upgraded to an army II.",
                field="military1",
            )
        )

        # Army II
        self.add_figure_family(
            FigureFamily(
                name="Army II",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "army2.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "army2.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "military.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "military.png"),
                description="The Army II is an offensive military figure. The army II requires as many food as its number-card value and additional 7 swords to be operational.",
                field="military1",
            )
        )

        # HImalya Archers
        self.add_figure_family(
            FigureFamily(
                name="Himalaya Archers",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "archers_black.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "archers_black.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "military.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "military.png"),
                description="The Himalaya Archers are defensive military figures. They attack without being called explicitly every time an enemy figure with the opposed symbol is used in battle and thereby reducing the power of the enemy figure by 3.",
                field="military1",
            )
        )

        # Djungle Archers
        self.add_figure_family(
            FigureFamily(
                name="Djungle Archers",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "archers_red.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "archers_red.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "military.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "military.png"),
                description="The Djungle Archers are offensive military figures. They attack without being called explicitly every time an enemy figure with the opposed symbol is used in battle and thereby reducing the power of the enemy figure by 3.",
                field="military1",
            )
        )

        # Wall
        self.add_figure_family(
            FigureFamily(
                name="Wall",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "wall.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "wall.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "military.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "military.png"),
                description="The Wall is a defensive military figure that cannot attack. It offers protection for village figures under attack by adding 5 to their power.",
                field="military2",
            )
        )

        # Cavalry
        self.add_figure_family(
            FigureFamily(
                name="Cavalry",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "cavalry.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "cavalry.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "military.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "military.png"),
                description="The Cavalry is an offensive figure that cannot be blocked by advancing. It gains its bloodline bonus from the enemy figures.",
                field="military2",
            )
        )

        # Ore Mine
        self.add_figure_family(
            FigureFamily(
                name="Ore Mine",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "ore_mine.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "ore_mine.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "military.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "military.png"),
                description="The Ore Mine is a defensive figure for the stone mason I or II producing ore required for a wall. It generates ore equal (Stone Mason I) or twice (Stone Mason II) to the number-card of the stone mason it is attached to.",
                field="village2",
            )
        )

        # Horse breeding
        self.add_figure_family(
            FigureFamily(
                name="Horse breeding",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "horse_breeding.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "horse_breeding.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village2.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village2.png"),
                description="The Horse breeding is an extension for the farm I or II producing horses required for a cavalry. It generates horses equal (Farm I) or twice (Farm II) to the number-card of the farm it is attached to.",
                field="village2",
            )
        )

        # Himalya Carpenter
        self.add_figure_family(
            FigureFamily(
                name="Himalaya Carpenter",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "carpenter_black.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "carpenter_black.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village2.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village2.png"),
                description="The Himalaya Carpenter is an extension for the shield manufactory producing black arrows required for the himalyan archers. It generates arrows equal to the number-card of the shield manufactory it is attached to.",
                field="village2",
            )
        )

        # Djungle Carpenter
        self.add_figure_family(
            FigureFamily(
                name="Djungle Carpenter",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "carpenter_red.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "carpenter_red.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village2.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village2.png"),
                description="The Djungle Carpenter is an extension for the sword manufactory producing red arrows required for the djungle archers. It generates arrows equal to the number-card of the sword manufactory it is attached to.",
                field="village2",
            )
        )

        # Himalya Shrine
        self.add_figure_family(
            FigureFamily(
                name="Himalaya Shrine",
                color="defensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "shrine_black.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "shrine_black.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village2.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village2.png"),
                description="The Himalaya Shrine is an extension for the temple enhancing its blocking capatibilities. A himalyan temple with shrine blocks all djungle bloodline bonuses.",
                field="village2",
            )
        )

        # Djungle Shrine
        self.add_figure_family(
            FigureFamily(
                name="Djungle Shrine",
                color="offensive",
                icon_img=pygame.image.load(settings.FIGURE_ICON_IMG_DIR + "shrine_red.png"),
                icon_gray_img=pygame.image.load(settings.FIGURE_ICON_GREYSCALE_IMG_DIR + "shrine_red.png"),
                frame_img=pygame.image.load(settings.FIGURE_FRAME_IMG_DIR + "village2.png"),
                frame_closed_img=pygame.image.load(settings.FIGURE_FRAME_CLOSED_IMG_DIR + "village2.png"),
                description="The Djungle Shrine is an extension for the temple enhancing its blocking capatibilities. A djungle temple with shrine blocks all himalyan bloodline bonuses.",
                field="village2",
            )
        )

    def add_figure_family(self, family: FigureFamily) -> None:
        """Add a figure family to the manager and categorize it."""
        self.families[family.name] = family
        self.families_by_field[family.field].append(family)
        self.families_by_color[family.color].append(family)


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
