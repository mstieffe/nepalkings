# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the conquer command-layer flow model."""

from types import SimpleNamespace


def test_objective_prefers_pending_panel_confirmation():
    from game.screens.conquer_flow import derive_conquer_objective

    game = SimpleNamespace(mode='conquer', game_over=False)
    field = SimpleNamespace(
        _pending_advance_figure=SimpleNamespace(name='Himalaya Rider'),
        figure_pending_defender_selection=None,
        figure_pending_own_defender_selection=None,
    )

    objective = derive_conquer_objective(game, SimpleNamespace(), field)

    assert objective.phase == 'advance'
    assert objective.primary_action == 'confirm_figure'
    assert 'Himalaya Rider' in objective.headline


def test_objective_guides_prelude_target_to_field():
    from game.screens.conquer_flow import derive_conquer_objective

    game = SimpleNamespace(mode='conquer', game_over=False,
                           pending_conquer_prelude_target=True)
    state = SimpleNamespace(pending_conquer_prelude_target={
        'spell_name': 'Explosion',
        'target_scope': 'opponent',
    })

    objective = derive_conquer_objective(game, state)

    assert objective.phase == 'prelude'
    assert objective.target_tab == 'field'
    assert objective.primary_action == 'select_target'
    assert 'Explosion' in objective.headline


def test_spell_names_from_events_deduplicates_in_order():
    from game.screens.conquer_flow import ConquerEvent, spell_names_from_events

    events = [
        ConquerEvent('a', 'prelude', 'A', spell_names=('Explosion',)),
        ConquerEvent('b', 'defender', 'B', spell_names=('Poison', 'Explosion')),
    ]

    assert spell_names_from_events(events) == ('Explosion', 'Poison')


def test_conquer_screen_converts_info_notification_to_event_without_gating():
    """Prelude receipts populate the spell compartment without gating the flow.

    Reduces log fragmentation: routine receipts (info / good tone) flow into
    the panel without forcing the player to click Next.
    """
    from game.screens.conquer_game_screen import ConquerGameScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(mode='conquer'))
    screen._conquer_events = []
    screen._conquer_event_keys = set()
    screen._conquer_event_seq = 0
    screen._conquer_pending_gate = None
    screen._conquer_gate_queue = []
    screen.dialogue_box = None
    screen.pending_notifications = []

    ConquerGameScreen.queue_or_show_notification(screen, {
        'title': 'Prelude Spell',
        'message': 'Your spell resolved.',
        'actions': ['ok'],
        'phase': 'prelude',
        'tone': 'good',
        'spell_names': ['Poison'],
        'event_key': 'own_prelude:1',
    })

    assert screen.dialogue_box is None
    assert len(screen._conquer_events) == 1
    event = screen._conquer_events[0]
    assert event.spell_names == ('Poison',)
    assert event.spell_side == 'own'
    assert event.spell_role == 'prelude'
    # Gate is NOT armed for routine receipts under the new flow.
    assert screen._conquer_pending_gate is None


def test_conquer_action_notification_does_not_gate():
    """Action-tone notifications route to the event log without blocking flow.

    Selection modes are activated immediately by _sync_conquer_action_modes
    from game state, so the player never has to click a 'Next' button for
    figure-selection steps.
    """
    from game.screens.conquer_game_screen import ConquerGameScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(mode='conquer'))
    screen._conquer_events = []
    screen._conquer_event_keys = set()
    screen._conquer_event_seq = 0
    screen._conquer_pending_gate = None
    screen._conquer_gate_queue = []
    screen.dialogue_box = None
    screen.pending_notifications = []
    screen.subscreens = {'field': SimpleNamespace(
        defender_selection_mode=False,
        conquer_own_defender_mode=False,
        _reset_defender_selectable=lambda: None,
    )}

    ConquerGameScreen.queue_or_show_notification(screen, {
        'title': "Choose Defender",
        'message': 'Pick a defender.',
        'actions': ['got it!'],
        'phase': 'defender',
        'tone': 'action',
    })

    assert screen.dialogue_box is None
    assert screen._conquer_pending_gate is None  # no gate armed
    assert len(screen._conquer_events) == 1      # event still recorded in panel


