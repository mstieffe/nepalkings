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
                'You build your position, then clash in battles until someone reaches the point goal.',
            ],
        },
        {
            'title': 'Build, then battle',
            'layout': 'image_top',
            'image': lambda: td.duel_build_battle_diagram(),
            'image_caption': 'Building phases create the board that decides the battle phase.',
            'lines': [
                'Each round has a building phase to turn cards into figures and spells, then a battle phase where they fight for points.',
                "Both players draw from one shared deck, so every card you take is a card your opponent can't have.",
            ],
        },
    ]


def conquer_battle_intro_pages():
    return [{
        'title': 'Your prepared attack',
        'layout': 'image_top',
        'image': lambda: td.battle_flow_diagram(),
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
