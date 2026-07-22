# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the kingdom-screen exploration polish: anchored land inspector,
hover preview card, map scan modes, and the hero kingdom chip."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame


# ── Anchored land inspector ─────────────────────────────────────────

def _tile(**overrides):
    data = {
        'col': 2, 'row': 3, 'tier': 2, 'gold_rate': 4.2,
        'suit_bonus_suit': 'Spades', 'suit_bonus_value': 2,
        'owner': {'owned_since': '2026-05-11T00:00:00'},
        'owner_username': 'rival', 'owner_user_id': 42, 'is_mine': False,
        'defence_incomplete': False, 'kingdom_component_size': 0,
        'kingdom_bonuses': {}, 'kingdom_shield_remaining': 0,
        'kingdom_shield_reason': None, 'land_id': 7,
        'conquer_cooldown_remaining': 0,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _viewport():
    from config import settings
    return pygame.Rect(int(0.05 * settings.SCREEN_WIDTH),
                       int(0.14 * settings.SCREEN_HEIGHT),
                       int(0.60 * settings.SCREEN_WIDTH),
                       int(0.78 * settings.SCREEN_HEIGHT))


def _anchored_box(**kwargs):
    from config import settings
    from game.components.land_detail_box import LandDetailBox
    pygame.display.set_mode((1, 1))
    win = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    return LandDetailBox(win, _tile(), anchored=True, viewport_rect=_viewport(),
                         **kwargs)


def test_anchored_inspector_docks_to_bottom_of_viewport():
    vp = _viewport()
    box = _anchored_box()
    assert vp.contains(box.box_rect)
    # Docked near the bottom edge, horizontally centred.
    assert box.box_rect.bottom > vp.centery
    assert abs(box.box_rect.centerx - vp.centerx) <= 3


def test_anchored_inspector_outside_click_falls_through():
    """Clicking outside the panel returns None so the map can re-target."""
    vp = _viewport()
    box = _anchored_box(on_close=lambda: None)
    box._created_at = pygame.time.get_ticks() - 500
    event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                               pos=(vp.x + 2, vp.y + 2))
    assert box.handle_event(event) is None


def test_anchored_inspector_contains_point():
    box = _anchored_box()
    assert box.contains_point(box.box_rect.center)
    assert not box.contains_point((box.box_rect.x - 20, box.box_rect.y - 20))


def test_inspector_omits_blank_owned_since_line():
    from config import settings
    from game.components.land_detail_box import LandDetailBox
    pygame.display.set_mode((1, 1))
    win = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    tile = _tile(owner={}, owner_username='legacy-owner')

    box = LandDetailBox(win, tile, anchored=True, viewport_rect=_viewport(),
                        conquest_outcome='expand')

    assert not any(kind == 'since' for kind, _text in box._lines)
    assert ('conquest_hint', 'Expands your existing kingdom') in box._lines


