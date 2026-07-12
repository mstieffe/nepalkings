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
    "conquer_game_battle_dagger": "battle_dagger",
    "conquer_game_battle_collapsed": "battle_collapsed",
    "conquer_game_battle_intro_1": "battle_intro_1",
    "conquer_game_battle_intro_2": "battle_intro_2",
}

KINGDOM_SCREEN_ALIASES = {
    "kingdom": "alerts",
    "kingdom_alerts": "alerts",
    "kingdom_history": "history",
    "kingdom_messages": "messages",
}

KINGDOM_CONFIG_ALIASES = {
    "kingdom_config": "top",
    "kingdom_config_shield": "shield",
}

BOOSTER_REVEAL_ALIASES = {
    "collection_booster_reveal_special": "special",
    "collection_booster_reveal_hidden": "hidden",
    "collection_booster_reveal_bulk": "bulk",
}

COLLECTION_SCREEN_ALIASES = {
    "collection": "default",
    "collection_profile": "profile",
    "collection_locked": "locked",
    "collection_loading": "loading",
    "collection_error": "error",
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


def fixture_kingdom_style() -> dict:
    return {
        "badge_key": "badge_plain",
        "border_key": "border_simple_gold",
        "surface_key": "surface_plain",
        "color_key": "color_royal_gold",
        "sigil_key": "sigil_mountain",
    }


def fixture_map_land(col: int, row: int, land_id: int, *, owned: bool,
                     kingdom_id: int | None = None,
                     kingdom_name: str | None = None) -> dict:
    owner = {"id": 1, "user_id": 1, "username": "MobileUser"} if owned else {
        "id": 2,
        "user_id": 2,
        "username": "RivalKing",
    }
    return {
        "id": land_id,
        "col": col,
        "row": row,
        "tier": 3 if owned else 2,
        "gold_rate": 18 if owned else 9,
        "suit_bonus_suit": "Hearts" if owned else "Spades",
        "suit_bonus_value": 2 if owned else 1,
        "owner": owner,
        "owner_style": fixture_kingdom_style() if owned else {},
        "is_mine": owned,
        "defence_incomplete": False,
        "kingdom_component_id": 401 if owned else 902,
        "kingdom_component_size": 4 if owned else 2,
        "kingdom_level": 7 if owned else 3,
        "kingdom_tier_name": "Mountain Realm" if owned else "Border Duchy",
        "kingdom_bonuses": {"gold_production": 0.10} if owned else {},
        "kingdom_name": kingdom_name or ("Pocket Himalaya" if owned else "Rival Ridge"),
        "kingdom_id": kingdom_id,
        "kingdom_shield_remaining": 0,
        "kingdom_shield_reason": None,
        "kingdom_is_shielded": False,
        "conquer_cooldown_remaining": 0,
    }


def humanize_key(key: str) -> str:
    return " ".join(part.capitalize() for part in str(key).split("_") if part)


def catalog_row(cosmetic_type: str, key: str, entry: dict,
                *, index: int, default_key: str) -> dict:
    row = dict(entry or {})
    row["type"] = cosmetic_type
    row["name"] = row.get("name") or humanize_key(
        key.removeprefix(f"{cosmetic_type}_"))
    row["rarity"] = row.get("rarity") or ("default" if key == default_key else "common")
    if key == default_key:
        row["price_gold"] = 0
    elif cosmetic_type == "sigil" and index % 2:
        row["price_gold"] = None
        row["unlock_kind"] = "win_conquer_battles"
        row["unlock_value"] = 10 + index
    else:
        row["price_gold"] = 120 + index * 75
    return row


def fixture_cosmetic_catalog() -> dict:
    from config import settings

    sources = [
        ("badge", settings.HEX_BADGE_STYLES,
         getattr(settings, "HEX_BADGE_DEFAULT_KEY", "badge_plain")),
        ("border", settings.HEX_BORDER_SKINS, "border_simple_gold"),
        ("surface", settings.HEX_SURFACE_SKINS, "surface_plain"),
        ("color", settings.KINGDOM_COLOR_PALETTE, settings.KINGDOM_COLOR_DEFAULT_KEY),
        ("sigil", settings.KINGDOM_SIGIL_STYLES, settings.KINGDOM_SIGIL_DEFAULT_KEY),
    ]
    catalog: dict[str, dict] = {}
    for cosmetic_type, mapping, default_key in sources:
        for index, (key, entry) in enumerate(mapping.items()):
            catalog[key] = catalog_row(
                cosmetic_type, key, entry, index=index, default_key=default_key)
    return catalog


def fixture_kingdom_config_payload() -> dict:
    style = fixture_kingdom_style()
    return {
        "id": 4,
        "name": "Pocket Himalaya",
        "style": style,
        "land_ids": [7, 8, 9, 10],
        "lands_count": 4,
        "unlocked_cosmetics": [
            "badge_plain",
            "badge_parchment_scroll",
            "border_simple_gold",
            "border_royal_blue",
            "surface_plain",
            "surface_parchment",
            "color_royal_gold",
            "color_crimson",
            "sigil_none",
            "sigil_mountain",
        ],
        "shield_remaining": 0,
        "level": 7,
        "level_max": 50,
        "experience": 640,
        "xp_into_level": 120,
        "xp_for_next_level": 250,
        "skill_points_total": 4,
        "skill_points_spent": 2,
        "skill_points_available": 2,
        "raw_gold_rate": 18.0,
        "effective_gold_rate": 21.0,
        "gold_rate_per_hour": 21.0,
        "pending_gold": 37.0,
        "vault_cap": 80,
        "vault_full": False,
        "production_items": [
            {
                "key": "gold",
                "kind": "gold",
                "label": "Gold Vault",
                "skill_key": "gold_vault",
                "pending": 37.0,
                "capacity": 80,
                "progress_ratio": 0.46,
                "collectable": True,
            },
            {
                "key": "main_booster",
                "kind": "booster",
                "label": "Main Booster Pack",
                "skill_key": "main_booster_production",
                "enabled": True,
                "pending": 1,
                "capacity": 1,
                "full": True,
                "progress_ratio": 1.0,
            },
            {
                "key": "side_booster",
                "kind": "booster",
                "label": "Side Booster Pack",
                "skill_key": "side_booster_production",
                "enabled": True,
                "pending": 0,
                "capacity": 1,
                "seconds_remaining": 4800,
                "progress_ratio": 0.58,
            },
            {
                "key": "map",
                "kind": "map",
                "label": "Map",
                "skill_key": "map_production",
                "enabled": True,
                "pending": 0,
                "capacity": 1,
                "seconds_remaining": 9400,
                "progress_ratio": 0.34,
            },
        ],
        "skills": {
            "gold_production": {
                "name": "Gold Production",
                "description": "Boosts hourly gold from connected lands.",
                "level": 1,
                "max_level": 5,
                "next_cost": 1,
                "increments": {"1": 0.03, "2": 0.06},
            },
            "gold_vault": {
                "name": "Gold Vault",
                "description": "Raises the stored gold capacity.",
                "level": 1,
                "max_level": 5,
                "next_cost": 1,
                "effect_values": [100, 250, 500, 1000, 2000],
            },
            "main_booster_production": {
                "name": "Main Booster Production",
                "description": "Produces main booster packs over time.",
                "level": 1,
                "max_level": 5,
                "next_cost": 2,
                "effect_values": [96, 48, 24, 12, 6],
            },
            "side_booster_production": {
                "name": "Side Booster Production",
                "description": "Produces side booster packs over time.",
                "level": 1,
                "max_level": 5,
                "next_cost": 2,
                "effect_values": [96, 48, 24, 12, 6],
            },
        },
        "loot_inbox": {
            "gained": [{
                "cards": [
                    {"rank": "A", "suit": "Hearts"},
                    {"rank": "10", "suit": "Clubs"},
                ],
            }],
            "lost": [{
                "cards": [
                    {"rank": "7", "suit": "Spades"},
                ],
            }],
            "gained_card_count": 2,
            "lost_card_count": 1,
        },
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
    requested_subscreen = subscreen
    battle_variants = {
        "battle_collapsed",
        "battle_dagger",
        "battle_intro_1",
        "battle_intro_2",
    }
    subscreen = "battle" if requested_subscreen in battle_variants else subscreen
    client._init_perf_conquer_fixture(progress_noop)
    client.state.screen = "conquer_game"
    client.state.subscreen = subscreen
    screen = client.screens["conquer_game"]
    game = client.state.game
    if game is not None:
        game.turn = True
        if subscreen == "battle_shop":
            # The current tactics-hand conquer flow routes away from the
            # legacy battle shop. Keep this screenshot pointed at a real
            # populated shop by fixture-marking it as an older battle-move game.
            game.conquer_move_model = "battle_move"
            game.battle_confirmed = True
            game.battle_moves_phase = True
            game.battle_turn_player_id = None
            game.in_battle_phase = False
            game.battle_round = 0
        elif subscreen == "battle":
            game.battle_confirmed = True
            game.battle_moves_phase = False
            game.conquer_move_model = "tactics_hand"
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
        if requested_subscreen == "battle_collapsed":
            screen._conquer_timeline_hover_open = False
            screen._conquer_timeline_last_layout_mode = "battle"
        if requested_subscreen == "battle_dagger":
            rail = getattr(screen, "_tactics_rail", None)
            if rail is not None:
                rail._expanded_groups.add("Dagger")
                for move in rail._hand_moves():
                    if move.get("family_name") == "Dagger" and not move.get("card_id_b"):
                        rail._selected_id = move.get("id")
                        break
        if requested_subscreen in {"battle_intro_1", "battle_intro_2"}:
            onboarding = client.state.user_dict.setdefault("onboarding", {})
            onboarding.setdefault("menu_hints_seen", [])
            onboarding.setdefault("completed_steps", [])
            screen._battle_intro_dialogue = None
            screen._maybe_show_battle_intro_window()
            if screen._battle_intro_dialogue is not None:
                screen._battle_intro_dialogue.page_index = (
                    1 if requested_subscreen == "battle_intro_2" else 0
                )
    return screen


def fixture_kingdom_map_data() -> dict:
    lands = [
        fixture_map_land(4, 4, 7, owned=True, kingdom_id=4,
                         kingdom_name="Pocket Himalaya"),
        fixture_map_land(5, 4, 8, owned=True, kingdom_id=4,
                         kingdom_name="Pocket Himalaya"),
        fixture_map_land(4, 5, 9, owned=True, kingdom_id=4,
                         kingdom_name="Pocket Himalaya"),
        fixture_map_land(5, 5, 10, owned=True, kingdom_id=4,
                         kingdom_name="Pocket Himalaya"),
        fixture_map_land(6, 4, 21, owned=False, kingdom_id=9,
                         kingdom_name="Rival Ridge"),
        fixture_map_land(6, 5, 22, owned=False, kingdom_id=9,
                         kingdom_name="Rival Ridge"),
        fixture_map_land(3, 4, 23, owned=False, kingdom_id=12,
                         kingdom_name="Border Duchy"),
        fixture_map_land(3, 5, 24, owned=False, kingdom_id=12,
                         kingdom_name="Border Duchy"),
    ]
    largest = [
        {
            "rank": 1,
            "name": "Pocket Himalaya",
            "username": "MobileUser",
            "user_id": 1,
            "kingdom_id": 4,
            "kingdom_component_id": 401,
            "size": 4,
            "land_ids": [7, 8, 9, 10],
        },
        {
            "rank": 2,
            "name": "Rival Ridge",
            "username": "RivalKing",
            "user_id": 2,
            "kingdom_id": 9,
            "kingdom_component_id": 902,
            "size": 2,
            "land_ids": [21, 22],
        },
    ]
    realms = [
        {
            "rank": 1,
            "username": "MobileUser",
            "user_id": 1,
            "total_lands": 4,
            "largest_kingdom_id": 4,
            "largest_component_id": 401,
            "largest_land_ids": [7, 8, 9, 10],
        },
        {
            "rank": 2,
            "username": "RivalKing",
            "user_id": 2,
            "total_lands": 2,
            "largest_kingdom_id": 9,
            "largest_component_id": 902,
            "largest_land_ids": [21, 22],
        },
    ]
    return {
        "lands": lands,
        "conquer_cooldown_remaining": 0,
        "my_kingdom": {
            "components": [{"land_ids": [7, 8, 9, 10], "size": 4}],
        },
        "my_kingdoms": [{
            "id": 4,
            "name": "Pocket Himalaya",
            "land_ids": [7, 8, 9, 10],
            "lands_count": 4,
            "pending_gold": 37.0,
            "vault_cap": 80,
            "production": {
                "main_booster": {"pending": 1},
                "side_booster": {"pending": 0},
            },
        }],
        "my_lands_count": 4,
        "my_total_gold_rate": 18.0,
        "my_effective_gold_rate": 21.0,
        "top_largest_kingdoms": largest,
        "top_greatest_realms": realms,
        "my_largest_rank": 1,
        "my_largest_size": 4,
        "my_realm_rank": 1,
        "my_realm_size": 4,
    }


def populate_kingdom_screen(screen, tab: str) -> None:
    old_load_activity = getattr(screen, "_load_activity", None)
    screen._load_activity = lambda: None
    try:
        screen._apply_map_response({
            "data": fixture_kingdom_map_data(),
            "status_code": 200,
            "error": None,
        })
    finally:
        if old_load_activity is not None:
            screen._load_activity = old_load_activity
    screen._activity_poller = None
    screen._loading = False
    screen._error = None
    screen._activity_tab = tab
    screen._activity_scroll_offsets = {"alerts": 0, "history": 0, "messages": 0}
    screen._notifications = [
        {
            "activity_title": "RivalKing conquered your land",
            "activity_detail": "Loot lost: A of Hearts + 1 more",
            "activity_tone": "bad",
            "activity_land_label": "2h  -  Land (6, 4)",
            "seen": False,
            "land_id": 21,
            "land_col": 6,
            "land_row": 4,
        },
        {
            "kind": "level_up",
            "payload": {"new_level": 7, "sp_gained": 1,
                        "kingdom_name": "Pocket Himalaya"},
            "timestamp": "2026-05-27T08:15:00Z",
            "seen": False,
        },
        {
            "kind": "kingdoms_merged",
            "payload": {
                "absorbed_kingdom_name": "High Pass",
                "absorbed_lands": 2,
                "xp_awarded": 45,
            },
            "timestamp": "2026-05-27T07:30:00Z",
            "seen": False,
        },
    ]
    screen._attack_history = [
        {
            "attacker_user_id": 1,
            "defender_user_id": 2,
            "attacker_username": "MobileUser",
            "defender_username": "RivalKing",
            "result": "attacker_won",
            "role": "attacker",
            "loot_cards": [{"rank": "K", "suit": "Spades"}],
            "land_id": 21,
            "land_col": 6,
            "land_row": 4,
            "timestamp": "2026-05-27T06:30:00Z",
        },
        {
            "attacker_user_id": 2,
            "defender_user_id": 1,
            "attacker_username": "RivalKing",
            "defender_username": "MobileUser",
            "result": "defender_won",
            "role": "defender",
            "loot_cards": [{"rank": "Q", "suit": "Hearts"}],
            "land_id": 7,
            "land_col": 4,
            "land_row": 4,
            "timestamp": "2026-05-26T19:10:00Z",
        },
    ]
    screen._conversations = [
        {
            "other_user_id": 2,
            "other_username": "RivalKing",
            "last_message": "Nice shield timing. Rematch soon?",
            "last_sender_user_id": 2,
            "last_seen_by_recipient": False,
            "last_timestamp": "2026-05-27T08:45:00Z",
            "last_land_id": 21,
            "last_land_col": 6,
            "last_land_row": 4,
            "unread_count": 2,
            "is_ai": False,
        },
        {
            "other_user_id": 5,
            "other_username": "MountainGuide",
            "last_message": "The pass is safe for now.",
            "last_sender_user_id": 1,
            "last_seen_by_recipient": True,
            "last_timestamp": "2026-05-26T20:10:00Z",
            "last_land_id": 7,
            "last_land_col": 4,
            "last_land_row": 4,
            "unread_count": 0,
            "is_ai": True,
        },
    ]
    screen._messages = list(screen._conversations)
    screen._message_unread_count = 2


def populate_kingdom_config(screen, section: str) -> None:
    kingdom = fixture_kingdom_config_payload()
    screen.state.kingdom_config_id = kingdom["id"]
    screen.state.kingdom_config_land_id = None
    screen._data = {
        "success": True,
        "catalog": fixture_cosmetic_catalog(),
        "gold": 1234,
        "shield_options_hours": [6, 12, 24],
        "selected_kingdom_id": kingdom["id"],
        "kingdoms": [kingdom],
        "rename_price_gold": 150,
        "vault_default_cap": 50,
    }
    screen._catalog = screen._data["catalog"]
    screen._kingdom = kingdom
    screen._gold = 1234
    screen._selected_hours = 6
    screen._quote = {"price_gold": 108, "hours": 6}
    screen._message = ""
    screen._loading = False
    screen._content_scroll = 0
    if section == "shield":
        layout = screen._layout_rects()
        screen._content_scroll = max(0, layout["cosmetics_h"] + layout["gap"] - 20)


def canonical_screen_name(screen_name: str) -> str:
    if screen_name in COLLECTION_SCREEN_ALIASES:
        return "collection"
    if screen_name in BOOSTER_REVEAL_ALIASES:
        return "collection"
    if screen_name in KINGDOM_SCREEN_ALIASES:
        return "kingdom"
    if screen_name in KINGDOM_CONFIG_ALIASES:
        return "kingdom_config"
    if screen_name in DUEL_SCREEN_ALIASES:
        return "game"
    if screen_name in CONQUER_GAME_ALIASES:
        return "conquer_game"
    return screen_name


def uses_fixture(screen_name: str) -> bool:
    return (
        screen_name in KINGDOM_SCREEN_ALIASES
        or screen_name in KINGDOM_CONFIG_ALIASES
        or screen_name in DUEL_SCREEN_ALIASES
        or screen_name in CONQUER_GAME_ALIASES
        or screen_name in BOOSTER_REVEAL_ALIASES
        or screen_name in COLLECTION_SCREEN_ALIASES
        or screen_name in {"conquer", "defence"}
    )


def populate_collection_screen(screen) -> None:
    """Populate a mixed stock snapshot so visual reviews exercise real states."""
    from config import settings

    screen._profile_dialogue = None
    screen._profile_card = None
    screen._sell_dialogue = None
    screen._trade_dialogue = None
    screen._reveal_overlay = None
    screen._show_locked_cards = False
    screen._load_error = None
    screen._recent_card_gains = {}
    screen._recent_gains_started_at = None
    cards = []
    for suit_index, suit in enumerate(settings.SUITS):
        for rank_index, rank in enumerate(settings.RANKS):
            if (suit_index * 2 + rank_index) % 5 == 0:
                continue
            total = 1 + ((suit_index * 3 + rank_index) % 5)
            if (suit_index + rank_index) % 11 == 0:
                locked = total
            elif (suit_index + rank_index) % 4 == 0:
                locked = total // 2
            else:
                locked = 0
            cards.append({
                "suit": suit,
                "rank": rank,
                "total": total,
                "locked": locked,
            })
    screen._apply_collection_data({
        "cards": cards,
        "gold": 1234,
        "booster_packs": 2,
        "booster_packs_side": 1,
        "maps": 3,
    })
    screen._poller = None
    screen._current_collection_coach_step = lambda: None


def populate_collection_booster_reveal(screen, variant: str):
    import pygame
    from game.components.booster_reveal import BoosterRevealOverlay
    from config import settings

    cards = [
        {"suit": "Hearts", "rank": "7", "value": 7, "tier": 1,
         "_impact_new_type": True, "_impact_owned_after": 1},
        {"suit": "Clubs", "rank": "J", "value": 1, "tier": 2,
         "_impact_new_type": False, "_impact_owned_after": 4},
        {"suit": "Spades", "rank": "K", "value": 4, "tier": 3,
         "_impact_new_type": True, "_impact_owned_after": 1},
    ]
    if variant == "bulk":
        suits = ["Hearts", "Diamonds", "Clubs", "Spades"]
        ranks = ["7", "8", "9", "10", "J", "Q", "K", "A"]
        cards = [
            {"suit": suits[i % 4], "rank": ranks[i % 8],
             "value": 7, "tier": (i % 3) + 1,
             "_impact_new_type": i < 3,
             "_impact_owned_after": 1 if i < 3 else 2 + (i % 4)}
            for i in range(12)
        ]
    overlay = BoosterRevealOverlay(screen.window, cards, pack_type="main")
    if variant == "special":
        now = pygame.time.get_ticks()
        overlay._states = ["revealed"] * len(cards)
        overlay._reveal_started_at = [
            now - settings.COLLECTION_REVEAL_FLIP_MS - 80,
            now - settings.COLLECTION_REVEAL_FLIP_MS - 140,
            now - settings.COLLECTION_REVEAL_FLIP_MS - 220,
        ]

    def render():
        screen.window.fill((16, 13, 10))
        overlay.draw()

    return SimpleNamespace(render=render)


def prepare_screen(client, screen_name: str):
    if screen_name in COLLECTION_SCREEN_ALIASES:
        screen = client.screens["collection"]
        populate_collection_screen(screen)
        variant = COLLECTION_SCREEN_ALIASES[screen_name]
        if variant == "profile":
            screen._open_profile_dialogue("Hearts", "A")
        elif variant == "locked":
            screen._show_locked_cards = True
        elif variant in {"loading", "error"}:
            screen._data_loaded = False
            screen._load_error = (
                "Could not load collection" if variant == "error" else None)
        return screen

    if screen_name in BOOSTER_REVEAL_ALIASES:
        screen = client.screens["collection"]
        return populate_collection_booster_reveal(
            screen, BOOSTER_REVEAL_ALIASES[screen_name])

    if screen_name in CONQUER_GAME_ALIASES:
        return populate_conquer_game(client, CONQUER_GAME_ALIASES[screen_name])

    if screen_name in DUEL_SCREEN_ALIASES:
        screen = client.screens["game"]
        populate_duel_game(client, screen, DUEL_SCREEN_ALIASES[screen_name])
        return screen

    if screen_name in KINGDOM_SCREEN_ALIASES:
        screen = client.screens["kingdom"]
        populate_kingdom_screen(screen, KINGDOM_SCREEN_ALIASES[screen_name])
        return screen

    if screen_name in KINGDOM_CONFIG_ALIASES:
        screen = client.screens["kingdom_config"]
        populate_kingdom_config(screen, KINGDOM_CONFIG_ALIASES[screen_name])
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
        actual_name = canonical_screen_name(screen_name)
        known_names = (
            *client.screens.keys(),
            *DUEL_SCREEN_ALIASES.keys(),
            *CONQUER_GAME_ALIASES.keys(),
            *KINGDOM_SCREEN_ALIASES.keys(),
            *KINGDOM_CONFIG_ALIASES.keys(),
            *BOOSTER_REVEAL_ALIASES.keys(),
            *COLLECTION_SCREEN_ALIASES.keys(),
        )
        if screen_name not in known_names:
            print(f"skip {screen_name}: screen not loaded")
            failures += 1
            continue
        try:
            client.state.screen = actual_name
            screen = client.screens.get(actual_name)
            if screen is not None and not uses_fixture(screen_name) and hasattr(screen, "on_enter"):
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
            "collection_profile,collection_locked,collection_loading,collection_error,"
            "collection_booster_reveal_special,"
            "game_field,game_battle_shop,game_battle,"
            "conquer_game_field,conquer_game_battle_shop,conquer_game_battle,"
            "conquer_game_battle_dagger,conquer_game_battle_collapsed"
        ),
    )
    args = parser.parse_args()
    width_s, height_s = args.size.lower().split("x", 1)
    screens = [s.strip() for s in args.screens.split(",") if s.strip()]
    return render_screens(int(width_s), int(height_s), args.ui_scale, screens)


if __name__ == "__main__":
    raise SystemExit(main())
