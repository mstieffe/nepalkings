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


def test_main_menu_area_coach_leads_with_journey():
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

    # Action-first: the coach leads straight into the journey (first
    # conquest) — no generic area tour up front.
    step = screen._current_area_coach_step()
    assert step['id'] == 'post_boosters_kingdom'
    assert step['rect'] == screen.button_kingdom.rect


def _journey_ready_menu_screen(completed_steps):
    """A GameMenuScreen with every area + guide hint already seen, so the
    next coach step comes from the conquer-first journey."""
    import pygame
    from game.screens.game_menu_screen import GameMenuScreen

    seen = [
        'kingdom', 'collection', 'duel', 'rankings',
        'guide', 'guide_first_duel_reward',
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


def test_main_menu_journey_coach_routes_conquer_reward_kingdom_then_optional_duel():
    # Fresh account: first conquest comes before Collection.
    screen = _journey_ready_menu_screen(completed_steps=[])
    step = screen._current_area_coach_step()
    assert step['id'] == 'post_boosters_kingdom'
    assert step['rect'] == screen.button_kingdom.rect

    # First land conquered: open a single main booster as the reward beat.
    screen.state.user_dict['onboarding']['completed_steps'] = [
        'finish_first_conquer_battle',
    ]
    step = screen._current_area_coach_step()
    assert step['id'] == 'open_main_booster_reward'
    assert step['rect'] == screen.button_collection.rect

    # Reward pack opened but tutorial not finished: steer BACK TO THE KINGDOM
    # (collect production + finish the config tour), NOT to a duel.
    screen.state.user_dict['onboarding']['completed_steps'].append(
        'open_first_main_booster')
    step = screen._current_area_coach_step()
    assert step['id'] == 'return_to_kingdom_loop'
    assert step['rect'] == screen.button_kingdom.rect

    # Tutorial finished: only now is a duel offered, and clearly as optional.
    screen.state.user_dict['onboarding']['completed_steps'].append(
        'finish_tutorial')
    step = screen._current_area_coach_step()
    assert step['id'] == 'ready_first_duel'
    assert step['rect'] == screen.button_duel.rect
    assert step['title'].lower().startswith('optional')

    # Optional duel played: the journey coach is finished.
    screen.state.user_dict['onboarding']['completed_steps'].append(
        'finish_first_duel')
    assert screen._current_area_coach_step() is None


def test_duel_never_blocks_tutorial_completion_in_journey():
    # Tutorial complete WITHOUT a duel: journey only ever offers the duel as an
    # optional, skippable nudge — never a mandatory step.
    screen = _journey_ready_menu_screen(completed_steps=[
        'finish_first_conquer_battle',
        'open_first_main_booster',
        'collect_first_kingdom_production',
        'finish_tutorial',
    ])
    step = screen._current_journey_coach_step()
    assert step['id'] == 'ready_first_duel'

    # Skipping the optional nudge ends the journey; the duel is not required.
    screen.state.user_dict['onboarding']['menu_hints_seen'] = ['ready_first_duel']
    assert screen._current_journey_coach_step() is None


def test_guide_prompt_does_not_loop_after_tutorial_complete():
    screen = _journey_ready_menu_screen(completed_steps=[
        'finish_first_conquer_battle',
        'open_first_main_booster',
        'collect_first_kingdom_production',
        'finish_tutorial',
        'finish_first_duel',
    ])
    screen.state.user_dict['onboarding']['menu_hints_seen'] = [
        'duel', 'kingdom', 'collection', 'rankings', 'ready_first_duel',
    ]

    step = screen._current_area_coach_step()
    assert step['id'] == 'guide'

    screen.state.user_dict['onboarding']['menu_hints_seen'].append('guide')
    assert screen._current_area_coach_step() is None


def test_guide_prompt_can_return_to_unfinished_reward_walkthrough():
    screen = _journey_ready_menu_screen(completed_steps=[
        'open_first_main_booster',
        'finish_first_conquer_battle',
    ])
    # return_to_kingdom_loop already seen so the journey coach yields to the
    # guide walkthrough, which should re-show while the tutorial is unfinished.
    screen.state.user_dict['onboarding']['menu_hints_seen'] = [
        'duel', 'kingdom', 'collection', 'rankings',
        'return_to_kingdom_loop', 'guide',
    ]

    step = screen._current_area_coach_step()
    assert step['id'] == 'guide'


def test_kingdom_coach_progresses_from_map_to_conquer_button():
    import pygame
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': ['kingdom_overview_window'],
        'completed_steps': [],
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen._kingdom_overview_dialogue = None
    screen.dialogue_box = None
    screen._thread = None
    screen._new_msg_picker = None
    screen._detail_box = None
    screen._hex_map = object()
    screen._loading = False
    screen._error = None
    screen._map_viewport_rect = pygame.Rect(50, 60, 300, 220)

    assert screen._current_kingdom_coach_step()['id'] == 'kingdom_pick_land'

    conquer_rect = pygame.Rect(120, 180, 140, 34)
    screen._detail_box = SimpleNamespace(
        _buttons=[('conquer', SimpleNamespace(rect=conquer_rect, disabled=False))]
    )
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_conquer_button'
    assert step['rect'] == conquer_rect


def test_kingdom_coach_routes_from_first_land_to_reward_pack_then_production():
    import pygame
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': ['kingdom_overview_window', 'kingdom_after_conquer_map'],
        'completed_steps': ['finish_first_conquer_battle'],
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen._kingdom_overview_dialogue = None
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

    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'open_main_booster_reward'
    assert step['button_label'] == 'Open Pack'
    assert step['navigate_screen'] == 'collection'

    # The duel is no longer wedged into the mandatory kingdom tour; after the
    # reward pack the loop pays off with production collection.
    screen.state.user_dict['onboarding']['completed_steps'].append(
        'open_first_main_booster')
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_production_intro'
    assert step['action'] == 'click'
    assert step['rect'] == screen._collect_all_rect


def test_kingdom_coach_shifts_to_post_battle_map_and_config_steps():
    import pygame
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': ['kingdom_overview_window'],
        'completed_steps': [
            'open_first_main_booster',
            'finish_first_conquer_battle',
        ],
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen._kingdom_overview_dialogue = None
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

    screen.state.user_dict['onboarding']['menu_hints_seen'] = [
        'kingdom_overview_window', 'kingdom_after_conquer_map']
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_production_intro'
    assert step['rect'] == screen._collect_all_rect

    # Production advances once the gold is actually collected (the step is
    # tracked server-side; the coach gates on the completed step, not on the
    # hint being seen).
    screen.state.user_dict['onboarding']['completed_steps'].append(
        'collect_first_kingdom_production')
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_defence_intro'

    screen.state.user_dict['onboarding']['completed_steps'].append(
        'save_first_defence_config')
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_config_intro'

    screen.state.user_dict['onboarding']['completed_steps'].remove(
        'save_first_defence_config')
    screen.state.user_dict['onboarding']['menu_hints_seen'] = [
        'kingdom_overview_window',
        'kingdom_after_conquer_map',
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
    # Conquer comes before boosters in onboarding, so the config coach must be
    # ready for a fresh account.
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'completed_steps': [],
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
        'conquer_config_prelude_spell',
        'conquer_config_to_battle',
    ]
    seen = []
    for step_id in expected:
        screen.state.user_dict['onboarding']['menu_hints_seen'] = list(seen)
        step = screen._current_conquer_coach_step()
        assert step['id'] == step_id
        if step_id in {
            'conquer_config_build_edit',
            'conquer_config_battle_plan',
            'conquer_config_prelude_spell',
        }:
            assert step['action'] == 'next'
            assert step['button_label'] == 'Got it'
        if step_id == 'conquer_config_to_battle':
            assert step['button_label'] == 'Got it'
        seen.append(step_id)


def test_conquer_second_build_coach_guides_manual_build():
    import pygame
    from game.screens.conquer_screen import ConquerScreen

    screen = object.__new__(ConquerScreen)
    # First conquest done, exactly one battle finished: the guided second
    # conquest where the player builds the attack by hand.
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'completed_steps': ['finish_first_conquer_battle'],
        'facts': {'conquer_battles': 1},
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen.dialogue_box = None
    screen._loading = False
    screen._error = None
    screen._config = {'land_id': 2, 'figures': [], 'battle_moves': []}
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
    screen._btn_battle = pygame.Rect(520, 380, 140, 42)

    # Empty config: coach the Build button first (clickable).
    step = screen._current_conquer_coach_step()
    assert step['id'] == 'conquer_build_yourself'
    assert step['action'] == 'click'
    assert step['rect'] == screen._btn_build

    # Until a figure exists, do not advance past the build step.
    screen.state.user_dict['onboarding']['menu_hints_seen'] = ['conquer_build_yourself']
    assert screen._current_conquer_coach_step() is None

    # Once a figure is built, guide tactics then Start Battle.
    screen._config['figures'] = [{'family_name': 'Djungle King'}]
    step = screen._current_conquer_coach_step()
    assert step['id'] == 'conquer_build_yourself_tactics'

    screen.state.user_dict['onboarding']['menu_hints_seen'] = [
        'conquer_build_yourself', 'conquer_build_yourself_tactics']
    step = screen._current_conquer_coach_step()
    assert step['id'] == 'conquer_build_yourself_battle'
    assert step['rect'] == screen._btn_battle

    # Tutorial-skipped players get no second-build coaching.
    screen.state.user_dict['onboarding']['onboarding_skipped'] = True
    screen.state.user_dict['onboarding']['menu_hints_seen'] = []
    screen._config['figures'] = []
    assert screen._current_conquer_coach_step() is None


def test_conquer_second_build_coach_inactive_after_two_battles():
    import pygame
    from game.screens.conquer_screen import ConquerScreen

    screen = object.__new__(ConquerScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'completed_steps': ['finish_first_conquer_battle'],
        'facts': {'conquer_battles': 2},
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen.dialogue_box = None
    screen._loading = False
    screen._error = None
    screen._config = {'land_id': 3, 'figures': [], 'battle_moves': []}
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
    screen._btn_battle = pygame.Rect(520, 380, 140, 42)

    # Past the second conquest (and first conquest done) -> no coach at all.
    assert screen._current_conquer_coach_step() is None


def test_explicit_missing_coach_step_does_not_use_stale_cached_step():
    import pygame

    screen, _ = _screen_with_gold(100)
    screen._menu_coach_step = {
        'id': 'stale_step',
        'rect': pygame.Rect(10, 10, 80, 40),
        'title': 'Old Step',
        'body': 'This step should not block events after a subscreen opens.',
    }

    event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(20, 20))

    assert screen._handle_menu_coach_events([event], None) is False


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


def test_defence_coach_walks_setup_steps_after_first_conquer():
    """The defence config should coach a brand-new owner through build →
    battle plan → final response → save (it had no coaching before)."""
    import pygame
    from game.screens.defence_screen import DefenceScreen

    screen = object.__new__(DefenceScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'completed_steps': [
            'open_first_main_booster', 'open_first_side_booster',
            'finish_first_conquer_battle',
        ],
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen._logout_dialogue = None
    screen.dialogue_box = None
    screen._loading = False
    screen._error = None
    screen._config = {'land_id': 1}
    screen._layout_built = True
    screen._active_subscreen = None
    screen._figure_detail_box = None
    screen._move_detail_box = None
    screen._active_info_key = None
    screen._btn_build = pygame.Rect(150, 80, 34, 34)
    screen._battle_plan_rect = pygame.Rect(260, 80, 180, 120)
    screen._counter_panel_rect = pygame.Rect(260, 340, 180, 120)
    screen._btn_save = pygame.Rect(520, 500, 140, 42)

    expected = ['defence_intro', 'defence_battle_plan',
                'defence_final_response', 'defence_save']
    seen = []
    for want in expected:
        screen.state.user_dict['onboarding']['menu_hints_seen'] = list(seen)
        step = screen._current_defence_coach_step()
        assert step is not None and step['id'] == want, (want, step)
        seen.append(want)
    screen.state.user_dict['onboarding']['menu_hints_seen'] = list(seen)
    assert screen._current_defence_coach_step() is None


def _menu_screen_for_completion(core_steps, *, welcome_pending=False, skipped=False):
    from game.screens.game_menu_screen import GameMenuScreen
    screen = object.__new__(GameMenuScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'core_steps': core_steps,
        'welcome_pending': welcome_pending,
        'onboarding_skipped': skipped,
    }})
    screen._tutorial_celebrated = set()
    return screen


