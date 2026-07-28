# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Lightweight Game-like proxy for kingdom conquer/defence screens.

BuildFigureScreen and BattleShopScreen reference ``self.game`` extensively.
This proxy provides the minimal interface they need so the screens can
operate in ``mode='conquer'`` or ``mode='defence'`` without a real duel Game.
"""

from game.components.figures.figure_manager import FigureManager


class KingdomGameProxy:
    """Minimal stand-in for a duel Game object used by kingdom config screens.

    Attributes mirror the Game properties that BuildFigureScreen and
    BattleShopScreen read, but are either no-ops or return safe defaults.
    """

    def __init__(self, config=None, land_id=None, mode='conquer',
                 land_suit_bonus_suit=None, land_suit_bonus_value=None,
                 land=None, land_bonus_role=None):
        self._config = config or {}
        self.land_id = land_id
        self.land = land or {}
        self.mode = mode  # 'conquer' or 'defence'

        # Land suit bonus (used by FieldFigureIcon for battle bonus calculation)
        self.land_suit_bonus_suit = (
            land_suit_bonus_suit
            if land_suit_bonus_suit is not None
            else self.land.get('suit_bonus_suit')
        )
        self.land_suit_bonus_value = (
            land_suit_bonus_value
            if land_suit_bonus_value is not None
            else self.land.get('suit_bonus_value')
        )
        self.land_home_ground_asymmetry_enabled = bool(
            self.land.get('land_home_ground_asymmetry_enabled', False))
        self.land_home_ground_attacker_factor = float(
            self.land.get('land_home_ground_attacker_factor', 1.0))
        # Config figures do not have live Player ids yet, so their side of the
        # future battle is explicit: conquer setup is attacker, defence setup
        # is defender.
        self.land_bonus_role = land_bonus_role

        # Properties read by SubScreen / BuildFigureScreen / BattleShopScreen
        self.game_id = None
        self.player_id = None
        self.game_over = False
        self.action_in_progress = False
        self.turn = True  # always "your turn" in config mode
        self.ceasefire_active = False
        self.advancing_figure_id = None
        self.advancing_player_id = None
        self.invader_player_id = None
        self.pending_forced_advance = False
        self.battle_confirmed = False
        self.battle_moves_phase = False
        self.in_battle_phase = False
        self.both_battle_moves_ready = False
        self.waiting_for_opponent_battle_moves = False
        self.battle_modifier = []
        self.infinite_hammer_active = False

        # Chat stubs
        self.chat_messages = []

        # Figure manager for resource calculation
        self._figure_manager = FigureManager()

    # ── Config sync ─────────────────────────────────────────────────

    def set_config(self, config):
        """Update after a server response returns a new config."""
        self._config = config or {}

    # ── Lock / unlock stubs ─────────────────────────────────────────

    def lock_actions(self):
        self.action_in_progress = True

    def unlock_actions(self):
        self.action_in_progress = False

    # ── Card helpers (redirected to card_source externally) ──────────

    def get_hand(self):
        """Not used — CollectionCardSource.get_cards() is used instead."""
        return [], []

    def get_figures(self, families, is_opponent=False):
        """Return config figures."""
        return self._config.get('figures', [])

    # ── Resource calculation ────────────────────────────────────────

    def calculate_resources(self, families, is_opponent=False):
        """Calculate aggregate produces/requires from config figures."""
        produces = {}
        requires = {}
        for fig in self._config.get('figures', []):
            for res, amt in (fig.get('produces') or {}).items():
                produces[res] = produces.get(res, 0) + amt
            for res, amt in (fig.get('requires') or {}).items():
                requires[res] = requires.get(res, 0) + amt
        return {'produces': produces, 'requires': requires}

    # ── Stubs for methods called after build/buy ────────────────────

    def update(self):
        """No-op — config screens don't poll."""
        pass

    def update_from_dict(self, data):
        """No-op — not used in kingdom mode."""
        pass

    def is_battle_active(self):
        return False

    def landslide_active(self):
        """Whether the config currently contains a Landslide modifier."""
        modifiers = self.battle_modifier if isinstance(
            self.battle_modifier, list) else []
        return any(
            isinstance(modifier, dict)
            and modifier.get('type') == 'Landslide'
            for modifier in modifiers
        )

    def effective_land_bonus(self):
        """Return the land bonus after config-time battle modifiers."""
        suit = self.land_suit_bonus_suit
        value = self.land_suit_bonus_value
        if not suit or not value:
            return None, 0
        value = int(value)
        if self.landslide_active():
            value = -abs(value)
        return suit, value

    def effective_land_bonus_for(self, player_id):
        """Mirror Game.effective_land_bonus_for() before Player ids exist."""
        suit, value = self.effective_land_bonus()
        if not suit or not value:
            return suit, value
        is_attacker = self.land_bonus_role == 'attacker'
        if self.land_bonus_role is None:
            invader_id = self.invader_player_id
            is_attacker = invader_id is not None and player_id == invader_id
        if self.land_home_ground_asymmetry_enabled and is_attacker:
            value = int(round(
                int(value) * self.land_home_ground_attacker_factor))
        return suit, value

    @property
    def cached_figures_data(self):
        return {}
