# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for Conquer ownership-transfer helpers."""

from types import SimpleNamespace


def _land(db, owner_user_id, *, col, row):
    from models import Land

    land = Land(
        col=col,
        row=row,
        owner_user_id=owner_user_id,
        tier=1,
        gold_rate=1.0,
        suit_bonus_suit='Hearts',
        suit_bonus_value=3,
    )
    db.session.add(land)
    db.session.flush()
    return land


class TestSplitTransferPayload:
    def test_empty_inputs_return_stable_defaults(self):
        from routes.games import _split_transfer_payload

        assert _split_transfer_payload(None, None, None, None) == {
            'kingdom_id': None,
            'kingdom_name': None,
            'land_id': None,
            'land_col': None,
            'land_row': None,
            'split_land_id': None,
            'split_land_col': None,
            'split_land_row': None,
            'component_count': 0,
            'lost_component_count': 0,
            'kept_land_count': 0,
            'transferred_land_count': 0,
            'lost_land_count': 0,
            'gained_land_count': 0,
            'transferred_land_ids': [],
            'land_samples': [],
            'conqueror_user_id': None,
            'conqueror_username': None,
            'defender_user_id': None,
            'defender_username': None,
        }

    def test_uses_land_and_users_and_limits_samples_to_three(self):
        from routes.games import _split_transfer_payload

        summary = {
            'source_kingdom_id': 41,
            'source_kingdom_name': 'Old Kingdom',
            'split_land_id': 52,
            'component_count': '4',
            'lost_component_count': '2',
            'kept_land_count': '3',
            'transferred_land_count': '5',
            'transferred_land_ids': [52, 53, 54, 55, 56],
            'transferred_lands': [
                {'id': 52},
                {'id': 53},
                {'id': 54},
                {'id': 55},
            ],
        }
        land = SimpleNamespace(id=52, col=7, row=9)
        attacker = SimpleNamespace(id=11, username='attacker')
        defender = SimpleNamespace(id=22, username='defender')

        result = _split_transfer_payload(
            summary,
            land,
            attacker,
            defender,
        )

        assert result == {
            'kingdom_id': 41,
            'kingdom_name': 'Old Kingdom',
            'land_id': 52,
            'land_col': 7,
            'land_row': 9,
            'split_land_id': 52,
            'split_land_col': 7,
            'split_land_row': 9,
            'component_count': 4,
            'lost_component_count': 2,
            'kept_land_count': 3,
            'transferred_land_count': 5,
            'lost_land_count': 5,
            'gained_land_count': 5,
            'transferred_land_ids': [52, 53, 54, 55, 56],
            'land_samples': [{'id': 52}, {'id': 53}, {'id': 54}],
            'conqueror_user_id': 11,
            'conqueror_username': 'attacker',
            'defender_user_id': 22,
            'defender_username': 'defender',
        }


class TestRecordSplitTransferNotifications:
    def test_missing_or_empty_transfer_creates_no_notifications(
            self, app, db, two_users):
        from models import KingdomNotification
        from routes.games import _record_split_transfer_notifications

        attacker, defender = two_users

        assert _record_split_transfer_notifications(
            None, None, attacker, defender) is None
        assert _record_split_transfer_notifications(
            {'transferred_land_count': 0},
            None,
            attacker,
            defender,
        ) is None
        assert KingdomNotification.query.count() == 0

    def test_creates_lost_and_claimed_notifications(
            self, app, db, two_users):
        from models import KingdomNotification
        from routes.games import _record_split_transfer_notifications

        attacker, defender = two_users
        land = SimpleNamespace(id=52, col=7, row=9, kingdom_id=88)
        summary = {
            'old_owner_id': defender.id,
            'source_kingdom_id': 41,
            'source_kingdom_name': 'Old Kingdom',
            'split_land_id': land.id,
            'component_count': 2,
            'lost_component_count': 1,
            'kept_land_count': 2,
            'transferred_land_count': 1,
            'transferred_land_ids': [land.id],
            'transferred_lands': [{'id': land.id}],
        }

        result = _record_split_transfer_notifications(
            summary,
            land,
            attacker,
            defender,
        )
        db.session.flush()

        notifications = KingdomNotification.query.order_by(
            KingdomNotification.kind
        ).all()
        assert result is None
        assert len(notifications) == 2
        claimed = next(
            row for row in notifications
            if row.kind == 'kingdom_split_claimed'
        )
        lost = next(
            row for row in notifications
            if row.kind == 'kingdom_split_lost'
        )
        assert claimed.user_id == attacker.id
        assert claimed.kingdom_id == land.kingdom_id
        assert claimed.payload['gained_kingdom_id'] == land.kingdom_id
        assert claimed.payload['defender_user_id'] == defender.id
        assert lost.user_id == defender.id
        assert lost.kingdom_id == summary['source_kingdom_id']
        assert 'gained_kingdom_id' not in lost.payload
        assert lost.payload['conqueror_user_id'] == attacker.id


class TestWipeDefenceDraftsForLostLand:
    def test_missing_identifiers_are_noops(self):
        from routes.games import _wipe_defence_drafts_for_lost_land

        assert _wipe_defence_drafts_for_lost_land(None, 1) is None
        assert _wipe_defence_drafts_for_lost_land(1, None) is None

    def test_deletes_only_matching_defence_drafts(
            self, app, db, two_users):
        from models import LandConfig
        from routes.games import _wipe_defence_drafts_for_lost_land

        owner, other_user = two_users
        land = _land(db, owner.id, col=601, row=601)
        draft = LandConfig(
            user_id=owner.id,
            config_type='defence',
            status='draft',
            land_id=land.id,
        )
        active = LandConfig(
            user_id=owner.id,
            config_type='defence',
            status='active',
            land_id=land.id,
        )
        other_draft = LandConfig(
            user_id=other_user.id,
            config_type='defence',
            status='draft',
            land_id=land.id,
        )
        db.session.add_all([draft, active, other_draft])
        db.session.commit()
        draft_id = draft.id
        active_id = active.id
        other_draft_id = other_draft.id

        result = _wipe_defence_drafts_for_lost_land(owner.id, land.id)
        db.session.flush()

        assert result is None
        assert db.session.get(LandConfig, draft_id) is None
        assert db.session.get(LandConfig, active_id) is not None
        assert db.session.get(LandConfig, other_draft_id) is not None


class TestClearSplitTransferDefences:
    def test_missing_inputs_return_empty_list(self):
        from routes.games import _clear_split_transfer_defences

        assert _clear_split_transfer_defences(None, {}) == []
        assert _clear_split_transfer_defences(1, None) == []

    def test_clears_active_defence_and_drafts_for_transferred_lands(
            self, app, db, two_users):
        from models import LandConfig
        from routes.games import _clear_split_transfer_defences

        old_owner, _ = two_users
        land = _land(db, old_owner.id, col=602, row=602)
        active = LandConfig(
            user_id=old_owner.id,
            config_type='defence',
            status='active',
            land_id=land.id,
        )
        draft = LandConfig(
            user_id=old_owner.id,
            config_type='defence',
            status='draft',
            land_id=land.id,
        )
        db.session.add_all([active, draft])
        db.session.flush()
        land.defence_config_id = active.id
        db.session.commit()
        active_id = active.id
        draft_id = draft.id

        result = _clear_split_transfer_defences(
            old_owner.id,
            {
                'transferred_land_ids': [
                    land.id,
                    999_999,
                ],
            },
        )
        db.session.flush()

        assert result == [active_id]
        assert db.session.get(LandConfig, active_id) is None
        assert db.session.get(LandConfig, draft_id) is None
        assert land.defence_config_id is None
