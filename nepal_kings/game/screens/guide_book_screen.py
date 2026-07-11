# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from pygame.locals import *
from config import settings
from game.screens.sub_screen import SubScreen


class GuideBookScreen(SubScreen):
    """Screen for displaying the game guide with a sidebar menu and scrollable content."""

    def __init__(self, window, state, x: int = 0, y: int = 0, title=None,
                 initial_section=None):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        # ── sections ────────────────────────────────────────────────────
        self.sections = self._build_sections()
        self.current_section = 0
        if initial_section:
            for i, section in enumerate(self.sections):
                if section['title'] == initial_section:
                    self.current_section = i
                    break
        self.scroll_offset = 0          # pixel offset (not line index)

        # ── fonts ───────────────────────────────────────────────────────
        self.section_title_font = settings.get_font(settings.GUIDE_SECTION_TITLE_FONT_SIZE, bold=True)

        self.heading_font = settings.get_font(settings.GUIDE_HEADING_FONT_SIZE, bold=True)

        self.body_font = settings.get_font(settings.GUIDE_BODY_FONT_SIZE)

        self.menu_font = settings.get_font(settings.GUIDE_MENU_FONT_SIZE)

        self.menu_font_active = settings.get_font(settings.GUIDE_MENU_FONT_ACTIVE_SIZE, bold=True)

        self.table_font = settings.get_font(settings.GUIDE_TABLE_FONT_SIZE)

        self.small_body_font = settings.get_font(settings.GUIDE_TABLE_FONT_SIZE)

        # ── image cache ─────────────────────────────────────────────────
        self._image_cache = {}

        # ── layout geometry (from config) ───────────────────────────────
        self.sidebar_x = settings.GUIDE_SIDEBAR_X
        self.sidebar_y = settings.GUIDE_SIDEBAR_Y
        self.sidebar_w = settings.GUIDE_SIDEBAR_W
        self.sidebar_h = settings.GUIDE_SIDEBAR_H
        self.menu_item_h = settings.GUIDE_MENU_ITEM_H
        self.menu_item_pad = settings.GUIDE_MENU_ITEM_PAD

        self.content_x = settings.GUIDE_CONTENT_X
        self.content_y = settings.GUIDE_CONTENT_Y
        self.content_w = settings.GUIDE_CONTENT_W
        self.content_h = settings.GUIDE_CONTENT_H

        self.scrollbar_w = settings.GUIDE_SCROLLBAR_W
        self.scrollbar_x = settings.GUIDE_SCROLLBAR_X
        self.scrollbar_y = settings.GUIDE_SCROLLBAR_Y
        self.scrollbar_h = settings.GUIDE_SCROLLBAR_H

        self.scrollbar_rect = pygame.Rect(
            self.scrollbar_x, self.scrollbar_y, self.scrollbar_w, self.scrollbar_h)
        self.handle_rect = pygame.Rect(
            self.scrollbar_x, self.scrollbar_y, self.scrollbar_w, 40)

        self.dragging = False
        self._touch_scrolling = False
        self._touch_last_y = 0
        self.scrollbar_handle_color = settings.GUIDE_SCROLLBAR_HANDLE_P

        # Pre-render content surfaces for the initially selected section
        self._rendered_content = None   # pygame.Surface or None
        self._rendered_height = 0       # total pixel height of rendered content
        self._render_section()

        # Pre-build sidebar item rects for hit testing
        self.menu_rects = []
        self._build_menu_rects()

    # ════════════════════════════════════════════════════════════════════
    #  Image helpers
    # ════════════════════════════════════════════════════════════════════

    def _load_icon(self, path, size=None):
        """Load and cache a square icon, scaled to *size* px."""
        if size is None:
            size = settings.GUIDE_ICON_SIZE
        key = (path, size, size)
        if key not in self._image_cache:
            try:
                img = pygame.image.load(path).convert_alpha()
                img = pygame.transform.smoothscale(img, (size, size))
                self._image_cache[key] = img
            except Exception:
                # Fallback: visible red-bordered placeholder
                surf = pygame.Surface((size, size), pygame.SRCALPHA)
                pygame.draw.rect(surf, (200, 60, 60, 180), surf.get_rect(), 2)
                self._image_cache[key] = surf
        return self._image_cache[key]

    def _load_image(self, path, max_width=None, max_height=None):
        """Load and cache an image, constraining to max dimensions."""
        if max_width is None:
            max_width = settings.GUIDE_IMAGE_MAX_W
        key = (path, max_width, max_height)
        if key not in self._image_cache:
            try:
                img = pygame.image.load(path).convert_alpha()
                w, h = img.get_size()
                if max_width and w > max_width:
                    scale = max_width / w
                    w, h = int(w * scale), int(h * scale)
                if max_height and h > max_height:
                    scale = max_height / h
                    w, h = int(w * scale), int(h * scale)
                img = pygame.transform.smoothscale(img, (w, h))
                self._image_cache[key] = img
            except Exception:
                surf = pygame.Surface((32, 32), pygame.SRCALPHA)
                pygame.draw.rect(surf, (200, 60, 60, 180), surf.get_rect(), 2)
                self._image_cache[key] = surf
        return self._image_cache[key]

    # Icon-path prefixes that should always use the SMALL size
    _SMALL_ICON_PREFIXES = (
        'img/figures/state_icons/',
        'img/suits/',
        'img/resource_icons/',
    )

    def _icon_size_for_path(self, path):
        """Return inline icon size: small for skills/suits/resources, large otherwise."""
        if any(path.startswith(p) for p in self._SMALL_ICON_PREFIXES):
            return settings.GUIDE_ICON_SIZE
        return settings.GUIDE_ICON_SIZE_LARGE

    # ════════════════════════════════════════════════════════════════════
    #  Content sections
    # ════════════════════════════════════════════════════════════════════

    def _build_sections(self):
        """Build the guide-book content sections.

        Supported block formats inside ``content``:
          - ``str``                              → body paragraph (word-wrapped)
          - ``""``                               → blank spacing line
          - ``{'heading': '...'}``               → amber sub-heading
          - ``{'bullet': '...'}``                → bulleted paragraph
          - ``{'separator': True}``              → horizontal rule
          - ``{'icon_text': path, 'text': '...'}`` → icon + paragraph
          - ``{'icon_bullet': path, 'text': '...'}`` → icon + bulleted text
          - ``{'image': path, ...}``             → centred image
          - ``{'table': {'headers': [...], 'rows': [[...]], 'col_widths': [...]}}``
        """

        # ── shorthand icon paths ────────────────────────────────────
        _s = 'img/suits/'
        _r = 'img/resource_icons/'
        _sl = 'img/slot_icons/'
        _fi = 'img/figures/icons_small/'
        _sk = 'img/figures/state_icons/'
        _sp = 'img/spells/icons/'
        _bm = 'img/battle/icons/'
        _st = 'img/status_icons/'
        _gb = 'img/game_button/symbol/'
        _kg = 'img/kingdom/skill_icons/'
        _dlg = 'img/dialogue_box/icons/'

        sections = [

            # ── 0  Overview ─────────────────────────────────────────
            {
                'title': 'Overview',
                'group': 'Basics',
                'mode': 'both',
                'content': [
                    'Welcome to Nepal Kings - a strategy card game set in '
                    'the kingdoms of the Himalayas.',
                    '',
                    {'heading': 'Two Ways to Play'},
                    'There are two ways to play. They share cards, figures, '
                    'suit rules, and battle math, but they answer different '
                    'questions:',
                    '',
                    {'table': {
                        'headers': ['', 'Conquest', 'Duels'],
                        'rows': [
                            ['Opponent', 'AI- or human-defended lands',
                             'Another ruler or the AI'],
                            ['Length', 'One land battle', 'A chosen point target'],
                            ['Your cards', 'Committed from your Collection',
                             'Hands drawn from one shared deck'],
                            ['You win by', 'Beating the land\'s defence',
                             'Point target or Checkmate'],
                        ],
                        'col_widths': [0.20, 0.40, 0.40],
                    }},
                    '',
                    {'bullet': 'Conquest: the map game. Assemble an attack '
                     'force from your Collection, challenge a land defence, '
                     'and claim the land if you win. See the Conquest '
                     'chapters.'},
                    {'bullet': 'Duels: the full head-to-head match. Both '
                     'players draw from a shared deck, build figures over '
                     'several rounds, cast spells, and battle for points. '
                     'See the Duels chapters.'},
                    '',
                    {'heading': 'The Two Sides'},
                    {'table': {
                        'headers': ['', 'Offensive (Green)', 'Defensive (Blue)'],
                        'rows': [
                            ['Suits',
                             [(_s + 'hearts.png', ''), (_s + 'diamonds.png', '')],
                             [(_s + 'clubs.png', ''), (_s + 'spades.png', '')]],
                            ['Castle', 'Djungle Maharaja', 'Himalaya Maharaja'],
                            ['Specialty', 'Charge & mobility', 'Defense & buffs'],
                        ],
                        'col_widths': [0.20, 0.40, 0.40],
                    }},
                    '',
                    {'heading': 'Your Forces'},
                    'In both modes your figures live in three fields:',
                    '',
                    {'icon_bullet': _sl + 'castle_small.png',
                     'text': 'Castle: home of the Maharaja and Kings. '
                     'Produces villagers and warriors.'},
                    {'icon_bullet': _sl + 'village_small.png',
                     'text': 'Village: farms, temples, and craftsmen. '
                     'Produces food, materials, and armour.'},
                    {'icon_bullet': _sl + 'military_small.png',
                     'text': 'Military: soldiers and fortifications '
                     'that fight in battle.'},
                    '',
                    {'heading': 'Win Conditions'},
                    {'bullet': 'Conquest: win the conquer battle to take '
                     'the land into your kingdom.'},
                    {'bullet': 'Duels - Score: reach the point target chosen '
                     'when the game is created. Quick (7), Standard (21), '
                     'and Epic (35) are presets, but the target can also be '
                     'typed in. Points are earned by winning battles and '
                     'forcing folds.'},
                    {'bullet': 'Duels - Checkmate: destroy your opponent\'s '
                     'Maharaja. This ends the game immediately regardless '
                     'of score.'},
                ],
            },

            # ── 1  Game Flow ────────────────────────────────────────
            {
                'title': 'Game Flow',
                'group': 'Duels',
                'mode': 'duel',
                'content': [
                    {'note': 'This chapter describes duels: full matches '
                     'against another ruler or the AI. Conquer battles are '
                     'single-land fights with prepared forces - see Conquer '
                     'Battles.'},
                    '',
                    'A duel consists of many rounds. Each round both '
                    'players take turns building their kingdoms, then '
                    'resolve a battle.',
                    '',
                    {'heading': 'Rounds & Turns'},
                    {'icon_text': _st + 'turn_active.png',
                     'text': 'Each round both the invader and the defender '
                     'receive 6 turns. Players alternate taking one action '
                     'per turn.'},
                    '',
                    {'heading': 'Turn Actions'},
                    'Each of the following costs one turn:',
                    '',
                    {'bullet': 'Build a figure (place cards from '
                     'your hand onto the board).'},
                    {'bullet': 'Pick up a figure (return its cards to your '
                     'hand and free the slot).'},
                    {'bullet': 'Change cards (swap any number of main-hand '
                     'cards for new ones from the deck).'},
                    {'bullet': 'Cast a spell (pay the card cost and apply '
                     'the effect).'},
                    '',
                    {'heading': 'Ceasefire'},
                    {'icon_text': _st + 'ceasefire_active.png',
                     'text': 'At the start of each round a ceasefire is '
                     'active. During ceasefire the invader cannot advance. '
                     'The ceasefire lifts after the invader has used 3 '
                     'turns (or when the invader has only 1 turn left).'},
                    '',
                    {'heading': 'Advancing'},
                    {'icon_text': _st + 'invader_active.png',
                     'text': 'Both players can advance a figure once the '
                     'ceasefire has lifted. Any figure without Cannot '
                     'Attack can advance. The invader must advance with '
                     'their last turn. Advancing immediately sets the '
                     'advancing player\'s remaining turns to 0. The '
                     'defender then gets 1 turn to counter-advance or '
                     'respond.'},
                    '',
                    {'heading': 'End of Round'},
                    'After the battle is resolved a new round begins:',
                    '',
                    {'bullet': 'The winner (or the defender, on a draw) becomes the invader.'},
                    {'bullet': 'Both players reset to 6 turns.'},
                    {'bullet': 'Ceasefire activates.'},
                    {'bullet': 'Each player draws 2 side cards.'},
                    {'bullet': 'Resting figures become available again.'},
                    '',
                    {'heading': 'Auto-Fill'},
                    'If your main hand drops below 5 cards at the start of '
                    'your turn, it is automatically refilled from the deck '
                    'to 5 cards.',
                ],
            },

            # ── 2  Cards & Hands ────────────────────────────────────
            {
                'title': 'Cards & Hands',
                'group': 'Basics',
                'mode': 'both',
                'content': [
                    'The card pool contains 104 cards: 64 main cards and '
                    '40 side cards. In duel mode both players draw from the '
                    'same shared deck; each player is dealt 12 main cards '
                    'and 8 side cards.',
                    '',
                    {'heading': 'The Four Suits'},
                    {'table': {
                        'headers': ['Suit', 'Colour', 'Type'],
                        'rows': [
                            [(_s + 'hearts.png', 'Hearts'), 'Green', 'Offensive'],
                            [(_s + 'diamonds.png', 'Diamonds'), 'Green', 'Offensive'],
                            [(_s + 'clubs.png', 'Clubs'), 'Blue', 'Defensive'],
                            [(_s + 'spades.png', 'Spades'), 'Blue', 'Defensive'],
                        ],
                        'col_widths': [0.35, 0.30, 0.35],
                    }},
                    '',
                    {'heading': 'Suit Advantage Cycle'},
                    'Each suit beats one other suit. This cycle determines '
                    'Distance Attack targets and Blocks Bonus targets:',
                    '',
                    'Spades \u2192 Hearts \u2192 Clubs \u2192 Diamonds '
                    '\u2192 Spades',
                    '',
                    {'heading': 'Card Categories'},
                    {'table': {
                        'headers': ['Card', 'Val', 'Cat.', 'Figure', 'Spell', 'Battle Move'],
                        'rows': [
                            ['K (King)', '4', 'Key',
                             'King, Maharaja',
                             'Infinite Hammer',
                             'Call King'],
                            ['A (Ace)', '3', 'Key',
                             'Fortress, Gorkha',
                             'Invader Swap',
                             'Call Military'],
                            ['Q (Queen)', '2', 'Key',
                             'Farm upgrade, Temple, Mfg.',
                             'Blitzkrieg',
                             'Block'],
                            ['J (Jack)', '1', 'Key',
                             'Farm',
                             'Peasant War',
                             'Call Villager'],
                            ['10', '10', 'Num.',
                             'Power card',
                             'Fill up to 10',
                             'Dagger'],
                            ['9', '9', 'Num.',
                             'Power card',
                             'All Seeing Eye, Ceasefire',
                             'Dagger'],
                            ['8', '8', 'Num.',
                             'Power card',
                             'Draw 2 Main, Ceasefire',
                             'Dagger'],
                            ['7', '7', 'Num.',
                             'Power card, Mfg. upgrade',
                             'Dump Cards, Ceasefire',
                             'Dagger'],
                            ['6', '6', 'Side',
                             'Healer upgrade, number card',
                             'Explosion',
                             '\u2014'],
                            ['5', '5', 'Side',
                             'Wall, Cavalry',
                             'Civil War',
                             '\u2014'],
                            ['4', '4', 'Side',
                             'Archer, Wall, Cavalry',
                             'Forced Deal',
                             '\u2014'],
                            ['3', '3', 'Side',
                             'Archer, Mason, Carpenter',
                             'Poison, Health Boost',
                             '\u2014'],
                            ['2', '2', 'Side',
                             'Healer, Craftsman',
                             'Draw 2 Side',
                             '\u2014'],
                        ],
                        'col_widths': [0.11, 0.05, 0.06, 0.30, 0.30, 0.18],
                    }},
                    '',
                    {'heading': 'Your Two Hands'},
                    {'note': 'Hands and card changing exist in duels only. '
                     'In conquest your cards live in your Collection and '
                     'are committed to attacks and defences instead.'},
                    {'bullet': 'Main Hand (up to 12 cards): your primary '
                     'set of cards. Auto-refilled to 5 if it drops below '
                     'that threshold.'},
                    {'bullet': 'Side Hand (up to 8 cards): additional cards '
                     'obtained at the start of each round (2 cards) and '
                     'through certain spells.'},
                    '',
                    {'heading': 'Changing Cards'},
                    'Once per turn you may swap any number of main-hand '
                    'cards for new ones from the deck. This consumes one turn.',
                ],
            },

            # ── 3  Building Figures ─────────────────────────────────
            {
                'title': 'Building',
                'group': 'Duels',
                'mode': 'duel',
                'content': [
                    {'note': 'Building with turns as described here happens '
                     'in duels. In conquest you assemble figures beforehand '
                     'in the attack setup - see Conquering a Land.'},
                    '',
                    {'icon_text': _gb + 'hammer_active.png',
                     'text': 'Figures are built in the Build Screen. Open '
                     'it by clicking the hammer button on the main game '
                     'screen. Building a figure costs one turn.'},
                    '',
                    {'heading': 'How to Build'},
                    '1. Choose a colour (Djungle or Himalaya) to filter '
                    'which figure families are shown.',
                    '2. Click a figure family icon. Only families you '
                    'have the cards for are highlighted.',
                    '3. Scroll through the available variants (different '
                    'suits and number cards).',
                    '4. Press "create!" and confirm. The required cards '
                    'are automatically taken from your hand.',
                    '',
                    {'heading': 'Card Requirements'},
                    {'bullet': 'Key Card: determines the figure type '
                     '(e.g. J for farms, A for fortresses, K for kings).'},
                    {'bullet': 'Number Card (7\u201310): sets the figure\'s '
                     'base power and resource output or consumption. Not '
                     'every figure needs one.'},
                    {'bullet': 'All cards must be of the same suit.'},
                    '',
                    {'heading': 'Figure Colour'},
                    'Green figures (Hearts / Diamonds) are offensive. '
                    'Blue figures (Clubs / Spades) are defensive.',
                    '',
                    {'heading': 'Upgrading'},
                    'Upgrades happen on the Field Screen, not the Build '
                    'Screen. Click an existing figure, then press '
                    '"Upgrade" (only shown when you hold the required '
                    'upgrade card). The upgrade card is taken from your '
                    'hand and the figure transforms into its upgraded '
                    'form. Upgrading does not cost a turn.',
                    '',
                    {'heading': 'Picking Up'},
                    'On the Field Screen you may pick up a figure to '
                    'reclaim its cards back into your hand. The slot '
                    'becomes empty again. This costs one turn.',
                ],
            },

            # ── 4  Castle Figures ───────────────────────────────────
            {
                'title': 'Castle',
                'group': 'Basics',
                'mode': 'both',
                'content': [
                    {'icon_text': _sl + 'castle_small.png',
                     'text': 'Castle figures are the rulers of your kingdom. '
                     'Each player starts with a Maharaja already placed. '
                     'Additional Kings can be built using King (K) cards.'},
                    '',
                    {'heading': 'Himalaya Castle (Blue)'},
                    {'table': {
                        'headers': ['Figure', 'Key Cards', 'Power', 'Battle Bonus', 'Produces'],
                        'rows': [
                            [(_fi + 'castle_black.png', 'Himalaya King'),
                             'K\u2663 or K\u2660', '15', '+4',
                             '2 Villagers, 1 Warrior'],
                            [(_fi + 'maharaja_black.png', 'Himalaya Maharaja'),
                             'K\u2663 or K\u2660', '16', '+4',
                             '3 Villagers, 2 Warriors'],
                        ],
                        'col_widths': [0.24, 0.16, 0.10, 0.14, 0.36],
                    }},
                    '',
                    {'heading': 'Djungle Castle (Green)'},
                    {'table': {
                        'headers': ['Figure', 'Key Cards', 'Power', 'Battle Bonus', 'Produces'],
                        'rows': [
                            [(_fi + 'castle_red.png', 'Djungle King'),
                             'K\u2665 or K\u2666', '15', '+4',
                             '2 Villagers, 1 Warrior'],
                            [(_fi + 'maharaja_red.png', 'Djungle Maharaja'),
                             'K\u2665 or K\u2666', '16', '+4',
                             '3 Villagers, 2 Warriors'],
                        ],
                        'col_widths': [0.24, 0.16, 0.10, 0.14, 0.36],
                    }},
                    '',
                    {'heading': 'Checkmate'},
                    {'icon_text': _sk + 'checkmate.png',
                     'text': 'The Maharaja has the Checkmate skill. '
                     'If your Maharaja is destroyed you instantly lose the '
                     'game. The Maharaja is immune to all spells and cannot '
                     'be selected as a defender by your opponent. It is '
                     'always visible to both players. Protect it at all costs!'},
                    '',
                    {'heading': 'Castle Resources'},
                    'Castles are the only source of Villagers and Warriors. '
                    'Without a castle producing these resources, you cannot '
                    'sustain village or military figures. Building additional '
                    'Kings increases your resource output.',
                ],
            },

            # ── 5  Village Figures ──────────────────────────────────
            {
                'title': 'Village',
                'group': 'Basics',
                'mode': 'both',
                'content': [
                    {'icon_text': _sl + 'village_small.png',
                     'text': 'Village figures produce the resources your '
                     'kingdom needs - food for soldiers, materials for '
                     'construction, and armour for elite units. Each '
                     'village figure consumes 1 Villager.'},
                    '',
                    {'heading': 'Farms'},
                    'Farms produce food. Small farms can be upgraded to '
                    'large farms by adding a Queen card, doubling output.',
                    '',
                    {'table': {
                        'headers': ['Figure', 'Key', 'Number', 'Upgrade', 'Produces'],
                        'rows': [
                            [(_fi + 'yack_farm1.png', 'Small Yack Farm'),
                             'J (blue)', '7\u201310', 'Q \u2192 Large',
                             'Food \u00d7 N'],
                            [(_fi + 'yack_farm2.png', 'Large Yack Farm'),
                             'J + Q (blue)', '7\u201310', '\u2014',
                             'Food \u00d7 2N'],
                            [(_fi + 'rice_farm1.png', 'Small Rice Farm'),
                             'J (green)', '7\u201310', 'Q \u2192 Large',
                             'Food \u00d7 N'],
                            [(_fi + 'rice_farm2.png', 'Large Rice Farm'),
                             'J + Q (green)', '7\u201310', '\u2014',
                             'Food \u00d7 2N'],
                        ],
                        'col_widths': [0.28, 0.16, 0.12, 0.18, 0.26],
                    }},
                    '',
                    {'heading': 'Temples & Manufactories'},
                    'Temples block the opponent\'s support bonus in battle. '
                    'They can be upgraded to Manufactories that produce armour.',
                    '',
                    {'table': {
                        'headers': ['Figure', 'Key', 'Number', 'Upgrade', 'Produces'],
                        'rows': [
                            [(_fi + 'shrine_black.png', 'Himalaya Temple'),
                             'Q + Q (blue)', '\u2014', '7 \u2192 Shield Mfg.',
                             '\u2014 (blocks bonus)'],
                            [(_fi + 'manufactory_black.png', 'Shield Manufactory'),
                             'Q + Q (blue)', '7', '\u2014',
                             'Armour \u00d7 7'],
                            [(_fi + 'shrine_red.png', 'Djungle Temple'),
                             'Q + Q (green)', '\u2014', '7 \u2192 Sword Mfg.',
                             '\u2014 (blocks bonus)'],
                            [(_fi + 'manufactory_red.png', 'Sword Manufactory'),
                             'Q + Q (green)', '7', '\u2014',
                             'Armour \u00d7 7'],
                        ],
                        'col_widths': [0.28, 0.16, 0.10, 0.20, 0.26],
                    }},
                    '',
                    {'heading': 'Healers & Craftsmen'},
                    'Healers buff allied village figures. They can be '
                    'upgraded to Craftsmen that produce materials.',
                    '',
                    {'table': {
                        'headers': ['Figure', 'Key', 'Number', 'Upgrade', 'Produces'],
                        'rows': [
                            [(_fi + 'himalaya_healer.png', 'Himalaya Healer'),
                             '2 + 2 (blue)', '\u2014', '6 \u2192 Stone Mason',
                             '\u2014 (buffs allies)'],
                            [(_fi + 'stone_mason.png', 'Stone Mason'),
                             '2 (blue)', '3 / 4 / 6', '\u2014',
                             'Material \u00d7 N'],
                            [(_fi + 'djungle_healer.png', 'Djungle Healer'),
                             '2 + 2 (green)', '\u2014', '6 \u2192 Carpenter',
                             '\u2014 (buffs allies)'],
                            [(_fi + 'carpenter.png', 'Carpenter'),
                             '2 (green)', '3 / 4 / 6', '\u2014',
                             'Material \u00d7 N'],
                        ],
                        'col_widths': [0.28, 0.16, 0.12, 0.20, 0.24],
                    }},
                ],
            },

            # ── 6  Military Figures ─────────────────────────────────
            {
                'title': 'Military',
                'group': 'Basics',
                'mode': 'both',
                'content': [
                    {'icon_text': _sl + 'military_small.png',
                     'text': 'Military figures are your primary fighting '
                     'force. They are typically the ones advancing into '
                     'battle. Each military figure consumes 1 Warrior.'},
                    '',
                    {'heading': 'Fortresses'},
                    'Fortresses cannot attack but must be targeted first '
                    'by opponents. They act as shields for your kingdom.',
                    '',
                    {'table': {
                        'headers': ['Figure', 'Key', 'Number', 'Upgrade', 'Consumes'],
                        'rows': [
                            [(_fi + 'fortress1.png', 'Wooden Fortress'),
                             'A (blue)', '7\u201310', '7 \u2192 Stone',
                             'Food \u00d7 N'],
                            [(_fi + 'fortress2.png', 'Stone Fortress'),
                             'A + 7 (blue)', '7\u201310', '\u2014',
                             'Food \u00d7 N, Armour \u00d7 7'],
                        ],
                        'col_widths': [0.28, 0.14, 0.12, 0.16, 0.30],
                    }},
                    '',
                    {'heading': 'Gorkha Warriors'},
                    'Gorkha Warriors are powerful offensive units with the '
                    'Instant Advance skill, allowing them to attack '
                    'immediately when placed.',
                    '',
                    {'table': {
                        'headers': ['Figure', 'Key', 'Number', 'Upgrade', 'Consumes'],
                        'rows': [
                            [(_fi + 'army1.png', 'Gorkha Warriors'),
                             'A (green)', '7\u201310', '7 \u2192 Elite',
                             'Food \u00d7 N'],
                            [(_fi + 'army2.png', 'Elite Gorkha Warriors'),
                             'A + 7 (green)', '7\u201310', '\u2014',
                             'Food \u00d7 N, Armour \u00d7 7'],
                        ],
                        'col_widths': [0.28, 0.14, 0.12, 0.16, 0.30],
                    }},
                    '',
                    {'heading': 'Cavalry'},
                    {'table': {
                        'headers': ['Figure', 'Key', 'Number', 'Consumes', 'Skills'],
                        'rows': [
                            [(_fi + 'cavalry.png', 'Cavalry'),
                             '4 + 5 (green)', '3 / 6',
                             'Material \u00d7 N',
                             'Instant Advance, Cannot Be Blocked, '
                             'Rest After Attack, Cannot Defend'],
                        ],
                        'col_widths': [0.22, 0.14, 0.10, 0.20, 0.34],
                    }},
                    '',
                    'Cavalry is the most mobile unit in the game - it can '
                    'advance immediately, cannot be counter-advanced, but '
                    'must rest for one round after battle.',
                    '',
                    {'heading': 'Walls'},
                    {'table': {
                        'headers': ['Figure', 'Key', 'Number', 'Consumes', 'Skills'],
                        'rows': [
                            [(_fi + 'wall.png', 'Wall'),
                             '4 + 5 (blue)', '3 / 6',
                             'Material \u00d7 N',
                             'Defence Buff, Cannot Attack, '
                             'Cannot Defend, Cannot Be Targeted'],
                        ],
                        'col_widths': [0.22, 0.14, 0.10, 0.20, 0.34],
                    }},
                    '',
                    'Walls cannot fight but boost the defence power of '
                    'your figures when defending by the value of their '
                    'number card.',
                    '',
                    {'heading': 'Archers'},
                    {'table': {
                        'headers': ['Figure', 'Key', 'Number', 'Consumes', 'Skills'],
                        'rows': [
                            [(_fi + 'archers_black.png', 'Himalaya Archer'),
                             '4 (blue)', '3 / 6',
                             'Material \u00d7 N',
                             'Distance Attack'],
                            [(_fi + 'archers_red.png', 'Djungle Archer'),
                             '4 (green)', '3 / 6',
                             'Material \u00d7 N',
                             'Distance Attack'],
                        ],
                        'col_widths': [0.22, 0.14, 0.10, 0.20, 0.34],
                    }},
                    '',
                    'Archers have the Distance Attack skill: once per '
                    'battle they reduce the power of an opponent\'s figure '
                    'whose suit they have an advantage over.',
                ],
            },

            # ── 7  Skills ──────────────────────────────────────────
            {
                'title': 'Skills',
                'group': 'Basics',
                'mode': 'both',
                'content': [
                    'Some figures have innate skills that modify how they '
                    'behave in battle or interact with game mechanics. '
                    'Each skill is listed below with the figures that '
                    'have it in parentheses.',
                    '',
                    {'note': 'Skills apply in both modes. Skills about '
                     'advancing and counter-advancing only matter in duels; '
                     'in conquer battles figures fight directly.'},
                    '',
                    {'separator': True},
                    '',
                    {'heading': 'Combat Skills'},
                    '',
                    {'icon_text': _sk + 'distance.png',
                     'text': 'Distance Attack: reduces the power of an '
                     'opponent\'s figure whose suit this figure has an '
                     'advantage over. The reduction equals the value of '
                     'the number card. Used once per battle. (Archers)'},
                    '',
                    {'icon_text': _sk + 'buff.png',
                     'text': 'Buffs Allies: increases the base power of '
                     'all village figures with the same suit by +4. '
                     'This bonus is treated as base power and cannot be '
                     'blocked. (Healers)'},
                    '',
                    {'icon_text': _sk + 'buff_defence.png',
                     'text': 'Defence Buff: when your figure is defending, '
                     'it gains additional power equal to this figure\'s '
                     'number card value. (Wall)'},
                    '',
                    {'icon_text': _sk + 'block.png',
                     'text': 'Blocks Bonus: blocks the support bonus of '
                     'the opponent\'s battle figure whose suit this figure '
                     'has an advantage over. (Temples)'},
                    '',
                    {'separator': True},
                    '',
                    {'heading': 'Movement Skills'},
                    '',
                    {'icon_text': _sk + 'instant_charge.png',
                     'text': 'Instant Advance: this figure can advance '
                     'immediately on the turn it is built, without waiting '
                     'for the next round. (Gorkha Warriors, Cavalry)'},
                    '',
                    {'icon_text': _sk + 'cannot_be_blocked.png',
                     'text': 'Cannot Be Blocked: when this figure advances, '
                     'the opponent cannot counter-advance. Instead, the '
                     'advancing player selects the opponent\'s battle '
                     'figure. (Cavalry)'},
                    '',
                    {'icon_text': _sk + 'hourglass.png',
                     'text': 'Rest After Attack: after participating in '
                     'battle, this figure must rest for the upcoming round '
                     'and cannot be used. (Cavalry)'},
                    '',
                    {'separator': True},
                    '',
                    {'heading': 'Targeting Skills'},
                    '',
                    {'icon_text': _sk + 'must_be_attacked.png',
                     'text': 'Must Be Attacked: opponents must target '
                     'this figure before any other figure when selecting '
                     'a defender. (Fortresses)'},
                    '',
                    {'icon_text': _sk + 'cannot_defend.png',
                     'text': 'Cannot Defend: this figure cannot be selected '
                     'as a defender and cannot counter-advance. (Walls, '
                     'Cavalry)'},
                    '',
                    {'icon_text': _sk + 'cannot_be_targeted.png',
                     'text': 'Cannot Be Targeted: this figure cannot be '
                     'selected as a target for battle or spells. (Walls)'},
                    '',
                    {'icon_text': _sk + 'cannot_attack.png',
                     'text': 'Cannot Attack: this figure cannot initiate '
                     'an advance or be selected as an attacking figure. '
                     '(Temples, Healers, Fortresses, Walls, Manufactories)'},
                    '',
                    {'icon_text': _sk + 'checkmate.png',
                     'text': 'Checkmate: if this figure is destroyed, its '
                     'owner instantly loses the game. Immune to all spells. '
                     'Cannot be selected as a defender by the opponent. '
                     'Always visible. (Maharaja only)'},
                ],
            },

            # ── 8  Resources & Economy ──────────────────────────────
            {
                'title': 'Resources',
                'group': 'Basics',
                'mode': 'both',
                'content': [
                    {'icon_text': _r + 'rice_meat.png',
                     'text': 'Your figures produce and consume resources. '
                     'If a figure\'s requirements aren\'t met, it suffers '
                     'a resource deficit.'},
                    '',
                    {'note': 'The same economy runs in both modes: in duels '
                     'it is checked every round; in conquest it is checked '
                     'while you assemble an attack or defence force.'},
                    '',
                    {'heading': 'Resource Types'},
                    {'table': {
                        'headers': ['Resource', 'Produced By', 'Consumed By'],
                        'rows': [
                            [(_r + 'villager_black.png', 'Villager (Blue)'),
                             'Kings / Maharaja (Blue)',
                             'All blue village figures'],
                            [(_r + 'villager_red.png', 'Villager (Green)'),
                             'Kings / Maharaja (Green)',
                             'All green village figures'],
                            [(_r + 'warrior_black.png', 'Warrior (Blue)'),
                             'Kings / Maharaja (Blue)',
                             'All blue military figures'],
                            [(_r + 'warrior_red.png', 'Warrior (Green)'),
                             'Kings / Maharaja (Green)',
                             'All green military figures'],
                            [(_r + 'rice_meat.png', 'Food'),
                             'Farms (card value \u00d7 1 or 2)',
                             'Fortresses, Gorkhas'],
                            [(_r + 'wood_stone.png', 'Material'),
                             'Mason / Carpenter (3/4/6)',
                             'Walls, Archers, Cavalry'],
                            [(_r + 'sword_shield.png', 'Armour'),
                             'Manufactories (7)',
                             'Stone Fortress, Elite Gorkha'],
                        ],
                        'col_widths': [0.30, 0.35, 0.35],
                    }},
                    '',
                    {'heading': 'Resource Deficit'},
                    'If consumption exceeds production for a resource, '
                    'figures that depend on that resource fall into deficit. '
                    'The check is iterative: a figure in deficit does not '
                    'contribute its own production, which can cascade and '
                    'cause additional deficits.',
                    '',
                    {'bullet': 'Figures in resource deficit cannot advance '
                     'into battle.'},
                    {'bullet': 'If a battle figure has a deficit, its owner '
                     'automatically loses the battle (10 points to opponent).'},
                    {'bullet': 'Deficit is shown with red-bordered values on '
                     'the resource panel.'},
                    '',
                    {'heading': 'Economy Tips'},
                    {'bullet': 'Always ensure you have enough Villagers '
                     'before building more village figures.'},
                    {'bullet': 'Build farms early to feed your military.'},
                    {'bullet': 'Upgrade a temple to a manufactory before '
                     'building elite units that require armour.'},
                ],
            },

            # ── 9  Spells ──────────────────────────────────────────
            {
                'title': 'Spells',
                'group': 'Duels',
                'mode': 'duel',
                'content': [
                    {'note': 'Spell casting mid-game happens in duels. In '
                     'conquest only Prelude spells apply: chosen in the '
                     'attack setup, they trigger once before the battle '
                     'starts - see Conquering a Land.'},
                    '',
                    {'icon_text': _gb + 'book_active.png',
                     'text': 'Cast spells by paying specific card '
                     'combinations from your hand. Casting a spell costs '
                     'one turn.'},
                    '',
                    {'heading': 'Greed Spells'},
                    'Card manipulation: draw, exchange, or discard cards.',
                    '',
                    {'icon_text': _sp + 'draw_two_side.png',
                     'text': 'Draw 2 Side Cards: Cost: 1\u00d7 2 (any suit). '
                     'Draw 2 additional side cards from the deck.'},
                    '',
                    {'icon_text': _sp + 'draw_two_main.png',
                     'text': 'Draw 2 Main Cards: Cost: 1\u00d7 8 (any suit). '
                     'Draw 2 additional main cards from the deck.'},
                    '',
                    {'icon_text': _sp + 'fill10.png',
                     'text': 'Fill up to 10: Cost: 1\u00d7 10 (any suit). '
                     'Fill your main hand up to 10 cards.'},
                    '',
                    {'icon_text': _sp + 'forced_deal.png',
                     'text': 'Forced Deal: Cost: 2\u00d7 4 (same colour). '
                     'Exchange 2 random main cards with your opponent.'},
                    '',
                    {'icon_text': _sp + 'dump_cards.png',
                     'text': 'Dump Cards: Cost: 4\u00d7 7 (all same colour). '
                     'Both players dump all cards and refill to 5 main '
                     '+ 4 side.'},
                    '',
                    {'separator': True},
                    '',
                    {'heading': 'Enchantment Spells'},
                    'Modify figure power or reveal information.',
                    '',
                    {'icon_text': _sp + 'poisson_portion.png',
                     'text': 'Poison: Cost: 2\u00d7 3 (same colour, blue). '
                     'Target: opponent figure. Reduces its power by \u20136 '
                     'for next battle.'},
                    '',
                    {'icon_text': _sp + 'health_portion.png',
                     'text': 'Health Boost: Cost: 2\u00d7 3 (same colour, green). '
                     'Target: own figure. Increases its power by +6 '
                     'for next battle.'},
                    '',
                    {'icon_text': _sp + 'eye.png',
                     'text': 'All Seeing Eye: Cost: 2\u00d7 9 (same colour). '
                     'All opponent\'s cards and hidden figures become '
                     'visible until end of round.'},
                    '',
                    {'icon_text': _sp + 'bomb.png',
                     'text': 'Explosion: Cost: 4\u00d7 6 (all same colour). '
                     'Destroy any target figure. Cannot target Maharajas.'},
                    '',
                    {'icon_text': _sp + 'infinite_hammer.png',
                     'text': 'Infinite Hammer: Cost: 1\u00d7 K (any suit). '
                     'This turn you can build, upgrade, and pick up as many '
                     'figures as you want.'},
                    '',
                    {'separator': True},
                    '',
                    {'heading': 'Tactics Spells (Counterable)'},
                    'Battle condition modifiers. All tactics spells can be '
                    'countered by your opponent if they hold matching cards. '
                    'Cannot be cast during ceasefire.',
                    '',
                    {'icon_text': _sp + 'ceasefire.png',
                     'text': 'Ceasefire: Cost: 3 same-colour number cards '
                     '(7+8+9 or 8+9+10). Both players gain 3 additional '
                     'turns. Invader starts next turn. Ceasefire reactivates.'},
                    '',
                    {'icon_text': _sp + 'peasant_war.png',
                     'text': 'Peasant War: Cost: 2\u00d7 J (same colour). '
                     'Only village figures can be selected for battle. '
                     'Both players get 2 turns. Invader starts.'},
                    '',
                    {'icon_text': _sp + 'civil_war.png',
                     'text': 'Civil War: Cost: 2\u00d7 5 (same colour). '
                     'Each player selects up to 2 village figures of the '
                     'same colour for battle. Both get 2 turns.'},
                    '',
                    {'icon_text': _sp + 'invader_swap.png',
                     'text': 'Invader Swap: Cost: 2\u00d7 A (same colour). '
                     'Invader and defender roles swap. Both get 2 turns. '
                     'Invader starts.'},
                    '',
                    {'icon_text': _sp + 'blitzkrieg.png',
                     'text': 'Blitzkrieg: Cost: 2\u00d7 Q (same colour). '
                     'You become invader. Your next advance cannot be '
                     'counter-advanced. Both get 2 turns. Ceasefire until '
                     'last turn.'},
                    '',
                    {'heading': 'Counter-Spelling'},
                    'When an opponent casts a Tactics spell, you are prompted '
                    'to counter it. To counter, you must pay the same card '
                    'cost as the spell. If countered, the spell is negated '
                    'and both players\' cards are discarded.',
                ],
            },

            # ── 10  Battle ─────────────────────────────────────────
            {
                'title': 'Battle',
                'group': 'Duels',
                'mode': 'duel',
                'content': [
                    {'note': 'This is the duel battle flow. Conquer battles '
                     'skip advancing and the Battle Shop entirely - see '
                     'Conquer Battles.'},
                    '',
                    {'icon_text': _gb + 'battle_active.png',
                     'text': 'Battles determine who scores points and who '
                     'loses figures. They follow a structured flow from '
                     'advance to resolution.'},
                    '',
                    {'heading': 'Battle Flow Overview'},
                    '1. Invader advances a figure.',
                    '2. Defender counter-advances (or invader selects if '
                    'blocked).',
                    '3. Both players decide: fight or fold.',
                    '4. Both players buy up to 3 battle moves in the '
                    'Battle Shop.',
                    '5. Three combat rounds are played.',
                    '6. Winner is determined by total power difference.',
                    '',
                    {'separator': True},
                    '',
                    {'heading': 'Counter-Advance'},
                    'After the invader advances, the defender selects a '
                    'figure to counter-advance. This costs the defender\'s '
                    'remaining turn.',
                    '',
                    {'bullet': 'Cannot Be Blocked: if the advancing figure '
                     'has this skill, the invader selects the defender\'s '
                     'battle figure instead.'},
                    {'bullet': 'Must Be Attacked: figures with this skill '
                     '(Fortresses) must be chosen as the defender before '
                     'any others.'},
                    {'bullet': 'Blitzkrieg: the first advance after this '
                     'spell cannot be counter-advanced.'},
                    '',
                    {'heading': 'Fold'},
                    'After both figures are selected, each player can choose '
                    'to fold (the invader decides first). Folding forfeits '
                    'the battle and awards the opponent 10 points.',
                    '',
                    {'separator': True},
                    '',
                    {'heading': 'Battle Shop Moves'},
                    {'icon_text': _gb + 'battleshop_active.png',
                     'text': 'Before the 3-round battle begins, both '
                     'players purchase up to 3 battle moves by playing '
                     'cards.'},
                    '',
                    {'table': {
                        'headers': ['Move', 'Card', 'Effect'],
                        'rows': [
                            [(_bm + 'dagger.png', 'Dagger'),
                             '7 / 8 / 9 / 10',
                             'Adds card value to your power this round'],
                            [(_bm + 'double_dagger.png', 'Double Dagger'),
                             '2 same-colour daggers',
                             'Combined value of both cards'],
                            [(_bm + 'block.png', 'Block'),
                             'Q',
                             'Both powers become 0 this round'],
                            [(_bm + 'village.png', 'Call Villager'),
                             'J',
                             'Call a village figure into battle'],
                            [(_bm + 'military.png', 'Call Military'),
                             'A',
                             'Deploy additional military figure'],
                            [(_bm + 'castle.png', 'Call King'),
                             'K',
                             'Call the king himself into the fray'],
                        ],
                        'col_widths': [0.22, 0.22, 0.56],
                    }},
                    '',
                    {'heading': 'Three Combat Rounds'},
                    'After both players confirm their moves, the battle '
                    'plays out over 3 rounds. The invader plays first each '
                    'round. Each round both players play one move (or pass '
                    'if they have no moves left).',
                    '',
                    'The power difference each round is accumulated and '
                    'added to the overall figure power difference.',
                    '',
                    {'separator': True},
                    '',
                    {'heading': 'Power Calculation'},
                    'A figure\'s total power is:',
                    '',
                    'Base Power + Ally Buffs + Support Bonus + Enchantments '
                    '\u2212 Distance Attack',
                    '',
                    {'bullet': 'Base Power: sum of all card values (or '
                     'fixed: King = 15, Maharaja = 16).'},
                    {'bullet': 'Ally Buffs: +4 per Healer with the same suit '
                     '(treated as base power, not blockable).'},
                    {'bullet': 'Support Bonus: sum of all same-suit allies\' '
                     'key-card values + Defence Buff bonus. CAN be blocked '
                     'by opponent\'s temple.'},
                    {'bullet': 'Enchantments: Poison (\u22126) or '
                     'Health Boost (+6).'},
                    {'bullet': 'Distance Attack: Archer penalty equal to '
                     'its number card value vs. a suit-disadvantaged opponent.'},
                    '',
                    {'heading': 'Resolution'},
                    {'table': {
                        'headers': ['Outcome', 'Points', 'What Happens'],
                        'rows': [
                            ['Win',
                             'Loser\'s figure base power',
                             'Loser\'s figure destroyed. Winner picks 1 card.'],
                            ['Draw',
                             '\u2014',
                             'Defender chooses: destroy opponent\'s figure, '
                             'take 10 pts, or pick a card.'],
                            ['Fold',
                             '10 pts to opponent',
                             'No figure destroyed. New round starts.'],
                            ['Auto-Loss',
                             '10 pts to opponent',
                             'Triggered when a player has no valid figures.'],
                        ],
                        'col_widths': [0.14, 0.24, 0.62],
                    }},
                    '',
                    {'heading': 'Civil War Battles'},
                    'In a Civil War both players select up to 2 village '
                    'figures of the same colour. If the loser has 2 figures '
                    'in battle, both are destroyed and the points awarded '
                    'equal the sum of both figures\' base power.',
                ],
            },

            # ── 11  Your Kingdom (Conquest) ─────────────────────────
            {
                'title': 'Your Kingdom',
                'group': 'Conquest',
                'mode': 'conquest',
                'content': [
                    'The Kingdom screen shows a map of lands. Lands you '
                    'conquer join your kingdom, produce riches over time, '
                    'and can be attacked by other rulers.',
                    '',
                    {'heading': 'Lands & Tiers'},
                    'Every land has a tier from 1 to 6. Higher tiers field '
                    'stronger defences and produce more:',
                    '',
                    {'table': {
                        'headers': ['Tier', 'Name'],
                        'rows': [
                            ['1', 'Border Watch'],
                            ['2', 'Mountain Warden'],
                            ['3', 'Suit Bastion'],
                            ['4', 'Apex Citadel'],
                            ['5', 'Imperial Bulwark'],
                            ['6', 'Eternal Citadel'],
                        ],
                        'col_widths': [0.20, 0.80],
                    }},
                    '',
                    {'heading': 'Production'},
                    {'icon_bullet': _kg + 'gold.png',
                     'text': 'Gold: every land produces gold over time. '
                     'Collect it on the Kingdom screen - the vault only '
                     'holds so much uncollected gold, so visit regularly.'},
                    {'icon_bullet': _kg + 'main_booster_production.png',
                     'text': 'Boosters & maps: kingdom skills unlock slow '
                     'production of booster packs and maps.'},
                    '',
                    {'heading': 'Levels & Skills'},
                    'Kingdoms earn experience and level up (to level 50). '
                    'Each level grants 3 skill points to spend on skills:',
                    '',
                    {'icon_bullet': _kg + 'gold_vault.png',
                     'text': 'Economy: Gold Production, Gold Vault, Main / '
                     'Side Booster Production, Map Production, and Atlas '
                     '(storage capacity).'},
                    {'icon_bullet': _kg + 'shield.png',
                     'text': 'Defence: Shield Cost Reduction and Core '
                     'Protection - when your kingdom shrinks to its last '
                     'lands, they are shielded automatically.'},
                    {'icon_bullet': _kg + 'loot_chance.png',
                     'text': 'Loot Chance: a successful defence can loot '
                     'cards from the attacker.'},
                    '',
                    {'heading': 'Cooldown & Maps'},
                    {'icon_bullet': _dlg + 'map.png',
                     'text': 'After a conquest there is a cooldown before '
                     'your next attack (15 minutes). Spending a Map skips '
                     'it immediately.'},
                    '',
                    {'heading': 'Shields'},
                    'Buy shields with gold (priced per hour and per land) '
                    'to protect your lands from other rulers while you are '
                    'away.',
                ],
            },

            # ── 12  Conquering a Land (Conquest) ────────────────────
            {
                'title': 'Conquering a Land',
                'group': 'Conquest',
                'mode': 'conquest',
                'content': [
                    'Tap a land on the map to see its tier, defence, and '
                    'production, then open the Conquer setup to prepare '
                    'your attack.',
                    '',
                    {'heading': 'Assemble Your Attack'},
                    {'bullet': 'Figures: build your attack force from cards '
                     'in your Collection. The recipes are the same as in '
                     'duels (see the Basics chapters), and the resource '
                     'economy must hold up.'},
                    {'bullet': 'Tactics: choose exactly three battle-move '
                     'cards - one is played in each battle round. You need '
                     'all three before you can start.'},
                    {'bullet': 'Prelude spells (optional): effects that '
                     'trigger once before the battle starts, such as '
                     'drawing extra tactics.'},
                    '',
                    {'note': 'Cards committed to an attack or defence are '
                     'locked - they cannot be sold or used elsewhere until '
                     'you release them.'},
                    '',
                    {'heading': 'Stakes'},
                    {'table': {
                        'headers': ['Outcome', 'What Happens'],
                        'rows': [
                            ['Win', 'The land joins your kingdom and you '
                             'loot cards from its defence.'],
                            ['Lose', 'The defence may loot some of your '
                             'committed cards.'],
                            ['Draw', 'Ownership unchanged; no cards are '
                             'looted.'],
                        ],
                        'col_widths': [0.16, 0.84],
                    }},
                    '',
                    {'heading': 'After Victory'},
                    'Your winning attack force becomes the land\'s new '
                    'defence. You can rework it any time in the defence '
                    'setup - keep your best lands well defended, because '
                    'other rulers can attack them.',
                ],
            },

            # ── 13  Conquer Battles (Conquest) ──────────────────────
            {
                'title': 'Conquer Battles',
                'group': 'Conquest',
                'mode': 'conquest',
                'content': [
                    'A conquer battle is not a full duel. It is a short, '
                    'focused land fight: your prepared attack force against '
                    'the land\'s saved defence, whether that defence belongs '
                    'to the AI or another ruler. There is no building or '
                    'advancing mid-battle, and no routine deck draw. Gamble '
                    'is the exception: it replaces one tactic with two random tactics.',
                    '',
                    {'heading': 'Three Rounds'},
                    'The battle lasts three rounds. In each round you play '
                    'one of your tactic cards against the defence, and the '
                    'total power difference decides the battle.',
                    '',
                    {'heading': 'Your Actions Each Round'},
                    {'bullet': 'Play: play one of your prepared tactics.'},
                    {'bullet': 'Combine: merge two Daggers into a Double '
                     'Dagger for a stronger strike.'},
                    {'bullet': 'Dismantle: split a combined tactic back '
                     'into its parts.'},
                    {'bullet': 'Gamble: sacrifice one tactic to draw two '
                     'random replacements. Once per round, up to three '
                     'times per battle.'},
                    {'bullet': 'Skip: pass the round without playing.'},
                    '',
                    {'note': 'Each round has a 60-second timer. When it '
                     'runs out, a random tactic is played for you - so '
                     'don\'t wander off mid-battle.'},
                    '',
                    {'heading': 'Defending Your Lands'},
                    'Your lands defend themselves automatically using '
                    'their defence setup. Check the Alerts panel on the '
                    'Kingdom screen for attack reports, and refresh your '
                    'defences as you loot better cards.',
                ],
            },

        ]

        # Order chapters so each sidebar group is consecutive:
        # shared reference first, then the conquest journey, then duels.
        order = [
            'Overview', 'Cards & Hands', 'Castle', 'Village', 'Military',
            'Skills', 'Resources',
            'Your Kingdom', 'Conquering a Land', 'Conquer Battles',
            'Game Flow', 'Building', 'Spells', 'Battle',
        ]
        by_title = {section['title']: section for section in sections}
        return [by_title[title] for title in order]

    # ════════════════════════════════════════════════════════════════════
    #  Rendering helpers
    # ════════════════════════════════════════════════════════════════════

    def _build_menu_rects(self):
        """Pre-calculate rectangles for sidebar items and group headers.

        Sections carry an optional ``group`` label; consecutive sections
        sharing a group get one header row above them. Item height shrinks
        automatically so every row fits inside the sidebar.
        """
        self.menu_rects = []
        self._sidebar_group_rows = []
        pad = self.menu_item_pad

        rows = []              # ('header', label) | ('item', section_index)
        last_group = None
        for i, section in enumerate(self.sections):
            group = section.get('group')
            if group and group != last_group:
                rows.append(('header', group))
                last_group = group
            rows.append(('item', i))

        n_items = len(self.sections)
        n_headers = sum(1 for kind, _ in rows if kind == 'header')
        header_ratio = 0.72
        avail = (self.sidebar_h - settings.GUIDE_MENU_TOP_PAD
                 - pad * max(0, len(rows) - 1) - int(0.008 * settings.SCREEN_HEIGHT))
        fit_h = int(avail / max(1.0, n_items + header_ratio * n_headers))
        item_h = max(19, min(settings.GUIDE_MENU_ITEM_H, fit_h))
        header_h = max(16, int(item_h * header_ratio))
        self.menu_item_h = item_h

        y = self.sidebar_y + settings.GUIDE_MENU_TOP_PAD
        for kind, value in rows:
            if kind == 'header':
                rect = pygame.Rect(self.sidebar_x, y, self.sidebar_w, header_h)
                self._sidebar_group_rows.append((value, rect))
                y += header_h + pad
            else:
                rect = pygame.Rect(self.sidebar_x, y, self.sidebar_w, item_h)
                self.menu_rects.append(rect)
                y += item_h + pad

    def _render_section(self):
        """Pre-render the current section's content onto an off-screen surface.

        This allows pixel-level scrolling without re-rendering every frame.
        """
        section = self.sections[self.current_section]
        content = section['content']

        line_spacing = settings.GUIDE_LINE_SPACING
        paragraph_spacing = settings.GUIDE_PARAGRAPH_SPACING
        heading_spacing_above = settings.GUIDE_HEADING_SPACING_ABOVE
        bullet_indent = settings.GUIDE_BULLET_INDENT
        bullet_marker_gap = settings.GUIDE_BULLET_MARKER_GAP
        separator_v_pad = settings.GUIDE_SEPARATOR_V_PAD
        usable_width = self.content_w - settings.GUIDE_CONTENT_MARGIN

        # First pass - measure total height
        y = 0
        blocks = self._layout_blocks(content, usable_width, bullet_indent,
                                      bullet_marker_gap, line_spacing,
                                      paragraph_spacing, heading_spacing_above,
                                      separator_v_pad)
        for block in blocks:
            y += block['height']

        total_h = max(y, 1)
        self._rendered_height = total_h

        # Compute visible body height (content_h minus title and padding)
        title_h = self.section_title_font.get_height()
        body_overhead = (settings.GUIDE_TITLE_TOP_PAD + title_h
                         + settings.GUIDE_TITLE_BOTTOM_PAD
                         + settings.GUIDE_BODY_BOTTOM_PAD)
        self._visible_body_h = max(1, self.content_h - body_overhead)

        # Second pass - draw onto surface
        surf = pygame.Surface((self.content_w, total_h), pygame.SRCALPHA)
        y = 0
        text_x = settings.GUIDE_CONTENT_TEXT_X

        for block in blocks:
            if block['type'] == 'separator':
                sep_y = y + block['height'] // 2
                pygame.draw.line(surf, settings.GUIDE_SEPARATOR_CLR,
                                 (text_x, sep_y),
                                 (text_x + usable_width, sep_y), 1)
            elif block['type'] == 'heading':
                surf.blit(block['surface'], (text_x, y))
            elif block['type'] == 'bullet':
                # Draw bullet marker
                marker = self.body_font.render('\u2022', True, settings.GUIDE_BULLET_CLR)
                surf.blit(marker, (text_x + bullet_indent, y))
                # Draw wrapped lines
                lx = text_x + bullet_indent + marker.get_width() + bullet_marker_gap
                ly = y
                for line_surf in block['lines']:
                    surf.blit(line_surf, (lx, ly))
                    ly += line_surf.get_height() + line_spacing
            elif block['type'] == 'paragraph':
                ly = y
                for line_surf in block['lines']:
                    surf.blit(line_surf, (text_x, ly))
                    ly += line_surf.get_height() + line_spacing
            elif block['type'] == 'note':
                box = pygame.Rect(text_x, y, usable_width, block['box_h'])
                bg = pygame.Surface((box.w, box.h), pygame.SRCALPHA)
                bg.fill((250, 210, 120, 24))
                surf.blit(bg, box.topleft)
                pygame.draw.rect(surf, (150, 126, 74), box, 1, border_radius=4)
                pygame.draw.rect(surf, settings.GUIDE_HEADING_CLR,
                                 pygame.Rect(box.x, box.y, 3, box.h))
                lx = text_x + block['pad_x'] + 6
                ly = y + block['pad_y']
                for line_surf in block['lines']:
                    surf.blit(line_surf, (lx, ly))
                    ly += line_surf.get_height() + line_spacing
            elif block['type'] == 'icon_text':
                icon_sz = block.get('icon_size', settings.GUIDE_ICON_SIZE)
                icon_gap = settings.GUIDE_ICON_TEXT_GAP
                icon = self._load_icon(block['icon_path'], icon_sz)
                # Vertically centre icon relative to first text line
                surf.blit(icon, (text_x, y))
                lx = text_x + icon_sz + icon_gap
                ly = y
                for line_surf in block['lines']:
                    surf.blit(line_surf, (lx, ly))
                    ly += line_surf.get_height() + line_spacing
            elif block['type'] == 'icon_bullet':
                icon_sz = block.get('icon_size', settings.GUIDE_ICON_SIZE)
                icon_gap = settings.GUIDE_ICON_TEXT_GAP
                icon = self._load_icon(block['icon_path'], icon_sz)
                ix = text_x + bullet_indent
                surf.blit(icon, (ix, y))
                lx = ix + icon_sz + icon_gap
                ly = y
                for line_surf in block['lines']:
                    surf.blit(line_surf, (lx, ly))
                    ly += line_surf.get_height() + line_spacing
            elif block['type'] == 'table':
                self._render_table_block(surf, block, text_x, y,
                                         usable_width, line_spacing)
            elif block['type'] == 'image':
                v_pad = settings.GUIDE_IMAGE_V_PAD
                img = block['surface']
                # Centre horizontally
                ix = text_x + (usable_width - img.get_width()) // 2
                surf.blit(img, (ix, y + v_pad))
            elif block['type'] == 'blank':
                pass  # just spacing

            y += block['height']

        self._rendered_content = surf

    def _render_table_block(self, surf, block, text_x, y, usable_width,
                            line_spacing):
        """Render a table block onto *surf* at position (*text_x*, *y*)."""
        headers = block['headers']
        rows = block['rows']
        col_widths_frac = block.get('col_widths')
        row_h = block.get('row_h', settings.GUIDE_TABLE_ROW_H)
        col_pad = settings.GUIDE_TABLE_COL_PAD
        icon_sz = block.get('icon_size', settings.GUIDE_TABLE_ICON_SIZE)
        border_clr = settings.GUIDE_TABLE_BORDER_CLR

        num_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
        if num_cols == 0:
            return

        # Calculate column x-positions
        if col_widths_frac:
            col_ws = [int(usable_width * f) for f in col_widths_frac]
        else:
            col_ws = [usable_width // num_cols] * num_cols

        col_xs = []
        cx = text_x
        for cw in col_ws:
            col_xs.append(cx)
            cx += cw

        cur_y = y

        # ── header row ──────────────────────────────────────────────
        if headers:
            # Header background
            hdr_bg = pygame.Surface((usable_width, row_h), pygame.SRCALPHA)
            hdr_bg.fill((158, 81, 33, 40))
            surf.blit(hdr_bg, (text_x, cur_y))

            for ci, hdr in enumerate(headers):
                hdr_surf = self.table_font.render(
                    str(hdr), True, settings.GUIDE_TABLE_HEADER_CLR)
                hy = cur_y + (row_h - hdr_surf.get_height()) // 2
                surf.blit(hdr_surf, (col_xs[ci] + col_pad, hy))

            # Bottom border for header
            pygame.draw.line(surf, border_clr,
                             (text_x, cur_y + row_h),
                             (text_x + usable_width, cur_y + row_h), 1)
            cur_y += row_h

        # ── data rows ──────────────────────────────────────────────
        for ri, row in enumerate(rows):
            # Zebra stripe
            if ri % 2 == 1:
                stripe = pygame.Surface((usable_width, row_h), pygame.SRCALPHA)
                stripe.fill(settings.GUIDE_TABLE_ROW_BG_ALT)
                surf.blit(stripe, (text_x, cur_y))

            for ci, cell in enumerate(row):
                if ci >= num_cols:
                    break
                cx_pos = col_xs[ci] + col_pad
                if isinstance(cell, list):
                    # List of (icon_path, text) pairs — draw icons side by side
                    draw_x = cx_pos
                    for item in cell:
                        if isinstance(item, tuple) and len(item) == 2:
                            ip, ct = item
                            ic = self._load_icon(ip, icon_sz)
                            iy = cur_y + (row_h - icon_sz) // 2
                            surf.blit(ic, (draw_x, iy))
                            draw_x += icon_sz + 2
                            if ct:
                                ts = self.table_font.render(
                                    str(ct), True, settings.GUIDE_TABLE_CELL_CLR)
                                ty = cur_y + (row_h - ts.get_height()) // 2
                                surf.blit(ts, (draw_x, ty))
                                draw_x += ts.get_width() + 4
                elif isinstance(cell, tuple) and len(cell) == 2:
                    # (icon_path, text)
                    icon_path, cell_text = cell
                    icon = self._load_icon(icon_path, icon_sz)
                    iy = cur_y + (row_h - icon_sz) // 2
                    surf.blit(icon, (cx_pos, iy))
                    txt_surf = self.table_font.render(
                        str(cell_text), True, settings.GUIDE_TABLE_CELL_CLR)
                    ty = cur_y + (row_h - txt_surf.get_height()) // 2
                    surf.blit(txt_surf, (cx_pos + icon_sz + 4, ty))
                else:
                    txt_surf = self.table_font.render(
                        str(cell), True, settings.GUIDE_TABLE_CELL_CLR)
                    ty = cur_y + (row_h - txt_surf.get_height()) // 2
                    surf.blit(txt_surf, (cx_pos, ty))

            # Row border
            pygame.draw.line(surf, border_clr,
                             (text_x, cur_y + row_h),
                             (text_x + usable_width, cur_y + row_h), 1)
            cur_y += row_h

    def _layout_blocks(self, content, usable_width, bullet_indent,
                       bullet_marker_gap, line_spacing, paragraph_spacing,
                       heading_spacing_above, separator_v_pad):
        """Convert the content list into a list of measured layout blocks."""
        blocks = []
        bullet_marker_w = self.body_font.render('\u2022', True, (255, 255, 255)).get_width()
        bullet_text_w = usable_width - bullet_indent - bullet_marker_w - bullet_marker_gap

        for item in content:
            if isinstance(item, dict):
                if 'heading' in item:
                    surf = self.heading_font.render(item['heading'], True, settings.GUIDE_HEADING_CLR)
                    blocks.append({
                        'type': 'heading',
                        'surface': surf,
                        'height': heading_spacing_above + surf.get_height() + line_spacing,
                    })
                elif 'bullet' in item:
                    wrapped = self._wrap_text(item['bullet'], self.body_font, bullet_text_w)
                    line_surfs = [self.body_font.render(l, True, settings.GUIDE_BODY_TEXT_CLR) for l in wrapped]
                    h = sum(s.get_height() + line_spacing for s in line_surfs)
                    blocks.append({
                        'type': 'bullet',
                        'lines': line_surfs,
                        'height': h,
                    })
                elif 'note' in item:
                    # Amber callout box: mode cross-references and caveats.
                    pad_x = max(8, int(0.008 * settings.SCREEN_WIDTH))
                    pad_y = max(5, int(0.006 * settings.SCREEN_HEIGHT))
                    text_w = usable_width - pad_x * 2 - 6
                    wrapped = self._wrap_text(item['note'], self.small_body_font, text_w)
                    line_surfs = [self.small_body_font.render(l, True, (238, 216, 158))
                                  for l in wrapped]
                    text_h = sum(s.get_height() + line_spacing for s in line_surfs)
                    text_h = max(0, text_h - line_spacing)
                    box_h = text_h + pad_y * 2
                    blocks.append({
                        'type': 'note',
                        'lines': line_surfs,
                        'box_h': box_h,
                        'pad_x': pad_x,
                        'pad_y': pad_y,
                        'height': box_h + paragraph_spacing,
                    })
                elif 'separator' in item:
                    blocks.append({
                        'type': 'separator',
                        'height': separator_v_pad * 2 + 1,
                    })
                elif 'icon_text' in item:
                    icon_sz = self._icon_size_for_path(item['icon_text'])
                    icon_gap = settings.GUIDE_ICON_TEXT_GAP
                    text_w = usable_width - icon_sz - icon_gap
                    wrapped = self._wrap_text(item['text'], self.body_font, text_w)
                    line_surfs = [self.body_font.render(l, True, settings.GUIDE_BODY_TEXT_CLR) for l in wrapped]
                    text_h = sum(s.get_height() + line_spacing for s in line_surfs)
                    total_h = max(icon_sz, text_h) + line_spacing
                    blocks.append({
                        'type': 'icon_text',
                        'icon_path': item['icon_text'],
                        'icon_size': icon_sz,
                        'lines': line_surfs,
                        'height': total_h,
                    })
                elif 'icon_bullet' in item:
                    icon_sz = self._icon_size_for_path(item['icon_bullet'])
                    icon_gap = settings.GUIDE_ICON_TEXT_GAP
                    text_w = usable_width - bullet_indent - icon_sz - icon_gap
                    wrapped = self._wrap_text(item['text'], self.body_font, text_w)
                    line_surfs = [self.body_font.render(l, True, settings.GUIDE_BODY_TEXT_CLR) for l in wrapped]
                    text_h = sum(s.get_height() + line_spacing for s in line_surfs)
                    total_h = max(icon_sz, text_h) + line_spacing
                    blocks.append({
                        'type': 'icon_bullet',
                        'icon_path': item['icon_bullet'],
                        'icon_size': icon_sz,
                        'lines': line_surfs,
                        'height': total_h,
                    })
                elif 'table' in item:
                    table_data = item['table']
                    headers = table_data.get('headers', [])
                    rows = table_data.get('rows', [])
                    # Auto-detect whether any cell uses a large icon
                    has_large_icon = False
                    for row in rows:
                        for cell in row:
                            if isinstance(cell, tuple) and len(cell) == 2:
                                if not any(cell[0].startswith(p)
                                           for p in self._SMALL_ICON_PREFIXES):
                                    has_large_icon = True
                                    break
                        if has_large_icon:
                            break
                    row_h = (settings.GUIDE_TABLE_ROW_H_LARGE
                             if has_large_icon else settings.GUIDE_TABLE_ROW_H)
                    tbl_icon_sz = (settings.GUIDE_TABLE_ICON_SIZE_LARGE
                                   if has_large_icon
                                   else settings.GUIDE_TABLE_ICON_SIZE)
                    num_rows = len(rows) + (1 if headers else 0)
                    total_h = row_h * num_rows + separator_v_pad * 2
                    blocks.append({
                        'type': 'table',
                        'headers': headers,
                        'rows': rows,
                        'col_widths': table_data.get('col_widths', None),
                        'height': total_h,
                        'usable_width': usable_width,
                        'row_h': row_h,
                        'icon_size': tbl_icon_sz,
                    })
                elif 'image' in item:
                    img = self._load_image(
                        item['image'],
                        max_width=item.get('max_width', settings.GUIDE_IMAGE_MAX_W),
                        max_height=item.get('max_height', None))
                    v_pad = settings.GUIDE_IMAGE_V_PAD
                    blocks.append({
                        'type': 'image',
                        'surface': img,
                        'height': img.get_height() + v_pad * 2,
                    })
            elif item == '':
                blocks.append({
                    'type': 'blank',
                    'height': paragraph_spacing,
                })
            else:
                wrapped = self._wrap_text(item, self.body_font, usable_width)
                line_surfs = [self.body_font.render(l, True, settings.GUIDE_BODY_TEXT_CLR) for l in wrapped]
                h = sum(s.get_height() + line_spacing for s in line_surfs)
                blocks.append({
                    'type': 'paragraph',
                    'lines': line_surfs,
                    'height': h,
                })

        return blocks

    @staticmethod
    def _wrap_text(text, font, max_width):
        """Word-wrap *text* to fit within *max_width* pixels."""
        words = text.split()
        lines = []
        current = ''
        for word in words:
            test = f'{current} {word}'.strip()
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or ['']

    # ════════════════════════════════════════════════════════════════════
    #  Section switching
    # ════════════════════════════════════════════════════════════════════

    def _select_section(self, index):
        """Switch to a different guide-book section."""
        if index == self.current_section:
            return
        from utils import sound
        sound.play('ui_click')
        self.current_section = index
        self.scroll_offset = 0
        self._render_section()
        self._section_shown_ms = pygame.time.get_ticks()

    # ════════════════════════════════════════════════════════════════════
    #  Embedding (menu Guide overlay)
    # ════════════════════════════════════════════════════════════════════

    def embed_into(self, area):
        """Re-position sidebar/content/scrollbar to fit inside *area*.

        Used by the menu Guide overlay's Rulebook tab, where the book is
        drawn inside the overlay panel instead of the in-game sub-screen.
        Draw with ``draw_embedded()`` afterwards (skips the sub-screen
        background) while ``handle_events()`` keeps working as usual.
        """
        gap = max(10, int(0.010 * settings.SCREEN_WIDTH))
        scroll_gap = max(4, int(0.004 * settings.SCREEN_WIDTH))
        self.scrollbar_w = max(4, int(0.006 * settings.SCREEN_WIDTH))

        self.sidebar_x = area.x
        self.sidebar_y = area.y
        self.sidebar_w = min(settings.GUIDE_SIDEBAR_W, int(area.w * 0.26))
        self.sidebar_h = area.h
        # _build_menu_rects() fits item heights to the new sidebar height.

        self.content_x = self.sidebar_x + self.sidebar_w + gap
        self.content_y = area.y
        self.content_w = area.right - self.content_x - scroll_gap - self.scrollbar_w
        self.content_h = area.h

        self.scrollbar_x = self.content_x + self.content_w + scroll_gap
        self.scrollbar_y = self.content_y
        self.scrollbar_h = self.content_h
        self.scrollbar_rect = pygame.Rect(
            self.scrollbar_x, self.scrollbar_y, self.scrollbar_w, self.scrollbar_h)
        self.handle_rect = pygame.Rect(
            self.scrollbar_x, self.scrollbar_y, self.scrollbar_w, 40)

        self.scroll_offset = 0
        self._render_section()
        self._build_menu_rects()

    def draw_embedded(self):
        """Draw sidebar + content + scrollbar only (no sub-screen chrome)."""
        self._draw_sidebar()
        self._draw_content()
        self._draw_scrollbar()

    # ════════════════════════════════════════════════════════════════════
    #  Scrollbar helpers
    # ════════════════════════════════════════════════════════════════════

    @property
    def _max_scroll(self):
        return max(0, self._rendered_height - self._visible_body_h)

    def _clamp_scroll(self):
        self.scroll_offset = max(0, min(self.scroll_offset, self._max_scroll))

    def _update_scrollbar_handle(self):
        """Recalculate handle size and position from current scroll offset."""
        if self._rendered_height <= self._visible_body_h:
            self.handle_rect.height = 0
            return

        visible_ratio = self._visible_body_h / self._rendered_height
        handle_h = max(int(self.scrollbar_h * visible_ratio), settings.GUIDE_SCROLLBAR_MIN_HANDLE)
        max_scroll = self._max_scroll
        ratio = self.scroll_offset / max_scroll if max_scroll > 0 else 0
        handle_y = self.scrollbar_y + ratio * (self.scrollbar_h - handle_h)
        self.handle_rect.update(self.scrollbar_x, int(handle_y), self.scrollbar_w, handle_h)

    # ════════════════════════════════════════════════════════════════════
    #  Events
    # ════════════════════════════════════════════════════════════════════

    def handle_events(self, events):
        super().handle_events(events)
        for event in events:
            if event.type == MOUSEBUTTONDOWN and event.button == 1:
                # Sidebar click?
                for i, rect in enumerate(self.menu_rects):
                    if rect.collidepoint(event.pos):
                        self._select_section(i)
                        break
                # Scrollbar handle drag start?
                if self.handle_rect.height > 0 and self.handle_rect.collidepoint(event.pos):
                    self.dragging = True
                    self.scrollbar_handle_color = settings.GUIDE_SCROLLBAR_HANDLE_A
                else:
                    # Touch-drag scroll start in content area
                    content_rect = pygame.Rect(self.content_x, self.content_y,
                                               self.content_w, self.content_h)
                    if content_rect.collidepoint(event.pos):
                        self._touch_scrolling = True
                        self._touch_last_y = event.pos[1]

            elif event.type == MOUSEBUTTONUP:
                if self.dragging:
                    self.dragging = False
                    self.scrollbar_handle_color = settings.GUIDE_SCROLLBAR_HANDLE_P
                self._touch_scrolling = False

            elif event.type == MOUSEMOTION:
                if self.dragging:
                    self._handle_scrollbar_drag(event)
                elif getattr(self, '_touch_scrolling', False):
                    # Touch-drag vertical scrolling
                    dy = event.pos[1] - self._touch_last_y
                    self._touch_last_y = event.pos[1]
                    self.scroll_offset -= dy
                    self._clamp_scroll()

            elif event.type == MOUSEWHEEL:
                # Only scroll when mouse is over the content area or scrollbar
                mx, my = pygame.mouse.get_pos()
                content_rect = pygame.Rect(self.content_x, self.content_y,
                                           self.content_w, self.content_h)
                if content_rect.collidepoint(mx, my) or self.scrollbar_rect.collidepoint(mx, my):
                    self.scroll_offset -= event.y * settings.GUIDE_SCROLL_SPEED
                    self._clamp_scroll()

    def _handle_scrollbar_drag(self, event):
        """Translate handle drag into a scroll offset."""
        handle_h = self.handle_rect.height
        y_min = self.scrollbar_y
        y_max = self.scrollbar_y + self.scrollbar_h - handle_h
        if y_max <= y_min:
            return
        clamped_y = max(y_min, min(y_max, event.pos[1] - handle_h // 2))
        ratio = (clamped_y - y_min) / (y_max - y_min)
        self.scroll_offset = int(ratio * self._max_scroll)
        self._clamp_scroll()

    # ════════════════════════════════════════════════════════════════════
    #  Update
    # ════════════════════════════════════════════════════════════════════

    def update(self, game):
        super().update(game)
        self.game = game

    # ════════════════════════════════════════════════════════════════════
    #  Drawing
    # ════════════════════════════════════════════════════════════════════

    def draw(self):
        super().draw()
        self._draw_sidebar()
        self._draw_content()
        self._draw_scrollbar()

    def _draw_sidebar(self):
        """Draw the section menu on the left."""
        # Semi-transparent sidebar background
        bg = pygame.Surface((self.sidebar_w, self.sidebar_h), pygame.SRCALPHA)
        bg.fill(settings.GUIDE_SIDEBAR_BG)
        self.window.blit(bg, (self.sidebar_x, self.sidebar_y))

        # Decorative border
        pygame.draw.rect(self.window, settings.GUIDE_BORDER_CLR,
                         (self.sidebar_x, self.sidebar_y, self.sidebar_w, self.sidebar_h), 2)

        # Group headers: small-caps label with a thin rule filling the row.
        text_x = settings.GUIDE_MENU_TEXT_X
        for label, rect in getattr(self, '_sidebar_group_rows', []):
            surf = self.small_body_font.render(label.upper(), True,
                                               settings.GUIDE_BULLET_CLR)
            ly = rect.centery - surf.get_height() // 2 + 2
            self.window.blit(surf, (rect.x + text_x, ly))
            rule_x = rect.x + text_x + surf.get_width() + 8
            rule_end = rect.right - text_x
            if rule_end > rule_x:
                pygame.draw.line(self.window, settings.GUIDE_SEPARATOR_CLR,
                                 (rule_x, rect.centery + 2),
                                 (rule_end, rect.centery + 2), 1)

        mouse_pos = pygame.mouse.get_pos()
        for i, rect in enumerate(self.menu_rects):
            is_active = (i == self.current_section)
            is_hovered = rect.collidepoint(mouse_pos) and not is_active

            # Item background
            if is_active:
                item_bg = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                item_bg.fill(settings.GUIDE_SIDEBAR_ITEM_ACTIVE)
                self.window.blit(item_bg, rect.topleft)
            elif is_hovered:
                item_bg = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                item_bg.fill(settings.GUIDE_SIDEBAR_ITEM_HOVER)
                self.window.blit(item_bg, rect.topleft)

            # Item text
            font = self.menu_font_active if is_active else self.menu_font
            clr = settings.GUIDE_MENU_TEXT_ACTIVE if is_active else settings.GUIDE_MENU_TEXT_CLR
            label = font.render(self.sections[i]['title'], True, clr)
            lx = rect.x + settings.GUIDE_MENU_TEXT_X
            ly = rect.centery - label.get_height() // 2
            self.window.blit(label, (lx, ly))

    def _draw_content(self):
        """Draw the scrollable content area for the active section."""
        if self._rendered_content is None:
            return

        # Subtle darkened background for readability
        bg = pygame.Surface((self.content_w, self.content_h), pygame.SRCALPHA)
        bg.fill(settings.GUIDE_CONTENT_BG)
        self.window.blit(bg, (self.content_x, self.content_y))

        # Decorative border
        pygame.draw.rect(self.window, settings.GUIDE_BORDER_CLR,
                         (self.content_x, self.content_y, self.content_w, self.content_h), 2)

        # Section title at the top of the content area
        section = self.sections[self.current_section]
        title_surf = self.section_title_font.render(section['title'], True, settings.GUIDE_SECTION_TITLE_CLR)
        title_x = self.content_x + (self.content_w - title_surf.get_width()) // 2
        title_y = self.content_y + settings.GUIDE_TITLE_TOP_PAD
        self.window.blit(title_surf, (title_x, title_y))
        self._draw_mode_chip(section, title_y, title_surf.get_height())

        # Clipping region for scrollable body (below the title)
        body_top = title_y + title_surf.get_height() + settings.GUIDE_TITLE_BOTTOM_PAD
        body_height = self.content_h - (body_top - self.content_y) - settings.GUIDE_BODY_BOTTOM_PAD

        clip_rect = pygame.Rect(self.content_x, body_top, self.content_w, body_height)
        old_clip = self.window.get_clip()
        self.window.set_clip(clip_rect)

        # Blit pre-rendered content with scroll offset. A freshly-selected
        # section fades in over 150ms (near-free: content is pre-rendered).
        shown_ms = getattr(self, '_section_shown_ms', 0)
        elapsed = pygame.time.get_ticks() - shown_ms if shown_ms else 999
        if elapsed < 150:
            from game.components.easing import ease_out_cubic
            self._rendered_content.set_alpha(
                int(70 + 185 * ease_out_cubic(elapsed / 150.0)))
        else:
            self._rendered_content.set_alpha(255)
        self.window.blit(self._rendered_content,
                         (self.content_x, body_top - self.scroll_offset))

        self.window.set_clip(old_clip)

    # Mode chip styling: (label, border colour, text colour)
    _MODE_CHIPS = {
        'both':     ('CONQUEST & DUELS', (150, 126, 74),  (210, 196, 158)),
        'conquest': ('CONQUEST',         (128, 168, 96),  (186, 218, 156)),
        'duel':     ('DUELS',            (196, 152, 82),  (240, 206, 138)),
    }

    def _draw_mode_chip(self, section, title_y, title_h):
        """Small tag in the content header telling which mode a chapter covers."""
        chip = self._MODE_CHIPS.get(section.get('mode'))
        if not chip:
            return
        label, border_clr, text_clr = chip
        txt = self.small_body_font.render(label, True, text_clr)
        pad_x = max(6, int(0.005 * settings.SCREEN_WIDTH))
        chip_h = txt.get_height() + 6
        chip_w = txt.get_width() + pad_x * 2
        rect = pygame.Rect(
            self.content_x + self.content_w - chip_w - int(0.012 * settings.SCREEN_WIDTH),
            title_y + (title_h - chip_h) // 2,
            chip_w, chip_h)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (0, 0, 0, 70), bg.get_rect(), border_radius=chip_h // 2)
        self.window.blit(bg, rect.topleft)
        pygame.draw.rect(self.window, border_clr, rect, 1, border_radius=chip_h // 2)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_scrollbar(self):
        """Draw the scrollbar track and handle."""
        self._update_scrollbar_handle()
        if self.handle_rect.height <= 0:
            return  # nothing to scroll

        # Track
        pygame.draw.rect(self.window, settings.GUIDE_SCROLLBAR_TRACK, self.scrollbar_rect)
        # Handle
        pygame.draw.rect(self.window, self.scrollbar_handle_color, self.handle_rect)