def test_conquer_selection_mode_activates_without_next_click():
    """Defender selection mode activates immediately — no Next gate needed.

    With the gate removed, _sync_conquer_action_modes can enable
    defender_selection_mode as soon as the game state reflects the
    pending selection, without waiting for a player acknowledgement.
    """
    from game.screens.conquer_game_screen import ConquerGameScreen

    field = SimpleNamespace(
        defender_selection_mode=False,
        conquer_own_defender_mode=False,
        _reset_defender_selectable=lambda: None,
        _update_defender_selectable=lambda: setattr(field, 'update_called', True),
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(
        game=SimpleNamespace(
            mode='conquer',
            pending_defender_selection=True,
            defender_selection_dialogue_shown=True,
            turn=True,
            pending_conquer_own_defender_selection=False,
        ),
        subscreen='battle_shop',
    )
    screen.subscreens = {'field': field, 'battle_shop': SimpleNamespace()}
    screen._conquer_events = []
    screen._conquer_event_keys = set()
    screen._conquer_event_seq = 0
    screen._conquer_pending_gate = None
    screen._conquer_gate_queue = []

    # No gate is active, so _sync_conquer_action_modes runs freely.
    assert screen._conquer_flow_gate_active() is False
    ConquerGameScreen._sync_conquer_action_modes(screen)

    assert field.defender_selection_mode is True


def test_conquer_reset_clears_stale_withdraw_result(monkeypatch):
    from game.screens.conquer_game_screen import ConquerGameScreen

    monkeypatch.setattr(
        'game.screens.game_screen.GameScreen._reset_game_screen_state',
        lambda self: None,
    )
    game = SimpleNamespace(
        mode='conquer',
        state='open',
        game_over=True,
        pending_game_over={'game_over': True},
        game_over_shown=True,
        _conquer_result_dialogue_shown=True,
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=game, pending_conquer_prelude_target='stale')
    screen._last_conquer_auto_route_key = ('battle',)
    screen._conquer_events = [object()]
    screen._conquer_event_keys = {'old'}
    screen._conquer_event_seq = 3
    screen._conquer_pending_confirmation = {'kind': 'advance'}
    screen._conquer_objective_action_rects = {'next_gate': object()}
    screen._conquer_pending_gate = {'key': 'old'}
    screen._conquer_gate_queue = [{'key': 'queued'}]
    screen._withdraw_dialogue_open = True
    screen._last_battle_cycle_key = ('something',)

    ConquerGameScreen._reset_game_screen_state(screen)

    assert game.game_over is False
    assert game.pending_game_over is None
    assert game.game_over_shown is False
    assert game._conquer_result_dialogue_shown is False
    assert screen._conquer_events == []
    assert screen._conquer_pending_gate is None
    assert screen._conquer_gate_queue == []
    assert screen._withdraw_dialogue_open is False
    assert screen._last_battle_cycle_key is None


def test_battle_cycle_reset_clears_panel_state_after_battle_resolves():
    """Once the previous fight's figures clear, conquer events get wiped."""
    from game.screens.conquer_game_screen import ConquerGameScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    game = SimpleNamespace(
        mode='conquer',
        game_id=11,
        advancing_player_id=1,
        advancing_figure_id=42,
        defending_figure_id=7,
        current_round=3,
    )
    screen.state = SimpleNamespace(game=game)
    screen._conquer_events = [object()]
    screen._conquer_event_keys = {'old'}
    screen._conquer_event_seq = 5
    screen._conquer_pending_confirmation = None
    screen._conquer_objective_action_rects = {}
    screen._conquer_pending_gate = None
    screen._conquer_gate_queue = []
    screen._last_conquer_auto_route_key = ('battle',)
    screen._last_battle_cycle_key = None

    # First update: registers the cycle key.
    ConquerGameScreen._check_battle_cycle_reset(screen)
    assert screen._conquer_events  # not yet reset

    # Battle ends: figures cleared.
    game.advancing_figure_id = None
    game.defending_figure_id = None
    ConquerGameScreen._check_battle_cycle_reset(screen)

    assert screen._conquer_events == []
    assert screen._last_conquer_auto_route_key is None


def test_event_spells_by_side_groups_correctly():
    from game.screens.conquer_flow import ConquerEvent, event_spells_by_side

    events = [
        ConquerEvent('a', 'prelude', 'A', spell_names=('Explosion',),
                     spell_side='own', spell_role='prelude'),
        ConquerEvent('b', 'defender', 'B', spell_names=('Mirror',),
                     spell_side='opponent', spell_role='counter'),
        ConquerEvent('c', 'prelude', 'C', spell_names=('Poison',),
                     spell_side='opponent', spell_role='prelude'),
    ]

    grouped = event_spells_by_side(events)

    assert grouped['own'] == ['Explosion']
    # Opponent side preserves the order events arrived in.
    assert grouped['opponent'] == ['Mirror', 'Poison']
    assert grouped['own_roles'] == {'Explosion': 'prelude'}
    assert grouped['opponent_roles'] == {'Mirror': 'counter', 'Poison': 'prelude'}


def test_infer_spell_metadata_from_event_key_prefix():
    from game.screens.conquer_flow import infer_spell_metadata

    side, role = infer_spell_metadata({
        'event_key': 'own_prelude:42',
        'phase': 'prelude',
    })
    assert side == 'own'
    assert role == 'prelude'

    side, role = infer_spell_metadata({
        'event_key': 'opponent_counter:9',
        'title': 'Opponent Counter Spell',
    })
    assert side == 'opponent'
    assert role == 'counter'


def test_conquer_screen_keeps_result_notification_modal():
    from game.screens.conquer_game_screen import ConquerGameScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(mode='conquer'))
    screen._conquer_events = []
    screen._conquer_event_keys = set()
    screen._conquer_event_seq = 0
    screen.dialogue_box = None
    screen.pending_notifications = []
    shown = []

    def fake_make_dialogue_box(**kwargs):
        shown.append(kwargs)
        screen.dialogue_box = object()

    screen.make_dialogue_box = fake_make_dialogue_box

    ConquerGameScreen.queue_or_show_notification(screen, {
        'title': 'Attack Failed',
        'message': 'The defender held.',
        'actions': ['ok'],
        'type': 'game_over',
    })

    assert len(screen._conquer_events) == 0
    assert shown and shown[0]['title'] == 'Attack Failed'


