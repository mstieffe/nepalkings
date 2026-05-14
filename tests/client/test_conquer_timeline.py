# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the conquer timeline derivation and panel routing."""

from types import SimpleNamespace

import pygame


def _make_game(**overrides):
    base = dict(
        mode='conquer',
        opponent_name='Defender',
        land_id=42,
        land_tier=2,
        land_gold_rate=7.5,
        land_suit_bonus_suit='Mighty',
        land_suit_bonus_value=2,
        cached_active_spells=[],
        pending_conquer_prelude_target=False,
        pending_forced_advance=False,
        pending_defender_selection=False,
        pending_conquer_own_defender_selection=False,
        civil_war_awaiting_second=False,
        civil_war_defender_second=False,
        advancing_figure_id=None,
        defending_figure_id=None,
        advancing_player_id=None,
        battle_confirmed=False,
        battle_turn_player_id=None,
        battle_moves_phase=False,
        waiting_for_counter_response=False,
        game_over=False,
        state='active',
        player_id=1,
        defender_player_id=2,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_state(game):
    return SimpleNamespace(game=game, pending_conquer_prelude_target=None)


def _make_figure(fig_id=10, name='Village Guard', player_id=1):
    return SimpleNamespace(
        id=fig_id,
        name=name,
        player_id=player_id,
        family=SimpleNamespace(
            frame_img=None,
            frame_hidden_img=None,
            frame_closed_img=None,
            icon_img=None,
            icon_img_small=None,
        ),
        cards=[SimpleNamespace(id=1)],
    )


def test_idle_timeline_has_seven_steps_with_overview_active():
    from game.screens.conquer_flow import derive_conquer_timeline

    game = _make_game()
    steps = derive_conquer_timeline(game, _make_state(game), None, None)

    kinds = [s.kind for s in steps]
    # Counter spell step is conditional and only inserted when a counter
    # spell was actually cast.  All other six are always present in order.
    expected = ['overview', 'prelude_own', 'prelude_opp',
                'attacker', 'defender', 'to_battle']
    assert [k for k in kinds if k != 'counter'] == expected
    actives = [s for s in steps if s.active]
    # At most one active step at a time.
    assert len(actives) <= 1


def test_overview_step_has_welcome_land_and_gold_info():
    from game.screens.conquer_flow import derive_conquer_timeline

    game = _make_game(opponent_name='Kathmandu')
    overview = derive_conquer_timeline(game, _make_state(game), None, None)[0]

    assert overview.kind == 'overview'
    assert 'fighting Kathmandu' in overview.info_body
    assert 'Kathmandu' in overview.info_body
    assert '7.5 gold/hour' in overview.info_body
    assert any(a.get('label') == 'Gold/hr' and a.get('value') == '7.5'
               for a in overview.info_assets)


def test_finished_game_freezes_all_steps_completed():
    from game.screens.conquer_flow import derive_conquer_timeline

    game = _make_game(state='finished', game_over=True)
    steps = derive_conquer_timeline(game, _make_state(game), None, None)

    assert all(s.completed for s in steps)
    assert not any(s.active for s in steps)


def test_attacker_step_active_when_advancing_figure_pending():
    from game.screens.conquer_flow import derive_conquer_timeline

    game = _make_game(
        pending_forced_advance=True,
        advancing_figure_id=None,
    )
    steps = derive_conquer_timeline(game, _make_state(game), None, None)

    by_kind = {s.kind: s for s in steps}
    assert by_kind['attacker'].active
    assert not by_kind['defender'].active


def test_no_prelude_steps_show_empty_frames_when_attacker_can_act():
    from game.screens.conquer_flow import derive_conquer_timeline

    game = _make_game(turn=True)
    steps = derive_conquer_timeline(game, _make_state(game), None, None)

    by_kind = {s.kind: s for s in steps}
    assert not by_kind['prelude_own'].active
    assert by_kind['prelude_own'].completed
    assert by_kind['prelude_own'].icon_kind == 'none'
    assert by_kind['prelude_own'].sidenote == 'No prelude'
    assert not by_kind['prelude_opp'].active
    assert by_kind['prelude_opp'].completed
    assert by_kind['prelude_opp'].icon_kind == 'none'
    assert by_kind['prelude_opp'].sidenote == 'No prelude'
    assert by_kind['attacker'].active


def test_own_prelude_uses_spell_assets_instead_of_no_spell_text():
    from game.screens.conquer_flow import derive_conquer_timeline

    drawn = {'id': 101, 'rank': '8', 'suit': 'Hearts', 'value': 8, 'type': 'main'}
    game = _make_game(
        turn=True,
        pending_forced_advance=True,
        conquer_own_prelude_spells=[{
            'spell_name': 'Draw 2 MainCards',
            'effect_data': {
                'drawn_cards': [drawn],
                'cards_drawn': 1,
                'card_type': 'main',
            },
        }],
    )

    steps = derive_conquer_timeline(game, _make_state(game), None, None)
    own = {s.kind: s for s in steps}['prelude_own']

    assert own.completed
    assert own.icon_kind == 'spell'
    assert 'No prelude' not in own.info_headline
    assert 'drew 1 main card' in own.info_body
    assert any(a.get('kind') == 'card' and a.get('reveal') for a in own.info_assets)


def test_forced_deal_prelude_marks_lost_and_gained_cards():
    from game.screens.conquer_flow import derive_conquer_timeline

    lost = [
        {'id': 101, 'rank': '3', 'suit': 'Hearts', 'value': 3, 'type': 'main'},
        {'id': 102, 'rank': '5', 'suit': 'Clubs', 'value': 5, 'type': 'main'},
    ]
    gained = [
        {'id': 201, 'rank': 'K', 'suit': 'Spades', 'value': 13, 'type': 'main'},
        {'id': 202, 'rank': 'A', 'suit': 'Diamonds', 'value': 14, 'type': 'main'},
    ]
    game = _make_game(
        turn=True,
        pending_forced_advance=True,
        conquer_own_prelude_spells=[{
            'spell_name': 'Forced Deal',
            'effect_data': {
                'cards_given': lost,
                'cards_received': gained,
            },
        }],
    )

    steps = derive_conquer_timeline(game, _make_state(game), None, None)
    own = {s.kind: s for s in steps}['prelude_own']
    card_assets = [a for a in own.info_assets if a.get('kind') == 'card']
    lost_assets = [a for a in card_assets if a.get('role') == 'lost']
    gained_assets = [a for a in card_assets if a.get('role') == 'gained']

    assert 'you lost 2 card(s) and gained 2' in own.info_body
    assert len(lost_assets) == 2
    assert len(gained_assets) == 2
    assert all(a.get('crossed') and a.get('dim') and a.get('label') == 'Lost'
               for a in lost_assets)
    assert all(not a.get('crossed') and a.get('label') == 'Gained'
               for a in gained_assets)


def test_sequence_gate_holds_own_then_opponent_prelude_before_attacker():
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from game.screens.conquer_flow import derive_conquer_timeline

    game = _make_game(
        turn=True,
        pending_forced_advance=True,
        conquer_own_prelude_spells=[{'spell_name': 'Draw 2 MainCards'}],
        conquer_opp_prelude_spells=[{'spell_name': 'Fill up to 10'}],
    )
    screen = SimpleNamespace(
        _conquer_acknowledged_step_kinds=set(),
        _conquer_timeline_step_started_at={},
    )
    panel = ConquerTimelinePanel.__new__(ConquerTimelinePanel)

    steps = panel._apply_sequence_gates(
        screen, derive_conquer_timeline(game, _make_state(game), None, None))
    by_kind = {s.kind: s for s in steps}
    assert by_kind['overview'].active

    screen._conquer_acknowledged_step_kinds.add('overview')
    steps = panel._apply_sequence_gates(
        screen, derive_conquer_timeline(game, _make_state(game), None, None))
    by_kind = {s.kind: s for s in steps}
    assert by_kind['prelude_own'].active
    assert not by_kind['prelude_opp'].completed
    assert not by_kind['attacker'].active

    screen._conquer_acknowledged_step_kinds.add('prelude_own')
    steps = panel._apply_sequence_gates(
        screen, derive_conquer_timeline(game, _make_state(game), None, None))
    by_kind = {s.kind: s for s in steps}
    assert by_kind['prelude_opp'].active
    assert not by_kind['attacker'].active

    screen._conquer_acknowledged_step_kinds.add('prelude_opp')
    steps = panel._apply_sequence_gates(
        screen, derive_conquer_timeline(game, _make_state(game), None, None))
    by_kind = {s.kind: s for s in steps}
    assert by_kind['attacker'].active


def test_field_selection_focus_waits_for_matching_timeline_step():
    from game.screens.field_screen import FieldScreen

    game = _make_game(
        mode='conquer',
        pending_forced_advance=True,
        forced_advance_dialogue_shown=True,
    )
    parent = SimpleNamespace(
        active_conquer_timeline_step=lambda: SimpleNamespace(
            kind='prelude_own', interactive=False),
        request_conquer_figure_confirmation=lambda *args, **kwargs: None,
    )
    field = FieldScreen.__new__(FieldScreen)
    field.game = game
    field.state = SimpleNamespace(parent_screen=parent)
    field.defender_selection_mode = False
    field.conquer_own_defender_mode = False

    assert FieldScreen._is_conquer_selection_active(field) is False

    parent.active_conquer_timeline_step = lambda: SimpleNamespace(
        kind='attacker', interactive=True)
    assert FieldScreen._is_conquer_selection_active(field) is True


def test_field_selection_focus_activates_for_civil_war_second_attacker():
    from game.screens.field_screen import FieldScreen

    game = _make_game(civil_war_awaiting_second=True)
    parent = SimpleNamespace(
        active_conquer_timeline_step=lambda: SimpleNamespace(
            kind='attacker', interactive=True),
    )
    field = FieldScreen.__new__(FieldScreen)
    field.game = game
    field.state = SimpleNamespace(parent_screen=parent)
    field.defender_selection_mode = False
    field.conquer_own_defender_mode = False

    assert FieldScreen._is_conquer_selection_active(field) is True


def test_tactics_hand_battle_field_click_opens_view_only_detail(monkeypatch):
    from game.screens.field_screen import FieldScreen

    captured = {}

    class FakeDetailBox:
        def __init__(self, _window, figure, _game, **kwargs):
            self.figure = figure
            captured.update(kwargs)

        def handle_events(self, _events):
            return None

    monkeypatch.setattr('game.screens.field_screen.FigureDetailBox', FakeDetailBox)

    figure = _make_figure()
    game = _make_game(
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_turn_player_id=1,
        battle_round=1,
        civil_war_awaiting_second=True,
    )
    game.action_in_progress = False
    game.calculate_resources = lambda _families: {'gold': 1}
    confirmation_calls = []
    parent = SimpleNamespace(
        waiting_for_counter_response=False,
        request_conquer_figure_confirmation=(
            lambda *args, **kwargs: confirmation_calls.append((args, kwargs))
        ),
    )
    icon = SimpleNamespace(
        figure=figure,
        hovered=True,
        clicked=False,
        is_visible=True,
    )
    field = FieldScreen.__new__(FieldScreen)
    field.window = pygame.Surface((1200, 800))
    field.game = game
    field.state = SimpleNamespace(
        parent_screen=parent,
        pending_spell_cast=None,
        pending_conquer_prelude_target=None,
    )
    field.scroll_text_list_shifter = None
    field._close_rect = pygame.Rect(0, 0, 0, 0)
    field._on_done = None
    field.dialogue_box = None
    field.figure_detail_box = None
    field.figure_icons = [icon]
    field.figures = [figure]
    field.figure_manager = SimpleNamespace(families={})
    field.figure_pending_pickup = None
    field.figure_pending_upgrade = None
    field.figure_pending_defender_selection = None
    field.figure_pending_own_defender_selection = None
    field._pending_advance_figure = None
    field.defender_selection_mode = False
    field.conquer_own_defender_mode = False
    field._force_immediate_redraw = lambda: None

    event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10))
    FieldScreen.handle_events(field, [event])

    assert isinstance(field.figure_detail_box, FakeDetailBox)
    assert captured['conquer_view_only'] is True
    assert field._pending_advance_figure is None
    assert confirmation_calls == []


