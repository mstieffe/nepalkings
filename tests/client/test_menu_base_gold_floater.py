# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for shared menu chrome gold-gain floater bookkeeping."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


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


def _daily_quest_screen(quest=None):
    import pygame
    from config import settings
    from game.screens._menu_base import MenuScreenMixin

    _ensure_pygame_display()
    screen = object.__new__(MenuScreenMixin)
    screen.window = pygame.Surface((620, 180), pygame.SRCALPHA)
    screen.state = SimpleNamespace(user_dict={
        'gold': 100,
        'onboarding': {'daily_quest': quest} if quest is not None else {},
    })
    screen._onboarding_guide_buttons = []
    screen._onboarding_guide_font = settings.get_font(max(16, int(0.020 * settings.SCREEN_HEIGHT)))
    screen._onboarding_guide_small_font = settings.get_font(max(14, int(0.017 * settings.SCREEN_HEIGHT)))
    screen._onboarding_guide_section_font = settings.get_font(
        max(18, int(0.023 * settings.SCREEN_HEIGHT)), bold=True)
    screen._onboarding_guide_icon_cache = {}

    def icon(color):
        surf = pygame.Surface((24, 24), pygame.SRCALPHA)
        surf.fill(color)
        return surf

    screen._gold_icon = icon((220, 180, 70, 255))
    screen._booster_icon = icon((90, 150, 220, 255))
    screen._booster_side_icon = icon((170, 120, 220, 255))
    screen._map_icon = icon((120, 190, 120, 255))
    return screen


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


def test_daily_quest_countdown_text_formats_reset_time():
    screen = _daily_quest_screen()
    future = datetime.now(timezone.utc) + timedelta(hours=2, minutes=4)

    assert screen._daily_quest_countdown_text(future.isoformat()).startswith('Resets in 2h')
    assert screen._daily_quest_countdown_text(datetime.now(timezone.utc).isoformat()) == 'Resets soon'
    assert screen._daily_quest_countdown_text('') == ''
    assert screen._daily_quest_countdown_text('not-a-date') == ''


def test_daily_quest_claimable_card_registers_claim_button():
    import pygame

    screen = _daily_quest_screen({
        'title': 'Finish 1 duel',
        'description': 'Play one full duel today.',
        'progress': 1,
        'target': 1,
        'claimable': True,
        'claimed': False,
        'reward': {'gold': 60},
        'resets_at': (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
    })

    screen._draw_onboarding_area_overview(pygame.Rect(10, 10, 560, 120))

    assert any(action == ('claim', 'daily_quest')
               for _rect, action in screen._onboarding_guide_buttons)


def test_guide_tab_badges_separate_lessons_from_goals_and_daily_rewards():
    screen, _ = _screen_with_gold(100)
    screen.state.user_dict['onboarding'] = {
        'pending_reward_count': 4,
        'core_steps': [
            {'id': 'journey_ready', 'claimable': True},
            {'id': 'journey_done', 'claimable': False},
        ],
        'daily_quest': {'claimable': True},
        'early_goals': [
            {'id': 'goal_ready_1', 'claimable': True},
            {'id': 'goal_ready_2', 'claimable': True},
            {'id': 'goal_done', 'claimable': False},
        ],
    }

    counts = screen._onboarding_guide_tab_badge_counts()

    assert counts == {'journey': 1, 'goals': 3, 'rulebook': 0}


def test_goal_accomplishment_lights_goals_tab_not_journey():
    screen, _ = _screen_with_gold(100)
    screen.state.user_dict['onboarding'] = {
        'pending_reward_count': 1,
        'core_steps': [],
        'daily_quest': {'claimable': False},
        'early_goals': [{'id': 'goal_ready', 'claimable': True}],
    }

    counts = screen._onboarding_guide_tab_badge_counts()

    assert counts['journey'] == 0
    assert counts['goals'] == 1
    assert counts['rulebook'] == 0


def test_guide_uses_journey_goals_and_rulebook_tabs():
    from game.screens._menu_base import MenuScreenMixin

    assert MenuScreenMixin._GUIDE_TABS == (
        ('journey', 'Journey'),
        ('goals', 'Goals'),
        ('rulebook', 'Rulebook'),
    )


def test_journey_catalogue_contains_first_journey_and_every_lesson():
    from game.screens._menu_base import MenuScreenMixin

    screen = object.__new__(MenuScreenMixin)
    onboarding = {
        'welcome_seen': True,
        'next_action': {
            'screen': 'kingdom',
            'label': 'Conquer First Land',
        },
        'core_steps': [
            {
                'id': 'finish_first_conquer_battle',
                'group': 'first_journey',
                'completed': False,
                'reward': {},
            },
            {
                'id': 'finish_tutorial',
                'group': 'first_journey',
                'completed': False,
                'claimed': False,
                'claimable': False,
                'reward': {'gold': 2000, 'booster_packs': 7},
            },
        ],
        'lessons': [
            {
                'id': lesson_id,
                'group': 'lessons',
                'title': title,
                'completed': False,
            }
            for lesson_id, title in (
                ('grow_collection', 'Grow Your Collection'),
                ('build_attack', 'Build Your Own Attack'),
                ('run_kingdom', 'Run Your Kingdom'),
                ('defend_land', 'Defend Your Land'),
                ('duel_basics', 'Duel Basics'),
            )
        ],
    }

    catalogue = screen._onboarding_journey_catalogue(onboarding)

    assert [item['id'] for item in catalogue] == [
        'finish_tutorial',
        'grow_collection',
        'build_attack',
        'run_kingdom',
        'defend_land',
        'duel_basics',
    ]
    assert catalogue[0]['title'] == 'Your Path to the Crown'
    assert catalogue[0]['reward'] == {
        'gold': 2000,
        'booster_packs': 7,
    }
    assert catalogue[0]['entry_screen'] == 'kingdom'
    assert catalogue[0]['started'] is True


def test_lesson_catalogue_card_registers_start_and_first_journey_actions():
    import pygame

    screen = _daily_quest_screen()
    screen.window = pygame.Surface((760, 320), pygame.SRCALPHA)
    screen._onboarding_guide_buttons = []
    screen._draw_onboarding_lesson_card(
        {
            'id': 'grow_collection',
            'title': 'Grow Your Collection',
            'description': 'Open both pack types.',
            'reward': {'booster_packs': 2},
            'progress_label': '0/6',
            'completed': False,
            'started': False,
            'locked': False,
        },
        pygame.Rect(10, 10, 700, 136),
    )
    screen._draw_onboarding_lesson_card(
        {
            'id': 'finish_tutorial',
            'title': 'Your Path to the Crown',
            'description': 'Conquer your first land.',
            'reward': {'gold': 2000},
            'progress_label': '1/2',
            'completed': False,
            'started': True,
            'locked': False,
            'first_journey': True,
            'entry_screen': 'kingdom',
        },
        pygame.Rect(10, 160, 700, 136),
    )

    actions = [
        action for _rect, action in screen._onboarding_guide_buttons
    ]
    assert ('start_lesson', 'grow_collection') in actions
    assert ('continue_journey', 'kingdom') in actions


def test_completed_lesson_catalogue_card_registers_reward_free_replay():
    import pygame

    screen = _daily_quest_screen()
    screen.window = pygame.Surface((760, 170), pygame.SRCALPHA)
    screen._onboarding_guide_buttons = []
    screen._draw_onboarding_lesson_card(
        {
            'id': 'run_kingdom',
            'title': 'Run Your Kingdom',
            'description': 'Manage production and style.',
            'reward': {'gold': 500, 'maps': 1},
            'progress_label': '5/5',
            'completed': True,
            'claimed': True,
            'claimable': False,
        },
        pygame.Rect(10, 10, 700, 136),
    )

    actions = [
        action for _rect, action in screen._onboarding_guide_buttons
    ]
    assert actions == [('start_lesson', 'run_kingdom')]


def test_replay_completed_steps_only_counts_actions_repeated_this_session():
    from game.screens._menu_base import MenuScreenMixin

    screen = object.__new__(MenuScreenMixin)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'replaying_lesson': 'grow_collection',
        'completed_steps': [
            'finish_tutorial',
            'open_first_main_booster',
            'open_first_side_booster',
            'sell_first_card',
            'trade_first_card',
            'finish_collection_lesson',
        ],
        'lesson_replay_steps': ['open_first_main_booster'],
        'lesson_skipped_steps': ['open_first_side_booster'],
    }})

    assert screen._onboarding_completed_steps() == {
        'finish_tutorial',
        'open_first_main_booster',
        'open_first_side_booster',
    }


