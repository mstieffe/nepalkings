# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Render smoke tests for the unified conquer tactics UI."""

from types import SimpleNamespace

import pygame


def _move(move_id, *, family='Dagger', suit='Hearts', rank='A', value=5,
          status='available', played_round=None, card_id_b=None, suit_b=None,
          call_figure_id=None):
    return {
        'id': move_id,
        'card_id': move_id + 100,
        'card_id_b': card_id_b,
        'family_name': family,
        'suit': suit,
        'suit_b': suit_b,
        'rank': rank,
        'value': value,
        'status': status,
        'played_round': played_round,
        'call_figure_id': call_figure_id,
        'source': 'config',
    }


def _fighter(fig_id, name, value, player_id, color, *, suit='Hearts',
             field='military', buffs_allies=False, buffs_allies_defence=False,
             blocks_bonus=False, distance_attack=False, battle_bonus=None):
    icon = pygame.Surface((64, 64), pygame.SRCALPHA)
    icon.fill(color)
    frame = pygame.Surface((80, 80), pygame.SRCALPHA)
    pygame.draw.circle(frame, (238, 206, 111), (40, 40), 38, 4)
    return SimpleNamespace(
        id=fig_id,
        name=name,
        player_id=player_id,
        suit=suit,
        field=field,
        value=value,
        number_card=SimpleNamespace(value=value),
        get_value=lambda: value,
        get_battle_bonus=lambda: value if battle_bonus is None else battle_bonus,
        family=SimpleNamespace(
            icon_img=icon,
            icon_img_small=icon,
            frame_img=frame,
            field=field,
        ),
        buffs_allies=buffs_allies,
        buffs_allies_defence=buffs_allies_defence,
        blocks_bonus=blocks_bonus,
        distance_attack=distance_attack,
    )


