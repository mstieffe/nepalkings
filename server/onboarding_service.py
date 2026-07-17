# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Account-level onboarding state, milestones, and rewards."""

from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
import hashlib
import random

from sqlalchemy import inspect, or_, text
from sqlalchemy.orm.attributes import flag_modified

import server_settings as settings
from models import db, GameResult, LandAttackLog, LandConfig


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _nonnegative_int(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


DAILY_QUEST_REWARD_ID = 'daily_quest'
DAILY_QUEST_RESET_HOUR_UTC = 0

FIRST_JOURNEY_REWARD = {
    # Preserve every existing opening/tutorial grant, but pay it out once the
    # player has actually conquered a land and completed the map return.
    'gold': int(getattr(settings, 'INITIAL_GOLD', 0) or 0),
    'booster_packs': int(getattr(settings, 'STARTER_BOOSTER_PACKS', 0) or 0) + 7,
    'booster_packs_side': int(
        getattr(settings, 'STARTER_BOOSTER_PACKS_SIDE', 0) or 0) + 3,
    'maps': 4,
}


# Ordered to match the real first-session journey: reveal the prepared starter
# collection, conquer a land, collect the finale, then explore optional systems.
CORE_STEPS = [
    {
        'id': 'finish_first_conquer_battle',
        'title': 'Conquer your first land',
        'description': 'Win your first land battle as the attacker.',
        'reward': {},
        'group': 'first_journey',
    },
    {
        'id': 'finish_tutorial',
        'title': 'Finish the kingdom tour',
        'description': 'Return to the kingdom map and complete the final guided step.',
        'reward': FIRST_JOURNEY_REWARD,
        'group': 'first_journey',
    },
    {
        'id': 'finish_collection_lesson',
        'title': 'Grow your collection',
        'description': 'Open both pack types, then learn how to sell and convert spare cards.',
        'reward': {
            'gold': 250,
            'booster_packs': 2,
            'booster_packs_side': 1,
        },
        'group': 'lessons',
    },
    {
        'id': 'finish_build_attack_lesson',
        'title': 'Build your own attack',
        'description': 'Assemble your next attack and finish a real land battle.',
        'reward': {'gold': 250, 'maps': 2},
        'group': 'lessons',
    },
    {
        'id': 'finish_run_kingdom_lesson',
        'title': 'Run your kingdom',
        'description': 'Manage production, skills, loot, protection, and kingdom style.',
        'reward': {'gold': 500, 'maps': 1},
        'group': 'lessons',
    },
    {
        'id': 'finish_defend_land_lesson',
        'title': 'Defend your land',
        'description': 'Prepare and save a complete land defence.',
        'reward': {
            'gold': 250,
            'booster_packs': 2,
            'booster_packs_side': 1,
        },
        'group': 'lessons',
    },
    {
        'id': 'finish_duel_basics_lesson',
        'title': 'Complete Duel Basics',
        'description': 'Finish a duel after seeing every contextual Duel Basics tip.',
        'reward': {
            'gold': 500,
            'booster_packs': 3,
            'booster_packs_side': 2,
        },
        'group': 'lessons',
    },
]


FOLLOW_UP_LESSONS = [
    {
        'id': 'grow_collection',
        'title': 'Grow Your Collection',
        'description': 'Open both pack types and learn how spare copies become gold or cards you need.',
        'group': 'lessons',
        'entry_screen': 'collection',
        'entry_label': 'Start Grow Your Collection',
        'completion_step': 'finish_collection_lesson',
        'substeps': [
            {
                'id': 'collection_growth_intro',
                'title': 'Learn main cards, side cards, and copy states',
                'source': 'menu_hint',
            },
            {
                'id': 'open_first_main_booster',
                'title': 'Open a main booster',
                'source': 'completed_step',
            },
            {
                'id': 'open_first_side_booster',
                'title': 'Open a side booster',
                'source': 'completed_step',
            },
            {
                'id': 'sell_first_card',
                'title': 'Sell a free spare card',
                'source': 'completed_step',
            },
            {
                'id': 'trade_first_card',
                'title': 'Convert spare copies into another suit',
                'source': 'completed_step',
            },
            {
                'id': 'collection_growth_recap',
                'title': 'See how copies power kingdom growth',
                'source': 'menu_hint',
            },
        ],
    },
    {
        'id': 'build_attack',
        'title': 'Build Your Own Attack',
        'description': 'Build figures, choose tactics and a prelude, then fight a real conquest.',
        'group': 'lessons',
        'entry_screen': 'kingdom',
        'entry_label': 'Start Build Your Own Attack',
        'completion_step': 'finish_build_attack_lesson',
        'substeps': [
            {
                'id': 'build_attack_intro_window',
                'title': 'Learn the attack-building plan',
                'source': 'menu_hint',
            },
            {
                'id': 'conquer_build_yourself',
                'title': 'Build a figure from your Collection',
                'source': 'menu_hint',
            },
            {
                'id': 'conquer_build_yourself_tactics',
                'title': 'Add three tactics',
                'source': 'menu_hint',
            },
            {
                'id': 'conquer_build_yourself_prelude',
                'title': 'Review the optional prelude spell',
                'source': 'menu_hint',
            },
            {
                'id': 'finish_second_conquer_battle',
                'title': 'Finish the land battle',
                'source': 'completed_step',
            },
        ],
    },
    {
        'id': 'run_kingdom',
        'title': 'Run Your Kingdom',
        'description': 'Manage production, skills, maps, loot, protection, and kingdom appearance.',
        'group': 'lessons',
        'entry_screen': 'kingdom',
        'entry_label': 'Start Run Your Kingdom',
        'completion_step': 'finish_run_kingdom_lesson',
        'substeps': [
            {
                'id': 'kingdom_management_intro',
                'title': 'Learn production, maps, and the Loot Inbox',
                'source': 'menu_hint',
            },
            {
                'id': 'kingdom_collect_production',
                'title': 'Find the production collection control',
                'source': 'menu_hint',
            },
            {
                'id': 'kingdom_config_essentials',
                'title': 'Review production and kingdom skills',
                'source': 'menu_hint',
            },
            {
                'id': 'kingdom_config_shields_style',
                'title': 'Review shields and kingdom cosmetics',
                'source': 'menu_hint',
            },
            {
                'id': 'buy_first_cosmetic',
                'title': 'Buy and equip one kingdom cosmetic',
                'source': 'completed_step',
            },
        ],
    },
    {
        'id': 'defend_land',
        'title': 'Defend Your Land',
        'description': 'Choose figures, tactics, and a defender response, then save the defence.',
        'group': 'lessons',
        'entry_screen': 'kingdom',
        'entry_label': 'Start Defend Your Land',
        'completion_step': 'finish_defend_land_lesson',
        'substeps': [
            {
                'id': 'defend_land_intro_window',
                'title': 'Learn how a saved defence protects land',
                'source': 'menu_hint',
            },
            {
                'id': 'defence_intro',
                'title': 'Review defending figures',
                'source': 'menu_hint',
            },
            {
                'id': 'defence_battle_plan',
                'title': 'Fill the three-round battle plan',
                'source': 'menu_hint',
            },
            {
                'id': 'defence_final_response',
                'title': 'Choose the defender response',
                'source': 'menu_hint',
            },
            {
                'id': 'save_first_defence_config',
                'title': 'Save the completed defence',
                'source': 'completed_step',
            },
        ],
    },
    {
        'id': 'duel_basics',
        'title': 'Duel Basics',
        'description': 'Play a friendly AI duel and learn setup turns, advancing, tactics, and scoring.',
        'group': 'lessons',
        'entry_screen': 'duel_menu',
        'entry_label': 'Start Duel Basics',
        'completion_step': 'finish_duel_basics_lesson',
        'substeps': [
            {
                'id': 'duel_tutorial_start_window',
                'title': 'Learn the duel objective and round rhythm',
                'source': 'menu_hint',
            },
            {
                'id': 'field',
                'title': 'Read setup turns, roles, and resources',
                'source': 'duel_hint',
            },
            {
                'id': 'build',
                'title': 'Build a figure',
                'source': 'duel_hint',
            },
            {
                'id': 'cast_spell',
                'title': 'Review spells and card changes',
                'source': 'duel_hint',
            },
            {
                'id': 'battle_shop_select_moves',
                'title': 'Buy battle moves',
                'source': 'duel_hint',
            },
            {
                'id': 'battle_shop_ready',
                'title': 'Lock in the battle plan',
                'source': 'duel_hint',
            },
            {
                'id': 'battle_move_panel',
                'title': 'Open a battle move',
                'source': 'duel_hint',
            },
            {
                'id': 'battle_move_actions',
                'title': 'Use a battle move',
                'source': 'duel_hint',
            },
            {
                'id': 'battle_score',
                'title': 'Read the battle score',
                'source': 'duel_hint',
            },
            {
                'id': 'finish_first_duel',
                'title': 'Finish the duel',
                'source': 'completed_step',
            },
        ],
    },
]
FOLLOW_UP_LESSON_BY_ID = {
    lesson['id']: lesson for lesson in FOLLOW_UP_LESSONS
}

REPLAY_MENU_HINT_IDS_BY_LESSON = {
    'grow_collection': (
        'collection_growth_intro',
        'collection_growth_main',
        'collection_growth_side',
        'collection_sell_spare',
        'collection_trade_spare',
        'collection_growth_recap',
    ),
    'build_attack': (
        'build_attack_intro_window',
        'conquer_choose_next_land',
        'conquer_open_next_attack',
        'conquer_build_yourself',
        'conquer_build_yourself_tactics',
        'conquer_build_yourself_prelude',
        'conquer_build_yourself_battle',
    ),
    'run_kingdom': (
        'kingdom_management_intro',
        'kingdom_open_management',
        'kingdom_collect_production',
        'kingdom_config_essentials',
        'kingdom_config_shields_style',
        'kingdom_buy_cosmetic',
    ),
    'defend_land': (
        'defend_land_intro_window',
        'defence_choose_land',
        'defence_open_config',
        'defence_intro',
        'defence_battle_plan',
        'defence_final_response',
        'defence_save',
    ),
    'duel_basics': (
        'duel_tutorial_start_window',
        'beginner_duel',
        'send_first_duel_challenge',
    ),
}

REPLAY_STEP_IDS_BY_LESSON = {
    'grow_collection': (
        'open_first_main_booster',
        'open_first_side_booster',
        'sell_first_card',
        'trade_first_card',
    ),
    'build_attack': ('finish_second_conquer_battle',),
    'run_kingdom': ('buy_first_cosmetic',),
    'defend_land': ('save_first_defence_config',),
    'duel_basics': ('finish_first_duel',),
}

SKIPPABLE_LESSON_COACH_STEPS = {
    'grow_collection': {
        'collection_growth_main': (
            'collection_growth_main', 'open_first_main_booster'),
        'collection_growth_side': (
            'collection_growth_side', 'open_first_side_booster'),
        'collection_sell_spare': (
            'collection_sell_spare', 'sell_first_card'),
        'collection_trade_spare': (
            'collection_trade_spare', 'trade_first_card'),
    },
    'build_attack': {
        'conquer_choose_next_land': ('conquer_choose_next_land',),
        'conquer_open_next_attack': ('conquer_open_next_attack',),
        'conquer_build_yourself': ('conquer_build_yourself',),
        'conquer_build_yourself_tactics': (
            'conquer_build_yourself_tactics',),
        'conquer_build_yourself_battle': (
            'conquer_build_yourself_battle',
            'finish_second_conquer_battle',
        ),
    },
    'run_kingdom': {
        'kingdom_buy_cosmetic': (
            'kingdom_buy_cosmetic',
            'buy_first_cosmetic',
        ),
    },
    'defend_land': {
        'defence_save': ('defence_save', 'save_first_defence_config'),
    },
}

DUEL_COACH_SKIP_HINTS = {
    'build': ('build',),
    'battle_shop_select_moves': ('battle_shop_select_moves',),
    'battle_shop_ready': ('battle_shop_ready',),
    'battle_move_panel': ('battle_move_panel',),
    'battle_move_actions': ('battle_move_actions',),
}


EARLY_GOALS = [
    {
        'id': 'win_first_duel',
        'title': 'Win your first duel',
        'description': 'Win any finished duel.',
        'reward': {'gold': 75},
    },
    {
        'id': 'win_5_duels',
        'title': 'Win 5 duels',
        'description': 'Build a winning rhythm in duel mode.',
        'reward': {'booster_packs': 1},
    },
    {
        'id': 'win_10_duels',
        'title': 'Win 10 duels',
        'description': 'Prove your duel strategy over repeated wins.',
        'reward': {'booster_packs': 3},
    },
    {
        'id': 'finish_3_duels',
        'title': 'Finish 3 duels',
        'description': 'Get comfortable with the duel rhythm.',
        'reward': {'booster_packs_side': 1},
    },
    {
        'id': 'finish_10_duels',
        'title': 'Finish 10 duels',
        'description': 'Keep playing through full matches.',
        'reward': {'booster_packs_side': 2},
    },
    {
        'id': 'lose_5_duels',
        'title': 'Learn from 5 duel losses',
        'description': 'Every finished duel teaches something useful.',
        'reward': {'gold': 100},
    },
    {
        'id': 'lose_10_duels',
        'title': 'Learn from 10 duel losses',
        'description': 'Stay in the fight and keep refining your deck.',
        'reward': {'booster_packs_side': 2},
    },
    {
        'id': 'earn_1000_gold',
        'title': 'Earn 1000 gold',
        'description': 'Earn gold from play, production, and card sales.',
        'reward': {'booster_packs': 1},
    },
    {
        'id': 'earn_10000_gold',
        'title': 'Earn 10000 gold',
        'description': 'Earn gold from play, production, and card sales.',
        'reward': {'booster_packs': 10},
    },
    {
        'id': 'conquer_1_land',
        'title': 'Conquer 1 land',
        'description': 'Win a land battle as the attacker.',
        'reward': {'maps': 1},
    },
    {
        'id': 'collect_kingdom_production_5',
        'title': 'Collect production 5 times',
        'description': 'Return to your kingdom and claim ready output.',
        'reward': {'booster_packs_side': 1},
    },
    {
        'id': 'finish_10_conquer_battles',
        'title': 'Finish 10 conquer battles',
        'description': 'Fight repeated battles across the kingdom map.',
        'reward': {'gold': 1500},
    },
    {
        'id': 'conquer_5_lands',
        'title': 'Conquer 5 lands',
        'description': 'Also unlocks the 5-land conquest cosmetic achievement.',
        'reward': {'gold': 500},
        'cosmetic_unlock_hint': 'sigil_wolf',
    },
    {
        'id': 'conquer_10_lands',
        'title': 'Conquer 10 lands',
        'description': 'Also unlocks the 10-land conquest cosmetic achievement.',
        'reward': {'gold': 1000},
        'cosmetic_unlock_hint': 'sigil_tower',
    },
    {
        'id': 'conquer_20_lands',
        'title': 'Conquer 20 lands',
        'description': 'Push your kingdom farther across the map.',
        'reward': {'gold': 2000},
    },
    {
        'id': 'conquer_25_lands',
        'title': 'Conquer 25 lands',
        'description': 'Also unlocks the 25-land Serpent sigil achievement.',
        'reward': {'gold': 2500},
        'cosmetic_unlock_hint': 'sigil_serpent',
    },
]


DAILY_QUESTS = [
    {
        'id': 'dq_finish_1_duel',
        'fact': 'duel_finishes',
        'target': 1,
        'tier': 'easy',
        'title': 'Finish 1 duel',
        'description': 'Play one full duel from start to finish.',
        'reward': {'gold': 60},
        'requires_completed_step': 'finish_first_duel',
    },
    {
        'id': 'dq_finish_2_duels',
        'fact': 'duel_finishes',
        'target': 2,
        'tier': 'medium',
        'title': 'Finish 2 duels',
        'description': 'Complete two full duel matches today.',
        'reward': {'booster_packs_side': 1},
        'requires_completed_step': 'finish_first_duel',
    },
    {
        'id': 'dq_finish_3_duels',
        'fact': 'duel_finishes',
        'target': 3,
        'tier': 'hard',
        'title': 'Finish 3 duels',
        'description': 'Play through three complete duels today.',
        'reward': {'booster_packs': 1},
        'requires_completed_step': 'finish_first_duel',
    },
    {
        'id': 'dq_win_1_duel',
        'fact': 'duel_wins',
        'target': 1,
        'tier': 'medium',
        'title': 'Win 1 duel',
        'description': 'Win one finished duel today.',
        'reward': {'gold': 150},
        'requires_completed_step': 'finish_first_duel',
    },
    {
        'id': 'dq_win_2_duels',
        'fact': 'duel_wins',
        'target': 2,
        'tier': 'hard',
        'title': 'Win 2 duels',
        'description': 'Win two finished duels today.',
        'reward': {'booster_packs': 2},
        'requires_completed_step': 'finish_first_duel',
    },
    {
        'id': 'dq_battle_1_conquer',
        'fact': 'conquer_battles',
        'target': 1,
        'tier': 'easy',
        'title': 'Fight 1 land battle',
        'description': 'Finish one conquer battle today.',
        'reward': {'maps': 1},
        'requires_completed_step': 'finish_first_conquer_battle',
    },
    {
        'id': 'dq_battle_2_conquer',
        'fact': 'conquer_battles',
        'target': 2,
        'tier': 'medium',
        'title': 'Fight 2 land battles',
        'description': 'Finish two conquer battles today.',
        'reward': {'gold': 180},
        'requires_completed_step': 'finish_first_conquer_battle',
    },
    {
        'id': 'dq_battle_4_conquer',
        'fact': 'conquer_battles',
        'target': 4,
        'tier': 'hard',
        'title': 'Fight 4 land battles',
        'description': 'Finish four conquer battles today.',
        'reward': {'maps': 2},
        'requires_completed_step': 'finish_first_conquer_battle',
    },
    {
        'id': 'dq_conquer_1_land',
        'fact': 'conquered_lands',
        'target': 1,
        'tier': 'medium',
        'title': 'Conquer 1 land',
        'description': 'Win one land battle as the attacker today.',
        'reward': {'gold': 220},
        'requires_completed_step': 'finish_first_conquer_battle',
    },
    {
        'id': 'dq_conquer_2_lands',
        'fact': 'conquered_lands',
        'target': 2,
        'tier': 'hard',
        'title': 'Conquer 2 lands',
        'description': 'Win two land battles as the attacker today.',
        'reward': {'booster_packs_side': 2},
        'requires_completed_step': 'finish_first_conquer_battle',
    },
    {
        'id': 'dq_earn_100_gold',
        'fact': 'gold_earned',
        'target': 100,
        'tier': 'easy',
        'title': 'Earn 100 gold',
        'description': 'Earn gold from duels, production, or card sales today.',
        'reward': {'gold': 50},
        'requires_completed_step': 'finish_first_conquer_battle',
    },
    {
        'id': 'dq_earn_300_gold',
        'fact': 'gold_earned',
        'target': 300,
        'tier': 'medium',
        'title': 'Earn 300 gold',
        'description': 'Earn gold from play, production, or card sales today.',
        'reward': {'booster_packs_side': 1},
        'requires_completed_step': 'finish_first_conquer_battle',
    },
    {
        'id': 'dq_earn_750_gold',
        'fact': 'gold_earned',
        'target': 750,
        'tier': 'hard',
        'title': 'Earn 750 gold',
        'description': 'Earn a strong pile of gold today.',
        'reward': {'booster_packs': 2},
        'requires_completed_step': 'finish_first_conquer_battle',
    },
    {
        'id': 'dq_collect_prod_1',
        'fact': 'kingdom_production_collections',
        'target': 1,
        'tier': 'easy',
        'title': 'Collect production',
        'description': 'Claim ready output from a kingdom today.',
        'reward': {'gold': 70},
        'requires_completed_step': 'finish_first_conquer_battle',
    },
    {
        'id': 'dq_collect_prod_2',
        'fact': 'kingdom_production_collections',
        'target': 2,
        'tier': 'medium',
        'title': 'Collect production twice',
        'description': 'Claim ready kingdom output two times today.',
        'reward': {'maps': 1},
        'requires_completed_step': 'finish_first_conquer_battle',
    },
]

DAILY_QUEST_BY_ID = {quest['id']: quest for quest in DAILY_QUESTS}
DAILY_QUEST_FACT_KEYS = (
    'duel_finishes',
    'duel_wins',
    'conquer_battles',
    'conquered_lands',
    'gold_earned',
    'kingdom_production_collections',
)


CORE_STEP_IDS = {step['id'] for step in CORE_STEPS}
MILESTONE_STEP_IDS = {
    'open_first_main_booster',
    'open_first_side_booster',
    'finish_second_conquer_battle',
    'collect_first_kingdom_production',
    'save_first_defence_config',
    'finish_first_duel',
    'sell_first_card',
    'trade_first_card',
    'buy_first_cosmetic',
}
ONBOARDING_STEP_IDS = CORE_STEP_IDS | MILESTONE_STEP_IDS
EARLY_GOAL_IDS = {goal['id'] for goal in EARLY_GOALS}
DUEL_HINT_IDS = (
    'field', 'build', 'cast_spell', 'change_cards', 'game_status',
    'resource_panel', 'battle_shop_select_moves', 'battle_shop_ready',
    'battle_move_panel', 'battle_move_actions', 'battle_score',
)
DUEL_BASICS_REQUIRED_HINT_IDS = (
    'field',
    'build',
    'cast_spell',
    'battle_shop_select_moves',
    'battle_shop_ready',
    'battle_move_panel',
    'battle_move_actions',
    'battle_score',
)
# Order matters: mark_menu_hint re-sorts a user's seen hints by this tuple's
# order, and several tests assert that ordering. Keep ids in journey order.
# (duel/kingdom/collection/rankings are marked when the player clicks those
# main-menu buttons, so they remain even though they are no longer tour steps.)
MENU_HINT_IDS = (
    'duel', 'kingdom', 'collection', 'rankings', 'guide',
    'guide_rewards_track',
    'open_starter_cards',
    'collection_basics_window',
    'starter_cards_present_window', 'starter_suit_reveal',
    'collection_growth_intro', 'collection_growth_main',
    'collection_growth_side',
    'post_starter_cards_kingdom',
    'kingdom_overview_window',
    'kingdom_pick_land',
    'kingdom_conquer_button',
    'conquer_config_to_battle',
    'build_attack_intro_window',
    'conquer_choose_next_land', 'conquer_open_next_attack',
    'conquer_build_yourself', 'conquer_build_yourself_tactics',
    'conquer_build_yourself_prelude',
    'conquer_build_yourself_battle',
    'battle_intro_window',
    'conquer_battle_tactics',
    'kingdom_after_conquer_map',
    'return_to_kingdom_loop',
    'new_game', 'duel_tutorial_start_window',
    'beginner_duel', 'send_first_duel_challenge',
    'kingdom_management_intro',
    'kingdom_open_management', 'kingdom_collect_production',
    'kingdom_open_style',
    'defend_land_intro_window',
    'defence_choose_land', 'defence_open_config',
    'defence_intro', 'defence_battle_plan',
    'defence_final_response', 'defence_save',
    'collection_sell_spare', 'collection_trade_spare',
    'collection_growth_recap',
    'loot_risk_intro',
    'kingdom_config_essentials',
    'kingdom_config_shields_style',
    'kingdom_buy_cosmetic',
)
COACH_VERSION = 'first_session_v7'
ONBOARDING_SCHEMA_VERSION = 5


def ensure_onboarding_state_column():
    """Idempotently add ``User.onboarding_state`` to existing databases."""
    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        return False
    existing = {col['name'] for col in inspector.get_columns('user')}
    if 'onboarding_state' in existing:
        return False
    db.session.execute(text('ALTER TABLE "user" ADD COLUMN onboarding_state JSON'))
    db.session.commit()
    return True


def default_onboarding_state(*, new_user=False):
    return {
        'schema_version': ONBOARDING_SCHEMA_VERSION,
        'welcome_pending': bool(new_user),
        'welcome_seen': False,
        # Set once the offensive starter set has been granted after the
        # Collection roulette settles, so it is never granted twice.
        'starter_set_granted': False,
        'completed_steps': [],
        'claimed_rewards': [],
        'early_goals_claimed': [],
        'duel_hints_seen': [],
        'menu_hints_seen': [],
        'onboarding_skipped': False,
        'active_lesson': None,
        'lessons_dismissed': [],
        # Completed lessons can be replayed without changing their historical
        # completion or claimed reward. These fields hold the temporary replay
        # session and the hints hidden while it is active.
        'replaying_lesson': None,
        'lesson_replay_baseline': {},
        'lesson_replay_steps': [],
        'lesson_replay_original_menu_hints': [],
        'lesson_replay_original_duel_hints': [],
        # Milestones performed after the current lesson was started.  Some
        # global milestones may already be true before a lesson begins (the
        # first conquest, for example, creates an active defence), so lesson
        # completion must be able to distinguish old history from the action
        # the lesson is currently asking the player to perform.
        'lesson_session_steps': [],
        'lesson_skipped_steps': [],
        'replay_completion_pending': None,
        # {'offensive': <red suit>, 'defensive': <black suit>} selected before
        # the Collection roulette; revealed one-armed-bandit style there.
        'starter_suits': None,
        'daily_quest': None,
        'daily_quests_claimed_count': 0,
        'counters': {
            'gold_earned': 0,
            'kingdom_production_collections': 0,
        },
    }


def _state(user):
    base = default_onboarding_state(new_user=False)
    raw = deepcopy(user.onboarding_state or {})
    for key, value in raw.items():
        if key == 'counters':
            counters = dict(base['counters'])
            counters.update(value or {})
            base['counters'] = counters
        elif key in base:
            base[key] = value
    for list_key in (
        'completed_steps', 'claimed_rewards', 'early_goals_claimed',
        'duel_hints_seen', 'menu_hints_seen', 'lessons_dismissed',
        'lesson_replay_steps', 'lesson_replay_original_menu_hints',
        'lesson_replay_original_duel_hints', 'lesson_session_steps',
        'lesson_skipped_steps',
    ):
        if not isinstance(base.get(list_key), list):
            base[list_key] = []
    if not isinstance(base.get('counters'), dict):
        base['counters'] = default_onboarding_state()['counters']
    if not isinstance(base.get('lesson_replay_baseline'), dict):
        base['lesson_replay_baseline'] = {}
    base['schema_version'] = ONBOARDING_SCHEMA_VERSION
    return base


def _save_state(user, state, *, commit=False):
    user.onboarding_state = state
    flag_modified(user, 'onboarding_state')
    if commit:
        db.session.commit()


def set_initial_onboarding(user):
    user.onboarding_state = default_onboarding_state(new_user=True)


def assign_starter_suits(user, *, commit=False):
    """Assign (once) a random offensive (red) and defensive (black) starter suit.

    Returns ``{'offensive': <suit>, 'defensive': <suit>}``. Idempotent: an
    already-assigned pair is returned unchanged.
    """
    import random
    state = _state(user)
    suits = state.get('starter_suits') or {}
    if not suits.get('offensive') or not suits.get('defensive'):
        suits = {
            'offensive': random.choice(list(settings.OFFENSIVE_SUITS)),
            'defensive': random.choice(list(settings.DEFENSIVE_SUITS)),
        }
        state['starter_suits'] = suits
        _save_state(user, state, commit=commit)
    return dict(suits)


def grant_starter_set(user, *, commit=False):
    """Assign the random offensive starter suit and grant its curated set — once.

    Deferred from signup and welcome: the player receives the set only after
    the Collection roulette settles. Idempotent via the 'starter_set_granted'
    state flag. Returns the assigned offensive suit.
    """
    if not user:
        return None
    state = _state(user)
    suits = state.get('starter_suits') or {}
    offensive = suits.get('offensive')
    if state.get('starter_set_granted'):
        return offensive
    import random
    from models import CollectionCard
    if not offensive:
        offensive = random.choice(list(settings.OFFENSIVE_SUITS))
        state['starter_suits'] = {
            'offensive': offensive,
            'defensive': random.choice(list(settings.DEFENSIVE_SUITS)),
        }
    for rank, value in settings.STARTER_OFFENSIVE_SET:
        db.session.add(CollectionCard(
            user_id=user.id, rank=rank, suit=offensive, value=value, locked=False))
    state['starter_set_granted'] = True
    _save_state(user, state, commit=commit)
    return offensive


def prepare_starter_suit_reveal(user, *, commit=False):
    """Choose the hidden roulette result without granting any cards yet."""
    if not user:
        return None, 'User not found'
    state = _state(user)
    if not state.get('welcome_seen'):
        return None, 'Start the tutorial before revealing starter cards'
    suits = assign_starter_suits(user, commit=commit)
    return suits.get('offensive'), None


def complete_starter_suit_reveal(user, *, commit=False):
    """Grant the starter cards after the roulette has visibly settled."""
    if not user:
        return None, 'User not found'
    state = _state(user)
    if not state.get('welcome_seen'):
        return None, 'Start the tutorial before revealing starter cards'
    seen = set(state.get('menu_hints_seen') or [])
    if 'collection_basics_window' not in seen:
        return None, 'Learn the Collection basics before revealing starter cards'
    suit = grant_starter_set(user, commit=False)
    mark_menu_hints(user, (
        'starter_cards_present_window',
        'starter_suit_reveal',
    ), commit=commit)
    return suit, None


def get_starter_suits(user):
    """Return the player's assigned starter suits, with safe defaults."""
    state = _state(user)
    suits = state.get('starter_suits') or {}
    return {
        'offensive': suits.get('offensive') or settings.OFFENSIVE_SUITS[0],
        'defensive': suits.get('defensive') or settings.DEFENSIVE_SUITS[0],
    }


def mark_step(user, step_id, *, commit=False):
    if not user or step_id not in ONBOARDING_STEP_IDS:
        return False
    state = _state(user)
    completed = set(state.get('completed_steps') or [])
    replaying = state.get('replaying_lesson')
    replay_step_ids = set(
        REPLAY_STEP_IDS_BY_LESSON.get(replaying) or ())
    replay_steps = set(state.get('lesson_replay_steps') or [])
    replay_changed = bool(
        replaying and step_id in replay_step_ids
        and step_id not in replay_steps)
    if replay_changed:
        state['lesson_replay_steps'] = sorted(
            replay_steps | {step_id})

    active_lesson = state.get('active_lesson')
    lesson_step_ids = set(
        REPLAY_STEP_IDS_BY_LESSON.get(active_lesson) or ())
    lesson_session_steps = set(
        state.get('lesson_session_steps') or [])
    lesson_session_changed = bool(
        active_lesson and step_id in lesson_step_ids
        and step_id not in lesson_session_steps)
    if lesson_session_changed:
        state['lesson_session_steps'] = sorted(
            lesson_session_steps | {step_id})

    if step_id in completed and not replay_changed and not lesson_session_changed:
        return False
    if step_id not in completed:
        state['completed_steps'] = sorted(completed | {step_id})
    _save_state(user, state, commit=commit)
    return True


def complete_tutorial(user, *, commit=False):
    """Complete the final kingdom-tour beat after a real first conquest."""
    if not user:
        return False, 'User not found'
    state = _state(user)
    facts = _facts(user, state)
    if int(facts.get('conquered_lands') or 0) < 1:
        return False, 'Conquer your first land before finishing the tour'
    changed = mark_step(user, 'finish_tutorial', commit=commit)
    return changed, None


def record_gold_earned(user, amount, *, commit=False):
    if not user:
        return False
    try:
        amount = int(amount or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return False
    state = _state(user)
    ensure_daily_quest(user, state=state)
    counters = dict(state.get('counters') or {})
    counters['gold_earned'] = int(counters.get('gold_earned') or 0) + amount
    state['counters'] = counters
    _save_state(user, state, commit=commit)
    return True


def increment_counter(user, counter_key, amount=1, *, commit=False):
    if not user:
        return False
    try:
        amount = int(amount or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return False
    state = _state(user)
    ensure_daily_quest(user, state=state)
    counters = dict(state.get('counters') or {})
    counters[counter_key] = int(counters.get(counter_key) or 0) + amount
    state['counters'] = counters
    _save_state(user, state, commit=commit)
    return True


def mark_duel_hint(user, hint_id, *, commit=False):
    if not user or hint_id not in DUEL_HINT_IDS:
        return False
    state = _state(user)
    seen = set(state.get('duel_hints_seen') or [])
    if hint_id in seen:
        return False
    state['duel_hints_seen'] = [hint for hint in DUEL_HINT_IDS if hint in seen | {hint_id}]
    _save_state(user, state, commit=commit)
    return True


def mark_duel_hints(user, hint_ids, *, commit=False):
    """Atomically mark several validated Duel coach steps."""
    if not user:
        return False
    requested = set(hint_ids or [])
    if not requested or not requested.issubset(DUEL_HINT_IDS):
        return False
    state = _state(user)
    seen = set(state.get('duel_hints_seen') or [])
    changed = bool(requested - seen)
    if changed:
        state['duel_hints_seen'] = [
            hint for hint in DUEL_HINT_IDS if hint in seen | requested]
        _save_state(user, state, commit=commit)
    return changed


def mark_menu_hint(user, hint_id, *, commit=False):
    if not user or hint_id not in MENU_HINT_IDS:
        return False
    state = _state(user)
    seen = set(state.get('menu_hints_seen') or [])
    if hint_id in seen:
        return False
    state['menu_hints_seen'] = [hint for hint in MENU_HINT_IDS if hint in seen | {hint_id}]
    _save_state(user, state, commit=commit)
    return True


def mark_menu_hints(user, hint_ids, *, commit=False):
    """Atomically mark several validated menu coach steps."""
    if not user:
        return False
    requested = set(hint_ids or [])
    if not requested or not requested.issubset(MENU_HINT_IDS):
        return False
    state = _state(user)
    seen = set(state.get('menu_hints_seen') or [])
    changed = bool(requested - seen)
    if changed:
        state['menu_hints_seen'] = [
            hint for hint in MENU_HINT_IDS if hint in seen | requested]
        _save_state(user, state, commit=commit)
    return changed


def mark_welcome_seen(user, *, commit=False):
    if not user:
        return False
    # Welcome is orientation only. Cards arrive after the Collection roulette;
    # all economy items arrive in the First Journey finale reward.
    state = _state(user)
    state['welcome_pending'] = False
    state['welcome_seen'] = True
    _save_state(user, state, commit=commit)
    return True


def skip_onboarding(user, *, commit=False):
    state = _state(user)
    state['onboarding_skipped'] = True
    state['welcome_pending'] = False
    # Pausing guidance must not bypass or duplicate the end-of-journey reward.
    _save_state(user, state, commit=commit)
    return state


def resume_onboarding(user, *, commit=False):
    state = _state(user)
    state['onboarding_skipped'] = False
    _save_state(user, state, commit=commit)
    return state


def _clear_lesson_replay(state, *, restore_hints=True):
    """End a replay session and optionally restore its historical hints."""
    if restore_hints:
        menu_seen = set(state.get('menu_hints_seen') or [])
        menu_seen.update(
            state.get('lesson_replay_original_menu_hints') or [])
        state['menu_hints_seen'] = [
            hint for hint in MENU_HINT_IDS if hint in menu_seen]

        duel_seen = set(state.get('duel_hints_seen') or [])
        duel_seen.update(
            state.get('lesson_replay_original_duel_hints') or [])
        state['duel_hints_seen'] = [
            hint for hint in DUEL_HINT_IDS if hint in duel_seen]

    state['replaying_lesson'] = None
    state['lesson_replay_baseline'] = {}
    state['lesson_replay_steps'] = []
    state['lesson_replay_original_menu_hints'] = []
    state['lesson_replay_original_duel_hints'] = []


def start_lesson(user, lesson_id, *, commit=False):
    """Activate one optional lesson and return its configured entry point."""
    if not user:
        return None, 'User not found'
    lesson = FOLLOW_UP_LESSON_BY_ID.get(lesson_id)
    if not lesson:
        return None, 'Unknown lesson'
    state = _state(user)
    if state.get('replay_completion_pending'):
        return None, 'Finish the completed lesson recap before starting another lesson'
    facts = _facts(user, state)
    if 'finish_tutorial' not in facts.get('completed_steps', set()):
        return None, 'Finish the First Journey before starting this lesson'
    _clear_lesson_replay(state, restore_hints=True)
    state['lesson_session_steps'] = []
    state['lesson_skipped_steps'] = []
    facts = _facts(user, state)
    completed = (
        lesson.get('completion_step')
        in set(facts.get('completed_steps') or []))
    if completed:
        menu_seen = set(state.get('menu_hints_seen') or [])
        replay_menu = set(
            REPLAY_MENU_HINT_IDS_BY_LESSON.get(lesson_id) or ())
        state['lesson_replay_original_menu_hints'] = [
            hint for hint in MENU_HINT_IDS
            if hint in menu_seen and hint in replay_menu]
        state['menu_hints_seen'] = [
            hint for hint in MENU_HINT_IDS
            if hint in menu_seen and hint not in replay_menu]

        duel_seen = set(state.get('duel_hints_seen') or [])
        replay_duel = (
            set(DUEL_HINT_IDS) if lesson_id == 'duel_basics' else set())
        state['lesson_replay_original_duel_hints'] = [
            hint for hint in DUEL_HINT_IDS
            if hint in duel_seen and hint in replay_duel]
        state['duel_hints_seen'] = [
            hint for hint in DUEL_HINT_IDS
            if hint in duel_seen and hint not in replay_duel]
        state['replaying_lesson'] = lesson_id
        state['lesson_replay_baseline'] = {
            'conquer_battles': _nonnegative_int(
                facts.get('conquer_battles')),
            'duel_finishes': _nonnegative_int(
                facts.get('duel_finishes')),
        }
        state['lesson_replay_steps'] = (
            ['buy_first_cosmetic']
            if lesson_id == 'run_kingdom' else [])
    state['active_lesson'] = lesson_id
    state['onboarding_skipped'] = False
    dismissed = set(state.get('lessons_dismissed') or [])
    dismissed.discard(lesson_id)
    state['lessons_dismissed'] = sorted(dismissed)
    _save_state(user, state, commit=commit)
    return lesson, None


def dismiss_lesson(user, lesson_id, *, commit=False):
    """Dismiss one optional lesson without pausing every tutorial track."""
    if not user or lesson_id not in FOLLOW_UP_LESSON_BY_ID:
        return False
    state = _state(user)
    dismissed = set(state.get('lessons_dismissed') or [])
    changed = (
        lesson_id not in dismissed
        or state.get('active_lesson') == lesson_id
        or state.get('replaying_lesson') == lesson_id
        or bool(state.get('lesson_skipped_steps'))
    )
    dismissed.add(lesson_id)
    state['lessons_dismissed'] = sorted(dismissed)
    if state.get('active_lesson') == lesson_id:
        state['active_lesson'] = None
    if state.get('replaying_lesson') == lesson_id:
        _clear_lesson_replay(state, restore_hints=True)
    state['lesson_session_steps'] = []
    state['lesson_skipped_steps'] = []
    if changed:
        _save_state(user, state, commit=commit)
    return True


def skip_lesson_step(user, lesson_id, step_id, *, commit=False):
    """Mark one blocked optional-lesson coach step as intentionally skipped."""
    if not user:
        return False, 'User not found'
    if lesson_id not in FOLLOW_UP_LESSON_BY_ID:
        return False, 'Unknown lesson'
    state = _state(user)
    if state.get('active_lesson') != lesson_id:
        return False, 'Lesson is not active'

    if lesson_id == 'duel_basics':
        skipped_ids = DUEL_COACH_SKIP_HINTS.get(step_id)
        if not skipped_ids:
            return False, 'This lesson step cannot be skipped'
        seen = set(state.get('duel_hints_seen') or [])
        state['duel_hints_seen'] = [
            hint for hint in DUEL_HINT_IDS
            if hint in seen | set(skipped_ids)]
    else:
        skipped_ids = (
            SKIPPABLE_LESSON_COACH_STEPS
            .get(lesson_id, {})
            .get(step_id)
        )
        if not skipped_ids:
            return False, 'This lesson step cannot be skipped'
        menu_seen = set(state.get('menu_hints_seen') or [])
        menu_seen.update(
            skipped_id for skipped_id in skipped_ids
            if skipped_id in MENU_HINT_IDS)
        state['menu_hints_seen'] = [
            hint for hint in MENU_HINT_IDS if hint in menu_seen]

    skipped = set(state.get('lesson_skipped_steps') or [])
    skipped.update(skipped_ids)
    state['lesson_skipped_steps'] = sorted(skipped)
    completed = set(state.get('completed_steps') or [])
    completed.update(set(skipped_ids) & ONBOARDING_STEP_IDS)
    state['completed_steps'] = sorted(completed)
    _save_state(user, state, commit=commit)
    return True, None


def acknowledge_replay_completion(
        user, lesson_id, *, commit=False):
    """Clear the replay finale after the player closes its recap window."""
    if not user:
        return False
    state = _state(user)
    if state.get('replay_completion_pending') != lesson_id:
        return False
    state['replay_completion_pending'] = None
    _save_state(user, state, commit=commit)
    return True


def reset_onboarding(user, *, commit=False):
    state = _state(user)
    state['onboarding_skipped'] = False
    state['welcome_pending'] = True
    state['welcome_seen'] = False
    state['duel_hints_seen'] = []
    state['active_lesson'] = None
    state['lessons_dismissed'] = []
    _clear_lesson_replay(state, restore_hints=False)
    state['lesson_session_steps'] = []
    state['lesson_skipped_steps'] = []
    state['replay_completion_pending'] = None
    _save_state(user, state, commit=commit)
    return state


def _duel_result_count(user_id):
    return GameResult.query.filter(
        or_(GameResult.winner_user_id == user_id, GameResult.loser_user_id == user_id)
    ).count()


def _duel_win_count(user_id):
    return GameResult.query.filter_by(winner_user_id=user_id).count()


def _duel_loss_count(user_id):
    return GameResult.query.filter_by(loser_user_id=user_id).count()


def _conquer_battle_count(user_id):
    return LandAttackLog.query.filter(
        or_(LandAttackLog.attacker_user_id == user_id,
            LandAttackLog.defender_user_id == user_id)
    ).count()


def _conquer_lands_count(user_id):
    return LandAttackLog.query.filter_by(
        attacker_user_id=user_id, result='attacker_won'
    ).count()


def _saved_defence_count(user_id):
    return LandConfig.query.filter_by(
        user_id=user_id, config_type='defence', status='active'
    ).count()


def _lesson_replay_complete(
        lesson_id, state, *, menu_hints_seen,
        duel_finishes, conquer_battles):
    """Return whether the temporary, reward-free replay reached its end."""
    replay_steps = set(state.get('lesson_replay_steps') or [])
    lesson_session_steps = set(
        state.get('lesson_session_steps') or [])
    skipped_steps = set(state.get('lesson_skipped_steps') or [])
    replay_or_skipped_steps = (
        replay_steps | lesson_session_steps | skipped_steps)
    baseline = state.get('lesson_replay_baseline') or {}
    if lesson_id == 'grow_collection':
        return (
            {
                'collection_growth_intro',
                'collection_growth_recap',
            }.issubset(menu_hints_seen)
            and set(REPLAY_STEP_IDS_BY_LESSON[lesson_id]).issubset(
                replay_or_skipped_steps)
        )
    if lesson_id == 'build_attack':
        return (
            {
                'build_attack_intro_window',
                'conquer_build_yourself',
                'conquer_build_yourself_tactics',
                'conquer_build_yourself_prelude',
            }.issubset(menu_hints_seen)
            and (
                conquer_battles > _nonnegative_int(
                    baseline.get('conquer_battles'))
                or 'finish_second_conquer_battle' in skipped_steps
            )
        )
    if lesson_id == 'run_kingdom':
        # Replaying management should not force the player to buy another
        # cosmetic. Revisiting the full guidance is sufficient.
        return {
            'kingdom_management_intro',
            'kingdom_config_essentials',
            'kingdom_collect_production',
            'kingdom_config_shields_style',
        }.issubset(menu_hints_seen)
    if lesson_id == 'defend_land':
        return (
            {
                'defend_land_intro_window',
                'defence_intro',
                'defence_battle_plan',
                'defence_final_response',
            }.issubset(menu_hints_seen)
            and 'save_first_defence_config' in replay_or_skipped_steps
        )
    if lesson_id == 'duel_basics':
        return (
            'duel_tutorial_start_window' in menu_hints_seen
            and set(DUEL_BASICS_REQUIRED_HINT_IDS).issubset(
                set(state.get('duel_hints_seen') or []))
            and (
                duel_finishes > _nonnegative_int(
                    baseline.get('duel_finishes'))
                or 'finish_first_duel' in skipped_steps
            )
        )
    return True


def _facts(user, state=None):
    state = state or _state(user)
    counters = state.get('counters') or {}
    user_id = user.id
    duel_finishes = _duel_result_count(user_id)
    duel_wins = _duel_win_count(user_id)
    duel_losses = _duel_loss_count(user_id)
    conquer_battles = _conquer_battle_count(user_id)
    conquered_lands = _conquer_lands_count(user_id)
    production_collections = int(counters.get('kingdom_production_collections') or 0)
    skipped_steps = set(state.get('lesson_skipped_steps') or [])
    completed = set(state.get('completed_steps') or [])
    completed.update(skipped_steps & ONBOARDING_STEP_IDS)
    if duel_finishes >= 1:
        completed.add('finish_first_duel')
    if (
            'finish_first_duel' in completed
            and 'duel_tutorial_start_window'
            in set(state.get('menu_hints_seen') or [])
            and set(DUEL_BASICS_REQUIRED_HINT_IDS).issubset(
                set(state.get('duel_hints_seen') or []))):
        completed.add('finish_duel_basics_lesson')
    # Win-based: the first-conquest tutorial beat is only "done" once a land is
    # actually conquered. A lost first battle is a no-penalty retry, so the
    # player stays in the conquest phase until they win.
    if conquered_lands >= 1:
        completed.add('finish_first_conquer_battle')
    if production_collections >= 1:
        completed.add('collect_first_kingdom_production')
    if _saved_defence_count(user_id) >= 1:
        completed.add('save_first_defence_config')
    if conquer_battles >= 2:
        completed.add('finish_second_conquer_battle')
    menu_hints_seen = set(state.get('menu_hints_seen') or [])
    menu_hints_seen.update(skipped_steps & set(MENU_HINT_IDS))
    if (
            {
                'collection_growth_intro',
                'collection_growth_recap',
            }.issubset(menu_hints_seen)
            and {
                'open_first_main_booster',
                'open_first_side_booster',
                'sell_first_card',
                'trade_first_card',
            }.issubset(completed)):
        completed.add('finish_collection_lesson')
    if (
            'finish_second_conquer_battle' in completed
            and {
                'build_attack_intro_window',
                'conquer_build_yourself',
                'conquer_build_yourself_tactics',
                'conquer_build_yourself_prelude',
            }.issubset(menu_hints_seen)):
        completed.add('finish_build_attack_lesson')
    if (
            {
                'kingdom_management_intro',
                'kingdom_config_essentials',
                'kingdom_collect_production',
                'kingdom_config_shields_style',
            }.issubset(menu_hints_seen)):
        if 'buy_first_cosmetic' in completed:
            completed.add('finish_run_kingdom_lesson')
    if (
            state.get('active_lesson') == 'defend_land'
            and 'save_first_defence_config' in (
                set(state.get('lesson_session_steps') or [])
                | skipped_steps)
            and {
                'defend_land_intro_window',
                'defence_intro',
                'defence_battle_plan',
                'defence_final_response',
            }.issubset(menu_hints_seen)):
        completed.add('finish_defend_land_lesson')

    replaying_lesson = state.get('replaying_lesson')
    replay_lesson = FOLLOW_UP_LESSON_BY_ID.get(replaying_lesson)
    if replay_lesson and not _lesson_replay_complete(
            replaying_lesson,
            state,
            menu_hints_seen=menu_hints_seen,
            duel_finishes=duel_finishes,
            conquer_battles=conquer_battles):
        completed.discard(replay_lesson.get('completion_step'))

    early_completed = set()
    if duel_wins >= 1:
        early_completed.add('win_first_duel')
    if duel_wins >= 5:
        early_completed.add('win_5_duels')
    if duel_wins >= 10:
        early_completed.add('win_10_duels')
    if duel_finishes >= 3:
        early_completed.add('finish_3_duels')
    if duel_finishes >= 10:
        early_completed.add('finish_10_duels')
    if duel_losses >= 5:
        early_completed.add('lose_5_duels')
    if duel_losses >= 10:
        early_completed.add('lose_10_duels')
    gold_earned = int(counters.get('gold_earned') or 0)
    if gold_earned >= 1000:
        early_completed.add('earn_1000_gold')
    if gold_earned >= 10000:
        early_completed.add('earn_10000_gold')
    if conquered_lands >= 1:
        early_completed.add('conquer_1_land')
    if production_collections >= 5:
        early_completed.add('collect_kingdom_production_5')
    if conquer_battles >= 10:
        early_completed.add('finish_10_conquer_battles')
    if conquered_lands >= 5:
        early_completed.add('conquer_5_lands')
    if conquered_lands >= 10:
        early_completed.add('conquer_10_lands')
    if conquered_lands >= 20:
        early_completed.add('conquer_20_lands')
    if conquered_lands >= 25:
        early_completed.add('conquer_25_lands')

    return {
        'completed_steps': completed,
        'early_completed': early_completed,
        'duel_finishes': duel_finishes,
        'duel_wins': duel_wins,
        'duel_losses': duel_losses,
        'conquer_battles': conquer_battles,
        'conquered_lands': conquered_lands,
        'gold_earned': gold_earned,
        'kingdom_production_collections': production_collections,
    }


def _reward_label(reward):
    parts = []
    if int(reward.get('gold') or 0):
        parts.append(f"+{int(reward.get('gold'))} gold")
    if int(reward.get('booster_packs') or 0):
        amount = int(reward.get('booster_packs'))
        parts.append(f"+{amount} main booster" + ('' if amount == 1 else 's'))
    if int(reward.get('booster_packs_side') or 0):
        amount = int(reward.get('booster_packs_side'))
        parts.append(f"+{amount} side booster" + ('' if amount == 1 else 's'))
    if int(reward.get('maps') or 0):
        amount = int(reward.get('maps'))
        parts.append(f"+{amount} map" + ('' if amount == 1 else 's'))
    return ', '.join(parts)


def _coerce_utc_naive(now=None):
    if now is None:
        return _utcnow()
    if now.tzinfo is not None:
        return now.astimezone(timezone.utc).replace(tzinfo=None)
    return now


def _daily_quest_day_key(now=None):
    current = _coerce_utc_naive(now)
    shifted = current - timedelta(hours=DAILY_QUEST_RESET_HOUR_UTC)
    return shifted.date().isoformat()


def _daily_quest_resets_at(now=None):
    current = _coerce_utc_naive(now)
    shifted = current - timedelta(hours=DAILY_QUEST_RESET_HOUR_UTC)
    next_day = shifted.date() + timedelta(days=1)
    return (
        datetime.combine(next_day, time.min)
        + timedelta(hours=DAILY_QUEST_RESET_HOUR_UTC)
    )


def _daily_quest_baseline(facts):
    return {
        key: int((facts or {}).get(key) or 0)
        for key in DAILY_QUEST_FACT_KEYS
    }


def _daily_quest_tiers(state, facts):
    claimed_count = _nonnegative_int(
        (state or {}).get('daily_quests_claimed_count'))
    completed = set((facts or {}).get('completed_steps') or [])
    # Existing players who completed both introductory modes enter the mature
    # pool instead of being treated like brand-new accounts.
    if claimed_count == 0 and {
            'finish_tutorial', 'finish_first_duel'}.issubset(completed):
        claimed_count = 6
    if claimed_count < 3:
        return {'easy'}
    if claimed_count < 6:
        return {'easy', 'medium'}
    return {'easy', 'medium', 'hard'}


def _eligible_daily_quests(facts, state=None):
    completed = set((facts or {}).get('completed_steps') or [])
    tiers = _daily_quest_tiers(state, facts)
    eligible = []
    for quest in DAILY_QUESTS:
        required = quest.get('requires_completed_step')
        if required and required not in completed:
            continue
        if quest.get('tier', 'easy') not in tiers:
            continue
        eligible.append(quest)
    return eligible


def _select_daily_quest(user_id, day_key, quests=None):
    pool = list(quests or DAILY_QUESTS)
    if not pool:
        return None
    seed_text = f'{int(user_id or 0)}:{day_key}'
    seed = int(hashlib.sha256(seed_text.encode('utf-8')).hexdigest(), 16)
    rng = random.Random(seed)
    weights = {'easy': 60, 'medium': 30, 'hard': 10}
    tiers = sorted({quest.get('tier', 'easy') for quest in pool})
    selected_tier = rng.choices(
        tiers, weights=[weights.get(tier, 1) for tier in tiers], k=1)[0]
    tier_pool = [
        quest for quest in pool if quest.get('tier', 'easy') == selected_tier]
    return rng.choice(tier_pool)


def ensure_daily_quest(user, *, state=None, facts=None, commit=False):
    if not user:
        return None
    state = state if state is not None else _state(user)
    facts = facts if facts is not None else _facts(user, state)
    day_key = _daily_quest_day_key()
    eligible = _eligible_daily_quests(facts, state)
    eligible_ids = {quest['id'] for quest in eligible}
    dq = state.get('daily_quest')

    if not eligible:
        if dq is not None:
            state['daily_quest'] = None
            _save_state(user, state, commit=commit)
        return None

    valid = (
        isinstance(dq, dict)
        and dq.get('day_key') == day_key
        and dq.get('quest_id') in eligible_ids
    )
    if not valid:
        quest = _select_daily_quest(user.id, day_key, eligible)
        if not quest:
            return None
        dq = {
            'day_key': day_key,
            'quest_id': quest['id'],
            'baseline': _daily_quest_baseline(facts),
            'claimed': False,
            'generated_at': _utcnow().isoformat(),
        }
        state['daily_quest'] = dq
        _save_state(user, state, commit=commit)
    return dq


def _locked_daily_quest_payload():
    return {
        'id': DAILY_QUEST_REWARD_ID,
        'locked': True,
        'title': 'Daily Quest',
        'description': 'Conquer your first land to unlock daily quests.',
        'tier': 'locked',
        'target': 1,
        'progress': 0,
        'completed': False,
        'claimed': False,
        'claimable': False,
        'reward': {},
        'reward_label': '',
        'day_key': _daily_quest_day_key(),
        'resets_at': _daily_quest_resets_at().isoformat(),
    }


def _daily_quest_payload(user, state, facts):
    dq = ensure_daily_quest(user, state=state, facts=facts, commit=False)
    if not dq:
        return _locked_daily_quest_payload()
    quest = DAILY_QUEST_BY_ID.get(dq.get('quest_id'))
    if not quest:
        return _locked_daily_quest_payload()

    fact_key = quest.get('fact')
    baseline = dq.get('baseline') or {}
    current = int((facts or {}).get(fact_key) or 0)
    start = int(baseline.get(fact_key) or 0)
    target = max(1, int(quest.get('target') or 1))
    raw_progress = max(0, current - start)
    completed = raw_progress >= target
    claimed = bool(dq.get('claimed'))
    reward = dict(quest.get('reward') or {})
    return {
        'id': DAILY_QUEST_REWARD_ID,
        'quest_id': quest['id'],
        'fact': fact_key,
        'title': quest.get('title') or 'Daily Quest',
        'description': quest.get('description') or '',
        'tier': quest.get('tier') or 'easy',
        'target': target,
        'progress': min(raw_progress, target),
        'completed': completed,
        'claimed': claimed,
        'claimable': bool(completed and not claimed),
        'reward': reward,
        'reward_label': _reward_label(reward),
        'day_key': dq.get('day_key') or _daily_quest_day_key(),
        'resets_at': _daily_quest_resets_at().isoformat(),
    }


def _step_payload(step, completed, claimed):
    payload = dict(step)
    reward = dict(payload.get('reward') or {})
    payload['reward'] = reward
    payload['reward_label'] = _reward_label(reward)
    payload['completed'] = bool(completed)
    payload['claimed'] = bool(claimed)
    payload['claimable'] = bool(completed and not claimed and reward)
    return payload


def _lesson_substep_complete(substep, facts, state, lesson_id=None):
    source = substep.get('source')
    step_id = substep.get('id')
    if step_id in set(state.get('lesson_skipped_steps') or []):
        return True
    if source == 'menu_hint':
        return step_id in set(state.get('menu_hints_seen') or [])
    if source == 'duel_hint':
        return step_id in set(state.get('duel_hints_seen') or [])
    if (
            lesson_id == 'defend_land'
            and state.get('active_lesson') == lesson_id
            and step_id == 'save_first_defence_config'):
        return step_id in set(
            state.get('lesson_session_steps') or [])
    if (
            state.get('replaying_lesson') == lesson_id
            and step_id in set(
                REPLAY_STEP_IDS_BY_LESSON.get(lesson_id) or ())):
        if lesson_id == 'build_attack':
            baseline = state.get('lesson_replay_baseline') or {}
            return _nonnegative_int(facts.get('conquer_battles')) > (
                _nonnegative_int(baseline.get('conquer_battles')))
        if lesson_id == 'duel_basics':
            baseline = state.get('lesson_replay_baseline') or {}
            return _nonnegative_int(facts.get('duel_finishes')) > (
                _nonnegative_int(baseline.get('duel_finishes')))
        return step_id in set(state.get('lesson_replay_steps') or [])
    return step_id in set(facts.get('completed_steps') or [])


def _follow_up_lesson_payloads(state, facts, claimed_core):
    """Serialize the optional curriculum from one central lesson registry."""
    core_by_id = {step['id']: step for step in CORE_STEPS}
    first_journey_complete = 'finish_tutorial' in set(
        facts.get('completed_steps') or [])
    active_lesson = state.get('active_lesson')
    dismissed = set(state.get('lessons_dismissed') or [])
    payloads = []
    for lesson in FOLLOW_UP_LESSONS:
        completion_step = lesson.get('completion_step')
        completed = completion_step in set(facts.get('completed_steps') or [])
        substeps = []
        progress = 0
        for substep in lesson.get('substeps') or []:
            item = dict(substep)
            item['completed'] = _lesson_substep_complete(
                substep, facts, state, lesson['id'])
            progress += int(item['completed'])
            substeps.append(item)
        reward_source = core_by_id.get(completion_step) or {}
        reward = dict(reward_source.get('reward') or {})
        claimed = completion_step in claimed_core
        is_active = active_lesson == lesson['id'] and not completed
        started = bool(is_active or progress)
        locked = not first_journey_complete
        payloads.append({
            **{key: value for key, value in lesson.items()
               if key != 'substeps'},
            'lesson': True,
            'substeps': substeps,
            'progress': progress,
            'total_steps': len(substeps),
            'progress_label': f'{progress}/{len(substeps)}',
            'completed': completed,
            'claimed': claimed,
            'claimable': bool(
                completed and not claimed and reward and not locked),
            'reward': reward,
            'reward_id': completion_step,
            'reward_label': _reward_label(reward),
            'active': is_active,
            'started': started,
            'dismissed': lesson['id'] in dismissed,
            'replaying': state.get('replaying_lesson') == lesson['id'],
            'locked': locked,
            'action_label': 'Continue' if started else 'Start',
        })
    return payloads


def _journey_metadata(completed_steps, menu_hints_seen=None):
    """First-session guided path.

    The mandatory tutorial is the kingdom core loop: reveal the prepared
    starter collection -> conquer a land. Booster opening is deferred until
    after the finale, and the duel remains optional.
    """
    completed = set(completed_steps or [])
    seen = set(menu_hints_seen or [])
    if ('starter_suit_reveal' not in seen
            and 'finish_first_conquer_battle' not in completed):
        return {
            'coach_version': COACH_VERSION,
            'journey_phase': 'reveal_starter_cards',
            'next_action': {
                'screen': 'collection',
                'label': 'Reveal Starter Cards',
                'target_id': 'starter_suit_reveal',
            },
        }
    if 'finish_first_conquer_battle' not in completed:
        return {
            'coach_version': COACH_VERSION,
            'journey_phase': 'first_conquest',
            'next_action': {
                'screen': 'kingdom',
                'label': 'Conquer First Land',
                'target_id': 'recommended_tutorial_land',
            },
        }
    if 'finish_tutorial' not in completed:
        return {
            'coach_version': COACH_VERSION,
            'journey_phase': 'finish_tutorial',
            'next_action': {
                'screen': 'kingdom',
                'label': 'Finish the Kingdom Tour',
                'target_id': 'kingdom_after_conquer_map',
            },
        }
    return {
        'coach_version': COACH_VERSION,
        'journey_phase': 'complete',
        'next_action': None,
    }


def _starter_present_payload(user):
    return {
        'gold': int(user.gold or 0),
        'booster_packs': int(user.booster_packs or 0),
        'booster_packs_side': int(user.booster_packs_side or 0),
        'maps': int(user.maps or 0),
        'starter_defaults': {
            'gold': int(getattr(settings, 'INITIAL_GOLD', 0) or 0),
            'booster_packs': int(getattr(settings, 'STARTER_BOOSTER_PACKS', 0) or 0),
            'booster_packs_side': int(getattr(settings, 'STARTER_BOOSTER_PACKS_SIDE', 0) or 0),
            'maps': int(getattr(settings, 'STARTER_MAPS', 0) or 0),
        },
    }


def serialize_onboarding_state(user):
    if not user:
        return {}
    state = _state(user)
    facts = _facts(user, state)
    active_lesson = FOLLOW_UP_LESSON_BY_ID.get(state.get('active_lesson'))
    if (
            active_lesson
            and active_lesson.get('completion_step')
            in facts.get('completed_steps', set())):
        replay_finished = (
            state.get('replaying_lesson') == active_lesson.get('id'))
        completion_step = active_lesson.get('completion_step')
        completed_steps = set(state.get('completed_steps') or [])
        if state.get('lesson_skipped_steps'):
            completed_steps.update(
                set(state.get('lesson_skipped_steps') or [])
                & ONBOARDING_STEP_IDS)
        # Persist the computed lesson finish itself.  Otherwise a completion
        # that depends on session-scoped actions would disappear as soon as
        # those temporary markers are cleared below.
        completed_steps.add(completion_step)
        state['completed_steps'] = sorted(completed_steps)
        if replay_finished:
            state['replay_completion_pending'] = active_lesson.get('id')
            _clear_lesson_replay(state, restore_hints=True)
        state['active_lesson'] = None
        state['lesson_session_steps'] = []
        state['lesson_skipped_steps'] = []
        # Completion state must persist so a refresh cannot restart a replay
        # or a first-time lesson that was completed by skipping a blocked step.
        _save_state(user, state, commit=False)
    claimed_core = set(state.get('claimed_rewards') or [])
    claimed_early = set(state.get('early_goals_claimed') or [])
    core_steps = [
        _step_payload(step, step['id'] in facts['completed_steps'], step['id'] in claimed_core)
        for step in CORE_STEPS
    ]
    first_journey_complete = 'finish_tutorial' in facts['completed_steps']
    if not first_journey_complete:
        for step in core_steps:
            if step.get('group') == 'first_journey':
                continue
            step['locked'] = True
            step['claimable'] = False
    early_goals = [
        _step_payload(goal, goal['id'] in facts['early_completed'], goal['id'] in claimed_early)
        for goal in EARLY_GOALS
    ]
    goals_unlocked = first_journey_complete
    if not goals_unlocked:
        for goal in early_goals:
            goal['locked'] = True
            goal['claimable'] = False
    daily_quest = _daily_quest_payload(user, state, facts)
    lessons = _follow_up_lesson_payloads(state, facts, claimed_core)
    facts_payload = dict(facts)
    facts_payload['completed_steps'] = sorted(facts['completed_steps'])
    facts_payload['early_completed'] = sorted(facts['early_completed'])
    journey = _journey_metadata(
        facts['completed_steps'], state.get('menu_hints_seen') or [])
    return {
        **journey,
        'schema_version': (
            _nonnegative_int(state.get('schema_version'))
            or ONBOARDING_SCHEMA_VERSION),
        'welcome_pending': bool(state.get('welcome_pending')),
        'welcome_seen': bool(state.get('welcome_seen')),
        'completed_steps': sorted(facts['completed_steps']),
        'claimed_rewards': sorted(claimed_core),
        'early_goals_claimed': sorted(claimed_early),
        'duel_hints_seen': list(state.get('duel_hints_seen') or []),
        'menu_hints_seen': list(state.get('menu_hints_seen') or []),
        'starter_suits': dict(state.get('starter_suits') or {}),
        'starter_set_granted': bool(state.get('starter_set_granted')),
        'onboarding_skipped': bool(state.get('onboarding_skipped')),
        'active_lesson': state.get('active_lesson'),
        'lessons_dismissed': list(state.get('lessons_dismissed') or []),
        'replaying_lesson': state.get('replaying_lesson'),
        'lesson_replay_steps': list(
            state.get('lesson_replay_steps') or []),
        'lesson_skipped_steps': list(
            state.get('lesson_skipped_steps') or []),
        'replay_completion_pending': state.get(
            'replay_completion_pending'),
        'counters': dict(state.get('counters') or {}),
        'daily_quests_claimed_count': _nonnegative_int(
            state.get('daily_quests_claimed_count')),
        'facts': facts_payload,
        'core_steps': core_steps,
        'lessons': lessons,
        'early_goals': early_goals,
        'daily_quest': daily_quest,
        'starter_present': _starter_present_payload(user),
        'pending_reward_count': (
            sum(1 for item in core_steps + early_goals if item['claimable'])
            + (1 if daily_quest.get('claimable') else 0)
        ),
    }


def _apply_reward(user, reward):
    reward = dict(reward or {})
    if int(reward.get('gold') or 0):
        user.gold = int(user.gold or 0) + int(reward['gold'])
    if int(reward.get('booster_packs') or 0):
        user.booster_packs = int(user.booster_packs or 0) + int(reward['booster_packs'])
    if int(reward.get('booster_packs_side') or 0):
        user.booster_packs_side = int(user.booster_packs_side or 0) + int(reward['booster_packs_side'])
    if int(reward.get('maps') or 0):
        user.maps = int(user.maps or 0) + int(reward['maps'])
    return reward


def _balances(user):
    return {
        'gold': int(user.gold or 0),
        'booster_packs': int(user.booster_packs or 0),
        'booster_packs_side': int(user.booster_packs_side or 0),
        'maps': int(user.maps or 0),
    }


def claim_daily_quest(user, *, commit=False):
    if not user:
        return {'success': False, 'message': 'User not found'}, 404
    state = _state(user)
    facts = _facts(user, state)
    dq = ensure_daily_quest(user, state=state, facts=facts, commit=False)
    if not dq:
        return {'success': False, 'message': 'Daily quest is not unlocked yet'}, 400

    payload = _daily_quest_payload(user, state, facts)
    if payload.get('claimed'):
        return {
            'success': True,
            'already_claimed': True,
            'reward_id': DAILY_QUEST_REWARD_ID,
            'reward': {},
            'balances': _balances(user),
            'onboarding': serialize_onboarding_state(user),
        }, 200
    if not payload.get('completed'):
        return {'success': False, 'message': 'Daily quest is not ready yet'}, 400

    reward = _apply_reward(user, payload.get('reward') or {})
    dq = dict(dq)
    dq['claimed'] = True
    dq['claimed_at'] = _utcnow().isoformat()
    state['daily_quest'] = dq
    state['daily_quests_claimed_count'] = _nonnegative_int(
        state.get('daily_quests_claimed_count')) + 1
    state['last_claimed_at'] = dq['claimed_at']
    _save_state(user, state, commit=False)
    if commit:
        db.session.commit()
    return {
        'success': True,
        'reward_id': DAILY_QUEST_REWARD_ID,
        'reward': reward,
        'reward_label': _reward_label(reward),
        'balances': _balances(user),
        'onboarding': serialize_onboarding_state(user),
    }, 200


def claim_reward(user, reward_id, *, commit=False):
    if not user:
        return {'success': False, 'message': 'User not found'}, 404
    if reward_id == DAILY_QUEST_REWARD_ID:
        return claim_daily_quest(user, commit=commit)
    state = _state(user)
    facts = _facts(user, state)

    core_by_id = {step['id']: step for step in CORE_STEPS}
    early_by_id = {goal['id']: goal for goal in EARLY_GOALS}
    if reward_id in core_by_id:
        claimed_key = 'claimed_rewards'
        source = core_by_id[reward_id]
        eligible = (
            reward_id in facts['completed_steps']
            and (
                source.get('group') == 'first_journey'
                or 'finish_tutorial' in facts['completed_steps']
            )
        )
    elif reward_id in early_by_id:
        claimed_key = 'early_goals_claimed'
        eligible = (
            'finish_tutorial' in facts['completed_steps']
            and reward_id in facts['early_completed'])
        source = early_by_id[reward_id]
    else:
        return {'success': False, 'message': 'Unknown onboarding reward'}, 404

    claimed = set(state.get(claimed_key) or [])
    if reward_id in claimed:
        return {
            'success': True,
            'already_claimed': True,
            'reward_id': reward_id,
            'reward': {},
            'balances': _balances(user),
            'onboarding': serialize_onboarding_state(user),
        }, 200

    if not eligible:
        return {'success': False, 'message': 'Onboarding reward is not ready yet'}, 400

    reward = _apply_reward(user, source.get('reward') or {})
    claimed.add(reward_id)
    state[claimed_key] = sorted(claimed)
    if reward_id in CORE_STEP_IDS:
        completed = set(state.get('completed_steps') or [])
        completed.add(reward_id)
        state['completed_steps'] = sorted(completed)
    state['last_claimed_at'] = _utcnow().isoformat()
    _save_state(user, state, commit=False)
    if commit:
        db.session.commit()
    return {
        'success': True,
        'reward_id': reward_id,
        'reward': reward,
        'reward_label': _reward_label(reward),
        'balances': _balances(user),
        'onboarding': serialize_onboarding_state(user),
    }, 200
