# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for conquer loot helper boundaries."""

import importlib
import pickle
from types import SimpleNamespace


class TestNormaliseLootCard:
    def test_ai_config_reexports_neutral_rank_values(self):
        from ai.defence.config import AI_DEFENCE_RANK_VALUES as ai_values
        from game_service.card_values import AI_DEFENCE_RANK_VALUES as shared_values

        assert ai_values is shared_values

    def test_route_reexports_canonical_loot_helper(self):
        from game_service.conquer_loot import _normalise_loot_card as canonical
        from routes.games import _normalise_loot_card as legacy

        assert legacy is canonical
        assert canonical.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical)) is canonical

    def test_rejects_falsy_or_incomplete_cards(self):
        from routes.games import _normalise_loot_card

        assert _normalise_loot_card(None, source='figure') is None
        assert _normalise_loot_card({}, source='figure') is None
        assert _normalise_loot_card(
            {'rank': 'A'},
            source='figure',
        ) is None
        assert _normalise_loot_card(
            {'suit': 'Spades'},
            source='figure',
        ) is None

    def test_normalises_dict_and_honours_role_and_id_overrides(self):
        from routes.games import _normalise_loot_card

        result = _normalise_loot_card(
            {
                'id': 7,
                'suit': 'Hearts',
                'rank': 'K',
                'value': '9',
                'role': 'support',
            },
            source='figure',
            role=SimpleNamespace(value='override'),
            card_id=99,
        )

        assert result == {
            'id': 99,
            'suit': 'Hearts',
            'rank': 'K',
            'value': 9,
            'role': 'override',
            'source': 'figure',
            'bucket': 'key',
        }

    def test_normalises_object_with_rank_value_and_source_role_fallbacks(self):
        from routes.games import _normalise_loot_card

        result = _normalise_loot_card(
            SimpleNamespace(
                id=44,
                suit='Spades',
                rank='A',
                value=None,
            ),
            source='battle_move',
        )

        assert result == {
            'id': 44,
            'suit': 'Spades',
            'rank': 'A',
            'value': 3,
            'role': 'battle_move',
            'source': 'battle_move',
            'bucket': 'key',
        }


class TestSnapshotConfigLootCards:
    def test_route_reexports_canonical_loot_helper(self):
        from game_service.conquer_loot import (
            _snapshot_config_loot_cards as canonical,
        )
        from routes.games import _snapshot_config_loot_cards as legacy

        assert legacy is canonical
        assert canonical.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical)) is canonical

    def test_none_config_returns_empty_list(self):
        from routes.games import _snapshot_config_loot_cards

        assert _snapshot_config_loot_cards(None) == []

    def test_snapshots_all_sources_in_order_and_suppresses_duplicate_ids(
            self, app, db, two_users):
        from models import (
            CollectionCard,
            LandConfig,
            LandConfigBattleMove,
            LandConfigFigure,
        )
        from routes.games import _snapshot_config_loot_cards

        user, _ = two_users
        cfg = LandConfig(user_id=user.id, config_type='conquer')
        db.session.add(cfg)
        db.session.flush()

        def card(rank, value):
            row = CollectionCard(
                user_id=user.id,
                suit='Spades',
                rank=rank,
                value=value,
            )
            db.session.add(row)
            db.session.flush()
            return row

        figure_key = card('A', 11)
        figure_number = card('7', 7)
        move = card('8', 8)
        modifier = card('2', 2)
        spell = card('3', 3)
        prelude = card('4', 4)
        counter = card('5', 5)
        db.session.add(LandConfigFigure(
            config_id=cfg.id,
            family_name='F',
            name='F',
            suit='Spades',
            color='offensive',
            field='village',
            card_ids=[figure_key.id, figure_number.id],
            card_roles=['key', 'number'],
        ))
        db.session.add(LandConfigBattleMove(
            config_id=cfg.id,
            family_name='Dagger',
            card_id=move.id,
            suit='Spades',
            rank='8',
            value=8,
            round_index=0,
        ))
        cfg.modifier_card_ids = [figure_key.id, modifier.id]
        cfg.spell_card_ids = [spell.id]
        cfg.prelude_spell_card_ids = [prelude.id]
        cfg.counter_spell_card_ids = [counter.id]
        db.session.commit()

        result = _snapshot_config_loot_cards(cfg)

        assert [
            (row['id'], row['source'], row['role'], row['bucket'])
            for row in result
        ] == [
            (figure_key.id, 'figure', 'key', 'key'),
            (figure_number.id, 'figure', 'number', 'number'),
            (move.id, 'battle_move', 'battle_move', 'number'),
            (modifier.id, 'modifier', 'modifier', 'key'),
            (spell.id, 'spell', 'spell', 'number'),
            (prelude.id, 'prelude_spell', 'prelude_spell', 'key'),
            (counter.id, 'counter_spell', 'counter_spell', 'key'),
        ]
        assert result[0]['suit'] == 'Spades'
        assert result[0]['rank'] == 'A'
        assert result[0]['value'] == 11


