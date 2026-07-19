# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for conquer loot helper boundaries."""

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
