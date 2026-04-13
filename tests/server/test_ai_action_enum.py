# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Action-enum and phase-detection tests for AI workflow."""

from ai.action_enum import detect_phase, enumerate_actions, _all_battle_rounds_done


def _base_game_dict(ai_id=1, opp_id=2):
    return {
        'id': 1,
        'state': 'open',
        'current_round': 1,
        'stake': 45,
        'fold_winner_id': None,
        'pending_spell_id': None,
        'waiting_for_counter_player_id': None,
        'battle_modifier': [],
        'battle_confirmed': False,
        'battle_moves_confirmed': {},
        'battle_round': 0,
        'battle_turn_player_id': None,
        'battle_skipped_rounds': {},
        'battle_moves': [],
        'battle_decisions': None,
        'advancing_figure_id': None,
        'advancing_figure_id_2': None,
        'advancing_player_id': None,
        'defending_figure_id': None,
        'defending_figure_id_2': None,
        'turn_player_id': None,
        'invader_player_id': ai_id,
        'ceasefire_active': False,
        'players': [
            {
                'id': ai_id,
                'points': 0,
                'turns_left': 2,
                'main_hand': [],
                'side_hand': [],
                'figures': [],
            },
            {
                'id': opp_id,
                'points': 0,
                'turns_left': 2,
                'main_hand': [],
                'side_hand': [],
                'figures': [],
            },
        ],
    }


def _create_pending_spell(db, spell_name='Peasant War'):
    from models import User, Game, Player, ActiveSpell
    from werkzeug.security import generate_password_hash

    ai_user = User(
        username='[AI] EnumBot',
        password_hash=generate_password_hash('x'),
        is_ai=True,
        gold=9999,
    )
    human_user = User(
        username='enum_human',
        password_hash=generate_password_hash('x'),
        is_ai=False,
        gold=9999,
    )
    db.session.add_all([ai_user, human_user])
    db.session.commit()

    game = Game(current_round=1, stake=35, state='open')
    db.session.add(game)
    db.session.commit()

    ai_player = Player(user_id=ai_user.id, game_id=game.id, turns_left=2, points=0)
    human_player = Player(user_id=human_user.id, game_id=game.id, turns_left=2, points=0)
    db.session.add_all([ai_player, human_player])
    db.session.commit()

    game.turn_player_id = ai_player.id
    game.invader_player_id = ai_player.id
    db.session.commit()

    spell = ActiveSpell(
        game_id=game.id,
        player_id=human_player.id,
        spell_name=spell_name,
        spell_type='tactics',
        spell_family_name=spell_name,
        suit='Hearts',
        target_figure_id=None,
        cast_round=1,
        duration=0,
        is_active=True,
        is_pending=True,
        counterable=True,
        effect_data={},
    )
    db.session.add(spell)
    db.session.commit()

    return game, ai_player, human_player, spell


def test_detect_phase_returns_battle_shop_before_ai_confirms_moves():
    game_dict = _base_game_dict(ai_id=7, opp_id=8)
    game_dict['battle_confirmed'] = True
    game_dict['battle_moves_confirmed'] = {}

    assert detect_phase(game_dict, 7) == 'battle_shop'


def test_detect_phase_defender_waits_for_invader_battle_decision():
    game_dict = _base_game_dict(ai_id=10, opp_id=11)
    game_dict['advancing_figure_id'] = 101
    game_dict['defending_figure_id'] = 202
    game_dict['advancing_player_id'] = 11  # AI is defender
    game_dict['battle_decisions'] = {}

    # Defender must wait until invader decides battle.
    assert detect_phase(game_dict, 10) is None

    game_dict['battle_decisions'] = {'11': 'battle'}
    assert detect_phase(game_dict, 10) == 'battle_decision'


def test_all_battle_rounds_done_requires_both_players_to_cover_all_rounds():
    game_dict = _base_game_dict(ai_id=1, opp_id=2)
    game_dict['battle_confirmed'] = True
    game_dict['battle_moves'] = [
        {'player_id': 1, 'played_round': 0},
        {'player_id': 1, 'played_round': 1},
        {'player_id': 1, 'played_round': 2},
        {'player_id': 2, 'played_round': 0},
        {'player_id': 2, 'played_round': 1},
    ]
    game_dict['battle_skipped_rounds'] = {'2': [2]}
    assert _all_battle_rounds_done(game_dict, 1) is True

    game_dict['battle_skipped_rounds'] = {'2': []}
    assert _all_battle_rounds_done(game_dict, 1) is False