def test_tactics_hand_battle_field_yes_clears_stale_pending_action():
    from game.screens.field_screen import FieldScreen

    figure = _make_figure()
    game = _make_game(
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_turn_player_id=1,
        battle_round=1,
    )
    game.action_in_progress = False
    field = FieldScreen.__new__(FieldScreen)
    field.game = game
    field.state = SimpleNamespace(
        parent_screen=SimpleNamespace(waiting_for_counter_response=False),
    )
    field.scroll_text_list_shifter = None
    field._close_rect = pygame.Rect(0, 0, 0, 0)
    field._on_done = None
    field.dialogue_box = SimpleNamespace(update=lambda _events: 'yes')
    field.figure_icons = []
    field.figure_pending_pickup = None
    field.figure_pending_upgrade = None
    field.figure_pending_defender_selection = None
    field.figure_pending_own_defender_selection = None
    field._pending_advance_figure = figure

    FieldScreen.handle_events(field, [])

    assert field.dialogue_box is None
    assert field._pending_advance_figure is None


def test_target_required_prelude_adds_hidden_opponent_figure_asset():
    from game.screens.conquer_flow import derive_conquer_timeline

    target = _make_figure(20, 'Secret Defender', player_id=2)
    field = SimpleNamespace(
        figures=[target],
        icon_cache={20: SimpleNamespace(is_visible=False)},
        _pending_advance_figure=None,
        figure_pending_defender_selection=None,
        figure_pending_own_defender_selection=None,
    )
    game = _make_game(
        turn=True,
        conquer_own_prelude_spells=[{
            'spell_name': 'Poison',
            'target_figure_id': 20,
            'effect_data': {'target_figure_id': 20},
        }],
    )

    own = {s.kind: s for s in derive_conquer_timeline(
        game, _make_state(game), field, None)}['prelude_own']
    figure_assets = [a for a in own.info_assets if a.get('kind') == 'figure']

    assert figure_assets
    assert figure_assets[0]['figure'] is target
    assert figure_assets[0]['side'] == 'opponent'
    assert figure_assets[0]['reveal'] is False


