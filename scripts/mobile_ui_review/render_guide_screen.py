#!/usr/bin/env python3
"""Render the Guide lesson catalogue and Goals tab for visual review.

    python scripts/mobile_ui_review/render_guide_screen.py --size 1280x800
    python scripts/mobile_ui_review/render_guide_screen.py \
        --size 854x480 --ui-scale 1.6 --mobile
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "nepal_kings"
OUT_DIR = ROOT / "artifacts" / "mobile-ui-review" / "guide"


def configure_env(
        width: int, height: int, ui_scale: str, mobile: bool) -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ["NK_SCREEN_WIDTH"] = str(width)
    os.environ["NK_SCREEN_HEIGHT"] = str(height)
    os.environ["NK_IS_MOBILE"] = "1" if mobile else "0"
    os.environ["NK_UI_SCALE"] = ui_scale
    os.environ.setdefault("SERVER_URL", "http://localhost:5000")
    sys.path.insert(0, str(APP_DIR))
    os.chdir(APP_DIR)


def onboarding_fixture() -> dict:
    lesson_specs = (
        (
            "grow_collection",
            "Grow Your Collection",
            "Open both pack types and learn how spare copies become useful.",
            {"gold": 250, "booster_packs": 2, "booster_packs_side": 1},
            "2/5",
            True,
        ),
        (
            "build_attack",
            "Build Your Own Attack",
            "Build figures, choose tactics and a prelude, then conquer land.",
            {"gold": 250, "maps": 2},
            "0/5",
            False,
        ),
        (
            "run_kingdom",
            "Run Your Kingdom",
            "Manage production, skills, protection, loot, and appearance.",
            {"gold": 500, "maps": 1},
            "5/5",
            False,
        ),
        (
            "defend_land",
            "Defend Your Land",
            "Prepare figures, tactics, and a response for your defence.",
            {"gold": 250, "booster_packs": 2, "booster_packs_side": 1},
            "0/5",
            False,
        ),
        (
            "duel_basics",
            "Duel Basics",
            "Play a friendly duel and learn its complete round rhythm.",
            {"gold": 500, "booster_packs": 3, "booster_packs_side": 2},
            "0/10",
            False,
        ),
    )
    lessons = []
    for lesson_id, title, description, reward, progress, active in lesson_specs:
        completed = lesson_id == "run_kingdom"
        lessons.append({
            "id": lesson_id,
            "title": title,
            "description": description,
            "group": "lessons",
            "lesson": True,
            "progress_label": progress,
            "total_steps": int(progress.split("/")[1]),
            "reward": reward,
            "reward_id": f"finish_{lesson_id}_lesson",
            "completed": completed,
            "claimed": completed,
            "claimable": False,
            "locked": False,
            "active": active,
            "started": active or completed,
            "dismissed": False,
        })
    return {
        "welcome_seen": True,
        "starter_set_granted": True,
        "completed_steps": ["finish_tutorial", "finish_run_kingdom_lesson"],
        "claimed_rewards": ["finish_tutorial", "finish_run_kingdom_lesson"],
        "next_action": None,
        "active_lesson": "grow_collection",
        "onboarding_skipped": False,
        "core_steps": [
            {
                "id": "finish_first_conquer_battle",
                "title": "Conquer your first land",
                "group": "first_journey",
                "completed": True,
                "claimed": True,
                "claimable": False,
                "reward": {},
            },
            {
                "id": "finish_tutorial",
                "title": "Finish the kingdom tour",
                "group": "first_journey",
                "completed": True,
                "claimed": True,
                "claimable": False,
                "reward": {
                    "gold": 2000,
                    "booster_packs": 7,
                    "booster_packs_side": 3,
                    "maps": 4,
                },
            },
        ],
        "lessons": lessons,
        "daily_quest": {
            "id": "daily_quest",
            "title": "Finish one duel",
            "description": "Play one full duel today.",
            "progress": 1,
            "target": 1,
            "completed": True,
            "claimed": False,
            "claimable": True,
            "reward": {"gold": 60},
            "resets_at": "2026-07-17T00:00:00+00:00",
        },
        "early_goals": [
            {
                "id": "win_first_duel",
                "title": "Win your first duel",
                "description": "Win any finished duel.",
                "completed": True,
                "claimed": False,
                "claimable": True,
                "reward": {"gold": 75},
            },
            {
                "id": "win_5_duels",
                "title": "Win 5 duels",
                "description": "Build a winning rhythm in duel mode.",
                "completed": False,
                "claimed": False,
                "claimable": False,
                "reward": {"booster_packs": 1},
            },
            {
                "id": "conquer_5_lands",
                "title": "Conquer 5 lands",
                "description": "Grow your kingdom across the map.",
                "completed": False,
                "claimed": False,
                "claimable": False,
                "reward": {"maps": 2},
            },
        ],
        "pending_reward_count": 2,
    }


def render(width: int, height: int, ui_scale: str, mobile: bool) -> None:
    configure_env(width, height, ui_scale, mobile)
    import pygame

    pygame.init()
    window = pygame.display.set_mode((width, height))

    from game.screens._menu_base import MenuScreenMixin

    class GuidePreview(MenuScreenMixin):
        pass

    state = SimpleNamespace(
        user_dict={
            "id": 1,
            "username": "GuidePreview",
            "gold": 2450,
            "booster_packs": 2,
            "booster_packs_side": 1,
            "maps": 3,
            "onboarding": onboarding_fixture(),
        },
        set_msg=lambda _message: None,
        screen="game_menu",
    )
    preview = object.__new__(GuidePreview)
    preview.window = window
    preview.state = state
    preview._init_menu_chrome()
    preview._onboarding_guide_open = True

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"{width}x{height}"

    def shot(tab: str, name: str, scroll_to_bottom: bool = False) -> None:
        preview._onboarding_guide_tab = tab
        preview._reset_onboarding_guide_scroll()
        window.blit(preview._bg, (0, 0))
        preview._draw_onboarding_guide()
        if scroll_to_bottom:
            preview._onboarding_guide_scroll = (
                preview._max_onboarding_guide_scroll())
            window.blit(preview._bg, (0, 0))
            preview._draw_onboarding_guide()
        output = OUT_DIR / f"{name}-{suffix}.png"
        pygame.image.save(window, str(output))
        print(output)

    shot("journey", "journey-top")
    shot("journey", "journey-bottom", scroll_to_bottom=True)
    shot("goals", "goals")
    pygame.quit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default="1280x800")
    parser.add_argument("--ui-scale", default="1.0")
    parser.add_argument("--mobile", action="store_true")
    args = parser.parse_args()
    width, height = args.size.lower().split("x", 1)
    render(int(width), int(height), args.ui_scale, args.mobile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