def test_modal_inspector_still_centres_on_screen():
    from config import settings
    from game.components.land_detail_box import LandDetailBox
    pygame.display.set_mode((1, 1))
    win = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    box = LandDetailBox(win, _tile())  # modal (default)
    assert abs(box.box_rect.centerx - settings.SCREEN_WIDTH // 2) <= 2
    assert abs(box.box_rect.centery - settings.SCREEN_HEIGHT // 2) <= 2


def test_inspector_shows_region_champion_and_personal_progress():
    box = _anchored_box(region_info={
        'key': 'kathmandu',
        'name': 'Kathmandu Valley',
        'champion': {'user_id': 9, 'username': 'Malla'},
        'champion_land_count': 12,
        'my_land_count': 5,
        'lands_to_champion': 4,
    })
    lines = dict(box._lines)
    assert lines['region'] == 'Region: Kathmandu Valley'
    assert lines['region_champion'] == 'Champion: Malla (12 lands)'
    assert lines['region_progress'] == 'Your progress: 5 lands · 4 more needed'


def test_champion_inspector_shows_pending_tribute_rate_and_cap():
    box = _anchored_box(region_info={
        'key': 'karnali',
        'name': 'Karnali',
        'champion': {'user_id': 1, 'username': 'Malla'},
        'champion_land_count': 12,
        'my_land_count': 12,
        'lands_to_champion': 0,
        'is_champion': True,
        'my_pending_tribute': 18.5,
        'tribute_rate_per_hour': 3.4,
        'tribute_cap': 81.6,
    })

    lines = dict(box._lines)
    assert lines['region_tribute'] == (
        'Tribute: 18.5g ready · +3.4g/h · 81.6g cap')


# ── Map scan modes ──────────────────────────────────────────────────

def _make_land(col, row, **o):
    d = dict(id=col * 100 + row, col=col, row=row, tier=1, gold_rate=5.0,
             suit_bonus_suit='Hearts', suit_bonus_value=2, owner=None,
             is_mine=False, kingdom_component_id=None, kingdom_component_size=0,
             kingdom_level=0, kingdom_tier_name=None, kingdom_bonuses={},
             kingdom_id=None, kingdom_name=None, region=None)
    d.update(o)
    return d


def _hexmap():
    from config import settings
    from game.components.hex_map import HexMap
    pygame.display.set_mode((1, 1))
    win = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    lands = [
        _make_land(0, 0, is_mine=True, owner={'user_id': 1}, gold_rate=2.0),
        _make_land(1, 0, owner={'user_id': 2}, gold_rate=9.0,
                   kingdom_shield_remaining=300),
        _make_land(2, 0, gold_rate=5.0),
        _make_land(3, 0, owner={'user_id': 3}, gold_rate=1.0),
    ]
    return HexMap(lands, win, viewport_rect=_viewport())


def test_terrain_mode_has_no_wash():
    hm = _hexmap()
    hm.set_map_mode('terrain')
    assert hm._mode_overlay_color(hm.tiles[0]) is None


def test_ownership_mode_distinguishes_owners():
    hm = _hexmap()
    hm.set_map_mode('ownership')
    mine = next(t for t in hm.tiles if t.is_mine)
    enemy = next(t for t in hm.tiles if t.owner and not t.is_mine)
    unclaimed = next(t for t in hm.tiles if not t.owner)
    c_mine, c_enemy, c_unc = (hm._mode_overlay_color(mine),
                              hm._mode_overlay_color(enemy),
                              hm._mode_overlay_color(unclaimed))
    assert c_mine[1] > c_mine[0]        # green-ish for mine
    assert c_enemy[0] > c_enemy[1]      # red-ish for enemy
    assert c_mine != c_enemy != c_unc


def test_gold_mode_is_a_normalized_heatmap():
    hm = _hexmap()
    hm.set_map_mode('gold')
    low = hm._mode_overlay_color(next(t for t in hm.tiles if t.gold_rate == 1.0))
    high = hm._mode_overlay_color(next(t for t in hm.tiles if t.gold_rate == 9.0))
    assert sum(high[:3]) > sum(low[:3])


def test_vulnerable_mode_flags_open_and_protected():
    hm = _hexmap()
    hm.set_map_mode('vulnerable')
    open_tile = next(t for t in hm.tiles
                     if t.owner and not t.is_mine and not t.kingdom_shield_remaining)
    protected = next(t for t in hm.tiles if t.kingdom_shield_remaining)
    assert hm._mode_overlay_color(open_tile)[1] > hm._mode_overlay_color(open_tile)[0]
    assert hm._mode_overlay_color(protected)[0] > hm._mode_overlay_color(protected)[1]


def test_render_does_not_crash_in_any_mode():
    from game.screens.kingdom_screen import _MAP_MODES
    hm = _hexmap()
    for key, _ in _MAP_MODES:
        hm.set_map_mode(key)
        hm.render()


def test_focus_lands_can_zoom_to_fit_for_explicit_navigation():
    hm = _hexmap()
    hm.zoom = 0.5
    target_ids = [hm.tiles[0].land_id, hm.tiles[1].land_id]

    selected = hm.focus_lands(target_ids, fit=True, max_zoom=1.5)

    assert selected is not None
    assert hm.zoom == 1.5
    for land_id in target_ids:
        rect = hm.land_screen_rect(land_id)
        assert rect is not None
        assert hm.viewport_rect.colliderect(rect)


def test_full_96_by_50_map_opens_with_both_ends_visible():
    from config import settings
    from game.components.hex_map import HexMap

    win = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    lands = [
        _make_land(col, row, region=(
            'karnali' if col < 24 else
            'lumbini' if col < 48 else
            'kathmandu' if col < 64 else
            'kirat' if col < 80 else 'mithila'))
        for row in range(50) for col in range(96)
    ]
    hm = HexMap(lands, win, viewport_rect=_viewport())
    west = hm.land_screen_rect(lands[0]['id'])
    east = hm.land_screen_rect(lands[-1]['id'])
    assert west is not None
    assert east is not None
    assert hm.viewport_rect.colliderect(west)
    assert hm.viewport_rect.colliderect(east)
    assert settings.HEX_MAP_ZOOM_MIN <= hm.zoom < 0.90


def test_region_focus_fits_only_the_requested_region():
    hm = _hexmap()
    for index, tile in enumerate(hm.tiles):
        tile.region = 'kathmandu' if index < 2 else 'kirat'
    selected = hm.focus_region('kathmandu')
    assert selected is not None
    assert selected.region == 'kathmandu'
    assert hm.zoom <= 1.15


def test_two_finger_gesture_zooms_when_runtime_exposes_it():
    gesture_type = getattr(pygame, 'MULTIGESTURE', None)
    if gesture_type is None:
        return
    hm = _hexmap()
    before = hm.zoom
    event = pygame.event.Event(
        gesture_type, num_fingers=2, pinched=0.02, x=0.5, y=0.5)

    hm.handle_event(event)

    assert hm.zoom > before


# ── Map-mode toolbar (kingdom screen) ───────────────────────────────

def _mode_screen():
    from config import settings
    from game.screens.kingdom_screen import KingdomScreen
    pygame.display.set_mode((1, 1))
    s = KingdomScreen.__new__(KingdomScreen)
    s.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    s._hex_map = _hexmap()
    s._loading = False
    s._error = None
    s._map_mode = 'terrain'
    s._map_mode_rects = {}
    s._map_viewport_rect = _viewport()
    s._nav_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE, bold=True)
    s._activity_small_font = settings.get_font(int(settings.FS_TINY * 0.86))
    s._notifications = []
    s._message_unread_count = 0
    return KingdomScreen, s


def test_toolbar_draws_all_modes_and_click_switches():
    from game.screens.kingdom_screen import _MAP_MODES
    KingdomScreen, s = _mode_screen()
    s._draw_map_modes_toolbar()
    assert tuple(key for key, _label in _MAP_MODES) == ('terrain', 'gold')
    assert set(s._map_mode_rects) == {k for k, _ in _MAP_MODES}
    gold_rect = s._map_mode_rects['gold']
    assert KingdomScreen._handle_map_mode_click(s, gold_rect.center) is True
    assert s._map_mode == 'gold'
    assert s._hex_map.map_mode == 'gold'
    assert KingdomScreen._point_in_map_modes(s, gold_rect.center) is True


# ── Hover preview ───────────────────────────────────────────────────

def _hover_screen(tile, hex_rect=pygame.Rect(300, 300, 40, 46)):
    from config import settings
    from game.screens.kingdom_screen import KingdomScreen
    pygame.display.set_mode((1, 1))
    s = KingdomScreen.__new__(KingdomScreen)
    s.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    s._hex_map = SimpleNamespace(
        hovered_tile=tile,
        conquest_outcome_for=lambda t: 'expand',
        land_screen_rect=lambda land_id: hex_rect,
    )
    s._loading = False
    s._error = None
    s._thread = None
    s._new_msg_picker = None
    s._kingdom_overview_dialogue = None
    s.dialogue_box = None
    s._detail_box = None
    s._map_viewport_rect = _viewport()
    s._activity_title_font = settings.get_font(settings.FS_SMALL, bold=True)
    s._activity_font = settings.get_font(settings.FS_TINY)
    return s


def _drew_something(screen):
    before = screen.window.get_buffer().raw
    screen._draw_hover_preview()
    return before != screen.window.get_buffer().raw


def test_hover_preview_draws_for_hovered_tile():
    assert _drew_something(_hover_screen(_tile(owner=None, owner_username=None)))


def test_hover_preview_keeps_only_land_stats_and_owner_summary():
    from game.screens.kingdom_screen import KingdomScreen

    lines = KingdomScreen._hover_preview_lines(_tile())

    assert lines == (
        'Land (2, 3)  ·  Tier 2',
        '4.2 gold/hr  ·  Spades +2',
        'Owner: rival',
    )
    assert not any('Conquer' in line or 'shield' in line for line in lines)


def test_hover_preview_folds_region_into_first_of_three_lines():
    from game.screens.kingdom_screen import KingdomScreen

    lines = KingdomScreen._hover_preview_lines(
        _tile(region='kathmandu'))

    assert lines[0] == 'Kathmandu Valley · (2, 3) · Tier 2'
    assert len(lines) == 3


def test_hover_preview_suppressed_without_hover():
    s = _hover_screen(_tile())
    s._hex_map.hovered_tile = None
    assert not _drew_something(s)


def test_hover_preview_suppressed_for_inspected_tile():
    t = _tile()
    s = _hover_screen(t)
    s._detail_box = SimpleNamespace(tile=t)
    assert not _drew_something(s)


# ── Hero kingdom chip ───────────────────────────────────────────────

def _chip_screen(kingdoms):
    from config import settings
    from game.screens.kingdom_screen import KingdomScreen
    pygame.display.set_mode((1, 1))
    s = KingdomScreen.__new__(KingdomScreen)
    s.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    s._map_data = {'my_kingdoms': kingdoms}
    s._kingdom_chip_index = 0
    for a in ('_kingdom_chip_rect', '_kingdom_chip_prev_rect',
              '_kingdom_chip_next_rect', '_kingdom_chip_gear_rect'):
        setattr(s, a, None)
    s._kingdom_chip_font = settings.get_font(settings.FS_SMALL, bold=True)
    s._kingdom_chip_small_font = settings.get_font(settings.FS_TINY)
    s._kingdom_chip_edit_icon = None
    s._kingdom_chip_edit_icon_scaled = None
    s._kingdom_chip_edit_icon_scaled_sz = 0
    s._header_rect = pygame.Rect(int(0.04 * settings.SCREEN_WIDTH),
                                 int(0.10 * settings.SCREEN_HEIGHT),
                                 int(0.87 * settings.SCREEN_WIDTH),
                                 int(0.105 * settings.SCREEN_HEIGHT))
    return KingdomScreen, s


_K1 = {'id': 1, 'name': 'Ironhold', 'level': 3, 'level_max': 20,
       'xp_into_level': 40.0, 'xp_for_next_level': 100.0,
       'style': {'sigil_key': 'sigil_none', 'color_key': None}}
_K_MAX = {'id': 2, 'name': 'Greywatch', 'level': 20, 'level_max': 20,
          'xp_into_level': 0.0, 'xp_for_next_level': 0.0, 'style': {}}


def test_hero_chip_draws_and_fits_header():
    _, s = _chip_screen([_K1, _K_MAX])
    s._draw_kingdom_chip()
    from config import settings
    assert s._kingdom_chip_rect is not None
    assert s._kingdom_chip_rect.top >= s._header_rect.top
    # Stays on the left so it never collides with the centred info bar.
    assert s._kingdom_chip_rect.right < settings.SCREEN_WIDTH * 0.42


def test_hero_chip_handles_max_level_without_error():
    _, s = _chip_screen([_K_MAX])
    s._draw_kingdom_chip()  # xp_for_next_level == 0 must not divide-by-zero


def test_hero_chip_next_prev_still_cycle():
    KingdomScreen, s = _chip_screen([_K1, _K_MAX])
    s._focus_kingdom_on_map = MagicMock()
    s._draw_kingdom_chip()
    assert KingdomScreen._handle_kingdom_chip_click(s, s._kingdom_chip_next_rect.center)
    assert s._kingdom_chip_index == 1


# ── Collapsible leaderboard ─────────────────────────────────────────

def _leaderboard():
    from config import settings
    from game.components.leaderboard_panel import LeaderboardPanel
    pygame.display.set_mode((1, 1))
    win = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    panel = LeaderboardPanel(win, rect=(40, 60, 220, 300))
    panel.set_data(
        top_largest=[{'rank': 1, 'name': 'A', 'size': 9, 'user_id': 5}],
        top_realms=[{'rank': 1, 'username': 'A', 'total_lands': 12, 'user_id': 5}],
    )
    return panel


def test_leaderboard_toggle_collapses_and_expands():
    panel = _leaderboard()
    panel.render()
    assert panel.collapsed is False
    # Full rect is hit-testable when expanded.
    assert panel.contains_point((45, 250))
    # Click the toggle caret.
    ev = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                            pos=panel._toggle_rect.center)
    panel.handle_event(ev)
    assert panel.collapsed is True
    panel.render()
    # Collapsed: only the header band is hit-testable; the body area frees the map.
    assert panel.contains_point((45, panel.rect.y + 4))
    assert not panel.contains_point((45, 250))


