from config.settings import SUITS_BLACK, SUITS_RED, NUMBER_CARDS, SCREEN_WIDTH, SCREEN_HEIGHT
from game.components.figures.figure import Military2Figure
from game.components.card import Card

############# Military II #############

military2_dict_list = [
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
        "suits": SUITS_BLACK,
        "build_position": (0.7 * SCREEN_WIDTH, 0.19 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Military2Figure(
                name=f"Wall {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("4", suit, 4), Card("5", suit, 5), Card("6", suit, 6)],
            )
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
        "suits": SUITS_RED,
        "build_position": (0.7 * SCREEN_WIDTH, 0.19 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Military2Figure(
                name=f"Cavalry {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("4", suit, 4), Card("5", suit, 5), Card("6", suit, 6)],
            )
        ]
    },
    # Himalya Archer
    {
        "name": "Himalya Archer",
        "color": "defensive",
        "field": "military2",
        "description": (
            "The Himalya Archer is a defensive figure that can attack enemy figures in the village. It gains its bloodline bonus "
            "from the enemy figures."
        ),
        "icon_img": "archers_black.png",
        "icon_gray_img": "archers_black.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "suits": SUITS_RED,
        "build_position": (0.7 * SCREEN_WIDTH, 0.47 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Military2Figure(
                name=f"Himalya Archer {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1), Card("3", suit, 3)],
            )
        ]
    },
    # Djungle Archer
    {
        "name": "Djungle Archer",
        "color": "offensive",
        "field": "military2",
        "description": (
            "The Djungle Archer is an offensive figure that can attack enemy figures in the village. It gains its bloodline bonus "
            "from the enemy figures."
        ),
        "icon_img": "archers_red.png",
        "icon_gray_img": "archers_red.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "suits": SUITS_RED,
        "build_position": (0.7 * SCREEN_WIDTH, 0.47 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Military2Figure(
                name=f"Djungle Archer {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1), Card("3", suit, 3)],
            )
        ]
    }
]