class _ConquerUiParent:
    def __init__(self, window, game, moves, opp_played=None):
        self.window = window
        self.state = SimpleNamespace(game=game)
        self.subscreens = {
            'battle': SimpleNamespace(opp_played=opp_played or []),
        }
        self._moves = list(moves)

    def _current_conquer_battle_moves(self):
        return list(self._moves)

    def _conquer_battle_move_icon_assets(self, icon_size):
        from config import settings

        return ({}, {}, {}, {}, settings.get_font(max(8, icon_size // 3), bold=True))


def _rect_has_non_background_pixel(surface, rect, background=(0, 0, 0)):
    bounds = pygame.Rect(rect).clip(surface.get_rect())
    step_x = max(1, bounds.width // 12)
    step_y = max(1, bounds.height // 12)
    for x in range(bounds.left, bounds.right, step_x):
        for y in range(bounds.top, bounds.bottom, step_y):
            if surface.get_at((x, y))[:3] != background:
                return True
    return False


def test_conquer_field_halo_rect_tracks_actual_icon_frame_size():
    from game.screens.field_screen import FieldScreen

    icon = SimpleNamespace(
        hovered=False,
        clicked=False,
        rect_frame=pygame.Rect(0, 0, 44, 56),
        rect_frame_big=pygame.Rect(0, 0, 72, 88),
    )

    halo = FieldScreen._conquer_icon_halo_rect(icon, (300, 400), padding=2)

    assert halo.size == (48, 60)
    assert halo.center == (300, 400)

    icon.hovered = True
    halo = FieldScreen._conquer_icon_halo_rect(icon, (300, 400), padding=2)

    assert halo.size == (76, 92)
    assert halo.center == (300, 400)


def test_conquer_selection_marker_sits_on_outward_side_of_figure():
    """Round 12: selection markers sit on the side of the figure facing the
    opposing line — own = right, opponent = left — and never overlap the
    figure frame, so they cannot collide with the figure's info chip."""
    from game.screens.field_screen import FieldScreen

    icon = SimpleNamespace(
        hovered=False,
        clicked=False,
        rect_frame=pygame.Rect(0, 0, 44, 56),
        rect_frame_big=pygame.Rect(0, 0, 72, 88),
    )
    halo = FieldScreen._conquer_icon_halo_rect(icon, (300, 400), padding=0)

    own = FieldScreen._conquer_icon_marker_geometry(icon, (300, 400), is_own=True)
    opp = FieldScreen._conquer_icon_marker_geometry(icon, (300, 400), is_own=False)

    # Side flag matches expected anchoring.
    assert own['side'] == 'right'
    assert opp['side'] == 'left'

    # Bars sit fully outside the frame (no overlap with the figure or its chip).
    assert own['bar_rect'].left >= halo.right
    assert opp['bar_rect'].right <= halo.left

    # Bar is a thin vertical accent (3px wide, ~40% of frame height).
    assert own['bar_rect'].width == 3
    assert own['bar_rect'].height < halo.height
    assert own['bar_rect'].height >= int(halo.height * 0.35)

    # Vertically centered on the figure, so the link line connects cleanly.
    assert own['midpoint'][1] == halo.centery
    assert opp['midpoint'][1] == halo.centery
    # Triangle pin points outward beyond the bar (inward toward figure edge).
    assert min(p[0] for p in own['triangle']) < own['bar_rect'].left
    assert max(p[0] for p in opp['triangle']) > opp['bar_rect'].right
    # The arrowhead is centered on the marker, not pinned to the top edge.
    assert min(p[1] for p in own['triangle']) < own['midpoint'][1]
    assert max(p[1] for p in own['triangle']) > own['midpoint'][1]


def test_conquer_selection_focus_redraws_whole_selectable_icon_without_cutout_box():
    """Target selection dims the field, then redraws selectable icons above
    it. The selectable info box remains crisp, while the old halo-padding
    area is dimmed instead of becoming a rectangular cutout."""
    from game.screens.field_screen import FieldScreen

    surface = pygame.Surface((220, 180))
    background = (60, 60, 70)
    surface.fill(background)

    class DummyIcon:
        def __init__(self, figure_id, selectable, frame_rect, info_rect,
                     frame_color, info_color):
            self.figure = SimpleNamespace(id=figure_id, player_id=1)
            self.selectable = selectable
            self.hovered = False
            self.clicked = False
            self.rect_frame = pygame.Rect(frame_rect)
            self.rect_frame_big = pygame.Rect(frame_rect)
            self.info_rect = pygame.Rect(info_rect)
            self.frame_color = frame_color
            self.info_color = info_color
            self.draw_calls = 0

        def draw(self, x, y):
            self.draw_calls += 1
            pygame.draw.rect(surface, self.frame_color, self.rect_frame)
            pygame.draw.rect(surface, self.info_color, self.info_rect)

    selectable_frame = (210, 170, 70)
    selectable_info = (70, 210, 130)
    other_frame = (170, 70, 70)
    selectable = DummyIcon(
        1, True,
        pygame.Rect(90, 60, 30, 32),
        pygame.Rect(80, 96, 50, 14),
        selectable_frame,
        selectable_info,
    )
    other = DummyIcon(
        2, False,
        pygame.Rect(140, 60, 30, 32),
        pygame.Rect(130, 96, 50, 14),
        other_frame,
        (80, 80, 80),
    )
    drawn_icons = [
        (selectable, selectable.rect_frame.centerx, selectable.rect_frame.centery),
        (other, other.rect_frame.centerx, other.rect_frame.centery),
    ]
    for icon, ix, iy in drawn_icons:
        icon.draw(ix, iy)

    screen = FieldScreen.__new__(FieldScreen)
    screen.window = surface
    screen.game = SimpleNamespace(player_id=1)
    screen._is_conquer_selection_active = lambda: True
    screen._conquer_pending_focus_figure = lambda: None
    screen._icon_is_selectable_for_current_mode = (
        lambda icon: getattr(icon, 'selectable', False))
    screen._draw_conquer_marker = lambda marker, color: None

    cutout = FieldScreen._conquer_icon_halo_rect(
        selectable, selectable.rect_frame.center, padding=4)
    old_cutout_only_point = (selectable.rect_frame.left - 3,
                             selectable.rect_frame.centery)
    assert cutout.collidepoint(old_cutout_only_point)
    assert not selectable.rect_frame.collidepoint(old_cutout_only_point)
    assert surface.get_at(old_cutout_only_point)[:3] == background

    screen._draw_conquer_selection_focus(drawn_icons)

    assert selectable.draw_calls == 2
    assert other.draw_calls == 1
    assert surface.get_at(selectable.rect_frame.center)[:3] == selectable_frame
    assert surface.get_at(selectable.info_rect.center)[:3] == selectable_info
    assert surface.get_at(other.rect_frame.center)[:3] != other_frame
    assert surface.get_at(old_cutout_only_point)[:3] != background


def test_tactics_rail_draws_scrollable_long_tactics_without_blank_output():
    from config import settings
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=1,
        battle_turn_player_id=1,
        last_battle_result=None,
    )
    moves = [
        _move(1, family='Very Long Tactical Dagger Name That Must Clip', rank='A', value=9),
        _move(2, family='Block', suit='Spades', rank='K', value=0),
        _move(3, family='Sword', suit='Clubs', rank='Q', value=7),
        _move(4, family='Shield', suit='Diamonds', rank='J', value=4),
        _move(5, family='Lance', suit='Hearts', rank='10', value=6),
        _move(6, family='Dagger', suit='Diamonds', rank='9', value=5),
        _move(7, family='Double Dagger', suit='Hearts', suit_b='Diamonds',
              rank='8', value=10, card_id_b=207),
    ]
    parent = _ConquerUiParent(window, game, moves)
    rail = ConquerTacticsRail(parent)

    rail.draw()

    layout = rail._ensure_layout().tactics_rail
    assert _rect_has_non_background_pixel(window, rail.rect())
    outside_rail = pygame.Rect(rail.rect().right + 1, rail.rect().top, 8, rail.rect().height)
    assert not _rect_has_non_background_pixel(window, outside_rail)
    # Family headers between groups consume some vertical space, so the
    # rail may render slightly fewer cells than ``cells_visible`` —
    # require at least 1 and no more than the layout slot count.
    assert 1 <= len(rail._cell_rects) <= layout.cells_visible
    # Round 13: groups default to collapsed, so the long hand renders as
    # one row per group + 1-row groups directly. Scroll-down may not be
    # needed at default zoom — but scrolling must still clamp safely.
    rail._scroll = 99
    rail._clamp_scroll()
    assert rail._scroll <= len(moves) - 1
    rail.draw()
    grouped = rail._hand_moves_grouped()
    last_grouped = grouped[-1]
    last_group_label = rail._family_group(last_grouped)
    # The last group's *representative* (strongest) must be visible after
    # the clamp, even when collapsed.
    rep_ids = [m['id'] for m in grouped if rail._family_group(m) == last_group_label]
    assert any(rid in rail._cell_move_ids for rid in rep_ids), (
        f"last group {last_group_label} unreachable after scroll-clamp; "
        f"rendered={rail._cell_move_ids}, scroll={rail._scroll}"
    )
    first_id = rail._cell_move_ids[0]
    assert rail.move_cell_rect(first_id) == rail._cell_rects[0]
    rail._scroll = 0
    rail.draw()
    # Hovering a collapsed-group cell does NOT produce a preview — the
    # cell is meant to be clicked to expand instead.
    first_kind = rail._cell_kinds[0] if rail._cell_kinds else 'move'
    rail._hovered_id = rail._cell_move_ids[0]
    if first_kind == 'collapsed':
        assert rail.preview_move() is None
        # Expand the first collapsed group and re-render so we can hover
        # an actual move row.
        rail._toggle_group(rail._cell_groups[0])
        rail.draw()
        rail._hovered_id = rail._cell_move_ids[0]
        assert rail._cell_kinds[0] == 'move'
    assert rail.preview_move()['id'] == rail._cell_move_ids[0]
    game.battle_turn_player_id = 2
    assert rail.preview_move() is None

    font = settings.get_font(settings.FS_SMALL, bold=True)
    fitted = ConquerTacticsRail._fit_text(
        'Very Long Tactical Dagger Name That Must Clip', font, 80)
    assert font.size(fitted)[0] <= 80
    assert fitted.endswith('...')


def test_tactics_rail_action_buttons_adapt_to_selected_tactic():
    from config import settings
    from game.components.conquer_tactics_rail import (
        ACTION_COMBINE,
        ACTION_DISMANTLE,
        ACTION_GAMBLE,
        ACTION_PLAY,
        ConquerTacticsRail,
    )

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=1,
        battle_turn_player_id=1,
        battle_confirmed=True,
        battle_gamble_counts={},
        last_battle_result=None,
    )
    moves = [
        _move(1, family='Call King', suit='Hearts', rank='K', value=4),
        _move(2, family='Dagger', suit='Hearts', rank='9', value=9),
        _move(3, family='Double Dagger', suit='Hearts', suit_b='Diamonds',
              rank='8+9', value=17, card_id_b=203),
    ]
    rail = ConquerTacticsRail(_ConquerUiParent(window, game, moves))

    rail._selected_id = 1
    rail.draw()
    assert set(rail._action_button_rects) == {ACTION_PLAY, ACTION_GAMBLE}

    rail._selected_id = 2
    rail.draw()
    assert set(rail._action_button_rects) == {ACTION_PLAY, ACTION_GAMBLE, ACTION_COMBINE}

    rail._selected_id = 3
    rail.draw()
    assert set(rail._action_button_rects) == {ACTION_PLAY, ACTION_GAMBLE, ACTION_DISMANTLE}


def test_tactics_rail_header_shows_per_round_gamble_state():
    from config import settings
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer', player_id=1, battle_round=1,
        battle_turn_player_id=1, battle_confirmed=True,
        battle_gamble_counts={'1': {'count': 1, 'rounds': [0]}},
        last_battle_result=None,
    )
    rail = ConquerTacticsRail(
        _ConquerUiParent(window, game, [_move(1), _move(2)]))

    assert rail._top_strip_count_text(game) == (
        '2 tactics · Gamble ready this round')

    game.battle_gamble_counts = {'1': {'count': 2, 'rounds': [0, 1]}}

    assert rail._top_strip_count_text(game) == (
        '2 tactics · Gamble used this round')
    assert 'left' not in rail._top_strip_count_text(game)


def test_tactics_rail_collapses_groups_to_strongest_with_count_chip():
    """Round 13: multi-member family groups collapse by default to a
    single representative (strongest) row tagged with an ×N chip."""
    from config import settings
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer', player_id=1, battle_round=1,
        battle_turn_player_id=1, battle_confirmed=True,
        battle_gamble_counts={}, last_battle_result=None,
    )
    moves = [
        _move(10, family='Buff', suit='Hearts', rank='9', value=4),
        _move(11, family='Buff', suit='Spades', rank='K', value=7),  # strongest Buff
        _move(12, family='Buff', suit='Clubs', rank='J', value=2),
        _move(13, family='Block', suit='Diamonds', rank='10', value=0),
    ]
    rail = ConquerTacticsRail(_ConquerUiParent(window, game, moves))
    rail.draw()

    # Buff group (3 members) collapses; Block group (1 member) stays as-is.
    assert 'collapsed' in rail._cell_kinds
    # The collapsed Buff representative is the strongest (id=11), not the
    # first-listed one (id=10).
    collapsed_idx = rail._cell_kinds.index('collapsed')
    assert rail._cell_groups[collapsed_idx] == 'Buff'
    assert rail._cell_move_ids[collapsed_idx] == 11
    # Block stays expanded (single member).
    assert 'move' in rail._cell_kinds


def test_tactics_rail_click_toggles_group_expand():
    """Round 13: clicking a collapsed cell expands the group; clicking
    again collapses it. Selection is unaffected."""
    from config import settings
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer', player_id=1, battle_round=1,
        battle_turn_player_id=1, battle_confirmed=True,
        battle_gamble_counts={}, last_battle_result=None,
    )
    moves = [
        _move(20, family='Buff', suit='Hearts', rank='9', value=4),
        _move(21, family='Buff', suit='Spades', rank='K', value=7),
        _move(22, family='Buff', suit='Clubs', rank='J', value=2),
    ]
    rail = ConquerTacticsRail(_ConquerUiParent(window, game, moves))
    rail.draw()
    assert rail._cell_kinds == ['collapsed']
    pos = rail._cell_rects[0].center
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    rail.handle_event(event)
    rail.draw()
    # All three Buffs visible after expand; selection unchanged.
    assert rail._cell_kinds == ['move', 'move', 'move']
    assert rail._selected_id is None
    # Toggle back.
    pos = rail._cell_rects[0].center
    rail.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    rail.draw()
    # Clicking an expanded "move" row triggers selection, not collapse.
    # The group stays expanded; we collapse via the dedicated API to
    # verify state transitions still work.
    rail._toggle_group('Buff')
    rail.draw()
    assert rail._cell_kinds == ['collapsed']


def test_tactics_rail_expanded_group_has_collapse_control():
    from config import settings
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer', player_id=1, battle_round=1,
        battle_turn_player_id=1, battle_confirmed=True,
        battle_gamble_counts={}, last_battle_result=None,
    )
    moves = [
        _move(60, family='Buff', suit='Hearts', rank='9', value=4),
        _move(61, family='Buff', suit='Spades', rank='K', value=7),
        _move(62, family='Buff', suit='Clubs', rank='J', value=2),
    ]
    rail = ConquerTacticsRail(_ConquerUiParent(window, game, moves))
    rail._expanded_groups.add('Buff')
    rail.draw()

    assert rail._cell_kinds == ['move', 'move', 'move']
    toggle_rect = rail._cell_group_toggle_rects[0]
    assert toggle_rect is not None

    rail.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=toggle_rect.center))
    rail.draw()

    assert rail._cell_kinds == ['collapsed']
    assert rail._selected_id is None


