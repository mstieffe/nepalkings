#!/usr/bin/env python3
"""Render the tutorial dialogue windows to PNGs for visual review.

Builds each onboarding window (welcome 1+2, welcome gift, lands, starter-suit
reveal, the conquer battle window and the kingdom overview) at a chosen canvas
size and saves a PNG per page/state, so layout overflow and alignment can be
inspected directly.

    python scripts/mobile_ui_review/render_tutorial_windows.py --size 1280x800
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "nepal_kings"
OUT_DIR = ROOT / "artifacts" / "mobile-ui-review" / "tutorial"


def configure_env(width: int, height: int, ui_scale: str, mobile: bool) -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ["NK_SCREEN_WIDTH"] = str(width)
    os.environ["NK_SCREEN_HEIGHT"] = str(height)
    os.environ["NK_IS_MOBILE"] = "1" if mobile else "0"
    os.environ["NK_UI_SCALE"] = ui_scale
    os.environ.setdefault("SERVER_URL", "http://localhost:5000")
    sys.path.insert(0, str(APP_DIR))
    os.chdir(APP_DIR)


def _save(win, name, width, height):
    import pygame
    win.fill((18, 20, 26))
    return name, win


def render(width: int, height: int, ui_scale: str, mobile: bool) -> None:
    configure_env(width, height, ui_scale, mobile)
    import pygame
    pygame.init()
    surf = pygame.display.set_mode((width, height))

    from game.components.tutorial_window import (
        TutorialWindowDialogue, StarterSuitRevealDialogue)
    from game.components.rewards_reveal_dialogue import RewardsRevealDialogueBox
    from game.components import tutorial_diagrams as td

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"{width}x{height}"

    def shot(name, dialogue, page=None):
        surf.fill((30, 40, 28))  # leafy backdrop so the panel edges are visible
        if page is not None:
            dialogue.page_index = page
        dialogue.draw()
        out = OUT_DIR / f"{name}-{suffix}.png"
        pygame.image.save(surf, str(out))
        print(out)

    welcome = TutorialWindowDialogue(
        surf,
        [
            {'title': 'A Chess of Cards', 'layout': 'text_image_text',
             'lines': ['Welcome, Mira! A 1-vs-1 tactical card game.'],
             'image': lambda: td.card_recipe_examples(),
             'lines_below': ['Figures and spells are card combinations,',
                             'so it all runs on one standard deck.']},
            {'title': 'Offensive & Defensive', 'layout': 'image_top',
             'image': lambda: td.offensive_vs_defensive_diagram(),
             'image_caption': 'Warriors strike; a Tower holds the line.',
             'lines': [
                 'Each figure is built from cards of ONE suit.',
                 'Hearts & Diamonds attack; Clubs & Spades defend.']},
        ],
        title='Welcome to Nepal Kings')
    shot('welcome-1', welcome, page=0)
    shot('welcome-2', welcome, page=1)

    gift = RewardsRevealDialogueBox(
        surf, 'Your Welcome Gift', 'welcome',
        ['You keep a permanent collection of cards.',
         'Grow it by opening booster packs, bought with gold —',
         'you need cards to conquer and defend your kingdom.',
         "Here's a gift to get you started:"],
        [{'kind': 'gold', 'label': '2000 gold', 'description': 'Spend it on booster packs, cosmetics, and shields.'},
         {'kind': 'main_booster', 'label': '2 main boosters', 'description': 'Main cards build your core figures, spells, and tactics.'},
         {'kind': 'side_booster', 'label': '1 side booster', 'description': 'Side cards unlock advanced figures and effects.'}],
        footer_when_done='Added to your collection!',
        hint_text='Click each box to reveal your gift.')
    shot('welcome-gift', gift)

    lands = TutorialWindowDialogue(
        surf,
        [{'title': 'Lands & Your Kingdom', 'layout': 'image_top',
          'image': lambda: td.land_hex_diagram(),
          'image_caption': 'Each land produces gold; higher tiers are richer but tougher.',
          'lines': [
              'Your kingdom is made of lands that produce gold.',
              'Conquer and defend lands to grow it.',
              'First, here is a starter set of cards for attack and defence…']}],
        title='Your Kingdom Awaits')
    shot('welcome-lands', lands)

    for phase, nm in (('off_done', 'reveal-offensive'), ('def_done', 'reveal-defensive')):
        reveal = StarterSuitRevealDialogue(surf, 'Hearts', 'Spades')
        reveal._phase = phase
        shot(nm, reveal)

    battle = TutorialWindowDialogue(
        surf,
        [{'title': 'How a Battle Flows', 'layout': 'text_only',
          'lines': ['1. A prelude spell fires first (yours drew extra cards).',
                    '2. You pick your attacking figure to advance.',
                    '3. Three quick tactic rounds then decide the winner.']},
         {'title': 'Figures Decide Most', 'layout': 'image_top',
          'image': lambda: td.figure_buttons('offensive'),
          'image_caption': 'Your figures vs the defender.',
          'lines': ["Most of a battle is your figures' total power",
                    "against the defender's. Strong figures win."]},
         {'title': 'Tactics Tip the Rounds', 'layout': 'image_top',
          'image': lambda: td.daggers_diagram(),
          'image_caption': 'Combine same-colour Daggers for a bigger hit.',
          'lines': ['Each round, Play a Dagger (a 7-10 card) to add its value.',
                    'Combine same-colour Daggers into one, Block to cancel a',
                    'round, or Call a field figure into it.']}],
        title='How Battles Work')
    shot('battle-1', battle, page=0)
    shot('battle-2', battle, page=1)
    shot('battle-3', battle, page=2)

    kingdom = TutorialWindowDialogue(
        surf,
        [{'title': 'Read Your Map', 'layout': 'image_top',
          'image': lambda: td.map_legend_diagram(),
          'image_caption': 'Tap the glowing target — tuned for your first conquest.',
          'lines': ['Each hex is a land. Yours are marked with a crown,',
                    'rivals hold the rest. A hex shows its tier and gold rate.']},
         {'title': 'The Growth Loop', 'layout': 'image_top',
          'image': lambda: td.growth_loop_diagram(),
          'image_caption': 'Conquer, produce gold, grow — then repeat.',
          'lines': ['A conquered land produces gold — spend it on packs',
                    'and skills, then take the next adjacent land.']},
         {'title': 'Attack & Defend', 'layout': 'image_top',
          'image': lambda: td.attack_defend_diagram(),
          'image_caption': 'Warriors attack; a Tower defends.',
          'lines': ['You conquer rival lands — and rivals can attack yours.',
                    'Station a defence so your lands hold while you are away.']},
         {'title': 'Three Fields', 'layout': 'image_top',
          'image': lambda: td.field_compartments_diagram(),
          'image_caption': 'Castle, Village and Military.',
          'lines': ['Figures stand in one of three fields, and produce',
                    'and require resources to support each other.']}],
        title='Your Kingdom')
    for i in range(4):
        shot(f'kingdom-{i + 1}', kingdom, page=i)

    pygame.quit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default="1280x800")
    parser.add_argument("--ui-scale", default="1.0")
    parser.add_argument("--mobile", action="store_true")
    args = parser.parse_args()
    w, h = args.size.lower().split("x", 1)
    render(int(w), int(h), args.ui_scale, args.mobile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