def test_replay_payload_does_not_merge_back_cleared_historical_hints():
    from game.screens._menu_base import MenuScreenMixin

    screen = object.__new__(MenuScreenMixin)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': ['kingdom_management_intro'],
    }})
    incoming = {
        'replaying_lesson': 'run_kingdom',
        'menu_hints_seen': [],
        'duel_hints_seen': [],
    }

    assert screen._merge_onboarding_state(incoming) == incoming


def test_starting_same_replay_again_reenables_its_finish_window():
    from game.screens._menu_base import MenuScreenMixin

    screen = object.__new__(MenuScreenMixin)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'replaying_lesson': None,
    }})
    screen._menu_chrome_username = None
    screen._tutorial_celebrated = {'replay:grow_collection'}
    screen._sync_menu_user_context = lambda: None

    screen._apply_onboarding_payload({
        'onboarding': {
            'replaying_lesson': 'grow_collection',
            'menu_hints_seen': [],
            'duel_hints_seen': [],
        },
    })

    assert 'replay:grow_collection' not in screen._tutorial_celebrated


def test_active_replay_clears_stale_finish_guard_on_destination_screen():
    from game.screens._menu_base import MenuScreenMixin

    screen = object.__new__(MenuScreenMixin)
    onboarding = {
        'welcome_pending': False,
        'onboarding_skipped': False,
        'replaying_lesson': 'defend_land',
        'replay_completion_pending': None,
        'core_steps': [],
        'lessons': [],
    }
    screen.state = SimpleNamespace(user_dict={'onboarding': onboarding})
    screen._tutorial_celebrated = {'replay:defend_land'}

    assert screen._pending_tutorial_completion() is None
    assert 'replay:defend_land' not in screen._tutorial_celebrated

    onboarding['replaying_lesson'] = None
    onboarding['replay_completion_pending'] = 'defend_land'
    onboarding['lessons'] = [{
        'id': 'defend_land',
        'completion_step': 'finish_defend_land_lesson',
    }]

    pending = screen._pending_tutorial_completion()
    assert pending is not None
    assert pending[0] == 'replay:defend_land'
    assert pending[4] == 'defend_land'


def test_goals_tab_owns_daily_quest_and_goal_claim_actions():
    import pygame

    screen = _daily_quest_screen()
    screen.window = pygame.Surface((900, 700), pygame.SRCALPHA)
    screen.state.user_dict['onboarding'] = {
        'daily_quest': {
            'title': 'Finish 1 duel',
            'description': 'Play one full duel today.',
            'progress': 1,
            'target': 1,
            'claimable': True,
            'claimed': False,
            'reward': {'gold': 60},
            'resets_at': (
                datetime.now(timezone.utc) + timedelta(hours=3)
            ).isoformat(),
        },
        'early_goals': [{
            'id': 'win_first_duel',
            'title': 'Win your first duel',
            'description': 'Win any finished duel.',
            'completed': True,
            'claimable': True,
            'reward': {'gold': 75},
        }],
    }
    screen._onboarding_guide_buttons = []
    screen._onboarding_guide_item_rects = {}
    screen._onboarding_guide_section_header_rects = {}
    screen._onboarding_guide_scroll = 0
    screen._onboarding_guide_scroll_area = None
    screen._onboarding_guide_content_h = 0

    screen._draw_onboarding_guide_goals(
        pygame.Rect(40, 30, 800, 620),
        120,
    )

    actions = [
        action for _rect, action in screen._onboarding_guide_buttons
    ]
    assert ('claim', 'daily_quest') in actions
    assert ('claim', 'win_first_duel') in actions


def test_daily_quest_locked_and_missing_cards_do_not_register_claim_button():
    import pygame

    locked = _daily_quest_screen({
        'locked': True,
        'title': 'Daily Quest',
        'description': 'Conquer your first land to unlock daily quests.',
        'progress': 0,
        'target': 1,
        'claimable': False,
        'reward': {},
    })
    locked._draw_onboarding_area_overview(pygame.Rect(10, 10, 560, 120))

    missing = _daily_quest_screen()
    missing._draw_onboarding_area_overview(pygame.Rect(10, 10, 560, 120))

    assert locked._onboarding_guide_buttons == []
    assert missing._onboarding_guide_buttons == []


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


