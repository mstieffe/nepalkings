# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Viewer-aware API serializers.

Core model serializers remain full-fidelity for trusted in-process callers.
Routes should use these helpers before sending game state to a client.
"""
from copy import deepcopy

def viewer_player_for_game(game, viewer_user_id):
    if game is None or viewer_user_id is None:
        return None
    for player in game.players:
        if player.user_id == viewer_user_id:
            return player
    return None


def viewer_has_all_seeing_eye(game_dict, viewer_player_id):
    if viewer_player_id is None:
        return False
    return any(
        'All Seeing Eye' in str(spell.get('spell_name', ''))
        and spell.get('player_id') == viewer_player_id
        and spell.get('is_active')
        for spell in game_dict.get('active_spells', [])
    )


def _redact_card(card):
    redacted = dict(card or {})
    redacted.update({
        'id': None,
        'rank': None,
        'suit': None,
        'value': 0,
        'deck_position': None,
    })
    if 'card_id' in redacted:
        redacted['card_id'] = None
    if 'card_id_b' in redacted:
        redacted['card_id_b'] = None
    return redacted


def _redact_card_link(link):
    redacted = dict(link or {})
    redacted.update({
        'card_id': None,
        'rank': None,
        'suit': None,
        'value': 0,
        'deck_position': None,
    })
    return redacted


def serialize_figure_for_viewer(figure, viewer_player_id, reveal_opponent=False):
    # Field figures are PUBLIC in Nepal Kings — both players see each other's
    # army and its card composition; that visibility is core to the attack/
    # defense strategy. Only hand cards and unplayed battle moves/tactics are
    # secret (see serialize_game_for_viewer / redact_battle_move). The
    # viewer_player_id / reveal_opponent parameters are kept for call-site
    # compatibility but no longer redact figures.
    return figure.serialize() if hasattr(figure, 'serialize') else dict(figure or {})


def _move_is_revealed(move):
    return move.get('played_round') is not None or move.get('status') == 'played'


def redact_battle_move(move):
    if _move_is_revealed(move):
        return dict(move)
    return {
        'id': move.get('id'),
        'game_id': move.get('game_id'),
        'player_id': move.get('player_id'),
        'played_round': move.get('played_round'),
    }


def redact_conquer_tactic(tactic):
    if _move_is_revealed(tactic):
        return dict(tactic)
    return {
        'id': tactic.get('id'),
        'game_id': tactic.get('game_id'),
        'player_id': tactic.get('player_id'),
        'status': tactic.get('status'),
        'played_round': tactic.get('played_round'),
        'revealed_step_index': tactic.get('revealed_step_index'),
        'discarded_step_index': tactic.get('discarded_step_index'),
    }


def redact_payload_for_viewer(value, viewer_player_id, reveal_opponent=False):
    if isinstance(value, list):
        return [
            redact_payload_for_viewer(item, viewer_player_id, reveal_opponent)
            for item in value
        ]
    if not isinstance(value, dict):
        return value

    item = {
        key: redact_payload_for_viewer(val, viewer_player_id, reveal_opponent)
        for key, val in value.items()
    }

    looks_like_card = (
        {'rank', 'suit', 'value'}.issubset(item.keys())
        or {'card_id', 'card_type'}.issubset(item.keys())
    )
    belongs_to_opponent = (
        item.get('player_id') is not None
        and item.get('player_id') != viewer_player_id
    )
    if looks_like_card and belongs_to_opponent and not reveal_opponent:
        return _redact_card(item)
    if 'cards' in item and belongs_to_opponent and not reveal_opponent:
        item['cards'] = [_redact_card_link(c) for c in item.get('cards') or []]
    return item


def serialize_spell_for_viewer(spell, viewer_player_id, reveal_opponent=False):
    data = spell.serialize() if hasattr(spell, 'serialize') else dict(spell or {})
    data['effect_data'] = redact_payload_for_viewer(
        data.get('effect_data'), viewer_player_id, reveal_opponent)
    return data


def serialize_battle_moves_for_viewer(moves, viewer_player_id, reveal_opponent=False):
    output = []
    for move in moves:
        data = move.serialize() if hasattr(move, 'serialize') else dict(move or {})
        if data.get('player_id') != viewer_player_id and not reveal_opponent:
            data = redact_battle_move(data)
        output.append(data)
    return output


def serialize_game_for_viewer(game, viewer_user_id):
    data = deepcopy(game.serialize())
    viewer_player = viewer_player_for_game(game, viewer_user_id)
    viewer_player_id = viewer_player.id if viewer_player else None
    reveal_opponent = viewer_has_all_seeing_eye(data, viewer_player_id)

    for player in data.get('players', []):
        is_viewer = player.get('id') == viewer_player_id
        if not is_viewer and not reveal_opponent:
            # Hand cards are secret; field figures are public (see
            # serialize_figure_for_viewer) so they are left intact here.
            player['main_hand'] = [_redact_card(c) for c in player.get('main_hand', [])]
            player['side_hand'] = [_redact_card(c) for c in player.get('side_hand', [])]

    for key in ('main_cards', 'side_cards'):
        filtered = []
        for card in data.get(key, []):
            if card.get('in_deck'):
                continue
            owner = card.get('player_id')
            if owner is not None and owner != viewer_player_id and not reveal_opponent:
                filtered.append(_redact_card(card))
            else:
                filtered.append(card)
        data[key] = filtered

    data['battle_moves'] = [
        move if (
            move.get('player_id') == viewer_player_id or reveal_opponent
        ) else redact_battle_move(move)
        for move in data.get('battle_moves', [])
    ]
    data['conquer_tactics'] = [
        tactic if (
            tactic.get('player_id') == viewer_player_id or reveal_opponent
        ) else redact_conquer_tactic(tactic)
        for tactic in data.get('conquer_tactics', [])
    ]
    data['active_spells'] = [
        redact_payload_for_viewer(spell, viewer_player_id, reveal_opponent)
        for spell in data.get('active_spells', [])
    ]

    # AI seed is useful internally for deterministic planning, not for clients.
    data['ai_seed'] = None
    return data
