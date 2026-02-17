from config.settings import SUITS_BLACK, SUITS_RED, SCREEN_WIDTH, SCREEN_HEIGHT, NUMBER_CARDS
from game.components.figures.figure import VillageFigure
from game.components.cards.card import Card

############# Village #############

VILLAGE_START_POS_X = 0.39 * SCREEN_WIDTH
VILLAGE_START_POS_Y = 0.38 * SCREEN_HEIGHT
VILLAGE_DELTA_X = 0.09 * SCREEN_WIDTH

VILLAGE_POSITIONS = {
    0: (VILLAGE_START_POS_X, VILLAGE_START_POS_Y),
    1: (VILLAGE_START_POS_X + VILLAGE_DELTA_X, VILLAGE_START_POS_Y),
    2: (VILLAGE_START_POS_X + 2 * VILLAGE_DELTA_X, VILLAGE_START_POS_Y),
    3: (VILLAGE_START_POS_X + 3 * VILLAGE_DELTA_X, VILLAGE_START_POS_Y),
    4: (VILLAGE_START_POS_X + 4 * VILLAGE_DELTA_X, VILLAGE_START_POS_Y),
    5: (VILLAGE_START_POS_X + 5 * VILLAGE_DELTA_X, VILLAGE_START_POS_Y),
    6: (VILLAGE_START_POS_X + 6 * VILLAGE_DELTA_X, VILLAGE_START_POS_Y)
}

