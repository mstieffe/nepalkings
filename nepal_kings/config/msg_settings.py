from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT

INPUTFIELD_BORDER_COLOR_ACTIVE = (250, 170, 0)
INPUTFIELD_BORDER_COLOR_PASSIVE = (60, 60, 60)
INPUTFIELD_TEXT_COLOR_HEADER= (220, 220, 220)
INPUTFIELD_FONT_SIZE = int(0.04 * SCREEN_HEIGHT)
INPUTFIELD_FONT_SIZE_TITLE = int(0.03 * SCREEN_HEIGHT)
INPUTFIELD_COLOR_PASSIVE = (100, 100, 100)
INPUTFIELD_COLOR_ACTIVE = (120, 120, 120) #(250, 170, 0)

INPUTFIELD_WIDTH = int(0.55 * SCREEN_WIDTH)
INPUTFIELD_WIDTH_SMALL = int(0.3 * SCREEN_WIDTH)
INPUTFIELD_HEIGHT = int(0.04 * SCREEN_HEIGHT)

MSG_BACKGROUND_COLOR = (0, 0, 0)

MSG_FONT_SIZE = int(0.022 * SCREEN_HEIGHT)

MSG_MAX_WIDTH = int(0.8 * SCREEN_WIDTH)
MSG_MAX_HEIGHT = int(0.45 * SCREEN_HEIGHT)

MSG_TEXT_BOX_X = int(0.24 * SCREEN_WIDTH)
MSG_TEXT_BOX_Y = int(0.07 * SCREEN_HEIGHT)
MSG_TEXT_BOX_WIDTH = int(0.64 * SCREEN_WIDTH)
MSG_TEXT_BOX_HEIGHT = int(0.52 * SCREEN_HEIGHT)

MSG_LOG_BUTTON_X = int(0.15 * SCREEN_WIDTH)
MSG_LOG_BUTTON_Y = int(0.07 * SCREEN_HEIGHT)
MSG_CHAT_BUTTON_X = int(0.15 * SCREEN_WIDTH)
MSG_CHAT_BUTTON_Y = int(0.12 * SCREEN_HEIGHT)
MSG_SEND_BUTTON_X = int(0.8 * SCREEN_WIDTH)
MSG_SEND_BUTTON_Y = int(0.635 * SCREEN_HEIGHT)

MSG_INPUT_X = int(0.24 * SCREEN_WIDTH)
MSG_INPUT_Y = int(0.64 * SCREEN_HEIGHT)

MSG_TEXT_X = int(0.27 * SCREEN_WIDTH)
MSG_TEXT_Y = int(0.10 * SCREEN_HEIGHT)

MSG_BACKGROUND_COLOR = (30, 30, 30)  # General background color
MSG_TEXT_COLOR = (220, 215, 200)  # Warm off-white text
MSG_TIMESTAMP_COLOR = (160, 150, 130)  # Muted gold for timestamps
MSG_SENDER_COLOR = (200, 180, 120)  # Warm gold for sender names

# Message bubble styling
MSG_BUBBLE_CORNER_R = int(0.006 * SCREEN_HEIGHT)
MSG_BUBBLE_PAD_X = int(0.008 * SCREEN_WIDTH)
MSG_BUBBLE_PAD_Y = int(0.003 * SCREEN_HEIGHT)
MSG_BUBBLE_SPACING = int(0.004 * SCREEN_HEIGHT)

# Build-up phase log colors
LOG_MSG_BG_COLOR = (50, 50, 150)  # Legacy
LOG_MSG_SELF_BG_COLOR = (30, 55, 45)  # Muted dark green
LOG_MSG_OPP_BG_COLOR = (35, 40, 60)  # Muted dark blue
CHAT_MSG_BG_COLOR = (50, 150, 50)  # Legacy
CHAT_MSG_SELF_BG_COLOR = (55, 40, 25)  # Warm dark brown
CHAT_MSG_OPP_BG_COLOR = (45, 25, 30)  # Dark wine

# Battle-phase log entry colors (distinct from build-up)
BATTLE_LOG_SELF_BG_COLOR = (50, 30, 50)  # Dark purple
BATTLE_LOG_OPP_BG_COLOR = (40, 25, 45)  # Darker purple

MSG_BG_TRANSPARENCY = 180

# Scrollbar styling
SCROLLBAR_COLOR = (50, 45, 40)  # Dark track
SCROLLBAR_HANDLE_COLOR_ACTIVE = (180, 150, 80)  # Warm gold when dragging
SCROLLBAR_HANDLE_COLOR_PASSIVE = (90, 80, 60)  # Muted warm handle
SCROLLBAR_CORNER_R = int(0.003 * SCREEN_WIDTH)
SCROLLBAR_HEIGHT = int(0.484 * SCREEN_HEIGHT)
SCROLLBAR_WIDTH = int(0.006 * SCREEN_WIDTH)
SCROLLBAR_X = int(0.858 * SCREEN_WIDTH)
SCROLLBAR_Y = int(0.08795 * SCREEN_HEIGHT)