def test_opponent_prelude_drawn_cards_are_hidden():
    from game.screens.conquer_flow import derive_conquer_timeline

    drawn = {'id': 201, 'rank': 'K', 'suit': 'Spades', 'value': 13, 'type': 'main'}
    game = _make_game(
        conquer_opp_prelude_spells=[{
            'spell_name': 'Draw 2 MainCards',
            'effect_data': {'drawn_cards': [drawn], 'cards_drawn': 1},
        }],
    )

    opp = {s.kind: s for s in derive_conquer_timeline(
        game, _make_state(game), None, None)}['prelude_opp']
    card_assets = [a for a in opp.info_assets if a.get('kind') == 'card']

    assert card_assets
    assert all(a.get('reveal') is False for a in card_assets)


def test_info_asset_layout_contains_many_mixed_icons():
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from config import settings

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    panel = ConquerTimelinePanel(window)
    rect = pygame.Rect(100, 20, 340, 150)
    assets = [
        {'kind': 'spell', 'name': 'Draw 2 MainCards'},
        {'kind': 'figure', 'figure': _make_figure(), 'side': 'own', 'reveal': True},
        {'kind': 'card', 'card': {'id': 1, 'rank': '7'}, 'reveal': True},
        {'kind': 'card', 'card': {'id': 2, 'rank': '8'}, 'reveal': False},
        {'kind': 'resource', 'label': 'Gold/hr', 'value': '7.5'},
        {'kind': 'resource', 'label': 'Suit bonus', 'value': '+2 Mighty'},
        {'kind': 'spell', 'name': 'Poison'},
        {'kind': 'card', 'card': {'id': 3, 'rank': 'K'}, 'reveal': False},
    ]

    layout = panel._layout_info_asset_rects(
        rect, rect.top + 44, rect.bottom - 38, assets)
    clip = pygame.Rect(
        rect.left + 12,
        rect.top + 44,
        rect.width - 24,
        rect.bottom - 38 - (rect.top + 44),
    )

    assert len(layout) == len(assets)
    for _asset, asset_rect in layout:
        assert clip.contains(asset_rect)


