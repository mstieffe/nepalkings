"""Tests for achievement-unlocked kingdom sigils."""

from models import (db as models_db, Game, KingdomCosmeticUnlock,
                    KingdomNotification, Land, LandAttackLog, Player)
from kingdom_service import (apply_sigil_unlocks, create_kingdom,
                             evaluate_sigil_unlocks_for_user,
                             kingdom_unlocked_cosmetics)


def _add_land(db, col, row, owner_id=None, suit='Hearts', tier=1):
    land = Land(
        col=col,
        row=row,
        tier=tier,
        gold_rate=10.0,
        suit_bonus_suit=suit,
        suit_bonus_value=1,
        owner_user_id=owner_id,
    )
    db.session.add(land)
    db.session.flush()
    return land


def _add_finished_win(db, user_id, mode='duel'):
    game = Game(state='finished', mode=mode)
    db.session.add(game)
    db.session.flush()
    player = Player(user_id=user_id, game_id=game.id)
    db.session.add(player)
    db.session.flush()
    game.winner_player_id = player.id
    return game


def test_evaluate_sigil_unlocks_uses_progress_and_lifetime_stats(db, two_users):
    u1, u2 = two_users
    kingdom = create_kingdom(u1.id)
    kingdom.level = 10

    attack_land = _add_land(db, 20, 0, owner_id=u2.id)
    for _ in range(5):
        db.session.add(LandAttackLog(
            land_id=attack_land.id,
            attacker_user_id=u1.id,
            defender_user_id=u2.id,
            result='attacker_won',
        ))

    for idx, suit in enumerate(('Hearts', 'Diamonds', 'Clubs', 'Spades')):
        _add_land(db, idx, 0, owner_id=u1.id, suit=suit)
    _add_land(db, 10, 0, owner_id=u1.id, suit='Neutral')
    _add_land(db, 11, 0, owner_id=u1.id, suit='Hearts', tier=6)

    for _ in range(10):
        _add_finished_win(db, u1.id, mode='conquer')

    db.session.commit()

    earned = evaluate_sigil_unlocks_for_user(u1.id)

    assert 'sigil_none' in earned
    assert 'sigil_mountain' in earned      # level 5
    assert 'sigil_lotus' in earned         # level 10
    assert 'sigil_wolf' in earned          # 5 conquered lands
    assert 'sigil_sword' in earned         # 10 wins
    assert 'sigil_eagle' in earned         # 10 conquer wins
    assert 'sigil_sun' in earned           # owns every non-neutral suit
    assert 'sigil_dragon' in earned        # owns max-tier land
    assert 'sigil_tower' not in earned     # needs 10 conquered lands


def test_apply_sigil_unlocks_is_idempotent_and_per_kingdom(db, two_users):
    u1, _ = two_users
    kingdom_a = create_kingdom(u1.id)
    kingdom_b = create_kingdom(u1.id)
    kingdom_a.level = 5
    kingdom_b.level = 1
    db.session.commit()

    assert 'sigil_none' in kingdom_unlocked_cosmetics(kingdom_a.id)
    assert 'sigil_mountain' not in kingdom_unlocked_cosmetics(kingdom_a.id)

    newly = apply_sigil_unlocks(u1.id)
    models_db.session.flush()

    assert set(newly) == {
        (kingdom_a.id, 'sigil_mountain'),
        (kingdom_b.id, 'sigil_mountain'),
    }
    assert KingdomCosmeticUnlock.query.filter_by(
        cosmetic_key='sigil_mountain').count() == 2
    assert KingdomNotification.query.filter_by(kind='sigil_unlocked').count() == 2

    assert apply_sigil_unlocks(u1.id) == []
    models_db.session.flush()
    assert KingdomCosmeticUnlock.query.filter_by(
        cosmetic_key='sigil_mountain').count() == 2
    assert KingdomNotification.query.filter_by(kind='sigil_unlocked').count() == 2
