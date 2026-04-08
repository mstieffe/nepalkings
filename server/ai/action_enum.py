# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
Action enumerator for the AI opponent.

Determines the current game phase and lists all legal actions
the AI can take, formatted for the LLM to choose from.
"""
import logging
from ai.figure_recipes import find_buildable_figures

logger = logging.getLogger('nepalkings.ai.actions')


def _has_active_infinite_hammer(game_dict, ai_player):
    """Check if the AI has an active Infinite Hammer spell from active_spells in game_dict."""
    for spell in game_dict.get('active_spells', []):
        if ('Infinite Hammer' in spell.get('spell_name', '')
                and spell.get('player_id') == ai_player.get('id')
                and spell.get('is_active')):
            return True
    return False


def _est_power(fig):
    """Estimate figure power (sum of card values, castle=15)."""
    if not fig:
        return 0
    if fig.get('field') == 'castle':
        return 15
    cards = fig.get('cards_to_figure', [])
    return sum(c.get('card_value', c.get('value', 0)) for c in cards)


def detect_phase(game_dict: dict, ai_player_id: int) -> str:
    """
    Determine the current game phase from the AI player's perspective.
    Returns one of: 'normal_turn', 'select_defender', 'battle_decision',
    'battle_shop', 'battle_round', 'finish_battle', 'counter_spell',
    or None if AI doesn't need to act.
    """
    # Game over?
    if game_dict.get('state') == 'finished':
        return None

    # Post-battle: fold_winner_id is set but battle_confirmed still True
    # → the winner needs to pick a card (finish_battle_pick_card)
    #   or it's a draw (finish_battle_draw)
    # These are handled inline in the AI worker, not as separate phases.
    # But if the human called finish_battle first (setting fold_winner_id),
    # the AI needs to call finish_battle too and then handle the result.
    if game_dict.get('fold_winner_id') and game_dict.get('battle_confirmed'):
        # The battle was resolved. Winner picks a card.
        if game_dict.get('fold_winner_id') == ai_player_id:
            return 'post_battle_pick'
        # AI lost — nothing to do (winner picks)
        return None

    # Spell counter — opponent cast a counterable spell
    if game_dict.get('waiting_for_counter_player_id') == ai_player_id:
        return 'counter_spell'

    # Battle round — AI's turn to play a battle move
    if (game_dict.get('battle_confirmed') and
            game_dict.get('battle_turn_player_id') == ai_player_id):
        # Check if all 3 rounds are done (both players played/skipped each round)
        if _all_battle_rounds_done(game_dict, ai_player_id):
            return 'finish_battle'
        return 'battle_round'

    # Also check finish_battle when it's NOT the AI's turn but rounds are done
    if (game_dict.get('battle_confirmed') and
            _all_battle_rounds_done(game_dict, ai_player_id) and
            not game_dict.get('fold_winner_id')):
        return 'finish_battle'

    # Battle shop — battle confirmed, AI hasn't confirmed moves yet
    if game_dict.get('battle_confirmed'):
        moves_conf = game_dict.get('battle_moves_confirmed') or {}
        if str(ai_player_id) not in moves_conf:
            return 'battle_shop'
        # Battle is in progress but it's not the AI's battle turn — wait
        return None

    # Battle decision — advancing + defending figures set, AI hasn't decided
    if (game_dict.get('advancing_figure_id') and
            game_dict.get('defending_figure_id') and
            not game_dict.get('battle_confirmed')):
        decisions = game_dict.get('battle_decisions') or {}
        if str(ai_player_id) not in decisions:
            # Server enforces invader-first: defender can't decide until invader
            # has chosen 'battle'. If AI is the defender, wait for invader.
            advancing_pid = game_dict.get('advancing_player_id')
            if advancing_pid != ai_player_id:
                # AI is defender — check invader has decided 'battle'
                if decisions.get(str(advancing_pid)) != 'battle':
                    return None  # Wait for invader to decide first
            return 'battle_decision'
        # AI already decided but opponent hasn't — wait
        return None

    # Select defender — opponent advanced, no defending figure, AI is the invader  
    # The INVADER selects which of the OPPONENT's figures to fight
    if (game_dict.get('advancing_figure_id') and
            not game_dict.get('defending_figure_id') and
            game_dict.get('advancing_player_id') == ai_player_id and
            game_dict.get('turn_player_id') == ai_player_id):
        return 'select_defender'

    # Normal turn — it's AI's turn
    if game_dict.get('turn_player_id') == ai_player_id:
        return 'normal_turn'

    return None


def _all_battle_rounds_done(game_dict: dict, ai_player_id: int) -> bool:
    """Check if all 3 battle rounds (0, 1, 2) have been played/skipped by both players."""
    if not game_dict.get('battle_confirmed'):
        return False

    battle_moves = game_dict.get('battle_moves') or []
    skipped = game_dict.get('battle_skipped_rounds') or {}

    # Get both player IDs
    player_ids = [p['id'] for p in game_dict.get('players') or []]
    if len(player_ids) != 2:
        return False

    for pid in player_ids:
        played_rounds = {m['played_round'] for m in battle_moves
                         if m.get('player_id') == pid and m.get('played_round') is not None}
        skipped_rounds = set(skipped.get(str(pid), []))
        covered = played_rounds | skipped_rounds
        if not {0, 1, 2}.issubset(covered):
            return False

    return True


def enumerate_actions(game_dict: dict, ai_player_id: int, phase: str) -> list:
    """
    List all legal actions for the AI in the given phase.
    
    Returns a list of dicts:
    [{'id': 1, 'type': 'build_figure', 'description': '...', 'params': {...}}, ...]
    """
    ai_player = _get_ai_player(game_dict, ai_player_id)
    opponent = _get_opponent(game_dict, ai_player_id)

    if phase == 'normal_turn':
        return _enum_normal_turn(game_dict, ai_player, opponent)
    elif phase == 'select_defender':
        return _enum_select_defender(game_dict, ai_player, opponent)
    elif phase == 'battle_decision':
        return _enum_battle_decision(game_dict, ai_player, opponent)
    elif phase == 'battle_shop':
        return _enum_battle_shop(game_dict, ai_player, opponent)
    elif phase == 'battle_round':
        return _enum_battle_round(game_dict, ai_player, opponent)
    elif phase == 'counter_spell':
        return _enum_counter_spell(game_dict, ai_player, opponent)
    else:
        return []


def format_actions_for_llm(actions: list) -> str:
    """Format action list as numbered text for LLM prompt."""
    if not actions:
        return "No actions available."
    lines = ["Available actions:"]
    for a in actions:
        lines.append(f"  {a['id']}. [{a['type']}] {a['description']}")
    return '\n'.join(lines)


# ── Phase-specific enumerators ──────────────────────────────────


def _enum_normal_turn(game_dict, ai_player, opponent):
    """Enumerate actions for a normal turn."""
    actions = []
    action_id = 1

    # Check if Infinite Hammer is active — restricts actions to build + end only
    infinite_hammer_active = _has_active_infinite_hammer(game_dict, ai_player)

    # Compute current resource balance for deficit analysis
    from ai.game_state import compute_resource_totals
    current_produces, current_requires = compute_resource_totals(ai_player.get('figures', []))

    # 1) Build figures
    buildable = find_buildable_figures(
        ai_player.get('main_hand', []),
        ai_player.get('side_hand', []),
        ai_player.get('figures', []),
    )
    # Build lookup of card details from hand for enriching build descriptions
    card_lookup = {}
    for c in ai_player.get('main_hand', []):
        card_lookup[c['id']] = c
    for c in ai_player.get('side_hand', []):
        card_lookup[c['id']] = c

    for fig in buildable:
        recipe = fig['recipe']
        # Show what cards are being consumed so AI can evaluate the trade-off
        card_strs = []
        total_val = 0
        for c in fig.get('cards', []):
            card_detail = card_lookup.get(c.get('id'), {})
            r = card_detail.get('rank', '?')
            s = card_detail.get('suit', '?')[:1]
            v = card_detail.get('value', 0)
            card_strs.append(f"{r}{s}({v})")
            total_val += v
        cards_desc = '+'.join(card_strs) if card_strs else '?'
        
        # Check if building this figure would cause or worsen a deficit
        deficit_warn = _check_build_deficit_impact(
            fig, ai_player.get('figures', []), current_produces, current_requires)
        
        actions.append({
            'id': action_id,
            'type': 'build_figure',
            'description': (f"Build {fig['display_name']} [cards: {cards_desc}, power={total_val}] "
                            f"— produces: {fig['produces']}, requires: {fig['requires']}"
                            f"{deficit_warn}"),
            'params': {
                'family_name': recipe['family_name'],
                'field': recipe['field'],
                'color': recipe['color'],
                'name': fig['name'],
                'suit': fig['suit'],
                'description': '',
                'upgrade_family_name': recipe.get('upgrade_family_name'),
                'produces': fig['produces'],
                'requires': fig['requires'],
                'cards': fig['cards'],
                'instant_charge_advance': recipe.get('special_flags', {}).get('instant_charge', False),
                'cannot_be_blocked': recipe.get('special_flags', {}).get('cannot_be_blocked', False),
                'rest_after_attack': recipe.get('special_flags', {}).get('rest_after_attack', False),
            },
        })
        action_id += 1

    # 2) Advance a figure (if ceasefire is off and AI has eligible figures)
    # Blocked during Infinite Hammer
    from ai.game_state import compute_resource_totals as _crt
    if not infinite_hammer_active and not game_dict.get('ceasefire_active') and not game_dict.get('advancing_figure_id'):
        resting = set(game_dict.get('resting_figure_ids', []))
        # Check battle modifier restrictions on advance
        modifiers = game_dict.get('battle_modifier') if isinstance(game_dict.get('battle_modifier'), list) else []
        has_peasant_war = any(m.get('type') == 'Peasant War' for m in modifiers)
        has_civil_war = any(m.get('type') == 'Civil War' for m in modifiers)
        # Compute which figures are in deficit (cannot advance)
        _eff_prod, _tot_req = _crt(ai_player.get('figures', []))
        for fig in ai_player.get('figures', []):
            fig_id = fig['id']
            # Skip figures that can't attack or are resting
            if fig.get('cannot_attack'):
                continue
            if fig.get('cannot_defend') and fig.get('cannot_attack'):
                continue
            if fig_id in resting:
                continue
            # Peasant War / Civil War: only village figures can advance
            if (has_peasant_war or has_civil_war) and fig.get('field') != 'village':
                continue
            # Skip figures in resource deficit (server rejects advance)
            fig_reqs = fig.get('requires') or {}
            in_deficit = False
            for res in fig_reqs:
                if _tot_req.get(res, 0) > _eff_prod.get(res, 0):
                    in_deficit = True
                    break
            if in_deficit:
                continue
            power = _est_figure_power(fig)
            field = fig.get('field', '?')
            checkmate_warn = " ⚠️ CHECKMATE RISK" if fig.get('checkmate') else ""
            modifier_note = ""
            if has_peasant_war:
                modifier_note = " [PEASANT WAR: village only]"
            elif has_civil_war:
                modifier_note = " [CIVIL WAR: village only]"
            turns = ai_player.get('turns_left', '?')
            is_invader = (game_dict.get('invader_player_id') == ai_player.get('id'))
            defender_warn = "" if is_invader else " ⚠️ You are DEFENDER — the invader MUST advance on their last turn. Let them come to you! Only advance if you have an overwhelming advantage."
            actions.append({
                'id': action_id,
                'type': 'advance_figure',
                'description': (f"Advance {fig['name']} ({field}, power≈{power}) — "
                                f"costs ALL {turns} remaining turns{checkmate_warn}{modifier_note}{defender_warn}"),
                'params': {'figure_id': fig_id},
            })
            action_id += 1

    # 2b) Counter-advance — opponent has advanced but AI hasn't responded yet.
    # Blitzkrieg prevents counter-advance; otherwise AI may choose to counter-advance.
    elif (not infinite_hammer_active and not game_dict.get('ceasefire_active') and
          game_dict.get('advancing_figure_id') and
          game_dict.get('advancing_player_id') != ai_player.get('id') and
          not game_dict.get('defending_figure_id')):
        modifiers = game_dict.get('battle_modifier') if isinstance(game_dict.get('battle_modifier'), list) else []
        has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)
        has_peasant_war = any(m.get('type') == 'Peasant War' for m in modifiers)
        has_civil_war = any(m.get('type') == 'Civil War' for m in modifiers)
        # Check if the opponent's advancing figure has cannot_be_blocked
        adv_fig_id = game_dict.get('advancing_figure_id')
        adv_fig = next((f for f in opponent.get('figures', []) if f['id'] == adv_fig_id), None)
        advancing_cannot_be_blocked = adv_fig.get('cannot_be_blocked', False) if adv_fig else False
        if not has_blitzkrieg and not advancing_cannot_be_blocked:
            resting = set(game_dict.get('resting_figure_ids', []))
            _eff_prod, _tot_req = _crt(ai_player.get('figures', []))
            for fig in ai_player.get('figures', []):
                fig_id = fig['id']
                if fig.get('cannot_defend'):
                    continue
                if fig_id in resting:
                    continue
                if (has_peasant_war or has_civil_war) and fig.get('field') != 'village':
                    continue
                fig_reqs = fig.get('requires') or {}
                in_deficit = False
                for res in fig_reqs:
                    if _tot_req.get(res, 0) > _eff_prod.get(res, 0):
                        in_deficit = True
                        break
                if in_deficit:
                    continue
                power = _est_figure_power(fig)
                field = fig.get('field', '?')
                actions.append({
                    'id': action_id,
                    'type': 'advance_figure',
                    'description': (f"Counter-advance {fig['name']} ({field}, power≈{power}) — "
                                    f"defend against opponent's advancing figure"),
                    'params': {'figure_id': fig_id},
                })
                action_id += 1

    # 3) Cast spells — blocked during Infinite Hammer
    if not infinite_hammer_active:
        spell_actions, action_id = _enum_spells(game_dict, ai_player, opponent, action_id)
        actions.extend(spell_actions)

    # 4) Change cards — blocked during Infinite Hammer
    if not infinite_hammer_active:
        free_cards = [c for c in ai_player.get('main_hand', [])
                      if not c.get('part_of_figure') and not c.get('part_of_battle_move')]
        low = sum(1 for c in free_cards if c.get('rank') in ('7', '8'))
        total_free = len(free_cards)
        actions.append({
            'id': action_id,
            'type': 'change_cards',
            'description': f"Change cards — swap low-value cards for new ones ({low} low-value of {total_free} free cards)",
            'params': {},
        })
        action_id += 1

    # 5) End Infinite Hammer — only available when active
    if infinite_hammer_active:
        build_count = sum(1 for a in actions if a['type'] == 'build_figure')
        if build_count > 0:
            desc = (f"⚠️ End Infinite Hammer mode — DO NOT choose this while builds remain! "
                    f"You still have {build_count} builds available. Build ALL of them first!")
        else:
            desc = "End Infinite Hammer mode — no more builds available, safe to end."
        actions.append({
            'id': action_id,
            'type': 'end_infinite_hammer',
            'description': desc,
            'params': {},
        })
        action_id += 1

    return actions


def _enum_select_defender(game_dict, ai_player, opponent):
    """
    The AI (as invader) selects which OPPONENT figure to fight.
    Includes power estimates to help the LLM choose strategically.
    """
    actions = []
    action_id = 1

    # Find AI's advancing figure for power comparison
    adv_fig_id = game_dict.get('advancing_figure_id')
    ai_power = 0
    for fig in ai_player.get('figures', []):
        if fig['id'] == adv_fig_id:
            ai_power = _est_figure_power(fig)
            break

    # Check battle modifier restrictions on defender selection
    modifiers = game_dict.get('battle_modifier') if isinstance(game_dict.get('battle_modifier'), list) else []
    has_peasant_war = any(m.get('type') == 'Peasant War' for m in modifiers)
    has_civil_war = any(m.get('type') == 'Civil War' for m in modifiers)

    # For Civil War, determine the color of the AI's advancing figure
    civil_war_color = None
    if has_civil_war:
        for fig in ai_player.get('figures', []):
            if fig['id'] == adv_fig_id:
                civil_war_color = fig.get('color')
                break

    checkmate_fallback = []
    for fig in opponent.get('figures', []):
        # Skip figures that can't be targeted
        if fig.get('cannot_be_targeted'):
            continue
        # Checkmate figures are normally skipped; keep as fallback
        if fig.get('checkmate'):
            checkmate_fallback.append(fig)
            continue
        # Peasant War: only village figures can be selected
        if has_peasant_war and fig.get('field') != 'village':
            continue
        # Civil War: only village figures of matching color
        if has_civil_war:
            if fig.get('field') != 'village':
                continue
            if civil_war_color and fig.get('color') != civil_war_color:
                continue
        fig_power = _est_figure_power(fig)
        diff = ai_power - fig_power
        field = fig.get('field', '?')
        abilities = []
        if fig.get('must_be_attacked'):
            abilities.append('must-attack-first')
        if fig.get('cannot_attack'):
            abilities.append('cannot-attack')
        ability_str = f" [{', '.join(abilities)}]" if abilities else ""

        actions.append({
            'id': action_id,
            'type': 'select_defender',
            'description': (f"Attack opponent's {fig['name']} ({field}, power≈{fig_power}, "
                            f"diff={diff:+d}){ability_str}"),
            'params': {'figure_id': fig['id']},
        })
        action_id += 1

    # Fallback: if no non-checkmate targets, allow checkmate figures
    if not actions and checkmate_fallback:
        for fig in checkmate_fallback:
            fig_power = _est_figure_power(fig)
            diff = ai_power - fig_power
            field = fig.get('field', '?')
            actions.append({
                'id': action_id,
                'type': 'select_defender',
                'description': (f"Attack opponent's {fig['name']} ({field}, power≈{fig_power}, "
                                f"diff={diff:+d}) [CHECKMATE — exposed!]"),
                'params': {'figure_id': fig['id']},
            })
            action_id += 1

    return actions


def _est_figure_power(fig):
    """Quick power estimate: castle=15, else sum of card values."""
    if fig.get('field') == 'castle':
        return 15
    cards = fig.get('cards_to_figure', [])
    return sum(c.get('card_value', c.get('value', 0)) for c in cards)


def _check_build_deficit_impact(new_fig, existing_figures, current_produces, current_requires):
    """Check if building a figure would cause or worsen resource deficits.
    Returns a warning string (empty if no issue)."""
    new_requires = new_fig.get('requires') or {}
    new_produces = new_fig.get('produces') or {}
    
    if not new_requires and new_produces:
        # Pure producer (e.g., castle) — always good
        prod_str = ', '.join(f"+{v} {k}" for k, v in new_produces.items() if v)
        return f" ✅ Adds resources: {prod_str}"
    
    # Simulate adding this figure
    sim_requires = dict(current_requires)
    sim_produces = dict(current_produces)
    for res, amt in new_requires.items():
        if amt:
            sim_requires[res] = sim_requires.get(res, 0) + amt
    for res, amt in new_produces.items():
        if amt:
            sim_produces[res] = sim_produces.get(res, 0) + amt
    
    # Check for new deficits
    warnings = []
    for res in sim_requires:
        needed = sim_requires.get(res, 0)
        available = sim_produces.get(res, 0)
        if needed > available:
            was_deficit = current_requires.get(res, 0) > current_produces.get(res, 0)
            if was_deficit:
                warnings.append(f"{res} already in deficit")
            else:
                warnings.append(f"CREATES {res} deficit (need {needed}, have {available})")
    
    if warnings:
        return f" ⚠️ DEFICIT WARNING: {'; '.join(warnings)} — figure CANNOT advance, auto-loses battles!"
    return ""


def _enum_battle_decision(game_dict, ai_player, opponent):
    """AI decides to fold or battle, with rich context about the figures involved."""
    # Find the advancing and defending figures
    adv_fig_id = game_dict.get('advancing_figure_id')
    def_fig_id = game_dict.get('defending_figure_id')
    is_invader = game_dict.get('advancing_player_id') == ai_player['id']

    ai_fig = None
    opp_fig = None
    all_figs = ai_player.get('figures', []) + opponent.get('figures', [])
    for f in all_figs:
        if f['id'] == adv_fig_id:
            if is_invader:
                ai_fig = f
            else:
                opp_fig = f
        elif f['id'] == def_fig_id:
            if is_invader:
                opp_fig = f
            else:
                ai_fig = f

    ai_power = _est_power(ai_fig)
    opp_power = _est_power(opp_fig)
    ai_fig_name = ai_fig['name'] if ai_fig else '?'
    opp_fig_name = opp_fig['name'] if opp_fig else '?'

    # Count battle-usable cards in hand
    battle_cards = [c for c in ai_player.get('main_hand', [])
                    if not c.get('part_of_figure') and not c.get('part_of_battle_move')
                    and c.get('rank') in ('K', 'A', 'Q', 'J', '7', '8', '9', '10')]
    top_cards = sorted(battle_cards, key=lambda c: c.get('value', 0), reverse=True)[:3]
    top_str = ', '.join(f"{c['rank']}({c.get('value', 0)})" for c in top_cards) if top_cards else 'none'
    total_battle_value = sum(c.get('value', 0) for c in top_cards)

    role = "INVADER (you advanced)" if is_invader else "DEFENDER (opponent advanced toward you)"
    context = (f"You are {role}. "
               f"YOUR figure: {ai_fig_name} (power≈{ai_power}). "
               f"OPPONENT figure: {opp_fig_name} (power≈{opp_power}). "
               f"Power diff: {ai_power - opp_power:+d}. "
               f"Your top 3 battle cards: {top_str} (total≈{total_battle_value}). "
               f"Estimated total advantage: {ai_power - opp_power + total_battle_value:+d}.")

    actions = [
        {
            'id': 1,
            'type': 'battle_decision',
            'description': f"BATTLE — fight! {context}",
            'params': {'decision': 'battle'},
        },
        {
            'id': 2,
            'type': 'battle_decision',
            'description': f"FOLD — saves your {ai_fig_name} but opponent gets 10 free points. Fold if your figure is valuable and you have weak battle cards.",
            'params': {'decision': 'fold'},
        },
    ]
    return actions


def _enum_battle_shop(game_dict, ai_player, opponent):
    """
    AI buys battle moves from hand cards, can gamble/combine, and confirms.
    Returns buy + gamble + combine + confirm actions.
    """
    actions = []
    action_id = 1
    
    # Get current battle moves for the AI
    ai_moves = [m for m in game_dict.get('battle_moves', []) 
                if m.get('player_id') == ai_player['id']]
    num_moves = len(ai_moves)
    
    # ── Build lookup of AI's figures for Call power estimation ──
    ai_figures = ai_player.get('figures', [])
    RED_SUITS = {'Hearts', 'Diamonds'}
    BLACK_SUITS = {'Clubs', 'Spades'}

    def _call_power(rank, suit, family_name):
        """Estimate effective power of a Call move with best matching figure.
        Called figures bring their base power + healer buffs only (NOT support bonus)."""
        base = {'K': 4, 'A': 3, 'J': 1}.get(rank, 0)
        card_color = 'red' if suit in RED_SUITS else 'black'
        field_map = {'Call King': 'castle', 'Call Military': 'military', 'Call Villager': 'village'}
        target_field = field_map.get(family_name)
        best_total = 0
        best_fig_name = None
        for fig in ai_figures:
            if fig.get('field') != target_field:
                continue
            fig_suit = fig.get('suit', '')
            fig_color = 'red' if fig_suit in RED_SUITS else 'black'
            if fig_color != card_color:
                continue
            # Base figure power
            power = _est_power(fig)
            # Healer buff: +4 per same-suit Healer for village figures
            # (Healer buffs are added to base power, so called villagers benefit)
            if target_field == 'village':
                for other in ai_figures:
                    if other.get('suit') == fig_suit and 'Healer' in other.get('name', ''):
                        power += 4
            suit_match = suit == fig_suit
            total = power + (base if suit_match else 0)
            if total > best_total:
                best_total = total
                best_fig_name = fig.get('name', '?')
        if best_total > 0:
            return best_total, best_fig_name
        return base, None

    if num_moves < 3:
        # Can buy more moves — list buyable cards
        available = [c for c in ai_player.get('main_hand', [])
                     if not c.get('part_of_figure') and not c.get('part_of_battle_move')]
        
        battle_family = {
            'J': 'Call Villager',
            'Q': 'Block',
            'A': 'Call Military',
            'K': 'Call King',
        }
        
        for card in available:
            rank = card['rank']
            if rank in battle_family:
                family_name = battle_family[rank]
            elif rank in ['7', '8', '9', '10']:
                family_name = 'Dagger'
            else:
                continue  # Side cards can't be battle moves
            
            card_value = card.get('value', 0)
            card_suit = card['suit']
            
            # Build descriptive text based on move type
            if family_name in ('Call King', 'Call Military', 'Call Villager'):
                eff_power, fig_name = _call_power(rank, card_suit, family_name)
                if fig_name:
                    desc = f"Buy {family_name} ({rank} of {card_suit}) — calls {fig_name}, effective power≈{eff_power}"
                else:
                    desc = f"Buy {family_name} ({rank} of {card_suit}) — no matching figure, power={card_value}"
            elif family_name == 'Block':
                desc = f"Buy Block (Q of {card_suit}) — NULLIFIES entire round (both sides 0)"
            else:
                desc = f"Buy Dagger ({rank} of {card_suit}) — power={card_value}"
            
            actions.append({
                'id': action_id,
                'type': 'buy_battle_move',
                'description': desc,
                'params': {
                    'card_id': card['id'],
                    'family_name': family_name,
                    'card_type': 'main',
                    'suit': card_suit,
                    'rank': rank,
                    'value': card_value,
                },
            })
            action_id += 1
    
    # ── Combine: merge two same-colour Daggers into Double Dagger ──
    dagger_moves = [m for m in ai_moves if m.get('family_name') == 'Dagger']
    if len(dagger_moves) >= 2:
        for i in range(len(dagger_moves)):
            for j in range(i + 1, len(dagger_moves)):
                m_a, m_b = dagger_moves[i], dagger_moves[j]
                suit_a = m_a.get('suit', '')
                suit_b = m_b.get('suit', '')
                color_a = 'red' if suit_a in RED_SUITS else 'black'
                color_b = 'red' if suit_b in RED_SUITS else 'black'
                if color_a == color_b:
                    combined_val = m_a.get('value', 0) + m_b.get('value', 0)
                    actions.append({
                        'id': action_id,
                        'type': 'combine_battle_moves',
                        'description': f"Combine Dagger({m_a.get('value',0)}) + Dagger({m_b.get('value',0)}) → Double Dagger (power={combined_val}) — frees 1 move slot!",
                        'params': {
                            'move_id_a': m_a['id'],
                            'move_id_b': m_b['id'],
                        },
                    })
                    action_id += 1
    
    # ── Gamble: sacrifice 1 weak move → draw 2 random (max 3 per battle) ──
    gamble_counts = game_dict.get('battle_gamble_counts') or {}
    already_gambled = gamble_counts.get(str(ai_player['id']), 0) >= 3
    if ai_moves and not already_gambled:
        for move in ai_moves:
            if move.get('family_name') == 'Double Dagger':
                continue  # Don't gamble double daggers
            move_val = move.get('value', 0)
            move_name = move.get('family_name', move.get('name', '?'))
            # Flag unmatched Call moves as prime gamble targets
            family = move.get('family_name', '')
            if family in ('Call King', 'Call Military', 'Call Villager'):
                rank_map = {'Call King': 'K', 'Call Military': 'A', 'Call Villager': 'J'}
                rank = rank_map.get(family, '')
                card_suit = move.get('suit', '')
                eff_power, fig_name = _call_power(rank, card_suit, family)
                if fig_name:
                    desc = f"Gamble: sacrifice {move_name}(calls {fig_name}, eff_power≈{eff_power}) → draw 2 random. BAD gamble — keep this Call!"
                else:
                    base = {'K': 4, 'A': 3, 'J': 1}.get(rank, 0)
                    desc = f"Gamble: sacrifice {move_name}(NO matching figure, value={base}) → draw 2 random. GREAT gamble target!"
            elif move_val >= 9:
                desc = f"Gamble: sacrifice {move_name}(value={move_val}) → draw 2 random. Risky — {move_val} is already strong."
            else:
                desc = f"Gamble: sacrifice {move_name}(value={move_val}) → draw 2 random. Decent gamble — low value card."
            actions.append({
                'id': action_id,
                'type': 'gamble_battle_move',
                'description': desc,
                'params': {
                    'battle_move_id': move['id'],
                },
            })
            action_id += 1
    
    # Only offer confirm when the AI has 3+ moves (server requires exactly 3).
    # If AI can't reach 3 (no buy, no gamble), offer confirm as deadlock escape.
    has_buy_actions = any(a['type'] == 'buy_battle_move' for a in actions)
    has_gamble_actions = any(a['type'] == 'gamble_battle_move' for a in actions)
    has_combine_actions = any(a['type'] == 'combine_battle_moves' for a in actions)
    if num_moves >= 3:
        actions.append({
            'id': action_id,
            'type': 'confirm_battle_moves',
            'description': f"CONFIRM battle moves ({num_moves}/3 ready) — finalize and start battle!",
            'params': {},
        })
        action_id += 1
    elif not has_buy_actions and not has_gamble_actions:
        # True deadlock — no way to reach 3 moves, offer confirm as escape hatch
        actions.append({
            'id': action_id,
            'type': 'confirm_battle_moves',
            'description': f"CONFIRM battle moves ({num_moves}/3 — can't buy more, server may reject)",
            'params': {},
        })
        action_id += 1
    else:
        # < 3 moves but CAN still buy/gamble — tell LLM it must reach 3
        if has_gamble_actions and not has_buy_actions:
            # Mark gamble actions as mandatory
            for a in actions:
                if a['type'] == 'gamble_battle_move':
                    a['description'] = "⚠️ MUST GAMBLE to reach 3 moves! " + a['description']
    
    return actions


_CALL_FIELD_MAP = {
    'Call Villager': 'village',
    'Call Military': 'military',
    'Call King': 'castle',
}

_RED_SUITS = {'Hearts', 'Diamonds'}
_BLACK_SUITS = {'Clubs', 'Spades'}


def _figure_power_from_dict(fig):
    """Compute base power from a serialized figure dict."""
    if fig.get('field') == 'castle':
        return 15
    cards = fig.get('cards', fig.get('cards_to_figure', []))
    return sum(c.get('value', 0) for c in cards)


def _get_best_call_figure(move, game_dict, ai_player):
    """Return the best eligible figure dict for a Call move, or None."""
    family = move.get('family_name', '')
    field_type = _CALL_FIELD_MAP.get(family)
    if not field_type:
        return None

    bm_suit = move.get('suit', '')
    bm_is_red = bm_suit in _RED_SUITS

    # IDs of figures already in battle
    fighting_ids = set()
    for attr in ('advancing_figure_id', 'advancing_figure_id_2',
                 'defending_figure_id', 'defending_figure_id_2'):
        fid = game_dict.get(attr)
        if fid is not None:
            fighting_ids.add(fid)

    # IDs of figures already called in earlier rounds of this battle
    already_called_ids = set()
    for bm in game_dict.get('battle_moves', []):
        if bm.get('player_id') == ai_player['id'] and bm.get('played_round') is not None:
            cfid = bm.get('call_figure_id')
            if cfid is not None:
                already_called_ids.add(cfid)

    best_fig = None
    best_power = -1
    for fig in ai_player.get('figures', []):
        if fig.get('field') != field_type:
            continue
        if fig['id'] in fighting_ids:
            continue
        if fig['id'] in already_called_ids:
            continue
        # Colour check: red BM → red figure, black BM → black figure
        fig_suit = fig.get('suit', '')
        if bm_is_red and fig_suit not in _RED_SUITS:
            continue
        if not bm_is_red and fig_suit not in _BLACK_SUITS:
            continue
        power = _figure_power_from_dict(fig)
        if power > best_power:
            best_power = power
            best_fig = fig

    return best_fig


def _enum_battle_round(game_dict, ai_player, opponent):
    """AI plays a battle move or skips."""
    actions = []
    action_id = 1
    
    current_round = game_dict.get('battle_round', 0)
    
    # Get unplayed moves
    ai_moves = [m for m in game_dict.get('battle_moves', [])
                if m.get('player_id') == ai_player['id'] and m.get('played_round') is None]
    
    for move in ai_moves:
        family = move.get('family_name', '')
        params = {'battle_move_id': move['id']}

        # For Call moves, auto-select the best eligible figure
        call_fig = _get_best_call_figure(move, game_dict, ai_player) if family in _CALL_FIELD_MAP else None
        if call_fig:
            params['call_figure_id'] = call_fig['id']
            fig_power = _figure_power_from_dict(call_fig)
            combined = fig_power + (move.get('value', 0) or 0)
            desc = (f"Play {family} "
                    f"(card={move.get('value', '?')}) + "
                    f"{call_fig.get('name', '?')} (power={fig_power}) "
                    f"= {combined} total for round {current_round + 1}")
        elif family in _CALL_FIELD_MAP:
            # Call move but no eligible figure — only card value applies
            desc = (f"Play {family} "
                    f"(value={move.get('value', '?')}, NO eligible figure) "
                    f"for round {current_round + 1}")
        else:
            desc = (f"Play {family} "
                    f"(value={move.get('value', '?')}) "
                    f"for round {current_round + 1}")

        actions.append({
            'id': action_id,
            'type': 'play_battle_move',
            'description': desc,
            'params': params,
        })
        action_id += 1
    
    # Can only skip if no unplayed moves remain
    if not ai_moves:
        actions.append({
            'id': action_id,
            'type': 'skip_battle_turn',
            'description': "Skip this round (no moves left to play)",
            'params': {},
        })
        action_id += 1
    
    return actions


def _enum_counter_spell(game_dict, ai_player, opponent):
    """AI decides whether to allow or counter a pending spell.
    Enriched with spell details and counter-cost info."""
    pending_spell_id = game_dict.get('pending_spell_id')
    logger.info(f"Enumerating counter_spell actions (pending_spell_id={pending_spell_id})")

    # Get pending spell name from the DB (we're inside app_context)
    spell_name = '?'
    try:
        from models import ActiveSpell
        pending = ActiveSpell.query.get(pending_spell_id)
        if pending:
            spell_name = pending.spell_name
    except Exception as e:
        logger.warning(f"Failed to query spell name for id={pending_spell_id}: {e}")

    # Look up counter cost from known spell definitions
    _COUNTER_COSTS = {
        'Ceasefire': '7+8+9 or 8+9+10 same-color main cards',
        'Peasant War': '2× J same-color main cards',
        'Civil War': '2× 5 same-color side cards',
        'Invader Swap': '2× A same-color main cards',
        'Blitzkrieg': '2× Q same-color main cards',
    }
    counter_cost = _COUNTER_COSTS.get(spell_name, 'same cards as the original spell')

    # Check if AI has the counter cards
    _COUNTER_RANK_MAP = {
        'Peasant War': 'J', 'Blitzkrieg': 'Q', 'Invader Swap': 'A', 'Civil War': '5',
    }
    can_counter = False
    counter_cards_data = []
    rank_needed = _COUNTER_RANK_MAP.get(spell_name)

    free_main = [c for c in ai_player.get('main_hand', [])
                 if not c.get('part_of_figure') and not c.get('part_of_battle_move')]
    free_side = [c for c in ai_player.get('side_hand', [])
                 if not c.get('part_of_figure') and not c.get('part_of_battle_move')]

    if spell_name == 'Ceasefire':
        # Need 7+8+9 or 8+9+10 same color
        for color_suits in [('Hearts', 'Diamonds'), ('Clubs', 'Spades')]:
            color_cards = [c for c in free_main if c['suit'] in color_suits]
            ranks_available = {c['rank'] for c in color_cards}
            for seq in [('7', '8', '9'), ('8', '9', '10')]:
                if all(r in ranks_available for r in seq):
                    can_counter = True
                    for r in seq:
                        card = next(c for c in color_cards if c['rank'] == r)
                        counter_cards_data.append({'id': card['id'], 'rank': card['rank'],
                                                   'suit': card['suit'], 'value': card.get('value', 0)})
                    break
            if can_counter:
                break
    elif rank_needed:
        cards_pool = free_side if spell_name == 'Civil War' else free_main
        for color_suits in [('Hearts', 'Diamonds'), ('Clubs', 'Spades')]:
            matching = [c for c in cards_pool if c['rank'] == rank_needed and c['suit'] in color_suits]
            if len(matching) >= 2:
                can_counter = True
                for c in matching[:2]:
                    counter_cards_data.append({'id': c['id'], 'rank': c['rank'],
                                               'suit': c['suit'], 'value': c.get('value', 0)})
                break

    actions = [
        {
            'id': 1,
            'type': 'allow_spell',
            'description': f"Allow opponent's {spell_name} to take effect",
            'params': {'pending_spell_id': pending_spell_id},
        },
    ]

    if can_counter and counter_cards_data:
        card_desc = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in counter_cards_data)
        actions.append({
            'id': 2,
            'type': 'counter_spell',
            'description': f"Counter {spell_name} (costs: {card_desc}) — blocks spell, both lose cards but keep turns",
            'params': {
                'pending_spell_id': pending_spell_id,
                'counter_spell_name': spell_name,
                'counter_spell_type': 'tactics',
                'counter_spell_family_name': spell_name,
                'counter_cards': counter_cards_data,
            },
        })
    else:
        actions.append({
            'id': 2,
            'type': 'counter_spell',
            'description': f"Counter {spell_name} — ⚠️ You do NOT have the required cards ({counter_cost}). This will FAIL!",
            'params': {
                'pending_spell_id': pending_spell_id,
                'counter_spell_name': spell_name,
                'counter_spell_type': 'tactics',
                'counter_spell_family_name': spell_name,
                'counter_cards': [],
            },
        })

    logger.info(f"Counter spell enum: spell={spell_name}, can_counter={can_counter}, actions={len(actions)}")
    return actions

_RED_SUITS_SET = {'Hearts', 'Diamonds'}
_BLACK_SUITS_SET = {'Clubs', 'Spades'}


def _enum_spells(game_dict, ai_player, opponent, action_id):
    """
    Enumerate all castable spells from the AI's hand.
    Returns (actions_list, next_action_id).
    """
    actions = []
    ceasefire = game_dict.get('ceasefire_active', False)

    # Gather free (non-figure, non-battle-move) cards
    free_main = [c for c in ai_player.get('main_hand', [])
                 if not c.get('part_of_figure') and not c.get('part_of_battle_move')]
    free_side = [c for c in ai_player.get('side_hand', [])
                 if not c.get('part_of_figure') and not c.get('part_of_battle_move')]

    ai_figures = ai_player.get('figures', [])
    opp_figures = opponent.get('figures', [])

    # Index cards by (rank, color_group) for quick lookup
    def _color(suit):
        return 'red' if suit in _RED_SUITS_SET else 'black'

    main_by_rank_color = {}  # {(rank, color): [card, ...]}
    for c in free_main:
        key = (c['rank'], _color(c['suit']))
        main_by_rank_color.setdefault(key, []).append(c)

    side_by_rank_color = {}
    for c in free_side:
        key = (c['rank'], _color(c['suit']))
        side_by_rank_color.setdefault(key, []).append(c)

    main_by_rank = {}
    for c in free_main:
        main_by_rank.setdefault(c['rank'], []).append(c)

    side_by_rank = {}
    for c in free_side:
        side_by_rank.setdefault(c['rank'], []).append(c)

    def _pick(pool, rank, color, n):
        """Pick n cards of given rank and color from pool. Returns list or None."""
        key = (rank, color)
        cards = pool.get(key, [])
        if len(cards) >= n:
            return cards[:n]
        return None

    def _card_dicts(cards):
        """Format cards for the cast_spell params."""
        return [{'id': c['id'], 'rank': c['rank'], 'suit': c['suit'], 'value': c.get('value', 0)} for c in cards]

    def _primary_suit(cards):
        """Return the suit of the first card (used as spell suit)."""
        return cards[0]['suit'] if cards else 'Hearts'

    # ── GREED SPELLS (always castable, not counterable) ──

    # Draw 2 SideCards — 1× rank 2 (side, any suit)
    for rank2_cards in [side_by_rank.get('2', [])]:
        if rank2_cards:
            c = rank2_cards[0]
            actions.append({
                'id': action_id, 'type': 'cast_spell',
                'description': f"Spell: Draw 2 Side Cards (cost: {c['rank']}{c['suit'][:1]}) — draw 2 side cards from deck",
                'params': {
                    'spell_name': 'Draw 2 SideCards', 'spell_type': 'greed',
                    'spell_family_name': 'Draw 2 SideCards', 'suit': c['suit'],
                    'cards': _card_dicts([c]), 'target_figure_id': None,
                    'counterable': False, 'possible_during_ceasefire': True,
                },
            })
            action_id += 1

    # Draw 2 MainCards — 1× rank 8 (main, any suit)
    for rank8_cards in [main_by_rank.get('8', [])]:
        if rank8_cards:
            c = rank8_cards[0]
            actions.append({
                'id': action_id, 'type': 'cast_spell',
                'description': f"Spell: Draw 2 Main Cards (cost: {c['rank']}{c['suit'][:1]}) — draw 2 main cards from deck",
                'params': {
                    'spell_name': 'Draw 2 MainCards', 'spell_type': 'greed',
                    'spell_family_name': 'Draw 2 MainCards', 'suit': c['suit'],
                    'cards': _card_dicts([c]), 'target_figure_id': None,
                    'counterable': False, 'possible_during_ceasefire': True,
                },
            })
            action_id += 1

    # Fill up to 10 — 1× rank 10 (main, any suit)
    main_hand_count = len([c for c in ai_player.get('main_hand', [])
                           if not c.get('part_of_figure') and not c.get('part_of_battle_move')])
    if main_hand_count < 10:
        for rank10_cards in [main_by_rank.get('10', [])]:
            if rank10_cards:
                c = rank10_cards[0]
                fill = 10 - main_hand_count + 1  # +1 because the 10 itself goes to deck
                actions.append({
                    'id': action_id, 'type': 'cast_spell',
                    'description': f"Spell: Fill up to 10 (cost: {c['rank']}{c['suit'][:1]}) — draw ~{fill} main cards to fill hand to 10",
                    'params': {
                        'spell_name': 'Fill up to 10', 'spell_type': 'greed',
                        'spell_family_name': 'Fill up to 10', 'suit': c['suit'],
                        'cards': _card_dicts([c]), 'target_figure_id': None,
                        'counterable': False, 'possible_during_ceasefire': True,
                    },
                })
                action_id += 1

    # Forced Deal — 2× rank 4 (side, same color)
    for color in ('red', 'black'):
        cards = _pick(side_by_rank_color, '4', color, 2)
        if cards:
            desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in cards)
            actions.append({
                'id': action_id, 'type': 'cast_spell',
                'description': f"Spell: Forced Deal (cost: {desc_cards}) — swap 2 random main cards with opponent",
                'params': {
                    'spell_name': 'Forced Deal', 'spell_type': 'greed',
                    'spell_family_name': 'Forced Deal', 'suit': _primary_suit(cards),
                    'cards': _card_dicts(cards), 'target_figure_id': None,
                    'counterable': False, 'possible_during_ceasefire': True,
                },
            })
            action_id += 1
            break  # only offer once

    # Dump Cards — 4× rank 7 (main, same color, need 4)
    for color in ('red', 'black'):
        cards = _pick(main_by_rank_color, '7', color, 4)
        if cards:
            desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in cards)
            actions.append({
                'id': action_id, 'type': 'cast_spell',
                'description': f"Spell: Dump Cards (cost: {desc_cards}) — both discard ALL cards, redraw 5 main + 4 side. Desperate move!",
                'params': {
                    'spell_name': 'Dump Cards', 'spell_type': 'greed',
                    'spell_family_name': 'Dump Cards', 'suit': _primary_suit(cards),
                    'cards': _card_dicts(cards), 'target_figure_id': None,
                    'counterable': False, 'possible_during_ceasefire': True,
                },
            })
            action_id += 1
            break

    # ── ENCHANTMENT SPELLS (not counterable) ──

    # Poison — 2× rank 3 (side, black suits ♣♠)
    poison_cards = _pick(side_by_rank_color, '3', 'black', 2)
    if poison_cards and opp_figures:
        # Offer one action per targetable opponent figure
        for fig in opp_figures:
            if fig.get('checkmate'):
                continue  # Can't poison Maharaja
            fig_power = _est_figure_power(fig)
            desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in poison_cards)
            actions.append({
                'id': action_id, 'type': 'cast_spell',
                'description': f"Spell: Poison on {fig['name']} (power≈{fig_power}) (cost: {desc_cards}) — reduces power by 6!",
                'params': {
                    'spell_name': 'Poison', 'spell_type': 'enchantment',
                    'spell_family_name': 'Poison', 'suit': _primary_suit(poison_cards),
                    'cards': _card_dicts(poison_cards), 'target_figure_id': fig['id'],
                    'counterable': False, 'possible_during_ceasefire': True,
                },
            })
            action_id += 1

    # Health Boost — 2× rank 3 (side, red suits ♥♦)
    hb_cards = _pick(side_by_rank_color, '3', 'red', 2)
    if hb_cards and ai_figures:
        for fig in ai_figures:
            fig_power = _est_figure_power(fig)
            desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in hb_cards)
            actions.append({
                'id': action_id, 'type': 'cast_spell',
                'description': f"Spell: Health Boost on {fig['name']} (power≈{fig_power}) (cost: {desc_cards}) — +6 power!",
                'params': {
                    'spell_name': 'Health Boost', 'spell_type': 'enchantment',
                    'spell_family_name': 'Health Boost', 'suit': _primary_suit(hb_cards),
                    'cards': _card_dicts(hb_cards), 'target_figure_id': fig['id'],
                    'counterable': False, 'possible_during_ceasefire': True,
                },
            })
            action_id += 1

    # All Seeing Eye — 2× rank 9 (main, same color)
    for color in ('red', 'black'):
        cards = _pick(main_by_rank_color, '9', color, 2)
        if cards:
            desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in cards)
            actions.append({
                'id': action_id, 'type': 'cast_spell',
                'description': f"Spell: All Seeing Eye (cost: {desc_cards}) — reveal all opponent cards until end of round",
                'params': {
                    'spell_name': 'All Seeing Eye', 'spell_type': 'enchantment',
                    'spell_family_name': 'All Seeing Eye', 'suit': _primary_suit(cards),
                    'cards': _card_dicts(cards), 'target_figure_id': None,
                    'counterable': False, 'possible_during_ceasefire': True,
                },
            })
            action_id += 1
            break

    # Explosion — 4× rank 6 (side, same color)
    for color in ('red', 'black'):
        cards = _pick(side_by_rank_color, '6', color, 4)
        if cards and opp_figures:
            for fig in opp_figures:
                if fig.get('checkmate'):
                    continue
                fig_power = _est_figure_power(fig)
                desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in cards)
                actions.append({
                    'id': action_id, 'type': 'cast_spell',
                    'description': f"Spell: Explosion on {fig['name']} (power≈{fig_power}) (cost: {desc_cards}) — DESTROYS the figure!",
                    'params': {
                        'spell_name': 'Explosion', 'spell_type': 'enchantment',
                        'spell_family_name': 'Explosion', 'suit': _primary_suit(cards),
                        'cards': _card_dicts(cards), 'target_figure_id': fig['id'],
                        'counterable': False, 'possible_during_ceasefire': True,
                    },
                })
                action_id += 1
            break

    # Infinite Hammer — 1× K (main, any suit)
    # Only offer if there are at least 2 builds available AFTER removing the K card
    k_cards = main_by_rank.get('K', [])
    if k_cards:
        c = k_cards[0]
        # Simulate hand without this K to check if builds remain
        remaining_main = [card for card in ai_player.get('main_hand', [])
                          if card['id'] != c['id']
                          and not card.get('part_of_figure') and not card.get('part_of_battle_move')]
        remaining_side = [card for card in ai_player.get('side_hand', [])
                          if not card.get('part_of_figure') and not card.get('part_of_battle_move')]
        post_hammer_builds = find_buildable_figures(remaining_main, remaining_side, ai_figures)
        if len(post_hammer_builds) >= 2:
            actions.append({
                'id': action_id, 'type': 'cast_spell',
                'description': (f"Spell: Infinite Hammer (cost: K{c['suit'][:1]}) — unlimited builds this turn! "
                                f"⚠️ Uses a K card. {len(post_hammer_builds)} builds available after casting."),
                'params': {
                    'spell_name': 'Infinite Hammer', 'spell_type': 'enchantment',
                    'spell_family_name': 'Infinite Hammer', 'suit': c['suit'],
                    'cards': _card_dicts([c]), 'target_figure_id': None,
                    'counterable': False, 'possible_during_ceasefire': True,
                },
            })
            action_id += 1

    # ── TACTICS SPELLS (NOT during ceasefire or advance, counterable) ──
    if not ceasefire and not game_dict.get('advancing_figure_id'):
        # Check existing battle modifiers to avoid duplicates
        existing_modifiers = set()
        for mod in (game_dict.get('battle_modifier') or []):
            existing_modifiers.add(mod.get('type', ''))

        # Peasant War — 2× J (main, same color)
        if 'Peasant War' not in existing_modifiers:
            for color in ('red', 'black'):
                cards = _pick(main_by_rank_color, 'J', color, 2)
                if cards:
                    desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in cards)
                    actions.append({
                        'id': action_id, 'type': 'cast_spell',
                        'description': f"Spell: Peasant War (cost: {desc_cards}) — only village figures battle; both get 2 turns. COUNTERABLE!",
                        'params': {
                            'spell_name': 'Peasant War', 'spell_type': 'tactics',
                            'spell_family_name': 'Peasant War', 'suit': _primary_suit(cards),
                            'cards': _card_dicts(cards), 'target_figure_id': None,
                            'counterable': True, 'possible_during_ceasefire': False,
                        },
                    })
                    action_id += 1
                    break

        # Civil War — 2× 5 (side, same color)
        if 'Civil War' not in existing_modifiers:
            for color in ('red', 'black'):
                cards = _pick(side_by_rank_color, '5', color, 2)
                if cards:
                    desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in cards)
                    actions.append({
                        'id': action_id, 'type': 'cast_spell',
                        'description': f"Spell: Civil War (cost: {desc_cards}) — each picks 2 village figures for battle; both get 2 turns. COUNTERABLE!",
                        'params': {
                            'spell_name': 'Civil War', 'spell_type': 'tactics',
                            'spell_family_name': 'Civil War', 'suit': _primary_suit(cards),
                            'cards': _card_dicts(cards), 'target_figure_id': None,
                            'counterable': True, 'possible_during_ceasefire': False,
                        },
                    })
                    action_id += 1
                    break

        # Invader Swap — 2× A (main, same color)
        if 'Invader Swap' not in existing_modifiers:
            for color in ('red', 'black'):
                cards = _pick(main_by_rank_color, 'A', color, 2)
                if cards:
                    desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in cards)
                    actions.append({
                        'id': action_id, 'type': 'cast_spell',
                        'description': f"Spell: Invader Swap (cost: {desc_cards}) — swap invader/defender; both get 2 turns. COUNTERABLE! ⚠️ Costs 2 Aces!",
                        'params': {
                            'spell_name': 'Invader Swap', 'spell_type': 'tactics',
                            'spell_family_name': 'Invader Swap', 'suit': _primary_suit(cards),
                            'cards': _card_dicts(cards), 'target_figure_id': None,
                            'counterable': True, 'possible_during_ceasefire': False,
                        },
                    })
                    action_id += 1
                    break

        # Blitzkrieg — 2× Q (main, same color)
        if 'Blitzkrieg' not in existing_modifiers:
            for color in ('red', 'black'):
                cards = _pick(main_by_rank_color, 'Q', color, 2)
                if cards:
                    desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in cards)
                    actions.append({
                        'id': action_id, 'type': 'cast_spell',
                        'description': f"Spell: Blitzkrieg (cost: {desc_cards}) — you become invader; advance can't be countered; both get 2 turns. COUNTERABLE! ⚠️ Costs 2 Queens!",
                        'params': {
                            'spell_name': 'Blitzkrieg', 'spell_type': 'tactics',
                            'spell_family_name': 'Blitzkrieg', 'suit': _primary_suit(cards),
                            'cards': _card_dicts(cards), 'target_figure_id': None,
                            'counterable': True, 'possible_during_ceasefire': False,
                        },
                    })
                    action_id += 1
                    break

        # Ceasefire — 7+8+9 or 8+9+10 (main, same color)
        for color in ('red', 'black'):
            for seq in [('8', '9', '10'), ('7', '8', '9')]:
                cards_found = []
                used_ids = set()
                for rank in seq:
                    pool = main_by_rank_color.get((rank, color), [])
                    card = next((c for c in pool if c['id'] not in used_ids), None)
                    if card:
                        cards_found.append(card)
                        used_ids.add(card['id'])
                if len(cards_found) == 3:
                    desc_cards = '+'.join(f"{c['rank']}{c['suit'][:1]}" for c in cards_found)
                    actions.append({
                        'id': action_id, 'type': 'cast_spell',
                        'description': f"Spell: Ceasefire (cost: {desc_cards}) — both players +3 turns, ceasefire reactivates. COUNTERABLE!",
                        'params': {
                            'spell_name': 'Ceasefire', 'spell_type': 'tactics',
                            'spell_family_name': 'Ceasefire', 'suit': _primary_suit(cards_found),
                            'cards': _card_dicts(cards_found), 'target_figure_id': None,
                            'counterable': True, 'possible_during_ceasefire': False,
                        },
                    })
                    action_id += 1
                    break
            else:
                continue
            break

    return actions, action_id


# ── Helpers ────────────────────────────────────────────────────


def _get_ai_player(game_dict, ai_player_id):
    for p in game_dict['players']:
        if p['id'] == ai_player_id:
            return p
    return {}


def _get_opponent(game_dict, ai_player_id):
    for p in game_dict['players']:
        if p['id'] != ai_player_id:
            return p
    return {}
