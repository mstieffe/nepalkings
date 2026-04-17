# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for v2.0 server settings validity."""
import server_settings as config


class TestV2ServerSettings:
    def test_booster_pack_constants(self):
        assert config.STARTER_BOOSTER_PACKS >= 0
        assert config.BOOSTER_PACK_PRICE > 0
        assert config.BOOSTER_PACK_CARDS > 0
        assert config.DUEL_WINNER_BOOSTER_PACKS >= 0
        assert config.DUEL_LOSER_BOOSTER_PACKS >= 0

    def test_booster_tier_probabilities_sum_to_one(self):
        total = sum(config.BOOSTER_TIER_PROBABILITIES.values())
        assert abs(total - 1.0) < 1e-6

    def test_booster_tier_ranks_nonempty(self):
        for tier, ranks in config.BOOSTER_TIER_RANKS.items():
            assert len(ranks) > 0, f"Tier {tier} has no ranks"

    def test_key_card_ranks(self):
        assert 'J' in config.KEY_CARD_RANKS
        assert 'Q' in config.KEY_CARD_RANKS
        assert 'K' in config.KEY_CARD_RANKS
        assert 'A' in config.KEY_CARD_RANKS

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

    def test_ai_defence_templates_all_tiers(self):
        for tier in (1, 2, 3):
            assert tier in config.AI_DEFENCE_TEMPLATES
            assert len(config.AI_DEFENCE_TEMPLATES[tier]) > 0

    def test_ai_defence_template_structure(self):
        for tier, templates in config.AI_DEFENCE_TEMPLATES.items():
            for tmpl in templates:
                assert 'figures' in tmpl
                assert 'battle_moves' in tmpl
                assert len(tmpl['battle_moves']) == 3
                for fig in tmpl['figures']:
                    assert 'family_name' in fig
                    assert 'cards' in fig
                for move in tmpl['battle_moves']:
                    assert 'family_name' in move
                    assert 'round_index' in move
