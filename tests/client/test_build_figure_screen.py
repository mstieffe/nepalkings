# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for kingdom-mode figure building display filters."""

from types import SimpleNamespace


def _make_instant_charge_figure():
    family = SimpleNamespace(
        name='Gorkha Warriors',
        description=(
            'The Gorkha Warriors is an offensive military figure that charges instantly into battle '
            'when placed on the field. Requires food equal to its number-card value.'
        ),
        field='military',
    )
    return SimpleNamespace(
        name='Gorkha Warriors',
        description=family.description,
        family=family,
        instant_charge=True,
        checkmate=False,
    )


class TestBuildFigureScreenModeFiltering:
    def test_conquer_builder_hides_instant_advance_on_display_figure(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        screen = BuildFigureScreen.__new__(BuildFigureScreen)
        screen.mode = 'conquer'
        figure = _make_instant_charge_figure()

        display = BuildFigureScreen._display_figure_for_mode(screen, figure)

        assert display is not figure
        assert display.instant_charge is False
        assert 'charges instantly into battle' not in display.description.lower()
        assert 'charges instantly into battle' not in display.family.description.lower()

    def test_duel_builder_keeps_instant_advance_display_unchanged(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        screen = BuildFigureScreen.__new__(BuildFigureScreen)
        screen.mode = 'duel'
        figure = _make_instant_charge_figure()

        display = BuildFigureScreen._display_figure_for_mode(screen, figure)

        assert display is figure
        assert display.instant_charge is True

    def test_kingdom_builder_disables_instant_charge_advance_action(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        screen = BuildFigureScreen.__new__(BuildFigureScreen)
        screen.mode = 'defence'
        screen.game = SimpleNamespace(
            ceasefire_active=False,
            advancing_figure_id=None,
            advancing_player_id=None,
            player_id=1,
            battle_modifier=[],
            figures=[],
        )

        can_charge, is_counter, reason = BuildFigureScreen._can_instant_charge_advance(
            screen,
            _make_instant_charge_figure(),
        )

        assert can_charge is False
        assert is_counter is False
        assert reason == 'disabled_in_kingdom_config'


class TestBuildFigureScreenKingdomCardPool:
    def test_successful_kingdom_build_rebuilds_card_source_from_free_counts(self, monkeypatch):
        from game.components.cards.card import Card
        from game.core.card_source import CollectionCardSource
        from game.screens import build_figure_screen as module
        from game.screens.build_figure_screen import BuildFigureScreen

        screen = BuildFigureScreen.__new__(BuildFigureScreen)
        screen.mode = 'conquer'
        game = SimpleNamespace(land_id=7, _config={})
        game.set_config = lambda config: setattr(game, '_config', config)
        screen.game = game
        screen.card_source = CollectionCardSource(
            [Card('K', 'Hearts', 13, id=1), Card('K', 'Hearts', 13, id=2)],
            config_figures=[],
            locked_card_ids=set(),
        )
        screen.map_figure_cards_to_hand = lambda _figure: [Card('K', 'Hearts', 13, id=1)]

        new_config = {
            'figures': [{'id': 10, 'card_ids': [101]}],
            'battle_moves': [],
        }

        class Response:
            def json(self):
                return {'success': True, 'config': new_config}

        monkeypatch.setattr(module.requests, 'post', lambda *args, **kwargs: Response())
        monkeypatch.setattr(
            module.collection_service,
            'fetch_collection_cards',
            lambda: {'cards': [{'rank': 'K', 'suit': 'Hearts', 'free': 1}]},
        )

        figure = SimpleNamespace(
            family=SimpleNamespace(name='Himalaya King', color='defensive', field='castle'),
            name='Himalaya King',
            suit='Hearts',
            key_cards=[],
            number_card=None,
            upgrade_card=None,
            cards=[Card('K', 'Hearts', 13)],
            produces={},
            requires={},
            description='',
            upgrade_family_name=None,
            checkmate=False,
            cannot_be_blocked=False,
            rest_after_attack=False,
        )

        result = BuildFigureScreen._create_figure_kingdom(screen, figure)

        assert result['success'] is True
        assert game._config == new_config
        main, side = screen.card_source.get_cards()
        assert [(card.rank, card.suit) for card in main] == [('K', 'Hearts')]
        assert side == []

    def test_refresh_selected_family_removes_now_locked_figure(self):
        from game.components.cards.card import Card
        from game.core.card_source import CollectionCardSource
        from game.screens.build_figure_screen import BuildFigureScreen

        family = SimpleNamespace(
            name='Himalaya King',
            description='Castle figure',
            field='castle',
            suits=['Hearts'],
        )
        figure = SimpleNamespace(
            name='Himalaya King',
            family=family,
            cards=[Card('K', 'Hearts', 13)],
            produces={},
            requires={},
            get_value=lambda: 13,
            get_battle_bonus=lambda: 0,
        )
        family.figures = [figure]
        family.get_figures_by_suit = lambda suit: [figure] if suit == 'Hearts' else []

        displayed_lists = []
        screen = BuildFigureScreen.__new__(BuildFigureScreen)
        screen.mode = 'conquer'
        screen.selected_figure_family = family
        screen.card_source = CollectionCardSource(
            [Card('K', 'Hearts', 13, id=1)],
            config_figures=[],
            locked_card_ids=set(),
        )
        screen.scroll_text_list_shifter = SimpleNamespace(
            set_displayed_texts=lambda texts: displayed_lists.append(texts)
        )
        screen.update_family_icon_states = lambda: None
        screen._display_figure_for_mode = lambda fig: fig
        screen.get_given_cards_for_figure = lambda _fig: []
        screen.get_missing_cards_converted_ZK_for_figure = lambda fig: fig.cards

        BuildFigureScreen._refresh_selected_figure_family(screen)

        assert displayed_lists[-1][0]['content'] is figure

        screen.card_source = CollectionCardSource(
            [],
            config_figures=[],
            locked_card_ids=set(),
        )

        BuildFigureScreen._refresh_selected_figure_family(screen)

        refreshed = displayed_lists[-1]
        assert refreshed[0]['content'] is None
        assert refreshed[0]['missing_cards'] == figure.cards


class TestBuildFigureScreenKingdomExtras:
    """New kingdom-mode UX: cap badge, resource strip, suit filter."""

    def _make_screen(self, mode='conquer'):
        from game.screens.build_figure_screen import BuildFigureScreen, _SUITS
        screen = BuildFigureScreen.__new__(BuildFigureScreen)
        screen.mode = mode
        screen._suit_filter = set(_SUITS)
        return screen

    def test_suit_filter_hides_non_matching_entries(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        captured = []
        screen = self._make_screen('conquer')
        screen._suit_filter = {'diamonds'}
        screen.scroll_text_list_shifter = SimpleNamespace(
            set_displayed_texts=lambda texts: captured.append(list(texts)))
        screen.update_family_icon_states = lambda: None
        screen._display_figure_for_mode = lambda f: f
        screen.get_given_cards_for_figure = lambda _f: []
        screen.get_missing_cards_converted_ZK_for_figure = lambda _f: []

        family = SimpleNamespace(
            suits=['hearts', 'diamonds'],
            description='',
            field='village',
            name='Fam',
        )

        def figs_by_suit(suit):
            fig = SimpleNamespace(
                family=family, name='F', cards=[],
                produces=None, requires=None,
                suit=suit, instant_charge=False, checkmate=False,
                cannot_be_blocked=False, rest_after_attack=False,
                cannot_attack=False,
            )
            fig.get_value = lambda: 1
            fig.get_battle_bonus = lambda: 0
            return [fig]

        family.get_figures_by_suit = figs_by_suit
        screen.get_figures_in_hand = lambda _family: []  # force unbuildable branch

        BuildFigureScreen._set_figure_family_scroll_text(screen, family)

        last = captured[-1]
        assert len(last) == 1
        assert last[0]['suit'] == 'diamonds'

    def test_suit_filter_hides_matching_buildable_figures_too(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        captured = []
        screen = self._make_screen('conquer')
        screen._suit_filter = {'diamonds'}
        screen.scroll_text_list_shifter = SimpleNamespace(
            set_displayed_texts=lambda texts: captured.append(list(texts)))

        family = SimpleNamespace(
            description='',
            field='village',
            name='Fam',
        )
        hearts = SimpleNamespace(
            family=family, name='Hearts Fam', cards=[], suit='hearts',
            produces=None, requires=None,
        )
        diamonds = SimpleNamespace(
            family=family, name='Diamonds Fam', cards=[], suit='diamonds',
            produces=None, requires=None,
        )
        for fig in (hearts, diamonds):
            fig.get_value = lambda: 1
            fig.get_battle_bonus = lambda: 0

        screen.get_figures_in_hand = lambda _family: [hearts, diamonds]

        BuildFigureScreen._set_figure_family_scroll_text(screen, family)

        assert screen.selected_figures == [diamonds]
        assert [entry['content'] for entry in captured[-1]] == [diamonds]

    def test_suit_filter_all_on_keeps_full_list(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        captured = []
        screen = self._make_screen('conquer')
        screen.scroll_text_list_shifter = SimpleNamespace(
            set_displayed_texts=lambda texts: captured.append(list(texts)))
        screen.update_family_icon_states = lambda: None
        screen._display_figure_for_mode = lambda f: f
        screen.get_given_cards_for_figure = lambda _f: []
        screen.get_missing_cards_converted_ZK_for_figure = lambda _f: []

        family = SimpleNamespace(
            suits=['hearts', 'diamonds'], description='', field='village', name='F',
        )

        def figs_by_suit(suit):
            fig = SimpleNamespace(
                family=family, name='F', cards=[],
                produces=None, requires=None,
                suit=suit, instant_charge=False, checkmate=False,
                cannot_be_blocked=False, rest_after_attack=False,
                cannot_attack=False,
            )
            fig.get_value = lambda: 1
            fig.get_battle_bonus = lambda: 0
            return [fig]

        family.get_figures_by_suit = figs_by_suit
        screen.get_figures_in_hand = lambda _family: []

        BuildFigureScreen._set_figure_family_scroll_text(screen, family)
        assert {e['suit'] for e in captured[-1]} == {'hearts', 'diamonds'}

    def test_family_icon_state_respects_suit_filter(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        screen = self._make_screen('conquer')
        screen._suit_filter = {'diamonds'}
        family = SimpleNamespace(name='Fam')
        button = SimpleNamespace(family=family, is_active=True)
        screen.figure_family_buttons = {
            'offensive': [button],
            'defensive': [],
        }
        heart_figure = SimpleNamespace(suit='hearts')
        screen.get_figures_in_hand = lambda _family: [heart_figure]

        BuildFigureScreen.update_family_icon_states(screen)

        assert button.is_active is False

        diamond_figure = SimpleNamespace(suit='diamonds')
        screen.get_figures_in_hand = lambda _family: [heart_figure, diamond_figure]

        BuildFigureScreen.update_family_icon_states(screen)

        assert button.is_active is True

    def test_handle_suit_filter_click_toggles_state(self):
        from game.screens.build_figure_screen import BuildFigureScreen, _SUITS

        screen = self._make_screen('conquer')
        screen.color = 'Djungle'
        screen._refresh_selected_figure_family = lambda: None
        import pygame
        pygame.init()
        rects = {
            'hearts':   pygame.Rect(0, 0, 20, 20),
            'diamonds': pygame.Rect(60, 0, 20, 20),
        }
        screen._suit_filter_rects = rects
        screen._compute_suit_chip_rects = lambda: setattr(
            screen, '_suit_filter_rects', rects)

        # Click hearts chip: deselect hearts (diamonds still active for Djungle)
        handled = BuildFigureScreen._handle_suit_filter_click(screen, (10, 10))
        assert handled is True
        assert 'hearts' not in screen._suit_filter
        assert 'diamonds' in screen._suit_filter

        # Click empty area: not handled
        assert BuildFigureScreen._handle_suit_filter_click(screen, (500, 500)) is False

    def test_handle_suit_filter_click_last_active_restores_color_pair(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        screen = self._make_screen('conquer')
        screen.color = 'Djungle'
        screen._refresh_selected_figure_family = lambda: None
        # Only diamonds active for Djungle; clicking it should restore both.
        screen._suit_filter = {'diamonds', 'clubs', 'spades'}
        import pygame
        pygame.init()
        rects = {
            'hearts':   pygame.Rect(0, 0, 20, 20),
            'diamonds': pygame.Rect(60, 0, 20, 20),
        }
        screen._suit_filter_rects = rects
        screen._compute_suit_chip_rects = lambda: setattr(
            screen, '_suit_filter_rects', rects)

        BuildFigureScreen._handle_suit_filter_click(screen, (70, 10))
        assert {'hearts', 'diamonds'} <= screen._suit_filter

    def test_castle_cap_badge_uses_proxy_land_and_config(self):
        from game.screens.build_figure_screen import BuildFigureScreen

        calls = []

        def fake_draw(window, rect, current, cap, *, font=None, always=False):
            calls.append({'current': current, 'cap': cap, 'always': always})
            return rect

        import game.screens.build_figure_screen as module
        original = module.draw_castle_cap_indicator
        module.draw_castle_cap_indicator = fake_draw
        try:
            screen = self._make_screen('conquer')
            screen.window = object()
            screen.game = SimpleNamespace(
                land={'tier': 3},
                _config={'figures': [
                    {'field': 'castle'}, {'field': 'castle'}, {'field': 'village'}
                ]},
            )
            screen._kingdom_res_font = None
            import pygame
            pygame.init()
            screen._sx = lambda x: x
            screen._sy = lambda y: y

            BuildFigureScreen._draw_castle_cap_badge(screen)
        finally:
            module.draw_castle_cap_indicator = original

        assert calls and calls[0]['cap'] == 3
        assert calls[0]['current'] == 2
        assert calls[0]['always'] is True