def test_timeline_figure_art_uses_field_frame_icon_ratio():
    from config import settings
    from game.components.conquer_timeline_panel import ConquerTimelinePanel

    family = SimpleNamespace(
        frame_img=pygame.Surface((512, 479), pygame.SRCALPHA),
        frame_hidden_img=pygame.Surface((512, 479), pygame.SRCALPHA),
        frame_closed_img=pygame.Surface((512, 479), pygame.SRCALPHA),
        icon_img_small=pygame.Surface((150, 150), pygame.SRCALPHA),
        icon_img=None,
    )
    figure = SimpleNamespace(family=family)
    slot = pygame.Rect(10, 10, 42, 42)

    _frame_src, frame_rect, _icon_src, icon_rect = (
        ConquerTimelinePanel._figure_art_layout(slot, figure, reveal=True)
    )

    assert slot.contains(frame_rect)
    assert slot.contains(icon_rect)
    assert frame_rect.width < slot.width
    assert frame_rect.height < slot.height
    assert abs((frame_rect.width / icon_rect.width) - settings.FRAME_FIGURE_SCALE) < 0.08


def test_timeline_bubble_hover_records_step_info(monkeypatch):
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from game.screens.conquer_flow import TimelineStep

    panel = ConquerTimelinePanel(pygame.Surface((1200, 800)))
    rect = pygame.Rect(100, 30, 140, 120)
    step = TimelineStep(
        kind='prelude_own',
        title='Your Prelude',
        icon_kind='spell',
        icon_payload='Poison',
        completed=True,
        info_headline='You cast Poison',
        info_body='Poison: target receives -6 battle power.',
        info_assets=({'kind': 'spell', 'name': 'Poison'},),
    )
    screen = SimpleNamespace()

    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: rect.center)

    panel._draw_bubble(screen, rect, step, is_active=False)

    assert panel._step_hover == (step, rect)


def test_step_hover_replaces_icon_name_tooltip():
    from game.components.conquer_timeline_panel import ConquerTimelinePanel

    panel = ConquerTimelinePanel.__new__(ConquerTimelinePanel)
    panel._step_hover = ('step', 'step-anchor')
    panel._spell_hover = ('Poison', 'spell-anchor')
    panel._figure_hover = ('figure', 'figure-anchor', 'own')
    calls = []

    panel._draw_step_info_tooltip = lambda *args: calls.append(('step', args))
    panel._draw_spell_tooltip = lambda *args: calls.append(('spell', args))
    panel._draw_figure_tooltip = lambda *args: calls.append(('figure', args))

    panel._draw_hover_tooltips(SimpleNamespace())

    assert calls == [('step', (SimpleNamespace(), 'step', 'step-anchor'))]


def test_conquer_screen_draws_timeline_hover_after_buttons():
    from game.screens.conquer_game_screen import ConquerGameScreen

    draw_order = []

    class FakePanel:
        def draw(self, _screen):
            draw_order.append('timeline')

        def draw_hover_tooltips(self, _screen):
            draw_order.append('timeline-hover')

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((1200, 800))
    screen.state = SimpleNamespace(
        game=SimpleNamespace(mode='conquer'),
        subscreen='field',
    )
    screen.subscreens = {
        'field': SimpleNamespace(draw=lambda: draw_order.append('field')),
    }
    screen._conquer_timeline_panel = FakePanel()
    screen.game_buttons = [SimpleNamespace(
        draw=lambda: draw_order.append('button'),
        draw_hover_text=lambda: draw_order.append('button-hover'),
    )]
    screen.field_button = SimpleNamespace(rect_symbol=pygame.Rect(0, 0, 1, 1))
    screen.battle_button = SimpleNamespace(rect_symbol=pygame.Rect(0, 0, 1, 1))
    screen.waiting_for_counter_response = False
    screen.counter_spell_selector = None
    screen.dialogue_box = None
    screen._ensure_conquer_screen_game = lambda: True
    screen._normalize_conquer_subscreen = lambda: None
    screen._conquer_attention_counts = lambda: {'field': 0, 'battle': 0}
    screen._draw_tab_state = lambda: draw_order.append('tab-state')
    screen._draw_conquer_battle_moves_panel = lambda: draw_order.append('move-panel')

    ConquerGameScreen.render(screen)

    assert draw_order == [
        'field', 'timeline', 'button', 'button-hover', 'tab-state',
        'move-panel', 'timeline-hover',
    ]


def test_tactics_hand_prebattle_draws_single_canvas_without_tabs():
    from game.screens.conquer_game_screen import ConquerGameScreen

    draw_order = []

    class FakePanel:
        def draw(self, _screen):
            draw_order.append('timeline')

        def draw_within(self, _screen, _rect):
            draw_order.append('timeline-within')

        def draw_collapsed_strip(self, _screen, _rect):
            draw_order.append('timeline-strip')

        def draw_hover_tooltips(self, _screen):
            draw_order.append('timeline-hover')

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((1200, 800))
    screen.state = SimpleNamespace(
        game=SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_round=0,
            battle_turn_player_id=None,
            last_battle_result=None,
        ),
        subscreen='field',
    )
    screen.subscreens = {
        'field': SimpleNamespace(draw=lambda: draw_order.append('field')),
    }
    screen._conquer_timeline_panel = FakePanel()
    screen.game_buttons = [SimpleNamespace(
        draw=lambda: draw_order.append('button'),
        draw_hover_text=lambda: draw_order.append('button-hover'),
    )]
    screen._tactics_rail = SimpleNamespace(draw=lambda: draw_order.append('rail'))
    screen._round_ledger = SimpleNamespace(draw=lambda: draw_order.append('ledger'))
    screen.waiting_for_counter_response = False
    screen.counter_spell_selector = None
    screen.dialogue_box = None
    screen._ensure_conquer_screen_game = lambda: True
    # Persistent header collaborators (pre-battle now uses the two-row header).
    screen._draw_conquer_collapsed_header = lambda: draw_order.append('header')
    screen._sync_conquer_timeline_hover_state = lambda: None
    screen._is_conquer_timeline_overlay_open = lambda: False

    ConquerGameScreen.render(screen)

    assert draw_order == [
        'field', 'header', 'rail', 'ledger', 'timeline-hover',
    ]


