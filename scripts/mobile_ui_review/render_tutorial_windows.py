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
            {'title': 'Your Path to the Crown', 'layout': 'image_top',
             'image': lambda: td.kingdom_journey_diagram(),
             'image_caption': 'Cards build figures, figures take lands, lands win the crown.',
             'lines': ['Welcome, Mira! Your goal: become King of Nepal.',
                       'Turn your cards into figures, conquer lands for gold,',
                       'and grow your kingdom until the crown is yours.']},
            {'title': 'Cards Become Recipes', 'layout': 'text_image_text',
             'lines': ['It all starts with your cards — each one is a recipe.'],
             'image': lambda: td.card_recipe_examples(),
             'lines_below': ['Combine same-suit cards into figures; turn single',
                             'cards into spells and battle tactics.',
                             'You build them by hand from your own collection.']},
            {'title': 'Skills Follow the Suit', 'layout': 'image_top',
             'image': lambda: td.offensive_vs_defensive_diagram(),
             'image_caption': 'Attack skills push forward; defence skills hold the line.',
             'lines': [
                 'Every figure carries skills, and its suit shapes them.',
                 'Hearts & Diamonds bring offensive skills to conquer;',
                 'Clubs & Spades bring defensive skills to hold your lands.']},
        ],
        title='Welcome to Nepal Kings')
    shot('welcome-1', welcome, page=0)
    shot('welcome-2', welcome, page=1)
    shot('welcome-3', welcome, page=2)

    gift = RewardsRevealDialogueBox(
        surf, 'Your Welcome Gift', 'welcome',
        ['You keep a permanent collection of cards.',
         'Your first attack is prepared already.',
         'Packs, maps and gold grow your options after each conquest.',
         "Here's a gift to claim before you begin:"],
        [{'kind': 'gold', 'label': '2000 gold', 'description': 'Spend it on booster packs, cosmetics, and shields.'},
         {'kind': 'main_booster', 'label': '2 main boosters', 'description': 'Main cards build your core figures, spells, and tactics.'},
         {'kind': 'side_booster', 'label': '1 side booster', 'description': 'Side cards unlock advanced figures and effects.'}],
        footer_when_done='Added to your collection!',
        hint_text='Click each box to reveal your gift.')
    shot('welcome-gift', gift)

    reveal = StarterSuitRevealDialogue(surf, 'Hearts')
    reveal._phase = 'done'
    shot('reveal-starter', reveal)

    battle = TutorialWindowDialogue(
        surf,
        [{'title': 'How a Battle Flows', 'layout': 'image_top',
          'image': lambda: td.starter_tactics_diagram(),
          'image_caption': 'Your three tactics: Call King, Call Villager, Block.',
          'lines': ['A battle runs in three beats: your prelude fires, your figures',
                    'set the score, then three tactic rounds let you swing it.',
                    'Each round, Play a tactic — or Gamble it for new cards.',
                    "Call King or Call Villager adds that figure's power; Block cancels the round."]}],
        title='How Battles Work')
    shot('battle-1', battle, page=0)

    kingdom = TutorialWindowDialogue(
        surf,
        [{'title': 'Read Your Map', 'layout': 'image_top',
          'image': lambda: td.kingdom_map_diagram(),
          'image_caption': 'Conquer a neighbour to grow your kingdom.',
          'lines': ['Your lands form a kingdom; rivals hold the rest.',
                    'Conquer a neighbouring land to expand, one hex at a time.']},
         ],
        title='Your Kingdom')
    shot('kingdom-1', kingdom, page=0)

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