def test_tactics_rail_auto_expands_dagger_group_for_combine():
    """Round 13: selecting a single Dagger or arming Combine forces the
    Dagger group to expand so partners stay visible even when default-
    collapsed."""
    from config import settings
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer', player_id=1, battle_round=1,
        battle_turn_player_id=1, battle_confirmed=True,
        battle_gamble_counts={}, last_battle_result=None,
    )
    moves = [
        _move(30, family='Dagger', suit='Hearts', rank='9', value=9),
        _move(31, family='Dagger', suit='Diamonds', rank='5', value=5),
        _move(32, family='Dagger', suit='Spades', rank='4', value=4),
    ]
    rail = ConquerTacticsRail(_ConquerUiParent(window, game, moves))
    rail.draw()
    # Default: Dagger group collapsed (3 members > 1).
    assert rail._cell_kinds == ['collapsed']
    # Selecting one of the daggers auto-expands the group.
    rail._selected_id = 30
    rail.draw()
    assert rail._cell_kinds == ['move', 'move', 'move']


def test_tactics_rail_top_strip_wraps_long_banner_into_multiline():
    """Round 13: long banners wrap onto multiple lines instead of being
    truncated, growing the top strip into the hand list (subject to a
    floor of three visible cells)."""
    from config import settings
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer', player_id=1, battle_round=1,
        battle_turn_player_id=1, battle_confirmed=True,
        battle_gamble_counts={}, last_battle_result=None,
    )
    rail = ConquerTacticsRail(
        _ConquerUiParent(window, game, [_move(40, family='Buff', value=3)]))

    long_text = (
        'Forced deal triggered: opponent must reveal a hidden tactic '
        'and you may swap it with one of your own daggers immediately!'
    )
    rail.set_result_banner(long_text, ttl_ms=None)
    rail.draw()

    layout = rail._ensure_layout().tactics_rail
    base_h = pygame.Rect(*layout.top_strip_rect).height
    assert rail._dyn_top_strip_rect is not None
    assert rail._dyn_top_strip_rect.height >= base_h
    # If the message is long enough to need two or more lines, the strip
    # actually grew.
    font = settings.get_font(max(11, int(settings.FS_SMALL * 0.95)), bold=True)
    avail = max(1, rail._dyn_top_strip_rect.width - 16)
    line_count = len(ConquerTacticsRail._wrap_text(long_text, font, avail))
    if line_count >= 2:
        assert rail._dyn_top_strip_rect.height > base_h
    # Hand list never shrinks below three cells.
    assert rail._dyn_hand_list_rect is not None
    assert rail._dyn_hand_list_rect.height >= 3 * layout.cell_height


def test_tactics_rail_banner_can_use_detail_space_before_truncating():
    from config import settings
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer', player_id=1, battle_round=1,
        battle_turn_player_id=1, battle_confirmed=True,
        battle_gamble_counts={}, last_battle_result=None,
    )
    rail = ConquerTacticsRail(
        _ConquerUiParent(window, game, [_move(70, family='Buff', value=3)]))
    long_text = ' '.join([
        'Conquer notification with enough words to require several lines'
        for _ in range(6)
    ])

    rail.set_result_banner(long_text, ttl_ms=None)
    rail.draw()

    layout = rail._ensure_layout().tactics_rail
    top_base = pygame.Rect(*layout.top_strip_rect)
    assert rail._dyn_top_strip_rect.height > top_base.height
    # Long banners are allowed to consume selected-detail space before
    # squeezing the hand list below its three-cell floor.
    assert rail._dyn_top_strip_rect.height >= top_base.height + 2
    assert rail._dyn_hand_list_rect.height >= 3 * layout.cell_height


def test_tactics_rail_action_tray_hides_skip_when_hand_has_moves():
    """Round 13: Skip is removed from the action tray whenever the player
    still has any tactic to play. It only appears when the hand is empty
    and it's the player's battle turn."""
    from config import settings
    from game.components.conquer_tactics_rail import (
        ACTION_PLAY, ACTION_SKIP, ConquerTacticsRail,
    )

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer', player_id=1, battle_round=1,
        battle_turn_player_id=1, battle_confirmed=True,
        battle_gamble_counts={}, last_battle_result=None,
    )
    moves = [_move(50, family='Call', suit='Hearts', rank='K', value=4)]
    rail = ConquerTacticsRail(_ConquerUiParent(window, game, moves))
    rail._selected_id = 50
    rail.draw()
    assert ACTION_SKIP not in rail._action_button_rects
    assert ACTION_PLAY in rail._action_button_rects

    # Empty hand → Skip becomes the sole offered action.
    rail2 = ConquerTacticsRail(_ConquerUiParent(window, game, []))
    rail2.draw()
    assert set(rail2._action_button_rects) == {ACTION_SKIP}


def test_round_ledger_draws_filled_rounds_and_result_click_target():
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=3,
        battle_turn_player_id=1,
        last_battle_result=None,
    )
    moves = [
        _move(11, family='Dagger', suit='Hearts', rank='A', value=5,
              status='played', played_round=0),
        _move(12, family='Block', suit='Spades', rank='K', value=0,
              status='played', played_round=1),
        _move(13, family='Sword', suit='Clubs', rank='Q', value=8,
              status='played', played_round=2),
    ]
    opp_played = [
        _move(21, family='Shield', suit='Clubs', rank='9', value=3, played_round=0),
        _move(22, family='Lance', suit='Diamonds', rank='8', value=7, played_round=1),
        _move(23, family='Dagger', suit='Spades', rank='7', value=4, played_round=2),
    ]
    parent = _ConquerUiParent(window, game, moves, opp_played=opp_played)
    ledger = ConquerRoundLedger(parent)

    ledger.draw()

    assert _rect_has_non_background_pixel(window, ledger.rect())
    assert ledger._total_circle_rect is not None
    assert ledger.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        button=1,
        pos=ledger._total_circle_rect.center,
    )) is None

    game.last_battle_result = {'outcome': 'win'}
    ledger.draw()

    assert ledger.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        button=1,
        pos=ledger._total_circle_rect.center,
    )) == 'open_result'


def test_round_ledger_draws_hover_preview_ghost_math():
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=1,
        battle_turn_player_id=1,
        last_battle_result=None,
    )
    preview = _move(14, family='Sword', suit='Hearts', rank='Q', value=9)
    moves = [
        _move(11, family='Dagger', suit='Hearts', rank='A', value=5,
              status='played', played_round=0),
        preview,
    ]
    opp_played = [
        _move(21, family='Shield', suit='Clubs', rank='9', value=3, played_round=0),
        _move(22, family='Lance', suit='Diamonds', rank='8', value=4, played_round=1),
        None,
    ]
    parent = _ConquerUiParent(window, game, moves, opp_played=opp_played)
    parent._tactics_rail = SimpleNamespace(preview_move=lambda: preview)
    ledger = ConquerRoundLedger(parent)

    you_per = ledger._player_played_per_round()
    opp_per = ledger._opp_played_per_round()
    ghost = ledger._ghost_preview(you_per)

    assert ghost == (1, preview)
    assert ledger._ghost_total_diff(you_per, opp_per, ghost) == 7

    ledger.draw()

    layout = ledger._ensure_layout().round_ledger
    assert _rect_has_non_background_pixel(window, layout.round_card_rects[1])
    assert _rect_has_non_background_pixel(window, layout.total_circle_rect)


def test_round_ledger_derives_conquer_result_labels_without_false_tie():
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        invader_player_id=1,
        battle_round=3,
        battle_turn_player_id=None,
        last_battle_result=None,
    )
    ledger = ConquerRoundLedger(_ConquerUiParent(window, game, []))

    assert ledger._resolved_total_status({
        'conquer_result': 'attacker_won',
        'winner_player_id': 1,
    }, 0)[1] == 'WIN'
    assert ledger._resolved_total_status({
        'conquer_result': 'defender_won',
        'winner_player_id': 2,
    }, 0)[1] == 'LOSE'
    assert ledger._resolved_total_status({
        'winner_name': 'Attacker',
        'loser_name': 'Defender',
    }, 0)[1] == 'DONE'


def test_conquer_effects_rect_projectile_keeps_target_for_impact():
    from game.components.conquer_effects import ConquerEffectsLayer

    window = pygame.Surface((900, 620), pygame.SRCALPHA)
    layer = ConquerEffectsLayer(window, lambda _target_id: None)
    source = pygame.Rect(20, 20, 48, 36)
    target = pygame.Rect(640, 120, 180, 320)

    layer.spawn_spell_to_rect('Dump Cards', source, target, floating_text='redraw')
    started_at = layer._projectiles[0]['started_at']
    layer._draw_projectiles(started_at + layer.PROJECTILE_MS + 1)

    assert not layer._projectiles
    assert layer._impacts
    assert layer._impacts[0]['target_rect'] == target


