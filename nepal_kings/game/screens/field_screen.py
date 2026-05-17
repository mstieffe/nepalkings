# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from pygame.locals import *
from config import settings
from game.core.figure_buffs import apply_buffs_allies_to_icon_map
from game.components.conquer_layout import compute_conquer_layout
from game.screens.sub_screen import SubScreen
from game.components.figures.figure_manager import FigureManager
from game.components.figures.figure import Figure
from game.components.figures.figure_icon import FieldFigureIcon
from game.components.figure_detail_box import FigureDetailBox
from game.components.cards.card import Card
from game.components.cards.card_img import CardImg
from utils.figure_service import pickup_figure, upgrade_figure, fetch_figures
from utils.perf_monitor import perf_section
import logging

logger = logging.getLogger('nk.screens.field')


class _ImmediateDialogueResponse:
    """Tiny adapter used by conquer command-panel confirmations."""

    def __init__(self, response):
        self.response = response

    def update(self, _events):
        return self.response



class FieldScreen(SubScreen):
    """Screen for displaying figures on the field."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        self.figure_manager = FigureManager()

        self.figures = []  # List to store the player's figures
        self.figure_icons = []  # List to store figure icons for rendering
        self.icon_cache = {}  # Cache to store pre-rendered icons
        self._conquer_visual_ghost_ids = set()
        self._last_conquer_visual_ghost_key = ()
        self._loaded_conquer_visual_ghost_key = ()
        self._last_conquer_spell_replay_key = ()
        self._last_tactics_hand_support_visibility_key = ()
        self._field_static_surface = None
        self._field_static_surface_key = None
        self._field_static_surface_pos = (0, 0)
        # Cache of (icon, x, y) tuples for the last full figure draw — used
        # by the conquer game screen to re-blit figures on top of the duel
        # lane so figure info boxes stay in the foreground.
        self._last_drawn_figure_layout = None
        self.last_figure_ids = set()  # Track the last set of figure IDs
        self.last_enchantment_state = {}  # Track enchantment state for each figure
        self.last_player_id = None  # Track the last player ID to detect player changes
        self.figure_detail_box = None  # Detail box for selected figure
        self.figure_pending_pickup = None  # Figure waiting for pickup confirmation
        self.figure_pending_upgrade = None  # Figure waiting for upgrade confirmation
        self.figure_pending_defender_selection = None  # Figure waiting for defender selection confirmation
        self.figure_pending_own_defender_selection = None  # Own figure waiting for own-defender confirmation (Invader Swap)
        self._pending_advance_figure = None  # Figure waiting for advance confirmation
        
        # Defender selection mode flag (True when player needs to select defender vs opponent advance)
        self.defender_selection_mode = False
        # Conquer own-defender mode (True when Invader Swap conquerer must pick their OWN defender)
        self.conquer_own_defender_mode = False
        
        # Version of cached figure data last processed by load_figures
        self._last_figures_version = -1
        self._field_static_surface = None
        self._field_static_surface_key = None
        self._field_static_surface_pos = (0, 0)
        
        # Cache for opponent cards (for All Seeing Eye spell)
        self.opponent_card_cache = []  # List of pre-rotated card surfaces
        self.opponent_card_cache_main_count = 0  # Number of main cards in cache
        self.last_opponent_card_ids = set()  # Track opponent card IDs to detect changes
        self._opponent_card_rects = []  # (rect, card_data) for hover detection
        self._opponent_card_hovered_idx = -1  # Index of hovered card (-1 = none)
        self._opponent_hover_surface = None  # Enlarged card surface for hover
        
        # Initialize categorized figures structure
        self.categorized_figures = {
            'self': {'castle': [], 'village': [], 'military': []}, 
            'opponent': {'castle': [], 'village': [], 'military': []}
        }

        # Font for field titles
        self.field_title_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE)
        self.board_title_font = settings.get_font(settings.FIELD_BOARD_TITLE_FONT_SIZE, bold=True)
        
        # Font for target selection prompt
        self.target_prompt_font = settings.get_font(settings.FIELD_TITLE_FONT_SIZE + 4, bold=True)
        
        # Cache All Seeing Eye status to avoid repeated expensive checks
        self.cached_all_seeing_eye_status = None
        self.cached_opponent_all_seeing_eye_status = None
        self.last_all_seeing_eye_check = 0
        self.all_seeing_eye_check_interval = 1000  # Check every 1 second instead of every frame
        self._last_all_seeing_eye_status = None  # Track previous status for change detection
        
        # Load slot icons for compartment backgrounds
        self.slot_icons = self._load_slot_icons()
        
        # Load All Seeing Eye icon for displaying active spell status
        eye_icon_path = 'img/spells/icons/eye.png'
        self.all_seeing_eye_icon = pygame.image.load(eye_icon_path).convert_alpha()
        # Scale to match board title font size
        icon_size = settings.FIELD_BOARD_TITLE_FONT_SIZE
        self.all_seeing_eye_icon = pygame.transform.smoothscale(self.all_seeing_eye_icon, (icon_size, icon_size))

        # Pre-load battle modifier icons for error dialogues
        self._battle_modifier_icons = {}
        self._load_battle_modifier_icons()

        self.init_field_compartments()

    def reset_state(self):
        """Reset all game-specific transient state.

        Called by GameScreen._reset_game_screen_state() when switching games.
        """
        self.figures = []
        self.figure_icons = []
        self.icon_cache = {}
        self.last_figure_ids = set()
        self.last_enchantment_state = {}
        self.last_player_id = None
        self._last_figures_version = -1
        self.categorized_figures = {
            'self': {'castle': [], 'village': [], 'military': []},
            'opponent': {'castle': [], 'village': [], 'military': []}
        }
        self.figure_detail_box = None
        self.figure_pending_pickup = None
        self.figure_pending_upgrade = None
        self.figure_pending_defender_selection = None
        self.figure_pending_own_defender_selection = None
        self._pending_advance_figure = None
        self.defender_selection_mode = False
        self.conquer_own_defender_mode = False
        self.opponent_card_cache = []
        self.opponent_card_cache_main_count = 0
        self.last_opponent_card_ids = set()
        self._opponent_card_rects = []
        self._opponent_card_hovered_idx = -1
        self._opponent_hover_surface = None
        self.cached_all_seeing_eye_status = None
        self.cached_opponent_all_seeing_eye_status = None
        self._last_all_seeing_eye_status = None
        self._conquer_visual_ghost_ids = set()
        self._last_conquer_visual_ghost_key = ()
        self._loaded_conquer_visual_ghost_key = ()
        self._last_conquer_spell_replay_key = ()
        self._last_tactics_hand_support_visibility_key = ()
        self.dialogue_box = None
        self._reset_defender_selectable()
        logger.debug("[FieldScreen] State reset for game switch")

    def update(self, game):
        """Update the game state and load figures."""
        super().update(game)

        self.game = game
        # Only rebuild figures when the background poller delivered new data
        # or when conquer timeline replay changes what field effects/ghosts
        # are allowed to be visible.
        current_version = getattr(game, '_figures_data_version', 0)
        current_ghost_key = self._conquer_visual_ghost_key()
        current_spell_replay_key = self._conquer_spell_replay_visibility_key()
        figures_reloaded = False
        if (current_version != self._last_figures_version
                or current_ghost_key != self._last_conquer_visual_ghost_key
                or current_spell_replay_key != self._last_conquer_spell_replay_key):
            self._last_figures_version = current_version
            self._last_conquer_visual_ghost_key = current_ghost_key
            self._last_conquer_spell_replay_key = current_spell_replay_key
            self.load_figures()
            figures_reloaded = True
        self._sync_tactics_hand_support_visibility(force=figures_reloaded)

    def update_hover_state(self, pos=None):
        """Update hover state for figure icons from the current cursor or event pos."""
        self._sync_field_compartments_layout()
        # Update hover state: only one figure can be hovered at a time
        # Check in reverse order (topmost figures get priority)
        hovered_icon = None
        for icon in reversed(self.figure_icons):
            if pos is not None and hasattr(icon, 'rect_frame'):
                hit = icon.rect_frame.collidepoint(pos)
            elif callable(getattr(icon, 'collide', None)):
                hit = icon.collide()
            else:
                hit = bool(getattr(icon, 'hovered', False))
            if hit and hovered_icon is None:
                icon.hovered = True
                hovered_icon = icon
            else:
                icon.hovered = False

    def _load_battle_modifier_icons(self):
        """Pre-load battle modifier icons for use in error dialogues."""
        import os
        icon_dir = settings.SPELL_ICON_IMG_DIR
        icon_size = settings.BATTLE_MODIFIER_ICON_SIZE
        modifier_types = {
            'Civil War': 'civil_war.png',
            'Peasant War': 'peasant_war.png',
            'Blitzkrieg': 'blitzkrieg.png',
        }
        for modifier_name, filename in modifier_types.items():
            icon_path = os.path.join(icon_dir, filename)
            if os.path.exists(icon_path):
                img = pygame.image.load(icon_path).convert_alpha()
                img = pygame.transform.smoothscale(img, (icon_size, icon_size))
                self._battle_modifier_icons[modifier_name] = img

    def _get_modifier_icon_images(self, modifier_name):
        """Return a list with the modifier icon surface if available, else empty list."""
        icon = self._battle_modifier_icons.get(modifier_name)
        return [icon] if icon else []

    def _load_slot_icons(self):
        """Load and prepare slot icons for compartment backgrounds."""
        slot_icons = {}
        for field_type, img_path in settings.SLOT_ICON_IMG_PATH_DICT.items():
            # Load image
            icon = pygame.image.load(img_path).convert_alpha()
            
            # Set transparency
            icon.set_alpha(settings.SLOT_ICON_TRANSPARENCY)
            
            # Scale to fit compartment (leave some padding)
            target_size = int(settings.FIELD_ICON_WIDTH * 0.7)
            icon = pygame.transform.smoothscale(icon, (target_size, target_size*1.5))
            
            slot_icons[field_type] = icon
        return slot_icons

    def init_field_compartments(self):
        """Initialize compartments for the field screen.
        generates rectangle of size settings.FIELD_ICON_WIDTH and settings.FIELD_HEIGHT. Fill it with settings.FIELD_FILL_COLOR and make a border with settings.FIELD_BORDER_COLOR of width settings.FIELD_BORDER_WIDTH.
        Make 3 fields each for the swlf and opponent, starting at position settings.FIELD_SELF_X, settings.FIELD_OPPONENT_X and y position settings.FIELD_Y.
        Set transparency of the field to settings.FIELD_TRANSPARENCY.
        Margin in x direction is settings.FIELD_ICON_PADDING
        """
        self._sync_field_compartments_layout(force=True)

    def _uses_unified_conquer_layout(self):
        game = getattr(self, 'game', None)
        return bool(
            game
            and getattr(game, 'mode', 'duel') == 'conquer'
            and getattr(game, 'conquer_move_model', 'battle_move') == 'tactics_hand'
        )

    def _conquer_layout_mode(self):
        parent = getattr(getattr(self, 'state', None), 'parent_screen', None)
        parent_mode = getattr(parent, '_conquer_effective_layout_mode', None)
        if callable(parent_mode):
            return parent_mode()
        game = getattr(self, 'game', None)
        if not game:
            return 'pre_battle'
        if getattr(game, 'last_battle_result', None):
            return 'result'
        if (getattr(game, 'battle_turn_player_id', None) is not None
                or getattr(game, 'battle_round', 0) in (1, 2, 3)):
            return 'battle'
        return 'pre_battle'

    def _unified_conquer_compartments(self):
        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode=self._conquer_layout_mode(),
        )
        columns = layout.battlefield.columns
        return {
            'self': {
                'castle': pygame.Rect(columns.you_castle),
                'village': pygame.Rect(columns.you_village),
                'military': pygame.Rect(columns.you_military),
            },
            'opponent': {
                'military': pygame.Rect(columns.opp_military),
                'village': pygame.Rect(columns.opp_village),
                'castle': pygame.Rect(columns.opp_castle),
            },
        }

    def _legacy_field_compartments(self):
        compartments = {'self': {}, 'opponent': {}}

        self_x = self._sx(settings.FIELD_SELF_X)
        opponent_x = self._sx(settings.FIELD_OPPONENT_X)
        field_y = self._sy(settings.FIELD_Y)
        field_step = settings.FIELD_ICON_WIDTH + settings.FIELD_ICON_PADDING_X

        compartments['self']['castle'] = pygame.Rect(self_x, field_y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['self']['village'] = pygame.Rect(self_x + field_step, field_y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['self']['military'] = pygame.Rect(self_x + 2 * field_step, field_y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)

        compartments['opponent']['military'] = pygame.Rect(opponent_x, field_y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['opponent']['village'] = pygame.Rect(opponent_x + field_step, field_y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['opponent']['castle'] = pygame.Rect(opponent_x + 2 * field_step, field_y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        return compartments

    def _sync_field_compartments_layout(self, *, force=False):
        if self._uses_unified_conquer_layout():
            layout_key = ('unified_conquer', self._conquer_layout_mode())
            compartments = self._unified_conquer_compartments()
        else:
            layout_key = ('legacy', getattr(self, '_layout_offset_x', 0), getattr(self, '_layout_offset_y', 0))
            compartments = self._legacy_field_compartments()
        if force or layout_key != getattr(self, '_field_compartment_layout_key', None):
            self.compartments = compartments
            self._field_compartment_layout_key = layout_key

    def _draw_unified_conquer_battlefield_backdrop(self):
        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode=self._conquer_layout_mode(),
        )
        rect = pygame.Rect(layout.battlefield.rect)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (35, 28, 20, 176), panel.get_rect(), border_radius=8)
        pygame.draw.rect(panel, (116, 91, 55, 220), panel.get_rect(), 2, border_radius=8)
        self.window.blit(panel, rect.topleft)

    def _get_opponent_hand_cards(self):
        """Get opponent's hand cards (not in deck, not part of figure)."""
        opponent_id = self.game.opponent_player.get('id') if self.game.opponent_player else None
        if not opponent_id:
            return [], []
        
        # Filter main cards (cards are dictionaries from server)
        opponent_main_cards = [
            card for card in self.game.main_cards
            if card.get('player_id') == opponent_id and not card.get('in_deck') and not card.get('part_of_figure')
        ]
        
        # Filter side cards (cards are dictionaries from server)
        opponent_side_cards = [
            card for card in self.game.side_cards
            if card.get('player_id') == opponent_id and not card.get('in_deck') and not card.get('part_of_figure')
        ]
        
        return opponent_main_cards, opponent_side_cards

    def load_figures(self):
        """Retrieve all figures for the current player."""
        try:
            # Check if player has changed and clear cache if so
            if self.last_player_id != self.game.player_id:
                self.icon_cache.clear()
                self.last_figure_ids.clear()
                self.last_enchantment_state.clear()
                self.last_player_id = self.game.player_id
            
            # Load figures using the game's `get_figures` method
            families = self.figure_manager.families

            # Categorize figures into compartments
            categorized_figures = {
                'self': {'castle': [], 'village': [], 'military': []}, 
                'opponent': {'castle': [], 'village': [], 'military': []}
            }
            
            self_figures = self.game.get_figures(families)
            opponent_figures = self.game.get_figures(families, is_opponent=True)
            self._filter_conquer_timeline_enchantments(
                self_figures + opponent_figures)
            real_figure_ids = {
                getattr(figure, 'id', None)
                for figure in (self_figures + opponent_figures)
            }
            visual_ghost_key = self._conquer_visual_ghost_key()
            visual_ghosts = self._conquer_visual_ghost_figures(real_figure_ids)
            self._conquer_visual_ghost_ids = {
                getattr(figure, 'id', None)
                for figure in visual_ghosts
                if getattr(figure, 'id', None) is not None
            }
            
            for figure in self_figures:
                if figure.family.field == 'castle':
                    categorized_figures['self']['castle'].append(figure)
                elif figure.family.field == 'village':
                    categorized_figures['self']['village'].append(figure)
                elif figure.family.field == 'military':
                    categorized_figures['self']['military'].append(figure)
            for figure in opponent_figures:
                if figure.family.field == 'castle':
                    categorized_figures['opponent']['castle'].append(figure)
                elif figure.family.field == 'village':
                    categorized_figures['opponent']['village'].append(figure)
                elif figure.family.field == 'military':
                    categorized_figures['opponent']['military'].append(figure)

            for figure in visual_ghosts:
                side = 'self' if figure.player_id == self.game.player_id else 'opponent'
                field = getattr(getattr(figure, 'family', None), 'field', None)
                if field in categorized_figures[side]:
                    categorized_figures[side][field].append(figure)
                    
            timeline_figures = [
                figure for figure in visual_ghosts
                if not self._is_conquer_visual_ghost_figure(figure)
            ]
            self.figures = self_figures + opponent_figures + timeline_figures
            self.categorized_figures = categorized_figures

            # Get current figure IDs and enchantment states
            current_figure_ids = {figure.id for figure in self.figures}
            current_figure_ids.update(self._conquer_visual_ghost_ids)
            current_enchantment_state = self._get_enchantment_state()

            # Regenerate icons if figure IDs or enchantments have changed
            visual_ghosts_changed = (
                visual_ghost_key != getattr(self, '_loaded_conquer_visual_ghost_key', ())
            )
            figures_changed = current_figure_ids != self.last_figure_ids or visual_ghosts_changed
            enchantments_changed = current_enchantment_state != self.last_enchantment_state
            
            # Check if All Seeing Eye status changed (need to regenerate icons for visibility)
            all_seeing_eye_changed = (self.cached_all_seeing_eye_status != self._last_all_seeing_eye_status)
            
            if figures_changed or enchantments_changed or all_seeing_eye_changed:
                if all_seeing_eye_changed:
                    logger.debug(f"[FIELD_SCREEN] All Seeing Eye status changed: {self._last_all_seeing_eye_status} -> {self.cached_all_seeing_eye_status}")
                    # Clear icon cache for opponent figures to regenerate with new visibility
                    self.icon_cache.clear()
                    self._last_all_seeing_eye_status = self.cached_all_seeing_eye_status
                if enchantments_changed:
                    # Clear cache for figures whose enchantments changed
                    changed_ids = []
                    for figure_id in current_figure_ids:
                        old_enchant = self.last_enchantment_state.get(figure_id)
                        new_enchant = current_enchantment_state.get(figure_id)
                        if old_enchant != new_enchant:
                            if figure_id in self.icon_cache:
                                del self.icon_cache[figure_id]
                            changed_ids.append(figure_id)
                    if changed_ids:
                        logger.debug(f"[FIELD_SCREEN] Enchantments changed for {len(changed_ids)} figure(s), regenerating")
                
                # Remove stale entries from icon_cache (destroyed figures)
                stale_ids = self.last_figure_ids - current_figure_ids
                for stale_id in stale_ids:
                    if stale_id in self.icon_cache:
                        del self.icon_cache[stale_id]
                
                # check if the figure is opponent or not
                self._generate_figure_icons()
                self.last_figure_ids = current_figure_ids
                self.last_enchantment_state = current_enchantment_state
                self._loaded_conquer_visual_ghost_key = visual_ghost_key
        except Exception as e:
            logger.error(f"Error loading figures: {e}")

    def _conquer_visual_ghost_specs(self):
        if not self.game or getattr(self.game, 'mode', 'duel') != 'conquer':
            return []
        parent = getattr(getattr(self, 'state', None), 'parent_screen', None)
        provider = getattr(parent, 'conquer_field_visual_ghost_specs', None)
        if not callable(provider):
            return []
        try:
            specs = provider() or []
        except Exception:
            return []
        return [spec for spec in specs if isinstance(spec, dict)]

    def _conquer_spell_replay_visibility(self):
        if not self.game or getattr(self.game, 'mode', 'duel') != 'conquer':
            return None
        parent = getattr(getattr(self, 'state', None), 'parent_screen', None)
        provider = getattr(parent, 'conquer_prelude_enchantment_visibility', None)
        if not callable(provider):
            return None
        try:
            visibility = provider() or {}
        except Exception:
            return None
        if not isinstance(visibility, dict):
            return None
        return visibility

    def _conquer_spell_replay_visibility_key(self):
        visibility = self._conquer_spell_replay_visibility()
        if not visibility:
            return ()
        tracked = tuple(sorted(tuple(row) for row in visibility.get('tracked', set())))
        revealed = tuple(sorted(tuple(row) for row in visibility.get('revealed', set())))
        return tracked, revealed

    def _filter_conquer_timeline_enchantments(self, figures):
        visibility = self._conquer_spell_replay_visibility()
        if not visibility:
            return
        tracked = {tuple(row) for row in visibility.get('tracked', set())}
        revealed = {tuple(row) for row in visibility.get('revealed', set())}
        if not tracked:
            return
        for figure in figures or []:
            enchantments = getattr(figure, 'active_enchantments', None)
            if not enchantments:
                continue
            figure_id = getattr(figure, 'id', None)
            filtered = []
            for enchantment in enchantments:
                if not isinstance(enchantment, dict):
                    filtered.append(enchantment)
                    continue
                spell_name = enchantment.get('spell_name')
                key = (spell_name, figure_id)
                if key in tracked and key not in revealed:
                    continue
                filtered.append(enchantment)
            figure.active_enchantments = filtered

    def _conquer_visual_ghost_key(self):
        rows = []
        for spec in self._conquer_visual_ghost_specs():
            snapshot = spec.get('snapshot') if isinstance(spec.get('snapshot'), dict) else {}
            target_id = spec.get('target_id')
            if target_id is None:
                continue
            rows.append((
                target_id,
                snapshot.get('player_id'),
                snapshot.get('field'),
                snapshot.get('family_name') or snapshot.get('name'),
                snapshot.get('name'),
                snapshot.get('suit'),
                bool(spec.get('visual_only', True)),
                bool(spec.get('force_visible', True)),
                spec.get('spell_name'),
                spec.get('phase'),
            ))
        return tuple(sorted(rows))

    def _conquer_visual_ghost_figures(self, existing_ids):
        existing_ids = set(existing_ids or [])
        ghosts = []
        seen = set()
        for spec in self._conquer_visual_ghost_specs():
            target_id = spec.get('target_id')
            if target_id is None or target_id in existing_ids or target_id in seen:
                continue
            snapshot = spec.get('snapshot') if isinstance(spec.get('snapshot'), dict) else {}
            figure = self._build_conquer_visual_ghost_figure(snapshot, target_id, spec)
            if figure is None:
                continue
            ghosts.append(figure)
            seen.add(target_id)
        return ghosts

    def _build_conquer_visual_ghost_figure(self, snapshot, target_id, spec=None):
        spec = spec if isinstance(spec, dict) else {}
        family_name = snapshot.get('family_name') or snapshot.get('name')
        family = (getattr(self.figure_manager, 'families', None) or {}).get(family_name)
        if family is None:
            return None
        cards = self._cards_from_conquer_snapshot(snapshot.get('cards') or [])
        if not any(cards.values()):
            return None
        number_card = (cards.get('number') or [None])[0]
        upgrade_card = (cards.get('upgrade') or [None])[0]
        key_cards = list(cards.get('key') or [])
        if not key_cards and number_card is None:
            return None

        suit = snapshot.get('suit')
        matched = None
        for candidate in getattr(family, 'figures', []) or []:
            if suit and getattr(candidate, 'suit', None) != suit:
                continue
            matched = candidate
            if number_card and getattr(candidate, 'number_card', None):
                if candidate.number_card.rank == number_card.rank:
                    break

        def flag(name, default=False):
            if name in snapshot:
                return bool(snapshot.get(name))
            return bool(getattr(matched, name, default)) if matched is not None else default

        figure = Figure(
            name=snapshot.get('name') or family_name,
            sub_name=snapshot.get('sub_name', ''),
            suit=suit,
            family=family,
            key_cards=key_cards,
            number_card=number_card,
            upgrade_card=upgrade_card,
            description=snapshot.get('description', ''),
            upgrade_family_name=snapshot.get('upgrade_family_name'),
            produces={},
            requires={},
            id=target_id,
            player_id=snapshot.get('player_id'),
            cannot_attack=flag('cannot_attack'),
            must_be_attacked=flag('must_be_attacked'),
            rest_after_attack=flag('rest_after_attack'),
            distance_attack=flag('distance_attack'),
            buffs_allies=flag('buffs_allies'),
            buffs_allies_defence=flag('buffs_allies_defence'),
            blocks_bonus=flag('blocks_bonus'),
            cannot_defend=flag('cannot_defend'),
            instant_charge=flag('instant_charge'),
            cannot_be_blocked=flag('cannot_be_blocked'),
            cannot_be_targeted=flag('cannot_be_targeted'),
            checkmate=flag('checkmate'),
            override_base_power=getattr(matched, 'override_base_power', None),
        )
        figure._conquer_timeline_snapshot = True
        figure._conquer_visual_only = bool(spec.get('visual_only', True))
        figure._conquer_force_visible = bool(spec.get('force_visible', True))
        figure._conquer_snapshot_spell_name = spec.get('spell_name')
        figure._conquer_snapshot_phase = spec.get('phase')
        figure._conquer_explosion_ghost = spec.get('spell_name') == 'Explosion'
        return figure

    @staticmethod
    def _cards_from_conquer_snapshot(cards_data):
        cards = {'key': [], 'number': [], 'upgrade': []}
        number_ranks = {str(rank) for rank in getattr(settings, 'NUMBER_CARDS', [])}
        for card_data in cards_data or []:
            if not isinstance(card_data, dict):
                continue
            rank = card_data.get('rank')
            suit = card_data.get('suit')
            if not rank or not suit:
                continue
            value = card_data.get('value')
            if value is None:
                value = getattr(settings, 'RANK_TO_VALUE', {}).get(str(rank), 0)
            card = Card(
                rank=rank,
                suit=suit,
                value=int(value or 0),
                id=card_data.get('card_id') or card_data.get('id'),
                game_id=card_data.get('game_id'),
                player_id=card_data.get('player_id'),
                in_deck=card_data.get('in_deck'),
                deck_position=card_data.get('deck_position'),
                part_of_figure=card_data.get('part_of_figure'),
                type=card_data.get('card_type') or card_data.get('type'),
                role=card_data.get('role'),
            )
            role = card_data.get('role')
            if role in cards:
                cards[role].append(card)
            elif str(rank) in number_ranks and not cards['number']:
                cards['number'].append(card)
            else:
                cards['key'].append(card)
        return cards

    @staticmethod
    def _is_conquer_visual_ghost_figure(figure):
        return bool(getattr(figure, '_conquer_visual_only', False))

    @staticmethod
    def _is_conquer_timeline_snapshot_figure(figure):
        return bool(getattr(figure, '_conquer_timeline_snapshot', False))

    def _get_enchantment_state(self):
        """
        Create a snapshot of current enchantment state for all figures.
        Returns a dict mapping figure_id to tuple of enchantment data.
        """
        enchantment_state = {}
        for figure in self.figures:
            if hasattr(figure, 'active_enchantments') and figure.active_enchantments:
                # Create a hashable representation of enchantments
                enchantments_tuple = tuple(
                    (e.get('spell_name'), e.get('power_modifier'))
                    for e in figure.active_enchantments
                )
                enchantment_state[figure.id] = enchantments_tuple
            else:
                enchantment_state[figure.id] = None
        return enchantment_state

    def _generate_figure_icons(self, is_visible=True):
        """Generate and cache icons for the current figures."""


        
        self.figure_icons = []
        
        # Collect all player figures for battle bonus calculation
        all_player_figures = []
        for field_type, figures in self.categorized_figures['self'].items():
            all_player_figures.extend(
                figure for figure in figures
                if not self._is_conquer_visual_ghost_figure(figure)
            )
        
        # Collect all opponent figures for their battle bonus calculation
        all_opponent_figures = []
        for field_type, figures in self.categorized_figures['opponent'].items():
            all_opponent_figures.extend(
                figure for figure in figures
                if not self._is_conquer_visual_ghost_figure(figure)
            )
        
        # Calculate resources for both self and opponent
        # Use the cached figure_manager instead of creating a new one
        try:
            families = self.figure_manager.families
            resources_data = self.game.calculate_resources(families, is_opponent=False)
            opponent_resources_data = self.game.calculate_resources(families, is_opponent=True)
        except Exception as e:
            resources_data = None
            opponent_resources_data = None

        # Check if current player has cast "All Seeing Eye" spell
        # This makes opponent figures visible to the current player
        # Use cached status if available, otherwise check and cache
        current_time = pygame.time.get_ticks()
        if self.cached_all_seeing_eye_status is None or current_time - self.last_all_seeing_eye_check > self.all_seeing_eye_check_interval:
            self.cached_all_seeing_eye_status = self.game.has_active_all_seeing_eye()
            self.last_all_seeing_eye_check = current_time
        
        conquer_revealed_support_ids = self._tactics_hand_revealed_support_figure_ids()

        for category, compartments in self.categorized_figures.items():
            for field_type, figures in compartments.items():
                for figure in figures:
                    figure_is_ghost = self._is_conquer_visual_ghost_figure(figure)
                    # Determine which figures and resources to use based on category
                    figures_list = all_opponent_figures if category == 'opponent' else all_player_figures
                    resources = None if figure_is_ghost else (
                        opponent_resources_data if category == 'opponent' else resources_data)
                    
                    is_visible = self._tactics_hand_figure_visible(
                        figure, category, conquer_revealed_support_ids)
                    
                    if figure.id not in self.icon_cache:
                        self.icon_cache[figure.id] = FieldFigureIcon(
                            window=self.window,
                            game=self.game,
                            figure=figure,
                            is_visible=is_visible,
                            all_player_figures=figures_list,
                            resources_data=resources,
                        )
                    else:
                        # Update cached icon with new figure reference (in case enchantments changed)
                        self.icon_cache[figure.id].figure = figure
                        self.icon_cache[figure.id].game = self.game
                        # Update visibility and recalculate battle bonus for cached icon
                        self.icon_cache[figure.id].is_visible = is_visible
                        self.icon_cache[figure.id].battle_bonus_received = self.icon_cache[figure.id]._calculate_battle_bonus_received(figures_list)
                        self.icon_cache[figure.id].has_deficit = self.icon_cache[figure.id]._check_resource_deficit(resources)
                    if figure_is_ghost:
                        self.icon_cache[figure.id].defender_selectable = False
                        self.icon_cache[figure.id].in_defender_selection_mode = False
                    elif not (getattr(self, 'defender_selection_mode', False)
                              or getattr(self, 'conquer_own_defender_mode', False)):
                        self.icon_cache[figure.id].defender_selectable = True
                        self.icon_cache[figure.id].in_defender_selection_mode = False
                    self.figure_icons.append(self.icon_cache[figure.id])

        # ── Apply buffs_allies bonus to village figure icons ──
        for category in ('self', 'opponent'):
            all_figs = []
            for field_type, figures in self.categorized_figures[category].items():
                all_figs.extend(
                    figure for figure in figures
                    if not self._is_conquer_visual_ghost_figure(figure)
                )
            apply_buffs_allies_to_icon_map(
                all_figs,
                self.icon_cache,
                has_deficit=lambda fig: (
                    fig.id in self.icon_cache and self.icon_cache[fig.id].has_deficit
                ),
            )

    def handle_events(self, events):
        """Handle events for interacting with the field."""
        super().handle_events(events)
        
        # Update hover state on pointer movement and click/touch events. Web
        # clients can deliver a click without a preceding motion event, and a
        # background figure refresh may otherwise leave stale hover state.
        for event in events:
            if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN,
                              pygame.MOUSEBUTTONUP):
                self.update_hover_state(getattr(event, 'pos', None))
        
        # Handle dialogue box events first (before target selection mode check)
        # This ensures auto-closing dialogues work even during target selection
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response == 'auto_close':
                # Auto-close: just close dialogue and continue to other event handling
                self.dialogue_box = None
            elif response:
                # Remember the current dialogue so we can detect if a new one was created
                dialogue_before_response = self.dialogue_box
                # Button clicked - process the response
                if response == 'yes':
                    # Block all actions in finished games
                    if getattr(self.game, 'game_over', False):
                        self.dialogue_box = None
                        return

                    # Block double-actions while a previous action is still in progress
                    if self.game.action_in_progress:
                        self.dialogue_box = None
                        return

                    if self._is_tactics_hand_battle_field_view_only():
                        self.figure_pending_pickup = None
                        self.figure_pending_upgrade = None
                        self.figure_pending_defender_selection = None
                        self.figure_pending_own_defender_selection = None
                        self._pending_advance_figure = None
                        self.dialogue_box = None
                        return

                    # Check if player is waiting for counter spell response
                    if hasattr(self.state, 'parent_screen') and hasattr(self.state.parent_screen, 'waiting_for_counter_response'):
                        if self.state.parent_screen.waiting_for_counter_response:
                            self.dialogue_box = None
                            self.make_dialogue_box(
                                message="You cannot pickup or upgrade figures while waiting for opponent's response to your spell.",
                                actions=['ok'],
                                icon="error",
                                title="Action Blocked"
                            )
                            return

                    # Check if battle is active
                    if hasattr(self.game, 'is_battle_active') and self.game.is_battle_active():
                        self.dialogue_box = None
                        self.make_dialogue_box(
                            message="You cannot pickup or upgrade figures while a battle is in progress.",
                            actions=['ok'],
                            icon="error",
                            title="Action Blocked"
                        )
                        return
                    
                    # Check which action is pending
                    if self.figure_pending_pickup:
                        # User confirmed pickup
                        try:
                            self.game.lock_actions()
                            # Call server to pick up the figure
                            result = pickup_figure(
                                self.figure_pending_pickup.id,
                                self.game.player_id,
                                self.game.game_id
                            )
                            
                            if result.get('success'):
                                # Success message
                                card_count = result.get('main_card_count', 0) + result.get('side_card_count', 0)
                                logger.debug(f"Successfully picked up {self.figure_pending_pickup.name}. {card_count} cards returned to hand.")
                                
                                # Refresh game state (cards, turn, figures) from server
                                # (update() -> _apply_game_dict -> unlock_actions)
                                self.game.update()
                                
                                self.state.set_msg(f"Picked up {self.figure_pending_pickup.name}. {card_count} cards returned to your hand.")
                                
                            else:
                                # Show error message
                                error_msg = result.get('message', 'Unknown error')
                                logger.error(f"Failed to pick up figure: {error_msg}")
                                self.state.set_msg(f"Failed to pick up figure: {error_msg}")
                                self.game.unlock_actions()
                                
                        except Exception as e:
                            logger.error(f"Error picking up figure: {str(e)}")
                            self.state.set_msg(f"Error picking up figure: {str(e)}")
                            self.game.unlock_actions()
                        
                        # Close the detail box and dialogue box
                        self.figure_detail_box = None
                        for icon in self.figure_icons:
                            icon.clicked = False
                        self.figure_pending_pickup = None
                    
                    elif getattr(self, '_pending_advance_figure', None):
                        # User confirmed advance
                        figure = self._pending_advance_figure
                        self._pending_advance_figure = None
                        # Restore advance overlay flag on all icons (was disabled for dialogue preview)
                        for icon in self.figure_icons:
                            icon.show_advance_overlay = True
                        from utils.game_service import advance_figure
                        try:
                            self.game.lock_actions()
                            result = advance_figure(
                                self.game.game_id,
                                self.game.player_id,
                                figure.id
                            )
                            if result.get('success'):
                                logger.debug(f"[FIELD] Advanced {figure.name} successfully")
                                self.state.set_msg(f"Advanced {figure.name} toward battle!")
                                # Update game state from response
                                # (update_from_dict -> unlock_actions)
                                if result.get('game'):
                                    self.game.update_from_dict(result['game'])
                                # Reload figures to refresh icons
                                self.load_figures()
                                
                                # Check if Civil War needs a second figure
                                if result.get('civil_war_need_second'):
                                    civil_war_color = result.get('civil_war_color', '')
                                    color_name = 'red' if civil_war_color == 'offensive' else 'black'
                                    self.game.civil_war_awaiting_second = True
                                    self.game.civil_war_required_color = civil_war_color
                                    cw_icons = self._get_modifier_icon_images('Civil War')
                                    self.make_dialogue_box(
                                        message=f"Civil War! You may select a second village figure of the same color ({color_name}), or fight with only one figure.",
                                        actions=['select second', 'skip'],
                                        images=cw_icons if cw_icons else None,
                                        icon="magic" if not cw_icons else None,
                                        title="Civil War - Second Figure"
                                    )
                                else:
                                    # Clear Civil War second pick state if it was active
                                    if hasattr(self.game, 'civil_war_awaiting_second'):
                                        self.game.civil_war_awaiting_second = False
                                        self.game.civil_war_required_color = None
                                    # Clear forced advance state if it was a forced advance
                                    if self.game.forced_advance_dialogue_shown:
                                        self.game.pending_forced_advance = False
                                    # Trigger advance notification check (Blitzkrieg needs the combined dialogue)
                                    self.game.pending_own_advance_notification = True
                                    self.game.own_advance_figure_name = figure.name
                            else:
                                error_msg = result.get('message', 'Unknown error')
                                logger.error(f"[FIELD] Failed to advance: {error_msg}")
                                self.make_dialogue_box(
                                    message=f"Cannot advance: {error_msg}",
                                    actions=['ok'],
                                    icon="error",
                                    title="Advance Failed"
                                )
                                self.game.unlock_actions()
                        except Exception:
                            self.game.unlock_actions()
                            raise

                    elif self.figure_pending_defender_selection:
                        # User confirmed defender selection
                        target_figure = self.figure_pending_defender_selection
                        from utils.game_service import select_defender
                        try:
                            self.game.lock_actions()
                            result = select_defender(
                                self.game.game_id,
                                self.game.player_id,
                                target_figure.id
                            )
                            
                            if result.get('success'):
                                if result.get('conquer_result'):
                                    if result.get('game'):
                                        self.game.update_from_dict(result['game'])
                                    self.load_figures()
                                    self.defender_selection_mode = False
                                    self._reset_defender_selectable()
                                    self.game.pending_defender_selection = False
                                    if hasattr(self.game, 'civil_war_defender_second'):
                                        self.game.civil_war_defender_second = False
                                        self.game.civil_war_required_color = None
                                    parent = getattr(self.state, 'parent_screen', None)
                                    if parent and hasattr(parent, '_handle_conquer_result_response'):
                                        parent._handle_conquer_result_response(result)
                                    else:
                                        self.game.game_over = True
                                        self.game.conquer_result = result.get('conquer_result')
                                    self.figure_pending_defender_selection = None
                                    self.dialogue_box = None
                                    return

                                # Check if this was a deficit auto-loss
                                if result.get('deficit_loss'):
                                    # Defender's figure had a deficit — they auto-lose
                                    deficit_fig_name = result.get('deficit_figure_name', 'Unknown')
                                    winner = result.get('winner', 'You')
                                    points = result.get('points', 10)
                                    # Update game state from response
                                    if result.get('game'):
                                        self.game.update_from_dict(result['game'])
                                    self.load_figures()
                                    self.defender_selection_mode = False
                                    self._reset_defender_selectable()
                                    self.game.pending_defender_selection = False
                                    # Clear Civil War state
                                    if hasattr(self.game, 'civil_war_defender_second'):
                                        self.game.civil_war_defender_second = False
                                        self.game.civil_war_required_color = None
                                    # Mark fold result as shown so check_fold_result() doesn't double-show
                                    self.game.fold_result_shown = True
                                    new_round = self.game.current_round
                                    self.make_dialogue_box(
                                        message=f"Opponent's {deficit_fig_name} has a resource deficit and cannot fight!\n\n{winner} wins {points} points.\n\nRound {new_round} begins.",
                                        actions=['ok'],
                                        icon="magic",
                                        title="Resource Deficit — Victory!"
                                    )
                                # Check if Civil War needs a second defender
                                elif result.get('civil_war_need_second'):
                                    if result.get('game'):
                                        self.game.update_from_dict(result['game'])
                                    self.load_figures()
                                    civil_war_color = result.get('civil_war_color', '')
                                    color_name = 'red' if civil_war_color == 'offensive' else 'black'
                                    self.game.civil_war_defender_second = True
                                    self.game.civil_war_required_color = civil_war_color
                                    self.game.pending_battle_ready = False
                                    self.game.battle_ready_shown = False
                                    cw_icons = self._get_modifier_icon_images('Civil War')
                                    self.make_dialogue_box(
                                        message=f"Civil War! You may select a second opponent village figure of the same color ({color_name}), or proceed with only one.",
                                        actions=['select second', 'skip'],
                                        images=cw_icons if cw_icons else None,
                                        icon="magic" if not cw_icons else None,
                                        title="Civil War - Second Defender"
                                    )
                                    # Update selectable figures for second pick
                                    self._update_defender_selectable()
                                else:
                                    # Normal success — update and exit defender mode
                                    if result.get('game'):
                                        self.game.update_from_dict(result['game'])
                                    self.load_figures()
                                    self.defender_selection_mode = False
                                    self._reset_defender_selectable()
                                    selected_name = result.get('figure_name', target_figure.name)
                                    if result.get('civil_war_second_rejected'):
                                        self.make_dialogue_box(
                                            message=result.get(
                                                'message',
                                                'Civil War requires same-color defenders. Keeping first defender only.'
                                            ),
                                            actions=['ok'],
                                            icon='magic',
                                            title='Civil War'
                                        )
                                    self.state.set_msg(f"Selected {selected_name} as opponent's defender.")
                                    self.game.pending_defender_selection = False
                                    # Defender was selected manually. Re-arm battle-ready
                                    # transition in case a stale guard flag was left set.
                                    if (self.game.advancing_figure_id and
                                            self.game.defending_figure_id and
                                            not self.game.battle_confirmed and
                                            not self.game.fold_outcome):
                                        self.game.waiting_for_battle_decision = False
                                        self.game.battle_ready_shown = False
                                        self.game.pending_battle_ready = True
                                    logger.debug(f"[SELECT_DEFENDER] Success: defender={target_figure.name} (id={target_figure.id}), "
                                          f"pending_battle_ready={self.game.pending_battle_ready}, "
                                          f"battle_ready_shown={self.game.battle_ready_shown}")
                                    # Clear Civil War defender state
                                    if hasattr(self.game, 'civil_war_defender_second'):
                                        self.game.civil_war_defender_second = False
                                        self.game.civil_war_required_color = None
                            else:
                                error_msg = result.get('message', 'Unknown error')
                                self.make_dialogue_box(
                                    message=f"Failed to select defender: {error_msg}",
                                    actions=['ok'],
                                    icon="error",
                                    title="Error"
                                )
                                self.game.unlock_actions()
                        except Exception:
                            self.game.unlock_actions()
                            raise
                        
                        self.figure_pending_defender_selection = None
                    
                    elif self.figure_pending_own_defender_selection:
                        # Invader Swap: conquerer confirmed selection of their own defender
                        target_figure = self.figure_pending_own_defender_selection
                        from utils.game_service import select_conquer_own_defender
                        try:
                            self.game.lock_actions()
                            result = select_conquer_own_defender(
                                self.game.game_id,
                                self.game.player_id,
                                target_figure.id,
                            )
                            if result.get('success'):
                                if result.get('game'):
                                    self.game.update_from_dict(result['game'])
                                self.load_figures()
                                self.game.pending_conquer_own_defender_selection = False
                                if result.get('civil_war_need_second'):
                                    civil_war_color = result.get('civil_war_color', '')
                                    color_name = 'red' if civil_war_color == 'offensive' else 'black'
                                    self.conquer_own_defender_mode = True
                                    self.game.civil_war_defender_second = True
                                    self.game.civil_war_required_color = civil_war_color
                                    self.game.pending_battle_ready = False
                                    self.game.battle_ready_shown = False
                                    cw_icons = self._get_modifier_icon_images('Civil War')
                                    self.make_dialogue_box(
                                        message=f"Civil War! You may select a second own village figure of the same color ({color_name}), or proceed with only one.",
                                        actions=['select second', 'skip'],
                                        images=cw_icons if cw_icons else None,
                                        icon="magic" if not cw_icons else None,
                                        title="Civil War - Second Defender",
                                    )
                                else:
                                    self.conquer_own_defender_mode = False
                                    self._reset_defender_selectable()
                                    self.game.civil_war_defender_second = False
                                    self.game.civil_war_required_color = None
                                    # Re-arm battle-ready
                                    if (self.game.advancing_figure_id
                                            and self.game.defending_figure_id
                                            and not self.game.battle_confirmed
                                            and not self.game.fold_outcome):
                                        self.game.waiting_for_battle_decision = False
                                        self.game.battle_ready_shown = False
                                        self.game.pending_battle_ready = True
                                    selected_name = result.get('figure_name', target_figure.name)
                                    self.state.set_msg(f"Selected {selected_name} as your defender.")
                            else:
                                error_msg = result.get('message', 'Unknown error')
                                self.make_dialogue_box(
                                    message=f"Failed to select defender: {error_msg}",
                                    actions=['ok'],
                                    icon="error",
                                    title="Error",
                                )
                                self.game.unlock_actions()
                        except Exception:
                            self.game.unlock_actions()
                            raise
                        self.figure_pending_own_defender_selection = None

                    elif self.figure_pending_upgrade:
                        # User confirmed upgrade
                        self.game.lock_actions()
                        try:
                            # Find the upgrade card in the player's hand
                            main_hand, side_hand = self.game.get_hand()
                            hand_cards = main_hand + side_hand
                            
                            upgrade_card_template = self.figure_pending_upgrade.upgrade_card
                            upgrade_card = None
                            
                            # Find the actual card in hand that matches the upgrade_card template
                            for card in hand_cards:
                                if card.to_tuple() == upgrade_card_template.to_tuple():
                                    upgrade_card = card
                                    break
                            
                            if not upgrade_card:
                                raise Exception("Upgrade card not found in hand")
                            
                            # Determine card type
                            upgrade_card_type = 'main' if upgrade_card.is_main_card else 'side'
                            
                            # Look up the upgrade target family to get produces/requires
                            target_produces = {}
                            target_requires = {}
                            target_family_name = self.figure_pending_upgrade.upgrade_family_name
                            if target_family_name and target_family_name in self.figure_manager.families:
                                target_family = self.figure_manager.families[target_family_name]
                                for tmpl in target_family.figures:
                                    if tmpl.suit == self.figure_pending_upgrade.suit:
                                        # Match by number card if both have one
                                        if self.figure_pending_upgrade.number_card and tmpl.number_card:
                                            if tmpl.number_card.rank == self.figure_pending_upgrade.number_card.rank:
                                                target_produces = tmpl.produces or {}
                                                target_requires = tmpl.requires or {}
                                                break
                                        elif not self.figure_pending_upgrade.number_card and not tmpl.number_card:
                                            target_produces = tmpl.produces or {}
                                            target_requires = tmpl.requires or {}
                                            break
                            
                            # Call server to upgrade the figure
                            result = upgrade_figure(
                                self.figure_pending_upgrade.id,
                                self.game.player_id,
                                self.game.game_id,
                                upgrade_card.id,
                                upgrade_card_type,
                                produces=target_produces,
                                requires=target_requires
                            )
                            
                            if result.get('success'):
                                # Success message
                                logger.debug(f"Successfully upgraded {self.figure_pending_upgrade.name} to {self.figure_pending_upgrade.upgrade_family_name}.")
                                self.state.set_msg(f"Upgraded {self.figure_pending_upgrade.name} to {self.figure_pending_upgrade.upgrade_family_name}.")
                                # Refresh full game state (turn, cards) and figures from server
                                # (update() -> _apply_game_dict -> unlock_actions)
                                self.game.update()
                                self.load_figures()
                                logger.debug(f"[FIELD_SCREEN] Figures reloaded after upgrade, count: {len(self.figures)}")
                            else:
                                # Show error message
                                error_msg = result.get('message', 'Unknown error')
                                logger.error(f"Failed to upgrade figure: {error_msg}")
                                self.state.set_msg(f"Failed to upgrade figure: {error_msg}")
                                self.game.unlock_actions()
                                
                        except Exception as e:
                            logger.error(f"Error upgrading figure: {str(e)}")
                            self.state.set_msg(f"Error upgrading figure: {str(e)}")
                            self.game.unlock_actions()
                        
                        # Close the detail box and dialogue box
                        self.figure_detail_box = None
                        for icon in self.figure_icons:
                            icon.clicked = False
                        self.figure_pending_upgrade = None
                        
                elif response == 'no' or response == 'cancel':
                    # User cancelled action
                    self.figure_pending_pickup = None
                    self.figure_pending_upgrade = None
                    self.figure_pending_defender_selection = None
                    self.figure_pending_own_defender_selection = None
                    self._pending_advance_figure = None
                    # Restore advance overlay flag on all icons (was disabled for dialogue preview)
                    for icon in self.figure_icons:
                        icon.show_advance_overlay = True
                    # Keep the detail box open
                
                elif response == 'select second':
                    # Civil War — player wants to pick a second figure
                    # Just dismiss dialogue, the civil_war_awaiting_second / 
                    # civil_war_defender_second flag stays set so they can pick
                    pass
                elif response == 'skip':
                    if getattr(self.game, 'game_over', False):
                        self.dialogue_box = None
                        return
                    # Civil War — player skips the second figure pick
                    from utils.game_service import skip_civil_war_second
                    if getattr(self.game, 'civil_war_awaiting_second', False):
                        result = skip_civil_war_second(
                            self.game.game_id, self.game.player_id, 'advance'
                        )
                        if result.get('success'):
                            if result.get('game'):
                                self.game.update_from_dict(result['game'])
                        self.game.civil_war_awaiting_second = False
                        self.game.civil_war_required_color = None
                        # Clear forced advance state if it was a forced advance
                        if self.game.forced_advance_dialogue_shown:
                            self.game.pending_forced_advance = False
                        # Trigger advance notification check (Blitzkrieg needs the combined dialogue)
                        self.game.pending_own_advance_notification = True
                        self.game.own_advance_figure_name = None
                    elif getattr(self.game, 'civil_war_defender_second', False):
                        skip_context = (
                            'own_defender' if self.conquer_own_defender_mode
                            else 'defender'
                        )
                        result = skip_civil_war_second(
                            self.game.game_id, self.game.player_id, skip_context
                        )
                        if result.get('success'):
                            if result.get('game'):
                                self.game.update_from_dict(result['game'])
                            self.game.civil_war_defender_second = False
                            self.game.civil_war_required_color = None
                            if self.conquer_own_defender_mode:
                                self.conquer_own_defender_mode = False
                                self.game.pending_conquer_own_defender_selection = False
                            else:
                                self.defender_selection_mode = False
                                self._reset_defender_selectable()
                                self.game.pending_defender_selection = False
                        else:
                            self.make_dialogue_box(
                                message=f"Failed to skip second figure: {result.get('message', 'Unknown error')}",
                                actions=['ok'],
                                icon="error",
                                title="Error",
                            )
                elif response == 'ok' or response == 'got it!':
                    # Simple acknowledgment
                    pass
                
                # Close the dialogue box (only if no new dialogue was created during response handling)
                if self.dialogue_box is dialogue_before_response:
                    self.dialogue_box = None
                return  # Don't process other events when button was clicked
            else:
                # Dialogue is still open, no response yet - block other events
                return

        if self._is_tactics_hand_battle_field_view_only():
            self._handle_tactics_hand_battle_inspection(events)
            return
        
        # If in target selection mode, only allow figure selection
        pending_spell_cast = hasattr(self.state, 'pending_spell_cast') and self.state.pending_spell_cast
        pending_prelude_target = getattr(self.state, 'pending_conquer_prelude_target', None)
        if pending_spell_cast or pending_prelude_target:
            self._handle_target_selection(events)
            return
        
        # If in defender selection mode, only allow selecting own figures as defender
        if self.defender_selection_mode:
            self._handle_defender_selection(events)
            return

        # If in conquer own-defender mode, original conquerer picks their OWN figure to defend
        if self.conquer_own_defender_mode:
            self._handle_conquer_own_defender_selection(events)
            return
        
        # Handle figure detail box events first (if open)
        if self.figure_detail_box:
            response = self.figure_detail_box.handle_events(events)
            if response:
                if response == 'close':
                    self.figure_detail_box = None
                    # Deselect the figure
                    for icon in self.figure_icons:
                        icon.clicked = False
                elif response == 'advance':
                    # Show confirmation dialogue before advancing
                    figure = self.figure_detail_box.figure
                    self._pending_advance_figure = figure
                    # Find the existing FieldFigureIcon (has correct bonus/enchantments)
                    advance_icon = None
                    for icon in self.figure_icons:
                        if hasattr(icon, 'figure') and icon.figure.id == figure.id:
                            advance_icon = icon
                            break
                    if not advance_icon:
                        # Fallback: create a new icon if not found
                        from game.components.figures.figure_icon import FieldFigureIcon
                        advance_icon = FieldFigureIcon(
                            self.window,
                            self.game,
                            figure,
                            is_visible=True,
                            x=0,
                            y=0,
                            all_player_figures=[figure],
                            resources_data={}
                        )
                    advance_icon.show_advance_overlay = False
                    conquer_parent = self._conquer_parent()
                    if conquer_parent:
                        conquer_parent.request_conquer_figure_confirmation(
                            'advance',
                            figure,
                            icon=advance_icon,
                            message=f"Advance {figure.name} toward battle?",
                            title="Advance Figure",
                        )
                    else:
                        self.make_dialogue_box(
                            message=f"Do you want to advance {figure.name} toward battle?",
                            actions=['yes', 'cancel'],
                            images=[advance_icon],
                            icon=None,
                            title="Advance Figure"
                        )
                    # Close detail box
                    self.figure_detail_box = None
                    for icon in self.figure_icons:
                        icon.clicked = False
                elif response == 'disabled_advance_ceasefire':
                    # Advance button clicked while disabled due to ceasefire
                    # Check if it's a Blitzkrieg-induced ceasefire
                    modifiers = self.game.battle_modifier if isinstance(self.game.battle_modifier, list) else []
                    has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)
                    if has_blitzkrieg:
                        blitz_icons = self._get_modifier_icon_images('Blitzkrieg')
                        self.make_dialogue_box(
                            message="Blitzkrieg ceasefire is active.\n\nNo one can advance until ceasefire ends.",
                            actions=['ok'],
                            images=blitz_icons if blitz_icons else None,
                            icon="error" if not blitz_icons else None,
                            title="Blitzkrieg Ceasefire"
                        )
                    else:
                        self.make_dialogue_box(
                            message="You cannot advance figures during ceasefire.\n\nWait for the ceasefire to end.",
                            actions=['ok'],
                            icon="ceasefire_passive",
                            title="Ceasefire Active"
                        )
                elif response == 'disabled_advance_cannot_attack':
                    # Advance button clicked while disabled due to cannot_attack
                    self.make_dialogue_box(
                        message="This figure cannot attack and therefore cannot advance toward battle.",
                        actions=['ok'],
                        icon="error",
                        title="Cannot Attack"
                    )
                elif response == 'disabled_advance_cannot_be_blocked':
                    # Advance button clicked while disabled because opponent's advancing figure has cannot_be_blocked
                    self.make_dialogue_box(
                        message="The opponent's advancing figure cannot be blocked.\n\nYou cannot counter-advance against it.",
                        actions=['ok'],
                        icon="error",
                        title="Cannot Be Blocked"
                    )
                elif response == 'disabled_advance_blitzkrieg':
                    # Advance button clicked while disabled due to Blitzkrieg modifier
                    blitz_icons = self._get_modifier_icon_images('Blitzkrieg')
                    self.make_dialogue_box(
                        message="Blitzkrieg is active!\n\nThe defending player cannot counter-advance.",
                        actions=['ok'],
                        images=blitz_icons if blitz_icons else None,
                        icon="error" if not blitz_icons else None,
                        title="Blitzkrieg"
                    )
                elif response == 'disabled_advance_peasant_war':
                    # Advance button clicked while disabled due to Peasant War on non-village figure
                    pw_icons = self._get_modifier_icon_images('Peasant War')
                    self.make_dialogue_box(
                        message="Peasant War is active!\n\nOnly village figures can advance during Peasant War.",
                        actions=['ok'],
                        images=pw_icons if pw_icons else None,
                        icon="error" if not pw_icons else None,
                        title="Peasant War"
                    )
                elif response == 'disabled_advance_civil_war':
                    # Advance button clicked while disabled due to Civil War on non-village figure
                    cw_icons = self._get_modifier_icon_images('Civil War')
                    self.make_dialogue_box(
                        message="Civil War is active!\n\nOnly village figures can advance during Civil War.",
                        actions=['ok'],
                        images=cw_icons if cw_icons else None,
                        icon="error" if not cw_icons else None,
                        title="Civil War"
                    )
                elif response in ('disabled_upgrade_forced_advance', 'disabled_pick up_forced_advance'):
                    # Upgrade or Pick up clicked during forced advance
                    self.make_dialogue_box(
                        message="Last turn!\n\nYou must advance a figure toward battle. You cannot pick up or upgrade figures right now.",
                        actions=['ok'],
                        icon="error",
                        title="Battle Time"
                    )
                elif response == 'disabled_advance_civil_war_wrong_color':
                    # Advance clicked on wrong-color figure during Civil War second pick
                    required_color = getattr(self.game, 'civil_war_required_color', '')
                    color_name = 'red' if required_color == 'offensive' else 'black'
                    cw_icons = self._get_modifier_icon_images('Civil War')
                    self.make_dialogue_box(
                        message=f"Civil War requires a second village figure of the same color ({color_name}).",
                        actions=['ok'],
                        images=cw_icons if cw_icons else None,
                        icon="error" if not cw_icons else None,
                        title="Wrong Color"
                    )
                elif response == 'disabled_advance_civil_war_already_selected':
                    # Advance clicked on already-selected figure during Civil War
                    cw_icons = self._get_modifier_icon_images('Civil War')
                    self.make_dialogue_box(
                        message="This figure is already selected for battle. Choose a different figure.",
                        actions=['ok'],
                        images=cw_icons if cw_icons else None,
                        icon="error" if not cw_icons else None,
                        title="Already Selected"
                    )
                elif response == 'disabled_advance_resource_deficit':
                    # Advance clicked on a figure with resource deficit
                    self.make_dialogue_box(
                        message="This figure has a resource deficit and cannot advance toward battle.\n\nEnsure your figures' resource requirements are met before advancing.",
                        actions=['ok'],
                        icon="error",
                        title="Resource Deficit"
                    )
                elif response and response.startswith('disabled_') and response.endswith('_battle_active'):
                    # Any action disabled because a battle is in progress
                    self.make_dialogue_box(
                        message="You cannot perform this action while a battle is in progress.",
                        actions=['ok'],
                        icon="error",
                        title="Action Blocked"
                    )
                elif response and response.startswith('disabled_') and response.endswith('_resting'):
                    # Any action disabled because the figure is resting after battle
                    self.make_dialogue_box(
                        message="This figure is resting after battle and cannot act this round.\n\nIt will be available again next round.",
                        actions=['ok'],
                        icon="error",
                        title="Figure Resting"
                    )
                elif response == 'upgrade':
                    # Handle upgrade action - show confirmation dialogue with upgrade card image
                    upgrade_card = self.figure_detail_box.figure.upgrade_card
                    if upgrade_card:
                        self.figure_pending_upgrade = self.figure_detail_box.figure
                        # Create card image for display in dialogue
                        from game.components.cards.card_img import CardImg
                        card_img = CardImg(self.window, upgrade_card.suit, upgrade_card.rank)
                        self.make_dialogue_box(
                            f"Are you sure you want to upgrade {self.figure_pending_upgrade.name} to {self.figure_pending_upgrade.upgrade_family_name}? This will cost you:",
                            actions=['yes', 'cancel'],
                            images=[card_img],
                            title="Upgrade Figure"
                        )
                elif response == 'pick up':
                    # Handle pick up action - show confirmation dialogue
                    self.figure_pending_pickup = self.figure_detail_box.figure
                    self.make_dialogue_box(
                        f"Are you sure you want to pick up {self.figure_pending_pickup.name}? This will remove the figure from the field and return it to your hand.",
                        actions=['yes', 'cancel'],
                        title="Pick Up Figure"
                    )
            # If response is 'close', we already handled it above
            # For other actions, keep the box open unless user clicks close/outside
            return  # Don't process other events when detail box is open
        
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # Only allow one figure to be selected at a time
                # Check in reverse order (topmost figure gets priority)
                clicked_icon = None
                for icon in reversed(self.figure_icons):
                    if icon.hovered:
                        clicked_icon = icon
                        break
                
                if clicked_icon:
                    # Normal figure selection behavior
                    # Deselect all other icons
                    for icon in self.figure_icons:
                        if icon != clicked_icon:
                            icon.clicked = False
                    # Toggle the clicked icon
                    was_clicked = clicked_icon.clicked
                    clicked_icon.clicked = not clicked_icon.clicked
                    
                    # Force immediate visual feedback by redrawing the screen
                    # This ensures the icon state change is visible before the detail box opens
                    self._force_immediate_redraw()
                    
                    # Open detail box if figure was just selected and is visible
                    if clicked_icon.clicked and not was_clicked and clicked_icon.is_visible:
                        # During Civil War second-pick, skip detail box and go straight
                        # to advance confirmation (no pickup/upgrade allowed)
                        cw_second_pick = (getattr(self.game, 'civil_war_awaiting_second', False) or
                                          getattr(self.game, 'civil_war_defender_second', False))
                        if cw_second_pick:
                            figure = clicked_icon.figure
                            cw_icons = self._get_modifier_icon_images('Civil War')

                            if (getattr(self.game, 'civil_war_awaiting_second', False)
                                    and not self._is_civil_war_second_attacker_selectable(figure, clicked_icon)):
                                self.make_dialogue_box(
                                    message="Civil War requires another eligible village figure of the same color.",
                                    actions=['ok'],
                                    images=cw_icons if cw_icons else None,
                                    icon="error" if not cw_icons else None,
                                    title="Invalid Selection"
                                )
                                clicked_icon.clicked = False
                                continue
                            
                            # Validate: must be a village figure
                            figure_field = self._figure_field(figure)
                            if figure_field != 'village':
                                self.make_dialogue_box(
                                    message="Civil War requires village figures only.",
                                    actions=['ok'],
                                    images=cw_icons if cw_icons else None,
                                    icon="error" if not cw_icons else None,
                                    title="Invalid Selection"
                                )
                                clicked_icon.clicked = False
                            # Validate: must match required color (only reject on mismatch)
                            elif (getattr(self.game, 'civil_war_required_color', None) and
                                    self._figure_color(figure) != self.game.civil_war_required_color):
                                color_name = 'red' if self.game.civil_war_required_color == 'offensive' else 'black'
                                self.make_dialogue_box(
                                    message=f"Civil War requires a second village figure of the same color ({color_name}).",
                                    actions=['ok'],
                                    images=cw_icons if cw_icons else None,
                                    icon="error" if not cw_icons else None,
                                    title="Wrong Color"
                                )
                                clicked_icon.clicked = False
                            # Validate: not already selected as first figure
                            elif (figure.id == self.game.advancing_figure_id or
                                  figure.id == self.game.defending_figure_id):
                                self.make_dialogue_box(
                                    message="This figure is already selected for battle. Choose a different figure.",
                                    actions=['ok'],
                                    images=cw_icons if cw_icons else None,
                                    icon="error" if not cw_icons else None,
                                    title="Already Selected"
                                )
                                clicked_icon.clicked = False
                            # Validate: no resource deficit
                            elif getattr(clicked_icon, 'has_deficit', False):
                                self.make_dialogue_box(
                                    message="This figure has a resource deficit and cannot advance toward battle.",
                                    actions=['ok'],
                                    images=cw_icons if cw_icons else None,
                                    icon="error" if not cw_icons else None,
                                    title="Resource Deficit"
                                )
                                clicked_icon.clicked = False
                            else:
                                # Valid selection — show confirmation
                                self._pending_advance_figure = figure
                                advance_icon = clicked_icon
                                advance_icon.show_advance_overlay = False
                                conquer_parent = self._conquer_parent()
                                if conquer_parent:
                                    conquer_parent.request_conquer_figure_confirmation(
                                        'advance',
                                        figure,
                                        icon=advance_icon,
                                        message=f"Select {figure.name} as your second Civil War figure?",
                                        title="Civil War - Second Figure",
                                    )
                                else:
                                    self.make_dialogue_box(
                                        message=f"Select {figure.name} as your second Civil War figure?",
                                        actions=['yes', 'cancel'],
                                        images=[advance_icon] + (cw_icons if cw_icons else []),
                                        icon=None,
                                        title="Civil War - Second Figure"
                                    )
                        else:
                            conquer_parent = self._conquer_parent()

                            # Forced advance in conquer mode: clicking an eligible
                            # figure directly queues confirmation — no detail box.
                            if (conquer_parent
                                    and getattr(self.game, 'pending_forced_advance', False)
                                    and not getattr(self.game, 'advancing_figure_id', None)
                                    and getattr(self.game, 'forced_advance_dialogue_shown', False)
                                    and self._icon_is_selectable_for_current_mode(clicked_icon)):
                                figure = clicked_icon.figure
                                self._pending_advance_figure = figure
                                clicked_icon.show_advance_overlay = False
                                conquer_parent.request_conquer_figure_confirmation(
                                    'advance',
                                    figure,
                                    icon=clicked_icon,
                                    message=f"Advance {figure.name} toward battle?",
                                    title="Advance Figure",
                                )
                                clicked_icon.clicked = False
                            else:
                                # Calculate resources once for efficiency
                                resources_data = self.game.calculate_resources(self.figure_manager.families)

                                self.figure_detail_box = FigureDetailBox(
                                    self.window,
                                    clicked_icon.figure,
                                    self.game,
                                    all_figures=self.figures,
                                    resources_data=resources_data,
                                    conquer_view_only=bool(conquer_parent),
                                )
                    # Close detail box if figure was deselected
                    elif not clicked_icon.clicked:
                        self.figure_detail_box = None


    def handle_figure_click(self, figure):
        """Handle actions when a figure is clicked."""
        logger.debug(f"Selected figure: {figure.name}")
        # Add additional functionality for interacting with the figure

    def _conquer_parent(self):
        parent = getattr(getattr(self, 'state', None), 'parent_screen', None)
        if (parent and getattr(self.game, 'mode', 'duel') == 'conquer'
                and hasattr(parent, 'request_conquer_figure_confirmation')):
            return parent
        return None

    def _is_tactics_hand_battle_field_view_only(self):
        game = self.game
        if not game or getattr(game, 'mode', 'duel') != 'conquer':
            return False
        if getattr(game, 'conquer_move_model', 'battle_move') != 'tactics_hand':
            return False
        if not getattr(game, 'battle_confirmed', False):
            return False
        return (
            getattr(game, 'battle_turn_player_id', None) is not None
            or bool(getattr(game, 'both_battle_moves_ready', False))
            or bool(getattr(game, 'last_battle_result', None))
        )

    def _tactics_hand_battle_figure_ids(self):
        game = self.game
        if not game:
            return set()
        ids = set()
        for attr in (
                'advancing_figure_id', 'advancing_figure_id_2',
                'defending_figure_id', 'defending_figure_id_2'):
            fig_id = getattr(game, attr, None)
            if fig_id is not None:
                ids.add(fig_id)
        return ids

    def _is_tactics_hand_battle_fighter(self, figure):
        return getattr(figure, 'id', None) in self._tactics_hand_battle_figure_ids()

    def _tactics_hand_active_support_figure_ids(self, *, opponent_only=False):
        if not self._is_tactics_hand_battle_field_view_only():
            return set()
        parent = self._conquer_parent()
        if parent is None:
            return set()
        cached_getter = getattr(parent, 'conquer_active_support_figure_ids', None)
        if callable(cached_getter):
            try:
                return set(cached_getter(opponent_only=opponent_only) or set())
            except Exception:
                return set()
        lane_figures = getattr(parent, '_conquer_lane_figures', None)
        support_entries = getattr(parent, '_conquer_lane_support_entries', None)
        if not callable(lane_figures) or not callable(support_entries):
            return set()
        try:
            player_figures, opponent_figures = lane_figures()
            sides = (False,) if opponent_only else (True, False)
            active_ids = set()
            for is_player in sides:
                for entry in support_entries(
                        player_figures,
                        opponent_figures,
                        is_player=is_player,
                ) or []:
                    figure = entry.get('figure') if isinstance(entry, dict) else None
                    fig_id = getattr(figure, 'id', None)
                    if fig_id is not None:
                        active_ids.add(fig_id)
            return active_ids
        except Exception:
            return set()

    def _tactics_hand_revealed_support_figure_ids(self):
        return self._tactics_hand_active_support_figure_ids(opponent_only=True)

    @staticmethod
    def _entry_get(entry, key, default=None):
        if isinstance(entry, dict):
            return entry.get(key, default)
        return getattr(entry, key, default)

    def _conquer_played_tactic_entries(self):
        game = self.game
        entries = []
        entries.extend(list(getattr(game, 'conquer_tactics', []) or []))
        parent = self._conquer_parent()
        getter = None
        if parent:
            getter = getattr(parent, '_current_conquer_tactics', None)
            if getter is None:
                getter = getattr(parent, '_current_conquer_battle_moves', None)
        if getter:
            try:
                entries.extend(list(getter() or []))
            except Exception:
                pass
        opponent_getter = getattr(parent, '_current_conquer_opponent_tactics', None) if parent else None
        if opponent_getter:
            try:
                entries.extend(list(opponent_getter() or []))
            except Exception:
                pass
        battle = getattr(parent, 'subscreens', {}).get('battle') if parent else None
        if battle is not None:
            entries.extend(list(getattr(battle, 'player_moves', []) or []))
            entries.extend(list(getattr(battle, 'opponent_moves', []) or []))
            entries.extend([m for m in (getattr(battle, 'opp_played', []) or []) if m])
        played = []
        for entry in entries:
            status = self._entry_get(entry, 'status')
            played_round = self._entry_get(entry, 'played_round')
            if status == 'played' or played_round is not None:
                played.append(entry)
        return played

    def _conquer_called_figure_ids(self):
        ids = set()
        for tactic in self._conquer_played_tactic_entries():
            fig_id = self._entry_get(tactic, 'call_figure_id')
            if fig_id is not None:
                ids.add(fig_id)
        return ids

    def _conquer_preview_tactic(self):
        parent = self._conquer_parent()
        rail = getattr(parent, '_tactics_rail', None) if parent else None
        preview = getattr(rail, 'preview_move', None)
        if not callable(preview):
            return None
        move = preview()
        if not isinstance(move, dict):
            return None
        if move.get('played_round') is not None:
            return None
        if move.get('status', 'available') != 'available':
            return None
        return move

    def _conquer_preview_called_figure_ids(self):
        move = self._conquer_preview_tactic()
        fig_id = self._entry_get(move, 'call_figure_id') if move else None
        return {fig_id} if fig_id is not None else set()

    @staticmethod
    def _figure_active_skill_keys(figure):
        getter = getattr(figure, 'get_active_skill_keys', None)
        if callable(getter):
            try:
                return set(getter() or [])
            except Exception:
                return set()
        return {
            key for key in (
                'buffs_allies', 'buffs_allies_defence', 'blocks_bonus',
                'distance_attack')
            if getattr(figure, key, False)
        }

    def _tactics_hand_support_visibility_key(self):
        game = self.game
        if not game or getattr(game, 'mode', 'duel') != 'conquer':
            return ()
        parent = self._conquer_parent()
        return (
            getattr(game, 'game_id', None),
            getattr(game, 'player_id', None),
            getattr(game, '_figures_data_version', 0),
            getattr(game, 'battle_turn_player_id', None),
            getattr(game, 'battle_round', None),
            bool(getattr(game, 'last_battle_result', None)),
            bool(getattr(game, 'both_battle_moves_ready', False)),
            getattr(game, 'advancing_player_id', None),
            getattr(game, 'advancing_figure_id', None),
            getattr(game, 'advancing_figure_id_2', None),
            getattr(game, 'defending_figure_id', None),
            getattr(game, 'defending_figure_id_2', None),
            getattr(game, 'land_suit_bonus_suit', None),
            getattr(game, 'land_suit_bonus_value', None),
            getattr(parent, '_conquer_tactic_cache_key', None),
            getattr(parent, '_conquer_opponent_tactic_cache_key', None),
            bool(getattr(self, 'cached_all_seeing_eye_status', False)),
        )

    def _tactics_hand_figure_visible(self, figure, category, support_ids):
        figure_is_ghost = self._is_conquer_visual_ghost_figure(figure)
        figure_is_snapshot = self._is_conquer_timeline_snapshot_figure(figure)
        force_visible_snapshot = (
            figure_is_snapshot
            and bool(getattr(figure, '_conquer_force_visible', False))
        )
        figure_id = getattr(figure, 'id', None)
        support_id_keys = {str(fig_id) for fig_id in (support_ids or set())}
        is_revealed_support = (
            figure_id is not None and str(figure_id) in support_id_keys
        )
        return (figure_is_ghost or force_visible_snapshot or category == 'self' or
                getattr(figure, 'name', None) in ['Himalaya Maharaja', 'Djungle Maharaja'] or
                (category == 'opponent' and self.cached_all_seeing_eye_status) or
                (category == 'opponent' and is_revealed_support))

    def _sync_tactics_hand_support_visibility(self, *, force=False):
        if not self._uses_unified_conquer_layout():
            self._last_tactics_hand_support_visibility_key = ()
            return
        key = self._tactics_hand_support_visibility_key()
        if not force and key == self._last_tactics_hand_support_visibility_key:
            return
        self._last_tactics_hand_support_visibility_key = key
        support_ids = self._tactics_hand_revealed_support_figure_ids()
        player_id = getattr(self.game, 'player_id', None) if self.game else None
        for icon in getattr(self, 'figure_icons', []) or []:
            figure = getattr(icon, 'figure', None)
            if figure is None:
                continue
            category = 'self' if getattr(figure, 'player_id', None) == player_id else 'opponent'
            icon.is_visible = self._tactics_hand_figure_visible(
                figure, category, support_ids)

    def _conquer_battle_context_kind(self, figure):
        if not self._is_tactics_hand_battle_field_view_only() or figure is None:
            return None
        if self._is_tactics_hand_battle_fighter(figure):
            return None
        if getattr(figure, 'id', None) in self._conquer_preview_called_figure_ids():
            return 'preview'
        # Persistent ring around already-called figures was retired —
        # the support lane now lists called figures as their own entries
        # and the field icon dim/grey states already convey involvement.
        return None

    def _draw_tactics_hand_battle_context_overlays(self, drawn_icons):
        if not self._is_tactics_hand_battle_field_view_only():
            return
        # Side markers (round 12) replace the previous rounded-square halos
        # so the highlight no longer overlaps the figure's info chip.
        # Color-coded: gold = selected/pending, cyan = hover, green/red
        # = friendly/enemy support, blue = called.
        game = self.game
        active_support_ids = self._tactics_hand_active_support_figure_ids()
        for icon, ix, iy in drawn_icons:
            figure = getattr(icon, 'figure', None)
            if figure is None or self._is_tactics_hand_battle_fighter(figure):
                continue
            cx, cy = int(ix), int(iy)
            is_own = getattr(figure, 'player_id', None) == getattr(game, 'player_id', None)
            hover_source_ids = set(getattr(self, '_conquer_hover_source_figure_ids', set()) or [])
            is_hover_source = (
                getattr(figure, 'id', None) in hover_source_ids
                or (not hover_source_ids
                    and getattr(figure, 'id', None)
                    == getattr(self, '_conquer_hover_source_figure_id', None))
            )
            is_icon_hovered = bool(getattr(icon, 'hovered', False))
            context_kind = self._conquer_battle_context_kind(figure)
            if (not context_kind
                    and getattr(figure, 'id', None) in active_support_ids
                    and (is_hover_source or is_icon_hovered)):
                context_kind = 'support'
            if not context_kind:
                continue
            if is_hover_source or is_icon_hovered:
                color = (120, 220, 235, 245)
            elif context_kind == 'preview':
                phase = (pygame.time.get_ticks() % 900) / 900.0
                pulse = 1.0 - abs(0.5 - phase) * 2.0
                color = (120, 205, 220, int(150 + 70 * pulse))
            elif context_kind == 'called':
                color = (118, 192, 245, 220)
            else:
                color = (112, 220, 150, 220) if is_own else (232, 118, 110, 220)
            marker = self._conquer_icon_marker_geometry(
                icon, (cx, cy), is_own=is_own)
            self._draw_conquer_marker(marker, color)

    def _open_tactics_hand_battle_detail(self, clicked_icon):
        resources_data = {}
        if hasattr(self.game, 'calculate_resources'):
            families = getattr(getattr(self, 'figure_manager', None), 'families', None)
            resources_data = self.game.calculate_resources(families)
        self.figure_detail_box = FigureDetailBox(
            self.window,
            clicked_icon.figure,
            self.game,
            all_figures=self.figures,
            resources_data=resources_data,
            conquer_view_only=True,
        )

    def _handle_tactics_hand_battle_inspection(self, events):
        if self.figure_detail_box:
            response = self.figure_detail_box.handle_events(events)
            if response == 'close':
                self.figure_detail_box = None
                for icon in self.figure_icons:
                    icon.clicked = False
            return

        for event in events:
            if event.type != MOUSEBUTTONDOWN:
                continue
            clicked_icon = None
            for icon in reversed(self.figure_icons):
                if icon.hovered:
                    clicked_icon = icon
                    break

            if not clicked_icon:
                continue

            for icon in self.figure_icons:
                if icon != clicked_icon:
                    icon.clicked = False
            was_clicked = clicked_icon.clicked
            clicked_icon.clicked = not clicked_icon.clicked

            if hasattr(self, '_force_immediate_redraw'):
                self._force_immediate_redraw()

            if clicked_icon.clicked and not was_clicked and clicked_icon.is_visible:
                self._open_tactics_hand_battle_detail(clicked_icon)
            elif not clicked_icon.clicked:
                self.figure_detail_box = None
            return

    def cancel_conquer_panel_confirmation(self):
        """Cancel a command-panel figure confirmation."""
        self.figure_pending_defender_selection = None
        self.figure_pending_own_defender_selection = None
        self._pending_advance_figure = None
        for icon in self.figure_icons:
            icon.show_advance_overlay = True
        parent = self._conquer_parent()
        if parent and hasattr(parent, 'clear_conquer_figure_confirmation'):
            parent.clear_conquer_figure_confirmation()

    def _confirm_conquer_panel_pending(self):
        """Run the existing yes-confirmation path without opening a modal."""
        if getattr(self.game, 'game_over', False) or self.game.action_in_progress:
            return False
        self.dialogue_box = _ImmediateDialogueResponse('yes')
        self.handle_events([])
        parent = self._conquer_parent()
        if parent and hasattr(parent, 'clear_conquer_figure_confirmation'):
            parent.clear_conquer_figure_confirmation()
        return True

    def confirm_pending_advance(self):
        return bool(getattr(self, '_pending_advance_figure', None)
                    and self._confirm_conquer_panel_pending())

    def confirm_pending_defender_selection(self):
        return bool(self.figure_pending_defender_selection
                    and self._confirm_conquer_panel_pending())

    def confirm_pending_own_defender_selection(self):
        return bool(self.figure_pending_own_defender_selection
                    and self._confirm_conquer_panel_pending())
    
    def _handle_target_selection(self, events):
        """Handle events when in target selection mode."""
        pending_spell_cast = getattr(self.state, 'pending_spell_cast', None)
        pending_prelude_target = getattr(self.state, 'pending_conquer_prelude_target', None)
        if not pending_spell_cast and not pending_prelude_target:
            return

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # Check which figure was clicked
                clicked_icon = None
                for icon in reversed(self.figure_icons):
                    if icon.hovered:
                        clicked_icon = icon
                        break
                
                if clicked_icon:
                    # Check if target figure has checkmate (immune to all spells)
                    target_figure = clicked_icon.figure
                    
                    if hasattr(target_figure, 'checkmate') and target_figure.checkmate:
                        self.make_dialogue_box(
                            message=f"{target_figure.name} is immune to spells!",
                            actions=[],
                            icon="error",
                            title="Immune to Spells",
                            auto_close_delay=2000
                        )
                        return

                    if pending_spell_cast:
                        # Apply cast-screen spell to the selected figure
                        self._apply_spell_to_target(target_figure)
                        return

                    # Conquer startup prelude targeting
                    target_scope = pending_prelude_target.get('target_scope')
                    if target_scope == 'own' and target_figure.player_id != self.game.player_id:
                        self.make_dialogue_box(
                            message="Select one of your own figures for this prelude spell.",
                            actions=[],
                            icon="error",
                            title="Invalid Target",
                            auto_close_delay=2000
                        )
                        return
                    if target_scope == 'opponent' and target_figure.player_id == self.game.player_id:
                        self.make_dialogue_box(
                            message="Select one of your opponent's figures for this prelude spell.",
                            actions=[],
                            icon="error",
                            title="Invalid Target",
                            auto_close_delay=2000
                        )
                        return

                    valid_target_ids = set(pending_prelude_target.get('valid_target_ids', []))
                    if valid_target_ids and target_figure.id not in valid_target_ids:
                        self.make_dialogue_box(
                            message="That figure is not a valid target for this prelude spell.",
                            actions=[],
                            icon="error",
                            title="Invalid Target",
                            auto_close_delay=2000
                        )
                        return
                    
                    self._apply_conquer_prelude_to_target(target_figure)
                    return
            
            elif event.type == KEYDOWN:
                # Allow ESC to cancel target selection
                if event.key == K_ESCAPE:
                    if pending_spell_cast:
                        self.state.pending_spell_cast = None
                        self.make_dialogue_box(
                            message="Spell casting cancelled.",
                            actions=['ok'],
                            icon="error",
                            title="Cancelled"
                        )
                    else:
                        self.make_dialogue_box(
                            message="Prelude target selection is required before you can continue.",
                            actions=[],
                            icon="info",
                            title="Target Required",
                            auto_close_delay=2000
                        )
                    return
    
    def _handle_defender_selection(self, events):
        """Handle events when in defender selection mode — advancing player selects opponent's defender."""
        # Determine active battle modifier restrictions
        modifiers = self.game.battle_modifier if isinstance(self.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        has_peasant_war = 'Peasant War' in modifier_types
        has_blitzkrieg = 'Blitzkrieg' in modifier_types
        has_civil_war = 'Civil War' in modifier_types
        village_only = has_peasant_war or has_civil_war
        
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # Check which figure was clicked
                clicked_icon = None
                for icon in reversed(self.figure_icons):
                    if icon.hovered:
                        clicked_icon = icon
                        break
                
                if clicked_icon:
                    logger.debug(f"[DEFENDER_CLICK] Clicked: {clicked_icon.figure.name} (id={clicked_icon.figure.id}), defender_selectable={getattr(clicked_icon, 'defender_selectable', 'N/A')}, is_visible={clicked_icon.is_visible}")
                    # Show error for non-selectable figures (works for both visible and hidden)
                    if hasattr(clicked_icon, 'defender_selectable') and not clicked_icon.defender_selectable:
                        reason = "This figure cannot be selected as a defender."
                        title = "Cannot Select"
                        images = []
                        target_fig = clicked_icon.figure
                        if target_fig.player_id == self.game.player_id:
                            reason = "You must select one of your opponent's figures."
                        elif village_only and hasattr(target_fig, 'family') and target_fig.family.field != 'village':
                            active_mod = 'Peasant War' if has_peasant_war else 'Civil War'
                            reason = f"{active_mod} is active — only village figures can be selected."
                            title = active_mod
                            images = self._get_modifier_icon_images(active_mod)
                        elif hasattr(target_fig, 'cannot_defend') and target_fig.cannot_defend:
                            reason = f"{target_fig.name} cannot defend and cannot be selected for battle."
                        elif hasattr(target_fig, 'cannot_be_targeted') and target_fig.cannot_be_targeted:
                            reason = f"{target_fig.name} cannot be targeted by the opponent."
                        elif hasattr(target_fig, 'checkmate') and target_fig.checkmate:
                            reason = f"{target_fig.name} has Checkmate and cannot be selected as a defender."
                        elif not clicked_icon.is_visible:
                            reason = "This hidden figure cannot be selected as a defender."
                        elif hasattr(target_fig, 'must_be_attacked') and not target_fig.must_be_attacked:
                            reason = "You must select a figure with the 'Must Be Attacked' trait first."
                        self.make_dialogue_box(
                            message=reason,
                            actions=[],
                            images=images if images else None,
                            icon="error" if not images else None,
                            title=title,
                            auto_close_delay=2000
                        )
                        return
                    
                    target_figure = clicked_icon.figure
                    
                    # Must be an OPPONENT's figure (advancing player picks from opponent)
                    if target_figure.player_id == self.game.player_id:
                        self.make_dialogue_box(
                            message="You must select one of your opponent's figures as the defender.",
                            actions=[],
                            icon="error",
                            title="Invalid Selection",
                            auto_close_delay=2000
                        )
                        return
                    
                    # Village-only restriction (Peasant War / Civil War)
                    if village_only and hasattr(target_figure, 'family') and target_figure.family.field != 'village':
                        active_mod = 'Peasant War' if has_peasant_war else 'Civil War'
                        mod_icons = self._get_modifier_icon_images(active_mod)
                        self.make_dialogue_box(
                            message=f"{active_mod} is active — only village figures can be selected for battle.",
                            actions=[],
                            images=mod_icons if mod_icons else None,
                            icon="error" if not mod_icons else None,
                            title=active_mod,
                            auto_close_delay=2000
                        )
                        return
                    
                    # Check cannot_defend constraint (figure cannot be advanced against)
                    if hasattr(target_figure, 'cannot_defend') and target_figure.cannot_defend:
                        self.make_dialogue_box(
                            message=f"{target_figure.name} cannot defend and cannot be selected for battle.",
                            actions=[],
                            icon="error",
                            title="Cannot Defend",
                            auto_close_delay=2000
                        )
                        return
                    
                    # Check cannot_be_targeted constraint (opponent cannot choose this figure)
                    if hasattr(target_figure, 'cannot_be_targeted') and target_figure.cannot_be_targeted:
                        self.make_dialogue_box(
                            message=f"{target_figure.name} cannot be targeted by the opponent.",
                            actions=[],
                            icon="error",
                            title="Cannot Be Targeted",
                            auto_close_delay=2000
                        )
                        return
                    
                    # Checkmate defenders are protected unless no other legal
                    # defender exists; then they are the only valid target.
                    if hasattr(target_figure, 'checkmate') and target_figure.checkmate:
                        has_non_checkmate = any(
                            fig.player_id != self.game.player_id
                            and not (hasattr(fig, 'cannot_defend') and fig.cannot_defend)
                            and not (hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted)
                            and not (hasattr(fig, 'checkmate') and fig.checkmate)
                            and (not village_only or (
                                hasattr(fig, 'family') and fig.family.field == 'village'))
                            for fig in self.figures
                        )
                        if has_non_checkmate:
                            self.make_dialogue_box(
                                message=f"{target_figure.name} has Checkmate and cannot be selected as a defender.",
                                actions=[],
                                icon="error",
                                title="Checkmate",
                                auto_close_delay=2000
                            )
                            return
                    
                    # Check must_be_attacked constraint on opponent's eligible figures
                    # Exclude figures with cannot_defend, cannot_be_targeted, or checkmate
                    opponent_figures = [
                        fig for fig in self.figures 
                        if fig.player_id != self.game.player_id
                        and not (hasattr(fig, 'cannot_defend') and fig.cannot_defend)
                        and not (hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted)
                        and not (hasattr(fig, 'checkmate') and fig.checkmate)
                    ]
                    
                    # Village-only filter for must_be_attacked check too
                    if village_only:
                        opponent_figures = [
                            fig for fig in opponent_figures
                            if hasattr(fig, 'family') and fig.family.field == 'village'
                        ]
                    
                    # Check if advancing figure has cannot_be_blocked — if so, skip must_be_attacked
                    advancing_figure = None
                    if self.game.advancing_figure_id:
                        for fig in self.figures:
                            if fig.id == self.game.advancing_figure_id:
                                advancing_figure = fig
                                break
                    
                    advancing_cannot_be_blocked = (
                        advancing_figure and 
                        hasattr(advancing_figure, 'cannot_be_blocked') and 
                        advancing_figure.cannot_be_blocked
                    )
                    
                    # Blitzkrieg also skips must_be_attacked
                    skip_must_be_attacked = advancing_cannot_be_blocked or has_blitzkrieg
                    
                    if not skip_must_be_attacked:
                        must_be_attacked_figures = [
                            fig for fig in opponent_figures
                            if hasattr(fig, 'must_be_attacked') and fig.must_be_attacked
                        ]
                        must_be_attacked_ids = {fig.id for fig in must_be_attacked_figures}
                        
                        if must_be_attacked_figures and target_figure.id not in must_be_attacked_ids:
                            figure_names = ', '.join(f.name for f in must_be_attacked_figures)
                            self.make_dialogue_box(
                                message=f"You must select a figure with the 'Must Be Attacked' trait.\n\nEligible figures: {figure_names}",
                                actions=['ok'],
                                icon="error",
                                title="Invalid Selection"
                            )
                            return
                    
                    # Valid selection — show confirmation dialogue with figure icon
                    self.figure_pending_defender_selection = target_figure
                    if clicked_icon.is_visible:
                        confirm_msg = f"Are you sure you want to select {target_figure.name} as the defender for battle?"
                    else:
                        confirm_msg = "Are you sure you want to select this hidden figure as the defender for battle?"
                    conquer_parent = self._conquer_parent()
                    if conquer_parent:
                        conquer_parent.request_conquer_figure_confirmation(
                            'opponent_defender',
                            target_figure,
                            icon=clicked_icon,
                            message=confirm_msg,
                            title="Confirm Defender",
                        )
                    else:
                        self.make_dialogue_box(
                            message=confirm_msg,
                            actions=['yes', 'no'],
                            images=[clicked_icon],
                            title="Confirm Defender"
                        )
                    return

    def _handle_conquer_own_defender_selection(self, events):
        """Handle Invader Swap conquer own-defender mode: conquerer selects their OWN figure."""
        modifiers = self.game.battle_modifier if isinstance(self.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        has_peasant_war = 'Peasant War' in modifier_types
        has_civil_war = 'Civil War' in modifier_types
        village_only = has_peasant_war or has_civil_war

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                clicked_icon = None
                for icon in reversed(self.figure_icons):
                    if icon.hovered:
                        clicked_icon = icon
                        break

                if not clicked_icon:
                    continue

                target_figure = clicked_icon.figure

                # Must select own figure
                if target_figure.player_id != self.game.player_id:
                    self.make_dialogue_box(
                        message="You must select one of your OWN figures to defend against the invader.",
                        actions=[],
                        icon="error",
                        title="Invalid Selection",
                        auto_close_delay=2000,
                    )
                    continue

                # Village-only restriction
                if village_only and self._figure_field(target_figure) != 'village':
                    active_mod = 'Peasant War' if has_peasant_war else 'Civil War'
                    mod_icons = self._get_modifier_icon_images(active_mod)
                    self.make_dialogue_box(
                        message=f"{active_mod} is active — only village figures can defend.",
                        actions=[],
                        images=mod_icons if mod_icons else None,
                        icon="error" if not mod_icons else None,
                        title=active_mod,
                        auto_close_delay=2000,
                    )
                    continue

                if (getattr(self.game, 'civil_war_defender_second', False)
                        and has_civil_war):
                    required_color = getattr(self.game, 'civil_war_required_color', None)
                    figure_color = self._figure_color(target_figure)
                    if required_color and figure_color != required_color:
                        color_name = 'red' if required_color == 'offensive' else 'black'
                        mod_icons = self._get_modifier_icon_images('Civil War')
                        self.make_dialogue_box(
                            message=f"Civil War requires a second village figure of the same color ({color_name}).",
                            actions=[],
                            images=mod_icons if mod_icons else None,
                            icon="error" if not mod_icons else None,
                            title="Wrong Color",
                            auto_close_delay=2000,
                        )
                        continue
                    if target_figure.id == self.game.defending_figure_id:
                        mod_icons = self._get_modifier_icon_images('Civil War')
                        self.make_dialogue_box(
                            message="This figure is already selected for battle. Choose a different figure.",
                            actions=[],
                            images=mod_icons if mod_icons else None,
                            icon="error" if not mod_icons else None,
                            title="Already Selected",
                            auto_close_delay=2000,
                        )
                        continue

                if getattr(clicked_icon, 'has_deficit', False):
                    self.make_dialogue_box(
                        message=f"{target_figure.name} has a resource deficit and cannot defend.",
                        actions=[],
                        icon="error",
                        title="Resource Deficit",
                        auto_close_delay=2000,
                    )
                    continue

                if hasattr(target_figure, 'cannot_defend') and target_figure.cannot_defend:
                    self.make_dialogue_box(
                        message=f"{target_figure.name} cannot defend.",
                        actions=[],
                        icon="error",
                        title="Cannot Defend",
                        auto_close_delay=2000,
                    )
                    continue

                # Valid own figure - confirm
                self.figure_pending_own_defender_selection = target_figure
                confirm_msg = f"Select {target_figure.name} as your defending figure?"
                conquer_parent = self._conquer_parent()
                if conquer_parent:
                    conquer_parent.request_conquer_figure_confirmation(
                        'own_defender',
                        target_figure,
                        icon=clicked_icon,
                        message=confirm_msg,
                        title="Confirm Own Defender",
                    )
                else:
                    self.make_dialogue_box(
                        message=confirm_msg,
                        actions=['yes', 'no'],
                        images=[clicked_icon],
                        title="Confirm Own Defender",
                    )
                return

    def _apply_spell_to_target(self, target_figure):
        """
        Apply a pending spell cast to the selected target figure.
        
        :param target_figure: The figure selected as the target
        """
        if getattr(self.game, 'game_over', False):
            return
        if self.game.action_in_progress:
            return
        from utils import spell_service
        
        pending = self.state.pending_spell_cast
        selected_spell = pending['spell']
        real_cards = pending['real_cards']
        
        # Determine if target figure should be visible in success dialogue
        # Explosion always reveals the destroyed figure
        # Other spells (Poison, Health Boost) respect the figure's actual visibility
        is_opponent_figure = target_figure.player_id != self.game.player_id
        player_has_all_seeing_eye = self.game.has_active_all_seeing_eye()
        is_maharaja = target_figure.name in ['Himalaya Maharaja', 'Djungle Maharaja']
        
        if 'Explosion' in selected_spell.name:
            # Explosion reveals the destroyed figure
            show_figure_visible = True
        elif is_opponent_figure:
            # For opponent figures, check if they're naturally visible
            show_figure_visible = is_maharaja or player_has_all_seeing_eye
        else:
            # Own figures are always visible
            show_figure_visible = True
        
        # Create figure icon for targeted spells to show in success dialogue
        # Always hide bonus and deficit to avoid revealing opponent's strategic state
        figure_icon = FieldFigureIcon(
            window=self.window,
            game=self.game,
            figure=target_figure,
            is_visible=show_figure_visible,
            all_player_figures=[],  # Empty list to prevent bonus calculation
            resources_data=None
        )
        # Explicitly set battle bonus and deficit to hide them
        figure_icon.battle_bonus_received = 0
        figure_icon.has_deficit = False
        
        # Prepare card data for server
        cards_data = [{
            'id': card.id,
            'rank': card.rank,
            'suit': card.suit,
            'value': card.value
        } for card in real_cards]
        
        # Call spell service to cast the spell
        self.game.lock_actions()
        try:
            result = spell_service.cast_spell(
                player_id=self.game.player_id,
                game_id=self.game.game_id,
                spell_name=selected_spell.name,
                spell_type=selected_spell.family.type,
                spell_family_name=selected_spell.family.name,
                suit=selected_spell.suit,
                cards=cards_data,
                target_figure_id=target_figure.id,
                counterable=selected_spell.counterable,
                possible_during_ceasefire=selected_spell.possible_during_ceasefire
            )
        except Exception:
            self.game.unlock_actions()
            raise
        
        if result.get('success'):
            # For Explosion spells, don't apply enchantment locally since figure is destroyed
            # Just update from server to remove the figure
            if 'Explosion' not in selected_spell.name:
                # Apply enchantment locally for immediate visual feedback
                self._apply_enchantment_to_figure(target_figure, selected_spell)
            else:
                # For Explosion spells, remove destroyed figure from cache immediately
                if target_figure.id in self.icon_cache:
                    del self.icon_cache[target_figure.id]
            
            # Update game state from server response
            # (update_from_dict -> unlock_actions)
            if result.get('game'):
                self.game.update_from_dict(result['game'])
            
            # Update game state from server (refresh figures cache)
            try:
                self.game.cached_figures_data[self.game.player_id] = fetch_figures(self.game.player_id)
                if self.game.opponent_player:
                    opponent_id = self.game.opponent_player['id']
                    self.game.cached_figures_data[opponent_id] = fetch_figures(opponent_id)
                self.game._figures_data_version += 1
            except Exception:
                pass
            
            # Refresh figure icons to show updated enchantments (or removed figure for Explosion)
            self.load_figures()
            
            # Determine figure name to display in message
            # Only reveal name for Explosion or visible figures
            if 'Explosion' in selected_spell.name or show_figure_visible:
                figure_name_display = target_figure.name
            else:
                figure_name_display = "an opponent figure"
            
            # Show success message with figure icon
            if 'Explosion' in selected_spell.name:
                self.make_dialogue_box(
                    message=f"{selected_spell.name} destroyed {figure_name_display}!",
                    actions=['ok'],
                    icon="magic",
                    title="Figure Destroyed",
                    images=[figure_icon]
                )
                # Check if Explosion triggered checkmate game-over
                game_over_info = result.get('game_over')
                if game_over_info:
                    self.game.pending_game_over = game_over_info
            else:
                self.make_dialogue_box(
                    message=f"{selected_spell.name} cast on {figure_name_display}!",
                    actions=['ok'],
                    icon="magic",
                    title="Spell Cast",
                    images=[figure_icon]
                )
        else:
            self.game.unlock_actions()
            # Show error message
            error_msg = result.get('message', 'Unknown error')
            self.make_dialogue_box(
                message=f"Failed to cast spell: {error_msg}",
                actions=['got it!'],
                icon="error",
                title="Casting Failed"
            )
        
        # Clear pending spell cast
        self.state.pending_spell_cast = None

    def _apply_conquer_prelude_to_target(self, target_figure):
        """Resolve pending conquer prelude target selection."""
        if getattr(self.game, 'game_over', False):
            return
        if self.game.action_in_progress:
            return

        pending = getattr(self.state, 'pending_conquer_prelude_target', None)
        if not pending:
            return

        from utils.game_service import resolve_conquer_prelude_target

        spell_name = pending.get('spell_name', 'Prelude spell')
        spell_id = pending.get('spell_id')
        if spell_id is None:
            self.make_dialogue_box(
                message="Missing prelude spell context. Please wait for sync and try again.",
                actions=['ok'],
                icon="error",
                title="Prelude Failed"
            )
            return

        is_opponent_figure = target_figure.player_id != self.game.player_id
        player_has_all_seeing_eye = self.game.has_active_all_seeing_eye()
        is_maharaja = target_figure.name in ['Himalaya Maharaja', 'Djungle Maharaja']
        if 'Explosion' in spell_name:
            show_figure_visible = True
        elif is_opponent_figure:
            show_figure_visible = is_maharaja or player_has_all_seeing_eye
        else:
            show_figure_visible = True
        if 'Explosion' in spell_name or show_figure_visible:
            figure_name_display = target_figure.name
        else:
            figure_name_display = "an opponent figure"

        self.game.lock_actions()
        try:
            result = resolve_conquer_prelude_target(
                game_id=self.game.game_id,
                spell_id=spell_id,
                target_figure_id=target_figure.id,
            )
        except Exception:
            self.game.unlock_actions()
            raise

        if result.get('success'):
            if result.get('game'):
                self.game.update_from_dict(result['game'])

            try:
                self.game.cached_figures_data[self.game.player_id] = fetch_figures(self.game.player_id)
                if self.game.opponent_player:
                    opponent_id = self.game.opponent_player['id']
                    self.game.cached_figures_data[opponent_id] = fetch_figures(opponent_id)
                self.game._figures_data_version += 1
            except Exception:
                pass

            self.load_figures()
            self.state.pending_conquer_prelude_target = None
            self.game.pending_conquer_prelude_target = False

            spell_effect = result.get('spell_effect') or {}
            self._sync_resolved_conquer_prelude_snapshot(
                pending, target_figure, figure_name_display, spell_effect)
            effect_text = spell_effect.get('effect')
            success_msg = effect_text or f"{spell_name} was applied to {figure_name_display}."
            title = "Prelude Spell"
            if 'Explosion' in spell_name and 'destroyed' in success_msg.lower():
                title = "Figure Destroyed"
            # In conquer mode the timeline panel surfaces this beat;
            # only the duel mode falls back to a modal dialogue.
            in_conquer = (self.game and getattr(self.game, 'mode', 'duel') == 'conquer')
            if not in_conquer:
                self.make_dialogue_box(
                    message=success_msg,
                    actions=['ok'],
                    icon="magic",
                    title=title
                )

            game_over_info = spell_effect.get('game_over')
            if game_over_info:
                self.game.pending_game_over = game_over_info
            return

        if result.get('game'):
            self.game.update_from_dict(result['game'])
        else:
            self.game.unlock_actions()

        reason = result.get('reason')
        if reason == 'no_valid_target':
            self.state.pending_conquer_prelude_target = None
            self.game.pending_conquer_prelude_target = False
            self.make_dialogue_box(
                message=result.get('message', f"No valid target is available for {spell_name}."),
                actions=['ok'],
                icon="info",
                title="No Valid Target"
            )
            return

        error_msg = result.get('message', 'Unknown error')
        self.make_dialogue_box(
            message=f"Failed to resolve prelude spell: {error_msg}",
            actions=['ok'],
            icon="error",
            title="Prelude Failed"
        )

    def _sync_resolved_conquer_prelude_snapshot(self, pending, target_figure,
                                                figure_name_display,
                                                spell_effect):
        spells = getattr(self.game, 'conquer_own_prelude_spells', None)
        if not isinstance(spells, list) or not isinstance(pending, dict):
            return

        spell_id = pending.get('spell_id')
        spell_name = pending.get('spell_name', 'Prelude spell')
        effect_data = dict(spell_effect or {})
        effect_data['prelude_origin'] = True
        effect_data['prelude_status'] = 'executed'
        effect_data['target_figure_id'] = getattr(target_figure, 'id', None)
        effect_data['target_figure_name'] = figure_name_display

        resolved = dict(pending)
        resolved.update({
            'spell_name': spell_name,
            'target_figure_id': getattr(target_figure, 'id', None),
            'target_figure_name': figure_name_display,
            'target_figure': target_figure,
            'effect_data': effect_data,
        })

        for idx, existing in enumerate(spells):
            if not isinstance(existing, dict):
                continue
            if (spell_id is not None and existing.get('spell_id') == spell_id
                    or existing.get('spell_name') == spell_name
                    and existing.get('target_figure_id') in (None, getattr(target_figure, 'id', None))):
                spells[idx] = resolved
                return
        spells.append(resolved)
    
    def _apply_enchantment_to_figure(self, figure, spell):
        """
        Apply an enchantment effect to a figure locally.
        
        :param figure: The figure to enchant
        :param spell: The spell being cast
        """
        # Determine power modifier based on spell name
        power_modifier = 0
        if 'Poison' in spell.name:
            power_modifier = -6
        elif 'Boost' in spell.name or 'Health' in spell.name:
            power_modifier = 6
        
        # Get icon filename from spell family config
        # The icon_img in configs is a filename string (e.g., 'poisson_portion.png')
        icon_filename = 'default_spell_icon.png'  # Default fallback
        
        # Try to get the icon filename from the spell's family configuration
        if hasattr(spell, 'family') and spell.family:
            # Check if it's from the ability_spell_config
            if 'Poison' in spell.name:
                icon_filename = 'poisson_portion.png'
            elif 'Boost' in spell.name or 'Health' in spell.name:
                icon_filename = 'health_portion.png'
            elif 'Explosion' in spell.name:
                icon_filename = 'bomb.png'
            elif 'All Seeing Eye' in spell.name:
                icon_filename = 'eye.png'
            elif 'Infinite Hammer' in spell.name:
                icon_filename = 'infinite_hammer.png'
        
        # Apply enchantment to figure
        figure.add_enchantment(
            spell_name=spell.name,
            spell_icon=icon_filename,
            power_modifier=power_modifier
        )

    def _draw_opponent_hand_cards(self):
        """Draw opponent's hand cards rotated 90 degrees after the castle compartment."""
        opponent_main_cards, opponent_side_cards = self._get_opponent_hand_cards()
        all_opponent_cards = opponent_main_cards + opponent_side_cards
        
        # Track current opponent card IDs
        current_card_ids = {card.get('id') for card in all_opponent_cards if card.get('id')}
        
        # Only regenerate card surfaces if cards have changed
        if current_card_ids != self.last_opponent_card_ids:
            self._generate_opponent_card_cache(opponent_main_cards, opponent_side_cards)
            self.last_opponent_card_ids = current_card_ids
        
        # Get the opponent's castle compartment for positioning
        castle_comp = self.compartments['opponent']['castle']
        
        # Card dimensions (after rotation)
        card_display_width = int(settings.CARD_WIDTH * 0.30)
        rotated_card_height = card_display_width
        
        # Starting position
        start_x = castle_comp.right + settings.FIELD_ICON_PADDING_X
        start_y = castle_comp.top + int(0.028 * settings.SCREEN_HEIGHT)
        
        card_spacing = max(1, int(0.003 * settings.SCREEN_HEIGHT))
        group_spacing = int(0.015 * settings.SCREEN_HEIGHT)  # Extra gap between main/side
        
        main_count = self.opponent_card_cache_main_count
        
        # Draw cached card surfaces and track rects for hover detection
        self._opponent_card_rects = []
        current_y = start_y
        mouse_pos = pygame.mouse.get_pos()
        hovered_idx = -1
        
        for i, card_surface in enumerate(self.opponent_card_cache):
            # Add group separator between main and side cards
            if i == main_count and main_count > 0 and len(self.opponent_card_cache) > main_count:
                current_y += group_spacing
            
            card_rect = pygame.Rect(start_x, current_y,
                                    card_surface.get_width(), card_surface.get_height())
            self._opponent_card_rects.append(card_rect)
            
            if card_rect.collidepoint(mouse_pos):
                hovered_idx = i
            
            self.window.blit(card_surface, (start_x, current_y))
            current_y += rotated_card_height + card_spacing
        
        # Update hover state (actual drawing deferred to draw_opponent_card_hover)
        if hovered_idx != self._opponent_card_hovered_idx:
            self._opponent_card_hovered_idx = hovered_idx
            if hovered_idx >= 0:
                self._opponent_hover_surface = self._make_opponent_hover_card(hovered_idx)
            else:
                self._opponent_hover_surface = None

    def draw_opponent_card_hover(self):
        """Draw the enlarged hover card overlay. Called from game_screen after buttons."""
        hovered_idx = self._opponent_card_hovered_idx
        if not self._opponent_hover_surface or hovered_idx < 0:
            return
        if hovered_idx >= len(self._opponent_card_rects):
            return
        hr = self._opponent_card_rects[hovered_idx]
        hx = hr.right + int(0.006 * settings.SCREEN_WIDTH)
        hy = hr.centery - self._opponent_hover_surface.get_height() // 2
        if hx + self._opponent_hover_surface.get_width() > settings.SCREEN_WIDTH:
            hx = hr.left - self._opponent_hover_surface.get_width() - int(0.006 * settings.SCREEN_WIDTH)
        hy = max(0, min(hy, settings.SCREEN_HEIGHT - self._opponent_hover_surface.get_height()))
        self.window.blit(self._opponent_hover_surface, (hx, hy))

    def _generate_opponent_card_cache(self, opponent_main_cards, opponent_side_cards):
        """Generate and cache rotated card surfaces for opponent's hand."""
        self.opponent_card_cache = []
        self._opponent_card_data = []  # Store (suit, rank) for hover enlargement
        self._opponent_card_hovered_idx = -1
        self._opponent_hover_surface = None
        
        card_display_width = int(settings.CARD_WIDTH * 0.27)
        card_display_height = int(settings.CARD_HEIGHT * 0.27)
        
        # Generate main cards
        for card in opponent_main_cards:
            suit, rank = card.get('suit'), card.get('rank')
            card_img = CardImg(self.window, suit, rank, 
                              width=card_display_width, height=card_display_height)
            
            card_surface = pygame.Surface((card_display_width, card_display_height), pygame.SRCALPHA)
            card_img.front_img.convert_alpha()
            card_surface.blit(card_img.front_img, (0, 0))
            rotated_surface = pygame.transform.rotate(card_surface, -90)
            
            self.opponent_card_cache.append(rotated_surface)
            self._opponent_card_data.append((suit, rank))
        
        self.opponent_card_cache_main_count = len(opponent_main_cards)
        
        # Generate side cards
        for card in opponent_side_cards:
            suit, rank = card.get('suit'), card.get('rank')
            card_img = CardImg(self.window, suit, rank,
                              width=card_display_width, height=card_display_height)
            
            card_surface = pygame.Surface((card_display_width, card_display_height), pygame.SRCALPHA)
            card_img.front_img.convert_alpha()
            card_surface.blit(card_img.front_img, (0, 0))
            rotated_surface = pygame.transform.rotate(card_surface, -90)
            
            self.opponent_card_cache.append(rotated_surface)
            self._opponent_card_data.append((suit, rank))

    def _make_opponent_hover_card(self, idx):
        """Create an enlarged rotated card surface for the hovered opponent card."""
        if idx < 0 or idx >= len(self._opponent_card_data):
            return None
        suit, rank = self._opponent_card_data[idx]
        hover_w = int(settings.CARD_WIDTH * 0.55)
        hover_h = int(settings.CARD_HEIGHT * 0.55)
        card_img = CardImg(self.window, suit, rank, width=hover_w, height=hover_h)
        surf = pygame.Surface((hover_w, hover_h), pygame.SRCALPHA)
        surf.blit(card_img.front_img, (0, 0))
        return pygame.transform.rotate(surf, -90)

    def _draw_target_selection_prompt(self):
        """Draw a prominent prompt asking the player to select a target figure."""
        pending_spell_cast = getattr(self.state, 'pending_spell_cast', None)
        pending_prelude_target = getattr(self.state, 'pending_conquer_prelude_target', None)

        if pending_spell_cast:
            spell_name = pending_spell_cast['spell'].name if 'spell' in pending_spell_cast else 'Spell'
            prompt_text = f"SELECT A TARGET FOR {spell_name.upper()}"
            cancel_text = "Press ESC to cancel"
        elif pending_prelude_target:
            spell_name = pending_prelude_target.get('spell_name', 'Prelude Spell')
            prompt_text = f"SELECT A PRELUDE TARGET FOR {spell_name.upper()}"
            cancel_text = "Checkmate figures cannot be targeted"
        else:
            return
        
        prompt_surface = self.target_prompt_font.render(prompt_text, True, (255, 50, 50))  # Bright red
        
        # Create cancel instruction text
        cancel_font = settings.get_font(int(settings.FIELD_TITLE_FONT_SIZE * 0.9))
        cancel_surface = cancel_font.render(cancel_text, True, (255, 255, 150))  # Light yellow
        
        # Create background box for better visibility
        text_width = max(prompt_surface.get_width(), cancel_surface.get_width())
        line_gap = int(0.009 * settings.SCREEN_HEIGHT)
        text_height = prompt_surface.get_height() + cancel_surface.get_height() + line_gap
        padding = int(0.018 * settings.SCREEN_HEIGHT)
        border_w = max(2, int(0.004 * settings.SCREEN_HEIGHT))
        
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
        
        # Draw yellow border for emphasis
        pygame.draw.rect(self.window, (255, 255, 0), box_rect, border_w)
        
        # Draw main prompt text centered in box
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        # Draw cancel text below
        cancel_x = box_rect.centerx - cancel_surface.get_width() // 2
        cancel_y = text_y + prompt_surface.get_height() + line_gap
        self.window.blit(cancel_surface, (cancel_x, cancel_y))
        
        # Add pulsing effect to main prompt
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))
    
    def _draw_defender_selection_prompt(self):
        """Draw a prominent prompt asking the advancing player to select an opponent's defender."""
        # Create prompt text
        prompt_text = "SELECT OPPONENT'S DEFENDER"
        prompt_surface = self.target_prompt_font.render(prompt_text, True, (100, 200, 255))  # Blue
        
        # Create instruction text
        info_font = settings.get_font(int(settings.FIELD_TITLE_FONT_SIZE * 0.9))
        
        # Check for must_be_attacked constraint on opponent's eligible figures
        # Exclude figures with cannot_defend or cannot_be_targeted
        opponent_figures = [
            fig for fig in self.figures 
            if fig.player_id != self.game.player_id
            and not (hasattr(fig, 'cannot_defend') and fig.cannot_defend)
            and not (hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted)
        ]
        
        # Check if advancing figure has cannot_be_blocked — if so, skip must_be_attacked
        advancing_figure = None
        if self.game.advancing_figure_id:
            for fig in self.figures:
                if fig.id == self.game.advancing_figure_id:
                    advancing_figure = fig
                    break
        
        advancing_cannot_be_blocked = (
            advancing_figure and 
            hasattr(advancing_figure, 'cannot_be_blocked') and 
            advancing_figure.cannot_be_blocked
        )
        
        if advancing_cannot_be_blocked:
            info_text = "Your figure cannot be blocked — select any opponent figure"
        else:
            must_be_attacked_figures = [
                fig for fig in opponent_figures
                if hasattr(fig, 'must_be_attacked') and fig.must_be_attacked
            ]
            if must_be_attacked_figures:
                figure_names = ', '.join(f.name for f in must_be_attacked_figures)
                info_text = f"Must select: {figure_names}"
            else:
                info_text = "Click one of your opponent's figures to face your advance"
        
        info_surface = info_font.render(info_text, True, (180, 220, 255))  # Light blue
        
        # Create background box
        line_gap = int(0.009 * settings.SCREEN_HEIGHT)
        text_width = max(prompt_surface.get_width(), info_surface.get_width())
        text_height = prompt_surface.get_height() + info_surface.get_height() + line_gap
        padding = int(0.018 * settings.SCREEN_HEIGHT)
        border_w = max(2, int(0.004 * settings.SCREEN_HEIGHT))
        
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
        
        # Draw blue border for emphasis
        pygame.draw.rect(self.window, (100, 200, 255), box_rect, border_w)
        
        # Draw main prompt text centered in box
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        # Draw info text below
        info_x = box_rect.centerx - info_surface.get_width() // 2
        info_y = text_y + prompt_surface.get_height() + line_gap
        self.window.blit(info_surface, (info_x, info_y))
        
        # Add pulsing effect
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))

    def _draw_conquer_own_defender_prompt(self):
        """Draw a prominent prompt for Invader Swap own-defender selection."""
        prompt_text = "SELECT YOUR DEFENDER (INVADER SWAP)"
        prompt_surface = self.target_prompt_font.render(prompt_text, True, (255, 200, 80))  # Gold

        info_font = settings.get_font(int(settings.FIELD_TITLE_FONT_SIZE * 0.9))
        info_text = "Click one of your own figures to defend against the invader"
        info_surface = info_font.render(info_text, True, (255, 220, 140))

        line_gap = int(0.009 * settings.SCREEN_HEIGHT)
        text_width = max(prompt_surface.get_width(), info_surface.get_width())
        text_height = prompt_surface.get_height() + info_surface.get_height() + line_gap
        padding = int(0.018 * settings.SCREEN_HEIGHT)
        border_w = max(2, int(0.004 * settings.SCREEN_HEIGHT))

        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding,
        )

        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)

        pygame.draw.rect(self.window, (255, 200, 80), box_rect, border_w)

        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))

        info_x = box_rect.centerx - info_surface.get_width() // 2
        info_y = text_y + prompt_surface.get_height() + line_gap
        self.window.blit(info_surface, (info_x, info_y))

        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))

    def _force_immediate_redraw(self):
        """
        Force an immediate redraw of the field screen to show visual feedback.
        This is called when an icon state changes to provide instant visual response
        before any heavy operations (like opening detail box) occur.
        """
        # Redraw the field screen with updated icon states
        self.draw()

    def _refresh_all_seeing_eye_status(self):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_all_seeing_eye_check <= self.all_seeing_eye_check_interval:
            return
        try:
            self.cached_all_seeing_eye_status = (
                self.game.has_active_all_seeing_eye() if self.game else False)
            self.cached_opponent_all_seeing_eye_status = (
                self.game.has_opponent_cast_all_seeing_eye() if self.game else False)
        except Exception:
            self.cached_all_seeing_eye_status = False
            self.cached_opponent_all_seeing_eye_status = False
        self.last_all_seeing_eye_check = current_time

    def _field_static_layer_key(self):
        compartment_key = []
        for player in ('self', 'opponent'):
            for field in ('castle', 'village', 'military'):
                rect = self.compartments[player][field]
                compartment_key.append((player, field, rect.x, rect.y, rect.w, rect.h))
        bounds = self._field_static_bounds()
        return (
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            (bounds.x, bounds.y, bounds.w, bounds.h),
            tuple(compartment_key),
            bool(self.cached_all_seeing_eye_status),
            bool(self.cached_opponent_all_seeing_eye_status),
        )

    def _field_static_bounds(self):
        rects = [
            self.compartments[player][field]
            for player in ('self', 'opponent')
            for field in ('castle', 'village', 'military')
        ]
        left = min(rect.left for rect in rects)
        right = max(rect.right for rect in rects)
        top = min(rect.top for rect in rects)
        bottom = max(rect.bottom for rect in rects)
        title_pad = max(settings.FIELD_BOARD_TITLE_FONT_SIZE * 2,
                        abs(settings.FIELD_BOARD_TITLE_Y_OFFSET) * 2)
        bounds = pygame.Rect(left, top - title_pad, right - left, bottom - top + title_pad)
        bounds.left = max(0, bounds.left)
        bounds.top = max(0, bounds.top)
        bounds.right = min(settings.SCREEN_WIDTH, bounds.right)
        bounds.bottom = min(settings.SCREEN_HEIGHT, bounds.bottom)
        return bounds

    def _draw_field_static_layer(self):
        self._refresh_all_seeing_eye_status()
        cache_key = self._field_static_layer_key()
        if self._field_static_surface_key != cache_key or self._field_static_surface is None:
            bounds = self._field_static_bounds()
            surface = pygame.Surface(bounds.size, pygame.SRCALPHA)
            fill_color = (*settings.FIELD_FILL_COLOR[:3], settings.FIELD_TRANSPARENCY)
            border_color = (*settings.FIELD_BORDER_COLOR[:3], settings.FIELD_TRANSPARENCY)

            for player in ('self', 'opponent'):
                for field in ('castle', 'village', 'military'):
                    compartment = self.compartments[player][field]
                    local_compartment = compartment.move(-bounds.x, -bounds.y)
                    pygame.draw.rect(surface, fill_color, local_compartment)
                    if field in self.slot_icons:
                        slot_icon = self.slot_icons[field]
                        icon_rect = slot_icon.get_rect()
                        icon_rect.centerx = compartment.centerx
                        icon_rect.top = compartment.top + int(compartment.height * 0.018)
                        icon_rect.move_ip(-bounds.x, -bounds.y)
                        surface.blit(slot_icon, icon_rect)

            for player in ('self', 'opponent'):
                castle_comp = self.compartments[player]['castle']
                village_comp = self.compartments[player]['village']
                military_comp = self.compartments[player]['military']
                left = min(castle_comp.left, village_comp.left, military_comp.left)
                right = max(castle_comp.right, village_comp.right, military_comp.right)
                top = castle_comp.top
                bottom = castle_comp.bottom
                width = right - left
                height = bottom - top
                if width <= 0 or height <= 0:
                    continue
                group_rect = pygame.Rect(left - bounds.x, top - bounds.y, width, height)
                pygame.draw.rect(surface, border_color, group_rect, settings.FIELD_BORDER_WIDTH)
                comp_positions = sorted([
                    (castle_comp.left, castle_comp.width),
                    (village_comp.left, village_comp.width),
                    (military_comp.left, military_comp.width),
                ], key=lambda item: item[0])
                for i in range(len(comp_positions) - 1):
                    divider_x = comp_positions[i][0] + comp_positions[i][1]
                    pygame.draw.line(
                        surface,
                        border_color,
                        (divider_x - bounds.x, top - bounds.y),
                        (divider_x - bounds.x, bottom - bounds.y),
                        settings.FIELD_BORDER_WIDTH,
                    )

            for player in ('self', 'opponent'):
                castle_comp = self.compartments[player]['castle']
                village_comp = self.compartments[player]['village']
                military_comp = self.compartments[player]['military']
                left = min(castle_comp.left, village_comp.left, military_comp.left)
                right = max(castle_comp.right, village_comp.right, military_comp.right)
                title_text_str = 'YOU' if player == 'self' else 'OPPONENT'
                title_text = self.board_title_font.render(
                    title_text_str, True, settings.FIELD_BOARD_TITLE_COLOR)
                title_rect = title_text.get_rect()
                if player == 'self':
                    title_rect.left = left
                else:
                    title_rect.right = right
                title_rect.bottom = castle_comp.top + settings.FIELD_BOARD_TITLE_Y_OFFSET
                title_rect.move_ip(-bounds.x, -bounds.y)

                show_eye_icon = (
                    self.cached_all_seeing_eye_status if player == 'opponent'
                    else self.cached_opponent_all_seeing_eye_status
                )
                if show_eye_icon:
                    eye_rect = self.all_seeing_eye_icon.get_rect()
                    if player == 'self':
                        eye_rect.left = title_rect.right + 5
                    else:
                        eye_rect.right = title_rect.left - 5
                    eye_rect.centery = title_rect.centery
                    surface.blit(self.all_seeing_eye_icon, eye_rect)
                surface.blit(title_text, title_rect)

            for player in ('self', 'opponent'):
                for field in ('castle', 'village', 'military'):
                    compartment = self.compartments[player][field]
                    title_text = self.field_title_font.render(
                        field.upper(), True, settings.FIELD_TITLE_COLOR)
                    title_rect = title_text.get_rect()
                    if player == 'self':
                        title_rect.left = compartment.left + settings.FIELD_TITLE_PADDING
                    else:
                        title_rect.right = compartment.right - settings.FIELD_TITLE_PADDING
                    title_rect.top = compartment.top + settings.FIELD_TITLE_PADDING
                    title_rect.move_ip(-bounds.x, -bounds.y)
                    surface.blit(title_text, title_rect)

            self._field_static_surface = surface
            self._field_static_surface_key = cache_key
            self._field_static_surface_pos = bounds.topleft

        self.window.blit(self._field_static_surface, self._field_static_surface_pos)

    def draw(self):
        """Draw the screen, including the field background and figure icons."""
        self._sync_field_compartments_layout()
        if self._uses_unified_conquer_layout():
            self._draw_unified_conquer_battlefield_backdrop()
        else:
            super().draw()

        # Safety check: ensure categorized_figures exists
        if not hasattr(self, 'categorized_figures') or not self.categorized_figures:
            return

        if self.figures or True:  # Always draw compartments even without figures
            with perf_section('field.static_layer'):
                self._draw_field_static_layer()

            # Fourth pass: Draw figures
            # Collect all icon positions across compartments, then draw in
            # z-order layers so that a selected/hovered info box always
            # appears on top of icons in neighbouring compartments.
            all_regular = []
            all_selected = []
            all_hovered = None

            for player in ['self', 'opponent']:
                for field in ['castle', 'village', 'military']:
                    compartment = self.compartments[player][field]
                    # Safety check for categorized_figures
                    if player not in self.categorized_figures or field not in self.categorized_figures[player]:
                        continue
                    figures = self.categorized_figures[player][field]

                    if len(figures) > 0:
                        # Calculate the y-position to distribute icons in the compartment.
                        #
                        # The icon's y coordinate is the CENTER of the frame.
                        # The frame extends frame_h/2 above and below that center.
                        # Below, a name box + power row extends even further.
                        # We reserve just enough top/bottom margin so the first
                        # icon's frame top and the last icon's info box bottom
                        # stay inside the compartment, then distribute centers
                        # evenly across the remaining space.
                        frame_h = settings.FRAME_FIGURE_SCALE * settings.FIGURE_ICON_HEIGHT
                        # The frame has ornamental corners — the visible figure
                        # content is smaller than frame_h/2, so we can let the
                        # decorative part overlap the title area slightly.
                        top_margin = settings.FIGURE_ICON_HEIGHT * 0.42
                        # Bottom margin: info box extends ~0.34*FIH + caption below center
                        caption_font_size = settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE
                        caption_h = int(caption_font_size * 2.6)
                        bottom_margin = 0.34 * settings.FIGURE_ICON_HEIGHT + caption_h

                        title_space = settings.FIELD_TITLE_FONT_SIZE + settings.FIELD_TITLE_PADDING
                        total_height = compartment.height - 2 * settings.FIELD_BORDER_WIDTH
                        
                        # Usable range for icon centers
                        first_center = compartment.top + title_space + top_margin
                        last_center = compartment.top + total_height - bottom_margin
                        
                        if len(figures) == 1:
                            icon_y_start = (first_center + last_center) / 2
                            icon_spacing = 0
                        else:
                            # Default center-to-center spacing: the icon's visual
                            # height (top_margin + bottom_margin ≈ frame visible area
                            # + caption) plus a small gap between icons.
                            default_spacing = top_margin + bottom_margin + settings.FIELD_ICON_PADDING_Y
                            max_spacing = (last_center - first_center) / (len(figures) - 1)
                            if max_spacing >= default_spacing:
                                # Enough room — use default spacing and centre the group
                                icon_spacing = default_spacing
                                group_h = (len(figures) - 1) * icon_spacing
                                offset = ((last_center - first_center) - group_h) / 2
                                icon_y_start = first_center + offset
                            else:
                                # Tight — spread evenly across available range
                                icon_spacing = max_spacing
                                icon_y_start = first_center

                        # Calculate positions and separate into layers: regular, selected, hovered
                        for i, figure in enumerate(figures):
                            if (self._is_tactics_hand_battle_field_view_only()
                                    and self._is_tactics_hand_battle_fighter(figure)):
                                continue
                            if figure.id not in self.icon_cache:
                                continue
                            icon = self.icon_cache[figure.id]
                            icon_x = compartment.centerx
                            icon_y = icon_y_start + i * icon_spacing
                            
                            if icon.hovered:
                                all_hovered = (icon, icon_x, icon_y)
                            elif icon.clicked:
                                all_selected.append((icon, icon_x, icon_y))
                            else:
                                all_regular.append((icon, icon_x, icon_y))

            # Draw in global z-order layers: regular -> selected -> hovered
            # Reverse regular so bottom icons are drawn first and top icons
            # paint over them, keeping each figure's lower info box visible.
            for icon, icon_x, icon_y in reversed(all_regular):
                icon.draw(icon_x, icon_y)

            for icon, icon_x, icon_y in reversed(all_selected):
                icon.draw(icon_x, icon_y)

            if all_hovered:
                icon, icon_x, icon_y = all_hovered
                icon.draw(icon_x, icon_y)

            # Cache the last draw layout so the conquer game screen can
            # redraw these icons as a top-of-z-order overlay above the
            # duel-lane panel (figures must remain in the foreground so
            # their small info boxes are never occluded).
            self._last_drawn_figure_layout = {
                'regular': list(all_regular),
                'selected': list(all_selected),
                'hovered': all_hovered,
            }

            self._draw_tactics_hand_battle_context_overlays(
                all_regular + all_selected
                + ([all_hovered] if all_hovered else []))

            # Conquer selection focus: dim the field, redraw selectable icons
            # cleanly above it, then add a compact side marker.
            self._draw_conquer_selection_focus(
                all_regular + all_selected
                + ([all_hovered] if all_hovered else []))

        # Draw opponent's hand cards if All Seeing Eye is active (use cached status)
        if self.cached_all_seeing_eye_status:
            self._draw_opponent_hand_cards()

        # Note: Figure detail box is drawn in game_screen.py to ensure it's on top of hand cards
        
        conquer_parent = self._conquer_parent()

        # Draw target selection prompt if in target selection mode
        if ((hasattr(self.state, 'pending_spell_cast') and self.state.pending_spell_cast)
            or (getattr(self.state, 'pending_conquer_prelude_target', None)
                and not conquer_parent)):
            self._draw_target_selection_prompt()
        
        # Draw defender selection prompt if in defender selection mode
        if self.defender_selection_mode and not conquer_parent:
            self._draw_defender_selection_prompt()

        # Draw own-defender selection prompt for Invader Swap
        if self.conquer_own_defender_mode and not conquer_parent:
            self._draw_conquer_own_defender_prompt()

    @staticmethod
    def _figure_field(figure):
        family = getattr(figure, 'family', None)
        return getattr(figure, 'field', None) or getattr(family, 'field', None)

    @staticmethod
    def _figure_color(figure):
        family = getattr(figure, 'family', None)
        return getattr(figure, 'color', None) or getattr(family, 'color', None)

    def _active_modifier_types(self):
        modifiers = self.game.battle_modifier if self.game and isinstance(self.game.battle_modifier, list) else []
        return [m.get('type') for m in modifiers if isinstance(m, dict)]

    def _is_civil_war_second_attacker_selectable(self, figure, icon=None):
        game = self.game
        if not game or figure is None:
            return False
        if figure.player_id != game.player_id:
            return False
        if self._figure_field(figure) != 'village':
            return False
        if figure.id == getattr(game, 'advancing_figure_id', None):
            return False
        required_color = getattr(game, 'civil_war_required_color', None)
        if required_color and self._figure_color(figure) != required_color:
            return False
        if figure.id in (getattr(game, 'resting_figure_ids', None) or []):
            return False
        if getattr(figure, 'cannot_attack', False):
            return False
        if icon is not None and getattr(icon, 'has_deficit', False):
            return False
        return True

    def _is_conquer_own_defender_selectable(self, figure, icon=None):
        game = self.game
        if not game or figure is None:
            return False
        if figure.player_id != game.player_id:
            return False
        modifier_types = self._active_modifier_types()
        if (('Peasant War' in modifier_types or 'Civil War' in modifier_types)
                and self._figure_field(figure) != 'village'):
            return False
        if (getattr(game, 'civil_war_defender_second', False)
                and 'Civil War' in modifier_types):
            if figure.id == getattr(game, 'defending_figure_id', None):
                return False
            required_color = getattr(game, 'civil_war_required_color', None)
            if required_color and self._figure_color(figure) != required_color:
                return False
        if getattr(figure, 'cannot_defend', False):
            return False
        if getattr(figure, 'cannot_be_targeted', False):
            return False
        if icon is not None and getattr(icon, 'has_deficit', False):
            return False
        return True

    def _icon_is_selectable_for_current_mode(self, icon):
        """Return True when ``icon`` is a valid click target right now.

        Rules per active conquer selection mode:
          * Opponent-defender mode → trust ``icon.defender_selectable``
            (already computed by ``_update_defender_selectable``).
          * Own-defender mode → only own figures whose family field is village
            when Peasant War / Civil War is active, otherwise all own figures
            that don't have ``cannot_defend`` / ``cannot_be_targeted``.
          * Forced advance → own figures that are not resting and don't have
            ``cannot_attack``.
          * Conquer prelude target → all figures matching the target_scope.
        """
        figure = getattr(icon, 'figure', None)
        if figure is None:
            return False
        if self._is_conquer_visual_ghost_figure(figure):
            return False

        game = self.game
        is_own = (game is not None and figure.player_id == game.player_id)
        modifier_types = self._active_modifier_types()
        village_only = ('Peasant War' in modifier_types
                        or 'Civil War' in modifier_types)

        if self.defender_selection_mode:
            return bool(getattr(icon, 'defender_selectable', True)) and not is_own

        if self.conquer_own_defender_mode:
            return self._is_conquer_own_defender_selectable(figure, icon)

        if game is not None and getattr(game, 'civil_war_awaiting_second', False):
            return self._is_civil_war_second_attacker_selectable(figure, icon)

        if (game is not None
                and getattr(game, 'pending_forced_advance', False)
                and not getattr(game, 'advancing_figure_id', None)):
            if not is_own:
                return False
            resting = (figure.id in (getattr(game, 'resting_figure_ids', None) or []))
            if resting:
                return False
            if getattr(figure, 'cannot_attack', False):
                return False
            if village_only and self._figure_field(figure) != 'village':
                return False
            return True

        scope_target = getattr(self.state, 'pending_conquer_prelude_target', None)
        if scope_target:
            target_scope = (scope_target.get('target_scope')
                            if isinstance(scope_target, dict) else None)
            if getattr(figure, 'checkmate', False):
                return False
            if target_scope == 'own':
                return is_own
            if target_scope == 'opponent':
                return not is_own
            return True

        return True

    def _is_conquer_selection_active(self):
        """True when the field is in an active, player-visible selection mode.

        Each branch requires that the server/game has fully committed to the
        selection step (dialogue shown / mode flag set) to prevent premature
        dimming during a preceding phase.
        """
        conquer_parent = self._conquer_parent()
        active_step = None
        if conquer_parent and hasattr(conquer_parent, 'active_conquer_timeline_step'):
            active_step = conquer_parent.active_conquer_timeline_step()

        def timeline_allows(kind):
            if active_step is None:
                return True
            return bool(
                getattr(active_step, 'kind', None) == kind
                and getattr(active_step, 'interactive', False)
            )

        if self.defender_selection_mode or self.conquer_own_defender_mode:
            return timeline_allows('defender')
        if getattr(self.state, 'pending_conquer_prelude_target', None):
            return timeline_allows('prelude_own')
        game = self.game
        if not game:
            return False
        if getattr(game, 'civil_war_awaiting_second', False):
            return timeline_allows('attacker')
        if getattr(game, 'civil_war_defender_second', False):
            return timeline_allows('defender')
        # Forced advance: only dim once the player has been notified that
        # they must pick their attacker (forced_advance_dialogue_shown guards
        # against dimming in the preceding step before the prompt appears).
        if (getattr(game, 'pending_forced_advance', False)
                and not getattr(game, 'advancing_figure_id', None)
                and getattr(game, 'forced_advance_dialogue_shown', False)):
            return timeline_allows('attacker')
        return False

    def _conquer_pending_focus_figure(self):
        """Return the figure currently pending confirmation, if any.

        The pending figure should keep a strong yellow ring even though it has
        already been clicked, so the player visually links the field figure
        with the icon shown in the conquer top panel.
        """
        for attr in ('_pending_advance_figure',
                     'figure_pending_defender_selection',
                     'figure_pending_own_defender_selection'):
            fig = getattr(self, attr, None)
            if fig is not None:
                return fig
        return None

    @staticmethod
    def _conquer_icon_halo_rect(icon, center, *, padding=2):
        use_big = bool(getattr(icon, 'hovered', False) or getattr(icon, 'clicked', False))
        frame = None
        if use_big:
            frame = getattr(icon, 'rect_frame_big', None) or getattr(icon, 'rect_frame', None)
        else:
            frame = getattr(icon, 'rect_frame', None) or getattr(icon, 'rect_frame_big', None)
        if frame is not None:
            rect = pygame.Rect(frame)
            rect.center = (int(center[0]), int(center[1]))
        else:
            frame_h = settings.FRAME_FIGURE_SCALE * settings.FIGURE_ICON_HEIGHT
            rect = pygame.Rect(0, 0, int(frame_h * 0.76), int(frame_h * 0.92))
            rect.center = (int(center[0]), int(center[1]))
        pad = max(0, int(padding))
        if pad:
            rect.inflate_ip(pad * 2, pad * 2)
        return rect

    @staticmethod
    def _conquer_halo_radius(rect):
        rect = pygame.Rect(rect)
        return max(3, min(7, min(rect.width, rect.height) // 8))

    @staticmethod
    def _conquer_icon_marker_geometry(icon, center, *, is_own, padding=3):
        """Return geometry for a side marker (round 12).

        Replaces the previous full rounded-rect halo around selectable
        figures with a small 3px vertical bar topped by a small inward-
        pointing triangle, sitting on the side of the figure that faces
        the opposing line — right for own figures, left for opponent
        figures. This keeps the marker clear of the figure's info chip
        on the opposite side.
        """
        halo = FieldScreen._conquer_icon_halo_rect(icon, center, padding=0)
        bar_w = 3
        bar_h = max(18, int(halo.height * 0.40))
        if is_own:
            bar_x = halo.right + padding
            side = 'right'
        else:
            bar_x = halo.left - padding - bar_w
            side = 'left'
        bar_rect = pygame.Rect(bar_x, 0, bar_w, bar_h)
        bar_rect.centery = halo.centery
        midpoint = (bar_rect.centerx, bar_rect.centery)
        # A centered, compact arrowhead points inward toward the figure. This
        # reads cleaner than the old top-pinned triangle and keeps the marker
        # out of the figure/info-box footprint.
        tri_w = 6
        tri_h = 8
        mid_y = bar_rect.centery
        if is_own:
            # bar's inward edge is its left side
            inner_x = bar_rect.left
            tip_x = inner_x - tri_w
        else:
            inner_x = bar_rect.right
            tip_x = inner_x + tri_w
        triangle = [
            (inner_x, mid_y - tri_h // 2),
            (inner_x, mid_y + tri_h // 2),
            (tip_x, mid_y),
        ]
        return {
            'side': side,
            'bar_rect': bar_rect,
            'triangle': triangle,
            'midpoint': midpoint,
        }

    def _draw_conquer_marker(self, marker, color):
        """Render a marker (bar + triangle) onto self.window with alpha."""
        if not marker:
            return
        bar_rect = pygame.Rect(marker['bar_rect'])
        triangle = list(marker['triangle'])
        xs = [bar_rect.left, bar_rect.right] + [p[0] for p in triangle]
        ys = [bar_rect.top, bar_rect.bottom] + [p[1] for p in triangle]
        pad = 3
        bx = min(xs) - pad
        by = min(ys) - pad
        bw = (max(xs) - min(xs)) + pad * 2
        bh = (max(ys) - min(ys)) + pad * 2
        surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
        local_bar = bar_rect.move(-bx, -by)
        local_tri = [(p[0] - bx, p[1] - by) for p in triangle]
        pygame.draw.rect(surf, color, local_bar, 0, border_radius=2)
        pygame.draw.polygon(surf, color, local_tri)
        self.window.blit(surf, (bx, by))

    def draw_figures_overlay(self):
        """Redraw the cached figure icons on top of overlay panels.

        The conquer game screen calls this after rendering the duel lane so
        that figure icons (and their small info boxes) always stay in the
        foreground, even when an HUD panel would otherwise occlude them.
        """
        layout = getattr(self, '_last_drawn_figure_layout', None)
        if not layout:
            return
        # Performance: only redraw figures whose icon rect intersects the
        # overlay clip (duel lane). Redrawing every figure every frame is
        # expensive and causes visible lag in the conquer screen.
        clip = getattr(self, '_figure_overlay_clip_rect', None)

        def _needs_redraw(icon):
            if clip is None:
                return True
            rect = getattr(icon, 'rect_frame_big', None) or getattr(icon, 'rect_frame', None)
            if rect is None:
                return True
            return rect.colliderect(clip)

        for icon, icon_x, icon_y in reversed(layout.get('regular') or []):
            if _needs_redraw(icon):
                icon.draw(icon_x, icon_y)
        for icon, icon_x, icon_y in reversed(layout.get('selected') or []):
            if _needs_redraw(icon):
                icon.draw(icon_x, icon_y)
        hovered = layout.get('hovered')
        if hovered:
            icon, icon_x, icon_y = hovered
            if _needs_redraw(icon):
                icon.draw(icon_x, icon_y)

    def _draw_conquer_selection_focus(self, drawn_icons):
        """Dim the field and redraw selectable figure icons above it.

        The earlier implementation punched rounded-square cutouts through the
        dim layer, which could read as a box around each target. The current
        version draws one simple dim pass, then re-blits the whole selectable
        field icon (frame, glow, and info box) above it before adding the
        compact side marker.
        """
        if not self._is_conquer_selection_active():
            return

        import math
        pending_focus = self._conquer_pending_focus_figure()
        t = pygame.time.get_ticks() / 1000.0
        pulse = 0.5 + 0.5 * math.sin(t * 3.2)

        # Partition icons into selectable / non-selectable.
        selectable_entries = []
        for icon, ix, iy in drawn_icons:
            if not icon or not getattr(icon, 'figure', None):
                continue
            if self._icon_is_selectable_for_current_mode(icon):
                selectable_entries.append((icon, int(ix), int(iy)))

        # Dim everything first. Selectable icons are redrawn above this layer,
        # so their frame and info box stay crisp without a visible cutout box.
        dim = pygame.Surface(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 155))
        self.window.blit(dim, (0, 0))

        regular_entries = []
        selected_entries = []
        hovered_entries = []
        for entry in selectable_entries:
            icon = entry[0]
            if getattr(icon, 'hovered', False):
                hovered_entries.append(entry)
            elif getattr(icon, 'clicked', False):
                selected_entries.append(entry)
            else:
                regular_entries.append(entry)

        for icon, cx, cy in reversed(regular_entries):
            icon.draw(cx, cy)
        for icon, cx, cy in reversed(selected_entries):
            icon.draw(cx, cy)
        for icon, cx, cy in hovered_entries:
            icon.draw(cx, cy)

        # Pulsing gold/cyan side markers drawn on the window after the dim
        # layer and redrawn icons. A small 3px vertical bar with an inward-
        # pointing arrowhead replaces any full figure border.
        alpha = int(150 + 90 * pulse)
        gold = (245, 205, 95, alpha)
        cyan = (120, 220, 235, min(255, alpha + 40))
        own_id = getattr(getattr(self, 'game', None), 'player_id', None)
        for icon, cx, cy in selectable_entries:
            figure = getattr(icon, 'figure', None)
            is_own = getattr(figure, 'player_id', None) == own_id
            is_pending = (pending_focus is not None
                          and getattr(figure, 'id', None)
                              == getattr(pending_focus, 'id', None))
            marker = self._conquer_icon_marker_geometry(
                icon, (cx, cy), is_own=is_own)
            self._draw_conquer_marker(marker, cyan if is_pending else gold)

    def _update_defender_selectable(self):
        """Mark figure icons as selectable/non-selectable for defender selection mode."""
        # Get advancing figure to check cannot_be_blocked
        advancing_figure = None
        if self.game.advancing_figure_id:
            for fig in self.figures:
                if fig.id == self.game.advancing_figure_id:
                    advancing_figure = fig
                    break
        
        advancing_cannot_be_blocked = (
            advancing_figure and 
            hasattr(advancing_figure, 'cannot_be_blocked') and 
            advancing_figure.cannot_be_blocked
        )
        
        # Check active battle modifiers
        modifiers = self.game.battle_modifier if isinstance(self.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        has_peasant_war = 'Peasant War' in modifier_types
        has_blitzkrieg = 'Blitzkrieg' in modifier_types
        has_civil_war = 'Civil War' in modifier_types
        village_only = has_peasant_war or has_civil_war
        
        # Blitzkrieg acts like cannot_be_blocked for must_be_attacked purposes
        skip_must_be_attacked = advancing_cannot_be_blocked or has_blitzkrieg
        
        # Determine which opponent figures are eligible
        opponent_figures_eligible = []
        checkmate_fallback = []
        for fig in self.figures:
            if fig.player_id == self.game.player_id:
                continue
            if hasattr(fig, 'cannot_defend') and fig.cannot_defend:
                continue
            if hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted:
                continue
            if hasattr(fig, 'checkmate') and fig.checkmate:
                checkmate_fallback.append(fig)
                continue
            # Village-only restriction (Peasant War / Civil War)
            if village_only and hasattr(fig, 'family') and fig.family.field != 'village':
                continue
            # Civil War second pick: must match color of first defender
            if has_civil_war and hasattr(self.game, 'civil_war_defender_second') and self.game.civil_war_defender_second:
                required_color = getattr(self.game, 'civil_war_required_color', None)
                if required_color and hasattr(fig, 'family') and fig.family.color != required_color:
                    continue
                # Exclude the figure already selected as first defender
                if fig.id == self.game.defending_figure_id:
                    continue
            opponent_figures_eligible.append(fig)
        
        # Fallback: if no non-checkmate targets, allow checkmate figures
        if not opponent_figures_eligible and checkmate_fallback:
            opponent_figures_eligible = checkmate_fallback
        
        # must_be_attacked filtering — only consider village figures if village_only
        must_be_attacked_figures = []
        if not skip_must_be_attacked:
            must_be_attacked_figures = [
                fig for fig in opponent_figures_eligible
                if hasattr(fig, 'must_be_attacked') and fig.must_be_attacked
            ]
        
        # Build set of must_be_attacked figure IDs for reliable comparison
        must_be_attacked_ids = {fig.id for fig in must_be_attacked_figures}
        eligible_ids = {fig.id for fig in opponent_figures_eligible}
        
        logger.debug(f"[DEFENDER_SELECT] Advancing figure: {advancing_figure.name if advancing_figure else 'None'}, cannot_be_blocked: {advancing_cannot_be_blocked}")
        logger.debug(f"[DEFENDER_SELECT] Battle modifiers: peasant_war={has_peasant_war}, blitzkrieg={has_blitzkrieg}, civil_war={has_civil_war}")
        logger.debug(f"[DEFENDER_SELECT] Eligible opponent figures: {[(f.name, f.id, getattr(f, 'must_be_attacked', False)) for f in opponent_figures_eligible]}")
        logger.debug(f"[DEFENDER_SELECT] Must-be-attacked figures: {[(f.name, f.id) for f in must_be_attacked_figures]}")
        
        for icon in self.figure_icons:
            fig = icon.figure
            # Enable defender selection mode on all icons (allows hidden figure hover)
            icon.in_defender_selection_mode = True
            
            # Own figures are never selectable as defenders
            if fig.player_id == self.game.player_id:
                icon.defender_selectable = False
                continue
            
            # Opponent figure must be in the eligible set (handles cannot_defend, cannot_be_targeted, village_only)
            if fig.id not in eligible_ids:
                icon.defender_selectable = False
                continue
            
            # If must_be_attacked applies, only those figures are selectable
            if must_be_attacked_ids and fig.id not in must_be_attacked_ids:
                icon.defender_selectable = False
                logger.debug(f"[DEFENDER_SELECT] {fig.name} (id={fig.id}) NOT selectable (must_be_attacked constraint)")
                continue
            
            icon.defender_selectable = True
            logger.debug(f"[DEFENDER_SELECT] {fig.name} (id={fig.id}) IS selectable")

    def _update_conquer_own_defender_selectable(self):
        """Mark figure icons for Invader Swap own-defender selection."""
        for icon in self.figure_icons:
            icon.in_defender_selection_mode = True
            icon.defender_selectable = self._is_conquer_own_defender_selectable(
                getattr(icon, 'figure', None), icon)

    def selectable_defender_figure_ids(self):
        """List figure ids currently selectable as the opponent defender.

        Used by the conquer screen to auto-resolve a defender selection
        when only one valid target remains.  Returns an empty list when
        not in defender-selection mode.
        """
        if not getattr(self, 'defender_selection_mode', False):
            return []
        ids = []
        for icon in self.figure_icons:
            fig = getattr(icon, 'figure', None)
            if fig is None:
                continue
            if self._is_conquer_visual_ghost_figure(fig):
                continue
            if not getattr(icon, 'defender_selectable', False):
                continue
            if getattr(fig, 'player_id', None) == self.game.player_id:
                continue
            ids.append(fig.id)
        return ids

    def selectable_own_defender_figure_ids(self):
        """List figure ids currently selectable as the conquerer's own
        defender (Invader Swap second-pick)."""
        if not getattr(self, 'conquer_own_defender_mode', False):
            return []
        ids = []
        for icon in self.figure_icons:
            fig = getattr(icon, 'figure', None)
            if fig is None:
                continue
            if self._is_conquer_visual_ghost_figure(fig):
                continue
            if not getattr(icon, 'defender_selectable', False):
                continue
            if getattr(fig, 'player_id', None) != self.game.player_id:
                continue
            ids.append(fig.id)
        return ids
    
    def _reset_defender_selectable(self):
        """Reset all figure icons to selectable (normal state)."""
        for icon in self.figure_icons:
            icon.defender_selectable = True
            icon.in_defender_selection_mode = False