def test_guide_prioritizes_server_next_action_then_optional_learning():
    from game.screens._menu_base import MenuScreenMixin

    screen = object.__new__(MenuScreenMixin)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'next_action': {'screen': 'kingdom', 'label': 'Conquer First Land'},
        'core_steps': [],
    }})
    assert screen._guide_next_action()['screen'] == 'kingdom'

    screen.state.user_dict['onboarding'] = {
        'next_action': None,
        'active_lesson': None,
        'lessons': [{
            'id': 'duel_basics',
            'title': 'Duel Basics',
            'completed': False,
            'group': 'lessons',
            'entry_screen': 'duel_menu',
            'entry_label': 'Start Duel Basics',
        }],
    }
    assert screen._guide_next_action() == {
        'screen': 'duel_menu',
        'label': 'Start Duel Basics',
        'target_id': 'duel_basics',
        'lesson_id': 'duel_basics',
    }


def test_guide_collapses_completed_nonclaimable_rows():
    from game.screens._menu_base import MenuScreenMixin

    items = [
        {'id': 'done', 'completed': True, 'claimable': False},
        {'id': 'reward', 'completed': True, 'claimable': True},
        {'id': 'next', 'completed': False, 'claimable': False},
    ]
    assert [item['id'] for item in MenuScreenMixin._onboarding_pending_items(items)] == [
        'reward', 'next']


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


def test_optional_menu_lesson_step_skip_keeps_lesson_active(
        monkeypatch):
    import pygame
    from game.screens import _menu_base

    screen, _ = _screen_with_gold(100)
    screen.state.user_dict['onboarding'] = {
        'onboarding_skipped': False,
        'menu_hints_seen': [],
        'active_lesson': 'defend_land',
    }
    messages = []
    screen.state.set_msg = messages.append
    monkeypatch.setattr(
        _menu_base.onboarding_service,
        'skip_lesson_step',
        lambda lesson_id, step_id: {
            'onboarding': {
                'onboarding_skipped': False,
                'menu_hints_seen': [step_id],
                'lesson_skipped_steps': [step_id],
                'active_lesson': lesson_id,
                'lessons_dismissed': [],
            },
        },
    )
    screen._menu_coach_step = {
        'id': 'defence_save',
        'rect': pygame.Rect(10, 10, 120, 40),
        'action': 'next',
    }
    skip_rect = pygame.Rect(240, 80, 150, 32)
    screen._menu_coach_buttons = [
        (skip_rect, ('skip_lesson_step', 'defence_save'))]
    screen._menu_coach_pressed_button_action = None

    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=skip_rect.center)
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=skip_rect.center)
    assert screen._handle_menu_coach_events([down]) is True
    assert screen._handle_menu_coach_events([up]) is True
    assert screen.state.user_dict['onboarding']['onboarding_skipped'] is False
    assert screen.state.user_dict['onboarding']['menu_hints_seen'] == [
        'defence_save']
    assert screen.state.user_dict['onboarding']['active_lesson'] == (
        'defend_land')
    assert screen.state.user_dict['onboarding']['lessons_dismissed'] == []
    assert messages == ['Step skipped. Continue with the next step.']


def test_skippable_menu_lesson_card_draws_step_skip_not_lesson_dismiss():
    import pygame
    from config import settings

    _ensure_pygame_display()
    screen, _ = _screen_with_gold(100)
    screen.window = pygame.Surface(
        (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen.state.user_dict['onboarding'] = {
        'onboarding_skipped': False,
        'active_lesson': 'grow_collection',
        'menu_hints_seen': [],
    }
    screen._menu_coach_font = settings.get_font(
        max(14, int(0.018 * settings.SCREEN_HEIGHT)))
    screen._menu_coach_title_font = settings.get_font(
        max(16, int(0.024 * settings.SCREEN_HEIGHT)), bold=True)
    step = {
        'id': 'collection_growth_main',
        'title': 'Open a Main Pack',
        'body': 'Open a Main Pack to add cards to your Collection.',
        'rect': pygame.Rect(120, 120, 96, 32),
        'action': 'click',
    }

    screen._draw_menu_coach(step)

    actions = [action for _rect, action in screen._menu_coach_buttons]
    assert ('skip_lesson_step', 'collection_growth_main') in actions
    assert ('skip_tutorial', 'collection_growth_main') in actions
    assert all(action[0] != 'dismiss_lesson' for action in actions)


def test_final_menu_coach_draws_finish_instead_of_skip():
    import pygame
    from config import settings

    _ensure_pygame_display()
    screen, _ = _screen_with_gold(100)
    screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen.state.user_dict['onboarding'] = {
        'onboarding_skipped': False,
        'menu_hints_seen': [],
    }
    screen._menu_coach_font = settings.get_font(
        max(14, int(0.018 * settings.SCREEN_HEIGHT)))
    screen._menu_coach_title_font = settings.get_font(
        max(16, int(0.024 * settings.SCREEN_HEIGHT)), bold=True)
    step = {
        'id': 'kingdom_after_conquer_map',
        'title': 'Your First Land!',
        'body': 'You took your first land.',
        'rect': pygame.Rect(120, 120, 96, 32),
        'action': 'coach',
        'finish_tutorial_button': True,
    }

    screen._draw_menu_coach(step)

    actions = [action for _rect, action in screen._menu_coach_buttons]
    assert ('finish_tutorial', 'kingdom_after_conquer_map') in actions
    assert all(action[0] != 'skip_tutorial' for action in actions)


def test_menu_coach_finish_button_calls_finish_hook():
    import pygame

    screen, _ = _screen_with_gold(100)
    screen._menu_coach_step = {
        'id': 'kingdom_after_conquer_map',
        'rect': pygame.Rect(10, 10, 120, 40),
        'action': 'coach',
        'finish_tutorial_button': True,
    }
    finish_rect = pygame.Rect(240, 80, 150, 32)
    screen._menu_coach_buttons = [
        (finish_rect, ('finish_tutorial', 'kingdom_after_conquer_map')),
    ]
    screen._menu_coach_pressed_button_action = None
    called = []
    screen._finish_menu_coach_tutorial = lambda step_id: called.append(step_id)

    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=finish_rect.center)
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=finish_rect.center)

    assert screen._handle_menu_coach_events([down]) is True
    assert screen._handle_menu_coach_events([up]) is True
    assert called == ['kingdom_after_conquer_map']


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
            'onboarding': {
                'completed_steps': ['finish_duel_basics_lesson']},
        }
    ))

    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=claim_rect.center)
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=claim_rect.center)

    assert screen._handle_onboarding_guide_events([down]) is True
    assert screen._handle_onboarding_guide_events([up]) is True
    assert claimed == ['first_duel']


