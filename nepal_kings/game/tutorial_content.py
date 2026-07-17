# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Single-source page definitions for onboarding tutorial windows."""

import pygame

from config import settings
from game.components import tutorial_diagrams as td


def welcome_pages(username, *, screen_height=None):
    height = int(screen_height or settings.SCREEN_HEIGHT)
    return [{
        'title': 'Your path to the crown',
        'layout': 'image_top',
        'image': lambda: td.conquer_start_image(int(0.26 * height)),
        'image_frame': False,
        'image_caption': '',
        'lines': [
            f'Welcome, {username}!',
            'You want to become the greatest king of Nepal?',
            'Turn cards into figures, spells, and tactics, then conquer land after land until the crown is yours.',
        ],
        'button_label': 'Start Tutorial',
    }]


def reward_reveal_items(reward):
    """Turn a reward payload into the shared reveal-card descriptions."""
    reward = dict(reward or {})
    items = []
    gold = int(reward.get('gold') or 0)
    if gold > 0:
        items.append({
            'kind': 'gold', 'label': f'{gold} gold',
            'description': 'Spend it on booster packs, cosmetics, and shields.',
        })
    main = int(reward.get('booster_packs') or 0)
    if main > 0:
        items.append({
            'kind': 'main_booster',
            'label': f"{main} main booster" + ('' if main == 1 else 's'),
            'description': 'Main cards build your core figures, spells, and tactics.',
        })
    side = int(reward.get('booster_packs_side') or 0)
    if side > 0:
        items.append({
            'kind': 'side_booster',
            'label': f"{side} side booster" + ('' if side == 1 else 's'),
            'description': 'Side cards unlock advanced figures and effects.',
        })
    maps = int(reward.get('maps') or 0)
    if maps > 0:
        items.append({
            'kind': 'map',
            'label': f"{maps} map" + ('' if maps == 1 else 's'),
            'description': 'Maps skip the cooldown after conquering a land.',
        })
    return items


def collection_basics_pages():
    return [{
        'title': 'Cards become actions',
        'layout': 'text_image_text',
        'lines': [
            'Every figure, spell, and tactic is built from a regular deck of cards: some from a single card, some from a recipe.',
            "Don't worry about memorizing recipes: the game always shows you what you can build.",
        ],
        'image': lambda: td.card_recipe_examples(),
        'image_caption': 'Some examples.',
    }]


def starter_present_pages():
    # Intentional presentation contract: all four suits remain visible even
    # though the balanced starter grant is restricted server-side.
    return [{
        'title': 'Your starter set',
        'layout': 'image_top',
        'image': lambda: td.suit_roulette_diagram(),
        'image_caption': 'One of the four suits, drawn at random.',
        'lines': [
            'You will receive a starter set of cards, all in one suit.',
            'Spin the roulette to reveal which suit is yours.',
        ],
        'button_label': 'Spin Roulette',
    }]


def collection_growth_pages():
    return [
        {
            'title': 'Build a collection with purpose',
            'layout': 'image_top',
            'image': lambda: td.collection_growth_start_image(),
            'image_frame': False,
            'image_caption': 'Your kingdom is built on your collection.',
            'lines': [
                'Now that you are a true conqueror, it is time to learn how to manage your card collection.',
                'This lesson covers card types, selling, trading, and how to grow your collection with purpose.',
            ],
        },
        {
            'title': 'Key cards and number cards',
            'layout': 'text_image_text',
            'lines': [
                'Key cards have jewels and are the fixed core of every figure.',
                'Number cards are the variable part of the figure and define resource cost and production',
            ],
            'image': lambda: td.key_number_cards_diagram(),
        },
        {
            'title': 'Two packs, two jobs',
            'layout': 'text_image_text',
            'lines': [
                'Main packs contain ranks 7–Ace. They form the core stock for many figures, spells, and battle tactics.',
                'Side packs contain ranks 2–6 and support advanced figures and spells.',
            ],
            'image': lambda: td.two_pack_jobs_diagram(),
            'image_caption': 'Different ranks feed different recipes; both card pools help your kingdom grow.',
        },
        {
            'title': 'Card borders show rarity',
            'layout': 'image_bottom',
            'lines': [
                'Cards have different rarities, shown by the border color.',
                'Rarity defines the chances of drawing a card from a booster pack, and the value of the card in trade.',
            ],
            'image': lambda: td.card_rarity_code_diagram(),
            'button_label': 'Begin Lesson',
        },
    ]


