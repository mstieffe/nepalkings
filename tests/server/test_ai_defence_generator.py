# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for generated AI land defence templates."""

from types import SimpleNamespace

from ai.defence.config import (
    AI_DEFENCE_BLACK_SUITS,
    AI_DEFENCE_FIGURE_CATALOG,
    AI_DEFENCE_GENERATION_RULES,
    AI_DEFENCE_RED_SUITS,
    AI_DEFENCE_SUITS,
)
from ai.defence.generator import (
    get_ai_defence_name_for_land,
    get_ai_defence_template_for_land,
    template_resource_deficit_map,
    validate_ai_defence_template,
)
from ai.figure_recipes import FAMILY_SKILLS
from game_service.figure_rule_helpers import battle_required_field


def _land(tier=1, suit='Hearts', seed=123, land_id=1, col=4, row=5):
    return SimpleNamespace(
        id=land_id,
        col=col,
        row=row,
        tier=tier,
        suit_bonus_suit=suit,
        suit_bonus_value=2 * tier,
        ai_template_index=seed,
    )


def _color_group(suit):
    return 'red' if suit in AI_DEFENCE_RED_SUITS else 'black'


def _has_opposite_color_figure(template, primary_suit):
    primary_color = _color_group(primary_suit)
    return any(_color_group(fig['suit']) != primary_color for fig in template['figures'])


def _has_fortress(template):
    return any(
        fig['family_name'] in {'Wooden Fortress', 'Stone Fortress'}
        for fig in template['figures']
    )


def _can_counter_advance(figure):
    skills = FAMILY_SKILLS.get(figure.get('family_name')) or {}
    return not (
        figure.get('cannot_attack')
        or figure.get('cannot_defend')
        or skills.get('cannot_attack')
        or skills.get('cannot_defend')
    )