def test_round_ledger_uses_revealed_opponent_tactics_and_icons(monkeypatch):
    from config import settings
    from game.components import conquer_round_ledger as ledger_module
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=2,
        battle_turn_player_id=1,
        last_battle_result=None,
    )
    moves = [
        _move(11, family='Dagger', suit='Hearts', rank='A', value=5,
              status='played', played_round=0),
    ]
    opponent_move = _move(
        21,
        family='Shield',
        suit='Clubs',
        rank='9',
        value=3,
        status='played',
        played_round=0,
    )
    parent = _ConquerUiParent(window, game, moves, opp_played=[])
    parent._current_conquer_opponent_tactics = lambda: [opponent_move]
    calls = []

    def capture_icon(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(ledger_module, 'draw_battle_move_icon', capture_icon)
    ledger = ConquerRoundLedger(parent)

    assert ledger._opp_played_per_round()[0] == opponent_move

    ledger.draw()

    assert len(calls) >= 2


def test_tactics_hand_field_overlay_does_not_dim_idle_figures():
    from config import settings
    from game.screens.field_screen import FieldScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((255, 255, 255))
    before = window.get_at((100, 100))
    figure = SimpleNamespace(
        id=99,
        player_id=2,
        family=SimpleNamespace(name='Scout'),
    )
    field = FieldScreen.__new__(FieldScreen)
    field.window = window
    field.game = SimpleNamespace(player_id=1)
    field._is_tactics_hand_battle_field_view_only = lambda: True
    field._is_tactics_hand_battle_fighter = lambda _figure: False
    field._conquer_preview_called_figure_ids = lambda: set()
    field._conquer_called_figure_ids = lambda: set()
    field._figure_active_skill_keys = lambda _figure: set()
    field._conquer_hover_source_figure_id = None

    FieldScreen._draw_tactics_hand_battle_context_overlays(
        field,
        [(SimpleNamespace(figure=figure), 100, 100)],
    )

    assert window.get_at((100, 100)) == before


def test_tactics_hand_reveals_opponent_support_sources(monkeypatch):
    from game.screens import field_screen as field_module
    from game.screens.field_screen import FieldScreen

    class FakeFieldFigureIcon:
        def __init__(self, *, figure, is_visible, **_kwargs):
            self.figure = figure
            self.is_visible = is_visible
            self.has_deficit = False
            self.rect_frame = pygame.Rect(0, 0, 40, 48)

        def _calculate_battle_bonus_received(self, _figures):
            return 0

        def _check_resource_deficit(self, _resources):
            return False

    monkeypatch.setattr(field_module, 'FieldFigureIcon', FakeFieldFigureIcon)

    attacker = _fighter(10, 'Attacker', 8, 1, (80, 160, 210), suit='Hearts')
    defender = _fighter(20, 'Defender', 5, 2, (200, 105, 90), suit='Hearts')
    opponent_support = _fighter(
        30,
        'Hidden Support',
        4,
        2,
        (180, 120, 90),
        suit='Hearts',
        field='castle',
    )
    hidden_non_support = _fighter(
        31,
        'Hidden Idle',
        4,
        2,
        (120, 120, 120),
        suit='Spades',
        field='village',
    )

    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_turn_player_id=1,
        player_id=1,
        calculate_resources=lambda *_args, **_kwargs: None,
        has_active_all_seeing_eye=lambda: False,
    )

    class Parent:
        def request_conquer_figure_confirmation(self):
            return None

        def _conquer_lane_figures(self):
            return [attacker], [defender]

        def _conquer_lane_support_entries(self, _player_figures, _opponent_figures, *, is_player):
            if is_player:
                return []
            return [{
                'kind': 'support_bonus',
                'label': 'Support',
                'value': '+4',
                'figure': opponent_support,
            }]

    field = FieldScreen.__new__(FieldScreen)
    field.window = pygame.Surface((200, 200))
    field.game = game
    field.state = SimpleNamespace(parent_screen=Parent())
    field.figure_manager = SimpleNamespace(families={})
    field.categorized_figures = {
        'self': {'military': [attacker], 'village': [], 'castle': []},
        'opponent': {
            'military': [defender],
            'village': [hidden_non_support],
            'castle': [opponent_support],
        },
    }
    field.icon_cache = {}
    field.cached_all_seeing_eye_status = None
    field.last_all_seeing_eye_check = 0
    field.all_seeing_eye_check_interval = 1000

    FieldScreen._generate_figure_icons(field)

    assert field.icon_cache[opponent_support.id].is_visible is True
    assert field.icon_cache[hidden_non_support.id].is_visible is False
    assert FieldScreen._conquer_battle_context_kind(field, opponent_support) is None
    assert FieldScreen._tactics_hand_revealed_support_figure_ids(field) == {opponent_support.id}


def test_round_ledger_hover_completed_round_draws_recap(monkeypatch):
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=2,
        battle_turn_player_id=2,
        last_battle_result=None,
    )
    moves = [
        _move(11, family='Dagger', suit='Hearts', rank='A', value=5,
              status='played', played_round=0),
    ]
    opp_played = [
        _move(21, family='Shield', suit='Clubs', rank='9', value=3, played_round=0),
        None,
        None,
    ]
    parent = _ConquerUiParent(window, game, moves, opp_played=opp_played)
    ledger = ConquerRoundLedger(parent)
    layout = ledger._ensure_layout().round_ledger
    hover_pos = pygame.Rect(*layout.round_card_rects[0]).center
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: hover_pos)

    ledger.draw()

    assert ledger._hover_round_idx == 0
    assert ledger._hover_popover_rect is not None
    assert _rect_has_non_background_pixel(window, ledger._hover_popover_rect)


def test_round_ledger_animates_newly_completed_round_reveal(monkeypatch):
    from config import settings
    from game.components.conquer_round_ledger import ConquerRoundLedger

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    game = SimpleNamespace(
        mode='conquer',
        player_id=1,
        battle_round=2,
        battle_turn_player_id=2,
        last_battle_result=None,
    )
    moves = [
        _move(11, family='Dagger', suit='Hearts', rank='A', value=5,
              status='played', played_round=0),
    ]
    opp_played = [
        _move(21, family='Shield', suit='Clubs', rank='9', value=3, played_round=0),
        None,
        None,
    ]
    parent = _ConquerUiParent(window, game, moves, opp_played=opp_played)
    ledger = ConquerRoundLedger(parent)
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)

    ledger.draw()

    assert 0 in ledger._round_reveal_animations
    layout = ledger._ensure_layout().round_ledger
    assert _rect_has_non_background_pixel(window, layout.round_card_rects[0])

    monkeypatch.setattr(
        pygame.time,
        'get_ticks',
        lambda: 1001 + ConquerRoundLedger.REVEAL_REPLAY_MS,
    )
    ledger.draw()

    assert 0 not in ledger._round_reveal_animations


def test_conquer_duel_lane_draws_current_battle_fighters():
    from config import settings
    from game.components.conquer_layout import compute_conquer_layout
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    attacker = _fighter(10, 'Attacking Guard', 8, 1, (80, 160, 210))
    defender = _fighter(20, 'Defending Guard', 5, 2, (200, 105, 90))
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        player_id=1,
        advancing_player_id=1,
        advancing_figure_id=10,
        defending_figure_id=20,
        advancing_figure_id_2=None,
        defending_figure_id_2=None,
        battle_turn_player_id=1,
        battle_round=1,
        last_battle_result=None,
        opponent_name='Bhaktapur',
        conquer_tactics=[
            _move(11, family='Sword', suit='Hearts', rank='Q', value=8,
                  status='played', played_round=0),
        ],
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {
        'field': SimpleNamespace(figures=[attacker, defender]),
        'battle': SimpleNamespace(opp_played=[
            _move(21, family='Shield', suit='Clubs', rank='9', value=3,
                  status='played', played_round=0),
        ]),
    }

    ConquerGameScreen._draw_conquer_duel_lane(screen)

    lane = compute_conquer_layout(
        settings.SCREEN_WIDTH,
        settings.SCREEN_HEIGHT,
        mode='battle',
    ).battlefield.duel_lane
    player_figures, opponent_figures = ConquerGameScreen._conquer_lane_figures(screen)

    assert player_figures == [attacker]
    assert opponent_figures == [defender]
    assert _rect_has_non_background_pixel(window, lane.rect)
    assert _rect_has_non_background_pixel(window, lane.you_support_badge_rail)
    assert _rect_has_non_background_pixel(window, lane.opp_support_badge_rail)
    assert _rect_has_non_background_pixel(window, lane.diff_band)


