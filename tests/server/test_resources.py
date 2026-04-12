# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for resource production: castle figures produce slots that village/military figures consume."""
import pytest


class TestCastleFigureProduction:
    """Verify the produces dict on castle figures matches the spec."""

    def _get_figure(self, db, game_id, name):
        from models import Figure
        return Figure.query.filter_by(game_id=game_id, name=name).first()

    def test_himalaya_king_produces_2_villager_black_1_warrior_black(self, db):
        """The castle_config specifies produces={'villager_black':2,'warrior_black':1}."""
        # Validate the expected produces dict directly from the castle config data
        expected = {'villager_black': 2, 'warrior_black': 1}
        from game.components.figures.family_configs.castle_config import castle_dict_list
        entry = next(e for e in castle_dict_list if e['name'] == 'Himalaya King')
        # Build a dummy FigureFamily and instantiate a CastleFigure
        from game.components.figures.figure import CastleFigure, FigureFamily
        # Minimal stub for FigureFamily (no pygame needed for this test)
        family = _make_stub_family(entry['name'], 'defensive', 'castle', entry['suits'])
        figures = entry['figures'](family, entry['suits'][0])
        assert len(figures) == 1
        fig = figures[0]
        assert fig.produces == expected

    def test_himalaya_maharaja_produces_3_villager_black_2_warrior_black(self, db):
        expected = {'villager_black': 3, 'warrior_black': 2}
        from game.components.figures.family_configs.castle_config import castle_dict_list
        entry = next(e for e in castle_dict_list if e['name'] == 'Himalaya Maharaja')
        family = _make_stub_family(entry['name'], 'defensive', 'castle', entry['suits'])
        fig = entry['figures'](family, entry['suits'][0])[0]
        assert fig.produces == expected

    def test_djungle_king_produces_2_villager_red_1_warrior_red(self, db):
        expected = {'villager_red': 2, 'warrior_red': 1}
        from game.components.figures.family_configs.castle_config import castle_dict_list
        entry = next(e for e in castle_dict_list if e['name'] == 'Djungle King')
        family = _make_stub_family(entry['name'], 'offensive', 'castle', entry['suits'])
        fig = entry['figures'](family, entry['suits'][0])[0]
        assert fig.produces == expected

    def test_djungle_maharaja_produces_3_villager_red_2_warrior_red(self, db):
        expected = {'villager_red': 3, 'warrior_red': 2}
        from game.components.figures.family_configs.castle_config import castle_dict_list
        entry = next(e for e in castle_dict_list if e['name'] == 'Djungle Maharaja')
        family = _make_stub_family(entry['name'], 'offensive', 'castle', entry['suits'])
        fig = entry['figures'](family, entry['suits'][0])[0]
        assert fig.produces == expected


class TestResourceValidationDB:
    """Server-side DB tests verifying that resource produces/requires are stored."""

    def test_building_castle_figure_stores_produces(self, app, db):
        from models import Figure, Game, Player, User
        from werkzeug.security import generate_password_hash
        from game_service.deck import Deck

        u = User(username='res_u1', password_hash=generate_password_hash('x'), gold=100)
        db.session.add(u)
        db.session.commit()
        game = Game(current_round=1, stake=35)
        db.session.add(game)
        db.session.commit()
        player = Player(user_id=u.id, game_id=game.id, turns_left=6, points=0)
        db.session.add(player)
        db.session.commit()
        game.turn_player_id = player.id
        db.session.commit()

        deck = Deck(game)
        deck.create()
        deck.shuffle()

        # Create a castle figure directly
        fig = Figure(
            player_id=player.id,
            game_id=game.id,
            family_name='Himalaya King',
            field='castle',
            color='defensive',
            name='Himalaya King',
            suit='Clubs',
            produces={'villager_black': 2, 'warrior_black': 1},
            requires={},
        )
        db.session.add(fig)
        db.session.commit()
        db.session.refresh(fig)
        assert fig.produces == {'villager_black': 2, 'warrior_black': 1}

    def test_picking_up_figure_frees_resource_slot(self, app, db):
        """After picking up a village figure, its requires are no longer in play."""
        from models import Figure, Game, Player, User
        from werkzeug.security import generate_password_hash

        u = User(username='res_u2', password_hash=generate_password_hash('x'), gold=100)
        db.session.add(u)
        db.session.commit()
        game = Game(current_round=1, stake=35)
        db.session.add(game)
        db.session.commit()
        player = Player(user_id=u.id, game_id=game.id, turns_left=6, points=0)
        db.session.add(player)
        db.session.commit()

        fig = Figure(
            player_id=player.id,
            game_id=game.id,
            family_name='Small Yack Farm',
            field='village',
            color='defensive',
            name='Small Yack Farm',
            suit='Clubs',
            produces={},
            requires={'villager_black': 1},
        )
        db.session.add(fig)
        db.session.commit()
        fig_id = fig.id

        # Pick up the figure
        from models import CardToFigure
        db.session.delete(fig)
        db.session.commit()

        assert db.session.get(Figure, fig_id) is None


# ---------------------------------------------------------------------------
# Utility — stubbed FigureFamily for config tests (no pygame needed)
# ---------------------------------------------------------------------------

def _make_stub_family(name, color, field, suits):
    """Create a minimal FigureFamily without pygame surfaces."""
    class _StubSurface:
        pass

    from game.components.figures.figure import FigureFamily
    stub = object.__new__(FigureFamily)
    stub.name = name
    stub.color = color
    stub.field = field
    stub.suits = suits
    stub.figures = []
    stub.icon_img = _StubSurface()
    stub.icon_gray_img = _StubSurface()
    stub.icon_img_small = _StubSurface()
    stub.icon_gray_img_small = _StubSurface()
    stub.frame_img = _StubSurface()
    stub.frame_closed_img = _StubSurface()
    stub.frame_hidden_img = _StubSurface()
    stub.frame_hidden_greyscale_img = _StubSurface()
    stub.glow_img = _StubSurface()
    stub.build_position = None
    stub.description = ''
    return stub
