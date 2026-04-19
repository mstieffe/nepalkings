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
                 land_suit_bonus_suit=None, land_suit_bonus_value=None):
        self._config = config or {}
        self.land_id = land_id
        self.mode = mode  # 'conquer' or 'defence'

        # Land suit bonus (used by FieldFigureIcon for battle bonus calculation)
        self.land_suit_bonus_suit = land_suit_bonus_suit
        self.land_suit_bonus_value = land_suit_bonus_value

        # Properties read by SubScreen / BuildFigureScreen / BattleShopScreen
        self.game_id = None
        self.player_id = None
        self.game_over = False
        self.action_in_progress = False
        self.turn = True  # always "your turn" in config mode
        self.ceasefire_active = False
        self.advancing_figure_id = None
        self.advancing_player_id = None
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

    @property
    def cached_figures_data(self):
        return {}
