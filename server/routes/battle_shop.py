# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Server routes for battle shop — buy and return battle moves."""

import random
import logging
from flask import Blueprint, request, jsonify, current_app, g
from models import db, Game, Player, MainCard, SideCard, BattleMove, User, LogEntry
from game_service.game_mode import is_tactics_hand_conquer
import server_settings as settings
from routes.auth import require_token, verify_game_membership, verify_player_ownership
from routes.serialization import serialize_battle_moves_for_viewer, serialize_game_for_viewer

battle_shop = Blueprint('battle_shop', __name__)

logger = logging.getLogger('nepalkings.server')
_ai_logger = logging.getLogger('nepalkings.ai.trigger')

@battle_shop.after_request
def _ai_trigger_hook(response):
    """After every POST, check if an AI player needs to act."""
    if request.method == 'POST' and settings.AI_ENABLED:
        if request.headers.get('X-NepalKings-AI-Internal') == '1':
            return response
        game_id = None
        try:
            if request.is_json and request.json:
                game_id = request.json.get('game_id')
        except Exception:
            pass
        if game_id:
            try:
                from ai.ai_worker import trigger_ai_if_needed
                trigger_ai_if_needed(int(game_id), app=current_app._get_current_object())
            except Exception as e:
                _ai_logger.warning(f"AI trigger error in battle_shop hook: {e}")
    return response

# Max battle moves per player
MAX_BATTLE_MOVES = 3


def _available_battle_move_card_count(game_id, player_id):
    """Count unreserved in-hand cards that can still back battle moves."""
    main_count = MainCard.query.filter_by(
        game_id=game_id,
        player_id=player_id,
        in_deck=False,
        part_of_figure=False,
        part_of_battle_move=False,
    ).count()
    side_count = SideCard.query.filter_by(
        game_id=game_id,
        player_id=player_id,
        in_deck=False,
        part_of_figure=False,
        part_of_battle_move=False,
    ).count()
    return main_count + side_count


def _required_battle_move_count(game, player_id):
    """Return how many moves this player must confirm for the battle.

    Duel normally requires all three moves.  The only exception is the rare
    exhausted-deck state where auto-fill could not leave enough in-hand cards;
    then the player must confirm every move they can actually make.
    """
    if not game or game.mode == 'conquer':
        return 0
    existing = BattleMove.query.filter_by(
        game_id=game.id,
        player_id=player_id,
    ).count()
    available_cards = _available_battle_move_card_count(game.id, player_id)
    return min(MAX_BATTLE_MOVES, existing + available_cards)


def _battle_move_requirement_payload(game, player_id):
    required = _required_battle_move_count(game, player_id)
    existing = BattleMove.query.filter_by(
        game_id=game.id,
        player_id=player_id,
    ).count() if game else 0
    return {
        'required_battle_moves': required,
        'selected_battle_moves': existing,
        'max_battle_moves': MAX_BATTLE_MOVES,
    }


def _is_battle_move_selection_phase(game):
    """Return True while players are selecting/confirming pre-battle moves."""
    return bool(game and game.battle_confirmed and game.battle_turn_player_id is None)


def _is_tactics_hand_conquer(game):
    """Return True for conquer games using the unified tactics-hand model.

    These games skip the legacy battle_shop buy/return/confirm phase: the
    configured battle moves are already the player's starting hand at
    battle-decision time, and the player interacts with them directly via
    play/combine/dismantle/gamble.
    """
    return is_tactics_hand_conquer(game)


def _block_legacy_battle_shop_mutation(game):
    """Reject buy/return/confirm requests for tactics-hand conquer games."""
    if _is_tactics_hand_conquer(game):
        return jsonify({
            'success': False,
            'message': 'Battle shop is disabled for this conquer game (tactics-hand model).',
            'reason': 'tactics_hand_no_shop',
        }), 400
    return None


def _guard_confirmed_selection_locked(game, player_id):
    """Block editing pre-battle moves after this player pressed Ready."""
    if not _is_battle_move_selection_phase(game):
        return None

    confirmed = game.battle_moves_confirmed or {}
    if confirmed.get(str(player_id)):
        return jsonify({
            'success': False,
            'message': 'Your battle moves are already confirmed and cannot be changed.',
            'reason': 'battle_moves_locked'
        }), 400
    return None