class TestSnapshotTemplateLootCards:
    def test_route_reexports_canonical_loot_helper(self):
        from game_service.conquer_loot import (
            _snapshot_template_loot_cards as canonical,
        )
        from routes.games import _snapshot_template_loot_cards as legacy

        assert legacy is canonical
        assert canonical.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical)) is canonical

    def test_none_template_returns_empty_list(self):
        from routes.games import _snapshot_template_loot_cards

        assert _snapshot_template_loot_cards(None) == []

    def test_preserves_figure_then_move_order_and_role_precedence(self):
        from routes.games import _snapshot_template_loot_cards

        template = {
            'figures': [
                {
                    'card_roles': ['fallback-key', 'fallback-number'],
                    'cards': [
                        {
                            'suit': 'Hearts',
                            'rank': 'A',
                            'value': 3,
                            'role': 'explicit-key',
                        },
                        {
                            'suit': 'Diamonds',
                            'rank': '7',
                            'value': 7,
                        },
                        'invalid-card',
                        {'suit': 'Clubs'},
                    ],
                },
            ],
            'battle_moves': [
                {'suit': 'Spades', 'rank': '8', 'value': 8},
                {'rank': '9', 'value': 9},
            ],
        }

        result = _snapshot_template_loot_cards(template)

        assert [
            (
                row['suit'],
                row['rank'],
                row['source'],
                row['role'],
                row['bucket'],
            )
            for row in result
        ] == [
            ('Hearts', 'A', 'figure', 'explicit-key', 'key'),
            ('Diamonds', '7', 'figure', 'fallback-number', 'number'),
            ('Spades', '8', 'battle_move', 'battle_move', 'number'),
        ]


class TestLootCardBucket:
    def test_route_reexports_canonical_loot_helper(self):
        from game_service.conquer_loot import _loot_card_bucket as canonical_helper
        from routes.games import _loot_card_bucket as legacy_helper

        assert legacy_helper is canonical_helper
        assert canonical_helper.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical_helper)) is canonical_helper

    def test_classifies_known_trimmed_numeric_and_unknown_ranks(self):
        from routes.games import _loot_card_bucket

        assert _loot_card_bucket('A') == 'key'
        assert _loot_card_bucket('  K ') == 'key'
        assert _loot_card_bucket(2) == 'key'
        assert _loot_card_bucket('10') == 'number'
        assert _loot_card_bucket(7) == 'number'
        assert _loot_card_bucket(None) == 'number'
        assert _loot_card_bucket('unknown') == 'number'
        assert _loot_card_bucket('a') == 'number'


class TestDeleteLootedCollectionCards:
    def test_route_reexports_canonical_loot_helper(self):
        from game_service.conquer_loot import (
            _delete_looted_collection_cards as canonical_helper,
        )
        from routes.games import _delete_looted_collection_cards as legacy_helper

        assert legacy_helper is canonical_helper
        assert canonical_helper.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical_helper)) is canonical_helper

    def test_none_or_empty_cards_are_noops(self):
        from routes.games import _delete_looted_collection_cards

        assert _delete_looted_collection_cards(None) is None
        assert _delete_looted_collection_cards([]) is None

    def test_deletes_only_cards_with_listed_ids(self, app, db, two_users):
        from models import CollectionCard
        from routes.games import _delete_looted_collection_cards

        user, _ = two_users
        deleted_a = CollectionCard(
            user_id=user.id, suit='spades', rank='A', value=11)
        deleted_b = CollectionCard(
            user_id=user.id, suit='hearts', rank='K', value=10)
        retained = CollectionCard(
            user_id=user.id, suit='clubs', rank='Q', value=10)
        db.session.add_all([deleted_a, deleted_b, retained])
        db.session.commit()
        deleted_ids = [deleted_a.id, deleted_b.id]
        retained_id = retained.id

        _delete_looted_collection_cards([
            {'id': deleted_a.id},
            {'id': deleted_b.id},
            {'id': deleted_a.id},
            {'suit': 'diamonds', 'rank': 'J'},
        ])
        db.session.commit()

        for card_id in deleted_ids:
            assert db.session.get(CollectionCard, card_id) is None
        assert db.session.get(CollectionCard, retained_id) is not None


