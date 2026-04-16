# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Bounded multi-turn strategy planner for AI action selection."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from ai.figure_completion import best_figure_targets
from ai.opponent_model import build_opponent_belief_snapshot


_RANK_VALUE_MAP = {
    '2': 2,
    '3': 3,
    '4': 4,
    '5': 5,
    '6': 6,
    '7': 7,
    '8': 8,
    '9': 9,
    '10': 10,
    'J': 11,
    'Q': 12,
    'K': 13,
    'A': 14,
}


@dataclass
class StrategyPlan:
    plan_id: int
    seed_action_id: int
    strategy_name: str
    phase: str
    horizon_turns: int
    turn_steps: list[str]
    planned_battle_figure: dict[str, Any] | None
    likely_opponent_figure: dict[str, Any] | None
    planned_battle_moves: list[dict[str, Any]]
    feasibility_probability: float
    expected_power_diff: float
    expected_battle_move_power: float
    total_score: float
    score_breakdown: dict[str, float]
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            'plan_id': self.plan_id,
            'seed_action_id': self.seed_action_id,
            'strategy_name': self.strategy_name,
            'phase': self.phase,
            'horizon_turns': self.horizon_turns,
            'turn_steps': list(self.turn_steps),
            'planned_battle_figure': self.planned_battle_figure,
            'likely_opponent_figure': self.likely_opponent_figure,
            'planned_battle_moves': list(self.planned_battle_moves),
            'feasibility_probability': round(self.feasibility_probability, 4),
            'expected_power_diff': round(self.expected_power_diff, 3),
            'expected_battle_move_power': round(self.expected_battle_move_power, 3),
            'total_score': round(self.total_score, 4),
            'score_breakdown': {
                k: round(v, 4)
                for k, v in self.score_breakdown.items()
            },
            'notes': list(self.notes),
        }


def _find_player(game_dict: dict[str, Any], player_id: int) -> dict[str, Any] | None:
    return next((p for p in game_dict.get('players', []) if p.get('id') == player_id), None)


def _find_opponent(game_dict: dict[str, Any], ai_player_id: int) -> dict[str, Any] | None:
    return next((p for p in game_dict.get('players', []) if p.get('id') != ai_player_id), None)


def _figure_power(fig: dict[str, Any], all_figures: list[dict[str, Any]] | None = None) -> int:
    if fig.get('field') == 'castle':
        base = 15
    else:
        cards = fig.get('cards', fig.get('cards_to_figure', []))
        base = sum(int(c.get('value') or c.get('card_value') or 0) for c in cards)
    if all_figures:
        from ai.game_state import compute_support_bonus
        base += compute_support_bonus(fig, all_figures)
    return base


def _extract_power_from_action_description(action: dict[str, Any]) -> int | None:
    desc = str(action.get('description', ''))
    match = re.search(r'power\s*[=≈]\s*(\d+)', desc)
    if match:
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return None
    return None


def _free_main_cards(player: dict[str, Any]) -> list[dict[str, Any]]:
    cards = [
        c for c in player.get('main_hand', [])
        if not c.get('part_of_figure') and not c.get('part_of_battle_move')
    ]
    cards.sort(key=lambda c: int(c.get('value') or 0), reverse=True)
    return cards


def _planned_battle_moves(player: dict[str, Any], count: int = 3) -> list[dict[str, Any]]:
    cards = _free_main_cards(player)
    out = []
    for c in cards[: max(1, int(count))]:
        out.append(
            {
                'rank': c.get('rank'),
                'suit': c.get('suit'),
                'value': int(c.get('value') or 0),
            }
        )
    return out