def test_conquer_battle_move_panel_layout_fits_left_gutter_for_ten_moves():
    from config import settings
    from game.screens.conquer_game_screen import ConquerGameScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    button_x = int(settings.SCREEN_WIDTH * 0.040)
    top = int(settings.SCREEN_HEIGHT * 0.30)
    size = settings.FIELD_BUTTON_WIDTH
    screen.field_button = SimpleNamespace(
        rect_symbol=pygame.Rect(button_x, top, size, size),
        rect_glow=pygame.Rect(button_x - 8, top - 8, size + 16, size + 16),
    )
    screen.battle_button = SimpleNamespace(
        rect_symbol=pygame.Rect(button_x, top + size + 16, size, size),
        rect_glow=pygame.Rect(button_x - 8, top + size + 8, size + 16, size + 16),
    )

    ten = ConquerGameScreen._conquer_battle_moves_panel_layout(screen, 10)
    three = ConquerGameScreen._conquer_battle_moves_panel_layout(screen, 3)
    sub_x, _sub_y = ConquerGameScreen._conquer_subscreen_origin(screen)

    assert ten is not None
    assert three is not None
    assert ten['rect'].right < sub_x
    assert ten['rect'].top > screen.battle_button.rect_glow.bottom
    assert len(ten['icon_rects']) == 10
    assert all(ten['rect'].contains(icon_rect) for icon_rect in ten['icon_rects'])
    assert ten['icon_size'] <= three['icon_size']


def test_collapsed_timeline_strip_uses_larger_icons(monkeypatch):
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from game.screens.conquer_flow import TimelineStep

    panel = ConquerTimelinePanel(pygame.Surface((640, 140)))
    panel.derive_display_steps = lambda _screen: [
        TimelineStep(kind='overview', title='Land', completed=True),
        TimelineStep(kind='attacker', title='Attacker', active=True),
    ]
    drawn = []

    def capture_icon(_screen, rect, _step):
        drawn.append(rect.copy())

    monkeypatch.setattr(panel, '_draw_step_icon', capture_icon)

    panel.draw_collapsed_strip(SimpleNamespace(), pygame.Rect(0, 0, 300, 58))

    assert drawn
    assert max(rect.width for rect in drawn) > 26


def test_expanded_timeline_right_reserve_preserves_full_bottom_border(monkeypatch):
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from game.screens.conquer_flow import TimelineStep

    window = pygame.Surface((1000, 200))
    window.fill((0, 0, 0))
    panel = ConquerTimelinePanel(window)
    rect = pygame.Rect(20, 20, 900, 120)
    right_reserve = 140
    panel.derive_display_steps = lambda _screen: [
        TimelineStep(kind='overview', title='Land', completed=True),
        TimelineStep(kind='attacker', title='Attacker', completed=True),
        TimelineStep(
            kind='defender',
            title='Defender',
            active=True,
            info_headline='Choose Defender',
            info_body='Waiting for the defender slot.',
        ),
    ]
    bubble_rects = []
    info_rects = []

    def capture_bubble(_screen, bubble_rect, _step, _is_active):
        bubble_rects.append(bubble_rect.copy())

    def capture_info(_screen, info_rect, *_args):
        info_rects.append(info_rect.copy())

    monkeypatch.setattr(panel, '_draw_bubble', capture_bubble)
    monkeypatch.setattr(panel, '_draw_info_box', capture_info)

    panel.draw_within(SimpleNamespace(), rect, right_reserve=right_reserve)

    content_limit = rect.right - right_reserve
    assert bubble_rects
    assert info_rects
    assert all(bubble_rect.right <= content_limit for bubble_rect in bubble_rects)
    assert all(info_rect.right <= content_limit for info_rect in info_rects)
    assert window.get_at((rect.right - 2, rect.bottom - 1))[:3] == (189, 149, 75)


def test_step_info_tooltip_draws_step_assets(monkeypatch):
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from game.screens.conquer_flow import TimelineStep

    panel = ConquerTimelinePanel(pygame.Surface((1200, 800)))
    assets = (
        {'kind': 'spell', 'name': 'Poison'},
        {'kind': 'resource', 'label': 'Battle power', 'value': '-6', 'tone': 'bad'},
    )
    step = TimelineStep(
        kind='counter',
        title='Counter Spell',
        icon_kind='spell',
        icon_payload='Poison',
        tone='warning',
        info_headline='Rival cast Poison',
        info_body='Poison: target receives -6 battle power.',
        info_assets=assets,
    )
    drawn_assets = []

    def fake_draw_info_assets(_screen, _rect, _start_y, _bottom_limit, tooltip_assets):
        drawn_assets.extend(tooltip_assets)

    monkeypatch.setattr(panel, '_draw_info_assets', fake_draw_info_assets)

    panel._draw_step_info_tooltip(
        SimpleNamespace(state=SimpleNamespace(game=None)),
        step,
        pygame.Rect(100, 30, 140, 120),
    )

    assert drawn_assets == list(assets)


