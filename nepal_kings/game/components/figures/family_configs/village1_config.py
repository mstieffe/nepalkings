from config.settings import SUITS_BLACK, SUITS_RED, SCREEN_WIDTH, SCREEN_HEIGHT, NUMBER_CARDS
from game.components.figures.figure import Village1Figure
from game.components.card import Card

############# Village #############

village_dict_list= [
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
        "frame_img": "village1.png",
        "frame_closed_img": "village1.png",
        "suits": SUITS_BLACK,
        "build_position": (0.5 * SCREEN_WIDTH, 0.19 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village1Figure(
                name=f"Stone Mason I {suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1)],
                number_card=Card(str(number), suit, number),
                upgrade_card=Card("Q", suit, 2),
                upgrade_family_name="Stone Mason II",
                extension_card=Card("2", suit, 2),
                extension_family_name="Ore Mine"
            )
            for number in NUMBER_CARDS
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
        "frame_img": "village1.png",
        "frame_closed_img": "village1.png",
        "suits": SUITS_BLACK,
        "build_position": (0.5 * SCREEN_WIDTH, 0.33 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village1Figure(
                name=f"Stone Mason II {suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1), Card("Q", suit, 2)],
                number_card=Card(str(number), suit, number),
                upgrade_card=None,
                upgrade_family_name=None,
                extension_card=Card("2", suit, 2),
                extension_family_name="Ore Mine"
            )
            for number in NUMBER_CARDS
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
        "frame_img": "village1.png",
        "frame_closed_img": "village1.png",
        "suits": SUITS_RED,
        "build_position": (0.5 * SCREEN_WIDTH, 0.19 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village1Figure(
                name=f"Farm I {suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1)],
                number_card=Card(str(number), suit, number),
                upgrade_card=Card("Q", suit, 2),
                upgrade_family_name="Farm II",
                extension_card=Card("2", suit, 2),
                extension_family_name="Horse Breeding"
            )
            for number in NUMBER_CARDS
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
        "frame_img": "village1.png",
        "frame_closed_img": "village1.png",
        "suits": SUITS_RED,
        "build_position": (0.5 * SCREEN_WIDTH, 0.33 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village1Figure(
                name=f"Farm II {suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1), Card("Q", suit, 2)],
                number_card=Card(str(number), suit, number),
                upgrade_card=None,
                upgrade_family_name=None,
                extension_card=Card("2", suit, 2),
                extension_family_name="Horse Breeding"
            )
            for number in NUMBER_CARDS
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
        "frame_img": "village1.png",
        "frame_closed_img": "village1.png",
        "suits": SUITS_BLACK,
        "build_position": (0.5 * SCREEN_WIDTH, 0.61 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village1Figure(
                name=f"Himalaya Temple {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("Q", suit, 2), Card("Q", suit, 2)],
                number_card=None,
                upgrade_card=None,
                extension_card=Card("2", suit, 2),
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
        "frame_img": "village1.png",
        "frame_closed_img": "village1.png",
        "suits": SUITS_RED,
        "build_position": (0.5 * SCREEN_WIDTH, 0.61 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village1Figure(
                name=f"Djungle Temple {suit}",
                suit=suit,
                family=family,
                key_cards=[Card("Q", suit, 2), Card("Q", suit, 2)],
                number_card=None,
                upgrade_card=None,
                extension_card=Card("2", suit, 2),
                extension_family_name="Djungle Shrine"
            )
        ]
    },
    # Manufactory Shields
    {
        "name": "Himalaya Manufactory",
        "color": "defensive",
        "field": "village1",
        "description": (
            "The Manufactory Shields is a defensive figure who provides you with essential shield resources "
            "required for constructing a fortress II. It generates shields equal to its number-card value."
        ),
        "icon_img": "manufactory_black.png",
        "icon_gray_img": "manufactory_black.png",
        "frame_img": "village1.png",
        "frame_closed_img": "village1.png",
        "suits": SUITS_BLACK,
        "build_position": (0.5 * SCREEN_WIDTH, 0.47 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village1Figure(
                name=f"Himalaya Manufactory {suit} {7}",
                suit=suit,
                family=family,
                key_cards=[Card("Q", suit, 2), Card("Q", suit, 2)],
                number_card=Card(str(7), suit, 7)
            )
        ]
    },
    # Manufactory Swords
    {
        "name": "Djungle Manufactory",
        "color": "offensive",
        "field": "village1",
        "description": (
            "The Manufactory Swords is an offensive figure who provides you with essential sword resources "
            "required for constructing an army II. It generates swords equal to its number-card value."
        ),
        "icon_img": "manufactory_red.png",
        "icon_gray_img": "manufactory_red.png",
        "frame_img": "village1.png",
        "frame_closed_img": "village1.png",
        "suits": SUITS_RED,
        "build_position": (0.5 * SCREEN_WIDTH, 0.47 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Village1Figure(
                name=f"Djungle Manufactory {suit} {7}",
                suit=suit,
                family=family,
                key_cards=[Card("Q", suit, 2), Card("Q", suit, 2)],
                number_card=Card(str(7), suit, 7)
            )
        ]
    }
]