def _estimate_target_figure_for_action(
    action: dict[str, Any],
    ai_player: dict[str, Any],
    top_targets: list[dict[str, Any]],
) -> dict[str, Any] | None:
    action_type = action.get('type')
    params = action.get('params', {}) or {}

    if action_type == 'advance_figure':
        fid = params.get('figure_id')
        ai_figs = ai_player.get('figures', [])
        fig = next((f for f in ai_figs if f.get('id') == fid), None)
        if fig:
            return {
                'figure_id': fig.get('id'),
                'name': fig.get('name'),
                'field': fig.get('field'),
                'suit': fig.get('suit'),
                'state': 'already_built',
                'power_estimate': _figure_power(fig, ai_figs),
            }

    if action_type == 'build_figure':
        family_name = params.get('family_name')
        suit = params.get('suit')
        target = next(
            (
                t for t in top_targets
                if t.get('family_name') == family_name and t.get('suit') == suit
            ),
            None,
        )

        if target:
            est_power = _extract_power_from_action_description(action)
            if est_power is None:
                est_power = _estimate_recipe_power(target)
            return {
                'figure_id': None,
                'name': target.get('name'),
                'field': target.get('field'),
                'suit': target.get('suit'),
                'state': target.get('card_state'),
                'power_estimate': est_power,
                'completion_probability': target.get('completion_probability', 0.0),
                'resource_blocked': target.get('resource_blocked', False),
                'assumed_main_draws_per_turn': target.get('assumed_main_draws_per_turn'),
                'assumed_side_draws_per_turn': target.get('assumed_side_draws_per_turn'),
            }

    # For change_cards: pick the target figure with the highest
    # (probability * power) product — this steers the single change_cards
    # plan toward the goal that benefits most from fresh cards.
    if action_type in ('change_cards', 'change_side_cards') and top_targets:
        best = max(
            top_targets,
            key=lambda t: (
                float(t.get('completion_probability', 0.0))
                * _estimate_recipe_power(t)
            ),
        )
        return {
            'figure_id': None,
            'name': best.get('name'),
            'field': best.get('field'),
            'suit': best.get('suit'),
            'state': best.get('card_state'),
            'power_estimate': _estimate_recipe_power(best),
            'completion_probability': best.get('completion_probability', 0.0),
            'resource_blocked': best.get('resource_blocked', False),
            'assumed_main_draws_per_turn': best.get('assumed_main_draws_per_turn'),
            'assumed_side_draws_per_turn': best.get('assumed_side_draws_per_turn'),
        }

    if top_targets:
        t = top_targets[0]
        return {
            'figure_id': None,
            'name': t.get('name'),
            'field': t.get('field'),
            'suit': t.get('suit'),
            'state': t.get('card_state'),
            'power_estimate': _estimate_recipe_power(t),
            'completion_probability': t.get('completion_probability', 0.0),
            'resource_blocked': t.get('resource_blocked', False),
            'assumed_main_draws_per_turn': t.get('assumed_main_draws_per_turn'),
            'assumed_side_draws_per_turn': t.get('assumed_side_draws_per_turn'),
        }

    current_figs = ai_player.get('figures', [])
    if current_figs:
        strongest = max(current_figs, key=lambda f: _figure_power(f, current_figs))
        return {
            'figure_id': strongest.get('id'),
            'name': strongest.get('name'),
            'field': strongest.get('field'),
            'suit': strongest.get('suit'),
            'state': 'already_built',
            'power_estimate': _figure_power(strongest, current_figs),
        }

    return None


def _estimate_recipe_power(target: dict[str, Any]) -> int:
    """Approximate figure power from known recipe key-card obligations."""
    missing_main = target.get('missing_main', {}) or {}
    missing_side = target.get('missing_side', {}) or {}

    # Missing dict uses rank_suit keys. We only recover rank contribution from key names.
    main_component = 0
    for key in missing_main:
        rank = str(key).split('_', 1)[0]
        main_component += _RANK_VALUE_MAP.get(rank, 0)

    side_component = 0
    for key in missing_side:
        rank = str(key).split('_', 1)[0]
        side_component += _RANK_VALUE_MAP.get(rank, 0)

    number_component = int(target.get('number_value_assumed') or 0)

    estimate = main_component + side_component + number_component
    if estimate <= 0:
        # Generic fallback for unknown recipe details.
        return 10
    return estimate