def test_collapsed_leaderboard_row_clicks_do_not_focus():
    panel = _leaderboard()
    focused = []
    panel.on_focus = focused.append
    panel.render()
    ev = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                            pos=panel._toggle_rect.center)
    panel.handle_event(ev)  # collapse
    panel.render()
    # A click in the (now hidden) body must not reach a row.
    body = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(60, 250))
    assert panel.handle_event(body) is None
    assert focused == []


def test_leaderboard_regions_view_focuses_clicked_region():
    panel = _leaderboard()
    panel.set_data(regions=[{
        'key': 'kathmandu', 'name': 'Kathmandu Valley',
        'champion': {'user_id': 4, 'username': 'Malla'},
        'champions': [{'user_id': 4, 'username': 'Malla'}],
        'champion_land_count': 12, 'my_land_count': 5, 'min_lands': 1,
        'lands_to_champion': 7,
    }])
    focused = []
    panel.on_focus = focused.append
    panel.render()
    switch = pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=1,
        pos=panel._tab_rects['regions'].center)
    assert panel.handle_event(switch) == {'view': 'regions'}
    panel.render()
    assert len(panel._row_rects) == 1
    click = pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=1,
        pos=panel._row_rects[0][0].center)
    panel.handle_event(click)
    assert focused[0]['region_key'] == 'kathmandu'