def test_onboarding_guide_draws_start_button_for_follow_up_lesson():
    import pygame
    from config import settings

    _ensure_pygame_display()
    screen, _ = _screen_with_gold(100)
    screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen.state.user_dict['onboarding'] = {
        'completed_steps': ['finish_tutorial'],
        'onboarding_skipped': False,
    }
    screen._onboarding_guide_buttons = []
    screen._onboarding_guide_item_rects = {}
    screen._onboarding_guide_section_header_rects = {}
    screen._onboarding_guide_icon_cache = {}
    screen._onboarding_guide_section_font = settings.get_font(settings.FS_SMALL, bold=True)
    screen._onboarding_guide_font = settings.get_font(settings.FS_SMALL)
    screen._onboarding_guide_small_font = settings.get_font(settings.FS_TINY)
    icon = pygame.Surface((18, 18), pygame.SRCALPHA)
    screen._gold_icon = icon
    screen._booster_icon = icon
    screen._booster_side_icon = icon
    screen._map_icon = icon

    screen._draw_onboarding_guide_section(
        'Checklist',
        [{
            'id': 'duel_basics',
            'title': 'Duel Basics',
            'description': 'Play a guided duel from start to finish.',
            'reward': {'booster_packs': 3},
            'lesson': True,
            'total_steps': 8,
            'progress_label': '0/8',
            'completed': False,
            'locked': False,
        }],
        pygame.Rect(20, 20, 420, 90),
    )

    actions = [action for _rect, action in screen._onboarding_guide_buttons]
    assert ('start_lesson', 'duel_basics') in actions


def test_completed_lesson_claim_button_uses_completion_reward_id():
    import pygame
    from config import settings

    _ensure_pygame_display()
    screen, _ = _screen_with_gold(100)
    screen.window = pygame.Surface(
        (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen._onboarding_guide_buttons = []
    screen._onboarding_guide_item_rects = {}
    screen._onboarding_guide_section_header_rects = {}
    screen._onboarding_guide_icon_cache = {}
    screen._onboarding_guide_section_font = settings.get_font(
        settings.FS_SMALL, bold=True)
    screen._onboarding_guide_font = settings.get_font(settings.FS_SMALL)
    screen._onboarding_guide_small_font = settings.get_font(settings.FS_TINY)
    icon = pygame.Surface((18, 18), pygame.SRCALPHA)
    screen._gold_icon = icon
    screen._booster_icon = icon
    screen._booster_side_icon = icon
    screen._map_icon = icon

    screen._draw_onboarding_guide_section(
        'Lessons',
        [{
            'id': 'duel_basics',
            'reward_id': 'finish_duel_basics_lesson',
            'title': 'Duel Basics',
            'description': 'Play a guided duel.',
            'reward': {'booster_packs': 3},
            'lesson': True,
            'total_steps': 10,
            'progress_label': '10/10',
            'completed': True,
            'claimable': True,
        }],
        pygame.Rect(20, 20, 420, 90),
    )

    actions = [action for _rect, action in screen._onboarding_guide_buttons]
    assert ('claim', 'finish_duel_basics_lesson') in actions


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

    # Action-first: reveal the prepared starter set in Collection.
    step = screen._current_area_coach_step()
    assert step['id'] == 'open_starter_cards'
    assert step['rect'] == screen.button_collection.rect


def _journey_ready_menu_screen(completed_steps):
    """A GameMenuScreen with every area + guide hint already seen, so the
    next coach step comes from the collection-first journey."""
    import pygame
    from game.screens.game_menu_screen import GameMenuScreen

    seen = [
        'kingdom', 'collection', 'duel', 'rankings',
        'guide', 'guide_rewards_track',
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


def test_main_menu_journey_coach_routes_starter_reveal_then_conquer():
    # Fresh account: visit Collection to learn cards and run the roulette.
    screen = _journey_ready_menu_screen(completed_steps=[])
    step = screen._current_area_coach_step()
    assert step['id'] == 'open_starter_cards'
    assert step['rect'] == screen.button_collection.rect
    assert step['title'] == 'Visit Your Collection'
    assert step['body'] == (
        'This is the main menu. Let us visit your collection first, where all '
        'your personal cards are stored that you have gathered.')

    # Starter set revealed: now conquer the first land.
    screen.state.user_dict['onboarding']['menu_hints_seen'].append(
        'starter_suit_reveal')
    step = screen._current_area_coach_step()
    assert step['id'] == 'post_starter_cards_kingdom'
    assert step['rect'] == screen.button_kingdom.rect

    # First land conquered but the final kingdom card has not been acknowledged:
    # steer back to the kingdom, NOT to production collection or a duel.
    screen.state.user_dict['onboarding']['completed_steps'].append(
        'finish_first_conquer_battle')
    step = screen._current_area_coach_step()
    assert step['id'] == 'return_to_kingdom_loop'
    assert step['rect'] == screen.button_kingdom.rect
    assert 'first land' in step['body']

    # Tutorial finished: the duel is NOT pushed here. With the guide hint
    # already seen, the menu coaching simply goes quiet.
    screen.state.user_dict['onboarding']['completed_steps'].append(
        'finish_tutorial')
    assert screen._current_area_coach_step() is None


def test_duel_never_blocks_tutorial_completion_in_journey():
    # Tutorial complete WITHOUT a duel: the journey coach goes quiet. The duel
    # is never a journey step and is no longer pushed here — it's mentioned in
    # the completion box and started from the Duel menu on opt-in.
    screen = _journey_ready_menu_screen(completed_steps=[
        'finish_first_conquer_battle',
        'finish_tutorial',
    ])
    assert screen._current_journey_coach_step() is None


def test_menu_coach_quiet_after_tutorial_complete():
    # The guide icon is no longer coach-pointed: once the journey is done the
    # menu shows no coaching card at all (the guide prompt interrupted the flow
    # without adding value and was removed).
    screen = _journey_ready_menu_screen(completed_steps=[
        'finish_first_conquer_battle',
        'finish_tutorial',
        'finish_first_duel',
    ])
    screen.state.user_dict['onboarding']['menu_hints_seen'] = [
        'duel', 'kingdom', 'collection', 'rankings',
    ]
    assert screen._current_area_coach_step() is None


def test_menu_coach_does_not_point_at_guide_before_final_land_card():
    # Even while the final "Your First Land" card is unfinished, the menu does
    # not surface a guide coach card; only the actionable journey steps appear.
    screen = _journey_ready_menu_screen(completed_steps=[
        'finish_first_conquer_battle',
    ])
    # return_to_kingdom_loop already seen, so the journey coach is quiet and the
    # (removed) guide walkthrough must not take its place.
    screen.state.user_dict['onboarding']['menu_hints_seen'] = [
        'duel', 'kingdom', 'collection', 'rankings',
        'return_to_kingdom_loop',
    ]
    assert screen._current_area_coach_step() is None


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


def test_kingdom_coach_offers_retry_after_lost_first_conquest():
    # Lost the first conquest (a battle finished but no land won): the coach
    # re-guides the no-penalty retry, pointing back at the marked land.
    import pygame
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': ['kingdom_overview_window', 'kingdom_pick_land'],
        'completed_steps': ['open_first_main_booster'],
        'facts': {'conquer_battles': 1},
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

    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_conquer_retry'
    assert step['rect'] == screen._map_viewport_rect
    assert step['mark_on_click'] is False  # re-shows until they win


def test_kingdom_coach_finishes_on_first_land_card():
    import pygame
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': ['kingdom_overview_window'],
        'completed_steps': ['finish_first_conquer_battle', 'open_first_main_booster'],
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
    assert step['id'] == 'kingdom_after_conquer_map'
    assert step['action'] == 'coach'
    assert step['rect'] == screen._map_viewport_rect
    assert step['interactive_rects'] == [screen._map_viewport_rect]
    assert step['finish_tutorial_button'] is True


def test_kingdom_coach_ends_after_first_land_finish_card_seen():
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
    assert screen._current_kingdom_coach_step() is None


def _follow_up_kingdom_screen(active_lesson):
    import pygame
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [
            'kingdom_overview_window',
            'kingdom_after_conquer_map',
        ],
        'completed_steps': [
            'finish_first_conquer_battle',
            'finish_tutorial',
        ],
        'active_lesson': active_lesson,
    }})
    screen._onboarding_guide_open = False
    screen._welcome_present_dialogue = None
    screen._kingdom_overview_dialogue = None
    screen._kingdom_management_dialogue = None
    screen._logout_dialogue = None
    screen.dialogue_box = None
    screen._thread = None
    screen._new_msg_picker = None
    screen._detail_box = None
    screen._hex_map = object()
    screen._loading = False
    screen._error = None
    screen._map_viewport_rect = pygame.Rect(50, 60, 300, 220)
    screen._kingdom_chip_gear_rect = pygame.Rect(60, 28, 28, 28)
    screen._collect_all_rect = pygame.Rect(340, 32, 110, 34)
    screen._collect_all_enabled = False
    return screen