def _action_feasibility(action: dict[str, Any], target: dict[str, Any] | None) -> float:
    t = action.get('type')

    if t == 'build_figure':
        if not target:
            return 0.0
        if target.get('resource_blocked'):
            return 0.05
        return float(target.get('completion_probability', 0.0))

    if t in ('change_cards', 'change_side_cards'):
        if target:
            return max(0.35, min(0.95, float(target.get('completion_probability', 0.5))))
        return 0.4

    if t == 'cast_spell':
        return 0.85

    # Enumerated actions are legal by construction.
    return 1.0


def _modifier_bonus(
    action: dict[str, Any],
    active_modifiers: list[str],
    opp_figures: list[dict[str, Any]] | None = None,
    own_figures: list[dict[str, Any]] | None = None,
    game_dict: dict[str, Any] | None = None,
    ai_player_id: int | None = None,
) -> float:
    """Compute action bonus using board state when available.

    For targeted spells (Poison, Health Boost, Explosion) the bonus is
    derived from the *actual* target figure power so the scorer naturally
    prefers high-value targets and avoids wasting spells on weak ones.
    Tactical spells (Blitzkrieg, War, Hammer) keep rule-derived constants
    because their value is structural, not figure-dependent.
    """
    bonus = 0.0
    opp_figures = opp_figures or []
    own_figures = own_figures or []

    action_type = action.get('type')

    # ── (1) Maharaja advance penalty ──
    # Advancing a checkmate figure risks instant game loss if the battle
    # is lost.  Apply a heavy penalty so the AI strongly prefers any
    # alternative figure — even one with slightly lower raw power —
    # since same-suit support bonuses often close the gap anyway.
    if action_type == 'advance_figure':
        params = action.get('params', {}) or {}
        fig_id = params.get('figure_id')
        if fig_id is not None:
            fig = next((f for f in own_figures if f.get('id') == fig_id), None)
            if fig and fig.get('checkmate'):
                bonus -= 8.0

    # ── (2) Same-suit build promotion ──
    # Building a figure whose suit matches existing figures increases
    # support bonus potential in battle.  Estimate the support bonus
    # the new figure would receive from existing same-suit allies.
    if action_type == 'build_figure':
        params = action.get('params', {}) or {}
        build_suit = params.get('suit')
        build_field = params.get('field', '').lower()
        if build_suit:
            from ai.game_state import compute_support_bonus
            # Create a lightweight stub for the new figure to estimate its
            # incoming support from existing allies.
            stub = {'id': None, 'suit': build_suit, 'field': build_field,
                    'name': params.get('name', ''), 'player_id': None}
            est_support = compute_support_bonus(stub, own_figures)
            bonus += est_support

    if action_type == 'cast_spell':
        desc = str(action.get('description', ''))
        params = action.get('params', {}) or {}
        spell_name = params.get('spell_family_name', params.get('spell_name', ''))
        target_fid = params.get('target_figure_id')

        # ── Tactical spells: rule-derived structural advantage ──
        if 'Blitzkrieg' in desc:
            bonus += 3.5
        if 'Infinite Hammer' in desc:
            bonus += 2.0

        # ── (4) Peasant War / Civil War: state-dependent bonus ──
        # Base value is 2.5, but increases when the opponent's military
        # is clearly stronger than ours (war spells force village-only
        # battles, bypassing the opponent's military advantage).
        if 'Peasant War' in desc or 'Civil War' in desc:
            bonus += 2.5
            opp_mil_power = sum(
                _figure_power(f, opp_figures) for f in opp_figures
                if f.get('field') == 'military' and not f.get('cannot_attack')
            )
            own_mil_power = sum(
                _figure_power(f, own_figures) for f in own_figures
                if f.get('field') == 'military' and not f.get('cannot_attack')
            )
            if opp_mil_power > own_mil_power + 5:
                # Opponent's military clearly outguns ours → war spells
                # are more valuable because they sidestep that advantage.
                bonus += min(3.0, (opp_mil_power - own_mil_power) * 0.3)

            # ── (5) Civil War: require two same-color village figures ──
            # Civil War lets each player pick 2 village figures of the
            # same color.  If we don't have two, the spell is wasted.
            if 'Civil War' in desc:
                from collections import Counter
                village_colors = Counter(
                    f.get('color') for f in own_figures
                    if f.get('field') == 'village'
                )
                max_same_color = max(village_colors.values()) if village_colors else 0
                if max_same_color < 2:
                    # We can't field two village figures → penalise heavily
                    bonus -= 4.0
                else:
                    # We have a valid pair → small extra incentive
                    bonus += 1.0

        # ── (3) Invader Swap with strong defense ──
        # If the AI is currently the invader and has strong defensive
        # figures (fortress, wall, or high-power military with
        # cannot_attack), swapping roles forces the opponent to advance
        # into our prepared defenses.
        if spell_name == 'Invader Swap':
            is_invader = False
            if game_dict and ai_player_id is not None:
                is_invader = game_dict.get('invader_player_id') == ai_player_id
            if is_invader:
                # Sum defensive strength: fortress/wall power + wall bonus
                defensive_power = sum(
                    _figure_power(f, own_figures) for f in own_figures
                    if f.get('cannot_attack') or f.get('must_be_attacked')
                )
                if defensive_power > 0:
                    # Strong defense makes role swap very attractive
                    bonus += min(4.0, defensive_power * 0.3)
                else:
                    # No special defenses → Invader Swap is risky, mild
                    # baseline because swapping away initiative is costly
                    bonus += 0.5
            else:
                # We're already defender → swapping to become invader is
                # sometimes useful but not the defensive play this rule
                # is about.  Flat baseline.
                bonus += 1.0

        # ── Targeted enchantment spells: state-dependent impact ──
        if spell_name == 'Poison' and target_fid is not None:
            fig = next((f for f in opp_figures if f.get('id') == target_fid), None)
            if fig:
                fig_power = _figure_power(fig, opp_figures)
                bonus += min(6.0, fig_power * 0.4)
            else:
                bonus += 3.0

        elif spell_name == 'Health Boost' and target_fid is not None:
            fig = next((f for f in own_figures if f.get('id') == target_fid), None)
            if fig:
                fig_power = _figure_power(fig, own_figures)
                bonus += min(6.0, fig_power * 0.3 + 3.0)
            else:
                bonus += 3.0

        elif spell_name == 'Explosion' and target_fid is not None:
            fig = next((f for f in opp_figures if f.get('id') == target_fid), None)
            if fig:
                fig_power = _figure_power(fig, opp_figures)
                resource_value = sum(
                    int(v) for v in (fig.get('produces') or {}).values()
                )
                bonus += fig_power * 0.4 + resource_value * 1.5
            else:
                bonus += 5.0

    if 'Blitzkrieg' in active_modifiers and action_type == 'advance_figure':
        bonus += 1.5

    return bonus