def test_conquer_duel_lane_uses_hovered_tactic_as_preview(monkeypatch):
    from config import settings
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    attacker = _fighter(10, 'Attacking Guard', 8, 1, (80, 160, 210))
    defender = _fighter(20, 'Defending Guard', 5, 2, (200, 105, 90))
    preview = _move(11, family='Sword', suit='Hearts', rank='Q', value=9)
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        player_id=1,
        advancing_player_id=1,
        advancing_figure_id=10,
        defending_figure_id=20,
        advancing_figure_id_2=None,
        defending_figure_id_2=None,
        battle_turn_player_id=1,
        battle_round=1,
        last_battle_result=None,
        opponent_name='Bhaktapur',
        conquer_tactics=[preview],
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {
        'field': SimpleNamespace(figures=[attacker, defender]),
        'battle': SimpleNamespace(opp_played=[
            _move(21, family='Shield', suit='Clubs', rank='9', value=3,
                  status='played', played_round=0),
        ]),
    }
    screen._tactics_rail = SimpleNamespace(preview_move=lambda: preview)
    captured = {'diff': None}

    def capture_diff(_self, _rect, _player_figures, _opponent_figures,
                     player_move=None, opponent_move=None, round_idx=0,
                     **_kwargs):
        captured['diff'] = (player_move, opponent_move, round_idx)

    monkeypatch.setattr(ConquerGameScreen, '_draw_conquer_lane_diff', capture_diff)

    assert ConquerGameScreen._conquer_lane_preview_move(
        screen, [None, None, None], 1) == preview

    ConquerGameScreen._draw_conquer_duel_lane(screen)

    assert captured['diff'][0] == preview


def test_conquer_duel_lane_draws_real_support_badges_and_chips(monkeypatch):
    from config import settings
    from game.components.conquer_layout import compute_conquer_layout
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    attacker = _fighter(10, 'Village Guard', 8, 1, (80, 160, 210),
                        suit='Hearts', field='village')
    defender = _fighter(20, 'Defending Guard', 5, 2, (200, 105, 90),
                        suit='Hearts', field='military')
    healer = _fighter(30, 'Djungle Healer', 4, 1, (90, 190, 120),
                      suit='Hearts', field='village', buffs_allies=True)
    archer = _fighter(31, 'Spades Archer', 3, 1, (90, 120, 200),
                      suit='Spades', field='military', distance_attack=True)
    castle_support = _fighter(32, 'King Support', 4, 1, (130, 180, 120),
                              suit='Hearts', field='castle', battle_bonus=4)
    wall = _fighter(40, 'Stone Wall', 6, 2, (180, 140, 110),
                    suit='Clubs', field='military', buffs_allies_defence=True)
    game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        player_id=1,
        opponent_id=2,
        advancing_player_id=1,
        advancing_figure_id=10,
        defending_figure_id=20,
        advancing_figure_id_2=None,
        defending_figure_id_2=None,
        battle_turn_player_id=1,
        battle_round=1,
        last_battle_result=None,
        opponent_name='Bhaktapur',
        land_suit_bonus_suit='Hearts',
        land_suit_bonus_value=2,
        conquer_tactics=[
            _move(11, family='Sword', suit='Hearts', rank='Q', value=8,
                  status='played', played_round=0, call_figure_id=30),
        ],
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {
        'field': SimpleNamespace(
            figures=[attacker, defender, healer, archer, castle_support, wall],
            icon_cache={
                30: SimpleNamespace(rect_frame=pygame.Rect(180, 200, 44, 56)),
                32: SimpleNamespace(rect_frame=pygame.Rect(230, 200, 44, 56)),
            },
            _conquer_hover_source_figure_id=None,
        ),
        'battle': SimpleNamespace(opp_played=[
            _move(21, family='Shield', suit='Clubs', rank='9', value=3,
                  status='played', played_round=0),
        ]),
    }

    player_support = ConquerGameScreen._conquer_lane_support_entries(
        screen, [attacker], [defender], is_player=True)
    opponent_support = ConquerGameScreen._conquer_lane_support_entries(
        screen, [attacker], [defender], is_player=False)

    # 'called' may also appear when the test fixture includes a played
    # tactic with call_figure_id (#1 — show called figures in the lane).
    kinds = [entry['kind'] for entry in player_support]
    assert kinds[:3] == ['support_bonus', 'buffs_allies', 'distance_attack']
    assert set(kinds) - {'support_bonus', 'buffs_allies', 'distance_attack', 'land_bonus', 'called'} == set()
    assert [entry['kind'] for entry in opponent_support] == ['buffs_allies_defence', 'land_bonus']
    player_rows, player_total = ConquerGameScreen._conquer_lane_receipt_components(
        screen,
        [attacker],
        game.conquer_tactics[0],
        player_support,
        opponent_support,
    )
    opponent_rows, opponent_total = ConquerGameScreen._conquer_lane_receipt_components(
        screen,
        [defender],
        screen.subscreens['battle'].opp_played[0],
        opponent_support,
        player_support,
    )

    player_row_values = {(row['label'], row['value']) for row in player_rows}
    opponent_row_values = {(row['label'], row['value']) for row in opponent_rows}
    assert ('Called', 16) in player_row_values
    assert ('Support', 4) in player_row_values
    assert ('Buffs', 4) in player_row_values
    assert ('Land', 2) in player_row_values
    assert ('Wall', 6) in opponent_row_values
    assert ('Land', 2) in opponent_row_values
    assert ('Range', -3) in opponent_row_values
    called_row = next(row for row in player_rows if row['label'] == 'Called')
    support_row = next(row for row in player_rows if row['label'] == 'Support')
    range_row = next(row for row in opponent_rows if row['label'] == 'Range')
    assert called_row['source_figure_ids'] == [healer.id]
    assert support_row['source_figure_ids'] == [castle_support.id]
    assert range_row['source_figure_ids'] == [archer.id]
    assert player_total == 34
    assert opponent_total == 13

    ConquerGameScreen._draw_conquer_duel_lane(screen)

    lane = compute_conquer_layout(
        settings.SCREEN_WIDTH,
        settings.SCREEN_HEIGHT,
        mode='battle',
    ).battlefield.duel_lane
    assert _rect_has_non_background_pixel(window, lane.you_support_badge_rail)
    assert _rect_has_non_background_pixel(window, lane.opp_support_badge_rail)
    assert lane.you_support_chip_rail[2] == 0

    first_badge = screen._conquer_support_badge_rects[0]
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: first_badge['rect'].center)
    hovered = ConquerGameScreen._update_conquer_support_hover_state(screen)
    assert hovered['figure_id'] == castle_support.id
    assert screen.subscreens['field']._conquer_hover_source_figure_id == castle_support.id
    assert ConquerGameScreen._conquer_support_source_rect(screen, castle_support.id) == pygame.Rect(230, 200, 44, 56)

    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: pygame.Rect(230, 200, 44, 56).center)
    hovered = ConquerGameScreen._update_conquer_support_hover_state(screen)
    assert hovered['figure_id'] == castle_support.id
    assert screen.subscreens['field']._conquer_hover_source_figure_id == castle_support.id