def collection_growth_recap_pages():
    return [{
        'title': 'Your cards build the kingdom',
        'layout': 'text_image_text',
        'lines': [
            'Your conquered lands require defence figures that lock your active cards.',
            'More copies let you equip more lands and expand your kingdom.',
        ],
        'image': lambda: td.collection_capacity_diagram(),
        'image_max_height_ratio': 0.30,
        'button_label': 'Complete Lesson',
    }]


def build_attack_intro_pages():
    return [{
        'title': 'Make the next attack yours',
        'layout': 'image_top',
        'image': lambda: td.build_attack_start_image(),
        'image_frame': False,
        'image_caption': 'Figures set the strength; tactics and a prelude shape the fight.',
        'lines': [
            'Your first attack was prepared for you. Now you will build the whole plan yourself.',
            'Choose three figures, add three tactics, review the optional prelude spell, then finish the conquest.',
        ],
        'button_label': 'Begin Lesson',
    }]


def duel_intro_pages():
    return [
        {
            'title': 'The full game, head to head',
            'layout': 'image_top',
            'image': lambda: td.duel_start_image(),
            'image_frame': False,
            'image_caption': 'Draw, build, battle, and climb toward the point goal.',
            'lines': [
                'A duel is Nepal Kings at full depth: two players, one board, turn by turn.',
                'Reach the chosen point goal, or destroy the enemy Maharaja for an immediate Checkmate victory.',
            ],
        },
        {
            'title': 'Build, then battle',
            'layout': 'image_top',
            'image': lambda: td.duel_build_battle_diagram(),
            'image_caption': 'Building phases create the board that decides the battle phase.',
            'lines': [
                'Each round starts with a building phase: draw cards, complete recipes, and shape your board with figures and spells.',
                'Then the battle phase begins. Your figures and battle moves fight for points before the next round starts.',
            ],
        },
        {
            'title': 'One shared card pool',
            'layout': 'image_top',
            'image': lambda: td.duel_shared_card_pool_image(),
            'image_frame': False,
            'image_caption': 'Every draw changes what remains for both players.',
            'lines': [
                'Both players draw from the same deck. Watch the cards your rival takes and what remains.',
                'Draw to complete your own recipes—or take a card before your rival can use it.',
            ],
            'button_label': 'Begin Lesson',
        },
    ]


def conquer_battle_intro_pages():
    return [{
        'title': 'Your prepared attack',
        'layout': 'image_top',
        'image': lambda: td.battle_flow_diagram(),
        'image_frame': False,
        'lines': [
            '1. Both players fire their prelude spells.',
            '2. Battle figures are selected and set the starting score.',
            '3. Three tactic moves are played to turn the tide.',
            'Win the total, and the land is yours. This first battle is risk-free.',
        ],
    }]


def kingdom_overview_pages():
    return [{
        'title': 'Read your map',
        'layout': 'image_top',
        'image': lambda: pygame.image.load(
            'img/tutorial/read_your_map.png').convert_alpha(),
        'image_frame': False,
        'image_caption': 'Conquer a neighbour to grow your kingdom.',
        'lines': [
            'Every hex is a land. Yours form your kingdom; rivals hold the rest.',
            'Conquer neighbouring lands to grow, one hex at a time.',
        ],
    }]


def kingdom_management_pages():
    return [{
        'title': 'Turn land into a thriving kingdom',
        'layout': 'image_top',
        'image': lambda: td.run_kingdom_start_image(),
        'image_frame': False,
        'image_caption': 'Production, skills, loot, protection, and style all live behind the map.',
        'lines': [
            'Owned lands produce gold, packs, and maps. You will find the collection control and review how production and skills grow.',
            'Then visit shields and cosmetics, and choose one new look for your kingdom.',
        ],
        'button_label': 'Begin Lesson',
    }]


def defend_land_intro_pages():
    return [{
        'title': 'Make your land costly to take',
        'layout': 'image_top',
        'image': lambda: td.defend_land_start_image(),
        'image_frame': False,
        'image_caption': 'A saved defence is the plan rivals must overcome.',
        'lines': [
            'Every owned land can hold its own defensive figures, tactics, prelude, and final response.',
            'Build a complete plan and save it so the land is ready when another ruler attacks.',
        ],
        'button_label': 'Begin Lesson',
    }]


def loot_risk_pages():
    return [{
        'title': 'Cards, locks, and loot',
        'layout': 'image_top',
        'image': lambda: td.loot_risk_diagram(),
        'image_caption': 'Committed cards are locked, not spent.',
        'lines': [
            "Cards in an attack or defence are locked while it's active, not spent.",
            'If you lose, you only lose the cards the winner loots; everything else returns to your collection.',
            'Higher-tier lands raise the stakes with bigger loot.',
        ],
    }]
