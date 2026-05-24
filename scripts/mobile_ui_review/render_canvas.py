#!/usr/bin/env python3
"""Render Pygame screens at the mobile-web internal canvas size.

This complements ``capture_web.py``. The browser harness catches viewport and
web-shell problems; this direct renderer gives deterministic screen-by-screen
PNGs from the same Pygame layout code, without depending on the WASM runtime's
package installer.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "nepal_kings"
OUT_DIR = ROOT / "artifacts" / "mobile-ui-review" / "canvas"

DEFAULT_USER = {
    "id": 1,
    "username": "MobileUser",
    "gold": 1234,
    "booster_packs": 2,
    "booster_packs_side": 1,
    "maps": 3,
}

DUEL_SCREEN_ALIASES = {
    "game": "field",
    "game_field": "field",
    "game_battle_shop": "battle_shop",
    "game_battle": "battle",
}

CONQUER_GAME_ALIASES = {
    "conquer_game": "field",
    "conquer_game_field": "field",
    "conquer_game_battle_shop": "battle_shop",
    "conquer_game_battle": "battle",
}

MAIN_RANKS = {"7", "8", "9", "10", "J", "Q", "K", "A"}
RANK_VALUE = {
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 1,
    "Q": 2,
    "K": 4,
    "A": 3,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
}


def configure_env(width: int, height: int, ui_scale: str) -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ["NK_SCREEN_WIDTH"] = str(width)
    os.environ["NK_SCREEN_HEIGHT"] = str(height)
    os.environ["NK_IS_MOBILE"] = "1"
    os.environ["NK_UI_SCALE"] = ui_scale
    os.environ.setdefault("SERVER_URL", "http://localhost:5000")
    sys.path.insert(0, str(APP_DIR))
    os.chdir(APP_DIR)


def progress_noop(*_args, **_kwargs) -> None:
    return None


def fixture_land(*, owned: bool) -> dict:
    owner = {"id": 1, "username": "MobileUser"} if owned else {
        "id": 2,
        "username": "RivalKing",
    }
    return {
        "id": 42 if not owned else 7,
        "tier": 3,
        "owner": owner,
        "owner_name": owner["username"],
        "ai_name": None,
        "kingdom_name": "Pocket Himalaya",
        "gold_rate": 18,
        "suit_bonus_suit": "Hearts",
        "suit_bonus_value": 2,
        "kingdom_skill_effects": [
            "+10% loot chance from Falcon Sigil",
            "+1 village shield",
        ],
        "kingdom_bonuses": {"loot_chance": 0.10},
    }


def fixture_collection_cards() -> list[dict]:
    cards = []
    cid = 9000
    for suit in ("Hearts", "Diamonds", "Clubs", "Spades"):
        for rank in ("3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"):
            cid += 1
            cards.append({
                "id": cid,
                "suit": suit,
                "rank": rank,
                "free": 2,
                "total": 3,
                "locked": 1,
            })
    return cards


def _find_figure_template(manager, name: str, suit: str):
    candidates = manager.get_figures_by_name(name)
    if not candidates:
        raise RuntimeError(f"Unknown fixture figure: {name}")
    return next((fig for fig in candidates if fig.suit == suit), candidates[0])


def _card_payload(card, role: str, card_id: int, player_id: int | None = None) -> dict:
    return {
        "id": card_id,
        "card_id": card_id,
        "rank": card.rank,
        "suit": card.suit,
        "value": getattr(card, "value", RANK_VALUE.get(card.rank, 0)),
        "role": role,
        "player_id": player_id,
        "in_deck": False,
        "part_of_figure": True,
        "card_type": "main" if card.rank in MAIN_RANKS else "side_card",
        "type": "main" if card.rank in MAIN_RANKS else "side_card",
    }


def _cards_from_template(template, start_card_id: int, player_id: int | None = None):
    specs = []
    roles = []
    ids = []
    details = []
    card_id = start_card_id
    for card in getattr(template, "key_cards", []) or []:
        payload = _card_payload(card, "key", card_id, player_id)
        specs.append({k: payload[k] for k in ("rank", "suit", "value")})
        roles.append("key")
        ids.append(card_id)
        details.append(payload)
        card_id += 1
    for role, card in (
        ("number", getattr(template, "number_card", None)),
        ("upgrade", getattr(template, "upgrade_card", None)),
    ):
        if not card:
            continue
        payload = _card_payload(card, role, card_id, player_id)
        specs.append({k: payload[k] for k in ("rank", "suit", "value")})
        roles.append(role)
        ids.append(card_id)
        details.append(payload)
        card_id += 1
    return specs, roles, ids, details, card_id


def fixture_config_figure(manager, name: str, suit: str, figure_id: int,
                          *, player_id: int = 1, card_start: int = 1000) -> dict:
    template = _find_figure_template(manager, name, suit)
    specs, roles, ids, details, _next = _cards_from_template(
        template, card_start, player_id)
    return {
        "id": figure_id,
        "player_id": player_id,
        "family_name": template.family.name,
        "name": template.name,
        "sub_name": getattr(template, "sub_name", ""),
        "suit": template.suit,
        "field": template.family.field,
        "description": getattr(template, "description", ""),
        "upgrade_family_name": getattr(template, "upgrade_family_name", None),
        "produces": dict(getattr(template, "produces", {}) or {}),
        "requires": dict(getattr(template, "requires", {}) or {}),
        "card_specs": specs,
        "card_roles": roles,
        "card_ids": ids,
        "card_details": details,
        "cards": details,
        "has_deficit": False,
        "cannot_be_blocked": getattr(template, "cannot_be_blocked", False),
        "rest_after_attack": getattr(template, "rest_after_attack", False),
        "checkmate": getattr(template, "checkmate", False),
    }


def fixture_game_figure(manager, name: str, suit: str, figure_id: int,
                        *, player_id: int, card_start: int) -> dict:
    data = fixture_config_figure(
        manager, name, suit, figure_id,
        player_id=player_id, card_start=card_start)
    data["cards"] = data["card_details"]
    return data


def fixture_move(move_id: int, round_index: int, family: str, suit: str,
                 rank: str, value: int | None = None) -> dict:
    value = RANK_VALUE.get(rank, 0) if value is None else value
    return {
        "id": move_id,
        "card_id": move_id + 5000,
        "round_index": round_index,
        "family_name": family,
        "suit": suit,
        "rank": rank,
        "value": value,
        "card_type": "main",
    }


def fixture_hand_card(card_id: int, player_id: int, suit: str, rank: str,
                      *, battle_move: bool = False, side: bool = False) -> dict:
    return {
        "id": card_id,
        "card_id": card_id,
        "game_id": 57,
        "player_id": player_id,
        "suit": suit,
        "rank": rank,
        "value": RANK_VALUE.get(rank, 0),
        "in_deck": False,
        "part_of_figure": False,
        "part_of_battle_move": battle_move,
        "type": "side_card" if side else "main",
    }


def populate_conquer_config(screen) -> None:
    screen._land_id = 42
    screen.state.conquer_land_id = 42
    manager = screen._figure_manager
    figures = [
        fixture_config_figure(manager, "Himalaya King", "Hearts", 101, card_start=1100),
        fixture_config_figure(manager, "Large Rice Farm", "Diamonds", 102, card_start=1120),
        fixture_config_figure(manager, "Djungle Healer", "Hearts", 103, card_start=1140),
        fixture_config_figure(manager, "Gorkha Warriors", "Hearts", 104, card_start=1160),
        fixture_config_figure(manager, "Djungle Archer", "Spades", 105, card_start=1180),
    ]
    screen._land = fixture_land(owned=False)
    screen._config = {
        "figures": figures,
        "battle_moves": [
            fixture_move(201, 0, "Call Military", "Hearts", "A", 3),
            fixture_move(202, 1, "Block", "Spades", "Q", 2),
            fixture_move(203, 2, "Dagger", "Diamonds", "9", 9),
        ],
        "prelude_spell_name": "Blitzkrieg",
        "prelude_spell_card_details": [
            {"suit": "Hearts", "rank": "Q", "value": 2},
            {"suit": "Diamonds", "rank": "Q", "value": 2},
        ],
    }
    screen._collection_cards = fixture_collection_cards()
    screen._cooldown_remaining = 0
    screen._maps_available = 3
    screen._loading = False
    screen._error = None
    screen._layout_built = False
    screen._rebuild_figure_objects()


def populate_defence_config(screen) -> None:
    screen._land_id = 7
    screen.state.defence_land_id = 7
    manager = screen._figure_manager
    figures = [
        fixture_config_figure(manager, "Wall", "Hearts", 301, card_start=2100),
        fixture_config_figure(manager, "Djungle Temple", "Spades", 302, card_start=2120),
        fixture_config_figure(manager, "Large Rice Farm", "Diamonds", 303, card_start=2140),
        fixture_config_figure(manager, "Gorkha Warriors", "Hearts", 304, card_start=2160),
        fixture_config_figure(manager, "Djungle Archer", "Spades", 305, card_start=2180),
    ]
    config = {
        "figures": figures,
        "battle_moves": [
            fixture_move(401, 0, "Block", "Clubs", "Q", 2),
            fixture_move(402, 1, "Call Villager", "Hearts", "J", 1),
            fixture_move(403, 2, "Dagger", "Spades", "10", 10),
        ],
        "prelude_spell_name": "Health Boost",
        "prelude_spell_data": {"target_figure_id": 304},
        "prelude_spell_target_figure_id": 304,
        "prelude_spell_target_figure": {
            "id": 304,
            "name": "Gorkha Warriors",
            "suit": "Hearts",
        },
        "battle_figure_id": 305,
        "battle_figure_id_2": None,
        "counter_spell_name": None,
        "counter_spell_card_ids": None,
        "counter_spell_target_figure_id": None,
        "counter_spell_target_figure": None,
        "auto_gamble": True,
        "auto_gamble_threshold": 8,
        "draft_dirty": True,
    }
    screen._land = fixture_land(owned=True)
    screen._apply_config(config)
    screen._collection_cards = fixture_collection_cards()
    screen._loading = False
    screen._error = None
    screen._layout_built = False
    screen._rebuild_figure_objects()


def make_duel_game(screen, subscreen: str):
    from game.core.game import Game

    player_id = 113
    opponent_id = 114
    active_battle = subscreen == "battle"
    selecting_moves = subscreen == "battle_shop"
    game_dict = {
        "id": 57,
        "state": "open",
        "mode": "duel",
        "date": "2026-05-20T12:00:00",
        "stake": 35,
        "game_limit": 70,
        "players": [
            {
                "id": player_id,
                "user_id": 1,
                "username": "MobileUser",
                "turns_left": 2,
                "points": 34,
                "is_online": True,
            },
            {
                "id": opponent_id,
                "user_id": 2,
                "username": "[AI] Strategos",
                "turns_left": 1,
                "points": 28,
                "is_online": True,
            },
        ],
        "main_cards": [
            fixture_hand_card(601, player_id, "Hearts", "7"),
            fixture_hand_card(602, player_id, "Diamonds", "9"),
            fixture_hand_card(603, player_id, "Clubs", "Q", battle_move=selecting_moves),
            fixture_hand_card(604, player_id, "Spades", "A"),
            fixture_hand_card(605, player_id, "Hearts", "10"),
            fixture_hand_card(606, opponent_id, "Clubs", "8"),
            fixture_hand_card(607, opponent_id, "Spades", "K"),
            fixture_hand_card(608, opponent_id, "Diamonds", "7"),
        ],
        "side_cards": [
            fixture_hand_card(701, player_id, "Hearts", "3", side=True),
            fixture_hand_card(702, player_id, "Clubs", "5", side=True),
            fixture_hand_card(703, opponent_id, "Diamonds", "4", side=True),
        ],
        "current_round": 4,
        "invader_player_id": player_id,
        "turn_player_id": player_id,
        "ceasefire_active": False,
        "ceasefire_start_turn": None,
        "pending_spell_id": None,
        "battle_modifier": [{"type": "Blitzkrieg"}] if active_battle else None,
        "waiting_for_counter_player_id": None,
        "advancing_figure_id": 501 if active_battle else None,
        "advancing_figure_id_2": None,
        "advancing_player_id": player_id if active_battle else None,
        "defending_figure_id": 601 if active_battle else None,
        "defending_figure_id_2": None,
        "battle_decisions": {"113": "battle", "114": "battle"} if active_battle else None,
        "battle_confirmed": active_battle or selecting_moves,
        "battle_moves_confirmed": {"113": True, "114": True} if active_battle else {},
        "fold_outcome": None,
        "fold_winner_id": None,
        "battle_round": 1 if active_battle else 0,
        "battle_turn_player_id": player_id if active_battle else None,
        "battle_skipped_rounds": {},
        "post_battle_drawn_cards": None,
        "last_battle_result": None,
        "winner_player_id": None,
        "finished_at": None,
        "auto_loss_reason": None,
        "auto_loss_detail": None,
        "resting_figure_ids": [],
    }
    game = Game(game_dict, dict(DEFAULT_USER), lightweight=True)
    game.turn = True
    game.battle_moves_phase = selecting_moves
    game.in_battle_phase = active_battle
    game.battle_turns_left = 2 if active_battle else 3
    manager = screen.figure_manager
    game.cached_figures_data = {
        player_id: [
            fixture_game_figure(manager, "Gorkha Warriors", "Hearts", 501,
                                player_id=player_id, card_start=3100),
            fixture_game_figure(manager, "Djungle Healer", "Hearts", 502,
                                player_id=player_id, card_start=3120),
            fixture_game_figure(manager, "Large Rice Farm", "Diamonds", 503,
                                player_id=player_id, card_start=3140),
            fixture_game_figure(manager, "Himalaya King", "Hearts", 504,
                                player_id=player_id, card_start=3160),
        ],
        opponent_id: [
            fixture_game_figure(manager, "Wall", "Clubs", 601,
                                player_id=opponent_id, card_start=4100),
            fixture_game_figure(manager, "Djungle Archer", "Spades", 602,
                                player_id=opponent_id, card_start=4120),
            fixture_game_figure(manager, "Small Yack Farm", "Diamonds", 603,
                                player_id=opponent_id, card_start=4140),
        ],
    }
    game._figures_data_version = 1
    game.log_entries = [
        {"round": 4, "turn": 1, "message": "MobileUser advanced Gorkha Warriors"},
    ]
    game.chat_messages = [
        {"username": "[AI] Strategos", "message": "The pass is guarded."},
    ]
    return game


def populate_duel_game(client, screen, subscreen: str) -> None:
    game = make_duel_game(screen, subscreen)
    client.state.user_dict = dict(DEFAULT_USER)
    client.state.game = game
    client.state.screen = "game"
    client.state.subscreen = subscreen
    screen.state.game = game
    screen.main_hand.state = client.state
    screen.side_hand.state = client.state
    for hand in (screen.main_hand, screen.side_hand):
        for button in getattr(hand, "buttons", []):
            button.state = client.state
    screen.main_hand.update(game)
    screen.side_hand.update(game)
    for subscreen_obj in screen.subscreens.values():
        if hasattr(subscreen_obj, "game"):
            subscreen_obj.game = game
    field = screen.subscreens.get("field")
    if field is not None:
        field.update(game)
    shop = screen.subscreens.get("battle_shop")
    if shop is not None:
        shop.game = game
        if hasattr(shop.card_source, "game"):
            shop.card_source.game = game
        shop.bought_moves = [
            fixture_move(801, 0, "Call Military", "Hearts", "A", 3),
            fixture_move(802, 1, "Block", "Clubs", "Q", 2),
        ] if subscreen == "battle_shop" else []
        shop._loaded_game_key = (game.game_id, game.player_id)
        shop._loaded_bought_moves_key = shop._bought_moves_cache_key(game)
        shop.ready_button.disabled = False
        shop.ready_button.active = True
    battle = screen.subscreens.get("battle")
    if battle is not None:
        battle.game = game
        for attr, default in (
            ("_card_picker_active", False),
            ("_card_picker_cards", []),
            ("_card_picker_selected", None),
            ("_card_picker_hovered", None),
            ("_card_picker_callback", None),
            ("_card_picker_title", ""),
            ("_card_picker_confirm_btn", None),
            ("_card_picker_box_rect", None),
        ):
            if not hasattr(battle, attr):
                setattr(battle, attr, default)
        battle._resources_data = game.calculate_resources(
            battle.figure_manager.families, is_opponent=False)
        battle._opponent_resources_data = game.calculate_resources(
            battle.figure_manager.families, is_opponent=True)
        battle.player_moves = [
            fixture_move(811, 0, "Call Military", "Hearts", "A", 3),
            fixture_move(812, 1, "Dagger", "Diamonds", "9", 9),
            fixture_move(813, 2, "Block", "Spades", "Q", 2),
        ]
        battle.opponent_moves = [
            fixture_move(821, 0, "Block", "Clubs", "Q", 2),
            fixture_move(822, 1, "Dagger", "Spades", "8", 8),
            fixture_move(823, 2, "Call Villager", "Hearts", "J", 1),
        ]
        battle.player_played = [battle.player_moves[0], None, None]
        battle.opponent_played = [battle.opponent_moves[0], None, None]
        battle.current_round = 1
        battle.is_player_turn = True
        battle.player_is_invader = True
        battle._loaded_game_key = (game.game_id, game.player_id)
        battle._load_battle_figures()
    for element in screen.display_elements:
        try:
            from game.components.info_scroll import InfoScroll
            if isinstance(element, InfoScroll):
                element.update(game, families=screen.figure_manager.families)
            else:
                element.update(game)
        except Exception:
            traceback.print_exc(limit=2)


def populate_conquer_game(client, subscreen: str):
    client._init_perf_conquer_fixture(progress_noop)
    client.state.screen = "conquer_game"
    client.state.subscreen = subscreen
    screen = client.screens["conquer_game"]
    game = client.state.game
    if game is not None:
        game.turn = True
        if subscreen == "battle_shop":
            game.battle_confirmed = True
            game.battle_moves_phase = True
            game.battle_turn_player_id = None
        elif subscreen == "battle":
            game.battle_confirmed = True
            game.battle_moves_phase = False
            game.in_battle_phase = True
            game.battle_turn_player_id = game.player_id
            game.battle_round = 1
        for subscreen_obj in screen.subscreens.values():
            if hasattr(subscreen_obj, "game"):
                subscreen_obj.game = game
        if subscreen == "battle_shop":
            shop = screen.subscreens.get("battle_shop")
            if shop is not None:
                shop.bought_moves = [
                    fixture_move(901, 0, "Call Military", "Hearts", "A", 3),
                    fixture_move(902, 1, "Block", "Clubs", "Q", 2),
                    fixture_move(903, 2, "Dagger", "Diamonds", "9", 9),
                ]
                shop._loaded_game_key = (game.game_id, game.player_id)
                shop._loaded_bought_moves_key = shop._bought_moves_cache_key(game)
        if subscreen == "battle":
            battle = screen.subscreens.get("battle")
            if battle is not None:
                battle.game = game
                for attr, default in (
                    ("_card_picker_active", False),
                    ("_card_picker_cards", []),
                    ("_card_picker_selected", None),
                    ("_card_picker_hovered", None),
                    ("_card_picker_callback", None),
                    ("_card_picker_title", ""),
                    ("_card_picker_confirm_btn", None),
                    ("_card_picker_box_rect", None),
                ):
                    if not hasattr(battle, attr):
                        setattr(battle, attr, default)
                battle._resources_data = game.calculate_resources(
                    battle.figure_manager.families, is_opponent=False)
                battle._opponent_resources_data = game.calculate_resources(
                    battle.figure_manager.families, is_opponent=True)
                battle.player_moves = [
                    fixture_move(911, 0, "Call Military", "Hearts", "A", 3),
                    fixture_move(912, 1, "Dagger", "Diamonds", "9", 9),
                    fixture_move(913, 2, "Block", "Spades", "Q", 2),
                ]
                battle.opponent_moves = [
                    fixture_move(921, 0, "Block", "Clubs", "Q", 2),
                    fixture_move(922, 1, "Dagger", "Spades", "8", 8),
                    fixture_move(923, 2, "Call Villager", "Hearts", "J", 1),
                ]
                battle.player_played = [battle.player_moves[0], None, None]
                battle.opponent_played = [battle.opponent_moves[0], None, None]
                battle.current_round = 1
                battle.is_player_turn = True
                battle.player_is_invader = True
                battle._loaded_game_key = (game.game_id, game.player_id)
                battle._load_battle_figures()
    return screen


def prepare_screen(client, screen_name: str):
    if screen_name in CONQUER_GAME_ALIASES:
        return populate_conquer_game(client, CONQUER_GAME_ALIASES[screen_name])

    if screen_name in DUEL_SCREEN_ALIASES:
        screen = client.screens["game"]
        populate_duel_game(client, screen, DUEL_SCREEN_ALIASES[screen_name])
        return screen

    screen = client.screens.get(screen_name)
    if screen is None:
        return None
    if screen_name == "conquer":
        populate_conquer_config(screen)
    elif screen_name == "defence":
        populate_defence_config(screen)
    return screen


def render_screens(width: int, height: int, ui_scale: str, screens: list[str]) -> int:
    configure_env(width, height, ui_scale)
    import pygame
    from nepal_kings import Client

    pygame.mouse.set_cursor = lambda *args, **kwargs: None

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = Client()
    client.state.user_dict = dict(DEFAULT_USER)
    client.state._last_seen_at = None
    client.state.badge_new_games = 2
    client.state.badge_new_challenges = 1

    failures = 0
    for screen_name in screens:
        if screen_name not in (*client.screens.keys(), *DUEL_SCREEN_ALIASES.keys(), *CONQUER_GAME_ALIASES.keys()):
            print(f"skip {screen_name}: screen not loaded")
            failures += 1
            continue
        try:
            if screen_name not in DUEL_SCREEN_ALIASES and screen_name not in CONQUER_GAME_ALIASES:
                client.state.screen = screen_name
            screen = client.screens.get(screen_name)
            if hasattr(screen, "on_enter"):
                try:
                    screen.on_enter()
                except Exception:
                    # Capture the static layout even when data fetching fails.
                    traceback.print_exc(limit=2)
            screen = prepare_screen(client, screen_name)
            if screen is None:
                print(f"skip {screen_name}: screen not loaded")
                failures += 1
                continue
            screen.render()
            pygame.display.flip()
            out = OUT_DIR / f"{screen_name}-{width}x{height}.png"
            pygame.image.save(pygame.display.get_surface(), str(out))
            print(out)
        except Exception:
            failures += 1
            print(f"failed {screen_name}")
            traceback.print_exc()
    pygame.quit()
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default="854x480")
    parser.add_argument("--ui-scale", default="1.6")
    parser.add_argument(
        "--screens",
        default=(
            "login,game_menu,duel_menu,new_game,load_game,rankings,"
            "settings,kingdom,kingdom_config,conquer,defence,collection,"
            "game_field,game_battle_shop,game_battle,"
            "conquer_game_field,conquer_game_battle_shop,conquer_game_battle"
        ),
    )
    args = parser.parse_args()
    width_s, height_s = args.size.lower().split("x", 1)
    screens = [s.strip() for s in args.screens.split(",") if s.strip()]
    return render_screens(int(width_s), int(height_s), args.ui_scale, screens)


if __name__ == "__main__":
    raise SystemExit(main())
