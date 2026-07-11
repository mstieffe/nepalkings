# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import math
import pygame
from pygame.locals import *
from game.screens.screen import Screen
from config import settings
from config.screen_settings import _UI_SCALE
#from game.components.card_img import CardImg
from game.components.cards.hand import Hand
from game.components.coach_card import draw_coach_button, draw_coach_panel
from game.components.info_scroll import InfoScroll
from game.components.scoreboard_scroll import ScoreboardScroll
from game.components.buttons.state_button import StateButton
from utils.utils import GameButton
from utils import onboarding_service
from game.screens.build_figure_screen import BuildFigureScreen
from game.screens.log_screen import LogScreen
from game.screens.field_screen import FieldScreen
from game.screens.cast_spell_screen import CastSpellScreen
from game.screens.guide_book_screen import GuideBookScreen
from game.screens.battle_screen import BattleScreen
from game.screens.battle_shop_screen import BattleShopScreen
from game.components.figures.figure_manager import FigureManager
from game.components.conquer_effects import EffectsLayer, apply_screen_shake
from utils.background_poller import BackgroundPoller
from game.core.game import Game
import logging
from datetime import datetime

logger = logging.getLogger('nk.screens.game_screen')



class GameScreen(Screen):
    def __init__(self, state, progress_callback=None):
        super().__init__(state)
        _report = progress_callback or (lambda f, l=None: None)
        
        # Store reference to game_screen in state for button access
        self.state.parent_screen = self

        # Track current (game_id, player_id) to detect game/user switches
        self._current_game_key = None

        # ── Background game-state poller (non-blocking) ────────
        self._game_poller = None  # Created on first update_game()
        self._poller_data_version = 0  # _game_data_version when poll started
        self.update_interval = 2000  # ms between polls (remote-friendly)

        # Unread chat message tracking
        self._last_seen_chat_count = 0
        self._badge_font = settings.get_font(int(0.015 * settings.SCREEN_HEIGHT * _UI_SCALE))

        # Field & battle badge tracking
        self._field_unseen_count = 0
        self._last_seen_figure_ids = None    # set of figure IDs when player last viewed field
        self._battle_unseen_count = 0
        self._last_seen_battle_round = None  # (battle_round, battle_turn_player_id) snapshot
        self.scoreboard_scroll = None
        self.resource_scroll = None
        self.turn_button = None
        self.invader_button = None
        self.ceasefire_button = None

        _report(0.05, 'Loading figures …')
        # Initialize figure manager
        self.figure_manager = FigureManager()

        _report(0.12, 'Loading cards …')
        # Initialize hands for the game (main and side hands)
        self.main_hand = Hand(self.window, self.state, x=settings.MAIN_HAND_X, y=settings.MAIN_HAND_Y)
        self.side_hand = Hand(self.window, self.state, x=settings.SIDE_HAND_X, y=settings.SIDE_HAND_Y, type="side_card")

        _report(0.20, 'Loading buttons …')
        # Initialize buttons and add to the game_buttons list
        self.initialize_buttons()
        self.initialize_state_buttons()

        self.display_elements = []
        self.initialiaze_scoareboard_scroll()
        self.initialize_info_scroll()

        _report(0.30, 'Loading playing field …')
        # Define which screen is visible, allowing flexibility in switching between subscreens
        self.subscreens = {}
        self.subscreens['field'] = FieldScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Playing Board')

        _report(0.40, 'Loading figure builder …')
        self.subscreens['build_figure'] = BuildFigureScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Figure Builder')

        _report(0.50, 'Loading spell book …')
        self.subscreens['cast_spell'] = CastSpellScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Spell Book')

        _report(0.55, 'Loading log book …')
        self.subscreens['log'] = LogScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Log-Book')

        _report(0.60, 'Loading guide book …')
        self.subscreens['tutorial'] = GuideBookScreen(
            self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y,
            title='Guide Book', initial_section='Game Flow')

        _report(0.70, 'Loading battle arena …')
        self.subscreens['battle'] = BattleScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Battle Arena')

        _report(0.80, 'Loading battle shop …')
        self.subscreens['battle_shop'] = BattleShopScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Battle Shop')
        
        # Track previous subscreen to detect changes
        self.previous_subscreen = None
        
        # Queue for pending notifications (to avoid overwriting active dialogue boxes)
        self.pending_notifications = []
        self._active_dialogue_type = None  # Track the type of the currently-displayed dialogue
        
        # Counter spell state
        self.waiting_for_counter_response = False  # True when caster is waiting
        self.need_to_respond_to_spell = False  # True when defender needs to respond
        self.pending_spell_details = None  # Store spell details for counter
        self.counter_spell_selector = None  # Active counter spell selector UI
        self._cached_castable_spells = None  # Cached castable spells for current pending spell
        self._pending_spell_fetch_ready = False  # Flag: background fetch completed
        self._last_resolved_spell_id = None  # Guard: prevents stale polls from re-triggering
        
        _report(0.88, 'Loading spells …')
        # Pre-create SpellManager so spell images are loaded at startup, not on first counter-spell
        from game.components.spells.spell_manager import SpellManager
        self._cached_spell_manager = SpellManager()
        
        _report(0.94, 'Loading battle modifiers …')
        # Battle modifier icon cache (loaded once at init)
        self._battle_modifier_icons = {}
        self._load_battle_modifier_icons()
        self._previous_battle_modifiers = []  # Track for change detection / notifications
        self._just_allowed_spell = False  # Flag to suppress duplicate notification after allowing a spell
        self._hovered_battle_modifier = None  # Index of currently hovered modifier (or None)
        self._seen_conquer_opponent_spell_ids = set()  # Active opponent spell IDs already announced in conquer mode
        self._battle_modifier_font = settings.get_font(settings.GAME_BUTTON_FONT_SIZE)
        self._spell_box_title_font = settings.get_font(settings.BATTLE_SPELL_BOX_TITLE_FONT_SIZE, bold=True)
        self._tooltip_font = settings.get_font(settings.TOOLTIP_FONT_SIZE)
        self._duel_coach_font = settings.get_font(max(12, int(settings.FS_SMALL * 0.95)))
        self._duel_coach_title_font = settings.get_font(max(13, int(settings.FS_SMALL * 1.05)), bold=True)
        self._duel_coach_buttons = []
        self._duel_coach_step = None
        self._duel_coach_pressed_button_action = None

        # ── Duel effects layer (draw-only visual juice) ────────
        # ConquerGameScreen bypasses this __init__ and owns its own
        # _conquer_effects, so this layer exists only for duel games.
        self._fx = EffectsLayer(self.window, self._lookup_duel_figure_rect)
        self._battle_unlock_prev_locked = True

    def _lookup_duel_figure_rect(self, figure_id):
        """Return the on-screen rect of ``figure_id`` or ``None`` (fail-soft).

        Anchors effects to field figure icons while the field tab is open;
        on any other subscreen the effect falls back to its anchor-free
        rendering (banner instead of projectile, etc.).
        """
        if figure_id is None:
            return None
        if getattr(self.state, 'subscreen', None) != 'field':
            return None
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        if field is None:
            return None
        icon = (getattr(field, 'icon_cache', None) or {}).get(figure_id)
        if icon is None:
            for candidate in getattr(field, 'figure_icons', None) or []:
                if getattr(getattr(candidate, 'figure', None), 'id', None) == figure_id:
                    icon = candidate
                    break
        if icon is None:
            return None
        rect = getattr(icon, 'rect_frame', None) or getattr(icon, 'rect_icon', None)
        if rect is not None:
            return pygame.Rect(rect)
        x = getattr(icon, 'x', None)
        y = getattr(icon, 'y', None)
        if x is not None and y is not None:
            return pygame.Rect(int(x) - 24, int(y) - 24, 48, 48)
        return None

    def _draw_subscreen_switch_veil(self):
        """160ms fade-in veil over a freshly-switched subscreen.

        Draw-only — never touches handle_events, so the phase gates'
        programmatic tab switches simply trigger the same fade.
        """
        switched_at = getattr(self, '_subscreen_switched_at', 0)
        if not switched_at:
            return
        elapsed = pygame.time.get_ticks() - switched_at
        if elapsed >= 160:
            return
        from game.components.easing import ease_out_cubic
        alpha = int(110 * (1.0 - ease_out_cubic(elapsed / 160.0)))
        if alpha <= 0:
            return
        veil = getattr(self, '_subscreen_veil_surface', None)
        if veil is None:
            veil = pygame.Surface(
                (settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH,
                 settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT))
            veil.fill(settings.BACKGROUND_COLOR)
            self._subscreen_veil_surface = veil
        veil.set_alpha(alpha)
        self.window.blit(veil, (settings.SUB_SCREEN_X, settings.SUB_SCREEN_Y))

    def _pump_battle_unlock_pulse(self):
        """One-shot pulse + sound when the battle tab flips locked → unlocked.

        Edge-detected per frame so it covers every unlock site (battle-ready
        check, navigation enforcement, battle-moves phase, ...) without
        touching them individually.
        """
        locked = bool(getattr(self.battle_button, 'locked', True))
        was_locked = self._battle_unlock_prev_locked
        self._battle_unlock_prev_locked = locked
        if not was_locked or locked:
            return
        rect = getattr(self.battle_button, 'rect_hit', None)
        if rect is not None:
            self._fx.spawn_rect_pulse(pygame.Rect(rect), (238, 206, 130),
                                      duration_ms=700, scale=1.2)
        from utils import sound
        sound.play('battle_start', volume=0.5)

    def on_enter(self):
        """Mark this screen as the active game parent for shared subscreens."""
        self.state.parent_screen = self
        if not self._ensure_duel_screen_game():
            return
        # Figure entrance: the field figures cascade in whenever the game
        # screen is (re)entered — same welcome-in moment as conquer.
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        if field is not None and hasattr(field, 'begin_figure_entrance_cascade'):
            try:
                field.begin_figure_entrance_cascade()
            except Exception:
                pass

    def _ensure_duel_screen_game(self):
        """Route conquer battles to their dedicated parent screen."""
        if self.state.game and getattr(self.state.game, 'mode', 'duel') == 'conquer':
            self.state.screen = 'conquer_game'
            return False
        return True
    
    # Notification dict keys consumed by routing/dedup/tone logic rather than by
    # the DialogueBox itself. Stripped before forwarding to make_dialogue_box so
    # callers can attach metadata without crashing the dialogue constructor.
    _NOTIFICATION_META_KEYS = (
        'type', 'event_key', 'phase', 'tone', 'spell_names',
        'force_modal', 'target_tab', 'no_gate', 'spell_side', 'spell_role',
    )

    def make_dialogue_box(self, message, actions=None, images=None, icon=None, title="", auto_close_delay=None, message_after_images=None):
        """Create a dialogue box with specified message, actions, images, and icon."""
        from game.components.dialogue_box import DialogueBox
        from utils import sound
        sound.play_for_dialogue(title)
        self._active_dialogue_type = None  # Clear — callers via queue_or_show set it after
        self.dialogue_box = DialogueBox(self.window, message, actions=actions, images=images, icon=icon, title=title, auto_close_delay=auto_close_delay, message_after_images=message_after_images)

    def _consume_notification_meta(self, notification_data):
        """Split notification meta keys from dialogue-box kwargs.

        Returns ``(dialogue_kwargs, dialogue_type)``. Unknown meta keys are
        dropped silently so callers can attach routing/dedup hints (`phase`,
        `tone`, `event_key`, ...) without crashing make_dialogue_box.
        """
        data = dict(notification_data)
        dialogue_type = data.pop('type', None)
        for key in self._NOTIFICATION_META_KEYS:
            data.pop(key, None)
        return data, dialogue_type

    def queue_or_show_notification(self, notification_data):
        """Queue a notification if dialogue box is active, otherwise show it immediately."""
        if self.dialogue_box:
            # Dialogue box already showing - add to queue
            self.pending_notifications.append(notification_data)
        else:
            # No dialogue box - show immediately
            data, dialogue_type = self._consume_notification_meta(notification_data)
            self.make_dialogue_box(**data)
            self._active_dialogue_type = dialogue_type

    def show_next_queued_notification(self):
        """Show the next queued notification if any exist."""
        if self.pending_notifications:
            notification_data = self.pending_notifications.pop(0)
            data, dialogue_type = self._consume_notification_meta(notification_data)
            self.make_dialogue_box(**data)
            self._active_dialogue_type = dialogue_type
        else:
            self._active_dialogue_type = None

    def initialiaze_scoareboard_scroll(self):
        """Initialize resources for the info scroll."""

        scoreboard_scroll = ScoreboardScroll(
            self.window, 
            self.state.game,
            settings.SCOREBOARD_SCROLL_X, 
            settings.SCOREBOARD_SCROLL_Y, 
            settings.SCOREBOARD_SCROLL_WIDTH, 
            settings.SCOREBOARD_SCROLL_HEIGHT, 
            settings.SCOREBOARD_SCROLL_BG_IMG_PATH)
        self.scoreboard_scroll = scoreboard_scroll
        self.display_elements.append(scoreboard_scroll)


    def initialize_info_scroll(self):
        """Initialize merged info scroll with resources and slots (excluding castle)."""
        info_data = [
            {'element': 'village',  'icon_img': settings.RESOURCE_ICON_IMG_PATH_DICT['villager_red_black'], 'red': '0/0', 'black': '0/0', 'red_deficit': False, 'black_deficit': False},
            {'element': 'military', 'icon_img': settings.RESOURCE_ICON_IMG_PATH_DICT['warrior_red_black'],  'red': '0/0', 'black': '0/0', 'red_deficit': False, 'black_deficit': False},
            {'element': 'food',     'icon_img': settings.RESOURCE_ICON_IMG_PATH_DICT['rice_meat'],          'red': '0/0', 'black': '0/0', 'red_deficit': False, 'black_deficit': False},
            {'element': 'material', 'icon_img': settings.RESOURCE_ICON_IMG_PATH_DICT['wood_stone'],         'red': '0/0', 'black': '0/0', 'red_deficit': False, 'black_deficit': False},
            {'element': 'amor',     'icon_img': settings.RESOURCE_ICON_IMG_PATH_DICT['sword_shield'],       'red': '0/0', 'black': '0/0', 'red_deficit': False, 'black_deficit': False},
        ]
        info_scroll = InfoScroll(
            self.window,
            settings.INFO_SCROLL_X,
            settings.INFO_SCROLL_Y,
            settings.INFO_SCROLL_WIDTH,
            settings.INFO_SCROLL_HEIGHT,
            'Resources',
            info_data,
            settings.INFO_SCROLL_BG_IMG_PATH)
        self.resource_scroll = info_scroll
        self.display_elements.append(info_scroll)

    def initialize_state_buttons(self):
        """Initialize state buttons for the game screen."""

        # Add state buttons for the game screen
        self.turn_button = StateButton(
            self.window, 
            'turn_tracker', 
            'turn', 
            settings.STATE_BUTTON_TURN_X, 
            settings.STATE_BUTTON_TURN_Y, 
            settings.STATE_BUTTON_SYMBOL_WIDTH, 
            settings.STATE_BUTTON_GLOW_WIDTH, 
            state=self.state, 
            hover_text_active='it is your turn!',
            hover_text_passive='not your turn!',
            track_turn = True
        )
        self.game_buttons.append(self.turn_button)

        # Add state buttons for the game screen
        self.invader_button = StateButton(
            self.window, 
            'invader_tracker', 
            'invader', 
            settings.STATE_BUTTON_INVADER_X, 
            settings.STATE_BUTTON_INVADER_Y, 
            settings.STATE_BUTTON_SYMBOL_WIDTH, 
            settings.STATE_BUTTON_GLOW_WIDTH, 
            state=self.state, 
            hover_text_active='you are the defender!',
            hover_text_passive='you are the invader!',
            track_invader = True
        )
        self.game_buttons.append(self.invader_button)

        # Add ceasefire state button
        self.ceasefire_button = StateButton(
            self.window, 
            'ceasefire_tracker', 
            'ceasefire', 
            settings.STATE_BUTTON_CEASEFIRE_X, 
            settings.STATE_BUTTON_CEASEFIRE_Y, 
            settings.STATE_BUTTON_SYMBOL_WIDTH, 
            settings.STATE_BUTTON_GLOW_WIDTH, 
            state=self.state, 
            hover_text_active='ceasefire active - battles blocked!',
            hover_text_passive='battles are allowed!',
            track_ceasefire = True
        )
        self.game_buttons.append(self.ceasefire_button)

    def initialize_buttons(self):
        """Initialize buttons for the game screen, including hand and action buttons."""
        #self.game_buttons = []

        # Add buttons from both hands (main and side hand buttons)
        self.game_buttons.extend(self.main_hand.buttons)
        self.game_buttons.extend(self.side_hand.buttons)

        home_button = GameButton(
            self.window, 
            'home',
            'home', 
            'plain',
            settings.HOME_BUTTON_X, settings.HOME_BUTTON_Y,
            settings.HOME_BUTTON_WIDTH,
            settings.HOME_BUTTON_WIDTH,
            glow_width=settings.HOME_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.HOME_BUTTON_WIDTH_BIG,
            glow_width_big=settings.HOME_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='home menu',
            screen='game_menu',
            track_turn = False,
            tooltip_anchor='top-left'
        )
        self.game_buttons.append(home_button)

        # Tutorial button (switches to the tutorial subscreen)
        tutorial_button = GameButton(
            self.window, 
            'view_tutorial',
            'tutorial', 
            'plain',
            settings.TUTORIAL_BUTTON_X, settings.TUTORIAL_BUTTON_Y,
            settings.TUTORIAL_BUTTON_WIDTH,
            settings.TUTORIAL_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.TUTORIAL_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='guide book',
            subscreen='tutorial',
            track_turn = False,
            tooltip_anchor='top-left'
        )
        self.game_buttons.append(tutorial_button)

        # Log button (switches to the log subscreen)
        self.log_button = GameButton(
            self.window, 
            'view_log',
            'letter', 
            'plain',
            settings.LETTER_BUTTON_X, settings.LETTER_BUTTON_Y,
            settings.LETTER_BUTTON_WIDTH,
            settings.LETTER_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.LETTER_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='log book',
            subscreen='log',
            track_turn = False,
            tooltip_anchor='top-left'
        )
        self.game_buttons.append(self.log_button)

        # Field button (switches to the field subscreen)
        self.field_button = GameButton(
            self.window, 
            'view_field',
            'map', 
            'plain',
            settings.FIELD_BUTTON_X, settings.FIELD_BUTTON_Y,
            settings.FIELD_BUTTON_WIDTH,
            settings.FIELD_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.FIELD_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='playing board',
            subscreen='field',
            track_turn = False,
            tooltip_anchor='top-left'
        )

        # Action button (for casting spells)
        self.cast_spell_button = GameButton(
            self.window, 
            'cast_spell',
            'book', 
            'plant',
            settings.ACTION_BUTTON_X, settings.ACTION_BUTTON_Y,
            settings.ACTION_BUTTON_WIDTH,
            settings.ACTION_BUTTON_WIDTH,
            state=self.state,
            hover_text='cast spell!',
            subscreen='cast_spell'
        )
        self.game_buttons.append(self.cast_spell_button)

        # Build figure button (switches to the build figure subscreen)
        self.build_button = GameButton(
            self.window, 
            'build_figure',
            'hammer', 
            'rope',
            settings.BUILD_BUTTON_X, settings.BUILD_BUTTON_Y,
            settings.BUILD_BUTTON_WIDTH,
            settings.BUILD_BUTTON_WIDTH,
            state=self.state,
            hover_text='build figure',
            subscreen='build_figure'
        )
        self.game_buttons.append(self.build_button)


        self.game_buttons.append(self.field_button)


        # Battle button (switches to the battle subscreen)
        # Inactive during normal round, only becomes active in battle phase
        self.battle_button = GameButton(
            self.window, 
            'view_battle',
            'battle', 
            'plain',
            settings.BATTLE_BUTTON_X, settings.BATTLE_BUTTON_Y,
            settings.BATTLE_BUTTON_WIDTH,
            settings.BATTLE_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.BATTLE_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='battle arena',
            subscreen='battle',
            track_turn = False,
            locked = True,
            tooltip_anchor='top-left'
        )
        self.game_buttons.append(self.battle_button)

        # Battle shop button (switches to the battle shop subscreen)
        self.battle_shop_button = GameButton(
            self.window, 
            'view_battle_shop',
            'battleshop', 
            'plain',
            settings.BATTLE_SHOP_BUTTON_X, settings.BATTLE_SHOP_BUTTON_Y,
            settings.BATTLE_SHOP_BUTTON_WIDTH,
            settings.BATTLE_SHOP_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.BATTLE_SHOP_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='battle shop',
            subscreen='battle_shop',
            track_turn = False,
            tooltip_anchor='top-left'
        )
        self.game_buttons.append(self.battle_shop_button)



    def _consume_game_poll_result(self):
        """Apply the full game poller's pending result, if any.

        A result is only applied when no action response updated the game
        while the poll was in flight (version race) — otherwise the stale
        poll would clobber the newer state. A discarded result must also
        invalidate the poller's unchanged-body signature: that short-circuit
        assumes every delivered result was consumed, and without the
        invalidation an idle server (identical response bodies) would never
        re-deliver the dropped state — the conquer pre-battle flow then
        stalls forever on a stale `game.turn` (production game 140).
        """
        poller = self._game_poller
        if poller is None or not poller.has_result():
            return
        result = poller.result
        if self._poller_data_version == self.state.game._game_data_version:
            self.state.game.apply_server_data(result)
        else:
            logger.warning(
                f"[POLLER] Discarding stale result (poll v{self._poller_data_version} "
                f"vs current v{self.state.game._game_data_version})")
            poller.invalidate_cache()

    def update_game(self):
        """Update the game state and related components."""
        # Check if game exists (may be None after logout)
        if not self.state.game:
            return

        # Drain any in-flight async start_turn responses (web path).
        # Cheap no-op on desktop and when nothing is pending; without this
        # the conquer battle UI would either block on a sync POST or never
        # see the response.
        try:
            self.state.game.drain_pending_start_turn()
        except Exception:
            pass
        
        # Detect game or user switch — reset stale state
        current_id = getattr(self.state.game, 'game_id', None)
        current_pid = getattr(self.state.game, 'player_id', None)
        current_key = (current_id, current_pid)
        if current_key != self._current_game_key:
            self._reset_game_screen_state()
            self._current_game_key = current_key
            # Recreate poller for the new game
            self._game_poller = BackgroundPoller(
                Game.fetch_server_data, args=(current_id,))
            self._poller_data_version = getattr(self.state.game, '_game_data_version', 0)
        
        # Check if subscreen changed - if so, deselect all cards
        if self.previous_subscreen != self.state.subscreen:
            self.main_hand.deselect_all_cards()
            self.side_hand.deselect_all_cards()
            # Re-lock the battle button when leaving battle/battle_shop
            # BUT keep it unlocked during an active battle phase or battle moves selection
            if self.previous_subscreen in ('battle', 'battle_shop') and self.state.subscreen == 'field':
                if (not getattr(self.state.game, 'in_battle_phase', False) and
                        not getattr(self.state.game, 'battle_moves_phase', False)):
                    self.battle_button.locked = True
            # Mark chats as read when opening the log screen
            if self.state.subscreen == 'log' and self.state.game and self.state.game.chat_messages:
                self._last_seen_chat_count = len(self.state.game.chat_messages)
            # Clear field badge when switching to field
            if self.state.subscreen == 'field':
                self._field_unseen_count = 0
                self._last_seen_figure_ids = self._get_all_figure_ids()
            # Clear battle badge when switching to battle
            if self.state.subscreen == 'battle':
                self._battle_unseen_count = 0
                self._last_seen_battle_round = self._get_battle_snapshot()
            self.previous_subscreen = self.state.subscreen
        
        if self._try_handle_finished_conquer_game():
            return

        # ── Finished game: read-only mode — skip polling and notifications ──
        if self.state.game.game_over:
            pending_game_over = getattr(self.state.game, 'pending_game_over', None)
            if pending_game_over and not getattr(self.state.game, 'game_over_shown', False):
                subscreen = self.subscreens.get(self.state.subscreen) if self.state.subscreen in self.subscreens else None
                subscreen_dialogue_open = bool(getattr(subscreen, 'dialogue_box', None))
                if not subscreen_dialogue_open:
                    self.check_game_over()
            else:
                self.state.game.game_over_shown = True  # suppress loaded finished games without a result payload
            self.check_conquer_battle_ended()
            if not self.state.game:
                return  # conquer ended — game cleared

            # One-time figure fetch for lightweight games (e.g. from async poller)
            if not any(self.state.game.cached_figures_data.values()):
                from utils.figure_service import fetch_figures
                for player in self.state.game.players:
                    pid = player['id']
                    try:
                        self.state.game.cached_figures_data[pid] = fetch_figures(pid)
                    except Exception:
                        self.state.game.cached_figures_data[pid] = []
                self.state.game._figures_data_version += 1

            self.main_hand.update(self.state.game)
            self.side_hand.update(self.state.game)
            for elem in self.display_elements:
                if isinstance(elem, InfoScroll):
                    elem.update(self.state.game, families=self.figure_manager.families)
                else:
                    elem.update(self.state.game)
            return

        # Skip full server poll while defender is actively responding to counter spell
        # (they don't need fresh data while deciding, and the poll blocks the UI)
        if not self.need_to_respond_to_spell:
            # Non-blocking: kick off background fetch, apply when ready
            if self._game_poller is None:
                self._game_poller = BackgroundPoller(
                    Game.fetch_server_data,
                    args=(self.state.game.game_id,))
                self._poller_data_version = self.state.game._game_data_version
            self._consume_game_poll_result()
            if not self._game_poller.busy:
                self._poller_data_version = self.state.game._game_data_version
                self._game_poller.poll(
                    args=(self.state.game.game_id,))

        if self._try_handle_finished_conquer_game():
            return
        
        # ── Badge tracking (field & battle) ──
        self._update_field_badge()
        self._update_battle_badge()
        
        # ── Safety valve: auto-clear stale action lock ──
        self.state.game.check_action_lock_timeout()
        
        # Check for battle loot notification (which card the winner kept)
        self.check_loot_notification()
        
        # Check for opponent turn notification (includes Forced Deal and Dump Cards details)
        self.check_opponent_turn_notification()
        
        # Check for Infinite Hammer mode activation
        self.check_infinite_hammer_activation()
        
        # Check for battle modifier changes
        self.check_battle_modifier_changes()
        
        # Check for advance/battle state
        self.check_forced_advance()
        self.check_own_advance_notification()
        self.check_opponent_advance_notification()
        self.check_defender_selection_needed()
        self.check_conquer_own_defender_selection()
        self.check_waiting_for_defender_pick()
        self.check_battle_ready()
        
        # Check for fold outcome and auto-proceed (polling detection for waiting player)
        self.check_fold_result()
        self.check_pending_battle_choice_timeout()
        self.check_game_over()
        self.check_conquer_battle_ended()
        self.check_auto_proceed_to_battle()
        self.check_battle_moves_ready()
        
        # Reconnect: detect active battle on server that the client missed
        self.check_battle_reconnect()
        self._enforce_battle_navigation_state()
        
        # Check for ceasefire ended notification AFTER action results
        # so it appears after the success message of the action that caused it
        self.check_ceasefire_ended_notification()
        
        # Check for ceasefire active notification (new round start)
        # Queued after victory/defeat so it appears second
        self.check_ceasefire_active_notification()
        
        # Check for post-battle side card draw notification
        # so it appears after victory/defeat and ceasefire notifications
        self.check_post_battle_side_cards()
        
        # Check for auto-fill notification LAST among post-battle notifications
        # so it appears after victory/defeat, loot, ceasefire, and side cards
        self.check_auto_fill_notification()
        
        # Check for pending counter spell state
        self.check_counter_spell_state()
        
        self.main_hand.update(self.state.game)
        self.side_hand.update(self.state.game)
        
        # Check if player needs to discard cards due to exceeding max hand size
        # Only check if it's the player's turn, not in discard mode, and not in battle
        in_battle = (getattr(self.state.game, 'in_battle_phase', False)
                     or getattr(self.state.game, 'battle_confirmed', False)
                     or getattr(self.state.game, 'advancing_figure_id', None))
        if self.state.game.turn and not in_battle and not self.main_hand.discard_mode and not self.side_hand.discard_mode:
            if self.main_hand.needs_discard():
                excess = self.main_hand.get_excess_card_count()
                self.main_hand.start_discard_mode(excess)
            elif self.side_hand.needs_discard():
                excess = self.side_hand.get_excess_card_count()
                self.side_hand.start_discard_mode(excess)
        
        for elem in self.display_elements:
            # Pass families to info scroll for resource calculation
            if isinstance(elem, InfoScroll):
                elem.update(self.state.game, families=self.figure_manager.families)
            else:
                elem.update(self.state.game)

        # Keep marking chats as read while on the log screen
        if self.state.subscreen == 'log' and self.state.game and self.state.game.chat_messages:
            self._last_seen_chat_count = len(self.state.game.chat_messages)
    
    def _reset_game_screen_state(self):
        """Reset all transient game screen state when switching to a different game."""
        # Clear pending notifications and dialogue box
        self.pending_notifications = []
        self.dialogue_box = None
        self._active_dialogue_type = None
        
        # Reset counter spell state
        self.waiting_for_counter_response = False
        self.need_to_respond_to_spell = False
        self.pending_spell_details = None
        self.counter_spell_selector = None
        self._cached_castable_spells = None
        self._pending_spell_fetch_ready = False
        self._last_resolved_spell_id = None
        
        # Reset battle modifier tracking
        self._previous_battle_modifiers = []
        self._hovered_battle_modifier = None
        self._just_allowed_spell = False
        self._seen_conquer_opponent_spell_ids = set()
        self.state.pending_conquer_prelude_target = None
        
        # Clear queued notifications and stale advance/turn flags so
        # they don't replay after the fold/battle result dialogue.
        self.pending_notifications = []
        if self.state.game:
            self.state.game.pending_advance_notification = False
            self.state.game.pending_own_advance_notification = False
            self._clear_opponent_turn_summaries(self.state.game)
            self.state.game.pending_conquer_prelude_target = False
        
        # ── Reset ALL subscreens ──
        # Each subscreen has a reset_state() that clears its game-specific
        # transient state (pending actions, dialogue boxes, selections, etc.)
        for name, subscreen in self.subscreens.items():
            if hasattr(subscreen, 'reset_state'):
                subscreen.reset_state()
        
        # Reset waiting for defender pick state
        if self.state.game:
            self.state.game.pending_waiting_for_defender_pick = False
            self.state.game.waiting_for_defender_pick_shown = False
            self.state.game.pending_battle_ready = False
            self.state.game.battle_ready_shown = False
            # Reset Civil War second pick state
            self.state.game.civil_war_awaiting_second = False
            self.state.game.civil_war_defender_second = False
            self.state.game.civil_war_required_color = None
            # Reset fold/battle decision state
            self.state.game.waiting_for_battle_decision = False
            self.state.game.pending_fold_result = False
            self.state.game.fold_result_shown = False
            self.state.game.auto_proceed_to_battle = False
            # Reset battle moves phase state
            self.state.game.battle_moves_phase = False
            self.state.game.battle_moves_ready = False
            self.state.game.waiting_for_opponent_battle_moves = False
            self.state.game.both_battle_moves_ready = False
            # Reset active battle phase state
            self.state.game.in_battle_phase = False
            self.state.game.battle_turns_left = 0
        
        # Re-lock battle button
        self.battle_button.locked = True
        self._battle_unlock_prev_locked = True

        # Drop any in-flight effect animations from the previous game.
        # (getattr: this method is shared — ConquerGameScreen has no _fx.)
        fx = getattr(self, '_fx', None)
        if fx is not None:
            fx.clear()

        # Reset unread chat counter
        self._last_seen_chat_count = 0

        # Reset field & battle badge counters
        self._field_unseen_count = 0
        self._last_seen_figure_ids = None
        self._battle_unseen_count = 0
        self._last_seen_battle_round = None
        
        # Reset subscreen to default (field) so stale battle/shop view doesn't persist
        self.state.subscreen = 'field'
        
        # Reset subscreen tracking
        self.previous_subscreen = None
        
        # Reset hand discard mode
        if hasattr(self, 'main_hand'):
            self.main_hand.deselect_all_cards()
            if hasattr(self.main_hand, 'discard_mode'):
                self.main_hand.discard_mode = False
                self.main_hand.cards_to_discard_count = 0
                self.main_hand.dialogue_box = None
        if hasattr(self, 'side_hand'):
            self.side_hand.deselect_all_cards()
            if hasattr(self.side_hand, 'discard_mode'):
                self.side_hand.discard_mode = False
                self.side_hand.cards_to_discard_count = 0
                self.side_hand.dialogue_box = None
        
        logger.info(f"[GAME_SCREEN] State reset for new game {self._current_game_key}")

    def check_counter_spell_state(self):
        """Check if player needs to respond to counter spell or is waiting for opponent."""
        if not self.state.game:
            return
        
        # Check if this player needs to respond to a counterable spell
        if self.state.game.waiting_for_counter and not self.need_to_respond_to_spell:
            # Guard: ignore stale poll data for a spell we already resolved
            if self.state.game.pending_spell_id == self._last_resolved_spell_id:
                return
            # Player needs to respond - start background fetch (non-blocking)
            self.need_to_respond_to_spell = True
            self._fetch_pending_spell_async()
        
        # Show dialogue once background fetch completes (defender side)
        if self._pending_spell_fetch_ready and self.need_to_respond_to_spell and not self.dialogue_box:
            self._pending_spell_fetch_ready = False
            self._show_counter_spell_dialogue()
        
        # Check if player is waiting for opponent's response (caster side)
        if self.state.game.pending_spell_id and not self.state.game.waiting_for_counter and not self.waiting_for_counter_response:
            # Guard: ignore stale poll data for a spell we already resolved
            if self.state.game.pending_spell_id == self._last_resolved_spell_id:
                return
            # Player cast a counterable spell and is waiting
            self.waiting_for_counter_response = True
            
            # Fetch spell name for display in background
            self._fetch_pending_spell_async(is_caster=True)
        
        # Pick up caster spell name once fetch completes
        if self._pending_spell_fetch_ready and self.waiting_for_counter_response:
            self._pending_spell_fetch_ready = False
            self.pending_spell_name = self.pending_spell_details.get('spell_name', 'your spell') if self.pending_spell_details else 'your spell'
            self.pending_spell_family_name = self.pending_spell_details.get('spell_family_name', self.pending_spell_name) if self.pending_spell_details else self.pending_spell_name
            # Persistent prompt will be drawn in render() - no dialogue box
        
        # Clear waiting state when spell is resolved
        if not self.state.game.pending_spell_id:
            # NOTE: Do NOT clear _last_resolved_spell_id here.
            # On the web platform, stale poller results can arrive AFTER
            # update_from_dict() has already set pending_spell_id = None.
            # If we clear the guard now, the stale data will re-trigger the
            # counter-spell dialogue.  The guard persists until a new game
            # is loaded (_reset_game_screen_state) and uses unique spell IDs,
            # so it won't interfere with future spells.
            if self.waiting_for_counter_response:
                self.waiting_for_counter_response = False
                # Suppress the next turn summary — the caster already saw the
                # opponent's last action at the start of this turn; the spell
                # resolution triggers start_turn again but would re-show the
                # same stale summary.
                self.state.game.suppress_next_turn_summary = True
                # Show caster notification that spell was resolved
                spell_name = self.pending_spell_name or 'Your spell'
                # Check logs to determine if spell was allowed or countered
                last_log = None
                if self.state.game.log_entries:
                    for log in reversed(self.state.game.log_entries):
                        if log.get('type') in ('spell_allowed', 'spell_countered'):
                            last_log = log
                            break
                
                spell_family = getattr(self, 'pending_spell_family_name', spell_name)
                spell_images = self._get_spell_icon_image(spell_family)
                
                if last_log and last_log.get('type') == 'spell_countered':
                    self.queue_or_show_notification({
                        'message': f"{spell_name} was countered by your opponent!\n\nYour cards were consumed but the spell had no effect.\nYou keep your turn.",
                        'actions': ['ok'],
                        'images': spell_images,
                        'icon': "error",
                        'title': "Spell Countered"
                    })
                else:
                    self.queue_or_show_notification({
                        'message': f"{spell_name} was allowed by your opponent!\n\nThe spell has been executed successfully.",
                        'actions': ['ok'],
                        'images': spell_images,
                        'icon': "magic",
                        'title': "Spell Executed"
                    })
                self.pending_spell_name = None
                self.pending_spell_family_name = None
                self.pending_spell_details = None  # Clear cache when spell resolved
                self._cached_castable_spells = None
                self._pending_spell_fetch_ready = False
            if self.need_to_respond_to_spell:
                self.need_to_respond_to_spell = False
                self.pending_spell_details = None  # Clear cache when spell resolved
                self._cached_castable_spells = None
                self._pending_spell_fetch_ready = False
    
    def _get_spell_manager(self):
        """Get or create a cached SpellManager instance (avoids reloading images from disk)."""
        if self._cached_spell_manager is None:
            from game.components.spells.spell_manager import SpellManager
            self._cached_spell_manager = SpellManager()
        return self._cached_spell_manager
    
    def _get_spell_icon_image(self, spell_name):
        """Get a spell's icon image from the cached SpellManager. Returns list with icon or empty list."""
        spell_manager = self._get_spell_manager()
        family = spell_manager.get_family_by_name(spell_name)
        if family and family.icon_img:
            return [family.icon_img]
        return []
    
    def _fetch_pending_spell_async(self, is_caster=False):
        """Fetch pending spell details in a background thread to avoid blocking the game loop."""
        if self.pending_spell_details is not None:
            # Already cached - signal ready immediately
            self._pending_spell_fetch_ready = True
            return
        
        if not self.state.game or not self.state.game.pending_spell_id:
            return
        
        import threading
        spell_id = self.state.game.pending_spell_id
        
        def _fetch():
            from utils import http_compat as requests
            try:
                response = requests.get(
                    f'{settings.SERVER_URL}/spells/get_pending_spell',
                    params={'spell_id': spell_id},
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    self.pending_spell_details = data.get('spell', {})
                else:
                    self.pending_spell_details = {}
            except:
                self.pending_spell_details = {}
            
            # Cache castable spells (SpellManager is already pre-loaded, so this is fast)
            if not is_caster:
                self._cache_castable_spells()
            
            # Signal that data is ready (picked up on next update cycle)
            self._pending_spell_fetch_ready = True
        
        thread = threading.Thread(target=_fetch, daemon=True)
        try:
            thread.start()
        except RuntimeError:
            _fetch()  # web fallback: run synchronously
    
    def _cache_castable_spells(self):
        """Compute and cache castable counter spells for the current pending spell."""
        spell_data = self.pending_spell_details or {}
        spell_family_name = spell_data.get('spell_family_name')
        
        if not spell_family_name:
            self._cached_castable_spells = []
            return
        
        main_hand_cards = self.main_hand.cards if hasattr(self, 'main_hand') else []
        side_hand_cards = self.side_hand.cards if hasattr(self, 'side_hand') else []
        all_cards = main_hand_cards + side_hand_cards
        
        spell_manager = self._get_spell_manager()
        family = spell_manager.get_family_by_name(spell_family_name)
        if family:
            self._cached_castable_spells = [
                spell for spell in spell_manager.find_castable_spells(all_cards)
                if spell.family.name == spell_family_name
            ]
        else:
            self._cached_castable_spells = []
    
    def _load_battle_modifier_icons(self):
        """Pre-load battle modifier icons at startup."""
        import os
        icon_dir = settings.SPELL_ICON_IMG_DIR
        icon_size = settings.BATTLE_MODIFIER_ICON_SIZE
        modifier_types = {
            'Civil War': 'civil_war.png',
            'Peasant War': 'peasant_war.png',
            'Blitzkrieg': 'blitzkrieg.png',
            'Royal Decree': 'kings_war.png',
            'Landslide': 'landslide.png',
        }
        for modifier_name, filename in modifier_types.items():
            icon_path = os.path.join(icon_dir, filename)
            if os.path.exists(icon_path):
                img = pygame.image.load(icon_path).convert_alpha()
                img = pygame.transform.smoothscale(img, (icon_size, icon_size))
                self._battle_modifier_icons[modifier_name] = img
    
    def _draw_battle_modifier_icons(self):
        """Draw active battle modifier icons inside a styled panel below the resource scroll."""
        if not self.state.game or not self.state.game.battle_modifier:
            self._hovered_battle_modifier = None
            return
        
        modifiers = self.state.game.battle_modifier
        if not isinstance(modifiers, list) or len(modifiers) == 0:
            self._hovered_battle_modifier = None
            return
        
        icon_size = settings.BATTLE_MODIFIER_ICON_SIZE
        icon_pad = settings.BATTLE_MODIFIER_ICON_PADDING
        box_pad = settings.BATTLE_SPELL_BOX_PADDING
        corner_r = settings.BATTLE_SPELL_BOX_CORNER_R
        title_margin = settings.BATTLE_SPELL_BOX_TITLE_MARGIN
        title_spacing = settings.BATTLE_SPELL_BOX_TITLE_SPACING

        # Render title
        title_surf = self._spell_box_title_font.render(
            'Battle Spells', True, settings.BATTLE_SPELL_BOX_TITLE_COLOR)

        # Panel dimensions: width matches the resource box, height fits title + one row of icons
        box_w = settings.INFO_SCROLL_WIDTH
        title_h = title_surf.get_height()
        box_h = title_margin + title_h + title_spacing + icon_size + box_pad

        # Position below the InfoScroll
        box_x = settings.INFO_SCROLL_X
        box_y = (settings.INFO_SCROLL_Y + settings.INFO_SCROLL_HEIGHT
                 + settings.BATTLE_SPELL_BOX_Y_OFFSET)

        # Draw semi-transparent panel
        panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(panel, settings.BATTLE_SPELL_BOX_BG_CLR,
                         (0, 0, box_w, box_h), border_radius=corner_r)
        pygame.draw.rect(panel, settings.BATTLE_SPELL_BOX_BORDER_CLR,
                         (0, 0, box_w, box_h),
                         settings.BATTLE_SPELL_BOX_BORDER_WIDTH,
                         border_radius=corner_r)
        self.window.blit(panel, (box_x, box_y))

        # Draw title centred in the panel
        title_rect = title_surf.get_rect(centerx=box_x + box_w // 2,
                                         top=box_y + title_margin)
        self.window.blit(title_surf, title_rect)

        # Draw icons row
        icons_y = box_y + title_margin + title_h + title_spacing
        # Centre icons horizontally in the panel
        total_icons_w = len(modifiers) * icon_size + (len(modifiers) - 1) * icon_pad
        icons_start_x = box_x + (box_w - total_icons_w) // 2

        mx, my = pygame.mouse.get_pos()
        self._hovered_battle_modifier = None

        for i, modifier in enumerate(modifiers):
            modifier_type = modifier.get('type', '')
            icon = self._battle_modifier_icons.get(modifier_type)
            if icon:
                x = icons_start_x + i * (icon_size + icon_pad)
                self.window.blit(icon, (x, icons_y))

                # Check hover
                icon_rect = pygame.Rect(x, icons_y, icon_size, icon_size)
                if icon_rect.collidepoint(mx, my):
                    self._hovered_battle_modifier = i
    
    def _draw_battle_modifier_hover_text(self):
        """Draw a styled tooltip pill for the hovered battle modifier icon."""
        if self._hovered_battle_modifier is None or not self.state.game:
            return
        
        modifiers = self.state.game.battle_modifier
        if not isinstance(modifiers, list) or self._hovered_battle_modifier >= len(modifiers):
            return
        
        modifier = modifiers[self._hovered_battle_modifier]
        modifier_type = modifier.get('type', 'Unknown')
        caster_id = modifier.get('caster_id')
        caster_name = modifier.get('caster_name', 'Unknown')
        
        is_self = (caster_id == self.state.game.player_id)
        who = "You" if is_self else caster_name
        dot_clr = settings.TOOLTIP_DOT_ACTIVE_CLR if is_self else settings.TOOLTIP_DOT_PASSIVE_CLR

        hover_text = f"{who} casted {modifier_type}"

        text_surf = self._tooltip_font.render(hover_text, True, settings.TOOLTIP_TEXT_COLOR)

        pad_x = settings.TOOLTIP_PAD_X
        pad_y = settings.TOOLTIP_PAD_Y
        dot_r = settings.TOOLTIP_DOT_RADIUS
        dot_sp = settings.TOOLTIP_DOT_SPACING
        corner_r = settings.TOOLTIP_CORNER_R

        tw, th = text_surf.get_size()
        pill_w = pad_x + dot_r * 2 + dot_sp + tw + pad_x
        pill_h = th + pad_y * 2

        # Anchor to the right of the hovered icon
        icon_size = settings.BATTLE_MODIFIER_ICON_SIZE
        icon_pad = settings.BATTLE_MODIFIER_ICON_PADDING
        box_pad = settings.BATTLE_SPELL_BOX_PADDING
        box_x = settings.INFO_SCROLL_X
        box_w = settings.INFO_SCROLL_WIDTH
        box_y = (settings.INFO_SCROLL_Y + settings.INFO_SCROLL_HEIGHT
                 + settings.BATTLE_SPELL_BOX_Y_OFFSET)
        title_h = self._spell_box_title_font.get_height()
        title_margin = settings.BATTLE_SPELL_BOX_TITLE_MARGIN
        title_spacing = settings.BATTLE_SPELL_BOX_TITLE_SPACING
        icons_y = box_y + title_margin + title_h + title_spacing

        total_icons_w = len(modifiers) * icon_size + (len(modifiers) - 1) * icon_pad
        icons_start_x = box_x + (box_w - total_icons_w) // 2
        icon_x = icons_start_x + self._hovered_battle_modifier * (icon_size + icon_pad)

        pill_x = icon_x + icon_size + settings.TOOLTIP_OFFSET_X
        pill_y = icons_y + icon_size // 2 - pill_h // 2

        # Clamp to screen
        pill_x = min(pill_x, settings.SCREEN_WIDTH - pill_w - 4)
        pill_y = max(4, min(pill_y, settings.SCREEN_HEIGHT - pill_h - 4))

        # Draw pill
        pill = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pygame.draw.rect(pill, settings.TOOLTIP_BG_COLOR,
                         (0, 0, pill_w, pill_h), border_radius=corner_r)
        pygame.draw.rect(pill, settings.TOOLTIP_BORDER_COLOR,
                         (0, 0, pill_w, pill_h),
                         settings.TOOLTIP_BORDER_WIDTH, border_radius=corner_r)
        self.window.blit(pill, (pill_x, pill_y))

        # Status dot
        dot_cx = pill_x + pad_x + dot_r
        dot_cy = pill_y + pill_h // 2
        pygame.draw.circle(self.window, dot_clr, (dot_cx, dot_cy), dot_r)

        # Text
        self.window.blit(text_surf, (pill_x + pad_x + dot_r * 2 + dot_sp, pill_y + pad_y))
    
    def check_battle_modifier_changes(self):
        """Detect new battle modifiers and show notifications to the opponent."""
        if not self.state.game:
            return
        
        current_modifiers = self.state.game.battle_modifier
        if not isinstance(current_modifiers, list):
            current_modifiers = []

        # Conquer mode has dedicated prelude/counter notifications; suppress
        # generic modifier popups to keep the sequence clean and non-duplicated.
        if self.state.game.mode == 'conquer':
            self._previous_battle_modifiers = list(current_modifiers)
            return
        
        # Skip detection right after a battle ended — stale poll data may
        # still contain old modifiers that look "new" after the reset.
        if self.state.game.suppress_next_turn_summary:
            self._previous_battle_modifiers = list(current_modifiers)
            return
        
        previous_types = [m.get('type') for m in self._previous_battle_modifiers]
        current_types = [m.get('type') for m in current_modifiers]
        
        # Detect newly added modifiers
        if len(current_modifiers) > len(self._previous_battle_modifiers):
            new_modifiers = current_modifiers[len(self._previous_battle_modifiers):]
            for modifier in new_modifiers:
                modifier_type = modifier.get('type', 'Unknown')
                caster_name = modifier.get('caster_name', 'Opponent')
                caster_id = modifier.get('caster_id')
                
                # Only notify if the caster is the opponent (not self)
                # AND we didn't just allow this spell (which already showed its own notification)
                if caster_id and caster_id != self.state.game.player_id:
                    # Skip if we just came from allowing this spell
                    # (the _handle_counter_spell_allow already showed a notification)
                    if hasattr(self, '_just_allowed_spell') and self._just_allowed_spell:
                        self._just_allowed_spell = False
                    else:
                        desc = self._get_battle_modifier_description(modifier_type)
                        if not desc:
                            desc = 'A battle modifier is now active.'
                        
                        # Load icon for the notification
                        icon_img = self._battle_modifier_icons.get(modifier_type)
                        images = [icon_img] if icon_img else []
                        
                        self.queue_or_show_notification({
                            'message': f"{caster_name} activated {modifier_type}!\n\n{desc}",
                            'actions': ['ok'],
                            'images': images,
                            'icon': "magic",
                            'title': f"{modifier_type}"
                        })
        
        # Update tracked state
        self._previous_battle_modifiers = list(current_modifiers)
    

    def _show_counter_spell_dialogue(self):
        """Show dialogue asking player to counter or allow spell."""
        if not self.state.game or not self.state.game.pending_spell_id:
            return
        
        # Use cached spell data and castable spells (no network request, no image loading)
        spell_data = self.pending_spell_details or {}
        spell_name = spell_data.get('spell_name', 'a spell')
        spell_family_name = spell_data.get('spell_family_name', spell_name)
        
        # Get spell icon for the dialogue
        spell_images = self._get_spell_icon_image(spell_family_name)
        
        # Use cached castable spells
        castable_spells = self._cached_castable_spells or []
        can_counter = len(castable_spells) > 0
        
        # Show appropriate dialogue based on whether player can counter
        if can_counter:
            message = f"Opponent cast {spell_name}!\n\nDo you want to counter it or allow it?"
            actions = ['counter', 'allow']
        else:
            message = f"Opponent cast {spell_name}!\n\nYou don't have the cards to counter.\nYou must allow it."
            actions = ['allow']
        
        self.make_dialogue_box(
            message=message,
            actions=actions,
            images=spell_images,
            icon="magic",
            title="Counter Spell?" if can_counter else "Allow Spell"
        )
    
    def check_auto_fill_notification(self):
        """Check for auto-fill notification and show dialogue if needed."""
        if not self.state.game or not self.state.game.pending_auto_fill:
            return
        if self.state.game.game_over or self.state.game.pending_game_over:
            self.state.game.pending_auto_fill = None
            return
        
        auto_fill = self.state.game.pending_auto_fill
        main_filled = auto_fill.get('main_cards_filled', 0)
        side_filled = auto_fill.get('side_cards_filled', 0)
        cards_data = auto_fill.get('cards', [])
        
        # Build message
        message_parts = []
        if main_filled > 0:
            message_parts.append(f"{main_filled} main card{'s' if main_filled > 1 else ''}")
        if side_filled > 0:
            message_parts.append(f"{side_filled} side card{'s' if side_filled > 1 else ''}")
        
        message = f"Your hand was below the minimum. Refilled: {' and '.join(message_parts)}."
        
        # Create card images from the cards data
        from game.components.cards.card_img import CardImg
        card_images = []
        for card_data in cards_data:
            card_img = CardImg(self.window, card_data['suit'], card_data['rank'])
            card_images.append(card_img.front_img)
        
        # Queue or show dialogue
        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'images': card_images,
            'icon': "loot",
            'title': "Cards Refilled"
        })
        
        # Clear the notification
        self.state.game.pending_auto_fill = None
    
    def check_post_battle_side_cards(self):
        """Check for post-battle side card draw notification and show dialogue."""
        if not self.state.game or not self.state.game.pending_post_battle_side_cards:
            return
        if self.state.game.game_over or self.state.game.pending_game_over:
            self.state.game.pending_post_battle_side_cards = None
            return
        
        # Defer side card notification while still on battle screen —
        # the player must see the battle result first.
        if self.state.subscreen == 'battle':
            return

        cards_data = self.state.game.pending_post_battle_side_cards
        count = len(cards_data)
        if count == 0:
            self.state.game.pending_post_battle_side_cards = None
            return

        message = f"New round! You drew {count} side card{'s' if count > 1 else ''}."

        # Create card images from the cards data
        from game.components.cards.card_img import CardImg
        card_images = []
        for card_data in cards_data:
            card_img = CardImg(self.window, card_data['suit'], card_data['rank'])
            card_images.append(card_img.front_img)

        # Queue or show dialogue
        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'images': card_images,
            'icon': "loot",
            'title': "Side Cards Drawn"
        })

        # Clear the notification
        self.state.game.pending_post_battle_side_cards = None

    def check_loot_notification(self):
        """Show the battle loser which card the winner chose to keep."""
        if not self.state.game or not self.state.game.pending_loot_notification:
            return

        # Suppress loot notification when the game is over
        if self.state.game.game_over or self.state.game.pending_game_over:
            self.state.game.pending_loot_notification = None
            return

        # Defer while still on battle screen
        if self.state.subscreen == 'battle':
            logger.debug(f"[LOOT_DEBUG] check_loot_notification: deferred (subscreen=battle)")
            return

        loot = self.state.game.pending_loot_notification
        logger.debug(f"[LOOT_DEBUG] check_loot_notification: showing loot={loot}, dialogue_box={self.dialogue_box is not None}")
        winner_name = loot.get('winner_name', 'Opponent')
        suit = loot['suit']
        rank = loot['rank']
        card_type = loot.get('card_type', 'main')
        type_label = 'side card' if card_type == 'side' else 'main card'

        message = f"{winner_name} kept your {type_label} as loot."

        from game.components.cards.card_img import CardImg
        card_img = CardImg(self.window, suit, rank)

        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'images': [card_img.front_img],
            'icon': "loot",
            'title': "Battle Loot"
        })

        self.state.game.pending_loot_notification = None

    def check_opponent_turn_notification(self):
        """Check for opponent turn summary and show dialogue if needed."""
        if not self.state.game or not self._has_opponent_turn_summary_pending(self.state.game):
            return
        if self.state.game.game_over or self.state.game.pending_game_over:
            self._clear_opponent_turn_summaries(self.state.game)
            return
        
        summary = self._pop_opponent_turn_summary(self.state.game)
        if not summary:
            return
        opponent_name = summary.get('opponent_name', 'Opponent')
        action = summary.get('action')
        
        logger.debug(f"\n{'='*60}")
        logger.debug(f"[OPPONENT_TURN_CLIENT] Processing notification")
        logger.debug(f"[OPPONENT_TURN_CLIENT] Summary: {summary}")
        logger.debug(f"[OPPONENT_TURN_CLIENT] Action: {action}")
        logger.debug(f"{'='*60}\n")
        logger.info(f"[WELCOME_MSG] Processing notification - action: {action}")
        logger.debug(f"{'='*60}\n")
        
        # Check for game start notification
        if action == 'game_start':
            is_turn = summary.get('is_turn', False)
            is_invader = summary.get('is_invader', False)

            # ── Conquer mode game start ──
            if summary.get('mode') == 'conquer':
                self.state.game._game_start_pending = False

                own_spells = summary.get('own_prelude_spells', [])
                own_drawn_cards = summary.get('own_drawn_cards', [])
                opp_spells = summary.get('opponent_prelude_spells', [])
                own_no_target_spells = summary.get('own_prelude_no_target_spells', [])
                opponent_no_target_spells = summary.get('opponent_prelude_no_target_spells', [])
                pending_prelude_target = summary.get('pending_prelude_target')

                # Snapshot prelude spells on the game so the conquer
                # timeline panel can read them later (ActiveSpell rows
                # do not carry a phase_cast marker).
                self.state.game.conquer_own_prelude_spells = (
                    list(own_spells) + list(own_no_target_spells)
                )
                self.state.game.conquer_opp_prelude_spells = (
                    list(opp_spells) + list(opponent_no_target_spells)
                )
                # Include any pending target-required prelude (own side) so
                # the panel shows the icon while the user is still picking
                # a target.
                if isinstance(pending_prelude_target, dict):
                    self.state.game.conquer_own_prelude_spells.append(
                        dict(pending_prelude_target)
                    )

                self.state.pending_conquer_prelude_target = None
                self.state.game.pending_conquer_prelude_target = False

                # Seed baseline tracking so generic modifier alerts and stale
                # prelude spells are not re-announced later in conquer flow.
                summary_modifiers = summary.get('battle_modifier')
                if isinstance(summary_modifiers, list):
                    self._previous_battle_modifiers = list(summary_modifiers)
                active_spells = getattr(self.state.game, 'cached_active_spells', []) or []
                self._seen_conquer_opponent_spell_ids = {
                    s.get('id') for s in active_spells
                    if s.get('id') is not None and s.get('player_id') != self.state.game.player_id
                }

                # (1) Intro box — who, what land, invader/defender role
                tier = self.state.game.land_tier
                land_label = f"Tier {tier} land" if tier else "this land"
                role_text = "invader" if is_invader else "defender"
                intro_msg = (f"Conquer Battle Started!\n\n"
                             f"You are the {role_text}. You are fighting "
                             f"{opponent_name} for control of {land_label}.")
                self.queue_or_show_notification({
                    'message': intro_msg,
                    'actions': ['ok'],
                    'icon': 'welcome',
                    'title': 'Conquer Battle',
                    'phase': 'start',
                    'tone': 'info',
                    'event_key': f"conquer_start:{getattr(self.state.game, 'game_id', 'local')}",
                })

                # (2) Own prelude spell success (if any)
                if own_spells:
                    from game.components.cards.card import Card
                    card_images = []
                    for card_data in own_drawn_cards:
                        card = Card(
                            rank=card_data['rank'],
                            suit=card_data['suit'],
                            value=card_data['value'],
                            id=card_data.get('id'),
                            type=card_data.get('type', 'main'),
                        )
                        card_img = card.make_icon(self.window, self.state.game, 0, 0)
                        card_images.append(card_img.front_img)

                    spell_names = ', '.join(s['spell_name'] for s in own_spells)
                    effect_lines = [
                        self._describe_conquer_prelude_effect(spell, own=True)
                        for spell in own_spells
                    ]
                    spell_msg = f"Your prelude spell {spell_names} was executed!"
                    if effect_lines:
                        spell_msg += "\n\n" + "\n".join(f"• {line}" for line in effect_lines)

                    spell_icon_images = self._get_spell_icon_image(own_spells[0]['spell_name'])
                    all_images = spell_icon_images + card_images
                    self.queue_or_show_notification({
                        'message': spell_msg,
                        'actions': ['ok'],
                        'images': all_images if all_images else None,
                        'icon': None if all_images else 'magic',
                        'title': 'Prelude Spell',
                        'phase': 'prelude',
                        'tone': 'good',
                        'spell_names': [s['spell_name'] for s in own_spells],
                        'spell_side': 'own',
                        'spell_role': 'prelude',
                        'event_key': 'own_prelude:' + ','.join(
                            str(s.get('id') or s.get('spell_name')) for s in own_spells),
                    })

                # (3) Opponent prelude spell turn notification (if any)
                if opp_spells:
                    opp_spell_names = ', '.join(s['spell_name'] for s in opp_spells)
                    opp_effect_lines = [
                        self._describe_conquer_prelude_effect(spell, own=False)
                        for spell in opp_spells
                    ]

                    opp_images = []
                    for s in opp_spells:
                        opp_images.extend(self._get_spell_icon_image(s['spell_name']))

                    opp_msg = f"{opponent_name}'s turn:"
                    opp_msg_after = f"• Cast {opp_spell_names}"
                    if opp_effect_lines:
                        opp_msg_after += "\n" + "\n".join(f"  > {line}" for line in opp_effect_lines)

                    self.queue_or_show_notification({
                        'message': opp_msg,
                        'actions': ['ok'],
                        'images': opp_images if opp_images else None,
                        'icon': None if opp_images else 'info',
                        'title': 'Opponent Prelude',
                        'message_after_images': opp_msg_after,
                        'phase': 'prelude',
                        'tone': 'warning',
                        'spell_names': [s['spell_name'] for s in opp_spells],
                        'spell_side': 'opponent',
                        'spell_role': 'prelude',
                        'event_key': 'opponent_prelude:' + ','.join(
                            str(s.get('id') or s.get('spell_name')) for s in opp_spells),
                    })

                # (4) Explicit no-target notifications
                for spell_info in own_no_target_spells:
                    spell_name = spell_info.get('spell_name', 'Prelude spell')
                    spell_images = self._get_spell_icon_image(spell_name)
                    self.queue_or_show_notification({
                        'message': (f"Your prelude spell {spell_name} could not be applied.\n\n"
                                    f"No valid target was available (checkmate figures are excluded)."),
                        'actions': ['ok'],
                        'images': spell_images if spell_images else None,
                        'icon': None if spell_images else 'info',
                        'title': 'No Valid Target',
                        'phase': 'prelude',
                        'tone': 'warning',
                        'spell_names': [spell_name],
                        'spell_side': 'own',
                        'spell_role': 'prelude',
                        'event_key': f'own_no_target:{spell_name}',
                    })

                for spell_info in opponent_no_target_spells:
                    spell_name = spell_info.get('spell_name', 'Prelude spell')
                    spell_images = self._get_spell_icon_image(spell_name)
                    self.queue_or_show_notification({
                        'message': (f"{opponent_name}'s prelude spell {spell_name} had no valid target.\n\n"
                                    f"Checkmate figures are excluded from targeting."),
                        'actions': ['ok'],
                        'images': spell_images if spell_images else None,
                        'icon': None if spell_images else 'info',
                        'title': 'Opponent Prelude',
                        'phase': 'prelude',
                        'tone': 'warning',
                        'spell_names': [spell_name],
                        'spell_side': 'opponent',
                        'spell_role': 'prelude',
                        'event_key': f'opponent_no_target:{spell_name}',
                    })

                # (5) Pending attacker prelude target selection
                if pending_prelude_target:
                    spell_name = pending_prelude_target.get('spell_name', 'Prelude spell')
                    scope = pending_prelude_target.get('target_scope')
                    if scope == 'own':
                        target_hint = "one of your own figures"
                    else:
                        target_hint = "one of your opponent's figures"

                    self.state.pending_conquer_prelude_target = pending_prelude_target
                    self.state.game.pending_conquer_prelude_target = True

                    spell_images = self._get_spell_icon_image(spell_name)
                    self.queue_or_show_notification({
                        'message': (f"Your prelude spell {spell_name} needs a target.\n\n"
                                    f"Select {target_hint} on the field to resolve it.\n\n"
                                    f"Checkmate figures cannot be targeted."),
                        'actions': ['got it!'],
                        'images': spell_images if spell_images else None,
                        'icon': None if spell_images else 'magic',
                        'title': 'Select Prelude Target',
                        'phase': 'prelude',
                        'tone': 'action',
                        'spell_names': [spell_name],
                        'spell_side': 'own',
                        'spell_role': 'prelude',
                        'event_key': f'prelude_target:{pending_prelude_target.get("spell_id") or spell_name}',
                    })

                return

            # ── Duel mode game start ──
            maharaja_data = summary.get('maharaja', {})
            
            # Create Figure object from maharaja data to generate FieldFigureIcon
            from game.components.figures.figure import Figure
            from game.components.figures.figure_manager import FigureManager
            
            # Get families for figure reconstruction
            figure_manager = FigureManager()
            families = figure_manager.families
            
            # Convert maharaja data to Figure instance
            maharaja_figure = self._create_figure_from_data(maharaja_data, families)
            
            if maharaja_figure:
                logger.info(f"[WELCOME_MSG] Creating FieldFigureIcon for {maharaja_figure.name}")
                logger.info(f"[WELCOME_MSG] Figure has {len(maharaja_figure.cards)} cards")
                
                # Create FieldFigureIcon for the maharaja (same as explosion spell)
                from game.components.figures.figure_icon import FieldFigureIcon
                maharaja_icon = FieldFigureIcon(
                    self.window,
                    self.state.game,
                    maharaja_figure,
                    is_visible=True,
                    x=0,
                    y=0,
                    all_player_figures=[maharaja_figure],
                    resources_data={}
                )
                
                # Build images list - only the maharaja icon
                import os
                images = [maharaja_icon]
                
                logger.info(f"[WELCOME_MSG] Showing dialogue with {len(images)} images")
                
                # Build welcome message with game information
                role_text = "invader" if is_invader else "defender"
                maharaja_name = maharaja_figure.name
                turn_status = "It's your turn!" if is_turn else "It's your opponent's turn."
                
                turn_msg = f"Hello Adventurer!\n\nYou are playing with the {maharaja_name} and start with the {role_text} role. You are fighting {opponent_name}."
                
                notification = {
                    'message': turn_msg,
                    'actions': ['ok'],
                    'images': images,
                    'icon': "welcome",
                    'title': "Game Started"
                }
                if is_invader:
                    notification['message_after_images'] = turn_status
                self.queue_or_show_notification(notification)

                # Clear the pending flag so turn-change detection resumes.
                self.state.game._game_start_pending = False

                # For the defender's first turn the invader has already played.
                # Use the live turn state (updated by polling) rather than the
                # potentially stale is_turn from the server response — a fast
                # AI opponent may have played between the request and now.
                if not is_invader and self.state.game.turn:
                    logger.info("[WELCOME_MSG] Defender first turn — re-requesting start_turn for opponent action")
                    self.state.game._start_turn_async()
            else:
                # Safety: clear flag even if maharaja wasn't found
                self.state.game._game_start_pending = False

            return

        # ── Duel "your turn" moment ──
        # Every summary below announces "It's your turn now!"; give it a
        # sound + banner beat. play_for_dialogue has no stinger for the
        # "Your Turn" title, so this does not double-fire. Conquer runs its
        # own transition choreography (this method is shared via update_game).
        if getattr(self.state.game, 'mode', 'duel') != 'conquer':
            from utils import sound
            sound.play('your_turn', volume=0.8)
            fx = getattr(self, '_fx', None)
            if fx is not None:
                fx.spawn_banner('YOUR TURN', (238, 206, 130))

        # Check if action is missing, None, or the string 'unknown'
        if not action or action == 'unknown':
            # Generic message if no specific action detected
            message = summary.get('message', f"{opponent_name} completed their turn.")
            self.queue_or_show_notification({
                'message': f"{message}\n\nIt's your turn now!",
                'actions': ['ok'],
                'icon': "info",
                'title': "Your Turn"
            })
        else:
            # Build message based on the action (action is a dict)
            action_type = action.get('type')
            action_message = action.get('message', 'completed their turn')
            spell_name = action.get('spell_name', '')
            
            logger.debug(f"[OPPONENT_TURN_CLIENT] Processing action: type={action_type}, spell={repr(spell_name)}, has_new_cards={'new_cards' in action}")
            if 'new_cards' in action:
                logger.debug(f"[OPPONENT_TURN_CLIENT] new_cards present with {len(action.get('new_cards', []))} cards")
            
            # Load icons for actions
            images = []
            
            # Special handling for Forced Deal with card details
            if (action_type in ('spell', 'counter_spell') and spell_name == 'Forced Deal' and 
                'cards_given' in action and 'cards_received' in action):
                
                from game.components.cards.card import Card
                import os
                
                cards_given = action.get('cards_given', [])
                cards_received = action.get('cards_received', [])
                
                logger.info(f"[FORCED_DEAL_CLIENT] Showing cards: gave {len(cards_given)}, received {len(cards_received)}")
                
                # Add received cards (show first)
                for card_data in cards_received:
                    card = Card(
                        rank=card_data['rank'],
                        suit=card_data['suit'],
                        value=card_data['value'],
                        id=card_data.get('id'),
                        type=card_data.get('type', 'main')
                    )
                    card_img = card.make_icon(self.window, self.state.game, 0, 0)
                    images.append(card_img.front_img)
                
                # Add given cards (with transparency and red cross)
                for card_data in cards_given:
                    card = Card(
                        rank=card_data['rank'],
                        suit=card_data['suit'],
                        value=card_data['value'],
                        id=card_data.get('id'),
                        type=card_data.get('type', 'main')
                    )
                    card_img = card.make_icon(self.window, self.state.game, 0, 0)
                    given_card_img = card_img.front_img.copy()
                    given_card_img.set_alpha(128)  # 50% transparency
                    
                    # Add red cross overlay
                    red_cross_path = os.path.join('img', 'new_cards', 'red_cross.png')
                    if os.path.exists(red_cross_path):
                        red_cross = pygame.image.load(red_cross_path)
                        cross_size = min(given_card_img.get_width(), given_card_img.get_height())
                        red_cross = pygame.transform.scale(red_cross, (cross_size, cross_size))
                        cross_x = (given_card_img.get_width() - cross_size) // 2
                        cross_y = (given_card_img.get_height() - cross_size) // 2
                        given_card_img.blit(red_cross, (cross_x, cross_y))
                    
                    images.append(given_card_img)
            
            # Special handling for Dump Cards with new cards
            elif (action_type in ('spell', 'counter_spell') and spell_name == 'Dump Cards' and 
                  'new_cards' in action):
                
                logger.debug(f"[DUMP_CARDS_CLIENT] ENTERING Dump Cards card display block")
                
                from game.components.cards.card import Card
                new_cards = action.get('new_cards', [])
                
                logger.debug(f"[DUMP_CARDS_CLIENT] Showing {len(new_cards)} new cards from opponent turn notification")
                logger.debug(f"[DUMP_CARDS_CLIENT] new_cards data: {new_cards}")
                
                # Add all new cards
                for card_data in new_cards:
                    card = Card(
                        rank=card_data['rank'],
                        suit=card_data['suit'],
                        value=card_data['value'],
                        id=card_data.get('id'),
                        type=card_data.get('type', 'main')
                    )
                    card_img = card.make_icon(self.window, self.state.game, 0, 0)
                    images.append(card_img.front_img)
            
            # Special handling for Poison with affected figure
            elif (action_type in ('spell', 'counter_spell') and spell_name == 'Poison' and 
                  action.get('affects_player') and action.get('target_figure_id')):
                import os
                spell_icon_path = os.path.join('img', 'spells', 'icons', action.get('spell_icon', 'poisson_portion.png'))
                if os.path.exists(spell_icon_path):
                    spell_icon_img = pygame.image.load(spell_icon_path)
                    images.append(spell_icon_img)
                # Find figure icon for the affected figure
                target_figure_id = action.get('target_figure_id')
                field_screen = self.subscreens.get('field')
                if field_screen:
                    for icon in getattr(field_screen, 'figure_icons', []):
                        if icon.figure.id == target_figure_id:
                            images.append(icon)
                            break
            
            # Load spell icon if this is a spell action (and not Forced Deal/Dump Cards/Poison with cards)
            elif action_type in ('spell', 'counter_spell') and action.get('spell_icon'):
                import os
                spell_icon_path = os.path.join('img', 'spells', 'icons', action.get('spell_icon'))
                if os.path.exists(spell_icon_path):
                    spell_icon_img = pygame.image.load(spell_icon_path)
                    images.append(spell_icon_img)
            
            # Load spell icon for infinite_hammer notification
            elif action_type == 'infinite_hammer' and action.get('spell_icon'):
                import os
                spell_icon_path = os.path.join('img', 'spells', 'icons', action.get('spell_icon'))
                if os.path.exists(spell_icon_path):
                    spell_icon_img = pygame.image.load(spell_icon_path)
                    images.append(spell_icon_img)
            
            # Load action icon for build, upgrade, pickup, or card_change actions
            elif action.get('icon'):
                import os
                action_icon_path = os.path.join('img', 'game_button', 'symbol', action.get('icon'))
                if os.path.exists(action_icon_path):
                    action_icon_img = pygame.image.load(action_icon_path)
                    images.append(action_icon_img)
            
            # Special handling for explosion - show bomb icon and destroyed figure name prominently
            if action_type == 'explosion':
                import os
                bomb_icon_path = os.path.join('img', 'spells', 'icons', 'bomb.png')
                if os.path.exists(bomb_icon_path):
                    bomb_icon_img = pygame.image.load(bomb_icon_path)
                    images.append(bomb_icon_img)
                destroyed_figure = action.get('destroyed_figure', 'a figure')
                message = f"{opponent_name} cast Explosion!\n\nYour {destroyed_figure} was destroyed.\n\nIt's your turn now!"
                message_after = None
                icon = "error"
            # Special handling for Poison on player's figure
            elif (action_type in ('spell', 'counter_spell') and spell_name == 'Poison' and 
                  action.get('affects_player') and action.get('target_figure_name')):
                target_name = action.get('target_figure_name')
                message = f"{opponent_name} cast Poison!\n\nYour {target_name} was poisoned (-6 power).\n\nIt's your turn now!"
                message_after = None
                icon = "error"
            else:
                # Split message: title before icon, details after icon
                message = f"{opponent_name}'s turn:"
                
                # Build the message after icon
                message_after = f"• {action_message}"
                
                # Add details if spell affects player
                if action.get('affects_player'):
                    details = action.get('details', '')
                    if details:
                        message_after += f"\n  > {details}"
                
                message_after += "\n\nIt's your turn now!"
                
                icon = "info"
            
            self.queue_or_show_notification({
                'message': message,
                'actions': ['ok'],
                'icon': icon,
                'title': "Your Turn",
                'images': images if images else None,
                'message_after_images': message_after if not action_type == 'explosion' else None
            })
        
    @staticmethod
    def _has_opponent_turn_summary_pending(game):
        return bool(
            getattr(game, 'pending_opponent_turn_summary', None)
            or getattr(game, 'pending_opponent_turn_summaries', None)
        )

    @staticmethod
    def _pop_opponent_turn_summary(game):
        popper = getattr(game, 'pop_pending_opponent_turn_summary', None)
        if callable(popper):
            return popper()
        summary = getattr(game, 'pending_opponent_turn_summary', None)
        game.pending_opponent_turn_summary = None
        return summary

    @staticmethod
    def _clear_opponent_turn_summaries(game):
        clearer = getattr(game, 'clear_pending_opponent_turn_summaries', None)
        if callable(clearer):
            clearer()
            return
        game.pending_opponent_turn_summary = None
        if hasattr(game, 'pending_opponent_turn_summaries'):
            game.pending_opponent_turn_summaries = []
    
    def check_ceasefire_ended_notification(self):
        """Check if ceasefire ended and show notification if needed."""
        if not self.state.game or not self.state.game.pending_ceasefire_ended:
            return
        if self.state.game.game_over or self.state.game.pending_game_over:
            self.state.game.pending_ceasefire_ended = False
            return
        
        # Guard: if ceasefire is actually active now (e.g. transient state during
        # battle resolution), drop the stale notification
        if self.state.game.ceasefire_active:
            self.state.game.pending_ceasefire_ended = False
            return
        
        # Guard: don't show ceasefire-ended right after a battle resolved —
        # the Blitzkrieg ceasefire naturally ends with the battle and doesn't
        # need a separate notification.
        if self.state.game.suppress_next_turn_summary:
            self.state.game.pending_ceasefire_ended = False
            return
        
        # Defer: don't interrupt other notification sequences — wait until
        # the queue is empty and no dialogue is active
        if self.dialogue_box or self.pending_notifications:
            return
        
        # Load ceasefire passive icon
        import os
        icon_path = os.path.join('img', 'status_icons', 'ceasefire_passive.png')
        images = []
        if os.path.exists(icon_path):
            ceasefire_img = pygame.image.load(icon_path)
            images.append(ceasefire_img)
        
        # Show notification to both players
        self.queue_or_show_notification({
            'message': "Ceasefire has ended!\n\nBattles can now begin.",
            'actions': ['ok'],
            'images': images if images else None,
            'icon': "info",
            'title': "Ceasefire Ended"
        })
        
        # Clear the notification
        self.state.game.pending_ceasefire_ended = False
    
    def check_ceasefire_active_notification(self):
        """Show ceasefire-active notification when ceasefire activates."""
        if not self.state.game or not self.state.game.pending_ceasefire_active_notification:
            return
        if self.state.game.game_over or self.state.game.pending_game_over:
            self.state.game.pending_ceasefire_active_notification = False
            return
        
        # If ceasefire is no longer active, discard the stale notification
        if not self.state.game.ceasefire_active:
            logger.info(f"[CEASEFIRE] check_ceasefire_active: discarding — ceasefire no longer active")
            self.state.game.pending_ceasefire_active_notification = False
            return
        
        # Display-level dedup: only show once per round regardless of source
        if self.state.game._ceasefire_active_displayed_round == self.state.game.current_round:
            logger.info(f"[CEASEFIRE] check_ceasefire_active: discarding — already displayed for round {self.state.game.current_round}")
            self.state.game.pending_ceasefire_active_notification = False
            return
        
        # If ceasefire already ended this round, this is stale data — discard
        if (self.state.game._ceasefire_notified_round == self.state.game.current_round
                and self.state.game._ceasefire_notified_state == 'ended'):
            logger.info(f"[CEASEFIRE] check_ceasefire_active: discarding — ceasefire already ended round {self.state.game.current_round}")
            self.state.game.pending_ceasefire_active_notification = False
            return

        if self._duel_coach_has_pending_step():
            logger.info(f"[CEASEFIRE] check_ceasefire_active: suppressing during first-duel coach, round={self.state.game.current_round}")
            self.state.game._ceasefire_active_displayed_round = self.state.game.current_round
            self.state.game.pending_ceasefire_active_notification = False
            return
        
        # Defer while still on battle screen
        if self.state.subscreen == 'battle':
            return
        
        # Defer: don't interrupt other notification sequences — wait until
        # the queue is empty and no dialogue is active
        if self.dialogue_box or self.pending_notifications:
            return
        
        # Load ceasefire active icon
        import os
        icon_path = os.path.join('img', 'status_icons', 'ceasefire_active.png')
        images = []
        if os.path.exists(icon_path):
            ceasefire_img = pygame.image.load(icon_path)
            images.append(ceasefire_img)
        
        # Customize message based on whether Blitzkrieg is active
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)
        
        if has_blitzkrieg:
            message = "Ceasefire is active!\n\nNo battles can commence while ceasefire is in effect.\n\nThe ceasefire will last until the last turn."
        else:
            message = "Ceasefire is active!\n\nNo battles can commence while ceasefire is in effect.\n\nThe ceasefire will last for 3 invader turns."
        
        logger.info(f"[CEASEFIRE] check_ceasefire_active: SHOWING notification for round {self.state.game.current_round}")
        self.state.game._ceasefire_active_displayed_round = self.state.game.current_round
        
        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'images': images if images else None,
            'icon': "info",
            'title': "Ceasefire Active"
        })
        
        self.state.game.pending_ceasefire_active_notification = False
    
    def check_infinite_hammer_activation(self):
        """Check if Infinite Hammer spell was just activated and show initial dialogue."""
        if not self.state.game:
            return
        
        # Check if Infinite Hammer just became active
        is_active = self.state.game.check_infinite_hammer_active()
        
        if is_active and not self.state.game.infinite_hammer_dialogue_shown:
            # Show initial dialogue explaining mode
            self.queue_or_show_notification({
                'message': "Infinite Hammer is now active!\n\nYou can build, upgrade, and pickup figures without ending your turn.\n\nCard changes and other spells are blocked.\n\nPress ESC when you're ready to end your turn.",
                'actions': ['ok'],
                'icon': "infinite_hammer",
                'title': "Infinite Hammer Active"
            })
            
            # Mark dialogue as shown and enable mode
            self.state.game.infinite_hammer_dialogue_shown = True
            self.state.game.infinite_hammer_active = True
        elif not is_active and self.state.game.infinite_hammer_active:
            # Spell is no longer active - clear client state
            self.state.game.infinite_hammer_active = False
            self.state.game.infinite_hammer_dialogue_shown = False
    
    def check_forced_advance(self):
        """Check if player must advance (turns_left <= 1) and show forced advance dialogue."""
        if not self.state.game or not self.state.game.turn:
            return
        
        # Don't trigger during post-battle resolution (battle still confirmed on server,
        # e.g. winner hasn't picked card yet — turns_left may still be 0 from the old round)
        if self.state.game.battle_confirmed:
            return
        
        # Wait for the conquer game-start sequence (intro + prelude spells)
        # to be shown before prompting the player to advance.
        if self.state.game.mode == 'conquer' and (
            self.state.game._game_start_pending
            or self._has_opponent_turn_summary_pending(self.state.game)
            or getattr(self.state.game, 'pending_conquer_prelude_target', False)
        ):
            return
        
        # Force advance when: invader, 1 or fewer turns left, ceasefire not
        # active, no active advance already, and dialogue not already shown.
        # Only the INVADER must advance on their last turn — not the defender.
        if (self.state.game.invader and
            self.state.game.current_player.get('turns_left', 0) <= 1 and
            not self.state.game.ceasefire_active and
            not self.state.game.advancing_figure_id and
            not self.state.game.forced_advance_dialogue_shown):
            
            # Check if ANY figure can actually advance
            can_any_advance = self._check_any_figure_can_advance()
            
            if not can_any_advance:
                # No figure can advance — auto-lose the battle
                self.state.game.forced_advance_dialogue_shown = True
                self._handle_cannot_advance_loss()
                return
            
            self.state.game.pending_forced_advance = True
            self.state.game.forced_advance_dialogue_shown = True
            
            # Show notification dialogue
            import os
            icon_path = os.path.join('img', 'figures', 'state_icons', 'charge.png')
            images = []
            if os.path.exists(icon_path):
                advance_img = pygame.image.load(icon_path).convert_alpha()
                images.append(advance_img)
            
            # Build message depending on game mode
            if self.state.game.mode == 'conquer':
                msg = "Select one of your figures on the field to advance toward battle."
                title = "Advance your Battle Figure"
            else:
                msg = "Last turn!\n\nIt's time to advance a figure toward battle.\n\nGo to the field and select a figure to advance, or build a figure with Instant Charge to build and advance in one action."
                title = "Battle Time"
            
            self.queue_or_show_notification({
                'message': msg,
                'actions': ['ok'],
                'images': images if images else None,
                'icon': None if images else "info",
                'title': title,
                'phase': 'advance',
                'tone': 'action',
                'event_key': (
                    f"forced_advance:{getattr(self.state.game, 'game_id', 'local')}:"
                    f"{getattr(self.state.game, 'current_round', 'current')}"
                ),
            })
    
    def _check_any_figure_can_advance(self):
        """Check if any of the player's figures can be advanced given current modifiers."""
        field_screen = self.subscreens.get('field')
        if not field_screen or not hasattr(field_screen, 'categorized_figures'):
            return True  # Assume yes if we can't check
        
        own_figures = field_screen.categorized_figures.get('self', {})
        all_own_figures = []
        for field_type, fig_list in own_figures.items():
            all_own_figures.extend(fig_list)
        
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        
        # Check if opponent's advancing figure has cannot_be_blocked
        # (would block counter-advance for all figures, including instant_charge build+advance)
        if self.state.game.advancing_figure_id and self.state.game.advancing_player_id != self.state.game.player_id:
            field_screen = self.subscreens.get('field')
            if field_screen:
                for fig in getattr(field_screen, 'figures', []):
                    if hasattr(fig, 'id') and fig.id == self.state.game.advancing_figure_id:
                        if hasattr(fig, 'cannot_be_blocked') and fig.cannot_be_blocked:
                            return False
                        break
        
        # Blitzkrieg: defender cannot counter-advance
        if 'Blitzkrieg' in modifier_types:
            if (self.state.game.advancing_figure_id and 
                self.state.game.advancing_player_id != self.state.game.player_id):
                return False
        
        # Get icon cache for deficit checks
        icon_cache = getattr(field_screen, 'icon_cache', {})
        
        for fig in all_own_figures:
            # Skip figures that cannot attack
            if hasattr(fig, 'cannot_attack') and fig.cannot_attack:
                continue
            
            # Skip figures with resource deficit (check from icon cache)
            icon = icon_cache.get(fig.id)
            if icon and getattr(icon, 'has_deficit', False):
                continue
            
            # Peasant War / Civil War: only village figures can advance
            if 'Peasant War' in modifier_types or 'Civil War' in modifier_types:
                figure_field = getattr(fig.family, 'field', None) if hasattr(fig, 'family') else None
                if figure_field != 'village':
                    continue
            
            # This figure can advance
            return True
        
        # No field figure can advance — check if any instant charge figure can be built
        build_screen = self.subscreens.get('build_figure')
        if build_screen and hasattr(build_screen, 'figure_manager') and build_screen.game:
            for family in build_screen.figure_manager.families.values():
                buildable = build_screen.get_figures_in_hand(family)
                for fig in buildable:
                    if getattr(fig, 'instant_charge', False):
                        can_charge, _, _ = build_screen._can_instant_charge_advance(fig)
                        if can_charge:
                            return True
        
        return False
    
    def _handle_cannot_advance_loss(self):
        """Handle the case where the player cannot advance any figure — auto-lose."""
        if getattr(self.state.game, 'game_over', False):
            return
        from utils.game_service import cannot_advance_loss
        result = cannot_advance_loss(self.state.game.game_id, self.state.game.player_id)
        
        if result.get('success'):
            if result.get('conquer_result'):
                self._handle_conquer_result_response(result)
                return

            # Check for game-over
            if result.get('game_over'):
                if result.get('game'):
                    self.state.game.update_from_dict(result['game'])
                self._reset_battle_state()
                self.state.game.fold_result_shown = True
                self._show_game_over_dialogue(result['game_over'])
                return

            winner = result.get('winner', 'Opponent')
            points = result.get('points', 10)
            
            # Update game state from response
            if result.get('game'):
                self.state.game.update_from_dict(result['game'])
            
            # Reset all battle state (includes suppress_next_turn_summary)
            self._reset_battle_state()
            
            new_round = self.state.game.current_round
            
            # Mark fold result as shown so check_fold_result() doesn't double-show
            self.state.game.fold_result_shown = True
            
            self.queue_or_show_notification({
                'message': (f"You have no figures that can advance!\n\n"
                           f"{winner} wins {points} points and is now the invader.\n\n"
                           f"Round {new_round} begins. {winner} starts the new round."),
                'actions': ['ok'],
                'icon': 'magic',
                'title': "Defeat"
            })
        else:
            error_msg = result.get('message', 'Unknown error')
            logger.error(f"[GAME_SCREEN] Auto-loss failed: {error_msg}")
    
    def _check_any_defender_selectable(self):
        """Check if any of the opponent's figures can be selected as a defender."""
        field_screen = self.subscreens.get('field')
        if not field_screen or not hasattr(field_screen, 'categorized_figures'):
            return True  # Assume yes if we can't check
        
        opponent_figures = field_screen.categorized_figures.get('opponent', {})
        all_opponent_figures = []
        for field_type, fig_list in opponent_figures.items():
            all_opponent_figures.extend(fig_list)
        
        if not all_opponent_figures:
            return False
        
        # Get advancing figure for cannot_be_blocked check
        advancing_figure = None
        if self.state.game.advancing_figure_id:
            for fig in getattr(field_screen, 'figures', []):
                if fig.id == self.state.game.advancing_figure_id:
                    advancing_figure = fig
                    break
        
        advancing_cannot_be_blocked = (
            advancing_figure and 
            hasattr(advancing_figure, 'cannot_be_blocked') and 
            advancing_figure.cannot_be_blocked
        )
        
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        has_blitzkrieg = 'Blitzkrieg' in modifier_types
        village_only = 'Peasant War' in modifier_types or 'Civil War' in modifier_types
        skip_must_be_attacked = advancing_cannot_be_blocked or has_blitzkrieg
        
        eligible = []
        checkmate_fallback = []
        for fig in all_opponent_figures:
            if hasattr(fig, 'cannot_defend') and fig.cannot_defend:
                continue
            if hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted:
                continue
            if village_only and hasattr(fig, 'family') and fig.family.field != 'village':
                continue
            if hasattr(fig, 'checkmate') and fig.checkmate:
                checkmate_fallback.append(fig)
                continue
            eligible.append(fig)

        if not eligible and checkmate_fallback:
            eligible = checkmate_fallback
        
        if not eligible:
            return False
        
        # Check must_be_attacked constraint
        if not skip_must_be_attacked:
            must_be_attacked = [f for f in eligible if hasattr(f, 'must_be_attacked') and f.must_be_attacked]
            if must_be_attacked:
                return True  # At least one must_be_attacked figure exists
        
        return len(eligible) > 0
    
    def _handle_defender_no_figures_loss(self):
        """Handle the case where the defender has no valid figures — defender auto-loses."""
        from utils.game_service import defender_no_figures_loss
        result = defender_no_figures_loss(self.state.game.game_id, self.state.game.player_id)
        
        if result.get('success'):
            if result.get('conquer_result'):
                self._handle_conquer_result_response(result)
                return

            # Check for game-over
            if result.get('game_over'):
                if result.get('game'):
                    self.state.game.update_from_dict(result['game'])
                self._reset_battle_state()
                self.state.game.fold_result_shown = True
                self._show_game_over_dialogue(result['game_over'])
                return

            loser = result.get('loser', 'Opponent')
            points = result.get('points', 10)
            
            # Update game state from response
            if result.get('game'):
                self.state.game.update_from_dict(result['game'])
            
            # Reset all battle state
            self._reset_battle_state()
            
            new_round = self.state.game.current_round
            
            # Mark fold result as shown so check_fold_result() doesn't double-show
            self.state.game.fold_result_shown = True
            
            self.queue_or_show_notification({
                'message': (f"{loser} has no valid figures for battle!\n\n"
                           f"You win {points} points.\n\n"
                           f"You are now the invader.\n\n"
                           f"Round {new_round} begins. It's your turn!"),
                'actions': ['ok'],
                'icon': 'magic',
                'title': "Victory!"
            })
        else:
            error_msg = result.get('message', 'Unknown error')
            logger.error(f"[GAME_SCREEN] Defender auto-loss failed: {error_msg}")
    
    def _get_battle_modifier_description(self, modifier_type):
        """Return human-readable effect text for a battle modifier spell."""
        if self.state.game and getattr(self.state.game, 'mode', None) == 'conquer':
            conquer_descriptions = {
                'Civil War': 'Conquer restriction: only village figures can fight, and each side may use up to two same-color village figures.',
                'Peasant War': 'Conquer restriction: only village figures can be selected for this battle.',
                'Blitzkrieg': 'Conquer restriction: the defender cannot counter-advance; the invader selects the defender after advancing. Ceasefire is active until the last turn.',
                'Royal Decree': 'Conquer restriction: only castle figures can advance or defend. Both players dumped their hands and drew fresh cards.',
                'Landslide': 'Conquer twist: the land bonus is inverted — figures matching the land suit lose it instead of gaining it (both sides).',
            }
            if modifier_type in conquer_descriptions:
                return conquer_descriptions[modifier_type]
        descriptions = {
            'Civil War': 'Each player may choose up to two villagers of the same color. Both players have 2 turns left. The invader starts next turn.',
            'Peasant War': 'Only villagers can be selected for the battle. Both players have 2 turns left. The invader starts next turn.',
            'Blitzkrieg': 'The advancing figure cannot be blocked. Both players have 2 turns left. The invader starts next turn. Ceasefire is active until the last turn.',
            'Royal Decree': 'Only castle figures can advance or defend. Both players dump their hands and draw fresh cards.',
            'Landslide': 'The land bonus is inverted for this battle — matching figures lose it instead of gaining it.',
        }
        return descriptions.get(modifier_type)

    def _is_battle_modifier_spell(self, spell_name):
        """Return True when the spell name maps to a battle modifier."""
        return self._get_battle_modifier_description(spell_name) is not None

    def _get_modifier_explanation_lines(self, modifier_names):
        """Build de-duplicated '<Modifier>: <effect>' lines for notifications."""
        lines = []
        seen = set()
        for modifier_name in modifier_names:
            if not modifier_name or modifier_name in seen:
                continue
            seen.add(modifier_name)
            desc = self._get_battle_modifier_description(modifier_name)
            if desc:
                lines.append(f"{modifier_name}: {desc}")
        return lines

    def _describe_conquer_prelude_effect(self, spell_info, *, own=True):
        """Return a concise human-readable conquer prelude effect line."""
        spell_name = spell_info.get('spell_name', 'Prelude spell')
        effect_data = spell_info.get('effect_data') or {}
        target_name = spell_info.get('target_figure_name') or effect_data.get('target_figure_name')

        modifier_desc = self._get_battle_modifier_description(spell_name)
        if modifier_desc:
            return f"{spell_name}: {modifier_desc}"
        if spell_name == 'Invader Swap':
            if effect_data.get('conquer_invader_swap'):
                if own:
                    return ("Invader Swap: the defender became the invader. "
                            "They must advance first; you will choose a defender "
                            "unless the advance cannot be blocked.")
                else:
                    return ("Opponent cast Invader Swap: you are now the invader "
                            "and must advance first.")
            return "Invader Swap: roles have been swapped."
        if spell_name == 'Poison':
            if target_name:
                return f"Poison: {target_name} receives -6 battle power."
            return "Poison: target receives -6 battle power."
        if spell_name == 'Health Boost':
            if target_name:
                return f"Health Boost: {target_name} receives +6 battle power."
            return "Health Boost: target receives +6 battle power."
        if spell_name == 'Explosion':
            destroyed = effect_data.get('destroyed_figure_name') or target_name or 'a figure'
            card_count = effect_data.get('card_count')
            if card_count is not None:
                return f"Explosion: destroyed {destroyed}; {card_count} card(s) returned to the deck."
            return f"Explosion: destroyed {destroyed}."
        if spell_name == 'Dump Cards':
            own_dumped = effect_data.get('caster_dumped') if own else effect_data.get('opponent_dumped')
            opp_dumped = effect_data.get('opponent_dumped') if own else effect_data.get('caster_dumped')
            caster_label = 'You' if own else 'Opponent'
            return (f"Dump Cards (cast by {caster_label}): you discarded {own_dumped or 0} card(s), "
                    f"opponent discarded {opp_dumped or 0}; both redrew a fresh hand.")
        if spell_name == 'Forced Deal':
            given = effect_data.get('cards_given') or effect_data.get('caster_gave') or []
            received = effect_data.get('cards_received') or effect_data.get('caster_received') or []
            if not own:
                given = effect_data.get('opponent_gave') or []
                received = effect_data.get('opponent_received') or []
            if given or received:
                return f"Forced Deal: exchanged {len(given)} card(s) for {len(received)} card(s)."
            return "Forced Deal: exchanged 2 random main cards."
        drawn = effect_data.get('drawn_cards') or []
        if drawn:
            return f"{spell_name}: drew {len(drawn)} card(s)."
        return f"{spell_name}: executed successfully."

    def _get_battle_modifier_info(self):
        """Get battle modifier summary text and icon images for notification dialogues."""
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        if not modifiers:
            return "", []

        modifier_names = []
        modifier_images = []
        for mod in modifiers:
            mod_type = mod.get('type', 'Unknown')
            icon_img = self._battle_modifier_icons.get(mod_type)
            if icon_img:
                modifier_images.append(icon_img)
            modifier_names.append(mod_type)

        modifier_texts = self._get_modifier_explanation_lines(modifier_names)
        text = "\n".join(modifier_texts)
        return text, modifier_images

    def check_own_advance_notification(self):
        """Check if Blitzkrieg combine-advance-and-select is needed.
        For normal advances, the persistent prompt replaces the dialogue.
        In conquer mode, show a confirmation notification."""
        if not self.state.game or not self.state.game.pending_own_advance_notification:
            return
        
        figure_name = self.state.game.own_advance_figure_name or "your figure"

        # Conquer mode: show a brief advance confirmation
        if self.state.game.mode == 'conquer':
            self.state.game.pending_own_advance_notification = False

            images = []
            if self.state.game.advancing_figure_id:
                field_screen = self.subscreens.get('field')
                if field_screen:
                    for icon in getattr(field_screen, 'figure_icons', []):
                        if hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id:
                            images.append(icon)
                            break

            modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
            has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)

            if has_blitzkrieg:
                modifier_text, modifier_icons = self._get_battle_modifier_info()
                images.extend(modifier_icons)
                msg = (f"You advanced {figure_name} toward battle!\n\n"
                       f"Blitzkrieg is active — the defender cannot counter-advance.\n"
                       f"Select which of the defender's figures to face in battle.")
                title = "Blitzkrieg Advance"
            else:
                msg = f"You advanced {figure_name} toward battle!"
                title = "Advancing!"

            self.queue_or_show_notification({
                'message': msg,
                'actions': ['ok'],
                'images': images if images else None,
                'icon': None if images else "info",
                'title': title,
                'phase': 'advance',
                'tone': 'action' if has_blitzkrieg else 'good',
                'spell_names': ['Blitzkrieg'] if has_blitzkrieg else [],
                'event_key': f'own_advance:{self.state.game.advancing_figure_id}:{has_blitzkrieg}',
            })
            return
        
        figure_name = self.state.game.own_advance_figure_name or "your figure"
        
        # Check active battle modifiers
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        has_blitzkrieg = 'Blitzkrieg' in modifier_types
        
        # Blitzkrieg: notify that advance happened, but DON'T immediately trigger
        # defender selection — the defender gets their last turn first (build, etc.).
        # After the defender's turn ends, pending_defender_selection kicks in via polling.
        if has_blitzkrieg:
            self.state.game.pending_own_advance_notification = False
            
            # Gather icons
            images = []
            if self.state.game.advancing_figure_id:
                field_screen = self.subscreens.get('field')
                if field_screen:
                    for icon in getattr(field_screen, 'figure_icons', []):
                        if hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id:
                            images.append(icon)
            modifier_text, modifier_icons = self._get_battle_modifier_info()
            images.extend(modifier_icons)
            
            message = (f"You advanced {figure_name} toward battle!\n\n"
                       f"Blitzkrieg is active — your opponent cannot counter-advance.\n"
                       f"Your opponent gets one last turn before you select their battle figure.")
            
            self.queue_or_show_notification({
                'message': message,
                'actions': ['got it!'],
                'images': images if images else None,
                'icon': None if images else "info",
                'title': "Blitzkrieg Advance"
            })
            return
        
        # For normal/Civil War/Peasant War advances: no dialogue needed.
        # The persistent prompt (YOUR FIGURE ADVANCING) already shows the status.
        self.state.game.pending_own_advance_notification = False

    def check_opponent_advance_notification(self):
        """Check if opponent advanced a figure and show notification."""
        if not self.state.game or not self.state.game.pending_advance_notification:
            return
        
        # Check if advancing figure has cannot_be_blocked
        advancing_fig = None
        advancing_icon = None
        has_cannot_be_blocked = False
        advancing_description = "a figure"
        if self.state.game.advancing_figure_id:
            field_screen = self.subscreens.get('field')
            if field_screen:
                for fig in getattr(field_screen, 'figures', []):
                    if fig.id == self.state.game.advancing_figure_id:
                        advancing_fig = fig
                        has_cannot_be_blocked = hasattr(fig, 'cannot_be_blocked') and fig.cannot_be_blocked
                        # Build anonymous description: field type + card count
                        field_type = getattr(fig.family, 'field', 'unknown') if hasattr(fig, 'family') else 'unknown'
                        card_count = len(fig.cards) if hasattr(fig, 'cards') else '?'
                        advancing_description = f"a {field_type} figure with {card_count} cards"
                        break
                # Find the advancing figure's FieldFigureIcon for display
                for icon in getattr(field_screen, 'figure_icons', []):
                    if hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id:
                        advancing_icon = icon
                        break
        
        # Always show the charge_opponent icon (not the hidden field icon)
        images = []
        import os
        icon_path = os.path.join('img', 'figures', 'state_icons', 'charge_opponent.png')
        if os.path.exists(icon_path):
            advance_img = pygame.image.load(icon_path).convert_alpha()
            images.append(advance_img)
        
        # Check for battle modifiers
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        
        # Add battle modifier icons
        modifier_text, modifier_icons = self._get_battle_modifier_info()
        images.extend(modifier_icons)
        
        # Build message with prominent modifier context
        # Message before images: "Your opponent advanced..."
        # Message after images: options/instructions
        message_after = None
        if self.state.game.mode == 'conquer':
            title = "Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = "The battle will begin shortly."
        elif 'Blitzkrieg' in modifier_types and not has_cannot_be_blocked:
            title = "Blitzkrieg — Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = (f"Blitzkrieg is active — you cannot counter-advance.\n\n"
                       f"Spend your turn on something else. The opponent will select your battle figure.")
        elif has_cannot_be_blocked:
            title = "Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = (f"This figure cannot be blocked — you cannot counter-advance.\n\n"
                       f"Spend your turn on something else (e.g. build figures, cast spells, or manage your hand). "
                       f"After your turn, the opponent will select one of your figures to face them in battle.")
            if modifier_text:
                message_after += f"\n\n{modifier_text}"
        elif 'Civil War' in modifier_types:
            title = "Civil War — Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = (f"Civil War is active — you may counter-advance with up to two village figures of the same color, "
                       f"or spend your turn normally and the opponent will select your battle figures.")
        elif 'Peasant War' in modifier_types:
            title = "Peasant War — Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = (f"Peasant War is active — only village figures may be used for battle.\n\n"
                       f"You can counter-advance with a village figure, or spend your turn normally "
                       f"and the opponent will select your battle figure.")
        else:
            title = "Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = (f"You have two options:\n"
                       f"• Counter-advance: select one of your own figures on the field and advance it. "
                       f"Your figure will face the opponent's figure in battle.\n"
                       f"• Spend your turn normally (build figures, cast spells, etc.). "
                       f"The opponent will then choose which of your figures faces them in battle.")
            if modifier_text:
                message_after += f"\n\n{modifier_text}"
        
        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'images': images if images else None,
            'icon': None if images else "info",
            'title': title,
            'message_after_images': message_after,
            'phase': 'advance',
            'tone': 'warning',
            'spell_names': [m for m in ('Blitzkrieg', 'Civil War', 'Peasant War')
                            if m in modifier_types],
            'event_key': f'opponent_advance:{self.state.game.advancing_figure_id}',
        })
        
        self.state.game.pending_advance_notification = False

    def _clear_stale_conquer_defender_flags_if_no_advance(self):
        game = self.state.game if self.state else None
        if (not game
                or getattr(game, 'mode', 'duel') != 'conquer'
                or getattr(game, 'advancing_figure_id', None)):
            return False
        clear_flags = getattr(game, '_clear_conquer_advance_dependent_flags', None)
        if callable(clear_flags):
            clear_flags()
        else:
            game.pending_defender_selection = False
            game.defender_selection_dialogue_shown = False
            game.pending_waiting_for_defender_pick = False
            game.waiting_for_defender_pick_shown = False
            game.pending_battle_ready = False
            game.battle_ready_shown = False
            game.pending_advance_notification = False
            game.pending_own_advance_notification = False
            game.own_advance_figure_name = None
            if hasattr(game, 'pending_conquer_own_defender_selection'):
                game.pending_conquer_own_defender_selection = False
                game.conquer_own_defender_selection_shown = False
            game.civil_war_awaiting_second = False
            game.civil_war_defender_second = False
            game.civil_war_required_color = None
        return True

    def check_defender_selection_needed(self):
        """Check if the advancing player's turn returned and they need to select a defender."""
        if not self.state.game or not self.state.game.pending_defender_selection:
            return

        if self._clear_stale_conquer_defender_flags_if_no_advance():
            return
        
        # Only proceed when it's actually the player's turn (turn returned from opponent)
        # This prevents showing defender selection immediately after build+advance
        if not self.state.game.turn:
            return
        
        # Don't re-queue if dialogue was already shown
        if self.state.game.defender_selection_dialogue_shown:
            return
        
        # Check if any opponent figure is selectable before showing dialogue
        # If none are eligible, the defender auto-loses
        if not self._check_any_defender_selectable():
            self.state.game.defender_selection_dialogue_shown = True
            self._handle_defender_no_figures_loss()
            return
        
        # Find the advancing figure name(s) and icon(s)
        advancing_figure_name = "your figure"
        advancing_icons = []
        if self.state.game.advancing_figure_id:
            field_screen = self.subscreens.get('field')
            if field_screen:
                for fig in getattr(field_screen, 'figures', []):
                    if fig.id == self.state.game.advancing_figure_id:
                        advancing_figure_name = fig.name
                        break
                # Find the FieldFigureIcon(s) for display
                for icon in getattr(field_screen, 'figure_icons', []):
                    if hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id:
                        advancing_icons.append(icon)
                    if (self.state.game.advancing_figure_id_2 and
                        hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id_2):
                        advancing_icons.append(icon)
                        advancing_figure_name = "your figures"
        
        images = []
        if advancing_icons:
            images.extend(advancing_icons)
        else:
            import os
            icon_path = os.path.join('img', 'figures', 'state_icons', 'charge.png')
            if os.path.exists(icon_path):
                advance_img = pygame.image.load(icon_path).convert_alpha()
                images.append(advance_img)
        
        # Build message with battle modifier context
        base_msg = f"Your opponent did not counter-advance.\n\nSelect one of your opponent's figures to face {advancing_figure_name} in battle."
        
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        
        if 'Peasant War' in modifier_types:
            base_msg += "\n\nPeasant War is active — you may only select village figures."
        elif 'Civil War' in modifier_types:
            base_msg += "\n\nCivil War is active — you may only select village figures."
        
        modifier_text, modifier_icons = self._get_battle_modifier_info()
        images.extend(modifier_icons)
        
        self.queue_or_show_notification({
            'message': base_msg,
            'actions': ['got it!'],
            'images': images if images else None,
            'icon': None if images else "info",
            'title': "Select Opponent's Defender",
            'phase': 'defender',
            'tone': 'action',
            'spell_names': [m for m in ('Civil War', 'Peasant War')
                            if m in modifier_types],
            'event_key': f'select_defender:{self.state.game.advancing_figure_id}',
        })
        
        # Prevent re-queuing on subsequent update cycles
        self.state.game.defender_selection_dialogue_shown = True

    def _handle_forced_advance_dialogue_response(self):
        """Handle response from forced advance confirmation — switch to field screen."""
        self.state.subscreen = 'field'
    
    def check_conquer_own_defender_selection(self):
        """After a conquer Invader Swap blockable advance, prompt the original
        conquerer to select one of their own figures as their defender."""
        if not self.state.game or not self.state.game.pending_conquer_own_defender_selection:
            return
        if self._clear_stale_conquer_defender_flags_if_no_advance():
            return
        if self.state.game.conquer_own_defender_selection_shown:
            return

        self.state.game.conquer_own_defender_selection_shown = True

        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        restriction_note = ""
        if 'Civil War' in modifier_types:
            restriction_note = "\n\nCivil War is active — only village figures may defend."
        elif 'Peasant War' in modifier_types:
            restriction_note = "\n\nPeasant War is active — only village figures may defend."

        message = (
            f"Invader Swap — Choose Your Defender\n\n"
            f"The opponent has advanced. Select one of your own figures to defend against them.\n\n"
            f"Fortresses may also defend if legal.{restriction_note}"
        )
        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'icon': 'info',
            'title': 'Invader Swap — Choose Defender',
            'phase': 'defender',
            'tone': 'action',
            'spell_names': ['Invader Swap'],
            'event_key': f"invader_swap_own_defender:{getattr(self.state.game, 'game_id', 'local')}",
        })

    def check_waiting_for_defender_pick(self):
        """Check if defender (Player B) should be notified that opponent is picking their battle figure.
        Instead of a click-through dialogue, we just activate the persistent 'BATTLE INCOMING' prompt."""
        if not self.state.game or not self.state.game.pending_waiting_for_defender_pick:
            return
        if self._clear_stale_conquer_defender_flags_if_no_advance():
            return
        
        # Don't re-activate if already shown
        if self.state.game.waiting_for_defender_pick_shown:
            return
        
        # Activate persistent prompt directly (no click-through dialogue)
        self.state.game.waiting_for_defender_pick_shown = True
    
    def check_battle_ready(self):
        """Check if both advancing and defending figures are set — battle is ready to begin.
        Sequential flow: invader (advancing player) decides first, then defender.
        Handles reconnect: skips dialogue if server already has our decision or battle_confirmed."""
        if not self.state.game or not self.state.game.pending_battle_ready:
            return
        
        # Don't re-queue if already shown
        if self.state.game.battle_ready_shown:
            return
        
        logger.info(f"[CHECK_BATTLE_READY] Firing: advancing={self.state.game.advancing_figure_id}, "
              f"defending={self.state.game.defending_figure_id}, "
              f"is_advancing={self.state.game.advancing_player_id == self.state.game.player_id}, "
              f"dialogue_box={'yes' if self.dialogue_box else 'no'}")
        
        # ── Reconnect guard: battle already confirmed on server ──
        if self.state.game.battle_confirmed:
            self.state.game.battle_ready_shown = True
            self.state.game.pending_battle_ready = False

            bmc = self.state.game.battle_moves_confirmed or {}
            player_ids = [str(p['id']) for p in self.state.game.players]
            both_moves_ready = all(bmc.get(pid) for pid in player_ids)
            battle_started = both_moves_ready and self.state.game.battle_turn_player_id is not None
            my_moves_ready = bmc.get(str(self.state.game.player_id))

            if battle_started:
                # Both players already confirmed moves — go straight to battle
                self.battle_button.locked = False
                self.state.subscreen = 'battle'
                logger.info("[BATTLE_READY] Reconnect: both moves confirmed — entering battle screen")
            elif my_moves_ready:
                # We confirmed but opponent hasn't — go to battle shop in waiting mode
                self.battle_button.locked = True
                self.state.game.battle_moves_phase = True
                self.state.game.battle_moves_ready = True
                self.state.game.waiting_for_opponent_battle_moves = True
                self.state.subscreen = 'battle_shop'
                shop = self.subscreens.get('battle_shop')
                if shop:
                    shop._load_bought_moves()
                    shop._battle_moves_confirmed = True
                    shop._waiting_for_opponent = True
                logger.info("[BATTLE_READY] Reconnect: our moves confirmed — waiting for opponent")
            else:
                # Neither confirmed yet — enter battle shop normally
                self.battle_button.locked = True
                self.state.game.auto_proceed_to_battle = True
                logger.info("[BATTLE_READY] Reconnect: battle confirmed, moves not yet selected")
            return
        
        # ── Reconnect guard: we already submitted our decision ──
        decisions = self.state.game.battle_decisions or {}
        my_decision = decisions.get(str(self.state.game.player_id))
        if my_decision == 'battle':
            self.state.game.battle_ready_shown = True
            self.state.game.waiting_for_battle_decision = True
            logger.info("[BATTLE_READY] Reconnect: our decision already recorded — resuming wait")
            return
        
        # ── Conquer mode: auto-fight (no fight/fold dialogue) ──
        if self.state.game.mode == 'conquer':
            self.state.game.battle_ready_shown = True

            is_invader = (self.state.game.advancing_player_id == self.state.game.player_id)
            if not is_invader:
                decisions = self.state.game.battle_decisions or {}
                invader_decided = (
                    decisions.get(str(self.state.game.advancing_player_id)) == 'battle'
                )
                if not invader_decided:
                    # Invader Swap can make the human the defender in conquer
                    # mode. The server still enforces invader-first battle
                    # decisions, so wait for the automated invader instead of
                    # submitting a defender decision that would be rejected.
                    # Keep pending_battle_ready latched: once battle_decisions
                    # carries the invader's entry, polls can no longer re-set
                    # it, so clearing it here would stall the game forever.
                    self.state.game.battle_ready_shown = False
                    logger.info(
                        "[BATTLE_READY] Conquer defender waiting for invader "
                        "battle decision"
                    )
                    return

            if is_invader:
                # Check for Blitzkrieg (invader already selected defender's figure)
                modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
                has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)

                defender_counter_advanced = bool(self.state.game.defending_figure_id)

                # Check for defender counter-spell (enchantment, NOT greed).
                # Filter out spells already seen during conquer startup so
                # prelude effects are not announced again as counter spells.
                all_counter_spells = [
                    s for s in (getattr(self.state.game, 'cached_active_spells', []) or [])
                    if s.get('player_id') != self.state.game.player_id
                    and s.get('spell_name') not in ('Draw 2 MainCards', 'Fill up to 10', 'Dump Cards')
                ]

                seen_spell_ids = set(getattr(self, '_seen_conquer_opponent_spell_ids', set()) or set())
                counter_spells = []
                for spell_data in all_counter_spells:
                    spell_id = spell_data.get('id')
                    if spell_id is None or spell_id not in seen_spell_ids:
                        counter_spells.append(spell_data)

                current_opponent_spell_ids = {
                    s.get('id') for s in all_counter_spells if s.get('id') is not None
                }
                if current_opponent_spell_ids:
                    self._seen_conquer_opponent_spell_ids.update(current_opponent_spell_ids)

                if defender_counter_advanced and not has_blitzkrieg:
                    # (7) No counter spell — defender counter-advanced.
                    # Keep defender identity hidden: show field category + card count.
                    images = []
                    field_screen = self.subscreens.get('field')
                    defending_description = "a hidden figure"
                    if field_screen and self.state.game.defending_figure_id:
                        for fig in getattr(field_screen, 'figures', []):
                            if fig.id == self.state.game.defending_figure_id:
                                field_key = getattr(fig.family, 'field', 'unknown') if hasattr(fig, 'family') else 'unknown'
                                field_map = {
                                    'castle': 'Castle',
                                    'village': 'Village',
                                    'military': 'Military',
                                }
                                field_label = field_map.get(str(field_key).lower(), str(field_key).title())
                                card_count = len(fig.cards) if hasattr(fig, 'cards') else '?'
                                defending_description = f"a hidden {field_label} figure with {card_count} cards"
                                break

                        for icon in getattr(field_screen, 'figure_icons', []):
                            if hasattr(icon, 'figure') and icon.figure.id == self.state.game.defending_figure_id:
                                hidden_icon = getattr(icon, 'frame_hidden_img', None)
                                if hidden_icon is not None:
                                    images.append(hidden_icon.copy())
                                break

                    if not images:
                        import os
                        icon_path = os.path.join('img', 'figures', 'state_icons', 'charge_opponent.png')
                        if os.path.exists(icon_path):
                            images.append(pygame.image.load(icon_path).convert_alpha())

                    self.queue_or_show_notification({
                        'message': f"The defender counter-advanced with {defending_description}!",
                        'actions': ['ok'],
                        'images': images if images else None,
                        'icon': None if images else 'info',
                        'title': 'Defender Response',
                        'phase': 'defender',
                        'tone': 'warning',
                        'event_key': f'defender_response:{self.state.game.defending_figure_id}',
                    })

                elif counter_spells:
                    # (6) Defender cast a counter spell — show turn notification
                    opponent_name = self.state.game.opponent_name or "Defender"
                    spell_names = ', '.join(s.get('spell_name', '?') for s in counter_spells)
                    modifier_lines = self._get_modifier_explanation_lines(
                        [s.get('spell_name') for s in counter_spells if self._is_battle_modifier_spell(s.get('spell_name'))]
                    )

                    spell_images = []
                    for s in counter_spells:
                        spell_images.extend(self._get_spell_icon_image(s.get('spell_name', '')))

                    msg_after = f"• Cast {spell_names}"
                    if modifier_lines:
                        msg_after += "\n" + "\n".join(f"  > {line}" for line in modifier_lines)

                    self.queue_or_show_notification({
                        'message': f"{opponent_name}'s turn:",
                        'actions': ['ok'],
                        'images': spell_images if spell_images else None,
                        'icon': None if spell_images else 'info',
                        'title': 'Defender Counter Spell',
                        'message_after_images': msg_after,
                        'phase': 'defender',
                        'tone': 'warning',
                        'spell_names': [s.get('spell_name', '') for s in counter_spells],
                        'spell_side': 'opponent',
                        'spell_role': 'counter',
                        'event_key': 'defender_counter:' + ','.join(
                            str(s.get('id') or s.get('spell_name')) for s in counter_spells),
                    })

                    # (8) Defender used last turn for spell — did not counter-advance
                    # Invader must select defender's battle figure (skip if
                    # Blitzkrieg already handled this via check_defender_selection_needed)
                    if not self.state.game.defending_figure_id and not has_blitzkrieg:
                        advancing_figure_name = "your figure"
                        advancing_icons = []
                        field_screen = self.subscreens.get('field')
                        if field_screen and self.state.game.advancing_figure_id:
                            for fig in getattr(field_screen, 'figures', []):
                                if fig.id == self.state.game.advancing_figure_id:
                                    advancing_figure_name = fig.name
                                    break
                            for icon in getattr(field_screen, 'figure_icons', []):
                                if hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id:
                                    advancing_icons.append(icon)
                                    break

                        sel_images = advancing_icons if advancing_icons else None
                        self.queue_or_show_notification({
                            'message': (f"The defender did not counter-advance.\n\n"
                                        f"Select one of the defender's figures to face "
                                        f"{advancing_figure_name} in battle."),
                            'actions': ['got it!'],
                            'images': sel_images,
                            'icon': None if sel_images else 'info',
                            'title': "Select Opponent's Defender",
                            'phase': 'defender',
                            'tone': 'action',
                            'event_key': f'defender_no_counter:{self.state.game.advancing_figure_id}',
                        })

            logger.info("[BATTLE_READY] Conquer mode — auto-submitting 'battle' decision")
            self.state.game.pending_battle_ready = False
            self._submit_battle_decision('battle')
            return
        
        is_advancing = (self.state.game.advancing_player_id == self.state.game.player_id)
        
        # Find the advancing and defending figure icons from the field screen
        advancing_icons = []
        defending_icons = []
        field_screen = self.subscreens.get('field')
        if field_screen:
            for icon in getattr(field_screen, 'figure_icons', []):
                if icon.figure.id == self.state.game.advancing_figure_id:
                    advancing_icons.append(icon)
                if self.state.game.advancing_figure_id_2 and icon.figure.id == self.state.game.advancing_figure_id_2:
                    advancing_icons.append(icon)
                if icon.figure.id == self.state.game.defending_figure_id:
                    defending_icons.append(icon)
                if self.state.game.defending_figure_id_2 and icon.figure.id == self.state.game.defending_figure_id_2:
                    defending_icons.append(icon)
        
        # Own figures always on the left, with "vs." separator between groups
        # Create a "vs." text surface at the target image height to avoid distortion
        target_height = settings.DIALOGUE_BOX_IMG_HEIGHT
        vs_font_size = max(12, target_height // 3)
        vs_font = settings.get_font(vs_font_size, bold=True)
        vs_text = vs_font.render("vs.", True, settings.TITLE_TEXT_COLOR)
        # Create transparent surface at target height with text centered
        vs_surface = pygame.Surface((vs_text.get_width() + settings.SMALL_SPACER_X * 2, target_height), pygame.SRCALPHA)
        vs_x = (vs_surface.get_width() - vs_text.get_width()) // 2
        vs_y = (target_height - vs_text.get_height()) // 2
        vs_surface.blit(vs_text, (vs_x, vs_y))
        
        if is_advancing:
            images = advancing_icons + [vs_surface] + defending_icons
        else:
            images = defending_icons + [vs_surface] + advancing_icons
        
        # Build description of opponent's figure(s) for the message
        opponent_figure_desc = ""
        if field_screen:
            opponent_fig_ids = []
            if is_advancing:
                # Invader's opponent is the defender
                opponent_fig_ids.append(self.state.game.defending_figure_id)
                if self.state.game.defending_figure_id_2:
                    opponent_fig_ids.append(self.state.game.defending_figure_id_2)
            else:
                # Defender's opponent is the invader
                opponent_fig_ids.append(self.state.game.advancing_figure_id)
                if self.state.game.advancing_figure_id_2:
                    opponent_fig_ids.append(self.state.game.advancing_figure_id_2)
            
            fig_descs = []
            for fig_id in opponent_fig_ids:
                for fig in getattr(field_screen, 'figures', []):
                    if fig.id == fig_id:
                        field_type = getattr(fig.family, 'field', 'unknown') if hasattr(fig, 'family') else 'unknown'
                        card_count = len(fig.cards) if hasattr(fig, 'cards') else '?'
                        fig_descs.append(f"a {field_type} figure with {card_count} cards")
                        break
            if fig_descs:
                opponent_figure_desc = f"\n\nYour opponent's figure: {', and '.join(fig_descs)}."
        
        if is_advancing:
            # --- Invader sees fight/fold dialogue immediately ---
            self.battle_button.locked = False
            
            message = ("Both battle figures have been selected!\n\n"
                       "You are the attacker."
                       f"{opponent_figure_desc}\n\n"
                       "Do you want to fight or fold?")
            
            self.queue_or_show_notification({
                'message': message,
                'actions': ['to battle!', 'fold'],
                'images': images if images else None,
                'icon': None if images else 'magic',
                'title': "Battle Phase Begins"
            })
            
            if field_screen:
                field_screen.defender_selection_mode = False
                field_screen._reset_defender_selectable()
            
            self.state.game.battle_ready_shown = True
        else:
            # --- Defender: wait for invader's decision first ---
            decisions = self.state.game.battle_decisions or {}
            invader_decided = decisions.get(str(self.state.game.advancing_player_id)) == 'battle'
            
            if not invader_decided:
                # Invader hasn't decided yet — waiting prompt is drawn in draw()
                return
            
            # Invader chose to fight — now show fight/fold dialogue to defender
            self.battle_button.locked = False
            
            message = ("Both battle figures have been selected!\n\n"
                       "You are the defender.\n\n"
                       "The invader has chosen to fight."
                       f"{opponent_figure_desc}\n\n"
                       "Do you want to fight or fold?")
            
            self.queue_or_show_notification({
                'message': message,
                'actions': ['to battle!', 'fold'],
                'images': images if images else None,
                'icon': None if images else 'magic',
                'title': "Battle Phase Begins"
            })
            
            if field_screen:
                field_screen.defender_selection_mode = False
                field_screen._reset_defender_selectable()
            
            self.state.game.battle_ready_shown = True
    
    def _submit_battle_decision(self, decision):
        """Submit a battle decision (battle or fold) to the server and handle the response."""
        if getattr(self.state.game, 'game_over', False):
            return
        from utils.game_service import battle_decision
        result = battle_decision(self.state.game.game_id, self.state.game.player_id, decision)
        
        if not result.get('success'):
            logger.error(f"[GAME_SCREEN] Battle decision failed: {result.get('message')}")
            # Check if the failure is because our decision was already recorded
            # (reconnect scenario).  If so, resume waiting for the opponent.
            # Otherwise (network error, server down), allow the fight/fold
            # dialogue to re-appear so the user can retry.
            reason = result.get('reason', '')
            if reason == 'already_decided' or 'already' in str(result.get('message', '')).lower():
                if decision == 'battle':
                    self.state.game.waiting_for_battle_decision = True
            else:
                # Network/server error — let the dialogue re-appear
                self.state.game.battle_ready_shown = False
                logger.error("[GAME_SCREEN] Battle decision POST failed — will re-show fight/fold dialogue")
            return
        
        if result.get('resolved'):
            outcome = result.get('outcome')
            if result.get('conquer_result'):
                self._handle_conquer_result_response(result)
                return
            if outcome == 'battle':
                # Both chose to fight — go to battle shop for move selection
                if result.get('game'):
                    self.state.game.update_from_dict(result['game'])
                self._enter_battle_moves_phase()
            elif outcome == 'fold_win':
                # One player folded
                if result.get('game'):
                    self.state.game.update_from_dict(result['game'])
                self._reset_battle_state()

                # Check for game-over
                if result.get('game_over'):
                    self.state.game.fold_result_shown = True
                    self._show_game_over_dialogue(result['game_over'])
                    return
                
                winner = result.get('winner', 'Opponent')
                loser = result.get('loser', 'You')
                points = result.get('points', 10)
                new_round = self.state.game.current_round
                
                if self.state.game.fold_winner_id == self.state.game.player_id:
                    title = "Victory!"
                    message = (f"{loser} has folded!\n\n"
                               f"You win {points} points.\n\n"
                               f"You are now the invader.\n\n"
                               f"Round {new_round} begins. It's your turn!")
                else:
                    title = "Defeat"
                    message = (f"You have folded.\n\n"
                               f"{winner} wins {points} points and is now the invader.\n\n"
                               f"Round {new_round} begins. {winner} starts the new round.")
                
                self.state.game.fold_result_shown = True
                self.queue_or_show_notification({
                    'message': message,
                    'actions': ['ok'],
                    'icon': 'magic',
                    'title': title
                })
        else:
            # Waiting for opponent's decision (invader chose battle, waiting for defender)
            self.state.game.waiting_for_battle_decision = True

    def _can_submit_battle_decision(self):
        """Return True if local state represents an unresolved battle decision phase."""
        game = self.state.game
        if not game:
            return False
        if not game.advancing_figure_id or not game.defending_figure_id:
            return False
        if game.battle_confirmed or game.fold_outcome:
            return False
        return True

    def _reset_battle_state(self):
        """Reset all battle-related state after fold or loss."""
        self.state.game.pending_battle_ready = False
        # Keep battle_ready_shown = True so stale in-flight polls can't
        # re-trigger the fight/fold dialogue.  It's reset by _apply_game_dict
        # when the server clears advancing_figure_id (new round).
        self.state.game.battle_ready_shown = True
        self.state.game.pending_forced_advance = False
        self.state.game.forced_advance_dialogue_shown = False
        self.state.game.pending_defender_selection = False
        self.state.game.defender_selection_dialogue_shown = False
        self.state.game.pending_waiting_for_defender_pick = False
        self.state.game.waiting_for_defender_pick_shown = False
        # Clear fold result flag so it doesn't suppress future turn notifications
        self.state.game.pending_fold_result = False
        # Suppress the next turn notification only if it's our turn now.
        # The fold/battle result dialogue already told us everything; the
        # immediate _handle_start_turn would just repeat it.  But if it's
        # the opponent's turn, our first _handle_start_turn fires only after
        # they complete an action — that's a genuine notification we must show.
        self.state.game.suppress_next_turn_summary = bool(self.state.game.turn)
        self.state.game.civil_war_awaiting_second = False
        self.state.game.civil_war_defender_second = False
        self.state.game.civil_war_required_color = None
        self.state.game.waiting_for_battle_decision = False
        self.state.game.auto_proceed_to_battle = False
        # Reset battle moves phase state
        self.state.game.battle_moves_phase = False
        self.state.game.battle_moves_ready = False
        self.state.game.waiting_for_opponent_battle_moves = False
        self.state.game.both_battle_moves_ready = False
        # Reset active battle phase state
        self.state.game.in_battle_phase = False
        self.state.game.battle_turns_left = 0
        # Clear stale ceasefire-ended flag
        self.state.game.pending_ceasefire_ended = False
        # Queue ceasefire-active notification for the new round
        # (only if not already displayed this round)
        if self.state.game.ceasefire_active and self.state.game._ceasefire_active_displayed_round != self.state.game.current_round:
            logger.info(f"[CEASEFIRE] _reset_battle_state: queuing ceasefire-active, round={self.state.game.current_round}")
            self.state.game.pending_ceasefire_active_notification = True
            # Mark as notified so polling doesn't re-trigger
            self.state.game._ceasefire_notified_round = self.state.game.current_round
            self.state.game._ceasefire_notified_state = 'active'
        # Sync modifier tracking to current state so stale poll data that still
        # contains the old modifier doesn't look "new" after we clear the list
        current = self.state.game.battle_modifier
        self._previous_battle_modifiers = list(current) if isinstance(current, list) else []
        # Discard any stale poller result so old server data (with modifier/
        # ceasefire still active) doesn't re-trigger notifications
        if self._game_poller and self._game_poller.has_result():
            _ = self._game_poller.result
            self._game_poller.invalidate_cache()
        
        self.battle_button.locked = True
        
        # Force battle shop to reload moves from server (deleted after battle)
        battle_shop = self.subscreens.get('battle_shop')
        if battle_shop:
            battle_shop.bought_moves = []
            battle_shop._loaded_game_key = None
            battle_shop._battle_moves_confirmed = False
            battle_shop._waiting_for_opponent = False
        
        field_screen = self.subscreens.get('field')
        if field_screen:
            field_screen.defender_selection_mode = False
            field_screen._reset_defender_selectable()
            field_screen.load_figures()

    def check_fold_result(self):
        """Check if a fold outcome was detected via polling (for the waiting player)."""
        if not self.state.game:
            return

        # Safety net: fold_outcome is set but pending_fold_result was never
        # triggered (e.g. update_from_dict overwrote fold_outcome before
        # _apply_game_dict could detect the transition).
        if (not self.state.game.pending_fold_result and
                self.state.game.fold_outcome and
                self.state.game.waiting_for_battle_decision and
                not self.state.game.fold_result_shown):
            logger.warning("[FOLD] Safety net: fold_outcome set but pending_fold_result "
                  "missed — forcing fold result")
            self.state.game.pending_fold_result = True
            self.state.game.waiting_for_battle_decision = False

        if not self.state.game.pending_fold_result:
            return
        if self.state.game.fold_result_shown:
            return
        
        self._reset_battle_state()
        
        fold_outcome = self.state.game.fold_outcome
        fold_winner_id = self.state.game.fold_winner_id
        new_round = self.state.game.current_round
        opponent_name = self.state.game.opponent_name or "Opponent"
        auto_loss_reason = self.state.game.auto_loss_reason
        auto_loss_detail = self.state.game.auto_loss_detail or ""
        
        if fold_outcome != 'fold_win':
            return
        
        is_winner = (fold_winner_id == self.state.game.player_id)
        
        if is_winner:
            # Build victory message based on the reason
            if auto_loss_reason == 'no_figures_to_advance':
                reason_text = f"{opponent_name} had no figures that could advance!"
            elif auto_loss_reason == 'no_defender_figures':
                reason_text = f"{opponent_name} had no valid figures for battle!"
            elif auto_loss_reason == 'resource_deficit':
                fig_name = auto_loss_detail if auto_loss_detail else "a figure"
                reason_text = f"{opponent_name}'s {fig_name} has a resource deficit and cannot fight!"
            elif auto_loss_reason == 'fold':
                reason_text = f"{opponent_name} has folded!"
            else:
                reason_text = f"{opponent_name} has folded!"
            
            title = "Victory!"
            message = (f"{reason_text}\n\n"
                       f"You win 10 points.\n\n"
                       f"You are now the invader.\n\n"
                       f"Round {new_round} begins. It's your turn!")
        else:
            # Build defeat message based on the reason
            if auto_loss_reason == 'no_figures_to_advance':
                reason_text = "You had no figures that could advance!"
            elif auto_loss_reason == 'no_defender_figures':
                reason_text = "You had no valid figures for battle!"
            elif auto_loss_reason == 'resource_deficit':
                fig_name = auto_loss_detail if auto_loss_detail else "Your figure"
                reason_text = f"Your {fig_name} has a resource deficit and cannot fight!"
            elif auto_loss_reason == 'fold':
                reason_text = f"You folded against {opponent_name}."
            else:
                reason_text = "You lost the battle."
            
            title = "Defeat"
            message = (f"{reason_text}\n\n"
                       f"{opponent_name} wins 10 points and is now the invader.\n\n"
                       f"Round {new_round} begins. {opponent_name} starts the new round.")
        
        self.state.game.fold_result_shown = True
        self.state.game.pending_fold_result = False
        
        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'icon': 'magic',
            'title': title
        })

    def check_pending_battle_choice_timeout(self):
        """Resolve expired post-battle choices with the server default."""
        game = self.state.game
        if not game or getattr(game, 'game_over', False):
            return
        if getattr(game, 'mode', 'duel') == 'conquer':
            return
        local_player_id = getattr(game, 'player_id', None)
        if local_player_id is None:
            return

        last = getattr(game, 'last_battle_result', None) or {}
        if not isinstance(last, dict):
            return

        # Surface a "defaulted" notice once even after the server already
        # cleared the pending choice (covers the path where the opposite
        # client triggered the default first).
        if last.get('post_battle_choice_defaulted'):
            seen_key = (last.get('post_battle_choice'), id(last))
            if getattr(game, '_pending_choice_defaulted_seen', None) != seen_key:
                game._pending_choice_defaulted_seen = seen_key
                self.queue_or_show_notification({
                    'message': 'A post-battle choice timed out and was resolved with the default.',
                    'actions': ['ok'],
                    'icon': 'magic',
                    'title': 'Battle Choice Defaulted',
                })

        pending = last.get('post_battle_pending_choice')
        if not pending:
            return

        pending_key = (pending.get('type'), pending.get('player_id'), pending.get('deadline_at'))
        if getattr(game, '_pending_choice_resolve_inflight', False):
            return

        deadline_raw = pending.get('deadline_at')
        try:
            deadline = datetime.fromisoformat(deadline_raw) if deadline_raw else None
            expired = bool(deadline and datetime.utcnow() >= deadline)
        except Exception:
            expired = False

        if not expired:
            if getattr(game, '_pending_choice_notice_key', None) != pending_key:
                game._pending_choice_notice_key = pending_key
                pending_player_id = pending.get('player_id')
                if (pending_player_id is not None
                        and pending_player_id != local_player_id):
                    choice_type = pending.get('type')
                    if choice_type == 'draw_choice':
                        msg = "Waiting for the defender to choose the draw reward. A default will apply if they do not respond."
                    else:
                        msg = "Waiting for the battle winner to pick a card. A default will apply if they do not respond."
                    self.queue_or_show_notification({
                        'message': msg,
                        'actions': ['ok'],
                        'icon': 'info',
                        'title': 'Waiting for Battle Choice',
                    })
            return

        # Cooldown: avoid retrying the resolve endpoint every frame on
        # transient failures or while the network round-trip is slow.
        now_ts = datetime.utcnow().timestamp()
        last_attempt = getattr(game, '_pending_choice_last_attempt_ts', 0.0)
        if now_ts - last_attempt < 5.0:
            return
        game._pending_choice_last_attempt_ts = now_ts

        from utils import game_service
        game._pending_choice_resolve_inflight = True
        try:
            result = game_service.resolve_pending_battle_choice(
                game.game_id, local_player_id
            )
        finally:
            game._pending_choice_resolve_inflight = False

        if result.get('success'):
            if result.get('game'):
                game.update_from_dict(result['game'])
            if result.get('defaulted'):
                self._reset_battle_state()
                self.queue_or_show_notification({
                    'message': result.get('message', 'Post-battle choice defaulted.'),
                    'actions': ['ok'],
                    'icon': 'magic',
                    'title': 'Battle Choice Defaulted',
                })
        elif result.get('reason') != 'pending_choice_not_expired':
            logger.warning(f"[POST_BATTLE_DEFAULT] Failed: {result.get('message')}")

    def check_game_over(self):
        """Check if the game has ended (detected via polling or response)."""
        if not self.state.game:
            return
        if self.state.game.game_over_shown:
            return
        if self.state.game.pending_game_over:
            self._show_game_over_dialogue(self.state.game.pending_game_over)

    def _card_line(self, card):
        if not isinstance(card, dict):
            return None
        rank = card.get('rank')
        suit = card.get('suit')
        if rank and suit:
            return f"{rank} of {suit}"
        if rank:
            return str(rank)
        if suit:
            return str(suit)
        return None

    def _card_lines(self, cards, max_lines=10):
        lines = []
        for card in cards or []:
            label = self._card_line(card)
            if label:
                lines.append(label)
        if len(lines) <= max_lines:
            return lines
        overflow = len(lines) - max_lines
        return lines[:max_lines] + [f"... and {overflow} more"]

    def _card_images(self, cards, max_images=4):
        from game.components.cards.card_img import CardImg

        images = []
        valid_cards = 0
        for card in cards or []:
            if not isinstance(card, dict):
                continue
            rank = card.get('rank')
            suit = card.get('suit')
            if not rank or not suit:
                continue
            valid_cards += 1
            if len(images) >= max_images:
                continue
            try:
                images.append(CardImg(self.window, suit, rank).front_img)
            except Exception:
                logger.warning(
                    "[CONQUER_RESULT] Failed to load loot card image for %s of %s",
                    rank,
                    suit,
                    exc_info=True,
                )
        return images, valid_cards

    def _auto_loss_reason_text(self, result):
        reason = result.get('auto_loss_reason')
        detail = result.get('auto_loss_detail') or ''
        if reason == 'no_figures_to_advance':
            return 'No figure could legally advance, so the attack was forfeited.'
        if reason == 'no_defender_figures':
            return 'The defender had no legal battle figure, so the defence was forfeited.'
        if reason == 'resource_deficit':
            name = detail or 'A selected figure'
            return f'{name} had a resource deficit and could not fight.'
        if reason == 'fold':
            return 'The battle was forfeited by fold.'
        if reason == 'withdraw':
            name = detail or 'The attacker'
            return f'{name} withdrew from the conquest.'
        return ''

    def _derive_finished_conquer_result(self):
        game = self.state.game if self.state else None
        if not game or game.mode != 'conquer' or game.state != 'finished':
            return None

        last = getattr(game, 'last_battle_result', None) or getattr(
            game, '_last_polled_battle_result', {}) or {}
        conquer_result = last.get('conquer_result')
        attacker_won = last.get('attacker_won')
        if conquer_result == 'draw' or game.winner_player_id is None:
            conquer_result = 'draw'
            attacker_won = False
        elif conquer_result in ('attacker_won', 'defender_won'):
            attacker_won = (conquer_result == 'attacker_won')
        else:
            attacker_player_id = last.get('conquer_attacker_player_id') or getattr(
                game, 'invader_player_id', None)
            attacker_won = bool(attacker_player_id and game.winner_player_id == attacker_player_id)
            conquer_result = 'attacker_won' if attacker_won else 'defender_won'

        result = {
            'success': True,
            'already_resolved': True,
            'conquer_result': conquer_result,
            'attacker_won': bool(attacker_won),
            'land_id': getattr(game, 'land_id', None),
            'land_tier': getattr(game, 'land_tier', None),
            'land_gold_rate': getattr(game, 'land_gold_rate', 0),
            'auto_loss_reason': last.get('auto_loss_reason'),
            'auto_loss_detail': last.get('auto_loss_detail'),
            'card_won_suit': last.get('card_won_suit'),
            'card_won_rank': last.get('card_won_rank'),
            'card_lost_suit': last.get('card_lost_suit'),
            'card_lost_rank': last.get('card_lost_rank'),
            'loot_gained_cards': last.get('conquer_loot_gained_cards') or last.get('loot_gained_cards') or [],
            'loot_lost_cards': last.get('conquer_loot_lost_cards') or last.get('loot_lost_cards') or [],
            'consumed_cards': last.get('conquer_consumed_cards') or last.get('consumed_cards') or [],
            'defence_consumed_cards': last.get('defence_consumed_cards') or [],
            'cards_spent': last.get('cards_spent'),
            'is_ai_defender': bool(last.get('is_ai_defender')),
            'conquer_attacker_player_id': last.get('conquer_attacker_player_id'),
            'conquer_defender_player_id': last.get('conquer_defender_player_id'),
            'fig_diff': last.get('fig_diff'),
            'round_diff': last.get('round_diff'),
            'adv_power': last.get('adv_power'),
            'def_power': last.get('def_power'),
        }
        return result

    def _handle_conquer_result_response(self, result):
        """Show conquer resolution from non-battle-screen server responses."""
        if not result or not result.get('conquer_result') or not self.state.game:
            return False

        if result.get('game'):
            self.state.game.update_from_dict(result['game'])

        game = self.state.game
        if getattr(game, '_conquer_result_dialogue_shown', False):
            return True

        game._conquer_result_dialogue_shown = True
        game.game_over = True
        game.conquer_result = result.get('conquer_result')
        self._reset_battle_state()

        attacker_won = bool(result.get('attacker_won'))
        conquer_result = result.get('conquer_result')
        is_attacker = self._is_current_player_conquer_attacker(result)

        # Stash Victory Review handoff so the game-over ack handler can route
        # the attacker to DefenceScreen after the result dialogue closes.
        # Mirrors the path in battle_screen._handle_conquer_end so auto-loss
        # outcomes (defender no figures, withdrawal, deficit, fold) also
        # trigger the review.
        if attacker_won and is_attacker:
            game._pending_victory_review = {
                'available': bool(result.get('victory_review_available')),
                'land_id': result.get('victory_review_land_id'),
                'config_id': result.get('victory_review_config_id'),
            }
        else:
            game._pending_victory_review = None
        reason_text = self._auto_loss_reason_text(result)
        images = []
        after_messages = []

        if conquer_result == 'draw':
            title = 'Draw!'
            icon = 'draw'
            message = (
                'The battle ended in a draw.\n\n'
                'The land remains unchanged. No cards were looted; all attack cards returned to your collection.'
            )
        elif attacker_won and is_attacker:
            land_tier = result.get('land_tier') or getattr(game, 'land_tier', None)
            gold_rate = result.get('land_gold_rate', 0) or 0
            land_label = f'Tier {land_tier} land' if land_tier else 'this land'
            title = 'Land Conquered!'
            icon = 'victory'
            # First conquest is a milestone — celebrate it (the dialog already
            # plays the conquer_win fanfare via sound.play_for_dialogue).
            _onboarding = (getattr(self.state, 'user_dict', None) or {}).get('onboarding') or {}
            _first_conquest = ('finish_first_conquer_battle'
                               not in set(_onboarding.get('completed_steps') or []))
            if _first_conquest:
                message = (f'Your first land is yours! You conquered {land_label}, '
                           'and this kingdom now grows from the map. '
                           'Next, return to your kingdom to finish the conquer tutorial.')
            else:
                message = f'You have conquered {land_label}!'
            if gold_rate:
                message += f'\n\nGold production increased by {gold_rate:.1f} gold/hour.'
            loot_cards = result.get('loot_gained_cards') or result.get('loot_lost_cards') or []
            loot_images, loot_count = self._card_images(loot_cards)
            if loot_images:
                images.extend(loot_images)
                message += '\n\nLoot gained (pending collection):'
                if loot_count > len(loot_images):
                    after_messages.append(
                        f'Showing {len(loot_images)} of {loot_count} looted cards.'
                    )
                after_messages.append(
                    'Collect looted cards from the Loot Inbox in your kingdom configuration.'
                )
            else:
                loot_lines = self._card_lines(loot_cards)
                if loot_lines:
                    message += '\n\nLoot gained (pending collection):\n' + '\n'.join(
                        f'• {line}' for line in loot_lines)
                    message += '\n\nCollect looted cards from the Loot Inbox in your kingdom configuration.'
        elif attacker_won and not is_attacker:
            title = 'Land Lost!'
            icon = 'defeat'
            message = 'The attacker has conquered your land.'
            loot_cards = result.get('loot_lost_cards') or result.get('loot_gained_cards') or []
            loot_images, loot_count = self._card_images(loot_cards)
            if loot_images:
                images.extend(loot_images)
                message += '\n\nLoot lost:'
                if loot_count > len(loot_images):
                    after_messages.append(
                        f'Showing {len(loot_images)} of {loot_count} looted cards.'
                    )
                after_messages.append('Every unlooted defence card returned to your collection.')
            else:
                loot_lines = self._card_lines(loot_cards)
                if loot_lines:
                    message += '\n\nLoot lost:\n' + '\n'.join(
                        f'• {line}' for line in loot_lines)
                message += '\n\nEvery unlooted defence card returned to your collection.'
        elif not attacker_won and is_attacker:
            title = 'Attack Failed'
            icon = 'defeat'
            message = 'You did not conquer this land.'
            is_ai_defender = bool(result.get('is_ai_defender'))
            loot_cards = result.get('loot_lost_cards') or []
            loot_images, loot_count = self._card_images(loot_cards)
            if loot_images:
                images.extend(loot_images)
                loot_title = 'Cards destroyed by AI defence:' if is_ai_defender else 'Cards looted by defending kingdom:'
                message += f'\n\n{loot_title}'
                if loot_count > len(loot_images):
                    after_messages.append(
                        f'Showing {len(loot_images)} of {loot_count} looted cards.'
                    )
                after_messages.append('Every unlooted attack card returned to your collection.')
            else:
                loot_lines = self._card_lines(loot_cards)
                if loot_lines:
                    loot_title = 'Cards destroyed by AI defence:' if is_ai_defender else 'Cards looted by defending kingdom:'
                    message += f'\n\n{loot_title}\n' + '\n'.join(
                        f'• {line}' for line in loot_lines)
                message += '\n\nEvery unlooted attack card returned to your collection.'
        else:
            title = 'Defence Successful!'
            icon = 'victory'
            message = 'You defended your land successfully!'
            loot_cards = result.get('loot_gained_cards') or result.get('loot_lost_cards') or []
            loot_images, loot_count = self._card_images(loot_cards)
            if loot_images:
                images.extend(loot_images)
                message += '\n\nLoot gained (pending collection):'
                if loot_count > len(loot_images):
                    after_messages.append(
                        f'Showing {len(loot_images)} of {loot_count} looted cards.'
                    )
                after_messages.append(
                    'Collect looted cards from the Loot Inbox in your kingdom configuration.'
                )
            else:
                loot_lines = self._card_lines(loot_cards)
                if loot_lines:
                    message += '\n\nLoot gained (pending collection):\n' + '\n'.join(
                        f'• {line}' for line in loot_lines)
                    message += '\n\nCollect looted cards from the Loot Inbox in your kingdom configuration.'

        breakdown_line = self._conquer_result_breakdown_line(result, is_attacker)
        if breakdown_line:
            message = f'{message}\n\n{breakdown_line}'

        if reason_text:
            message = f'{reason_text}\n\n{message}'

        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'images': images if images else None,
            'icon': icon,
            'title': title,
            'message_after_images': '\n\n'.join(after_messages) if after_messages else None,
            'type': 'game_over',
        })
        return True

    def _is_current_player_conquer_attacker(self, result=None):
        """Return whether the local player is the original conquer attacker.

        In conquer Invader Swap the current invader becomes the automated
        defender, so game.invader no longer identifies the player whose
        conquer config is attacking the land.
        """
        game = self.state.game if self.state else None
        if not game:
            return False

        result = result or {}
        last = getattr(game, 'last_battle_result', None) or getattr(
            game, '_last_polled_battle_result', {}) or {}
        attacker_id = (
            result.get('conquer_attacker_player_id')
            or last.get('conquer_attacker_player_id')
        )
        if attacker_id is not None:
            return str(attacker_id) == str(getattr(game, 'player_id', None))

        active_spells = (
            getattr(game, 'cached_active_spells', None)
            or getattr(game, 'active_spells', None)
            or []
        )
        for spell in active_spells:
            if not isinstance(spell, dict):
                continue
            effect_data = spell.get('effect_data')
            if (spell.get('spell_name') == 'Invader Swap'
                    and isinstance(effect_data, dict)
                    and effect_data.get('conquer_invader_swap')):
                old_invader_id = effect_data.get('old_invader_id')
                if old_invader_id is not None:
                    return str(old_invader_id) == str(getattr(game, 'player_id', None))

        return bool(getattr(game, 'invader', False))

    def _conquer_result_breakdown_line(self, result, is_attacker):
        """One-line figure-vs-tactic split for the conquer result dialog.

        The server stores ``fig_diff`` / ``round_diff`` in attacker
        perspective; flip them for a viewer who defended.  Surfacing this
        teaches players that figure power, not tactics, usually decides a
        conquer battle.  Returns '' when the breakdown is absent (e.g.
        auto-loss / withdrawal outcomes) so the line collapses cleanly.
        """
        if not isinstance(result, dict):
            return ''
        if result.get('fig_diff') is None or result.get('round_diff') is None:
            return ''
        try:
            fig = int(result.get('fig_diff') or 0)
            rounds = int(result.get('round_diff') or 0)
        except (TypeError, ValueError):
            return ''
        if not is_attacker:
            fig = -fig
            rounds = -rounds
        total = fig + rounds

        def _signed(value):
            return f'+{value}' if value >= 0 else str(value)

        return (f'Battle math — Figures {_signed(fig)} · '
                f'Tactics {_signed(rounds)} · Total {_signed(total)}')

    def _try_handle_finished_conquer_game(self):
        """Safety net for finished conquer games resolved outside BattleScreen."""
        game = self.state.game if self.state else None
        if not game or game.mode != 'conquer' or game.state != 'finished':
            return False
        if getattr(game, '_conquer_result_dialogue_shown', False):
            return True
        if getattr(game, '_conquer_battle_ended', False):
            return True
        result = self._derive_finished_conquer_result()
        if not result:
            return False
        return self._handle_conquer_result_response(result)

    def _show_game_over_dialogue(self, game_over_info):
        """Show a game-over dialogue with the result and gold awarded."""
        if self.state.game.game_over_shown:
            return
        self.state.game.game_over = True
        self.state.game.game_over_shown = True
        self.state.game.pending_game_over = game_over_info

        is_winner = (game_over_info.get('winner_player_id') == self.state.game.player_id)

        # Conquer mode: simplified game-over message (fallback path — normally
        # handled by battle_screen._handle_conquer_end with richer data)
        if self.state.game.mode == 'conquer':
            winner_pid = game_over_info.get('winner_player_id')
            is_attacker = self._is_current_player_conquer_attacker(game_over_info)
            # Stash Victory Review handoff for the checkmate-driven path.
            if is_winner and is_attacker:
                self.state.game._pending_victory_review = {
                    'available': bool(game_over_info.get('victory_review_available')),
                    'land_id': game_over_info.get('victory_review_land_id'),
                    'config_id': game_over_info.get('victory_review_config_id'),
                }
            else:
                self.state.game._pending_victory_review = None
            if winner_pid is None:
                # Draw — land ownership unchanged and attack cards returned.
                title = "Draw!"
                icon = 'draw'
                message = (
                    "The battle ended in a draw.\n\n"
                    "The land remains unchanged. No cards were looted; all attack cards returned to your collection."
                )
            elif is_winner and is_attacker:
                land_tier = self.state.game.land_tier
                land_label = "Tier {} land".format(land_tier) if land_tier else "this land"
                title = "Land Conquered!"
                icon = 'victory'
                message = "You have conquered {}!\n\nThe territory is now yours.".format(land_label)
            elif is_winner and not is_attacker:
                title = "Defence Successful!"
                icon = 'victory'
                message = "You defended your land successfully!"
            elif not is_winner and is_attacker:
                title = "Attack Failed"
                icon = 'defeat'
                message = "You did not conquer this land."
            else:
                title = "Land Lost!"
                icon = 'defeat'
                message = "The attacker has conquered your land."

            self.queue_or_show_notification({
                'message': message,
                'actions': ['ok'],
                'icon': icon,
                'title': title,
                'type': 'game_over',
            })
            return

        winner_name = game_over_info.get('winner_username', 'Winner')
        loser_name = game_over_info.get('loser_username', 'Loser')
        winner_score = game_over_info.get('winner_score', 0)
        loser_score = game_over_info.get('loser_score', 0)
        stake = game_over_info.get('stake', 45)
        game_limit = game_over_info.get('game_limit', stake)
        reason = game_over_info.get('reason', 'stake')
        checkmate_figure_name = game_over_info.get('checkmate_figure_name', 'Maharaja')
        rounds_played = game_over_info.get('rounds_played', 0)

        is_winner = (game_over_info.get('winner_player_id') == self.state.game.player_id)
        player_id = self.state.game.player_id
        winner_pid = game_over_info.get('winner_player_id')
        loser_pid = game_over_info.get('loser_player_id')

        if reason == 'checkmate':
            if is_winner:
                title = "Checkmate!"
                icon = 'victory'
                message = (
                    f"You destroyed {loser_name}'s {checkmate_figure_name}!\n\n"
                    f"Final Score: {winner_score} - {loser_score}\n"
                    f"Game Limit: {game_limit} points\n"
                    f"Stake: {stake} gold"
                )
            else:
                title = "Checkmate!"
                icon = 'defeat'
                message = (
                    f"Your {checkmate_figure_name} was destroyed!\n\n"
                    f"Final Score: {winner_score} - {loser_score}\n"
                    f"Game Limit: {game_limit} points\n"
                    f"Stake: {stake} gold"
                )
        else:
            if is_winner:
                title = "Victory!"
                icon = 'victory'
                message = (
                    f"Congratulations! You won the game!\n\n"
                    f"Final Score: {winner_score} - {loser_score}\n"
                    f"Game Limit: {game_limit} points\n"
                    f"Stake: {stake} gold"
                )
            else:
                title = "Defeat"
                icon = 'defeat'
                message = (
                    f"{winner_name} has won the game.\n\n"
                    f"Final Score: {winner_score} - {loser_score}\n"
                    f"Game Limit: {game_limit} points\n"
                    f"Stake: {stake} gold"
                )

        # Dialogue 1 contains only the result + game statistics. Rewards
        # (gold, booster packs, maps) move to a second dialogue with a
        # wooden-chest reveal interaction (see _show_game_over_rewards_dialogue).
        stats = game_over_info.get('stats', {})
        my_stats = stats.get(player_id) or stats.get(str(player_id)) or {}
        opp_id = loser_pid if is_winner else winner_pid
        opp_stats = stats.get(opp_id) or stats.get(str(opp_id)) or {}
        opp_name = loser_name if is_winner else winner_name

        message_after = ""
        if my_stats or opp_stats:
            stats_lines = [f"Rounds played: {rounds_played}",
                           f"          You / {opp_name}"]
            stat_labels = [
                ('battles_won', 'Battles won'),
                ('figures_built', 'Figures built'),
                ('spells_cast', 'Spells cast'),
                ('cards_changed', 'Cards changed'),
            ]
            for key, label in stat_labels:
                my_val = my_stats.get(key, 0)
                opp_val = opp_stats.get(key, 0)
                stats_lines.append(f"{label}: {my_val} / {opp_val}")
            message_after = "\n".join(stats_lines)

        # ── Result payoff (visual only; the dialogue plays the stinger) ──
        # Same recipe as conquer's _start_conquer_result_payoff. Fires
        # immediately and celebrates behind the modal — the render tail
        # re-draws the dialogue above active effects.
        fx = getattr(self, '_fx', None)
        if fx is not None:
            screen_rect = pygame.Rect(0, 0, self.window.get_width(),
                                      self.window.get_height())
            if is_winner:
                fx.spawn_banner('VICTORY', (238, 206, 130), duration_ms=1500)
                fx.spawn_confetti(
                    screen_rect,
                    [(238, 206, 130), (150, 230, 170), (255, 245, 200),
                     (214, 184, 112)],
                    count=54, delay_ms=120)
                fx.spawn_shake(amplitude=5, duration_ms=260)
            else:
                fx.spawn_banner('DEFEAT', (210, 90, 80), duration_ms=1200)
                # Slow ember/ash fall instead of festive confetti.
                fx.spawn_confetti(
                    screen_rect,
                    [(120, 96, 88), (96, 78, 70), (168, 110, 92)],
                    count=36, fall_speed=(60.0, 130.0), gravity=90.0,
                    life_ms=(800, 1400))
                fx.spawn_shake(amplitude=6, duration_ms=200)

        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'icon': icon,
            'title': title,
            'message_after_images': message_after,
            'type': 'game_over',
        })

    def _show_game_over_rewards_dialogue(self, game_over_info):
        """Show the second game-over dialogue: wooden-chest reveal of all loot.

        Each reward-pool draw (booster pack, map, or bonus gold) becomes a
        clickable chest. The stake winnings/losses are shown directly above
        the chest row because they are predictable loot, not a draw."""
        from game.components.rewards_reveal_dialogue import RewardsRevealDialogueBox
        _GOLD_PER_DRAW = int(getattr(settings, 'DUEL_REWARD_GOLD_AMOUNT', 80) or 80)

        is_winner = (game_over_info.get('winner_player_id') == self.state.game.player_id)
        stake = int(game_over_info.get('stake', 45) or 0)
        gold_awarded = int(game_over_info.get('gold_awarded', 0) or 0)
        rewards_key = 'winner_rewards' if is_winner else 'loser_rewards'
        rewards = game_over_info.get(rewards_key) or {}

        if is_winner:
            title = "Spoils of War"
            icon = 'victory'
            summary_lines = [f"Stake winnings: +{gold_awarded} gold"]
            gold_img_key = 'gold'
        else:
            title = "Spoils of War"
            icon = 'defeat'
            summary_lines = [f"Stake lost: -{stake} gold"]
            gold_img_key = 'gold_lost'
        summary_image = settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT.get(gold_img_key)

        # Build one chest per reward-pool item. Stake is NOT hidden.
        items = []
        main_n = int(rewards.get('main_booster') or 0)
        side_n = int(rewards.get('side_booster') or 0)
        map_n = int(rewards.get('map') or 0)
        gold_total = int(rewards.get('gold') or 0)
        gold_draws = (gold_total // _GOLD_PER_DRAW) if _GOLD_PER_DRAW > 0 else 0

        for _ in range(main_n):
            items.append({'kind': 'main_booster', 'label': 'Main booster pack'})
        for _ in range(side_n):
            items.append({'kind': 'side_booster', 'label': 'Side booster pack'})
        for _ in range(map_n):
            items.append({'kind': 'map', 'label': 'Map'})
        for _ in range(gold_draws):
            items.append({'kind': 'gold', 'label': f'+{_GOLD_PER_DRAW} gold'})

        # Mirror server-side maps award into the cached user dict so the
        # kingdom UI reflects the new count without a refetch.
        if map_n > 0 and self.state.user_dict is not None:
            self.state.user_dict['maps'] = int(
                self.state.user_dict.get('maps', 0)) + map_n

        if not items:
            # No draws to reveal (rare — e.g. all zero) → still show the
            # summary so the player can dismiss the result cleanly.
            footer = "No additional loot this duel."
        else:
            footer = "All loot collected!"

        dialogue = RewardsRevealDialogueBox(
            self.window,
            title=title,
            icon=icon,
            summary_lines=summary_lines,
            items=items,
            footer_when_done=footer,
            summary_image=summary_image,
        )
        self.dialogue_box = dialogue
        self._active_dialogue_type = 'game_over_rewards'

        # Celebratory pop behind the chest reveal.
        fx = getattr(self, '_fx', None)
        if fx is not None:
            w, h = self.window.get_width(), self.window.get_height()
            center = pygame.Rect(w // 2 - 20, h // 2 - 20, 40, 40)
            fx.spawn_burst(center, (238, 206, 130),
                           secondary=(255, 245, 200),
                           count=20, upward_bias=0.6, speed=(140.0, 260.0))

    def _on_game_over_acknowledged(self, response=None):
        """Handle game-over dialogue acknowledgement — return to game menu or kingdom."""
        if self.state.game and self.state.game.mode == 'conquer':
            # Victory Review hop: if the attacker just won and the server
            # offered a defence review, route to DefenceScreen first.  The
            # defence screen takes care of returning to kingdom afterwards.
            pending_review = getattr(
                self.state.game, '_pending_victory_review', None) or {}
            if pending_review.get('available') and pending_review.get('land_id'):
                game_id = (getattr(self.state.game, 'game_id', None)
                           or getattr(self.state.game, 'id', None))
                if game_id:
                    logger.info(
                        "[GAME_OVER] Conquer acknowledged — routing to "
                        "Victory Review for land=%s",
                        pending_review['land_id'])
                    self.state.victory_review_game_id = game_id
                    self.state.defence_land_id = pending_review['land_id']
                    self.state.game._pending_victory_review = None
                    self.state.game = None
                    self.state.screen = 'defence'
                    return
            logger.info("[GAME_OVER] Conquer game acknowledged — returning to kingdom")
            self.state.game = None
            self.state.screen = 'kingdom'
        else:
            logger.info("[GAME_OVER] Player acknowledged — returning to game menu")
            self.state.game = None
            self.state.screen = 'game_menu'

    def check_conquer_battle_ended(self):
        """Check if a conquer battle just ended (set by battle screen) and route to kingdom."""
        if not self.state.game:
            return
        if not getattr(self.state.game, '_conquer_battle_ended', False):
            return
        self.state.game._conquer_battle_ended = False
        logger.info("[CONQUER] Battle ended — returning to kingdom screen")
        self.state.game = None
        self.state.screen = 'kingdom'

    def check_auto_proceed_to_battle(self):
        """Check if both players chose battle (detected via polling for the waiting player)."""
        if not self.state.game:
            return

        if self.state.game.auto_proceed_to_battle:
            self.state.game.auto_proceed_to_battle = False
            self._enter_battle_moves_phase()
            return

        # Safety net: if battle_confirmed is True on the server but the
        # auto_proceed flag was never set (e.g. update_from_dict overwrote
        # battle_confirmed before _apply_game_dict could detect the
        # transition), force the transition now.
        if (self.state.game.battle_confirmed and
                (self.state.game.waiting_for_battle_decision or
                 self.state.game.mode == 'conquer') and
                not self.state.game.battle_moves_phase and
                not self.state.game.battle_moves_ready and
                not self.state.game.in_battle_phase):
            logger.warning("[BATTLE_DECISION] Safety net: battle_confirmed=True but "
                  "auto_proceed missed — forcing transition to battle shop")
            self.state.game.waiting_for_battle_decision = False
            self._enter_battle_moves_phase()

    def _enter_battle_moves_phase(self):
        """Transition both players into the battle shop for mandatory battle-move selection.
        In conquer mode, moves are pre-purchased — auto-confirm unless the
        player has extra hand cards (from prelude spells) that could be used
        to buy additional battle moves.
        """
        # Guard against double-entry (poller can re-trigger via pending_battle_ready).
        # `_sync_battle_moves_phase_from_server` flips battle_moves_phase=True from
        # polling alone — without navigation — so the guard must also confirm we
        # are already viewing the battle_shop subscreen. Otherwise the human
        # never leaves the field after the AI confirms 'battle'.
        if (self.state.game and self.state.game.battle_moves_phase
                and self.state.subscreen == 'battle_shop'):
            logger.debug("[BATTLE_MOVES] Already in battle moves phase — skipping")
            return

        if self.state.game and self.state.game.mode == 'conquer':
            # Check if the player has free hand cards (not part of figures
            # or battle moves — battle-move cards are pre-built from config)
            hand_cards = self.main_hand.cards if hasattr(self, 'main_hand') else []
            hand_cards = [c for c in hand_cards if not getattr(c, 'part_of_battle_move', False)]
            if len(hand_cards) > 0:
                # Player has extra cards — open battle shop so they can use them
                logger.info(f"[CONQUER] Player has {len(hand_cards)} hand cards — opening battle shop")
                self.state.game.battle_moves_phase = True
                self.state.game.battle_moves_ready = False
                self.state.game.waiting_for_opponent_battle_moves = False
                self.state.game.both_battle_moves_ready = False
                self.battle_button.locked = True
                self.state.subscreen = 'battle_shop'
                shop = self.subscreens.get('battle_shop')
                if shop:
                    shop._load_bought_moves()
                self.queue_or_show_notification({
                    'message': "You have extra cards from your prelude spell!\n\n"
                               "You may swap battle moves, or press\n"
                               "'Ready!' to proceed with your current moves.",
                    'actions': ['got it!'],
                    'icon': 'magic',
                    'title': 'Battle Shop',
                    'phase': 'moves',
                    'tone': 'action',
                    'event_key': f"extra_cards_battle_shop:{getattr(self.state.game, 'game_id', 'local')}",
                })
                return

            # No extra cards — auto-confirm moves
            from utils.battle_shop_service import confirm_battle_moves
            try:
                confirm_battle_moves(self.state.game.game_id, self.state.game.player_id)
            except Exception as e:
                logger.error(f"[CONQUER] Failed to auto-confirm battle moves: {e}")
            self.state.game.battle_moves_phase = False
            self.state.game.battle_moves_ready = True
            self.state.game.waiting_for_opponent_battle_moves = False
            self.battle_button.locked = False
            return

        self.state.game.battle_moves_phase = True
        self.state.game.battle_moves_ready = False
        self.state.game.waiting_for_opponent_battle_moves = False
        self.state.game.both_battle_moves_ready = False
        self.battle_button.locked = True
        self.state.subscreen = 'battle_shop'

        # Reload bought moves in the battle shop screen
        shop = self.subscreens.get('battle_shop')
        if shop:
            shop._load_bought_moves()

        # Show instruction notification
        self.queue_or_show_notification({
            'message': "Both warriors chose to fight!\n\n"
                       "Select 3 battle moves before the battle begins.\n"
                       "Press 'Ready!' when done.",
            'actions': ['got it!'],
            'icon': 'magic',
            'title': 'Prepare for Battle'
        })

    def check_battle_moves_ready(self):
        """Check if both players have confirmed their battle moves (polling detection)."""
        if not self.state.game:
            return

        game = self.state.game
        server_started_battle = bool(game.battle_confirmed and game.battle_turn_player_id is not None)
        should_enter_battle = bool(
            game.both_battle_moves_ready or
            (self.state.subscreen == 'battle_shop' and server_started_battle) or
            (game.mode == 'conquer' and server_started_battle)
        )
        if not should_enter_battle:
            return

        self.state.game.both_battle_moves_ready = False
        self.state.game.battle_moves_phase = False
        self.battle_button.locked = False
        self.state.subscreen = 'battle'

    def _enforce_battle_navigation_state(self):
        """Keep battle/battle-shop navigation aligned with server battle phase."""
        if not self.state.game:
            return

        game = self.state.game
        in_move_selection = bool(game.battle_confirmed and game.battle_turn_player_id is None and not game.fold_outcome)
        if in_move_selection:
            # In conquer mode, moves are already chosen — don't redirect to shop
            if game.mode == 'conquer':
                return
            # Battle rounds have not started yet: keep arena locked and route
            # accidental battle-screen entries back to battle shop.
            self.battle_button.locked = True
            if self.state.subscreen == 'battle':
                self.state.subscreen = 'battle_shop'
            return

        if game.battle_confirmed and game.battle_turn_player_id is not None:
            self.battle_button.locked = False

    def check_battle_reconnect(self):
        """Detect an active 3-round battle on the server that the client isn't showing.

        On reconnect (logout/login), all client-side battle flags are reset.
        If the server still has battle_confirmed + battle_turn_player_id set
        (i.e. the battle is in progress), route straight to the battle screen.
        """
        if not self.state.game:
            return
        if not getattr(self.state.game, 'battle_reconnect_pending', False):
            return
        # Only check once per login
        self.state.game.battle_reconnect_pending = False

        # Already on the battle screen — nothing to do
        if self.state.subscreen == 'battle':
            return

        # Server indicators for an active 3-round battle
        if (self.state.game.battle_confirmed and
                self.state.game.battle_turn_player_id is not None and
                not self.state.game.in_battle_phase):
            logger.info("[BATTLE_RECONNECT] Detected active battle on server — entering battle screen")
            self.battle_button.locked = False
            self.state.game.in_battle_phase = True
            self.state.game.battle_turns_left = 3  # will be synced by battle screen poll
            self.state.subscreen = 'battle'

    def _handle_battle_ready_response(self):
        """Handle response from battle-ready notification — switch to battle screen."""
        self.state.subscreen = 'battle'
    
    def _draw_forced_advance_prompt(self):
        """Draw a persistent prompt indicating player must advance a figure."""
        # Create prompt text
        target_prompt_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE)
        
        if self.state.game.mode == 'conquer':
            tier = self.state.game.land_tier
            land_label = "TIER {} LAND".format(tier) if tier else "LAND"
            prompt_text = "BATTLE FOR {}".format(land_label)
        else:
            prompt_text = "BATTLE TIME"
        prompt_surface = target_prompt_font.render(prompt_text, True, (255, 200, 100))  # Orange
        
        # Create instruction text
        cancel_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 2)
        if self.state.game.mode == 'conquer':
            instruction_text = "Advance a figure on the field"
        else:
            instruction_text = "Advance a figure on the field, or build+advance with Instant Charge"
        instruction_surface = cancel_font.render(instruction_text, True, (255, 230, 150))  # Light orange
        
        # Create background box for better visibility
        text_width = max(prompt_surface.get_width(), instruction_surface.get_width())
        text_height = prompt_surface.get_height() + instruction_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        # Draw semi-transparent black background
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        # Draw orange border for emphasis (breathing brightness, pure draw)
        border_pulse = 0.6 + 0.4 * abs(pygame.time.get_ticks() % 1000 - 500) / 500
        border_color = tuple(int(c * border_pulse) for c in (255, 200, 100))
        pygame.draw.rect(self.window, border_color, box_rect, 4)
        
        # Draw main prompt text centered in box
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        # Draw instruction text below
        instruction_x = box_rect.centerx - instruction_surface.get_width() // 2
        instruction_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(instruction_surface, (instruction_x, instruction_y))
        
        # Add pulsing effect to main prompt
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))
    
    def _draw_own_advance_waiting_prompt(self):
        """Draw a persistent prompt showing the advancing player is waiting for opponent."""
        target_prompt_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 2)
        
        # Include active modifier name in prompt header
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        if 'Civil War' in modifier_types:
            prompt_text = "YOUR FIGURE ADVANCING (Civil War)"
        elif 'Peasant War' in modifier_types:
            prompt_text = "YOUR FIGURE ADVANCING (Peasant War)"
        else:
            prompt_text = "YOUR FIGURE ADVANCING"
        prompt_surface = target_prompt_font.render(prompt_text, True, (100, 255, 150))  # Green
        
        detail_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 4)
        figure_name = self.state.game.own_advance_figure_name or "your figure"
        detail_text = f"Waiting for opponent's reaction to {figure_name}"
        detail_surface = detail_font.render(detail_text, True, (180, 255, 200))  # Light green
        
        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        pygame.draw.rect(self.window, (100, 255, 150), box_rect, 4)
        
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))
    
    def _draw_opponent_advance_prompt(self):
        """Draw a prompt showing opponent has advanced a figure."""
        target_prompt_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 2)
        
        # Include active modifier name in prompt header
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        
        # Check if advancing figure has cannot_be_blocked
        has_cannot_be_blocked = False
        if self.state.game.advancing_figure_id:
            field_screen = self.subscreens.get('field')
            if field_screen:
                for fig in getattr(field_screen, 'figures', []):
                    if fig.id == self.state.game.advancing_figure_id:
                        has_cannot_be_blocked = hasattr(fig, 'cannot_be_blocked') and fig.cannot_be_blocked
                        break
        
        if 'Blitzkrieg' in modifier_types:
            prompt_text = "OPPONENT ADVANCING (Blitzkrieg)"
        elif 'Civil War' in modifier_types:
            prompt_text = "OPPONENT ADVANCING (Civil War)"
        elif 'Peasant War' in modifier_types:
            prompt_text = "OPPONENT ADVANCING (Peasant War)"
        else:
            prompt_text = "OPPONENT ADVANCING"
        prompt_surface = target_prompt_font.render(prompt_text, True, (255, 200, 100))  # Orange
        
        detail_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 4)
        if 'Blitzkrieg' in modifier_types:
            detail_text = "Blitzkrieg — you cannot counter-advance"
        elif has_cannot_be_blocked:
            detail_text = "Cannot be blocked — spend your turn on something else"
        elif 'Civil War' in modifier_types:
            detail_text = "Counter-advance with up to two village figures (same color)"
        elif 'Peasant War' in modifier_types:
            detail_text = "Counter-advance with a village figure or spend your turn"
        else:
            detail_text = "Counter-advance or spend your turn on something else"
        detail_surface = detail_font.render(detail_text, True, (255, 230, 150))  # Light orange
        
        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        pygame.draw.rect(self.window, (255, 200, 100), box_rect, 4)
        
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))

    def _draw_waiting_for_defender_pick_prompt(self):
        """Draw a persistent prompt for the defender waiting for opponent to pick their battle figure."""
        target_prompt_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 2)
        prompt_text = "BATTLE INCOMING"
        prompt_surface = target_prompt_font.render(prompt_text, True, (255, 150, 150))  # Red-ish

        detail_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 4)
        # Check if Blitzkrieg prevented counter-advance
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        if 'Blitzkrieg' in modifier_types:
            detail_text = "Blitzkrieg prevented counter-advance — opponent is selecting your battle figure"
        else:
            detail_text = "Opponent is selecting which of your figures faces them in battle"
        detail_surface = detail_font.render(detail_text, True, (255, 200, 200))  # Light red

        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20

        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )

        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)

        pygame.draw.rect(self.window, (255, 150, 150), box_rect, 4)

        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))

        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))

        # Add pulsing effect
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))

    def _draw_waiting_for_battle_decision_prompt(self):
        """Draw a persistent prompt while waiting for opponent's battle/fold decision."""
        target_prompt_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 2)
        is_advancing = (self.state.game.advancing_player_id == self.state.game.player_id)
        
        if is_advancing:
            prompt_text = "WAITING FOR DEFENDER"
            detail_text = "You chose to fight — waiting for the defender to decide"
        else:
            prompt_text = "WAITING FOR INVADER"
            detail_text = "The invader is deciding whether to fight or fold"
        
        prompt_surface = target_prompt_font.render(prompt_text, True, (200, 200, 100))  # Yellow-ish

        detail_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 4)
        detail_surface = detail_font.render(detail_text, True, (220, 220, 150))  # Light yellow

        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20

        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )

        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)

        pygame.draw.rect(self.window, (200, 200, 100), box_rect, 4)

        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))

        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))

        # Add pulsing effect
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))

    def _draw_select_defender_prompt(self):
        """Draw a persistent prompt for the advancing player to select an opponent's defender."""
        target_prompt_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE)
        prompt_text = "SELECT OPPONENT'S DEFENDER"
        prompt_surface = target_prompt_font.render(prompt_text, True, (100, 200, 255))  # Blue

        detail_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 4)
        
        # Build detail text based on active battle modifiers and must_be_attacked
        detail_text = "Go to the field and select an opponent figure to face your advance"
        
        # Check active battle modifiers
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        
        if 'Peasant War' in modifier_types:
            detail_text = "Peasant War active — select an opponent's village figure"
        elif 'Civil War' in modifier_types:
            detail_text = "Civil War active — select an opponent's village figure"
        else:
            # Check if must_be_attacked constraint applies
            field_screen = self.subscreens.get('field')
            has_must_be_attacked = False
            if field_screen:
                for fig in getattr(field_screen, 'figures', []):
                    if (fig.player_id != self.state.game.player_id and
                        hasattr(fig, 'must_be_attacked') and fig.must_be_attacked and
                        not (hasattr(fig, 'cannot_defend') and fig.cannot_defend) and
                        not (hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted) and
                        not (hasattr(fig, 'checkmate') and fig.checkmate)):
                        has_must_be_attacked = True
                        break
            if has_must_be_attacked:
                detail_text = "Select a figure with 'Must Be Attacked' first"
            else:
                detail_text = "Select any opponent figure on the field"
        
        detail_surface = detail_font.render(detail_text, True, (180, 220, 255))  # Light blue

        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20

        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )

        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)

        # Blue border with breathing brightness (pure draw)
        border_pulse = 0.6 + 0.4 * abs(pygame.time.get_ticks() % 1000 - 500) / 500
        border_color = tuple(int(c * border_pulse) for c in (100, 200, 255))
        pygame.draw.rect(self.window, border_color, box_rect, 4)

        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))

        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))

        # Pulsing effect
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))

    def _handle_infinite_hammer_esc(self, events):
        """Handle ESC key press during Infinite Hammer mode to prompt for turn end confirmation."""
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # Show confirmation dialogue
                    self.make_dialogue_box(
                        message="Are you sure you want to end Infinite Hammer mode and pass your turn to your opponent?",
                        actions=['yes', 'no'],
                        icon="infinite_hammer",
                        title="End Turn?"
                    )
                    return True
        return False
    
    def _end_infinite_hammer_mode(self):
        """End Infinite Hammer mode — fire request in background thread."""
        # Immediately clear client state so UI updates
        self.state.game.infinite_hammer_active = False
        self.state.game.infinite_hammer_dialogue_shown = False

        import threading
        game_id = self.state.game.game_id
        player_id = self.state.game.player_id

        def _do():
            try:
                from utils import http_compat as _req
                from config import settings as _s
                resp = _req.post(
                    f'{_s.SERVER_URL}/spells/end_infinite_hammer',
                    json={'game_id': game_id, 'player_id': player_id},
                    timeout=10,
                )
                if resp.status_code == 200:
                    logger.info("[INFINITE_HAMMER] Mode ended successfully")
                else:
                    logger.error(f"[INFINITE_HAMMER] Failed: {resp.text}")
            except Exception as e:
                logger.error(f"[INFINITE_HAMMER] Error: {e}")

        try:
            threading.Thread(target=_do, daemon=True).start()
        except RuntimeError:
            _do()  # web fallback: run synchronously
    
    def _handle_counter_spell_counter(self):
        """Handle player choosing to counter the spell."""
        if getattr(self.state.game, 'game_over', False):
            return
        if not self.state.game or not self.state.game.pending_spell_id:
            return
        
        # Use cached pending spell details and castable spells (no network request, no image loading)
        try:
            spell_data = self.pending_spell_details or {}
            spell_name = spell_data.get('spell_name', 'Unknown')
            
            # Use cached castable spells
            castable_spells = self._cached_castable_spells or []
            
            if not castable_spells:
                self.make_dialogue_box(
                    message=f"You don't have the cards to counter {spell_name}.\nYou'll need to allow it.",
                    actions=['allow'],
                    icon="error",
                    title="Cannot Counter"
                )
                # Don't clear need_to_respond_to_spell - dialogue will handle the response
                return
            
            # Show counter spell selection
            self._show_counter_spell_selection(castable_spells, spell_name)
            
        except Exception as e:
            logger.error(f"[COUNTER_SPELL] Error: {str(e)}")
            self.make_dialogue_box(
                message=f"Error loading counter spells: {str(e)}",
                actions=['ok'],
                icon="error",
                title="Error"
            )
            self.need_to_respond_to_spell = False
    
    def _handle_counter_spell_allow(self):
        """Handle player choosing to allow the spell."""
        if getattr(self.state.game, 'game_over', False):
            return
        if not self.state.game or not self.state.game.pending_spell_id:
            return
        
        from utils import spell_service
        
        # Save spell data before clearing cache (needed for icon lookup)
        spell_data = self.pending_spell_details or {}
        resolved_spell_id = self.state.game.pending_spell_id
        
        result = spell_service.allow_spell(
            player_id=self.state.game.player_id,
            game_id=self.state.game.game_id,
            pending_spell_id=resolved_spell_id
        )
        
        if result.get('success'):
            self.need_to_respond_to_spell = False
            self._last_resolved_spell_id = resolved_spell_id
            
            # Clear spell cache immediately so next spell gets fresh data
            self.pending_spell_details = None
            self._cached_castable_spells = None
            self._pending_spell_fetch_ready = False
            
            # Discard any stale poller result so old server data doesn't
            # overwrite the fresh response and re-trigger the spell dialogue
            if self._game_poller and self._game_poller.has_result():
                _ = self._game_poller.result
            
            # Mark that we just allowed a spell so check_battle_modifier_changes
            # doesn't show a duplicate notification for the same modifier
            self._just_allowed_spell = True
            
            # Update game state directly from response (no server call needed)
            if result.get('game'):
                self.state.game.update_from_dict(result['game'])
            
            # Trigger start_turn so auto-fill fires (non-blocking)
            # (update_from_dict sets turn state, preventing update() from detecting the change)
            if self.state.game.turn:
                self.state.game._start_turn_async()
                # Clear stale opponent turn summary — we already show our own spell notification
                self._clear_opponent_turn_summaries(self.state.game)
            
            # Show spell effect result
            spell_effect = result.get('spell_effect', {})
            effect_message = spell_effect.get('effect', 'Spell executed successfully')
            spell_name = spell_effect.get('spell_name', 'The spell')
            
            # Get spell icon (use saved family name before cache was cleared)
            spell_family = spell_data.get('spell_family_name', spell_name) if spell_data else spell_name
            spell_images = self._get_spell_icon_image(spell_family)
            
            self.queue_or_show_notification({
                'message': f"You allowed {spell_name}.\n\n{effect_message}",
                'actions': ['ok'],
                'images': spell_images,
                'icon': "magic",
                'title': "Spell Allowed"
            })
        else:
            self.need_to_respond_to_spell = False
            # Set guard even on failure — the spell was already resolved
            # server-side (e.g. the first allow succeeded), so stale polls
            # must not re-trigger the dialogue.
            self._last_resolved_spell_id = resolved_spell_id
            # Discard stale poller result
            if self._game_poller and self._game_poller.has_result():
                _ = self._game_poller.result
            # Clear spell cache on error too
            self.pending_spell_details = None
            self._cached_castable_spells = None
            self._pending_spell_fetch_ready = False
            self.queue_or_show_notification({
                'message': f"Error: {result.get('message')}",
                'actions': ['ok'],
                'icon': "error",
                'title': "Error"
            })
    
    def _draw_counter_spell_waiting_prompt(self):
        """Draw a prominent prompt indicating player is waiting for counter spell response."""
        # Get spell name if available
        spell_name = getattr(self, 'pending_spell_name', None) or 'your spell'
        
        # Create prompt text
        target_prompt_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 2)
        prompt_text = f"WAITING FOR OPPONENT"
        prompt_surface = target_prompt_font.render(prompt_text, True, (255, 200, 100))  # Orange
        
        # Create detail text
        detail_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 4)
        detail_text = f"You cast {spell_name}. Opponent can counter or allow it."
        detail_surface = detail_font.render(detail_text, True, (255, 230, 150))  # Light orange
        
        # Create background box for better visibility
        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        # Draw semi-transparent black background
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        # Draw orange border for emphasis (breathing brightness, pure draw)
        border_pulse = 0.6 + 0.4 * abs(pygame.time.get_ticks() % 1000 - 500) / 500
        border_color = tuple(int(c * border_pulse) for c in (255, 200, 100))
        pygame.draw.rect(self.window, border_color, box_rect, 4)
        
        # Draw main prompt text centered in box
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        # Draw detail text below
        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))
    
    def _show_counter_spell_selection(self, castable_spells, target_spell_name):
        """Show UI for selecting which counter spell to cast."""
        from game.components.counter_spell_selector import CounterSpellSelector
        from collections import Counter
        
        # Get player's actual playable hand from the Hand UI components
        # These contain only the cards currently visible/playable in the hand
        main_hand_cards = self.main_hand.cards if hasattr(self, 'main_hand') else []
        side_hand_cards = self.side_hand.cards if hasattr(self, 'side_hand') else []
        all_cards = main_hand_cards + side_hand_cards
        
        logger.debug(f"[COUNTER_SPELL_SELECTOR] Main hand cards count: {len(main_hand_cards)}")
        logger.debug(f"[COUNTER_SPELL_SELECTOR] Side hand cards count: {len(side_hand_cards)}")
        logger.debug(f"[COUNTER_SPELL_SELECTOR] Total playable cards: {len(all_cards)}")
        logger.debug(f"[COUNTER_SPELL_SELECTOR] Main hand: {[(c.suit, c.rank) for c in main_hand_cards]}")
        logger.debug(f"[COUNTER_SPELL_SELECTOR] Side hand: {[(c.suit, c.rank) for c in side_hand_cards]}")
        
        hand_counter = Counter((card.suit, card.rank) for card in all_cards)
        
        logger.debug(f"[COUNTER_SPELL_SELECTOR] Player hand: {dict(hand_counter)}")
        logger.debug(f"[COUNTER_SPELL_SELECTOR] Input castable_spells count: {len(castable_spells)}")
        
        # Double-check each spell is actually castable with current hand
        verified_spells = []
        for spell in castable_spells:
            spell_counter = Counter((card.suit, card.rank) for card in spell.cards)
            can_cast = all(hand_counter[card_tuple] >= count 
                          for card_tuple, count in spell_counter.items())
            logger.debug(f"[COUNTER_SPELL_SELECTOR] Spell '{spell.name}' requires {dict(spell_counter)}, can_cast={can_cast}")
            if can_cast:
                verified_spells.append(spell)
        
        logger.debug(f"[COUNTER_SPELL_SELECTOR] Verified spells count: {len(verified_spells)}")
        
        if not verified_spells:
            # No valid spells after verification - player cannot counter
            logger.debug(f"[COUNTER_SPELL_SELECTOR] No verified spells found")
            self.make_dialogue_box(
                message=f"You don't have the cards to counter {target_spell_name}.\n\nYou'll need to allow it.",
                actions=['allow'],
                icon="error",
                title="Cannot Counter"
            )
            # Don't clear need_to_respond_to_spell - dialogue will handle the response
            return
        
        # Create spell selection options from all verified spells
        spell_options = []
        for spell in verified_spells:
            cards_text = " + ".join([f"{card.rank}{card.suit[0]}" for card in spell.cards])
            spell_options.append({
                'label': f"{spell.name} ({cards_text})",
                'spell': spell
            })
        
        if len(spell_options) == 1:
            # Only one option - cast it directly
            self._cast_counter_spell(spell_options[0]['spell'])
            return  # Exit after casting
        else:
            # Multiple options - show counter spell selector
            selector_width = settings.get_x(0.35)
            selector_height = settings.get_y(0.5)
            selector_x = (settings.SCREEN_WIDTH - selector_width) // 2
            selector_y = settings.get_y(0.25)
            
            self.counter_spell_selector = CounterSpellSelector(
                self.window,
                spell_options,
                selector_x,
                selector_y,
                selector_width,
                selector_height
            )
    
    def _cast_counter_spell(self, spell):
        """Cast the selected counter spell."""
        from utils import spell_service
        from collections import Counter
        
        # Get player's actual playable hand from the Hand UI components (same as in selector)
        main_hand_cards = self.main_hand.cards if hasattr(self, 'main_hand') else []
        side_hand_cards = self.side_hand.cards if hasattr(self, 'side_hand') else []
        all_cards = main_hand_cards + side_hand_cards
        
        # Match spell template cards to actual cards in hand and build counter_cards list
        spell_requirements = Counter((card.suit, card.rank) for card in spell.cards)
        counter_cards = []
        used_card_ids = []
        
        # For each required card, find matching card in hand
        for (suit, rank), count in spell_requirements.items():
            matching_cards = [c for c in all_cards if c.suit == suit and c.rank == rank and c.id not in used_card_ids]
            if len(matching_cards) < count:
                self.make_dialogue_box(
                    message=f"Error: Not enough {rank} of {suit} cards in hand.",
                    actions=['ok'],
                    icon="error",
                    title="Error"
                )
                self.need_to_respond_to_spell = False
                return
            # Take the required number of cards and build card dictionaries
            for i in range(count):
                card = matching_cards[i]
                counter_cards.append({
                    'id': card.id,
                    'suit': card.suit,
                    'rank': card.rank,
                    'value': card.value
                })
                used_card_ids.append(card.id)
        
        result = spell_service.counter_spell(
            player_id=self.state.game.player_id,
            game_id=self.state.game.game_id,
            pending_spell_id=self.state.game.pending_spell_id,
            counter_spell_name=spell.name,
            counter_spell_type=spell.family.type,
            counter_spell_family_name=spell.family.name,
            counter_cards=counter_cards
        )
        
        if result.get('success'):
            from utils import sound
            sound.play('booster_reveal')  # spell-cast sparkle (duel + conquer counter)
            self.need_to_respond_to_spell = False
            self._last_resolved_spell_id = self.state.game.pending_spell_id

            # Clear spell cache immediately so next spell gets fresh data
            self.pending_spell_details = None
            self._cached_castable_spells = None
            self._pending_spell_fetch_ready = False
            
            # Discard any stale poller result so old server data doesn't
            # overwrite the fresh response and re-trigger the spell dialogue
            if self._game_poller and self._game_poller.has_result():
                _ = self._game_poller.result
            
            # Update game state directly from response (no server call needed)
            if result.get('game'):
                self.state.game.update_from_dict(result['game'])
            
            # Trigger start_turn so auto-fill fires (non-blocking)
            # (update_from_dict sets turn state, preventing update() from detecting the change)
            if self.state.game.turn:
                self.state.game._start_turn_async()
                # Clear stale opponent turn summary — we already show our own spell notification
                self._clear_opponent_turn_summaries(self.state.game)
            
            # Show result
            effect = result.get('effect', 'Spell countered!')
            spell_images = self._get_spell_icon_image(spell.family.name)
            self.queue_or_show_notification({
                'message': f"You countered with {spell.name}!\n\n{effect}\n\nYou did not lose a turn.",
                'actions': ['ok'],
                'images': spell_images,
                'icon': "magic",
                'title': "Spell Countered"
            })
        else:
            error_msg = result.get('message', 'Unknown error')
            self.queue_or_show_notification({
                'message': f"Failed to counter spell: {error_msg}",
                'actions': ['ok'],
                'icon': "error",
                'title': "Error"
            })
            self.need_to_respond_to_spell = False
            # Set guard even on failure — the spell was already resolved
            # server-side, so stale polls must not re-trigger the dialogue.
            self._last_resolved_spell_id = self.state.game.pending_spell_id
            # Discard stale poller result
            if self._game_poller and self._game_poller.has_result():
                _ = self._game_poller.result
            # Clear spell cache on error too
            self.pending_spell_details = None
            self._cached_castable_spells = None
            self._pending_spell_fetch_ready = False
    
    def _draw_infinite_hammer_prompt(self):
        """Draw a prominent prompt indicating Infinite Hammer mode is active."""
        # Create prompt text
        target_prompt_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE)
        prompt_text = "INFINITE HAMMER MODE"
        prompt_surface = target_prompt_font.render(prompt_text, True, (255, 215, 0))  # Gold
        
        # Create instruction text
        cancel_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE - 2)
        instruction_text = "Build, upgrade, and pickup without ending turn • Press ESC to end turn"
        instruction_surface = cancel_font.render(instruction_text, True, (255, 255, 150))  # Light yellow
        
        # Create background box for better visibility
        text_width = max(prompt_surface.get_width(), instruction_surface.get_width())
        text_height = prompt_surface.get_height() + instruction_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        # Draw semi-transparent black background
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        # Draw gold border for emphasis
        pygame.draw.rect(self.window, (255, 215, 0), box_rect, 4)
        
        # Draw main prompt text centered in box
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        # Draw instruction text below
        instruction_x = box_rect.centerx - instruction_surface.get_width() // 2
        instruction_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(instruction_surface, (instruction_x, instruction_y))
        
        # Add pulsing effect to main prompt
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))
    
    
    
    def _create_figure_from_data(self, figure_data, families):
        """Helper method to create a Figure instance from serialized data."""
        from game.components.figures.figure import Figure
        from game.components.cards.card import Card
        
        family_name = figure_data.get('family_name')
        if family_name not in families:
            return None
        
        family = families[family_name]
        
        # Reconstruct cards from figure data
        cards_data = figure_data.get('cards', [])
        key_cards = []
        number_card = None
        upgrade_card = None
        
        for card_data in cards_data:
            card = Card(
                rank=card_data['rank'],
                suit=card_data['suit'],
                value=card_data['value'],
                id=card_data.get('card_id'),  # Use card_id, not id
                type=card_data.get('card_type', 'main')
            )
            # Check the role to categorize the card
            role = card_data.get('role', 'key')
            if role == 'key':
                key_cards.append(card)
            elif role == 'number':
                number_card = card
            elif role == 'upgrade':
                upgrade_card = card
        
        # Try to match family figure for combat attributes
        matched_family_figure = None
        for family_figure in family.figures:
            if family_figure.suit == figure_data.get('suit'):
                matched_family_figure = family_figure
                if not upgrade_card:
                    upgrade_card = family_figure.upgrade_card
                break
        
        # Create Figure instance (no game_id parameter)
        # Copy combat skill attributes from matched family figure
        from game.components.figures.family_configs.skill_config import SKILL_KEYS
        skill_kwargs = {k: getattr(matched_family_figure, k, False) if matched_family_figure else False
                        for k in SKILL_KEYS}
        override_base_power = getattr(matched_family_figure, 'override_base_power', None) if matched_family_figure else None
        figure = Figure(
            name=figure_data.get('name', ''),
            sub_name='',  # Not stored in DB
            suit=figure_data.get('suit'),
            family=family,
            key_cards=key_cards,
            number_card=number_card,
            upgrade_card=upgrade_card,
            upgrade_family_name=figure_data.get('upgrade_family_name'),
            produces=figure_data.get('produces', {}),
            requires=figure_data.get('requires', {}),
            description=figure_data.get('description', ''),
            id=figure_data.get('id'),
            player_id=figure_data.get('player_id'),
            override_base_power=override_base_power,
            **skill_kwargs,
        )
        
        # Apply enchantments if present
        enchantments = figure_data.get('enchantments', [])
        for enchantment in enchantments:
            figure.add_enchantment(
                spell_name=enchantment.get('spell_name', 'Unknown'),
                spell_icon=enchantment.get('spell_icon', 'default_spell_icon.png'),
                power_modifier=enchantment.get('power_modifier', 0)
            )
        
        return figure

    def _draw_unread_chat_badge(self):
        """Draw a red circle with unread message count on the log button."""
        if not self.state.game or not self.state.game.chat_messages:
            return
        # Only count opponent messages (not our own)
        current_player_id = self.state.game.player_id
        opponent_messages = [m for m in self.state.game.chat_messages if m.get('sender_id') != current_player_id]
        total_opponent = len(opponent_messages)
        # Count how many opponent messages existed when we last opened the log
        seen_opponent = 0
        if self._last_seen_chat_count > 0:
            # We stored total chat count; recount opponent msgs up to that point
            all_msgs = self.state.game.chat_messages
            for i, m in enumerate(all_msgs):
                if i >= self._last_seen_chat_count:
                    break
                if m.get('sender_id') != current_player_id:
                    seen_opponent += 1
        unread = total_opponent - seen_opponent
        if unread <= 0 or self.state.subscreen == 'log':
            return
        # Draw red circle badge at top-right of log button (gentle breathing
        # pulse so unseen activity draws the eye — pure draw, no state)
        badge_radius = int(0.006 * settings.SCREEN_WIDTH * _UI_SCALE
                           * (1.0 + 0.12 * math.sin(pygame.time.get_ticks() * 0.006)))
        badge_x = self.log_button.rect_symbol.right - badge_radius // 2
        badge_y = self.log_button.rect_symbol.top + badge_radius // 2
        pygame.draw.circle(self.window, (220, 40, 40), (badge_x, badge_y), badge_radius)
        pygame.draw.circle(self.window, (255, 255, 255), (badge_x, badge_y), badge_radius, 2)
        # Draw count text
        count_text = str(min(unread, 99))
        text_surface = self._badge_font.render(count_text, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=(badge_x, badge_y))
        self.window.blit(text_surface, text_rect)

    # ── Field & Battle badge helpers ──────────────────────────────

    def _get_all_figure_ids(self):
        """Return a frozenset of all figure IDs (both players) from current game state."""
        if not self.state.game or not self.state.game.players:
            return frozenset()
        ids = set()
        for player in self.state.game.players:
            for fig in player.get('figures', []):
                fid = fig.get('id') if isinstance(fig, dict) else getattr(fig, 'id', None)
                if fid is not None:
                    ids.add(fid)
        return frozenset(ids)

    def _get_battle_snapshot(self):
        """Return a snapshot of the current battle state for change detection."""
        if not self.state.game:
            return (0, None)
        return (
            getattr(self.state.game, 'battle_round', 0),
            getattr(self.state.game, 'battle_turn_player_id', None),
        )

    def _update_field_badge(self):
        """Detect figure changes and increment field badge when not on field screen."""
        current_ids = self._get_all_figure_ids()
        if self._last_seen_figure_ids is None:
            # First poll — initialise without incrementing
            self._last_seen_figure_ids = current_ids
            return
        if current_ids != self._last_seen_figure_ids:
            if self.state.subscreen == 'field':
                # Player is looking at the field — just update snapshot, no badge
                self._last_seen_figure_ids = current_ids
                self._field_unseen_count = 0
            else:
                # Figure set changed while player is elsewhere
                self._field_unseen_count += 1
                self._last_seen_figure_ids = current_ids

    def _update_battle_badge(self):
        """Detect battle round/turn changes and increment badge when not on battle screen."""
        snapshot = self._get_battle_snapshot()
        # Only track during an active battle
        if not getattr(self.state.game, 'in_battle_phase', False):
            self._last_seen_battle_round = snapshot
            self._battle_unseen_count = 0
            return
        if self._last_seen_battle_round is None:
            self._last_seen_battle_round = snapshot
            return
        if snapshot != self._last_seen_battle_round:
            if self.state.subscreen == 'battle':
                self._last_seen_battle_round = snapshot
                self._battle_unseen_count = 0
            else:
                self._battle_unseen_count += 1
                self._last_seen_battle_round = snapshot

    def _draw_button_badge(self, button, count):
        """Draw a red notification badge on a game button."""
        if count <= 0:
            return
        _ui = _UI_SCALE
        # Gentle breathing pulse — pure draw, no state.
        badge_radius = int(0.006 * settings.SCREEN_WIDTH * _ui
                           * (1.0 + 0.12 * math.sin(pygame.time.get_ticks() * 0.006)))
        badge_x = button.rect_symbol.right - badge_radius // 2
        badge_y = button.rect_symbol.top + badge_radius // 2
        pygame.draw.circle(self.window, (220, 40, 40), (badge_x, badge_y), badge_radius)
        pygame.draw.circle(self.window, (255, 255, 255), (badge_x, badge_y), badge_radius, 2)
        count_text = str(min(count, 99))
        text_surface = self._badge_font.render(count_text, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=(badge_x, badge_y))
        self.window.blit(text_surface, text_rect)

    def _draw_field_badge(self):
        """Draw field changes badge on the field button."""
        if self.state.subscreen == 'field' or self._field_unseen_count <= 0:
            return
        self._draw_button_badge(self.field_button, self._field_unseen_count)

    def _draw_battle_badge(self):
        """Draw battle changes badge on the battle button."""
        if self.state.subscreen == 'battle' or self._battle_unseen_count <= 0:
            return
        self._draw_button_badge(self.battle_button, self._battle_unseen_count)

    # ── First-duel coach marks ─────────────────────────────────────

    def _duel_onboarding(self):
        ud = getattr(self.state, 'user_dict', None) or {}
        return ud.get('onboarding') or {}

    def _apply_game_onboarding_payload(self, data):
        if not data or getattr(self.state, 'user_dict', None) is None:
            return
        onboarding = data.get('onboarding')
        if onboarding is not None:
            self.state.user_dict['onboarding'] = onboarding
        balances = data.get('balances') or {}
        for key in ('gold', 'booster_packs', 'booster_packs_side', 'maps'):
            if key in balances:
                self.state.user_dict[key] = balances[key]

    def _set_onboarding_skipped_local(self, skipped):
        ud = getattr(self.state, 'user_dict', None)
        if not ud:
            return
        onboarding = dict(ud.get('onboarding') or {})
        onboarding['onboarding_skipped'] = bool(skipped)
        if skipped:
            onboarding['welcome_pending'] = False
        ud['onboarding'] = onboarding

    def _pause_onboarding_tutorial(self):
        try:
            data = onboarding_service.skip_onboarding()
            self._apply_game_onboarding_payload(data)
        except Exception as exc:
            logger.debug("Failed to pause onboarding tutorial: %s", exc)
            self._set_onboarding_skipped_local(True)
        self._duel_coach_pressed_button_action = None
        if getattr(self.state, 'set_msg', None):
            self.state.set_msg('Tutorial paused. Open Guide to continue.')

    def _duel_coach_allowed(self):
        game = getattr(self.state, 'game', None)
        onboarding = self._duel_onboarding()
        if not game or getattr(game, 'mode', 'duel') == 'conquer':
            return False
        if not onboarding:
            return False
        if onboarding.get('onboarding_skipped'):
            return False
        if 'finish_first_duel' in set(onboarding.get('completed_steps') or []):
            return False
        if self.dialogue_box or self.pending_notifications:
            return False
        subscreen = self.subscreens.get(self.state.subscreen) if self.state.subscreen in self.subscreens else None
        if subscreen and getattr(subscreen, 'dialogue_box', None):
            return False
        if self.counter_spell_selector or self.need_to_respond_to_spell or self.waiting_for_counter_response:
            return False
        if getattr(game, 'pending_forced_advance', False):
            return False
        if getattr(game, 'pending_defender_selection', False):
            return False
        if getattr(game, 'game_over', False) or getattr(game, 'pending_game_over', False):
            return False
        if not getattr(game, 'turn', False) and not game.is_battle_active():
            return False
        return True

    def _duel_coach_has_pending_step(self):
        return self._current_duel_coach_step() is not None

    def _duel_coach_blocks_updates(self, step=None):
        """Keep the modal coach inert except over an explicit click target.

        Action lessons pass target events through in ``handle_events``.  Their
        controls also need one update tick while the pointer is over that
        target because several game controls use the current mouse state (not
        the event itself) to activate.
        """
        step = step if step is not None else self._current_duel_coach_step()
        if not step:
            return False
        if step.get('action') != 'click':
            return True
        pointer = pygame.mouse.get_pos()
        return not any(rect.collidepoint(pointer) for rect in self._duel_step_rects(step))

    def _current_duel_coach_step(self):
        if not self._duel_coach_allowed():
            return None
        seen = set((self._duel_onboarding() or {}).get('duel_hints_seen') or [])
        steps = [
            {'id': 'field', 'button': self.field_button, 'subscreen': 'field',
             'title': 'Your setup turns',
             'completes': ('field', 'game_status', 'resource_panel'),
             'body': 'Each round gives you 6 setup turns. Build on the board, watch your resources and score, then prepare for battle.'},
            {'id': 'build', 'button': self.build_button, 'subscreen': 'field',
             'title': 'Build your first figure', 'action': 'click',
             'button_label': 'Build', 'coach_subscreen': 'build_figure',
             'body': 'Tap Build, choose a glowing recipe, and create a figure. This lesson advances after the build succeeds.'},
            {'id': 'cast_spell',
             'rects': self._duel_setup_option_rects(),
             'subscreen': 'field', 'title': 'Other setup options',
             'completes': ('cast_spell', 'change_cards'),
             'separate_highlights': True,
             'body': 'Cast Spell spends a turn on a one-time effect. The round-arrow controls exchange selected cards when your hand needs help.'},
            {'id': 'battle_shop_select_moves', 'rects': self._duel_battle_shop_family_rects(), 'subscreen': 'battle_shop', 'title': 'Choose battle moves',
             'action': 'click',
             'body': 'Pick a move family, choose a matching card, and buy a move. The lesson advances after a purchase succeeds.'},
            {'id': 'battle_shop_ready', 'rects': self._duel_battle_shop_ready_rects(), 'subscreen': 'battle_shop', 'title': 'Ready for battle',
             'action': 'click',
             'body': "When your move slots are ready, tap Ready to lock in the battle plan."},
            {'id': 'battle_move_panel', 'rects': self._duel_battle_move_panel_rects(), 'subscreen': 'battle', 'title': 'Inspect a battle move',
             'action': 'click',
             'body': 'Tap one of your move icons to open its actions. You use one move per round.'},
            {'id': 'battle_move_actions', 'rects': self._duel_battle_move_action_rects(), 'subscreen': 'battle', 'title': 'Choose an action',
             'action': 'click',
             'body': 'Use plays the move. Gamble trades it for two random ones. Combine merges same-colour Daggers into a Double Dagger.',
             'requires_seen': 'battle_move_panel'},
            {'id': 'battle_score', 'rects': self._duel_battle_score_rects(), 'subscreen': 'battle', 'title': 'Read the score',
             'separate_highlights': True,
             'requires_seen': 'battle_move_actions',
             'body': 'The middle value compares the fighting figures; each round adds its difference on top. The total decides the battle: positive means you win.'},
        ]
        for step in steps:
            if step['id'] in seen:
                continue
            if step.get('requires_seen') and step['requires_seen'] not in seen:
                continue
            expected_subscreen = step.get('subscreen')
            if (expected_subscreen
                    and getattr(self.state, 'subscreen', None) != expected_subscreen):
                # Do not lecture over an unrelated screen; wait until gameplay
                # naturally reaches the relevant action surface.
                return None
            if step.get('rect') is None and not step.get('rects') and not step.get('button'):
                continue
            return step
        return None

    def _duel_change_cards_rects(self):
        rects = []
        for hand in (getattr(self, 'main_hand', None), getattr(self, 'side_hand', None)):
            for button in getattr(hand, 'buttons', []) or []:
                if getattr(button, 'name', None) == 'change_cards':
                    rect = getattr(button, 'rect_hit', None) or getattr(button, 'rect_symbol', None)
                    if rect:
                        rects.append(rect.copy())
        return rects

    def _duel_setup_option_rects(self):
        rects = []
        button = getattr(self, 'cast_spell_button', None)
        rect = (getattr(button, 'rect_hit', None)
                or getattr(button, 'rect_symbol', None)
                or getattr(button, 'rect', None))
        if rect:
            rects.append(rect.copy())
        rects.extend(self._duel_change_cards_rects())
        return rects

    @staticmethod
    def _duel_panel_rect(panel):
        rect = getattr(panel, 'rect', None)
        return rect.copy() if rect else None

    @staticmethod
    def _duel_combined_bounds(rects):
        usable = [pygame.Rect(rect) for rect in rects if rect]
        if not usable:
            return None
        bounds = usable[0].copy()
        for rect in usable[1:]:
            bounds.union_ip(rect)
        return bounds

    def _duel_active_subscreen(self, name):
        if getattr(self.state, 'subscreen', None) != name:
            return None
        return (getattr(self, 'subscreens', {}) or {}).get(name)

    def _duel_battle_shop_family_rects(self):
        game = getattr(self.state, 'game', None)
        if not game or not getattr(game, 'battle_moves_phase', False):
            return []
        shop = self._duel_active_subscreen('battle_shop')
        if not shop:
            return []
        rects = []
        for button in getattr(shop, 'move_family_buttons', []) or []:
            x = int(getattr(button, 'x', 0))
            y = int(getattr(button, 'y', 0))
            icon = getattr(button, 'icon_img_big', None) or getattr(button, 'icon_img', None)
            frame = getattr(button, 'frame_img_big', None) or getattr(button, 'frame_img', None)
            glow = getattr(button, 'glow_gold_big', None) or getattr(button, 'glow_white_big', None)
            caption = getattr(button, 'text_surface_big', None) or getattr(button, 'text_surface', None)
            width = max([surf.get_width() for surf in (icon, frame, glow, caption) if surf] or [settings.BATTLE_MOVE_ICON_WIDTH])
            icon_height = max([surf.get_height() for surf in (icon, frame, glow) if surf] or [settings.BATTLE_MOVE_ICON_HEIGHT])
            caption_height = caption.get_height() if caption else 0
            height = icon_height + caption_height + 24
            rects.append(pygame.Rect(x - width // 2, y - icon_height // 2 - 4, width, height))
        bounds = self._duel_combined_bounds(rects)
        return [bounds] if bounds else []

    def _duel_battle_shop_slot_rects(self, shop):
        sw = settings.BATTLE_SHOP_SLOT_WIDTH
        sh = settings.BATTLE_SHOP_SLOT_HEIGHT
        max_moves = settings.BATTLE_SHOP_MAX_MOVES
        delta_x = settings.BATTLE_SHOP_SLOT_DELTA_X
        box_cx = shop._sx(settings.BATTLE_SHOP_INFO_BOX_X + settings.BATTLE_SHOP_INFO_BOX_WIDTH // 2)
        total_span = (max_moves - 1) * delta_x + sw
        slot_start_x = box_cx - total_span // 2
        sy = shop._sy(settings.BATTLE_SHOP_SLOT_Y)
        rects = []
        for i in range(max_moves):
            sx = slot_start_x + i * delta_x
            cx = sx + sw // 2
            cy = sy + sh // 2
            rects.append(pygame.Rect(cx - sw, cy - sh, sw * 2, sh * 2))
        bounds = self._duel_combined_bounds(rects)
        return [bounds] if bounds else []

    def _duel_battle_shop_ready_rects(self):
        game = getattr(self.state, 'game', None)
        if not game or not getattr(game, 'battle_moves_phase', False):
            return []
        shop = self._duel_active_subscreen('battle_shop')
        if not shop:
            return []
        ready = getattr(getattr(shop, 'ready_button', None), 'rect', None)
        return [ready.copy()] if ready else []

    def _duel_battle_move_panel_rects(self):
        game = getattr(self.state, 'game', None)
        if not game or not getattr(game, 'battle_confirmed', False):
            return []
        battle = self._duel_active_subscreen('battle')
        if not battle or getattr(battle, 'battle_move_detail_box', None):
            return []
        panel_rect = battle._battle_panel_rect() if hasattr(battle, '_battle_panel_rect') else None
        return [panel_rect] if panel_rect else []

    def _duel_battle_move_action_rects(self):
        game = getattr(self.state, 'game', None)
        if not game or not getattr(game, 'battle_confirmed', False):
            return []
        battle = self._duel_active_subscreen('battle')
        detail_box = getattr(battle, 'battle_move_detail_box', None) if battle else None
        if not detail_box:
            return []
        rects = []
        for _action_id, button in getattr(detail_box, 'action_buttons', []) or []:
            rect = getattr(button, 'rect', None)
            if rect:
                rects.append(rect.copy())
        if rects:
            bounds = self._duel_combined_bounds(rects)
            return [bounds] if bounds else []
        box_rect = getattr(detail_box, 'border_rect', None) or getattr(detail_box, 'rect', None)
        return [box_rect.copy()] if box_rect else []

    def _duel_battle_figure_diff_rects(self):
        game = getattr(self.state, 'game', None)
        if not game or not getattr(game, 'battle_confirmed', False):
            return []
        battle = self._duel_active_subscreen('battle')
        if not battle or not hasattr(battle, '_figures_panel_rect'):
            return []
        panel = battle._figures_panel_rect()
        gap = int(0.005 * settings.SCREEN_HEIGHT)
        diff_margin_top = int(0.03 * settings.SCREEN_HEIGHT)
        diff_margin_bot = int(0.01 * settings.SCREEN_HEIGHT)
        diff_h_total = diff_margin_top + settings.FIGURES_DIFF_H + diff_margin_bot
        panel_mid = panel.y + panel.h // 2
        diff_area_top = panel_mid - diff_h_total // 2
        diff_area_bot = panel_mid + diff_h_total // 2
        return [pygame.Rect(panel.x, diff_area_top - gap, panel.w, diff_area_bot - diff_area_top + 2 * gap)]

    def _duel_battle_rounds_panel_rects(self):
        game = getattr(self.state, 'game', None)
        if not game or not getattr(game, 'battle_confirmed', False):
            return []
        battle = self._duel_active_subscreen('battle')
        if not battle or not hasattr(battle, '_rounds_panel_rect'):
            return []
        return [battle._rounds_panel_rect()]

    def _duel_battle_total_diff_rects(self):
        game = getattr(self.state, 'game', None)
        if not game or not getattr(game, 'battle_confirmed', False):
            return []
        battle = self._duel_active_subscreen('battle')
        if not battle:
            return []
        cx = battle._sx(settings.TOTAL_CIRCLE_X) if hasattr(battle, '_sx') else settings.TOTAL_CIRCLE_X
        cy = battle._sy(settings.TOTAL_CIRCLE_Y) if hasattr(battle, '_sy') else settings.TOTAL_CIRCLE_Y
        radius = settings.TOTAL_CIRCLE_RADIUS
        pad = max(8, int(radius * 0.18))
        return [pygame.Rect(cx - radius - pad, cy - radius - pad,
                            2 * (radius + pad), 2 * (radius + pad))]

    def _duel_game_status_rects(self):
        """Highlight rects for the merged 'game status' coach card: the
        scoreboard panel plus the turn, ceasefire, and role icons."""
        rects = []
        scoreboard = self._duel_panel_rect(getattr(self, 'scoreboard_scroll', None))
        if scoreboard:
            rects.append(scoreboard)
        for button in (getattr(self, 'turn_button', None),
                       getattr(self, 'ceasefire_button', None),
                       getattr(self, 'invader_button', None)):
            if button is None:
                continue
            rect = (getattr(button, 'rect_hit', None)
                    or getattr(button, 'rect_symbol', None)
                    or getattr(button, 'rect', None))
            if rect:
                rects.append(rect.copy())
        return rects

    def _duel_battle_score_rects(self):
        """Highlight rects for the merged battle-reading card: the figure
        difference, the rounds panel, and the total."""
        rects = []
        for getter in (self._duel_battle_figure_diff_rects,
                       self._duel_battle_rounds_panel_rects,
                       self._duel_battle_total_diff_rects):
            rects.extend(getter())
        return rects

    def _duel_step_rects(self, step):
        if not step:
            return []
        if step.get('rects'):
            return [pygame.Rect(rect) for rect in step.get('rects') if rect]
        if step.get('rect'):
            return [pygame.Rect(step['rect'])]
        button = step.get('button')
        rect = getattr(button, 'rect_hit', None) or getattr(button, 'rect_symbol', None)
        return [pygame.Rect(rect)] if rect else []

    def _duel_target_bounds(self, step):
        rects = self._duel_step_rects(step)
        if not rects:
            return None
        bounds = rects[0].copy()
        for rect in rects[1:]:
            bounds.union_ip(rect)
        return bounds

    def _duel_highlight_rects(self, step):
        rects = self._duel_step_rects(step)
        if not rects:
            return []
        if step.get('separate_highlights'):
            return rects
        bounds = self._duel_combined_bounds(rects)
        return [bounds] if bounds else []

    def _mark_duel_coach_seen(self, step_id):
        if not step_id:
            return
        try:
            data = onboarding_service.mark_tip(f'duel:{step_id}')
            onboarding = data.get('onboarding')
            if onboarding is not None and getattr(self.state, 'user_dict', None) is not None:
                self.state.user_dict['onboarding'] = onboarding
            return
        except Exception as exc:
            logger.debug("Failed to persist duel coach hint %s: %s", step_id, exc)
        ud = getattr(self.state, 'user_dict', None)
        if not ud:
            return
        onboarding = dict(ud.get('onboarding') or {})
        seen = list(onboarding.get('duel_hints_seen') or [])
        if step_id not in seen:
            seen.append(step_id)
        onboarding['duel_hints_seen'] = seen
        ud['onboarding'] = onboarding

    def _mark_duel_coaches_seen(self, step_ids, *, event=None):
        step_ids = tuple(step_ids or ())
        if not step_ids:
            return
        try:
            data = onboarding_service.mark_tips(
                [f'duel:{step_id}' for step_id in step_ids], event=event)
            onboarding = data.get('onboarding')
            if onboarding is not None and getattr(self.state, 'user_dict', None) is not None:
                self.state.user_dict['onboarding'] = onboarding
            return
        except Exception as exc:
            logger.debug('Failed to persist Duel coach hints %s: %s', step_ids, exc)
        for step_id in step_ids:
            self._mark_duel_coach_seen(step_id)

    def _open_duel_coach_step_subscreen(self, step):
        subscreen = (step or {}).get('subscreen')
        if subscreen and subscreen in self.subscreens:
            self.state.subscreen = subscreen

    def _skip_duel_coach(self):
        self._mark_duel_coaches_seen((
            'field', 'build', 'cast_spell', 'change_cards', 'game_status',
            'resource_panel', 'battle_shop_select_moves', 'battle_shop_ready',
            'battle_move_panel', 'battle_move_actions', 'battle_score',
        ), event='lesson_dismissed')
        self._duel_coach_pressed_button_action = None
        if getattr(self.state, 'set_msg', None):
            self.state.set_msg('Duel lesson skipped. Other guidance stays active.')

    def _wrap_duel_coach_lines(self, text, max_width, max_lines=5):
        words = str(text or '').split()
        lines = []
        current = ''
        for word in words:
            candidate = word if not current else f'{current} {word}'
            if self._duel_coach_font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:max_lines]

    def _draw_duel_coach_button(self, rect, label, action, muted=False):
        draw_coach_button(
            self.window, rect, label, self._duel_coach_font, muted=muted)
        self._duel_coach_buttons.append((rect.copy(), action))

    def _draw_duel_coach(self):
        step = self._current_duel_coach_step()
        self._duel_coach_buttons = []
        self._duel_coach_step = step
        if not step:
            return
        highlight_rects = self._duel_highlight_rects(step)
        target = self._duel_combined_bounds(highlight_rects)
        if not target:
            return
        card, button_h = draw_coach_panel(
            self.window,
            highlight_rects,
            title=step['title'],
            body=step['body'],
            title_font=self._duel_coach_title_font,
            body_font=self._duel_coach_font,
            ticks=pygame.time.get_ticks(),
            width_ratio=0.31,
            min_width=330,
            max_width=390,
            min_height=136,
            max_lines=5,
            has_button_row=True,
        )
        if card is None:
            return

        coach_subscreen = step.get('coach_subscreen')
        if step.get('action', 'next') != 'click' or coach_subscreen:
            button_label = step.get('button_label') or 'Next'
            button_w = max(76, self._duel_coach_font.size(button_label)[0] + 28)
            next_rect = pygame.Rect(card.right - button_w - 14, card.bottom - button_h - 12,
                                    button_w, button_h)
            action = (('open_subscreen', coach_subscreen) if coach_subscreen
                      else ('next', step['id']))
            self._draw_duel_coach_button(next_rect, button_label, action)
        skip_label = 'Skip Duel lesson'
        skip_w = max(112, self._duel_coach_font.size(skip_label)[0] + 24)
        skip_rect = pygame.Rect(card.x + 14, card.bottom - button_h - 12,
                                skip_w, button_h)
        self._draw_duel_coach_button(
            skip_rect, skip_label, ('skip_tutorial', step['id']), muted=True)

    @staticmethod
    def _duel_coach_blocking_event_types():
        event_types = {MOUSEBUTTONDOWN, MOUSEBUTTONUP, MOUSEWHEEL, KEYDOWN, KEYUP}
        text_input = getattr(pygame, 'TEXTINPUT', None)
        if text_input is not None:
            event_types.add(text_input)
        return event_types

    def _handle_duel_coach_events(self, events):
        if not self._duel_coach_step:
            return False
        block_types = self._duel_coach_blocking_event_types()
        target_rects = self._duel_step_rects(self._duel_coach_step)
        click_through = self._duel_coach_step.get('action') == 'click'
        for event in events:
            if event.type == QUIT:
                continue
            if event.type not in block_types:
                continue
            if event.type == MOUSEBUTTONDOWN and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                self._duel_coach_pressed_button_action = None
                for rect, action in list(self._duel_coach_buttons):
                    if rect.collidepoint(pos):
                        self._duel_coach_pressed_button_action = action
                        return True
                if click_through and any(rect.collidepoint(pos) for rect in target_rects):
                    return False
                return True
            if event.type == MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                pressed_action = getattr(self, '_duel_coach_pressed_button_action', None)
                self._duel_coach_pressed_button_action = None
                for rect, action in list(self._duel_coach_buttons):
                    if not rect.collidepoint(pos):
                        continue
                    if pressed_action and pressed_action != action:
                        return True
                    kind, step_id = action
                    if kind == 'next':
                        completes = self._duel_coach_step.get('completes') or (step_id,)
                        self._mark_duel_coaches_seen(completes)
                        self._open_duel_coach_step_subscreen(self._current_duel_coach_step())
                    elif kind == 'open_subscreen':
                        # Action CTAs navigate to the highlighted gameplay
                        # surface without completing the lesson.  The build
                        # step, for example, is marked only after the server
                        # confirms that a figure was actually created.
                        if step_id in self.subscreens:
                            self.state.subscreen = step_id
                    elif kind == 'skip_tutorial':
                        self._skip_duel_coach()
                    return True
                if click_through and any(rect.collidepoint(pos) for rect in target_rects):
                    coach_subscreen = self._duel_coach_step.get('coach_subscreen')
                    if coach_subscreen and coach_subscreen in self.subscreens:
                        self.state.subscreen = coach_subscreen
                        return True
                    return False
                return True
            return True
        return False

    @staticmethod
    def _fit_duel_coach_text(text, font, max_width):
        text = str(text or '')
        if font.size(text)[0] <= max_width:
            return text
        ell = '...'
        max_width = max(0, max_width - font.size(ell)[0])
        out = ''
        for char in text:
            if font.size(out + char)[0] > max_width:
                break
            out += char
        return out.rstrip() + ell

    def render(self):
        """Render the game screen, buttons, and active subscreen."""
        self.window.fill(settings.BACKGROUND_COLOR)

        # Check if game exists (may be None after logout)
        if not self.state.game:
            return
        if not self._ensure_duel_screen_game():
            return

        for element in self.display_elements:
            element.draw()

        # Draw active battle modifier icons below the resource scroll
        self._draw_battle_modifier_icons()

        # Draw game-specific text (e.g., opponent name)
        #self.draw_text(self.state.game.opponent_name, settings.BLACK, settings.get_x(0.1), settings.get_x(0.1))

        # Render game buttons
        #for button in self.game_buttons:
        #    button.draw()



        # Detect tab switches per frame (update_game polls too slowly for
        # this) so the incoming subscreen fades in under a brief veil.
        if self.state.subscreen != getattr(self, '_last_rendered_subscreen', None):
            self._last_rendered_subscreen = self.state.subscreen
            self._subscreen_switched_at = pygame.time.get_ticks()

        # Render the currently active subscreen
        if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
            self.subscreens[self.state.subscreen].draw()
            self._draw_subscreen_switch_veil()

        # Render the main and side hands
        self.main_hand.draw()
        self.side_hand.draw()

        # Render any general elements (e.g., dialogue box) from the parent class
        super().render()

        # Draw unread chat badge on top of log button
        self._draw_unread_chat_badge()

        # ── Overlays drawn AFTER super().render() so they appear on top ──

        # Draw All Seeing Eye hover card on top of buttons
        if self.state.subscreen == 'field':
            field_screen = self.subscreens.get('field')
            if field_screen and getattr(field_screen, 'cached_all_seeing_eye_status', False):
                field_screen.draw_opponent_card_hover()

        # Draw field & battle change badges
        self._draw_field_badge()
        self._draw_battle_badge()

        # Render figure detail box on top of everything (if open)
        if (self.state.subscreen in ('field', 'battle') and 
            self.state.subscreen in self.subscreens and 
            self.subscreens[self.state.subscreen] and
            hasattr(self.subscreens[self.state.subscreen], 'figure_detail_box') and
            self.subscreens[self.state.subscreen].figure_detail_box):
            self.subscreens[self.state.subscreen].figure_detail_box.draw()
        
        # Render battle move detail box on top of everything (if open)
        if (self.state.subscreen in ('battle_shop', 'battle') and 
            self.state.subscreen in self.subscreens and 
            self.subscreens[self.state.subscreen] and
            hasattr(self.subscreens[self.state.subscreen], 'battle_move_detail_box') and
            self.subscreens[self.state.subscreen].battle_move_detail_box):
            self.subscreens[self.state.subscreen].battle_move_detail_box.draw()
        
        # Render dialogue box on top of everything (if open)
        if (self.state.subscreen == 'field' and 
            self.state.subscreen in self.subscreens and 
            self.subscreens[self.state.subscreen] and
            hasattr(self.subscreens[self.state.subscreen], 'dialogue_box') and
            self.subscreens[self.state.subscreen].dialogue_box):
            self.subscreens[self.state.subscreen].dialogue_box.draw()
        
        # Draw Infinite Hammer mode prompt if active (appears on all subscreens)
        if self.state.game and self.state.game.infinite_hammer_active:
            self._draw_infinite_hammer_prompt()
        
        # Draw forced advance prompt (invader must advance)
        if (self.state.game and self.state.game.pending_forced_advance and 
            self.state.game.forced_advance_dialogue_shown and not self.dialogue_box and
            not self.state.game.advancing_figure_id):
            self._draw_forced_advance_prompt()

        # Modal guard: do not render persistent top prompts while a subscreen
        # dialogue is open (e.g. battle result dialogue) or during game-over
        # resolution.
        subscreen = self.subscreens.get(self.state.subscreen) if self.state.subscreen in self.subscreens else None
        subscreen_dialogue_open = bool(
            subscreen and hasattr(subscreen, 'dialogue_box') and getattr(subscreen, 'dialogue_box')
        )
        in_result_phase = bool(getattr(self.state.game, 'game_over', False) or getattr(self.state.game, 'pending_game_over', False))
        
        # Draw own advance waiting prompt (advancing player waiting for opponent's reaction)
        if (self.state.game and self.state.game.advancing_figure_id and
            self.state.game.advancing_player_id == self.state.game.player_id and
            not self.state.game.turn and not self.state.game.defending_figure_id and
            not subscreen_dialogue_open and not in_result_phase):
            self._draw_own_advance_waiting_prompt()
        
        # Draw opponent advance prompt (opponent advanced, your turn to respond: counter-advance or spend turn)
        if (self.state.game and self.state.game.advancing_figure_id and 
            self.state.game.advancing_player_id != self.state.game.player_id and
            self.state.game.turn and not self.state.game.pending_forced_advance and
            not self.state.game.defending_figure_id and
            not subscreen_dialogue_open and not in_result_phase):
            self._draw_opponent_advance_prompt()
        
        # Draw waiting for defender pick prompt
        if (self.state.game and self.state.game.advancing_figure_id and
            self.state.game.advancing_player_id != self.state.game.player_id and
            not self.state.game.turn and not self.state.game.defending_figure_id and
            self.state.game.waiting_for_defender_pick_shown and
            not subscreen_dialogue_open and not in_result_phase):
            self._draw_waiting_for_defender_pick_prompt()
        
        # Draw defender selection prompt for advancing player
        field_screen = self.subscreens.get('field')
        defender_selecting = field_screen and getattr(field_screen, 'defender_selection_mode', False)
        if (self.state.game and self.state.game.advancing_figure_id and
            self.state.game.pending_defender_selection and
            self.state.game.defender_selection_dialogue_shown and
            self.state.game.turn and
            not self.dialogue_box and not defender_selecting):
            self._draw_select_defender_prompt()
        
        # Draw counter spell waiting prompt if active
        if self.waiting_for_counter_response:
            self._draw_counter_spell_waiting_prompt()
        
        # Draw waiting for battle decision prompt if active (skip in conquer mode — AI always fights)
        if self.state.game and not self.dialogue_box:
            fold_active = (self.state.game.fold_outcome or self.state.game.pending_fold_result)
            is_conquer = (self.state.game.mode == 'conquer')
            if not is_conquer and self.state.game.waiting_for_battle_decision and not fold_active:
                self._draw_waiting_for_battle_decision_prompt()
            elif (not is_conquer and self.state.game.pending_battle_ready and
                  not self.state.game.battle_ready_shown and
                  self.state.game.advancing_player_id != self.state.game.player_id and
                  not fold_active):
                self._draw_waiting_for_battle_decision_prompt()
        
        # Draw counter spell selector on top of everything if active.
        # The selector blits its own dark overlay; do not draw a second one
        # here or the screen darkens twice (cosmetic regression).
        if self.counter_spell_selector:
            self.counter_spell_selector.draw()

        # Draw battle modifier hover text on top of everything
        self._draw_battle_modifier_hover_text()

        # Draw lightweight first-duel coach marks last, after normal prompts.
        self._draw_duel_coach()

        # Announce the battle tab becoming available (locked → unlocked edge).
        self._pump_battle_unlock_pulse()

        # ── Effects layer (banners, bursts, confetti, floaters) ──
        # Drawn above all chrome; an open modal dialogue is re-drawn on top
        # so effects celebrate *behind* it rather than obscuring the text.
        self._fx.draw()
        if self.dialogue_box and self._fx.any_active():
            self.dialogue_box.draw()
        apply_screen_shake(self.window, self._fx.screen_shake_offset())

    def draw_msg(self):
        """Disable floating notifications on the game screen."""
        pass




    def update(self, events):
        """Update the game screen and all relevant components."""
        if not self._ensure_duel_screen_game():
            return
        if (self.state.game and
            getattr(self.state.game, 'pending_conquer_prelude_target', False)):
            self.state.subscreen = 'field'

        # During defender selection, block subscreen changes from button clicks
        # super().update() calls button.update() which can change state.subscreen
        field_screen = self.subscreens.get('field')
        block_subscreen_change = (
            self.state.game and
            self.state.game.advancing_figure_id and
            self.state.game.pending_defender_selection and
            self.state.game.defender_selection_dialogue_shown and
            field_screen and field_screen.defender_selection_mode
        )
        
        if block_subscreen_change:
            saved_subscreen = self.state.subscreen

        coach_step = self._current_duel_coach_step()
        coach_blocks_button_updates = self._duel_coach_blocks_updates(coach_step)

        if not coach_blocks_button_updates:
            super().update()
        
        if block_subscreen_change:
            self.state.subscreen = saved_subscreen

        # Check if game exists (may be None after logout)
        if not self.state.game:
            return

        # Handle click on locked battle button
        if not coach_blocks_button_updates and self.battle_button.locked and self.battle_button.locked_clicked:
            self.battle_button.locked_clicked = False
            if not self.dialogue_box:
                self.queue_or_show_notification({
                    'message': "The Battle Arena becomes available\nonce the battle phase begins.",
                    'actions': ['ok'],
                    'icon': 'magic',
                })

        # Throttle updates to avoid constant re-rendering
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            self.update_game()

        if coach_blocks_button_updates:
            return

        # Lightweight per-frame hover detection for card hands
        self.main_hand.update_hover()
        self.side_hand.update_hover()

        # Update the active subscreen if necessary
        if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
            self.subscreens[self.state.subscreen].update(self.state.game)

    def handle_events(self, events):
        """Handle user input events (e.g., clicks, key presses)."""
        if not self._ensure_duel_screen_game():
            return
        # Handle dialogue box first if present
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                # Handle counter spell responses
                if response == 'counter':
                    self.dialogue_box = None  # Clear dialogue before calling handler
                    self._handle_counter_spell_counter()
                    return
                elif response == 'allow':
                    self.dialogue_box = None  # Clear dialogue before calling handler
                    self._handle_counter_spell_allow()
                    return
                # Handle Infinite Hammer end confirmation
                elif response == 'yes' and self.state.game and self.state.game.infinite_hammer_active:
                    self._end_infinite_hammer_mode()
                # Handle forced advance 'got it!' response — switch to field screen
                elif (response == 'got it!' and self.state.game and 
                      self.state.game.pending_forced_advance):
                    self._handle_forced_advance_dialogue_response()
                # Handle defender selection 'got it!' response — switch to field screen
                elif (response == 'got it!' and self.state.game and
                      self.state.game.advancing_figure_id and
                      self.state.game.pending_defender_selection):
                    self.state.subscreen = 'field'
                    field_screen = self.subscreens.get('field')
                    if field_screen:
                        field_screen.defender_selection_mode = True
                        field_screen._update_defender_selectable()
                    self.state.game.defender_selection_dialogue_shown = True
                # Handle Invader Swap own-defender selection 'ok' response
                elif (response == 'ok' and self.state.game and
                      getattr(self.state.game, 'advancing_figure_id', None) and
                      getattr(self.state.game, 'pending_conquer_own_defender_selection', False)
                      and not getattr(self.state.game, 'defending_figure_id', None)):
                    self.state.subscreen = 'field'
                    field_screen = self.subscreens.get('field')
                    if field_screen:
                        field_screen.conquer_own_defender_mode = True
                elif (response == 'got it!' and self.state.game and
                      getattr(self.state.game, 'pending_conquer_prelude_target', False)):
                    self.state.subscreen = 'field'
                # Handle battle ready 'to battle!' response — submit battle decision
                elif response == 'to battle!' and self._can_submit_battle_decision():
                    self.dialogue_box = None
                    self._submit_battle_decision('battle')
                    self.show_next_queued_notification()
                    return
                # Handle battle ready 'fold' response — submit fold decision
                elif response == 'fold' and self._can_submit_battle_decision():
                    self.dialogue_box = None
                    self._submit_battle_decision('fold')
                    self.show_next_queued_notification()
                    return
                # Handle game-over acknowledgement — for duel mode, the first
                # dialogue ('game_over') just shows result + stats; clicking ok
                # opens the rewards reveal dialogue. For conquer mode (or any
                # case without a pending_game_over payload), navigate away
                # immediately.
                elif (response == 'ok' and self.state.game and
                      self._active_dialogue_type == 'game_over'):
                    pending = getattr(self.state.game, 'pending_game_over', None)
                    is_duel = (getattr(self.state.game, 'mode', None) != 'conquer')
                    self.dialogue_box = None
                    self._active_dialogue_type = None
                    if is_duel and isinstance(pending, dict):
                        self._show_game_over_rewards_dialogue(pending)
                    else:
                        self._on_game_over_acknowledged()
                    return
                # Handle rewards-reveal acknowledgement — actually navigate away
                elif (response == 'ok' and self.state.game and
                      self._active_dialogue_type == 'game_over_rewards'):
                    self.dialogue_box = None
                    self._active_dialogue_type = None
                    self._on_game_over_acknowledged()
                    return
                self.dialogue_box = None  # Close dialogue box
                # Show next queued notification if any
                self.show_next_queued_notification()
                return  # Don't process other events while dialogue is open

        if self._handle_duel_coach_events(events):
            return
        
        # Check for ESC during Infinite Hammer mode (works across all subscreens)
        if self.state.game and self.state.game.infinite_hammer_active:
            if self._handle_infinite_hammer_esc(events):
                return  # ESC was pressed, dialogue shown, block other events
        
        # Block actions for defender who needs to respond (dialogue will handle it)
        if self.need_to_respond_to_spell:
            # Defender should only interact with the dialogue or counter spell selector
            # Handle counter spell selector events if active
            if self.counter_spell_selector:
                result = self.counter_spell_selector.handle_events(events)
                if result == 'CANCEL':
                    # Player cancelled - go back to counter/allow dialogue
                    self.counter_spell_selector = None
                    # Only show dialogue if there isn't one already
                    if not self.dialogue_box:
                        self._show_counter_spell_dialogue()
                elif result:
                    # Player selected a spell to counter with
                    self.counter_spell_selector = None
                    self._cast_counter_spell(result)
            # Allow interaction with log (chat) and guide book while waiting
            if self.state.subscreen in ('log', 'tutorial'):
                self.subscreens[self.state.subscreen].handle_events(events)
            return
        
        # Block all game actions while waiting for opponent to counter/allow our spell.
        # The caster can still navigate between screens (super handles tab buttons)
        # but cannot interact with subscreens, hands, or perform any game action.
        if self.waiting_for_counter_response:
            super().handle_events(events)
            # Allow interaction with log (chat) and guide book while waiting
            if self.state.subscreen in ('log', 'tutorial'):
                self.subscreens[self.state.subscreen].handle_events(events)
            return
        
        # During forced advance, only allow field and build_figure screens
        # (build screen is needed for build+advance with instant charge figures)
        if (self.state.game and self.state.game.pending_forced_advance and
            not self.state.game.advancing_figure_id):
            # Only allow field and build_figure subscreens
            if self.state.subscreen not in ('field', 'build_figure'):
                self.state.subscreen = 'field'
            # Still allow interaction with allowed subscreens
            super().handle_events(events)
            if not self.state.game:
                return
            if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
                self.subscreens[self.state.subscreen].handle_events(events)
            return
        
        # During defender selection, only allow field screen access
        field_screen = self.subscreens.get('field')
        if (self.state.game and self.state.game.advancing_figure_id and
            self.state.game.pending_defender_selection and
            self.state.game.defender_selection_dialogue_shown and
            field_screen and field_screen.defender_selection_mode):
            if self.state.subscreen != 'field':
                self.state.subscreen = 'field'
            super().handle_events(events)
            if not self.state.game:
                return
            if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
                self.subscreens[self.state.subscreen].handle_events(events)
            # After field screen handled events, defender may have been selected
            # (update_from_dict sets pending_battle_ready) — show fight/fold
            # immediately instead of waiting for the throttled update_game cycle.
            if self.state.game and self.state.game.pending_battle_ready:
                self.check_battle_ready()
            return
        
        # During Civil War second figure selection, only allow field screen access
        # Player must pick a second figure or skip — no builds, spells, pickups, etc.
        if (self.state.game and 
            (getattr(self.state.game, 'civil_war_awaiting_second', False) or
             getattr(self.state.game, 'civil_war_defender_second', False))):
            if self.state.subscreen != 'field':
                self.state.subscreen = 'field'
            super().handle_events(events)
            if not self.state.game:
                return
            if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
                self.subscreens[self.state.subscreen].handle_events(events)
            # Civil War second pick may complete defender selection — check immediately
            if self.state.game and self.state.game.pending_battle_ready:
                self.check_battle_ready()
            return
        
        # During active battle (fight/fold decided, battle-move selection, or
        # in-battle), block all normal game actions.  Only battle-related
        # subscreens (battle_shop, battle) and tab navigation are allowed.
        if self.state.game and self.state.game.is_battle_active():
            # Allow tab navigation (super handles tab buttons)
            super().handle_events(events)
            if not self.state.game:
                return
            # Only battle_shop, battle, log, and tutorial subscreens are interactive
            if self.state.subscreen in ('battle_shop', 'battle', 'log', 'tutorial'):
                if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
                    self.subscreens[self.state.subscreen].handle_events(events)
            return
        
        super().handle_events(events)

        # Check if game exists (may be None after logout)
        if not self.state.game:
            return

        # Handle events for the main and side hands
        self.main_hand.handle_events(events)
        self.side_hand.handle_events(events)

        # Pass events to the active subscreen
        if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
            self.subscreens[self.state.subscreen].handle_events(events)
