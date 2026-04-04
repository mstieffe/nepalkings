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

    # Battle decision — advancing + defending figures set, AI hasn't decided
    if (game_dict.get('advancing_figure_id') and
            game_dict.get('defending_figure_id') and
            not game_dict.get('battle_confirmed')):
        decisions = game_dict.get('battle_decisions') or {}
        if str(ai_player_id) not in decisions:
            return 'battle_decision'

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

    battle_moves = game_dict.get('battle_moves', [])
    skipped = game_dict.get('battle_skipped_rounds', {})

    # Get both player IDs
    player_ids = [p['id'] for p in game_dict.get('players', [])]
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

    # 1) Build figures
    buildable = find_buildable_figures(
        ai_player.get('main_hand', []),
        ai_player.get('side_hand', []),
        ai_player.get('figures', []),
    )
    for fig in buildable:
        recipe = fig['recipe']
        actions.append({
            'id': action_id,
            'type': 'build_figure',
            'description': f"Build {fig['display_name']} — produces: {fig['produces']}, requires: {fig['requires']}",
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
    if not game_dict.get('ceasefire_active') and not game_dict.get('advancing_figure_id'):
        resting = set(game_dict.get('resting_figure_ids', []))
        for fig in ai_player.get('figures', []):
            fig_id = fig['id']
            # Skip figures that can't attack or are resting
            if fig.get('cannot_attack'):
                continue
            if fig.get('cannot_defend') and fig.get('cannot_attack'):
                continue
            if fig_id in resting:
                continue
            actions.append({
                'id': action_id,
                'type': 'advance_figure',
                'description': f"Advance {fig['name']} (id={fig_id}) toward battle",
                'params': {'figure_id': fig_id},
            })
            action_id += 1

    # 3) Change cards (always available — swap hand and draw new)
    actions.append({
        'id': action_id,
        'type': 'change_cards',
        'description': "Change cards — return all hand cards, draw new ones",
        'params': {},
    })
    action_id += 1

    return actions


def _enum_select_defender(game_dict, ai_player, opponent):
    """
    The AI (as invader) selects which OPPONENT figure to fight.
    """
    actions = []
    action_id = 1
    
    for fig in opponent.get('figures', []):
        # Skip figures that can't be targeted (e.g., Wall with cannot_be_targeted)
        if fig.get('cannot_be_targeted'):
            continue
        actions.append({
            'id': action_id,
            'type': 'select_defender',
            'description': f"Select opponent's {fig['name']} (id={fig['id']}) as defender — {'CHECKMATE if destroyed!' if fig.get('checkmate') else 'normal figure'}",
            'params': {'figure_id': fig['id']},
        })
        action_id += 1
    
    return actions


def _enum_battle_decision(game_dict, ai_player, opponent):
    """AI decides to fold or battle."""
    actions = [
        {
            'id': 1,
            'type': 'battle_decision',
            'description': "BATTLE — fight for this figure",
            'params': {'decision': 'battle'},
        },
        {
            'id': 2,
            'type': 'battle_decision',
            'description': "FOLD — retreat (your figure is destroyed, opponent gains points)",
            'params': {'decision': 'fold'},
        },
    ]
    return actions


def _enum_battle_shop(game_dict, ai_player, opponent):
    """
    AI buys battle moves from hand cards and confirms.
    Returns buy + confirm actions.
    """
    actions = []
    action_id = 1
    
    # Get current battle moves for the AI
    ai_moves = [m for m in game_dict.get('battle_moves', []) 
                if m.get('player_id') == ai_player['id']]
    num_moves = len(ai_moves)
    
    if num_moves < 3:
        # Can buy more moves — list buyable cards
        available = [c for c in ai_player.get('main_hand', [])
                     if not c.get('part_of_figure') and not c.get('part_of_battle_move')]
        
        move_names = {
            'J': 'Call Villager (value=1)',
            'Q': 'Block (value=2)',
            'A': 'Call Military (value=3)',
            'K': 'Call King (value=4)',
        }
        
        for card in available:
            rank = card['rank']
            if rank in move_names:
                desc = move_names[rank]
            elif rank in ['7', '8', '9', '10']:
                desc = f"Dagger (value={rank})"
            else:
                continue  # Side cards can't be battle moves
            
            actions.append({
                'id': action_id,
                'type': 'buy_battle_move',
                'description': f"Buy {desc} — {rank} of {card['suit']}",
                'params': {'card_id': card['id']},
            })
            action_id += 1
    
    # Can always confirm (even with 0 moves)
    actions.append({
        'id': action_id,
        'type': 'confirm_battle_moves',
        'description': f"Confirm battle moves ({num_moves}/3 moves bought)",
        'params': {},
    })
    action_id += 1
    
    return actions


def _enum_battle_round(game_dict, ai_player, opponent):
    """AI plays a battle move or skips."""
    actions = []
    action_id = 1
    
    current_round = game_dict.get('battle_round', 0)
    
    # Get unplayed moves
    ai_moves = [m for m in game_dict.get('battle_moves', [])
                if m.get('player_id') == ai_player['id'] and m.get('played_round') is None]
    
    for move in ai_moves:
        actions.append({
            'id': action_id,
            'type': 'play_battle_move',
            'description': f"Play {move.get('name', '?')} (value={move.get('value', '?')}) for round {current_round + 1}",
            'params': {'move_id': move['id']},
        })
        action_id += 1
    
    # Can skip if no moves left (or strategically)
    actions.append({
        'id': action_id,
        'type': 'skip_battle_turn',
        'description': "Skip this round (play no move)",
        'params': {},
    })
    action_id += 1
    
    return actions


def _enum_counter_spell(game_dict, ai_player, opponent):
    """AI decides whether to allow or counter a pending spell."""
    actions = [
        {
            'id': 1,
            'type': 'allow_spell',
            'description': "Allow the spell to take effect",
            'params': {},
        },
        {
            'id': 2,
            'type': 'counter_spell',
            'description': "Counter the spell (block it)",
            'params': {},
        },
    ]
    return actions


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
