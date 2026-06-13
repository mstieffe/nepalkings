# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for shared menu chrome gold-gain floater bookkeeping."""

from types import SimpleNamespace


def _screen_with_gold(gold=100):
    from game.screens._menu_base import MenuScreenMixin
    screen = object.__new__(MenuScreenMixin)
    screen.state = SimpleNamespace(user_dict={'gold': gold})
    screen._last_seen_gold = gold
    calls = []
    screen._spawn_gold_gain_floater = lambda amount, pos: calls.append((amount, pos))
    return screen, calls


def _ensure_pygame_display():
    import pygame

    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))


def test_gold_gain_spawns_top_bar_floater():
    screen, calls = _screen_with_gold(100)

    screen._maybe_spawn_gold_gain_floater(135, (42, 24))

    assert calls == [(35, (42, 24))]
    assert screen._last_seen_gold == 135


def test_gold_loss_resets_baseline_without_floater():
    screen, calls = _screen_with_gold(100)

    screen._maybe_spawn_gold_gain_floater(80, (42, 24))

    assert calls == []
    assert screen._last_seen_gold == 80


def test_missing_gold_position_suppresses_floater_but_keeps_baseline():
    screen, calls = _screen_with_gold(100)

    screen._maybe_spawn_gold_gain_floater(125, None)

    assert calls == []
    assert screen._last_seen_gold == 125


def test_suppress_next_gold_floater_skips_once_then_resumes():
    screen, calls = _screen_with_gold(100)

    screen._suppress_next_gold_floater()
    screen._maybe_spawn_gold_gain_floater(140, (42, 24))
    screen._maybe_spawn_gold_gain_floater(160, (42, 24))

    assert calls == [(20, (42, 24))]
    assert screen._last_seen_gold == 160


def test_override_next_gold_floater_position_uses_custom_anchor_once():
    screen, calls = _screen_with_gold(100)

    screen._set_next_gold_floater_pos((9, 11))
    screen._maybe_spawn_gold_gain_floater(130, (42, 24))
    screen._maybe_spawn_gold_gain_floater(150, (42, 24))

    assert calls == [(30, (9, 11)), (20, (42, 24))]
    assert screen._last_seen_gold == 150


def test_onboarding_reward_floaters_use_collect_animation_labels():
    _ensure_pygame_display()
    from game.components.floating_text import FloatingTextLayer
    from config import settings

    screen, _ = _screen_with_gold(100)
    screen._onboarding_reward_floaters = FloatingTextLayer()

    screen._spawn_onboarding_reward_floaters({
        'gold': 50,
        'booster_packs': 1,
        'booster_packs_side': 2,
        'maps': 3,
    }, (200, 300))

    items = screen._onboarding_reward_floaters._items
    assert [item._text for item in items] == [
        '+50g',
        '+1 Main Pack',
        '+2 Side Packs',
        '+3 Maps',
    ]
    assert [item._delay_ms for item in items] == [
        0,
        settings.COLLECT_FLOAT_STAGGER_MS,
        settings.COLLECT_FLOAT_STAGGER_MS * 2,
        settings.COLLECT_FLOAT_STAGGER_MS * 3,
    ]


def test_onboarding_guide_claim_spawns_reward_floaters(monkeypatch):
    import pygame
    from game.screens import _menu_base

    screen, _ = _screen_with_gold(100)
    messages = []
    screen.state.set_msg = lambda message: messages.append(message)
    guide_rect = screen._onboarding_guide_rect()
    claim_rect = pygame.Rect(guide_rect.x + 20, guide_rect.y + 20, 96, 34)
    screen._onboarding_guide_close_rect = pygame.Rect(0, 0, 1, 1)
    screen._onboarding_guide_buttons = [(claim_rect, ('claim', 'first_duel'))]
    spawned = []
    screen._spawn_onboarding_reward_floaters = (
        lambda reward, pos: spawned.append((dict(reward), pos))
    )
    claimed = []
    monkeypatch.setattr(_menu_base.onboarding_service, 'claim_reward', lambda reward_id: (
        claimed.append(reward_id) or {
            'reward': {'gold': 50, 'maps': 1},
            'balances': {'gold': 150, 'maps': 1},
            'onboarding': {'completed_steps': ['first_duel']},
            'reward_label': 'Reward claimed',
        }
    ))

    event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=claim_rect.center)

    assert screen._handle_onboarding_guide_events([event]) is True
    assert claimed == ['first_duel']
    assert screen.state.user_dict['gold'] == 150
    assert screen._suppress_next_gold_gain_floater is True
    assert spawned == [({'gold': 50, 'maps': 1}, claim_rect.center)]
    assert messages == ['Reward claimed']


