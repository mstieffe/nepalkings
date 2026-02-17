from config.settings import SUITS_BLACK, SUITS_RED, NUMBER_CARDS, SCREEN_WIDTH, SCREEN_HEIGHT
from game.components.figures.figure import Military1Figure
from game.components.cards.card import Card

############# Military #############
military1_dict_list = [
    # Fortress I
    {
        "name": "Fortress I",
        "color": "defensive",
        "field": "military1",
        "description": (
            "The Fortress I is a defensive military figure. When under attack, the fortress fights the enemy figure "
            "without advancing. The Fortress I requires as many stones as its number-card value to be operational. "
            "The fortress can be upgraded to Fortress II."
        ),
        "icon_img": "fortress1.png",
        "icon_gray_img": "fortress1.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "glow_img": "blue.png",
        "suits": SUITS_BLACK,
        "build_position": (0.8 * SCREEN_WIDTH, 0.255 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Military1Figure(
                name=f"Fortress I {suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1)],
                number_card=Card(str(number), suit, number),
                upgrade_card=Card("7", suit, 7),
                upgrade_family_name="Fortress II"
            )
            for number in NUMBER_CARDS
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
        "glow_img": "blue.png",
        "suits": SUITS_BLACK,
        "build_position": (0.8 * SCREEN_WIDTH, 0.395 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Military1Figure(
                name=f"Fortress II {suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1), Card("Q", suit, 2), Card("7", suit, 7)],
                number_card=Card(str(number), suit, number)
            )
            for number in NUMBER_CARDS
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
        "glow_img": "green.png",
        "suits": SUITS_RED,
        "build_position": (0.8 * SCREEN_WIDTH, 0.255 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Military1Figure(
                name=f"Army I {suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1)],
                number_card=Card(str(number), suit, number),
                upgrade_card=Card("7", suit, 7),
                upgrade_family_name="Army II"
            )
            for number in NUMBER_CARDS
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
        "glow_img": "green.png",
        "suits": SUITS_RED,
        "build_position": (0.8 * SCREEN_WIDTH, 0.395 * SCREEN_HEIGHT),
        "figures": lambda family, suit: [
            Military1Figure(
                name=f"Army II {suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1), Card("Q", suit, 2), Card("7", suit, 7)],
                number_card=Card(str(number), suit, number)
            )
            for number in NUMBER_CARDS
        ]
    }
]
