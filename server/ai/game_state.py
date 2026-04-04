# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
Game state serializer for LLM prompts.

Converts the game dict (from game.serialize()) into a concise text
description that the LLM can understand and reason about.
"""
import logging

logger = logging.getLogger('nepalkings.ai.game_state')


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
    
    # AI's figures
    lines.append(f"\n=== YOUR FIGURES ({len(ai_player['figures'])}) ===")
    for fig in ai_player['figures']:
        lines.append(_describe_figure(fig))
    
    # Opponent's figures (visible info only — no card details)
    lines.append(f"\n=== OPPONENT'S FIGURES ({len(opponent['figures'])}) ===")
    for fig in opponent['figures']:
        lines.append(_describe_figure(fig, show_cards=False))
    
    # Opponent's hand size (no card details)
    opp_main = len(opponent.get('main_hand', []))
    opp_side = len(opponent.get('side_hand', []))
    lines.append(f"\nOpponent has {opp_main} main cards and {opp_side} side cards in hand.")
    
    # Battle state if active
    if game_dict.get('advancing_figure_id'):
        lines.append(f"\n=== BATTLE STATE ===")
        lines.append(f"Advancing figure ID: {game_dict['advancing_figure_id']}")
        if game_dict.get('defending_figure_id'):
            lines.append(f"Defending figure ID: {game_dict['defending_figure_id']}")
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
    
    parts = [f"  - {name} ({field}/{color})"]
    
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