def test_onboarding_guide_resume_button_clears_paused_flag(monkeypatch):
    import pygame
    from game.screens import _menu_base

    screen, _ = _screen_with_gold(100)
    screen.state.user_dict['onboarding'] = {'onboarding_skipped': True}
    messages = []
    screen.state.set_msg = lambda message: messages.append(message)
    guide_rect = pygame.Rect(0, 0, 400, 400)
    resume_rect = pygame.Rect(40, 90, 150, 30)
    screen._onboarding_guide_rect = lambda: guide_rect
    screen._onboarding_guide_scroll = 0
    screen._onboarding_guide_scroll_area = pygame.Rect(20, 40, 220, 120)
    screen._onboarding_guide_content_h = 120
    screen._onboarding_guide_scrollbar_rect = pygame.Rect(0, 0, 0, 0)
    screen._onboarding_guide_close_rect = pygame.Rect(360, 20, 24, 24)
    screen._onboarding_guide_buttons = [(resume_rect, ('resume_tutorial', None))]
    calls = []
    monkeypatch.setattr(_menu_base.onboarding_service, 'resume_onboarding', lambda: (
        calls.append(True) or {'onboarding': {'onboarding_skipped': False}}
    ))

    event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=resume_rect.center)

    assert screen._handle_onboarding_guide_events([event]) is True
    assert calls == [True]
    assert screen.state.user_dict['onboarding']['onboarding_skipped'] is False
    assert messages == ['Tutorial resumed']


def test_menu_coach_allowed_false_when_tutorial_paused():
    from game.screens._menu_base import MenuScreenMixin

    screen = object.__new__(MenuScreenMixin)
    screen.state = SimpleNamespace(user_dict={'onboarding': {'onboarding_skipped': True}})
    screen._onboarding_guide_open = False
    screen._logout_dialogue = None
    screen._welcome_present_dialogue = None
    screen.dialogue_box = None

    assert screen._menu_coach_allowed_common() is False


def test_menu_coach_skip_pauses_without_marking_seen(monkeypatch):
    import pygame
    from game.screens import _menu_base

    screen, _ = _screen_with_gold(100)
    screen.state.user_dict['onboarding'] = {
        'onboarding_skipped': False,
        'menu_hints_seen': [],
    }
    messages = []
    screen.state.set_msg = lambda message: messages.append(message)
    screen._menu_coach_step = {
        'id': 'duel',
        'rect': pygame.Rect(10, 10, 120, 40),
        'action': 'next',
    }
    skip_rect = pygame.Rect(240, 80, 120, 32)
    screen._menu_coach_buttons = [(skip_rect, ('skip_tutorial', 'duel'))]
    screen._menu_coach_pressed_button_action = None
    calls = []
    monkeypatch.setattr(_menu_base.onboarding_service, 'skip_onboarding', lambda: (
        calls.append(True) or {
            'onboarding': {
                'onboarding_skipped': True,
                'menu_hints_seen': [],
            }
        }
    ))

    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=skip_rect.center)
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=skip_rect.center)

    assert screen._handle_menu_coach_events([down]) is True
    assert screen._handle_menu_coach_events([up]) is True
    assert calls == [True]
    assert screen.state.user_dict['onboarding']['onboarding_skipped'] is True
    assert screen.state.user_dict['onboarding']['menu_hints_seen'] == []
    assert messages == ['Tutorial paused. Open Guide to continue.']


def test_onboarding_guide_mouse_wheel_scrolls_achievement_viewport():
    import pygame

    screen, _ = _screen_with_gold(100)
    screen._onboarding_guide_rect = lambda: pygame.Rect(0, 0, 400, 400)
    screen._onboarding_guide_scroll = 0
    screen._onboarding_guide_scroll_area = pygame.Rect(20, 40, 220, 100)
    screen._onboarding_guide_content_h = 320
    screen._onboarding_guide_scrollbar_rect = pygame.Rect(250, 40, 8, 100)

    event = pygame.event.Event(pygame.MOUSEWHEEL, y=-1, precise_y=-1, pos=(40, 80))

    assert screen._handle_onboarding_guide_events([event]) is True
    assert screen._onboarding_guide_scroll > 0