def test_build_attack_lesson_guides_land_then_conquer_button():
    import pygame

    screen = _follow_up_kingdom_screen('build_attack')
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'conquer_choose_next_land'

    conquer_rect = pygame.Rect(120, 180, 140, 34)
    screen._detail_box = SimpleNamespace(
        _buttons=[
            ('conquer', SimpleNamespace(
                rect=conquer_rect, disabled=False)),
        ],
    )
    screen.state.user_dict['onboarding']['menu_hints_seen'].append(
        'conquer_choose_next_land')
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'conquer_open_next_attack'
    assert step['rect'] == conquer_rect


def test_defend_land_lesson_guides_owned_land_then_defence_button():
    import pygame

    screen = _follow_up_kingdom_screen('defend_land')
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'defence_choose_land'

    defence_rect = pygame.Rect(120, 180, 140, 34)
    screen._detail_box = SimpleNamespace(
        _buttons=[
            ('defence', SimpleNamespace(
                rect=defence_rect, disabled=False)),
        ],
    )
    screen.state.user_dict['onboarding']['menu_hints_seen'].append(
        'defence_choose_land')
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'defence_open_config'
    assert step['rect'] == defence_rect


def test_run_kingdom_lesson_guides_collection_then_management():
    screen = _follow_up_kingdom_screen('run_kingdom')
    screen.state.user_dict['onboarding']['menu_hints_seen'].append(
        'kingdom_management_intro')

    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_collect_production'
    assert step['action'] == 'next'
    assert step['title'] == 'Production Appears Here'

    screen._collect_all_enabled = True
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_collect_production'
    assert step['rect'] == screen._collect_all_rect
    assert step['action'] == 'click'

    screen.state.user_dict['onboarding']['menu_hints_seen'].append(
        'kingdom_collect_production')
    step = screen._current_kingdom_coach_step()
    assert step['id'] == 'kingdom_open_management'
    assert step['rect'] == screen._kingdom_chip_gear_rect
    assert step['action'] == 'click'


def test_kingdom_lessons_open_matching_illustrated_intro(monkeypatch):
    from game.components import tutorial_window

    created = []

    class FakeTutorialWindow:
        def __init__(self, _window, pages, *, title, **_kwargs):
            self.pages = pages
            self.title = title
            created.append(self)

        def update(self, _events):
            return 'done'

    monkeypatch.setattr(
        tutorial_window, 'TutorialWindowDialogue', FakeTutorialWindow)

    cases = (
        ('build_attack', 'build_attack_intro_window',
         'Build Your Own Attack'),
        ('run_kingdom', 'kingdom_management_intro', 'Run Your Kingdom'),
        ('defend_land', 'defend_land_intro_window', 'Defend Your Land'),
    )
    for lesson_id, step_id, title in cases:
        screen = _follow_up_kingdom_screen(lesson_id)
        screen.window = object()
        marked = []
        screen._mark_menu_coach_seen = marked.append

        screen._maybe_show_kingdom_management_intro()

        dialogue = screen._kingdom_management_dialogue
        assert dialogue is created[-1]
        assert dialogue.title == title
        assert dialogue.pages[0]['image_frame'] is False
        assert screen._kingdom_management_intro_step_id == step_id
        assert screen._handle_kingdom_management_events([]) is True
        assert marked == [step_id]


def test_kingdom_finish_tutorial_button_marks_first_land_seen_and_complete():
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    marked_seen = []
    marked_steps = []
    screen._mark_menu_coach_seen = lambda step_id: marked_seen.append(step_id)
    screen._complete_onboarding_step = lambda step_id: (
        marked_steps.append(step_id) or True)

    screen._finish_menu_coach_tutorial('kingdom_after_conquer_map')

    assert marked_seen == ['kingdom_after_conquer_map']
    assert marked_steps == ['finish_tutorial']


def test_conquer_coach_collapses_to_single_battle_handoff():
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

    # The pre-assembled first attack collapses to a single hand-off window
    # anchored on Start Battle; once seen, there is no further setup coaching.
    step = screen._current_conquer_coach_step()
    assert step['id'] == 'conquer_config_to_battle'
    assert step['rect'] == screen._btn_battle
    assert step['action'] == 'next'
    assert step['button_label'] == 'Start Battle'

    screen.state.user_dict['onboarding']['menu_hints_seen'] = ['conquer_config_to_battle']
    assert screen._current_conquer_coach_step() is None


def test_conquer_coach_handoff_launches_battle_directly():
    from game.screens.conquer_screen import ConquerScreen

    screen = object.__new__(ConquerScreen)
    screen.state = SimpleNamespace(screen='conquer')
    screen._menu_coach_step = {'id': 'conquer_config_to_battle'}
    launched = []
    screen._on_battle_click = lambda: launched.append(True)

    screen._after_menu_coach_next('conquer_config_to_battle')

    assert launched == [True]