def test_pending_battle_figure_stays_out_of_timeline_bubble_until_confirmed():
    from game.screens.conquer_flow import derive_conquer_timeline

    fig = _make_figure()
    field = SimpleNamespace(
        figures=[fig],
        icon_cache={},
        _pending_advance_figure=fig,
        figure_pending_defender_selection=None,
        figure_pending_own_defender_selection=None,
    )
    game = _make_game(turn=True)

    steps = derive_conquer_timeline(game, _make_state(game), field, None)
    attacker = {s.kind: s for s in steps}['attacker']

    assert attacker.active
    assert attacker.icon_kind == 'none'
    assert attacker.info_assets[0]['kind'] == 'figure'
    assert attacker.info_assets[0]['reveal'] is True


def test_counter_spell_step_appears_between_attacker_and_defender_after_cast():
    from game.screens.conquer_flow import derive_conquer_timeline

    attacker = _make_figure(10, 'Own Attacker', player_id=1)
    field = SimpleNamespace(
        figures=[attacker],
        icon_cache={},
        _pending_advance_figure=None,
        figure_pending_defender_selection=None,
        figure_pending_own_defender_selection=None,
    )
    game = _make_game(
        opponent_name='Rival',
        advancing_figure_id=10,
        advancing_player_id=1,
        cached_active_spells=[{
            'id': 88,
            'player_id': 2,
            'spell_name': 'Poison',
            'target_figure_id': 10,
            'effect_data': {
                'counter_origin': True,
                'counter_status': 'executed',
                'target_figure_id': 10,
                'target_figure_name': 'Own Attacker',
            },
        }],
    )

    steps = derive_conquer_timeline(game, _make_state(game), field, None)
    kinds = [s.kind for s in steps]
    counter = {s.kind: s for s in steps}['counter']

    assert kinds.index('attacker') < kinds.index('counter') < kinds.index('defender')
    assert counter.owner == 'Rival'
    assert counter.icon_kind == 'spell'
    assert counter.icon_payload == 'Poison'
    assert counter.completed is True
    assert counter.active is False
    assert 'Poison' in counter.info_headline
    assert 'receives -6 battle power' in counter.info_body
    assert [a.get('kind') for a in counter.info_assets[:2]] == ['spell', 'figure']


def test_counter_spell_step_stays_hidden_before_cast():
    from game.screens.conquer_flow import derive_conquer_timeline

    game = _make_game(
        advancing_figure_id=10,
        advancing_player_id=1,
        waiting_for_counter_response=True,
        cached_active_spells=[],
    )

    steps = derive_conquer_timeline(game, _make_state(game), None, None)

    assert 'counter' not in [s.kind for s in steps]


def test_blitzkrieg_modifier_spell_appears_in_counter_slot_after_attacker():
    from game.screens.conquer_flow import derive_conquer_timeline

    attacker = _make_figure(10, 'Own Attacker', player_id=1)
    field = SimpleNamespace(
        figures=[attacker],
        icon_cache={},
        _pending_advance_figure=None,
        figure_pending_defender_selection=None,
        figure_pending_own_defender_selection=None,
    )
    game = _make_game(
        opponent_name='Rival',
        advancing_figure_id=10,
        advancing_player_id=1,
        battle_modifier=[{'type': 'Blitzkrieg', 'caster_id': 1, 'spell_id': 45}],
        cached_active_spells=[{
            'id': 45,
            'player_id': 1,
            'spell_name': 'Blitzkrieg',
            'effect_data': {'prelude_origin': True},
        }],
    )

    steps = derive_conquer_timeline(game, _make_state(game), field, None)
    kinds = [s.kind for s in steps]
    counter = {s.kind: s for s in steps}['counter']

    assert kinds.index('attacker') < kinds.index('counter') < kinds.index('defender')
    assert counter.owner == 'you'
    assert counter.icon_kind == 'spell'
    assert counter.icon_payload == 'Blitzkrieg'
    assert counter.completed is True
    assert 'Blitzkrieg' in counter.info_headline
    assert 'counter-advance is blocked' in counter.info_body
    assert counter.info_assets[0] == {'kind': 'spell', 'name': 'Blitzkrieg'}


def test_blitzkrieg_counter_slot_falls_back_to_battle_modifier_without_spell_row():
    from game.screens.conquer_flow import derive_conquer_timeline

    game = _make_game(
        opponent_name='Rival',
        advancing_figure_id=10,
        advancing_player_id=2,
        battle_modifier=[{'type': 'Blitzkrieg'}],
        cached_active_spells=[],
    )

    steps = derive_conquer_timeline(game, _make_state(game), None, None)
    counter = {s.kind: s for s in steps}['counter']

    assert counter.owner == 'Rival'
    assert counter.icon_payload == 'Blitzkrieg'
    assert 'attacker chooses the defender' in counter.info_body


def test_blitzkrieg_counter_step_stays_hidden_until_attacker_step_reached():
    from game.components.conquer_timeline_panel import ConquerTimelinePanel

    game = _make_game(
        turn=True,
        battle_modifier=[{'type': 'Blitzkrieg', 'caster_id': 1}],
        cached_active_spells=[{'id': 45, 'player_id': 1, 'spell_name': 'Blitzkrieg'}],
    )
    screen = SimpleNamespace(
        state=_make_state(game),
        subscreens={},
        _conquer_acknowledged_step_kinds={'overview'},
        _conquer_timeline_step_started_at={},
    )
    panel = ConquerTimelinePanel.__new__(ConquerTimelinePanel)

    steps = panel.derive_display_steps(screen)
    by_kind = {s.kind: s for s in steps}

    assert by_kind['attacker'].active
    assert by_kind['counter'].completed is False
    assert by_kind['counter'].active is False


