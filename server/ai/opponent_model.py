# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Opponent belief model derived from revealed information only."""

from __future__ import annotations

from collections import Counter
from math import exp
from typing import Any


def _find_players(game_dict: dict[str, Any], ai_player_id: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    players = game_dict.get('players', [])
    ai_player = next((p for p in players if p.get('id') == ai_player_id), None)
    opponent = next((p for p in players if p.get('id') != ai_player_id), None)
    return ai_player, opponent


def _figure_cards(fig: dict[str, Any]) -> list[dict[str, Any]]:
    cards = fig.get('cards')
    if isinstance(cards, list):
        return cards
    cards_to_figure = fig.get('cards_to_figure')
    if isinstance(cards_to_figure, list):
        return cards_to_figure
    return []


def _figure_power(fig: dict[str, Any]) -> int:
    if fig.get('field') == 'castle':
        return 15
    power = 0
    for card in _figure_cards(fig):
        power += int(card.get('value') or card.get('card_value') or 0)
    return power


def _active_modifier_names(game_dict: dict[str, Any]) -> list[str]:
    modifiers = game_dict.get('battle_modifier')
    if not isinstance(modifiers, list):
        return []

    names: list[str] = []
    for m in modifiers:
        if not isinstance(m, dict):
            continue
        t = str(m.get('type') or '').strip()
        if t:
            names.append(t)
    return names


def _revealed_cards(opponent: dict[str, Any], game_dict: dict[str, Any]) -> dict[str, Any]:
    revealed_main = Counter()
    revealed_side = Counter()
    revealed_rank_suit_main = Counter()
    revealed_rank_suit_side = Counter()

    for fig in opponent.get('figures', []):
        for card in _figure_cards(fig):
            rank = card.get('rank') or card.get('card_rank')
            suit = card.get('suit') or card.get('card_suit')
            card_type = card.get('card_type')

            if not card_type:
                # Figure key cards are mostly main if unspecified in legacy dicts.
                card_type = 'main'

            if card_type == 'side':
                revealed_side[str(rank)] += 1
                revealed_rank_suit_side[f"{rank}_{suit}"] += 1
            else:
                revealed_main[str(rank)] += 1
                revealed_rank_suit_main[f"{rank}_{suit}"] += 1

    for move in game_dict.get('battle_moves', []):
        if move.get('player_id') != opponent.get('id'):
            continue
        if move.get('played_round') is None:
            continue

        rank = move.get('rank')
        suit = move.get('suit')
        card_type = move.get('card_type', 'main')

        if card_type == 'side':
            revealed_side[str(rank)] += 1
            revealed_rank_suit_side[f"{rank}_{suit}"] += 1
        else:
            revealed_main[str(rank)] += 1
            revealed_rank_suit_main[f"{rank}_{suit}"] += 1

    return {
        'main_rank_counts': dict(revealed_main),
        'side_rank_counts': dict(revealed_side),
        'main_rank_suit_counts': dict(revealed_rank_suit_main),
        'side_rank_suit_counts': dict(revealed_rank_suit_side),
        'total_revealed': int(sum(revealed_main.values()) + sum(revealed_side.values())),
    }


def _figure_score(fig: dict[str, Any], modifiers: set[str], resting_ids: set[int]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = float(_figure_power(fig))

    if fig.get('field') == 'military':
        score += 2.0
        reasons.append('military figure')
    elif fig.get('field') == 'village':
        score += 1.0
        reasons.append('village figure')

    if fig.get('checkmate'):
        score += 3.0
        reasons.append('checkmate pressure')

    if fig.get('must_be_attacked'):
        score += 4.0
        reasons.append('must be attacked')

    if fig.get('cannot_be_blocked'):
        score += 2.0
        reasons.append('cannot be blocked')

    if fig.get('rest_after_attack'):
        score += 1.0
        reasons.append('rest-after-attack tempo')

    if fig.get('cannot_attack'):
        score -= 5.0
        reasons.append('cannot attack penalty')

    fig_id = int(fig.get('id') or -1)
    if fig_id in resting_ids:
        score -= 3.0
        reasons.append('currently resting')

    field = str(fig.get('field') or '')
    if 'Peasant War' in modifiers or 'Civil War' in modifiers:
        if field != 'village':
            score -= 8.0
            reasons.append('villager-only modifier active')

    if 'Blitzkrieg' in modifiers and fig.get('cannot_be_blocked'):
        score += 1.5
        reasons.append('blitzkrieg synergy')

    return score, reasons


def _softmax(scores: list[float], temperature: float = 5.0) -> list[float]:
    if not scores:
        return []
    t = max(0.1, float(temperature))
    m = max(scores)
    exps = [exp((s - m) / t) for s in scores]
    z = sum(exps)
    if z <= 0:
        return [0.0 for _ in exps]
    return [v / z for v in exps]


def build_opponent_belief_snapshot(
    game_dict: dict[str, Any],
    ai_player_id: int,
    max_figures: int = 3,
) -> dict[str, Any]:
    """Build a concise opponent model from known board information.

    This function never assumes hidden cards; it only scores currently visible
    figures/cards and active battle modifiers.
    """
    _, opponent = _find_players(game_dict, ai_player_id)
    if not opponent:
        return {
            'opponent_player_id': None,
            'opponent_username': None,
            'revealed_cards': {
                'main_rank_counts': {},
                'side_rank_counts': {},
                'main_rank_suit_counts': {},
                'side_rank_suit_counts': {},
                'total_revealed': 0,
            },
            'active_battle_modifiers': [],
            'likely_battle_figures': [],
        }

    modifier_names = _active_modifier_names(game_dict)
    resting_ids = set(int(x) for x in (game_dict.get('resting_figure_ids') or []) if isinstance(x, int))

    candidates = []
    for fig in opponent.get('figures', []):
        score, reasons = _figure_score(fig, set(modifier_names), resting_ids)
        candidates.append((fig, score, reasons))

    candidates.sort(key=lambda x: x[1], reverse=True)
    probs = _softmax([c[1] for c in candidates], temperature=5.0)

    likely_figures = []
    for idx, (fig, score, reasons) in enumerate(candidates[: max(1, int(max_figures))]):
        likely_figures.append(
            {
                'figure_id': fig.get('id'),
                'name': fig.get('name'),
                'family_name': fig.get('family_name'),
                'field': fig.get('field'),
                'power_estimate': _figure_power(fig),
                'score': round(float(score), 3),
                'probability': round(float(probs[idx] if idx < len(probs) else 0.0), 4),
                'reasons': reasons[:4],
            }
        )

    return {
        'opponent_player_id': opponent.get('id'),
        'opponent_username': opponent.get('username'),
        'revealed_cards': _revealed_cards(opponent, game_dict),
        'active_battle_modifiers': modifier_names,
        'likely_battle_figures': likely_figures,
    }