def test_leaderboard_view_tabs_have_visual_spacing():
    panel = _leaderboard()
    panel.render()
    rankings = panel._tab_rects['rankings']
    regions = panel._tab_rects['regions']
    assert regions.left - rankings.right >= 2


def test_all_region_rows_fit_and_use_champion_and_suit_icons():
    panel = _leaderboard()
    suits = ('Spades', 'Clubs', None, 'Hearts', 'Diamonds')
    panel.set_data(regions=[{
        'key': f'region-{index}',
        'name': ('Kathmandu Valley' if suit is None else suit),
        'dominant_suit': suit,
        'champion': {'user_id': index + 1, 'username': f'Player{index}'},
        'champions': [{'user_id': index + 1,
                       'username': f'Player{index}'}],
        'champion_land_count': 9 - index,
        'my_land_count': index,
        'lands_to_champion': max(0, 8 - index),
    } for index, suit in enumerate(suits)])
    panel._view = 'regions'

    panel.render()

    assert len(panel._row_rects) == 5
    assert panel._row_rects[-1][0].bottom <= panel.rect.bottom
    assert panel._champion_icon is not None
    assert all(panel._suit_icons[suit] is not None
               for suit in ('Spades', 'Clubs', 'Hearts', 'Diamonds'))


# ── Reward / conquest particle effects ──────────────────────────────