def test_onboarding_guide_touch_swipe_scrolls_without_claiming(monkeypatch):
    import pygame
    from game.screens import _menu_base

    screen, _ = _screen_with_gold(100)
    screen._onboarding_guide_rect = lambda: pygame.Rect(0, 0, 400, 400)
    screen._onboarding_guide_scroll = 0
    screen._onboarding_guide_scroll_area = pygame.Rect(20, 40, 220, 120)
    screen._onboarding_guide_content_h = 420
    screen._onboarding_guide_scrollbar_rect = pygame.Rect(250, 40, 8, 120)
    screen._onboarding_guide_close_rect = pygame.Rect(360, 20, 24, 24)
    claim_rect = pygame.Rect(40, 90, 80, 30)
    screen._onboarding_guide_buttons = [(claim_rect, ('claim', 'first_duel'))]
    claimed = []
    monkeypatch.setattr(_menu_base.onboarding_service, 'claim_reward', lambda reward_id: claimed.append(reward_id))

    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=claim_rect.center)
    move = pygame.event.Event(pygame.MOUSEMOTION, pos=(claim_rect.centerx, claim_rect.centery - 60))
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(claim_rect.centerx, claim_rect.centery - 60))

    assert screen._handle_onboarding_guide_events([down]) is True
    assert screen._handle_onboarding_guide_events([move]) is True
    assert screen._handle_onboarding_guide_events([up]) is True
    assert screen._onboarding_guide_scroll > 0
    assert claimed == []


def test_onboarding_guide_touch_tap_can_still_claim(monkeypatch):
    import pygame
    from game.screens import _menu_base

    screen, _ = _screen_with_gold(100)
    screen.state.set_msg = lambda _message: None
    screen._onboarding_guide_rect = lambda: pygame.Rect(0, 0, 400, 400)
    screen._onboarding_guide_scroll = 0
    screen._onboarding_guide_scroll_area = pygame.Rect(20, 40, 220, 120)
    screen._onboarding_guide_content_h = 420
    screen._onboarding_guide_scrollbar_rect = pygame.Rect(250, 40, 8, 120)
    screen._onboarding_guide_close_rect = pygame.Rect(360, 20, 24, 24)
    claim_rect = pygame.Rect(40, 90, 80, 30)
    screen._onboarding_guide_buttons = [(claim_rect, ('claim', 'first_duel'))]
    screen._spawn_onboarding_reward_floaters = lambda _reward, _pos: None
    claimed = []
    monkeypatch.setattr(_menu_base.onboarding_service, 'claim_reward', lambda reward_id: (
        claimed.append(reward_id) or {
            'reward': {},
            'balances': {},
            'onboarding': {'completed_steps': ['finish_first_duel']},
        }
    ))

    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=claim_rect.center)
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=claim_rect.center)

    assert screen._handle_onboarding_guide_events([down]) is True
    assert screen._handle_onboarding_guide_events([up]) is True
    assert claimed == ['first_duel']


def test_current_gold_amount_handles_missing_or_invalid_values():
    screen, _ = _screen_with_gold(100)

    screen.state.user_dict = {'gold': 'bad'}
    assert screen._current_gold_amount() == 0

    screen.state.user_dict = None
    assert screen._current_gold_amount() == 0


def test_mobile_safe_top_clears_resource_strip(monkeypatch):
    from game.screens import _menu_base

    monkeypatch.setattr(_menu_base, '_SH', 480)
    monkeypatch.setattr(_menu_base.settings, 'TOUCH_TARGET_MIN', 58)
    monkeypatch.setattr(_menu_base.settings, 'GAME_MENU_GOLD_MARGIN_Y', 12)
    monkeypatch.setattr(_menu_base.settings, 'GAME_MENU_GOLD_BOX_PAD_Y', 3)
    monkeypatch.setattr(_menu_base.settings, 'GAME_MENU_GOLD_ICON_SZ', 34)
    monkeypatch.setattr(_menu_base.settings, 'GAME_MENU_GOLD_FONT_SIZE', 27)

    assert _menu_base.menu_chrome_safe_top(48, extra_gap=6) == 58
    assert _menu_base.menu_chrome_safe_top(72, extra_gap=6) == 72