@battle_shop.route('/buy_battle_move', methods=['POST'])
@require_token
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

    err = verify_player_ownership(player_id)
    if err:
        return err

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    block = _block_legacy_battle_shop_mutation(game)
    if block:
        return block

    player = db.session.get(Player, player_id)
    if not player or player.game_id != game_id:
        return jsonify({'success': False, 'message': 'Player not found in this game'}), 404

    # Once active rounds start, battle moves are fixed.
    if game.battle_confirmed and game.battle_turn_player_id is not None:
        return jsonify({
            'success': False,
            'message': 'Cannot buy battle moves after battle rounds have started.'
        }), 400

    lock_err = _guard_confirmed_selection_locked(game, player_id)
    if lock_err:
        return lock_err

    # Check max battle moves
    existing_moves = BattleMove.query.filter_by(game_id=game_id, player_id=player_id).count()
    if existing_moves >= MAX_BATTLE_MOVES:
        return jsonify({'success': False, 'message': f'Maximum of {MAX_BATTLE_MOVES} battle moves reached'}), 400

    # Find and validate the card
    if card_type == 'side':
        card = db.session.get(SideCard, card_id)
    else:
        card = db.session.get(MainCard, card_id)

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
        'game': serialize_game_for_viewer(game, g.user_id),
    })


@battle_shop.route('/return_battle_move', methods=['POST'])
@require_token
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

    battle_move = db.session.get(BattleMove, battle_move_id)
    if not battle_move:
        return jsonify({'success': False, 'message': 'Battle move not found'}), 404

    err = verify_player_ownership(battle_move.player_id)
    if err:
        return err

    if battle_move.game_id != game_id or battle_move.player_id != player_id:
        return jsonify({'success': False, 'message': 'Battle move does not belong to this player'}), 400

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    block = _block_legacy_battle_shop_mutation(game)
    if block:
        return block

    if game.battle_confirmed and game.battle_turn_player_id is not None:
        return jsonify({
            'success': False,
            'message': 'Cannot return battle moves after battle rounds have started.'
        }), 400

    lock_err = _guard_confirmed_selection_locked(game, player_id)
    if lock_err:
        return lock_err

    # Un-reserve the card
    if battle_move.card_type == 'side':
        card = db.session.get(SideCard, battle_move.card_id)
    else:
        card = db.session.get(MainCard, battle_move.card_id)

    if card:
        card.part_of_battle_move = False

    # Delete the battle move
    db.session.delete(battle_move)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Battle move returned',
        'game': serialize_game_for_viewer(game, g.user_id),
    })


@battle_shop.route('/get_battle_moves', methods=['GET'])
@require_token
def get_battle_moves():
    """Get all battle moves for a player in a game.

    Expects query params: game_id, player_id
    """
    game_id = request.args.get('game_id', type=int)
    player_id = request.args.get('player_id', type=int)

    if not game_id or not player_id:
        return jsonify({'success': False, 'message': 'Missing game_id or player_id'}), 400
    membership_err = verify_game_membership(game_id)
    if membership_err:
        return membership_err
    game = db.session.get(Game, game_id)
    player = db.session.get(Player, player_id)
    if not player or player.game_id != game_id:
        return jsonify({'success': False, 'message': 'Player not found in this game'}), 404
    viewer = Player.query.filter_by(game_id=game_id, user_id=g.user_id).first()
    reveal = False
    if viewer:
        from routes.serialization import viewer_has_all_seeing_eye
        reveal = viewer_has_all_seeing_eye(game.serialize(), viewer.id)

    moves = BattleMove.query.filter_by(game_id=game_id, player_id=player_id).all()
    return jsonify({
        'success': True,
        'battle_moves': serialize_battle_moves_for_viewer(
            moves, viewer.id if viewer else None, reveal),
    })


