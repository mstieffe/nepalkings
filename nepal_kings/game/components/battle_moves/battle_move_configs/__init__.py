"""Battle move configuration definitions.

Each config dict defines a battle move family with its icon/frame assets,
required card rank, and description.
"""

CALL_VILLAGER_CONFIG = {
    "name": "Call Villager",
    "description": "Send a villager into the fray. A humble but brave choice.",
    "required_rank": "J",  # Jack = value 1
    "icon_img": "village.png",
    "icon_gray_img": "village.png",
    "frame_img": "village.png",
    "frame_gray_img": "village.png",
    "glow_green_img": "green.png",
    "glow_blue_img": "blue.png",
}

CALL_MILITARY_CONFIG = {
    "name": "Call Military",
    "description": "Deploy a trained soldier to the battlefield. A strong offensive move.",
    "required_rank": "A",  # Ace = value 3
    "icon_img": "military.png",
    "icon_gray_img": "military.png",
    "frame_img": "military.png",
    "frame_gray_img": "military.png",
    "glow_green_img": "green.png",
    "glow_blue_img": "blue.png",
}

CALL_KING_CONFIG = {
    "name": "Call King",
    "description": "The king himself rides into battle. The most powerful call.",
    "required_rank": "K",  # King = value 4
    "icon_img": "castle.png",
    "icon_gray_img": "castle.png",
    "frame_img": "castle.png",
    "frame_gray_img": "castle.png",
    "glow_green_img": "green.png",
    "glow_blue_img": "blue.png",
}

BLOCK_CONFIG = {
    "name": "Block",
    "description": "Raise a shield to deflect an enemy attack. A defensive maneuver.",
    "required_rank": "Q",  # Queen = value 2
    "icon_img": "block.png",
    "icon_gray_img": "block.png",
    "frame_img": "block.png",
    "frame_gray_img": "block.png",
    "glow_green_img": "green.png",
    "glow_blue_img": "blue.png",
}

DAGGER_CONFIG = {
    "name": "Dagger",
    "description": "Strike with a dagger for direct damage. Uses the full value of a number card.",
    "required_rank": "number",  # Number card 7-10
    "icon_img": "dagger.png",
    "icon_gray_img": "dagger.png",
    "frame_img": "dagger.png",
    "frame_gray_img": "dagger.png",
    "glow_green_img": "green.png",
    "glow_blue_img": "blue.png",
}

DOUBLE_DAGGER_CONFIG = {
    "name": "Double Dagger",
    "description": "Two daggers of the same colour combined for a devastating strike.",
    "required_rank": "none",  # Cannot be bought directly — only via combine
    "icon_img": "double_dagger.png",
    "icon_gray_img": "double_dagger.png",
    "frame_img": "dagger.png",        # reuse dagger frame
    "frame_gray_img": "dagger.png",
    "glow_green_img": "green.png",
    "glow_blue_img": "blue.png",
}

ALL_BATTLE_MOVE_CONFIGS = [
    CALL_VILLAGER_CONFIG,
    CALL_MILITARY_CONFIG,
    CALL_KING_CONFIG,
    BLOCK_CONFIG,
    DAGGER_CONFIG,
    DOUBLE_DAGGER_CONFIG,
]