def test_conquer_support_and_land_bonus_are_target_suit_specific():
    from game.screens.conquer_game_screen import ConquerGameScreen

    heart_battle = _fighter(10, 'Heart Warrior', 10, 1, (80, 160, 210),
                            suit='Hearts', field='military')
    club_battle = _fighter(11, 'Club Warrior', 8, 1, (80, 160, 210),
                           suit='Clubs', field='military')
    heart_support = _fighter(30, 'Heart King', 4, 1, (90, 190, 120),
                             suit='Hearts', field='castle', battle_bonus=4)
    club_support = _fighter(31, 'Club King', 4, 1, (90, 190, 120),
                            suit='Clubs', field='castle', battle_bonus=4)
    spade_temple = _fighter(40, 'Spades Temple', 5, 2, (200, 105, 90),
                            suit='Spades', field='military', blocks_bonus=True)
    opponent_battle = _fighter(41, 'Opponent Guard', 6, 2, (200, 105, 90),
                               suit='Diamonds', field='military')
    game = SimpleNamespace(
        mode='conquer', conquer_move_model='tactics_hand', player_id=1,
        opponent_id=2, advancing_player_id=1, advancing_figure_id=10,
        defending_figure_id=41, battle_turn_player_id=1, battle_round=1,
        last_battle_result=None, opponent_name='Foes',
        land_suit_bonus_suit='Clubs', land_suit_bonus_value=2,
        conquer_tactics=[],
    )
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = pygame.Surface((1200, 900))
    screen.state = SimpleNamespace(game=game)
    screen.subscreens = {
        'field': SimpleNamespace(
            figures=[heart_battle, club_battle, heart_support, club_support,
                     spade_temple, opponent_battle],
            icon_cache={},
        ),
        'battle': SimpleNamespace(opp_played=[]),
    }

    player_support = ConquerGameScreen._conquer_lane_support_entries(
        screen, [heart_battle, club_battle], [opponent_battle], is_player=True)
    opponent_support = ConquerGameScreen._conquer_lane_support_entries(
        screen, [heart_battle, club_battle], [opponent_battle], is_player=False)

    land_entry = next(entry for entry in player_support
                      if entry['kind'] == 'land_bonus')
    assert land_entry['source_figure_ids'] == []

    block_entry = next(entry for entry in opponent_support
                       if entry['kind'] == 'blocks_bonus')
    assert block_entry['target_figure_ids'] == [heart_battle.id]
    assert block_entry['target_suit'] == 'Hearts'

    heart_total = ConquerGameScreen._conquer_lane_figure_full_power(
        screen, heart_battle, support_entries=player_support,
        enemy_support_entries=opponent_support, is_player=True)
    club_total = ConquerGameScreen._conquer_lane_figure_full_power(
        screen, club_battle, support_entries=player_support,
        enemy_support_entries=opponent_support, is_player=True)

    assert heart_total == 10  # Spades Temple blocks Hearts support only.
    assert club_total == 14   # Clubs support + Clubs land bonus still count.

    rows, total = ConquerGameScreen._conquer_lane_receipt_components(
        screen, [heart_battle, club_battle], None, player_support, opponent_support)
    row_values = {(row['label'], row['value']) for row in rows}
    assert ('Support', 4) in row_values
    assert ('Land', 2) in row_values
    assert ('Blocked', 'support') in row_values
    blocked = next(row for row in rows if row['label'] == 'Blocked')
    support = next(row for row in rows if row['label'] == 'Support')
    assert blocked['source_figure_ids'] == [spade_temple.id]
    assert support['source_figure_ids'] == [club_support.id]
    assert total == 24


def test_conquer_support_entries_mark_blocked_support_bonus_only():
    from game.screens.conquer_game_screen import ConquerGameScreen

    support_entry = {
        'kind': 'support_bonus', 'label': 'Support', 'value': '+4',
        'numeric_value': 4, 'per_target_value': 4,
        'target_figure_ids': [10], 'source_figure_ids': [30],
        'suit': 'Hearts', 'target_suit': 'Hearts',
        'figure': _fighter(30, 'Heart King', 4, 1, (90, 190, 120),
                           suit='Hearts', field='castle'),
    }
    block_entry = {
        'kind': 'blocks_bonus', 'label': 'Block', 'value': 'Block',
        'target_figure_ids': [10], 'source_figure_ids': [40],
        'target_suit': 'Hearts',
        'figure': _fighter(40, 'Spade Temple', 5, 2, (200, 105, 90),
                           suit='Spades', blocks_bonus=True),
    }

    annotated = ConquerGameScreen._annotate_blocked_support_entries(
        [support_entry], [block_entry])
    group = ConquerGameScreen._conquer_support_display_sections(
        ConquerGameScreen.__new__(ConquerGameScreen), annotated)['clash'][0]

    assert group['kind'] == 'support_bonus'
    assert group['blocked_bonus'] is True
    assert group['blocked_full'] is True
    assert group['blocked_value'] == 4
    assert group['unblocked_numeric_value'] == 0
    # The badge still names the support value, but rendering will slash
    # this value chip instead of marking the whole figure as blocked.
    assert group['value'] == '+4'


def test_conquer_block_support_badge_displays_blocked_suit(monkeypatch):
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((180, 120))
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    captured_suits = []

    monkeypatch.setattr(
        ConquerGameScreen,
        '_load_conquer_skill_icon',
        lambda self, key, size: pygame.Surface((size, size), pygame.SRCALPHA),
    )

    def fake_suit_icon(_self, suit, size):
        captured_suits.append(suit)
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        surf.fill((255, 255, 255, 255))
        return surf

    monkeypatch.setattr(ConquerGameScreen, '_load_conquer_suit_icon', fake_suit_icon)

    ConquerGameScreen._draw_conquer_lane_support_badge(
        screen,
        pygame.Rect(40, 30, 52, 52),
        {
            'kind': 'blocks_bonus', 'label': 'Block', 'value': 'Block',
            'target_suit': 'Hearts', 'aggregate_count': 1,
            'figure': _fighter(90, 'Blocker', 4, 2, (200, 105, 90),
                               suit='Spades', blocks_bonus=True),
        },
        is_player=False,
    )

    assert captured_suits == ['Hearts']


def test_conquer_support_rail_overflow_registers_hover_popover(monkeypatch):
    from config import settings
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen._conquer_support_badge_rects = []
    screen._conquer_support_overflow_rects = []
    # Simulate a fully-progressed battle so all four support-rail
    # sections (clash + R1/R2/R3) are rendered and the section split
    # forces a single badge per section + an overflow chip
    # (round 10 #11 only renders sections for rounds that have begun).
    screen.state = SimpleNamespace(game=SimpleNamespace(battle_round=3))
    entries = [
        {'kind': 'support_bonus', 'label': 'Support', 'value': '+4', 'numeric_value': 4,
         'suit': 'Hearts', 'figure': _fighter(100, 'Supporter 0', 4, 1, (90, 150, 120), suit='Hearts')},
        {'kind': 'land_bonus', 'label': 'Land', 'value': '+2', 'numeric_value': 2,
         'suit': 'Hearts', 'figure': None, 'source_figure_ids': [100]},
        {'kind': 'buffs_allies', 'label': 'Buff', 'value': '+4', 'numeric_value': 4,
         'figure': _fighter(101, 'Supporter 1', 4, 1, (90, 150, 120), suit='Hearts')},
        {'kind': 'buffs_allies_defence', 'label': 'Wall', 'value': '+5', 'numeric_value': 5,
         'figure': _fighter(102, 'Supporter 2', 5, 1, (90, 150, 120), suit='Clubs')},
        {'kind': 'blocks_bonus', 'label': 'Block', 'value': 'Block', 'numeric_value': 0,
         'figure': _fighter(103, 'Supporter 3', 4, 1, (90, 150, 120), suit='Spades')},
        {'kind': 'distance_attack', 'label': 'Range', 'value': '-3', 'numeric_value': 3,
         'figure': _fighter(104, 'Supporter 4', 3, 1, (90, 150, 120), suit='Spades')},
    ]
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (0, 0))

    ConquerGameScreen._draw_conquer_lane_support_rail(
        screen,
        pygame.Rect(300, 160, 56, 240),
        entries,
        is_player=True,
    )

    assert len(screen._conquer_support_badge_rects) == 1
    assert len(screen._conquer_support_overflow_rects) == 1
    overflow = screen._conquer_support_overflow_rects[0]
    assert len(overflow['entries']) == len(entries) - 1
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: overflow['rect'].center)
    assert ConquerGameScreen._current_conquer_support_overflow_entry(screen) == overflow
    ConquerGameScreen._draw_conquer_support_overflow_popover(screen)


def test_conquer_call_support_badge_uses_bare_family_art(monkeypatch):
    from config import settings
    from game.screens import conquer_game_screen as module
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    move = _move(15, family='Call Villager', suit='Hearts', value=4)
    calls = []

    def fail_full_icon(*_args, **_kwargs):
        raise AssertionError('support Call badges should not draw full battle move icons')

    monkeypatch.setattr(module, 'draw_battle_move_icon', fail_full_icon)
    monkeypatch.setattr(
        ConquerGameScreen,
        '_draw_conquer_call_family_icon',
        lambda self, rect, drawn_move: calls.append((pygame.Rect(rect), drawn_move)),
    )

    ConquerGameScreen._draw_conquer_lane_support_badge(
        screen,
        pygame.Rect(120, 140, 46, 46),
        {'kind': 'called', 'move': move, 'value': '+12', 'aggregate_count': 1},
        is_player=True,
    )

    assert calls and calls[0][1] == move


def test_conquer_lane_diff_hover_stays_inside_diff_band(monkeypatch):
    from config import settings
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    anchor = pygame.Rect(300, 220, 150, 52)
    player_rows = [
        {'label': 'Base', 'value': 8},
        {'label': 'Support', 'value': 4},
        {'label': 'Total', 'value': 12},
    ]
    opponent_rows = [
        {'label': 'Base', 'value': 5},
        {'label': 'Total', 'value': 5},
    ]

    ConquerGameScreen._draw_conquer_lane_diff_popover(
        screen, anchor, player_rows, 12, opponent_rows, 5, 7)

    assert _rect_has_non_background_pixel(window, anchor)
    assert not _rect_has_non_background_pixel(
        window, pygame.Rect(anchor.left - 32, anchor.top, 24, anchor.height))
    assert not _rect_has_non_background_pixel(
        window, pygame.Rect(anchor.right + 8, anchor.top, 24, anchor.height))


