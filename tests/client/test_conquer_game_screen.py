# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for the dedicated conquer battle screen shell."""

from types import SimpleNamespace

import pygame


def _conquer_screen_class():
    from game.screens.conquer_game_screen import ConquerGameScreen

    return ConquerGameScreen


def _game_screen_class():
    from game.screens.game_screen import GameScreen

    return GameScreen


def _base_conquer_screen(game=None):
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(
        screen='conquer_game',
        subscreen='field',
        game=game or SimpleNamespace(mode='conquer'),
        pending_conquer_prelude_target=None,
    )
    screen.subscreens = {
        'field': SimpleNamespace(conquer_own_defender_mode=False),
        'battle_shop': SimpleNamespace(bought_moves=[]),
        'battle': SimpleNamespace(),
    }
    screen._last_conquer_auto_route_key = None
    screen._conquer_auto_ready_attempt_key = None
    return ConquerGameScreen, screen


def test_conquer_support_link_targets_halo_edge_not_icon_center():
    ConquerGameScreen = _conquer_screen_class()
    source = pygame.Rect(100, 100, 44, 56)

    halo = ConquerGameScreen._conquer_source_halo_rect(source)
    edge = ConquerGameScreen._conquer_rect_edge_point(halo, (20, halo.centery))

    assert edge == (halo.left, halo.centery)
    assert edge != source.center


def test_conquer_support_link_targets_marker_midpoint():
    """Round 12: the support/block link line ends at the side-marker midpoint
    of the source figure (not the figure center / halo edge)."""
    from game.screens.field_screen import FieldScreen

    ConquerGameScreen = _conquer_screen_class()
    icon = SimpleNamespace(
        hovered=False,
        clicked=False,
        rect_frame=pygame.Rect(0, 0, 44, 56),
        rect_frame_big=pygame.Rect(0, 0, 72, 88),
    )
    icon.rect_frame.center = (200, 300)
    icon.rect_frame_big.center = (200, 300)

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.subscreens = {
        'field': SimpleNamespace(
            icon_cache={42: icon},
            _conquer_icon_marker_geometry=FieldScreen._conquer_icon_marker_geometry,
        ),
    }

    own_endpoint = screen._conquer_support_source_marker_endpoint(42, is_own=True)
    opp_endpoint = screen._conquer_support_source_marker_endpoint(42, is_own=False)

    own_marker = FieldScreen._conquer_icon_marker_geometry(
        icon, (200, 300), is_own=True)
    opp_marker = FieldScreen._conquer_icon_marker_geometry(
        icon, (200, 300), is_own=False)

    # Endpoints match the marker midpoints (not the figure center).
    assert own_endpoint == own_marker['midpoint']
    assert opp_endpoint == opp_marker['midpoint']
    assert own_endpoint != (200, 300)
    # Own marker sits to the right of the figure, opponent marker to the left.
    assert own_endpoint[0] > 200
    assert opp_endpoint[0] < 200


def test_field_icon_click_refreshes_hover_from_event_pos():
    from game.screens.field_screen import FieldScreen

    screen = FieldScreen.__new__(FieldScreen)
    opened = []
    icon = SimpleNamespace(
        hovered=False,
        clicked=False,
        is_visible=True,
        rect_frame=pygame.Rect(40, 40, 30, 30),
        figure=SimpleNamespace(id=5, name='Gorkha Soldier'),
    )
    screen.figure_icons = [icon]
    screen.figure_detail_box = None
    screen.dialogue_box = None
    screen.scroll_text_list_shifter = None
    screen._close_rect = pygame.Rect(999, 999, 1, 1)
    screen._on_done = None
    screen._sync_field_compartments_layout = lambda: None
    screen._is_tactics_hand_battle_field_view_only = lambda: True
    screen._force_immediate_redraw = lambda: None
    screen._open_tactics_hand_battle_detail = lambda clicked: opened.append(clicked)

    event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=icon.rect_frame.center)

    FieldScreen.handle_events(screen, [event])

    assert opened == [icon]
    assert icon.clicked is True


def test_passive_timeline_still_allows_field_inspection_clicks():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    handled = []
    field = SimpleNamespace(
        dialogue_box=None,
        _is_tactics_hand_battle_field_view_only=lambda: True,
        handle_events=lambda events: handled.extend(events),
    )
    screen.state = SimpleNamespace(
        game=SimpleNamespace(mode='conquer'),
        subscreen='field',
    )
    screen.subscreens = {'field': field}
    screen.dialogue_box = None
    screen.need_to_respond_to_spell = False
    screen.waiting_for_counter_response = False
    screen._ensure_conquer_screen_game = lambda: True
    screen._handle_conquer_command_events = lambda events: False
    screen._handle_collapsed_header_events = lambda events: False
    screen._is_tactics_hand_game = lambda: True
    screen._round_ledger = SimpleNamespace(handle_event=lambda event: None)
    screen._tactics_rail = SimpleNamespace(handle_event=lambda event: False)
    screen._conquer_nav_buttons = lambda: []
    screen._normalize_conquer_subscreen = lambda: None
    screen.active_conquer_timeline_step = lambda: SimpleNamespace(interactive=False)

    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(50, 50))

    ConquerGameScreen.handle_events(screen, [event])

    assert handled == [event]