def _build_turn_steps(
    action: dict[str, Any],
    horizon_turns: int,
    target: dict[str, Any] | None,
    likely_opp: dict[str, Any] | None,
    battle_moves: list[dict[str, Any]],
) -> list[str]:
    turns = max(1, int(horizon_turns))
    action_desc = str(action.get('description', '')).strip()
    action_desc = action_desc if action_desc else f"take action #{action.get('id')}"

    target_name = target.get('name') if target else 'best available figure'
    opp_name = likely_opp.get('name') if likely_opp else 'highest-risk opponent figure'

    steps = [f"execute now: {action_desc}"]

    for turn_idx in range(2, turns + 1):
        if action.get('type') == 'build_figure':
            if turn_idx == 2:
                steps.append(f"advance {target_name} if legal; otherwise stabilize resources")
            else:
                steps.append(f"prepare battle moves and pressure {opp_name}")
        elif action.get('type') in ('change_cards', 'change_side_cards'):
            if turn_idx == 2:
                steps.append(f"build {target_name} with highest completion probability")
            elif turn_idx == 3:
                steps.append(f"advance strongest figure and force defense on {opp_name}")
            else:
                steps.append('optimize battle move quality and lock initiative')
        elif action.get('type') == 'advance_figure':
            if turn_idx == 2:
                steps.append(f"select defender targeting {opp_name} matchups")
            else:
                steps.append('choose battle/fold by projected win margin')
        elif action.get('type') == 'cast_spell':
            if turn_idx == 2:
                steps.append('exploit modifier window with restricted-opponent lines')
            else:
                steps.append(f"convert modifier advantage into battle against {opp_name}")
        elif action.get('type') in ('buy_battle_move', 'gamble_battle_move', 'combine_battle_moves'):
            if turn_idx == 2:
                bm_text = ', '.join(str(m.get('rank')) for m in battle_moves[:3])
                steps.append(f"target final 3-move set using cards {bm_text}")
            else:
                steps.append('confirm and sequence battle moves for highest differential')
        elif action.get('type') == 'battle_decision':
            steps.append('commit battle only if expected differential stays positive')
        else:
            steps.append('continue highest-EV legal action under current board state')

    return steps