def test_conquer_lane_metadata_uses_active_skill_keys():
    from game.screens.conquer_game_screen import ConquerGameScreen

    figure = _fighter(10, 'Guard', 8, 1, (80, 160, 210),
                      buffs_allies=True, distance_attack=True)
    screen = ConquerGameScreen.__new__(ConquerGameScreen)

    assert ConquerGameScreen._conquer_lane_active_skill_keys(screen, figure) == [
        'buffs_allies',
        'distance_attack',
    ]

    figure.get_active_skill_keys = lambda: ['blocks_bonus', 'missing_skill']
    assert ConquerGameScreen._conquer_lane_active_skill_keys(screen, figure) == [
        'blocks_bonus',
    ]


def test_tactic_flight_overlay_draws_nonblank_pill(monkeypatch):
    from config import settings
    from game.screens.conquer_game_screen import ConquerGameScreen

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    window.fill((0, 0, 0))
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.window = window
    screen._tactic_flight_animation = {
        'move': {'id': 7, 'family_name': 'Sword', 'value': 9},
        'source': pygame.Rect(40, 80, 120, 50),
        'target': pygame.Rect(800, 880, 160, 70),
        'started_at': 1000,
        'duration': ConquerGameScreen.TACTIC_FLIGHT_MS,
    }
    monkeypatch.setattr(pygame.time, 'get_ticks',
                        lambda: 1000 + ConquerGameScreen.TACTIC_FLIGHT_MS // 2)

    ConquerGameScreen._draw_tactic_flight_animation(screen)

    assert screen._tactic_flight_animation is not None
    # Pill travels along (40+120/2,80+50/2)=(100,105) -> (880,915); at the
    # midpoint with ease-out it sits past the middle of the travel arc.
    assert _rect_has_non_background_pixel(window, pygame.Rect(400, 450, 400, 400))

    monkeypatch.setattr(pygame.time, 'get_ticks',
                        lambda: 1000 + ConquerGameScreen.TACTIC_FLIGHT_MS + 50)
    ConquerGameScreen._draw_tactic_flight_animation(screen)

    assert screen._tactic_flight_animation is None


def test_conquer_lane_figure_full_power_includes_modifiers():
    from game.screens.conquer_game_screen import ConquerGameScreen

    fighter = _fighter(10, 'Hero', 8, 1, (200, 200, 200),
                       suit='Hearts', field='village')
    healer = _fighter(20, 'Healer', 4, 1, (90, 190, 120),
                      suit='Hearts', field='village', buffs_allies=True)
    enemy = _fighter(30, 'Foe', 5, 2, (200, 90, 90),
                    suit='Spades', field='military')
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(
        mode='conquer', conquer_move_model='tactics_hand',
        player_id=1, opponent_id=2,
        advancing_player_id=1, advancing_figure_id=10,
        defending_figure_id=30,
        advancing_figure_id_2=None, defending_figure_id_2=None,
        battle_turn_player_id=1, battle_round=1, last_battle_result=None,
        opponent_name='Foes', land_suit_bonus_suit=None,
        land_suit_bonus_value=None, conquer_tactics=[],
    ))
    screen.subscreens = {
        'field': SimpleNamespace(figures=[fighter, healer, enemy], icon_cache={}),
        'battle': SimpleNamespace(opp_played=[]),
    }

    diff = ConquerGameScreen._conquer_lane_figure_diff(screen)
    # Player Hero (8) + buffs from healer (+4) - opponent Foe (5) = 7
    assert diff == 7

    p_support = ConquerGameScreen._conquer_lane_support_entries(
        screen, [fighter], [enemy], is_player=True)
    o_support = ConquerGameScreen._conquer_lane_support_entries(
        screen, [fighter], [enemy], is_player=False)
    full = ConquerGameScreen._conquer_lane_figure_full_power(
        screen, fighter, support_entries=p_support,
        enemy_support_entries=o_support, is_player=True)
    assert full == 12  # 8 + 4 buff


def test_handle_conquer_lane_figure_click_opens_detail_box():
    from game.screens.conquer_game_screen import ConquerGameScreen

    fighter = _fighter(10, 'Hero', 8, 1, (200, 200, 200))
    opened = {'icon': None}

    def opener(icon):
        opened['icon'] = icon

    icon_obj = SimpleNamespace(figure=fighter)
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace())
    screen.subscreens = {
        'field': SimpleNamespace(
            icon_cache={10: icon_obj},
            figure_icons=[icon_obj],
            _open_tactics_hand_battle_detail=opener,
        ),
    }
    screen._conquer_lane_figure_rects = [
        {'rect': pygame.Rect(100, 100, 50, 50), 'figure': fighter, 'is_player': True},
    ]
    handled = ConquerGameScreen._handle_conquer_lane_figure_click(screen, (110, 110))
    assert handled is True
    assert opened['icon'] is icon_obj

    # Outside click does nothing.
    opened['icon'] = None
    assert ConquerGameScreen._handle_conquer_lane_figure_click(screen, (10, 10)) is False
    assert opened['icon'] is None


def test_tactics_rail_gamble_combine_dismantle_enabled_outside_my_turn():
    from game.components.conquer_tactics_rail import (
        ACTION_COMBINE, ACTION_DISMANTLE, ACTION_GAMBLE, ConquerTacticsRail,
    )

    dagger_a = _move(1, family='Dagger', suit='Hearts', rank='3', value=3)
    dagger_b = _move(2, family='Dagger', suit='Diamonds', rank='5', value=5)
    double = _move(3, family='Dagger', suit='Hearts', rank='3', value=8,
                   card_id_b=99, suit_b='Diamonds')
    moves = [dagger_a, dagger_b, double]
    parent = SimpleNamespace(
        window=pygame.Surface((100, 100)),
        state=SimpleNamespace(game=SimpleNamespace(
            battle_turn_player_id=999,  # not my turn
            player_id=1, battle_round=2, last_battle_result=None,
        )),
        _current_conquer_tactics=lambda: list(moves),
    )
    rail = ConquerTacticsRail(parent)

    # Gamble while it's not my turn:
    rail._selected_id = dagger_a['id']
    rail._trigger_action(ACTION_GAMBLE)
    pending = rail.consume_pending_action()
    assert pending and pending['action'] == ACTION_GAMBLE

    # Dismantle a double dagger while it's not my turn:
    rail._selected_id = double['id']
    rail._trigger_action(ACTION_DISMANTLE)
    pending = rail.consume_pending_action()
    assert pending and pending['action'] == ACTION_DISMANTLE

    # Combine two single daggers:
    rail._selected_id = dagger_a['id']
    rail._combine_partner_id = dagger_b['id']
    rail._combine_pending = True
    rail._trigger_action(ACTION_COMBINE)
    pending = rail.consume_pending_action()
    assert pending and pending['action'] == ACTION_COMBINE
    assert pending['partner']['id'] == dagger_b['id']


def test_round_ledger_total_includes_figure_diff():
    from game.components.conquer_round_ledger import ConquerRoundLedger

    parent = SimpleNamespace(
        window=pygame.Surface((100, 100)),
        state=SimpleNamespace(game=SimpleNamespace()),
        _conquer_lane_figure_diff=lambda: 6,
    )
    ledger = ConquerRoundLedger(parent)
    you_per = [_move(1, value=5), None, None]
    opp_per = [_move(2, value=3), None, None]
    total = ledger._total_diff(you_per, opp_per)
    # round1 diff (5-3=2) + figure diff (6) = 8
    assert total == 8


def test_current_conquer_tactics_filters_by_displayed_step(monkeypatch):
    """Spell-driven tactics with revealed_step_index ahead of the displayed
    step are hidden, and spell_purged tactics whose discarded_step_index is
    still in the future are replayed as available."""
    from game.screens.conquer_game_screen import ConquerGameScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(
        game_id=42, player_id=7, conquer_tactics=[],
        battle_turn_player_id=None, battle_round=0,
        _game_data_version=0, conquer_resolution_step=3,
    ))
    screen._is_tactics_hand_game = lambda: True
    screen._conquer_timeline_panel = SimpleNamespace(
        currently_resolved_step_index=lambda *a, **kw: 1,
    )
    screen._request_battle_state_poll = lambda force=False: None

    fake_state = {
        'player_tactics': [
            {'id': 1, 'status': 'available', 'revealed_step_index': None,
             'discarded_step_index': None, 'family_name': 'Dagger'},
            # Newer than displayed_step (=1) → hidden.
            {'id': 2, 'status': 'available', 'revealed_step_index': 2,
             'discarded_step_index': None, 'family_name': 'Sword'},
            # Purged at step 5 — still alive at displayed_step=1 → replayed.
            {'id': 3, 'status': 'spell_purged', 'revealed_step_index': None,
             'discarded_step_index': 5, 'family_name': 'Bow'},
            # Purged at step 1 (≤ displayed) → hidden.
            {'id': 4, 'status': 'spell_purged', 'revealed_step_index': None,
             'discarded_step_index': 1, 'family_name': 'Staff'},
        ],
        'opponent_tactics': [],
        'conquer_resolution_step': 3,
    }
    screen._conquer_tactic_cache = fake_state['player_tactics']
    screen._conquer_opponent_tactic_cache = []
    screen._conquer_tactic_cache_key = (
        ConquerGameScreen._battle_state_cache_key(screen)
    )

    visible = screen._current_conquer_tactics()
    visible_ids = {t['id'] for t in visible}
    assert visible_ids == {1, 3}
    replayed = next(t for t in visible if t['id'] == 3)
    # Spell-purged tactics that are still alive at the displayed step are
    # rendered as non-interactive "ghosts" — they keep their server-side
    # 'spell_purged' status so live actions cannot fire on them.
    assert replayed['status'] == 'spell_purged'
    assert replayed.get('_render_ghost') is True