def test_battle_started_timeline_shows_round_steps_without_overview_hold():
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from game.screens.conquer_flow import TimelineStep

    game = _make_game(
        battle_confirmed=True,
        battle_turn_player_id=1,
        battle_round=1,
        advancing_figure_id=10,
        advancing_player_id=1,
        defending_figure_id=20,
    )
    screen = SimpleNamespace(
        state=_make_state(game),
        subscreens={},
        _conquer_acknowledged_step_kinds=set(),
        _conquer_timeline_step_started_at={},
    )
    screen._conquer_battle_timeline_steps = lambda steps: steps + [TimelineStep(
        kind='battle_round_1_player',
        title='R1 You',
        icon_kind='tactic',
        active=True,
    )]
    panel = ConquerTimelinePanel.__new__(ConquerTimelinePanel)

    steps = panel.derive_display_steps(screen)
    by_kind = {step.kind: step for step in steps}

    assert by_kind['battle_round_1_player'].active is True
    assert by_kind['overview'].active is False


def test_civil_war_second_attacker_is_active_and_shows_pending_figure():
    from game.screens.conquer_flow import derive_conquer_timeline

    first = _make_figure(10, 'First Attacker', player_id=1)
    second = _make_figure(11, 'Second Attacker', player_id=1)
    field = SimpleNamespace(
        figures=[first, second],
        icon_cache={},
        _pending_advance_figure=second,
        figure_pending_defender_selection=None,
        figure_pending_own_defender_selection=None,
    )
    game = _make_game(
        turn=True,
        advancing_figure_id=10,
        advancing_player_id=1,
        civil_war_awaiting_second=True,
        civil_war_required_color='offensive',
    )

    steps = derive_conquer_timeline(game, _make_state(game), field, None)
    by_kind = {s.kind: s for s in steps}
    attacker = by_kind['attacker']

    assert attacker.active
    assert attacker.interactive
    assert attacker.primary_action == 'confirm'
    assert attacker.completed is False
    assert 'Civil War' in attacker.sidenote
    assert [a['figure'].id for a in attacker.info_assets if a.get('kind') == 'figure'] == [10, 11]
    assert by_kind['to_battle'].active is False


def test_civil_war_second_defender_is_active_and_shows_pending_own_defender():
    from game.screens.conquer_flow import derive_conquer_timeline

    attacker = _make_figure(10, 'Opponent Attacker', player_id=2)
    first = _make_figure(20, 'First Defender', player_id=1)
    second = _make_figure(21, 'Second Defender', player_id=1)
    field = SimpleNamespace(
        figures=[attacker, first, second],
        icon_cache={},
        _pending_advance_figure=None,
        figure_pending_defender_selection=None,
        figure_pending_own_defender_selection=second,
    )
    game = _make_game(
        advancing_figure_id=10,
        advancing_player_id=2,
        defending_figure_id=20,
        civil_war_defender_second=True,
        civil_war_required_color='offensive',
    )

    steps = derive_conquer_timeline(game, _make_state(game), field, None)
    by_kind = {s.kind: s for s in steps}
    defender = by_kind['defender']

    assert defender.active
    assert defender.interactive
    assert defender.primary_action == 'confirm'
    assert defender.completed is False
    assert defender.sidenote == 'Invader Swap'
    assert [a['figure'].id for a in defender.info_assets if a.get('kind') == 'figure'] == [20, 21]
    assert by_kind['to_battle'].active is False


def test_opponent_battle_figure_remains_hidden_until_revealed():
    from game.screens.conquer_flow import derive_conquer_timeline

    attacker = _make_figure(10, 'Own Attacker', player_id=1)
    defender = _make_figure(20, 'Hidden Defender', player_id=2)
    field = SimpleNamespace(
        figures=[attacker, defender],
        icon_cache={20: SimpleNamespace(is_visible=False)},
        _pending_advance_figure=None,
        figure_pending_defender_selection=None,
        figure_pending_own_defender_selection=None,
    )
    game = _make_game(
        advancing_figure_id=10,
        defending_figure_id=20,
        advancing_player_id=1,
    )

    steps = derive_conquer_timeline(game, _make_state(game), field, None)
    defender_step = {s.kind: s for s in steps}['defender']

    assert defender_step.icon_payload['side'] == 'opponent'
    assert defender_step.icon_payload['reveal'] is False
    assert defender_step.info_assets[0]['reveal'] is False


def test_own_battle_figure_is_always_revealed():
    from game.screens.conquer_flow import derive_conquer_timeline

    opponent_attacker = _make_figure(10, 'Opponent Attacker', player_id=2)
    own_defender = _make_figure(20, 'Own Defender', player_id=1)
    field = SimpleNamespace(
        figures=[opponent_attacker, own_defender],
        icon_cache={20: SimpleNamespace(is_visible=False)},
        _pending_advance_figure=None,
        figure_pending_defender_selection=None,
        figure_pending_own_defender_selection=None,
    )
    game = _make_game(
        advancing_figure_id=10,
        defending_figure_id=20,
        advancing_player_id=2,
    )

    steps = derive_conquer_timeline(game, _make_state(game), field, None)
    defender_step = {s.kind: s for s in steps}['defender']

    assert defender_step.icon_payload['side'] == 'own'
    assert defender_step.icon_payload['reveal'] is True
    assert defender_step.info_assets[0]['reveal'] is True


