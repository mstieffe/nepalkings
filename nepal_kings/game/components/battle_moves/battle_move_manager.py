"""Manager for battle move families and their instances."""

import pygame
from config import settings
from game.components.battle_moves.battle_move import BattleMoveFamily, BattleMove
from game.components.battle_moves.battle_move_configs import ALL_BATTLE_MOVE_CONFIGS


# Number card ranks (main cards only — 7..10)
_NUMBER_RANKS = {'7', '8', '9', '10'}


class BattleMoveManager:
    """Loads battle move families from config, provides helpers to match cards."""

    # Class-level image cache
    _image_cache = {}

    def __init__(self):
        self.families = []
        self.families_by_name = {}
        self._load_families()

    # ---------------------------------------------------------------- loading
    def _load_families(self):
        for cfg in ALL_BATTLE_MOVE_CONFIGS:
            icon_img = self._load_image(settings.BATTLE_MOVE_ICON_IMG_DIR + cfg['icon_img'])
            icon_gray_img = self._load_image(settings.BATTLE_MOVE_ICON_GREYSCALE_IMG_DIR + cfg['icon_gray_img'])
            frame_img = self._load_image(settings.BATTLE_MOVE_FRAME_IMG_DIR + cfg['frame_img'])
            frame_gray_img = self._load_image(settings.BATTLE_MOVE_FRAME_GREYSCALE_IMG_DIR + cfg['frame_gray_img'])
            glow_green_img = self._load_image(settings.BATTLE_MOVE_GLOW_IMG_DIR + cfg['glow_green_img'])
            glow_blue_img = self._load_image(settings.BATTLE_MOVE_GLOW_IMG_DIR + cfg['glow_blue_img'])

            family = BattleMoveFamily(
                name=cfg['name'],
                description=cfg['description'],
                required_rank=cfg['required_rank'],
                icon_img=icon_img,
                icon_gray_img=icon_gray_img,
                frame_img=frame_img,
                frame_gray_img=frame_gray_img,
                glow_green_img=glow_green_img,
                glow_blue_img=glow_blue_img,
            )
            self.families.append(family)
            self.families_by_name[family.name] = family

    def _load_image(self, path):
        if path not in BattleMoveManager._image_cache:
            try:
                BattleMoveManager._image_cache[path] = pygame.image.load(path).convert_alpha()
            except Exception as e:
                print(f"[BattleMoveManager] Failed to load image: {path} — {e}")
                # Return a small placeholder surface
                surf = pygame.Surface((64, 64), pygame.SRCALPHA)
                surf.fill((100, 100, 100, 128))
                BattleMoveManager._image_cache[path] = surf
        return BattleMoveManager._image_cache[path]

    # ----------------------------------------------------------- card matching
    def get_available_moves(self, hand_cards, already_bought_card_ids=None):
        """Return a dict  {family_name: [BattleMove, ...]}  for cards in hand.

        Cards that are already used for a bought move (by card id) are excluded.
        """
        if already_bought_card_ids is None:
            already_bought_card_ids = set()

        result = {}
        for family in self.families:
            moves = []
            for card in hand_cards:
                if card.id in already_bought_card_ids:
                    continue
                if self._card_matches_family(card, family):
                    move = BattleMove(
                        name=family.name,
                        family=family,
                        card=card,
                        suit=card.suit,
                    )
                    moves.append(move)
            if moves:
                result[family.name] = moves
        return result

    def get_families_with_moves(self, hand_cards, already_bought_card_ids=None):
        """Return list of families that have at least one buyable move."""
        available = self.get_available_moves(hand_cards, already_bought_card_ids)
        return [f for f in self.families if f.name in available]

    @staticmethod
    def _card_matches_family(card, family):
        """Check whether a card qualifies for the given family's required rank."""
        req = family.required_rank
        if req == 'number':
            return card.rank in _NUMBER_RANKS
        return card.rank == req