class TestConfigFigureKeyCardIds:
    def test_none_config_returns_empty_list(self):
        from routes.games import _config_figure_key_card_ids

        assert _config_figure_key_card_ids(None) == []

    def test_returns_case_insensitive_key_roles_in_figure_order(self):
        from routes.games import _config_figure_key_card_ids

        cfg = SimpleNamespace(figures=[
            SimpleNamespace(
                card_ids=[11, 12, 13],
                card_roles=['number', 'KEY'],
            ),
            SimpleNamespace(
                card_ids=[21, 22],
                card_roles=['key', None],
            ),
            SimpleNamespace(card_ids=None, card_roles=None),
        ])

        assert _config_figure_key_card_ids(cfg) == [12, 21]


class TestLootPolicyCompatibility:
    def test_route_reexports_canonical_policy_and_event_helpers(self):
        conquer_loot = importlib.import_module('game_service.conquer_loot')
        games = importlib.import_module('routes.games')

        names = (
            '_config_figure_key_card_ids',
            '_template_figure_key_cards',
            '_conquer_loot_base_quota',
            '_random_pick_without_replacement',
            '_select_conquer_loot_cards',
            '_loot_cards_public',
            '_create_kingdom_loot_events',
        )
        for name in names:
            canonical = getattr(conquer_loot, name)
            legacy = getattr(games, name)
            assert legacy is canonical
            assert canonical.__module__ == 'routes.games'
            assert pickle.loads(pickle.dumps(canonical)) is canonical


class TestTemplateFigureKeyCards:
    def test_finds_explicit_and_role_list_keys_without_copying_cards(self):
        from routes.games import _template_figure_key_cards

        explicit = {'suit': 'Spades', 'rank': 'A', 'role': 'KEY'}
        fallback = {'suit': 'Hearts', 'rank': 'K'}
        overridden = {'suit': 'Clubs', 'rank': 'Q', 'role': 'number'}
        template = {
            'figures': [{
                'cards': [explicit, fallback, overridden, 'invalid'],
                'card_roles': ['number', 'key', 'key', 'key'],
            }],
        }

        result = _template_figure_key_cards(template)

        assert result == [explicit, fallback]
        assert result[0] is explicit
        assert result[1] is fallback

    def test_none_template_returns_empty_list(self):
        from routes.games import _template_figure_key_cards

        assert _template_figure_key_cards(None) == []


class TestConquerLootBaseQuota:
    def test_coerces_tier_and_enforces_minimum_one(self):
        from routes.games import _conquer_loot_base_quota

        assert _conquer_loot_base_quota(None) == (1, 1)
        assert _conquer_loot_base_quota(0) == (1, 1)
        assert _conquer_loot_base_quota(-4) == (1, 1)
        assert _conquer_loot_base_quota('3') == (3, 3)
        assert _conquer_loot_base_quota(2.8) == (2, 2)
        assert _conquer_loot_base_quota('invalid') == (1, 1)


class _FirstChoiceRng:
    def __init__(self, random_values=()):
        self._random_values = iter(random_values)

    def choice(self, values):
        return values[0]

    def random(self):
        return next(self._random_values)


class TestRandomPickWithoutReplacement:
    def test_selects_without_mutating_input_or_repeating_positions(self):
        from routes.games import _random_pick_without_replacement

        pool = ['first', 'second', 'third']

        assert _random_pick_without_replacement(
            pool, 2, _FirstChoiceRng()) == ['first', 'second']
        assert pool == ['first', 'second', 'third']
        assert _random_pick_without_replacement(
            pool, 99, _FirstChoiceRng()) == pool
        assert _random_pick_without_replacement(
            pool, -1, _FirstChoiceRng()) == []