def _core_step(step_id, *, completed, claimed, reward=None):
    return {'id': step_id, 'completed': completed, 'claimed': claimed,
            'reward': reward or {}}


def test_tutorial_completion_celebrates_conquer_then_duel():
    from game.screens.game_menu_screen import GameMenuScreen
    screen = _menu_screen_for_completion([
        _core_step('finish_tutorial', completed=True, claimed=False,
                   reward={'booster_packs': 6, 'booster_packs_side': 2}),
        _core_step('finish_first_duel', completed=True, claimed=False,
                   reward={'booster_packs': 3}),
    ])
    pending = screen._pending_tutorial_completion()
    assert pending is not None
    assert pending[0] == 'finish_tutorial'
    assert 'Conquer Tutorial Complete' in pending[1]

    # Once celebrated, it advances to the duel tutorial.
    screen._tutorial_celebrated.add('finish_tutorial')
    pending = screen._pending_tutorial_completion()
    assert pending[0] == 'finish_first_duel'
    assert 'Duel Tutorial Complete' in pending[1]


def test_tutorial_completion_skips_claimed_and_incomplete():
    screen = _menu_screen_for_completion([
        _core_step('finish_tutorial', completed=True, claimed=True),
        _core_step('finish_first_duel', completed=False, claimed=False),
    ])
    assert screen._pending_tutorial_completion() is None