class TestAiDefenceGenerator:
    def test_rules_cover_all_kingdom_tiers(self):
        assert set(AI_DEFENCE_GENERATION_RULES) == {1, 2, 3, 4, 5, 6}

    def test_all_catalog_roles_are_reachable_from_rules(self):
        configured_roles = set(AI_DEFENCE_FIGURE_CATALOG)
        referenced_roles = set()
        for rules in AI_DEFENCE_GENERATION_RULES.values():
            referenced_roles.update(rules.get('core_roles') or [])
            referenced_roles.update(role for role, _ in (rules.get('optional_role_weights') or []))
        assert configured_roles <= referenced_roles

    def test_generated_templates_are_structurally_valid_for_all_tiers_and_suits(self):
        for tier in (1, 2, 3, 4, 5, 6):
            for suit in AI_DEFENCE_SUITS:
                template = get_ai_defence_template_for_land(_land(tier=tier, suit=suit))
                assert validate_ai_defence_template(template)
                assert len(template['battle_moves']) == 3
                assert template['figures']

    def test_high_tier_templates_include_side_card_figures(self):
        # Side-card-producing roles (manufactory/healer/temple/material/archer/
        # wall_cavalry) are stochastic in optional draws; sample several seeds.
        for tier in (2, 3, 4, 5, 6):
            saw_side_card = False
            for seed in range(30):
                template = get_ai_defence_template_for_land(
                    _land(tier=tier, suit='Hearts', seed=seed, land_id=4000 + seed)
                )
                has_side_card = any(
                    card.get('card_type') == 'side'
                    for fig in template['figures']
                    for card in fig.get('cards') or []
                )
                if has_side_card:
                    saw_side_card = True
                    break
            assert saw_side_card, f'tier={tier} produced no side-card figure in 30 seeds'

    def test_generated_templates_include_scripted_spells(self):
        # Spells are now drawn from weighted pools, including a None entry at
        # low tiers. T6 is configured without a None weight, so prelude and
        # counter must always be set there.
        for tier in (1, 2, 3, 4, 5, 6):
            template = get_ai_defence_template_for_land(_land(tier=tier, suit='Spades'))
            if template['prelude_spell_name']:
                assert isinstance(template['prelude_spell_data'], dict)
            if template['counter_spell_name']:
                assert isinstance(template['counter_spell_data'], dict)
        for suit in AI_DEFENCE_SUITS:
            template = get_ai_defence_template_for_land(_land(tier=6, suit=suit, seed=7))
            assert template['prelude_spell_name']
            assert template['counter_spell_name']

    def test_spell_pools_produce_variety_across_seeds(self):
        # Every configured spell (and the None sentinel where present) should
        # appear at least once across a handful of seeds for each tier.
        from ai.defence.config import AI_DEFENCE_GENERATION_RULES
        for tier in (1, 2, 3, 4, 5, 6):
            rules = AI_DEFENCE_GENERATION_RULES[tier]
            for key in ('prelude', 'counter'):
                expected = set()
                for entry in rules.get(f'{key}_spell_weights') or []:
                    name = entry[0]
                    if isinstance(name, str) and name.strip().lower() == 'none':
                        name = None
                    expected.add(name)
                seen = set()
                for seed in range(500):
                    template = get_ai_defence_template_for_land(
                        _land(tier=tier, suit='Hearts', seed=seed, land_id=3000 + seed)
                    )
                    seen.add(template[f'{key}_spell_name'])
                missing = expected - seen
                assert not missing, (
                    f'tier={tier} key={key} never produced spells: {missing}'
                )

    def test_generated_templates_have_no_resource_deficits(self):
        for tier in (1, 2, 3, 4, 5, 6):
            for suit in AI_DEFENCE_SUITS:
                template = get_ai_defence_template_for_land(_land(tier=tier, suit=suit))
                assert not any(template_resource_deficit_map(template['figures']).values())

    def test_generated_templates_always_have_legal_castle_and_village_defenders(self):
        for tier in (1, 2, 3, 4, 5, 6):
            for suit in AI_DEFENCE_SUITS:
                for seed in range(200):
                    template = get_ai_defence_template_for_land(
                        _land(
                            tier=tier,
                            suit=suit,
                            seed=seed,
                            land_id=8000 + tier * 1000 + seed,
                        )
                    )
                    assert not template['ai_name'].startswith('Fallback')
                    deficits = template_resource_deficit_map(template['figures'])
                    for required_field in ('castle', 'village'):
                        assert any(
                            figure['field'] == required_field
                            and not deficits[index]
                            and _can_counter_advance(figure)
                            for index, figure in enumerate(template['figures'])
                        ), (tier, suit, seed, required_field, template)

    def test_neutral_support_chain_does_not_collapse_to_fallback(self):
        # Regression for a tier-2 neutral land whose elite military draw
        # needs both food and armor providers. Those providers can exceed the
        # tier's villager capacity; repair must prune the optional deficit
        # figure instead of discarding the guaranteed farm or falling back.
        land = SimpleNamespace(
            id=4406,
            col=85,
            row=45,
            tier=2,
            suit_bonus_suit='Neutral',
            suit_bonus_value=0,
            ai_template_index=147709450,
        )

        template = get_ai_defence_template_for_land(land)

        assert not template['ai_name'].startswith('Fallback')
        assert validate_ai_defence_template(template)

    def test_battle_figure_obeys_prelude_and_figure_skill_legality(self):
        for tier in (1, 2, 3, 4, 5, 6):
            for suit in AI_DEFENCE_SUITS:
                for seed in range(200):
                    template = get_ai_defence_template_for_land(
                        _land(
                            tier=tier,
                            suit=suit,
                            seed=seed,
                            land_id=16000 + tier * 1000 + seed,
                        )
                    )
                    battle_idx = template['battle_figure_index']
                    battle_figure = template['figures'][battle_idx]
                    required_field = battle_required_field([{
                        'type': template['prelude_spell_name'],
                    }])
                    assert not template_resource_deficit_map(
                        template['figures'])[battle_idx]
                    assert _can_counter_advance(battle_figure)
                    if required_field:
                        assert battle_figure['field'] == required_field

    def test_validator_rejects_castle_only_peasant_war_template(self):
        template = get_ai_defence_template_for_land(_land())
        template['figures'] = [template['figures'][0]]
        template['battle_figure_index'] = 0
        template['prelude_spell_name'] = 'Peasant War'

        assert not validate_ai_defence_template(template)

    def test_validator_rejects_figure_that_cannot_counter_advance(self):
        template = get_ai_defence_template_for_land(_land(tier=3))
        fortress_idx = next(
            (
                index
                for index, figure in enumerate(template['figures'])
                if (FAMILY_SKILLS.get(figure['family_name']) or {}).get('cannot_attack')
            ),
            None,
        )
        if fortress_idx is None:
            fortress = dict(template['figures'][template['battle_figure_index']])
            fortress['cannot_attack'] = True
            template['figures'].append(fortress)
            fortress_idx = len(template['figures']) - 1
        template['prelude_spell_name'] = None
        template['battle_figure_index'] = fortress_idx

        assert not validate_ai_defence_template(template)

    def test_generation_is_deterministic_for_same_land(self):
        land = _land(tier=4, suit='Spades', seed=98765, land_id=44, col=8, row=9)
        assert get_ai_defence_template_for_land(land) == get_ai_defence_template_for_land(land)

    def test_lightweight_name_matches_full_template_name(self):
        for tier in (1, 2, 3, 4, 5, 6):
            for suit in (*AI_DEFENCE_SUITS, 'Neutral'):
                land = _land(tier=tier, suit=suit, seed=42, land_id=7000 + tier)
                assert get_ai_defence_name_for_land(land) == (
                    get_ai_defence_template_for_land(land)['ai_name']
                )

    def test_generation_varies_with_land_seed(self):
        first = get_ai_defence_template_for_land(
            _land(tier=4, suit='Spades', seed=1, land_id=44)
        )
        second = get_ai_defence_template_for_land(
            _land(tier=4, suit='Spades', seed=2, land_id=44)
        )
        assert first != second

    def test_high_tier_templates_are_tailored_to_land_suit(self):
        for tier in (3, 4, 5, 6):
            for suit in AI_DEFENCE_SUITS:
                template = get_ai_defence_template_for_land(_land(tier=tier, suit=suit))
                battle_figure = template['figures'][template['battle_figure_index']]
                assert battle_figure['suit'] == suit
                assert any(move['suit'] == suit for move in template['battle_moves'])

    def test_templates_keep_land_suit_anchor_while_allowing_cross_color_figures(self):
        # Tier 1 caps castle figures at 1 and has no producer for the opposite
        # color's resources, so cross-color figures are intentionally
        # infeasible at tier 1.  Cross-color emerges from tier 2 onwards via
        # extra castle slots and feasible optional draws.
        for tier in (2, 3, 4, 5, 6):
            for suit in AI_DEFENCE_SUITS:
                saw_cross_color = False
                for seed in range(120):
                    template = get_ai_defence_template_for_land(
                        _land(tier=tier, suit=suit, seed=seed, land_id=1000 + seed)
                    )
                    assert any(fig['suit'] == suit for fig in template['figures'])
                    assert any(move['suit'] == suit for move in template['battle_moves'])
                    saw_cross_color = saw_cross_color or _has_opposite_color_figure(template, suit)
                assert saw_cross_color, f'tier={tier} suit={suit} produced no cross-color figure'

    def test_black_suit_templates_can_be_fortress_free_at_every_tier(self):
        # Tier 1 cannot host a red-suit military figure (Gorkha) on a black
        # land because the lone black king cannot pay for red warriors;
        # fortress-free Gorkha emergence is only feasible from tier 2 up.
        for tier in (2, 3, 4, 5, 6):
            for suit in AI_DEFENCE_BLACK_SUITS:
                saw_fortress = False
                saw_fortress_free = False
                saw_gorkha_on_black_land = False
                for seed in range(260):
                    template = get_ai_defence_template_for_land(
                        _land(tier=tier, suit=suit, seed=seed, land_id=2000 + seed)
                    )
                    saw_fortress = saw_fortress or _has_fortress(template)
                    if not _has_fortress(template):
                        saw_fortress_free = True
                        saw_gorkha_on_black_land = saw_gorkha_on_black_land or any(
                            fig['family_name'] in {'Gorkha Warriors', 'Elite Gorkha Warriors'}
                            for fig in template['figures']
                        )
                assert saw_fortress
                assert saw_fortress_free
                assert saw_gorkha_on_black_land

    def test_call_moves_only_reference_available_fields(self):
        call_field = {
            'Call King': 'castle',
            'Call Military': 'military',
            'Call Villager': 'village',
        }
        for tier in (1, 2, 3, 4, 5, 6):
            template = get_ai_defence_template_for_land(_land(tier=tier, suit='Diamonds'))
            fields = {fig['field'] for fig in template['figures']}
            for move in template['battle_moves']:
                if move['family_name'] in call_field:
                    assert call_field[move['family_name']] in fields

    def test_neutral_lands_still_generate_valid_templates(self):
        template = get_ai_defence_template_for_land(_land(tier=2, suit='Neutral'))
        assert validate_ai_defence_template(template)
        assert not any(template_resource_deficit_map(template['figures']).values())