def _fx_screen():
    from config import settings
    from game.screens.kingdom_screen import KingdomScreen
    from game.components.conquer_effects import ConquerEffectsLayer
    pygame.display.set_mode((1, 1))
    s = KingdomScreen.__new__(KingdomScreen)
    s.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    s._fx = ConquerEffectsLayer(s.window, lambda _id: None)
    s._hex_map = _hexmap()
    s._user_item_display_rect = pygame.Rect(20, 20, 400, 60)
    return s


def test_collect_reward_fx_streams_from_owned_lands():
    s = _fx_screen()
    before = len(s._fx._copies)
    s._collect_reward_fx(gold_amount=50, main_boosters=0, side_boosters=0)
    assert len(s._fx._copies) > before          # orbs spawned from owned land(s)
    assert len(s._fx._impacts) >= 1             # HUD landing pulse


def test_collect_reward_fx_noop_when_nothing_collected():
    s = _fx_screen()
    s._collect_reward_fx(gold_amount=0, main_boosters=0, side_boosters=0)
    assert len(s._fx._copies) == 0
    assert len(s._fx._impacts) == 0


def test_celebrate_conquests_spawns_burst_pulse_and_map_gain(monkeypatch):
    import game.screens.kingdom_screen as module

    s = _fx_screen()
    mine = next(t for t in s._hex_map.tiles if t.is_mine)
    played = []
    monkeypatch.setattr(
        module.sound, 'play', lambda name, **kwargs: played.append(name))
    s._celebrate_conquests([mine.land_id])
    assert len(s._fx._particles) > 0            # celebratory burst
    assert len(s._fx._impacts) > 0              # border-merge pulse
    assert len(s._fx._banners) == 1             # "Land conquered!" banner
    assert played == ['map_gain']


def test_diff_new_conquests_ignores_first_load_then_detects():
    from game.screens.kingdom_screen import KingdomScreen
    s = KingdomScreen.__new__(KingdomScreen)
    s._prev_my_land_ids = None
    first = [{'id': 1, 'is_mine': True}, {'id': 2, 'is_mine': False}]
    assert KingdomScreen._diff_new_conquests(s, first) == []   # baseline only
    second = [{'id': 1, 'is_mine': True}, {'id': 2, 'is_mine': True}]
    assert KingdomScreen._diff_new_conquests(s, second) == [2]
    # No repeat celebration on a subsequent identical load.
    assert KingdomScreen._diff_new_conquests(s, second) == []