# Battle-related log types (used to pick battle colors)
BATTLE_LOG_TYPES = {
    'battle_move', 'battle_skip', 'battle_start', 'battle_decision',
    'battle_win', 'battle_draw', 'auto_loss', 'deficit_loss', 'fold_win',
    'advance', 'counter_advance', 'civil_war_skip',
}

# Chat/Log button images (same style as build figure color buttons)
MSG_BUTTON_ACTIVE_IMG = 'img/button/confirm/turkis.png'
MSG_BUTTON_INACTIVE_IMG = 'img/button/confirm/turkis_dark.png'
MSG_SEND_BUTTON_ACTIVE_IMG = 'img/button/confirm/green.png'
MSG_SEND_BUTTON_INACTIVE_IMG = 'img/button/confirm/grey.png'

# Log screen toggle/send button styling (programmatic, dark-themed)
LOG_BTN_W = int(0.07 * SCREEN_WIDTH)
LOG_BTN_H = int(0.035 * SCREEN_HEIGHT)
LOG_BTN_FONT_SIZE = int(0.022 * SCREEN_HEIGHT)
LOG_BTN_CORNER_R = int(0.005 * SCREEN_HEIGHT)
LOG_BTN_BG_CLR = (40, 38, 35, 160)
LOG_BTN_BG_ACTIVE_CLR = (55, 50, 40, 200)
LOG_BTN_BG_HOVER_CLR = (65, 58, 48, 200)
LOG_BTN_BORDER_CLR = (90, 80, 60)
LOG_BTN_BORDER_ACTIVE_CLR = (180, 160, 80)
LOG_BTN_TEXT_CLR = (180, 175, 160)
LOG_BTN_TEXT_ACTIVE_CLR = (250, 221, 0)
LOG_BTN_BORDER_W = 1

# Log entry icon settings
LOG_ICON_SIZE = int(0.019 * SCREEN_HEIGHT)
LOG_ICON_PAD = int(0.005 * SCREEN_WIDTH)

# Map log entry type → icon image path
LOG_ICON_TYPE_MAP = {
    # Build phase
    'card_changed': 'img/game_button/symbol/round_arrow_active.png',
    'card_discard': 'img/game_button/symbol/round_arrow_active.png',
    'figure_built': 'img/game_button/symbol/hammer_active.png',
    'figure_pickup': 'img/game_button/symbol/hammer_active.png',
    'figure_upgraded': 'img/game_button/symbol/hammer_active.png',
    'figure_destroyed': 'img/game_button/symbol/hammer_active.png',
    # Spells
    'spell_cast': 'img/dialogue_box/icons/magic.png',
    'spell_cast_pending': 'img/dialogue_box/icons/magic.png',
    'spell_countered': 'img/dialogue_box/icons/magic.png',
    'spell_allowed': 'img/dialogue_box/icons/magic.png',
    'spell_end': 'img/dialogue_box/icons/magic.png',
    # Battle
    'battle_move': 'img/game_button/symbol/battle_active.png',
    'battle_start': 'img/game_button/symbol/battle_active.png',
    'battle_decision': 'img/game_button/symbol/battle_active.png',
    'battle_skip': 'img/game_button/symbol/battle_active.png',
    'battle_win': 'img/dialogue_box/icons/victory_small.png',
    'battle_draw': 'img/dialogue_box/icons/draw.png',
    'fold_win': 'img/dialogue_box/icons/victory_small.png',
    'auto_loss': 'img/dialogue_box/icons/defeat_small.png',
    'deficit_loss': 'img/dialogue_box/icons/defeat_small.png',
    'advance': 'img/game_button/symbol/battle_active.png',
    'counter_advance': 'img/game_button/symbol/battle_active.png',
    'civil_war_skip': 'img/dialogue_box/icons/magic.png',
    'game_over': 'img/dialogue_box/icons/gold.png',
}

# Battle move family name → specific icon (resolved for type='battle_move')
LOG_BATTLE_MOVE_ICON_MAP = {
    'Call Villager': 'img/battle/icons/village.png',
    'Call Military': 'img/battle/icons/military.png',
    'Call King': 'img/battle/icons/castle.png',
    'Block': 'img/battle/icons/block.png',
    'Dagger': 'img/battle/icons/dagger.png',
    'Double Dagger': 'img/battle/icons/double_dagger.png',
}

# Chat input field styling (dark-themed)
LOG_INPUT_BG_CLR = (35, 33, 30, 200)
LOG_INPUT_BG_ACTIVE_CLR = (45, 42, 38, 220)
LOG_INPUT_BORDER_CLR = (80, 75, 60)
LOG_INPUT_BORDER_ACTIVE_CLR = (180, 160, 80)
LOG_INPUT_TEXT_CLR = (220, 215, 200)
LOG_INPUT_PLACEHOLDER_CLR = (120, 115, 100)
LOG_INPUT_CORNER_R = int(0.005 * SCREEN_HEIGHT)
LOG_INPUT_FONT_SIZE = int(0.024 * SCREEN_HEIGHT)
LOG_INPUT_H = int(0.038 * SCREEN_HEIGHT)