def test_enumerate_actions_counter_spell_has_real_counter_option_when_cards_exist(app, db):
    _, ai_player, human_player, spell = _create_pending_spell(db, spell_name='Peasant War')

    game_dict = _base_game_dict(ai_id=ai_player.id, opp_id=human_player.id)
    game_dict['pending_spell_id'] = spell.id
    game_dict['waiting_for_counter_player_id'] = ai_player.id
    game_dict['players'][0]['main_hand'] = [
        {'id': 1, 'rank': 'J', 'suit': 'Hearts', 'value': 11, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 2, 'rank': 'J', 'suit': 'Diamonds', 'value': 11, 'part_of_figure': False, 'part_of_battle_move': False},
    ]

    actions = enumerate_actions(game_dict, ai_player.id, 'counter_spell')
    counter_action = next(a for a in actions if a['type'] == 'counter_spell')

    assert 'will FAIL' not in counter_action['description']
    assert len(counter_action['params']['counter_cards']) == 2


def test_enumerate_actions_counter_spell_marks_failure_when_cards_missing(app, db):
    _, ai_player, human_player, spell = _create_pending_spell(db, spell_name='Peasant War')

    game_dict = _base_game_dict(ai_id=ai_player.id, opp_id=human_player.id)
    game_dict['pending_spell_id'] = spell.id
    game_dict['waiting_for_counter_player_id'] = ai_player.id
    game_dict['players'][0]['main_hand'] = [
        {'id': 9, 'rank': '7', 'suit': 'Clubs', 'value': 7, 'part_of_figure': False, 'part_of_battle_move': False},
    ]

    actions = enumerate_actions(game_dict, ai_player.id, 'counter_spell')
    counter_action = next(a for a in actions if a['type'] == 'counter_spell')

    assert 'will FAIL' in counter_action['description']
    assert counter_action['params']['counter_cards'] == []


def test_enumerate_actions_battle_round_offers_skip_when_no_unplayed_moves():
    game_dict = _base_game_dict(ai_id=3, opp_id=4)
    game_dict['battle_confirmed'] = True
    game_dict['battle_turn_player_id'] = 3
    game_dict['battle_round'] = 1
    game_dict['battle_moves'] = [
        {'id': 11, 'player_id': 3, 'family_name': 'Dagger', 'value': 8, 'played_round': 0},
        {'id': 12, 'player_id': 4, 'family_name': 'Dagger', 'value': 7, 'played_round': 0},
    ]

    actions = enumerate_actions(game_dict, 3, 'battle_round')
    action_types = {a['type'] for a in actions}

    assert 'skip_battle_turn' in action_types
    assert 'play_battle_move' not in action_types


def test_enumerate_actions_normal_turn_change_cards_description_uses_swap_summary():
    game_dict = _base_game_dict(ai_id=9, opp_id=10)
    game_dict['turn_player_id'] = 9
    game_dict['players'][0]['main_hand'] = [
        {'id': 1, 'rank': 'K', 'suit': 'Hearts', 'value': 4, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 2, 'rank': 'A', 'suit': 'Hearts', 'value': 3, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 3, 'rank': '10', 'suit': 'Clubs', 'value': 10, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 4, 'rank': '9', 'suit': 'Diamonds', 'value': 9, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 5, 'rank': 'Q', 'suit': 'Clubs', 'value': 12, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 6, 'rank': 'J', 'suit': 'Spades', 'value': 11, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 7, 'rank': '8', 'suit': 'Hearts', 'value': 8, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 8, 'rank': '7', 'suit': 'Hearts', 'value': 7, 'part_of_figure': False, 'part_of_battle_move': False},
    ]

    actions = enumerate_actions(game_dict, 9, 'normal_turn')
    change_action = next(a for a in actions if a['type'] == 'change_cards')

    assert '2 suggested swaps' in change_action['description']
    assert '2 low-rank of 8 free cards' in change_action['description']