def _score_plan(
    feasibility: float,
    expected_power_diff: float,
    expected_battle_move_power: float,
    modifier_bonus: float,
    turns_pressure: float,
) -> tuple[float, dict[str, float]]:
    offensive_value = expected_power_diff + 0.35 * expected_battle_move_power + modifier_bonus
    risk_penalty = (1.0 - feasibility) * 4.0
    total = feasibility * offensive_value + turns_pressure - risk_penalty

    return total, {
        'feasibility': feasibility,
        'offensive_value': offensive_value,
        'turns_pressure': turns_pressure,
        'risk_penalty': risk_penalty,
    }


def generate_strategy_plans(
    game_dict: dict[str, Any],
    ai_player_id: int,
    phase: str,
    actions: list[dict[str, Any]],
    max_plans: int = 5,
    max_main_draws_per_turn: int = 2,
    max_side_draws_per_turn: int = 1,
) -> list[dict[str, Any]]:
    """Generate bounded strategy plans seeded by currently legal actions."""
    if not actions:
        return []

    ai_player = _find_player(game_dict, ai_player_id)
    if not ai_player:
        return []

    horizon_turns = max(1, int(ai_player.get('turns_left') or 1))
    max_plans = max(1, int(max_plans))

    top_targets = best_figure_targets(
        game_dict,
        ai_player_id,
        remaining_turns=horizon_turns,
        max_results=max(6, max_plans),
        max_main_draws_per_turn=max_main_draws_per_turn,
        max_side_draws_per_turn=max_side_draws_per_turn,
    )
    opponent_snapshot = build_opponent_belief_snapshot(game_dict, ai_player_id)
    likely_opp = (opponent_snapshot.get('likely_battle_figures') or [None])[0]

    battle_moves = _planned_battle_moves(ai_player, count=3)
    expected_bm_power = float(sum(int(m.get('value') or 0) for m in battle_moves))

    plans: list[StrategyPlan] = []
    for idx, action in enumerate(actions, start=1):
        target = _estimate_target_figure_for_action(action, ai_player, top_targets)
        feasibility = _action_feasibility(action, target)

        own_power = float(target.get('power_estimate') if target else 0.0)
        opp_power = float(likely_opp.get('power_estimate') if likely_opp else 0.0)
        expected_power_diff = own_power - opp_power

        opp_player = _find_opponent(game_dict, ai_player_id)
        mod_bonus = _modifier_bonus(
            action,
            opponent_snapshot.get('active_battle_modifiers', []),
            opp_figures=opp_player.get('figures', []) if opp_player else [],
            own_figures=ai_player.get('figures', []),
            game_dict=game_dict,
            ai_player_id=ai_player_id,
        )
        turns_pressure = max(0.0, (4.0 - horizon_turns) * 0.5)
        total_score, score_breakdown = _score_plan(
            feasibility=feasibility,
            expected_power_diff=expected_power_diff,
            expected_battle_move_power=expected_bm_power,
            modifier_bonus=mod_bonus,
            turns_pressure=turns_pressure,
        )

        turn_steps = _build_turn_steps(
            action=action,
            horizon_turns=horizon_turns,
            target=target,
            likely_opp=likely_opp,
            battle_moves=battle_moves,
        )

        notes = []
        if target and target.get('resource_blocked'):
            notes.append('target build is resource blocked unless production improves')
        if likely_opp and likely_opp.get('probability', 0.0) >= 0.5:
            notes.append(f"opponent likely commits {likely_opp.get('name')} (p={likely_opp.get('probability')})")

        plans.append(
            StrategyPlan(
                plan_id=idx,
                seed_action_id=int(action.get('id') or idx),
                strategy_name=f"{str(action.get('type', 'action')).replace('_', ' ').title()} Line",
                phase=phase,
                horizon_turns=horizon_turns,
                turn_steps=turn_steps,
                planned_battle_figure=target,
                likely_opponent_figure=likely_opp,
                planned_battle_moves=battle_moves,
                feasibility_probability=max(0.0, min(1.0, feasibility)),
                expected_power_diff=expected_power_diff,
                expected_battle_move_power=expected_bm_power,
                total_score=total_score,
                score_breakdown=score_breakdown,
                notes=notes,
            )
        )

    # Stable order on ties: prefer lower action id.
    plans.sort(key=lambda p: (-p.total_score, p.seed_action_id))
    plans = plans[:max_plans]

    # Re-number plan ids after pruning.
    out = []
    for i, p in enumerate(plans, start=1):
        p.plan_id = i
        out.append(p.as_dict())
    return out


