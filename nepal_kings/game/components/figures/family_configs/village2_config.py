from config.settings import SUITS_BLACK, SUITS_RED, SCREEN_WIDTH, SCREEN_HEIGHT
from game.components.figures.figure import Village2Figure
from game.components.cards.card import Card

############# Extensions #############

village2_dict_list= [
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
        "suits": SUITS_BLACK,
        "build_position": (0.6 * SCREEN_WIDTH, 0.19 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village2Figure(
                name=f"Ore Mine {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("2", suit, 2)],
                attachment_family_name=attachment_family
            )
            for attachment_family in ["Stone Mason I", "Stone Mason II"]
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
        "suits": SUITS_RED,
        "build_position": (0.6 * SCREEN_WIDTH, 0.19 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village2Figure(
                name=f"Horse Breeding {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("2", suit, 2)],
                attachment_family_name=attachment_family
            )
            for attachment_family in ["Farm I", "Farm II"]
        ]
    },
    # Himalaya Shrine
    {
        "name": "Himalaya Shrine",
        "color": "defensive",
        "field": "village2",
        "description": (
            "The Himalaya Shrine is a defensive extension for the Farm I or II producing horses required for a Cavalry. "
            "It generates horses equal (Farm I) or twice (Farm II) to the number-card of the Farm it is attached to."
        ),
        "icon_img": "shrine_black.png",
        "icon_gray_img": "shrine_black.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "suits": SUITS_BLACK,
        "build_position": (0.6 * SCREEN_WIDTH, 0.61 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village2Figure(
                name=f"Himalaya Shrine {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("2", suit, 2)],
                attachment_family_name="Himalaya Temple"
            )
        ]
    },
    # Djungle Shrine
    {
        "name": "Djungle Shrine",
        "color": "offensive",
        "field": "village2",
        "description": (
            "The Djungle Shrine is an offensive extension for the Farm I or II producing horses required for a Cavalry. "
            "It generates horses equal (Farm I) or twice (Farm II) to the number-card of the Farm it is attached to."
        ),
        "icon_img": "shrine_red.png",
        "icon_gray_img": "shrine_red.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "suits": SUITS_RED,
        "build_position": (0.6 * SCREEN_WIDTH, 0.61 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village2Figure(
                name=f"Djungle Shrine {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("2", suit, 2)],
                attachment_family_name="Djungle Temple"
            )
        ]
    },
    # Himalaya Carpenter
    {
        "name": "Himalaya Carpenter",
        "color": "defensive",
        "field": "village2",
        "description": (
            "The Himalaya Carpenter is a defensive extension for the Stone Mason I or II producing ore required for a wall. "
            "It generates ore equal (Stone Mason I) or twice (Stone Mason II) to the number-card of the Stone Mason "
            "it is attached to."
        ),
        "icon_img": "carpenter_black.png",
        "icon_gray_img": "carpenter_black.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "suits": SUITS_BLACK,
        "build_position": (0.6 * SCREEN_WIDTH, 0.47 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village2Figure(
                name=f"Himalaya Carpenter {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("2", suit, 2)],
                attachment_family_name="Himalaya Manufactory"
            )
        ]
    },
    # Djungle Carpenter
    {
        "name": "Djungle Carpenter",
        "color": "offensive",
        "field": "village2",
        "description": (
            "The Djungle Carpenter is an offensive extension for the Stone Mason I or II producing ore required for a wall. "
            "It generates ore equal (Stone Mason I) or twice (Stone Mason II) to the number-card of the Stone Mason "
            "it is attached to."
        ),
        "icon_img": "carpenter_red.png",
        "icon_gray_img": "carpenter_red.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "suits": SUITS_RED,
        "build_position": (0.6 * SCREEN_WIDTH, 0.47 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village2Figure(
                name=f"Djungle Carpenter {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("2", suit, 2)],
                attachment_family_name="Djungle Manufactory"
            )
        ]
    }
]
