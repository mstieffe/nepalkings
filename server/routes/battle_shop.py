"""Server routes for battle shop — buy and return battle moves."""

import random
from flask import Blueprint, request, jsonify
from models import db, Game, Player, MainCard, SideCard, BattleMove, User, LogEntry

battle_shop = Blueprint('battle_shop', __name__)

# Max battle moves per player
MAX_BATTLE_MOVES = 3


@battle_shop.route('/buy_battle_move', methods=['POST'])
def buy_battle_move():
    """Buy a battle move by reserving one card from the player's hand.

    Expects JSON: {
        game_id, player_id, family_name, card_id, card_type, suit, rank, value
    }

    This is NOT a turn action — it can always be done.
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')
    family_name = data.get('family_name')
    card_id = data.get('card_id')
    card_type = data.get('card_type', 'main')  # 'main' or 'side'
    suit = data.get('suit')
    rank = data.get('rank')
    value = data.get('value', 0)

    if not all([game_id, player_id, family_name, card_id, suit, rank]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    player = Player.query.get(player_id)
    if not player or player.game_id != game_id:
        return jsonify({'success': False, 'message': 'Player not found in this game'}), 404

    # Check max battle moves
    existing_moves = BattleMove.query.filter_by(game_id=game_id, player_id=player_id).count()
    if existing_moves >= MAX_BATTLE_MOVES:
        return jsonify({'success': False, 'message': f'Maximum of {MAX_BATTLE_MOVES} battle moves reached'}), 400

    # Find and validate the card
    if card_type == 'side':
        card = SideCard.query.get(card_id)
    else:
        card = MainCard.query.get(card_id)

    if not card:
        return jsonify({'success': False, 'message': 'Card not found'}), 404

    if card.player_id != player_id:
        return jsonify({'success': False, 'message': 'Card does not belong to this player'}), 400

    if card.part_of_figure:
        return jsonify({'success': False, 'message': 'Card is already part of a figure'}), 400

    if card.part_of_battle_move:
        return jsonify({'success': False, 'message': 'Card is already reserved for a battle move'}), 400

    if card.in_deck:
        return jsonify({'success': False, 'message': 'Card is still in the deck'}), 400

    # Check for duplicate — same card should not be used twice
    existing_with_card = BattleMove.query.filter_by(
        game_id=game_id, player_id=player_id, card_id=card_id, card_type=card_type
    ).first()
    if existing_with_card:
        return jsonify({'success': False, 'message': 'This card is already used for a battle move'}), 400

    # Mark the card as reserved
    card.part_of_battle_move = True

    # Create the battle move
    battle_move = BattleMove(
        game_id=game_id,
        player_id=player_id,
        family_name=family_name,
        card_id=card_id,
        card_type=card_type,
        suit=suit,
        rank=rank,
        value=value,
    )
    db.session.add(battle_move)
    db.session.commit()

    return jsonify({
        'success': True,
        'battle_move': battle_move.serialize(),
        'game': game.serialize(),
    })


@battle_shop.route('/return_battle_move', methods=['POST'])
def return_battle_move():
    """Return (cancel) a previously bought battle move.

    Expects JSON: { game_id, player_id, battle_move_id }

    This is NOT a turn action.
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')
    battle_move_id = data.get('battle_move_id')

    if not all([game_id, player_id, battle_move_id]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    battle_move = BattleMove.query.get(battle_move_id)
    if not battle_move:
        return jsonify({'success': False, 'message': 'Battle move not found'}), 404

    if battle_move.game_id != game_id or battle_move.player_id != player_id:
        return jsonify({'success': False, 'message': 'Battle move does not belong to this player'}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    # Un-reserve the card
    if battle_move.card_type == 'side':
        card = SideCard.query.get(battle_move.card_id)
    else:
        card = MainCard.query.get(battle_move.card_id)

    if card:
        card.part_of_battle_move = False

    # Delete the battle move
    db.session.delete(battle_move)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Battle move returned',
        'game': game.serialize(),
    })