def test_defender_step_active_when_advancing_resolved():
    from game.screens.conquer_flow import derive_conquer_timeline

    game = _make_game(
        advancing_figure_id=10,
        advancing_player_id=1,
        pending_defender_selection=True,
        defender_selection_dialogue_shown=True,
        turn=True,
    )
    steps = derive_conquer_timeline(game, _make_state(game), None, None)

    by_kind = {s.kind: s for s in steps}
    assert by_kind['attacker'].completed
    assert by_kind['defender'].active


def test_opponent_defender_selected_by_player_gets_timeline_tag():
    from game.screens.conquer_flow import derive_conquer_timeline

    attacker = _make_figure(10, 'Own Attacker', player_id=1)
    defender = _make_figure(20, 'Opponent Defender', player_id=2)
    field = SimpleNamespace(
        figures=[attacker, defender],
        icon_cache={20: SimpleNamespace(is_visible=False)},
        _pending_advance_figure=None,
        figure_pending_defender_selection=None,
        figure_pending_own_defender_selection=None,
    )
    game = _make_game(
        advancing_figure_id=10,
        defending_figure_id=20,
        advancing_player_id=1,
    )

    steps = derive_conquer_timeline(game, _make_state(game), field, None)
    defender_step = {s.kind: s for s in steps}['defender']

    assert defender_step.sidenote == 'Chosen by you'
    assert defender_step.icon_payload['side'] == 'opponent'
    assert defender_step.icon_payload['reveal'] is False
    assert 'You selected this opponent figure' in defender_step.info_body


def test_to_battle_step_active_when_battle_confirmed():
    from game.screens.conquer_flow import derive_conquer_timeline

    game = _make_game(
        advancing_figure_id=10,
        defending_figure_id=20,
        advancing_player_id=1,
        battle_confirmed=True,
        battle_turn_player_id=1,
    )
    steps = derive_conquer_timeline(game, _make_state(game), None, None)

    by_kind = {s.kind: s for s in steps}
    assert by_kind['to_battle'].completed
    assert by_kind['attacker'].completed
    assert by_kind['defender'].completed


class TestConquerNotificationFiltering:
    def test_drops_simple_ok_notifications_in_conquer_mode(self):
        from game.screens.conquer_game_screen import ConquerGameScreen

        screen = ConquerGameScreen.__new__(ConquerGameScreen)
        screen.state = SimpleNamespace(game=_make_game())

        assert ConquerGameScreen._should_drop_conquer_notification(
            screen, {'message': 'hi', 'actions': ['ok']}) is True

    def test_keeps_force_modal_notifications(self):
        from game.screens.conquer_game_screen import ConquerGameScreen

        screen = ConquerGameScreen.__new__(ConquerGameScreen)
        screen.state = SimpleNamespace(game=_make_game())

        assert ConquerGameScreen._should_drop_conquer_notification(
            screen, {'message': 'x', 'force_modal': True}) is False

    def test_keeps_game_over_notifications(self):
        from game.screens.conquer_game_screen import ConquerGameScreen

        screen = ConquerGameScreen.__new__(ConquerGameScreen)
        screen.state = SimpleNamespace(game=_make_game())

        assert ConquerGameScreen._should_drop_conquer_notification(
            screen, {'message': 'x', 'type': 'game_over'}) is False

    def test_keeps_error_notifications(self):
        from game.screens.conquer_game_screen import ConquerGameScreen

        screen = ConquerGameScreen.__new__(ConquerGameScreen)
        screen.state = SimpleNamespace(game=_make_game())

        assert ConquerGameScreen._should_drop_conquer_notification(
            screen, {'title': 'Error', 'message': 'bad', 'actions': ['ok']}) is False

    def test_passes_through_in_duel_mode(self):
        from game.screens.conquer_game_screen import ConquerGameScreen

        screen = ConquerGameScreen.__new__(ConquerGameScreen)
        screen.state = SimpleNamespace(game=SimpleNamespace(mode='duel'))

        assert ConquerGameScreen._should_drop_conquer_notification(
            screen, {'message': 'x', 'actions': ['ok']}) is False


class TestBattleShopSnapBack:
    def _screen(self, **game_overrides):
        from game.screens.conquer_game_screen import ConquerGameScreen

        screen = ConquerGameScreen.__new__(ConquerGameScreen)
        screen.state = SimpleNamespace(
            subscreen='battle_shop',
            game=_make_game(**game_overrides),
        )
        screen._conquer_left_battle_shop_at = 0
        screen.BATTLE_SHOP_SNAPBACK_MS = 0
        return ConquerGameScreen, screen

    def test_no_action_when_not_in_moves_phase(self):
        cls, screen = self._screen(battle_moves_phase=False)
        screen.state.subscreen = 'field'

        cls._enforce_battle_shop_during_moves(screen)

        assert screen.state.subscreen == 'field'

    def test_snaps_back_after_window(self):
        cls, screen = self._screen(battle_moves_phase=True)
        screen.state.subscreen = 'field'

        cls._enforce_battle_shop_during_moves(screen)
        # Second tick after timestamp recorded triggers snap-back.
        cls._enforce_battle_shop_during_moves(screen)

        assert screen.state.subscreen == 'battle_shop'

    def test_keeps_user_on_battle_shop(self):
        cls, screen = self._screen(battle_moves_phase=True)
        screen.state.subscreen = 'battle_shop'

        cls._enforce_battle_shop_during_moves(screen)

        assert screen.state.subscreen == 'battle_shop'
