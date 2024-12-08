from config.settings import SUITS_BLACK, SUITS_RED, SCREEN_WIDTH, SCREEN_HEIGHT
from game.components.figures.figure import CastleFigure
from game.components.cards.card import Card

castle_dict_list = [
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
        "suits": SUITS_BLACK,
        "build_position": (0.605 * SCREEN_WIDTH, 0.22 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            CastleFigure(
                name=f"Himalaya King",
                sub_name=f"{suit}",
                suit=suit,
                family=family,
                key_cards=[Card("K", suit, 4)]
            )
        ]
    },
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
        "suits": SUITS_RED,
        "build_position": (0.605 * SCREEN_WIDTH, 0.22 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            CastleFigure(
                name=f"Djungle King",
                sub_name=f"{suit}",
                suit=suit,
                family=family,
                key_cards=[Card("K", suit, 4)]
            )
        ]
    }
]