@battle_shop.route('/get_battle_moves', methods=['GET'])
def get_battle_moves():
    """Get all battle moves for a player in a game.

    Expects query params: game_id, player_id
    """
    game_id = request.args.get('game_id', type=int)
    player_id = request.args.get('player_id', type=int)

    if not game_id or not player_id:
        return jsonify({'success': False, 'message': 'Missing game_id or player_id'}), 400

    moves = BattleMove.query.filter_by(game_id=game_id, player_id=player_id).all()
    return jsonify({
        'success': True,
        'battle_moves': [m.serialize() for m in moves],
    })


@battle_shop.route('/confirm_battle_moves', methods=['POST'])
def confirm_battle_moves():
    """Mark a player as ready (all 3 battle moves selected).

    When both players have confirmed, returns both_ready=True so the
    client can transition to the battle screen.

    Expects JSON: { game_id, player_id }
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')

    if not game_id or not player_id:
        return jsonify({'success': False, 'message': 'Missing game_id or player_id'}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    # Verify the player has exactly MAX_BATTLE_MOVES battle moves
    move_count = BattleMove.query.filter_by(game_id=game_id, player_id=player_id).count()
    if move_count < MAX_BATTLE_MOVES:
        return jsonify({
            'success': False,
            'message': f'You must select {MAX_BATTLE_MOVES} battle moves before confirming.'
        }), 400

    # Record this player's confirmation
    confirmed = dict(game.battle_moves_confirmed) if game.battle_moves_confirmed else {}
    confirmed[str(player_id)] = True
    game.battle_moves_confirmed = confirmed

    # Check if both players have confirmed
    player_ids = [str(p.id) for p in game.players]
    both_ready = all(confirmed.get(pid) for pid in player_ids)

    # Initialize 3-round battle tracking when both players are ready
    if both_ready:
        game.battle_round = 0
        game.battle_turn_player_id = game.invader_player_id
        # Reset played_round on all battle moves so they start as "in hand"
        moves = BattleMove.query.filter_by(game_id=game_id).all()
        for m in moves:
            m.played_round = None
            m.call_figure_id = None

    db.session.commit()

    return jsonify({
        'success': True,
        'both_ready': both_ready,
        'game': game.serialize(),
    })


# ── Rank → battle-move family mapping (mirrors client-side config) ──
_RANK_TO_FAMILY = {
    'J': 'Call Villager',
    'Q': 'Block',
    'A': 'Call Military',
    'K': 'Call King',
}
_NUMBER_RANKS = {'7', '8', '9', '10'}


def _family_for_rank(rank):
    """Map a card rank to the corresponding battle-move family name."""
    if rank in _RANK_TO_FAMILY:
        return _RANK_TO_FAMILY[rank]
    if rank in _NUMBER_RANKS:
        return 'Dagger'
    return None


@battle_shop.route('/gamble_battle_move', methods=['POST'])
def gamble_battle_move():
    """Gamble: sacrifice one battle move and draw two random replacements.

    • Returns the sacrificed move's card to the player's hand (un-reserves it).
    • Draws 2 cards from the main-card deck at random (cards still in deck).
    • Creates 2 new BattleMove records from those cards.
    • The player may temporarily hold > 3 battle moves.

    Expects JSON: { game_id, player_id, battle_move_id }

    Returns: { success, sacrificed, new_moves: [{...}, {...}], game }
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')
    battle_move_id = data.get('battle_move_id')

    if not all([game_id, player_id, battle_move_id]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    player = Player.query.get(player_id)
    if not player or player.game_id != game_id:
        return jsonify({'success': False, 'message': 'Player not found in this game'}), 404

    # Find the battle move to sacrifice
    bm = BattleMove.query.get(battle_move_id)
    if not bm:
        return jsonify({'success': False, 'message': 'Battle move not found'}), 404
    if bm.game_id != game_id or bm.player_id != player_id:
        return jsonify({'success': False, 'message': 'Battle move does not belong to this player'}), 400

    # 1. Un-reserve the sacrificed card
    if bm.card_type == 'side':
        old_card = SideCard.query.get(bm.card_id)
    else:
        old_card = MainCard.query.get(bm.card_id)
    if old_card:
        old_card.part_of_battle_move = False

    sacrificed_data = bm.serialize()

    # Delete the sacrificed battle move
    db.session.delete(bm)

    # 2. Draw 2 random cards from the main-card deck
    deck_cards = MainCard.query.filter_by(game_id=game_id, in_deck=True).all()
    if len(deck_cards) < 2:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Not enough cards in the deck to gamble'}), 400

    drawn = random.sample(deck_cards, 2)

    new_moves = []
    for card in drawn:
        # card.rank is a ChoiceType enum — use .value for the string representation
        rank_str = card.rank.value if hasattr(card.rank, 'value') else str(card.rank)
        suit_str = card.suit.value if hasattr(card.suit, 'value') else str(card.suit)

        family_name = _family_for_rank(rank_str)
        if not family_name:
            # Shouldn't happen with standard ranks, but safeguard
            continue

        card.in_deck = False
        card.player_id = player_id
        card.part_of_battle_move = True

        move = BattleMove(
            game_id=game_id,
            player_id=player_id,
            family_name=family_name,
            card_id=card.id,
            card_type='main',
            suit=suit_str,
            rank=rank_str,
            value=card.value,
        )
        db.session.add(move)
        db.session.flush()  # get move.id
        new_moves.append(move.serialize())

    db.session.commit()

    return jsonify({
        'success': True,
        'sacrificed': sacrificed_data,
        'new_moves': new_moves,
        'game': game.serialize(),
    })


# ── Suit colour helpers ──────────────────────────────────────
_RED_SUITS = {'Hearts', 'Diamonds'}
_BLACK_SUITS = {'Clubs', 'Spades'}


def _same_colour(suit_a, suit_b):
    """Return True if both suits belong to the same colour group."""
    if suit_a in _RED_SUITS and suit_b in _RED_SUITS:
        return True
    if suit_a in _BLACK_SUITS and suit_b in _BLACK_SUITS:
        return True
    return False


@battle_shop.route('/combine_battle_moves', methods=['POST'])
def combine_battle_moves():
    """Combine two same-colour Dagger battle moves into a Double Dagger.

    • Both moves must be Daggers belonging to the same player.
    • Suits must share the same colour (red or black).
    • Neither move may already be a Double Dagger.
    • The two source cards stay reserved; a new BattleMove is created with
      family_name='Double Dagger'.  The combined value is the sum of both.
    • The two source BattleMove records are deleted.

    Expects JSON: { game_id, player_id, move_id_a, move_id_b }

    Returns: { success, combined_move: {...}, removed_ids: [a, b], game }
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')
    move_id_a = data.get('move_id_a')
    move_id_b = data.get('move_id_b')

    if not all([game_id, player_id, move_id_a, move_id_b]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if move_id_a == move_id_b:
        return jsonify({'success': False, 'message': 'Cannot combine a move with itself'}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    bm_a = BattleMove.query.get(move_id_a)
    bm_b = BattleMove.query.get(move_id_b)

    if not bm_a or not bm_b:
        return jsonify({'success': False, 'message': 'Battle move not found'}), 404

    for bm in (bm_a, bm_b):
        if bm.game_id != game_id or bm.player_id != player_id:
            return jsonify({'success': False, 'message': 'Battle move does not belong to this player'}), 400
        if bm.family_name != 'Dagger':
            return jsonify({'success': False, 'message': 'Only Dagger moves can be combined'}), 400

    suit_a = bm_a.suit.value if hasattr(bm_a.suit, 'value') else str(bm_a.suit)
    suit_b = bm_b.suit.value if hasattr(bm_b.suit, 'value') else str(bm_b.suit)

    if not _same_colour(suit_a, suit_b):
        return jsonify({'success': False, 'message': 'Daggers must be the same colour to combine'}), 400

    combined_value = bm_a.value + bm_b.value
    # The combined move keeps the first dagger's card reference and suit;
    # the second card stays reserved (cards list stored in extra fields).
    rank_a = bm_a.rank.value if hasattr(bm_a.rank, 'value') else str(bm_a.rank)
    rank_b = bm_b.rank.value if hasattr(bm_b.rank, 'value') else str(bm_b.rank)

    removed_ids = [bm_a.id, bm_b.id]

    # Create the combined Double Dagger move
    combined = BattleMove(
        game_id=game_id,
        player_id=player_id,
        family_name='Double Dagger',
        card_id=bm_a.card_id,
        card_type=bm_a.card_type,
        suit=suit_a,
        rank=f'{rank_a}+{rank_b}',
        value=combined_value,
        card_id_b=bm_b.card_id,
        card_type_b=bm_b.card_type,
        suit_b=suit_b,
        value_a=bm_a.value,
        value_b=bm_b.value,
    )
    db.session.add(combined)

    # Delete the two source moves (cards stay reserved)
    db.session.delete(bm_a)
    db.session.delete(bm_b)

    db.session.flush()

    # Build the serialised combined move
    combined_data = combined.serialize()

    db.session.commit()

    return jsonify({
        'success': True,
        'combined_move': combined_data,
        'removed_ids': removed_ids,
        'game': game.serialize(),
    })


@battle_shop.route('/dismantle_battle_move', methods=['POST'])
def dismantle_battle_move():
    """Split a Double Dagger back into its two original Dagger battle moves.

    The Double Dagger is deleted and two new Dagger BattleMoves are created,
    one for each of the original cards.

    Expects JSON: { game_id, player_id, battle_move_id }

    Returns: { success, restored_moves: [{...}, {...}], removed_id, game }
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')
    battle_move_id = data.get('battle_move_id')

    if not all([game_id, player_id, battle_move_id]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    dd = BattleMove.query.get(battle_move_id)
    if not dd:
        return jsonify({'success': False, 'message': 'Battle move not found'}), 404

    if dd.game_id != game_id or dd.player_id != player_id:
        return jsonify({'success': False, 'message': 'Battle move does not belong to this player'}), 400

    if dd.family_name != 'Double Dagger':
        return jsonify({'success': False, 'message': 'Only Double Daggers can be dismantled'}), 400

    if dd.card_id_b is None:
        return jsonify({'success': False, 'message': 'Double Dagger is missing second card info'}), 400

    # Check max moves — dismantling adds 1 net move (DD removed, 2 daggers added)
    existing = BattleMove.query.filter_by(game_id=game_id, player_id=player_id).count()
    if existing >= MAX_BATTLE_MOVES:
        return jsonify({'success': False, 'message': 'Cannot dismantle: too many battle moves'}), 400

    # Parse the combined rank back into individual ranks
    ranks = dd.rank.split('+') if '+' in dd.rank else [dd.rank, dd.rank]
    rank_a = ranks[0]
    rank_b = ranks[1] if len(ranks) > 1 else ranks[0]

    suit_a = dd.suit if isinstance(dd.suit, str) else dd.suit.value
    suit_b = dd.suit_b if dd.suit_b else suit_a

    # Create two Dagger moves from the stored info
    dagger_a = BattleMove(
        game_id=game_id,
        player_id=player_id,
        family_name='Dagger',
        card_id=dd.card_id,
        card_type=dd.card_type,
        suit=suit_a,
        rank=rank_a,
        value=dd.value_a if dd.value_a is not None else dd.value // 2,
    )
    dagger_b = BattleMove(
        game_id=game_id,
        player_id=player_id,
        family_name='Dagger',
        card_id=dd.card_id_b,
        card_type=dd.card_type_b,
        suit=suit_b,
        rank=rank_b,
        value=dd.value_b if dd.value_b is not None else dd.value // 2,
    )

    removed_id = dd.id
    db.session.delete(dd)
    db.session.add(dagger_a)
    db.session.add(dagger_b)
    db.session.flush()

    db.session.commit()

    return jsonify({
        'success': True,
        'restored_moves': [dagger_a.serialize(), dagger_b.serialize()],
        'removed_id': removed_id,
        'game': game.serialize(),
    })