def recommended_action_id(plans: list[dict[str, Any]]) -> int | None:
    """Return seed action id for the highest-scoring generated plan."""
    if not plans:
        return None

    best = max(
        plans,
        key=lambda p: (
            float(p.get('total_score', 0.0)),
            -int(p.get('seed_action_id', 10**9)),
        ),
    )
    try:
        return int(best.get('seed_action_id'))
    except (TypeError, ValueError):
        return None


def format_strategy_plans_for_prompt(plans: list[dict[str, Any]]) -> str:
    """Render compact plan candidates for the LLM prompt."""
    if not plans:
        return "\n=== STRATEGY PLAN CANDIDATES ===\n  - No plan candidates generated."

    lines = ["\n=== STRATEGY PLAN CANDIDATES ==="]
    for p in plans:
        lines.append(
            f"PLAN {p.get('plan_id')} | seed_action={p.get('seed_action_id')} | "
            f"score={p.get('total_score')} | feasibility={p.get('feasibility_probability')}"
        )

        target = p.get('planned_battle_figure') or {}
        if target:
            lines.append(
                f"  planned_figure: {target.get('name')} ({target.get('field')}, "
                f"state={target.get('state')}, power~{target.get('power_estimate')})"
            )

        opp = p.get('likely_opponent_figure') or {}
        if opp:
            lines.append(
                f"  likely_opponent: {opp.get('name')} "
                f"(power~{opp.get('power_estimate')}, p={opp.get('probability')})"
            )

        moves = p.get('planned_battle_moves') or []
        if moves:
            move_str = ', '.join(
                f"{m.get('rank')}{str(m.get('suit') or '')[:1]}({m.get('value')})"
                for m in moves
            )
            lines.append(f"  planned_moves: {move_str}")

        for turn_idx, step in enumerate(p.get('turn_steps') or [], start=1):
            lines.append(f"  turn_{turn_idx}: {step}")

        for note in p.get('notes') or []:
            lines.append(f"  note: {note}")

    lines.append("Select the action that best matches the highest-EV plan while respecting current legal actions.")
    return '\n'.join(lines)
