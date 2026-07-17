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
    from game.tutorial_content import (
        build_attack_intro_pages,
        collection_basics_pages,
        collection_growth_pages,
        collection_growth_recap_pages,
        conquer_battle_intro_pages,
        defend_land_intro_pages,
        duel_intro_pages,
        kingdom_management_pages,
        kingdom_overview_pages,
        loot_risk_pages,
        starter_present_pages,
        welcome_pages,
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

    collection_growth = TutorialWindowDialogue(
        surf, collection_growth_pages(), title='Grow Your Collection')
    for index in range(len(collection_growth_pages())):
        shot(
            f'lesson-collection-{index + 1}',
            collection_growth,
            page=index,
        )
    collection_growth_recap = TutorialWindowDialogue(
        surf,
        collection_growth_recap_pages(),
        title='Grow Your Collection',
    )
    shot('lesson-collection-recap', collection_growth_recap, page=0)

    build_attack = TutorialWindowDialogue(
        surf, build_attack_intro_pages(), title='Build Your Own Attack')
    shot('lesson-build-attack', build_attack, page=0)

    run_kingdom = TutorialWindowDialogue(
        surf, kingdom_management_pages(), title='Run Your Kingdom')
    shot('lesson-run-kingdom', run_kingdom, page=0)

    defend_land = TutorialWindowDialogue(
        surf, defend_land_intro_pages(), title='Defend Your Land')
    shot('lesson-defend-land', defend_land, page=0)

    duel = TutorialWindowDialogue(
        surf, duel_intro_pages(), title='Duel Basics')
    for index in range(len(duel_intro_pages())):
        shot(f'duel-{index + 1}', duel, page=index)

    battle = TutorialWindowDialogue(
        surf,
        conquer_battle_intro_pages(),
        title='How Battles Work')
    for index in range(len(conquer_battle_intro_pages())):
        shot(f'battle-{index + 1}', battle, page=index)

    kingdom = TutorialWindowDialogue(
        surf,
        kingdom_overview_pages(),
        title='Your Kingdom',
        presentation='map_sidecar' if mobile else 'modal')
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