def test_mobile_safe_width_clears_right_icon_rail(monkeypatch):
    from game.screens import _menu_base

    monkeypatch.setattr(_menu_base, '_SW', 854)
    monkeypatch.setattr(_menu_base.settings, 'TOUCH_TARGET_MIN', 58)
    monkeypatch.setattr(_menu_base.settings, 'GAME_MENU_ICON_RIGHT_MARGIN', 3)
    monkeypatch.setattr(_menu_base.settings, 'GAME_MENU_ICON_STONE_SZ', 88)

    assert _menu_base.menu_chrome_safe_width(34, 742, extra_gap=10) == 719
    assert _menu_base.menu_chrome_safe_width(170, 512, extra_gap=10) == 512


def test_mobile_subscreen_boxes_clear_persistent_menu_chrome():
    import os
    from pathlib import Path
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    app_dir = root / 'nepal_kings'
    env = os.environ.copy()
    env.update({
        'SDL_VIDEODRIVER': 'dummy',
        'SDL_AUDIODRIVER': 'dummy',
        'NK_SCREEN_WIDTH': '854',
        'NK_SCREEN_HEIGHT': '480',
        'NK_UI_SCALE': '1.6',
        'NK_IS_MOBILE': '1',
        'PYTHONPATH': str(app_dir),
    })
    code = r'''
import importlib
import pygame
pygame.init()
pygame.display.set_mode((1, 1))
from config import settings

hud_bottom = (
    settings.GAME_MENU_GOLD_MARGIN_Y
    + 2 * settings.GAME_MENU_GOLD_BOX_PAD_Y
    + max(settings.GAME_MENU_GOLD_ICON_SZ, settings.GAME_MENU_GOLD_FONT_SIZE)
)
rail_left = (
    settings.SCREEN_WIDTH
    - settings.GAME_MENU_ICON_RIGHT_MARGIN
    - settings.GAME_MENU_ICON_STONE_SZ
)
modules = [
    'game.screens.collection_screen',
    'game.screens.ranking_screen',
    'game.screens.load_game_screen',
    'game.screens.new_game_screen',
    'game.screens.settings_screen',
    'game.screens.kingdom_screen',
    'game.screens.kingdom_config_screen',
    'game.screens.conquer_screen',
    'game.screens.defence_screen',
]
for name in modules:
    mod = importlib.import_module(name)
    assert mod._BOX_Y >= hud_bottom + 6, (name, mod._BOX_Y, hud_bottom)
    assert mod._BOX_X + mod._BOX_W <= rail_left - 8, (
        name, mod._BOX_X + mod._BOX_W, rail_left)
'''
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=app_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_onboarding_payload_preserves_local_hint_progress():
    screen, _ = _screen_with_gold(100)
    screen.state.user_dict['onboarding'] = {
        'menu_hints_seen': ['duel'],
        'duel_hints_seen': ['build'],
    }

    screen._apply_onboarding_payload({
        'onboarding': {
            'menu_hints_seen': [],
            'duel_hints_seen': ['field'],
            'welcome_pending': False,
        }
    })

    onboarding = screen.state.user_dict['onboarding']
    assert onboarding['menu_hints_seen'] == ['duel']
    assert onboarding['duel_hints_seen'] == ['field', 'build']


