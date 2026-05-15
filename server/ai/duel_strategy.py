"""Deterministic duel-mode AI decision module.

Replaces the LLM-driven `_ask_llm_for_action` path. Given a serialized game
state, the AI player's id, the current phase, the list of legal actions
(produced by `ai.action_enum.enumerate_actions`), and a seeded
`random.Random`, picks exactly one action and returns it.

Public surface: `choose_action`. All other functions are private.

Determinism: every decision is a pure function of (game_dict, ai_player_id,
phase, actions, rng). Pass a `random.Random(seed)` for replay.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from ai import strategy_planner

logger = logging.getLogger(__name__)

# ── Tuning constants ────────────────────────────────────────────────
NORMAL_TURN_TEMPERATURE = 0.15
NORMAL_TURN_TOP_K = 3
DEFENDER_TEMPERATURE = 0.3
DEFENDER_TOP_K = 3
BATTLE_ROUND_TEMPERATURE = 0.05  # near-greedy
# Gamble any play move whose effective value falls below this threshold
# (when a gamble action is available for that move). 11 matches the duel-AI
# tuning target: dump weak Daggers / Calls-without-figure for fresh draws.
BATTLE_ROUND_GAMBLE_THRESHOLD = 11
BATTLE_SHOP_TEMPERATURE = 0.3
BATTLE_SHOP_TOP_K = 3
# Estimated total advantage threshold below which we fold instead of fight.
BATTLE_DECISION_FOLD_THRESHOLD = -8
# Pending-spell harm score above which we counter (if we have the cards).
COUNTER_SPELL_HARM_THRESHOLD = 5

_RED_SUITS = {'Hearts', 'Diamonds'}
_BLACK_SUITS = {'Clubs', 'Spades'}


def choose_action(
    game_dict: dict[str, Any],
    ai_player_id: int,
    phase: str,
    actions: list[dict[str, Any]],
    rng,
) -> dict[str, Any]:
    """Pick exactly one action from `actions`.

    `rng` is a `random.Random` seeded from the game's `ai_seed` and a
    per-loop iteration counter, so the same inputs always produce the same
    action.
    """
    if not actions:
        raise ValueError("duel_strategy.choose_action called with no actions")
    if len(actions) == 1:
        return actions[0]

    handler = _PHASE_HANDLERS.get(phase)
    if handler is None:
        logger.warning("duel_strategy: unknown phase %r, returning first action", phase)
        return actions[0]
    return handler(game_dict, ai_player_id, actions, rng)


# ── Phase handlers ──────────────────────────────────────────────────

def _choose_normal_turn(game_dict, ai_player_id, actions, rng):
    plans = strategy_planner.generate_strategy_plans(
        game_dict,
        ai_player_id,
        'normal_turn',
        actions,
        max_plans=max(NORMAL_TURN_TOP_K, min(len(actions), 12)),
    )
    if not plans:
        return actions[0]

    by_id = {a['id']: a for a in actions}
    scored = []
    for plan in plans:
        action = by_id.get(plan.get('seed_action_id'))
        if action is None:
            continue
        scored.append((action, float(plan.get('total_score') or 0.0)))
    if not scored:
        return actions[0]
    return _softmax_sample(
        scored, rng, NORMAL_TURN_TEMPERATURE, NORMAL_TURN_TOP_K,
    )


def _choose_defender(game_dict, ai_player_id, actions, rng):
    """Prefer the weakest enemy figure (lowest power). Softmax-sample top-k."""
    opp = _opponent(game_dict, ai_player_id)
    opp_figs = opp.get('figures', []) or []
    power_by_id = {
        f.get('id'): _estimate_figure_power(f, opp_figs) for f in opp_figs
    }
    scored = []
    for action in actions:
        target_id = (action.get('params') or {}).get('figure_id')
        if target_id is None:
            scored.append((action, 0.0))
            continue
        # Lower power -> higher score (we want easy targets).
        scored.append((action, -float(power_by_id.get(target_id, 0))))
    return _softmax_sample(
        scored, rng, DEFENDER_TEMPERATURE, DEFENDER_TOP_K,
    )


def _choose_battle_decision(game_dict, ai_player_id, actions, rng):
    """Fold when the estimated total advantage is bad; otherwise fight."""
    advantage = _estimated_battle_advantage(game_dict, ai_player_id)
    fight = _by_decision(actions, 'battle')
    fold = _by_decision(actions, 'fold')
    if fight is None:
        return fold or actions[0]
    if fold is None:
        return fight
    if advantage < BATTLE_DECISION_FOLD_THRESHOLD:
        return fold
    return fight


def _choose_battle_round(game_dict, ai_player_id, actions, rng):
    """Pick the best move for this battle round. Mirrors conquer policy.

    Order of preference (matches ``_conquer_play_battle_round``):

      1. **Gamble first.** If any play move scores below
         ``BATTLE_ROUND_GAMBLE_THRESHOLD`` and a gamble action exists for it,
         sacrifice the weakest such move for two fresh draws.
      2. **Combine daggers.** If a same-colour Dagger pair can be merged
         into a Double Dagger, do it — bundles two cards into one stronger
         move and frees a slot.
      3. **Play.**
         - If the opponent has already played Block this round, the round
           is neutralised regardless — play the *weakest* non-Block to
           preserve strong cards for later rounds.
         - Otherwise pick the strongest non-Block. If we hold Block AND the
           strongest non-Block cannot beat the opponent's known value, play
           Block to neutralise.
      4. Fall back to skip / first gamble / first action when nothing else
         is available.
    """
    plays = [a for a in actions
             if a.get('type') in ('play_battle_move', 'play_conquer_tactic')]
    gambles = [a for a in actions
               if a.get('type') in ('gamble_battle_move', 'gamble_conquer_tactic')]
    combines = [a for a in actions
                if a.get('type') in ('combine_battle_moves',
                                     'combine_conquer_tactics')]
    skips = [a for a in actions if a.get('type') == 'skip_battle_turn']

    own = _own_player(game_dict, ai_player_id)
    ai_figs = own.get('figures', []) or []
    moves_by_id = _battle_moves_by_id(game_dict)
    opp_blocked = _opponent_played_block_this_round(game_dict, ai_player_id)
    opp_round_value = _opponent_current_round_value(game_dict, ai_player_id)

    # Score each play action; index by move id for gamble cross-reference.
    scored_plays = []
    play_score_by_move_id = {}
    for action in plays:
        params = action.get('params') or {}
        mv_id = params.get('battle_move_id')
        move = moves_by_id.get(mv_id) or {}
        call_id = params.get('call_figure_id')
        score = _score_battle_move_play(move, call_id, ai_figs, opp_round_value)
        scored_plays.append({'action': action, 'score': score, 'move': move})
        if mv_id is not None:
            play_score_by_move_id[mv_id] = score

    # Step 1 — Gamble weak moves.
    if gambles:
        candidates = []
        for action in gambles:
            mv_id = (action.get('params') or {}).get('battle_move_id')
            # Calls without an eligible figure appear only as gamble actions
            # (no matching play). Treat as score 0 — perfect burn candidate.
            score = play_score_by_move_id.get(mv_id, 0)
            if score < BATTLE_ROUND_GAMBLE_THRESHOLD:
                candidates.append((action, score))
        if candidates:
            candidates.sort(key=lambda pair: pair[1])  # weakest first
            return candidates[0][0]

    # Step 2 — Combine same-colour dagger pairs (best combined value wins).
    if combines:
        scored_combines = [(a, _score_combine_action(a)) for a in combines]
        scored_combines.sort(key=lambda pair: -pair[1])  # highest first
        return scored_combines[0][0]

    # Step 3 — Play.
    if scored_plays:
        if opp_blocked:
            # Round neutralised — preserve strong cards, play weakest non-Block.
            non_block = [
                p for p in scored_plays
                if (p['move'].get('family_name') or '') != 'Block'
            ]
            if non_block:
                non_block.sort(key=lambda p: p['score'])
                return non_block[0]['action']
            # Only Block remains — play it.
            return scored_plays[0]['action']

        block_play = next(
            (p for p in scored_plays
             if (p['move'].get('family_name') or '') == 'Block'),
            None,
        )
        non_block = [
            p for p in scored_plays
            if (p['move'].get('family_name') or '') != 'Block'
        ]
        strongest = max(non_block, key=lambda p: p['score']) if non_block else None

        # Block tie-break: neutralise if our strongest can't beat opponent's
        # known move this round.
        if (block_play is not None and strongest is not None
                and opp_round_value is not None
                and strongest['score'] <= int(opp_round_value)):
            return block_play['action']

        if non_block:
            return _softmax_sample(
                [(p['action'], p['score']) for p in non_block],
                rng, BATTLE_ROUND_TEMPERATURE, top_k=None,
            )
        if block_play is not None:
            return block_play['action']

    # Step 4 — Fallback.
    if skips:
        return skips[0]
    if gambles:
        return gambles[0]
    return actions[0]


def _choose_battle_shop(game_dict, ai_player_id, actions, rng):
    """Confirm when offered; otherwise combine daggers; otherwise buy strong."""
    by_type: dict[str, list] = {}
    for action in actions:
        by_type.setdefault(action.get('type'), []).append(action)

    if by_type.get('confirm_battle_moves'):
        return by_type['confirm_battle_moves'][0]
    if by_type.get('combine_battle_moves'):
        # Pick the highest-power combine (description embeds `power=N`).
        combines = by_type['combine_battle_moves']
        scored = [(a, _score_combine_action(a)) for a in combines]
        return _softmax_sample(
            scored, rng, BATTLE_SHOP_TEMPERATURE, top_k=BATTLE_SHOP_TOP_K,
        )
    if by_type.get('buy_battle_move'):
        buys = by_type['buy_battle_move']
        scored = [(a, _score_buy_action(a, game_dict, ai_player_id)) for a in buys]
        return _softmax_sample(
            scored, rng, BATTLE_SHOP_TEMPERATURE, top_k=BATTLE_SHOP_TOP_K,
        )
    return actions[0]


def _choose_counter_spell(game_dict, ai_player_id, actions, rng):
    """Allow by default. Counter only when we have the cards AND it hurts us."""
    allow = next((a for a in actions if a.get('type') == 'allow_spell'), None)
    counter = next((a for a in actions if a.get('type') == 'counter_spell'), None)
    if counter is None:
        return allow or actions[0]
    if allow is None:
        return counter

    params = counter.get('params') or {}
    counter_cards = params.get('counter_cards') or []
    # action_enum sets counter_cards = [] when we don't hold the required
    # cards; countering would fail server-side. Always allow in that case.
    if not counter_cards:
        return allow

    spell_name = params.get('counter_spell_name', '') or ''
    if _estimated_spell_harm(spell_name, game_dict, ai_player_id) < COUNTER_SPELL_HARM_THRESHOLD:
        return allow
    return counter


_PHASE_HANDLERS = {
    'normal_turn': _choose_normal_turn,
    'select_defender': _choose_defender,
    'battle_decision': _choose_battle_decision,
    'battle_round': _choose_battle_round,
    'battle_shop': _choose_battle_shop,
    'counter_spell': _choose_counter_spell,
}


# ── Scoring helpers ─────────────────────────────────────────────────

def _softmax_sample(scored, rng, temperature: float, top_k: int | None):
    """Sample one action from (action, score) pairs via softmax."""
    if not scored:
        return None
    if len(scored) == 1:
        return scored[0][0]

    scored = sorted(scored, key=lambda p: -p[1])
    if top_k is not None:
        scored = scored[:top_k]

    max_score = max(s for _, s in scored)
    tau = max(float(temperature), 0.01)
    weights = [math.exp((s - max_score) / tau) for _, s in scored]
    total = sum(weights)
    if total <= 0:
        return scored[0][0]

    r = rng.random() * total
    acc = 0.0
    for (action, _), w in zip(scored, weights):
        acc += w
        if r <= acc:
            return action
    return scored[-1][0]


def _own_player(game_dict, ai_player_id):
    for p in game_dict.get('players', []) or []:
        if p.get('id') == ai_player_id:
            return p
    return {}


def _opponent(game_dict, ai_player_id):
    for p in game_dict.get('players', []) or []:
        if p.get('id') != ai_player_id:
            return p
    return {}


def _by_decision(actions, decision):
    for a in actions:
        if (a.get('params') or {}).get('decision') == decision:
            return a
    return None


def _estimate_figure_power(fig, peer_figures):
    """Power estimate from a figure dict. Mirrors action_enum._est_power."""
    if not fig:
        return 0
    if fig.get('field') == 'castle':
        base = 15
    else:
        cards = fig.get('cards_to_figure', []) or fig.get('cards', []) or []
        base = sum(
            int(c.get('card_value', c.get('value', 0)) or 0) for c in cards
        )
    if peer_figures:
        try:
            from ai.game_state import compute_support_bonus
            base += compute_support_bonus(fig, peer_figures)
        except Exception:
            pass
    return int(base)


def _estimated_battle_advantage(game_dict, ai_player_id):
    """Rough total-advantage estimate at the battle_decision moment.

    Combines our figure power - their figure power, plus our expected top-3
    battle move value minus a rough opponent move estimate (proportional to
    their main-hand size).
    """
    own = _own_player(game_dict, ai_player_id)
    opp = _opponent(game_dict, ai_player_id)

    adv_id = game_dict.get('advancing_figure_id')
    def_id = game_dict.get('defending_figure_id')
    is_invader = game_dict.get('advancing_player_id') == ai_player_id
    own_fig_id = adv_id if is_invader else def_id
    opp_fig_id = def_id if is_invader else adv_id

    own_figs = own.get('figures', []) or []
    opp_figs = opp.get('figures', []) or []
    own_fig = next((f for f in own_figs if f.get('id') == own_fig_id), None)
    opp_fig = next((f for f in opp_figs if f.get('id') == opp_fig_id), None)
    own_power = _estimate_figure_power(own_fig, own_figs)
    opp_power = _estimate_figure_power(opp_fig, opp_figs)

    battle_cards = [
        c for c in own.get('main_hand', []) or []
        if not c.get('part_of_figure')
        and not c.get('part_of_battle_move')
        and c.get('rank') in ('K', 'A', 'Q', 'J', '7', '8', '9', '10')
    ]
    top3 = sorted(battle_cards, key=lambda c: c.get('value', 0) or 0, reverse=True)[:3]
    own_moves_value = sum(int(c.get('value', 0) or 0) for c in top3)

    opp_main_count = opp.get('num_main')
    if opp_main_count is None:
        opp_main_count = len([
            c for c in opp.get('main_hand', []) or []
            if not c.get('part_of_figure') and not c.get('part_of_battle_move')
        ])
    # Rough opponent move estimate: average card value ~5, capped at 3 moves.
    opp_moves_estimate = min(int(opp_main_count or 0), 3) * 5

    return (own_power - opp_power) + (own_moves_value - opp_moves_estimate)


def _battle_moves_by_id(game_dict):
    out = {}
    for m in (game_dict.get('battle_moves') or []):
        if m.get('id') is not None:
            out[m['id']] = m
    for m in (game_dict.get('conquer_tactics') or []):
        if m.get('id') is not None:
            out[m['id']] = m
    return out


def _opponent_played_block_this_round(game_dict, ai_player_id):
    """True when the opponent has already played a Block in the current
    battle round. When this is the case, the round neutralises to 0-0 no
    matter what we do, so we should sacrifice the weakest card we hold.
    """
    opp = _opponent(game_dict, ai_player_id)
    if not opp:
        return False
    opp_id = opp.get('id')
    current_round = game_dict.get('battle_round')
    for m in (game_dict.get('battle_moves') or []) + (game_dict.get('conquer_tactics') or []):
        if m.get('player_id') != opp_id:
            continue
        if m.get('played_round') != current_round:
            continue
        if (m.get('family_name') or '') == 'Block':
            return True
    return False


def _opponent_current_round_value(game_dict, ai_player_id):
    """If the opponent has already played a move this battle round, return
    its rough effective value; otherwise None."""
    opp = _opponent(game_dict, ai_player_id)
    if not opp:
        return None
    current_round = game_dict.get('battle_round')
    opp_id = opp.get('id')

    opp_move = None
    for m in (game_dict.get('battle_moves') or []) + (game_dict.get('conquer_tactics') or []):
        if m.get('player_id') != opp_id:
            continue
        if m.get('played_round') != current_round:
            continue
        opp_move = m
        break
    if not opp_move:
        return None

    if opp_move.get('family_name') == 'Block':
        # Treat Block as a high-value defensive move worth blocking back
        return 8

    call_id = opp_move.get('call_figure_id')
    opp_figs = opp.get('figures', []) or []
    call_fig = next((f for f in opp_figs if f.get('id') == call_id), None) if call_id else None
    return _score_battle_move_play(opp_move, call_id, opp_figs, None) \
        if call_fig is not None else int(opp_move.get('value') or 0)


def _score_battle_move_play(move, call_figure_id, own_figures, opp_round_value):
    """Score a 'play_battle_move' style action by its effective combat value.

    Mirrors `_conquer_move_effective_value` on dict data. Block scoring keys
    off the opponent's known move this round: if they played strong, Block
    becomes attractive; otherwise it scores near zero.
    """
    if not move:
        return 0
    family = move.get('family_name', '')
    base = int(move.get('value') or 0)

    if family == 'Block':
        # Block nullifies the round. Worth playing when opponent's known move
        # this round outscores anything we'd otherwise play.
        return int(opp_round_value) if opp_round_value is not None else 0

    if not call_figure_id:
        return base

    call_fig = next((f for f in own_figures if f.get('id') == call_figure_id), None)
    if not call_fig:
        return base

    fig_power = _estimate_figure_power(call_fig, own_figures)
    move_suit = (move.get('suit') or '').lower()
    fig_suit = (call_fig.get('suit') or '').lower()
    if move_suit and move_suit == fig_suit:
        return fig_power + base
    return fig_power


def _score_combine_action(action):
    """Pull the `power=N` number out of the combine description."""
    desc = action.get('description', '') or ''
    marker = 'power='
    idx = desc.find(marker)
    if idx < 0:
        return 0
    rest = desc[idx + len(marker):]
    num = ''
    for ch in rest:
        if ch.isdigit():
            num += ch
        else:
            break
    return int(num) if num else 0


_BUY_RANK_SCORE = {
    'K': 9, 'A': 8, 'Q': 7, 'J': 6,
    '10': 5, '9': 4, '8': 3, '7': 2,
}


def _score_buy_action(action, game_dict, ai_player_id):
    """Score a `buy_battle_move` action.

    Call moves with an eligible figure score by that figure's power; Block
    and Daggers score by raw card value rank. Pure card-value preference.
    """
    params = action.get('params') or {}
    family = params.get('family_name', '')
    rank = params.get('rank', '')
    suit = params.get('suit', '')
    value = int(params.get('value', 0) or 0)

    if family in ('Call King', 'Call Military', 'Call Villager'):
        own_figs = _own_player(game_dict, ai_player_id).get('figures', []) or []
        field_map = {
            'Call King': 'castle',
            'Call Military': 'military',
            'Call Villager': 'village',
        }
        target_field = field_map.get(family)
        card_color = 'red' if suit in _RED_SUITS else 'black'
        best = 0
        for fig in own_figs:
            if fig.get('field') != target_field:
                continue
            fig_suit = fig.get('suit') or ''
            fig_color = 'red' if fig_suit in _RED_SUITS else 'black'
            if fig_color != card_color:
                continue
            power = _estimate_figure_power(fig, own_figs)
            if suit == fig_suit:
                power += value
            if power > best:
                best = power
        if best > 0:
            return float(best)
        # No matching figure — Call move is a wasted slot; rank by raw value
        return float(_BUY_RANK_SCORE.get(rank, 0))

    if family == 'Block':
        # Block has utility but is hand-dependent; mid-rank preference.
        return 6.0

    # Daggers and other plain-value families
    return float(_BUY_RANK_SCORE.get(rank, value))


# ── Counter-spell harm estimation ────────────────────────────────────

_SPELL_BASE_HARM = {
    'Ceasefire': 4,
    'Peasant War': 6,
    'Civil War': 5,
    'Blitzkrieg': 7,
    'Invader Swap': 8,
}


def _estimated_spell_harm(spell_name, game_dict, ai_player_id):
    """How much does the opponent's pending spell hurt us? Higher = worse.

    Base score per spell type, +2 if we're meaningfully ahead on figure count
    (spells like Civil War / Peasant War mostly hurt the leader by
    restricting their battle pool).
    """
    base = _SPELL_BASE_HARM.get(spell_name, 3)
    own = _own_player(game_dict, ai_player_id)
    opp = _opponent(game_dict, ai_player_id)
    own_n = len(own.get('figures', []) or [])
    opp_n = len(opp.get('figures', []) or [])
    if own_n > opp_n + 1:
        base += 2
    return base