def test_conquer_second_build_coach_guides_manual_build():
    import pygame
    from game.screens.conquer_screen import ConquerScreen

    screen = object.__new__(ConquerScreen)
    # First conquest done, exactly one battle finished: the guided second
    # conquest where the player builds the attack by hand.
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'completed_steps': ['finish_first_conquer_battle'],
        'active_lesson': 'build_attack',
        'facts': {'conquer_battles': 2, 'conquered_lands': 1},
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
    screen._btn_prelude_edit = pygame.Rect(490, 180, 34, 34)
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
    screen._config['battle_moves'] = [{}, {}, {}]
    step = screen._current_conquer_coach_step()
    assert step['id'] == 'conquer_build_yourself_prelude'

    screen.state.user_dict['onboarding']['menu_hints_seen'].append(
        'conquer_build_yourself_prelude')
    step = screen._current_conquer_coach_step()
    assert step['id'] == 'conquer_build_yourself_battle'
    assert step['rect'] == screen._btn_battle

    # Tutorial-skipped players get no second-build coaching.
    screen.state.user_dict['onboarding']['onboarding_skipped'] = True
    screen.state.user_dict['onboarding']['menu_hints_seen'] = []
    screen._config['figures'] = []
    assert screen._current_conquer_coach_step() is None


def test_conquer_second_build_coach_inactive_after_lesson_completion():
    import pygame
    from game.screens.conquer_screen import ConquerScreen

    screen = object.__new__(ConquerScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'completed_steps': [
            'finish_first_conquer_battle',
            'finish_build_attack_lesson',
        ],
        'active_lesson': 'build_attack',
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
    screen._btn_prelude_edit = pygame.Rect(490, 180, 34, 34)
    screen._btn_battle = pygame.Rect(520, 380, 140, 42)

    # A completed lesson no longer emits coach cards.
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


def test_coach_only_card_can_leave_kingdom_map_interactive(monkeypatch):
    import pygame

    screen, _ = _screen_with_gold(100)
    viewport = pygame.Rect(100, 80, 500, 300)
    step = {
        'id': 'kingdom_after_conquer_map',
        'rect': viewport,
        'interactive_rects': [viewport],
        'title': 'Your First Land',
        'body': 'Explore the map.',
        'action': 'coach',
    }
    screen._menu_coach_buttons = []

    down = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=viewport.center)
    up = pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=1, pos=viewport.center)
    outside = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20))
    assert screen._handle_menu_coach_events([down], step) is False
    assert screen._handle_menu_coach_events([up], step) is False
    assert screen._handle_menu_coach_events([outside], step) is True

    # The coach chrome itself still consumes taps; only exposed map does not.
    screen._menu_coach_card_rect = pygame.Rect(200, 150, 180, 120)
    card_down = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(250, 180))
    assert screen._handle_menu_coach_events([card_down], step) is True
    screen._menu_coach_card_rect = None

    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: viewport.center)
    wheel = pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1)
    assert screen._handle_menu_coach_events([wheel], step) is False


def test_defence_coach_walks_setup_steps_after_tutorial():
    """Defence is dropped from the first session, so its coaching only appears
    on-demand once the conquer tutorial is finished: build → battle plan →
    final response → save."""
    import pygame
    from game.screens.defence_screen import DefenceScreen

    screen = object.__new__(DefenceScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'menu_hints_seen': [],
        'active_lesson': 'defend_land',
        'completed_steps': [
            'open_first_main_booster', 'open_first_side_booster',
            'finish_first_conquer_battle', 'collect_first_kingdom_production',
            'finish_tutorial', 'save_first_defence_config',
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


def _menu_screen_for_completion(core_steps, *, welcome_pending=False, skipped=False,
                                menu_hints_seen=None):
    from game.screens.game_menu_screen import GameMenuScreen
    screen = object.__new__(GameMenuScreen)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'core_steps': core_steps,
        'menu_hints_seen': list(
            ['kingdom_after_conquer_map'] if menu_hints_seen is None else menu_hints_seen),
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
        _core_step('finish_duel_basics_lesson', completed=True, claimed=False,
                   reward={'booster_packs': 3}),
    ])
    pending = screen._pending_tutorial_completion()
    assert pending is not None
    assert pending[0] == 'finish_tutorial'
    assert 'First Journey Complete' in pending[1]
    assert any(
        'Guide' in line and 'start the next lesson' in line
        for line in pending[2]
    )

    # Once celebrated, it advances to the duel tutorial.
    screen._tutorial_celebrated.add('finish_tutorial')
    pending = screen._pending_tutorial_completion()
    assert pending[0] == 'finish_duel_basics_lesson'
    assert 'Duel Basics Complete' in pending[1]


def test_first_journey_completion_surfaces_full_final_reward():
    screen = _menu_screen_for_completion([
        _core_step('finish_first_conquer_battle', completed=True, claimed=False,
                   reward={}),
        _core_step('finish_tutorial', completed=True, claimed=False,
                   reward={'gold': 2000, 'booster_packs': 9,
                           'booster_packs_side': 4, 'maps': 4}),
    ])

    pending = screen._pending_tutorial_completion()

    assert pending[3] == {
        'gold': 2000,
        'booster_packs_side': 4,
        'maps': 4,
        'booster_packs': 9,
    }


def test_every_follow_up_lesson_has_recap_next_step_and_reward_finale():
    from game.screens._menu_base import MenuScreenMixin

    expected = {
        'finish_collection_lesson': 'Build Your Own Attack',
        'finish_build_attack_lesson': 'Run Your Kingdom',
        'finish_run_kingdom_lesson': 'Defend Your Land',
        'finish_defend_land_lesson': 'Duel Basics',
        'finish_duel_basics_lesson': 'Goals',
    }
    completions = {
        step_id: (title, lines)
        for step_id, title, lines
        in MenuScreenMixin._TUTORIAL_COMPLETIONS
    }

    for step_id, next_step in expected.items():
        title, lines = completions[step_id]
        assert 'Complete!' in title
        assert len(lines) == 2
        assert next_step in lines[1]


