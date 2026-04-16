# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
Game state serializer for LLM prompts.

Converts the game dict (from game.serialize()) into a concise text
description that the LLM can understand and reason about.
"""
import logging

from ai.figure_recipes import FAMILY_SKILLS

logger = logging.getLogger('nepalkings.ai.game_state')


def enrich_figures_with_skills(game_dict: dict) -> dict:
    """Inject family-based skill flags into every serialized figure.

    Figure.serialize() only stores checkmate, cannot_be_blocked, and
    rest_after_attack in the DB.  The remaining nine skill flags
    (cannot_attack, must_be_attacked, cannot_defend, cannot_be_targeted,
    instant_charge, blocks_bonus, distance_attack, buffs_allies,
    buffs_allies_defence) are derived from the figure's family_name.

    This must be called once on the game_dict before any AI logic touches it.
    """
    for player in game_dict.get('players', []):
        for fig in player.get('figures', []):
            skills = FAMILY_SKILLS.get(fig.get('family_name'), {})
            for key, val in skills.items():
                # Don't overwrite DB-authoritative columns
                if key not in fig:
                    fig[key] = val
    return game_dict


def serialize_game_for_llm(game_dict: dict, ai_player_id: int) -> str:
    """
    Convert a game state dict into a human-readable text summary for the LLM.
    Only includes information the AI player should know (no hidden opponent cards).
    """
    lines = []
    
    # Find AI player and opponent
    ai_player = None
    opponent = None
    for p in game_dict['players']:
        if p['id'] == ai_player_id:
            ai_player = p
        else:
            opponent = p
    
    if not ai_player or not opponent:
        return "ERROR: Could not identify players."
    
    # Game info
    lines.append(f"=== GAME STATE ===")
    lines.append(f"Round: {game_dict['current_round']} | Stake (points to win): {game_dict['stake']}")
    lines.append(f"Your score: {ai_player['points']} | Opponent score: {opponent['points']}")
    lines.append(f"Your turns left: {ai_player['turns_left']} | Opponent turns left: {opponent['turns_left']}")
    
    is_invader = game_dict['invader_player_id'] == ai_player_id
    lines.append(f"You are: {'INVADER (attacker)' if is_invader else 'DEFENDER'}")
    lines.append(f"Ceasefire: {'ACTIVE (no advancing allowed)' if game_dict['ceasefire_active'] else 'OFF'}")
    
    # AI's hand cards
    lines.append(f"\n=== YOUR HAND ({len(ai_player['main_hand'])} main cards) ===")
    main_cards = _summarize_cards(ai_player['main_hand'])
    lines.append(main_cards)
    
    if ai_player.get('side_hand'):
        lines.append(f"Side cards ({len(ai_player['side_hand'])}): {_summarize_cards(ai_player['side_hand'])}")
    
    # Battle card analysis
    battle_cards = [c for c in ai_player.get('main_hand', [])
                    if not c.get('part_of_figure') and not c.get('part_of_battle_move')
                    and c.get('rank') in ('K', 'A', 'Q', 'J', '7', '8', '9', '10')]
    if battle_cards:
        by_val = sorted(battle_cards, key=lambda c: c.get('value', 0), reverse=True)
        top3 = by_val[:3]
        top_str = ', '.join(f"{c['rank']}({c.get('value', 0)})" for c in top3)
        total = sum(c.get('value', 0) for c in top3)
        lines.append(f"Battle-ready cards (top 3): {top_str} = total {total}")
    else:
        lines.append("Battle-ready cards: NONE — consider changing cards!")
    
    # AI's figures
    lines.append(f"\n=== YOUR FIGURES ({len(ai_player['figures'])}) ===")
    for fig in ai_player['figures']:
        lines.append(_describe_figure(fig))
    
    # Resource balance summary
    resource_summary = _compute_resource_summary(ai_player['figures'])
    lines.append(resource_summary)
    
    # Opponent's figures (visible info only — no card details)
    lines.append(f"\n=== OPPONENT'S FIGURES ({len(opponent['figures'])}) ===")
    for fig in opponent['figures']:
        lines.append(_describe_figure(fig, show_cards=False))
    
    # Check if AI has an active All Seeing Eye spell
    has_all_seeing_eye = any(
        'All Seeing Eye' in s.get('spell_name', '')
        and s.get('player_id') == ai_player_id
        and s.get('is_active')
        for s in game_dict.get('active_spells', [])
    )

    opp_main = opponent.get('main_hand', [])
    opp_side = opponent.get('side_hand', [])

    if has_all_seeing_eye and opp_main:
        lines.append(f"\n👁️ ALL SEEING EYE ACTIVE — opponent's cards revealed!")
        lines.append(f"Opponent main hand ({len(opp_main)}): {_summarize_cards(opp_main)}")
        if opp_side:
            lines.append(f"Opponent side hand ({len(opp_side)}): {_summarize_cards(opp_side)}")
        # Show opponent's figure card details too
        lines.append(f"\nOpponent's figure cards (revealed):")
        for fig in opponent['figures']:
            lines.append(_describe_figure(fig, show_cards=True))
    else:
        lines.append(f"\nOpponent has {len(opp_main)} main cards and {len(opp_side)} side cards in hand.")
    
    # Opponent threat analysis — skip when All Seeing Eye provides perfect info
    if not has_all_seeing_eye:
        lines.append(_analyze_opponent_threats(game_dict, ai_player, opponent))
    
    # Battle state if active
    if game_dict.get('advancing_figure_id'):
        lines.append(f"\n=== BATTLE STATE ===")
        adv_id = game_dict['advancing_figure_id']
        def_id = game_dict.get('defending_figure_id')
        adv_fig = _find_figure(game_dict, adv_id)
        def_fig = _find_figure(game_dict, def_id) if def_id else None
        adv_name = adv_fig['name'] if adv_fig else f"ID {adv_id}"
        lines.append(f"Advancing figure: {adv_name} (power≈{_est_power(adv_fig)})")
        if def_fig:
            lines.append(f"Defending figure: {def_fig['name']} (power≈{_est_power(def_fig)})")
        if game_dict.get('battle_confirmed'):
            lines.append(f"Battle confirmed! Round: {game_dict.get('battle_round', 0)+1}/3")
        if game_dict.get('battle_decisions'):
            lines.append(f"Battle decisions: {game_dict['battle_decisions']}")
    
    # Battle moves if in battle
    if game_dict.get('battle_confirmed'):
        ai_moves = [m for m in game_dict.get('battle_moves', []) if m.get('player_id') == ai_player_id]
        if ai_moves:
            lines.append(f"\nYour battle moves: {_summarize_battle_moves(ai_moves)}")
    
    # Active spells
    if game_dict.get('battle_modifier'):
        modifiers = game_dict['battle_modifier'] if isinstance(game_dict['battle_modifier'], list) else []
        if modifiers:
            mod_names = [m.get('type', '?') for m in modifiers]
            lines.append(f"\nActive battle modifiers: {', '.join(mod_names)}")
    
    return '\n'.join(lines)


def _find_figure(game_dict: dict, figure_id: int) -> dict | None:
    """Find a figure by ID across all players."""
    if not figure_id:
        return None
    for p in game_dict.get('players', []):
        for f in p.get('figures', []):
            if f['id'] == figure_id:
                return f
    return None


def _est_power(fig: dict | None) -> int:
    """Estimate a figure's base power from its cards (castle=15)."""
    if not fig:
        return 0
    if fig.get('field') == 'castle':
        return 15
    cards = fig.get('cards_to_figure', [])
    return sum(c.get('card_value', c.get('value', 0)) for c in cards)