def test_tutorial_completion_suppressed_while_welcome_pending():
    screen = _menu_screen_for_completion([
        _core_step('finish_tutorial', completed=True, claimed=False),
    ], welcome_pending=True)
    assert screen._pending_tutorial_completion() is None


def test_tutorial_completion_suppressed_when_skipped():
    screen = _menu_screen_for_completion([
        _core_step('finish_tutorial', completed=True, claimed=False),
    ], skipped=True)
    assert screen._pending_tutorial_completion() is None


def test_reward_reveal_items_covers_all_kinds():
    from game.screens.game_menu_screen import GameMenuScreen
    items = GameMenuScreen._reward_reveal_items(
        {'gold': 50, 'booster_packs': 6, 'booster_packs_side': 2, 'maps': 4})
    kinds = [it['kind'] for it in items]
    assert kinds == ['gold', 'main_booster', 'side_booster', 'map']
    assert all(it['label'] and it['description'] for it in items)


def _kingdom_overview_screen(seen=None, skipped=False, loaded=True):
    import pygame
    from game.screens.kingdom_screen import KingdomScreen
    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    if not pygame.font.get_init():
        pygame.font.init()
    screen = object.__new__(KingdomScreen)
    screen.window = pygame.display.get_surface()
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': list(seen or []),
        'completed_steps': [],
        'onboarding_skipped': skipped,
    }})
    screen._onboarding_guide_open = False
    screen.dialogue_box = None
    screen._thread = None
    screen._new_msg_picker = None
    screen._detail_box = None
    screen._kingdom_overview_dialogue = None
    screen._hex_map = object() if loaded else None
    screen._loading = not loaded
    screen._error = None
    return screen