class TestSelectConquerLootCards:
    def test_applies_independent_key_and_number_quotas(self):
        from routes.games import _select_conquer_loot_cards

        key_a = {'name': 'key-a', 'bucket': 'key'}
        number_a = {'name': 'number-a', 'bucket': 'number'}
        key_b = {'name': 'key-b', 'bucket': 'key'}
        number_b = {'name': 'number-b', 'bucket': 'number'}
        cards = [key_a, number_a, key_b, number_b]

        result = _select_conquer_loot_cards(
            cards,
            1,
            rng=_FirstChoiceRng(),
        )

        assert result == [key_a, number_a]
        assert cards == [key_a, number_a, key_b, number_b]

    def test_extra_chance_selects_remaining_cards_in_snapshot_order(self):
        from routes.games import _select_conquer_loot_cards

        key_a = {'name': 'key-a', 'bucket': 'key'}
        number_a = {'name': 'number-a', 'bucket': 'number'}
        key_b = {'name': 'key-b', 'bucket': 'key'}
        number_b = {'name': 'number-b', 'bucket': 'number'}

        result = _select_conquer_loot_cards(
            [key_a, number_a, key_b, number_b],
            1,
            extra_chance=1,
            rng=_FirstChoiceRng([0.0, 0.0]),
        )

        assert result == [key_a, number_a, key_b, number_b]

    def test_invalid_extra_chance_is_treated_as_zero(self):
        from routes.games import _select_conquer_loot_cards

        key_a = {'name': 'key-a', 'bucket': 'key'}
        key_b = {'name': 'key-b', 'bucket': 'key'}

        assert _select_conquer_loot_cards(
            [key_a, key_b],
            1,
            extra_chance='invalid',
            rng=_FirstChoiceRng(),
        ) == [key_a]


class TestLootCardsPublic:
    def test_strips_internal_fields_and_optionally_keeps_truthy_ids(self):
        from routes.games import _loot_cards_public

        cards = [
            {
                'id': 17,
                'suit': 'Spades',
                'rank': 'A',
                'value': '3',
                'role': 'key',
                'source': 'figure',
                'bucket': 'key',
                'internal': 'discard-me',
            },
            {
                'id': 0,
                'suit': 'Hearts',
                'rank': '7',
                'value': None,
            },
            'invalid',
        ]

        assert _loot_cards_public(cards, include_id=True) == [
            {
                'id': 17,
                'suit': 'Spades',
                'rank': 'A',
                'value': 3,
                'role': 'key',
                'source': 'figure',
                'bucket': 'key',
            },
            {
                'suit': 'Hearts',
                'rank': '7',
                'value': 0,
                'role': None,
                'source': None,
                'bucket': None,
            },
        ]
        assert 'id' not in _loot_cards_public(cards)[0]


class TestCreateKingdomLootEvents:
    def test_empty_cards_create_no_events(self, app, db, two_users):
        from models import KingdomLootEvent
        from routes.games import _create_kingdom_loot_events

        gained_user, lost_user = two_users

        assert _create_kingdom_loot_events(
            attack_log_id=None,
            land_id=None,
            gained_user_id=gained_user.id,
            lost_user_id=lost_user.id,
            cards=[],
        ) is None
        assert KingdomLootEvent.query.count() == 0

    def test_creates_mirrored_gain_and_loss_events(
            self, app, db, two_users):
        from models import KingdomLootEvent
        from routes.games import _create_kingdom_loot_events

        gained_user, lost_user = two_users
        cards = [{
            'id': 99,
            'suit': 'Spades',
            'rank': 'A',
            'value': '3',
            'role': 'key',
            'source': 'figure',
            'bucket': 'key',
            'internal': 'discard-me',
        }]

        result = _create_kingdom_loot_events(
            attack_log_id=None,
            land_id=None,
            gained_user_id=gained_user.id,
            lost_user_id=lost_user.id,
            gained_kingdom_id=101,
            lost_kingdom_id=202,
            source='attacker_win',
            cards=cards,
        )
        db.session.flush()

        events = KingdomLootEvent.query.order_by(
            KingdomLootEvent.direction
        ).all()
        assert result is None
        assert len(events) == 2
        gained = next(event for event in events if event.direction == 'gained')
        lost = next(event for event in events if event.direction == 'lost')
        expected_cards = [{
            'suit': 'Spades',
            'rank': 'A',
            'value': 3,
            'role': 'key',
            'source': 'figure',
            'bucket': 'key',
        }]
        assert gained.user_id == gained_user.id
        assert gained.kingdom_id == 101
        assert gained.counterparty_user_id == lost_user.id
        assert gained.cards == expected_cards
        assert gained.collected is False
        assert gained.seen is False
        assert lost.user_id == lost_user.id
        assert lost.kingdom_id == 202
        assert lost.counterparty_user_id == gained_user.id
        assert lost.cards == expected_cards
        assert lost.collected is True
        assert lost.seen is False