def test_main_menu_area_coach_starts_with_user_item_display():
    import pygame
    from game.screens.game_menu_screen import GameMenuScreen

    screen = object.__new__(GameMenuScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'welcome_pending': False,
        'completed_steps': [],
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen.dialogue_box = None
    screen._user_item_display_rect = pygame.Rect(8, 10, 180, 36)
    screen.button_duel = SimpleNamespace(rect=pygame.Rect(20, 80, 120, 44))
    screen.button_kingdom = SimpleNamespace(rect=pygame.Rect(20, 130, 120, 44))
    screen.button_collection = SimpleNamespace(rect=pygame.Rect(20, 180, 120, 44))
    screen.button_rankings = SimpleNamespace(rect=pygame.Rect(20, 230, 120, 44))
    screen._icon_home = SimpleNamespace(rect=pygame.Rect(760, 20, 42, 42))
    screen._icon_guide = SimpleNamespace(rect=pygame.Rect(760, 70, 42, 42))

    step = screen._current_area_coach_step()
    assert step['id'] == 'user_items'
    assert step['rect'] == screen._user_item_display_rect

    # Action-first: after the welcome-items pointer, the coach leads straight
    # into the journey (open your booster packs), not a generic area tour.
    screen.state.user_dict['onboarding']['menu_hints_seen'] = ['user_items']
    assert screen._current_area_coach_step()['id'] == 'open_boosters_first'


def _journey_ready_menu_screen(completed_steps):
    """A GameMenuScreen with every area + guide hint already seen, so the
    next coach step comes from the conquer-first journey."""
    import pygame
    from game.screens.game_menu_screen import GameMenuScreen

    seen = [
        'user_items', 'kingdom', 'collection', 'duel', 'rankings', 'home',
        'guide_achievements', 'guide_first_duel_reward',
    ]
    screen = object.__new__(GameMenuScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': list(seen),
        'welcome_pending': False,
        'completed_steps': list(completed_steps),
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen.dialogue_box = None
    screen._user_item_display_rect = pygame.Rect(8, 10, 180, 36)
    screen.button_duel = SimpleNamespace(rect=pygame.Rect(20, 80, 120, 44))
    screen.button_kingdom = SimpleNamespace(rect=pygame.Rect(20, 130, 120, 44))
    screen.button_collection = SimpleNamespace(rect=pygame.Rect(20, 180, 120, 44))
    screen.button_rankings = SimpleNamespace(rect=pygame.Rect(20, 230, 120, 44))
    screen._icon_home = SimpleNamespace(rect=pygame.Rect(760, 20, 42, 42))
    screen._icon_guide = SimpleNamespace(rect=pygame.Rect(760, 70, 42, 42))
    return screen


def test_main_menu_journey_coach_routes_boosters_then_conquer_then_duel():
    # Fresh account: open boosters first.
    screen = _journey_ready_menu_screen(completed_steps=[])
    step = screen._current_area_coach_step()
    assert step['id'] == 'open_boosters_first'
    assert step['rect'] == screen.button_collection.rect

    # Boosters opened: route to the first conquest, not a duel.
    screen.state.user_dict['onboarding']['completed_steps'] = [
        'open_first_main_booster', 'open_first_side_booster',
    ]
    step = screen._current_area_coach_step()
    assert step['id'] == 'post_boosters_kingdom'
    assert step['rect'] == screen.button_kingdom.rect

    # First land conquered: now invite the player to their first duel.
    screen.state.user_dict['onboarding']['completed_steps'].append(
        'finish_first_conquer_battle')
    step = screen._current_area_coach_step()
    assert step['id'] == 'ready_first_duel'
    assert step['rect'] == screen.button_duel.rect

    # First duel done: the journey coach is finished.
    screen.state.user_dict['onboarding']['completed_steps'].append(
        'finish_first_duel')
    assert screen._current_area_coach_step() is None


def test_kingdom_coach_progresses_from_map_to_conquer_button():
    import pygame
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'completed_steps': [
            'finish_first_duel', 'open_first_main_booster', 'open_first_side_booster'
        ],
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen.dialogue_box = None
    screen._thread = None
    screen._new_msg_picker = None
    screen._detail_box = None
    screen._hex_map = object()
    screen._loading = False
    screen._error = None
    screen._map_viewport_rect = pygame.Rect(50, 60, 300, 220)

    assert screen._current_kingdom_coach_step()['id'] == 'kingdom_map_intro'

    screen.state.user_dict['onboarding']['menu_hints_seen'] = ['kingdom_map_intro']
    assert screen._current_kingdom_coach_step()['id'] == 'kingdom_select_land'

    conquer_rect = pygame.Rect(120, 180, 140, 34)
    screen._detail_box = SimpleNamespace(
        _buttons=[('conquer', SimpleNamespace(rect=conquer_rect, disabled=False))]
    )
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_conquer_button'
    assert step['rect'] == conquer_rect


def test_kingdom_coach_shifts_to_post_battle_map_and_config_steps():
    import pygame
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'completed_steps': [
            'finish_first_duel',
            'open_first_main_booster',
            'open_first_side_booster',
            'finish_first_conquer_battle',
        ],
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen.dialogue_box = None
    screen._thread = None
    screen._new_msg_picker = None
    screen._detail_box = None
    screen._hex_map = object()
    screen._loading = False
    screen._error = None
    screen._map_viewport_rect = pygame.Rect(50, 60, 300, 220)
    screen._header_rect = pygame.Rect(40, 20, 420, 80)
    screen._collect_all_rect = pygame.Rect(340, 32, 110, 34)
    screen._kingdom_chip_gear_rect = pygame.Rect(60, 28, 28, 28)

    assert screen._current_kingdom_coach_step()['id'] == 'kingdom_after_conquer_map'

    screen.state.user_dict['onboarding']['menu_hints_seen'] = ['kingdom_after_conquer_map']
    assert screen._current_kingdom_coach_step()['id'] == 'kingdom_connected_lands'

    screen.state.user_dict['onboarding']['menu_hints_seen'] = [
        'kingdom_after_conquer_map',
        'kingdom_connected_lands',
    ]
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_production_intro'
    assert step['rect'] == screen._collect_all_rect

    screen.state.user_dict['onboarding']['menu_hints_seen'] = [
        'kingdom_after_conquer_map',
        'kingdom_connected_lands',
        'kingdom_production_intro',
    ]
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_defence_intro'

    screen.state.user_dict['onboarding']['menu_hints_seen'] = [
        'kingdom_after_conquer_map',
        'kingdom_connected_lands',
        'kingdom_production_intro',
        'kingdom_defence_intro',
    ]
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_config_intro'
    assert step['action'] == 'click'
    assert step['rect'] == screen._kingdom_chip_gear_rect


def test_conquer_coach_highlights_edit_controls_in_order():
    import pygame
    from game.screens.conquer_screen import ConquerScreen

    screen = object.__new__(ConquerScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'completed_steps': [
            'finish_first_duel', 'open_first_main_booster', 'open_first_side_booster'
        ],
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen.dialogue_box = None
    screen._loading = False
    screen._error = None
    screen._config = {'land_id': 1}
    screen._layout_built = True
    screen._active_subscreen = None
    screen._figure_detail_box = None
    screen._move_detail_box = None
    screen._active_info_key = None
    screen._field_rects = {'castle': pygame.Rect(20, 80, 120, 80)}
    screen._res_rect = pygame.Rect(20, 170, 120, 40)
    screen._btn_build = pygame.Rect(150, 80, 34, 34)
    screen._battle_plan_rect = pygame.Rect(260, 80, 180, 120)
    screen._btn_buy_move = pygame.Rect(450, 80, 34, 34)
    screen._prelude_panel_rect = pygame.Rect(260, 220, 180, 120)
    screen._btn_prelude_edit = pygame.Rect(450, 220, 34, 34)
    screen._prelude_spell_rect = pygame.Rect(300, 260, 42, 42)
    screen._btn_battle = pygame.Rect(520, 380, 140, 42)

    expected = [
        'conquer_config_field',
        'conquer_config_build_edit',
        'conquer_config_battle_plan',
        'conquer_config_prelude',
        'conquer_config_to_battle',
    ]
    seen = []
    for step_id in expected:
        screen.state.user_dict['onboarding']['menu_hints_seen'] = list(seen)
        step = screen._current_conquer_coach_step()
        assert step['id'] == step_id
        if step_id == 'conquer_config_to_battle':
            assert step['button_label'] == 'Got it'
        seen.append(step_id)


def test_menu_coach_next_step_blocks_everything_except_next():
    import pygame

    screen, _ = _screen_with_gold(100)
    marked = []
    after = []
    screen._menu_coach_buttons = [(pygame.Rect(10, 10, 80, 32), ('next', 'duel'))]
    screen._mark_menu_coach_seen = lambda step_id: marked.append(step_id)
    screen._after_menu_coach_next = lambda step_id: after.append(step_id)
    step = {'id': 'duel', 'rect': pygame.Rect(100, 100, 80, 40), 'title': 'Duel', 'body': 'Body'}

    target_click = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(120, 120))
    assert screen._handle_menu_coach_events([target_click], step) is True
    assert marked == []

    next_down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(30, 20))
    assert screen._handle_menu_coach_events([next_down], step) is True
    assert marked == []

    next_click = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(30, 20))
    assert screen._handle_menu_coach_events([next_click], step) is True
    assert marked == ['duel']
    assert after == ['duel']


def test_menu_coach_click_step_allows_only_target_click():
    import pygame

    screen, _ = _screen_with_gold(100)
    marked = []
    screen._menu_coach_buttons = []
    screen._mark_menu_coach_seen = lambda step_id: marked.append(step_id)
    step = {
        'id': 'start_first_duel',
        'rect': pygame.Rect(100, 100, 80, 40),
        'title': 'Duel',
        'body': 'Body',
        'action': 'click',
    }

    outside = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(20, 20))
    assert screen._handle_menu_coach_events([outside], step) is True
    assert marked == []

    inside = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(120, 120))
    assert screen._handle_menu_coach_events([inside], step) is False
    assert marked == ['start_first_duel']

    step['mark_on_click'] = False
    assert screen._handle_menu_coach_events([inside], step) is False
    assert marked == ['start_first_duel']