@battle_shop.route('/confirm_battle_moves', methods=['POST'])
@require_token
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

    err = verify_player_ownership(player_id)
    if err:
        return err

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    block = _block_legacy_battle_shop_mutation(game)
    if block:
        return block

    if not game.battle_confirmed:
        return jsonify({
            'success': False,
            'message': 'Battle move confirmation is only available during battle preparation.'
        }), 400

    # Idempotent: if battle already started, treat this as already ready.
    if game.battle_turn_player_id is not None:
        return jsonify({
            'success': True,
            'both_ready': True,
            'game': serialize_game_for_viewer(game, g.user_id),
            **_battle_move_requirement_payload(game, player_id),
        })

    # Verify the player has all currently possible battle moves.  Duel normally
    # requires three, but if auto-fill truly cannot provide enough cards (deck
    # exhausted and no more unreserved hand cards), the player may confirm fewer.
    # Conquer mode is config-driven and may have fewer prebuilt moves.
    move_count = BattleMove.query.filter_by(game_id=game_id, player_id=player_id).count()
    required_count = _required_battle_move_count(game, player_id)
    if game.mode != 'conquer' and move_count < required_count:
        return jsonify({
            'success': False,
            'message': f'You must select {required_count} battle move(s) before confirming.',
            **_battle_move_requirement_payload(game, player_id),
        }), 400

    # Record this player's confirmation
    player_ids = [str(p.id) for p in game.players]
    raw_confirmed = dict(game.battle_moves_confirmed) if game.battle_moves_confirmed else {}
    # Keep only current players to avoid stale confirmation maps.
    confirmed = {pid: bool(raw_confirmed.get(pid)) for pid in player_ids if raw_confirmed.get(pid)}
    confirmed[str(player_id)] = True
    game.battle_moves_confirmed = confirmed

    # Check if both players have confirmed
    both_ready = all(confirmed.get(pid) for pid in player_ids)

    # Safety: even if confirmation flags are set, ensure each player still has
    # the required number of moves before battle rounds can start.
    # (skip for conquer mode — moves are pre-built from config)
    if both_ready and game.mode != 'conquer':
        not_ready_ids = []
        for pid in player_ids:
            pid_int = int(pid)
            cnt = BattleMove.query.filter_by(game_id=game_id, player_id=pid_int).count()
            required = _required_battle_move_count(game, pid_int)
            if cnt < required:
                not_ready_ids.append(pid)

        if not_ready_ids:
            for pid in not_ready_ids:
                confirmed.pop(pid, None)
            game.battle_moves_confirmed = confirmed
            both_ready = False

    # Initialize 3-round battle tracking when both players are ready
    if both_ready:
        game.battle_moves_confirmed = {pid: True for pid in player_ids}
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
        'game': serialize_game_for_viewer(game, g.user_id),
        **_battle_move_requirement_payload(game, player_id),
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
@require_token
def gamble_battle_move():
    """Gamble: sacrifice one battle move and draw two random replacements.

    This action is only allowed DURING active battle rounds (not in battle shop).
    A player can gamble at most once per battle round, up to 3 times per battle.

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

    err = verify_player_ownership(player_id)
    if err:
        return err

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    block = _block_legacy_battle_shop_mutation(game)
    if block:
        return block

    lock_err = _guard_confirmed_selection_locked(game, player_id)
    if lock_err:
        return lock_err

    player = db.session.get(Player, player_id)
    if not player or player.game_id != game_id:
        return jsonify({'success': False, 'message': 'Player not found in this game'}), 404

    # Gambling is a battle-round action, not a battle-shop action.
    if not game.battle_confirmed:
        return jsonify({'success': False, 'message': 'Gamble is only available during active battle rounds'}), 400

    if game.battle_turn_player_id != player_id:
        return jsonify({'success': False, 'message': 'It is not your turn in the battle'}), 400

    # Enforce gamble limits: once per round, max 3 per battle.
    gamble_counts = game.battle_gamble_counts or {}
    pid_str = str(player_id)
    player_gamble_state = gamble_counts.get(pid_str, 0)

    if isinstance(player_gamble_state, dict):
        try:
            used_count = int(player_gamble_state.get('count', 0) or 0)
        except (TypeError, ValueError):
            used_count = 0
        used_rounds = []
        for r in player_gamble_state.get('rounds', []):
            try:
                used_rounds.append(int(r))
            except (TypeError, ValueError):
                continue
        used_rounds = sorted(set(used_rounds))
    else:
        try:
            used_count = int(player_gamble_state or 0)
        except (TypeError, ValueError):
            used_count = 0
        used_rounds = []

    current_round = int(game.battle_round or 0)

    if current_round in used_rounds:
        return jsonify({'success': False, 'message': 'You can only gamble once per battle round'}), 400

    if used_count >= 3:
        return jsonify({'success': False, 'message': 'You can only gamble 3 times per battle (once per round)'}), 400

    # Find the battle move to sacrifice
    bm = db.session.get(BattleMove, battle_move_id)
    if not bm:
        return jsonify({'success': False, 'message': 'Battle move not found'}), 404
    if bm.game_id != game_id or bm.player_id != player_id:
        return jsonify({'success': False, 'message': 'Battle move does not belong to this player'}), 400

    # ── Conquer mode: special gamble flow ──
    if game.mode == 'conquer':
        return _gamble_conquer(game, player, bm, gamble_counts, pid_str,
                               used_count, used_rounds, current_round)

    # 1. Un-reserve the sacrificed card
    if bm.card_type == 'side':
        old_card = db.session.get(SideCard, bm.card_id)
    else:
        old_card = db.session.get(MainCard, bm.card_id)
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

    # Track gamble usage for this player (count + rounds used)
    used_rounds = sorted(set(used_rounds + [current_round]))
    gamble_counts[pid_str] = {
        'count': used_count + 1,
        'rounds': used_rounds,
    }
    game.battle_gamble_counts = gamble_counts
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(game, 'battle_gamble_counts')

    drew_desc = ', '.join(
        '{}/{}/{} id={}'.format(m.get('family_name'), m.get('suit'), m.get('rank'), m.get('id'))
        for m in new_moves
    )
    logger.info(f"[GAMBLE] game={game_id} player={player_id} round={current_round} "
                f"sacrificed_bm={battle_move_id} ({sacrificed_data.get('family_name')}/{sacrificed_data.get('suit')}) "
                f"drew=[{drew_desc}]")

    db.session.commit()

    return jsonify({
        'success': True,
        'sacrificed': sacrificed_data,
        'new_moves': new_moves,
        'game': serialize_game_for_viewer(game, g.user_id),
    })


def _gamble_conquer(game, player, bm, gamble_counts, pid_str,
                    used_count, used_rounds, current_round):
    """Handle gamble for conquer mode.

    Sacrificed card is permanently removed from the player's collection.
    Two random replacement cards are generated as temporary in-game cards
    (not added to the collection).
    """
    from models import CollectionCard, LandConfig, LandConfigBattleMove

    sacrificed_data = bm.serialize()

    # Find and delete the corresponding CollectionCard via the config
    cfg_id = game.conquer_config_id
    if cfg_id:
        # Match by suit + rank in the config's battle moves
        cfg_move = LandConfigBattleMove.query.filter_by(
            config_id=cfg_id, suit=bm.suit, rank=bm.rank,
        ).first()
        if cfg_move and cfg_move.card_id:
            cc = db.session.get(CollectionCard, cfg_move.card_id)
            if cc:
                db.session.delete(cc)
            db.session.delete(cfg_move)

    # Delete the in-game MainCard backing this battle move
    old_card = db.session.get(MainCard, bm.card_id)
    if old_card:
        db.session.delete(old_card)

    # Delete the sacrificed battle move
    db.session.delete(bm)

    # Generate 2 random temporary replacement cards
    _SUITS = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
    _RANKS = ['7', '8', '9', '10', 'J', 'Q', 'A']
    _RANK_VALUES = {'7': 7, '8': 8, '9': 9, '10': 10, 'J': 1, 'Q': 2, 'A': 3}

    new_moves = []
    for _ in range(2):
        suit = random.choice(_SUITS)
        rank = random.choice(_RANKS)
        value = _RANK_VALUES.get(rank, 0)
        family_name = _family_for_rank(rank)

        mc = MainCard(
            rank=rank,
            suit=suit,
            value=value,
            game_id=game.id,
            player_id=player.id,
            in_deck=False,
            part_of_figure=False,
            part_of_battle_move=True,
        )
        db.session.add(mc)
        db.session.flush()

        move = BattleMove(
            game_id=game.id,
            player_id=player.id,
            family_name=family_name,
            card_id=mc.id,
            card_type='main',
            suit=suit,
            rank=rank,
            value=value,
        )
        db.session.add(move)
        db.session.flush()
        new_moves.append(move.serialize())

    # Track gamble usage
    used_rounds = sorted(set(used_rounds + [current_round]))
    gamble_counts[pid_str] = {
        'count': used_count + 1,
        'rounds': used_rounds,
    }
    game.battle_gamble_counts = gamble_counts
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(game, 'battle_gamble_counts')

    drew_desc = ', '.join(
        '{}/{}/{} id={}'.format(m.get('family_name'), m.get('suit'), m.get('rank'), m.get('id'))
        for m in new_moves
    )
    logger.info(f"[GAMBLE_CONQUER] game={game.id} player={player.id} round={current_round} "
                f"sacrificed_bm={bm.id} ({sacrificed_data.get('family_name')}/{sacrificed_data.get('suit')}) "
                f"drew=[{drew_desc}]")

    db.session.commit()

    return jsonify({
        'success': True,
        'sacrificed': sacrificed_data,
        'new_moves': new_moves,
        'game': serialize_game_for_viewer(game, g.user_id),
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
@require_token
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

    err = verify_player_ownership(player_id)
    if err:
        return err

    if move_id_a == move_id_b:
        return jsonify({'success': False, 'message': 'Cannot combine a move with itself'}), 400

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    block = _block_legacy_battle_shop_mutation(game)
    if block:
        return block

    lock_err = _guard_confirmed_selection_locked(game, player_id)
    if lock_err:
        return lock_err

    bm_a = db.session.get(BattleMove, move_id_a)
    bm_b = db.session.get(BattleMove, move_id_b)

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
        'game': serialize_game_for_viewer(game, g.user_id),
    })


@battle_shop.route('/dismantle_battle_move', methods=['POST'])
@require_token
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

    err = verify_player_ownership(player_id)
    if err:
        return err

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    block = _block_legacy_battle_shop_mutation(game)
    if block:
        return block

    lock_err = _guard_confirmed_selection_locked(game, player_id)
    if lock_err:
        return lock_err

    dd = db.session.get(BattleMove, battle_move_id)
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
        'game': serialize_game_for_viewer(game, g.user_id),
    })
