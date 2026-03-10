from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT

# ── Background & button images ──────────────────────────────────────
GAME_MENU_BG_IMG_PATH   = 'img/background/menu_background.png'
GAME_MENU_BTN_IMG_PATH  = 'img/menu_button/menu_button3.png'

# ── Login screen ────────────────────────────────────────────────────
LOGIN_BG_IMG_PATH       = 'img/background/menu_background_greyscale.png'
LOGIN_BTN_IMG_PATH      = 'img/menu_button/menu_button2.png'

# ── Menu-button layout ──────────────────────────────────────────────
GAME_MENU_BTN_W         = int(0.22 * SCREEN_WIDTH)
GAME_MENU_BTN_H         = int(0.07 * SCREEN_HEIGHT)
GAME_MENU_BTN_GAP       = int(0.025 * SCREEN_HEIGHT)

# ── Dark box around buttons ─────────────────────────────────────────
GAME_MENU_BOX_PAD_X     = int(0.04 * SCREEN_WIDTH)
GAME_MENU_BOX_PAD_TOP   = int(0.04 * SCREEN_HEIGHT)
GAME_MENU_BOX_PAD_BOTTOM = int(0.04 * SCREEN_HEIGHT)
GAME_MENU_BOX_BORDER_CLR = (180, 160, 130)
GAME_MENU_BOX_BG_CLR    = (30, 30, 30, 160)
GAME_MENU_BOX_BORDER_W  = 2

# ── Title ────────────────────────────────────────────────────────────
GAME_MENU_TITLE_FONT_SIZE   = int(0.04 * SCREEN_HEIGHT)
GAME_MENU_TITLE_CLR         = (250, 221, 0)
GAME_MENU_TITLE_PAD_BOTTOM  = int(0.03 * SCREEN_HEIGHT)

# ── Menu-button glow (rendered BEHIND the button) ───────────────────
GAME_MENU_GLOW_W_FACTOR = 1.2      # glow width  = button width  × factor
GAME_MENU_GLOW_H_FACTOR = 2.0      # glow height = button height × factor
GAME_MENU_GLOW_DIR      = 'img/menu_button/glow/'

# ── Gold display (upper-left) ───────────────────────────────────────
GAME_MENU_GOLD_ICON_PATH     = 'img/dialogue_box/icons/gold.png'
GAME_MENU_GOLD_ICON_SZ       = int(0.045 * SCREEN_HEIGHT)
GAME_MENU_GOLD_FONT_SIZE     = int(0.036 * SCREEN_HEIGHT)
GAME_MENU_GOLD_TEXT_CLR      = (250, 221, 0)
GAME_MENU_GOLD_MARGIN_X      = int(0.02 * SCREEN_WIDTH)
GAME_MENU_GOLD_MARGIN_Y      = int(0.025 * SCREEN_HEIGHT)
GAME_MENU_GOLD_ICON_TEXT_GAP = int(0.008 * SCREEN_WIDTH)
GAME_MENU_GOLD_BOX_PAD_X     = int(0.012 * SCREEN_WIDTH)
GAME_MENU_GOLD_BOX_PAD_Y     = int(0.008 * SCREEN_HEIGHT)
GAME_MENU_GOLD_BOX_BG_CLR    = (20, 20, 20, 140)
GAME_MENU_GOLD_BOX_BORDER_CLR = (180, 160, 130)
GAME_MENU_GOLD_BOX_BORDER_W  = 1

# ── Icon buttons (home / logout, top-right) ─────────────────────────
GAME_MENU_ICON_SYMBOL_PATH   = 'img/game_button/symbol/'
GAME_MENU_ICON_STONE_PATH    = 'img/game_button/stone/plain.png'
GAME_MENU_ICON_GLOW_PATH     = 'img/game_button/glow/'
GAME_MENU_ICON_STONE_SZ      = int(0.065 * SCREEN_WIDTH)
GAME_MENU_ICON_SYMBOL_SZ     = int(0.045 * SCREEN_WIDTH)
GAME_MENU_ICON_SYMBOL_BIG_SZ = int(0.050 * SCREEN_WIDTH)
GAME_MENU_ICON_GLOW_SZ       = int(0.055 * SCREEN_WIDTH)
GAME_MENU_ICON_GLOW_BIG_SZ   = int(0.065 * SCREEN_WIDTH)
GAME_MENU_ICON_GAP           = int(0.001 * SCREEN_WIDTH)
GAME_MENU_ICON_TOP_Y         = int(0.008 * SCREEN_HEIGHT)
GAME_MENU_ICON_RIGHT_MARGIN  = int(0.008 * SCREEN_WIDTH)

# ── ListButton defaults (programmatic list-item buttons) ────────────
LIST_BTN_W              = int(0.30 * SCREEN_WIDTH)
LIST_BTN_H              = int(0.050 * SCREEN_HEIGHT)
LIST_BTN_FONT_SIZE      = int(0.022 * SCREEN_HEIGHT)
LIST_BTN_CORNER_RADIUS  = int(0.006 * SCREEN_HEIGHT)
LIST_BTN_BORDER_W       = 1
LIST_BTN_BG_CLR         = (35, 35, 40, 180)
LIST_BTN_BG_HOVER_CLR   = (55, 55, 65, 200)
LIST_BTN_BG_CLICK_CLR   = (70, 70, 80, 220)
LIST_BTN_BORDER_CLR     = (100, 95, 85)
LIST_BTN_BORDER_HOVER_CLR = (220, 200, 140)
LIST_BTN_TEXT_CLR        = (190, 185, 175)
LIST_BTN_TEXT_HOVER_CLR  = (255, 245, 220)

# ── Sub-screen layout (load_game, new_game shared) ──────────────────
SUB_SCREEN_TITLE_FONT_SIZE   = int(0.035 * SCREEN_HEIGHT)
SUB_SCREEN_TITLE_CLR         = (250, 221, 0)
SUB_SCREEN_HEADER_FONT_SIZE  = int(0.026 * SCREEN_HEIGHT)
SUB_SCREEN_HEADER_CLR        = (220, 200, 140)
SUB_SCREEN_PANEL_BG_CLR      = (25, 25, 30, 170)
SUB_SCREEN_PANEL_BORDER_CLR  = (120, 110, 95)
SUB_SCREEN_PANEL_BORDER_W    = 1
SUB_SCREEN_PANEL_CORNER_R    = int(0.008 * SCREEN_HEIGHT)