def test_conquer_explosion_missing_target_gets_ghost_rect_and_animation():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    spell = {
        'spell_name': 'Explosion',
        'target_figure_id': 77,
        'effect_data': {
            'target_figure_id': 77,
            'target_figure_snapshot': {
                'id': 77,
                'player_id': 20,
                'name': 'Target Knight',
                'family_name': 'Knight',
                'field': 'military',
                'suit': 'Hearts',
                'cards': [{'rank': '6', 'suit': 'Hearts', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = []
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 160, 48)
    field = SimpleNamespace(
        icon_cache={},
        figure_icons=[],
        categorized_figures={
            'self': {'castle': [], 'village': [], 'military': []},
            'opponent': {'castle': [], 'village': [], 'military': []},
        },
        compartments={
            'self': {'military': pygame.Rect(20, 120, 120, 360)},
            'opponent': {'military': pygame.Rect(740, 120, 120, 360)},
        },
        figure_manager=SimpleNamespace(families={}),
    )
    screen.subscreens = {'field': field}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='prelude_own',
                icon_payload='Explosion',
                owner='you',
                active=True,
                completed=False,
            )]

    class _Effects:
        def __init__(self):
            self.spawned = []
            self.cleared = False

        def clear(self):
            self.cleared = True

        def spawn_explosion(self, anchor, target_id):
            self.spawned.append(('explosion', pygame.Rect(anchor), target_id))

        def spawn_banner(self, *args, **kwargs):
            self.spawned.append(('banner', args, kwargs))

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    assert effects.spawned
    assert effects.spawned[0][0] == 'explosion'
    assert effects.spawned[0][2] == 77
    ghost_rect = ConquerGameScreen._lookup_conquer_figure_rect(screen, 77)
    assert ghost_rect is not None
    assert ghost_rect.centerx == field.compartments['opponent']['military'].centerx


def test_conquer_health_boost_missing_target_uses_snapshot_anchor():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    spell = {
        'spell_name': 'Health Boost',
        'target_figure_id': 88,
        'effect_data': {
            'target_figure_id': 88,
            'target_figure_snapshot': {
                'id': 88,
                'player_id': 10,
                'name': 'Boosted Guard',
                'family_name': 'Guard',
                'field': 'village',
                'suit': 'Diamonds',
                'cards': [{'rank': '7', 'suit': 'Diamonds', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = []
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 160, 48)
    field = SimpleNamespace(
        icon_cache={},
        figure_icons=[],
        categorized_figures={
            'self': {'castle': [], 'village': [], 'military': []},
            'opponent': {'castle': [], 'village': [], 'military': []},
        },
        compartments={
            'self': {'village': pygame.Rect(20, 120, 120, 360)},
            'opponent': {'village': pygame.Rect(740, 120, 120, 360)},
        },
        figure_manager=SimpleNamespace(families={}),
    )
    screen.subscreens = {'field': field}

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [SimpleNamespace(
                kind='prelude_own',
                icon_payload='Health Boost',
                owner='you',
                active=True,
                completed=False,
            )]

    class _Effects:
        def __init__(self):
            self.spawned = []

        def clear(self):
            pass

        def spawn_spell_cast(self, spell_name, anchor, target_id, **kwargs):
            self.spawned.append((spell_name, pygame.Rect(anchor), target_id, kwargs))

        def spawn_banner(self, *args, **kwargs):
            self.spawned.append(('banner', args, kwargs))

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    assert effects.spawned
    assert effects.spawned[0][0] == 'Health Boost'
    assert effects.spawned[0][2] == 88
    assert effects.spawned[0][3]['floating_text'] == '+ Health'


def test_conquer_health_boost_refires_when_pending_target_resolves():
    """When a pending-target Health Boost first becomes active without a
    resolved target_figure_id, the pump should only emit a banner.  Once
    the target is resolved on a later frame, the real spell-cast
    animation must fire — even though the timeline step has already
    transitioned past ``pending``."""
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((900, 620), pygame.SRCALPHA)

    spell = {
        'spell_name': 'Health Boost',
        # Target unresolved on the first frame.
        'target_figure_id': None,
        'effect_data': {
            'target_figure_id': None,
            'target_figure_snapshot': {
                'id': 99,
                'player_id': 10,
                'name': 'Pending Guard',
                'family_name': 'Guard',
                'field': 'village',
                'suit': 'Diamonds',
                'cards': [{'rank': '7', 'suit': 'Diamonds', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_lane_figure_rects = []
    screen._last_seen_figure_rects = {}
    screen._last_announced_battle_round = 0
    screen._round_transition_until_ms = 0
    screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 160, 48)
    field = SimpleNamespace(
        icon_cache={},
        figure_icons=[],
        categorized_figures={
            'self': {'castle': [], 'village': [], 'military': []},
            'opponent': {'castle': [], 'village': [], 'military': []},
        },
        compartments={
            'self': {'village': pygame.Rect(20, 120, 120, 360)},
            'opponent': {'village': pygame.Rect(740, 120, 120, 360)},
        },
        figure_manager=SimpleNamespace(families={}),
    )
    screen.subscreens = {'field': field}

    step = SimpleNamespace(
        kind='prelude_own',
        icon_payload='Health Boost',
        owner='you',
        active=True,
        completed=False,
    )

    class _Panel:
        _active_step_rect = pygame.Rect(20, 20, 80, 48)

        def derive_display_steps(self, _screen):
            return [step]

    class _Effects:
        def __init__(self):
            self.spawned = []

        def clear(self):
            pass

        def spawn_spell_cast(self, spell_name, anchor, target_id, **kwargs):
            self.spawned.append(('spell_cast', spell_name, target_id, kwargs))

        def spawn_banner(self, *args, **kwargs):
            self.spawned.append(('banner', args, kwargs))

    effects = _Effects()
    screen._conquer_timeline_panel = _Panel()
    screen._conquer_effects = effects

    # First-frame seed: pending target → banner only, no spell_cast.
    ConquerGameScreen._pump_conquer_spell_animations(screen)
    assert effects.spawned, "first pump should still emit a banner"
    assert all(kind != 'spell_cast' for kind, *_rest in effects.spawned)

    # Server resolves the target.  Step transitions active → completed.
    spell['target_figure_id'] = 99
    spell['effect_data']['target_figure_id'] = 99
    step.active = False
    step.completed = True

    ConquerGameScreen._pump_conquer_spell_animations(screen)

    spell_casts = [row for row in effects.spawned if row[0] == 'spell_cast']
    assert spell_casts, "spell_cast must fire after the target resolves"
    assert spell_casts[-1][1] == 'Health Boost'
    assert spell_casts[-1][2] == 99


def test_conquer_visual_ghost_spec_persists_during_overview():
    """Bug regression: the Explosion victim must remain visible (and a
    normal field figure) during the overview / pre-prelude window so the
    player can see the destroyed-by reveal."""
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)

    spell = {
        'spell_name': 'Explosion',
        'target_figure_id': 77,
        'effect_data': {
            'target_figure_id': 77,
            'target_figure_snapshot': {
                'id': 77,
                'player_id': 20,
                'name': 'Doomed Knight',
                'family_name': 'Knight',
                'field': 'military',
                'suit': 'Hearts',
                'cards': [{'rank': '6', 'suit': 'Hearts', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)

    class _Panel:
        # Overview holds active.  Sequence gates have demoted prelude_own
        # to a non-active, non-completed state in real game flow, but in
        # other timelines the prelude step can still be reported as
        # completed (auto-resolved) — we cover that case below.
        def derive_display_steps(self, _screen):
            return [
                SimpleNamespace(kind='overview', active=True, completed=False,
                                icon_payload=None, owner=''),
                SimpleNamespace(kind='prelude_own', active=False, completed=True,
                                icon_payload='Explosion', owner='you'),
            ]

    screen._conquer_timeline_panel = _Panel()
    screen._field_explosion_ghost_hold_until = {}

    specs = ConquerGameScreen.conquer_field_visual_ghost_specs(screen)

    assert len(specs) == 1
    spec = specs[0]
    assert spec['target_id'] == 77
    assert spec['spell_name'] == 'Explosion'
    # Snapshot must remain a normal (selectable) field figure during the
    # pre-battle window, regardless of the underlying step phase.
    assert spec['visual_only'] is False
    assert spec['force_visible'] is True


def test_conquer_visual_ghost_spec_is_removed_when_explosion_executes():
    """Explosion victims are replay figures only until their spell executes."""
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)

    spell = {
        'spell_name': 'Explosion',
        'target_figure_id': 77,
        'effect_data': {
            'target_figure_id': 77,
            'target_figure_snapshot': {
                'id': 77,
                'player_id': 20,
                'name': 'Doomed Knight',
                'family_name': 'Knight',
                'field': 'military',
                'suit': 'Hearts',
                'cards': [{'rank': '6', 'suit': 'Hearts', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell],
        conquer_opp_prelude_spells=[],
    )
    screen.state = SimpleNamespace(game=game)
    screen._field_explosion_ghost_hold_until = {}

    phase_steps = {
        'pending': SimpleNamespace(kind='prelude_own', active=False,
                                   completed=False, icon_payload='Explosion',
                                   owner='you'),
        'active': SimpleNamespace(kind='prelude_own', active=True,
                                  completed=False, icon_payload='Explosion',
                                  owner='you'),
        'completed': SimpleNamespace(kind='prelude_own', active=False,
                                     completed=True, icon_payload='Explosion',
                                     owner='you'),
    }

    class _Panel:
        def __init__(self, step):
            self._step = step

        def derive_display_steps(self, _screen):
            return [self._step]

    captured = {}
    for label, step in phase_steps.items():
        screen._conquer_timeline_panel = _Panel(step)
        specs = ConquerGameScreen.conquer_field_visual_ghost_specs(screen)
        captured[label] = specs

    assert len(captured['pending']) == 1
    assert captured['pending'][0]['visual_only'] is False
    assert captured['pending'][0]['phase'] == 'pending'
    assert captured['active'] == []
    assert captured['completed'] == []


def test_conquer_explosion_visual_ghost_uses_active_spell_fallback():
    """The Explosion victim is visible before game_start summary snapshots land."""
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)

    active_spell = {
        'id': 500,
        'player_id': 10,
        'spell_name': 'Explosion',
        'spell_type': 'enchantment',
        'cast_round': 1,
        'target_figure_id': None,
        'effect_data': {
            'prelude_origin': True,
            'prelude_status': 'executed',
            'destroyed_figure_id': 77,
            'destroyed_figure_snapshot': {
                'id': 77,
                'player_id': 20,
                'name': 'Doomed Knight',
                'family_name': 'Knight',
                'field': 'military',
                'suit': 'Hearts',
                'cards': [{'rank': '6', 'suit': 'Hearts', 'role': 'number'}],
            },
        },
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[],
        conquer_opp_prelude_spells=[],
        cached_active_spells=[active_spell],
    )
    screen.state = SimpleNamespace(game=game)

    class _Panel:
        def derive_display_steps(self, _screen):
            return [
                SimpleNamespace(kind='overview', active=True, completed=False,
                                icon_payload=None, owner=''),
            ]

    screen._conquer_timeline_panel = _Panel()

    specs = ConquerGameScreen.conquer_field_visual_ghost_specs(screen)

    assert len(specs) == 1
    assert specs[0]['target_id'] == 77
    assert specs[0]['spell_name'] == 'Explosion'
    assert specs[0]['visual_only'] is False


def test_conquer_prelude_enchantment_hidden_until_step_active():
    ConquerGameScreen = _conquer_screen_class()
    from game.screens.field_screen import FieldScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    spell = {
        'spell_name': 'Poison',
        'target_figure_id': 77,
        'effect_data': {'target_figure_id': 77},
    }
    health_spell = {
        'spell_name': 'Health Boost',
        'target_figure_id': 88,
        'effect_data': {'target_figure_id': 88},
    }
    game = SimpleNamespace(
        mode='conquer',
        game_id=1,
        player_id=10,
        battle_round=0,
        battle_confirmed=False,
        conquer_own_prelude_spells=[spell, health_spell],
        conquer_opp_prelude_spells=[],
        cached_active_spells=[],
    )
    screen.state = SimpleNamespace(game=game)

    class _Panel:
        def __init__(self, steps):
            self._steps = steps

        def derive_display_steps(self, _screen):
            return self._steps

    field = FieldScreen.__new__(FieldScreen)
    field.game = game
    field.state = SimpleNamespace(parent_screen=screen)

    figure = SimpleNamespace(id=77, active_enchantments=[{
        'spell_name': 'Poison',
        'spell_icon': 'poisson_portion.png',
        'power_modifier': -6,
    }])
    boosted = SimpleNamespace(id=88, active_enchantments=[{
        'spell_name': 'Health Boost',
        'spell_icon': 'health_portion.png',
        'power_modifier': 6,
    }])

    screen._conquer_timeline_panel = _Panel([
        SimpleNamespace(kind='overview', active=True, completed=False),
        # Base game state may already mark the prelude complete; the active
        # overview still means this effect is not the leading timeline beat.
        SimpleNamespace(kind='prelude_own', active=False, completed=True),
    ])
    FieldScreen._filter_conquer_timeline_enchantments(field, [figure, boosted])
    assert figure.active_enchantments == []
    assert boosted.active_enchantments == []

    figure.active_enchantments = [{
        'spell_name': 'Poison',
        'spell_icon': 'poisson_portion.png',
        'power_modifier': -6,
    }]
    boosted.active_enchantments = [{
        'spell_name': 'Health Boost',
        'spell_icon': 'health_portion.png',
        'power_modifier': 6,
    }]
    screen._conquer_timeline_panel = _Panel([
        SimpleNamespace(kind='overview', active=False, completed=True),
        SimpleNamespace(kind='prelude_own', active=True, completed=False),
    ])
    FieldScreen._filter_conquer_timeline_enchantments(field, [figure, boosted])
    assert figure.active_enchantments
    assert boosted.active_enchantments


def test_conquer_explosion_pending_snapshot_is_normal_field_figure(monkeypatch):
    from game.components.cards.card import Card
    from game.components.figures.figure import Figure
    from game.screens.field_screen import FieldScreen

    family = SimpleNamespace(
        name='Target Knight',
        field='military',
        color='offensive',
        figures=[],
    )
    family.figures = [Figure(
        name='Target Knight',
        sub_name='Hearts 6',
        suit='Hearts',
        family=family,
        key_cards=[Card('K', 'Hearts', 13)],
        number_card=Card('6', 'Hearts', 6),
    )]
    live_figure = Figure(
        name='Live Guard',
        sub_name='Hearts 7',
        suit='Hearts',
        family=family,
        key_cards=[Card('Q', 'Hearts', 12)],
        number_card=Card('7', 'Hearts', 7),
        id=21,
        player_id=20,
    )
    snapshot = {
        'id': 77,
        'player_id': 20,
        'name': 'Target Knight',
        'family_name': 'Target Knight',
        'field': 'military',
        'suit': 'Hearts',
        'cards': [
            {'rank': 'K', 'suit': 'Hearts', 'value': 13, 'role': 'key'},
            {'rank': '6', 'suit': 'Hearts', 'value': 6, 'role': 'number'},
        ],
    }
    parent = SimpleNamespace(
        conquer_field_visual_ghost_specs=lambda: [{
            'target_id': 77,
            'snapshot': snapshot,
            'step_kind': 'prelude_own',
            'spell_name': 'Explosion',
            'phase': 'pending',
            'visual_only': False,
            'force_visible': True,
        }]
    )
    game = SimpleNamespace(
        mode='conquer',
        player_id=10,
        opponent_player={'id': 20},
        get_figures=lambda _families, is_opponent=False: [live_figure] if is_opponent else [],
        calculate_resources=lambda *_args, **_kwargs: {'produces': {}, 'requires': {}},
        has_active_all_seeing_eye=lambda: False,
    )
    field = FieldScreen.__new__(FieldScreen)
    field.window = pygame.Surface((900, 620), pygame.SRCALPHA)
    field.state = SimpleNamespace(parent_screen=parent)
    field.game = game
    field.figure_manager = SimpleNamespace(families={'Target Knight': family})
    field.icon_cache = {}
    field.last_figure_ids = set()
    field.last_enchantment_state = {}
    field.last_player_id = None
    field.cached_all_seeing_eye_status = None
    field._last_all_seeing_eye_status = None
    field._conquer_visual_ghost_ids = set()
    monkeypatch.setattr(FieldScreen, '_generate_figure_icons', lambda self: None)

    FieldScreen.load_figures(field)

    military_figures = field.categorized_figures['opponent']['military']
    assert [figure.id for figure in military_figures] == [21, 77]
    timeline_figure = military_figures[1]
    assert getattr(timeline_figure, '_conquer_timeline_snapshot', False) is True
    assert getattr(timeline_figure, '_conquer_visual_only', False) is False
    assert timeline_figure in field.figures
    assert 77 in field.last_figure_ids


def test_conquer_explosion_active_snapshot_is_visual_only_hold(monkeypatch):
    from game.components.cards.card import Card
    from game.components.figures.figure import Figure
    from game.screens.field_screen import FieldScreen

    family = SimpleNamespace(
        name='Target Knight',
        field='military',
        color='offensive',
        figures=[],
    )
    family.figures = [Figure(
        name='Target Knight',
        sub_name='Hearts 6',
        suit='Hearts',
        family=family,
        key_cards=[Card('K', 'Hearts', 13)],
        number_card=Card('6', 'Hearts', 6),
    )]
    snapshot = {
        'id': 77,
        'player_id': 20,
        'name': 'Target Knight',
        'family_name': 'Target Knight',
        'field': 'military',
        'suit': 'Hearts',
        'cards': [
            {'rank': 'K', 'suit': 'Hearts', 'value': 13, 'role': 'key'},
            {'rank': '6', 'suit': 'Hearts', 'value': 6, 'role': 'number'},
        ],
    }
    parent = SimpleNamespace(
        conquer_field_visual_ghost_specs=lambda: [{
            'target_id': 77,
            'snapshot': snapshot,
            'step_kind': 'prelude_own',
            'spell_name': 'Explosion',
            'phase': 'active',
            'visual_only': True,
            'force_visible': True,
        }]
    )
    game = SimpleNamespace(
        mode='conquer',
        player_id=10,
        opponent_player={'id': 20},
        get_figures=lambda _families, is_opponent=False: [],
        calculate_resources=lambda *_args, **_kwargs: {'produces': {}, 'requires': {}},
        has_active_all_seeing_eye=lambda: False,
    )
    field = FieldScreen.__new__(FieldScreen)
    field.window = pygame.Surface((900, 620), pygame.SRCALPHA)
    field.state = SimpleNamespace(parent_screen=parent)
    field.game = game
    field.figure_manager = SimpleNamespace(families={'Target Knight': family})
    field.icon_cache = {}
    field.last_figure_ids = set()
    field.last_enchantment_state = {}
    field.last_player_id = None
    field.cached_all_seeing_eye_status = None
    field._last_all_seeing_eye_status = None
    field._conquer_visual_ghost_ids = set()
    monkeypatch.setattr(FieldScreen, '_generate_figure_icons', lambda self: None)

    FieldScreen.load_figures(field)

    ghost = field.categorized_figures['opponent']['military'][0]
    assert getattr(ghost, '_conquer_timeline_snapshot', False) is True
    assert getattr(ghost, '_conquer_visual_only', False) is True
    assert ghost not in field.figures
    assert 77 in field.last_figure_ids


def test_conquer_skipped_tactics_fill_lanes_and_enable_finish():
    game = SimpleNamespace(
        mode='conquer',
        player_id=10,
        players=[{'id': 10}, {'id': 20}],
        battle_round=2,
        battle_turn_player_id=None,
        battle_skipped_rounds={'10': [1], '20': [2]},
        last_battle_result=None,
        game_over=False,
    )
    ConquerGameScreen, screen = _base_conquer_screen(game)
    screen._current_conquer_tactics = lambda: [
        {'id': 1, 'player_id': 10, 'family_name': 'Dagger', 'value': 3, 'played_round': 0},
        {'id': 2, 'player_id': 10, 'family_name': 'Wall', 'value': 4, 'played_round': 2},
    ]
    screen._current_conquer_opponent_tactics = lambda: [
        {'id': 3, 'player_id': 20, 'family_name': 'Block', 'value': 0, 'played_round': 0},
        {'id': 4, 'player_id': 20, 'family_name': 'Dagger', 'value': 2, 'played_round': 1},
    ]

    player_slots, opponent_slots = ConquerGameScreen._conquer_lane_played_tactics(screen)

    assert player_slots[1]['_skipped'] is True
    assert player_slots[1]['played_round'] == 1
    assert opponent_slots[2]['_skipped'] is True
    assert opponent_slots[2]['played_round'] == 2
    assert ConquerGameScreen._conquer_finish_available(screen) is True


def test_conquer_support_link_arrow_draws_over_existing_pixels():
    """Support leader arrows are drawn as a final overlay so the endpoint
    stays visible even if it crosses an already-rendered field icon."""
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((240, 160))
    screen.window.fill((32, 28, 24))

    badge_rect = pygame.Rect(150, 70, 24, 20)
    endpoint = (80, 80)
    icon_color = (150, 40, 40)
    pygame.draw.rect(screen.window, icon_color, pygame.Rect(68, 66, 28, 28))

    assert screen.window.get_at(endpoint)[:3] == icon_color
    screen._draw_conquer_lane_source_link(
        badge_rect, endpoint, is_player=True)

    assert screen.window.get_at(endpoint)[:3] != icon_color
    assert screen.window.get_at(endpoint).b > icon_color[2]


def test_conquer_support_hover_tracks_all_source_figures(monkeypatch):
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    field = SimpleNamespace()
    screen.subscreens = {'field': field}
    screen._conquer_receipt_row_rects = []
    screen._conquer_support_badge_rects = [{
        'rect': pygame.Rect(10, 10, 40, 32),
        'entry': {'kind': 'support_bonus'},
        'figure_id': None,
        'source_figure_ids': [101, 102, 103],
        'is_player': True,
    }]
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (20, 20))

    hovered = screen._update_conquer_support_hover_state()

    assert hovered is screen._conquer_support_badge_rects[0]
    assert field._conquer_hover_source_figure_ids == {101, 102, 103}
    # The legacy single-id attribute remains as a compatibility fallback,
    # but field rendering now uses the full set so every source is marked
    # consistently.
    assert field._conquer_hover_source_figure_id == 101


def test_field_support_ids_use_parent_cached_lane_context():
    from game.screens.field_screen import FieldScreen

    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_turn_player_id=1,
        both_battle_moves_ready=False,
        last_battle_result=None,
    )
    calls = []
    parent = SimpleNamespace(
        request_conquer_figure_confirmation=lambda *args, **kwargs: None,
        conquer_active_support_figure_ids=lambda opponent_only=False: calls.append(opponent_only) or ({20} if opponent_only else {10, 20}),
    )
    field = FieldScreen.__new__(FieldScreen)
    field.game = game
    field.state = SimpleNamespace(parent_screen=parent)

    assert FieldScreen._tactics_hand_active_support_figure_ids(field) == {10, 20}
    assert FieldScreen._tactics_hand_active_support_figure_ids(field, opponent_only=True) == {20}
    assert calls == [False, True]


def test_field_support_visibility_syncs_cached_icons_without_reload():
    from game.screens.field_screen import FieldScreen

    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_turn_player_id=1,
        battle_round=1,
        both_battle_moves_ready=False,
        last_battle_result=None,
        game_id=7,
        player_id=1,
        _figures_data_version=1,
    )
    support_ids = {'20'}
    parent = SimpleNamespace(
        request_conquer_figure_confirmation=lambda *args, **kwargs: None,
        _conquer_tactic_cache_key=('round', 1),
        _conquer_opponent_tactic_cache_key=('round', 1),
        conquer_active_support_figure_ids=lambda opponent_only=False: set(support_ids),
    )
    figure = SimpleNamespace(id=20, player_id=2, name='Support Soldier')
    icon = SimpleNamespace(figure=figure, is_visible=False)
    field = FieldScreen.__new__(FieldScreen)
    field.game = game
    field.state = SimpleNamespace(parent_screen=parent)
    field.figure_icons = [icon]
    field.cached_all_seeing_eye_status = False
    field._last_tactics_hand_support_visibility_key = ()

    FieldScreen._sync_tactics_hand_support_visibility(field)

    assert icon.is_visible is True

    support_ids.clear()
    parent._conquer_tactic_cache_key = ('round', 2)
    parent._conquer_opponent_tactic_cache_key = ('round', 2)
    FieldScreen._sync_tactics_hand_support_visibility(field)

    assert icon.is_visible is False


def test_conquer_dim_flags_compare_normalized_figure_ids():
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    support_icon = SimpleNamespace(
        figure=SimpleNamespace(id=20),
        conquer_battle_dimmed=True,
    )
    idle_icon = SimpleNamespace(
        figure=SimpleNamespace(id=30),
        conquer_battle_dimmed=False,
    )
    screen.subscreens = {
        'field': SimpleNamespace(figure_icons=[support_icon, idle_icon]),
    }
    screen._is_battle_phase_active = lambda: True
    screen._conquer_battle_involved_figure_ids = lambda: {'20'}

    ConquerGameScreen._update_conquer_battle_dim_flags(screen)

    assert support_icon.conquer_battle_dimmed is False
    assert idle_icon.conquer_battle_dimmed is True


class TestGameplayScreenRouting:
    def test_conquer_games_route_to_conquer_game_screen(self):
        from game.core.screen_routing import gameplay_screen_for

        assert gameplay_screen_for(SimpleNamespace(mode='conquer')) == 'conquer_game'

    def test_duel_games_route_to_duel_game_screen(self):
        from game.core.screen_routing import gameplay_screen_for

        assert gameplay_screen_for(SimpleNamespace(mode='duel')) == 'game'
        assert gameplay_screen_for(SimpleNamespace()) == 'game'

    def test_duel_game_screen_redirects_accidental_conquer_game(self):
        GameScreen = _game_screen_class()
        screen = GameScreen.__new__(GameScreen)
        screen.state = SimpleNamespace(
            screen='game',
            game=SimpleNamespace(mode='conquer'),
        )

        assert GameScreen._ensure_duel_screen_game(screen) is False
        assert screen.state.screen == 'conquer_game'

    def test_conquer_game_screen_redirects_accidental_duel_game(self):
        ConquerGameScreen, screen = _base_conquer_screen(
            SimpleNamespace(mode='duel'))

        assert ConquerGameScreen._ensure_conquer_screen_game(screen) is False
        assert screen.state.screen == 'game'

    def test_game_screens_set_active_parent_on_enter(self):
        GameScreen = _game_screen_class()
        duel = GameScreen.__new__(GameScreen)
        duel.state = SimpleNamespace(
            screen='game',
            game=SimpleNamespace(mode='duel'),
        )

        GameScreen.on_enter(duel)
        assert duel.state.parent_screen is duel

        ConquerGameScreen, conquer = _base_conquer_screen(
            SimpleNamespace(mode='conquer'))
        ConquerGameScreen.on_enter(conquer)

        assert conquer.state.parent_screen is conquer
        assert conquer.state.subscreen == 'field'


class TestConquerGameShell:
    def test_initializes_only_three_conquer_tab_buttons(self):
        from config import settings

        ConquerGameScreen = _conquer_screen_class()
        screen = ConquerGameScreen.__new__(ConquerGameScreen)
        screen.window = pygame.Surface((1200, 800))
        screen.state = SimpleNamespace(game=SimpleNamespace(turn=True), subscreen='field')

        ConquerGameScreen.initialize_buttons(screen)

        names = [button.name for button in screen.game_buttons]
        # Battle-shop is no longer surfaced as a tab — the user is auto-routed
        # there during the moves phase by the timeline panel.
        assert names == [
            'conquer_view_field',
            'conquer_view_battle',
        ]
        assert all('build' not in name for name in names)
        assert all('spell' not in name for name in names)
        assert all('log' not in name for name in names)
        assert screen.battle_button.locked is False
        assert screen.field_button.x == screen.battle_button.x
        assert screen.field_button.y < screen.battle_button.y
        sub_x, _sub_y = ConquerGameScreen._conquer_subscreen_origin(screen)
        assert screen.field_button.x + settings.FIELD_BUTTON_WIDTH < sub_x

    def test_normalizes_hidden_duel_subscreen_to_field(self):
        ConquerGameScreen, screen = _base_conquer_screen()
        screen.state.subscreen = 'build_figure'

        ConquerGameScreen._normalize_conquer_subscreen(screen)

        assert screen.state.subscreen == 'field'

    def test_tactics_hand_always_normalizes_to_unified_field_canvas(self):
        game = SimpleNamespace(mode='conquer', conquer_move_model='tactics_hand')
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'battle'

        ConquerGameScreen._normalize_conquer_subscreen(screen)

        assert screen.state.subscreen == 'field'
        assert ConquerGameScreen._conquer_nav_buttons(screen) == []

    def test_tactics_hand_getters_do_not_start_polling(self):
        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            game_id=44,
            player_id=10,
            battle_turn_player_id=10,
            battle_round=1,
            last_battle_result=None,
            conquer_resolution_step=0,
            conquer_tactics=[
                {'id': 1, 'player_id': 10, 'family_name': 'Dagger', 'status': 'available'},
                {'id': 2, 'player_id': 20, 'family_name': 'Wall', 'status': 'available'},
            ],
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen._conquer_tactic_cache = []
        screen._conquer_opponent_tactic_cache = []
        screen._conquer_tactic_cache_key = None
        screen._conquer_opponent_tactic_cache_key = None
        calls = []
        screen._request_battle_state_poll = lambda force=False: calls.append(force)

        player_tactics = ConquerGameScreen._current_conquer_tactics(screen)
        opponent_tactics = ConquerGameScreen._current_conquer_opponent_tactics(screen)

        assert calls == []
        assert [move['id'] for move in player_tactics] == [1]
        assert [move['id'] for move in opponent_tactics] == [2]
        assert opponent_tactics[0]['played_round'] is None

    def test_lane_context_reuses_support_graph_for_same_snapshot(self):
        ConquerGameScreen, screen = _base_conquer_screen(SimpleNamespace(mode='conquer'))
        screen._conquer_lane_context_cache_key = None
        screen._conquer_lane_context_cache = None
        screen._conquer_tactic_power_cache_key = None
        screen._conquer_tactic_power_cache = {}
        screen._conquer_lane_context_key = lambda: ('battle', 1)
        screen._conquer_lane_figures = lambda: (['player_fig'], ['opp_fig'])
        screen._conquer_lane_played_tactics = lambda: ([None, None, None], [None, None, None])
        calls = []

        def support_entries(player_figures, opponent_figures, *, is_player, played_slots=None):
            calls.append((tuple(player_figures), tuple(opponent_figures), is_player, played_slots is not None))
            return [{
                'figure': SimpleNamespace(id=1 if is_player else 2),
                'source_figure_ids': [10 if is_player else 20],
            }]

        screen._conquer_lane_support_entries = support_entries

        first = ConquerGameScreen._conquer_lane_context(screen)
        second = ConquerGameScreen._conquer_lane_context(screen)

        assert first is second
        assert len(calls) == 2
        assert calls == [
            (('player_fig',), ('opp_fig',), True, True),
            (('player_fig',), ('opp_fig',), False, True),
        ]
        assert first['player_support_ids'] == {1, 10}
        assert first['opponent_support_ids'] == {2, 20}
        assert {1, 2, 10, 20}.issubset(first['involved_ids'])

    def test_conquer_subscreen_origin_is_centered_below_header(self):
        from config import settings

        ConquerGameScreen, screen = _base_conquer_screen()

        x, y = ConquerGameScreen._conquer_subscreen_origin(screen)

        assert x == (settings.SCREEN_WIDTH - settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH) // 2
        assert y > int(settings.SCREEN_HEIGHT * ConquerGameScreen.HEADER_H_FACTOR)
        assert y > settings.SUB_SCREEN_Y

    def test_auto_routes_to_field_once_for_required_field_action(self):
        game = SimpleNamespace(
            mode='conquer',
            pending_conquer_prelude_target=True,
            pending_spell_id=99,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'battle'

        ConquerGameScreen._auto_route_conquer_once(screen)
        assert screen.state.subscreen == 'field'

        screen.state.subscreen = 'battle'
        ConquerGameScreen._auto_route_conquer_once(screen)
        assert screen.state.subscreen == 'battle'

    def test_auto_routes_to_battle_shop_once_for_move_confirmation(self):
        # The auto_route helper itself does not move the user to the
        # battle_shop subscreen anymore — that is handled by
        # ``_enforce_battle_shop_during_moves`` so the user is forced there
        # during the moves phase.
        game = SimpleNamespace(
            mode='conquer',
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            battle_confirmed=False,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.battle_button = SimpleNamespace(locked=False)
        screen.state.subscreen = 'field'
        screen._conquer_left_battle_shop_at = 0
        screen.BATTLE_SHOP_SNAPBACK_MS = 0  # snap immediately for the test.

        ConquerGameScreen._enforce_battle_shop_during_moves(screen)
        # First call records the timestamp.  Second call snaps back.
        ConquerGameScreen._enforce_battle_shop_during_moves(screen)

        assert screen.state.subscreen == 'battle_shop'

    def test_auto_routes_to_battle_when_battle_has_started(self):
        game = SimpleNamespace(
            mode='conquer',
            battle_confirmed=True,
            battle_turn_player_id=20,
            battle_round=1,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'field'

        ConquerGameScreen._auto_route_conquer_once(screen)

        assert screen.state.subscreen == 'battle'

    def test_auto_routes_tactics_hand_battle_to_field(self):
        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=1,
            player_id=42,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'battle'

        ConquerGameScreen._auto_route_conquer_once(screen)

        assert screen.state.subscreen == 'field'

    def test_attention_counts_mark_required_tabs(self):
        game = SimpleNamespace(
            mode='conquer',
            pending_forced_advance=True,
            advancing_figure_id=None,
            battle_confirmed=True,
            battle_turn_player_id=20,
            pending_conquer_prelude_target=False,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            civil_war_awaiting_second=False,
            civil_war_defender_second=False,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)

        counts = ConquerGameScreen._conquer_attention_counts(screen)

        # battle_shop no longer has a dedicated tab — its attention is
        # surfaced via the timeline panel + auto-routing instead.
        assert counts == {'field': 1, 'battle': 1}

    def test_attention_counts_keep_tactics_hand_battle_on_field(self):
        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=20,
            pending_conquer_prelude_target=False,
            pending_forced_advance=False,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            civil_war_awaiting_second=False,
            civil_war_defender_second=False,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)

        counts = ConquerGameScreen._conquer_attention_counts(screen)

        assert counts == {'field': 1, 'battle': 0}

    def test_confirming_figure_selection_acknowledges_selection_step(self):
        ConquerGameScreen, screen = _base_conquer_screen()
        screen._conquer_pending_confirmation = {'kind': 'advance'}
        screen._conquer_acknowledged_step_kinds = set()
        screen._conquer_timeline_step_started_at = {}
        screen.subscreens['field'] = SimpleNamespace(
            confirm_pending_advance=lambda: True)

        handled = ConquerGameScreen._handle_conquer_objective_action(
            screen, 'confirm')

        assert handled is True
        assert 'attacker' in screen._conquer_acknowledged_step_kinds

    def test_auto_confirms_conquer_moves_when_shop_has_no_changes(self, monkeypatch):
        game = SimpleNamespace(
            mode='conquer',
            game_id=12,
            player_id=3,
            battle_confirmed=True,
            battle_turn_player_id=None,
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            _game_data_version=1,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'field'
        screen.subscreens['battle_shop'] = SimpleNamespace(
            bought_moves=[{'id': 1}, {'id': 2}, {'id': 3}],
            card_source=None,
            game=game,
            _load_bought_moves=lambda: None,
            _can_ready_for_battle=lambda: True,
            has_available_battle_move_changes=lambda: False,
        )

        monkeypatch.setattr(
            'utils.battle_shop_service.confirm_battle_moves',
            lambda game_id, player_id: {'success': True, 'both_ready': True},
        )

        handled = ConquerGameScreen._auto_confirm_conquer_battle_moves_if_no_changes(screen)

        assert handled is True
        assert screen.state.subscreen == 'battle'
        assert game.battle_moves_phase is False
        assert game.both_battle_moves_ready is True

    def test_keeps_conquer_shop_when_move_changes_exist(self, monkeypatch):
        game = SimpleNamespace(
            mode='conquer',
            game_id=12,
            player_id=3,
            battle_confirmed=True,
            battle_turn_player_id=None,
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            _game_data_version=1,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.battle_button = SimpleNamespace(locked=False)
        screen.subscreens['battle_shop'] = SimpleNamespace(
            bought_moves=[{'id': 1}, {'id': 2}, {'id': 3}],
            card_source=None,
            game=game,
            _load_bought_moves=lambda: None,
            _can_ready_for_battle=lambda: True,
            has_available_battle_move_changes=lambda: True,
        )
        called = []
        monkeypatch.setattr(
            'utils.battle_shop_service.confirm_battle_moves',
            lambda game_id, player_id: called.append((game_id, player_id)),
        )

        handled = ConquerGameScreen._auto_confirm_conquer_battle_moves_if_no_changes(screen)

        assert handled is False
        assert called == []

    def test_battle_shop_reloads_moves_when_game_data_version_changes(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        game = SimpleNamespace(
            game_id=12,
            player_id=3,
            _game_data_version=2,
            battle_moves_phase=True,
            battle_confirmed=True,
        )
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.game = game
        screen.mode = 'duel'
        screen.card_source = SimpleNamespace(game=game)
        screen.buttons = []
        screen.scroll_text_list_shifter = None
        screen._loaded_game_key = (12, 3)
        screen._loaded_bought_moves_key = (12, 3, 1)
        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        screen._battle_moves_confirmed = False
        screen._waiting_for_opponent = False
        screen.confirm_button = SimpleNamespace(disabled=True, update=lambda: None)
        screen.ready_button = SimpleNamespace(disabled=True, update=lambda: None)
        screen.move_family_buttons = []
        screen._can_ready_for_battle = lambda: True
        screen._update_icon_states = lambda: None
        figure_loads = []
        screen._load_player_figures = lambda: figure_loads.append('figures')
        move_loads = []

        def _reload_moves():
            move_loads.append('moves')
            screen.bought_moves = [{'id': 1}, {'id': 2}]
            screen._loaded_game_key = BattleShopScreen._game_identity_key(screen, game)
            screen._loaded_bought_moves_key = BattleShopScreen._bought_moves_cache_key(screen, game)

        screen._load_bought_moves = _reload_moves

        BattleShopScreen.update(screen, game)

        assert move_loads == ['moves']
        assert figure_loads == []
        assert screen.confirm_button.disabled is False

    def test_battle_shop_config_ready_requires_three_moves(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        game = SimpleNamespace(
            game_id=None,
            player_id=None,
            battle_moves_phase=False,
            battle_confirmed=False,
        )
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.game = game
        screen.mode = 'conquer'
        screen.card_source = SimpleNamespace(game=game)
        screen.buttons = []
        screen.scroll_text_list_shifter = None
        screen._loaded_game_key = (None, None)
        screen._loaded_bought_moves_key = (None, None)
        screen._battle_moves_confirmed = False
        screen._waiting_for_opponent = False
        screen.confirm_button = SimpleNamespace(disabled=False, update=lambda: None)
        screen.ready_button = SimpleNamespace(
            disabled=False, active=True, update=lambda: None)
        screen.move_family_buttons = []
        screen._update_icon_states = lambda: None

        screen.bought_moves = [{'id': 1}, {'id': 2}]
        BattleShopScreen.update(screen, game)

        assert screen.ready_button.disabled is True
        assert screen.ready_button.active is False

        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        BattleShopScreen.update(screen, game)

        assert screen.ready_button.disabled is False
        assert screen.ready_button.active is True

    def test_battle_shop_config_ready_hover_changes_glow_state(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        class HoverButton:
            def __init__(self):
                self.disabled = False
                self.active = True
                self.hovered = False

            def update(self):
                self.hovered = True

        game = SimpleNamespace(
            game_id=None,
            player_id=None,
            battle_moves_phase=False,
            battle_confirmed=False,
        )
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.game = game
        screen.mode = 'conquer'
        screen.card_source = SimpleNamespace(game=game)
        screen.buttons = []
        screen.scroll_text_list_shifter = None
        screen._loaded_game_key = (None, None)
        screen._loaded_bought_moves_key = (None, None)
        screen._battle_moves_confirmed = False
        screen._waiting_for_opponent = False
        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        screen.confirm_button = SimpleNamespace(disabled=False, update=lambda: None)
        screen.ready_button = HoverButton()
        screen.move_family_buttons = []
        screen._update_icon_states = lambda: None

        BattleShopScreen.update(screen, game)

        assert screen.ready_button.disabled is False
        assert screen.ready_button.hovered is True
        assert screen.ready_button.active is False

    def test_battle_shop_config_ready_closes_subscreen_when_full(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        called = []
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.mode = 'defence_draft'
        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        screen._on_done = lambda: called.append('closed')

        handled = BattleShopScreen._on_config_ready(screen)

        assert handled is True
        assert called == ['closed']

        screen.bought_moves = [{'id': 1}, {'id': 2}]
        called.clear()

        handled = BattleShopScreen._on_config_ready(screen)

        assert handled is False
        assert called == []

    def test_battle_shop_config_ready_closes_on_mouseup_not_mousedown(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        called = []
        slot_clicks = []
        ready_rect = pygame.Rect(20, 20, 90, 42)
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.mode = 'conquer'
        screen.game = SimpleNamespace(
            game_over=False,
            battle_moves_phase=False,
            battle_confirmed=False,
        )
        screen.scroll_text_list_shifter = None
        screen.battle_move_detail_box = None
        screen.dialogue_box = None
        screen.move_family_buttons = []
        screen.confirm_button = SimpleNamespace(collide=lambda: False, disabled=True)
        screen.ready_button = SimpleNamespace(disabled=False, rect=ready_rect)
        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        screen._config_ready_pressed = False
        screen._on_done = lambda: called.append('closed')
        screen._close_rect = pygame.Rect(500, 500, 20, 20)
        screen._handle_slot_click = lambda event: slot_clicks.append(event.pos)

        BattleShopScreen.handle_events(screen, [pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=ready_rect.center)])

        assert called == []
        assert slot_clicks == []
        assert screen._config_ready_pressed is True

        BattleShopScreen.handle_events(screen, [pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1, pos=ready_rect.center)])

        assert called == ['closed']
        assert screen._config_ready_pressed is False

    def test_invader_swap_own_defender_mode_uses_own_selectable_update(self):
        game = SimpleNamespace(
            mode='conquer',
            player_id=1,
            invader=True,
            advancing_player_id=2,
            pending_defender_selection=False,
            defender_selection_dialogue_shown=False,
            pending_conquer_own_defender_selection=False,
            conquer_own_defender_selection_shown=False,
            civil_war_defender_second=True,
            cached_active_spells=[{
                'spell_name': 'Invader Swap',
                'effect_data': {
                    'conquer_invader_swap': True,
                    'old_invader_id': 1,
                },
            }],
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        calls = []
        field = SimpleNamespace(
            defender_selection_mode=False,
            conquer_own_defender_mode=False,
            _update_defender_selectable=lambda: calls.append('opponent'),
            _update_conquer_own_defender_selectable=lambda: calls.append('own'),
            _reset_defender_selectable=lambda: calls.append('reset'),
        )
        screen.subscreens['field'] = field

        ConquerGameScreen._sync_conquer_action_modes(screen)

        assert field.conquer_own_defender_mode is True
        assert calls == ['own']

    def test_own_defender_selectability_excludes_first_civil_war_pick(self):
        from game.screens.field_screen import FieldScreen

        def figure(fig_id, *, player_id=1, color='offensive', field='village'):
            return SimpleNamespace(
                id=fig_id,
                player_id=player_id,
                name=f'Figure {fig_id}',
                family=SimpleNamespace(color=color, field=field),
            )

        first = figure(20)
        second = figure(21)
        wrong_color = figure(22, color='defensive')
        opponent = figure(23, player_id=2)
        icons = [
            SimpleNamespace(
                figure=f,
                has_deficit=False,
                defender_selectable=None,
                in_defender_selection_mode=False,
            )
            for f in (first, second, wrong_color, opponent)
        ]
        field = FieldScreen.__new__(FieldScreen)
        field.game = SimpleNamespace(
            player_id=1,
            battle_modifier=[{'type': 'Civil War'}],
            defending_figure_id=20,
            civil_war_defender_second=True,
            civil_war_required_color='offensive',
        )
        field.figure_icons = icons

        FieldScreen._update_conquer_own_defender_selectable(field)

        assert [icon.defender_selectable for icon in icons] == [False, True, False, False]

    def test_own_defender_selectability_includes_fortress_and_alternates(self):
        from game.screens.field_screen import FieldScreen

        fortress = SimpleNamespace(
            id=30,
            player_id=1,
            name='Stone Fortress',
            family=SimpleNamespace(color='defensive', field='military'),
            cannot_attack=True,
            must_be_attacked=True,
        )
        normal = SimpleNamespace(
            id=31,
            player_id=1,
            name='Himalaya King',
            family=SimpleNamespace(color='defensive', field='castle'),
        )
        deficit_fortress = SimpleNamespace(
            id=32,
            player_id=1,
            name='Deficit Fortress',
            family=SimpleNamespace(color='defensive', field='military'),
            cannot_attack=True,
            must_be_attacked=True,
        )
        opponent = SimpleNamespace(
            id=33,
            player_id=2,
            name='Opponent',
            family=SimpleNamespace(color='offensive', field='village'),
        )
        icons = [
            SimpleNamespace(
                figure=figure,
                has_deficit=(figure.id == 32),
                defender_selectable=None,
                in_defender_selection_mode=False,
            )
            for figure in (fortress, normal, deficit_fortress, opponent)
        ]
        field = FieldScreen.__new__(FieldScreen)
        field.game = SimpleNamespace(
            player_id=1,
            battle_modifier=[],
            defending_figure_id=None,
            civil_war_defender_second=False,
            civil_war_required_color=None,
        )
        field.figure_icons = icons

        FieldScreen._update_conquer_own_defender_selectable(field)

        assert [icon.defender_selectable for icon in icons] == [True, True, False, False]

    def test_battle_result_attack_failed_is_shown_once(self):
        from game.screens.battle_screen import BattleScreen

        game = SimpleNamespace(
            player_id=1,
            invader=True,
            cached_active_spells=[],
            _conquer_result_dialogue_shown=False,
        )
        battle = BattleScreen.__new__(BattleScreen)
        battle.game = game
        battle.window = pygame.Surface((100, 100))
        shown = []

        def fake_dialogue(message, actions, icon, title, images=None):
            shown.append({
                'message': message,
                'actions': actions,
                'icon': icon,
                'title': title,
                'images': images,
            })

        battle.make_dialogue_box = fake_dialogue

        result = {
            'attacker_won': False,
            'conquer_result': 'defender_won',
            'conquer_attacker_player_id': 1,
        }

        BattleScreen._handle_conquer_end(battle, result)
        BattleScreen._handle_conquer_end(battle, result)

        assert len(shown) == 1
        assert shown[0]['title'] == 'Attack Failed'
        assert 'defender held their ground' not in shown[0]['message'].lower()
        assert game._conquer_result_dialogue_shown is True


class TestConquerSubscreenLayout:
    def test_field_compartments_translate_with_conquer_subscreen_origin(self):
        from config import settings
        from game.screens.field_screen import FieldScreen

        ConquerGameScreen, conquer = _base_conquer_screen()
        sub_x, sub_y = ConquerGameScreen._conquer_subscreen_origin(conquer)

        field = FieldScreen.__new__(FieldScreen)
        field._layout_offset_x = sub_x - settings.SUB_SCREEN_X
        field._layout_offset_y = sub_y - settings.SUB_SCREEN_Y

        FieldScreen.init_field_compartments(field)

        assert field.compartments['self']['castle'].topleft == (
            settings.FIELD_SELF_X + field._layout_offset_x,
            settings.FIELD_Y + field._layout_offset_y,
        )

        bg_rect = pygame.Rect(
            sub_x, sub_y,
            settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH,
            settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT,
        )
        all_compartments = [
            rect
            for player in field.compartments.values()
            for rect in player.values()
        ]
        layout_rect = all_compartments[0].unionall(all_compartments[1:])

        assert bg_rect.contains(layout_rect)

    def test_tactics_hand_field_uses_unified_battlefield_columns(self):
        from config import settings
        from game.components.conquer_layout import compute_conquer_layout
        from game.screens.field_screen import FieldScreen

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_round=0,
            battle_turn_player_id=None,
            last_battle_result=None,
        )
        field = FieldScreen.__new__(FieldScreen)
        field.game = game
        field._layout_offset_x = 0
        field._layout_offset_y = 0

        FieldScreen.init_field_compartments(field)

        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode='pre_battle',
        )
        assert field.compartments['self']['castle'] == pygame.Rect(
            layout.battlefield.columns.you_castle)
        assert field.compartments['opponent']['castle'] == pygame.Rect(
            layout.battlefield.columns.opp_castle)
        assert layout.tactics_rail.rect[0] + layout.tactics_rail.rect[2] <= layout.battlefield.rect[0]

    def test_tactics_hand_battle_field_identifies_fighters_and_sources(self):
        from game.screens.field_screen import FieldScreen

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=1,
            battle_round=1,
            player_id=1,
            advancing_figure_id=10,
            advancing_figure_id_2=None,
            defending_figure_id=20,
            defending_figure_id_2=None,
            last_battle_result=None,
            conquer_tactics=[{
                'status': 'played',
                'played_round': 0,
                'call_figure_id': 30,
            }],
        )
        field = FieldScreen.__new__(FieldScreen)
        field.game = game
        field.state = SimpleNamespace(parent_screen=None)

        attacker = SimpleNamespace(id=10, player_id=1)
        defender = SimpleNamespace(id=20, player_id=2)
        called = SimpleNamespace(id=30, player_id=1)
        support = SimpleNamespace(id=40, player_id=1, buffs_allies=True)
        plain = SimpleNamespace(id=50, player_id=1)

        assert FieldScreen._is_tactics_hand_battle_fighter(field, attacker) is True
        assert FieldScreen._is_tactics_hand_battle_fighter(field, defender) is True
        # Persistent 'called' ring was retired — the support lane already
        # surfaces called figures, so the field icon no longer rings them.
        assert FieldScreen._conquer_battle_context_kind(field, called) is None
        assert FieldScreen._conquer_battle_context_kind(field, support) is None
        assert FieldScreen._conquer_battle_context_kind(field, plain) is None

    def test_tactics_hand_battle_field_identifies_preview_called_source(self):
        from game.screens.field_screen import FieldScreen

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=1,
            battle_round=1,
            player_id=1,
            advancing_figure_id=10,
            defending_figure_id=20,
            last_battle_result=None,
            conquer_tactics=[],
        )
        preview = {
            'status': 'available',
            'played_round': None,
            'call_figure_id': 60,
        }
        parent = SimpleNamespace(
            request_conquer_figure_confirmation=lambda *_args, **_kwargs: None,
            _tactics_rail=SimpleNamespace(preview_move=lambda: preview),
        )
        field = FieldScreen.__new__(FieldScreen)
        field.game = game
        field.state = SimpleNamespace(parent_screen=parent)

        source = SimpleNamespace(id=60, player_id=1)

        assert FieldScreen._conquer_battle_context_kind(field, source) == 'preview'

    def test_tactics_hand_battle_context_overlay_draws_rings(self):
        from config import settings
        from game.screens.field_screen import FieldScreen

        window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        window.fill((0, 0, 0))
        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=1,
            battle_round=1,
            player_id=1,
            advancing_figure_id=10,
            defending_figure_id=20,
            last_battle_result=None,
            conquer_tactics=[],
        )
        field = FieldScreen.__new__(FieldScreen)
        field.window = window
        field.game = game
        support = SimpleNamespace(id=40, player_id=1, buffs_allies=True)

        class Parent:
            def request_conquer_figure_confirmation(self):
                return None

            def _conquer_lane_figures(self):
                return [], []

            def _conquer_lane_support_entries(
                    self, _player_figures, _opponent_figures, *, is_player):
                if is_player:
                    return [{
                        'kind': 'buffs_allies',
                        'label': 'Buff',
                        'value': '+4',
                        'figure': support,
                    }]
                return []

        field.state = SimpleNamespace(parent_screen=Parent())
        icon = SimpleNamespace(figure=support)
        field._conquer_hover_source_figure_id = support.id

        FieldScreen._draw_tactics_hand_battle_context_overlays(
            field,
            [(icon, 400, 400)],
        )

        radius = int(settings.FRAME_FIGURE_SCALE * settings.FIGURE_ICON_HEIGHT * 0.56)
        sample = pygame.Rect(400 - radius - 16, 400 - radius - 16,
                             (radius + 16) * 2, (radius + 16) * 2)
        has_ring_pixel = False
        for x in range(sample.left, sample.right, 4):
            for y in range(sample.top, sample.bottom, 4):
                if window.get_at((x, y))[:3] != (0, 0, 0):
                    has_ring_pixel = True
                    break
            if has_ring_pixel:
                break
        assert has_ring_pixel is True

    def test_field_compartments_keep_duel_coordinates_at_default_origin(self):
        from config import settings
        from game.screens.field_screen import FieldScreen

        field = FieldScreen.__new__(FieldScreen)
        field._layout_offset_x = 0
        field._layout_offset_y = 0

        FieldScreen.init_field_compartments(field)

        assert field.compartments['self']['castle'].topleft == (
            settings.FIELD_SELF_X,
            settings.FIELD_Y,
        )

    def test_battle_panels_translate_with_conquer_subscreen_origin(self):
        from config import settings
        from game.screens.battle_screen import BattleScreen

        ConquerGameScreen, conquer = _base_conquer_screen()
        sub_x, sub_y = ConquerGameScreen._conquer_subscreen_origin(conquer)

        battle = BattleScreen.__new__(BattleScreen)
        battle._layout_offset_x = sub_x - settings.SUB_SCREEN_X
        battle._layout_offset_y = sub_y - settings.SUB_SCREEN_Y

        bg_rect = pygame.Rect(
            sub_x, sub_y,
            settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH,
            settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT,
        )

        panel_rects = [
            BattleScreen._battle_panel_rect(battle),
            BattleScreen._figures_panel_rect(battle),
            BattleScreen._rounds_panel_rect(battle),
        ]
        for rect in panel_rects:
            assert bg_rect.contains(rect)

        total_radius = settings.TOTAL_CIRCLE_RADIUS
        total_rect = pygame.Rect(
            BattleScreen._sx(battle, settings.TOTAL_CIRCLE_X) - total_radius,
            BattleScreen._sy(battle, settings.TOTAL_CIRCLE_Y) - total_radius,
            total_radius * 2,
            total_radius * 2,
        )
        finish_rect = pygame.Rect(
            BattleScreen._sx(battle, settings.FINISH_BTN_X) - settings.FINISH_BTN_W // 2,
            BattleScreen._sy(battle, settings.FINISH_BTN_Y),
            settings.FINISH_BTN_W,
            settings.FINISH_BTN_H,
        )

        assert bg_rect.contains(total_rect)
        assert bg_rect.contains(finish_rect)

    def test_battle_panel_helpers_keep_duel_coordinates_at_default_origin(self):
        from config import settings
        from game.screens.battle_screen import BattleScreen

        battle = BattleScreen.__new__(BattleScreen)
        battle._layout_offset_x = 0
        battle._layout_offset_y = 0

        assert BattleScreen._battle_panel_rect(battle).topleft == (
            settings.BATTLE_PANEL_X,
            settings.BATTLE_PANEL_Y,
        )
        assert BattleScreen._battle_panel_icon_center(battle, 2) == (
            settings.BATTLE_PANEL_X + settings.BATTLE_PANEL_W // 2,
            settings.BATTLE_PANEL_ICON_START_Y + 2 * settings.BATTLE_PANEL_ICON_DELTA_Y,
        )


class TestTacticsHandRouting:
    """Phase 9-10 redesign: tactics-hand games never visit ``battle_shop``."""

    def _make_screen(self, *, conquer_move_model='tactics_hand', battle_confirmed=False,
                     battle_moves_phase=False, battle_turn_player_id=None,
                     battle_round=0, last_battle_result=None):
        ConquerGameScreen, screen = _base_conquer_screen(SimpleNamespace(
            mode='conquer',
            conquer_move_model=conquer_move_model,
            battle_confirmed=battle_confirmed,
            battle_turn_player_id=battle_turn_player_id,
            battle_round=battle_round,
            battle_moves_phase=battle_moves_phase,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            pending_battle_ready=False,
            last_battle_result=last_battle_result,
            game_id=1,
            player_id=42,
            opponent_name='Defender',
            land_tier=2,
            land_suit_bonus_suit='Hearts',
            land_suit_bonus_value=2,
        ))
        screen._conquer_left_battle_shop_at = 0
        screen._conquer_collapsed_header_rect = None
        return ConquerGameScreen, screen

    def test_is_tactics_hand_game_true_for_tactics_hand_marker(self):
        ConquerGameScreen, screen = self._make_screen(conquer_move_model='tactics_hand')
        assert ConquerGameScreen._is_tactics_hand_game(screen) is True

    def test_is_tactics_hand_game_false_for_legacy_battle_move_marker(self):
        ConquerGameScreen, screen = self._make_screen(conquer_move_model='battle_move')
        assert ConquerGameScreen._is_tactics_hand_game(screen) is False

    def test_required_tab_never_returns_battle_shop_for_tactics_hand(self):
        ConquerGameScreen, screen = self._make_screen(battle_moves_phase=True)
        tab, _key = ConquerGameScreen._conquer_required_tab(screen)
        assert tab != 'battle_shop'

    def test_required_tab_still_returns_battle_shop_for_legacy_games(self):
        ConquerGameScreen, screen = self._make_screen(
            conquer_move_model='battle_move', battle_moves_phase=True)
        tab, _key = ConquerGameScreen._conquer_required_tab(screen)
        assert tab == 'battle_shop'

    def test_enforce_battle_shop_during_moves_is_noop_for_tactics_hand(self):
        ConquerGameScreen, screen = self._make_screen(battle_moves_phase=True)
        screen.state.subscreen = 'field'
        ConquerGameScreen._enforce_battle_shop_during_moves(screen)
        # Must NOT yank the user onto the (gone) battle_shop subscreen.
        assert screen.state.subscreen == 'field'

    def test_header_uses_full_timeline_before_battle(self):
        ConquerGameScreen, screen = self._make_screen()

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'pre_battle'
        # Tactics-hand games use the persistent two-row header in every
        # mode (pre-battle included) so the top row stays constant.
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is True

    def test_header_collapses_when_battle_turn_starts(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'battle'
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is True

    def test_header_stays_collapsed_for_result_mode(self):
        ConquerGameScreen, screen = self._make_screen(
            last_battle_result={'winner_name': 'Attacker', 'loser_name': 'Defender'},
        )

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'result'
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is True

    def test_tactics_hand_result_dialogue_opens_without_battle_tab_route(self):
        result = {'conquer_result': 'attacker_won', 'attacker_won': True}
        ConquerGameScreen, screen = self._make_screen(last_battle_result=result)
        screen.state.subscreen = 'field'
        calls = []
        screen._handle_conquer_result_response = lambda payload: calls.append(payload)

        ConquerGameScreen._open_tactics_hand_result_dialogue(screen)

        assert calls == [result]
        assert screen.state.subscreen == 'field'

    def test_legacy_games_keep_full_timeline_header_during_battle(self):
        ConquerGameScreen, screen = self._make_screen(
            conquer_move_model='battle_move',
            battle_turn_player_id=42,
            battle_round=1,
        )

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'battle'
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is False

    def test_toggle_opens_and_closes_timeline_overlay(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        screen._conquer_collapsed_header_rect = pygame.Rect(0, 0, 240, 64)

        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is False
        ConquerGameScreen._toggle_conquer_timeline_overlay(screen)
        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is True
        ConquerGameScreen._toggle_conquer_timeline_overlay(screen)
        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is False
        assert screen._conquer_timeline_expanded_rect is None

    def test_open_timeline_overlay_syncs_expanded_rect(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        ConquerGameScreen._toggle_conquer_timeline_overlay(screen)

        ConquerGameScreen._sync_conquer_timeline_hover_state(screen)

        assert ConquerGameScreen._is_conquer_timeline_overlay_open(screen) is True
        assert screen._conquer_timeline_expanded_rect == (
            ConquerGameScreen._conquer_timeline_overlay_rect(screen))

    def test_expanded_timeline_uses_prebattle_content_layout(self):
        from config import settings
        from game.components.conquer_layout import compute_conquer_layout

        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        ConquerGameScreen._toggle_conquer_timeline_overlay(screen)
        ConquerGameScreen._sync_conquer_timeline_hover_state(screen)

        timeline_row = pygame.Rect(
            *ConquerGameScreen._conquer_header_layout(screen).timeline_row_rect
        )
        expanded = ConquerGameScreen._conquer_timeline_overlay_rect(screen)
        pre_header = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode='pre_battle',
        ).header.full_rect
        assert ConquerGameScreen._conquer_effective_layout_mode(screen) == 'pre_battle'
        assert expanded.top == timeline_row.top
        assert expanded.bottom == pre_header[1] + pre_header[3]

    def test_combined_status_label_tracks_active_timeline_step(self):
        from game.screens.conquer_flow import TimelineStep

        ConquerGameScreen, screen = self._make_screen()
        screen._conquer_timeline_panel = SimpleNamespace(
            derive_display_steps=lambda _screen: [TimelineStep(
                kind='prelude_own',
                title='Your Prelude',
                completed=False,
                active=True,
                interactive=False,
                primary_action='next',
            )]
        )

        label = ConquerGameScreen._conquer_combined_status_label(screen)

        assert label == 'Next · Your Prelude'

    def test_battle_timeline_steps_include_round_tactics(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=1,
        )
        you = {
            'id': 11,
            'family_name': 'Dagger',
            'suit': 'Hearts',
            'value': 5,
            'status': 'played',
            'played_round': 0,
        }
        opponent = {
            'id': 21,
            'family_name': 'Shield',
            'suit': 'Clubs',
            'value': 3,
            'status': 'played',
            'played_round': 0,
        }
        screen._current_conquer_tactics = lambda: [you]
        screen._current_conquer_opponent_tactics = lambda: [opponent]

        steps = ConquerGameScreen._conquer_battle_timeline_steps(screen, [])

        # Each round splits into a player + opponent step (in that order).
        kinds = [step.kind for step in steps]
        assert kinds == [
            'battle_round_1_player', 'battle_round_1_opponent',
            'battle_round_2_player', 'battle_round_2_opponent',
        ]
        you_step = steps[0]
        opp_step = steps[1]
        assert you_step.icon_kind == 'tactic'
        assert you_step.icon_payload == {'move': you, 'side': 'you'}
        assert you_step.owner == 'you'
        assert you_step.completed is True
        assert opp_step.icon_payload == {'move': opponent, 'side': 'opp'}
        assert opp_step.owner == 'opp'
        assert opp_step.completed is True
        assert 'You played Dagger' in you_step.info_body
        assert 'Defender played Shield' in opp_step.info_body
        # Round 2 is the active one; battle_round is zero-indexed.
        round2_player = steps[2]
        assert round2_player.active is True
        assert round2_player.completed is False

    def test_collapsed_header_clears_stale_actions_and_exposes_withdraw(self):
        from config import settings

        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        screen._conquer_header_font = settings.get_font(settings.FS_HEADING, bold=True)
        screen._conquer_hint_font = settings.get_font(settings.FS_SMALL)
        screen._conquer_badge_font = settings.get_font(settings.FS_TINY, bold=True)
        screen._conquer_status_font = settings.get_font(settings.FS_SMALL, bold=True)
        screen._conquer_objective_action_rects = {'next': pygame.Rect(1, 1, 10, 10)}
        screen._withdraw_dialogue_open = False
        screen._is_current_player_conquer_attacker = lambda: True

        ConquerGameScreen._draw_conquer_collapsed_header(screen)

        assert 'next' not in screen._conquer_objective_action_rects
        assert 'withdraw' in screen._conquer_objective_action_rects

    def test_tactics_hand_gamble_uses_conquer_tactic_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_GAMBLE

        ConquerGameScreen, screen = self._make_screen()
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.gamble_conquer_tactic',
            lambda game_id, player_id, tactic_id: called.append((game_id, player_id, tactic_id)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.gamble_battle_move',
            lambda *_args: called.append(('legacy',)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_GAMBLE, 'move': {'id': 7}},
        )

        assert called == [(1, 42, 7)]

    def test_tactics_hand_gamble_failure_shows_banner(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_GAMBLE

        ConquerGameScreen, screen = self._make_screen()
        banners = []
        resets = []
        rail = SimpleNamespace(
            _gamble_anim={'move_id': 7},
            reset_after_action=lambda: resets.append(True),
            set_result_banner=lambda *args, **kwargs: banners.append((args, kwargs)),
        )
        screen._tactics_rail = rail
        monkeypatch.setattr(
            'utils.game_service.gamble_conquer_tactic',
            lambda *_args: {
                'success': False,
                'message': 'You can only gamble once per battle round',
            },
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_GAMBLE, 'move': {'id': 7}},
        )

        assert banners[0][0][0] == 'You can only gamble once per battle round'
        assert resets == []
        assert rail._gamble_anim is None

    def test_duel_lane_preview_uses_zero_indexed_round(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=1,
        )
        preview = {'id': 12, 'status': 'available', 'played_round': None}
        screen._tactics_rail = SimpleNamespace(preview_move=lambda: preview)
        player_slots = [
            {'id': 11, 'status': 'played', 'played_round': 0},
            None,
            None,
        ]
        opponent_slots = [
            {'id': 21, 'status': 'played', 'played_round': 0},
            {'id': 22, 'status': 'played', 'played_round': 1},
            None,
        ]

        assert ConquerGameScreen._conquer_lane_focus_round(
            screen, player_slots, opponent_slots) == 1
        assert ConquerGameScreen._conquer_lane_preview_move(
            screen, player_slots, 1) is preview

    def test_tactics_hand_play_starts_flight_animation(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_PLAY

        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        source_rect = pygame.Rect(20, 30, 80, 40)
        screen._tactics_rail = SimpleNamespace(
            reset_after_action=lambda: None,
            move_cell_rect=lambda _move_id: source_rect,
        )
        called = []

        def fake_play(game_id, player_id, tactic_id):
            called.append((game_id, player_id, tactic_id))
            return {'success': True}

        monkeypatch.setattr(
            'utils.game_service.play_conquer_tactic',
            fake_play,
        )
        monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1234)

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {
                'action': ACTION_PLAY,
                'move': {'id': 7, 'family_name': 'Sword', 'value': 9},
            },
        )

        assert called == [(1, 42, 7)]
        animation = screen._tactic_flight_animation
        assert animation['move']['id'] == 7
        assert animation['source'] == source_rect
        assert animation['target'].width > 0
        from config import settings
        from game.components.conquer_layout import compute_conquer_layout
        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode='battle',
        )
        second_round = pygame.Rect(*layout.round_ledger.round_card_rects[1])
        first_round = pygame.Rect(*layout.round_ledger.round_card_rects[0])
        assert second_round.collidepoint(animation['target'].center)
        assert not first_round.collidepoint(animation['target'].center)
        assert animation['started_at'] == 1234

    def test_tactics_hand_dismantle_uses_conquer_tactic_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_DISMANTLE

        ConquerGameScreen, screen = self._make_screen()
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.dismantle_conquer_tactic',
            lambda game_id, player_id, tactic_id: called.append((game_id, player_id, tactic_id)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.dismantle_battle_move',
            lambda *_args: called.append(('legacy',)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_DISMANTLE, 'move': {'id': 8}},
        )

        assert called == [(1, 42, 8)]

    def test_legacy_gamble_still_uses_battle_shop_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_GAMBLE

        ConquerGameScreen, screen = self._make_screen(conquer_move_model='battle_move')
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.gamble_conquer_tactic',
            lambda *_args: called.append(('tactics',)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.gamble_battle_move',
            lambda game_id, player_id, move_id: called.append((game_id, player_id, move_id)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_GAMBLE, 'move': {'id': 9}},
        )

        assert called == [(1, 42, 9)]

    def test_legacy_dismantle_still_uses_battle_shop_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_DISMANTLE

        ConquerGameScreen, screen = self._make_screen(conquer_move_model='battle_move')
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.dismantle_conquer_tactic',
            lambda *_args: called.append(('tactics',)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.dismantle_battle_move',
            lambda game_id, player_id, move_id: called.append((game_id, player_id, move_id)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_DISMANTLE, 'move': {'id': 10}},
        )

        assert called == [(1, 42, 10)]


class TestConquerObjectiveTacticsHand:
    """Objective derivation never aims at battle_shop for tactics-hand."""

    def test_moves_objective_targets_field_for_tactics_hand(self):
        from game.screens.conquer_flow import derive_conquer_objective

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            battle_confirmed=False,
            pending_battle_ready=False,
            advancing_figure_id=None,
            defending_figure_id=None,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            pending_forced_advance=False,
            pending_conquer_prelude_target=False,
            pending_spell_id=None,
            current_round=1,
            game_over=False,
            game_state='active',
            state='active',
            mode_attribute=None,
            last_battle_result=None,
        )
        objective = derive_conquer_objective(
            game=game,
            field_screen=None,
            battle_shop_screen=None,
        )
        assert objective is not None
        assert objective.target_tab == 'field'
        assert objective.primary_action == 'play_tactic'

    def test_battle_objective_targets_field_for_tactics_hand(self):
        from game.screens.conquer_flow import derive_conquer_objective

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=1,
            player_id=42,
            both_battle_moves_ready=False,
            game_over=False,
            pending_game_over=False,
            pending_conquer_prelude_target=False,
            pending_forced_advance=False,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            civil_war_awaiting_second=False,
            civil_war_defender_second=False,
        )
        objective = derive_conquer_objective(
            game=game,
            field_screen=None,
            battle_shop_screen=None,
        )

        assert objective.target_tab == 'field'
        assert objective.primary_action == 'play_tactic'

    def test_moves_objective_targets_battle_shop_for_legacy_games(self):
        from game.screens.conquer_flow import derive_conquer_objective

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='battle_move',
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            battle_confirmed=False,
            pending_battle_ready=False,
            advancing_figure_id=None,
            defending_figure_id=None,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            pending_forced_advance=False,
            pending_conquer_prelude_target=False,
            pending_spell_id=None,
            current_round=1,
            game_over=False,
            game_state='active',
            state='active',
            mode_attribute=None,
            last_battle_result=None,
        )
        objective = derive_conquer_objective(
            game=game,
            field_screen=None,
            battle_shop_screen=SimpleNamespace(bought_moves=[]),
        )
        assert objective is not None
        assert objective.target_tab == 'battle_shop'