def test_kingdom_overview_window_shows_once_on_first_open():
    screen = _kingdom_overview_screen(seen=[])
    screen._maybe_show_kingdom_overview()
    assert screen._kingdom_overview_dialogue is not None
    # The kingdom coach is suppressed while the window is up.
    assert screen._kingdom_coach_ready() is False


def test_kingdom_overview_window_suppressed_after_seen():
    screen = _kingdom_overview_screen(seen=['kingdom_overview_window'])
    screen._maybe_show_kingdom_overview()
    assert screen._kingdom_overview_dialogue is None
    assert screen._kingdom_coach_ready() is True


def test_kingdom_overview_window_suppressed_when_skipped():
    screen = _kingdom_overview_screen(seen=[], skipped=True)
    screen._maybe_show_kingdom_overview()
    assert screen._kingdom_overview_dialogue is None


def test_kingdom_overview_window_waits_for_map_load():
    screen = _kingdom_overview_screen(seen=[], loaded=False)
    screen._maybe_show_kingdom_overview()
    assert screen._kingdom_overview_dialogue is None


def test_tutorial_completion_available_on_any_menu_mixin_screen():
    # The celebration logic lives on MenuScreenMixin, so non-menu tutorial
    # screens (e.g. the kingdom-config screen) can fire it after the last card.
    from game.screens._menu_base import MenuScreenMixin
    screen = object.__new__(MenuScreenMixin)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'core_steps': [
            {'id': 'finish_tutorial', 'completed': True, 'claimed': False,
             'reward': {'booster_packs': 6, 'booster_packs_side': 2}},
        ],
        'welcome_pending': False,
        'onboarding_skipped': False,
    }})
    screen._tutorial_celebrated = set()
    pending = screen._pending_tutorial_completion()
    assert pending is not None and pending[0] == 'finish_tutorial'
    # Items render with explanations.
    items = MenuScreenMixin._reward_reveal_items(pending[3])
    assert [it['kind'] for it in items] == ['main_booster', 'side_booster']


def test_welcome_sequence_advances_through_stages_then_marks_seen():
    from game.screens.game_menu_screen import GameMenuScreen
    screen = object.__new__(GameMenuScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {'welcome_pending': True}})
    screen._welcome_present_dialogue = None
    screen._starter_reveal_dialogue = None
    screen._welcome_stage = 0
    marked = []
    screen._mark_welcome_seen = lambda: marked.append(True)

    class _FakeDlg:
        def update(self, events):
            return 'done'

    # Three welcome stages: each dismiss advances; the last marks welcome seen.
    for expected_stage in range(GameMenuScreen._WELCOME_STAGES):
        screen._welcome_present_dialogue = _FakeDlg()
        assert screen._handle_welcome_present_events([]) is True
        assert screen._welcome_stage == expected_stage + 1
    assert marked == [True]
