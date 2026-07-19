# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Serialization of stable payloads for already-finished Conquer games."""

from models import Land, LandAttackLog, User, db


def serialize_finished_conquer_result(
    game,
    viewer_user_id=None,
    *,
    serialize_game_for_viewer,
    serialize_viewer_onboarding,
    conquer_attacker_player,
    conquer_original_defender_player,
):
    """Return a stable result payload for an already-finished Conquer game."""
    if not game or game.mode != 'conquer' or game.state != 'finished':
        return None

    serialized_game = (
        serialize_game_for_viewer(game, viewer_user_id)
        if viewer_user_id is not None
        else game.serialize()
    )

    land = db.session.get(Land, game.land_id) if game.land_id else None
    attacker_player = conquer_attacker_player(game)
    attacker_id = attacker_player.id if attacker_player else game.invader_player_id

    if game.winner_player_id is None:
        conquer_result = 'draw'
        attacker_won = False
    else:
        attacker_won = game.winner_player_id == attacker_id
        conquer_result = 'attacker_won' if attacker_won else 'defender_won'

    last_result = (
        game.last_battle_result
        if isinstance(game.last_battle_result, dict)
        else {}
    )

    payload = {
        'success': True,
        'message': f'Conquer battle already resolved: {conquer_result}',
        'already_resolved': True,
        'conquer_result': conquer_result,
        'attacker_won': attacker_won,
        'land_id': game.land_id,
        'land_gold_rate': land.gold_rate if land else 0,
        'land_tier': land.tier if land else None,
        'game': serialized_game,
    }
    onboarding = serialize_viewer_onboarding(viewer_user_id)
    if onboarding is not None:
        payload['onboarding'] = onboarding

    # Battle math is stored in one stable, non-viewer-specific perspective:
    # the player who was advancing when the clash resolved. This matters for
    # Invader Swap, where that player is the original Conquer defender.
    battle_math_keys = ('fig_diff', 'round_diff', 'adv_power', 'def_power')
    for key in battle_math_keys:
        if key in last_result:
            payload[key] = last_result.get(key)

    score_player_id = last_result.get('battle_score_player_id')
    if score_player_id is None and (
        last_result.get('fig_diff') is not None
        and last_result.get('round_diff') is not None
    ):
        score_player_id = game.invader_player_id

    score_diff = last_result.get('battle_score_diff')
    if score_diff is None and (
        last_result.get('fig_diff') is not None
        and last_result.get('round_diff') is not None
    ):
        try:
            score_diff = (
                int(last_result.get('fig_diff') or 0)
                + int(last_result.get('round_diff') or 0)
            )
        except (TypeError, ValueError):
            score_diff = None

    if score_player_id is not None:
        payload['battle_score_player_id'] = score_player_id
    if score_diff is not None:
        try:
            score_diff = int(score_diff)
            payload['battle_score_diff'] = score_diff
        except (TypeError, ValueError):
            score_diff = None

    viewer_player = None
    if viewer_user_id is not None:
        viewer_player = next(
            (
                player
                for player in game.players
                if str(player.user_id) == str(viewer_user_id)
            ),
            None,
        )
    if score_diff is not None and score_player_id is not None and viewer_player:
        viewer_total = (
            score_diff
            if str(viewer_player.id) == str(score_player_id)
            else -score_diff
        )
        payload['total_diff'] = viewer_total
        payload['battle_total_diff'] = viewer_total

    card_detail_keys = (
        'card_won_suit',
        'card_won_rank',
        'card_lost_suit',
        'card_lost_rank',
    )
    for key in card_detail_keys:
        if key in last_result:
            payload[key] = last_result.get(key)

    # Legacy rows may need their card details recovered from the latest attack
    # log. Once any result detail is cached, trust the per-game snapshot.
    has_cached_result_details = bool(
        last_result.get('conquer_resolved')
        or any(key in last_result for key in card_detail_keys)
        or 'conquer_consumed_cards' in last_result
        or 'conquer_loot_gained_cards' in last_result
        or 'conquer_loot_lost_cards' in last_result
    )
    if game.land_id and not has_cached_result_details:
        latest_log = (
            LandAttackLog.query.filter_by(land_id=game.land_id)
            .order_by(LandAttackLog.id.desc())
            .first()
        )
        if latest_log:
            if payload.get('card_won_suit') is None:
                payload['card_won_suit'] = latest_log.card_won_suit
            if payload.get('card_won_rank') is None:
                payload['card_won_rank'] = latest_log.card_won_rank
            if payload.get('card_lost_suit') is None:
                payload['card_lost_suit'] = latest_log.card_lost_suit
            if payload.get('card_lost_rank') is None:
                payload['card_lost_rank'] = latest_log.card_lost_rank
    if 'cards_spent' in last_result:
        payload['cards_spent'] = last_result.get('cards_spent')
    if 'conquer_consumed_cards' in last_result:
        payload['consumed_cards'] = last_result.get('conquer_consumed_cards') or []
    if 'defence_consumed_cards' in last_result:
        payload['defence_consumed_cards'] = (
            last_result.get('defence_consumed_cards') or []
        )
    if 'conquer_loot_lost_cards' in last_result:
        payload['loot_lost_cards'] = (
            last_result.get('conquer_loot_lost_cards') or []
        )
    if 'conquer_loot_gained_cards' in last_result:
        payload['loot_gained_cards'] = (
            last_result.get('conquer_loot_gained_cards') or []
        )
    if 'kingdom_split_transfer' in last_result:
        payload['kingdom_split_transfer'] = last_result.get(
            'kingdom_split_transfer'
        )
    if 'is_ai_defender' in last_result:
        payload['is_ai_defender'] = bool(last_result.get('is_ai_defender'))
    for key in (
        'conquer_attacker_player_id',
        'conquer_defender_player_id',
        'conquer_attacker_user_id',
        'conquer_defender_user_id',
    ):
        if key in last_result:
            payload[key] = last_result.get(key)
    if 'auto_loss_reason' in last_result:
        payload['auto_loss_reason'] = last_result.get('auto_loss_reason')
    if 'auto_loss_detail' in last_result:
        payload['auto_loss_detail'] = last_result.get('auto_loss_detail')

    cached_review_config = last_result.get('victory_review_config_id')
    cached_review_land = last_result.get('victory_review_land_id')
    attacker_user_id = last_result.get('conquer_attacker_user_id')
    attacker_user = (
        db.session.get(User, attacker_user_id) if attacker_user_id else None
    )
    review_available = bool(
        attacker_won
        and cached_review_config
        and attacker_user is not None
        and not getattr(attacker_user, 'is_ai', False)
        and not bool(last_result.get('attacker_first_conquest'))
        and game.victory_reviewed_at is None
    )
    payload['victory_review_available'] = review_available
    payload['victory_review_config_id'] = (
        cached_review_config if review_available else None
    )
    payload['victory_review_land_id'] = (
        cached_review_land if review_available else None
    )

    if conquer_result == 'draw':
        payload['outcome'] = 'draw'
        return payload

    payload['outcome'] = 'win'
    payload['winner_player_id'] = game.winner_player_id

    defender_player = conquer_original_defender_player(game)
    defender_player_id = defender_player.id if defender_player else None
    payload['loser_player_id'] = (
        defender_player_id if attacker_won else attacker_id
    )

    return payload