def test_current_conquer_tactics_uses_cached_state_without_sync_fetch(monkeypatch):
    from game.screens.conquer_game_screen import ConquerGameScreen
    from utils import game_service

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(game=SimpleNamespace(
        game_id=42, player_id=7, conquer_tactics=[],
        battle_turn_player_id=7, battle_round=1,
        _game_data_version=4, conquer_resolution_step=0,
        last_battle_result=None,
    ))
    screen._is_tactics_hand_game = lambda: True
    screen._conquer_timeline_panel = None
    cached = [{'id': 9, 'status': 'available', 'family_name': 'Dagger'}]
    screen._conquer_tactic_cache = cached
    screen._conquer_opponent_tactic_cache = []
    screen._conquer_tactic_cache_key = (
        ConquerGameScreen._battle_state_cache_key(screen)
    )
    screen._request_battle_state_poll = lambda force=False: None
    monkeypatch.setattr(
        game_service,
        'get_battle_state',
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError('sync fetch')),
    )

    assert screen._current_conquer_tactics() == cached


def test_timeline_panel_currently_resolved_step_index():
    """Timeline panel mirrors the server step minus the in-flight offset.

    Once the battle proper has started, all spell preludes are by definition
    in the past so we reveal every
    resolution step the server has bumped to.
    """
    from game.components.conquer_timeline_panel import ConquerTimelinePanel

    panel = ConquerTimelinePanel(pygame.Surface((10, 10)))
    screen = SimpleNamespace(
        _conquer_resolution_step_server=4,
        state=SimpleNamespace(game=SimpleNamespace(
            conquer_resolution_step=4,
            battle_confirmed=True,
            battle_turn_player_id=11,
            battle_round=1,
        )),
    )
    assert panel.currently_resolved_step_index(screen) == 4
    panel._displayed_step_offset = 1
    assert panel.currently_resolved_step_index(screen) == 3
    panel._displayed_step_offset = 99
    assert panel.currently_resolved_step_index(screen) == 0  # clamped


def test_timeline_panel_reveals_all_steps_on_zero_indexed_first_battle_round():
    """The first tactics-hand battle round is battle_round == 0.

    A Dump Cards counter spell can purge/redeal tactics immediately before
    that first round starts; the rail must not keep showing pre-battle ghosts
    until round 1.
    """
    from game.components.conquer_timeline_panel import ConquerTimelinePanel

    panel = ConquerTimelinePanel(pygame.Surface((10, 10)))
    screen = SimpleNamespace(
        _conquer_resolution_step_server=3,
        state=SimpleNamespace(game=SimpleNamespace(
            conquer_resolution_step=3,
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=0,
        )),
    )

    assert panel.currently_resolved_step_index(screen) == 3


def test_timeline_panel_reveals_all_steps_when_active_round_not_confirmed():
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from game.screens.conquer_flow import TimelineStep

    panel = ConquerTimelinePanel(pygame.Surface((10, 10)))
    screen = SimpleNamespace(
        _conquer_resolution_step_server=3,
        state=SimpleNamespace(game=SimpleNamespace(
            conquer_resolution_step=3,
            battle_confirmed=False,
            battle_turn_player_id=None,
            battle_round=1,
        )),
    )
    panel.derive_display_steps = lambda _screen: [
        TimelineStep(kind='overview', title='Overview', active=True),
        TimelineStep(kind='prelude_own', title='Prelude'),
    ]

    assert panel.currently_resolved_step_index(screen) == 3


def test_timeline_sequence_gates_skip_active_round_without_confirmed_flag():
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from game.screens.conquer_flow import TimelineStep

    panel = ConquerTimelinePanel.__new__(ConquerTimelinePanel)
    screen = SimpleNamespace(
        _conquer_acknowledged_step_kinds=set(),
        _conquer_timeline_step_started_at={},
        state=SimpleNamespace(game=SimpleNamespace(
            battle_confirmed=False,
            battle_turn_player_id=None,
            battle_round=1,
            game_over=False,
            last_battle_result=None,
        )),
    )
    steps = [
        TimelineStep(kind='overview', title='Overview', completed=True),
        TimelineStep(kind='prelude_own', title='Prelude', completed=True),
        TimelineStep(kind='attacker', title='Attack'),
    ]

    assert panel._apply_sequence_gates(screen, steps) is steps
    assert screen._conquer_timeline_step_started_at == {}


def test_timeline_panel_step_gated_by_completed_prelude_bubbles():
    """Before battle proper starts, displayed step is gated by the number
    of completed-or-active prelude bubbles the user has seen."""
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from game.screens.conquer_flow import TimelineStep

    panel = ConquerTimelinePanel(pygame.Surface((10, 10)))
    # Server has resolved 3 prelude-driven tactic mutations, but the user
    # has only seen the first prelude bubble light up.
    screen = SimpleNamespace(
        _conquer_resolution_step_server=3,
        state=SimpleNamespace(game=SimpleNamespace(
            conquer_resolution_step=3,
            battle_confirmed=False,
            battle_round=0,
        )),
    )
    panel.derive_display_steps = lambda _screen: [
        TimelineStep(kind='overview', title='Overview', completed=True),
        TimelineStep(kind='prelude_own', title='Spell A',
                     completed=False, active=True),
        TimelineStep(kind='prelude_opp', title='Spell B'),
        TimelineStep(kind='prelude_opp', title='Spell C'),
    ]
    # 1 prelude bubble active → reveal 1 mutation cascade.
    assert panel.currently_resolved_step_index(screen) == 1

    panel.derive_display_steps = lambda _screen: [
        TimelineStep(kind='overview', title='Overview', completed=True),
        TimelineStep(kind='prelude_own', title='Spell A', completed=True),
        TimelineStep(kind='prelude_opp', title='Spell B',
                     completed=False, active=True),
        TimelineStep(kind='prelude_opp', title='Spell C'),
    ]
    assert panel.currently_resolved_step_index(screen) == 2

    # All preludes seen — capped by server step.
    panel.derive_display_steps = lambda _screen: [
        TimelineStep(kind='overview', title='Overview', completed=True),
        TimelineStep(kind='prelude_own', title='Spell A', completed=True),
        TimelineStep(kind='prelude_opp', title='Spell B', completed=True),
        TimelineStep(kind='prelude_opp', title='Spell C',
                     completed=False, active=True),
    ]
    assert panel.currently_resolved_step_index(screen) == 3

    # No preludes yet seen → gated at 0 (configured battle moves shown).
    panel.derive_display_steps = lambda _screen: [
        TimelineStep(kind='overview', title='Overview',
                     completed=False, active=True),
        TimelineStep(kind='prelude_own', title='Spell A'),
    ]
    assert panel.currently_resolved_step_index(screen) == 0


def test_timeline_panel_counter_spell_bubble_reveals_counter_tactic_mutation():
    """Counter spells are spell timeline beats too.

    Dump Cards used as a counter spell stamps newly redealt tactics with the
    counter step; once the counter bubble is active/completed, those tactics
    should replace the purged ghosts in the rail.
    """
    from game.components.conquer_timeline_panel import ConquerTimelinePanel
    from game.screens.conquer_flow import TimelineStep

    panel = ConquerTimelinePanel(pygame.Surface((10, 10)))
    screen = SimpleNamespace(
        _conquer_resolution_step_server=3,
        state=SimpleNamespace(game=SimpleNamespace(
            conquer_resolution_step=3,
            battle_confirmed=False,
            battle_round=0,
        )),
    )
    panel.derive_display_steps = lambda _screen: [
        TimelineStep(kind='overview', title='Overview', completed=True),
        TimelineStep(kind='prelude_own', title='Your Prelude', completed=True),
        TimelineStep(kind='prelude_opp', title='Opponent Prelude', completed=True),
        TimelineStep(kind='counter', title='Counter Spell', active=True),
    ]

    assert panel.currently_resolved_step_index(screen) == 3
