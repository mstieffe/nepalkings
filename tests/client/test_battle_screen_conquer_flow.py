# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for conquer end-flow handling in BattleScreen."""

from types import SimpleNamespace


def _battle_screen_class():
    from game.screens.battle_screen import BattleScreen

    return BattleScreen


class TestBattleScreenConquerFlow:
    def _screen_for_kingdom_bonus(self, player_is_invader=True):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)
        screen.player_is_invader = player_is_invader
        screen.game = SimpleNamespace(
            mode='conquer',
            land_suit_bonus_suit='Hearts',
        )
        screen.player_figure = None
        screen.player_figure_2 = None
        screen.opponent_figure = None
        screen.opponent_figure_2 = None
        screen.player_figure_icon = None
        screen.player_figure_icon_2 = None
        screen.opponent_figure_icon = None
        screen.opponent_figure_icon_2 = None
        screen.player_played = [None, None, None]
        screen.opponent_played = [None, None, None]
        return BattleScreen, screen

    def test_tactics_hand_conquer_does_not_legacy_auto_skip(self, monkeypatch):
        from game.screens import battle_screen as battle_module

        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)
        screen.game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            game_id=10,
            player_id=20,
            game_over=False,
        )
        screen.is_player_turn = True
        screen._auto_skip_pending = False
        screen._has_played_move_this_turn = False
        screen.player_moves = []
        screen.player_played = [None, None, None]
        screen.opponent_played = [None, None, None]

        calls = []

        def fake_skip(*args):
            calls.append(args)
            return {'success': True}

        monkeypatch.setattr(battle_module.game_service, 'skip_battle_turn', fake_skip)

        BattleScreen._check_auto_skip(screen)

        assert calls == []

    @staticmethod
    def _figure(base=10, suit='Hearts', field='village'):
        return SimpleNamespace(
            suit=suit,
            family=SimpleNamespace(field=field),
            get_value=lambda: base,
            get_total_enchantment_modifier=lambda: 0,
        )

    def test_kingdom_skills_do_not_modify_client_figure_power_preview(self):
        BattleScreen, screen = self._screen_for_kingdom_bonus(player_is_invader=True)
        figure = self._figure(base=10, suit='Hearts', field='village')
        icon = SimpleNamespace(
            battle_bonus_received=2,
            buffs_allies_bonus=0,
            buffs_allies_defence_bonus=0,
            distance_attack_penalty=0,
            battle_bonus_blocked=False,
        )

        defender_power = BattleScreen._get_figure_total_power(screen, figure, icon)

        assert defender_power == 12  # 10 base +2 normal support only

    def test_blocks_bonus_still_zeroes_normal_support_bonus(self):
        BattleScreen, screen = self._screen_for_kingdom_bonus(player_is_invader=True)
        figure = self._figure(base=10, suit='Hearts', field='village')
        icon = SimpleNamespace(
            battle_bonus_received=2,
            buffs_allies_bonus=0,
            buffs_allies_defence_bonus=0,
            distance_attack_penalty=0,
            battle_bonus_blocked=True,
        )

        power = BattleScreen._get_figure_total_power(screen, figure, icon)

        assert power == 10  # base only; normal support bonus is blocked

    def test_active_temple_blocks_all_matching_battle_targets(self):
        BattleScreen, screen = self._screen_for_kingdom_bonus(player_is_invader=True)
        temple = SimpleNamespace(
            id=1,
            name='Himalaya Temple',
            suit='Spades',
            blocks_bonus=True,
            requires={},
        )
        target_a = SimpleNamespace(id=2, name='Djungle Warrior', suit='Hearts')
        target_b = SimpleNamespace(id=3, name='Djungle Cavalry', suit='Hearts')
        icon_a = SimpleNamespace(battle_bonus_blocked=False)
        icon_b = SimpleNamespace(battle_bonus_blocked=False)

        screen.player_figure = temple
        screen.player_figure_2 = None
        screen.opponent_figure = target_a
        screen.opponent_figure_2 = target_b
        screen.player_figure_icon = SimpleNamespace(battle_bonus_blocked=False)
        screen.player_figure_icon_2 = None
        screen.opponent_figure_icon = icon_a
        screen.opponent_figure_icon_2 = icon_b
        screen._resources_data = {'produces': {}, 'requires': {}}
        screen._opponent_resources_data = {'produces': {}, 'requires': {}}

        BattleScreen._detect_blocks_bonus(
            screen,
            player_figures=[temple],
            opponent_figures=[target_a, target_b],
        )

        assert icon_a.battle_bonus_blocked is True
        assert icon_b.battle_bonus_blocked is True
        assert screen.player_blocks_bonus_figure is temple
        assert screen.player_blocks_bonus_figures == [temple]

    def test_kingdom_skills_do_not_modify_client_call_figure_preview(self):
        BattleScreen, screen = self._screen_for_kingdom_bonus(player_is_invader=False)
        screen.player_buffs_allies_figures = []
        screen.opponent_buffs_allies_figures = []
        screen._player_da_archers = []
        screen._opponent_da_archers = []
        call_fig = self._figure(base=7, suit='Clubs', field='village')
        move = {
            'family_name': 'Call',
            'value': 5,
            'suit': 'Clubs',
            '_call_figure': call_fig,
        }

        power = BattleScreen._get_move_effective_power(
            screen, move, is_player=True, round_idx=0)

        assert power == 12  # 7 base +5 matching call move only

    def test_defender_call_figure_power_ignores_wall_bonus(self):
        BattleScreen, screen = self._screen_for_kingdom_bonus(player_is_invader=True)
        screen.player_buffs_allies_figures = []
        screen.opponent_buffs_allies_figures = []
        screen.player_buffs_allies_defence_figures = []
        screen.opponent_buffs_allies_defence_figures = [
            SimpleNamespace(number_card=SimpleNamespace(value=3)),
            SimpleNamespace(number_card=SimpleNamespace(value=6)),
        ]
        screen._player_da_archers = []
        screen._opponent_da_archers = []
        call_fig = self._figure(base=7, suit='Clubs', field='military')
        move = {
            'family_name': 'Call Military',
            'value': 5,
            'suit': 'Clubs',
            '_call_figure': call_fig,
        }

        power = BattleScreen._get_move_effective_power(
            screen, move, is_player=False, round_idx=0)

        assert power == 12  # 7 base +5 matching call move only; wall excluded

    def test_round_slot_called_figure_omits_wall_support_icons(self, monkeypatch):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)
        screen.window = SimpleNamespace(blit=lambda *args, **kwargs: None)
        screen.battle_move_detail_box = None
        screen.figure_detail_box = None
        screen.player_buffs_allies_figures = []
        screen.opponent_buffs_allies_figures = []
        screen.player_buffs_allies_defence_figures = []
        screen.opponent_buffs_allies_defence_figures = [
            SimpleNamespace(number_card=SimpleNamespace(value=6),
                            family=SimpleNamespace(icon_img=object())),
        ]
        screen.player_distance_attack_figure = None
        screen.opponent_distance_attack_figure = None
        screen._round_fig_icons = []
        screen._slot_glow_cache = {}
        screen._slot_icon_cache = {}
        screen._slot_frame_cache = {}
        screen._slot_suit_icon_cache = {}
        screen.font_icon_value = None
        screen.font_small = None
        screen._get_da_call_penalty = lambda *args, **kwargs: 0

        captured = {}

        def fake_draw_slot_figure_icons(self, cx, slot_cy, sw, slot_figures, is_player, r_index):
            captured['slot_figures'] = slot_figures

        monkeypatch.setattr(BattleScreen, '_draw_slot_figure_icons', fake_draw_slot_figure_icons)
        monkeypatch.setattr('game.screens.battle_screen.draw_battle_move_icon',
                            lambda *args, **kwargs: None)

        call_fig = SimpleNamespace(
            suit='Clubs',
            family=SimpleNamespace(field='military', icon_img=object()),
            get_value=lambda: 7,
        )
        played_move = {
            'family_name': 'Call Military',
            'suit': 'Clubs',
            'value': 5,
            '_call_figure': call_fig,
        }

        BattleScreen._draw_round_slot(
            screen, 0, 0, played_move, False, is_player=False, r_index=0)

        assert captured['slot_figures'] == [(call_fig, 'call')]

    def test_conquer_defeat_ack_queries_finish_battle_and_sets_fallback_game_over(self, monkeypatch):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        updates = []
        conquer_results = []
        resets = []
        finish_calls = []

        game = SimpleNamespace(
            mode='conquer',
            game_id=91,
            player_id=17,
            pending_game_over=None,
            game_over=False,
            update_from_dict=lambda data: updates.append(data),
        )

        screen.game = game
        screen._handle_conquer_end = lambda result: conquer_results.append(result)
        screen._reset_after_battle = lambda: resets.append(True)

        def fake_finish(game_id, player_id, total_diff):
            finish_calls.append({
                'game_id': game_id,
                'player_id': player_id,
                'total_diff': total_diff,
            })
            return {
                'success': True,
                'outcome': 'win',
                'winner_player_id': 99,
                'game': {'id': game_id},
            }

        def fail_pick(*_args, **_kwargs):
            raise AssertionError('loser flow must never call finish_battle_pick_card')

        monkeypatch.setattr('game.screens.battle_screen.game_service.finish_battle', fake_finish)
        monkeypatch.setattr('game.screens.battle_screen.game_service.finish_battle_pick_card', fail_pick)

        BattleScreen._on_defeat_acknowledged(screen, 'ok')

        assert len(finish_calls) == 1
        assert finish_calls[0]['game_id'] == 91
        assert finish_calls[0]['player_id'] == 17
        assert finish_calls[0]['total_diff'] == 0

        assert updates == [{'id': 91}]
        assert conquer_results == []
        assert game.pending_game_over == {'winner_player_id': 99}
        assert game.game_over is True
        assert resets == [True]

    def test_conquer_defeat_ack_routes_directly_when_conquer_result_is_ready(self, monkeypatch):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        conquer_results = []
        resets = []

        game = SimpleNamespace(
            mode='conquer',
            game_id=47,
            player_id=5,
            pending_game_over=None,
            game_over=False,
            update_from_dict=lambda _data: None,
        )

        screen.game = game
        screen._handle_conquer_end = lambda result: conquer_results.append(result)
        screen._reset_after_battle = lambda: resets.append(True)

        def fake_finish(game_id, player_id, total_diff):
            return {
                'success': True,
                'conquer_result': 'defender_won',
                'attacker_won': False,
            }

        monkeypatch.setattr('game.screens.battle_screen.game_service.finish_battle', fake_finish)

        BattleScreen._on_defeat_acknowledged(screen, 'ok')

        assert len(conquer_results) == 1
        assert conquer_results[0]['conquer_result'] == 'defender_won'
        assert resets == []

    def test_conquer_draw_fallback_payload_routes_to_conquer_end(self):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        handled = []
        screen.game = SimpleNamespace(mode='conquer')
        screen._handle_conquer_end = lambda result: handled.append(result)

        BattleScreen._show_draw_result(screen, {'outcome': 'draw'})

        assert len(handled) == 1
        assert handled[0]['conquer_result'] == 'draw'
        assert handled[0]['attacker_won'] is False

    def test_conquer_draw_dialogue_explains_spent_one_shot_cards(self):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        captured = {}
        screen.game = SimpleNamespace(invader=True, game_over=False, mode='conquer')
        screen.make_dialogue_box = lambda message, **kwargs: captured.update({
            'message': message,
            'kwargs': kwargs,
        })

        BattleScreen._handle_conquer_end(screen, {
            'conquer_result': 'draw',
            'attacker_won': False,
        })

        msg = captured.get('message', '')
        assert 'land remains unchanged' in msg
        assert 'No cards were looted' in msg
        assert 'all attack cards returned' in msg

    def test_conquer_attacker_loss_dialogue_lists_looted_and_returned_cards(self, monkeypatch):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        class _DummyCardImg:
            def __init__(self, *_args, **_kwargs):
                self.front_img = None

        monkeypatch.setattr('game.components.cards.card_img.CardImg', _DummyCardImg)

        captured = {}
        screen.window = object()
        screen.game = SimpleNamespace(invader=True, game_over=False, mode='conquer')
        screen.make_dialogue_box = lambda message, **kwargs: captured.update({
            'message': message,
            'kwargs': kwargs,
        })

        BattleScreen._handle_conquer_end(screen, {
            'conquer_result': 'defender_won',
            'attacker_won': False,
            'loot_lost_cards': [
                {'suit': 'Hearts', 'rank': 'K'},
            ],
        })

        msg = captured.get('message', '')
        assert 'Cards looted by defending kingdom:' in msg
        assert 'K of Hearts' in msg
        assert 'Every unlooted attack card returned' in msg
        assert 'Consumed cards:' not in msg

    def test_conquer_attacker_loss_dialogue_uses_ai_defence_wording(self, monkeypatch):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        class _DummyCardImg:
            def __init__(self, *_args, **_kwargs):
                self.front_img = None

        monkeypatch.setattr('game.components.cards.card_img.CardImg', _DummyCardImg)

        captured = {}
        screen.window = object()
        screen.game = SimpleNamespace(invader=True, game_over=False, mode='conquer')
        screen.make_dialogue_box = lambda message, **kwargs: captured.update({
            'message': message,
            'kwargs': kwargs,
        })

        BattleScreen._handle_conquer_end(screen, {
            'conquer_result': 'defender_won',
            'attacker_won': False,
            'is_ai_defender': True,
            'loot_lost_cards': [
                {'suit': 'Hearts', 'rank': 'K'},
            ],
        })

        msg = captured.get('message', '')
        assert 'Cards destroyed by AI defence:' in msg
        assert 'Cards looted by defending kingdom:' not in msg

    def test_conquer_defender_loss_dialogue_lists_lost_loot_and_returned_cards(self, monkeypatch):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        class _DummyCardImg:
            def __init__(self, *_args, **_kwargs):
                self.front_img = None

        monkeypatch.setattr('game.components.cards.card_img.CardImg', _DummyCardImg)

        captured = {}
        screen.window = object()
        screen.game = SimpleNamespace(invader=False, game_over=False, mode='conquer')
        screen.make_dialogue_box = lambda message, **kwargs: captured.update({
            'message': message,
            'kwargs': kwargs,
        })

        BattleScreen._handle_conquer_end(screen, {
            'conquer_result': 'attacker_won',
            'attacker_won': True,
            'loot_lost_cards': [
                {'suit': 'Spades', 'rank': '8'},
                {'suit': 'Hearts', 'rank': '3'},
            ],
        })

        msg = captured.get('message', '')
        assert 'Loot lost:' in msg
        assert '8 of Spades' in msg
        assert '3 of Hearts' in msg
        assert 'Every unlooted defence card returned' in msg

    def test_invader_swap_attacker_win_uses_original_attacker_identity(self):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        captured = {}
        screen.window = object()
        screen.game = SimpleNamespace(
            player_id=10,
            invader=False,
            game_over=False,
            mode='conquer',
            last_battle_result={
                'conquer_attacker_player_id': 10,
                'conquer_defender_player_id': 20,
            },
        )
        screen.make_dialogue_box = lambda message, **kwargs: captured.update({
            'message': message,
            'kwargs': kwargs,
        })

        BattleScreen._handle_conquer_end(screen, {
            'conquer_result': 'attacker_won',
            'attacker_won': True,
            'land_tier': 2,
        })

        assert captured['kwargs']['title'] == 'Land Conquered!'
        assert 'You have conquered' in captured['message']

    def test_try_resolve_server_finished_battle_handles_finished_conquer_draw(self):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        handled = []
        screen._battle_result = None
        screen.game = SimpleNamespace(
            mode='conquer',
            state='finished',
            winner_player_id=None,
            invader_player_id=88,
            land_tier=2,
            land_gold_rate=12,
            _last_polled_battle_result=None,
        )
        screen._handle_conquer_end = lambda result: handled.append(result)

        resolved = BattleScreen._try_resolve_server_finished_battle(screen)

        assert resolved is True
        assert len(handled) == 1
        assert handled[0]['conquer_result'] == 'draw'
        assert handled[0]['attacker_won'] is False
        assert screen._battle_result['conquer_result'] == 'draw'

    def test_try_resolve_server_finished_battle_prefers_explicit_cached_conquer_result(self):
        BattleScreen = _battle_screen_class()
        screen = BattleScreen.__new__(BattleScreen)

        handled = []
        screen._battle_result = None
        screen.game = SimpleNamespace(
            mode='conquer',
            state='active',
            winner_player_id=None,
            invader_player_id=9,
            land_tier=3,
            land_gold_rate=15,
            _last_polled_battle_result={
                'conquer_result': 'defender_won',
                'attacker_won': False,
            },
        )
        screen._handle_conquer_end = lambda result: handled.append(result)

        resolved = BattleScreen._try_resolve_server_finished_battle(screen)

        assert resolved is True
        assert len(handled) == 1
        assert handled[0]['conquer_result'] == 'defender_won'
        assert handled[0]['attacker_won'] is False
        assert screen._battle_result['conquer_result'] == 'defender_won'