def _summarize_cards(cards: list) -> str:
    """Summarize a list of card dicts into a compact string."""
    if not cards:
        return "(none)"
    
    # Group by rank
    by_rank = {}
    for c in cards:
        rank = c.get('rank', '?')
        suit = c.get('suit', '?')
        suit_short = {'Hearts': '♥', 'Diamonds': '♦', 'Clubs': '♣', 'Spades': '♠'}.get(suit, suit)
        by_rank.setdefault(rank, []).append(suit_short)
    
    parts = []
    for rank in ['K', 'A', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']:
        if rank in by_rank:
            suits = ''.join(by_rank[rank])
            parts.append(f"{rank}{suits}")
    
    return ' '.join(parts)


def _describe_figure(fig: dict, show_cards: bool = True) -> str:
    """Describe a figure for the LLM."""
    name = fig.get('name', '?')
    field = fig.get('field', '?')
    color = fig.get('color', '?')
    power = _est_power(fig)
    
    parts = [f"  - {name} ({field}/{color}, power≈{power})"]
    
    produces = fig.get('produces', {})
    if produces:
        prod_str = ', '.join(f"{v} {k}" for k, v in produces.items() if v)
        if prod_str:
            parts.append(f"produces: {prod_str}")
    
    requires = fig.get('requires', {})
    if requires:
        req_str = ', '.join(f"{v} {k}" for k, v in requires.items() if v)
        if req_str:
            parts.append(f"requires: {req_str}")
    
    # Special abilities
    abilities = []
    if fig.get('checkmate'):
        abilities.append('CHECKMATE')
    if fig.get('cannot_attack'):
        abilities.append('cannot-attack')
    if fig.get('must_be_attacked'):
        abilities.append('must-be-attacked')
    if fig.get('cannot_be_blocked'):
        abilities.append('unblockable')
    if fig.get('distance_attack'):
        abilities.append('ranged')
    if fig.get('buffs_allies'):
        abilities.append('buff-allies')
    if fig.get('buffs_allies_defence'):
        abilities.append('buff-allies-defence')
    if fig.get('blocks_bonus'):
        abilities.append('blocks-bonus')
    if fig.get('cannot_defend'):
        abilities.append('cannot-defend')
    if fig.get('cannot_be_targeted'):
        abilities.append('cannot-be-targeted')
    if fig.get('instant_charge'):
        abilities.append('instant-charge')
    if fig.get('rest_after_attack'):
        abilities.append('rest-after-attack')
    if abilities:
        parts.append(f"[{', '.join(abilities)}]")
    
    # Cards used (only for AI's own figures)
    if show_cards and fig.get('cards_to_figure'):
        card_strs = []
        for ctf in fig['cards_to_figure']:
            r = ctf.get('card_rank', '?')
            s = ctf.get('card_suit', '?')
            s_short = {'Hearts': '♥', 'Diamonds': '♦', 'Clubs': '♣', 'Spades': '♠'}.get(s, s)
            card_strs.append(f"{r}{s_short}")
        parts.append(f"cards: {' '.join(card_strs)}")
    
    return ' | '.join(parts)


def _summarize_battle_moves(moves: list) -> str:
    """Summarize battle moves."""
    if not moves:
        return "(none)"
    parts = []
    for m in moves:
        name = m.get('name', '?')
        value = m.get('value', '?')
        played_round = m.get('played_round')
        status = f" (played R{played_round})" if played_round is not None else ""
        parts.append(f"{name}({value}){status}")
    return ', '.join(parts)


def _compute_resource_summary(figures: list) -> str:
    """Compute resource balance (produced vs required) and identify deficit figures.
    
    Uses the same iterative deficit algorithm as the server:
    figures in deficit stop producing, which may cascade.
    """
    if not figures:
        return "\n=== RESOURCE BALANCE === (no figures)"
    
    # Compute totals
    total_produces = {}
    total_requires = {}
    for fig in figures:
        for res, amt in (fig.get('produces') or {}).items():
            if amt:
                total_produces[res] = total_produces.get(res, 0) + amt
        for res, amt in (fig.get('requires') or {}).items():
            if amt:
                total_requires[res] = total_requires.get(res, 0) + amt
    
    # Iterative deficit: exclude production from figures whose requirements aren't met
    excluded = set()
    stable = False
    while not stable:
        stable = True
        effective_produces = {}
        for i, fig in enumerate(figures):
            if i in excluded:
                continue
            for res, amt in (fig.get('produces') or {}).items():
                if amt:
                    effective_produces[res] = effective_produces.get(res, 0) + amt
        for i, fig in enumerate(figures):
            if i in excluded:
                continue
            for res in (fig.get('requires') or {}):
                if total_requires.get(res, 0) > effective_produces.get(res, 0):
                    excluded.add(i)
                    stable = False
                    break
    
    # Build summary
    lines = ["\n=== RESOURCE BALANCE ==="]
    all_resources = sorted(set(list(total_produces.keys()) + list(total_requires.keys())))
    for res in all_resources:
        prod = effective_produces.get(res, 0)
        req = total_requires.get(res, 0)
        status = "OK" if prod >= req else f"⚠️ DEFICIT (short by {req - prod})"
        lines.append(f"  {res}: produced={prod}, required={req} — {status}")
    
    # List deficit figures
    deficit_figs = [figures[i]['name'] for i in excluded]
    if deficit_figs:
        lines.append(f"  🚨 FIGURES IN DEFICIT (cannot advance, auto-lose battles): {', '.join(deficit_figs)}")
        lines.append(f"  ⚠️ DO NOT BUILD more figures that need these resources — fix the deficit first!")
    else:
        lines.append(f"  ✅ No deficits — all resource requirements met.")
    
    return '\n'.join(lines)


def compute_resource_totals(figures: list) -> tuple:
    """Return (effective_produces, total_requires) dicts after iterative deficit exclusion."""
    total_requires = {}
    for fig in figures:
        for res, amt in (fig.get('requires') or {}).items():
            if amt:
                total_requires[res] = total_requires.get(res, 0) + amt
    
    excluded = set()
    stable = False
    while not stable:
        stable = True
        effective = {}
        for i, fig in enumerate(figures):
            if i in excluded:
                continue
            for res, amt in (fig.get('produces') or {}).items():
                if amt:
                    effective[res] = effective.get(res, 0) + amt
        for i, fig in enumerate(figures):
            if i in excluded:
                continue
            for res in (fig.get('requires') or {}):
                if total_requires.get(res, 0) > effective.get(res, 0):
                    excluded.add(i)
                    stable = False
                    break
    
    return effective, total_requires


def _analyze_opponent_threats(game_dict, ai_player, opponent):
    """Analyze what the opponent might have based on visible information."""
    lines = ["\n=== OPPONENT THREAT ANALYSIS ==="]

    opp_main = len([c for c in opponent.get('main_hand', [])
                     if not c.get('part_of_figure') and not c.get('part_of_battle_move')])
    opp_side = len([c for c in opponent.get('side_hand', [])
                     if not c.get('part_of_figure') and not c.get('part_of_battle_move')])

    # Count cards committed to figures (both players) and in AI's free hand
    committed = {}  # rank → count
    for p in game_dict.get('players', []):
        for fig in p.get('figures', []):
            for ctf in fig.get('cards_to_figure', []):
                rank = ctf.get('card_rank', '?')
                committed[rank] = committed.get(rank, 0) + 1

    ai_hand = {}
    for c in ai_player.get('main_hand', []):
        if not c.get('part_of_figure') and not c.get('part_of_battle_move'):
            ai_hand[c.get('rank', '?')] = ai_hand.get(c.get('rank', '?'), 0) + 1
    for c in ai_player.get('side_hand', []):
        if not c.get('part_of_figure') and not c.get('part_of_battle_move'):
            ai_hand[c.get('rank', '?')] = ai_hand.get(c.get('rank', '?'), 0) + 1

    # Key card threat analysis (8 of each main-card rank in game)
    key_rank_copies = 8
    key_info = [
        ('K', 'Call King(19), King castle, Infinite Hammer'),
        ('A', 'Call Military(up to 23 with upgraded no-deficit military), military build, Invader Swap'),
        ('Q', 'Block(nullify round), Temple, Blitzkrieg'),
        ('J', 'Call Villager(up to 18 in 2-copy deck), Farm build, Peasant War'),
        ('10', 'Dagger(10), strongest guaranteed move'),
        ('9', 'Dagger(9), All Seeing Eye'),
    ]

    threat_lines = []
    for rank, threats in key_info:
        total = key_rank_copies
        in_figs = committed.get(rank, 0)
        in_ai = ai_hand.get(rank, 0)
        max_opp = max(0, min(total - in_figs - in_ai, opp_main))
        if max_opp > 0:
            threat_lines.append(f"  {rank}: opponent could have up to {max_opp} → {threats}")
        elif rank in ('K', 'A', 'Q'):
            threat_lines.append(f"  {rank}: ALL accounted for — opponent CANNOT have any")

    if threat_lines:
        lines.append("Key card tracking (8 of each main-card rank exist):")
        lines.extend(threat_lines)

    # Opponent's potential Call moves based on their figures
    opp_figures = opponent.get('figures', [])
    call_warnings = []
    for fig in opp_figures:
        field = fig.get('field', '?')
        power = _est_power(fig)
        name = fig.get('name', '?')
        suit = fig.get('suit', '?')

        if field == 'castle':
            if committed.get('K', 0) + ai_hand.get('K', 0) < key_rank_copies:
                call_warnings.append(
                    f"  ⚠️ Call King → {name} ({suit}): up to {power + 4} power")
        elif field == 'military':
            if committed.get('A', 0) + ai_hand.get('A', 0) < key_rank_copies:
                call_warnings.append(
                    f"  ⚠️ Call Military → {name} ({suit}): up to {power + 3} power")
        elif field == 'village':
            if committed.get('J', 0) + ai_hand.get('J', 0) < key_rank_copies:
                healer_buff = sum(4 for f in opp_figures
                                  if f.get('buffs_allies') and f.get('suit') == suit)
                total_power = power + healer_buff + 1
                buff_note = f" +{healer_buff} healer" if healer_buff else ""
                call_warnings.append(
                    f"  ⚠️ Call Villager → {name} ({suit}, base≈{power}{buff_note}): up to {total_power} power")

    if call_warnings:
        lines.append("Opponent's potential Call moves in battle:")
        lines.extend(call_warnings)

    # Spell threat awareness
    spell_threats = []
    ceasefire = game_dict.get('ceasefire_active', False)
    if not ceasefire and opp_main >= 2:
        counterable = []
        if max(0, key_rank_copies - committed.get('Q', 0) - ai_hand.get('Q', 0)) >= 2:
            counterable.append("Blitzkrieg(2×Q)")
        if max(0, key_rank_copies - committed.get('A', 0) - ai_hand.get('A', 0)) >= 2:
            counterable.append("Invader Swap(2×A)")
        if counterable:
            spell_threats.append(f"  Counterable tactics: {', '.join(counterable)}")
    if opp_side >= 2:
        spell_threats.append("  Enchantments: Poison(−6) or Health Boost(+6) possible")
    if opp_side >= 4:
        spell_threats.append("  ⚠️ Explosion possible — could destroy one of your figures!")

    if spell_threats:
        lines.append("Possible opponent spells:")
        lines.extend(spell_threats)

    return '\n'.join(lines)
