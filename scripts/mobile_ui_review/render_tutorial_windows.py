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
    from game.tutorial_content import (
        collection_basics_pages,
        conquer_battle_intro_pages,
        duel_intro_pages,
        kingdom_overview_pages,
        loot_risk_pages,
        starter_present_pages,
        welcome_pages,
        welcome_gift_lines,
        reward_reveal_items,
    )

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
        welcome_pages('Mira', screen_height=height),
        title='Welcome to Nepal Kings')
    shot('welcome-1', welcome, page=0)

    gift = RewardsRevealDialogueBox(
        surf, 'Your Welcome Gift', 'welcome',
        welcome_gift_lines(),
        reward_reveal_items({
            'gold': 2000, 'booster_packs': 2,
            'booster_packs_side': 1, 'maps': 0,
        }),
        footer_when_done='Added to your collection!',
        hint_text='Click each box to reveal your gift.')
    shot('welcome-gift', gift)

    reveal = StarterSuitRevealDialogue(surf, 'Hearts')
    reveal._phase = 'done'
    shot('reveal-starter', reveal)

    starter = TutorialWindowDialogue(
        surf, starter_present_pages(), title='Starter Cards')
    shot('starter-present', starter, page=0)

    collection = TutorialWindowDialogue(
        surf, collection_basics_pages(), title='Your Collection')
    for index in range(len(collection_basics_pages())):
        shot(f'collection-{index + 1}', collection, page=index)

    duel = TutorialWindowDialogue(
        surf, duel_intro_pages(), title='Duel Tutorial')
    for index in range(len(duel_intro_pages())):
        shot(f'duel-{index + 1}', duel, page=index)

    battle = TutorialWindowDialogue(
        surf,
        conquer_battle_intro_pages(),
        title='How Battles Work')
    shot('battle-1', battle, page=0)
    shot('battle-2', battle, page=1)

    kingdom = TutorialWindowDialogue(
        surf,
        kingdom_overview_pages(),
        title='Your Kingdom')
    shot('kingdom-1', kingdom, page=0)

    loot = TutorialWindowDialogue(
        surf, loot_risk_pages(), title='Conquer Loot')
    shot('loot-risk', loot, page=0)

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
