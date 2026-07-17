# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for v2.0 server settings validity."""
from ai.defence import config as ai_defence_config
import server_settings as config


class TestV2ServerSettings:
    def test_booster_pack_constants(self):
        assert config.STARTER_BOOSTER_PACKS >= 0
        assert config.STARTER_BOOSTER_PACKS_SIDE >= 0
        assert config.BOOSTER_PACK_PRICE > 0
        assert config.BOOSTER_PACK_SIDE_PRICE > 0
        assert config.BOOSTER_PACK_CARDS > 0
        assert config.DUEL_WINNER_BOOSTER_PACKS >= 0
        assert config.DUEL_LOSER_BOOSTER_PACKS >= 0

    def test_booster_tier_probabilities_sum_to_one(self):
        total = sum(config.BOOSTER_TIER_PROBABILITIES.values())
        assert abs(total - 1.0) < 1e-6

    def test_booster_side_tier_probabilities_sum_to_one(self):
        total = sum(config.BOOSTER_SIDE_TIER_PROBABILITIES.values())
        assert abs(total - 1.0) < 1e-6

    def test_booster_tier_ranks_nonempty(self):
        for tier, ranks in config.BOOSTER_TIER_RANKS.items():
            assert len(ranks) > 0, f"Tier {tier} has no ranks"

    def test_booster_side_tier_ranks_nonempty(self):
        for tier, ranks in config.BOOSTER_SIDE_TIER_RANKS.items():
            assert len(ranks) > 0, f"Side tier {tier} has no ranks"

    def test_duel_booster_reward_probabilities_sum_to_one(self):
        total = sum(config.DUEL_BOOSTER_REWARD_PROBABILITIES.values())
        assert abs(total - 1.0) < 1e-6

    def test_duel_booster_reward_probabilities_keys(self):
        assert 'main' in config.DUEL_BOOSTER_REWARD_PROBABILITIES
        assert 'side' in config.DUEL_BOOSTER_REWARD_PROBABILITIES

    def test_key_card_ranks(self):
        assert set(config.KEY_CARD_RANKS) == {
            'J', 'Q', 'K', 'A', '2', '4', '5'}

    def test_booster_rarity_assignments_and_per_rank_probabilities(self):
        assert config.BOOSTER_TIER_RANKS == {
            1: ['7', '8', '9'],
            2: ['J', 'Q', '10'],
            3: ['K', 'A'],
        }
        assert config.BOOSTER_SIDE_TIER_RANKS == {
            1: ['3'],
            2: ['2', '6'],
            3: ['4', '5'],
        }

        def per_rank(probabilities, ranks, tier):
            return probabilities[tier] / len(ranks[tier])

        main = [
            per_rank(
                config.BOOSTER_TIER_PROBABILITIES,
                config.BOOSTER_TIER_RANKS,
                tier,
            )
            for tier in (1, 2, 3)
        ]
        side = [
            per_rank(
                config.BOOSTER_SIDE_TIER_PROBABILITIES,
                config.BOOSTER_SIDE_TIER_RANKS,
                tier,
            )
            for tier in (1, 2, 3)
        ]
        assert main[0] > main[1] > main[2]
        assert side[0] > side[1] > side[2]

    def test_kingdom_map_dimensions(self):
        assert config.KINGDOM_MAP_COLS > 0
        assert config.KINGDOM_MAP_ROWS > 0

    def test_land_tier_probabilities_sum_to_one(self):
        total = sum(config.LAND_TIER_PROBABILITIES.values())
        assert abs(total - 1.0) < 1e-6

    def test_land_gold_rate_ranges_valid(self):
        for tier, (lo, hi) in config.LAND_GOLD_RATE_RANGES.items():
            assert lo > 0
            assert hi >= lo

    def test_land_suit_bonus_ranges_valid(self):
        for tier, (lo, hi) in config.LAND_SUIT_BONUS_RANGES.items():
            assert lo > 0
            assert hi >= lo

    def test_conquer_cooldown_positive(self):
        assert config.CONQUER_COOLDOWN_SECONDS > 0

    def test_land_conquer_protection_nonnegative(self):
        assert config.LAND_CONQUER_PROTECTION_SECONDS >= 0

    def test_ai_defence_generation_rules_all_tiers(self):
        for tier in (1, 2, 3, 4):
            assert tier in ai_defence_config.AI_DEFENCE_GENERATION_RULES

    def test_ai_defence_generation_rule_structure(self):
        for rules in ai_defence_config.AI_DEFENCE_GENERATION_RULES.values():
            assert rules['core_roles']
            assert len(rules['optional_count_range']) == 2
            assert rules['number_ranks']
            assert rules['battle_plan']
