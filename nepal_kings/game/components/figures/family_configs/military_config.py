from config.settings import SUITS_BLACK, SUITS_RED, NUMBER_CARDS, SCREEN_WIDTH, SCREEN_HEIGHT
from game.components.figures.figure import MilitaryFigure
from game.components.cards.card import Card

MILITARY_START_POS_X = 0.48 * SCREEN_WIDTH
MILITARY_START_POS_Y = 0.56 * SCREEN_HEIGHT
MILITARY_DELTA_X = 0.09 * SCREEN_WIDTH

MILITARY_POSITIONS = {
    0: (MILITARY_START_POS_X + 0.5 * MILITARY_DELTA_X, MILITARY_START_POS_Y),
    1: (MILITARY_START_POS_X + 1.5 * MILITARY_DELTA_X, MILITARY_START_POS_Y),
    2: (MILITARY_START_POS_X + 2.5 * MILITARY_DELTA_X, MILITARY_START_POS_Y),
    3: (MILITARY_START_POS_X + 3.5 * MILITARY_DELTA_X, MILITARY_START_POS_Y)
}

############# Military #############
############# Military #############
military_dict_list = [
    # Fortress I
    {
        "name": "Wooden Fortress",
        "color": "defensive",
        "field": "military",
        "description": (
            "The Wooden Fortress is a defensive military figure. When under attack, the fortress fights the enemy figure "
            "without advancing. The Wooden Fortress requires as many stones as its number-card value to be operational. "
            "The fortress can be upgraded to Stone Fortress."
        ),
        "icon_img": "fortress1.png",
        "icon_gray_img": "fortress1.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "glow_img": "blue.png",
        "suits": SUITS_BLACK,
        "build_position": MILITARY_POSITIONS[1],
        "figures": lambda family, suit: [
            MilitaryFigure(
                name="Wooden Fortress",
                sub_name=f"{suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("A", suit, 3)],
                number_card=Card(str(number), suit, number),
                upgrade_card=Card("7", suit, 7),
                upgrade_family_name="Stone Fortress",
                requires={'warrior_black': 1, 'food_black': int(number)},
                cannot_attack=True,  # Fortresses are defensive and cannot attack
                must_be_attacked=True  # Fortresses must be attacked before other figures
            )
            for number in NUMBER_CARDS
        ]
    },
    # Fortress II
    {
        "name": "Stone Fortress",
        "color": "defensive",
        "field": "military",
        "description": (
            "The Stone Fortress is a defensive military figure. When under attack, the fortress fights the enemy figure "
            "without advancing. The Stone Fortress requires as many stones as its number-card value and an additional 7 shields to be operational."
        ),
        "icon_img": "fortress2.png",
        "icon_gray_img": "fortress2.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "glow_img": "blue.png",
        "suits": SUITS_BLACK,
        "build_position": MILITARY_POSITIONS[0],
        "figures": lambda family, suit: [
            MilitaryFigure(
                name="Stone Fortress",
                sub_name=f"{suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("A", suit, 3), Card("7", suit, 7)],
                number_card=Card(str(number), suit, number),
                requires={'warrior_black': 1, 'food_black': int(number), 'armor_black': 7},
                cannot_attack=True,  # Fortresses are defensive and cannot attack
                must_be_attacked=True  # Fortresses must be attacked before other figures
            )
            for number in NUMBER_CARDS
        ]
    },
    # Army I
    {
        "name": "Gorkha Warriors",
        "color": "offensive",
        "field": "military",
        "description": (
            "The Gorkha Warriors is an offensive military figure. Gorkha Warriors require as many food as its number-card value to "
            "be operational. The figure can be upgraded to Elite Gorkha Warriors."
        ),
        "icon_img": "army1.png",
        "icon_gray_img": "army1.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "glow_img": "green.png",
        "suits": SUITS_RED,
        "build_position": MILITARY_POSITIONS[1],
        "figures": lambda family, suit: [
            MilitaryFigure(
                name="Gorkha Warriors",
                sub_name=f"{suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("A", suit, 3)],
                number_card=Card(str(number), suit, number),
                upgrade_card=Card("7", suit, 7),
                upgrade_family_name="Elite Gorkha Warriors",
                requires={'warrior_red': 1, 'food_red': int(number)},
                instant_charge=True  # Warriors charge instantly into battle
            )
            for number in NUMBER_CARDS
        ]
    },
    # Army II
    {
        "name": "Elite Gorkha Warriors",
        "color": "offensive",
        "field": "military",
        "description": (
            "The Elite Gorkha Warriors is an offensive military figure. Elite Gorkha Warriors require as many food as its number-card value "
            "and an additional 7 swords to be operational."
        ),
        "icon_img": "army2.png",
        "icon_gray_img": "army2.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "glow_img": "green.png",
        "suits": SUITS_RED,
        "build_position": MILITARY_POSITIONS[0],
        "figures": lambda family, suit: [
            MilitaryFigure(
                name="Elite Gorkha Warriors",
                sub_name=f"{suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("A", suit, 3), Card("7", suit, 7)],
                number_card=Card(str(number), suit, number),
                requires={'warrior_red': 1, 'food_red': int(number), 'armor_red': 7},
                instant_charge=True  # Elite Warriors charge instantly into battle
            )
            for number in NUMBER_CARDS
        ]
    },
    # Wall
    {
        "name": "Wall",
        "color": "defensive",
        "field": "military",
        "description": (
            "The Wall is a defensive military figure that cannot attack. It offers protection for village figures "
            "under attack by adding 5 to their power."
        ),
        "icon_img": "wall.png",
        "icon_gray_img": "wall.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "glow_img": "blue.png",
        "suits": SUITS_BLACK,
        "build_position": MILITARY_POSITIONS[2],
        "figures": lambda family, suit: [
            MilitaryFigure(
                name="Wall",
                sub_name=f"{suit}",
                suit=suit,
                family=family,
                key_cards=[Card("4", suit, 4), Card("5", suit, 5)],
                number_card=Card("6", suit, 6),
                requires={'warrior_black': 1, 'material_black': 6},
                cannot_attack=True,  # Walls are defensive and cannot attack
                cannot_defend=True,  # Walls cannot defend other figures
                buffs_allies=True  # Walls provide buffs to allied figures under attack
            )
        ]
    },
    # Cavalry
    {
        "name": "Cavalry",
        "color": "offensive",
        "field": "military",
        "description": (
            "The Cavalry is an offensive figure that cannot be blocked by advancing. It gains its bloodline bonus "
            "from the enemy figures."
        ),
        "icon_img": "cavalry.png",
        "icon_gray_img": "cavalry.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "glow_img": "green.png",
        "suits": SUITS_RED,
        "build_position": MILITARY_POSITIONS[2],
        "figures": lambda family, suit: [
            MilitaryFigure(
                name="Cavalry",
                sub_name=f"{suit}",
                suit=suit,
                family=family,
                key_cards=[Card("4", suit, 4), Card("5", suit, 5)],
                number_card=Card("6", suit, 6),
                requires={'warrior_red': 1, 'material_red': 6},
                rest_after_attack=True,  # Cavalry needs rest after attacking
                cannot_defend=True,  # Cavalry cannot defend other figures
                instant_charge=True,  # Cavalry charges instantly into battle
                cannot_be_blocked=True  # Cavalry cannot be blocked when advancing
            )
        ]
    },
    # Himalya Archer
    {
        "name": "Himalya Archer",
        "color": "defensive",
        "field": "military",
        "description": (
            "The Himalya Archer is a defensive figure that can attack enemy figures in the village. It gains its bloodline bonus "
            "from the enemy figures."
        ),
        "icon_img": "archers_black.png",
        "icon_gray_img": "archers_black.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "glow_img": "blue.png",
        "suits": SUITS_BLACK,
        "build_position": MILITARY_POSITIONS[3],
        "figures": lambda family, suit: [
            MilitaryFigure(
                name="Himalya Archer",
                sub_name=f"{suit}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1)],
                number_card=Card("3", suit, 3),
                requires={'warrior_black': 1, 'material_black': 3},
                distance_attack=True  # Archers can attack from distance
            )
        ]
    },
    # Djungle Archer
    {
        "name": "Djungle Archer",
        "color": "offensive",
        "field": "military",
        "description": (
            "The Djungle Archer is an offensive figure that can attack enemy figures in the village. It gains its bloodline bonus "
            "from the enemy figures."
        ),
        "icon_img": "archers_red.png",
        "icon_gray_img": "archers_red.png",
        "frame_img": "military.png",
        "frame_closed_img": "military.png",
        "glow_img": "green.png",
        "suits": SUITS_RED,
        "build_position": MILITARY_POSITIONS[3],
        "figures": lambda family, suit: [
            MilitaryFigure(
                name="Djungle Archer",
                sub_name=f"{suit}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1)],
                number_card=Card("3", suit, 3),
                requires={'warrior_red': 1, 'material_red': 3},
                distance_attack=True  # Archers can attack from distance
            )
        ]
    }
]