############# Village #############
village_dict_list = [
    # Small Yack Farm
    {
        "name": "Small Yack Farm",
        "color": "defensive",
        "field": "village",
        "description": (
            "The small yack farm is a defensive figure who supplies you with essential food resources "
            "required for constructing a fortress. It generates food equal to its number-card value. "
            "The small yack farm can be upgraded to a large yack farm."
        ),
        "icon_img": "yack_farm1.png",
        "icon_gray_img": "yack_farm1.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "blue.png",
        "suits": SUITS_BLACK,
        "build_position": VILLAGE_POSITIONS[2],
        "figures": lambda family, suit: [
            VillageFigure(
                name="Small Yack Farm",
                sub_name=f"{suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1)],
                number_card=Card(str(number), suit, number),
                upgrade_card=Card("Q", suit, 2),
                upgrade_family_name="Large Yack Farm",
                produces={'food_black': int(number)} if suit in ['Clubs', 'Spades'] else {'food_red': int(number)},
                requires={'villager_black': 1},
            )
            for number in NUMBER_CARDS
        ]
    },
    # Large Yack Farm
    {
        "name": "Large Yack Farm",
        "color": "defensive",
        "field": "village",
        "description": (
            "The large yack farm is a defensive figure who supplies you with essential food resources "
            "required for constructing a fortress. It generates food equal to twice its number-card value."
        ),
        "icon_img": "yack_farm2.png",
        "icon_gray_img": "yack_farm2.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "blue.png",
        "suits": SUITS_BLACK,
        "build_position": VILLAGE_POSITIONS[3],
        "figures": lambda family, suit: [
            VillageFigure(
                name="Large Yack Farm",
                sub_name=f"{suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1), Card("Q", suit, 2)],
                number_card=Card(str(number), suit, number),
                produces={'food_black': int(number) * 2} if suit in ['Clubs', 'Spades'] else {'food_red': int(number) * 2},
                requires={'villager_black': 1},
            )
            for number in NUMBER_CARDS
        ]
    },
    # Small Rice Farm
    {
        "name": "Small Rice Farm",
        "color": "offensive",
        "field": "village",
        "description": (
            "The small rice farm is an offensive figure who supplies you with essential food resources "
            "required for recruiting Gorkha soldiers. It generates food equal to its number-card value. "
            "The small rice farm can be upgraded to a large rice farm."
        ),
        "icon_img": "rice_farm1.png",
        "icon_gray_img": "rice_farm1.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "green.png",
        "suits": SUITS_RED,
        "build_position": VILLAGE_POSITIONS[2],
        "figures": lambda family, suit: [
            VillageFigure(
                name="Small Rice Farm",
                sub_name=f"{suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1)],
                number_card=Card(str(number), suit, number),
                upgrade_card=Card("Q", suit, 2),
                upgrade_family_name="Large Rice Farm",
                produces={'food_red': int(number)} if suit in ['Hearts', 'Diamonds'] else {'food_black': int(number)},
                requires={'villager_red': 1},
            )
            for number in NUMBER_CARDS
        ]
    },
    # Large Rice Farm
    {
        "name": "Large Rice Farm",
        "color": "offensive",
        "field": "village",
        "description": (
            "The large rice farm is an offensive figure who supplies you with essential food resources "
            "required for recruiting Gorkha warriors. It generates food equal to twice its number-card value."
        ),
        "icon_img": "rice_farm2.png",
        "icon_gray_img": "rice_farm2.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "green.png",
        "suits": SUITS_RED,
        "build_position": VILLAGE_POSITIONS[3],
        "figures": lambda family, suit: [
            VillageFigure(
                name="Large Rice Farm",
                sub_name=f"{suit} {number}",
                suit=suit,
                family=family,
                key_cards=[Card("J", suit, 1), Card("Q", suit, 2)],
                number_card=Card(str(number), suit, number),
                produces={'food_red': int(number) * 2} if suit in ['Hearts', 'Diamonds'] else {'food_black': int(number) * 2},
                requires={'villager_red': 1},
            )
            for number in NUMBER_CARDS
        ]
    },
    # Himalaya Temple
    {
        "name": "Himalaya Temple",
        "color": "defensive",
        "field": "village",
        "description": (
            "The Himalaya Temple is a spiritual figure who provides you with protection against the bloodline bonus "
            "of its counterpart, i.e., Spade Temple protecting against Heart and Cross Temple protecting against Diamond."
        ),
        "icon_img": "shrine_black.png",
        "icon_gray_img": "shrine_black.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "blue.png",
        "suits": SUITS_BLACK,
        "build_position": VILLAGE_POSITIONS[0],
        "figures": lambda family, suit: [
            VillageFigure(
                name="Himalaya Temple",
                sub_name=f"{suit}",
                suit=suit,
                family=family,
                key_cards=[Card("Q", suit, 2), Card("Q", suit, 2)],
                upgrade_card=Card("7", suit, 7),
                upgrade_family_name="Shield Manufactory",
                requires={'villager_black': 1},
                cannot_attack=True,  # Temples cannot attack
                blocks_bonus=True  # Temples block enemy bloodline bonus
            )
        ]
    },
    # Djungle Temple
    {
        "name": "Djungle Temple",
        "color": "offensive",
        "field": "village",
        "description": (
            "The Djungle Temple is a spiritual figure who provides you with protection against the bloodline bonus "
            "of its counterpart, i.e., Heart Temple protecting against Cross and Diamond Temple protecting against Spade."
        ),
        "icon_img": "shrine_red.png",
        "icon_gray_img": "shrine_red.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "green.png",
        "suits": SUITS_RED,
        "build_position": VILLAGE_POSITIONS[0],
        "figures": lambda family, suit: [
            VillageFigure(
                name="Djungle Temple",
                sub_name=f"{suit}",
                suit=suit,
                family=family,
                key_cards=[Card("Q", suit, 2), Card("Q", suit, 2)],
                upgrade_card=Card("7", suit, 7),
                upgrade_family_name="Sword Manufactory",
                requires={'villager_red': 1},
                cannot_attack=True,  # Temples cannot attack
                blocks_bonus=True  # Temples block enemy bloodline bonus
            )
        ]
    },
    # Shield Manufactory
    {
        "name": "Shield Manufactory",
        "color": "defensive",
        "field": "village",
        "description": (
            "The Shield Manufactory is a defensive figure who provides you with essential shield resources "
            "required for constructing a fortress II. It generates shields equal to its number-card value."
        ),
        "icon_img": "manufactory_black.png",
        "icon_gray_img": "manufactory_black.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "yellow.png",
        "suits": SUITS_BLACK,
        "build_position": VILLAGE_POSITIONS[1],
        "figures": lambda family, suit: [
            VillageFigure(
                name="Shield Manufactory",
                sub_name=f"{suit} 7",
                suit=suit,
                family=family,
                key_cards=[Card("Q", suit, 2), Card("Q", suit, 2)],
                number_card=Card("7", suit, 7),
                produces={'armor_black': 7} if suit in ['Clubs', 'Spades'] else {'armor_black': 7},
                requires={'villager_black': 1},
            )
        ]
    },
    # Sword Manufactory
    {
        "name": "Sword Manufactory",
        "color": "offensive",
        "field": "village",
        "description": (
            "The Sword Manufactory is an offensive figure who provides you with essential sword resources "
            "required for constructing an army II. It generates swords equal to its number-card value."
        ),
        "icon_img": "manufactory_red.png",
        "icon_gray_img": "manufactory_red.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "yellow.png",
        "suits": SUITS_RED,
        "build_position": VILLAGE_POSITIONS[1],
        "figures": lambda family, suit: [
            VillageFigure(
                name="Sword Manufactory",
                sub_name=f"{suit} 7",
                suit=suit,
                family=family,
                key_cards=[Card("Q", suit, 2), Card("Q", suit, 2)],
                number_card=Card("7", suit, 7),
                produces={'armor_red': 7} if suit in ['Hearts', 'Diamonds'] else {'armor_black': 7},
                requires={'villager_red': 1},
                )
        ]
    },
    # Carpenter
    {
        "name": "Carpenter",
        "color": "offensive",
        "field": "village",
        "description": (
            "The Carpenter is an offensive figure producing wood required for cavalry or archers. "
            "It generates wood equal to its number-card value."
        ),
        "icon_img": "carpenter.png",
        "icon_gray_img": "carpenter.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "yellow.png",
        "suits": SUITS_RED,
        "build_position": VILLAGE_POSITIONS[4],
        "figures": lambda family, suit: [
            VillageFigure(
                name="Carpenter",
                sub_name=f"{suit} 6",
                suit=suit,
                family=family,
                key_cards=[Card("2", suit, 2), Card("2", suit, 2)],
                number_card=Card("6", suit, 6),
                produces={'material_red': 6} if suit in ['Hearts', 'Diamonds'] else {'material_black': 6},
                requires={'villager_red': 1},
            )
        ]
    },
    # Stone Mason
    {
        "name": "Stone Mason",
        "color": "defensive",
        "field": "village",
        "description": (
            "The Stone Mason is an offensive figure producing stone required for constructing a wall or catapult. "
            "It generates stone equal to its number-card value."
        ),
        "icon_img": "stone_mason.png",
        "icon_gray_img": "stone_mason.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "yellow.png",
        "suits": SUITS_BLACK,
        "build_position": VILLAGE_POSITIONS[4],
        "figures": lambda family, suit: [
            VillageFigure(
                name="Stone Mason",
                sub_name=f"{suit} 6",
                suit=suit,
                family=family,
                key_cards=[Card("2", suit, 2), Card("2", suit, 2)],
                number_card=Card("6", suit, 6),
                produces={'material_black': 6} if suit in ['Clubs', 'Spades'] else {'material_red': 6},
                requires={'villager_black': 1},
            )
        ]
    },
    # Himalaya Healer
    {
        "name": "Himalaya Healer",
        "color": "defensive",
        "field": "village",
        "description": (
            "The Himalaya Healer is a defensive figure supporting other villagers giving them a +4 boost. "
        ),
        "icon_img": "himalaya_healer.png",
        "icon_gray_img": "himalaya_healer.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "yellow.png",
        "suits": SUITS_BLACK,
        "build_position": VILLAGE_POSITIONS[5],
        "figures": lambda family, suit: [
            VillageFigure(
                name=f"Himalaya Healer",
                sub_name=f"{suit}",
                suit=suit,
                family=family,
                key_cards=[Card("2", suit, 2), Card("2", suit, 2)],
                upgrade_card=Card("6", suit, 6),
                upgrade_family_name="Stone Mason",
                requires={'villager_black': 1},
                cannot_attack=True,  # Healers cannot attack
                buffs_allies=True  # Healers buff allied figures
            )
        ]
    },
    # Djungle Healer
    {
        "name": "Djungle Healer",
        "color": "offensive",
        "field": "village",
        "description": (
            "The Djungle Healer is an offensive figure supporting other villagers giving them a +4 boost. "
        ),
        "icon_img": "djungle_healer.png",
        "icon_gray_img": "djungle_healer.png",
        "frame_img": "village2.png",
        "frame_closed_img": "village2.png",
        "glow_img": "yellow.png",
        "suits": SUITS_RED,
        "build_position": VILLAGE_POSITIONS[5],
        "figures": lambda family, suit: [
            VillageFigure(
                name=f"Djungle Healer",
                sub_name=f"{suit}",
                suit=suit,
                family=family,
                key_cards=[Card("2", suit, 2), Card("2", suit, 2)],
                upgrade_card=Card("6", suit, 6),
                upgrade_family_name="Carpenter",
                requires={'villager_red': 1},
                cannot_attack=True,  # Healers cannot attack
                buffs_allies=True  # Healers buff allied figures
            )
        ]
    }
]
