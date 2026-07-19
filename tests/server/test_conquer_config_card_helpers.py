# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for Conquer configuration-card helpers."""

import importlib
import inspect
from types import SimpleNamespace


games = importlib.import_module('routes.games')


def _make_collection_card(db, user_id, *, suit, rank, value):
    from models import CollectionCard

    card = CollectionCard(
        user_id=user_id,
        suit=suit,
        rank=rank,
        value=value,
        locked=True,
        lock_type='conquer_figure',
    )
    db.session.add(card)
    db.session.flush()
    return card


def _make_config_figure(db, config_id, card_ids, *, name):
    from models import LandConfigFigure

    figure = LandConfigFigure(
        config_id=config_id,
        family_name='Villager',
        name=name,
        suit='Hearts',
        color='offensive',
        field='village',
        card_ids=card_ids,
        card_roles=['key'] * len(card_ids),
        produces={},
        requires={},
    )
    db.session.add(figure)
    db.session.flush()
    return figure


def test_conquer_config_card_helper_route_api_is_stable():
    expected_signatures = {
        '_snapshot_collection_cards': '(card_ids, include_id=False)',
        '_snapshot_config_battle_cards': '(cfg, include_id=False)',
        '_consume_config_figure_cards': '(cfg, exclude_card_ids=None)',
    }

    for name, expected_signature in expected_signatures.items():
        helper = getattr(games, name)
        assert str(inspect.signature(helper)) == expected_signature
        assert helper.__module__ == 'routes.games'


def test_snapshot_collection_cards_deduplicates_and_preserves_requested_order(
    db,
    two_users,
):
    user, _ = two_users
    first = _make_collection_card(
        db,
        user.id,
        suit='Hearts',
        rank='K',
        value=4,
    )
    second = _make_collection_card(
        db,
        user.id,
        suit='Spades',
        rank='A',
        value=11,
    )
    db.session.commit()

    snapshot = games._snapshot_collection_cards(
        [second.id, None, first.id, second.id, 0, 999999],
    )

    assert snapshot == [
        {'suit': 'Spades', 'rank': 'A'},
        {'suit': 'Hearts', 'rank': 'K'},
    ]


def test_snapshot_collection_cards_optionally_includes_database_ids(
    db,
    two_users,
):
    user, _ = two_users
    card = _make_collection_card(
        db,
        user.id,
        suit='Diamonds',
        rank='Q',
        value=2,
    )
    db.session.commit()

    assert games._snapshot_collection_cards([card.id], include_id=True) == [
        {'suit': 'Diamonds', 'rank': 'Q', 'id': card.id}
    ]


def test_snapshot_collection_cards_returns_empty_for_falsey_input():
    assert games._snapshot_collection_cards(None) == []
    assert games._snapshot_collection_cards([]) == []
    assert games._snapshot_collection_cards([None, 0]) == []


def test_snapshot_config_battle_cards_uses_route_helpers(monkeypatch):
    cfg = SimpleNamespace(id=17)
    calls = []
    monkeypatch.setattr(
        games,
        '_config_battle_card_ids',
        lambda value: calls.append(('ids', value)) or [4, 8],
    )
    monkeypatch.setattr(
        games,
        '_snapshot_collection_cards',
        lambda card_ids, include_id=False: (
            calls.append(('snapshot', card_ids, include_id))
            or [{'card_ids': card_ids, 'include_id': include_id}]
        ),
    )

    result = games._snapshot_config_battle_cards(cfg, include_id=True)

    assert result == [{'card_ids': [4, 8], 'include_id': True}]
    assert calls == [
        ('ids', cfg),
        ('snapshot', [4, 8], True),
    ]


def test_consume_config_figure_cards_deletes_figures_and_nonexcluded_cards(
    db,
    two_users,
):
    from models import CollectionCard, LandConfig, LandConfigFigure

    user, _ = two_users
    cfg = LandConfig(user_id=user.id, config_type='conquer')
    db.session.add(cfg)
    db.session.flush()
    consumed_first = _make_collection_card(
        db,
        user.id,
        suit='Hearts',
        rank='J',
        value=1,
    )
    excluded = _make_collection_card(
        db,
        user.id,
        suit='Clubs',
        rank='9',
        value=9,
    )
    consumed_second = _make_collection_card(
        db,
        user.id,
        suit='Spades',
        rank='8',
        value=8,
    )
    first_figure = _make_config_figure(
        db,
        cfg.id,
        [consumed_first.id, excluded.id],
        name='First',
    )
    second_figure = _make_config_figure(
        db,
        cfg.id,
        [excluded.id, consumed_second.id],
        name='Second',
    )
    db.session.commit()
    config_id = cfg.id
    figure_ids = [first_figure.id, second_figure.id]
    consumed_ids = [consumed_first.id, consumed_second.id]
    excluded_id = excluded.id

    result = games._consume_config_figure_cards(
        cfg,
        exclude_card_ids=[excluded_id],
    )
    db.session.flush()

    assert result is None
    for card_id in consumed_ids:
        assert db.session.get(CollectionCard, card_id) is None
    assert db.session.get(CollectionCard, excluded_id) is excluded
    for figure_id in figure_ids:
        assert db.session.get(LandConfigFigure, figure_id) is None
    assert LandConfigFigure.query.filter_by(config_id=config_id).count() == 0