def test_follow_up_completion_uses_reveal_boxes_and_finish_lesson_button(
        monkeypatch):
    from game.components import rewards_reveal_dialogue

    captured = {}

    class FakeRewardsReveal:
        def __init__(self, *args, **kwargs):
            captured['args'] = args
            captured['kwargs'] = kwargs

    monkeypatch.setattr(
        rewards_reveal_dialogue,
        'RewardsRevealDialogueBox',
        FakeRewardsReveal,
    )
    screen = _menu_screen_for_completion([
        _core_step(
            'finish_collection_lesson',
            completed=True,
            claimed=False,
            reward={
                'gold': 250,
                'booster_packs': 2,
                'booster_packs_side': 1,
            },
        ),
    ])
    screen.window = object()
    screen._tutorial_complete_dialogue = None
    screen._welcome_present_dialogue = None
    screen._starter_reveal_dialogue = None
    screen.dialogue_box = None
    screen._onboarding_guide_open = False

    screen._maybe_show_tutorial_completion()

    assert captured['kwargs']['ok_label'] == 'Finish Lesson'
    assert captured['kwargs']['hint_text'] == (
        'Click each box to reveal your reward.')
    assert len(captured['args'][4]) == 3


def test_replay_completion_shows_finish_window_without_reward_and_acknowledges(
        monkeypatch):
    from game.components import rewards_reveal_dialogue
    from game.screens import _menu_base

    captured = {}

    class FakeRewardsReveal:
        def __init__(self, *args, **kwargs):
            captured['args'] = args
            captured['kwargs'] = kwargs

        def update(self, _events):
            return 'ok'

    monkeypatch.setattr(
        rewards_reveal_dialogue,
        'RewardsRevealDialogueBox',
        FakeRewardsReveal,
    )
    screen = _menu_screen_for_completion([
        _core_step(
            'finish_collection_lesson',
            completed=True,
            claimed=True,
            reward={
                'gold': 250,
                'booster_packs': 2,
                'booster_packs_side': 1,
            },
        ),
    ])
    onboarding = screen.state.user_dict['onboarding']
    onboarding['replay_completion_pending'] = 'grow_collection'
    onboarding['lessons'] = [{
        'id': 'grow_collection',
        'completion_step': 'finish_collection_lesson',
        'completed': True,
        'claimed': True,
    }]
    screen.window = object()
    screen._tutorial_complete_dialogue = None
    screen._welcome_present_dialogue = None
    screen._starter_reveal_dialogue = None
    screen.dialogue_box = None
    screen._onboarding_guide_open = False
    screen.state.set_msg = lambda message: captured.setdefault(
        'messages', []).append(message)
    screen._apply_onboarding_payload = (
        lambda data: captured.setdefault('payloads', []).append(data))

    acknowledgements = []
    monkeypatch.setattr(
        _menu_base.onboarding_service,
        'acknowledge_replay_completion',
        lambda lesson_id: (
            acknowledgements.append(lesson_id)
            or {'onboarding': {'replay_completion_pending': None}}
        ),
    )
    monkeypatch.setattr(
        _menu_base.onboarding_service,
        'claim_reward',
        lambda _step_id: pytest.fail(
            'A replay finale must not claim the reward again'),
    )

    screen._maybe_show_tutorial_completion()

    assert captured['args'][4] == []
    assert captured['kwargs']['hint_text'] is None
    assert captured['kwargs']['ok_label'] == 'Finish Lesson'
    assert captured['kwargs']['footer_when_done'] == (
        'Replay complete. No additional reward is granted.')
    assert screen._tutorial_complete_step_id == 'replay:grow_collection'
    assert screen._tutorial_complete_replay_lesson_id == 'grow_collection'

    assert screen._handle_tutorial_completion_events([]) is True
    assert acknowledgements == ['grow_collection']
    assert captured['messages'] == [
        'Lesson replay complete. No additional reward.']
    assert screen._tutorial_complete_dialogue is None
    assert screen._tutorial_complete_replay_lesson_id is None


def test_finishing_first_journey_does_not_auto_start_next_lesson(monkeypatch):
    from game.screens import _menu_base
    from game.screens._menu_base import MenuScreenMixin

    screen = object.__new__(MenuScreenMixin)
    screen.state = SimpleNamespace(
        screen='kingdom',
        user_dict={'onboarding': {'active_lesson': None}},
        set_msg=lambda _message: None,
    )
    screen._tutorial_complete_dialogue = SimpleNamespace(
        update=lambda _events: 'ok')
    screen._tutorial_complete_step_id = 'finish_tutorial'
    screen._tutorial_complete_replay_lesson_id = None
    screen._apply_onboarding_payload = lambda _data: None
    screen._suppress_next_gold_floater = lambda: None
    starts = []
    monkeypatch.setattr(
        _menu_base.onboarding_service,
        'claim_reward',
        lambda step_id: {
            'reward': {'gold': 2000},
            'reward_label': 'First Journey rewards claimed',
        },
    )
    monkeypatch.setattr(
        _menu_base.onboarding_service,
        'start_lesson',
        lambda lesson_id: starts.append(lesson_id),
    )

    assert screen._handle_tutorial_completion_events([]) is True

    assert starts == []
    assert screen.state.screen == 'kingdom'
    assert screen._tutorial_complete_dialogue is None
    assert screen._tutorial_complete_step_id is None


def test_tutorial_completion_skips_claimed_and_incomplete():
    screen = _menu_screen_for_completion([
        _core_step('finish_tutorial', completed=True, claimed=True),
        _core_step(
            'finish_duel_basics_lesson',
            completed=False,
            claimed=False),
    ])
    assert screen._pending_tutorial_completion() is None


def test_tutorial_completion_waits_for_first_land_finish_card():
    screen = _menu_screen_for_completion([
        _core_step('finish_tutorial', completed=True, claimed=False),
    ], menu_hints_seen=[])
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


def test_mobile_kingdom_overview_uses_interactive_map_sidecar():
    screen = _kingdom_overview_screen(seen=[])
    screen._mobile_ui = True
    screen._maybe_show_kingdom_overview()

    assert screen._kingdom_overview_dialogue.presentation == 'map_sidecar'
    assert screen._kingdom_overview_dialogue.background_interactive is True
    assert screen._kingdom_overview_dialogue._overlay is None


def test_kingdom_overview_routes_exposed_pointer_events_to_map():
    import pygame
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    dialogue_received = []
    map_received = []
    screen._kingdom_overview_dialogue = SimpleNamespace(
        captures_event=lambda event: event.pos[0] >= 400,
        update=lambda events: dialogue_received.extend(events),
    )
    screen._hex_map = SimpleNamespace(
        _dragging=False,
        handle_event=lambda event: map_received.append(event))
    screen._begin_map_control_press = lambda pos: False
    screen._drag_map_control_press = lambda pos: False
    screen._finish_map_control_press = lambda pos: False

    map_down = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(120, 200))
    panel_down = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(600, 200))
    assert screen._handle_kingdom_overview_events(
        [map_down, panel_down]) is True
    assert dialogue_received == [panel_down]
    assert map_received == [map_down]

    # A map drag that crosses beneath the sidecar must still receive motion and
    # release so it cannot get stuck in a dragging state.
    screen._hex_map._dragging = True
    crossing_motion = pygame.event.Event(
        pygame.MOUSEMOTION, pos=(600, 220), rel=(300, 20), buttons=(1, 0, 0))
    screen._handle_kingdom_overview_events([crossing_motion])
    assert map_received[-1] == crossing_motion