def test_refresh_tabs_locks_battle_until_confirmed():
    from game.screens.conquer_game_screen import ConquerGameScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(
        battle_confirmed=False,
        both_battle_moves_ready=False,
    ))
    screen.field_button = SimpleNamespace(locked=True, locked_clicked=True)
    screen.battle_shop_button = SimpleNamespace(locked=True, locked_clicked=True)
    screen.battle_button = SimpleNamespace(locked=False, locked_clicked=True)

    ConquerGameScreen._refresh_conquer_tab_locks(screen)

    assert screen.field_button.locked is False
    assert screen.battle_shop_button.locked is False
    assert screen.battle_button.locked is True


def test_withdraw_posts_and_routes_to_conquer_result(monkeypatch):
    from game.screens.conquer_game_screen import ConquerGameScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(
        game_id=7,
        player_id=3,
        mode='conquer',
    ))
    screen._conquer_events = []
    screen._conquer_event_keys = set()
    screen._conquer_event_seq = 0
    handled = []

    monkeypatch.setattr('utils.game_service.conquer_withdraw', lambda game_id, player_id: {
        'success': True,
        'conquer_result': 'defender_won',
        'attacker_won': False,
    })
    screen._handle_conquer_result_response = handled.append

    ConquerGameScreen._confirm_withdraw(screen)

    assert handled and handled[0]['conquer_result'] == 'defender_won'
    assert any(event.key == 'withdraw:confirmed' for event in screen._conquer_events)