def test_finishing_kingdom_overview_focuses_marked_land():
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    marked = []
    focused = []
    screen._kingdom_overview_dialogue = SimpleNamespace(
        captures_event=lambda event: True,
        update=lambda events: 'done',
    )
    screen._mark_menu_coach_seen = marked.append
    screen._focus_recommended_tutorial_land = lambda: focused.append(True)

    assert screen._handle_kingdom_overview_events([]) is True
    assert screen._kingdom_overview_dialogue is None
    assert marked == ['kingdom_overview_window']
    assert focused == [True]


def test_mobile_marked_land_focus_uses_phone_friendly_zoom_and_clears_selection():
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    tile = SimpleNamespace(land_id=42)
    calls = []
    screen._mobile_ui = True
    screen._recommended_tutorial_land_id = 42
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'completed_steps': [],
        'onboarding_skipped': False,
    }})
    screen._hex_map = SimpleNamespace(
        selected_tile=tile,
        focus_lands=lambda ids, **kwargs: (
            calls.append((ids, kwargs)) or tile),
    )

    assert screen._focus_recommended_tutorial_land() is tile
    assert calls == [([42], {'fit': True, 'max_zoom': 1.5})]
    assert screen._hex_map.selected_tile is None


def test_mobile_marked_land_accepts_tap_around_tiny_rendered_hex(monkeypatch):
    import pygame
    from config import settings
    from game.screens.kingdom_screen import KingdomScreen

    screen = object.__new__(KingdomScreen)
    tile = SimpleNamespace(land_id=42)
    tiny_hex = pygame.Rect(100, 100, 8, 8)
    screen._mobile_ui = True
    monkeypatch.setattr(settings, 'TOUCH_TARGET_MIN', 58)
    monkeypatch.setattr(settings, 'TOUCH_ICON_MIN', 32)
    screen._recommended_tutorial_land_id = 42
    screen._map_viewport_rect = pygame.Rect(20, 20, 500, 300)
    screen._hex_map = SimpleNamespace(
        tiles=[tile],
        land_screen_rect=lambda land_id: tiny_hex,
    )
    step = {'id': 'kingdom_pick_land'}
    near = (tiny_hex.centerx + settings.TOUCH_TARGET_MIN // 2 - 2,
            tiny_hex.centery)

    assert not tiny_hex.collidepoint(near)
    assert screen._recommended_tutorial_touch_tile(near, step) is tile
    assert screen._recommended_tutorial_touch_tile((200, 200), step) is None


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


def test_kingdom_screen_surfaces_conquer_tutorial_completion():
    # The conquer tutorial completes on the kingdom screen's first-land finish
    # card, so the kingdom screen surfaces the completion celebration itself
    # instead of waiting for the player to return to the menu.
    screen = _kingdom_overview_screen(seen=[
        'kingdom_overview_window', 'kingdom_after_conquer_map'])
    screen.state.user_dict['onboarding']['core_steps'] = [
        {'id': 'finish_tutorial', 'completed': True, 'claimed': False,
         'reward': {'booster_packs': 6, 'booster_packs_side': 2}},
    ]
    pending = screen._pending_tutorial_completion()
    assert pending is not None and pending[0] == 'finish_tutorial'
    assert 'First Journey Complete' in pending[1]


def test_tutorial_completion_available_on_any_menu_mixin_screen():
    # The celebration logic lives on MenuScreenMixin, so the tutorial-coach
    # screens that complete a tutorial can fire it after the last card.
    from game.screens._menu_base import MenuScreenMixin
    screen = object.__new__(MenuScreenMixin)
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'core_steps': [
            {'id': 'finish_tutorial', 'completed': True, 'claimed': False,
             'reward': {'booster_packs': 6, 'booster_packs_side': 2}},
        ],
        'menu_hints_seen': ['kingdom_after_conquer_map'],
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

    # The welcome and gift are one stage; dismissing it marks welcome seen.
    for expected_stage in range(GameMenuScreen._WELCOME_STAGES):
        screen._welcome_present_dialogue = _FakeDlg()
        assert screen._handle_welcome_present_events([]) is True
        assert screen._welcome_stage == expected_stage + 1
    assert marked == [True]


def test_welcome_intro_uses_supplied_conquer_image_without_extra_frame():
    _ensure_pygame_display()
    from config import settings
    from game.components import tutorial_diagrams as td
    from game.screens.game_menu_screen import GameMenuScreen
    screen = object.__new__(GameMenuScreen)
    screen.window = None
    screen.state = SimpleNamespace(user_dict={'onboarding': {}})

    dialogue = screen._build_welcome_stage(0, 'Maya')

    page = dialogue.pages[0]
    image = page['image']()
    assert page['layout'] == 'image_top'
    # The illustration carries its own frame, so the window must not add one.
    assert page['image_frame'] is False
    # The banner is returned at native resolution regardless of any size hint;
    # the tutorial window sizes it (a single scale pass), so the same cached
    # surface comes back whether or not a target height is supplied.
    assert image is td.conquer_start_image()
    assert image is td.conquer_start_image(int(0.26 * settings.SCREEN_HEIGHT))
    assert image.get_width() > 1 and image.get_height() > 1


def test_welcome_defers_gift_and_routes_to_starter_cards():
    import pygame

    _ensure_pygame_display()
    from config import settings
    from game.screens.game_menu_screen import GameMenuScreen

    screen = object.__new__(GameMenuScreen)
    screen.window = pygame.Surface(
        (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen.state = SimpleNamespace(user_dict={'onboarding': {
        'starter_present': {'starter_defaults': {
            'gold': 2000,
            'booster_packs': 2,
            'booster_packs_side': 1,
        }},
    }})

    dialogue = screen._build_welcome_stage(0, 'Maya')

    assert dialogue.title == 'Welcome to Nepal Kings'
    assert len(dialogue.pages) == 1
    page = dialogue.pages[0]
    lines = ' '.join(page['lines'])
    assert page['button_label'] == 'Start Tutorial'
    assert 'You want to become the greatest king of Nepal?' in lines
    assert '2,000 gold' not in lines
    assert 'booster' not in lines.lower()
    assert not hasattr(dialogue, '_btn_pause')
